"""Run one R/D/S-u cell (arm × seed × budget) and print its per-cell summary.

With ``--preregistration FILE`` the run is gated: the engine's HEAD SHA (clean
checkout), ``--image-digest``, seed, budget and arm must match the file's fenced
block or nothing runs (exit 2, mismatches on stderr). Without it the cell is an
UNREGISTERED smoke run and is labelled so. The only producer wired here is the
synthetic one (results are never native evidence); the runtime lane binds the
native node-tar producer inside the controller with the same ``run_rds_cell`` and
the same gate.
"""

import argparse
import json
import sys
from pathlib import Path

from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.rds import (
    RdsArm,
    RdsCellAborted,
    RdsCellConfig,
    RVariant,
    VocabularyMode,
    run_rds_cell,
    summary_record,
)
from inodefence.evaluation.rds_preregistration import (
    CellRequest,
    PreregistrationFormatError,
    PreregistrationMismatch,
    load_preregistration,
    require_preregistered_cell,
)
from inodefence.generator import minimal_seed_corpus
from inodefence.provenance import capture_source

SYNTHETIC_LABEL = "synthetic cell — not native evidence"
UNREGISTERED_LABEL = "unregistered smoke run — not a preregistered experiment"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=tuple(arm.value for arm in RdsArm))
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--budget", type=int, required=True)
    parser.add_argument(
        "--vocabulary",
        choices=tuple(mode.value for mode in VocabularyMode),
        default=VocabularyMode.OBSERVED_NAMES.value,
        help="ignored under --preregistration (the file fixes it)",
    )
    parser.add_argument(
        "--r-variant",
        choices=tuple(variant.value for variant in RVariant),
        default=RVariant.WALK.value,
        help="ignored under --preregistration (the file fixes it)",
    )
    parser.add_argument("--preregistration", type=Path)
    parser.add_argument("--image-digest", help="sha256:<64 hex>; required with --preregistration")
    parser.add_argument("--producer", choices=("synthetic",), default="synthetic")
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args(argv)

    arm = RdsArm(args.arm)
    source = capture_source()
    engine = {"sha": source.revision, "dirty": source.dirty}
    labels = [SYNTHETIC_LABEL]
    gate: dict[str, object] | None = None
    if args.preregistration is None:
        labels.append(UNREGISTERED_LABEL)
        config = RdsCellConfig(
            arm, args.seed, args.budget, VocabularyMode(args.vocabulary), RVariant(args.r_variant)
        )
    else:
        try:
            preregistration = load_preregistration(args.preregistration)
            config = require_preregistered_cell(
                preregistration,
                CellRequest(
                    arm,
                    args.seed,
                    args.budget,
                    source.revision,
                    source.dirty,
                    args.image_digest,
                ),
            )
        except PreregistrationFormatError as error:
            print(f"preregistration unusable: {error}", file=sys.stderr)
            return 2
        except PreregistrationMismatch as error:
            print("refusing to run:", file=sys.stderr)
            for item in error.mismatches:
                print(f"  - {item}", file=sys.stderr)
            return 2
        gate = {
            "file": str(args.preregistration),
            "engine_sha": preregistration.engine_sha,
            "image_digest": preregistration.image_digest,
            "matched": True,
        }

    try:
        cell = run_rds_cell(minimal_seed_corpus(), synthetic_effect_result, config)
        summary = cell.summary
        returncode = 0
    except RdsCellAborted as error:
        summary = error.summary
        returncode = 1
    report = {
        "label": labels,
        "producer": args.producer,
        "engine": engine,
        "preregistration": gate,
        "summary": summary_record(summary),
    }
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="ascii")
        print(f"rds cell summary: {args.out}", file=sys.stderr)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())

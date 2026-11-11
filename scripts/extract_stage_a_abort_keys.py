"""Extract the sealed abort keys of benchmark Stage A jobs=2 blocks, for the host qualification.

A host qualification run (D047) stops on input dependence when an abort comes back at the same
(arm policy, seed, step index, case id) as a Stage A jobs=2 abort. Stage A raw exists on HOST1
only, so this writes one key file both hosts compare against:

    python -m scripts.extract_stage_a_abort_keys \\
        --block ~/inodefence-benchmarks/concurrency-scaling-v2/A/block-1-j2 \\
        --block ~/inodefence-benchmarks/concurrency-scaling-v2/A/block-4-j2 \\
        --design experiments/configs/concurrency-scaling-v2.md \\
        --out ~/inodefence-evidence/<dir>/stage-a-j2-abort-keys.json

Sealed: from ``block.json`` only cell metadata (arm label, seed, returncode, file names); from a
report only the ``aborted`` stub of a nonzero cell (step index and case id; the reason text is
not kept); from a steps file only ``index`` and ``case_id``. No oracle field is read or written.
The arm label is replaced by the design's search-policy string, so a launcher whose arm is named
``R`` matches Stage A's ``R-restart`` only when the policy strings are equal. The file must be
written outside the repository; its sha256 is printed for the record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scripts.compare_pilot_rerun_paths import (
    CellFiles,
    UnreadableReport,
    UnreadableSteps,
    read_abort,
    read_case_ids,
)
from scripts.run_concurrency_benchmark import BLOCK_FILE, load_design

SCHEMA = "inodefence-stage-a-abort-keys-v1"
RAW_DIR = "raw"


def path_sha256(case_ids: Sequence[str]) -> str:
    """One hash for a case-id sequence (input identifiers only)."""
    return hashlib.sha256("\n".join(case_ids).encode("utf-8")).hexdigest()


def extract(blocks: Sequence[Path], design_path: Path) -> dict[str, Any]:
    design = load_design(design_path)
    design_sha = hashlib.sha256(design_path.read_bytes()).hexdigest()
    policies = {arm.label: str(arm.search) for arm in design.arms}
    sources: list[dict[str, Any]] = []
    aborts: list[dict[str, Any]] = []
    for block in blocks:
        record_bytes = (block / BLOCK_FILE).read_bytes()
        record = json.loads(record_bytes)
        if record.get("design_sha256") != design_sha:
            raise ValueError(f"{block}: block ran under design {record.get('design_sha256')}")
        sources.append(
            {
                "block": block.name,
                "stage": record.get("stage"),
                "jobs": record.get("jobs"),
                "block_json_sha256": hashlib.sha256(record_bytes).hexdigest(),
            }
        )
        for cell in record["cells"]:
            if not cell.get("returncode"):
                continue
            label = cell["arm"]
            if label not in policies:
                raise ValueError(f"{block}: arm {label!r} is not in the design")
            files = CellFiles(
                label,
                policies[label],
                int(cell["seed"]),
                int(cell["returncode"]),
                block / RAW_DIR / cell["steps"],
                block / RAW_DIR / cell["report"],
            )
            stub = read_abort(files)
            if stub is None:
                continue
            case_ids = read_case_ids(files.steps) if files.steps and files.steps.is_file() else []
            aborts.append(
                {
                    "block": block.name,
                    "search_policy": policies[label],
                    "seed": files.seed,
                    "step_index": stub.step_index,
                    "case_id": stub.case_id,
                    "recorded_steps": len(case_ids),
                    "path_prefix_sha256": path_sha256(case_ids[: stub.step_index]),
                }
            )
    return {
        "schema": SCHEMA,
        "classification": "sealed Stage A jobs=2 abort keys: input identifiers only, no oracle",
        "design": {"file": design_path.name, "sha256": design_sha, "design_id": design.design_id},
        "mutation_policy": design.mutation_policy,
        "image_digest": design.image_digest,
        "budget": design.budget,
        "blocks": sources,
        "aborts": sorted(aborts, key=lambda a: (a["search_policy"], a["seed"], a["block"])),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--block", type=Path, action="append", required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1].resolve()
    target = args.out.expanduser().resolve()
    if target == repo_root or repo_root in target.parents:
        # The key file is evidence: only its sha256 and path go into the repository.
        print(f"{args.out}: --out must be outside the repository ({repo_root})", file=sys.stderr)
        return 2
    try:
        document = extract([block.expanduser() for block in args.block], args.design)
    except (OSError, ValueError, KeyError, UnreadableReport, UnreadableSteps) as error:
        print(f"no key file written: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    data = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(data)
    print(f"{hashlib.sha256(data).hexdigest()}  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""One command per target: run it at a version, judge C0/C1/C2, save the result and the inputs.

    make target-run TARGET=node-tar TAR_VERSION=7.5.2
    python scripts/run_target.py --target node-tar --version 7.5.2 --version 7.5.3 --out DIR

For each version this writes, under ``DIR/<target>-<version>/``:

- ``result.json``: the common ``inodefence-target-result-v1`` record
  (``inodefence.target_result``; label ``demo run``),
- ``inputs/<case>.tar``: every TAR that was extracted, named in ``repro_inputs`` with its SHA-256,
- ``raw/<case>.json``: the target's raw observation for that case, unchanged.

A version directory that already has a ``result.json`` is refused; nothing is overwritten.

Targets are registered in ``TARGETS``. Each entry is a target-specific adapter that lives here or
in its own repro module, never in the common format module. Only ``node-tar`` is registered so far.
Its mode is ``fixture-regression``: the same hand-built hard-link and symlink-write fixtures that
``make regression`` runs, sent through the same disposable-container path
(``experiments.repro.cross_release_identity.run_one``; the host is never the extraction target).
That path observes the post-extraction state of an external reference file beside ``extract/``.
It observes C1 (inode identity shared) and C2 (reference changed) but not C0, so C0 is ``null``
("not observed", never "no violation"). The version is a plain input; no release id or CVE id is
a decision condition. ``--dry-run`` writes nothing and runs no container.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.repro import cross_release_identity as cri
from scripts import regression_check as rc

from inodefence.target_result import (
    RUN_ERROR,
    CaseVerdict,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULT_NAME = "result.json"


@dataclass(frozen=True, slots=True)
class CaseRun:
    """One executed case: its input bytes, the target's raw observation, and the verdict."""

    verdict: CaseVerdict
    tar: bytes
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TargetAdapter:
    mode: ResultMode
    observed_contracts: tuple[str, ...]
    image_ref: Callable[[str], str | None]
    plan: Callable[[str], list[dict[str, Any]]]
    run: Callable[[str], list[CaseRun]]
    axes: Callable[[str], TargetAxes]


# ---- node-tar adapter (target-specific; reuses the make regression fixtures and engine) ----


def _node_tar_case(fixture: rc.RegressionFixture, raw: dict[str, Any]) -> CaseRun:
    row = rc.evaluate_fixture(fixture, raw)
    c1, c2 = row["c1_identity_shared"], row["c2_reference_changed"]
    # An unobservable C1/C2 is a failed observation, never a nonviolation.
    errored = row["outcome"] == "run_error" or c1 is None or c2 is None
    verdict = CaseVerdict(
        case_id=fixture.name,
        outcome=RUN_ERROR if errored else str(row["outcome"]),
        c0=None,
        c1=None if errored else c1,
        c2=None if errored else c2,
    )
    return CaseRun(verdict, fixture.tar, raw)


def _node_tar_run(version: str) -> list[CaseRun]:
    runs = []
    for fixture in rc.build_fixtures():
        raw = cri.run_one(version, base64.b64encode(fixture.tar).decode())
        runs.append(_node_tar_case(fixture, raw))
    return runs


NODE_TAR = TargetAdapter(
    mode=ResultMode.FIXTURE_REGRESSION,
    observed_contracts=("C1", "C2"),
    image_ref=lambda version: cri.IMAGE.format(release=version),
    plan=lambda version: rc.dry_run(version)["would_run"],
    run=_node_tar_run,
    axes=lambda version: TargetAxes(target_version=version),
)

TARGETS: dict[str, TargetAdapter] = {"node-tar": NODE_TAR}


# ---- target-independent command ----


def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()


def engine_provenance(image_ref: str | None) -> Provenance:
    """The engine revision that ran (HEAD + dirty flag) and the image's local id, when known."""
    sha = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no")
    image_id = None
    if image_ref is not None:
        try:
            done = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            image_id = done.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            image_id = None
    return Provenance(
        engine_sha=sha or None,
        engine_dirty=status is None or bool(status),
        image_ref=image_ref,
        image_id=image_id,
    )


def build_result(
    target: str,
    adapter: TargetAdapter,
    version: str,
    runs: list[CaseRun],
    provenance: Provenance,
) -> TargetResult:
    return TargetResult(
        target=target,
        axes=adapter.axes(version),
        mode=adapter.mode,
        observed_contracts=adapter.observed_contracts,
        cases=tuple(run.verdict for run in runs),
        repro_inputs=tuple(
            repro_input(run.verdict.case_id, f"inputs/{run.verdict.case_id}.tar", run.tar)
            for run in runs
        ),
        provenance=provenance,
    )


def write_result(out_dir: Path, result: TargetResult, runs: list[CaseRun]) -> Path:
    """Write inputs, raw observations, then result.json last (its presence means complete)."""
    result_path = out_dir / RESULT_NAME
    if result_path.exists():
        raise FileExistsError(f"refusing to overwrite {result_path}")
    (out_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    for run, item in zip(runs, result.repro_inputs, strict=True):
        (out_dir / item.tar_path).write_bytes(run.tar)
        raw_path = out_dir / "raw" / f"{run.verdict.case_id}.json"
        raw_path.write_text(json.dumps(run.raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result_path.write_text(result.dumps(), encoding="utf-8")
    return result_path


def summary_line(result: TargetResult) -> str:
    axes = result.axes
    axis = ",".join(
        f"{name}={value}"
        for name, value in (
            ("version", axes.target_version),
            ("runtime", axes.runtime_version),
            ("filter", axes.extraction_filter),
        )
        if value is not None
    )
    return (
        f"TARGET-RUN {result.verdict.value} target={result.target} {axis} "
        f"mode={result.mode.value} violating={len(result.violating_cases)}/{result.executed} "
        f"errored={result.errored} (demo run)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="run one target at fixed versions (demo run)")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--version", required=True, action="append", help="repeatable")
    parser.add_argument("--out", type=Path, help="output directory (required unless --dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    args = parser.parse_args(argv)
    for version in args.version:
        rc._validate_version(parser, version)
    if len(set(args.version)) != len(args.version):
        parser.error("each --version may be given once")
    adapter = TARGETS[args.target]

    if args.dry_run:
        plan = {
            "target": args.target,
            "mode": adapter.mode.value,
            "observed_contracts": list(adapter.observed_contracts),
            "versions": {
                v: {"image": adapter.image_ref(v), "would_run": adapter.plan(v)}
                for v in args.version
            },
            "note": "dry-run: no container executed, nothing written",
        }
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if args.out is None:
        parser.error("--out is required unless --dry-run")

    out_dirs = {v: args.out / f"{args.target}-{v}" for v in args.version}
    for out_dir in out_dirs.values():
        if (out_dir / RESULT_NAME).exists():
            parser.error(f"{out_dir / RESULT_NAME} already exists; choose another --out")

    worst = 0
    for version, out_dir in out_dirs.items():
        provenance = engine_provenance(adapter.image_ref(version))
        runs = adapter.run(version)
        result = build_result(args.target, adapter, version, runs, provenance)
        path = write_result(out_dir, result, runs)
        print(f"{summary_line(result)} -> {path}")
        worst = max(worst, {"PASS": 0, "FAIL": 1, "ERROR": 2}[result.verdict.value])
    return worst


if __name__ == "__main__":
    raise SystemExit(main())

"""One command per target: run it on fixed axes, judge C0/C1/C2, save the result and the inputs.

    make target-run TARGET=node-tar TARGET_VERSIONS="7.5.2 7.5.3"
    make target-run TARGET=python-tarfile TARGET_VERSIONS=3.12.16 TARGET_FILTERS=data
    python scripts/run_target.py --target node-tar --version 7.5.2 --version 7.5.3 --out DIR

A run is a list of cells. A cell is one fixed point on the target's axes
(``inodefence.target_result.TargetAxes``: ``target_version`` / ``runtime_version`` /
``extraction_filter``). ``--version`` is the target's version axis (node-tar: the package
version -> ``target_version``; python-tarfile: the exact interpreter ``X.Y.Z`` ->
``runtime_version``); ``--extraction-filter`` is the filter axis for targets that have one.
One invocation varies at most one axis: several ``--version`` together with several
``--extraction-filter`` is refused, so a configuration comparison and a version comparison never
mix in one run. For each cell this writes, under ``DIR/<cell dirname>/``:

- ``result.json``: the common ``inodefence-target-result-v1`` record
  (``inodefence.target_result``; label ``demo run``),
- ``inputs/<case>.tar``: every TAR that was extracted, named in ``repro_inputs`` with its SHA-256,
- ``raw/<case>.json``: the target's raw observation for that case, unchanged.

A cell directory that already has a ``result.json`` is refused; nothing is overwritten.

Targets are registered in ``TARGETS`` as ``"module:ATTRIBUTE"`` and loaded on use. Each entry is
a target-specific ``TargetAdapter`` that lives here or in its own module, never in the common
format module. ``node-tar`` (below) and ``python-tarfile``
(``scripts.run_python_tarfile_target.ADAPTER``) are registered. Both run in mode
``fixture-regression``: the same hand-built hard-link and symlink-write fixtures that
``make regression`` runs, each extracted in a disposable container (the host is never the
extraction target) that observes the post-extraction state of an external reference file beside
``extract/``. That observes C1 (inode identity shared) and C2 (reference changed) but not C0, so
C0 is ``null`` ("not observed", never "no violation"). Versions and filters are plain inputs; no
release id or CVE id is a decision condition. ``--dry-run`` writes nothing and runs no container.
"""

from __future__ import annotations

import argparse
import base64
import importlib
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
class RunCell:
    """One fixed point on the target's axes: where its result goes and which image runs it."""

    dirname: str
    axes: TargetAxes
    image_ref: str | None


@dataclass(frozen=True, slots=True)
class TargetAdapter:
    """What a target supplies. ``cells`` validates the axis values (``ValueError`` if invalid)."""

    mode: ResultMode
    observed_contracts: tuple[str, ...]
    cells: Callable[[list[str], list[str]], list[RunCell]]
    plan: Callable[[RunCell], list[dict[str, Any]]]
    run: Callable[[RunCell], list[CaseRun]]


def fixture_case(fixture: rc.RegressionFixture, raw: dict[str, Any]) -> CaseRun:
    """Judge one regression fixture from a raw observation (shared by fixture-regression targets).

    An unobservable C1/C2 is a failed observation, never a nonviolation.
    """
    row = rc.evaluate_fixture(fixture, raw)
    c1, c2 = row["c1_identity_shared"], row["c2_reference_changed"]
    errored = row["outcome"] == "run_error" or c1 is None or c2 is None
    verdict = CaseVerdict(
        case_id=fixture.name,
        outcome=RUN_ERROR if errored else str(row["outcome"]),
        c0=None,
        c1=None if errored else c1,
        c2=None if errored else c2,
    )
    return CaseRun(verdict, fixture.tar, raw)


def fixture_plan() -> list[dict[str, Any]]:
    return [
        {"fixture": f.name, "kind": f.kind, "tar_bytes": len(f.tar)} for f in rc.build_fixtures()
    ]


# ---- node-tar adapter (target-specific; reuses the make regression fixtures and engine) ----


def _node_tar_cells(versions: list[str], filters: list[str]) -> list[RunCell]:
    if filters:
        raise ValueError("node-tar has no extraction-filter axis; drop --extraction-filter")
    for version in versions:
        if rc._VERSION_RE.fullmatch(version) is None:
            raise ValueError(f"node-tar --version must be dotted numeric, e.g. 7.5.2: {version!r}")
    return [
        RunCell(
            dirname=f"node-tar-{v}",
            axes=TargetAxes(target_version=v),
            image_ref=cri.IMAGE.format(release=v),
        )
        for v in versions
    ]


def _node_tar_run(cell: RunCell) -> list[CaseRun]:
    version = cell.axes.target_version
    assert version is not None
    runs = []
    for fixture in rc.build_fixtures():
        raw = cri.run_one(version, base64.b64encode(fixture.tar).decode())
        runs.append(fixture_case(fixture, raw))
    return runs


NODE_TAR = TargetAdapter(
    mode=ResultMode.FIXTURE_REGRESSION,
    observed_contracts=("C1", "C2"),
    cells=_node_tar_cells,
    plan=lambda cell: fixture_plan(),
    run=_node_tar_run,
)

# Adding a target: write a module with a TargetAdapter, then add one line here.
TARGETS: dict[str, str] = {
    "node-tar": "scripts.run_target:NODE_TAR",
    "python-tarfile": "scripts.run_python_tarfile_target:ADAPTER",
    "oras-go": "scripts.run_oras_go_target:ADAPTER",
    "decompress": "scripts.run_decompress_target:ADAPTER",
}


def load_adapter(target: str) -> TargetAdapter:
    module_name, _, attribute = TARGETS[target].partition(":")
    if module_name == __name__ or (module_name == "scripts.run_target" and __name__ == "__main__"):
        return globals()[attribute]
    return getattr(importlib.import_module(module_name), attribute)


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
    cell: RunCell,
    runs: list[CaseRun],
    provenance: Provenance,
) -> TargetResult:
    return TargetResult(
        target=target,
        axes=cell.axes,
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
    parser = argparse.ArgumentParser(description="run one target on fixed axes (demo run)")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument(
        "--version",
        required=True,
        action="append",
        help="the target's version axis (node-tar package / python-tarfile runtime); repeatable",
    )
    parser.add_argument(
        "--extraction-filter",
        action="append",
        default=[],
        help="extraction-filter axis, for targets that have one; repeatable",
    )
    parser.add_argument("--out", type=Path, help="output directory (required unless --dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    args = parser.parse_args(argv)
    versions, filters = args.version, args.extraction_filter
    if len(set(versions)) != len(versions) or len(set(filters)) != len(filters):
        parser.error("each --version / --extraction-filter may be given once")
    if len(versions) > 1 and len(filters) > 1:
        parser.error(
            "vary one axis per run: several --version with one --extraction-filter, "
            "or one --version with several --extraction-filter"
        )
    adapter = load_adapter(args.target)
    try:
        cells = adapter.cells(versions, filters)
    except ValueError as error:
        parser.error(str(error))

    if args.dry_run:
        plan = {
            "target": args.target,
            "mode": adapter.mode.value,
            "observed_contracts": list(adapter.observed_contracts),
            "cells": {
                cell.dirname: {
                    "axes": {
                        "target_version": cell.axes.target_version,
                        "runtime_version": cell.axes.runtime_version,
                        "extraction_filter": cell.axes.extraction_filter,
                    },
                    "image": cell.image_ref,
                    "would_run": adapter.plan(cell),
                }
                for cell in cells
            },
            "note": "dry-run: no container executed, nothing written",
        }
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if args.out is None:
        parser.error("--out is required unless --dry-run")

    for cell in cells:
        if (args.out / cell.dirname / RESULT_NAME).exists():
            parser.error(
                f"{args.out / cell.dirname / RESULT_NAME} already exists; choose another --out"
            )

    worst = 0
    for cell in cells:
        runs = adapter.run(cell)
        # After the run, so image_id names the image that was pulled and actually used.
        provenance = engine_provenance(cell.image_ref)
        result = build_result(args.target, adapter, cell, runs, provenance)
        path = write_result(args.out / cell.dirname, result, runs)
        print(f"{summary_line(result)} -> {path}")
        worst = max(worst, {"PASS": 0, "FAIL": 1, "ERROR": 2}[result.verdict.value])
    return worst


if __name__ == "__main__":
    raise SystemExit(main())

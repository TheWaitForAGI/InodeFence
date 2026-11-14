"""Python tarfile target run: isolated run -> C1/C2 judgment -> common result file (demo run).

    python -m scripts.run_python_tarfile_target --runtime-version 3.12.16 \
        --extraction-filter fully_trusted --extraction-filter data --out DIR
    python -m scripts.run_python_tarfile_target --runtime-version 3.12.10 \
        --runtime-version 3.12.16 --extraction-filter data --out DIR

Python tarfile has two independent axes, recorded in separate ``axes`` fields of
``inodefence-target-result-v1``:

- ``extraction_filter`` (``fully_trusted`` vs ``data``) on one fixed runtime: a configuration
  comparison of the same library. It is not a comparison between versions.
- ``runtime_version`` (exact ``X.Y.Z``) under one fixed filter: an interpreter-version comparison.

One invocation varies at most one axis; giving several values for both is refused, so the two
comparisons never mix in one run. ``target_version`` stays ``null`` (the library ships with the
runtime; its version is the runtime version).

Mode is ``fixture-regression`` with the same hand-built hard-link and symlink-write fixtures that
``make regression`` sends to node-tar (``scripts.regression_check.build_fixtures``), each extracted
in a fresh ``python:<runtime>-slim`` container (``experiments.repro.python_tarfile_identity``) in
the same ``extract/`` + ``ext/reference.bin`` layout. That path observes C1 and C2, not C0, so C0
is ``null`` ("not observed"). For each (runtime, filter) cell this writes, under
``DIR/python-tarfile-py<runtime>-<filter>/``: ``result.json``, ``inputs/<case>.tar``,
``raw/<case>.json``. Existing results are never overwritten. ``--dry-run`` runs nothing.

The output layout, the no-overwrite rule and the provenance (engine HEAD, dirty flag, local image
id) are the node-tar command's own (``scripts.run_target``), imported unchanged. ``run_target``
takes one version per target, so Python's two axes run through this command until it grows a
filter argument.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.repro import python_tarfile_identity as pti
from scripts import regression_check as rc
from scripts.run_target import RESULT_NAME, CaseRun, engine_provenance, write_result

from inodefence.target_result import (
    RUN_ERROR,
    CaseVerdict,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)

TARGET = "python-tarfile"
MODE = ResultMode.FIXTURE_REGRESSION
OBSERVED = ("C1", "C2")


@dataclass(frozen=True, slots=True)
class Cell:
    """One configuration: a fixed runtime and a fixed extraction filter."""

    runtime_version: str
    extraction_filter: str

    @property
    def axes(self) -> TargetAxes:
        return TargetAxes(
            target_version=None,
            runtime_version=self.runtime_version,
            extraction_filter=self.extraction_filter,
        )

    @property
    def dirname(self) -> str:
        return f"{TARGET}-py{self.runtime_version}-{self.extraction_filter}"


def compared_axis(runtimes: list[str], filters: list[str]) -> str | None:
    """Which single axis this invocation varies; refuses to vary both."""
    if len(runtimes) > 1 and len(filters) > 1:
        raise ValueError(
            "vary one axis per run: several --runtime-version with one --extraction-filter, "
            "or one --runtime-version with several --extraction-filter"
        )
    if len(runtimes) > 1:
        return "runtime_version"
    if len(filters) > 1:
        return "extraction_filter"
    return None


def case_from_raw(fixture: rc.RegressionFixture, raw: dict[str, Any]) -> CaseRun:
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


def run_cell(cell: Cell, *, runner: pti.Runner = subprocess.run) -> list[CaseRun]:
    runs = []
    for fixture in rc.build_fixtures():
        raw = pti.run_one(
            cell.runtime_version,
            cell.extraction_filter,
            base64.b64encode(fixture.tar).decode(),
            runner=runner,
        )
        runs.append(case_from_raw(fixture, raw))
    return runs


def build_result(cell: Cell, runs: list[CaseRun], prov: Provenance) -> TargetResult:
    return TargetResult(
        target=TARGET,
        axes=cell.axes,
        mode=MODE,
        observed_contracts=OBSERVED,
        cases=tuple(run.verdict for run in runs),
        repro_inputs=tuple(
            repro_input(run.verdict.case_id, f"inputs/{run.verdict.case_id}.tar", run.tar)
            for run in runs
        ),
        provenance=prov,
    )


def summary_line(result: TargetResult) -> str:
    return (
        f"TARGET-RUN {result.verdict.value} target={result.target} "
        f"runtime={result.axes.runtime_version} filter={result.axes.extraction_filter} "
        f"mode={result.mode.value} violating={len(result.violating_cases)}/{result.executed} "
        f"errored={result.errored} (demo run)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="run Python tarfile in a container (demo run)")
    parser.add_argument(
        "--runtime-version", required=True, action="append", help="exact X.Y.Z; repeatable"
    )
    parser.add_argument("--extraction-filter", required=True, action="append", choices=pti.FILTERS)
    parser.add_argument("--out", type=Path, help="output directory (required unless --dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    args = parser.parse_args(argv)
    runtimes, filters = args.runtime_version, args.extraction_filter
    for runtime in runtimes:
        if pti.RUNTIME_RE.fullmatch(runtime) is None:
            parser.error(f"--runtime-version must be exact X.Y.Z, got {runtime!r}")
    if len(set(runtimes)) != len(runtimes) or len(set(filters)) != len(filters):
        parser.error("each --runtime-version / --extraction-filter may be given once")
    try:
        axis = compared_axis(runtimes, filters)
    except ValueError as error:
        parser.error(str(error))
    cells = [Cell(r, f) for r in runtimes for f in filters]
    fixed = (
        {"extraction_filter": filters[0]}
        if axis == "runtime_version"
        else {"runtime_version": runtimes[0]}
        if axis == "extraction_filter"
        else {"runtime_version": runtimes[0], "extraction_filter": filters[0]}
    )

    if args.dry_run:
        plan = {
            "target": TARGET,
            "mode": MODE.value,
            "observed_contracts": list(OBSERVED),
            "compared_axis": axis,
            "fixed_axes": fixed,
            "cells": {
                c.dirname: {
                    "image": pti.image_ref(c.runtime_version),
                    "would_run": [
                        {"fixture": f.name, "kind": f.kind, "tar_bytes": len(f.tar)}
                        for f in rc.build_fixtures()
                    ],
                }
                for c in cells
            },
            "note": "dry-run: no container executed, nothing written",
        }
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if args.out is None:
        parser.error("--out is required unless --dry-run")
    for cell in cells:
        if (args.out / cell.dirname / RESULT_NAME).exists():
            parser.error(f"{args.out / cell.dirname / RESULT_NAME} already exists")

    print(f"COMPARE axis={axis} fixed={json.dumps(fixed, sort_keys=True)} (demo run)")
    worst = 0
    for cell in cells:
        runs = run_cell(cell)
        # After the run, so image_id names the image that was pulled and actually used.
        prov = engine_provenance(pti.image_ref(cell.runtime_version))
        result = build_result(cell, runs, prov)
        path = write_result(args.out / cell.dirname, result, runs)
        print(f"{summary_line(result)} -> {path}")
        worst = max(worst, {"PASS": 0, "FAIL": 1, "ERROR": 2}[result.verdict.value])
    return worst


if __name__ == "__main__":
    raise SystemExit(main())

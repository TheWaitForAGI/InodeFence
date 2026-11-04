"""Measure the per-case fresh-container path and the worker pool side by side.

This is EXP-0 measurement 4: run the *same* ``version x arm x seed`` matrix twice,
once with each execution method, and report their throughput next to each other
together with the G1 parity verdict per cell. It changes no isolation: both methods
use the locked harness, the same pinned image and the same contained-target policy
as ``make demo``. The only thing that varies is which execution mechanism runs the
campaigns -- a controller per cell (the existing parallel path) versus a pre-started
pool of workers each pinned to one campaign.

The analysis is pure and lives in :mod:`inodefence.evaluation.throughput`; the two
Docker-backed method runners live with the worker pool (they both must emit the
canonical per-case evidence the parity extractor reads). Until that lands this script
plans the matrix (``--plan``, no Docker) and wires the pure measurement, so the
orchestration is testable without executing anything.

Usage (host terminal, once the worker pool lands):

    PYTHONPATH=src python3.12 -m scripts.measure_worker_pool_throughput \
        --mode demo --seeds 123,456,789 --arm default --budget 20 --jobs 3 \
        --output ~/inodefence-evidence/<new-dir>

    # plan only, no Docker:
    PYTHONPATH=src python3.12 -m scripts.measure_worker_pool_throughput \
        --mode demo --seeds 123,456 --arm default --budget 20 --plan
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from scripts.run_parallel_native import MAX_BUDGET, MODES, Arm, Cell, build_cells, parse_arm

from inodefence.evaluation.execution_parity import ParitySubject
from inodefence.evaluation.throughput import MethodMeasurement, build_comparison, render_report

# One method's measured run of the whole matrix: its aggregate timing plus the
# per-cell parity subject (keyed by Cell.run_id) the parity extractor consumes.
MethodResult = tuple[MethodMeasurement, dict[str, ParitySubject]]


class MethodRunner(Protocol):
    """Runs the matrix with one execution method and returns its measured result."""

    def __call__(self, cells: Sequence[Cell], output_dir: Path) -> MethodResult: ...


def plan_cells(
    mode: str,
    versions: Sequence[str | None],
    arms: Sequence[Arm],
    seeds: Sequence[int],
    budget: int,
) -> list[Cell]:
    """The matrix both methods run; identical planning to the parallel native runner."""
    return build_cells(mode, versions, arms, seeds, budget)


def measure(
    cells: Sequence[Cell],
    per_case_runner: MethodRunner,
    worker_pool_runner: MethodRunner,
    output_dir: Path,
) -> dict[str, object]:
    """Run both methods on the same matrix and build the side-by-side report.

    The per-case run is the parity baseline; the worker pool is the candidate. Each
    runner writes its own evidence under a method subdirectory of ``output_dir`` and
    returns its aggregate timing and per-cell parity subjects.
    """
    per_case_dir = output_dir / "per-case"
    worker_pool_dir = output_dir / "worker-pool"
    per_case_measurement, per_case_subjects = per_case_runner(cells, per_case_dir)
    worker_pool_measurement, worker_pool_subjects = worker_pool_runner(cells, worker_pool_dir)
    comparison = build_comparison(
        per_case_measurement, worker_pool_measurement, per_case_subjects, worker_pool_subjects
    )
    return render_report(comparison)


def _comma_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--versions", type=_comma_list, default=[], help="demo-historical only")
    parser.add_argument("--seeds", type=_comma_list, default=["123"], help="RNG seeds, comma list")
    parser.add_argument(
        "--arm", dest="arms", action="append", default=[], help="'default' or LABEL=SEARCH/MUTATION"
    )
    parser.add_argument("--budget", type=int, default=20, help=f"1..{MAX_BUDGET} (default 20)")
    parser.add_argument("--jobs", type=int, default=3, help="max concurrent campaigns per method")
    parser.add_argument("--output", type=Path, default=None, help="new evidence directory")
    parser.add_argument(
        "--plan", action="store_true", help="print the planned matrix and exit (no Docker)"
    )
    return parser.parse_args(argv)


def _resolve_cells(args: argparse.Namespace) -> list[Cell]:
    if not 1 <= args.budget <= MAX_BUDGET:
        raise SystemExit(f"--budget must be in 1..{MAX_BUDGET}")
    try:
        seeds = [int(seed) for seed in args.seeds]
    except ValueError as error:
        raise SystemExit("--seeds must be integers") from error
    if not seeds:
        raise SystemExit("--seeds must list at least one seed")
    if args.mode == "demo-historical" and not args.versions:
        raise SystemExit("demo-historical requires --versions (e.g. 7.5.2,7.5.3)")
    if args.mode == "demo" and args.versions:
        raise SystemExit("demo runs the pinned node-tar; do not pass --versions")
    try:
        arms = [parse_arm(spec) for spec in (args.arms or ["default"])]
    except ValueError as error:
        raise SystemExit(str(error)) from error
    versions: list[str | None] = list(args.versions) if args.mode == "demo-historical" else [None]
    try:
        return build_cells(args.mode, versions, arms, seeds, args.budget)
    except ValueError as error:
        raise SystemExit(str(error)) from error


def _build_runners(jobs: int) -> tuple[MethodRunner, MethodRunner]:
    """Load the two Docker-backed method runners from the worker pool module.

    Both runners live with the worker pool because both must emit the canonical
    per-case evidence (steps, resets, isolation) the parity extractor reads. This
    import fails until that module lands; ``--plan`` never reaches here.
    """
    try:
        # Forward reference to the worker pool module landing in this lane's step 4.
        from inodefence.execution import worker_pool  # pyright: ignore[reportAttributeAccessIssue]
    except ImportError as error:
        raise SystemExit(
            "worker pool method runners are not available yet "
            "(inodefence.execution.worker_pool.measurement_runners); "
            "run with --plan to inspect the matrix, or land the worker pool first"
        ) from error
    return worker_pool.measurement_runners(jobs)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    cells = _resolve_cells(args)

    if args.plan:
        print(f"mode={args.mode} jobs={args.jobs} budget={args.budget} cells={len(cells)}")
        for cell in cells:
            print(f"  {cell.run_id}: seed={cell.seed} arm={cell.arm.label} version={cell.version}")
        return 0

    if args.output is None:
        raise SystemExit("--output is required unless --plan")
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise SystemExit(f"output directory is not empty, refusing to mix results: {args.output}")

    per_case_runner, worker_pool_runner = _build_runners(args.jobs)
    report = measure(cells, per_case_runner, worker_pool_runner, args.output)
    report_path = args.output / "throughput-parity.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = report["summary"]
    assert isinstance(summary, dict)
    print(
        f"done: speedup x{summary['speedup']} over {summary['cells_compared']} cells; "
        f"parity {'PASS' if summary['parity_passed'] else 'FAIL'}; report {report_path}"
    )
    return 0 if summary["parity_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

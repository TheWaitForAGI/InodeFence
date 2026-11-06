"""Plan (and, with a Docker slot, launch) the worker-pool run of a campaign matrix.

Each matrix cell becomes one worker: a dedicated controller container + runtime volume
(campaign = worker, 1:1), named with the ``s3wp-`` tag so concurrent workers never share
a writable path. This reuses the existing ``run_parallel_native`` planning and the
``container_host`` ``--controller/--volume`` bring-up path, so no isolation flag is
re-spelled and R4 is untouched.

``--dry-run`` prints the planned bring-up (per-worker run id, controller, volume, mount
and environment) and launches nothing -- the validation path for this stacked PR. The
actual Docker run and the worker-pool-vs-per-case parity judgement happen on the
integration base (``claude/s3-wp-integration``) once a Docker slot is assigned; this
script refuses to launch otherwise.

Usage (host terminal, plan only):

    PYTHONPATH=src python3.12 -m scripts.run_worker_pool \
        --mode demo --seeds 123,456 --arm default --budget 50 --dry-run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.run_parallel_native import MAX_BUDGET, MODES, build_cells, cell_env, parse_arm

from inodefence.execution.worker_pool import plan_worker_bringup


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
    parser.add_argument("--budget", type=int, default=50, help=f"1..{MAX_BUDGET} (default 50)")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the planned worker bring-up and exit"
    )
    return parser.parse_args(argv)


def plan_bringups(args: argparse.Namespace) -> list[dict[str, object]]:
    """The per-worker bring-up plan for the resolved matrix (no Docker)."""
    if not 1 <= args.budget <= MAX_BUDGET:
        raise SystemExit(f"--budget must be in 1..{MAX_BUDGET}")
    try:
        seeds = [int(seed) for seed in args.seeds]
    except ValueError as error:
        raise SystemExit("--seeds must be integers") from error
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
        cells = build_cells(args.mode, versions, arms, seeds, args.budget)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    placeholder_output = Path("~/inodefence-evidence/wp-parity-20261104").expanduser()
    return [
        plan_worker_bringup(cell.run_id, cell_env(cell, placeholder_output, {})).describe()
        for cell in cells
    ]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    bringups = plan_bringups(args)
    if not args.dry_run:
        raise SystemExit(
            "worker-pool launch needs an assigned Docker slot on the integration base "
            "(claude/s3-wp-integration); run with --dry-run to inspect the plan"
        )
    print(f"workers={len(bringups)} (campaign = worker, 1:1; each owns a dedicated volume)")
    for bringup in bringups:
        print(json.dumps(bringup, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

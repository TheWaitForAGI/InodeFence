"""Run many native node-tar effect campaigns in parallel on one host.

Each cell of a ``mode x version x arm x seed`` matrix runs
``scripts/local_node_tar_smoke.sh`` with a unique ``RUN_ID`` so that the
controller, runtime volume and evidence filename never collide; a semaphore
(``--jobs``) caps how many run at once (keep it small on a laptop, e.g. 3-4).
The shared images are built once up front (``BUILD_ONLY``) and every cell then
reuses them (``SKIP_BUILD``), so a cold build does not run N times at once.

This changes no isolation: every cell uses the same trusted non-root controller
and the same contained-target policy as a single ``make demo`` /
``make demo-native-historical`` run. The only thing the matrix varies is the
resource *names* and the campaign parameters (seed, budget, policy arm). Runs
only from the host terminal where Docker is available.

Usage (host terminal):

    PYTHONPATH=src python3.12 -m scripts.run_parallel_native \
        --mode demo-historical --versions 7.5.2,7.5.3 --seeds 123,456,789 \
        --arm default --budget 100 --jobs 3 \
        --output ~/inodefence-evidence/<new-dir>

    PYTHONPATH=src python3.12 -m scripts.run_parallel_native \
        --mode demo --seeds 123,456,789 \
        --arm p2-m1=P2_EFFECT_ADAPTIVE/M1 --budget 20 --jobs 3 \
        --output ~/inodefence-evidence/<new-dir>

An ``--arm`` is either ``default`` (the script's in-code policy defaults) or
``LABEL=SEARCH/MUTATION`` where SEARCH/MUTATION are EffectSearchPolicy /
MutationPolicy names (or ``-`` to keep that side's default). Results land in
``<output>/<run-id>.json`` (plus ``.steps.jsonl`` for ``demo``), each cell's
console log in ``<output>/<run-id>.log``, and a manifest in
``<output>/matrix.json``. Exit status is 0 only when every cell succeeds.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from time import monotonic

from inodefence.feedback import EffectSearchPolicy
from inodefence.mutator import MutationPolicy

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "local_node_tar_smoke.sh"
# Docker's own name grammar; shared with local_node_tar_smoke.sh's RUN_ID guard.
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
ARM_DEFAULT = "default"
MODES = ("demo", "demo-historical")
MAX_BUDGET = 100


@dataclass(frozen=True, slots=True)
class Arm:
    """A named (search policy, mutation policy) pair; ``None`` keeps the default."""

    label: str
    search: str | None
    mutation: str | None


@dataclass(frozen=True, slots=True)
class Cell:
    """One campaign in the matrix."""

    mode: str
    version: str | None
    arm: Arm
    seed: int
    budget: int

    @property
    def run_id(self) -> str:
        token = f"{self.version or 'native'}-{self.arm.label}-s{self.seed}"
        if not TOKEN.fullmatch(token):
            raise ValueError(f"run id is not a valid resource name: {token!r}")
        return token

    @property
    def evidence_basename(self) -> str:
        stem = "effect-demo-native" if self.mode == "demo" else "effect-demo-historical"
        return f"inodefence-{stem}-{self.run_id}"


def _resolve_policy(name: str, enum: type[StrEnum]) -> str:
    """Accept an enum member name or its value; return the canonical value string."""
    try:
        return enum[name].value
    except KeyError:
        pass
    try:
        return enum(name).value
    except ValueError:
        choices = ", ".join(member.name for member in enum)
        raise ValueError(f"unknown {enum.__name__} {name!r}; choose from: {choices}") from None


def parse_arm(spec: str) -> Arm:
    """Parse ``default`` or ``LABEL=SEARCH/MUTATION`` into an :class:`Arm`."""
    if spec == ARM_DEFAULT:
        return Arm(ARM_DEFAULT, None, None)
    label, sep, rest = spec.partition("=")
    if not sep or "/" not in rest:
        raise ValueError(f"arm must be 'default' or 'LABEL=SEARCH/MUTATION', got {spec!r}")
    if not TOKEN.fullmatch(label):
        raise ValueError(f"arm label is not a valid resource name: {label!r}")
    search_name, _, mutation_name = rest.partition("/")

    def side(name: str, enum: type[StrEnum]) -> str | None:
        name = name.strip()
        if name in ("", "-", ARM_DEFAULT):
            return None
        return _resolve_policy(name, enum)

    return Arm(label, side(search_name, EffectSearchPolicy), side(mutation_name, MutationPolicy))


def build_cells(
    mode: str,
    versions: Sequence[str | None],
    arms: Sequence[Arm],
    seeds: Sequence[int],
    budget: int,
) -> list[Cell]:
    """Cartesian product version x arm x seed; run ids within a matrix are unique."""
    cells = [
        Cell(mode, version, arm, seed, budget)
        for version in versions
        for arm in arms
        for seed in seeds
    ]
    run_ids = [cell.run_id for cell in cells]
    duplicates = sorted({rid for rid in run_ids if run_ids.count(rid) > 1})
    if duplicates:
        raise ValueError(f"duplicate run ids in matrix (arm labels must differ): {duplicates}")
    return cells


def cell_env(cell: Cell, output_dir: Path, base_env: dict[str, str]) -> dict[str, str]:
    """Environment for one cell: unique names, reused images, campaign parameters."""
    env = dict(base_env)
    env["RUN_ID"] = cell.run_id
    env["SKIP_BUILD"] = "1"
    env.pop("BUILD_ONLY", None)
    env["INODEFENCE_EVIDENCE_DIR"] = str(output_dir)
    env["DEMO_SEED"] = str(cell.seed)
    env["DEMO_BUDGET"] = str(cell.budget)
    if cell.arm.search is not None:
        env["DEMO_POLICY"] = cell.arm.search
    else:
        env.pop("DEMO_POLICY", None)
    if cell.arm.mutation is not None:
        env["DEMO_MUTATION_POLICY"] = cell.arm.mutation
    else:
        env.pop("DEMO_MUTATION_POLICY", None)
    if cell.mode == "demo-historical":
        assert cell.version is not None
        env["TAR_VERSION"] = cell.version
    else:
        env.pop("TAR_VERSION", None)
    return env


@dataclass(slots=True)
class CellResult:
    cell: Cell
    returncode: int
    wall_seconds: float
    evidence: Path
    evidence_exists: bool
    log: Path


def _run_cell(cell: Cell, output_dir: Path, base_env: dict[str, str], bash: str) -> CellResult:
    env = cell_env(cell, output_dir, base_env)
    evidence = output_dir / f"{cell.evidence_basename}.json"
    log = output_dir / f"{cell.run_id}.log"
    started = monotonic()
    with log.open("w", encoding="utf-8") as stream:
        completed = subprocess.run(
            [bash, str(SCRIPT), cell.mode],
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return CellResult(
        cell=cell,
        returncode=completed.returncode,
        wall_seconds=monotonic() - started,
        evidence=evidence,
        evidence_exists=evidence.is_file(),
        log=log,
    )


def _warmup(mode: str, output_dir: Path, base_env: dict[str, str], bash: str) -> int:
    """Build the shared images once before fanning out (BUILD_ONLY, no controller)."""
    env = dict(base_env)
    env["BUILD_ONLY"] = "1"
    env.pop("SKIP_BUILD", None)
    env.pop("RUN_ID", None)
    log = output_dir / "warmup.log"
    with log.open("w", encoding="utf-8") as stream:
        completed = subprocess.run(
            [bash, str(SCRIPT), mode],
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return completed.returncode


def _write_manifest(
    path: Path, args: argparse.Namespace, arms: Sequence[Arm], cells: Sequence[CellResult]
) -> None:
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "mode": args.mode,
        "jobs": args.jobs,
        "budget": args.budget,
        "versions": list(args.versions),
        "seeds": list(args.seeds),
        "arms": [{"label": a.label, "search": a.search, "mutation": a.mutation} for a in arms],
        "cells": [
            {
                "run_id": r.cell.run_id,
                "mode": r.cell.mode,
                "version": r.cell.version,
                "arm": r.cell.arm.label,
                "search": r.cell.arm.search,
                "mutation": r.cell.arm.mutation,
                "seed": r.cell.seed,
                "budget": r.cell.budget,
                "returncode": r.returncode,
                "wall_seconds": round(r.wall_seconds, 3),
                "evidence": r.evidence.name,
                "evidence_exists": r.evidence_exists,
                "log": r.log.name,
            }
            for r in cells
        ],
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _comma_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _prepare_output_dir(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit(f"output directory is not empty, refusing to mix results: {output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument(
        "--versions", type=_comma_list, default=[], help="demo-historical only, e.g. 7.5.2,7.5.3"
    )
    parser.add_argument("--seeds", type=_comma_list, default=["123"], help="RNG seeds, comma list")
    parser.add_argument(
        "--arm",
        dest="arms",
        action="append",
        default=[],
        help="'default' or LABEL=SEARCH/MUTATION (repeatable); defaults to 'default'",
    )
    parser.add_argument("--budget", type=int, default=20, help=f"1..{MAX_BUDGET} (default 20)")
    parser.add_argument("--jobs", type=int, default=3, help="max concurrent campaigns (default 3)")
    parser.add_argument("--output", type=Path, required=True, help="new/empty evidence directory")
    parser.add_argument("--python", default=None, help="host Python for the inner script (PYTHON)")
    parser.add_argument(
        "--context", default=None, help="Docker context (INODEFENCE_DOCKER_CONTEXT)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the planned matrix and exit (no Docker)"
    )
    args = parser.parse_args(argv)

    if not 1 <= args.budget <= MAX_BUDGET:
        parser.error(f"--budget must be in 1..{MAX_BUDGET}")
    if args.jobs < 1:
        parser.error("--jobs must be >= 1")
    try:
        seeds = [int(seed) for seed in args.seeds]
    except ValueError:
        parser.error("--seeds must be integers")
    if not seeds:
        parser.error("--seeds must list at least one seed")
    for version in args.versions:
        if not TOKEN.fullmatch(version):
            parser.error(f"version is not a valid tag/name: {version!r}")

    if args.mode == "demo-historical" and not args.versions:
        parser.error("demo-historical requires --versions (e.g. 7.5.2,7.5.3)")
    if args.mode == "demo" and args.versions:
        parser.error("demo runs the pinned repository node-tar; do not pass --versions")

    try:
        arms = [parse_arm(spec) for spec in (args.arms or [ARM_DEFAULT])]
    except ValueError as error:
        parser.error(str(error))
    versions: list[str | None] = list(args.versions) if args.mode == "demo-historical" else [None]
    args.versions = list(args.versions)
    args.seeds = seeds
    try:
        cells = build_cells(args.mode, versions, arms, seeds, args.budget)
    except ValueError as error:
        parser.error(str(error))

    if args.jobs > 4:
        print(
            f"warning: --jobs {args.jobs} is high for a laptop host (M5/32GB); 3-4 is safer.",
            file=sys.stderr,
        )

    base_env = dict(os.environ)
    if args.python:
        base_env["PYTHON"] = args.python
    if args.context:
        base_env["INODEFENCE_DOCKER_CONTEXT"] = args.context

    if args.dry_run:
        print(f"mode={args.mode} jobs={args.jobs} budget={args.budget} cells={len(cells)}")
        for cell in cells:
            env = cell_env(cell, args.output, base_env)
            extra = {
                k: env[k]
                for k in ("DEMO_POLICY", "DEMO_MUTATION_POLICY", "TAR_VERSION")
                if k in env
            }
            print(f"  {cell.run_id}: seed={cell.seed} budget={cell.budget} {extra}")
        return 0

    bash = shutil.which("bash")
    if bash is None:
        raise SystemExit("bash not found: the native matrix runs only on the host terminal")

    _prepare_output_dir(args.output)
    print(f"warmup: building shared images once (mode={args.mode})...", file=sys.stderr)
    warmup_rc = _warmup(args.mode, args.output, base_env, bash)
    if warmup_rc != 0:
        raise SystemExit(f"warmup build failed (rc={warmup_rc}); see {args.output / 'warmup.log'}")

    print(f"running {len(cells)} campaigns, up to {args.jobs} at a time...", file=sys.stderr)
    results: list[CellResult] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(_run_cell, cell, args.output, base_env, bash): cell for cell in cells
        }
        for future in futures:
            result = future.result()
            status = "ok" if result.returncode == 0 else f"FAILED rc={result.returncode}"
            print(
                f"  {result.cell.run_id}: {status} ({result.wall_seconds:.1f}s)"
                f"{'' if result.evidence_exists else ' [no evidence]'}",
                file=sys.stderr,
            )
            results.append(result)

    results.sort(key=lambda r: r.cell.run_id)
    manifest = args.output / "matrix.json"
    _write_manifest(manifest, args, arms, results)
    ok = sum(1 for r in results if r.returncode == 0 and r.evidence_exists)
    print(f"done: {ok}/{len(results)} cells ok; manifest {manifest}", file=sys.stderr)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

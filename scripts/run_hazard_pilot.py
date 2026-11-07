"""Driver of the exploratory hazard pilot (``exp3-hazard-pilot-v1``).

UNREGISTERED: labelled ``demo run``, never EXP-0/EXP-2/EXP-3 evidence and never pooled with
them. The design file is the single source of every parameter; this script has no parameter
flags, so what ran is what the committed design says.

Thin on purpose: each cell goes through the existing controller path
(``run_parallel_native.cell_env``, ``run_exp0.run_cell_with_watchdog``,
``run_exp0.wait_for_disk``). Nothing in the search, oracle, observer or isolation code is
touched or reimplemented. It exists because the existing drivers cannot run this plan:
``run_parallel_native`` caps budgets at 100, and ``run_g1_smoke`` runs one R variant at a time
and refuses its sentinel flags on a live run.

What it adds is only scheduling and clocks:

* seed-block order, with the arm order rotated per block, so a host fault or host drift is not
  confounded with one arm the way an arm-grouped order would be;
* per-cell CLOCK_REALTIME, CLOCK_MONOTONIC and CLOCK_MONOTONIC_RAW stamps, because this host's
  monotonic clock is not real time;
* no outcome in anything it writes outside the cell files, so progress can be read without
  seeing results (``--status``).

Layout under ``--output``::

    raw/<evidence>.json / .steps.jsonl / <run_id>.log   cell files (controller path)
    raw/attempts/                                        files of a no-record attempt
    raw/clocks.jsonl, raw/pilot.json, raw/matrix.json    schedule and clocks, no outcomes
    host/samples.jsonl                                   load, clocks, containers every 300 s
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from scripts.run_exp0 import archive_attempt, run_cell_with_watchdog, wait_for_disk
from scripts.run_g1_smoke import cell_paths
from scripts.run_parallel_native import Arm, Cell, cell_env

from inodefence.evaluation.rds import RdsArm, RdsCellConfig, RVariant, VocabularyMode
from inodefence.provenance import capture_source

LABELS = ("demo run", "exploratory hazard pilot (unregistered, not pooled, separate from EXP-2)")
MODE = "demo-historical"
FENCE_OPEN = "```hazard-pilot"
FENCE_CLOSE = "```"
ARM_PREFIX = "arm."
#: Pilot arm label -> the (RdsArm, RVariant) the design's search policy must realize.
ARM_CONFIG: Mapping[str, tuple[RdsArm, RVariant]] = {
    "R-walk": (RdsArm.R, RVariant.WALK),
    "R-restart": (RdsArm.R, RVariant.SEED_RESTART),
    "D": (RdsArm.D, RVariant.WALK),
    "S-u": (RdsArm.S_U, RVariant.WALK),
}
REQUIRED_KEYS = frozenset(
    {
        "design_id",
        "target_version",
        "image_digest",
        "docker_engine",
        "budget",
        "seeds",
        "mutation_policy",
        "vocabulary",
        "sentinel_generator_id",
        "sentinel_generator_seed",
        "sentinel_count",
        "observer_integrity_policy",
        "execution_mode",
        "jobs",
        "campaign_watchdog_seconds",
        "disk_pause_fraction",
    }
)
#: A cell that leaves no record at all may be retried once; nothing was observable from it, so
#: the retry cannot select on an outcome. A cell with any record is final.
MAX_ATTEMPTS = 2
#: Consecutive no-record cells that mean the infrastructure is down: stop starting new cells.
STOP_AFTER_NO_RECORD = 3
SAMPLE_SECONDS = 300.0
LOCAL_IMAGES = ("inodefence-controller:local", "inodefence-helper:local")


class DesignError(ValueError):
    """The design file is unusable; nothing runs."""


@dataclass(frozen=True, slots=True)
class PilotDesign:
    design_id: str
    target_version: str
    image_digest: str
    docker_engine: str
    budget: int
    seeds: tuple[int, ...]
    mutation_policy: str
    arms: tuple[Arm, ...]
    vocabulary: VocabularyMode
    sentinel_generator_id: str
    sentinel_generator_seed: int
    sentinel_count: int
    observer_integrity_policy: str
    execution_mode: str
    jobs: int
    campaign_watchdog_seconds: float
    disk_pause_fraction: float
    sha256: str

    def cell_config(self, cell: Cell) -> RdsCellConfig:
        arm, variant = ARM_CONFIG[cell.arm.label]
        return RdsCellConfig(arm, cell.seed, cell.budget, self.vocabulary, variant)


def _parse_block(text: str) -> dict[str, str]:
    lines = text.splitlines()
    try:
        start = lines.index(FENCE_OPEN)
    except ValueError:
        raise DesignError(f"no {FENCE_OPEN} block") from None
    values: dict[str, str] = {}
    for line in lines[start + 1 :]:
        if line.strip() == FENCE_CLOSE:
            return values
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not key or not value:
            raise DesignError(f"bad design line: {line!r}")
        if key in values:
            raise DesignError(f"duplicate design key: {key}")
        values[key] = value
    raise DesignError("hazard-pilot block is not closed")


def parse_design(text: str) -> PilotDesign:
    """Parse and validate the design block; every arm must realize its registered policy."""
    values = _parse_block(text)
    arm_values = {k[len(ARM_PREFIX) :]: v for k, v in values.items() if k.startswith(ARM_PREFIX)}
    plain = {k: v for k, v in values.items() if not k.startswith(ARM_PREFIX)}
    if set(plain) != REQUIRED_KEYS:
        missing = sorted(REQUIRED_KEYS - set(plain))
        unknown = sorted(set(plain) - REQUIRED_KEYS)
        raise DesignError(f"design keys differ: missing {missing}, unknown {unknown}")
    if set(arm_values) != set(ARM_CONFIG):
        raise DesignError(f"design arms {sorted(arm_values)} != {sorted(ARM_CONFIG)}")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", plain["image_digest"]) is None:
        raise DesignError("image_digest must be sha256:<64 hex>")
    seeds = tuple(int(item) for item in plain["seeds"].split(","))
    if len(set(seeds)) != len(seeds):
        raise DesignError("seeds must be unique")
    vocabulary = VocabularyMode(plain["vocabulary"])
    budget = int(plain["budget"])
    arms: list[Arm] = []
    for label, search in arm_values.items():
        arm, variant = ARM_CONFIG[label]
        config = RdsCellConfig(arm, seeds[0], budget, vocabulary, variant)
        if config.search_policy.value != search:
            raise DesignError(f"arm {label}: {search} is not {config.search_policy.value}")
        if config.mutation_policy.value != plain["mutation_policy"]:
            raise DesignError(f"arm {label}: vocabulary implies {config.mutation_policy.value}")
        arms.append(Arm(label, search, plain["mutation_policy"]))
    return PilotDesign(
        design_id=plain["design_id"],
        target_version=plain["target_version"],
        image_digest=plain["image_digest"],
        docker_engine=plain["docker_engine"],
        budget=budget,
        seeds=seeds,
        mutation_policy=plain["mutation_policy"],
        arms=tuple(arms),
        vocabulary=vocabulary,
        sentinel_generator_id=plain["sentinel_generator_id"],
        sentinel_generator_seed=int(plain["sentinel_generator_seed"]),
        sentinel_count=int(plain["sentinel_count"]),
        observer_integrity_policy=plain["observer_integrity_policy"],
        execution_mode=plain["execution_mode"],
        jobs=int(plain["jobs"]),
        campaign_watchdog_seconds=float(plain["campaign_watchdog_seconds"]),
        disk_pause_fraction=float(plain["disk_pause_fraction"]),
        sha256=sha256(text.encode("utf-8")).hexdigest(),
    )


def load_design(path: Path) -> PilotDesign:
    return parse_design(path.read_text(encoding="utf-8"))


def planned_cells(design: PilotDesign) -> list[Cell]:
    """Seed blocks in order; the arm order rotates by one position per block."""
    count = len(design.arms)
    return [
        Cell(
            MODE,
            design.target_version,
            design.arms[(block + offset) % count],
            seed,
            design.budget,
        )
        for block, seed in enumerate(design.seeds)
        for offset in range(count)
    ]


def clock_stamp() -> dict[str, float]:
    return {
        "realtime": time.clock_gettime(time.CLOCK_REALTIME),
        "monotonic": time.clock_gettime(time.CLOCK_MONOTONIC),
        "monotonic_raw": time.clock_gettime(time.CLOCK_MONOTONIC_RAW),
    }


def _docker(*args: str) -> str:
    done = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=60, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip()


def preflight(design: PilotDesign, expected_head: str) -> tuple[dict[str, Any], list[str]]:
    """Facts the run stands on, and the problems that refuse it."""
    source = capture_source()
    problems: list[str] = []
    if source.revision != expected_head:
        problems.append(f"checkout HEAD {source.revision} != expected {expected_head}")
    if source.dirty is not False:
        problems.append("checkout is not clean")
    facts: dict[str, Any] = {"checkout_head": source.revision, "checkout_dirty": source.dirty}
    try:
        server = _docker("version", "--format", "{{.Server.Version}}")
        image = f"inodefence-node-tar-effect:{design.target_version}"
        image_id = _docker("image", "inspect", image, "--format", "{{.Id}}")
        running = _docker("ps", "--format", "{{.Names}}").split()
        local = {
            name: _docker("image", "inspect", name, "--format", "{{.Id}}") for name in LOCAL_IMAGES
        }
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        return facts, [*problems, f"docker: {error}"]
    facts.update(docker_server=server, image_id=image_id, local_images=local)
    if server != design.docker_engine:
        problems.append(f"docker engine {server} != {design.docker_engine}")
    if image_id != design.image_digest:
        problems.append(f"{image} is {image_id}, not {design.image_digest}")
    if running:
        problems.append(f"other containers are running: {running}")
    return facts, problems


def base_environment(design: PilotDesign) -> dict[str, str]:
    env = dict(os.environ)
    env["DEMO_SENTINEL_SEED"] = str(design.sentinel_generator_seed)
    env["DEMO_SENTINEL_COUNT"] = str(design.sentinel_count)
    env["DEMO_OBSERVER_INTEGRITY_POLICY"] = design.observer_integrity_policy
    return env


def has_record(cell: Cell, raw: Path) -> bool:
    """A report, or a nonempty steps file: something outcome-bearing exists for this cell."""
    paths = cell_paths(cell, raw)
    steps = paths["steps_jsonl"]
    return paths["report"].is_file() or (steps.is_file() and steps.stat().st_size > 0)


def attempts_used(cell: Cell, raw: Path) -> int:
    """Attempts already made: archived logs plus a current log."""
    attempts = raw / "attempts"
    archived = len(list(attempts.glob(f"{cell.run_id}.attempt*.log"))) if attempts.is_dir() else 0
    return archived + (1 if cell_paths(cell, raw)["log"].exists() else 0)


class Schedule:
    """Runs cells through the controller path and records clocks; knows no outcomes."""

    def __init__(self, design: PilotDesign, raw: Path, bash: str) -> None:
        self.design = design
        self.raw = raw
        self.bash = bash
        self.base_env = base_environment(design)
        self.lock = threading.Lock()
        self.no_record_streak = 0
        self.stopped_reason: str | None = None

    def _append_clock(self, record: Mapping[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True)
        with self.lock, (self.raw / "clocks.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    def _note_cell_end(self, *, recorded: bool) -> None:
        """Count consecutive CELLS (not attempts) that ended without any record."""
        with self.lock:
            self.no_record_streak = 0 if recorded else self.no_record_streak + 1
            if self.no_record_streak >= STOP_AFTER_NO_RECORD and self.stopped_reason is None:
                self.stopped_reason = (
                    f"{STOP_AFTER_NO_RECORD} consecutive cells left no record; "
                    "infrastructure suspected, no new cell started"
                )

    def run_one(self, cell: Cell) -> dict[str, Any]:
        if has_record(cell, self.raw):
            return {"run_id": cell.run_id, "state": "final-from-earlier-invocation"}
        while True:
            if self.stopped_reason is not None:
                return {"run_id": cell.run_id, "state": "not-run"}
            used = attempts_used(cell, self.raw)
            if used >= MAX_ATTEMPTS:
                self._note_cell_end(recorded=False)
                return {"run_id": cell.run_id, "state": "no-record", "attempts": used}
            archive_attempt(cell, self.raw)
            wait_for_disk(self.raw, self.design.disk_pause_fraction)
            started = clock_stamp()
            result = run_cell_with_watchdog(
                cell,
                self.raw,
                cell_env(cell, self.raw, self.base_env),
                self.bash,
                limit_seconds=self.design.campaign_watchdog_seconds,
            )
            ended = clock_stamp()
            recorded = has_record(cell, self.raw)
            self._append_clock(
                {
                    "run_id": cell.run_id,
                    "arm": cell.arm.label,
                    "seed": cell.seed,
                    "attempt": used + 1,
                    "returncode": result.returncode,
                    "launcher_wall_seconds": result.wall_seconds,
                    "started": started,
                    "ended": ended,
                    "record_present": recorded,
                }
            )
            if recorded:
                self._note_cell_end(recorded=True)
                return {"run_id": cell.run_id, "state": "ran", "attempts": used + 1}


def sample_host(path: Path, stop: threading.Event) -> None:
    with path.open("a", encoding="utf-8") as stream:
        while True:
            try:
                containers = _docker("ps", "--format", "{{.Names}}").split()
            except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                containers = [f"error: {error}"]
            sample = {**clock_stamp(), "loadavg": os.getloadavg(), "containers": containers}
            stream.write(json.dumps(sample, sort_keys=True) + "\n")
            stream.flush()
            if stop.wait(SAMPLE_SECONDS):
                return


def print_plan(design: PilotDesign, cells: Sequence[Cell]) -> None:
    print(
        f"{design.design_id} sha256={design.sha256[:12]}… cells={len(cells)} "
        f"seeds={list(design.seeds)} budget={design.budget} jobs={design.jobs} "
        f"k={design.sentinel_count} image={design.image_digest[:19]}…"
    )
    for cell in cells:
        print(f"  {cell.run_id}: search={cell.arm.search}")


def print_status(raw: Path, total: int) -> int:
    """Progress and timing only: never reads a cell file, so no outcome can leak."""
    path = raw / "clocks.jsonl"
    records = (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if path.is_file()
        else []
    )
    finished = {record["run_id"] for record in records if record["record_present"]}
    nonzero = sum(1 for record in records if record["returncode"] != 0)
    print(
        f"finished {len(finished)}/{total}; attempts {len(records)}; nonzero exits {nonzero}; "
        f"no-record attempts {sum(1 for record in records if not record['record_present'])}"
    )
    if records:
        first = min(record["started"]["realtime"] for record in records)
        last = max(record["ended"]["realtime"] for record in records)
        print(f"real seconds first start -> last end: {last - first:.0f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-head", help="commit this checkout must be at (live run)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; no Docker")
    parser.add_argument("--status", action="store_true", help="progress only; no outcomes")
    args = parser.parse_args(argv)

    design = load_design(args.design)
    cells = planned_cells(design)
    raw: Path = args.output / "raw"
    if args.dry_run:
        print_plan(design, cells)
        return 0
    if args.status:
        return print_status(raw, len(cells))
    if not args.expected_head:
        parser.error("a live run needs --expected-head")
    facts, problems = preflight(design, args.expected_head)
    if problems:
        print("refusing to run:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    bash = shutil.which("bash")
    if bash is None:
        raise SystemExit("bash not found: the pilot runs only on the host terminal")
    raw.mkdir(parents=True, exist_ok=True)
    host = args.output / "host"
    host.mkdir(parents=True, exist_ok=True)
    pilot_record = {
        "label": list(LABELS),
        "design_file": args.design.name,
        "design_sha256": design.sha256,
        "created_at": datetime.now(UTC).isoformat(),
        "preflight": facts,
    }
    pilot_path = raw / "pilot.json"
    if pilot_path.is_file():
        earlier = json.loads(pilot_path.read_text(encoding="utf-8"))
        if earlier["design_sha256"] != design.sha256 or (
            earlier["preflight"]["checkout_head"] != facts["checkout_head"]
        ):
            print("refusing to run: this output was started under another design", file=sys.stderr)
            return 2
    else:
        pilot_path.write_text(json.dumps(pilot_record, indent=2, sort_keys=True) + "\n")
    stop_sampling = threading.Event()
    sampler = threading.Thread(
        target=sample_host, args=(host / "samples.jsonl", stop_sampling), daemon=True
    )
    sampler.start()
    schedule = Schedule(design, raw, bash)
    try:
        with ThreadPoolExecutor(max_workers=design.jobs) as pool:
            states = list(pool.map(schedule.run_one, cells))
    finally:
        stop_sampling.set()
        sampler.join(timeout=60)
    (raw / "matrix.json").write_text(
        json.dumps(
            {
                "label": list(LABELS),
                "design_sha256": design.sha256,
                "checkout_head": facts["checkout_head"],
                "created_at": datetime.now(UTC).isoformat(),
                "jobs": design.jobs,
                "stopped_reason": schedule.stopped_reason,
                "cells": states,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    ran = sum(1 for state in states if state["state"] != "not-run")
    print(f"cells with a final state: {ran}/{len(cells)}; stopped: {schedule.stopped_reason}")
    return 0 if ran == len(cells) and schedule.stopped_reason is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

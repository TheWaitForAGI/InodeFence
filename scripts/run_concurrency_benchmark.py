"""Driver of the concurrency scaling benchmark (``concurrency-scaling-v1``).

UNREGISTERED: labelled ``demo run``, never EXP-0/EXP-2/EXP-3 evidence and never pooled with
them. It asks one question: how many normally completed campaigns per real hour does this host
give at each concurrency level, while the results stay the same? The design file is the single
source of every parameter; only the number of concurrent campaigns differs between blocks.

Thin on purpose: each cell goes through the existing controller path
(``run_parallel_native.cell_env``, ``run_exp0.run_cell_with_watchdog``). Nothing in the search,
oracle, observer, isolation or execution code is touched or reimplemented.

What it adds:

* blocks per stage in the design's crossed order, for example jobs 2, 4, 4, 2;
* real-time stamps, because this host's monotonic clock is not real time;
* a light host sampler and a ``docker events`` log (no change to the engine under test);
* stop conditions, so an overloaded level ends early instead of wasting hours.

No outcome is written outside the cell files: ``block.json`` holds schedule, clocks and return
codes only, and the analysis script never reads oracle fields.

Layout under ``--output`` (refused inside the evidence tree or the repository)::

    <stage>/block-<n>-j<jobs>/preflight.json         design hash, checkout, approval reference
    <stage>/block-<n>-j<jobs>/raw/                   cell files (controller path)
    <stage>/block-<n>-j<jobs>/host/samples.jsonl     host samples
    <stage>/block-<n>-j<jobs>/host/events.jsonl      docker container lifecycle events
    <stage>/block-<n>-j<jobs>/block.json             schedule, clocks, return codes, stop reason
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from scripts.run_exp0 import WATCHDOG_RETURNCODE, disk_usage_fraction, run_cell_with_watchdog
from scripts.run_g1_smoke import cell_paths
from scripts.run_parallel_native import Arm, Cell, CellResult, cell_env

from inodefence.evaluation.rds import RdsArm, RdsCellConfig, RVariant, VocabularyMode
from inodefence.provenance import capture_source

LABELS = ("demo run", "concurrency benchmark (unregistered, not pooled, no oracle analysis)")
MODE = "demo-historical"
EXECUTION_MODE = "per-case-container"
FENCE_OPEN = "```concurrency-benchmark"
FENCE_CLOSE = "```"
ARM_PREFIX = "arm."
STAGE_PREFIX = "stage."
SMOKE_STAGE = "smoke"
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
        "smoke_budget",
        "smoke_seed",
        "mutation_policy",
        "vocabulary",
        "sentinel_generator_id",
        "sentinel_generator_seed",
        "sentinel_count",
        "observer_integrity_policy",
        "execution_mode",
        "campaign_watchdog_seconds",
        "disk_stop_fraction",
        "memory_stop_fraction",
        "stop_nonzero_cells",
        "preflight_load_fraction",
        "cooldown_seconds",
    }
)
#: Seeds this benchmark must never share: EXP-0, the hazard pilot and its checks, the proposed
#: EXP-3 block, and the existing exposure ranges. A new design must stay outside these too.
RESERVED_SEED_RANGES: tuple[tuple[int, int], ...] = (
    (0, 1415),
    (7001, 7002),
    (8001, 8003),
    (8101, 8110),
    (9001, 9999),
)
#: The pilot seeds a design may measure again on purpose: an abort's input comes round again, which
#: tests recurrence (design v2). Measured seeds only, and only these four; the range stays reserved.
PILOT_RERUN_SEEDS = frozenset({8102, 8103, 8106, 8110})
PROC_SAMPLE_SECONDS = 30.0
DOCKER_PROBE_SECONDS = 60.0
EVENT_ACTIONS = ("create", "start", "die", "destroy")
LOCAL_IMAGES = ("inodefence-controller:local", "inodefence-helper:local")
OWN_CONTAINER = re.compile(r"inodefence-(local-controller-|[0-9a-f]{32}$)")
BLOCK_FILE = "block.json"
INCOMPLETE_BLOCK_FILE = "block.incomplete.json"
#: Written by the analysis script; the next stage's gate reads its mechanical decision.
REPORT_JSON = "concurrency-report.json"
# Why a block stopped (design file, section 6.3). A load the level may have caused, or a fact about
# the host that voids the measurement whatever the level.
STOP_LEVEL = "level"
STOP_EXTERNAL = "external"


class DesignError(ValueError):
    """The design file is unusable; nothing runs."""


@dataclass(frozen=True, slots=True)
class Design:
    design_id: str
    target_version: str
    image_digest: str
    docker_engine: str
    budget: int
    seeds: tuple[int, ...]
    smoke_budget: int
    smoke_seed: int
    mutation_policy: str
    arms: tuple[Arm, ...]
    vocabulary: VocabularyMode
    sentinel_generator_id: str
    sentinel_generator_seed: int
    sentinel_count: int
    observer_integrity_policy: str
    campaign_watchdog_seconds: float
    disk_stop_fraction: float
    memory_stop_fraction: float
    stop_nonzero_cells: int
    preflight_load_fraction: float
    cooldown_seconds: float
    stages: Mapping[str, tuple[int, ...]]
    sha256: str


@dataclass(frozen=True, slots=True)
class Block:
    stage: str
    index: int
    jobs: int
    cells: tuple[Cell, ...]

    @property
    def name(self) -> str:
        return f"block-{self.index}-j{self.jobs}"


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
    raise DesignError("concurrency-benchmark block is not closed")


def _int_list(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in value.split(","))


def _check_seed(seed: int) -> None:
    for low, high in RESERVED_SEED_RANGES:
        if low <= seed <= high:
            raise DesignError(f"seed {seed} is inside the reserved range {low}-{high}")


def _parse_stages(values: Mapping[str, str]) -> dict[str, tuple[int, ...]]:
    stages = {key[len(STAGE_PREFIX) :]: _int_list(value) for key, value in values.items()}
    if SMOKE_STAGE not in stages or len(stages) < 2:
        raise DesignError("the design needs stage.smoke and at least one measured stage")
    for name, jobs in stages.items():
        if any(level < 1 for level in jobs):
            raise DesignError(f"stage {name}: jobs must be positive")
        if name == SMOKE_STAGE:
            continue
        # Crossed order: the second half mirrors the first, so host drift is not one level's.
        if len(set(jobs)) < 2 or jobs != tuple(reversed(jobs)):
            raise DesignError(f"stage {name}: order {jobs} must be crossed, for example 2,4,4,2")
    return stages


def parse_design(text: str) -> Design:
    """Parse and validate the design block; every arm must realize its named policy."""
    values = _parse_block(text)
    arm_values = {k[len(ARM_PREFIX) :]: v for k, v in values.items() if k.startswith(ARM_PREFIX)}
    stage_values = {k: v for k, v in values.items() if k.startswith(STAGE_PREFIX)}
    plain = {
        k: v
        for k, v in values.items()
        if not k.startswith(ARM_PREFIX) and not k.startswith(STAGE_PREFIX)
    }
    if set(plain) != REQUIRED_KEYS:
        missing = sorted(REQUIRED_KEYS - set(plain))
        unknown = sorted(set(plain) - REQUIRED_KEYS)
        raise DesignError(f"design keys differ: missing {missing}, unknown {unknown}")
    unknown_arms = sorted(set(arm_values) - set(ARM_CONFIG))
    if unknown_arms or not arm_values:
        raise DesignError(f"design arms {sorted(arm_values)} must be a subset of the known arms")
    if plain["execution_mode"] != EXECUTION_MODE:
        raise DesignError(
            f"execution_mode must stay {EXECUTION_MODE}: this benchmark varies concurrency only"
        )
    if re.fullmatch(r"sha256:[0-9a-f]{64}", plain["image_digest"]) is None:
        raise DesignError("image_digest must be sha256:<64 hex>")
    seeds = _int_list(plain["seeds"])
    smoke_seed = int(plain["smoke_seed"])
    if len(set(seeds)) != len(seeds) or smoke_seed in seeds:
        raise DesignError("seeds must be unique and differ from smoke_seed")
    for seed in (*(item for item in seeds if item not in PILOT_RERUN_SEEDS), smoke_seed):
        _check_seed(seed)
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
    return Design(
        design_id=plain["design_id"],
        target_version=plain["target_version"],
        image_digest=plain["image_digest"],
        docker_engine=plain["docker_engine"],
        budget=budget,
        seeds=seeds,
        smoke_budget=int(plain["smoke_budget"]),
        smoke_seed=smoke_seed,
        mutation_policy=plain["mutation_policy"],
        arms=tuple(arms),
        vocabulary=vocabulary,
        sentinel_generator_id=plain["sentinel_generator_id"],
        sentinel_generator_seed=int(plain["sentinel_generator_seed"]),
        sentinel_count=int(plain["sentinel_count"]),
        observer_integrity_policy=plain["observer_integrity_policy"],
        campaign_watchdog_seconds=float(plain["campaign_watchdog_seconds"]),
        disk_stop_fraction=float(plain["disk_stop_fraction"]),
        memory_stop_fraction=float(plain["memory_stop_fraction"]),
        stop_nonzero_cells=int(plain["stop_nonzero_cells"]),
        preflight_load_fraction=float(plain["preflight_load_fraction"]),
        cooldown_seconds=float(plain["cooldown_seconds"]),
        stages=_parse_stages(stage_values),
        sha256=sha256(text.encode("utf-8")).hexdigest(),
    )


def load_design(path: Path) -> Design:
    return parse_design(path.read_text(encoding="utf-8"))


def planned_cells(design: Design, stage: str) -> tuple[Cell, ...]:
    """Seed blocks with the arm order rotated per seed; identical for every block of a stage."""
    smoke = stage == SMOKE_STAGE
    seeds = (design.smoke_seed,) if smoke else design.seeds
    budget = design.smoke_budget if smoke else design.budget
    count = len(design.arms)
    return tuple(
        Cell(MODE, design.target_version, design.arms[(position + offset) % count], seed, budget)
        for position, seed in enumerate(seeds)
        for offset in range(count)
    )


def planned_blocks(design: Design, stage: str) -> tuple[Block, ...]:
    if stage not in design.stages:
        raise DesignError(f"unknown stage {stage!r}; design has {sorted(design.stages)}")
    cells = planned_cells(design, stage)
    return tuple(
        Block(stage, index, jobs, cells) for index, jobs in enumerate(design.stages[stage], start=1)
    )


def measured_stages(design: Design) -> tuple[str, ...]:
    """Measured stages in design order; each may start only after the previous one is clean."""
    return tuple(name for name in design.stages if name != SMOKE_STAGE)


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


def output_problem(output: Path, repo_root: Path, home: Path) -> str | None:
    """The benchmark's files stay apart from experiment evidence and from the repository."""
    resolved = output.expanduser().resolve()
    for parent, name in (
        ((home / "inodefence-evidence").resolve(), "the evidence tree"),
        (repo_root.resolve(), "the repository"),
    ):
        if resolved == parent or parent in resolved.parents:
            return f"--output must be outside {name} ({parent})"
    return None


def residual_resources() -> list[str]:
    """Benchmark-path containers or volumes left behind; a stale one blocks the next cell."""
    containers = _docker("ps", "-a", "--filter", "name=inodefence-", "--format", "{{.Names}}")
    volumes = _docker("volume", "ls", "--filter", "name=inodefence-local-", "--format", "{{.Name}}")
    return [*containers.split(), *volumes.split()]


def preflight(design: Design, expected_head: str) -> tuple[dict[str, Any], list[str]]:
    """Facts the run stands on, and the problems that refuse it."""
    source = capture_source()
    problems: list[str] = []
    if source.revision != expected_head:
        problems.append(f"checkout HEAD {source.revision} != expected {expected_head}")
    if source.dirty is not False:
        problems.append("checkout is not clean")
    load_one = os.getloadavg()[0]
    cores = os.cpu_count() or 1
    if load_one >= design.preflight_load_fraction * cores:
        problems.append(f"host is not quiet: load {load_one:.2f} on {cores} cores")
    facts: dict[str, Any] = {
        "checkout_head": source.revision,
        "checkout_dirty": source.dirty,
        "loadavg": os.getloadavg(),
        "cores": cores,
        "system": os.uname().sysname,
        "release": os.uname().release,
        "machine": os.uname().machine,
    }
    try:
        server = _docker("version", "--format", "{{.Server.Version}}")
        image = f"inodefence-node-tar-effect:{design.target_version}"
        image_id = _docker("image", "inspect", image, "--format", "{{.Id}}")
        running = _docker("ps", "--format", "{{.Names}}").split()
        residual = residual_resources()
        # Cells run with SKIP_BUILD=1, so these must exist before the first cell.
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
    if residual:
        problems.append(f"residual benchmark resources exist: {residual}")
    return facts, problems


def base_environment(design: Design) -> dict[str, str]:
    env = dict(os.environ)
    env["DEMO_SENTINEL_SEED"] = str(design.sentinel_generator_seed)
    env["DEMO_SENTINEL_COUNT"] = str(design.sentinel_count)
    env["DEMO_OBSERVER_INTEGRITY_POLICY"] = design.observer_integrity_policy
    return env


def read_host_counters(proc: Path = Path("/proc")) -> dict[str, Any]:
    """Cheap kernel counters. In WSL2 every distro shares one VM, so these cover Docker's work."""
    memory: dict[str, int] = {}
    for line in (proc / "meminfo").read_text(encoding="ascii").splitlines():
        name, _, rest = line.partition(":")
        if name in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
            memory[name] = int(rest.split()[0]) * 1024
    cpu = (proc / "stat").read_text(encoding="ascii").splitlines()[0].split()[1:]
    pressure: dict[str, str] = {}
    for name in ("cpu", "io", "memory"):
        path = proc / "pressure" / name
        if path.is_file():
            pressure[name] = path.read_text(encoding="ascii").splitlines()[0]
    return {"memory": memory, "cpu_jiffies": [int(item) for item in cpu], "pressure": pressure}


def host_stop_reason(sample: Mapping[str, Any], design: Design) -> tuple[str, str] | None:
    """A host sample that means this level must not start more cells: (reason, stop kind)."""
    memory = sample.get("memory") or {}
    total, available = memory.get("MemTotal"), memory.get("MemAvailable")
    if total and available is not None and available / total < design.memory_stop_fraction:
        return f"available memory {available / total:.1%} is under the stop fraction", STOP_LEVEL
    disk = sample.get("disk_fraction")
    if disk is not None and disk >= design.disk_stop_fraction:
        return f"disk usage {disk:.1%} reached the stop fraction", STOP_EXTERNAL
    foreign = [name for name in sample.get("containers") or () if OWN_CONTAINER.match(name) is None]
    if foreign:
        return f"foreign containers appeared during the block: {foreign}", STOP_EXTERNAL
    return None


class StartDenied(Exception):
    """A block stop was committed before this cell could start."""


class BlockRun:
    """Run a block and record start/stop order without recording oracle outcomes.

    ``start_order``, ``stop_order`` and rejected ``decision_order`` are a
    block-local sequence, persisted with the existing block record on completion.
    Launch and stop commit under one lock; a launch commits only after Popen
    succeeds. Waiting for the child never holds the lock.
    """

    def __init__(
        self,
        design: Design,
        block: Block,
        directory: Path,
        run_cell: Callable[[Cell, Path, dict[str, str], Callable[..., Any]], CellResult],
    ) -> None:
        self.design = design
        self.block = block
        self.directory = directory
        self.raw = directory / "raw"
        self.run_cell = run_cell
        self.base_env = base_environment(design)
        self.lock = threading.Lock()
        self.nonzero_cells = 0
        self.stopped_reason: str | None = None
        self.stop_kind: str | None = None
        self.records: list[dict[str, Any]] = []
        self.event_order = 0
        self.stop_order: int | None = None
        self.started_cells: dict[str, int] = {}
        self.completed_cells: set[str] = set()
        self.failures: list[dict[str, str]] = []
        self.require_logs = False

    def _stop_locked(self, reason: str, kind: str) -> None:
        if self.stopped_reason is None:
            self.event_order += 1
            self.stop_order = self.event_order
            self.stopped_reason = reason
            self.stop_kind = kind

    def request_stop(self, reason: str, kind: str) -> None:
        """The first reason is the block's reason: what came after it may be its consequence."""
        with self.lock:
            self._stop_locked(reason, kind)

    def record_failure(self, where: str, error: BaseException) -> None:
        with self.lock:
            self.failures.append(
                {
                    "where": where,
                    "type": type(error).__name__,
                    "message": str(error),
                    "observed_at": datetime.now(UTC).isoformat(),
                }
            )

    def run_one(self, cell: Cell) -> None:
        started: dict[str, Any] = {}
        start_order: int | None = None
        process: Any = None

        def launch(start: Callable[[], Any]) -> Any:
            nonlocal started, start_order, process
            with self.lock:
                if self.stopped_reason is not None:
                    raise StartDenied
                # Popen itself is the start boundary. Do not hold this lock while
                # the child runs or while the watchdog waits for it.
                try:
                    started = clock_stamp()
                    process = start()
                except BaseException as error:
                    self._stop_locked(
                        f"{cell.run_id} launch failed: {type(error).__name__}: {error}",
                        STOP_EXTERNAL,
                    )
                    raise
                self.event_order += 1
                start_order = self.event_order
                self.started_cells[cell.run_id] = start_order
                return process

        try:
            result = self.run_cell(cell, self.raw, cell_env(cell, self.raw, self.base_env), launch)
        except StartDenied:
            with self.lock:
                self.event_order += 1
                self.records.append(
                    {"run_id": cell.run_id, "state": "not-run", "decision_order": self.event_order}
                )
            return
        except BaseException as error:
            if start_order is not None:
                self.request_stop(
                    f"{cell.run_id} runner failed after start: {type(error).__name__}: {error}",
                    STOP_EXTERNAL,
                )
                self.record_failure(f"cell {cell.run_id}", error)
                if process is not None:
                    try:
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=30)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=30)
                        error.add_note(
                            f"started process {process.pid} exited with {process.returncode}; "
                            "container and volume cleanup still requires verification"
                        )
                    except Exception as cleanup_error:
                        error.add_note(
                            f"started process cleanup failed: {type(cleanup_error).__name__}: "
                            f"{cleanup_error}; process and resources may remain"
                        )
                raise
            if not isinstance(error, Exception):
                self.request_stop(
                    f"{cell.run_id} interrupted before start: {type(error).__name__}: {error}",
                    STOP_EXTERNAL,
                )
                self.record_failure(f"cell {cell.run_id}", error)
                raise
            with self.lock:
                self._stop_locked(
                    f"{cell.run_id} launch failed: {type(error).__name__}: {error}", STOP_EXTERNAL
                )
                self.event_order += 1
                self.records.append(
                    {
                        "run_id": cell.run_id,
                        "state": "not-run",
                        "decision_order": self.event_order,
                        "start_error": f"{type(error).__name__}: {error}",
                    }
                )
            self.record_failure(f"cell {cell.run_id}", error)
            return
        try:
            with self.lock:
                self.completed_cells.add(cell.run_id)
            ended = clock_stamp()
            paths = cell_paths(cell, self.raw)
            cleanup_unknown = False
            if self.require_logs and not result.log.is_file():
                raise OSError(f"cell log unavailable: {result.log}")
            if result.log.is_file():
                with result.log.open(encoding="utf-8", errors="replace") as stream:
                    cleanup_unknown = any("INODEFENCE_CLEANUP_UNKNOWN:" in line for line in stream)
            with self.lock:
                self.records.append(
                    {
                        "run_id": cell.run_id,
                        "state": "ran",
                        "arm": cell.arm.label,
                        "seed": cell.seed,
                        "budget": cell.budget,
                        "returncode": result.returncode,
                        "watchdog_killed": result.returncode == WATCHDOG_RETURNCODE,
                        "launcher_wall_seconds": result.wall_seconds,
                        "started": started,
                        "start_order": start_order,
                        "ended": ended,
                        "report": paths["report"].name,
                        "steps": paths["steps_jsonl"].name,
                        "log": paths["log"].name,
                    }
                )
                if result.returncode != 0:
                    self.nonzero_cells += 1
                if cleanup_unknown:
                    self._stop_locked(
                        f"{cell.run_id} cleanup resource state unknown", STOP_EXTERNAL
                    )
                elif result.returncode == WATCHDOG_RETURNCODE:
                    self._stop_locked(f"{cell.run_id} hit the campaign watchdog", STOP_LEVEL)
                elif self.nonzero_cells >= self.design.stop_nonzero_cells:
                    self._stop_locked(f"{self.nonzero_cells} cells exited nonzero", STOP_LEVEL)
        except BaseException as error:
            self.request_stop(
                f"{cell.run_id} result recording failed: {type(error).__name__}: {error}",
                STOP_EXTERNAL,
            )
            self.record_failure(f"cell {cell.run_id} result recording", error)
            raise

    def execute(self) -> dict[str, Any]:
        self.raw.mkdir(parents=True, exist_ok=True)
        started = clock_stamp()
        with ThreadPoolExecutor(max_workers=self.block.jobs) as pool:
            try:
                list(pool.map(self.run_one, self.block.cells))
            except BaseException as error:
                self.request_stop(
                    f"block interrupted: {type(error).__name__}: {error}", STOP_EXTERNAL
                )
                raise
        ended = clock_stamp()
        order = {cell.run_id: position for position, cell in enumerate(self.block.cells)}
        return {
            "label": list(LABELS),
            "design_id": self.design.design_id,
            "design_sha256": self.design.sha256,
            "stage": self.block.stage,
            "index": self.block.index,
            "jobs": self.block.jobs,
            "started": started,
            "ended": ended,
            "stopped_reason": self.stopped_reason,
            "stop_kind": self.stop_kind,
            "stop_order": self.stop_order,
            "finished": True,
            "cells": sorted(self.records, key=lambda record: order[record["run_id"]]),
        }


def _sample_host(
    run: BlockRun, path: Path, stop: threading.Event, seconds: float = PROC_SAMPLE_SECONDS
) -> None:
    """Sample until told to stop. A sampler failure stops the block: its guards would be off."""
    next_probe = 0.0
    try:
        with path.open("a", encoding="utf-8") as stream:
            while True:
                sample: dict[str, Any] = {
                    **clock_stamp(),
                    "loadavg": os.getloadavg(),
                    "disk_fraction": disk_usage_fraction(run.directory),
                    **read_host_counters(),
                }
                if sample["monotonic"] >= next_probe:
                    # Daemon responsiveness at a fixed low rate: the same load at every level.
                    probe_started = time.clock_gettime(time.CLOCK_REALTIME)
                    try:
                        names = _docker("ps", "--format", "{{.Names}}").split()
                        sample["containers"] = names
                        sample["docker_ps_seconds"] = (
                            time.clock_gettime(time.CLOCK_REALTIME) - probe_started
                        )
                    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                        sample["docker_ps_error"] = str(error)
                    next_probe = sample["monotonic"] + DOCKER_PROBE_SECONDS
                stream.write(json.dumps(sample, sort_keys=True) + "\n")
                stream.flush()
                host_stop = host_stop_reason(sample, run.design)
                if host_stop is not None:
                    run.request_stop(*host_stop)
                if stop.wait(seconds):
                    return
    except Exception as error:
        run.request_stop(f"host sampler failed: {type(error).__name__}: {error}", STOP_EXTERNAL)
        run.record_failure("host sampler", error)


def _start_events(path: Path) -> subprocess.Popen[bytes]:
    filters = [item for action in EVENT_ACTIONS for item in ("--filter", f"event={action}")]
    with path.open("wb") as stream:
        return subprocess.Popen(
            ["docker", "events", "--format", "{{json .}}", "--filter", "type=container", *filters],
            stdout=stream,
            stderr=subprocess.DEVNULL,
        )


def _stop_events(events: subprocess.Popen[bytes]) -> None:
    """Stop the event collector, preserving any failure and bounding the reap."""
    try:
        events.terminate()
        events.wait(timeout=30)
    except Exception as error:
        try:
            events.kill()
            events.wait(timeout=30)
        except Exception as cleanup_error:
            error.add_note(f"event collector cleanup failed: {cleanup_error}")
        raise


def _publish_json(path: Path, value: Mapping[str, Any]) -> None:
    """Publish once without exposing a partial file or replacing existing evidence."""
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".block-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as error:
                print(f"temporary block file could not be removed: {error}", file=sys.stderr)


def _run_block(
    design: Design, block: Block, directory: Path, bash: str, run: BlockRun
) -> dict[str, Any]:
    def run_cell(
        cell: Cell, raw: Path, env: dict[str, str], launch: Callable[..., Any]
    ) -> CellResult:
        return run_cell_with_watchdog(
            cell,
            raw,
            env,
            bash,
            limit_seconds=design.campaign_watchdog_seconds,
            popen=lambda *args, **kwargs: launch(lambda: subprocess.Popen(*args, **kwargs)),
        )

    host = directory / "host"
    host.mkdir(parents=True, exist_ok=True)
    run.run_cell = run_cell
    stop_sampling = threading.Event()
    sampler = threading.Thread(
        target=_sample_host, args=(run, host / "samples.jsonl", stop_sampling), daemon=True
    )
    events = _start_events(host / "events.jsonl")
    try:
        sampler.start()
        record = run.execute()
        if any(cell.get("state") == "not-run" for cell in record["cells"]):
            raise RuntimeError("block stopped before all cells started")
    finally:
        active_error = sys.exception()
        stop_sampling.set()
        cleanup_failure: Exception | None = None
        try:
            if sampler.ident is not None:
                sampler.join(timeout=60)
                if sampler.is_alive():
                    raise RuntimeError("host sampler did not stop")
        except Exception as cleanup_error:
            cleanup_failure = cleanup_error
        finally:
            try:
                _stop_events(events)
            except Exception as cleanup_error:
                if cleanup_failure is None:
                    cleanup_failure = cleanup_error
                else:
                    cleanup_failure.add_note(f"events cleanup failed: {cleanup_error}")
        if cleanup_failure is not None:
            if active_error is not None:
                active_error.add_note(f"block cleanup failed: {cleanup_failure}")
            else:
                raise cleanup_failure
    # A sampler stop that came after the last cell started is still a reason to end the stage.
    record["stopped_reason"] = run.stopped_reason
    record["stop_kind"] = run.stop_kind
    record["stop_order"] = run.stop_order
    residual = residual_resources()
    record["residual_after_block"] = residual
    if residual and record["stopped_reason"] is None:
        run.request_stop(f"residual resources after the block: {residual}", STOP_LEVEL)
        record["stopped_reason"] = run.stopped_reason
        record["stop_kind"] = run.stop_kind
        record["stop_order"] = run.stop_order
    if run.stopped_reason is not None:
        raise RuntimeError(f"block stopped: {run.stopped_reason}")
    _publish_json(directory / BLOCK_FILE, record)
    return record


def run_block(design: Design, block: Block, directory: Path, bash: str) -> dict[str, Any]:
    """Publish exceptional exits separately; never turn an incomplete block into a result."""

    def unavailable(*_args: Any) -> CellResult:
        raise RuntimeError("block runner is not initialized")

    run = BlockRun(design, block, directory, unavailable)
    run.require_logs = True
    try:
        return _run_block(design, block, directory, bash, run)
    except BaseException as error:
        observed_at = datetime.now(UTC).isoformat()
        run.request_stop(f"block failed: {type(error).__name__}: {error}", STOP_EXTERNAL)
        try:
            residual = {"status": "observed", "resources": residual_resources()}
        except Exception as residual_error:
            residual = {
                "status": "unknown",
                "error": f"{type(residual_error).__name__}: {residual_error}",
            }
        try:
            preflight = json.loads((directory / "preflight.json").read_text(encoding="utf-8"))
            revision = preflight.get("preflight", {}).get("checkout_head")
        except (OSError, ValueError, AttributeError):
            revision = None
        with run.lock:
            started = dict(run.started_cells)
            completed = sorted(run.completed_cells)
            evidence = {
                "schema": "inodefence-h1-incomplete-v1",
                "finished": False,
                "design_id": design.design_id,
                "design_sha256": design.sha256,
                "stage": block.stage,
                "block": block.name,
                "index": block.index,
                "jobs": block.jobs,
                "execution_sha": revision,
                "stopped_reason": run.stopped_reason,
                "stop_kind": run.stop_kind,
                "stop_order": run.stop_order,
                "started_cells": started,
                "completed_cells": completed,
                "unknown_cells": sorted(set(started) - run.completed_cells),
                "cell_records": list(run.records),
                "failures": list(run.failures),
                "exception": {
                    "type": type(error).__name__,
                    "message": str(error),
                    "notes": getattr(error, "__notes__", []),
                },
                "exception_observed_at": observed_at,
                "recorded_at": datetime.now(UTC).isoformat(),
                "watchdog_cells": [r["run_id"] for r in run.records if r.get("watchdog_killed")],
                "sampler_status": "requires_review",
                "residual_resources": residual,
                "follow_up_required": True,
            }
        try:
            _publish_json(directory / INCOMPLETE_BLOCK_FILE, evidence)
        except Exception as publish_error:
            error.add_note(f"incomplete evidence publication failed: {publish_error}")
        raise


def stage_state(output: Path, block: Block) -> str:
    """``pending``, ``clean``, ``stopped``, or ``incomplete`` (started without a block record)."""
    directory = output / block.stage / block.name
    record_path = directory / BLOCK_FILE
    if (directory / INCOMPLETE_BLOCK_FILE).exists():
        return "incomplete"
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("finished") is not True:
            return "incomplete"
        return "stopped" if record.get("stopped_reason") else "clean"
    return "incomplete" if directory.exists() else "pending"


def stage_gate_problem(design: Design, stage: str, output: Path) -> str | None:
    """Stages run in design order. A measured stage follows only a passed mechanical decision.

    Smoke must finish without a stop before the first measured stage. A later stage needs the
    analysis report of this design to say the previous stage passed and nothing halted.
    """
    if stage == SMOKE_STAGE:
        return None
    order = (SMOKE_STAGE, *measured_stages(design))
    previous = order[order.index(stage) - 1]
    if previous == SMOKE_STAGE:
        states = [stage_state(output, block) for block in planned_blocks(design, previous)]
        if any(state != "clean" for state in states):
            return f"stage {previous} is not clean ({states}); {stage} may not start"
        return None
    report_path = output / REPORT_JSON
    if not report_path.is_file():
        return f"no analysis report; analyze stage {previous} before {stage}"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("design_sha256") != design.sha256:
        return "the analysis report was made under another design"
    decision = report.get("decision") or {}
    if decision.get("halts"):
        return f"the analysis halted: {[item.get('rule') for item in decision['halts']]}"
    verdict = (decision.get("stages") or {}).get(previous) or {}
    if not verdict.get("passed"):
        return f"stage {previous} did not pass the decision rule; {stage} may not start"
    for earlier in order[: order.index(stage)]:
        states = [stage_state(output, block) for block in planned_blocks(design, earlier)]
        if any(state != "clean" for state in states):
            return f"stage {earlier} is not clean ({states}); {stage} may not start"
    return None


def print_plan(design: Design, stage: str) -> None:
    blocks = planned_blocks(design, stage)
    cells = blocks[0].cells
    print(
        f"{design.design_id} sha256={design.sha256[:12]}… stage={stage} "
        f"jobs order={[block.jobs for block in blocks]} cells/block={len(cells)} "
        f"seeds={sorted({cell.seed for cell in cells})} budget={cells[0].budget} "
        f"k={design.sentinel_count} mode={EXECUTION_MODE} image={design.image_digest[:19]}…"
    )
    for cell in cells:
        print(f"  {cell.run_id}: search={cell.arm.search}")


def print_status(design: Design, stage: str, output: Path) -> None:
    """Schedule state only: reads block records, never a cell file."""
    for block in planned_blocks(design, stage):
        record_path = output / block.stage / block.name / BLOCK_FILE
        state = stage_state(output, block)
        detail = ""
        if record_path.is_file():
            record = json.loads(record_path.read_text(encoding="utf-8"))
            elapsed = record["ended"]["realtime"] - record["started"]["realtime"]
            nonzero = sum(1 for cell in record["cells"] if cell.get("returncode", 0) != 0)
            detail = f" real_seconds={elapsed:.0f} nonzero={nonzero} {record['stopped_reason']}"
        print(f"{block.name}: {state}{detail}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", required=True, help="smoke, then the design's measured stages")
    parser.add_argument("--expected-head", help="commit this checkout must be at (live run)")
    parser.add_argument("--approval-ref", help="who approved this stage, recorded (live run)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; no Docker")
    parser.add_argument("--status", action="store_true", help="schedule state only; no outcomes")
    args = parser.parse_args(argv)

    design = load_design(args.design)
    try:
        blocks = planned_blocks(design, args.stage)
    except DesignError as error:
        parser.error(str(error))
    if args.dry_run:
        print_plan(design, args.stage)
        return 0
    if args.status:
        print_status(design, args.stage, args.output)
        return 0
    if not args.expected_head or not args.approval_ref:
        parser.error("a live run needs --expected-head and --approval-ref")
    repo_root = Path(__file__).resolve().parents[1]
    problem = output_problem(args.output, repo_root, Path.home())
    if problem is None:
        problem = stage_gate_problem(design, args.stage, args.output)
    if problem is not None:
        print(f"refusing to run: {problem}", file=sys.stderr)
        return 2
    states = [stage_state(args.output, block) for block in blocks]
    if "incomplete" in states or "stopped" in states:
        print(f"refusing to run: stage has unfinished blocks {states}", file=sys.stderr)
        return 2
    bash = shutil.which("bash")
    if bash is None:
        raise SystemExit("bash not found: the benchmark runs only on the host terminal")
    for block, state in zip(blocks, states, strict=True):
        if state == "clean":
            continue
        facts, problems = preflight(design, args.expected_head)
        if problems:
            print(f"refusing to start {block.name}:", file=sys.stderr)
            for item in problems:
                print(f"  - {item}", file=sys.stderr)
            return 2
        directory = args.output / block.stage / block.name
        directory.mkdir(parents=True)
        (directory / "preflight.json").write_text(
            json.dumps(
                {
                    "label": list(LABELS),
                    "design_sha256": design.sha256,
                    "approval_ref": args.approval_ref,
                    "preflight": facts,
                    "written_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        record = run_block(design, block, directory, bash)
        print(f"{block.name}: stopped={record['stopped_reason']}")
        if record["stopped_reason"]:
            return 1
        time.sleep(design.cooldown_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

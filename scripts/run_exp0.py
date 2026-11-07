"""Registered-experiment launcher (EXP-0 pilot, EXP-3 scale): one preregistration file in.

Input is ONE committed preregistration file (``experiments/preregistration/*.md``
with the fenced ``preregistration`` block). Nothing runs unless the gate passes for
every planned cell: engine HEAD SHA (clean checkout), image digest, seeds, budget,
arm policy IDs, ``observer_integrity_policy``, ``sentinel_*``, the five rule keys and
— when declared — ``experiment_id``, ``execution_mode`` and ``jobs_max``
(``inodefence.evaluation.rds_preregistration``).

Cells = preregistered seeds × R/D/S-u (+ S-a with ``--include-s-a`` when declared) ×
preregistered budget, each run as a ``local_node_tar_smoke.sh demo-historical``
campaign with a unique ``RUN_ID`` — the same path and summaries as
``scripts/run_g1_smoke.py``. Outputs are labelled ``registered run`` with the
experiment id, the preregistration file name, its SHA-256 and the engine SHA::

    <output>/registration.json                  what this directory was launched under
    <output>/matrix.json                        last invocation's cell results
    <output>/inodefence-effect-demo-historical-<run_id>.json / .steps.jsonl / <run_id>.log
    <output>/attempts/<run_id>.attempt<N>.*     files of a rerun cell's earlier attempt
    <output>/summaries/<run_id>.summary.json + index.json   analyze_exp0 input
    <manifest>                                  raw SHA-256 manifest (make_raw_manifest)

Scale controls (all from the file; the launcher only enforces them):

* ``execution_mode``: ``per-case-container`` (the controller demo path) or
  ``worker-pool`` (lane 4 ``inodefence.execution.worker_pool``: the cell gets the
  ``s3wp-`` worker run id and bring-up plan, and ``DEMO_EXECUTION_MODE=worker-pool``
  must be consumed by the smoke script; the module is imported lazily and a live run
  is refused when it or the wiring is absent).
* ``jobs_max``: upper bound on ``--jobs``.
* ``campaign_watchdog_seconds``: a cell running longer is terminated and counted as
  an abort (``watchdog``); its completed steps stay on disk and it reruns next time.
* ``disk_pause_fraction``: a new cell waits while the output filesystem is at least
  this full (lane 4 ``should_pause_for_disk``), logged in ``matrix.json``.
* ``interim_analysis = forbidden``: the index carries completion state only (no
  hit/T_first fields, no summary files) until every planned cell has a *final*
  terminal state AND the evidence passed the integrity checks. Terminal states
  (``cell_state``): ``complete``; ``abort-final`` = an abort record (report with an
  abort record, or steps on disk with a recorded termination) marked final with
  ``--finalize-abort RUN_ID[=NOTE]`` — the manual classification step of the run
  procedure until #203's reason classifier automates it (campaign aborts final at
  once, infrastructure aborts after the retry cap); ``abort-pending`` = an abort
  record not yet final (re-run next time); ``unattempted`` = no record (never
  started, in progress, or a controller that died before writing). Integrity:
  report/steps files present, the steps file a prefix of the report steps, the raw
  manifest generated and re-verified with the manifest script's ``--verify``
  (``manifest-verification.json``, an extra file outside the manifest). Once all of
  that holds the outcomes are published with aborted cells right-censored at their
  abort point and kept in the denominator (the preregistered abort rule); a final
  abort is never re-run. ``registration.json`` is updated before the manifest so the
  manifest covers its final bytes.

Idempotent: a rerun skips cells whose report is complete and conformant (budget
reached, no abort, planned config, preregistered image id and sentinel set) and
re-runs only the rest, moving their earlier files to ``attempts/``. ``--dry-run``
prints the gate verdict, the items a live run would refuse, and every cell's
command/env/paths without Docker, and exits non-zero when a live run would be refused
(gate or controller wiring, including a version or budget the controller rejects);
``--summarize-only`` rebuilds the summaries and manifest from existing files.

Post-run conformance (per cell, third bucket ``config_nonconformant`` when it
fails): the report's ``image_id`` must equal the preregistered digest and, when the
file declares a sentinel generator, the report's ``sentinel_set`` must match it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep
from typing import Any

from scripts.run_g1_smoke import (
    DEFAULT_EXECUTION_MODE,
    EXECUTION_MODES,
    SENTINEL_GENERATOR_ID,
    cell_paths,
    summarize_output,
)
from scripts.run_parallel_native import (
    SCRIPT,
    TOKEN,
    Arm,
    Cell,
    CellResult,
    _warmup,
    cell_env,
)

from inodefence.evaluation.rds import VOCABULARY_MUTATION_POLICY, RdsArm, RdsCellConfig
from inodefence.evaluation.rds_preregistration import (
    CellRequest,
    Preregistration,
    PreregistrationFormatError,
    TargetSpec,
    ledger_problems,
    load_preregistration,
    preregistration_mismatches,
)
from inodefence.evaluation.rds_report import ReportFormatError, load_cell_files
from inodefence.provenance import capture_source

DEFAULT_EXPERIMENT_ID = "exp0"
REGISTERED_LABEL = "registered run"
DEFAULT_VERSION = "7.5.2"
DEFAULT_JOBS = 2
DEFAULT_MANIFEST_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_raw_manifest.py"
REGISTRATION_FILE = "registration.json"
INTERIM_RULE = (
    "outcomes are published only when every planned cell has a final terminal state "
    "(complete report, or an abort record marked final) and the evidence passed the "
    "integrity checks (report/steps files present, steps prefix consistent, raw manifest "
    "generated and re-verified); aborted cells are right-censored at their abort point and "
    "kept in the denominator; until then the index carries completion state only"
)
ABORT_DECISIONS_FILE = "abort-decisions.json"
VERIFICATION_FILE = "manifest-verification.json"
CELL_STATES = ("complete", "abort-final", "abort-pending", "unattempted")
WORKER_POOL_MODE = "worker-pool"
# Fallbacks when lane 4's module is not importable (its constants are preferred).
DEFAULT_WATCHDOG_SECONDS = 2 * 60 * 60.0
DEFAULT_DISK_PAUSE_FRACTION = 0.9
DISK_POLL_SECONDS = 60.0
WATCHDOG_RETURNCODE = -15
# Env names the smoke script must consume for the declared options to reach the
# controller; probed in the script text so a declared-but-unwired option never
# silently runs with the default.
SENTINEL_ENV = ("DEMO_SENTINEL_SEED", "DEMO_SENTINEL_COUNT")
OBSERVER_ENV = "DEMO_OBSERVER_INTEGRITY_POLICY"
EXECUTION_MODE_ENV = "DEMO_EXECUTION_MODE"


def _script_has(variable: str) -> bool:
    """Whether the smoke script references an env variable (wiring probe)."""
    return SCRIPT.is_file() and variable in SCRIPT.read_text(encoding="utf-8")


def _worker_pool_module() -> Any | None:
    """Lane 4's worker-pool module, or None when its PR is not on this base."""
    try:
        import inodefence.execution.worker_pool as module  # pyright: ignore[reportMissingImports]
    except ImportError:
        return None
    return module


@dataclass(frozen=True, slots=True)
class TargetCell(Cell):
    """A planned cell bound to one registration target.

    ``run_id`` is ``<target_id>-<arm>-s<seed>``; for the single-target (EXP-0) form
    the target id is the node-tar version, so run ids and evidence paths are the
    ones G1/EXP-0 already use. Multi-target plans keep each target's evidence in
    ``<output>/<target_id>/`` (``subdir``) so per-target manifests cannot collide.
    """

    target_id: str = ""
    extractor: str = "node-tar"
    role: str = "train"
    hypothesis: str = "H-A"
    digest: str = ""
    digest_kind: str = "image"
    subdir: str | None = None

    @property
    def run_id(self) -> str:
        token = f"{self.target_id}-{self.arm.label}-s{self.seed}"
        if not TOKEN.fullmatch(token):
            raise ValueError(f"run id is not a valid resource name: {token!r}")
        return token


def target_record(target: TargetSpec) -> dict[str, Any]:
    return {
        "target_id": target.target_id,
        "extractor": target.extractor,
        "version": target.version,
        "digest": target.digest,
        "digest_kind": target.digest_kind,
        "role": target.role,
        "hypothesis": target.hypothesis,
        "exposure": target.exposure,
        "exposure_ref": target.exposure_ref,
        "exclusion_ref": target.exclusion_ref,
        "arms": None if target.arms is None else [arm.value for arm in target.arms],
        "budget": target.budget,
    }


@dataclass(frozen=True, slots=True)
class Exp0Plan:
    """The preregistered cells; every parameter comes from the file, none from flags."""

    preregistration: Preregistration
    preregistration_path: Path
    preregistration_sha256: str
    version: str
    include_s_a: bool
    execution_mode: str = DEFAULT_EXECUTION_MODE

    @property
    def plan(self) -> str:
        return self.preregistration.experiment_id or DEFAULT_EXPERIMENT_ID

    @property
    def watchdog_seconds(self) -> float:
        declared = self.preregistration.campaign_watchdog_seconds
        if declared is not None:
            return declared
        module = _worker_pool_module()
        return float(getattr(module, "CAMPAIGN_WATCHDOG_SECONDS", DEFAULT_WATCHDOG_SECONDS))

    @property
    def disk_pause_fraction(self) -> float:
        declared = self.preregistration.disk_pause_fraction
        if declared is not None:
            return declared
        module = _worker_pool_module()
        return float(getattr(module, "DISK_PAUSE_FRACTION", DEFAULT_DISK_PAUSE_FRACTION))

    @property
    def interim_forbidden(self) -> bool:
        return self.preregistration.interim_analysis == "forbidden"

    def arm_list(self) -> tuple[RdsArm, ...]:
        arms = [RdsArm.R, RdsArm.D, RdsArm.S_U]
        if self.include_s_a:
            arms.append(RdsArm.S_A)
        return tuple(arms)

    def arms(self) -> tuple[Arm, ...]:
        prereg = self.preregistration
        mutation = VOCABULARY_MUTATION_POLICY[prereg.vocabulary_mode].value
        return tuple(
            Arm(arm.value, prereg.arm_policies[arm].value, mutation) for arm in self.arm_list()
        )

    @property
    def multi_target(self) -> bool:
        return bool(self.preregistration.targets)

    def targets(self) -> tuple[TargetSpec, ...]:
        """Declared targets, or the single node-tar target the one-key form stands for."""
        prereg = self.preregistration
        if prereg.targets:
            return prereg.targets
        return (
            TargetSpec(
                self.version,
                "node-tar",
                self.version,
                prereg.image_digest or "",
                "image",
                "train",
                "H-A",
                "none",
                None,
                None,
                None,
                None,
            ),
        )

    def cells(self) -> list[Cell]:
        """Targets in order. A multi-target plan runs seed blocks with the arm order rotated.

        Then every arm runs at about the same time on each seed, so a slow host or a change over
        the run does not fall on one arm, and a campaign stopped early leaves only later seed blocks
        unfinished. The concurrency benchmark measures this same order
        (``run_concurrency_benchmark.planned_cells``). A single-key registration (EXP-0) keeps its
        recorded arm-then-seed order.
        """
        prereg = self.preregistration
        cells: list[Cell] = []
        for target in self.targets():
            arms = [
                arm
                for arm in self.arms()
                if target.arms is None or RdsArm(arm.label) in target.arms
            ]
            budget = target.budget if target.budget is not None else prereg.budget
            order = (
                [
                    (arms[(position + offset) % len(arms)], seed)
                    for position, seed in enumerate(prereg.seeds)
                    for offset in range(len(arms))
                ]
                if self.multi_target
                else [(arm, seed) for arm in arms for seed in prereg.seeds]
            )
            for arm, seed in order:
                cells.append(
                    TargetCell(
                        "demo-historical",
                        target.version,
                        arm,
                        seed,
                        budget,
                        target_id=target.target_id,
                        extractor=target.extractor,
                        role=target.role,
                        hypothesis=target.hypothesis,
                        digest=target.digest,
                        digest_kind=target.digest_kind,
                        subdir=target.target_id if self.multi_target else None,
                    )
                )
        return cells

    def analysis_plan(self) -> dict[str, Any]:
        prereg = self.preregistration
        return {
            "confirmatory_family": prereg.confirmatory_family,
            "confirmatory_targets": list(prereg.confirmatory_targets()),
            # Ordered Holm family for the analysis tools (lane 6): one record per
            # contrast, holdout targets with hypothesis H-A only.
            "confirmatory_contrasts": [dict(c) for c in prereg.confirmatory_contrasts()],
            "confirmatory_test": prereg.confirmatory_test,
            "multiplicity": prereg.multiplicity,
            "primary_endpoint": prereg.primary_endpoint,
            "event_threshold": prereg.event_threshold,
            "exposure_ledger": prereg.exposure_ledger,
            "exposure_ledger_sha256": prereg.exposure_ledger_sha256,
        }

    def cell_config(self, cell: Cell) -> RdsCellConfig:
        prereg = self.preregistration
        return RdsCellConfig(
            RdsArm(cell.arm.label),
            cell.seed,
            cell.budget,
            prereg.vocabulary_mode,
            prereg.r_variant,
        )

    def sentinel_request(self) -> dict[str, object] | None:
        prereg = self.preregistration
        if prereg.sentinel_generator_seed is None:
            return None
        return {
            "generator_id": prereg.sentinel_generator_id or SENTINEL_GENERATOR_ID,
            "generator_seed": prereg.sentinel_generator_seed,
            "count": prereg.sentinel_count,
        }

    def labels(self, engine_sha: str | None) -> list[str]:
        return [
            REGISTERED_LABEL,
            f"experiment={self.plan}",
            f"preregistration={self.preregistration_path.name}",
            f"preregistration_sha256={self.preregistration_sha256}",
            f"engine_sha={engine_sha}",
        ]

    def gate_text(self) -> str:
        return (
            f"preregistration gate on: {self.preregistration_path.name} "
            f"(sha256 {self.preregistration_sha256[:12]}…)"
        )


def gate_mismatches(
    plan: Exp0Plan,
    *,
    engine_sha: str | None,
    engine_dirty: bool | None,
    image_digest: str | None,
    observer_integrity_policy: str | None,
    jobs: int | None = None,
    target_digests: Mapping[str, str] | None = None,
    ledger: tuple[str | None, str | None] | None = None,
) -> tuple[str, ...]:
    """Union of every cell's mismatches (cells differ in target/arm/seed).

    Multi-target plans compare each cell against the digest supplied for its target
    (``--target-digest``); the one-key form compares ``image_digest``. ``ledger`` is
    the (text, sha256) of the exposure ledger, checked when a holdout is declared.
    """
    problems: list[str] = []
    for cell in plan.cells():
        target_id = cell.target_id if isinstance(cell, TargetCell) else None
        digest = image_digest
        if plan.multi_target and target_id is not None:
            digest = (target_digests or {}).get(target_id)
        request = CellRequest(
            RdsArm(cell.arm.label),
            cell.seed,
            cell.budget,
            engine_sha,
            engine_dirty,
            digest,
            plan.sentinel_request(),
            observer_integrity_policy,
            experiment_id=plan.plan,
            execution_mode=plan.execution_mode,
            jobs=jobs,
            target_id=target_id if plan.multi_target else None,
        )
        for item in preregistration_mismatches(plan.preregistration, request):
            if item not in problems:
                problems.append(item)
    if plan.multi_target:
        text, sha = ledger if ledger is not None else (None, None)
        for item in ledger_problems(plan.preregistration, text, sha):
            if item not in problems:
                problems.append(item)
    return tuple(problems)


def read_ledger(path: Path | None) -> tuple[str | None, str | None]:
    """(text, sha256) of the exposure ledger file, or (None, None) when unreadable."""
    if path is None or not path.is_file():
        return None, None
    data = path.read_bytes()
    return data.decode("utf-8"), hashlib.sha256(data).hexdigest()


def post_check(plan: Exp0Plan) -> Any:
    """Report-level conformance to the registration (image id, sentinel set)."""
    prereg = plan.preregistration

    def check(report: Mapping[str, Any] | None, cell: Cell) -> str | None:
        if report is None or "aborted" in report:
            return None
        expected = cell.digest if isinstance(cell, TargetCell) else prereg.image_digest
        kind = cell.digest_kind if isinstance(cell, TargetCell) else "image"
        field = "image_id" if kind == "image" else "lock_digest"
        recorded = report.get(field)
        if recorded != expected:
            return f"report {field} {recorded!r} != preregistered {expected}"
        if prereg.sentinel_generator_seed is not None:
            recorded = report.get("sentinel_set")
            if not isinstance(recorded, Mapping):
                return "preregistered sentinel set but the report records no sentinel_set"
            expected = plan.sentinel_request() or {}
            for key in ("generator_id", "generator_seed", "count"):
                if expected.get(key) is not None and recorded.get(key) != expected[key]:
                    return f"report sentinel_set.{key} {recorded.get(key)!r} != {expected[key]!r}"
        return None

    return check


def exp0_status(plan: str, cells: Any, vocabulary_equal: bool) -> dict[str, Any]:
    complete = sum(1 for cell in cells if cell["complete"])
    invalid = sum(1 for cell in cells if cell.get("invalid"))
    aborts = sum(1 for cell in cells if not cell["complete"] and not cell.get("invalid"))
    return {
        "plan": plan,
        "rule": "all preregistered cells complete and conformant; vocabulary equal across arms",
        "cells": len(cells),
        "complete": complete,
        "aborts": aborts,
        "invalid": invalid,
        "vocabulary_equal_across_arms": vocabulary_equal,
        "pass": bool(cells) and complete == len(cells) and vocabulary_equal,
    }


def cell_is_complete(plan: Exp0Plan, cell: Cell, output: Path) -> bool:
    """A cell counts as done only when its report is complete AND conformant."""
    paths = cell_paths(cell, output)
    if not paths["report"].is_file():
        return False
    try:
        loaded = load_cell_files(paths["report"], paths["steps_jsonl"])
    except (ReportFormatError, ValueError, json.JSONDecodeError):
        return False
    if loaded.report is None or loaded.aborted_at_step is not None:
        return False
    if len(loaded.records) != cell.budget or loaded.steps_from != "report":
        return False
    config = plan.cell_config(cell)
    recorded = loaded.report.get("config")
    if not isinstance(recorded, Mapping) or (
        recorded.get("random_seed") != config.random_seed
        or recorded.get("execution_budget") != config.execution_budget
        or recorded.get("search_policy") != config.search_policy.value
        or recorded.get("mutation_policy") != config.mutation_policy.value
    ):
        return False
    return post_check(plan)(loaded.report, cell) is None


def recorded_terminations(output: Path) -> set[str]:
    """Run ids whose termination a launcher invocation recorded in ``matrix.json``."""
    path = output / "matrix.json"
    if not path.is_file():
        return set()
    try:
        matrix = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    cells = matrix.get("cells") if isinstance(matrix, Mapping) else None
    if not isinstance(cells, list):
        return set()
    return {c["run_id"] for c in cells if isinstance(c, Mapping) and "run_id" in c}


def load_abort_decisions(output: Path) -> dict[str, dict[str, Any]]:
    """``abort-decisions.json``: run id -> {final, note, abort_reason, recorded_at}."""
    path = output / ABORT_DECISIONS_FILE
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return dict(loaded) if isinstance(loaded, Mapping) else {}


def cell_state(
    plan: Exp0Plan,
    cell: Cell,
    output: Path,
    decisions: Mapping[str, Mapping[str, Any]],
    terminated: Collection[str],
) -> str:
    """Terminal-state classification of one planned cell.

    ``complete``: report complete and conformant. ``abort-final``: an abort record
    exists (report with an abort record, or steps on disk with a recorded
    termination) and it was marked final (``--finalize-abort``; the manual
    classification step of the run procedure until #203's reason classifier lands).
    ``abort-pending``: an abort record exists but is not final (the next invocation
    re-runs it). ``unattempted``: no record at all (never started, in progress, or a
    controller that died before writing anything).
    """
    if cell_is_complete(plan, cell, output):
        return "complete"
    paths = cell_paths(cell, output)
    has_record = paths["report"].is_file() or (
        paths["steps_jsonl"].is_file() and cell.run_id in terminated
    )
    if not has_record:
        return "unattempted"
    return "abort-final" if decisions.get(cell.run_id, {}).get("final") else "abort-pending"


def record_abort_final(plan: Exp0Plan, output: Path, run_id: str, note: str | None) -> None:
    """Mark a cell's abort record final (a result, not a retry candidate); fail-closed."""
    cells = {cell.run_id: cell for cell in plan.cells()}
    if run_id not in cells:
        raise SystemExit(f"--finalize-abort {run_id}: not a planned cell")
    decisions = load_abort_decisions(output)
    state = cell_state(plan, cells[run_id], output, decisions, recorded_terminations(output))
    if state == "complete":
        raise SystemExit(f"--finalize-abort {run_id}: the cell is complete, nothing to finalize")
    if state == "unattempted":
        raise SystemExit(f"--finalize-abort {run_id}: no abort record on disk to finalize")
    paths = cell_paths(cells[run_id], output)
    reason: str | None = "no report written"
    if paths["report"].is_file():
        report = json.loads(paths["report"].read_text(encoding="utf-8"))
        aborted = report.get("aborted") if isinstance(report, Mapping) else None
        reason = (
            str(aborted.get("reason")) if isinstance(aborted, Mapping) else "report not complete"
        )
    decisions[run_id] = {
        "final": True,
        "note": note,
        "abort_reason": reason,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    (output / ABORT_DECISIONS_FILE).write_text(
        json.dumps(decisions, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _steps_prefix_consistent(records: Sequence[Mapping[str, Any]], steps: Sequence[Any]) -> bool:
    if len(records) > len(steps):
        return False
    for record, step in zip(records, steps, strict=False):
        if not isinstance(step, Mapping) or record.get("index") != step.get("index"):
            return False
        if record.get("oracle") != step.get("oracle"):
            return False
    return True


def evidence_integrity(plan: Exp0Plan, output: Path, states: Mapping[str, str]) -> list[str]:
    """Minimal per-cell file checks (the hash-level check is the raw manifest itself).

    Complete cells: report and steps file present and the steps file is a prefix of
    the report steps (index and oracle verdict agree). Abort records: the steps file
    is present; when the report carries steps they must agree the same way.
    """
    problems: list[str] = []
    for cell in plan.cells():
        state = states.get(cell.run_id, "unattempted")
        if state == "unattempted":
            continue
        paths = cell_paths(cell, output)
        if not paths["steps_jsonl"].is_file():
            problems.append(f"{cell.run_id}: steps file missing")
            continue
        if state == "complete" and not paths["report"].is_file():
            problems.append(f"{cell.run_id}: report missing")
            continue
        if not paths["report"].is_file():
            continue
        try:
            records = [
                json.loads(line)
                for line in paths["steps_jsonl"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            report = json.loads(paths["report"].read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            problems.append(f"{cell.run_id}: unreadable evidence ({error})")
            continue
        steps = report.get("steps") if isinstance(report, Mapping) else None
        if isinstance(steps, list) and not _steps_prefix_consistent(records, steps):
            problems.append(f"{cell.run_id}: steps file is not a prefix of the report steps")
    return problems


def verify_raw_manifest(
    output: Path, *, script: Path, python: str, manifest: Path
) -> dict[str, Any]:
    """Re-hash the output tree against the manifest just written (``--verify``)."""
    if not script.is_file() or not manifest.is_file():
        return {"verified": False, "reason": "manifest or script missing", "returncode": None}
    command = [python, str(script), "--verify", str(manifest), "--root", str(output)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "verified": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip()[-500:],
        "stderr": completed.stderr.strip()[-500:],
    }


def _remove_summaries(output: Path) -> None:
    for stale in (output / "summaries").glob("*.summary.json"):
        stale.unlink()


def archive_attempt(cell: Cell, output: Path) -> int | None:
    """Move an incomplete cell's files to ``attempts/``; returns the attempt number."""
    paths = cell_paths(cell, output)
    existing = [key for key in ("report", "steps_jsonl", "calls", "log") if paths[key].exists()]
    if not existing:
        return None
    attempts = output / "attempts"
    attempts.mkdir(exist_ok=True)
    number = 1
    while any(attempts.glob(f"{cell.run_id}.attempt{number}.*")):
        number += 1
    for key in existing:
        suffix = {
            "report": "json",
            "steps_jsonl": "steps.jsonl",
            "calls": "calls.jsonl",
            "log": "log",
        }[key]
        paths[key].rename(attempts / f"{cell.run_id}.attempt{number}.{suffix}")
    return number


def exp0_cell_env(
    plan: Exp0Plan, cell: Cell, output: Path, base_env: dict[str, str]
) -> dict[str, str]:
    subdir = getattr(cell, "subdir", None)
    env = cell_env(cell, output / subdir if subdir else output, base_env)
    prereg = plan.preregistration
    if prereg.sentinel_generator_seed is not None:
        env["DEMO_SENTINEL_SEED"] = str(prereg.sentinel_generator_seed)
        env["DEMO_SENTINEL_COUNT"] = str(prereg.sentinel_count)
    if prereg.observer_integrity_policy is not None:
        env[OBSERVER_ENV] = prereg.observer_integrity_policy
    if plan.execution_mode == WORKER_POOL_MODE:
        env[EXECUTION_MODE_ENV] = WORKER_POOL_MODE
        module = _worker_pool_module()
        if module is not None:
            # Lane 4's bring-up plan: dedicated s3wp- worker id (controller + volume).
            env.update(dict(module.plan_worker_bringup(cell.run_id, env).env))
    return env


def _controller_request_problems(plan: Exp0Plan) -> list[str]:
    """What the controller's own pre-bind check would refuse for each node-tar target.

    The controller checks a version and budget only when a cell starts, so a plan it
    cannot run would otherwise look fine until earlier targets have spent their budget.
    Calling the same function keeps one definition of what is admitted.
    """
    from scripts.run_effect_demo import _require_historical_request, historical_target_versions

    targets = [target for target in plan.targets() if target.extractor == "node-tar"]
    if not targets:
        return []
    try:
        allowed = historical_target_versions()
    except (OSError, ValueError) as error:
        return [f"controller version allowlist cannot be read: {error}"]
    problems: list[str] = []
    for target in targets:
        budget = target.budget if target.budget is not None else plan.preregistration.budget
        try:
            _require_historical_request(target.version, budget, allowed)
        except ValueError as error:
            problems.append(f"target {target.target_id}: {error}")
    return problems


def wiring_problems(plan: Exp0Plan) -> tuple[str, ...]:
    prereg = plan.preregistration
    problems: list[str] = []
    for target in plan.targets():
        if target.extractor != "node-tar":
            problems.append(
                f"target {target.target_id}: extractor {target.extractor!r} has no controller "
                f"wiring in {SCRIPT.name} (demo-historical runs node-tar only)"
            )
        if target.digest_kind == "lock":
            problems.append(
                f"target {target.target_id}: lock_digest targets need the controller to record "
                "lock_digest in the report (in-process wiring pending)"
            )
    problems.extend(_controller_request_problems(plan))
    if prereg.sentinel_generator_seed is not None and not all(_script_has(v) for v in SENTINEL_ENV):
        problems.append(
            f"preregistration declares a sentinel set but {SCRIPT.name} does not consume "
            f"{'/'.join(SENTINEL_ENV)} (lane 7 wiring pending)"
        )
    if prereg.observer_integrity_policy is not None and not _script_has(OBSERVER_ENV):
        problems.append(
            f"preregistration declares observer_integrity_policy but {SCRIPT.name} does not "
            f"consume {OBSERVER_ENV} (controller wiring pending)"
        )
    if plan.execution_mode == WORKER_POOL_MODE:
        if _worker_pool_module() is None:
            problems.append(
                "execution_mode worker-pool needs inodefence.execution.worker_pool "
                "(lane 4 PR #224 base) — not importable here"
            )
        if not _script_has(EXECUTION_MODE_ENV):
            problems.append(
                f"execution_mode worker-pool but {SCRIPT.name} does not consume "
                f"{EXECUTION_MODE_ENV} (controller worker-campaign wiring pending)"
            )
    return tuple(problems)


def write_registration(
    plan: Exp0Plan,
    output: Path,
    *,
    engine_sha: str | None,
    image_digest: str | None,
    preregistration_commit: str | None = None,
) -> dict[str, Any]:
    """Create or re-validate the directory's registration record."""
    path = output / REGISTRATION_FILE
    record = {
        "label": plan.labels(engine_sha),
        "experiment_id": plan.plan,
        "preregistration_file": plan.preregistration_path.name,
        "preregistration_sha256": plan.preregistration_sha256,
        # Record only (not compared): the commit that registered the file, so the
        # three provenance values (engine_sha, registration commit, file sha256) sit
        # together when the engine checkout predates the registration commit.
        "preregistration_commit": preregistration_commit,
        "engine_sha": engine_sha,
        "image_digest": image_digest,
        "version": plan.version,
        "include_s_a": plan.include_s_a,
        "execution_mode": plan.execution_mode,
        "campaign_watchdog_seconds": plan.watchdog_seconds,
        "disk_pause_fraction": plan.disk_pause_fraction,
        "interim_analysis": plan.preregistration.interim_analysis,
        "targets": [target_record(target) for target in plan.targets()],
        "analysis_plan": plan.analysis_plan(),
        "cells": [cell.run_id for cell in plan.cells()],
    }
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        for key in ("preregistration_sha256", "engine_sha", "image_digest"):
            if existing.get(key) != record[key]:
                raise SystemExit(
                    f"{output} was registered under a different {key} "
                    f"({existing.get(key)!r} != {record[key]!r}); use a new directory"
                )
        record["created_at"] = existing.get("created_at")
        record["invocations"] = int(existing.get("invocations", 0)) + 1
    else:
        record["created_at"] = datetime.now(UTC).isoformat()
        record["invocations"] = 1
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def write_raw_manifest(
    output: Path, *, script: Path, python: str, host: str, date: str, out: Path | None
) -> dict[str, Any]:
    """Run make_raw_manifest over the output tree (completion condition 8)."""
    if not script.is_file():
        return {"generated": False, "reason": f"manifest script missing: {script}", "path": None}
    manifest = (
        out
        if out is not None
        else Path("experiments/summaries") / f"raw-manifest-{host}-{date}.sha256"
    )
    command = [
        python,
        str(script),
        "--root",
        str(output),
        "--host",
        host,
        "--date",
        date,
        "--out",
        str(manifest),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "generated": completed.returncode == 0 and manifest.is_file(),
        "path": str(manifest),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip()[-500:],
        "stderr": completed.stderr.strip()[-500:],
    }


# ---- scale controls: watchdog and disk pause ------------------------------------


class DiskUsageUnavailable(RuntimeError):
    """The output filesystem's usage cannot be measured; the launcher must not guess."""


def disk_usage_fraction(path: Path) -> float:
    """Used fraction of the filesystem holding ``path``; fail closed when unmeasurable.

    A zero-sized total means the measurement is meaningless (not "empty disk"), so
    this raises instead of returning 0.0 — returning a low number would silently
    skip the pause that protects the host. ``shutil.disk_usage`` errors propagate.
    """
    usage = shutil.disk_usage(path)
    if usage.total <= 0:
        raise DiskUsageUnavailable(f"disk usage of {path} reports total={usage.total}")
    return (usage.total - usage.free) / usage.total


def should_pause_for_disk(fraction: float, threshold: float) -> bool:
    module = _worker_pool_module()
    if module is not None:
        return bool(module.should_pause_for_disk(fraction, threshold))
    return fraction >= threshold


def wait_for_disk(
    output: Path,
    threshold: float,
    *,
    usage: Callable[[Path], float] = disk_usage_fraction,
    pause: Callable[[float], None] = sleep,
    poll_seconds: float = DISK_POLL_SECONDS,
    log: Callable[[str], None] = print,
) -> int:
    """Block while the output filesystem is at/above ``threshold``; returns pauses taken."""
    pauses = 0
    while should_pause_for_disk(usage(output), threshold):
        if pauses == 0:
            log(f"disk usage at/above {threshold:.0%}; pausing new cells")
        pauses += 1
        pause(poll_seconds)
    if pauses:
        log(f"disk usage below {threshold:.0%} after {pauses} pause(s); resuming")
    return pauses


def run_cell_with_watchdog(
    cell: Cell,
    output: Path,
    env: dict[str, str],
    bash: str,
    *,
    limit_seconds: float,
    popen: Callable[..., Any] = subprocess.Popen,
) -> CellResult:
    """``run_parallel_native._run_cell`` plus a wall-clock limit.

    Past the limit the smoke script is terminated (then killed); the cell's files so
    far stay on disk (``.steps.jsonl`` keeps completed steps) and the result carries
    ``WATCHDOG_RETURNCODE`` so the manifest records the kill. Such a cell is not
    complete and reruns on the next invocation.
    """
    evidence = output / f"{cell.evidence_basename}.json"
    log = output / f"{cell.run_id}.log"
    started = monotonic()
    with log.open("w", encoding="utf-8") as stream:
        process = popen(
            [bash, str(SCRIPT), cell.mode],
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            returncode = process.wait(timeout=limit_seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            returncode = WATCHDOG_RETURNCODE
            stream.write(f"\n[watchdog] terminated after {limit_seconds:.0f} s\n")
    return CellResult(
        cell=cell,
        returncode=returncode,
        wall_seconds=monotonic() - started,
        evidence=evidence,
        evidence_exists=evidence.is_file(),
        log=log,
    )


def _refusal_preview(mismatches: Sequence[str], wiring: Sequence[str]) -> list[str]:
    lines = ["would be refused at live run:"]
    if not mismatches and not wiring:
        lines.append("  (nothing)")
    for item in mismatches:
        lines.append(f"  - gate: {item}")
    for item in wiring:
        lines.append(f"  - wiring: {item}")
    return lines


def _print_dry_run(
    plan: Exp0Plan, output: Path, base_env: dict[str, str], pending: list[Cell]
) -> None:
    cells = plan.cells()
    prereg = plan.preregistration
    print(
        f"plan={plan.plan} cells={len(cells)} pending={len(pending)} seeds={list(prereg.seeds)} "
        f"budget={prereg.budget} arms={[a.label for a in plan.arms()]} "
        f"vocabulary={prereg.vocabulary_mode.value} execution_mode={plan.execution_mode} "
        f"watchdog_seconds={plan.watchdog_seconds:.0f} "
        f"disk_pause_fraction={plan.disk_pause_fraction} "
        f"interim_analysis={prereg.interim_analysis or 'unspecified'}"
    )
    print(f"warmup: BUILD_ONLY=1 bash {SCRIPT} demo-historical")
    pending_ids = {cell.run_id for cell in pending}
    for cell in cells:
        env = exp0_cell_env(plan, cell, output, base_env)
        shown = {
            key: env[key]
            for key in (
                "RUN_ID",
                "SKIP_BUILD",
                "TAR_VERSION",
                "DEMO_SEED",
                "DEMO_BUDGET",
                "DEMO_POLICY",
                "DEMO_MUTATION_POLICY",
                "DEMO_SENTINEL_SEED",
                "DEMO_SENTINEL_COUNT",
                OBSERVER_ENV,
                EXECUTION_MODE_ENV,
                "INODEFENCE_EVIDENCE_DIR",
            )
            if key in env
        }
        state = "pending" if cell.run_id in pending_ids else "complete (skip)"
        paths = cell_paths(cell, output)
        print(f"  {cell.run_id} [{state}]: bash {SCRIPT} demo-historical")
        print(f"    env: {json.dumps(shown, sort_keys=True)}")
        print(f"    report={paths['report']} summary={paths['summary']}")


def _pending_cells(plan: Exp0Plan, output: Path) -> tuple[list[Cell], list[str], list[str]]:
    """Cells to (re-)run, complete cells skipped, final aborts skipped (never re-run)."""
    decisions = load_abort_decisions(output)
    terminated = recorded_terminations(output)
    pending: list[Cell] = []
    skipped: list[str] = []
    skipped_final: list[str] = []
    for cell in plan.cells():
        state = cell_state(plan, cell, output, decisions, terminated)
        if state == "complete":
            skipped.append(cell.run_id)
        elif state == "abort-final":
            skipped_final.append(cell.run_id)
        else:
            pending.append(cell)
    return pending, skipped, skipped_final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--image-digest",
        help="sha256:<64 hex> of the image the cells will run (one-key registrations)",
    )
    parser.add_argument(
        "--target-digest",
        action="append",
        default=[],
        metavar="ID=sha256:…",
        help="digest resolved for a declared target (multi-target registrations; "
        "repeat once per target)",
    )
    parser.add_argument(
        "--exposure-ledger",
        type=Path,
        default=None,
        help="override the exposure ledger path (default: the file's exposure_ledger, "
        "relative to the current directory)",
    )
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--include-s-a", action="store_true", help="also run the declared S-a ablation"
    )
    parser.add_argument("--observer-integrity-policy", choices=("stop", "invalid-continue"))
    parser.add_argument(
        "--execution-mode",
        choices=EXECUTION_MODES,
        default=None,
        help="defaults to the file's execution_mode (else per-case-container); must match it",
    )
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="<= the file's jobs_max")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--python", default=None)
    parser.add_argument("--context", default=None)
    parser.add_argument(
        "--manifest-host", default=None, help="host label for the raw manifest name"
    )
    parser.add_argument("--manifest-out", type=Path, default=None)
    parser.add_argument("--manifest-script", type=Path, default=DEFAULT_MANIFEST_SCRIPT)
    parser.add_argument("--no-manifest", action="store_true")
    parser.add_argument(
        "--preregistration-commit",
        default=None,
        help="record-only: the git commit that registered the preregistration file "
        "(written to registration.json and the index; never compared by the gate)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    parser.add_argument(
        "--finalize-abort",
        action="append",
        default=[],
        metavar="RUN_ID[=NOTE]",
        help="mark a cell's abort record final (a result, right-censored, kept in the "
        "denominator; never re-run); the manual classification step until #203 lands",
    )
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be >= 1")

    try:
        prereg = load_preregistration(args.preregistration)
    except (PreregistrationFormatError, OSError) as error:
        print(f"preregistration unusable: {error}", file=sys.stderr)
        return 2
    if args.include_s_a and RdsArm.S_A not in prereg.arm_policies:
        parser.error("--include-s-a requested but the preregistration declares no arm.S-a")
    execution_mode = args.execution_mode or prereg.execution_mode or DEFAULT_EXECUTION_MODE
    file_sha = sha256(args.preregistration.read_bytes()).hexdigest()
    plan = Exp0Plan(
        prereg, args.preregistration, file_sha, args.version, args.include_s_a, execution_mode
    )
    source = capture_source()
    target_digests: dict[str, str] = {}
    for item in args.target_digest:
        target_id, sep, digest = item.partition("=")
        if not sep or not target_id.strip() or not digest.strip():
            print(f"--target-digest expects ID=sha256:…, got {item!r}", file=sys.stderr)
            return 2
        target_digests[target_id.strip()] = digest.strip()
    if plan.multi_target and args.image_digest is not None:
        print(
            "this registration declares targets; supply --target-digest ID=… per target "
            "instead of --image-digest",
            file=sys.stderr,
        )
        return 2
    if not plan.multi_target and target_digests:
        print(
            "this registration has the single image_digest; --target-digest does not apply",
            file=sys.stderr,
        )
        return 2
    ledger_path = args.exposure_ledger
    if ledger_path is None and prereg.exposure_ledger is not None:
        ledger_path = Path(prereg.exposure_ledger)
    mismatches = gate_mismatches(
        plan,
        engine_sha=source.revision,
        engine_dirty=source.dirty,
        image_digest=args.image_digest,
        observer_integrity_policy=args.observer_integrity_policy,
        jobs=args.jobs,
        target_digests=target_digests,
        ledger=read_ledger(ledger_path),
    )
    if prereg.unknown_keys:
        print(
            "warning: unknown preregistration keys (not compared): "
            + ", ".join(prereg.unknown_keys),
            file=sys.stderr,
        )
    output: Path = args.output
    base_env = dict(os.environ)
    if args.python:
        base_env["PYTHON"] = args.python
    if args.context:
        base_env["INODEFENCE_DOCKER_CONTEXT"] = args.context
    wiring = wiring_problems(plan)

    if args.dry_run:
        print("gate: PASS" if not mismatches else "gate: FAIL", f"({plan.gate_text()})")
        for target in plan.targets():
            print(
                f"target {target.target_id}: {target.extractor} {target.version} "
                f"role={target.role} hypothesis={target.hypothesis} exposure={target.exposure} "
                f"{target.digest_kind}_digest={target.digest[:19]}…"
            )
        for line in _refusal_preview(mismatches, wiring):
            print(line)
        pending = _pending_cells(plan, output)[0]
        _print_dry_run(plan, output, base_env, pending)
        return 0 if not mismatches and not wiring else 2
    if mismatches:
        print("refusing to run (preregistration gate):", file=sys.stderr)
        for item in mismatches:
            print(f"  - {item}", file=sys.stderr)
        return 2

    def finish(results: list[CellResult] | None) -> int:
        terminated = recorded_terminations(output) | {r.cell.run_id for r in results or ()}
        decisions = load_abort_decisions(output)
        states = {
            cell.run_id: cell_state(plan, cell, output, decisions, terminated)
            for cell in plan.cells()
        }
        counts = {state: sum(1 for s in states.values() if s == state) for state in CELL_STATES}
        pending_now = sum(1 for s in states.values() if s != "complete")
        problems = evidence_integrity(plan, output, states)
        reasons: list[str] = []
        if counts["unattempted"]:
            reasons.append(f"{counts['unattempted']} cell(s) unattempted (no record on disk)")
        if counts["abort-pending"]:
            reasons.append(
                f"{counts['abort-pending']} abort record(s) not final "
                "(classify with --finalize-abort or re-run)"
            )
        reasons.extend(f"evidence integrity: {problem}" for problem in problems)
        if args.no_manifest:
            reasons.append("raw manifest not generated (--no-manifest)")

        def write(redact: bool, manifest_state: Mapping[str, Any]) -> dict[str, Any]:
            if redact:
                _remove_summaries(output)
            return summarize_output(
                plan,
                output,
                labels=plan.labels(source.revision),
                gate=plan.gate_text(),
                verdict_fn=exp0_status,
                post_check=post_check(plan),
                extra={
                    "preregistration": {
                        "file": plan.preregistration_path.name,
                        "sha256": plan.preregistration_sha256,
                        "engine_sha": source.revision,
                        "image_digest": args.image_digest,
                        "experiment_id": plan.plan,
                        "commit": args.preregistration_commit,
                    },
                    "targets": [target_record(target) for target in plan.targets()],
                    "analysis_plan": plan.analysis_plan(),
                    "interim": {
                        "analysis": prereg.interim_analysis,
                        "redacted": redact,
                        "rule": INTERIM_RULE,
                        "reasons": list(reasons),
                        "pending_cells": pending_now,
                        "states": counts,
                        "cell_states": states,
                        "integrity_problems": problems,
                        "manifest": dict(manifest_state),
                    },
                },
                redact_outcomes=redact,
            )

        def update_registration(status: Mapping[str, Any]) -> None:
            path = output / REGISTRATION_FILE
            registration = json.loads(path.read_text(encoding="utf-8"))
            registration["last_status"] = status
            registration["cell_states"] = states
            registration["abort_decisions"] = decisions
            path.write_text(
                json.dumps(registration, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

        redact = plan.interim_forbidden and bool(reasons)
        document = write(redact, {"generated": None, "verified": None})
        status = document["g1_verdict"]
        # registration.json is updated BEFORE the manifest so the manifest covers its
        # final bytes; everything learned after the manifest goes to VERIFICATION_FILE
        # (an extra file, which #208's verifier reports but does not fail on).
        update_registration(status)
        manifest: dict[str, Any] = {"generated": False, "reason": "--no-manifest", "path": None}
        verification: dict[str, Any] = {"verified": False, "reason": "manifest not generated"}
        if not args.no_manifest:
            host = args.manifest_host or os.uname().nodename.split(".")[0]
            manifest = write_raw_manifest(
                output,
                script=args.manifest_script,
                python=args.python or sys.executable,
                host=host,
                date=datetime.now(UTC).strftime("%Y%m%d"),
                out=args.manifest_out,
            )
            if manifest["generated"]:
                verification = verify_raw_manifest(
                    output,
                    script=args.manifest_script,
                    python=args.python or sys.executable,
                    manifest=Path(manifest["path"]),
                )
        manifest_ok = bool(manifest["generated"] and verification["verified"])
        if not redact and plan.interim_forbidden and not args.no_manifest and not manifest_ok:
            reasons.append(
                "raw manifest verification failed"
                if manifest["generated"]
                else "raw manifest not generated"
            )
            redact = True
            document = write(True, {"generated": manifest["generated"], "verified": False})
            status = document["g1_verdict"]
            update_registration(status)
        (output / VERIFICATION_FILE).write_text(
            json.dumps(
                {
                    "checked_at": datetime.now(UTC).isoformat(),
                    "raw_manifest": manifest,
                    "verification": verification,
                    "outcomes_redacted": redact,
                    "redaction_reasons": reasons,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": status,
                    "raw_manifest": manifest,
                    "manifest_verification": verification,
                    "outcomes_redacted": redact,
                    "redaction_reasons": reasons,
                },
                sort_keys=True,
            )
        )
        if not manifest["generated"] and not args.no_manifest:
            print("raw manifest NOT generated (completion condition 8 unmet)", file=sys.stderr)
        elif manifest["generated"] and not verification["verified"]:
            print(
                "raw manifest verification FAILED (completion condition 8 unmet)", file=sys.stderr
            )
        evidence_ok = not problems and (manifest_ok or args.no_manifest)
        return 0 if status["pass"] and evidence_ok else 1

    output.mkdir(parents=True, exist_ok=True)
    for cell in plan.cells():
        subdir = getattr(cell, "subdir", None)
        if subdir:
            (output / subdir).mkdir(parents=True, exist_ok=True)
    write_registration(
        plan,
        output,
        engine_sha=source.revision,
        image_digest=args.image_digest,
        preregistration_commit=args.preregistration_commit,
    )
    for item in args.finalize_abort:
        run_id, _, note = item.partition("=")
        record_abort_final(plan, output, run_id.strip(), note.strip() or None)
    if args.summarize_only:
        return finish(None)

    if wiring:
        print("refusing to run (controller wiring):", file=sys.stderr)
        for item in wiring:
            print(f"  - {item}", file=sys.stderr)
        return 2
    bash = shutil.which("bash")
    if bash is None:
        raise SystemExit("bash not found: the native launcher runs only on the host terminal")
    pending, skipped, skipped_final = _pending_cells(plan, output)
    archived = {cell.run_id: archive_attempt(cell, output) for cell in pending}
    if pending and not args.skip_build:
        code = _warmup("demo-historical", output, base_env, bash)
        if code != 0:
            print(
                f"image warmup failed (exit {code}); see {output / 'warmup.log'}", file=sys.stderr
            )
            return code
    disk_pauses: dict[str, int] = {}

    def run_one(cell: Cell) -> CellResult:
        pauses = wait_for_disk(output, plan.disk_pause_fraction)
        if pauses:
            disk_pauses[cell.run_id] = pauses
        return run_cell_with_watchdog(
            cell,
            output,
            exp0_cell_env(plan, cell, output, base_env),
            bash,
            limit_seconds=plan.watchdog_seconds,
        )

    results: list[CellResult] = []
    if pending:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(run_one, pending))
    (output / "matrix.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now(UTC).isoformat(),
                "label": plan.labels(source.revision),
                "plan": plan.plan,
                "mode": "demo-historical",
                "execution_mode": plan.execution_mode,
                "jobs": args.jobs,
                "campaign_watchdog_seconds": plan.watchdog_seconds,
                "disk_pause_fraction": plan.disk_pause_fraction,
                "disk_pauses": disk_pauses,
                "host": {
                    "machine": os.uname().machine,
                    "system": os.uname().sysname,
                    "release": os.uname().release,
                },
                "skipped_complete": skipped,
                "skipped_final_aborts": skipped_final,
                "archived_attempts": {k: v for k, v in archived.items() if v is not None},
                "cells": [
                    {
                        "run_id": r.cell.run_id,
                        "target_id": getattr(r.cell, "target_id", r.cell.version),
                        "arm": r.cell.arm.label,
                        "seed": r.cell.seed,
                        "budget": r.cell.budget,
                        "returncode": r.returncode,
                        "watchdog_killed": r.returncode == WATCHDOG_RETURNCODE,
                        "wall_seconds": round(r.wall_seconds, 3),
                        "evidence": r.evidence.name,
                        "evidence_exists": r.evidence_exists,
                        "log": r.log.name,
                    }
                    for r in results
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return finish(results)


if __name__ == "__main__":
    raise SystemExit(main())

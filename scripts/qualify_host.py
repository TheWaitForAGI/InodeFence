"""Judge one host's qualification run (D047 draft) from run_exp0's own records: qualification.json.

    python -m scripts.qualify_host --preregistration <qualification.md> \\
        --seed-assignment <assignment.json> --host-id HOST1 --output <run dir> \\
        --criteria <criteria.json> --criteria-sha256 <fixed before measurement> \\
        --stage-a-keys <stage-a-j2-abort-keys.json> --stage-a-keys-sha256 <recorded> \\
        [--peer <other host's run dir>] --out <qualification.json>

The criteria file holds every threshold and the expected image ids; its sha256 must equal the value
fixed before measurement, so a threshold cannot move after the data are in. Criteria (each PASS or
FAIL with its value; any FAIL fails the host):

* cleanup UNKNOWN 0 (start-gate verdicts and acknowledgements), leftover resources 0 and Docker
  Engine, image ids and shared execution path unchanged from start to end (host pre/postflight);
  image ids equal the expected ids and, with ``--peer``, the other host's;
* watchdog 0, every planned cell recorded (complete or abort-final, no inconsistent or no-record
  cell), no gate-refused start, no infrastructure stop;
* first-attempt abort ratio over attempted cells at most the threshold: a cell whose first attempt
  left no record, aborted or was inconsistent counts even if the retry then succeeded; retries are
  reported apart; aborts in an "unknown" category (injected by the criteria file) must be 0;
* per arm, (timed_out steps + infrastructure re-executions) per 1000 recorded steps at most the
  threshold; the longest attempt at most the threshold on both clocks;
* no Stage A jobs=2 abort recurs at the same (search policy, seed, step index, case id).

Sealed: from steps files only ``index``, ``case_id`` and ``feedback.trace_termination``; from a
report only the ``aborted`` stub and ``infra_reexecutions``. No oracle value is read into the
output. Every file read is listed in the output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

from scripts.run_exp0 import DEFAULT_VERSION, HOST_RECORD_DIR, START_GATE_DIR, Exp0Plan
from scripts.run_g1_smoke import cell_paths

from inodefence.evaluation.abort_classification import classify_abort_reason
from inodefence.evaluation.cell_completeness import (
    ABORT_FINAL,
    CELL_RESULTS_FILE,
    COMPLETE,
    INFRASTRUCTURE_STOP_EVENT,
    START_DENIED_FIELD,
    counted_attempts,
    read_cell_results,
    read_infrastructure_events,
)
from inodefence.evaluation.rds_preregistration import load_preregistration
from inodefence.evaluation.seed_assignment import load_seed_assignment
from inodefence.execution.call_diagnostics import strip_annotation
from inodefence.execution.start_gate import ACKNOWLEDGED, CLEAN

CRITERIA_SCHEMA = "inodefence-host-qualification-criteria-v1"
CRITERIA_KEYS = frozenset(
    {
        "schema",
        "max_first_attempt_abort_ratio",
        "max_unstable_steps_per_1000",
        "max_cell_seconds",
        "expected_cells",
        "expected_image_ids",
        "expected_docker_engine",
        "expected_shared_path_sha256",
        "expected_execution_sha",
    }
)
#: The three image references a run uses (D047 section 4, Q6). The run_exp0 --expected-images file
#: uses the same ``expected_image_ids`` key.
LOCAL_IMAGE_NAMES = ("inodefence-controller:local", "inodefence-helper:local")
TARGET_IMAGE_PREFIX = "inodefence-node-tar-effect:"
SHA256_ID = re.compile(r"sha256:[0-9a-f]{64}")
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")


def abort_category(stub: Mapping[str, Any]) -> str:
    """The stub's recorded category, else the original reason's.

    #343 appends "; [last anomalous docker call: ...]" to an abort reason;
    :func:`~inodefence.execution.call_diagnostics.strip_annotation` removes it, so
    the category is the original reason's.
    """
    recorded = stub.get("category")
    if isinstance(recorded, str) and recorded:
        return recorded
    reason = stub.get("reason")
    if not isinstance(reason, str):
        return "none"
    return classify_abort_reason(strip_annotation(reason)).value


def unconfirmed_abort(stub: Mapping[str, Any] | None) -> bool:
    """D047 Q8 (W4, corrected 2026-11-11), applied to an abort cell: the benchmark's H4 test.

    Unconfirmed when (i) there is no report or no ``aborted`` object, (ii) ``error_chain`` ends with
    a truncation mark, or (iii) ``error_chain`` is missing or empty and the reason classifies as
    ``cleanup_inspect`` or ``cleanup_remove``. No chain with a non-cleanup reason is confirmed; a
    whole chain is confirmed even when its innermost (last) element is a cleanup error. The one
    definition lives in ``analyze_concurrency_benchmark.first_error``.
    """
    from scripts.analyze_concurrency_benchmark import first_error

    return first_error(stub)["status"] == "unconfirmed"


#: ``local_node_tar_smoke.sh``'s failure line in a cell log.
FAILED_STEP = re.compile(r"FAILED at step: .*")
FIRST_ERROR = re.compile(r"(Traceback|Error|error:|FAILED cleanup|INODEFENCE_CLEANUP_UNKNOWN)")
LOG_LINE_LIMIT = 300


def recovered_first_attempt(output: Path, run_id: str, reader: Reader) -> dict[str, Any]:
    """A retried cell's first attempt (``attempts/<run_id>.attempt1.log``): report only.

    Only the shell's ``FAILED at step`` line and the first error line are kept, cut short.
    """
    log = output / "attempts" / f"{run_id}.attempt1.log"
    found: dict[str, Any] = {
        "run_id": run_id,
        "log": log.name,
        "failed_at": None,
        "first_error": None,
    }
    if not log.is_file():
        found["log"] = None
        return found
    reader.files.append(str(log))
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        failed = FAILED_STEP.search(line)
        if found["failed_at"] is None and failed is not None:
            found["failed_at"] = failed.group(0)[:LOG_LINE_LIMIT]
        elif found["first_error"] is None and FIRST_ERROR.search(line):
            found["first_error"] = line.strip()[:LOG_LINE_LIMIT]
    return found


def clock_difference(pre: Mapping[str, Any] | None, peer_pre: Mapping[str, Any] | None) -> Any:
    """Cross-host realtime difference from both preflights' SNTP measurements: report only."""
    from scripts.measure_clock_offset import combine

    mine = (pre or {}).get("clock_reference", {}).get("measurement")
    theirs = (peer_pre or {}).get("clock_reference", {}).get("measurement")
    if not isinstance(mine, Mapping) or not isinstance(theirs, Mapping):
        return "not measured on both hosts (--clock-reference)"
    try:
        return combine(mine, theirs)
    except (KeyError, TypeError, ValueError) as error:
        return f"unusable: {type(error).__name__}: {error}"


def stage_a_environment_problems(plan: Exp0Plan, keys: Mapping[str, Any]) -> list[str]:
    """Why a recurrence test against these Stage A keys would not hold for this plan (pre-run).

    The qualification cells must share the Stage A cell environment: search policies, mutation
    policy, vocabulary, sentinel set and budget, and every key seed must be planned.
    """
    prereg = plan.preregistration
    stage = keys.get("environment")
    if not isinstance(stage, Mapping):
        return ["the Stage A key file has no environment record"]
    mine = {
        "search_policies": sorted({str(arm.search) for arm in plan.arms()}),
        "mutation_policy": plan.arms()[0].mutation,
        "vocabulary": prereg.vocabulary_mode.value,
        "sentinel_generator_id": prereg.sentinel_generator_id,
        "sentinel_generator_seed": prereg.sentinel_generator_seed,
        "sentinel_count": prereg.sentinel_count,
        "observer_integrity_policy": prereg.observer_integrity_policy,
        "budget": prereg.budget,
    }
    problems = [
        f"{key}: qualification {mine[key]!r} != Stage A {stage.get(key)!r}"
        for key in mine
        if mine[key] != stage.get(key)
    ]
    if len({arm.mutation for arm in plan.arms()}) != 1:
        problems.append("arms use different mutation policies")
    planned = set(plan.run_seeds)
    missing = sorted({int(key["seed"]) for key in keys.get("aborts", ())} - planned)
    if missing:
        problems.append(f"Stage A abort seeds not planned here: {missing}")
    if keys.get("image_digest") not in {target.digest for target in plan.targets()}:
        problems.append("Stage A image is not a target image here")
    return problems


class QualificationInputError(ValueError):
    """An input file is missing, malformed or not the one fixed before measurement."""


def load_criteria(path: Path, expected_sha256: str) -> dict[str, Any]:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise QualificationInputError(
            f"criteria file sha256 {digest} != the value fixed before measurement {expected_sha256}"
        )
    criteria = json.loads(data)
    if not isinstance(criteria, dict) or criteria.get("schema") != CRITERIA_SCHEMA:
        raise QualificationInputError(f"criteria schema must be {CRITERIA_SCHEMA}")
    if set(criteria) != CRITERIA_KEYS:
        raise QualificationInputError(f"criteria keys must be exactly {sorted(CRITERIA_KEYS)}")
    problems = criteria_problems(criteria)
    if problems:
        raise QualificationInputError("criteria file refused: " + "; ".join(problems))
    return criteria


def criteria_problems(criteria: Mapping[str, Any]) -> list[str]:
    """Every missing, empty or malformed criterion. A judgement never runs on a partial file."""
    problems: list[str] = []
    for key in ("max_first_attempt_abort_ratio", "max_unstable_steps_per_1000"):
        try:
            if Fraction(str(criteria[key])) < 0:
                problems.append(f"{key} must not be negative")
        except (ValueError, ZeroDivisionError):
            problems.append(f"{key} must be a decimal number")
    seconds = criteria["max_cell_seconds"]
    if isinstance(seconds, bool) or not isinstance(seconds, int | float) or seconds <= 0:
        problems.append("max_cell_seconds must be a positive number")
    cells = criteria["expected_cells"]
    if isinstance(cells, bool) or not isinstance(cells, int) or cells <= 0:
        problems.append("expected_cells must be a positive integer")
    images = criteria["expected_image_ids"]
    if not isinstance(images, Mapping):
        problems.append("expected_image_ids must be an object")
    else:
        targets = [name for name in images if str(name).startswith(TARGET_IMAGE_PREFIX)]
        if len(images) != 3 or len(targets) != 1 or not set(LOCAL_IMAGE_NAMES) <= set(images):
            problems.append(
                "expected_image_ids must name exactly one target image and "
                f"{', '.join(LOCAL_IMAGE_NAMES)}"
            )
        for name, image_id in images.items():
            if not isinstance(image_id, str) or SHA256_ID.fullmatch(image_id) is None:
                problems.append(f"expected_image_ids[{name}] must be sha256:<64 hex>")
    engines = criteria["expected_docker_engine"]
    if (
        not isinstance(engines, Mapping)
        or not engines
        or not set(engines) <= {"HOST1", "HOST2"}
        or not all(isinstance(v, str) and v for v in engines.values())
    ):
        problems.append("expected_docker_engine must map HOST1/HOST2 to non-empty versions")
    shared = criteria["expected_shared_path_sha256"]
    if (
        not isinstance(shared, Mapping)
        or not shared
        or not all(isinstance(v, str) and HEX64.fullmatch(v) for v in shared.values())
    ):
        problems.append("expected_shared_path_sha256 must map every shared file to a sha256")
    execution = criteria["expected_execution_sha"]
    if not isinstance(execution, str) or HEX40.fullmatch(execution) is None:
        problems.append("expected_execution_sha must be a 40-hex git commit")
    return problems


def reexecution_count(report: Mapping[str, Any], stub: Mapping[str, Any] | None) -> int:
    """Case re-executions (D047 Q9): the recorded count, not the length of the event list.

    ``infra_reexecutions`` lists every stall event, including the one that gave up and ended in
    the abort; ``infra_reexecution_count`` (report, or the abort stub) counts only the events
    whose ``action`` is ``reexecuted``. Without a count, those events are counted.
    """
    for source in (report, stub or {}):
        count = source.get("infra_reexecution_count")
        if isinstance(count, int) and not isinstance(count, bool):
            return count
    events = report.get("infra_reexecutions")
    if not isinstance(events, list):
        return 0
    return sum(
        1 for event in events if isinstance(event, Mapping) and event.get("action") == "reexecuted"
    )


class Reader:
    """Reads only the fields named in the module docstring and lists every file it opens."""

    def __init__(self) -> None:
        self.files: list[str] = []

    def _json(self, path: Path) -> Any:
        self.files.append(str(path))
        return json.loads(path.read_text(encoding="utf-8"))

    def steps(self, path: Path) -> tuple[list[str], int]:
        """(case ids, timed_out steps)."""
        self.files.append(str(path))
        case_ids: list[str] = []
        timed_out = 0
        if not path.is_file():
            return case_ids, timed_out
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                break
            case_ids.append(str(record.get("case_id")))
            feedback = record.get("feedback")
            if isinstance(feedback, Mapping) and feedback.get("trace_termination") == "timed_out":
                timed_out += 1
        return case_ids, timed_out

    def report_fields(self, path: Path) -> tuple[Mapping[str, Any] | None, int]:
        """(abort stub, infra re-execution count); nothing else leaves the report."""
        if not path.is_file():
            return None, 0
        report = self._json(path)
        stub = report.get("aborted") if isinstance(report, Mapping) else None
        stub = stub if isinstance(stub, Mapping) else None
        return stub, reexecution_count(report if isinstance(report, Mapping) else {}, stub)

    def record(self, path: Path) -> Any:
        return self._json(path)


#: D047 section 6 labels beside PASS and FAIL.
STOPPED_INPUT_DEPENDENT = "STOPPED-INPUT-DEPENDENT"
NOT_RUN = "NOT-RUN"


def _verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def host_pairs(
    output: Path, reader: Reader
) -> list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]]:
    """Every launcher call's (stamp, preflight, postflight); a resume adds a pair, none is dropped.

    A preflight without its postflight (a call that never reached the end) keeps ``None``.
    """
    host = output / HOST_RECORD_DIR
    stamps = sorted(
        {p.name[len("preflight-") : -len(".json")] for p in host.glob("preflight-*.json")}
        | {p.name[len("postflight-") : -len(".json")] for p in host.glob("postflight-*.json")}
    )
    pairs = []
    for stamp in stamps:
        pre, post = host / f"preflight-{stamp}.json", host / f"postflight-{stamp}.json"
        pairs.append(
            (
                stamp,
                reader.record(pre) if pre.is_file() else None,
                reader.record(post) if post.is_file() else None,
            )
        )
    return pairs


def record_problems(
    record: Mapping[str, Any] | None, criteria: Mapping[str, Any], host_id: str, where: str
) -> list[str]:
    """One pre- or postflight against the expected values (D047 Q6)."""
    if record is None:
        return [f"{where}: missing"]
    problems = [f"{where}: {problem}" for problem in record.get("problems") or ()]
    ids = record.get("image_ids") or {}
    for name, want in criteria["expected_image_ids"].items():
        if ids.get(name) != want:
            problems.append(f"{where}: image {name} is {ids.get(name)}, expected {want}")
    want_engine = criteria["expected_docker_engine"].get(host_id)
    if want_engine is None or record.get("docker_server") != want_engine:
        problems.append(
            f"{where}: docker engine {record.get('docker_server')}, expected {want_engine}"
        )
    hashes = record.get("shared_path_sha256") or {}
    expected = criteria["expected_shared_path_sha256"]
    differing = sorted(
        name for name in set(hashes) | set(expected) if hashes.get(name) != expected.get(name)
    )
    if differing:
        problems.append(f"{where}: shared path files differ from expected: {differing}")
    execution = record.get("execution_sha")
    # Required on the postflight too (W1 records capture_source() again there): the controller
    # runs the checkout's code, which the 16 shared-path hashes do not cover. A change reverted
    # before the postflight is not seen (limit; the host-only, detached-worktree rule covers it).
    revision = execution.get("revision") if isinstance(execution, Mapping) else None
    dirty = execution.get("dirty") if isinstance(execution, Mapping) else None
    if revision != criteria["expected_execution_sha"] or dirty is not False:
        problems.append(
            f"{where}: execution sha {revision} (dirty {dirty}), "
            f"expected {criteria['expected_execution_sha']} clean"
        )
    return problems


def gate_state(output: Path) -> dict[str, Any]:
    """Start-gate cells whose cleanup is not verified clean (D047 Q1).

    Every registered cell (``<cell>.session``) must end with ``S``. ``U``, a pending ``W`` or
    ``C``, or no verdict at all counts, and so does any acknowledgement (a person cleared a U).
    """
    gate = output / START_GATE_DIR
    states: dict[str, int] = {}
    cells = {p.name[: -len(".session")] for p in gate.glob("*.session")}
    cells |= {p.name[: -len(".verdict")] for p in gate.glob("*.verdict")}
    for cell in sorted(cells):
        verdict = gate / f"{cell}.verdict"
        text = verdict.read_text(encoding="utf-8").strip() if verdict.is_file() else ""
        state = text.split(maxsplit=1)[0] if text else "none"
        if state != CLEAN:
            states[state] = states.get(state, 0) + 1
    acknowledged = len([p for p in (gate / ACKNOWLEDGED).glob("*") if p.is_dir()])
    return {"not_clean": states, "acknowledged": acknowledged}


def judge(
    *,
    plan: Exp0Plan,
    output: Path,
    criteria: Mapping[str, Any],
    stage_a: Mapping[str, Any] | None,
    peer: Path | None,
) -> dict[str, Any]:
    reader = Reader()
    results: dict[str, dict[str, Any]] = {}
    reports: dict[str, Any] = {}
    recovered: list[dict[str, Any]] = []

    def put(name: str, ok: bool, value: Any, threshold: Any = None) -> None:
        results[name] = {"result": _verdict(ok), "value": value, "threshold": threshold}

    # Q6: every launcher call's pre- and postflight against the expected values.
    host_id = plan.host_id or ""
    pairs = host_pairs(output, reader)
    q6: list[str] = [] if pairs else ["no host preflight record"]
    for stamp, pre, post in pairs:
        q6 += record_problems(pre, criteria, host_id, f"preflight-{stamp}")
        q6 += record_problems(post, criteria, host_id, f"postflight-{stamp}")
    put(
        "engine_images_path_execution_sha",
        not q6,
        {"calls": len(pairs), "problems": q6},
        {
            "image_ids": criteria["expected_image_ids"],
            "docker_engine": criteria["expected_docker_engine"].get(host_id),
            "execution_sha": criteria["expected_execution_sha"],
            "shared_path_files": len(criteria["expected_shared_path_sha256"]),
        },
    )
    if peer is not None:
        peer_pairs = host_pairs(peer, reader)
        peer_problems: list[str] = [] if peer_pairs else ["peer has no host preflight record"]
        for stamp, peer_pre, peer_post in peer_pairs:
            for where, record in (
                (f"peer preflight-{stamp}", peer_pre),
                (f"peer postflight-{stamp}", peer_post),
            ):
                peer_host = str((record or {}).get("host_id") or "")
                peer_problems += record_problems(record, criteria, peer_host, where)
                for _, mine, _ in pairs[:1]:
                    for key in ("image_ids", "shared_path_sha256"):
                        if (
                            mine is not None
                            and record is not None
                            and mine.get(key) != record.get(key)
                        ):
                            peer_problems.append(f"{where}: {key} differs from this host")
        put("equal_to_peer", not peer_problems, peer_problems)
        reports["clock_difference"] = clock_difference(
            pairs[0][1] if pairs else None, peer_pairs[0][1] if peer_pairs else None
        )
    # Q1: every gate cell verified clean.
    gate = gate_state(output)
    put("cleanup_unknown", not gate["not_clean"] and gate["acknowledged"] == 0, gate, 0)

    # Exit records and cells.
    results_path = output / CELL_RESULTS_FILE
    reader.files.append(str(results_path))
    attempts_by_cell = read_cell_results(results_path)
    events = read_infrastructure_events(results_path)
    stops = sum(1 for event in events if event.get("event") == INFRASTRUCTURE_STOP_EVENT)
    denied = sum(
        1
        for tried in attempts_by_cell.values()
        for attempt in tried
        if attempt.ended is not None and isinstance(attempt.ended.get(START_DENIED_FIELD), str)
    )
    put("start_denied", denied == 0, denied, 0)
    put("infrastructure_stops", stops == 0, stops, 0)

    from scripts.run_exp0 import target_cell_check

    cells = plan.cells()
    states: dict[str, str] = {}
    watchdog = 0
    first_attempt_failures = 0
    retries = 0
    attempted = 0
    categories: dict[str, int] = {}
    longest = {"realtime": 0.0, "monotonic": 0.0}
    per_arm: dict[str, dict[str, int]] = {}
    unconfirmed = 0
    aborts_at: dict[tuple[str, int], tuple[int, str]] = {}
    paths: dict[tuple[str, int], list[str]] = {}
    policy_of = {arm.label: str(arm.search) for arm in plan.arms()}
    for cell in cells:
        files = cell_paths(cell, output)
        check = target_cell_check(plan, cell, output, attempts_by_cell)
        states[cell.run_id] = check.state
        tried = counted_attempts(attempts_by_cell.get(cell.run_id, ()))
        # Q3: every attempt the watchdog ended, the retried ones too, not only the last.
        watchdog += sum(
            1
            for attempt in tried
            if attempt.ended is not None and attempt.ended.get("watchdog_fired") is True
        )
        if not tried:
            continue
        attempted += 1
        retries += len(tried) - 1
        if len(tried) > 1 or check.state != COMPLETE:
            first_attempt_failures += 1
        if len(tried) > 1 and check.state == COMPLETE:
            recovered.append(recovered_first_attempt(output, cell.run_id, reader))
        # Q10 is per cell: its attempts' durations added up on each clock.
        cell_seconds = dict.fromkeys(longest, 0.0)
        for attempt in tried:
            if attempt.ended is None:
                continue
            for clock in longest:
                start = attempt.started.get("clocks", {}).get(clock)
                end = attempt.ended.get("clocks", {}).get(clock)
                if isinstance(start, int | float) and isinstance(end, int | float):
                    cell_seconds[clock] += end - start
        for clock in longest:
            longest[clock] = max(longest[clock], cell_seconds[clock])
        case_ids, timed_out = reader.steps(files["steps_jsonl"])
        stub, reexecutions = reader.report_fields(files["report"])
        arm = per_arm.setdefault(cell.arm.label, {"steps": 0, "timed_out": 0, "reexecutions": 0})
        arm["steps"] += len(case_ids)
        arm["timed_out"] += timed_out
        arm["reexecutions"] += reexecutions
        key = (policy_of[cell.arm.label], cell.seed)
        paths[key] = case_ids
        if check.state != COMPLETE:
            unconfirmed += unconfirmed_abort(stub)
        if stub is not None:
            category = abort_category(stub)
            categories[category] = categories.get(category, 0) + 1
            if isinstance(stub.get("step_index"), int):
                aborts_at[key] = (stub["step_index"], str(stub.get("case_id")))
    counts = {
        state: sum(1 for s in states.values() if s == state) for state in set(states.values())
    }
    complete_enough = len(cells) == int(criteria["expected_cells"]) and all(
        state in (COMPLETE, ABORT_FINAL) for state in states.values()
    )
    put("record_completeness", complete_enough, counts, criteria["expected_cells"])
    put("watchdog", watchdog == 0, watchdog, 0)
    ratio_limit = Fraction(str(criteria["max_first_attempt_abort_ratio"]))
    ratio = Fraction(first_attempt_failures, attempted) if attempted else None
    put(
        "first_attempt_abort_ratio",
        ratio is not None and ratio <= ratio_limit,
        {
            "failed_first_attempts": first_attempt_failures,
            "attempted_cells": attempted,
            "ratio": None if ratio is None else float(ratio),
            "retries": retries,
            "abort_categories": dict(sorted(categories.items())),
        },
        str(criteria["max_first_attempt_abort_ratio"]),
    )
    put("unconfirmed_aborts", unconfirmed == 0, unconfirmed, 0)
    step_limit = Fraction(str(criteria["max_unstable_steps_per_1000"]))
    unstable_ok = all(
        arm["steps"] > 0
        and Fraction((arm["timed_out"] + arm["reexecutions"]) * 1000, arm["steps"]) <= step_limit
        for arm in per_arm.values()
    )
    put(
        "unstable_steps_per_1000_by_arm",
        unstable_ok and bool(per_arm),
        dict(sorted(per_arm.items())),
        str(criteria["max_unstable_steps_per_1000"]),
    )
    seconds = float(criteria["max_cell_seconds"])
    put(
        "longest_cell_seconds",
        all(v <= seconds for v in longest.values()),
        {k: round(v, 3) for k, v in longest.items()},
        seconds,
    )

    # Stage A recurrence (input dependence).
    if stage_a is None:
        put("stage_a_recurrence", False, "no Stage A key file given")
    else:
        environment = stage_a_environment_problems(plan, stage_a)
        comparable = not environment
        recurrences = []
        same_path_to_abort = 0
        for key in stage_a.get("aborts", ()):
            where = (key["search_policy"], int(key["seed"]))
            if where not in paths:
                continue
            prefix = paths[where][: int(key["step_index"])]
            if (
                hashlib.sha256("\n".join(prefix).encode("utf-8")).hexdigest()
                == key["path_prefix_sha256"]
            ):
                same_path_to_abort += 1
            if aborts_at.get(where) == (int(key["step_index"]), key["case_id"]):
                recurrences.append({"seed": where[1], "step_index": key["step_index"]})
        put(
            "stage_a_recurrence",
            comparable and not recurrences,
            {
                "comparable": comparable,
                "environment_problems": environment,
                "recurrences": recurrences,
                "keys": len(stage_a.get("aborts", ())),
                "same_path_to_abort": same_path_to_abort,
            },
            0,
        )
    stage_a_value = results.get("stage_a_recurrence", {}).get("value")
    recurred = isinstance(stage_a_value, Mapping) and bool(stage_a_value.get("recurrences"))
    if not attempted:
        verdict = NOT_RUN
    elif recurred:
        # D047 section 5: input dependence stops the host and gives no qualification verdict.
        verdict = STOPPED_INPUT_DEPENDENT
    else:
        verdict = _verdict(all(r["result"] == "PASS" for r in results.values()))
    return {
        "classification": "host qualification judgement: counts and identifiers only, no oracle",
        # Report only, never a criterion: retry-recovered first attempts, the clock difference.
        "reports": {"recovered_first_attempts": recovered, **reports},
        "verdict": verdict,
        "criteria": results,
        "files_read": sorted(set(reader.files)),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--seed-assignment", type=Path, required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--output", type=Path, help="this host's run directory")
    parser.add_argument("--criteria", type=Path)
    parser.add_argument("--criteria-sha256")
    parser.add_argument("--stage-a-keys", type=Path)
    parser.add_argument("--stage-a-keys-sha256")
    parser.add_argument("--peer", type=Path, help="the other host's run directory")
    parser.add_argument(
        "--check-environment",
        action="store_true",
        help="before the run: is the Stage A recurrence test valid for these cells? (no run read)",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.check_environment and None in (args.output, args.criteria, args.criteria_sha256):
        parser.error("a judgement needs --output, --criteria and --criteria-sha256")
    if args.check_environment and args.stage_a_keys is None:
        parser.error("--check-environment needs --stage-a-keys")
    try:
        stage_a = None
        if args.stage_a_keys is not None:
            data = args.stage_a_keys.read_bytes()
            if hashlib.sha256(data).hexdigest() != args.stage_a_keys_sha256:
                raise QualificationInputError("Stage A key file is not the recorded one")
            stage_a = json.loads(data)
        prereg = load_preregistration(args.preregistration)
        assignment = load_seed_assignment(args.seed_assignment, prereg.seeds)
        plan = Exp0Plan(
            prereg,
            args.preregistration,
            hashlib.sha256(args.preregistration.read_bytes()).hexdigest(),
            DEFAULT_VERSION,
            False,  # as run_exp0 without --include-s-a: S-a never runs in EXP-3, EXP-2 or D047
            assignment=assignment,
            host_id=args.host_id,
        )
        if args.check_environment:
            assert stage_a is not None
            problems = stage_a_environment_problems(plan, stage_a)
            document: dict[str, Any] = {
                "classification": "pre-run Stage A environment check (no run record is read)",
                "input_dependence_test_valid": not problems,
                "problems": problems,
            }
        else:
            criteria = load_criteria(args.criteria, args.criteria_sha256)
            document = judge(
                plan=plan, output=args.output, criteria=criteria, stage_a=stage_a, peer=args.peer
            )
    except (QualificationInputError, OSError, ValueError, KeyError) as error:
        print(f"qualification refused: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    document["inputs"] = {
        "criteria_sha256": args.criteria_sha256,
        "stage_a_keys_sha256": args.stage_a_keys_sha256,
        "host_id": args.host_id,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.check_environment:
        valid = document["input_dependence_test_valid"]
        print(json.dumps({"input_dependence_test_valid": valid, "out": str(args.out)}))
        return 0 if valid else 1
    print(json.dumps({"verdict": document["verdict"], "out": str(args.out)}))
    return 0 if document["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

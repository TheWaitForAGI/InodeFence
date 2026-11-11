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
from inodefence.execution.start_gate import ACKNOWLEDGED, UNKNOWN

CRITERIA_SCHEMA = "inodefence-host-qualification-criteria-v1"
CRITERIA_KEYS = frozenset(
    {
        "schema",
        "max_first_attempt_abort_ratio",
        "max_unstable_steps_per_1000",
        "max_cell_seconds",
        "unknown_abort_categories",
        "expected_cells",
        "expected_image_ids",
    }
)


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
    return criteria


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
        reexecutions = report.get("infra_reexecutions") if isinstance(report, Mapping) else None
        count = len(reexecutions) if isinstance(reexecutions, list) else 0
        return (stub if isinstance(stub, Mapping) else None), count

    def record(self, path: Path) -> Any:
        return self._json(path)


def _verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _host_records(output: Path, reader: Reader) -> tuple[dict | None, dict | None]:
    host = output / HOST_RECORD_DIR
    pre = sorted(host.glob("preflight-*.json"))
    post = sorted(host.glob("postflight-*.json"))
    return (
        reader.record(pre[-1]) if pre else None,
        reader.record(post[-1]) if post else None,
    )


def _gate_unknowns(output: Path) -> tuple[int, int]:
    gate = output / START_GATE_DIR
    unknown = 0
    for verdict in gate.glob("*.verdict"):
        if verdict.read_text(encoding="utf-8").startswith(UNKNOWN):
            unknown += 1
    acknowledged = len([p for p in (gate / ACKNOWLEDGED).glob("*") if p.is_dir()])
    return unknown, acknowledged


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

    def put(name: str, ok: bool, value: Any, threshold: Any = None) -> None:
        results[name] = {"result": _verdict(ok), "value": value, "threshold": threshold}

    # Host guard records (start and end).
    pre, post = _host_records(output, reader)
    expected_ids = dict(criteria["expected_image_ids"])
    put(
        "host_preflight_recorded",
        pre is not None and not pre.get("problems"),
        None if pre is None else pre.get("problems"),
    )
    put(
        "host_postflight_recorded",
        post is not None and not post.get("problems"),
        None if post is None else post.get("problems"),
    )
    ids_ok = (
        pre is not None
        and post is not None
        and all(
            pre.get("image_ids", {}).get(name) == want
            and post.get("image_ids", {}).get(name) == want
            for name, want in expected_ids.items()
        )
    )
    put(
        "image_ids_expected_start_and_end",
        ids_ok,
        None if pre is None else pre.get("image_ids"),
        expected_ids,
    )
    unchanged = (
        pre is not None
        and post is not None
        and all(
            pre.get(key) == post.get(key)
            for key in ("docker_server", "image_ids", "shared_path_sha256")
        )
    )
    put(
        "engine_images_path_unchanged",
        unchanged,
        None if pre is None else {"docker_server": pre.get("docker_server")},
    )
    if peer is not None:
        peer_pre, _ = _host_records(peer, reader)
        same = (
            peer_pre is not None
            and pre is not None
            and all(
                peer_pre.get("image_ids", {}).get(name) == pre.get("image_ids", {}).get(name)
                for name in expected_ids
            )
        )
        put("image_ids_equal_to_peer", same, None)
    unknown, acknowledged = _gate_unknowns(output)
    put(
        "cleanup_unknown",
        unknown == 0 and acknowledged == 0,
        {"unknown_verdicts": unknown, "acknowledged": acknowledged},
        0,
    )

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
    unknown_categories = set(criteria["unknown_abort_categories"])
    unknown_aborts = 0
    aborts_at: dict[tuple[str, int], tuple[int, str]] = {}
    paths: dict[tuple[str, int], list[str]] = {}
    policy_of = {arm.label: str(arm.search) for arm in plan.arms()}
    for cell in cells:
        files = cell_paths(cell, output)
        check = target_cell_check(plan, cell, output, attempts_by_cell)
        states[cell.run_id] = check.state
        watchdog += bool(check.watchdog and check.state == ABORT_FINAL)
        tried = counted_attempts(attempts_by_cell.get(cell.run_id, ()))
        if not tried:
            continue
        attempted += 1
        retries += len(tried) - 1
        if len(tried) > 1 or check.state != COMPLETE:
            first_attempt_failures += 1
        for attempt in tried:
            if attempt.ended is None:
                continue
            for clock in longest:
                start = attempt.started.get("clocks", {}).get(clock)
                end = attempt.ended.get("clocks", {}).get(clock)
                if isinstance(start, int | float) and isinstance(end, int | float):
                    longest[clock] = max(longest[clock], end - start)
        case_ids, timed_out = reader.steps(files["steps_jsonl"])
        stub, reexecutions = reader.report_fields(files["report"])
        arm = per_arm.setdefault(cell.arm.label, {"steps": 0, "timed_out": 0, "reexecutions": 0})
        arm["steps"] += len(case_ids)
        arm["timed_out"] += timed_out
        arm["reexecutions"] += reexecutions
        key = (policy_of[cell.arm.label], cell.seed)
        paths[key] = case_ids
        if stub is not None:
            reason = stub.get("reason")
            category = classify_abort_reason(reason).value if isinstance(reason, str) else "none"
            categories[category] = categories.get(category, 0) + 1
            unknown_aborts += category in unknown_categories
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
    put("unknown_aborts", unknown_aborts == 0, unknown_aborts, 0)
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
        "longest_attempt_seconds",
        all(v <= seconds for v in longest.values()),
        {k: round(v, 3) for k, v in longest.items()},
        seconds,
    )

    # Stage A recurrence (input dependence).
    if stage_a is None:
        put("stage_a_recurrence", False, "no Stage A key file given")
    else:
        comparable = stage_a.get("budget") == plan.preregistration.budget and stage_a.get(
            "image_digest"
        ) in {t.digest for t in plan.targets()}
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
                "recurrences": recurrences,
                "keys": len(stage_a.get("aborts", ())),
                "same_path_to_abort": same_path_to_abort,
            },
            0,
        )
    return {
        "classification": "host qualification judgement: counts and identifiers only, no oracle",
        "verdict": _verdict(all(r["result"] == "PASS" for r in results.values())),
        "criteria": results,
        "files_read": sorted(set(reader.files)),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--seed-assignment", type=Path, required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="this host's run directory")
    parser.add_argument("--criteria", type=Path, required=True)
    parser.add_argument("--criteria-sha256", required=True)
    parser.add_argument("--stage-a-keys", type=Path)
    parser.add_argument("--stage-a-keys-sha256")
    parser.add_argument("--peer", type=Path, help="the other host's run directory")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        criteria = load_criteria(args.criteria, args.criteria_sha256)
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
    print(json.dumps({"verdict": document["verdict"], "out": str(args.out)}))
    return 0 if document["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

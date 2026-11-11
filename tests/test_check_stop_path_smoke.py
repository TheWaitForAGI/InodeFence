"""check_stop_path_smoke (#347): each D042 criterion passes on a synthetic correct run and fails
on a synthetic input that breaks it; snapshots carry no oracle value."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from scripts import check_stop_path_smoke as check

CELLS = ["c1", "c2", "c3", "c4", "c5", "c6"]
NO_RECORD = ["c1", "c2", "c3"]
REF = "D042-smoke-1-B-20261112-1000"
SENTINEL = "SENTINEL-ORACLE-VALUE-7f3a"
_tick = iter(range(10_000))


def _clock() -> dict[str, float]:
    t = float(next(_tick))
    return {"realtime": 1000.0 + t, "monotonic": t, "monotonic_raw": t}


def _ev(event: str, run_id: str | None = None, **fields: Any) -> dict[str, Any]:
    record: dict[str, Any] = {"event": event, **fields}
    if run_id is not None:
        record["run_id"] = run_id
    record.setdefault("clocks", _clock())
    return record


def _text(events: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(e, sort_keys=True) + "\n" for e in events)


def _docker(**override: Any) -> dict[str, Any]:
    return {"containers": [], "volumes": [], "context": "default", **override}


def _snap(stage: str, events: list[dict[str, Any]], **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "stage": stage,
        "env_historical_image": False,
        "exit_code": 0,
        "stderr": {"stop_in_effect": False, "gate_closed": False},
        "cell_results_text": _text(events),
        "files": {},
        "index": None,
        "verification": None,
        "summaries": {},
        "matrix_not_started": None,
        "gate": {},
        "gate_acknowledged": 0,
        "logs": {},
        "destroy_events": {},
        "preflight": [],
        "postflight": [],
        "docker": _docker(),
        "manifest": None,
    }
    return {**base, **fields}


def _redacted_index(states: dict[str, str], **fields: Any) -> dict[str, Any]:
    return {
        "cells": len(CELLS),
        "outcomes_redacted": True,
        "interim_redacted": True,
        "interim_reasons": 1,
        "interim_integrity_problems": 0,
        "interim_manifest": {"generated": None, "verified": None},
        "cells_with_outcome_keys": 0,
        "cells_with_summary": 0,
        "invalid_run_ids": [],
        "invalid_count": 0,
        "cell_states": states,
        "completeness": {
            "complete": 0,
            "aborts": 3,
            "no_record": 3,
            "record_inconsistent": 0,
            "unattempted": 3,
        },
        "infrastructure_stopped": True,
        "stops": 1,
        "resume_approval_refs": [],
        **fields,
    }


LOG_OK = {
    "failed_effect_demo_historical": True,
    "no_such_image": True,
    "unknown_marker": False,
    "engine_set": True,
}
CLEAN_LOG = {**LOG_OK, "failed_effect_demo_historical": False, "no_such_image": False}


def scenario(first_only: bool = False) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Snapshots of a correct round: three injected no-record cells stop the run, the
    cause is logged, the resume runs the rest, and a last call does nothing."""
    b1_events: list[dict[str, Any]] = []
    for run in NO_RECORD:
        b1_events += [
            _ev("start", run, attempt=1, jobs=2),
            _ev("end", run, attempt=1, returncode=1),
            _ev("start", run, attempt=2, jobs=2),
            _ev("end", run, attempt=2, returncode=1),
        ]
    if first_only:
        b1_events += [_ev("start", "c4", attempt=1, jobs=2), _ev("end", "c4", attempt=1)]
    b1_events.append(_ev(check.STOP, reason="3 consecutive cells without a record"))
    started = [*NO_RECORD, *(["c4"] if first_only else [])]
    states1 = {run: "no-record" if run in NO_RECORD else "unattempted" for run in CELLS}
    files1 = {f"attempts/{run}.attempt1.log": f"h-{run}-a1" for run in NO_RECORD}
    files1 |= {f"{run}.log": f"h-{run}" for run in NO_RECORD}
    files1 |= {"start-gate/c1.verdict": "g1", "host/preflight-1.json": "p1"}
    logs1 = {f"attempts/{run}.attempt1.log": dict(LOG_OK) for run in NO_RECORD}
    logs1 |= {f"{run}.log": dict(LOG_OK) for run in NO_RECORD}
    preflight1 = [{"file": "preflight-1.json", "problems": 0, "expected_images": True}]
    b1 = _snap(
        "b1",
        b1_events,
        exit_code=1,
        index=_redacted_index(states1),
        files=files1,
        matrix_not_started=[run for run in CELLS if run not in started],
        gate={run: "S" for run in NO_RECORD},
        logs=logs1,
        destroy_events={f"inodefence-local-controller-{run}": 2 for run in NO_RECORD},
        preflight=preflight1,
        postflight=[{"file": "postflight-1.json", "problems": 0, "expected_images": True}],
    )
    b2 = _snap(
        "b2",
        b1_events,
        index=_redacted_index(states1),
        files=dict(files1),
        stderr={"stop_in_effect": True, "gate_closed": False},
    )
    b4_events = [*b1_events, _ev(check.RESUME, approval_ref=REF)]
    rest = [run for run in CELLS if run not in started]
    if first_only:
        b4_events += [_ev("start", "c4", attempt=2, jobs=2), _ev("end", "c4", attempt=2)]
    for run in rest:
        b4_events += [_ev("start", run, attempt=1, jobs=2), _ev("end", run, attempt=1)]
    ran = ["c4", *rest] if first_only else rest
    states5 = {run: "no-record" if run in NO_RECORD else "complete" for run in CELLS}
    index5 = {
        **_redacted_index(states5),
        "outcomes_redacted": False,
        "interim_redacted": False,
        "interim_reasons": 0,
        "cells_with_summary": 3,
        "invalid_run_ids": list(NO_RECORD),
        "invalid_count": 3,
        "completeness": {
            "complete": 3,
            "aborts": 3,
            "no_record": 3,
            "record_inconsistent": 0,
            "unattempted": 0,
        },
        "infrastructure_stopped": False,
        "resume_approval_refs": [REF],
    }
    files5 = {
        **files1,
        **{f"inodefence-effect-demo-historical-{run}.calls.jsonl": f"k-{run}" for run in ran},
        **{f"{run}.log": f"h-{run}" for run in ran},
        "host/preflight-2.json": "p2",
        "host/postflight-2.json": "q2",
        "summaries/index.json": "i5",
        "registration.json": "r1",
        "matrix.json": "m1",
        "manifest-verification.json": "v1",
    }
    summaries5 = {
        run: {
            "readable": True,
            "dense_detail": run not in NO_RECORD,
            "record_inconsistent_prefix": False,
            "invalid_no_record": run in NO_RECORD,
        }
        for run in CELLS
    }
    logs5 = {**logs1, **{f"{run}.log": dict(CLEAN_LOG) for run in ran}}
    preflight5 = [
        *preflight1,
        {"file": "preflight-2.json", "problems": 0, "expected_images": True},
    ]
    later = {
        "index": index5,
        "files": files5,
        "summaries": summaries5,
        "logs": logs5,
        "preflight": preflight5,
        "postflight": [{"file": "postflight-2.json", "problems": 0, "expected_images": True}],
        "verification": {"generated": True, "verified": True},
        "gate": {run: "S" for run in NO_RECORD},
    }
    manifest = {"lines": 40, "sha256": "m" * 64}
    b4 = _snap("b4", b4_events, **copy.deepcopy(later))
    b5a = _snap("b5a", b4_events, **copy.deepcopy(later), manifest=manifest)
    b5b_later = copy.deepcopy(later)
    b5b_later["files"] |= {"registration.json": "r2", "matrix.json": "m2"}
    b5b_later["files"]["manifest-verification.json"] = "v2"
    b5b = _snap("b5b", b4_events, **b5b_later, manifest=dict(manifest))
    snaps = {
        "b0": _snap("b0", []),
        "b1": b1,
        "pre-b2": _snap("pre-b2", b1_events),
        "b2": b2,
        "pre-b4": _snap("pre-b4", b1_events),
        "b4": b4,
        "pre-b5a": _snap("pre-b5a", b4_events),
        "b5a": b5a,
        "pre-b5b": _snap("pre-b5b", b4_events, manifest=dict(manifest)),
        "b5b": b5b,
    }
    tools = {
        "stage": "tools",
        "analyze_rc": 0,
        "analyze_has_number_blocks_invalid_excluded": True,
        "manifest_verify_rc": 0,
    }
    return snaps, tools


def _judge(
    snaps: dict[str, dict[str, Any]], tools: dict[str, Any], cause: float = 500.0
) -> dict[str, dict[str, Any]]:
    return check.judge_b(snaps, tools, cause_logged_at=cause, round_number=1)


@pytest.mark.parametrize("first_only", [False, True])
def test_a_correct_round_passes_every_criterion(first_only: bool) -> None:
    snaps, tools = scenario(first_only)
    result = _judge(snaps, tools)
    expected = {
        "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "N1", "P1", "B1", "B2", "B3", "B4",
        "B5", "B6", "B7", "B8", "B9", "C1", "F1", "X1", "X2", "X3",
    }  # fmt: skip
    assert set(result) == expected
    assert {name: item["result"] for name, item in result.items() if item["result"] != "PASS"} == {}


Snaps = dict[str, dict[str, Any]]


def _drop_line(text: str, predicate: Callable[[dict[str, Any]], bool]) -> str:
    return _text([e for e in check._events(text) if not predicate(e)])


def _set(stage: str, *path: str | int, value: Any) -> Callable[[Snaps, dict[str, Any]], None]:
    def apply(snaps: Snaps, _tools: dict[str, Any]) -> None:
        target: Any = snaps[stage]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return apply


def _texts(stages: tuple[str, ...], predicate: Callable[[dict[str, Any]], bool]) -> Any:
    def apply(snaps: Snaps, _tools: dict[str, Any]) -> None:
        for stage in stages:
            snaps[stage]["cell_results_text"] = _drop_line(
                snaps[stage]["cell_results_text"], predicate
            )

    return apply


def _tool(key: str, value: Any) -> Any:
    def apply(_snaps: Snaps, tools: dict[str, Any]) -> None:
        tools[key] = value

    return apply


def _extra_first_attempts(snaps: Snaps, _tools: dict[str, Any]) -> None:
    events = check._events(snaps["b1"]["cell_results_text"])
    extra = [
        _ev("start", "c5", attempt=1, jobs=2),
        _ev("end", "c5", attempt=1),
        _ev("start", "c6", attempt=1, jobs=2),
        _ev("end", "c6", attempt=1),
    ]
    snaps["b1"]["cell_results_text"] = _text([*events[:-1], *extra, events[-1]])


def _drop_calls(snaps: Snaps, _tools: dict[str, Any]) -> None:
    files = snaps["b5b"]["files"]
    del files["inodefence-effect-demo-historical-c5.calls.jsonl"]


B5_LATER = ("b4", "b5a", "b5b")
FAILURES: list[tuple[str, Any, bool]] = [
    ("A1", _set("b1", "exit_code", value=2), False),
    ("A1", _texts(("b1",), lambda e: e.get("event") == check.STOP), False),
    ("A2", _set("b1", "index", "completeness", "no_record", value=2), False),
    ("A3", _set("b5b", "files", "attempts/c1.attempt1.log", value="changed"), False),
    ("A3", _texts(("b1",), lambda e: e.get("run_id") == "c2" and e.get("attempt") == 2), False),
    ("A4", _set("b1", "matrix_not_started", value=["c4"]), False),
    ("A5", _extra_first_attempts, False),
    ("A6", _set("b1", "docker", "context", value="desktop-linux"), False),
    ("A7", _set("b5b", "verification", "verified", value=False), False),
    ("A7", _set("b5b", "index", "interim_manifest", "verified", value=True), False),
    ("A7", _set("b2", "index", "cells_with_outcome_keys", value=1), False),
    ("A7", _tool("manifest_verify_rc", 1), False),
    ("A8", _set("b1", "logs", "c1.log", "unknown_marker", value=True), False),
    ("A8", _set("b1", "logs", "attempts/c2.attempt1.log", "no_such_image", value=False), False),
    ("N1", _set("b2", "exit_code", value=1), False),
    ("N1", _set("b2", "stderr", "stop_in_effect", value=False), False),
    ("P1", None, False),
    ("B1", _set("b4", "index", "resume_approval_refs", value=[]), False),
    ("B2", _set("b4", "index", "infrastructure_stopped", value=True), False),
    ("B3", _texts(("b5b",), lambda e: e.get("run_id") == "c1" and e.get("attempt") == 2), False),
    ("B4", _texts(B5_LATER, lambda e: e.get("run_id") == "c4" and e.get("attempt") == 2), True),
    ("B5", _set("b5b", "index", "cell_states", "c5", value="abort-pending"), False),
    ("B6", _drop_calls, False),
    ("B7", _texts(("b2",), lambda e: e.get("run_id") == "c3" and e.get("event") == "end"), False),
    ("B8", _set("b5b", "index", "completeness", "complete", value=2), False),
    ("B9", _tool("analyze_rc", 1), False),
    ("B9", _set("b5b", "index", "invalid_run_ids", value=["c1", "c2"]), False),
    ("C1", _set("b5b", "files", "summaries/index.json", value="other"), False),
    ("C1", _set("b5b", "files", "host/postflight-3.json", value="new"), False),
    ("C1", _set("b5b", "manifest", "sha256", value="n" * 64), False),
    ("F1", _set("b5b", "summaries", "c5", "dense_detail", value=False), False),
    ("F1", _set("b5b", "summaries", "c1", "dense_detail", value=True), False),
    ("F1", _set("b5b", "summaries", "c2", "invalid_no_record", value=False), False),
    ("F1", _set("b5b", "summaries", "c6", "record_inconsistent_prefix", value=True), False),
    ("X1", _set("b1", "gate", "c1", value="U"), False),
    ("X1", _set("b1", "destroy_events", "inodefence-local-controller-c2", value=1), False),
    ("X2", _set("b4", "docker", "containers", value=["inodefence-local-controller-c4"]), False),
    ("X2", _set("b5b", "postflight", 0, "problems", value=1), False),
    ("X3", _set("pre-b4", "env_historical_image", value=True), False),
    ("X3", _set("b5b", "logs", "c5.log", "no_such_image", value=True), False),
]


@pytest.mark.parametrize(("criterion", "mutate", "first_only"), FAILURES)
def test_each_criterion_fails_on_its_broken_input(
    criterion: str, mutate: Any, first_only: bool
) -> None:
    snaps, tools = scenario(first_only)
    cause = 500.0
    if mutate is None:
        cause = 5000.0  # the cause line after the resume
    else:
        mutate(snaps, tools)
    result = _judge(snaps, tools, cause)
    assert result[criterion]["result"] == "FAIL", result[criterion]


def test_c1_allows_exactly_the_three_rewritten_files() -> None:
    snaps, tools = scenario()
    for name in check.C1_EXCEPTIONS:
        snaps["b5b"]["files"][name] = "rewritten"
    assert _judge(snaps, tools)["C1"]["result"] == "PASS"
    assert set(check.C1_EXCEPTIONS) == {
        "registration.json",
        "matrix.json",
        "manifest-verification.json",
    }


def test_a_missing_stage_is_a_failure_not_a_pass() -> None:
    snaps, tools = scenario()
    del snaps["pre-b5a"]
    result = _judge(snaps, tools)
    assert list(result) == ["inputs"] and result["inputs"]["result"] == "FAIL"


# ---- scenario A -----------------------------------------------------------------------------


def scenario_a() -> dict[str, dict[str, Any]]:
    a1_events = [
        _ev("start", "c1", attempt=1, jobs=2),
        _ev("start", "c2", attempt=1, jobs=2),
        _ev(check.STOP, reason="start gate: cleanup unknown for c1"),
    ]
    ack = {"path": "start-gate/acknowledged/c1", "cell": "c1", "note_sha256": "a" * 64}
    a2_events = [
        *a1_events,
        _ev(check.RESUME, approval_ref="D042-smoke-1-A-20261112-1100", gate_acks=[ack]),
    ]
    return {
        "a1": _snap("a1", a1_events, exit_code=1),
        "a-refused": _snap(
            "a-refused",
            a1_events,
            exit_code=2,
            stderr={"stop_in_effect": True, "gate_closed": True},
        ),
        "a2": _snap("a2", a2_events),
        "a-final": _snap("a-final", a2_events, postflight=[{"file": "p", "problems": 0}]),
    }


def test_a_correct_scenario_a_passes() -> None:
    result = check.judge_a(scenario_a())
    assert {name: item["result"] for name, item in result.items()} == {
        f"SA{n}": "PASS" for n in range(1, 7)
    }


def _a_reason(snaps: Snaps) -> None:
    events = check._events(snaps["a1"]["cell_results_text"])
    events[-1]["reason"] = "3 consecutive cells without a record"
    snaps["a1"]["cell_results_text"] = _text(events)


def _a_late_start(snaps: Snaps) -> None:
    events = check._events(snaps["a1"]["cell_results_text"])
    snaps["a1"]["cell_results_text"] = _text([*events, _ev("start", "c3", attempt=1, jobs=2)])


def _a_ack_without_note(snaps: Snaps) -> None:
    events = check._events(snaps["a2"]["cell_results_text"])
    del events[-1]["gate_acks"][0]["note_sha256"]
    snaps["a2"]["cell_results_text"] = _text(events)


@pytest.mark.parametrize(
    ("criterion", "mutate"),
    [
        ("SA1", _a_reason),
        ("SA2", _a_late_start),
        ("SA3", lambda s: s["a-refused"].update(exit_code=0)),
        ("SA3", lambda s: s["a-refused"]["stderr"].update(gate_closed=False)),
        ("SA4", lambda s: s["a2"].update(exit_code=2)),
        ("SA5", _a_ack_without_note),
        ("SA6", lambda s: s["a2"]["docker"].update(volumes=["inodefence-local-x"])),
        ("SA6", lambda s: s["a-final"]["postflight"][0].update(problems=1)),
    ],
)
def test_each_scenario_a_criterion_fails_on_its_broken_input(
    criterion: str, mutate: Callable[[Snaps], None]
) -> None:
    snaps = scenario_a()
    mutate(snaps)
    assert check.judge_a(snaps)[criterion]["result"] == "FAIL"


# ---- snapshots read no oracle value ---------------------------------------------------------


def _output_with_sentinels(root: Path) -> Path:
    out = root / "out"
    (out / "summaries").mkdir(parents=True)
    (out / "start-gate" / "acknowledged" / "c1").mkdir(parents=True)
    (out / "host").mkdir()
    (out / "attempts").mkdir()
    (out / "cell-results.jsonl").write_text(
        _text([_ev("start", "c1", attempt=1, jobs=2), _ev("end", "c1", attempt=1)]),
        encoding="utf-8",
    )
    cells = [
        {"run_id": "c1", "invalid": True, "summary": "summaries/c1.summary.json"},
        {"run_id": "c2", "hit": SENTINEL, "t_first": SENTINEL, "summary": "s"},
    ]
    index = {
        "cells": cells,
        "outcomes_redacted": False,
        "invalid_count": 1,
        "interim": {
            "redacted": False,
            "reasons": [],
            "integrity_problems": [],
            "manifest": {"generated": None, "verified": None},
            "cell_states": {"c1": "no-record", "c2": "complete"},
        },
        "cell_completeness": {"complete": 1, "no_record": 1, "infrastructure_stopped": False},
        "g1_verdict": {"hits": SENTINEL},
    }
    (out / "summaries" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (out / "summaries" / "c1.summary.json").write_text(
        json.dumps({"invalid_reason": "ReportFormatError: no-record: x", "hit": SENTINEL}),
        encoding="utf-8",
    )
    (out / "summaries" / "c2.summary.json").write_text(
        json.dumps({"dense_detail": {"first": SENTINEL}, "t_first": SENTINEL}), encoding="utf-8"
    )
    (out / "c2.report.json").write_text(json.dumps({"oracle": SENTINEL}), encoding="utf-8")
    (out / "c1.log").write_text(
        "FAILED at step: effect-demo-historical\nengine=29.8.0\n" + SENTINEL, encoding="utf-8"
    )
    (out / "start-gate" / "c1.verdict").write_text("S\n", encoding="utf-8")
    (out / "host" / "events.jsonl").write_text(
        json.dumps({"Action": "destroy", "Actor": {"Attributes": {"name": "x-c1"}}}) + "\n",
        encoding="utf-8",
    )
    (out / "host" / "preflight-1.json").write_text(
        json.dumps({"problems": [], "expected_images": {"file": "c"}}), encoding="utf-8"
    )
    (out / check.VERIFICATION).write_text(
        json.dumps({"raw_manifest": {"generated": True}, "verification": {"verified": True}}),
        encoding="utf-8",
    )
    (out / "matrix.json").write_text(json.dumps({"cells_not_started": ["c3"]}), encoding="utf-8")
    return out


def test_a_snapshot_keeps_keys_counts_and_hashes_but_no_oracle_value(tmp_path: Path) -> None:
    out = _output_with_sentinels(tmp_path)
    manifest = tmp_path / "raw.sha256"
    manifest.write_text(
        f"{'1' * 64}  ./cell-results.jsonl\n{'2' * 64}  ./registration.json\n", encoding="utf-8"
    )

    def docker(*call: str) -> str:
        return "default" if call[:2] == ("context", "show") else ""

    snap = check.take_snapshot(
        out,
        "b5b",
        manifest=manifest,
        exit_code=0,
        stderr="infrastructure stop in effect",
        docker=docker,
        environ={},
    )
    assert SENTINEL not in json.dumps(snap)
    index = snap["index"]
    assert index["cells_with_outcome_keys"] == 1 and index["invalid_run_ids"] == ["c1"]
    assert index["interim_manifest"] == {"generated": None, "verified": None}
    assert snap["summaries"]["c1"] == {
        "readable": True,
        "dense_detail": False,
        "record_inconsistent_prefix": False,
        "invalid_no_record": True,
    }
    assert snap["summaries"]["c2"]["dense_detail"] is True
    assert snap["verification"] == {"generated": True, "verified": True}
    assert snap["gate"] == {"c1": "S"} and snap["gate_acknowledged"] == 1
    assert snap["destroy_events"] == {"x-c1": 1}
    assert snap["logs"]["c1.log"]["failed_effect_demo_historical"] is True
    assert snap["preflight"] == [
        {"file": "preflight-1.json", "problems": 0, "expected_images": True}
    ]
    assert snap["matrix_not_started"] == ["c3"]
    assert snap["stderr"]["stop_in_effect"] is True
    assert snap["docker"] == {"containers": [], "volumes": [], "context": "default"}
    assert snap["files"]["c2.report.json"]  # hashed, never read into the snapshot
    assert snap["manifest"]["lines"] == 1  # registration.json is a C1 exception line


def test_manifest_facts_ignore_only_the_three_exception_lines(tmp_path: Path) -> None:
    def facts(lines: list[str]) -> dict[str, Any] | None:
        path = tmp_path / "m.sha256"
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        return check.manifest_facts(path)

    base = [f"{'1' * 64}  ./cell-results.jsonl", f"{'2' * 64}  ./matrix.json"]
    same = [f"{'1' * 64}  ./cell-results.jsonl", f"{'3' * 64}  ./matrix.json"]
    other = [f"{'4' * 64}  ./cell-results.jsonl", f"{'2' * 64}  ./matrix.json"]
    nested = [f"{'1' * 64}  ./cell-results.jsonl", f"{'5' * 64}  ./host/matrix.json"]
    assert facts(base) == facts(same)
    assert facts(base) != facts(other)
    assert facts(base) != facts(nested)
    assert check.manifest_facts(tmp_path / "absent") is None


def test_snapshot_cli_records_a_stage_once(tmp_path: Path) -> None:
    out = _output_with_sentinels(tmp_path)
    snaps = tmp_path / "snaps"
    argv = ["snapshot", "--output", str(out), "--snapshots", str(snaps), "--stage", "b1"]
    assert check.main([*argv, "--no-docker", "--exit-code", "1"]) == 0
    assert check.main([*argv, "--no-docker"]) == 2
    assert SENTINEL not in (snaps / "b1.json").read_text(encoding="utf-8")


def test_judge_cli_writes_the_report_and_fails_on_missing_stages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snaps_dir = tmp_path / "snaps"
    snaps_dir.mkdir()
    snaps, tools = scenario()
    for stage, record in snaps.items():
        (snaps_dir / f"{stage}.json").write_text(json.dumps(record), encoding="utf-8")
    (snaps_dir / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    report = tmp_path / "judgement.json"
    argv = ["judge", "--snapshots", str(snaps_dir), "--round", "1", "--out", str(report)]
    assert check.main([*argv, "--cause-logged-at", "500"]) == 0
    assert json.loads(report.read_text(encoding="utf-8"))["passed"] is True
    (snaps_dir / "b2.json").unlink()
    report.unlink()
    assert check.main([*argv, "--cause-logged-at", "500"]) == 1
    assert "passed: False" in capsys.readouterr().out

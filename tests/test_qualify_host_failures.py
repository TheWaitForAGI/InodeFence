"""qualify_host: an input that should fail each criterion does fail it (W4 (C) part 2, 1-4, 6).

One clean run, then one change per test. A criterion that stays PASS on its own failing input is a
fail-open judge.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0
from scripts import qualify_host

from test_qualify_host import _criteria, _judge, _keys, _run_host1
from test_qualify_host import qual_guards as qual_guards
from test_run_exp0 import TARGET_IMAGES, VICTIM, _fake_runner
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine
from test_run_exp0_host_guards import FakeDocker
from test_run_exp0_host_guards import real_guards as real_guards


@pytest.fixture
def clean_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qual_guards: FakeDocker
) -> dict[str, Any]:
    _, prereg, assignment, host, cells = _run_host1(
        tmp_path, monkeypatch, _fake_runner(TARGET_IMAGES)
    )
    return {
        "prereg": prereg,
        "assignment": assignment,
        "host": host,
        "cells": cells,
        "tmp": tmp_path,
    }


def judge(run: dict[str, Any], **criteria: Any) -> dict[str, Any]:
    code, report, _ = _judge(
        run["prereg"],
        run["assignment"],
        run["host"],
        _criteria(run["tmp"], run["cells"], **criteria),
        _keys(run["tmp"], [], run["prereg"]),
        run["tmp"] / "q.json",
    )
    assert code in (0, 1), report
    return report


def result(report: dict[str, Any], name: str) -> str:
    return report["criteria"][name]["result"]


def rewrite_json(path: Path, change: Any) -> None:
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


def rewrite_lines(path: Path, change: Any) -> None:
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    path.write_text("".join(json.dumps(change(row)) + "\n" for row in rows))


def preflight(run: dict[str, Any]) -> Path:
    return next((run["host"] / run_exp0.HOST_RECORD_DIR).glob("preflight-*.json"))


pytestmark = pytest.mark.usefixtures("admit_fixture_holdout")


def test_the_clean_run_passes(clean_run: dict[str, Any]) -> None:
    report = judge(clean_run)
    assert report["verdict"] == "PASS", report["criteria"]


# ---- criteria file (3) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"expected_image_ids": {}},
        {"expected_image_ids": {"inodefence-node-tar-effect:7.5.2": "sha256:" + "a" * 64}},
        {"expected_docker_engine": {}},
        {"expected_docker_engine": {"HOST1": ""}},
        {"expected_shared_path_sha256": {}},
        {"expected_execution_sha": ""},
        {"max_first_attempt_abort_ratio": "x"},
        {"max_cell_seconds": 0},
        {"expected_cells": 0},
    ],
)
def test_an_incomplete_criteria_file_is_refused(clean_run: dict[str, Any], change: Any) -> None:
    code, report, _ = _judge(
        clean_run["prereg"],
        clean_run["assignment"],
        clean_run["host"],
        _criteria(clean_run["tmp"], clean_run["cells"], **change),
        _keys(clean_run["tmp"], [], clean_run["prereg"]),
        clean_run["tmp"] / "q.json",
    )
    assert code == 2 and report == {}


def test_a_missing_criteria_key_is_refused(clean_run: dict[str, Any]) -> None:
    import hashlib

    path, _ = _criteria(clean_run["tmp"], clean_run["cells"])
    criteria = json.loads(path.read_text())
    del criteria["expected_execution_sha"]
    path.write_text(json.dumps(criteria))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    code, report, _ = _judge(
        clean_run["prereg"],
        clean_run["assignment"],
        clean_run["host"],
        (path, digest),
        _keys(clean_run["tmp"], [], clean_run["prereg"]),
        clean_run["tmp"] / "q.json",
    )
    assert code == 2 and report == {}


# ---- Q6 (1, 2) --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["shared_path_sha256"].update({"scripts/run_exp0.py": "0" * 64}),
        lambda r: r.update(docker_server="28.0.0"),
        lambda r: r.update(execution_sha={"revision": "1" * 40, "dirty": False}),
        lambda r: r.update(
            execution_sha={"revision": r["execution_sha"]["revision"], "dirty": True}
        ),
        lambda r: r.pop("execution_sha"),
        lambda r: r["image_ids"].update({"inodefence-helper:local": "sha256:" + "9" * 64}),
    ],
)
def test_q6_checks_every_expected_value(clean_run: dict[str, Any], change: Any) -> None:
    rewrite_json(preflight(clean_run), change)
    assert result(judge(clean_run), "engine_images_path_execution_sha") == "FAIL"


def test_q6_judges_every_launcher_call(clean_run: dict[str, Any]) -> None:
    """A resume adds a pair; a change in an earlier pair is not hidden by a later clean one."""
    host = clean_run["host"] / run_exp0.HOST_RECORD_DIR
    pre, post = preflight(clean_run), next(host.glob("postflight-*.json"))
    earlier = "00000000T000000.000000Z"
    shutil.copy(pre, host / f"preflight-{earlier}.json")
    shutil.copy(post, host / f"postflight-{earlier}.json")
    assert result(judge(clean_run), "engine_images_path_execution_sha") == "PASS"
    rewrite_json(
        host / f"postflight-{earlier}.json",
        lambda r: r["image_ids"].update({"inodefence-controller:local": "sha256:" + "8" * 64}),
    )
    assert result(judge(clean_run), "engine_images_path_execution_sha") == "FAIL"
    (host / f"postflight-{earlier}.json").unlink()  # a call that never reached its end
    assert result(judge(clean_run), "engine_images_path_execution_sha") == "FAIL"


def test_q6_peer_with_a_different_shared_path_fails(clean_run: dict[str, Any]) -> None:
    peer = clean_run["tmp"] / "peer"
    shutil.copytree(clean_run["host"] / run_exp0.HOST_RECORD_DIR, peer / run_exp0.HOST_RECORD_DIR)
    for record in (peer / run_exp0.HOST_RECORD_DIR).glob("*flight-*.json"):
        rewrite_json(record, lambda r: r.update(host_id="HOST2"))
    args = ["--peer", str(peer)]
    code, report, _ = _judge_with(clean_run, args)
    assert report["criteria"]["equal_to_peer"]["result"] == "PASS"
    for record in (peer / run_exp0.HOST_RECORD_DIR).glob("*flight-*.json"):
        rewrite_json(
            record, lambda r: r["shared_path_sha256"].update({"scripts/run_exp0.py": "0" * 64})
        )
    code, report, _ = _judge_with(clean_run, args)
    assert report["criteria"]["equal_to_peer"]["result"] == "FAIL" and code == 1


def _judge_with(run: dict[str, Any], extra: list[str]) -> tuple[int, dict[str, Any], str]:
    criteria = _criteria(run["tmp"], run["cells"])
    keys = _keys(run["tmp"], [], run["prereg"])
    out = run["tmp"] / "qp.json"
    code = qualify_host.main(
        [
            "--preregistration",
            str(run["prereg"]),
            "--seed-assignment",
            str(run["assignment"]),
            "--host-id",
            "HOST1",
            "--output",
            str(run["host"]),
            "--criteria",
            str(criteria[0]),
            "--criteria-sha256",
            criteria[1],
            "--stage-a-keys",
            str(keys[0]),
            "--stage-a-keys-sha256",
            keys[1],
            "--out",
            str(out),
            *extra,
        ]
    )
    return code, json.loads(out.read_text()), out.read_text()


# ---- Q1 (4) -----------------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["W", "C", "U reason", None])
def test_q1_any_gate_cell_not_clean_fails(clean_run: dict[str, Any], verdict: str | None) -> None:
    gate = clean_run["host"] / run_exp0.START_GATE_DIR
    gate.mkdir(exist_ok=True)
    (gate / "cell-x.session").write_text("s\n")
    if verdict is not None:
        (gate / "cell-x.verdict").write_text(verdict + "\n")
    assert result(judge(clean_run), "cleanup_unknown") == "FAIL"


def test_q1_a_clean_verdict_passes(clean_run: dict[str, Any]) -> None:
    gate = clean_run["host"] / run_exp0.START_GATE_DIR
    gate.mkdir(exist_ok=True)
    (gate / "cell-x.session").write_text("s\n")
    (gate / "cell-x.verdict").write_text("S\n")
    assert result(judge(clean_run), "cleanup_unknown") == "PASS"


# ---- Q3, Q4, Q5, Q7, Q9, Q10 (4, 6) -------------------------------------------------------------


def test_q3_a_watchdog_on_a_retried_attempt_fails(clean_run: dict[str, Any]) -> None:
    results = clean_run["host"] / "cell-results.jsonl"
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    first = next(r for r in rows if r.get("event") == "end")
    # An earlier attempt of the same cell that the watchdog ended, renumbered before the last.
    extra_start = {
        **next(r for r in rows if r.get("event") == "start" and r["run_id"] == first["run_id"]),
        "attempt": 0,
    }
    extra_end = {**first, "attempt": 0, "watchdog_fired": True}
    results.write_text("".join(json.dumps(r) + "\n" for r in [extra_start, extra_end, *rows]))
    assert result(judge(clean_run), "watchdog") == "FAIL"


def test_q4_a_cell_without_its_record_fails(clean_run: dict[str, Any]) -> None:
    report = next(
        p for p in clean_run["host"].rglob("*.json") if VICTIM in p.name and "summary" not in p.name
    )
    report.unlink()
    assert result(judge(clean_run), "record_completeness") == "FAIL"


def test_q4_a_different_cell_count_fails(clean_run: dict[str, Any]) -> None:
    report = judge(clean_run, expected_cells=clean_run["cells"] + 1)
    assert result(report, "record_completeness") == "FAIL"


@pytest.mark.parametrize("event", ["stop", "denied"])
def test_q5_a_stop_or_a_denied_start_fails(clean_run: dict[str, Any], event: str) -> None:
    results = clean_run["host"] / "cell-results.jsonl"
    with results.open("a") as stream:
        if event == "stop":
            stream.write(
                json.dumps(
                    {"event": "infrastructure-stop", "reason": "x", "clocks": {"realtime": 1.0}}
                )
                + "\n"
            )
        else:
            stream.write(
                json.dumps(
                    {"event": "start", "run_id": "z", "attempt": 1, "clocks": {"realtime": 1.0}}
                )
                + "\n"
            )
            stream.write(
                json.dumps(
                    {
                        "event": "end",
                        "run_id": "z",
                        "attempt": 1,
                        "clocks": {"realtime": 1.0},
                        "returncode": None,
                        "start_denied": "gate",
                    }
                )
                + "\n"
            )
    name = "infrastructure_stops" if event == "stop" else "start_denied"
    assert result(judge(clean_run), name) == "FAIL"


def test_q7_an_abort_above_the_threshold_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qual_guards: FakeDocker
) -> None:
    behaviour: dict[str, Any] = {**TARGET_IMAGES, "abort": {VICTIM}}
    _, prereg, assignment, host, cells = _run_host1(tmp_path, monkeypatch, _fake_runner(behaviour))
    run = {
        "prereg": prereg,
        "assignment": assignment,
        "host": host,
        "cells": cells,
        "tmp": tmp_path,
    }
    assert result(judge(run), "first_attempt_abort_ratio") == "PASS"  # 1 of 12 under .30
    assert (
        result(judge(run, max_first_attempt_abort_ratio="0.05"), "first_attempt_abort_ratio")
        == "FAIL"
    )


def test_q9_timed_out_steps_above_the_threshold_fail(clean_run: dict[str, Any]) -> None:
    steps = next(p for p in clean_run["host"].rglob("*.steps.jsonl"))

    def timed_out(row: dict[str, Any]) -> dict[str, Any]:
        row.setdefault("feedback", {})["trace_termination"] = "timed_out"
        return row

    rewrite_lines(steps, timed_out)
    assert result(judge(clean_run), "unstable_steps_per_1000_by_arm") == "FAIL"


def test_q10_a_cell_over_the_time_limit_fails(clean_run: dict[str, Any]) -> None:
    assert result(judge(clean_run, max_cell_seconds=1e-9), "longest_attempt_seconds") == "FAIL"

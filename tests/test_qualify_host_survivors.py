"""FAIL paths for the judgements W4's a76ffee mutants showed untested (W4 delta, 20 survivors).

Each test names the mutant it kills. Q* are qualify_host, C* the path comparator, M* the holdout
assignment generator.
"""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0
from scripts import (
    compare_cell_paths,
    extract_stage_a_abort_keys,
    make_seed_assignment,
    qualify_host,
)

from test_compare_cell_paths import flip_judgement, steps, write
from test_qualify_host import _criteria, _judge, _keys, _run_host1
from test_qualify_host import qual_guards as qual_guards
from test_qualify_host_failures import (
    _judge_with,
    judge,
    preflight,
    result,
    rewrite_json,
)
from test_qualify_host_failures import clean_run as clean_run
from test_run_exp0 import TARGET_IMAGES, VICTIM, _fake_runner
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine
from test_run_exp0_host_guards import FakeDocker
from test_run_exp0_host_guards import real_guards as real_guards

pytestmark = pytest.mark.usefixtures("admit_fixture_holdout")
Q6 = "engine_images_path_execution_sha"


def records(run: dict[str, Any]) -> Path:
    return run["host"] / run_exp0.HOST_RECORD_DIR


# ---- Q6 -----------------------------------------------------------------------------------------


def test_q22b_a_later_resumed_pair_is_judged_too(clean_run: dict[str, Any]) -> None:
    host = records(clean_run)
    pre, post = preflight(clean_run), next(host.glob("postflight-*.json"))
    later = "99999999T999999.999999Z"
    shutil.copy(pre, host / f"preflight-{later}.json")
    shutil.copy(post, host / f"postflight-{later}.json")
    assert result(judge(clean_run), Q6) == "PASS"
    rewrite_json(host / f"preflight-{later}.json", lambda r: r.update(docker_server="1.0"))
    assert result(judge(clean_run), Q6) == "FAIL"


def test_q27_a_record_s_own_problems_fail(clean_run: dict[str, Any]) -> None:
    rewrite_json(preflight(clean_run), lambda r: r.update(problems=["leftover container"]))
    assert result(judge(clean_run), Q6) == "FAIL"


def test_q6n_no_launcher_record_fails(clean_run: dict[str, Any]) -> None:
    for record in records(clean_run).glob("*flight-*.json"):
        record.unlink()
    assert result(judge(clean_run), Q6) == "FAIL"


def test_q6_postflight_without_an_execution_sha_fails(clean_run: dict[str, Any]) -> None:
    post = next(records(clean_run).glob("postflight-*.json"))
    rewrite_json(post, lambda r: r.pop("execution_sha"))
    assert result(judge(clean_run), Q6) == "FAIL"


def _peer(run: dict[str, Any]) -> Path:
    peer = run["tmp"] / "peer"
    shutil.copytree(records(run), peer / run_exp0.HOST_RECORD_DIR)
    for record in (peer / run_exp0.HOST_RECORD_DIR).glob("*flight-*.json"):
        rewrite_json(record, lambda r: r.update(host_id="HOST2"))
    return peer


def test_q28b_a_peer_record_off_its_expected_engine_fails(clean_run: dict[str, Any]) -> None:
    peer = _peer(clean_run)
    args = ["--peer", str(peer)]
    assert _judge_with(clean_run, args)[1]["criteria"]["equal_to_peer"]["result"] == "PASS"
    for record in (peer / run_exp0.HOST_RECORD_DIR).glob("preflight-*.json"):
        rewrite_json(record, lambda r: r.update(docker_server="1.0"))
    assert _judge_with(clean_run, args)[1]["criteria"]["equal_to_peer"]["result"] == "FAIL"


def test_q28c_a_peer_image_set_unlike_this_host_fails(clean_run: dict[str, Any]) -> None:
    """An extra image id passes the expected-value check; only the host comparison sees it."""
    peer = _peer(clean_run)
    for record in (peer / run_exp0.HOST_RECORD_DIR).glob("preflight-*.json"):
        rewrite_json(record, lambda r: r["image_ids"].update({"extra:local": "sha256:" + "e" * 64}))
    report = _judge_with(clean_run, ["--peer", str(peer)])[1]
    assert report["criteria"]["equal_to_peer"]["result"] == "FAIL"


# ---- criteria file ------------------------------------------------------------------------------


def _refused(run: dict[str, Any], criteria: dict[str, Any]) -> bool:
    path = run["tmp"] / "criteria-x.json"
    path.write_text(json.dumps(criteria))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    code, report, _ = _judge(
        run["prereg"],
        run["assignment"],
        run["host"],
        (path, digest),
        _keys(run["tmp"], [], run["prereg"]),
        run["tmp"] / "q.json",
    )
    return code == 2 and report == {}


def _criteria_dict(run: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_criteria(run["tmp"], run["cells"])[0].read_text())


def test_q29_an_unknown_criteria_key_is_refused(clean_run: dict[str, Any]) -> None:
    assert _refused(clean_run, {**_criteria_dict(clean_run), "max_retries": 3})


def test_q29c_a_malformed_image_id_is_refused(clean_run: dict[str, Any]) -> None:
    criteria = _criteria_dict(clean_run)
    criteria["expected_image_ids"]["inodefence-helper:local"] = "sha256:not-hex"
    assert _refused(clean_run, criteria)


# ---- Q1 -----------------------------------------------------------------------------------------


def _gate(run: dict[str, Any]) -> Path:
    gate = run["host"] / run_exp0.START_GATE_DIR
    gate.mkdir(exist_ok=True)
    return gate


def test_q16_an_acknowledged_unknown_fails(clean_run: dict[str, Any]) -> None:
    gate = _gate(clean_run)
    (gate / "cell-x.session").write_text("s\n")
    (gate / "cell-x.verdict").write_text("S\n")
    (gate / qualify_host.ACKNOWLEDGED / "cell-x").mkdir(parents=True)
    assert result(judge(clean_run), "cleanup_unknown") == "FAIL"


def test_q1n_a_verdict_without_its_session_counts(clean_run: dict[str, Any]) -> None:
    (_gate(clean_run) / "cell-y.verdict").write_text("U reason\n")
    assert result(judge(clean_run), "cleanup_unknown") == "FAIL"


# ---- Q8, Q9, Q10 --------------------------------------------------------------------------------


@pytest.fixture
def aborted_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qual_guards: FakeDocker
) -> dict[str, Any]:
    behaviour: dict[str, Any] = {**TARGET_IMAGES, "abort": {VICTIM}}
    _, prereg, assignment, host, cells = _run_host1(tmp_path, monkeypatch, _fake_runner(behaviour))
    return {
        "prereg": prereg,
        "assignment": assignment,
        "host": host,
        "cells": cells,
        "tmp": tmp_path,
    }


def test_q8o_an_abort_without_a_report_is_unconfirmed(aborted_run: dict[str, Any]) -> None:
    assert result(judge(aborted_run), "unconfirmed_aborts") == "PASS"  # broker, no chain
    report = next(p for p in aborted_run["host"].rglob(f"*-{VICTIM}.json"))
    report.unlink()
    assert result(judge(aborted_run), "unconfirmed_aborts") == "FAIL"


def test_q7x_case_re_executions_count_toward_q9(clean_run: dict[str, Any]) -> None:
    report = next(p for p in clean_run["host"].rglob("inodefence-effect-demo-*.json"))
    rewrite_json(report, lambda r: r.update(infra_reexecution_count=5))
    assert result(judge(clean_run), "unstable_steps_per_1000_by_arm") == "FAIL"


def test_q9_counts_re_executions_not_every_stall_event() -> None:
    """(e): the event that gave up and aborted is listed but is not a re-execution."""
    events = [{"action": "reexecuted"}, {"action": "abort"}]
    assert qualify_host.reexecution_count({"infra_reexecutions": events}, None) == 1
    stub = {"infra_reexecution_count": 1}
    assert qualify_host.reexecution_count({"infra_reexecutions": events}, stub) == 1


def _stretch(run: dict[str, Any], clock: str, seconds: float) -> None:
    results = run["host"] / "cell-results.jsonl"
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    end = next(r for r in rows if r.get("event") == "end")
    end["clocks"] = {**end["clocks"], clock: end["clocks"][clock] + seconds}
    results.write_text("".join(json.dumps(r) + "\n" for r in rows))


@pytest.mark.parametrize("clock", ["realtime", "monotonic"])
def test_q10m_either_clock_over_the_limit_fails(clean_run: dict[str, Any], clock: str) -> None:
    _stretch(clean_run, clock, 8000)
    assert result(judge(clean_run), "longest_cell_seconds") == "FAIL"


def test_q10_a_cell_is_the_sum_of_its_attempts(aborted_run: dict[str, Any]) -> None:
    """(f): two attempts of 4000 s each make an 8000 s cell, over 7200 s."""
    results = aborted_run["host"] / "cell-results.jsonl"
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    start = next(r for r in rows if r.get("event") == "start")
    end = next(r for r in rows if r.get("event") == "end" and r["run_id"] == start["run_id"])
    for row in (start, end):
        row["clocks"] = {"realtime": 0.0, "monotonic": 0.0}
    end["clocks"] = {"realtime": 4000.0, "monotonic": 4000.0}
    second = [{**start, "attempt": 2}, {**end, "attempt": 2}]
    results.write_text("".join(json.dumps(r) + "\n" for r in [*rows, *second]))
    report = judge(aborted_run)
    assert result(report, "longest_cell_seconds") == "FAIL"
    assert report["criteria"]["longest_cell_seconds"]["value"]["realtime"] == 8000.0


# ---- Stage A ------------------------------------------------------------------------------------


def _stage_a_key(run: dict[str, Any], case_id: str = "c") -> dict[str, Any]:
    steps_file = next(p for p in run["host"].rglob("*.steps.jsonl") if VICTIM in p.name)
    case_ids = [json.loads(line)["case_id"] for line in steps_file.read_text().splitlines()]
    plan = run_exp0.Exp0Plan(
        run_exp0.load_preregistration(run["prereg"]), run["prereg"], "x", "7.5.2", False
    )
    policy = next(str(arm.search) for arm in plan.arms() if arm.label == "D")
    return {
        "search_policy": policy,
        "seed": 9001,
        "step_index": 2,
        "case_id": case_id,
        "path_prefix_sha256": extract_stage_a_abort_keys.path_sha256(case_ids[:2]),
    }


def _judge_keys(run: dict[str, Any], keys: tuple[Path, str]) -> tuple[int, dict[str, Any]]:
    code, report, _ = _judge(
        run["prereg"],
        run["assignment"],
        run["host"],
        _criteria(run["tmp"], run["cells"]),
        keys,
        run["tmp"] / "q.json",
    )
    return code, report


def test_q31_a_recurrence_needs_the_same_case_and_stops_the_host(
    aborted_run: dict[str, Any],
) -> None:
    other = _keys(aborted_run["tmp"], [_stage_a_key(aborted_run, "other")], aborted_run["prereg"])
    _, report = _judge_keys(aborted_run, other)
    assert report["criteria"]["stage_a_recurrence"]["value"]["recurrences"] == []
    same = _keys(aborted_run["tmp"], [_stage_a_key(aborted_run)], aborted_run["prereg"])
    code, report = _judge_keys(aborted_run, same)
    assert report["verdict"] == qualify_host.STOPPED_INPUT_DEPENDENT and code == 1  # (d)


def test_q12_a_different_stage_a_environment_fails(aborted_run: dict[str, Any]) -> None:
    keys = _keys(aborted_run["tmp"], [], aborted_run["prereg"], vocabulary="other")
    _, report = _judge_keys(aborted_run, keys)
    assert report["criteria"]["stage_a_recurrence"]["value"]["comparable"] is False
    assert report["criteria"]["stage_a_recurrence"]["result"] == "FAIL"


def test_q14_no_stage_a_key_file_fails(clean_run: dict[str, Any]) -> None:
    criteria = _criteria(clean_run["tmp"], clean_run["cells"])
    out = clean_run["tmp"] / "q.json"
    code = qualify_host.main(
        [
            "--preregistration",
            str(clean_run["prereg"]),
            "--seed-assignment",
            str(clean_run["assignment"]),
            "--host-id",
            "HOST1",
            "--output",
            str(clean_run["host"]),
            "--criteria",
            str(criteria[0]),
            "--criteria-sha256",
            criteria[1],
            "--out",
            str(out),
        ]
    )
    report = json.loads(out.read_text())
    assert result(report, "stage_a_recurrence") == "FAIL" and code == 1


def test_q30_a_stage_a_key_file_other_than_recorded_is_refused(clean_run: dict[str, Any]) -> None:
    path, _ = _keys(clean_run["tmp"], [], clean_run["prereg"])
    code, _ = _judge_keys(clean_run, (path, "0" * 64))
    assert code == 2


def test_not_run_when_nothing_was_attempted(clean_run: dict[str, Any]) -> None:
    (clean_run["host"] / "cell-results.jsonl").write_text("")
    assert judge(clean_run)["verdict"] == qualify_host.NOT_RUN  # (d)


# ---- comparator ---------------------------------------------------------------------------------


def test_c3_two_incomparable_cells_need_explaining(tmp_path: Path) -> None:
    base = steps()
    pairs = {
        label: (write(tmp_path, label, base), tmp_path / f"missing-{label}.steps.jsonl")
        for label in ("a", "b")
    }
    summary = compare_cell_paths.compare_pairs(pairs)["summary"]
    assert summary["m_x"] == 0 and summary["incomparable"] == 2
    assert summary["needs_explanation"] is True


def test_c4_two_unexplained_cells_are_a_serious_difference(tmp_path: Path) -> None:
    base, other = steps(), flip_judgement(steps(), 2)
    cross = {
        label: (write(tmp_path, f"{label}-1", base), write(tmp_path, f"{label}-2", other))
        for label in ("u1", "u2")
    }
    reruns = {
        "HOST1": {
            label: (pair[0], write(tmp_path, f"{label}-1r", base)) for label, pair in cross.items()
        },
        "HOST2": {
            label: (pair[1], write(tmp_path, f"{label}-2r", other)) for label, pair in cross.items()
        },
    }
    explanation = compare_cell_paths.explain(compare_cell_paths.compare_pairs(cross), reruns)
    assert explanation["unexplained_host_dependent"] == 2
    assert explanation["serious_difference"] is True


# ---- holdout assignment generator ---------------------------------------------------------------


@pytest.fixture
def holdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from test_two_host_split import RULES, _setup, train_files

    _, args, _ = _setup(tmp_path, monkeypatch, rule=RULES[1])
    train_prereg, train_assignment = train_files(tmp_path, monkeypatch)
    out = tmp_path / "made.json"
    argv = [
        "--preregistration",
        args[args.index("--preregistration") + 1],
        "--rule",
        RULES[1],
        "--go-decision",
        str(tmp_path / "go.json"),
        "--train-preregistration",
        str(train_prereg),
        "--train-assignment",
        str(train_assignment),
        "--out",
        str(out),
    ]
    return {"argv": argv, "train": train_assignment, "go": tmp_path / "go.json"}


def test_m1_a_train_assignment_off_its_registered_sha_is_refused(holdout: dict[str, Any]) -> None:
    assert make_seed_assignment.main(holdout["argv"]) == 0
    document = json.loads(holdout["train"].read_text())
    hosts = document["hosts"]
    document["hosts"] = {"HOST1": hosts["HOST2"], "HOST2": hosts["HOST1"]}
    holdout["train"].write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    assert make_seed_assignment.main(holdout["argv"]) == 2


def test_m2_a_go_file_with_another_frozen_set_is_refused(holdout: dict[str, Any]) -> None:
    go = json.loads(holdout["go"].read_text())
    holdout["go"].write_text(json.dumps({**go, "frozen_participants": ["HOST1"]}))
    assert make_seed_assignment.main(holdout["argv"]) == 2

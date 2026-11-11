"""Two-host split of one registration: assignment rules, host gate, launcher records, merge, GO."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0
from scripts import exp_operating_check, gen_exp3_tables, make_seed_assignment, merge_host_indexes

from inodefence.evaluation.rds_preregistration import (
    SEED_ASSIGNMENT_RULES,
    PreregistrationFormatError,
    load_preregistration,
)
from inodefence.evaluation.seed_assignment import (
    RULES,
    SeedAssignmentError,
    assignment_bytes,
    parse_seed_assignment,
    rule_problems,
    split_alternate,
    split_by_rate,
)
from test_gen_exp3_tables import _inputs, _starts, _train_report
from test_run_exp0 import (
    BEFORE,
    BLOCK,
    TARGET_IMAGES,
    _deadline_setup,
    _fake_runner,
    _index,
    _result_lines,
)
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine

SEEDS = (9001, 9002, 9003, 9004)
ENGINE = "29.8.0"

# ---- assignment rules -------------------------------------------------------------------------


def test_rule_names_match_the_parser() -> None:
    assert SEED_ASSIGNMENT_RULES == RULES


def test_alternate_gives_odd_positions_to_host1() -> None:
    document = split_alternate(SEEDS)
    assert document["hosts"] == {"HOST1": [9001, 9003], "HOST2": [9002, 9004]}
    assert assignment_bytes(document) == assignment_bytes(split_alternate(list(SEEDS)))


@pytest.mark.parametrize(
    ("n", "rates", "host1"),
    [
        (3, {"HOST1": "1", "HOST2": "1"}, 1),  # 1.5 rounds half down
        (4, {"HOST1": "3", "HOST2": "1"}, 3),
        (4, {"HOST1": "4763.000001", "HOST2": "1587.666667"}, 3),
        (3, {"HOST1": "2", "HOST2": "1"}, 2),
    ],
)
def test_rate_split_is_exact_round_half_down(n: int, rates: dict[str, str], host1: int) -> None:
    document = split_by_rate(SEEDS, n, rates)
    assert document["hosts"]["HOST1"] == list(SEEDS[:host1])
    assert document["hosts"]["HOST2"] == list(SEEDS[host1:n])
    assert document["rates_exec_per_hour"] == rates and document["n"] == n


@pytest.mark.parametrize("bad", ["0", "-1", "x"])
def test_a_missing_or_zero_rate_makes_no_assignment(bad: str) -> None:
    with pytest.raises(SeedAssignmentError):
        split_by_rate(SEEDS, 4, {"HOST1": bad, "HOST2": "1"})


@pytest.mark.parametrize(
    ("hosts", "message"),
    [
        ({"HOST1": [9001, 9002], "HOST2": [9002, 9003, 9004]}, "assigned to HOST1 and HOST2"),
        ({"HOST1": [9001, 9005], "HOST2": [9002, 9003, 9004]}, "not registered"),
        ({"HOST1": [9003, 9001], "HOST2": [9002, 9004]}, "registered order"),
        ({"HOST1": [9001], "HOST2": [9003]}, "without gaps"),
    ],
)
def test_parse_refuses_split_or_foreign_seeds(hosts: dict[str, list[int]], message: str) -> None:
    data = assignment_bytes(
        {"schema": "inodefence-seed-assignment-v1", "rule": RULES[0], "hosts": hosts}
    )
    with pytest.raises(SeedAssignmentError, match=message):
        parse_seed_assignment(data, SEEDS)


def test_rule_problems_regenerate_bytes() -> None:
    good = assignment_bytes(split_alternate(SEEDS))
    sha = parse_seed_assignment(good, SEEDS).sha256
    assert (
        rule_problems(
            good, rule=RULES[0], registered_seeds=SEEDS, registered_sha256=sha, go_decision=None
        )
        == []
    )
    swapped = assignment_bytes(
        {**split_alternate(SEEDS), "hosts": {"HOST1": [9002, 9004], "HOST2": [9001, 9003]}}
    )
    assert rule_problems(
        swapped, rule=RULES[0], registered_seeds=SEEDS, registered_sha256=sha, go_decision=None
    )
    rates = {"HOST1": "3", "HOST2": "1"}
    holdout = assignment_bytes(split_by_rate(SEEDS, 4, rates))
    go = {"rates_exec_per_hour": rates, "frozen_participants": ["HOST1", "HOST2"]}
    kwargs: dict[str, Any] = {
        "rule": RULES[1],
        "registered_seeds": SEEDS,
        "registered_sha256": None,
    }
    assert rule_problems(holdout, go_decision=go, **kwargs) == []
    assert rule_problems(holdout, go_decision=None, **kwargs)
    assert rule_problems(holdout, go_decision={"decided_at": "x"}, **kwargs)
    assert rule_problems(
        holdout, go_decision={**go, "rates_exec_per_hour": {"HOST1": "1", "HOST2": "1"}}, **kwargs
    )
    # Holdout participants are the frozen train set less the recorded exclusions only.
    assert rule_problems(holdout, go_decision={**go, "frozen_participants": ["HOST1"]}, **kwargs)
    assert rule_problems(holdout, go_decision={**go, "excluded_hosts": ["HOST2"]}, **kwargs)
    no_frozen = {k: v for k, v in go.items() if k != "frozen_participants"}
    assert rule_problems(holdout, go_decision=no_frozen, **kwargs)
    assert rule_problems(holdout, go_decision={**go, "seed_assignment_sha256": "0" * 64}, **kwargs)


# ---- registration keys --------------------------------------------------------------------------


def _host_keys(rule: str, sha: str | None, *, jobs: tuple[int, int] = (2, 1)) -> str:
    text = (
        f"host.HOST1.jobs = {jobs[0]}\nhost.HOST1.docker_engine = {ENGINE}\n"
        f"host.HOST2.jobs = {jobs[1]}\nhost.HOST2.docker_engine = {ENGINE}\n"
        f"seed_assignment_rule = {rule}\n"
    )
    return text + (f"seed_assignment_sha256 = {sha}\n" if sha else "")


def _two_host_file(prereg: Path, keys: str) -> None:
    text = prereg.read_text(encoding="utf-8")
    text = text.replace("seeds = 9001, 9002\n", f"seeds = {', '.join(map(str, SEEDS))}\n")
    prereg.write_text(text.replace("jobs_max = 2\n", "jobs_max = 2\n" + keys), encoding="utf-8")


def _setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rule: str = RULES[0]
) -> tuple[Path, list[str], Path]:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    prereg = Path(args[args.index("--preregistration") + 1])
    assignment = tmp_path / "assignment.json"
    if rule == RULES[0]:
        data = assignment_bytes(split_alternate(SEEDS))
        _two_host_file(prereg, _host_keys(rule, parse_seed_assignment(data, SEEDS).sha256))
    else:
        rates = {"HOST1": "3", "HOST2": "1"}
        (tmp_path / "go.json").write_text(
            json.dumps({"rates_exec_per_hour": rates, "frozen_participants": ["HOST1", "HOST2"]}),
            encoding="utf-8",
        )
        data = assignment_bytes(split_by_rate(SEEDS, len(SEEDS), rates))
        _two_host_file(prereg, _host_keys(rule, None))
    assignment.write_bytes(data)
    monkeypatch.setattr(run_exp0, "docker_engine_version", lambda context: ENGINE)
    return out, args, assignment


def train_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A frozen two-host train registration and its alternate-v1 assignment."""
    train = tmp_path / "train"
    train.mkdir()
    _, args, assignment = _setup(train, monkeypatch, rule=RULES[0])
    return Path(args[args.index("--preregistration") + 1]), assignment


#: Controller and helper ids a two-host run is told to expect (--expected-images).
EXPECTED_CONTROLLER_ID = "sha256:" + "c" * 64
EXPECTED_HELPER_ID = "sha256:" + "d" * 64


def expected_images_file(args: list[str], directory: Path) -> Path:
    """An --expected-images file (criteria format) naming every guarded image of the plan."""
    from test_run_exp0 import _plan

    plan = _plan(Path(args[args.index("--preregistration") + 1]))
    local = {
        "inodefence-controller:local": EXPECTED_CONTROLLER_ID,
        "inodefence-helper:local": EXPECTED_HELPER_ID,
    }
    ids = {name: want or local[name] for name, want in run_exp0.guard_images(plan).items()}
    path = directory / "expected-images.json"
    path.write_text(json.dumps({"expected_image_ids": ids}), encoding="utf-8")
    return path


def _host_args(args: list[str], out: Path, host: str, assignment: Path, jobs: str) -> list[str]:
    host_out = out.parent / f"{out.name}-{host}"
    replaced = [str(host_out) if a == str(out) else a for a in args]
    expected = expected_images_file(args, out.parent)
    return [
        *replaced,
        "--seed-assignment",
        str(assignment),
        "--host-id",
        host,
        "--jobs",
        jobs,
        "--expected-images",
        str(expected),
    ]


def test_host_keys_parse_and_stay_out_of_one_host_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, args, _ = _setup(tmp_path, monkeypatch)
    prereg = load_preregistration(Path(args[args.index("--preregistration") + 1]))
    assert [(h.host_id, h.jobs, h.docker_engine) for h in prereg.hosts] == [
        ("HOST1", 2, ENGINE),
        ("HOST2", 1, ENGINE),
    ]
    assert prereg.seed_assignment_rule == RULES[0] and prereg.unknown_keys == ()
    one_host = tmp_path / "exp0.md"
    one_host.write_text(BLOCK, encoding="utf-8")
    plain = load_preregistration(one_host)
    assert plain.hosts == () and plain.seed_assignment_rule is None


@pytest.mark.parametrize(
    ("keys", "message"),
    [
        (_host_keys(RULES[0], None), "needs seed_assignment_sha256"),
        (_host_keys(RULES[1], "a" * 64), "made at GO"),
        (_host_keys(RULES[0], "a" * 64, jobs=(1, 1)), "jobs_max must equal"),
        (
            _host_keys(RULES[0], "a" * 64).replace("host.HOST2.docker_engine = 29.8.0\n", ""),
            "missing",
        ),
        ("host.HOST1.jobs = 2\n", "declared together"),
        (_host_keys("by-hand", "a" * 64), "seed_assignment_rule must be one of"),
    ],
)
def test_host_keys_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, keys: str, message: str
) -> None:
    _, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    prereg = Path(args[args.index("--preregistration") + 1])
    _two_host_file(prereg, keys)
    with pytest.raises(PreregistrationFormatError, match=message):
        load_preregistration(prereg)


# ---- host gate ----------------------------------------------------------------------------------


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
@pytest.mark.parametrize("mode", ["dry-run", "live"])
@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("jobs", "jobs 1 != registered host.HOST1.jobs 2"),
        ("engine", "docker engine 28.0.0 != registered host.HOST1.docker_engine"),
        ("assignment", "not the alternate-v1 split"),
    ],
)
def test_each_host_mismatch_refuses_before_warmup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    change: str,
    message: str,
) -> None:
    out, args, assignment = _setup(tmp_path, monkeypatch)
    jobs = "1" if change == "jobs" else "2"
    if change == "engine":
        monkeypatch.setattr(run_exp0, "docker_engine_version", lambda context: "28.0.0")
    if change == "assignment":
        swapped = {
            **split_alternate(SEEDS),
            "hosts": {"HOST1": [9002, 9004], "HOST2": [9001, 9003]},
        }
        assignment.write_bytes(assignment_bytes(swapped))

    def no_warmup(*_a: Any, **_k: Any) -> int:
        raise AssertionError("warmup must not run")

    monkeypatch.setattr(run_exp0, "_warmup", no_warmup)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    argv = _host_args(args, out, "HOST1", assignment, jobs)
    if mode == "dry-run":
        argv.append("--dry-run")
    assert run_exp0.main(argv) == 2
    captured = capsys.readouterr()
    assert message in captured.out + captured.err
    assert not (out.parent / f"{out.name}-HOST1" / "matrix.json").exists()


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_one_host_registration_never_queries_the_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE)

    def no_engine(context: str | None) -> str:
        raise AssertionError("one-host registrations do not query the engine")

    monkeypatch.setattr(run_exp0, "docker_engine_version", no_engine)
    assert run_exp0.main([*args, "--dry-run"]) == 0
    printed = capsys.readouterr().out
    assert "seed_assignment" not in printed and "gate: PASS" in printed


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_seed_assignment_needs_a_two_host_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    assignment = tmp_path / "a.json"
    assignment.write_bytes(assignment_bytes(split_alternate((9001, 9002))))
    assert run_exp0.main(_host_args(args, out, "HOST1", assignment, "2")) == 2


# ---- launcher records and merge ----------------------------------------------------------


def _run_host(
    args: list[str],
    out: Path,
    host: str,
    assignment: Path,
    jobs: str,
    monkeypatch: pytest.MonkeyPatch,
    extra: tuple[str, ...] = (),
) -> Path:
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main([*_host_args(args, out, host, assignment, jobs), *extra])
    return out.parent / f"{out.name}-{host}"


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_each_host_runs_only_its_seeds_and_records_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, assignment = _setup(tmp_path, monkeypatch)
    sha = parse_seed_assignment(assignment.read_bytes(), SEEDS).sha256
    host1 = _run_host(args, out, "HOST1", assignment, "2", monkeypatch)
    index = _index(host1)
    assert {cell["seed"] for cell in index["cells"]} == {9001, 9003}
    for record in (
        index["seed_assignment"],
        json.loads((host1 / "registration.json").read_text())["seed_assignment"],
        json.loads((host1 / "matrix.json").read_text())["seed_assignment"],
    ):
        assert (record["sha256"], record["host_id"]) == (sha, "HOST1")
    lines = _result_lines(host1)
    assert lines and all(
        (row["host_id"], row["seed_assignment_sha256"]) == ("HOST1", sha) for row in lines
    )
    # Bytes other than the rule's (here one extra newline) are refused even when they parse.
    other = tmp_path / "other.json"
    other.write_bytes(assignment.read_bytes().replace(b"\n", b"\n\n", 1))
    assert parse_seed_assignment(other.read_bytes(), SEEDS).hosts == {
        "HOST1": (9001, 9003),
        "HOST2": (9002, 9004),
    }
    assert run_exp0.main(_host_args(args, out, "HOST1", other, "2")) == 2


def _merge(
    tmp_path: Path, prereg: Path, assignment: Path, hosts: dict[str, Path], *extra: str
) -> int:
    argv = ["--preregistration", str(prereg), "--seed-assignment", str(assignment)]
    for host, path in hosts.items():
        argv += ["--host", f"{host}={path}"]
    return merge_host_indexes.main([*argv, "--output", str(tmp_path / "merged"), *extra])


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_merge_joins_two_hosts_and_refuses_mixed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, assignment = _setup(tmp_path, monkeypatch)
    prereg = Path(args[args.index("--preregistration") + 1])
    host1 = _run_host(args, out, "HOST1", assignment, "2", monkeypatch)
    # One host only: written, reported incomplete, never a pass.
    assert _merge(tmp_path, prereg, assignment, {"HOST1": host1}) == 1
    partial = _index(tmp_path / "merged")
    assert partial["merge"]["complete"] is False and partial["g1_verdict"]["pass"] is False
    assert partial["merge"]["reasons"] == ["host HOST2 not merged yet"]
    host2 = _run_host(args, out, "HOST2", assignment, "1", monkeypatch)
    assert _merge(tmp_path, prereg, assignment, {"HOST1": host1, "HOST2": host2}) == 0
    merged = _index(tmp_path / "merged")
    assert merged["merge"]["complete"] is True
    assert sorted({c["seed"] for c in merged["cells"]}) == list(SEEDS)
    assert len(merged["cells"]) == len(_index(host1)["cells"]) + len(_index(host2)["cells"])
    assert all(Path(c["summary"]).is_absolute() for c in merged["cells"] if c.get("summary"))
    pooled = merged["cell_completeness"]
    parts = [_index(h)["cell_completeness"] for h in (host1, host2)]
    assert pooled["cells"] == sum(p["cells"] for p in parts)
    assert pooled["recorded_steps"] == sum(p["recorded_steps"] for p in parts)
    # Swapped hosts, a different assignment file, and a seed on both hosts are refused.
    assert _merge(tmp_path, prereg, assignment, {"HOST1": host2, "HOST2": host1}) == 2
    other = tmp_path / "other.json"
    other.write_bytes(
        assignment_bytes(
            {**split_alternate(SEEDS), "hosts": {"HOST1": [9002, 9004], "HOST2": [9001, 9003]}}
        )
    )
    assert _merge(tmp_path, prereg, other, {"HOST1": host1, "HOST2": host2}) == 2
    index2 = json.loads((host2 / "summaries" / "index.json").read_text())
    index2["cells"][0]["seed"] = 9001
    (host2 / "summaries" / "index.json").write_text(json.dumps(index2))
    assert _merge(tmp_path, prereg, assignment, {"HOST1": host1, "HOST2": host2}) == 2


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_holdout_assignment_comes_from_the_go_rates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out, args, assignment = _setup(tmp_path, monkeypatch, rule=RULES[1])
    prereg = Path(args[args.index("--preregistration") + 1])
    go = tmp_path / "go.json"
    made = tmp_path / "made.json"
    train_prereg, train_assignment = train_files(tmp_path, monkeypatch)
    assert (
        make_seed_assignment.main(
            [
                "--preregistration",
                str(prereg),
                "--rule",
                RULES[1],
                "--go-decision",
                str(go),
                "--train-preregistration",
                str(train_prereg),
                "--train-assignment",
                str(train_assignment),
                "--record-in-go-decision",
                "--out",
                str(made),
            ]
        )
        == 0
    )
    assert made.read_bytes() == assignment.read_bytes()
    assert (
        json.loads(go.read_text())["seed_assignment_sha256"]
        == parse_seed_assignment(made.read_bytes(), SEEDS).sha256
    )
    dry = [*_host_args(args, out, "HOST1", made, "2"), "--dry-run"]
    assert run_exp0.main(dry) == 2  # no --go-decision: refused
    assert run_exp0.main([*dry, "--go-decision", str(go)]) == 0
    assert "seed_assignment host=HOST1" in capsys.readouterr().out
    go.write_text(
        json.dumps(
            {
                "rates_exec_per_hour": {"HOST1": "1", "HOST2": "3"},
                "frozen_participants": ["HOST1", "HOST2"],
            }
        ),
        encoding="utf-8",
    )
    assert run_exp0.main([*dry, "--go-decision", str(go)]) == 2
    go.write_text(json.dumps({"decided_at": "2026-11-20T00:00:00+09:00"}), encoding="utf-8")
    assert (
        make_seed_assignment.main(
            [
                "--preregistration",
                str(prereg),
                "--rule",
                RULES[1],
                "--go-decision",
                str(go),
                "--out",
                str(made),
            ]
        )
        == 2
    )


# ---- GO inputs and operating check over two hosts ----------------------------------------


def test_go_rate_is_the_sum_of_host_rates(tmp_path: Path) -> None:
    report = _train_report()
    report["hosts"] = {
        "HOST1": {"cell_completeness": {"recorded_steps": 1200}},
        "HOST2": {"cell_completeness": {"recorded_steps": 600}},
    }
    inputs = _inputs(report, tmp_path)
    files = {}
    # HOST1: 6 cells over 2 h; HOST2: 3 cells over 1 h with a resumed 0.5 h stop.
    for host, rows in {
        "HOST1": [*_starts(0.0, 6), {"event": "end", "clocks": {"realtime": 7200.0}}],
        "HOST2": [
            *_starts(0.0, 3),
            {"event": "infrastructure-stop", "clocks": {"realtime": 1800.0}},
            {"event": "infrastructure-resume", "clocks": {"realtime": 3600.0}},
            {"event": "end", "clocks": {"realtime": 5400.0}},
        ],
    }.items():
        path = tmp_path / f"{host}.jsonl"
        path.write_text("".join(json.dumps({**r, "host_id": host}) + "\n" for r in rows))
        files[host] = path
    two = gen_exp3_tables.Inputs(
        report, inputs.cell_results, inputs.hand_input, inputs.go_decision, files
    )
    text = gen_exp3_tables.render("T-EXP3-2", two)
    row = {
        line.split(" | ")[0].removeprefix("| "): line.split(" | ")[1]
        for line in text.splitlines()
        if line.startswith("| ")
    }
    # r_1 = 1200/2 h = 600; r_2 = 600/(1.5 h - 0.5 h gap) = 600; r = 1200.
    assert row["r_HOST1: HOST1 처리량(실시간, exec/h)"] == "600"
    assert row["r_HOST2: HOST2 처리량(실시간, exec/h)"] == "600"
    assert row["r: 정지 공백을 뺀 처리량(실시간, exec/h)"] == "1200"
    assert gen_exp3_tables.go_rates(two) == {"HOST1": "600.000000", "HOST2": "600.000000"}
    # An unresumed stop on one host leaves GO and the split without a value.
    files["HOST2"].write_text(
        files["HOST2"].read_text()
        + json.dumps({"event": "infrastructure-stop", "clocks": {"realtime": 5500.0}})
        + "\n"
    )
    assert "| 결과 | 미산출" in gen_exp3_tables.render("T-EXP3-2", two)
    with pytest.raises(gen_exp3_tables.TableInputError, match="미산출"):
        gen_exp3_tables.go_rates(two)


def _window(ended: int, failed: int, stopped: bool = False) -> dict[str, Any]:
    rate = failed / ended if ended else None
    return {
        "classification": "operating check: counts only, no automatic stop",
        "now": "2026-11-20T00:00:00+00:00",
        "window_start": "2026-11-19T00:00:00+00:00",
        "ended_cells": ended,
        "complete": ended - failed,
        "abort": failed,
        "abort_watchdog": 0,
        "no_record": 0,
        "record_inconsistent": 0,
        "infrastructure_failure_rate": rate,
        "min_ended_cells_met": ended >= 20,
        "stop_rate_reached": ended >= 20 and rate is not None and rate >= 0.60,
        "running_cells": 0,
        "awaiting_retry": 0,
        "infrastructure_stopped": stopped,
    }


def test_operating_check_pools_hosts_and_alarms_on_one(tmp_path: Path) -> None:
    now = datetime(2026, 11, 20, tzinfo=UTC)
    outputs = {"HOST1": tmp_path / "h1", "HOST2": tmp_path / "h2"}
    for path in outputs.values():
        path.mkdir()
    (outputs["HOST1"] / "cell-results.jsonl").write_text(
        json.dumps({"event": "end", "clocks": {"realtime": now.timestamp() - 30}}) + "\n"
    )
    report = exp_operating_check.pool_hosts(
        {"HOST1": _window(20, 14), "HOST2": _window(40, 2)}, outputs, now
    )
    assert report["ended_cells"] == 60 and report["infrastructure_failure_rate"] == pytest.approx(
        16 / 60
    )
    assert report["stop_rate_reached"] is False
    assert len(report["host_alarms"]) == 1 and "HOST1" in report["host_alarms"][0]
    assert report["clock_reference"]["HOST1"]["checker_now_minus_last_seconds"] == 30.0
    assert report["clock_reference"]["HOST2"]["last_realtime"] is None

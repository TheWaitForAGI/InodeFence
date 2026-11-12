"""Partial GO (D047 section 9.1): an unresumed-stop host leaves r, hold conditions, records."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0
from scripts import exp_operating_check, merge_host_indexes, partial_go_check

from test_run_exp0 import TARGET_IMAGES, _fake_runner
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine
from test_two_host_split import _host_args, _setup, _window

DECIDED = "2030-01-01T00:00:00+00:00"


class Everything:
    def __contains__(self, item: object) -> bool:
        return True


def _run(
    args: list[str],
    out: Path,
    host: str,
    assignment: Path,
    abort: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    behaviour = {**TARGET_IMAGES, "abort": abort}
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(behaviour))
    jobs = "2" if host == "HOST1" else "1"
    assert run_exp0.main(_host_args(args, out, host, assignment, jobs)) in (0, 1)
    return out.parent / f"{out.name}-{host}"


class ArmOnly:
    """Abort only the cells of one arm (run id ``<target>-<arm>-s<seed>``)."""

    def __init__(self, arm: str) -> None:
        self.marker = f"-{arm}-s"

    def __contains__(self, item: object) -> bool:
        return self.marker in str(item)


@pytest.fixture
def stopped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """HOST1 ran clean; every HOST2 cell aborted, then HOST2 stopped unresumed."""
    return _build(tmp_path, monkeypatch, Everything())


def _build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, abort: Any) -> dict[str, Any]:
    out, args, assignment = _setup(tmp_path, monkeypatch)
    prereg = Path(args[args.index("--preregistration") + 1])
    host1 = _run(args, out, "HOST1", assignment, (), monkeypatch)
    host2 = _run(args, out, "HOST2", assignment, abort, monkeypatch)
    # The fake stub's reason text classifies as "other"; record the category the launcher would.
    for report in host2.rglob("*.json"):
        data = json.loads(report.read_text())
        if isinstance(data, dict) and isinstance(data.get("aborted"), dict):
            data["aborted"]["category"] = "broker"
            report.write_text(json.dumps(data))
    results = host2 / "cell-results.jsonl"
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    last = max(row["clocks"]["realtime"] for row in rows)
    fields = {key: rows[0][key] for key in ("host_id", "seed_assignment_sha256")}
    with results.open("a") as stream:
        stop = {"event": "infrastructure-stop", "reason": "3 cells without a record", **fields}
        stream.write(json.dumps({**stop, "clocks": {"realtime": last + 1}}) + "\n")
    go = tmp_path / "go.json"
    go.write_text(json.dumps({"decided_at": DECIDED}))
    base = [
        "--preregistration",
        str(prereg),
        "--seed-assignment",
        str(assignment),
        "--host",
        f"HOST1={host1}",
        "--host",
        f"HOST2={host2}",
        "--go-decision",
        str(go),
        "--out",
        str(tmp_path / "check.json"),
    ]
    return {
        "base": base,
        "host1": host1,
        "host2": host2,
        "go": go,
        "tmp": tmp_path,
        "prereg": prereg,
        "assignment": assignment,
    }


def _check(run: dict[str, Any], *extra: str) -> dict[str, Any]:
    assert partial_go_check.main([*run["base"], *extra]) == 0
    return json.loads((run["tmp"] / "check.json").read_text())


def _manifest(run: dict[str, Any]) -> Path:
    results = run["host2"] / "cell-results.jsonl"
    path = run["tmp"] / "host2.sha256"
    digest = hashlib.sha256(results.read_bytes()).hexdigest()
    path.write_text(f"{digest}  cell-results.jsonl\n")
    return path


pytestmark = pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")


def _retry_same_input(run: dict[str, Any]) -> str:
    """Give one aborted cell a second attempt that aborted at the same step and case."""
    results = run["host2"] / "cell-results.jsonl"
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    start = next(r for r in rows if r.get("event") == "start")
    end = next(r for r in rows if r.get("event") == "end" and r.get("run_id") == start["run_id"])
    report = next(run["host2"].rglob(f"*-{start['run_id']}.json"))
    attempts = run["host2"] / "attempts"
    attempts.mkdir(exist_ok=True)
    (attempts / f"{start['run_id']}.attempt1.json").write_text(report.read_text())
    position = rows.index(end) + 1
    rows[position:position] = [{**start, "attempt": 2}, {**end, "attempt": 2}]
    results.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return str(start["run_id"])


def test_the_stopped_host_is_excluded_and_held_without_evidence(stopped: dict[str, Any]) -> None:
    retried = _retry_same_input(stopped)
    document = _check(stopped)
    assert document["excluded_hosts"] == ["HOST2"]
    assert document["status"].startswith("held")
    reasons = document["exclusions"]["HOST2"]["hold_reasons"]
    # The fake runner aborts every attempt at the same step and case: input dependence.
    assert "(ii) the same abort input in 1 cells" in reasons
    repeated = document["exclusions"]["HOST2"]["checks"]["ii_input_dependence"]
    assert [r["run_id"] for r in repeated["repeated_abort_keys"]] == [retried]
    assert any(r.startswith("(iii) no evidence manifest") for r in reasons)
    assert any(r.startswith("(iv)") for r in reasons)
    # The hold conditions and their evidence are what the GO file records (W4 C-iv).
    assert partial_go_check.main([*stopped["base"], "--record-in-go-decision"]) == 0
    recorded = json.loads(stopped["go"].read_text())
    assert recorded["exclusions"]["HOST2"]["hold_reasons"] == reasons
    assert set(recorded["exclusions"]["HOST2"]["checks"]) == {
        "i_stop_cause",
        "ii_input_dependence",
        "iii_records",
        "iv_statement",
    }
    triggers = document["exclusions"]["HOST2"]["checks"]["i_stop_cause"]["trigger_cells"]
    assert len(triggers) == 3 and all(t["category"] == "broker" for t in triggers)
    assert not document["hosts"]["HOST1"]["unresumed_stop"]
    text = (stopped["tmp"] / "check.json").read_text()
    for word in ("violated", "C1", "C2", "oracle_summary"):
        assert word not in text


def test_with_evidence_and_no_repeated_input_the_go_is_partial(stopped: dict[str, Any]) -> None:
    manifest = _manifest(stopped)
    extra = ["--raw-manifest", f"HOST2={manifest}", "--stop-statement", "HOST2=QUAL-HOST2-x"]
    document = _check(stopped, *extra, "--record-in-go-decision")
    assert document["exclusions"]["HOST2"]["hold_reasons"] == []
    assert document["status"].startswith("partial")
    recorded = json.loads(stopped["go"].read_text())
    assert recorded["excluded_hosts"] == ["HOST2"]
    assert recorded["partial_completion"]["HOST2"]
    # A changed evidence file is a hold.
    (stopped["host2"] / "cell-results.jsonl").write_text(
        (stopped["host2"] / "cell-results.jsonl").read_text() + "\n"
    )
    assert partial_go_check.main([*stopped["base"], *extra]) == 0
    reasons = json.loads((stopped["tmp"] / "check.json").read_text())["exclusions"]["HOST2"]
    assert "(iii) manifest hash differs: cell-results.jsonl" in reasons["hold_reasons"]
    # The recorded GO file is not overwritten with other values.
    assert partial_go_check.main([*stopped["base"], *extra, "--record-in-go-decision"]) == 2


def test_an_unattempted_cell_makes_its_seed_block_unfinished_and_the_merge_drops_it(
    stopped: dict[str, Any],
) -> None:
    results = stopped["host2"] / "cell-results.jsonl"
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    gone = next(r["run_id"] for r in rows if r.get("event") == "start")
    results.write_text("".join(json.dumps(r) + "\n" for r in rows if r.get("run_id") != gone))
    for path in list(stopped["host2"].rglob(f"*{gone}*")):
        path.unlink()
    document = _check(stopped)
    blocks = next(iter(document["partial_completion"]["HOST2"].values()))
    seed = int(gone.rsplit("-s", 1)[1])
    assert seed in blocks["unfinished_seeds"] and seed not in blocks["finished_seeds"]
    go = json.loads(stopped["go"].read_text())
    go.update({key: document[key] for key in partial_go_check.RECORD_KEYS})
    stopped["go"].write_text(json.dumps(go))
    merged = stopped["tmp"] / "merged"
    argv = [
        "--preregistration",
        str(stopped["prereg"]),
        "--seed-assignment",
        str(stopped["assignment"]),
        "--host",
        f"HOST1={stopped['host1']}",
        "--host",
        f"HOST2={stopped['host2']}",
        "--go-decision",
        str(stopped["go"]),
        "--output",
        str(merged),
    ]
    assert merge_host_indexes.main(argv) == 0
    deadline = json.loads((merged / "summaries" / "index.json").read_text())["deadline"]
    assert seed in next(iter(deadline["excluded_seeds"].values()))
    assert deadline["partial_go_excluded_hosts"] == ["HOST2"]
    assert merge_host_indexes.PARTIAL_GO_CAUSE in deadline["causes"].values()


def test_the_operating_check_marks_an_excluded_host_without_an_alarm(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    outputs = {"HOST1": tmp_path / "h1", "HOST2": tmp_path / "h2"}
    for path in outputs.values():
        path.mkdir()
    reports = {"HOST1": _window(30, 1), "HOST2": _window(30, 25, stopped=True)}
    now = datetime(2026, 11, 20, tzinfo=UTC)
    plain = exp_operating_check.pool_hosts(reports, outputs, now)
    assert plain["host_alarms"] and "excluded_by_partial_go" not in plain["hosts"]["HOST2"]
    marked = exp_operating_check.pool_hosts(reports, outputs, now, ("HOST2",))
    assert marked["hosts"]["HOST2"]["excluded_by_partial_go"] is True
    assert marked["host_alarms"] == []
    assert marked["abort"] == plain["abort"]  # its attempted cells stay in the pool


def test_without_a_stop_the_check_is_full_and_every_block_finished(
    stopped: dict[str, Any],
) -> None:
    """The smoke-output format check (runbook): no stop, every seed block finished."""
    results = stopped["host2"] / "cell-results.jsonl"
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    kept = [r for r in rows if r.get("event") != "infrastructure-stop"]
    results.write_text("".join(json.dumps(r) + "\n" for r in kept))
    document = _check(stopped)
    assert document["status"].startswith("full") and document["excluded_hosts"] == []
    for host in ("HOST1", "HOST2"):
        for blocks in document["partial_completion"][host].values():
            assert blocks["unfinished_seeds"] == [] and blocks["finished_seeds"]


def test_a_stop_after_complete_cells_is_held_and_all_stopped_is_not_computed(
    stopped: dict[str, Any],
) -> None:
    results = stopped["host1"] / "cell-results.jsonl"
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    fields = {key: rows[0][key] for key in ("host_id", "seed_assignment_sha256")}
    last = max(row["clocks"]["realtime"] for row in rows)
    stop = {"event": "infrastructure-stop", "reason": "operator", "clocks": {"realtime": last}}
    results.write_text(results.read_text() + json.dumps({**stop, **fields}) + "\n")
    document = _check(stopped)
    assert document["excluded_hosts"] == ["HOST1", "HOST2"]
    assert document["status"].startswith("not computed")
    reasons = document["exclusions"]["HOST1"]["hold_reasons"]
    assert "(i) the cells that ended the run are not found" in reasons


# ---- each hold branch and input range on its own (W4 flips_pgo survivors) ----------------------


def _host2_reasons(run: dict[str, Any]) -> list[str]:
    return list(_check(run)["exclusions"]["HOST2"]["hold_reasons"])


def test_i_a_trigger_cell_without_its_report_is_unconfirmed(stopped: dict[str, Any]) -> None:
    """A Guard stop's no-record cells have no report: Q8 calls them unconfirmed, so GO holds."""
    first = _check(stopped)["exclusions"]["HOST2"]["checks"]["i_stop_cause"]["trigger_cells"]
    for trigger in first:
        for report in stopped["host2"].rglob(f"*{trigger['run_id']}*.json"):
            report.unlink()
    assert any(r.startswith("(i) unconfirmed abort cause") for r in _host2_reasons(stopped))


def test_i_a_non_infrastructure_category_holds(stopped: dict[str, Any]) -> None:
    for report in stopped["host2"].rglob("*.json"):
        data = json.loads(report.read_text())
        if isinstance(data, dict) and isinstance(data.get("aborted"), dict):
            data["aborted"]["category"] = "observer_integrity"
            report.write_text(json.dumps(data))
    reasons = _host2_reasons(stopped)
    assert any(r.startswith("(i) not an infrastructure cause") for r in reasons)
    assert not any(r.startswith("(i) unconfirmed") for r in reasons)


def test_ii_aborts_on_one_arm_only_flag_the_independence_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _build(tmp_path, monkeypatch, ArmOnly("D"))
    document = _check(run)
    checks = document["exclusions"]["HOST2"]["checks"]["ii_input_dependence"]
    assert checks["independence_flag"] == partial_go_check.INDEPENDENCE_FLAG
    assert (
        "(ii) arm x abort independence flagged (p <= .10)"
        in (document["exclusions"]["HOST2"]["hold_reasons"])
    )


def _open_attempt(run: dict[str, Any]) -> tuple[str, int]:
    """A third start line for a cell, with no end line, before the stop."""
    results = run["host2"] / "cell-results.jsonl"
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    start = next(r for r in rows if r.get("event") == "start")
    stop = next(i for i, r in enumerate(rows) if r.get("event") == "infrastructure-stop")
    rows.insert(stop, {**start, "attempt": 3})
    results.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return str(start["run_id"]), int(str(start["run_id"]).rsplit("-s", 1)[1])


def test_iii_a_start_without_its_end_holds_and_leaves_the_block_unfinished(
    stopped: dict[str, Any],
) -> None:
    run_id, seed = _open_attempt(stopped)
    document = _check(stopped)
    reasons = document["exclusions"]["HOST2"]["hold_reasons"]
    assert "(iii) starts without an end line: 1" in reasons
    assert document["hosts"]["HOST2"]["unfinished_causes"][run_id] == "started-without-end"
    blocks = document["partial_completion"]["HOST2"]
    assert any(seed in b["unfinished_seeds"] for b in blocks.values())


def test_iii_a_gate_cell_not_verified_clean_holds(stopped: dict[str, Any]) -> None:
    gate = stopped["host2"] / run_exp0.START_GATE_DIR
    gate.mkdir(exist_ok=True)
    (gate / "cell-x.session").write_text("s\n")
    (gate / "cell-x.verdict").write_text("U reason\n")
    assert any(
        r.startswith("(iii) start-gate cells not verified clean") for r in _host2_reasons(stopped)
    )


def test_a_stop_after_the_go_decision_time_does_not_count(stopped: dict[str, Any]) -> None:
    stopped["go"].write_text(json.dumps({"decided_at": "2000-01-01T00:00:00+00:00"}))
    document = _check(stopped)
    assert document["excluded_hosts"] == [] and document["status"].startswith("full")


def test_the_merge_refuses_an_exclusion_without_its_completion(stopped: dict[str, Any]) -> None:
    stopped["go"].write_text(json.dumps({"decided_at": DECIDED, "excluded_hosts": ["HOST2"]}))
    argv = [
        "--preregistration",
        str(stopped["prereg"]),
        "--seed-assignment",
        str(stopped["assignment"]),
        "--host",
        f"HOST1={stopped['host1']}",
        "--host",
        f"HOST2={stopped['host2']}",
        "--go-decision",
        str(stopped["go"]),
        "--output",
        str(stopped["tmp"] / "merged"),
    ]
    assert merge_host_indexes.main(argv) == 2


# ---- (ii) on a table that cannot be tested: not assessable, shown, not a hold -----------------


def _ii(document: dict[str, Any]) -> dict[str, Any]:
    return dict(document["exclusions"]["HOST2"]["checks"]["ii_input_dependence"])


def test_a_guard_stop_with_no_recorded_cell_is_held_by_i_and_ii_is_not_assessable(
    stopped: dict[str, Any],
) -> None:
    """Guard stop (consecutive cells without a record): every trigger cell lacks its report, so (i)
    always holds; with no complete or abort-final cell (ii) is not assessable, not a hold."""
    for report in stopped["host2"].rglob("*.json"):
        if "summaries" not in report.parts and report.name != "matrix.json":
            report.unlink()
    document = _check(stopped)  # exit 0, not a refusal
    exclusion = document["exclusions"]["HOST2"]
    ii = _ii(document)
    assert ii["independence_flag"] == partial_go_check.NOT_ASSESSABLE
    assert ii["not_assessable_reason"] == "no complete or abort-final cell"
    assert ii["independence_p"] is None
    assert exclusion["notes"] == ["(ii) 검정 불가: no complete or abort-final cell"]
    assert any(r.startswith("(i) unconfirmed abort cause") for r in exclusion["hold_reasons"])
    assert not any(r.startswith("(ii)") for r in exclusion["hold_reasons"])


def test_one_arm_is_not_assessable_and_the_repeated_key_check_still_runs(
    stopped: dict[str, Any],
) -> None:
    retried = _retry_same_input(stopped)
    arm = retried.split("-s")[0].rsplit("-", 1)[-1]
    for report in stopped["host2"].rglob("*.json"):
        if f"-{arm}-s" not in report.name and "summaries" not in report.parts:
            if report.name != "matrix.json":
                report.unlink()
    document = _check(stopped)
    ii = _ii(document)
    assert ii["not_assessable_reason"] == "fewer than two arms"
    reasons = document["exclusions"]["HOST2"]["hold_reasons"]
    assert "(ii) the same abort input in 1 cells" in reasons
    assert "(ii) arm x abort independence flagged (p <= .10)" not in reasons


def test_an_error_from_the_test_on_a_well_shaped_table_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not caught and turned into "not assessable": a broken input must stop the tool."""
    run = _build(tmp_path, monkeypatch, ArmOnly("D"))

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("damaged table")

    monkeypatch.setattr(partial_go_check, "arm_abort_independence", broken)
    assert partial_go_check.main(run["base"]) == 2


def test_no_abort_final_cell_is_not_assessable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _build(tmp_path, monkeypatch, ())
    document = _check(run)
    assert _ii(document)["not_assessable_reason"] == "no abort-final cell"
    assert not any(r.startswith("(ii)") for r in document["exclusions"]["HOST2"]["hold_reasons"])


@pytest.mark.parametrize(
    ("table", "reason"),
    [
        ({}, "no complete or abort-final cell"),
        ({"D": [3, 2, 0]}, "fewer than two arms"),
        ({"D": [3, 0, 0], "R": [4, 0, 0]}, "no abort-final cell"),
        ({"D": [0, 3, 0], "R": [0, 4, 0]}, "no complete cell"),
        ({"D": [1, 0, 0], "R": [0, 1, 0]}, None),  # two cells: tested (exact p = 1)
        ({"D": [0, 4, 0], "R": [4, 0, 0], "S-u": [4, 0, 0]}, None),
    ],
)
def test_the_table_shape_alone_decides_whether_the_test_runs(
    table: dict[str, list[int]], reason: str | None
) -> None:
    assert partial_go_check.table_shape_problem(table) == reason

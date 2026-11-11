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


@pytest.fixture
def stopped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """HOST1 ran clean; every HOST2 cell aborted twice, then HOST2 stopped unresumed."""
    out, args, assignment = _setup(tmp_path, monkeypatch)
    prereg = Path(args[args.index("--preregistration") + 1])
    host1 = _run(args, out, "HOST1", assignment, (), monkeypatch)
    host2 = _run(args, out, "HOST2", assignment, Everything(), monkeypatch)
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

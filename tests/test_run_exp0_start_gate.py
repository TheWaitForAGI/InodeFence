"""run_exp0 --jobs through the real start gate: verdicts, denials, stops, retries and resume."""

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0
from scripts import gen_exp3_tables

from inodefence.evaluation.cell_completeness import (
    INFRASTRUCTURE_RESUME_EVENT,
    INFRASTRUCTURE_STOP_EVENT,
    START_DENIED_FIELD,
    Attempt,
    classify_cell,
    counted_attempts,
)
from inodefence.execution import start_gate
from inodefence.execution.start_gate import StartDenied, StartGate, acknowledge, record_verdict
from test_run_exp0 import (
    BEFORE,
    TARGET_IMAGES,
    VICTIM,
    _deadline_setup,
    _fake_runner,
    _index,
    _result_lines,
)
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine

GATE_SCRIPT = Path(start_gate.__file__)


@pytest.fixture
def real_gate(clean_engine: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """``clean_engine`` swaps in an always-clean gate; these tests use the real one."""
    monkeypatch.setattr(run_exp0, "StartGate", StartGate)


def _gated_runner(
    verdicts: dict[str, Any],
    *,
    deny: frozenset[str] | set[str] = frozenset(),
    fail: frozenset[str] | set[str] = frozenset(),
    watchdog: frozenset[str] | set[str] = frozenset(),
):
    """Fake cells whose child process goes through the gate's Popen and records a verdict.

    ``verdicts[run_id]`` is ``"S"``, ``("U", reason)`` or ``None`` (no verdict); default ``"S"``.
    A run id in ``deny`` raises StartDenied the first time (the gate refusing the start), and one in
    ``fail`` raises after its child started (a runner failure).
    """
    inner = _fake_runner(TARGET_IMAGES)
    calls: list[str] = []
    denied: set[str] = set()

    def run(cell, output, env, bash, *, limit_seconds, popen=subprocess.Popen, on_timeout=None):
        calls.append(cell.run_id)
        if cell.run_id in deny and cell.run_id not in denied:
            denied.add(cell.run_id)
            raise StartDenied(f"{cell.run_id}: test denial")
        verdict = verdicts.get(cell.run_id, "S")
        argv = [sys.executable, str(GATE_SCRIPT), "record"]
        if verdict is None:
            argv = [sys.executable, "-c", "pass"]
        elif isinstance(verdict, tuple):
            argv += list(verdict)
        else:
            argv.append(verdict)
        if cell.run_id in watchdog:
            # The child outlives the limit: the launcher marks W, then the trap records (or not).
            argv = [
                sys.executable,
                "-c",
                "import subprocess,sys,time; time.sleep(0.3); "
                "sys.exit(subprocess.call(sys.argv[1:]))",
                *argv,
            ]
        process = popen(argv, env=dict(env))
        if cell.run_id in watchdog and on_timeout is not None:
            on_timeout()
        process.wait()
        if cell.run_id in fail:
            raise RuntimeError("runner broke after the start")
        return inner(cell, output, env, bash, limit_seconds=limit_seconds)

    run.calls = calls  # type: ignore[attr-defined]
    return run


def _events(out: Path, name: str) -> list[dict[str, Any]]:
    return [row for row in _result_lines(out) if row.get("event") == name]


def _victim_rows(out: Path) -> list[dict[str, Any]]:
    return [row for row in _result_lines(out) if row.get("run_id") == VICTIM]


@pytest.mark.usefixtures("real_gate", "admit_fixture_holdout")
def test_clean_verdicts_run_every_cell_without_a_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="2")
    runner = _gated_runner({})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main(args)
    assert not _events(out, INFRASTRUCTURE_STOP_EVENT)
    states = _index(out)["interim"]["cell_states"]
    assert set(states.values()) == {"complete"} and len(runner.calls) == len(states)
    assert _index(out)["cell_completeness"]["start_denied_attempts"] == 0


@pytest.mark.usefixtures("real_gate", "admit_fixture_holdout")
@pytest.mark.parametrize("verdict", [("U", "controller ownership: test"), None])
def test_unknown_cleanup_keeps_the_record_and_stops_new_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: Any
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    runner = _gated_runner({VICTIM: verdict})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main(args)
    stops = _events(out, INFRASTRUCTURE_STOP_EVENT)
    assert len(stops) == 1 and stops[0]["reason"].startswith("cleanup unknown: ")
    states = _index(out)["interim"]["cell_states"]
    assert states[VICTIM] == "complete"  # the cell's own record stands
    started = runner.calls
    assert started[-1] == VICTIM  # nothing started after it (jobs=1)
    assert len(started) < len(states)
    # The next call refuses to start; the gate state is on disk.
    again = _gated_runner({})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", again)
    run_exp0.main(args)
    assert again.calls == []


@pytest.mark.usefixtures("real_gate", "admit_fixture_holdout")
def test_a_denied_start_keeps_its_lines_does_not_count_and_never_loops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    runner = _gated_runner({}, deny={VICTIM})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main(args)
    assert runner.calls.count(VICTIM) == 1  # one denial, then the stop: no retry loop
    rows = _victim_rows(out)
    assert [(r["event"], r["attempt"]) for r in rows] == [("start", 1), ("end", 1)]
    assert rows[1]["returncode"] is None and rows[1][START_DENIED_FIELD].endswith("test denial")
    stops = _events(out, INFRASTRUCTURE_STOP_EVENT)
    assert len(stops) == 1 and stops[0]["reason"].startswith(f"start gate denied {VICTIM}")
    index = _index(out)
    assert index["interim"]["cell_states"][VICTIM] == "unattempted"
    assert index["cell_completeness"]["start_denied_attempts"] == 1
    assert index["cell_completeness"]["start_denied_by_cell"] == {VICTIM: 1}
    # A resume (no gate problem: the denial left no U) runs it as attempt 2, counted as its first.
    resumed = _gated_runner({})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", resumed)
    run_exp0.main([*args, "--resume-after-stop", "W2-2026-11-11-1"])
    rows = _victim_rows(out)
    assert [(r["event"], r["attempt"]) for r in rows][-2:] == [("start", 2), ("end", 2)]
    assert _index(out)["interim"]["cell_states"][VICTIM] == "complete"


def test_only_the_explicit_field_excludes_an_attempt(tmp_path: Path) -> None:
    start = {"event": "start", "run_id": "c", "attempt": 1}
    null_exit = Attempt(1, start, {"event": "end", "returncode": None})
    denied = Attempt(2, {**start, "attempt": 2}, {"event": "end", START_DENIED_FIELD: "gate"})
    assert counted_attempts([null_exit, denied]) == (null_exit,)
    missing = tmp_path / "missing"
    state = classify_cell(
        report_path=missing,
        steps_path=missing,
        budget=1,
        attempts=[null_exit, denied, Attempt(3, {**start, "attempt": 3}, None)],
        complete_and_conformant=False,
    ).state
    assert state == "no-record"  # two counted attempts used up; the denial is not one of them


@pytest.mark.usefixtures("real_gate", "admit_fixture_holdout")
def test_resume_needs_acks_tied_to_the_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    monkeypatch.setattr(
        run_exp0, "run_cell_with_watchdog", _gated_runner({VICTIM: ("U", "volume: test")})
    )
    run_exp0.main(args)
    gate_dir = out / run_exp0.START_GATE_DIR
    approval = "W2-2026-11-11-2"
    assert run_exp0.main([*args, "--resume-after-stop", approval]) == 2
    assert "start gate still closed" in capsys.readouterr().err
    acknowledge(gate_dir, VICTIM, "approval=someone-else; by=x; reason=looked at it")
    assert run_exp0.main([*args, "--resume-after-stop", approval]) == 2
    assert f"does not name approval={approval}" in capsys.readouterr().err
    # Before a resume lists it, the note can still be corrected; after, its sha256 is on record.
    [stray] = (gate_dir / "acknowledged").iterdir()
    note = (
        f"approval={approval}; checked_at=2026-11-11T15:00+09:00; by=W2; "
        "residual=docker ps -a --filter name=inodefence- -> none; reason=volume removed by hand"
    )
    (stray / "note.txt").write_text(note + "\n", encoding="utf-8")
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _gated_runner({}))
    assert run_exp0.main([*args, "--resume-after-stop", approval]) == 0
    resume = _events(out, INFRASTRUCTURE_RESUME_EVENT)[-1]
    assert resume["approval_ref"] == approval
    [ack] = resume["gate_acks"]
    assert ack["cell"] == VICTIM and ack["path"] == f"acknowledged/{stray.name}"
    assert ack["note_sha256"] == hashlib.sha256((note + "\n").encode()).hexdigest()
    assert _index(out)["interim"]["cell_states"][VICTIM] == "complete"


@pytest.mark.usefixtures("real_gate", "admit_fixture_holdout")
def test_a_gate_closed_by_an_earlier_call_is_recorded_as_a_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    gate_dir = out / run_exp0.START_GATE_DIR
    gate_dir.mkdir(parents=True)
    (gate_dir / "ghost.session").write_text("other-session\n")
    record_verdict(gate_dir, "ghost", "U", "left by an earlier launcher")
    runner = _gated_runner({})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main(args)
    assert runner.calls == []
    [stop] = _events(out, INFRASTRUCTURE_STOP_EVENT)
    assert stop["reason"].startswith("start gate closed before this call: ")


@pytest.mark.usefixtures("real_gate", "admit_fixture_holdout")
def test_a_runner_error_marks_unknown_records_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    runner = _gated_runner({}, fail={VICTIM})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main(args)  # the exception does not escape pool.map
    end = [r for r in _victim_rows(out) if r["event"] == "end"][-1]
    assert end["runner_error"].startswith("launcher: runner error: RuntimeError")
    [stop] = _events(out, INFRASTRUCTURE_STOP_EVENT)
    assert stop["reason"].startswith(f"runner error on {VICTIM}")
    verdict = StartGate(out / run_exp0.START_GATE_DIR, check_filesystem=False).verdict(VICTIM)
    assert verdict is not None and verdict[0] == "U"


def test_go_attempted_cells_leave_out_denied_only_cells() -> None:
    rows = [
        {"event": "start", "run_id": "a", "attempt": 1, "clocks": {"realtime": 0.0}},
        {"event": "end", "run_id": "a", "attempt": 1, "clocks": {"realtime": 10.0}},
        {"event": "start", "run_id": "b", "attempt": 1, "clocks": {"realtime": 0.0}},
        {
            "event": "end",
            "run_id": "b",
            "attempt": 1,
            "clocks": {"realtime": 0.0},
            START_DENIED_FIELD: "gate",
        },
    ]
    assert gen_exp3_tables._run_clock(rows).attempted_cells == 1
    rows.append({"event": "start", "run_id": "b", "attempt": 2, "clocks": {"realtime": 11.0}})
    assert gen_exp3_tables._run_clock(rows).attempted_cells == 2


@pytest.mark.usefixtures("real_gate", "admit_fixture_holdout")
@pytest.mark.parametrize(("verdict", "stops"), [("S", 0), (None, 1)])
def test_watchdog_waits_for_the_trap_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: Any, stops: int
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    runner = _gated_runner({VICTIM: verdict}, watchdog={VICTIM})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main(args)
    found = _events(out, INFRASTRUCTURE_STOP_EVENT)
    assert len(found) == stops
    if stops:
        assert start_gate.WATCHDOG_TAG in found[0]["reason"]
    else:
        assert len(runner.calls) == len(_index(out)["interim"]["cell_states"])

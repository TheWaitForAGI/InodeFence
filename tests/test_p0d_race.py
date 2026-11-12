"""Coordinate first-attempt and retry authorization against infrastructure stop."""

from threading import Event

import pytest
import scripts.run_exp0 as launcher

from inodefence.evaluation.cell_completeness import InfrastructureGuard
from test_run_exp0 import (
    BEFORE,
    TARGET_IMAGES,
    _deadline_plan,
    _deadline_setup,
    _dies_without_a_record,
    _fake_runner,
    _result_lines,
)
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine

pytestmark = pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")


@pytest.mark.parametrize("blocked_attempt", [1, 2])
def test_stop_prevents_first_attempt_and_retry(tmp_path, monkeypatch, blocked_attempt):
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="2")
    victim = _deadline_plan(args).cells()[0].run_id
    at_boundary, stop_written = Event(), Event()
    original_authorize = InfrastructureGuard.authorize_attempt
    original_append = launcher.append_cell_result
    inner = _fake_runner(TARGET_IMAGES)
    victim_runs = []

    def authorize(guard, record_start):
        cells = dict(
            zip(
                record_start.__code__.co_freevars,
                (item.cell_contents for item in record_start.__closure__),
                strict=False,
            )
        )
        if cells["cell"].run_id == victim and record_start.__defaults__[0] == blocked_attempt:
            at_boundary.set()
            assert stop_written.wait(10), "other worker did not stop"
        return original_authorize(guard, record_start)

    def append(output, record):
        original_append(output, record)
        if record.get("event") == "infrastructure-stop":
            stop_written.set()

    def runner(cell, output, env, bash, **limits):
        if cell.run_id != victim:
            assert at_boundary.wait(10), "victim did not reach authorization boundary"
        else:
            victim_runs.append(cell.run_id)
        result = inner(cell, output, env, bash, **limits)
        return _dies_without_a_record(cell, output, result)

    monkeypatch.setattr(InfrastructureGuard, "authorize_attempt", authorize)
    monkeypatch.setattr(launcher, "append_cell_result", append)
    monkeypatch.setattr(launcher, "run_cell_with_watchdog", runner)
    launcher.main(args)
    rows = _result_lines(out)
    stop_pos = next(i for i, row in enumerate(rows) if row["event"] == "infrastructure-stop")
    assert not any(row.get("event") == "start" for row in rows[stop_pos + 1 :])
    assert len(victim_runs) == blocked_attempt - 1
    assert not any(
        row.get("event") == "start"
        and row.get("run_id") == victim
        and row.get("attempt") == blocked_attempt
        for row in rows
    )


def test_failed_start_record_never_authorizes():
    guard = InfrastructureGuard()

    def fail():
        raise OSError("synthetic write failure")

    with pytest.raises(OSError, match="synthetic write failure"):
        guard.authorize_attempt(fail)
    assert not guard.authorize_attempt(lambda: None)  # lock released; authorization stays closed


def test_start_write_failure_never_calls_runner(tmp_path, monkeypatch):
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    victim = _deadline_plan(args).cells()[0].run_id
    original_append = launcher.append_cell_result
    inner = _fake_runner(TARGET_IMAGES)

    def append(output, record):
        if record.get("event") == "start" and record.get("run_id") == victim:
            raise OSError("synthetic start write failure")
        original_append(output, record)

    monkeypatch.setattr(launcher, "append_cell_result", append)
    monkeypatch.setattr(launcher, "run_cell_with_watchdog", inner)
    with pytest.raises(OSError, match="synthetic start write failure"):
        launcher.main(args)
    assert inner.calls == []
    assert not (out / "cell-results.jsonl").exists()


def test_authorized_attempt_can_run_after_stop():
    from threading import Thread

    guard = InfrastructureGuard()
    start_entered, allow_write, stop_calling, stopped = (Event() for _ in range(4))
    order = []
    for _ in range(2):
        guard.note_cell_end(recorded=False)

    def start():
        def record():
            start_entered.set()
            assert allow_write.wait(5)
            order.append("start")

        assert guard.authorize_attempt(record)
        assert stopped.wait(5)
        order.append("runner")

    def stop():
        assert start_entered.wait(5)
        stop_calling.set()
        assert guard.note_cell_end(recorded=False) is not None
        order.append("stop")
        stopped.set()

    first = Thread(target=start)
    second = Thread(target=stop)
    first.start()
    second.start()
    assert stop_calling.wait(5)
    allow_write.set()
    first.join(5)
    second.join(5)
    assert not first.is_alive() and not second.is_alive()
    assert order == ["start", "stop", "runner"]
    assert not guard.authorize_attempt(lambda: order.append("unexpected"))


def test_authorized_work_remains_parallel():
    from threading import Barrier, Thread

    guard = InfrastructureGuard()
    rendezvous = Barrier(2, timeout=5)
    completed = []

    def worker():
        assert guard.authorize_attempt(lambda: None)
        rendezvous.wait()
        completed.append(True)

    threads = [Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(6)
    assert all(not thread.is_alive() for thread in threads) and len(completed) == 2

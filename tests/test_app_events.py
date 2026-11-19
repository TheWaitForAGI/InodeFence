"""``inodefence.app.events``: file changes become ordered, typed events; nothing is invented.
All folders are SYNTHETIC (``tests/app_synthetic.py``)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from tests import app_synthetic as syn

from inodefence.app import events, runs
from inodefence.app.events import EVENT_SCHEMA, EventKind, RunFollower, TimeSource, UiEvent
from inodefence.app.runs import RunKind, RunRef


def _kinds(items: list[UiEvent]) -> list[str]:
    return [e.kind.value for e in items]


def test_event_round_trip_and_strict_reader() -> None:
    stamp = "2026-01-01T00:00:00+00:00"
    event = UiEvent(EVENT_SCHEMA, 7, stamp, TimeSource.MTIME, "explore", "/x", "rid", True,
                    "node-tar", EventKind.RESULT_READY, verdict="PASS")  # fmt: skip
    line = event.to_json_line()
    assert "\n" not in line and UiEvent.from_json_line(line) == event
    with pytest.raises(ValueError):
        UiEvent.from_json_line(line.replace(EVENT_SCHEMA, "other"))
    with pytest.raises(ValueError):
        UiEvent.from_json_line(line[:-1] + ',"current_case":"x"}')


def test_follower_emits_changes_in_order(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    clock = syn.Clock()
    live, recorder = syn.live_run(out, rid, [syn.step(0)], clock=clock)
    follower = RunFollower([RunRef(RunKind.EXPLORE, out, rid)], clock=clock)
    first = follower.poll_once()
    assert _kinds(first) == ["progress", "state_change"]
    assert first[0].progress_current == 1 and first[0].progress_total == 20
    assert first[0].time_source is TimeSource.UPDATED_AT and first[0].run_id_derived
    assert follower.poll_once() == []  # nothing changed, nothing emitted
    clock.now += 1
    recorder.on_step(syn.step(1, c1=True, fp="c1-x"))
    second = follower.poll_once()
    assert _kinds(second) == ["progress", "violation_case"]
    case_event = second[1]
    assert case_event.case_id == f"{syn.SYNTHETIC}-case-1" and case_event.status == "candidate"
    assert case_event.time_source is TimeSource.RECORDED_AT and case_event.message == "C1"
    clock.now += 1
    recorder.close(state="finished")
    syn.write_result(out / "target-explore" / f"{rid}-result",
                     syn.result(cases=[syn.case("step-1", False)]))  # fmt: skip
    third = follower.poll_once()
    assert _kinds(third) == ["progress", "state_change", "result_ready"]
    assert third[1].message == "running -> finished" and third[2].verdict == "PASS"
    ids = [e.event_id for e in first + second + third]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    assert live.is_dir()


def test_unknown_stays_unknown_without_live_numbers(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), f"{syn.SYNTHETIC}-oras-1-20"
    (out / "target-explore" / f"{rid}-result").mkdir()  # no result yet, no live folder
    (first,) = RunFollower([RunRef(RunKind.EXPLORE, out, rid)]).poll_once()
    assert first.kind is EventKind.STATE_CHANGE and first.status == "unknown"
    assert first.progress_current is None and first.progress_total is None
    assert first.time_source is TimeSource.OBSERVED


def test_launcher_step_is_an_estimate(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), f"{syn.SYNTHETIC}-dc-1-20"
    log = out / "runtime" / "explore-launcher-20260101T000000Z-1.log"
    log.parent.mkdir(parents=True)
    log.write_text("==> [build image]\n", encoding="utf-8")
    follower = RunFollower([RunRef(RunKind.EXPLORE, out, rid)])
    (event,) = [e for e in follower.poll_once() if e.kind is EventKind.LAUNCHER_STEP]
    assert event.estimated and event.status == "build-image" and event.time_source.value == "mtime"


def test_half_written_result_is_silent_until_it_parses(tmp_path: Path) -> None:
    cell = tmp_path / f"{syn.SYNTHETIC}-verify" / "node-tar-7.5.2"
    path = syn.write_result(cell, syn.result(), text='{"schema": ')
    follower = RunFollower([RunRef(RunKind.VERIFY, cell, cell.name)])
    assert [e for e in follower.poll_once() if e.kind is not EventKind.STATE_CHANGE] == []
    path.write_text(syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION).dumps(), encoding="utf-8")
    (ready,) = follower.poll_once()
    assert ready.kind is EventKind.RESULT_READY and ready.verdict == "PASS"


def test_replay_ready_event(tmp_path: Path) -> None:
    case_dir = tmp_path / "violations" / "run-000001"
    case_dir.mkdir(parents=True)
    path = syn.replay(case_dir, {"c0": False, "c1": True, "c2": False}, [syn.judged_round(True)])
    ref = RunRef(RunKind.REPLAY, path.parent, path.parent.name)
    (event,) = RunFollower([ref]).poll_once()
    assert event.kind is EventKind.REPLAY_READY and event.status == "reproduced_violation"
    assert (event.progress_current, event.progress_total) == (1, 1)  # judged / requested


def test_subscribers_share_one_follower_and_drop_oldest(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    syn.live_run(out, rid, [syn.step(0)])
    follower = RunFollower(roots=[out], interval=0.05)
    a, b = follower.subscribe(), follower.subscribe(maxsize=1)
    follower.start()
    try:
        first = a.get(timeout=5)
        assert first is not None and first.kind is EventKind.PROGRESS
        deadline = time.time() + 5
        while b.dropped == 0 and time.time() < deadline:
            time.sleep(0.01)
        assert b.dropped >= 1 and b.get(timeout=1) is not None
    finally:
        follower.stop()
        a.close()
        b.close()


def test_diff_is_pure_and_matches_read_run(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    syn.live_run(out, rid, [syn.step(0)])
    snap = runs.read_run(RunRef(RunKind.EXPLORE, out, rid))
    assert events.diff_snapshots(snap, snap) == []
    assert _kinds(events.diff_snapshots(None, snap)) == ["progress", "state_change"]

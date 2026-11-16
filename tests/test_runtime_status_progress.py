"""PR 3 status additions: throughput and a timed stall warning (observation only)."""

from __future__ import annotations

from pathlib import Path

from inodefence.live_exploration import render_live_status
from test_live_exploration import _recorder, _step


def test_running_status_shows_throughput_and_budget_left(tmp_path: Path) -> None:
    rec, clock, live = _recorder(tmp_path)
    for index in range(3):
        clock.now += 2
        rec.on_step(_step(index))
    rec._write_progress()  # flush (test only)
    text = render_live_status(live, now=clock.now + 1, display="live")
    line = next(line for line in text.splitlines() if line.startswith("  throughput: "))
    assert "runs/min" in line and "budget left" in line and "at this rate" in line
    assert "STALE" not in text


def test_stale_warning_says_how_long_and_that_nothing_is_stopped(tmp_path: Path) -> None:
    rec, clock, live = _recorder(tmp_path)
    rec.on_step(_step(0))
    rec._write_progress()
    text = render_live_status(live, now=clock.now + 600, display="live")
    assert "** STALE: no new step written for a while -- is the run stuck? **" in text
    assert "(no snapshot for 600s, limit 120s; nothing is stopped automatically" in text


def test_finished_run_has_no_throughput_line(tmp_path: Path) -> None:
    rec, clock, live = _recorder(tmp_path)
    rec.on_step(_step(0))
    rec.close()
    text = render_live_status(live, now=clock.now + 5, display="live")
    assert "throughput:" not in text and "STALE" not in text

"""The Rich explore progress display (the ``ui`` extra) and how it is chosen.

The plain display and its line format are pinned by tests/test_explore_progress.py, unchanged.
Here: Rich is chosen only on an interactive terminal with Rich importable and no ``NO_COLOR``;
its live area shows the same fields with unknown values as ``?``; and the last line it leaves is
the very line the plain display prints (:func:`progress.format_line`).
"""

from __future__ import annotations

import builtins
import io
import re
from typing import Any

import pytest
from tests.test_explore_progress import _live_counts, _Tty, _view

from inodefence.drivers import progress as pg

pytest.importorskip("rich")

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def _block_rich(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def no_rich(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "rich" or name.startswith("rich."):
            raise ImportError(f"No module named {name!r} (blocked in this test)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_rich)


def test_rich_only_on_an_interactive_terminal_without_no_color(monkeypatch) -> None:
    assert isinstance(pg.select_display(_Tty(), {"TERM": "xterm"}), pg.RichDisplay)
    assert type(pg.select_display(io.StringIO(), {"TERM": "xterm"})) is pg.Display
    assert type(pg.select_display(_Tty(), {"TERM": "dumb"})) is pg.Display
    no_color = pg.select_display(_Tty(), {"TERM": "xterm", "NO_COLOR": "1"})
    assert type(no_color) is pg.Display and no_color.terminal  # the in-place plain line


def test_without_rich_the_plain_display_is_used_silently(monkeypatch) -> None:
    _block_rich(monkeypatch)
    display = pg.select_display(_Tty(), {"TERM": "xterm"})
    assert type(display) is pg.Display and display.terminal


def test_the_live_area_shows_the_same_fields_and_unknown_as_question_mark() -> None:
    unknown = pg.Counts()  # nothing read yet: every count unknown
    text = "\n".join(line for _, line in pg._rich_lines(_view(unknown)))
    assert "violations ?" in text and "success ?" in text and "un-judged ?" in text
    assert "C1=?" in text and " 0" not in text  # unknown is never shown as 0
    known = "\n".join(line for _, line in pg._rich_lines(_view(_live_counts(violations=2))))
    assert "success 15 · rejected 3" in known and "violations 2" in known
    assert "0.586 runs/s" in known


def test_the_last_line_is_the_plain_displays_last_line() -> None:
    stream = _Tty()
    display = pg.RichDisplay(stream, width=lambda: 120)
    display.message("[explore] header line")
    for runs in (1, 5, 18):
        assert display.update(_view(_live_counts(runs=runs)))
    final = _view(
        _live_counts(runs=40, state="finished"),
        phase=pg.COMPLETED,
        verdict="PASS",
        show_out=True,
    )
    display.final(final)
    out = stream.getvalue()
    assert out.endswith(pg.format_line(final) + "\n")  # exactly, after the live area is cleared
    assert "[explore] header line\n" in out
    assert "18/40 runs (45%)" in _plain(out)  # the bar's count, from progress.json's runs


def test_unknown_runs_draw_no_bar_and_no_percentage() -> None:
    stream = _Tty()
    display = pg.RichDisplay(stream, width=lambda: 120)
    display.update(_view(pg.Counts()))
    plain = _plain(stream.getvalue())
    assert "runs ?/40" in plain and "%" not in plain
    display.final(_view(pg.Counts(), phase=pg.ABORTED, cause="stopped"))


def test_the_drivers_own_output_goes_to_its_own_stream() -> None:
    display_stream, stdout = _Tty(), io.StringIO()
    display = pg.RichDisplay(display_stream, width=lambda: 100)
    display.update(_view(_live_counts()))
    display.passthrough(stdout, "result: /data/out/result.json\n")
    assert stdout.getvalue() == "result: /data/out/result.json\n"  # unchanged, not on stderr
    assert "result:" not in display_stream.getvalue()


def test_the_end_screen_is_a_result_panel_then_the_unchanged_last_line() -> None:
    stream = _Tty()
    display = pg.RichDisplay(stream, width=lambda: 100)
    display.update(_view(_live_counts(runs=18, violations=2)))
    final = _view(
        _live_counts(runs=40, violations=2, state="finished"),
        phase=pg.COMPLETED,
        verdict="FAIL",
        show_out=True,
    )
    display.final(final)
    out = stream.getvalue()
    assert out.endswith(pg.format_line(final) + "\n")  # still the very last line
    plain = _plain(out)
    assert "✗ FAIL" in plain and "oracle candidates (not confirmed)" in plain
    assert "inodefence status /data/out" in plain


def test_the_live_area_is_drawn_on_the_design_system() -> None:
    stream = _Tty()
    display = pg.RichDisplay(stream, width=lambda: 100)
    display.update(_view(_live_counts(runs=18, violations=2)))
    plain = _plain(stream.getvalue())
    assert "›  explore" in plain and "Outcomes (of the runs so far)" in plain
    assert "15/18" in plain and "violations" in plain  # bars from the stored counts


def test_unknown_terminations_draw_no_outcome_bars() -> None:
    stream = _Tty()
    pg.RichDisplay(stream, width=lambda: 100).update(_view(pg.Counts()))
    plain = _plain(stream.getvalue())
    assert "success ?" in plain and "%" not in plain


def test_the_end_keeps_the_final_frame_and_names_a_real_case_to_replay(tmp_path) -> None:
    stream = _Tty()
    display = pg.RichDisplay(stream, width=lambda: 120)
    display.update(_view(_live_counts(runs=18, violations=2)))
    final = _view(
        _live_counts(runs=40, violations=2, state="finished"),
        phase=pg.COMPLETED,
        verdict="FAIL",
        show_out=True,
    )
    cases = [tmp_path / "live" / "violations" / "run-000007", tmp_path / "x"]
    display.final(final, case_dirs=cases)
    out = stream.getvalue()
    assert out.endswith(pg.format_line(final) + "\n")
    tail = _plain(out.split("\x1b[2K")[-1] if "\x1b[2K" in out else out)
    assert "40/40 runs (100%)" in tail and "Outcomes" in tail  # the final frame stays
    joined = "".join(ch for ch in _plain(out) if ch not in "│\n ")
    assert f"inodefencereplay{cases[0]}(oneof2)".replace(" ", "") in joined  # may wrap


def test_no_case_no_replay_example() -> None:
    stream = _Tty()
    display = pg.RichDisplay(stream, width=lambda: 120)
    final = _view(_live_counts(runs=40, state="finished"), phase=pg.COMPLETED, verdict="PASS")
    display.final(final)
    assert "inodefence replay" not in _plain(stream.getvalue())


def test_estimates_and_log_derived_values_say_so() -> None:
    stream = _Tty()
    view = _view(_live_counts(runs=18), eta_seconds=38, step="explore")
    pg.RichDisplay(stream, width=lambda: 120).update(view)
    plain = _plain(stream.getvalue())
    assert "eta ~38s (estimate)" in plain
    assert "launcher step: explore (from the launcher log)" in plain

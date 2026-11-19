"""The TUI's formatting rules, without Textual (``inodefence.ui.tui.model``). SYNTHETIC data."""

from __future__ import annotations

from pathlib import Path

from tests import app_synthetic as syn

from inodefence.app.runs import ReadState, ReplayConclusion, ReplayRecord, RunKind, RunRef, read_run
from inodefence.ui.tui import model


def test_unknown_is_never_zero() -> None:
    assert model.count(None) == "?" and model.count(0) == "0"
    assert model.text(None) == "—" and model.ago(None) == "?"


def test_contract_cells_keep_three_values_with_text() -> None:
    assert [model.contract_cell(v).text for v in (True, False, None)] == ["V", "-", "?"]


def test_replay_cell_uses_judged_as_denominator() -> None:
    record = ReplayRecord(Path("r"), ReadState.OK, ReplayConclusion.PARTIALLY_REPRODUCED,
                          rounds_done=3, judged=2, same_contracts=1)  # fmt: skip
    assert model.replay_cell([record]).text == "partially_reproduced · 1/2 judged, 3 rounds"
    none_judged = ReplayRecord(Path("r"), ReadState.OK, ReplayConclusion.UNJUDGED, rounds_done=3,
                               judged=0)  # fmt: skip
    assert model.replay_cell([none_judged]).text == "unjudged · 0 judged of 3"
    assert model.replay_cell([]).text == "no replay"


def test_a_run_without_live_data_is_not_stalled(tmp_path: Path) -> None:
    out = syn.explore_out(tmp_path)
    snap = read_run(RunRef(RunKind.EXPLORE, out, f"{syn.SYNTHETIC}-oras-1-20"))
    cell = model.run_state(snap, now=snap.read_at + 3600)
    assert cell.text == "no live data" and not model.is_stalled(snap, snap.read_at + 3600)


def test_no_label_says_confirmed() -> None:
    words = [model.finding_class_cell(f).text for f in (None, *model.FindingClass)]
    words += [model.READ_ONLY_NOTE]
    assert not any("confirm" in w or "vulnerab" in w for w in words)

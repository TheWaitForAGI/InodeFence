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


def test_stall_threshold_is_four_pulls(tmp_path: Path) -> None:
    out, rid, clock = syn.explore_out(tmp_path), syn.run_id(), syn.Clock()
    syn.live_run(out, rid, [syn.step(0)], clock=clock)
    snap = read_run(RunRef(RunKind.EXPLORE, out, rid), now=clock.now)
    updated = snap.progress.updated_at if snap.progress else None
    assert updated is not None and model.ACTIVE_MAX_AGE_SECONDS == 60.0
    assert model.run_state(snap, updated + 60).text == "running"
    assert model.run_state(snap, updated + 61).text.startswith("stalled (")


def test_an_unvalidated_result_is_not_plain_finished(tmp_path: Path) -> None:
    import json

    out, rid = syn.explore_out(tmp_path), syn.run_id()
    data = syn.result(cases=[syn.case("step-1", False)]).to_json_dict()
    data["runs"]["executed"] = 99
    syn.write_result(out / "target-explore" / f"{rid}-result", syn.result(), text=json.dumps(data))
    snap = read_run(RunRef(RunKind.EXPLORE, out, rid))
    cell = model.run_state(snap, snap.read_at)
    assert cell.text == "finished (as stored, not validated)" and cell.style == model.WARN


def test_progress_bar_only_from_known_numbers() -> None:
    assert model.progress_bar(None, 20) is None and model.progress_bar(3, None) is None
    assert model.progress_bar(3, 0) is None
    assert model.progress_bar(10, 20) == "█████░░░░░" and model.progress_bar(25, 20) == "█" * 10


def test_replay_columns_split_label_and_counts() -> None:
    record = ReplayRecord(Path("r"), ReadState.OK, ReplayConclusion.REPRODUCED_VIOLATION,
                          rounds_done=3, judged=3, same_contracts=3)  # fmt: skip
    label, numbers = model.replay_columns([record])
    assert (label.text, numbers.text) == ("reproduced", "3/3 · 3 rounds")
    assert model.replay_columns([])[0].text == "no replay"


def test_event_cells_keep_time_source_apart(tmp_path: Path) -> None:
    from inodefence.app.events import EVENT_SCHEMA, EventKind, TimeSource, UiEvent

    event = UiEvent(EVENT_SCHEMA, 1, "2026-01-01T09:49:57+00:00", TimeSource.MTIME, "explore",
                    "/x", "rid", True, "node-tar", EventKind.LAUNCHER_STEP, status="build-image",
                    estimated=True)  # fmt: skip
    when, kind, run, content = model.event_cells(event)
    assert when.text == "09:49:57 m" and kind.text == "launcher_step" and run.text == "rid"
    assert content.text == "build-image (est.)"
    assert "m file mtime" in model.TIME_LEGEND


def test_module_entry_exits_3_with_the_hint_without_textual(monkeypatch, capsys) -> None:
    from inodefence.ui import tui
    from inodefence.ui.tui import __main__ as entry

    def unavailable(**_: object) -> int:
        raise tui.TuiUnavailable(tui.INSTALL_HINT)

    monkeypatch.setattr(entry, "run", unavailable)
    monkeypatch.setattr(entry.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(entry.sys.stdout, "isatty", lambda: True, raising=False)
    assert entry.main([]) == 3
    assert "inodefence[tui]" in capsys.readouterr().err


# -- QA mutation gaps G2-G6 ------------------------------------------------------------------------


def test_g2_only_live_progress_is_sampled_for_the_graph(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    syn.write_result(out / "target-explore" / f"{rid}-result", syn.result())
    finished = read_run(RunRef(RunKind.EXPLORE, out, rid))
    history: list[model.Sample] = []
    model.observe(history, finished)  # a result's numbers are not an observed snapshot
    assert history == []


def test_g3_unknown_increments_are_gaps_not_zero() -> None:
    samples = [
        model.Sample(1.0, 1, None),
        model.Sample(2.0, None, None),
        model.Sample(3.0, 5, None),
    ]
    assert model.increments(samples) == [None, None]
    assert model.sparkline([None, 4.0, None, 2.0], 4)[0] == " "  # a gap, not the lowest block


def test_g4_the_same_snapshot_is_sampled_once(tmp_path: Path) -> None:
    out, rid, clock = syn.explore_out(tmp_path), syn.run_id(), syn.Clock()
    syn.live_run(out, rid, [syn.step(0)], clock=clock)
    snap = read_run(RunRef(RunKind.EXPLORE, out, rid))
    history: list[model.Sample] = []
    model.observe(history, snap)
    model.observe(history, snap)  # same updated_at
    assert len(history) == 1


def test_g5_per_contract_counts_show_the_lower_bound_mark(tmp_path: Path) -> None:
    from dataclasses import replace

    out, rid = syn.explore_out(tmp_path), syn.run_id()
    syn.live_run(out, rid, [syn.step(0, c1=True, fp="c1-a")])
    snap = read_run(RunRef(RunKind.EXPLORE, out, rid))
    assert snap.progress is not None
    lower = replace(snap, progress=replace(snap.progress, contracts_lower_bound=True))
    state = model.DashboardState(snapshots={lower.ref.key: lower})
    by_contract = dict(model.oracle_lines(state, lower))["by contract"].text
    assert "C1 ≥1" in by_contract and "(from case folders)" in by_contract
    exact = dict(model.oracle_lines(state, snap))["by contract"].text
    assert "≥" not in exact


def test_g6_unknown_unjudged_stays_unknown(tmp_path: Path) -> None:
    out = syn.explore_out(tmp_path)
    snap = read_run(RunRef(RunKind.EXPLORE, out, "x-1-20"))
    rows = {label: value for label, value, _, _ in model.outcome_rows(snap)}
    assert rows["unjudged"] is None and rows["build-invalid"] is None


# -- QA mutation gaps E2, E4, T1, T2 ------------------------------------------------------------


def _progress_event(run_id: str, runs: int):
    from inodefence.app.events import EVENT_SCHEMA, EventKind, TimeSource, UiEvent

    return UiEvent(EVENT_SCHEMA, runs, "2026-01-01T00:00:00+00:00", TimeSource.UPDATED_AT,
                   "explore", "/root", run_id, True, "node-tar", EventKind.PROGRESS,
                   status="running", progress_current=runs, progress_total=20)  # fmt: skip


def test_e2_progress_of_different_runs_is_not_folded() -> None:
    folded = model.collapse_events([_progress_event("a", 1), _progress_event("b", 1)])
    assert [(e.run_id, n) for e, n in folded] == [("a", 1), ("b", 1)]


def test_e4_folding_keeps_the_newest_value() -> None:
    folded = model.collapse_events([_progress_event("a", n) for n in (1, 2, 3)])
    ((event, repeats),) = folded
    assert event.progress_current == 3 and repeats == 3


def test_t1_a_cut_value_says_it_was_cut() -> None:
    cut = model.shorten_middle("abcdefghijklmnopqrstuvwxyz", 10)
    assert len(cut) == 10 and "…" in cut and cut.startswith("abcd") and cut.endswith("wxyz")
    assert model.shorten_middle("short", 10) == "short"
    assert model.run_tail("abcdefghijklmnop", None) == "…ijklmnop"  # a cut id is marked
    assert model.run_tail("abc", None) == "abc"


def test_t2_percent_is_none_when_unknown() -> None:
    assert model.percent(None, 20) is None and model.percent(3, None) is None
    assert model.percent(3, 0) is None and model.percent(5, 20) == "25.0%"


def test_the_module_entry_refuses_a_non_interactive_terminal(monkeypatch, capsys) -> None:
    from inodefence.ui.tui import __main__ as entry

    monkeypatch.setattr(entry.sys.stdin, "isatty", lambda: False, raising=False)
    assert entry.main([]) == 3
    assert "interactive terminal" in capsys.readouterr().err

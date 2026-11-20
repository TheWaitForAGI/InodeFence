"""``inodefence tui``: the tiled screens on SYNTHETIC run folders (Textual Pilot, no Docker).

Skipped with the reason when Textual is not installed (it is in the ``dev`` extra, so CI runs it).
The follower is driven by hand (``poll_once`` + ``tick``) so every check is deterministic. The
checks pin content -- values, labels, how unknown is shown -- not pixels.
"""

from __future__ import annotations

import asyncio
import functools
import json
import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("textual", reason="Textual is the optional 'tui' extra (in 'dev' for CI)")

from tests import app_synthetic as syn  # noqa: E402

from inodefence.app.events import RunFollower  # noqa: E402
from inodefence.app.runs import LAUNCHER_QUIET_MAX_SECONDS, RunKind, RunRef  # noqa: E402
from inodefence.ui import tui  # noqa: E402
from inodefence.ui.tui import model  # noqa: E402
from inodefence.ui.tui.app import InodeFenceTui  # noqa: E402

REGISTRY = {
    "node-tar": {"explore": True, "replay": True},
    "python-tarfile": {"explore": True, "replay": True},
    "decompress": {"explore": True, "replay": True},
    "oras-go": {"explore": True, "replay": True},
}
SIZES = [(80, 24), (160, 48)]


def _sync(test):
    """Run an async Pilot test without an async pytest plugin (none is a project dependency)."""

    @functools.wraps(test)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        asyncio.run(test(*args, **kwargs))

    return wrapper


def _app(
    roots: list[Path],
    clock: syn.Clock,
    refs: list[RunRef] | None = None,
    images: dict[str, int] | None = None,
) -> InodeFenceTui:
    follower = RunFollower(refs or (), roots=roots, clock=clock)
    app = InodeFenceTui(roots=roots, follower=follower, background=False, clock=clock,
                        doctor=lambda: ("OK", "no check failed (synthetic)"),
                        targets=lambda: REGISTRY, images=lambda: images)  # fmt: skip
    app.load_now()
    return app


def _rows(app: InodeFenceTui, name: str) -> list[list[str]]:
    from textual.widgets import DataTable

    table = app.query_one(f"#{name}-table", DataTable)
    return [[str(cell) for cell in table.get_row_at(i)] for i in range(table.row_count)]


def _text(node: Any, selector: str) -> str:
    """The plain text a Static shows (Text, Table or Group), as a terminal would print it."""
    from rich.console import Console

    console = Console(width=200, record=True, color_system=None, file=open(os.devnull, "w"))
    console.print(node.query_one(selector).content)
    return console.export_text()


def _overview(app: InodeFenceTui) -> dict[str, str]:
    return {row.cells[0].text.strip(): row.cells[1].text for row in model.overview_rows(app.state)}


async def _settle(app: InodeFenceTui, pilot: Any) -> None:
    app.follower.poll_once()
    app.tick()
    await pilot.pause()


def test_the_package_imports_without_textual_and_names_the_extra() -> None:
    assert tui.TuiUnavailable.__mro__[1] is ImportError
    assert "inodefence[tui]" in tui.INSTALL_HINT


@pytest.mark.parametrize("size", SIZES)
@_sync
async def test_no_runs_shows_the_empty_state(tmp_path: Path, size: tuple[int, int]) -> None:
    app = _app([tmp_path], syn.Clock())
    async with app.run_test(size=size) as pilot:
        await _settle(app, pilot)
        assert app.query_one("#empty").display and not app.query_one("#ov-body").display
        empty = _text(app, "#empty")
        assert "no run folders found" in empty and str(tmp_path) in empty
        assert "inodefence explore --target" in empty
        figures = {label: value.text for label, value, _ in model.key_figures(app.state)}
        assert figures["targets"] == "4" and figures["active"] == "0"
        assert _overview(app)["system"].startswith("OK")
        assert _rows(app, "findings")[0][0] == "no violation candidates"


@pytest.mark.parametrize("size", SIZES)
@_sync
async def test_a_running_run_is_followed_and_a_live_candidate_appears(tmp_path, size) -> None:
    out, rid, clock = syn.explore_out(tmp_path), syn.run_id(), syn.Clock()
    _, recorder = syn.live_run(out, rid, [syn.step(0)], clock=clock)
    app = _app([out], clock)
    async with app.run_test(size=size) as pilot:
        await _settle(app, pilot)
        (row,) = _rows(app, "runs")
        assert (
            row[0] == "node-tar@7.5.2 #1-20" and row[1] == "● running" and row[2].endswith("1/20")
        )
        assert _rows(app, "campaigns")[0][1] == "● running"
        assert _overview(app)["active campaigns"] == "1"
        assert app.query_one("#p-campaign").border_subtitle == "following the newest run"
        events_before = len(app.events)
        clock.now += 1
        recorder.on_step(syn.step(1, c1=True, fp="c1-x"))
        await _settle(app, pilot)  # same app, no restart
        (finding,) = _rows(app, "findings")
        assert finding[1:4] == ["-", "V", "-"] and finding[4] == "candidate"
        assert finding[5] == "no replay" and finding[6] == "—"
        assert len(app.events) > events_before
        oracle = _text(app, "#p-oracle")
        assert "C1 1" in oracle and "candidates" in oracle
        assert "no replay 1" in _overview(app)["by replay"]


@_sync
async def test_the_graph_draws_only_observed_snapshots(tmp_path: Path) -> None:
    out, rid, clock = syn.explore_out(tmp_path), syn.run_id(), syn.Clock()
    _, recorder = syn.live_run(out, rid, [syn.step(0)], clock=clock)
    app = _app([out], clock)
    async with app.run_test(size=(160, 48)) as pilot:
        await _settle(app, pilot)
        key = next(iter(app.state.snapshots))
        assert len(app.history[key]) == 1  # one snapshot: nothing to draw yet
        assert model.sparkline(model.increments(app.history[key]), 40) == ""
        for index in range(1, 4):
            clock.now += 1
            recorder.on_step(syn.step(index))
            await _settle(app, pilot)
        assert [s.runs for s in app.history[key]] == [1, 2, 3, 4]
        assert model.increments(app.history[key]) == [1.0, 1.0, 1.0]


@_sync
async def test_a_quiet_running_snapshot_is_stalled_not_active(tmp_path: Path) -> None:
    out, rid, clock = syn.explore_out(tmp_path), syn.run_id(), syn.Clock()
    syn.live_run(out, rid, [syn.step(0)], clock=clock)
    clock.now += 600
    app = _app([out], clock)
    async with app.run_test(size=(80, 24)) as pilot:
        await _settle(app, pilot)
        (row,) = _rows(app, "runs")
        assert row[1].startswith("! stalled (")
        assert _overview(app)["active campaigns"] == "0" and _overview(app)["stalled"] == "1"


@_sync
async def test_other_targets_show_no_live_data_and_question_marks(tmp_path: Path) -> None:
    # python-tarfile, decompress and oras-go write nothing under target-explore/ until they end:
    # mid-run the launcher log is the only file, and the run is listed from it (QA D3).
    out = tmp_path / "pt-explore"
    log = out / "runtime" / "explore-launcher-20260101T000000Z-1.log"
    log.parent.mkdir(parents=True)
    log.write_text("==> [run controller]\n", encoding="utf-8")
    app = _app([out], syn.Clock(log.stat().st_mtime + 30))
    async with app.run_test(size=(160, 48)) as pilot:
        await _settle(app, pilot)
        (row,) = _rows(app, "campaigns")
        assert row[0] == "(no id yet) pt-explore"
        assert row[1].endswith(model.EST_ACTIVE)  # short in the table
        assert row[2] == "?/?" and row[3] == "?" and row[4] == "?"
        assert row[7].startswith("launcher-log est.")
        outcomes = _text(app, "#p-outcomes")
        assert "success" in outcomes and "?" in outcomes and "█" not in outcomes  # no bars
        campaign = _text(app, "#p-campaign")
        assert "no live data for this run" in campaign
        assert "launching/running (from launcher log, last write" in campaign  # long: panel
        assert "—@—" not in campaign and "@" not in campaign  # target unknown: one "—"
        (overview,) = _rows(app, "runs")
        assert overview[1].endswith(model.EST_ACTIVE) and overview[2] == "?/?"
        assert overview[3] == "?"  # progress and candidates keep their columns


def test_an_unknown_candidate_count_leaves_needs_repro_unknown(tmp_path: Path) -> None:
    out = tmp_path / "pt-explore"
    log = out / "runtime" / "explore-launcher-20260101T000000Z-1.log"
    log.parent.mkdir(parents=True)
    log.write_text("==> [run controller]\n", encoding="utf-8")
    from inodefence.app.runs import discover_runs, read_run

    (ref,) = [x.ref for x in discover_runs([out]) if x.ref]
    snapshot = read_run(ref, now=log.stat().st_mtime + 5)
    lines = dict(model.oracle_lines(model.DashboardState(roots=(out,)), snapshot))
    assert lines["candidates"].text == "?" and lines["needs repro check"].text == "?"


@_sync
async def test_the_overview_runs_table_keeps_every_column_at_140x40(tmp_path: Path) -> None:
    # ORCH (capture r2-tui-A-1): long state words pushed progress and cand. out of the table
    from textual.widgets import DataTable

    out = syn.explore_out(tmp_path / "a")
    syn.live_run(out, syn.run_id(1), [syn.step(0), syn.step(1)], close="finished")
    launch = tmp_path / "launch-fresh-python-tarfile-out"
    log = launch / "runtime" / "explore-launcher-20261120T021743Z-1654134.log"
    log.parent.mkdir(parents=True)
    log.write_text("==> [preflight]\n", encoding="utf-8")
    for age in (30.0, LAUNCHER_QUIET_MAX_SECONDS + 600):
        app = _app([tmp_path], syn.Clock(log.stat().st_mtime + age))
        async with app.run_test(size=(140, 40)) as pilot:
            await _settle(app, pilot)
            table = app.query_one("#runs-table", DataTable)
            widths = [c.get_render_width(table) for c in table.columns.values()]
            assert len(widths) == 4 and sum(widths) <= table.size.width, (age, widths)


@_sync
async def test_a_launcher_only_run_gone_quiet_is_no_activity(tmp_path: Path) -> None:
    out = tmp_path / "pt-explore"
    log = out / "runtime" / "explore-launcher-20260101T000000Z-1.log"
    log.parent.mkdir(parents=True)
    log.write_text("==> [run controller]\n", encoding="utf-8")
    clock = syn.Clock(log.stat().st_mtime + LAUNCHER_QUIET_MAX_SECONDS + 600)
    app = _app([out], clock)
    async with app.run_test(size=(160, 48)) as pilot:
        await _settle(app, pilot)
        (row,) = _rows(app, "campaigns")
        assert row[1].endswith(model.EST_QUIET) and "running" not in row[1]
        assert "no activity (launcher log last written" in _text(app, "#p-campaign")
        (snapshot,) = app.state.snapshots.values()
        assert not model.is_active(snapshot, clock()) and model.is_stalled(snapshot, clock())


@_sync
async def test_a_finished_live_run_does_not_wait_for_more_snapshots(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    syn.live_run(out, rid, [syn.step(1)], close="finished")
    app = _app([out], syn.Clock(), refs=[RunRef(RunKind.EXPLORE, out, rid)])
    async with app.run_test(size=(160, 48)) as pilot:
        await _settle(app, pilot)
        campaign = _text(app, "#p-campaign")
        assert "finished · no progress snapshots observed by this screen" in campaign
        assert "waiting for a second progress snapshot" not in campaign  # QA F6


@_sync
async def test_verify_fixtures_are_not_counted_as_candidates(tmp_path: Path) -> None:
    cell = tmp_path / "verify" / "node-tar-7.5.2"
    cases = [syn.case("toplevel_hardlink", True, termination=None),
             syn.case("dir_symlink_write", False, termination=None)]  # fmt: skip
    syn.write_result(cell, syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION, cases=cases))
    app = _app([tmp_path / "verify"], syn.Clock())
    async with app.run_test(size=(160, 48)) as pilot:
        await _settle(app, pilot)
        (verify,) = _rows(app, "verify")
        assert verify[5] == "1"  # fixtures V
        assert model.findings(app.state) == []  # no candidate from a verify cell
        rows = {r.key: r.cells[1].text for r in model.overview_rows(app.state)}
        assert rows["violation candidates"] == "0"
        assert rows["known fixtures violated (verify)"] == "1"


@_sync
async def test_finished_result_with_a_replayed_candidate(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    result_dir = out / "target-explore" / f"{rid}-result"
    res = syn.result(cases=[syn.case("step-1", False), syn.case("step-2", True)], saved=["step-2"])
    syn.write_result(result_dir, res)
    original = {"case_id": "step-2", "c0": False, "c1": True, "c2": False}
    rounds = [syn.judged_round(True), syn.judged_round(False), syn.failed_round()]
    syn.replay(result_dir, original, rounds)
    app = _app([out], syn.Clock())
    async with app.run_test(size=(160, 48)) as pilot:
        await _settle(app, pilot)
        assert _rows(app, "campaigns")[0][1] == "✓ finished"
        (finding,) = _rows(app, "findings")
        assert finding[5] == "partial" and finding[6] == "1/2 · 3 rounds"
        assert "partially 1" in _overview(app)["by replay"]
        await pilot.press("4")
        await pilot.pause()
        side = _text(app, "#finding-detail-body")
        assert "input SHA-256" in side and "round 3" in side and "replay rounds" in side
        assert "observation complete  yes" in side
        assert syn.TAR.decode() not in side  # the input's content is never shown
        await pilot.press("enter")
        await pilot.pause()
        detail = _text(app.screen, "#detail-body")
        assert "round 3" in detail and syn.TAR.decode() not in detail
        await pilot.press("escape", "3", "enter")
        await pilot.pause()
        from textual.widgets import TabbedContent

        # enter on a run opens its artifacts
        assert app.query_one("#tabs", TabbedContent).active == "artifacts"
        artifacts = _text(app, "#artifacts-body")
        assert "not re-checked" in artifacts and "result.json" in artifacts


@_sync
async def test_unvalidated_and_unreadable_are_marked(tmp_path: Path) -> None:
    verify = tmp_path / f"{syn.SYNTHETIC}-verify"
    data = syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION).to_json_dict()
    data["runs"]["executed"] = 99
    syn.write_result(verify / "node-tar-7.5.2", syn.result(), text=json.dumps(data))
    locked = verify / "locked"
    locked.mkdir()
    os.chmod(locked, 0)
    try:
        app = _app([verify], syn.Clock())
        async with app.run_test(size=(80, 24)) as pilot:
            await _settle(app, pilot)
            (row,) = _rows(app, "verify")
            assert row[1].endswith("(as stored)")
            unread = _overview(app)["folders not read"]
            assert unread == ("0" if os.geteuid() == 0 else "1")
    finally:
        os.chmod(locked, 0o755)


@_sync
async def test_an_explore_run_with_an_unvalidated_result_is_marked(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    data = syn.result(cases=[syn.case("step-1", False)]).to_json_dict()
    data["runs"]["executed"] = 99
    syn.write_result(out / "target-explore" / f"{rid}-result", syn.result(), text=json.dumps(data))
    app = _app([out], syn.Clock())
    async with app.run_test(size=(160, 48)) as pilot:
        await _settle(app, pilot)
        assert _rows(app, "campaigns")[0][1] == "! finished (as stored, not validated)"
        assert _rows(app, "runs")[0][1] == "! finished (as stored, not validated)"
        overview = _overview(app)
        assert overview["results as stored (not validated)"] == "1"
        assert overview["finished explore runs"] == "1"


@_sync
async def test_keys_switch_screens_and_help(tmp_path: Path) -> None:
    from textual.widgets import TabbedContent

    app = _app([tmp_path], syn.Clock())
    async with app.run_test(size=(80, 24)) as pilot:
        await _settle(app, pilot)
        for key, tab in (("2", "targets"), ("3", "campaigns"), ("4", "findings"),
                         ("5", "artifacts"), ("1", "overview")):  # fmt: skip
            await pilot.press(key)
            assert app.query_one("#tabs", TabbedContent).active == tab
        await pilot.press("question_mark")
        await pilot.pause()
        assert "read-only" in _text(app.screen, "#detail-body")
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is app.screen_stack[0]


@_sync
async def test_targets_come_from_registry_doctor_images_and_last_verify(tmp_path: Path) -> None:
    verify = tmp_path / f"{syn.SYNTHETIC}-verify"
    syn.write_result(verify / "node-tar-7.5.2", syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION))
    app = _app([verify], syn.Clock(), images={"node-tar": 3})
    async with app.run_test(size=(160, 48)) as pilot:
        await _settle(app, pilot)
        rows = {row[0]: row for row in _rows(app, "targets")}
        assert rows["node-tar"][3] == "3" and rows["node-tar"][4].startswith("7.5.2 · PASS")
        assert rows["oras-go"][3] == "—" and rows["oras-go"][4] == "—"


@_sync
async def test_narrow_and_wide_layouts(tmp_path: Path) -> None:
    out, rid, clock = syn.explore_out(tmp_path), syn.run_id(), syn.Clock()
    syn.live_run(out, rid, [syn.step(0)], clock=clock)
    for size, wide in (((80, 24), False), ((140, 40), True)):
        app = _app([out], clock)
        async with app.run_test(size=size) as pilot:
            await _settle(app, pilot)
            assert app.query_one("#ov-mid").display is wide
            assert app.query_one("#p-targets").display is wide
            assert app.query_one("#ov-body").has_class("narrow") is not wide


@_sync
async def test_a_refresh_keeps_the_selected_row(tmp_path: Path) -> None:
    from textual.widgets import DataTable

    out, rid, clock = syn.explore_out(tmp_path), syn.run_id(), syn.Clock()
    steps = [syn.step(0, c1=True, fp="c1-a"), syn.step(1, c1=True, fp="c1-b"), syn.step(2)]
    syn.live_run(out, rid, steps, clock=clock)
    app = _app([out], clock)
    async with app.run_test(size=(120, 36)) as pilot:
        await _settle(app, pilot)
        await pilot.press("4", "down")
        await pilot.pause()
        table = app.query_one("#findings-table", DataTable)
        assert table.cursor_row == 1
        selected = app.selected_key
        await _settle(app, pilot)  # a refresh redraws every table
        assert table.cursor_row == 1 and app.selected_key == selected


@_sync
async def test_the_cursor_follows_the_same_run_not_the_row_number(tmp_path: Path) -> None:
    from textual.widgets import DataTable

    from inodefence.ui.tui.model import Row

    out, clock = syn.explore_out(tmp_path), syn.Clock()
    recorders = []
    for seed in (1, 2, 3):
        _, recorder = syn.live_run(out, syn.run_id(seed), [syn.step(0)], clock=clock)
        recorders.append(recorder)
    app = _app([out], clock)
    async with app.run_test(size=(120, 36)) as pilot:
        await _settle(app, pilot)
        await pilot.press("3", "down", "down")
        await pilot.pause()
        table = app.query_one("#campaigns-table", DataTable)
        chosen = app._row_keys["campaigns"][2]
        assert table.cursor_row == 2 and app.selected_key == chosen
        clock.now += 1
        recorders[0].on_step(syn.step(1, c1=True, fp="c1-z"))  # an event from another run
        await _settle(app, pilot)
        assert app._row_keys["campaigns"][table.cursor_row] == chosen
        current = app._row_keys["campaigns"]
        reordered = [Row(k, tuple(model.Cell(c) for c in (k, *[""] * 7))) for k in current]
        app._fill("campaigns", list(reversed(reordered)))
        assert app._row_keys["campaigns"][table.cursor_row] == chosen
        app._fill("campaigns", [r for r in reordered if r.key != chosen])
        assert 0 <= table.cursor_row < 2


@_sync
async def test_events_fold_consecutive_progress_and_keep_other_kinds(tmp_path: Path) -> None:
    out, rid, clock = syn.explore_out(tmp_path), syn.run_id(), syn.Clock()
    _, recorder = syn.live_run(out, rid, [syn.step(0)], clock=clock)
    app = _app([out], clock)
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(app, pilot)
        for index in range(1, 5):
            clock.now += 1
            recorder.on_step(syn.step(index, c1=index == 2, fp="c1-q" if index == 2 else ""))
            await _settle(app, pilot)
        folded = model.collapse_events(list(app.events))
        kinds = [event.kind.value for event, _ in folded]
        assert "violation_case" in kinds
        assert max(n for _, n in folded) >= 2  # several progress snapshots on one line
        shown = _text(app, "#events-body")
        assert "violation_case" in shown and "×" in shown


def test_outcomes_zero_is_observed_and_unknown_is_question_mark(tmp_path: Path) -> None:
    from inodefence.app.runs import read_run

    out, rid = syn.explore_out(tmp_path), syn.run_id()
    syn.live_run(out, rid, [syn.step(0)])
    live = {label: value for label, value, _, _ in
            model.outcome_rows(read_run(RunRef(RunKind.EXPLORE, out, rid)))}  # fmt: skip
    assert live["rejected"] == 0 and live["unjudged"] == 0  # the snapshot holds these zeros
    other = {label: value for label, value, _, _ in
             model.outcome_rows(read_run(RunRef(RunKind.EXPLORE, out, "x-1-20")))}  # fmt: skip
    assert all(value is None for value in other.values())  # no file: unknown, not 0


@_sync
async def test_the_narrow_run_list_says_how_many_runs_do_not_fit(tmp_path: Path) -> None:
    out, clock = syn.explore_out(tmp_path), syn.Clock()
    for seed in range(1, 4):
        syn.live_run(out, syn.run_id(seed), [syn.step(0)], clock=clock)
    app = _app([out], clock)
    async with app.run_test(size=(80, 24)) as pilot:
        await _settle(app, pilot)
        await pilot.pause()
        assert app.query_one("#p-runs").border_subtitle == "3 explore runs · all"  # all fit
    for seed in range(4, 12):
        syn.live_run(out, syn.run_id(seed), [syn.step(0)], clock=clock)
    app = _app([out], clock)
    async with app.run_test(size=(80, 24)) as pilot:
        await _settle(app, pilot)
        await pilot.pause()
        subtitle = app.query_one("#p-runs").border_subtitle or ""
        assert subtitle.startswith("+") and subtitle.endswith("more (↑ ↓)")


def test_an_unclassified_violation_is_its_own_row_not_a_candidate(tmp_path: Path) -> None:
    from inodefence.app.runs import RunSnapshot, read_result

    path = tmp_path / "cell" / "result.json"
    cases = [syn.case("toplevel_hardlink", True, termination=None)]
    syn.write_result(path.parent, syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION, cases=cases))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["mode"] = 7  # broken, and no run kind below: unknown
    path.write_text(json.dumps(data), encoding="utf-8")
    summary = read_result(path)
    ref = RunRef(RunKind.VERIFY, path.parent, "cell")
    snapshot = RunSnapshot(ref, 0.0, summary=summary,
                           unclassified_violations=summary.unclassified_violations)  # fmt: skip
    state = model.DashboardState(snapshots={ref.key: snapshot})
    rows = {r.key: r.cells[1].text for r in model.overview_rows(state)}
    assert rows["unclassified (result not validated)"] == "1"
    assert rows["violation candidates"] == "0"
    assert rows["known fixtures violated (verify)"] == "0"
    model.verify_rows(state)  # renders without raising

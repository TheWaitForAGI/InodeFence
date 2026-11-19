"""``inodefence tui``: the five screens on SYNTHETIC run folders (Textual Pilot, no Docker).

Skipped with the reason when Textual is not installed (it is in the ``dev`` extra, so CI runs it).
The follower is driven by hand (``poll_once`` + ``tick``) so every check is deterministic.
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
from inodefence.app.runs import RunKind, RunRef  # noqa: E402
from inodefence.ui import tui  # noqa: E402
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


def _app(roots: list[Path], clock: syn.Clock, refs: list[RunRef] | None = None) -> InodeFenceTui:
    follower = RunFollower(refs or (), roots=roots, clock=clock)
    app = InodeFenceTui(roots=roots, follower=follower, background=False, clock=clock,
                        doctor=lambda: ("OK", "no check failed (synthetic)"),
                        targets=lambda: REGISTRY)  # fmt: skip
    app.load_now()
    return app


def _rows(app: InodeFenceTui, name: str) -> list[list[str]]:
    from textual.widgets import DataTable

    table = app.query_one(f"#{name}-table", DataTable)
    return [[str(cell) for cell in table.get_row_at(i)] for i in range(table.row_count)]


def _overview(app: InodeFenceTui) -> dict[str, str]:
    return {row[0].strip(): row[1] for row in _rows(app, "overview")}


async def _settle(app: InodeFenceTui, pilot: Any) -> None:
    app.follower.poll_once()
    app.tick()
    await pilot.pause()


def test_the_package_imports_without_textual_and_names_the_extra() -> None:
    assert tui.TuiUnavailable.__mro__[1] is ImportError
    assert "inodefence[tui]" in tui.INSTALL_HINT


@pytest.mark.parametrize("size", SIZES)
@_sync
async def test_no_runs(tmp_path: Path, size: tuple[int, int]) -> None:
    app = _app([tmp_path], syn.Clock())
    async with app.run_test(size=size) as pilot:
        await _settle(app, pilot)
        assert _rows(app, "campaigns") == [["no explore runs found", *[""] * 9]]
        assert _rows(app, "findings")[0][0] == "no violation candidates"
        overview = _overview(app)
        assert overview["system"].startswith("OK")
        assert overview["targets registered"] == "4"
        assert overview["violation candidates"] == "0"  # counted over the folders scanned
        assert "read-only" in str(app.query_one("#recent").render())


@pytest.mark.parametrize("size", SIZES)
@_sync
async def test_a_running_node_tar_run_then_a_live_candidate(tmp_path, size) -> None:
    out, rid, clock = syn.explore_out(tmp_path), syn.run_id(), syn.Clock()
    _, recorder = syn.live_run(out, rid, [syn.step(0)], clock=clock)
    app = _app([out], clock)
    async with app.run_test(size=size) as pilot:
        await _settle(app, pilot)
        (row,) = _rows(app, "campaigns")
        assert row[0] == rid and row[3] == "running" and row[4] == "1/20" and row[9] == "live"
        assert _overview(app)["active campaigns"] == "1"
        events_before = len(app.events)
        clock.now += 1
        recorder.on_step(syn.step(1, c1=True, fp="c1-x"))
        await _settle(app, pilot)  # same app, no restart
        (finding,) = _rows(app, "findings")
        assert finding[2:5] == ["-", "V", "-"] and finding[5] == "candidate"
        assert finding[7] == "no replay"
        assert len(app.events) > events_before
        assert "reproduced 0" in _overview(app)["by replay"]
        assert "no replay 1" in _overview(app)["by replay"]


@_sync
async def test_a_quiet_running_snapshot_is_stalled_not_active(tmp_path: Path) -> None:
    out, rid, clock = syn.explore_out(tmp_path), syn.run_id(), syn.Clock()
    syn.live_run(out, rid, [syn.step(0)], clock=clock)
    clock.now += 600
    app = _app([out], clock)
    async with app.run_test(size=(80, 24)) as pilot:
        await _settle(app, pilot)
        (row,) = _rows(app, "campaigns")
        assert row[3].startswith("stalled (")
        assert _overview(app)["active campaigns"] == "0" and _overview(app)["stalled"] == "1"


@_sync
async def test_other_targets_show_no_live_data_and_question_marks(tmp_path: Path) -> None:
    out = syn.explore_out(tmp_path)
    rid = f"{syn.SYNTHETIC}-3.12.7-data-1-20"
    ref = RunRef(RunKind.EXPLORE, out, rid)
    log = out / "runtime" / "explore-launcher-20260101T000000Z-1.log"
    log.parent.mkdir(parents=True)
    log.write_text("==> [run controller]\n", encoding="utf-8")
    app = _app([out], syn.Clock(), refs=[ref])
    async with app.run_test(size=(80, 24)) as pilot:
        await _settle(app, pilot)
        (row,) = _rows(app, "campaigns")
        assert row[3] == "no live data" and row[4] == "?/?" and row[5] == "?" and row[6] == "?"
        assert row[9].startswith("launcher-log est.")
        assert "0" not in (row[4], row[6], row[7])


@_sync
async def test_finished_result_with_a_replayed_candidate(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    result_dir = out / "target-explore" / f"{rid}-result"
    res = syn.result(cases=[syn.case("step-1", False), syn.case("step-2", True)], saved=["step-2"])
    syn.write_result(result_dir, res)
    original = {"case_id": "step-2", "c0": False, "c1": True, "c2": False}
    syn.replay(result_dir, original,
               [syn.judged_round(True), syn.judged_round(False), syn.failed_round()])  # fmt: skip
    app = _app([out], syn.Clock())
    async with app.run_test(size=(160, 48)) as pilot:
        await _settle(app, pilot)
        (row,) = _rows(app, "campaigns")
        assert row[3] == "finished" and row[9] == "result"
        (finding,) = _rows(app, "findings")
        assert finding[7] == "partially_reproduced · 1/2 judged, 3 rounds"
        assert "partially 1" in _overview(app)["by replay"]
        await pilot.press("4")
        await pilot.press("enter")
        await pilot.pause()
        detail = str(app.screen.query_one("#detail-body").render())
        assert "round 3" in detail and "input SHA-256" in detail
        assert syn.TAR.decode() not in detail  # the input's content is never shown
        await pilot.press("escape")
        await pilot.press("5")
        await pilot.pause()
        artifacts = str(app.query_one("#artifacts-body").render())
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
        assert "read-only" in str(app.screen.query_one("#detail-body").render())
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is app.screen_stack[0]


@_sync
async def test_targets_come_from_the_registry_and_last_verify(tmp_path: Path) -> None:
    verify = tmp_path / f"{syn.SYNTHETIC}-verify"
    syn.write_result(verify / "node-tar-7.5.2", syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION))
    app = _app([verify], syn.Clock())
    async with app.run_test(size=(160, 48)) as pilot:
        await _settle(app, pilot)
        rows = {row[0]: row for row in _rows(app, "targets")}
        assert rows["node-tar"][4].startswith("7.5.2 · PASS")
        assert rows["oras-go"][3] == "—" and rows["oras-go"][4] == "—"

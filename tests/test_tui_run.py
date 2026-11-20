"""Running a command from the TUI, end to end with the fake ``inodefence`` (nothing real runs):
pick, fill, confirm (focus on Cancel), start; plan; large budgets; commands that run nothing."""

from __future__ import annotations

import asyncio
import functools
import json
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("textual")

from tests import app_synthetic as syn  # noqa: E402
from tests import tui_fake_cli  # noqa: E402
from textual.widgets import Button, Input, OptionList, Static  # noqa: E402

from inodefence.app.events import RunFollower  # noqa: E402
from inodefence.ui.tui import launch  # noqa: E402
from inodefence.ui.tui.app import InodeFenceTui  # noqa: E402
from inodefence.ui.tui.screens_run import (  # noqa: E402
    PRODUCT_RUN,
    CommandFormScreen,
    CommandPicker,
    ConfirmScreen,
    OutputScreen,
)

REGISTRY = {"node-tar": {"explore": True, "replay": True, "options": []},
            "python-tarfile": {"explore": True, "replay": True, "options": [
                {"name": "extraction-filter", "description": "filter", "required": True,
                 "choices": ["fully_trusted", "data"], "single": True}]}}  # fmt: skip


def _sync(test):
    @functools.wraps(test)
    def run(*args: Any, **kwargs: Any) -> None:
        asyncio.run(test(*args, **kwargs))

    return run


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    program = tui_fake_cli.install(tmp_path / "bin")
    argv_log = tmp_path / "argv.jsonl"
    monkeypatch.setenv("FAKE_ARGV_LOG", str(argv_log))
    root = syn.explore_out(tmp_path / "scanned")
    app = InodeFenceTui(
        roots=[root], follower=RunFollower(roots=[root], clock=syn.Clock()), background=False,
        clock=syn.Clock(), doctor=lambda: ("OK", "synthetic"), targets=lambda: REGISTRY,
        images=lambda: None, cli=program, launch_root=tmp_path / "launches", cwd=tmp_path,
    )  # fmt: skip
    app.load_now()
    return {"app": app, "argv_log": argv_log, "launches": tmp_path / "launches", "tmp": tmp_path}


def _seen(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


async def _to_form(app: InodeFenceTui, pilot: Any, command: str) -> CommandFormScreen:
    await pilot.press("n")
    await pilot.pause()
    assert isinstance(app.screen, CommandPicker)
    options = app.screen.query_one(OptionList)
    index = next(
        i for i in range(options.option_count) if options.get_option_at_index(i).id == command
    )
    options.highlighted = index
    await pilot.press("enter")
    await pilot.pause()
    assert isinstance(app.screen, CommandFormScreen) and app.screen.form.name == command
    return app.screen


def _fill(screen: CommandFormScreen, **values: str) -> None:
    for dest, value in values.items():
        screen.query_one(f"#field-{dest}", Input).value = value


async def _press(app: InodeFenceTui, pilot: Any, button: str) -> None:
    app.screen.query_one(f"#{button}", Button).press()
    await pilot.pause()
    await pilot.pause()


@_sync
async def test_the_confirmation_shows_the_whole_command_and_enter_cancels(setup) -> None:
    app = setup["app"]
    async with app.run_test(size=(140, 44)) as pilot:
        form = await _to_form(app, pilot, "explore")
        _fill(form, version="7.5.2", seed="7")
        await _press(app, pilot, "form-continue")
        assert isinstance(app.screen, ConfirmScreen)
        command = str(app.screen.query_one("#confirm-command", Static).content)
        assert command == "inodefence explore --version 7.5.2 --seed 7"
        assert PRODUCT_RUN in str(app.screen.query_one("#confirm-notes", Static).content)
        assert app.focused is app.screen.query_one("#confirm-cancel", Button)  # focus on Cancel
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)
    assert _seen(setup["argv_log"]) == [] and app.launches == []  # nothing started


@_sync
async def test_start_runs_exactly_the_shown_command(setup) -> None:
    app = setup["app"]
    async with app.run_test(size=(140, 44)) as pilot:
        form = await _to_form(app, pilot, "explore")
        _fill(form, version="latest")
        await _press(app, pilot, "form-continue")
        await _press(app, pilot, "confirm-start")
        assert len(app.launches) == 1
    done = launch.wait(app.launches[0], timeout=20)
    assert done.exit_code == 0 and _seen(setup["argv_log"]) == [["explore", "--version", "latest"]]


@_sync
async def test_a_large_budget_needs_start_twice(setup) -> None:
    app = setup["app"]
    async with app.run_test(size=(140, 44)) as pilot:
        form = await _to_form(app, pilot, "explore")
        _fill(form, version="latest", budget="2500")
        await _press(app, pilot, "form-continue")
        notes = str(app.screen.query_one("#confirm-notes", Static).content)
        assert "budget 2500 is above 2000" in notes
        await _press(app, pilot, "confirm-start")
        assert isinstance(app.screen, ConfirmScreen) and app.launches == []  # asked once more
        await _press(app, pilot, "confirm-start")
        assert len(app.launches) == 1
    launch.wait(app.launches[0], timeout=20)


@_sync
async def test_the_plan_is_the_dry_run_and_starts_nothing(setup) -> None:
    app = setup["app"]
    async with app.run_test(size=(140, 44)) as pilot:
        form = await _to_form(app, pilot, "verify")
        _fill(form, version="7.5.2")
        await _press(app, pilot, "form-continue")
        await _press(app, pilot, "confirm-plan-button")
        deadline = time.monotonic() + 20
        while "plan (exit" not in str(app.screen.query_one("#confirm-plan-body", Static).content):
            assert time.monotonic() < deadline
            await pilot.pause(0.05)
        body = str(app.screen.query_one("#confirm-plan-body", Static).content)
        assert "fake inodefence verify --version 7.5.2 --dry-run" in body
        assert app.launches == []
    assert _seen(setup["argv_log"]) == [["verify", "--version", "7.5.2", "--dry-run"]]


@_sync
async def test_a_command_that_runs_nothing_shows_its_output_and_code(setup, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_EXIT", "2")
    app = setup["app"]
    async with app.run_test(size=(140, 44)) as pilot:
        form = await _to_form(app, pilot, "status")
        _fill(form, folder=str(setup["tmp"]))
        await _press(app, pilot, "form-continue")
        deadline = time.monotonic() + 20
        while not isinstance(app.screen, OutputScreen):
            assert time.monotonic() < deadline
            await pilot.pause(0.05)
        body = str(app.screen.query_one("#output-body", Static).content)
        assert "fake inodefence status" in body and body.rstrip().endswith("exit 2")
    assert app.launches == []  # waited for, not started detached


@_sync
async def test_an_out_folder_elsewhere_is_scanned_for_this_session(setup) -> None:
    app = setup["app"]
    elsewhere = setup["tmp"] / "elsewhere"
    async with app.run_test(size=(140, 44)) as pilot:
        form = await _to_form(app, pilot, "explore")
        _fill(form, version="latest", out=str(elsewhere))
        await _press(app, pilot, "form-continue")
        notes = str(app.screen.query_one("#confirm-notes", Static).content)
        assert "outside this screen's folders" in notes
        await _press(app, pilot, "confirm-start")
        assert elsewhere in app.roots
    launch.wait(app.launches[0], timeout=20)


@_sync
async def test_an_empty_required_field_keeps_the_form_open(setup) -> None:
    app = setup["app"]
    async with app.run_test(size=(140, 44)) as pilot:
        await _to_form(app, pilot, "explore")
        await _press(app, pilot, "form-continue")
        assert isinstance(app.screen, CommandFormScreen)
        assert "--version" in str(app.screen.query_one("#form-error", Static).content)
    assert app.launches == []


@_sync
async def test_the_picker_marks_the_commands_that_start_docker(setup) -> None:
    app = setup["app"]
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.press("n")
        await pilot.pause()
        options = app.screen.query_one(OptionList)
        marked = {
            options.get_option_at_index(i).id
            for i in range(options.option_count)
            if "starts Docker" in str(options.get_option_at_index(i).prompt)
        }
        assert marked == {"verify", "explore", "replay"}


@pytest.fixture
def with_runs(setup) -> dict[str, Any]:
    """An exploration result with a saved candidate, and a verify cell (both synthetic)."""
    root = setup["app"].roots[0]
    rid = syn.run_id()
    result_dir = root / "target-explore" / f"{rid}-result"
    res = syn.result(cases=[syn.case("step-1", False), syn.case("step-2", True)], saved=["step-2"])
    syn.write_result(result_dir, res)
    cell = root / "verify-cell"
    syn.write_result(cell, syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION,
                                      cases=[syn.case("dir_symlink_write", False)]))  # fmt: skip
    setup["app"].follower.poll_once()
    return {**setup, "result": result_dir / "result.json", "cell": cell / "result.json",
            "root": root}  # fmt: skip


@_sync
async def test_a_target_shortcut_fills_the_target(setup) -> None:
    app = setup["app"]
    async with app.run_test(size=(140, 44)) as pilot:
        app.tick()
        await pilot.press("2")
        await pilot.pause()
        table = app.query_one("#targets-table")
        table.move_cursor(row=app._row_keys["targets"].index("python-tarfile"))
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, CommandFormScreen) and app.screen.form.name == "explore"
        assert app.screen.values()["target"] == "python-tarfile"


@_sync
async def test_run_shortcuts_fill_status_summary_compare_and_replay(with_runs) -> None:
    app = with_runs["app"]
    async with app.run_test(size=(140, 44)) as pilot:
        app.tick()
        await pilot.pause()
        explore_key = next(
            k for k, s in app.state.snapshots.items() if s.ref.kind.value == "explore"
        )
        verify_key = next(k for k, s in app.state.snapshots.items() if s.ref.kind.value == "verify")
        app.selected_key = explore_key
        assert app.shortcut_preset("status")[0] == {"folder": str(with_runs["root"])}
        assert app.shortcut_preset("summary")[0] == {"result": str(with_runs["result"])}
        first, why = app.shortcut_preset("compare")
        assert first is None and why and "press c on another" in why
        app.selected_key = verify_key
        assert app.shortcut_preset("compare")[0] == {
            "a": str(with_runs["result"]), "b": str(with_runs["cell"]),
        }  # fmt: skip
        assert app.shortcut_preset("status")[0] is None  # a verify cell has no status
        app.selected_key = f"{explore_key}#step-2"
        assert app.shortcut_preset("replay")[0] == {
            "case_dir": str(with_runs["result"].parent), "case": "step-2",
        }  # fmt: skip
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, CommandFormScreen) and app.screen.form.name == "replay"
        assert app.screen.values()["case"] == "step-2"


@_sync
async def test_a_shortcut_without_a_fitting_row_says_why_and_opens_nothing(setup) -> None:
    app = setup["app"]
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.press("p")
        await pilot.pause()
        assert not isinstance(app.screen, CommandFormScreen)
        preset, why = app.shortcut_preset("verify")  # not on the Targets tab
        assert preset is None and why and "Targets" in why


def test_the_command_line_wraps_only_between_options_and_still_pastes() -> None:
    import shlex as _shlex

    from inodefence.ui.tui.screens_run import wrapped_command

    argv = ["inodefence", "explore", "--target", "python-tarfile", "--version", "3.12.16",
            "--budget", "2500", "--auto-prepare", "--extraction-filter", "data",
            "--out", "/a folder/with space"]  # fmt: skip
    text = wrapped_command(argv, 40)
    lines = text.splitlines()
    assert len(lines) > 1 and all(line.endswith(" \\") for line in lines[:-1])
    assert all(line.startswith("  ") for line in lines[1:])
    assert all(not line.strip().startswith(("3.12.16", "2500", "data")) for line in lines)
    assert _shlex.split(text.replace("\\\n", " ")) == argv  # pastes back to the same command


def test_required_and_common_fields_come_before_more_options() -> None:
    from inodefence.ui.tui.forms import command_forms
    from inodefence.ui.tui.screens_run import ordered_fields

    main, more = ordered_fields(command_forms()["explore"])
    assert [f.dest for f in main][:5] == ["version", "target", "budget", "seed", "auto_prepare"]
    assert {"profile", "dry_run", "verbose", "quiet"} <= {f.dest for f in more}

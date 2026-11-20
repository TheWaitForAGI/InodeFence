"""Starting ``inodefence`` from the TUI: exactly the typed command, detached, exit code recorded.

Every test uses the fake ``inodefence`` (``tests/tui_fake_cli.py``); nothing real runs.
"""

from __future__ import annotations

import ast
import json
import os
import time
from pathlib import Path

import pytest
from tests import tui_fake_cli

from inodefence.app.runs import RunOutcome
from inodefence.ui.tui import launch

SRC = Path(launch.__file__).resolve().parents[2]  # .../src/inodefence


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    program = tui_fake_cli.install(tmp_path / "bin")
    argv_log = tmp_path / "argv.jsonl"
    monkeypatch.setenv("FAKE_ARGV_LOG", str(argv_log))
    return {"program": program, "argv_log": argv_log, "records": tmp_path / "launches"}


def _start(fake: dict[str, Path], argv: list[str], cwd: Path) -> launch.Launch:
    return launch.start(argv, cwd=cwd, root=fake["records"], executable=fake["program"])


def test_the_command_runs_exactly_as_typed_and_its_code_is_recorded(
    fake: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_EXIT", "1")
    argv = ["inodefence", "explore", "--target", "node-tar", "--version", "7.5.2", "--auto-prepare"]
    started = _start(fake, argv, tmp_path)
    done = launch.wait(started, timeout=20)
    assert done.exit_code == 1 and done.ended and done.ended_at
    assert done.outcome() is RunOutcome.FAIL  # a judged violation, not an error
    (seen,) = [json.loads(line) for line in fake["argv_log"].read_text().splitlines()]
    assert seen == argv[1:]
    assert done.argv == tuple(argv) and done.cwd == str(tmp_path)
    assert "fake inodefence explore --target node-tar" in "\n".join(launch.output_tail(done))


@pytest.mark.parametrize(
    ("command", "code", "outcome"),
    [("verify", 0, RunOutcome.PASS), ("verify", 2, RunOutcome.ERROR),
     ("explore", 3, RunOutcome.REFUSED), ("replay", 1, RunOutcome.INCOMPLETE),
     ("replay", 4, RunOutcome.UNSUPPORTED), ("status", 0, RunOutcome.UNKNOWN)],
)  # fmt: skip
def test_each_exit_code_keeps_the_clis_meaning(
    fake: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    command: str, code: int, outcome: RunOutcome,
) -> None:  # fmt: skip
    monkeypatch.setenv("FAKE_EXIT", str(code))
    monkeypatch.setenv("FAKE_STDERR", "error: a refusal reason from the CLI")
    done = launch.wait(_start(fake, ["inodefence", command], tmp_path), timeout=20)
    assert done.exit_code == code and done.outcome() is outcome
    assert "a refusal reason from the CLI" in "\n".join(launch.output_tail(done))


def test_the_command_runs_in_a_session_of_its_own(
    fake: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SLEEP", "1.5")
    monkeypatch.setenv("FAKE_EXIT", "0")
    started = _start(fake, ["inodefence", "verify"], tmp_path)
    deadline = time.monotonic() + 10
    while launch.read_launch(started.folder).pid is None and time.monotonic() < deadline:
        time.sleep(0.05)
    running = launch.read_launch(started.folder)
    assert running.pid is not None and running.exit_code is None
    assert os.getsid(running.pid) != os.getsid(0)  # its own session: no hang-up from ours
    done = launch.wait(started, timeout=20)
    assert done.exit_code == 0


def test_only_inodefence_commands_are_started(fake: dict[str, Path], tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _start(fake, ["rm", "-rf", "/"], tmp_path)
    assert not fake["records"].exists() or not any(fake["records"].iterdir())


def test_records_are_listed_newest_first_and_a_broken_one_says_so(
    fake: dict[str, Path], tmp_path: Path
) -> None:
    first = launch.wait(_start(fake, ["inodefence", "doctor"], tmp_path), timeout=20)
    time.sleep(1.1)  # record folders are named by the UTC second
    second = launch.wait(_start(fake, ["inodefence", "targets"], tmp_path), timeout=20)
    listed = launch.list_launches(fake["records"])
    assert [x.folder for x in listed] == [second.folder, first.folder]
    (first.folder / launch.RECORD_FILE).write_text("{not json", encoding="utf-8")
    broken = launch.read_launch(first.folder)
    assert broken.error and broken.exit_code is None


def test_the_record_root_follows_xdg_state_home(tmp_path: Path) -> None:
    assert launch.records_root({"XDG_STATE_HOME": str(tmp_path)}) == (
        tmp_path / "inodefence" / "launches"
    )
    assert launch.records_root({"HOME": str(tmp_path)}) == (
        tmp_path / ".local/state" / "inodefence" / "launches"
    )


def test_a_missing_cli_is_the_tuis_own_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launch.sys, "executable", "/nonexistent/python")
    with pytest.raises(launch.CommandNotFound):
        launch.find_cli({"PATH": "/nonexistent"})


def _starts_processes(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == "subprocess" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            return True
        if isinstance(node, ast.Attribute) and node.attr in {"Popen", "system", "execv", "spawnv"}:
            return True
    return False


def test_only_the_launch_module_starts_processes() -> None:
    # The read model starts nothing; under ui/ only tui/launch.py (and its wrapper) does.
    starters = {
        str(p.relative_to(SRC))
        for p in [*(SRC / "ui").rglob("*.py"), *(SRC / "app" / n for n in (
            "runs.py", "events.py", "targets.py"))]
        if _starts_processes(p)
    }  # fmt: skip
    assert starters == {"ui/tui/launch.py", "ui/tui/launch_wrapper.py"}


def test_a_plan_is_the_same_command_with_dry_run(
    fake: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_EXIT", "0")
    argv = ["inodefence", "verify", "--version", "7.5.2"]
    code, output = launch.run_plan(argv, cwd=tmp_path, executable=fake["program"])
    assert code == 0 and "fake inodefence verify --version 7.5.2 --dry-run" in output
    (seen,) = [json.loads(line) for line in fake["argv_log"].read_text().splitlines()]
    assert seen == [*argv[1:], "--dry-run"]
    launch.run_plan([*argv, "--dry-run"], cwd=tmp_path, executable=fake["program"])
    last = json.loads(fake["argv_log"].read_text().splitlines()[-1])
    assert last.count("--dry-run") == 1  # never added twice


def test_a_plan_that_does_not_finish_in_time_says_so(
    fake: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SLEEP", "3")
    code, output = launch.run_plan(
        ["inodefence", "explore", "--version", "latest"],
        cwd=tmp_path, executable=fake["program"], timeout=0.5,
    )  # fmt: skip
    assert code is None and "no plan after" in output


def test_only_commands_that_run_nothing_are_waited_for(
    fake: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_EXIT", "2")
    code, output = launch.run_waited(
        ["inodefence", "status", str(tmp_path)], cwd=tmp_path, executable=fake["program"]
    )
    assert code == 2 and "fake inodefence status" in output
    for argv in (["inodefence", "explore", "--version", "latest"], ["inodefence", "replay", "x"]):
        with pytest.raises(ValueError):
            launch.run_waited(argv, cwd=tmp_path, executable=fake["program"])


def test_the_state_says_running_ended_or_the_code_and_its_meaning(
    fake: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SLEEP", "1.5")
    monkeypatch.setenv("FAKE_EXIT", "1")
    started = _start(fake, ["inodefence", "explore", "--version", "latest"], tmp_path)
    deadline = time.monotonic() + 10
    while launch.read_launch(started.folder).pid is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert launch.state_text(launch.read_launch(started.folder)) == "running"
    done = launch.wait(started, timeout=20)
    assert launch.state_text(done) == "exit 1 · FAIL (a violation was judged)"
    gone = launch.Launch(done.folder, done.argv, done.cwd, done.started_at, None, None, 2**22 + 7)
    assert launch.state_text(gone) == "ended (no exit code recorded)"

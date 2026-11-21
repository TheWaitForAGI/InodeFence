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


#: Every standard way to start a process (QA: os.exec*, os.spawn*, posix_spawn, asyncio
#: subprocesses and pty were missed): modules, and names that start a process wherever they live.
_PROCESS_MODULES = {"subprocess", "pty", "multiprocessing"}
_PROCESS_NAMES = {"Popen", "system", "popen", "fork", "forkpty", "posix_spawn", "posix_spawnp",
                  "create_subprocess_exec", "create_subprocess_shell", "startfile"}  # fmt: skip


def _starts_process_name(name: str) -> bool:
    return name in _PROCESS_NAMES or name.startswith(("exec", "spawn"))


def _starts_processes(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            a.name.split(".")[0] in _PROCESS_MODULES for a in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in _PROCESS_MODULES:
                return True
            if node.module in ("os", "asyncio") and any(
                _starts_process_name(a.name) for a in node.names
            ):
                return True
        if isinstance(node, ast.Attribute) and _starts_process_name(node.attr):
            base = node.value
            if isinstance(base, ast.Name) and base.id in ("os", "asyncio", "pty", "subprocess"):
                return True
            if node.attr in _PROCESS_NAMES - {"system", "popen"}:  # Popen, fork, ... anywhere
                return True
    return False


def test_only_the_launch_module_starts_processes() -> None:
    # The read model starts nothing; under ui/ only tui/launch.py (and its wrapper) does; in app/
    # only doctor.py does (its read-only Docker queries, from before the TUI ran anything).
    starters = {
        str(p.relative_to(SRC))
        for p in [*(SRC / "ui").rglob("*.py"), *(SRC / "app").glob("*.py")]
        if _starts_processes(p)
    }
    assert starters == {"ui/tui/launch.py", "ui/tui/launch_wrapper.py", "app/doctor.py"}


@pytest.mark.parametrize(
    "code",
    ["import os\nos.execv('/bin/true', [])", "import os\nos.spawnv(0, 'x', [])",
     "import os\nos.posix_spawn('x', [], {})", "from os import execvp",
     "import asyncio\nasyncio.create_subprocess_exec('x')", "import pty\npty.spawn('x')",
     "from asyncio import create_subprocess_shell", "import subprocess", "import os\nos.fork()",
     "import os\nos.system('x')", "import os\nos.popen('x')"],
)  # fmt: skip
def test_the_boundary_check_sees_every_way_to_start_a_process(tmp_path: Path, code: str) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(code + "\n", encoding="utf-8")
    assert _starts_processes(probe)


def test_the_boundary_check_does_not_flag_reading(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text("import os\nos.stat('.')\nos.kill\nre = __import__('re')\n", encoding="utf-8")
    assert not _starts_processes(probe)


def test_a_plan_is_the_same_command_with_dry_run(
    fake: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_EXIT", "0")
    argv = ["inodefence", "verify", "--version", "7.5.2"]
    code, output = launch.run_plan(argv, cwd=tmp_path, executable=fake["program"])
    assert code == 0 and "fake inodefence verify --dry-run --version 7.5.2" in output
    (seen,) = [json.loads(line) for line in fake["argv_log"].read_text().splitlines()]
    assert seen == ["verify", "--dry-run", "--version", "7.5.2"]  # before any positional
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


def test_a_plan_is_a_dry_run_whatever_the_case_folder_is_called(
    fake: dict[str, Path], tmp_path: Path
) -> None:
    # QA: a replay case folder named "--" turned an appended --dry-run into a positional
    from inodefence.cli import build_parser
    from inodefence.ui.tui.forms import command_forms, command_line

    for folder in ("--", "-x", "--dry-run", "run-000001"):
        argv = command_line(command_forms()["replay"], {"case_dir": folder, "rounds": "5"})
        args, _ = build_parser().parse_known_args(argv[1:])
        assert args.case_dir == Path(folder) and args.dry_run is False  # typed as given
        launch.run_plan(argv, cwd=tmp_path, executable=fake["program"])
        planned = json.loads(fake["argv_log"].read_text().splitlines()[-1])
        args, _ = build_parser().parse_known_args(planned)
        assert args.dry_run is True and args.case_dir == Path(folder)
    with pytest.raises(ValueError):  # "--dry-run" as a value is not a plan
        launch.run_waited(["inodefence", "replay", "--", "--dry-run"], cwd=tmp_path,
                          executable=fake["program"])  # fmt: skip


def test_records_are_readable_by_their_owner_only(fake: dict[str, Path], tmp_path: Path) -> None:
    import stat

    done = launch.wait(_start(fake, ["inodefence", "doctor"], tmp_path), timeout=20)
    for path, mode in ((fake["records"], 0o700), (done.folder, 0o700),
                       (done.folder / launch.RECORD_FILE, 0o600),
                       (done.folder / launch.OUTPUT_FILE, 0o600)):  # fmt: skip
        assert stat.S_IMODE(path.stat().st_mode) == mode, path


def test_ended_launches_are_reaped_so_no_zombie_stays(
    fake: dict[str, Path], tmp_path: Path
) -> None:
    started = [_start(fake, ["inodefence", "doctor"], tmp_path) for _ in range(3)]
    for item in started:
        launch.wait(item, timeout=20)
    deadline = time.monotonic() + 10
    while launch._STARTED and time.monotonic() < deadline:
        launch.reap()
        time.sleep(0.05)
    assert launch._STARTED == []
    for item in started:  # each wrapper's exit was collected: nothing left to wait for
        with pytest.raises(ChildProcessError):
            os.waitpid(item.pid or -1, os.WNOHANG)

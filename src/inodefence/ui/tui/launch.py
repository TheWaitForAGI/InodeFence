"""Start an ``inodefence`` command from the TUI, detached, and read back what it did.

This is the only module under ``inodefence.ui`` that starts a process (``tests/test_tui_launch.py``
pins it); the read model (``inodefence.app.runs`` / ``events`` / ``targets``) starts nothing. The
command is the CLI exactly as a person would type it (:func:`inodefence.ui.tui.forms.command_line`):
same argument checks, same exit codes, same ``result.json``. Nothing here stops a run or deletes
anything -- the CLI has no such command, so the TUI has none.

A launch runs ``python -m inodefence.ui.tui.launch_wrapper <record> -- inodefence ...`` in a new
session (``start_new_session``): closing the TUI does not stop it, exactly as a command started in
another terminal keeps running. Its output goes to ``<record>/output.log`` and the wrapper writes
``<record>/launch.json`` with the exit code when the command ends, so the code survives the TUI
being closed. Records live under ``$XDG_STATE_HOME/inodefence/launches/`` (default
``~/.local/state``), never in a result folder, and are never cleaned up here (decided 2026-11-20).
The run itself is found the way every run is -- by scanning its output folder -- so a run started
here is not treated differently from one started in a terminal.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inodefence.app.runs import RunOutcome, outcome_from_exit_code

SCHEMA = "inodefence-tui-launch-v1"
RECORD_FILE = "launch.json"
OUTPUT_FILE = "output.log"
CLI_NAME = "inodefence"


class CommandNotFound(RuntimeError):
    """The ``inodefence`` command could not be found (the TUI's own failure, nothing started)."""


def records_root(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    base = env.get("XDG_STATE_HOME") or str(
        Path(env.get("HOME", "~")).expanduser() / ".local/state"
    )
    return Path(base).expanduser() / "inodefence" / "launches"


def find_cli(environ: Mapping[str, str] | None = None) -> Path:
    """The ``inodefence`` this TUI belongs to: beside its own Python first, else on ``PATH``."""
    sibling = Path(sys.executable).parent / CLI_NAME
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return sibling
    env = os.environ if environ is None else environ
    found = shutil.which(CLI_NAME, path=env.get("PATH"))
    if found is None:
        raise CommandNotFound(f"`{CLI_NAME}` was not found beside {sys.executable} or on PATH")
    return Path(found)


@dataclass(frozen=True, slots=True)
class Launch:
    """One command started from the TUI, as its record says."""

    folder: Path
    argv: tuple[str, ...]
    cwd: str
    started_at: str | None
    ended_at: str | None
    exit_code: int | None
    #: the wrapper's process id (alive while the command runs)
    pid: int | None
    error: str | None = None

    @property
    def ended(self) -> bool:
        return self.exit_code is not None

    @property
    def command(self) -> str | None:
        """The sub-command (``explore``), or ``None``."""
        return self.argv[1] if len(self.argv) > 1 else None

    def outcome(self) -> RunOutcome | None:
        """What the exit code means for this command (the CLI's documented meaning), or ``None``
        while it runs. ``FAIL`` is a judged violation, not an error."""
        if self.exit_code is None or self.command is None:
            return None
        return outcome_from_exit_code(self.command, self.exit_code)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


#: Records hold command lines, paths and output: readable by their owner only.
FOLDER_MODE, FILE_MODE = 0o700, 0o600


def _private_file(path: Path) -> int:
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)


def write_record(folder: Path, record: Mapping[str, Any]) -> None:
    """Replace ``launch.json`` in one step (a reader never sees half a file); owner-only."""
    tmp = folder / f".{RECORD_FILE}.{os.getpid()}.tmp"
    text = json.dumps(dict(record), indent=2, sort_keys=True) + "\n"
    with os.fdopen(_private_file(tmp), "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, folder / RECORD_FILE)


#: Launches started by this process whose exit has not been collected yet (no zombies are left
#: while the TUI stays open: :func:`reap` collects the finished ones on every refresh).
_STARTED: list[subprocess.Popen[bytes]] = []


def reap() -> int:
    """Collect the exit of every finished launch this process started; returns how many."""
    finished = [process for process in _STARTED if process.poll() is not None]
    for process in finished:
        _STARTED.remove(process)
    return len(finished)


def start(
    argv: Sequence[str],
    *,
    cwd: Path,
    root: Path | None = None,
    executable: Path | None = None,
) -> Launch:
    """Start ``argv`` (``["inodefence", <command>, ...]``) detached; returns at once.

    ``executable`` replaces the ``inodefence`` found by :func:`find_cli` (tests use a fake one).
    """
    if not argv or argv[0] != CLI_NAME:
        raise ValueError(f"only `{CLI_NAME} ...` commands are started, got {list(argv)!r}")
    program = executable if executable is not None else find_cli()
    reap()
    base = root or records_root()
    base.mkdir(parents=True, exist_ok=True, mode=FOLDER_MODE)
    base.chmod(FOLDER_MODE)
    folder = base / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    folder.mkdir(mode=FOLDER_MODE, exist_ok=False)
    record = {"schema": SCHEMA, "argv": list(argv), "program": str(program), "cwd": str(cwd),
              "started_at": _now(), "ended_at": None, "exit_code": None, "pid": None}  # fmt: skip
    write_record(folder, record)
    with os.fdopen(_private_file(folder / OUTPUT_FILE), "wb") as output:
        process = subprocess.Popen(  # noqa: S603 -- argv is the CLI's own, built from its parser
            [sys.executable, "-m", "inodefence.ui.tui.launch_wrapper", str(folder), "--",
             str(program), *argv[1:]],
            cwd=cwd, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True,
        )  # fmt: skip
    _STARTED.append(process)
    return Launch(folder, tuple(argv), str(cwd), record["started_at"], None, None, process.pid)


def read_launch(folder: Path) -> Launch:
    """A record as stored; a missing or broken one says so in ``error`` (never raises)."""
    try:
        data = json.loads((folder / RECORD_FILE).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise ValueError("not a launch record")
    except (OSError, ValueError) as error:
        return Launch(folder, (), "", None, None, None, None, error=str(error))
    argv = data.get("argv")
    code, pid = data.get("exit_code"), data.get("pid")
    return Launch(
        folder=folder,
        argv=tuple(str(a) for a in argv) if isinstance(argv, list) else (),
        cwd=str(data.get("cwd") or ""),
        started_at=data.get("started_at") if isinstance(data.get("started_at"), str) else None,
        ended_at=data.get("ended_at") if isinstance(data.get("ended_at"), str) else None,
        exit_code=code if isinstance(code, int) and not isinstance(code, bool) else None,
        pid=pid if isinstance(pid, int) and not isinstance(pid, bool) else None,
        error=data.get("error") if isinstance(data.get("error"), str) else None,
    )


def list_launches(root: Path | None = None, limit: int = 50) -> list[Launch]:
    """The newest ``limit`` records, newest first (folder names start with the UTC start time)."""
    reap()
    base = root or records_root()
    try:
        folders = sorted((p for p in base.iterdir() if p.is_dir()), reverse=True)
    except OSError:
        return []
    return [read_launch(p) for p in folders[:limit]]


def output_tail(launch: Launch, lines: int = 20) -> list[str]:
    """The last ``lines`` lines of the command's output (what it printed, unchanged)."""
    try:
        with open(launch.folder / OUTPUT_FILE, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(size - 64 * 1024, 0))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[-lines:]


def wait(launch: Launch, timeout: float, poll: float = 0.05) -> Launch:
    """Read the record until it has an exit code or ``timeout`` passes (for tests and scripts)."""
    deadline = time.monotonic() + timeout
    current = read_launch(launch.folder)
    while current.exit_code is None and time.monotonic() < deadline:
        time.sleep(poll)
        current = read_launch(launch.folder)
    return current


#: How long the confirmation dialog waits for a ``--dry-run`` plan (it runs nothing).
PLAN_TIMEOUT_SECONDS = 60.0


#: Commands that run nothing and are waited for in the TUI (their output is shown as printed).
WAITED_COMMANDS = frozenset({"doctor", "targets", "status", "summary", "compare"})


def is_dry_run(argv: Sequence[str]) -> bool:
    """Whether the CLI's own parser reads ``argv`` as a ``--dry-run`` (never a string search)."""
    from inodefence.cli import build_parser

    try:
        args, _ = build_parser().parse_known_args(list(argv[1:]))
    except SystemExit:  # the parser refused it: not a plan
        return False
    return getattr(args, "dry_run", False) is True


def run_waited(
    argv: Sequence[str],
    *,
    cwd: Path,
    executable: Path | None = None,
    timeout: float = PLAN_TIMEOUT_SECONDS,
) -> tuple[int | None, str]:
    """Run ``argv`` and wait for it: ``(exit code, what it printed)``; ``None`` as the code when it
    did not finish in ``timeout``. Only for commands that start no extractor: a ``--dry-run`` plan
    (:func:`run_plan`) or one of :data:`WAITED_COMMANDS`."""
    if not argv or argv[0] != CLI_NAME:
        raise ValueError(f"only `{CLI_NAME} ...` commands are run, got {list(argv)!r}")
    if not is_dry_run(argv) and (len(argv) < 2 or argv[1] not in WAITED_COMMANDS):
        raise ValueError(f"{list(argv)!r} may start Docker: it is started detached, not waited for")
    program = executable if executable is not None else find_cli()
    try:
        done = subprocess.run(  # noqa: S603 -- the CLI's own command
            [str(program), *argv[1:]], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=timeout, check=False,
        )  # fmt: skip
    except subprocess.TimeoutExpired as error:
        raw = error.stdout  # text=True gives str, but the exception's type allows bytes too
        out = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw or "")
        return None, out + f"\n(no answer after {timeout:.0f} s)"
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def run_plan(
    argv: Sequence[str],
    *,
    cwd: Path,
    executable: Path | None = None,
    timeout: float = PLAN_TIMEOUT_SECONDS,
) -> tuple[int | None, str]:
    """The same command with ``--dry-run`` (added if absent), waited for: ``(exit code, output)``.

    For the confirmation dialog of a command that has ``--dry-run`` (verify, explore, replay):
    the CLI prints its plan and runs nothing. ``None`` as the code when it did not finish in time.
    """
    if not argv or argv[0] != CLI_NAME:
        raise ValueError(f"only `{CLI_NAME} ...` commands are planned, got {list(argv)!r}")
    # right after the sub-command: before any positional and before a "--" (QA: a case folder
    # named "--" turned an appended --dry-run into a positional)
    planned = list(argv) if is_dry_run(argv) else [*argv[:2], "--dry-run", *argv[2:]]
    code, output = run_waited(planned, cwd=cwd, executable=executable, timeout=timeout)
    if code is None:
        output = output.replace("(no answer after", "(no plan after")
    return code, output


#: What an exit code says, by the CLI's documented outcome (``RunOutcome``); FAIL is a verdict.
OUTCOME_TEXT = {
    RunOutcome.PASS: "PASS",
    RunOutcome.FAIL: "FAIL (a violation was judged)",
    RunOutcome.ERROR: "ERROR (no verdict)",
    RunOutcome.REFUSED: "refused before anything ran",
    RunOutcome.COMPLETE: "every round ran",
    RunOutcome.INCOMPLETE: "not every round ran",
    RunOutcome.UNSUPPORTED: "unsupported",
}


def alive(pid: int | None) -> bool:
    """Whether a process with this id exists (signal 0 asks without sending anything)."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def state_text(record: Launch) -> str:
    """``running``, the exit code with its meaning, or ``ended (no exit code recorded)``."""
    if record.error and not record.argv:
        return f"record not readable ({record.error})"
    if record.exit_code is None:
        return "running" if alive(record.pid) else "ended (no exit code recorded)"
    outcome = record.outcome()
    meaning = OUTCOME_TEXT.get(outcome) if outcome is not None else None
    return f"exit {record.exit_code}" + (f" · {meaning}" if meaning else "")

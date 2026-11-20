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


def write_record(folder: Path, record: Mapping[str, Any]) -> None:
    """Replace ``launch.json`` in one step (a reader never sees half a file)."""
    tmp = folder / f".{RECORD_FILE}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(dict(record), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, folder / RECORD_FILE)


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
    folder = (root or records_root()) / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    folder.mkdir(parents=True, exist_ok=False)
    record = {"schema": SCHEMA, "argv": list(argv), "program": str(program), "cwd": str(cwd),
              "started_at": _now(), "ended_at": None, "exit_code": None, "pid": None}  # fmt: skip
    write_record(folder, record)
    with open(folder / OUTPUT_FILE, "wb") as output:
        process = subprocess.Popen(  # noqa: S603 -- argv is the CLI's own, built from its parser
            [sys.executable, "-m", "inodefence.ui.tui.launch_wrapper", str(folder), "--",
             str(program), *argv[1:]],
            cwd=cwd, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True,
        )  # fmt: skip
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

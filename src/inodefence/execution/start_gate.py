"""Fail-closed, cross-process start gate for concurrent campaign launchers.

A launcher that runs cells concurrently must not start a new cell once any
cell's cleanup has concluded that its Docker resources are in an UNKNOWN state.
The child learns this inside its own cleanup, before the launcher thread that
waits for it returns, so the decision has to cross the process boundary. The
benchmark driver (``scripts/run_concurrency_benchmark.py``) and the registered
launcher (``scripts/run_exp0.py --jobs``) are meant to share this one gate.

Protocol (all files under one state directory, POSIX ``flock``; every lock
acquisition opens a fresh file description, so threads exclude each other too):

* ``gate.lock`` serializes "check every cell + Popen" (launcher) against
  "commit a verdict" (child or launcher). The atomic rename of a verdict under
  this lock is the linearization point: a verdict committed under the lock is
  seen by every later check, and a start admitted under the lock happened
  before it.
* ``<cell>.lock`` is a lifetime lock. The launcher locks a fresh open file
  description and hands it to the child with ``pass_fds``, then closes its own
  copy. The lock is released only when the child *and every descendant that
  inherited the descriptor* has exited or closed it. "Held" therefore means
  "maybe still running", never "clean".
* ``<cell>.verdict``: ``C`` when the child's cleanup starts (outcome pending),
  then ``S`` (cleanup verified) or ``U <reason>`` (resource state unknown).
  ``U`` is final. ``W`` (pending, like ``C``) is written by the launcher just
  before it terminates a cell on its watchdog; only the child's own cleanup can
  turn it into ``S``. The launcher never writes ``S``. It writes ``U`` when a
  reaped cell left no ``S`` (including a watchdog cell killed before its trap
  verified cleanup).
* ``<cell>.cleanup`` is created by the child with ``O_EXCL`` and no lock as the
  first act of its cleanup, before it records ``C``. The scan treats it as ``C``
  (pending). It narrows the window in which both lock-based records fail: an
  unlocked create still linearizes, since a scan that did not see it ran before it.
* ``<cell>.watchdog`` marks a cell the watchdog terminated. It survives verdict
  changes, so every denial caused by that cell names the watchdog and callers
  can classify it the same way whichever thread sees it first.
* ``<cell>.session`` names the launcher session that started the cell.

Before a start the launcher waits, holding no lock, while any live cell is in
``C`` or ``W`` (at most ``cleanup_wait_seconds``; past it the start is denied). Under the
gate lock it then denies the start when any registered cell has ``U``, has no
final verdict while its lifetime lock is free (it exited without verifying its
cleanup), has no final verdict and belongs to another launcher session (that
launcher ended abnormally), or when the state cannot be read or locked in time.
Only ``S`` counts as clean, so a lost notification path also stops new starts.

A denial persists on disk across launcher invocations. ``start_gate.py ack``
moves one cell's records aside after a person has checked its resources.

Scope: one gate per state directory. Two launchers with different state
directories on the same Docker host do not see each other.

The module uses only the standard library and also runs as a script, so the
smoke script records verdicts without importing the package::

    python start_gate.py record C
    python start_gate.py record U "controller ownership: ..."
    python start_gate.py record S
    python start_gate.py ack DIRECTORY CELL "who checked what"
"""

from __future__ import annotations

import fcntl
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GATE_DIR_ENV = "INODEFENCE_START_GATE_DIR"
GATE_CELL_ENV = "INODEFENCE_START_GATE_CELL"
GATE_LOCK = "gate.lock"
ACKNOWLEDGED = "acknowledged"
CLEANUP = "C"
WATCHDOG = "W"
CLEAN = "S"
UNKNOWN = "U"
PENDING = (CLEANUP, WATCHDOG)
#: Appended to every denial caused by a watchdog-terminated cell.
WATCHDOG_TAG = "(after watchdog)"
_CELL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")
#: Longest wait for ``gate.lock``. Its holders only scan small files, rename one
#: or call Popen, so reaching this means a holder is stuck; the caller then fails
#: closed (the launcher denies the start; the child leaves no final verdict).
LOCK_SECONDS = 60.0
#: Upper bound on one cleanup, from the client deadlines in
#: scripts/local_node_tar_smoke.sh: controller inspect 30 + two evidence files
#: x (exec 30 + cp 300) + rm 60 + inspect 30 + volume inspect 30 + rm 60 +
#: inspect 30 = 900 s, plus a 5 s kill grace for each of the 11 calls and margin.
CLEANUP_WAIT_SECONDS = 1000.0
POLL_SECONDS = 0.05
# Bound at import: the self-test must spawn a real process even when a caller
# (or a test) replaces subprocess.Popen to fake cell launches.
_REAL_POPEN = subprocess.Popen


class StartDenied(RuntimeError):
    """The gate refused a start. The message is the first reason found."""


class CleanupPending(RuntimeError):
    """A live cell is inside cleanup; wait (holding no lock) and try again."""

    def __init__(self, cells: list[str], deadline: float) -> None:
        super().__init__(", ".join(cells))
        self.deadline = deadline


class VerdictMissing(RuntimeError):
    """A finished cell did not leave a clean-cleanup verdict."""


def _check_cell(cell: str) -> str:
    if not _CELL.match(cell):
        raise ValueError(f"invalid gate cell name: {cell!r}")
    return cell


@contextmanager
def _locked(path: Path, seconds: float = LOCK_SECONDS) -> Iterator[None]:
    """Exclusive ``flock`` on a fresh file description, waiting at most ``seconds``."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    try:
        end = time.monotonic() + seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= end:
                    raise TimeoutError(f"{path.name} not acquired in {seconds:g}s") from None
                time.sleep(POLL_SECONDS)
        yield
    finally:
        os.close(fd)


def _write_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _read_verdict(path: Path) -> tuple[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    kind, _, reason = text.rstrip("\n").partition(" ")
    if kind not in (CLEANUP, WATCHDOG, CLEAN, UNKNOWN) or (kind != UNKNOWN and reason):
        raise ValueError(f"unreadable verdict {path.name}: {text[:80]!r}")
    return kind, reason


def _lock_is_free(path: Path) -> bool:
    """True when nobody holds ``path``. The probe releases at once."""
    fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True
    finally:
        os.close(fd)


def _commit_locked(path: Path, cell: str, verdict: str, reason: str) -> None:
    line = verdict if verdict != UNKNOWN else f"{UNKNOWN} {' '.join(reason.split()) or 'unknown'}"
    current = _read_verdict(path)
    if current is not None and current[0] == UNKNOWN:
        if verdict != UNKNOWN:
            raise RuntimeError(f"{cell}: UNKNOWN verdict is final")
        return
    if current is not None and current[0] == CLEAN and verdict != UNKNOWN:
        if verdict == CLEANUP:
            raise RuntimeError(f"{cell}: cleanup was already verified")
        return  # S stays S; a late watchdog mark changes nothing
    if current is not None and current[0] == WATCHDOG and verdict == CLEANUP:
        return  # the trap entering cleanup after SIGTERM: still pending as W
    _write_atomic(path, line + "\n")


def record_verdict(
    directory: Path,
    cell: str,
    verdict: str,
    reason: str = "",
    *,
    lock_seconds: float = LOCK_SECONDS,
) -> None:
    """Commit ``C``, ``S`` or ``U <reason>`` for ``cell`` under the gate lock.

    ``U`` is final: a later ``C`` or ``S`` is refused and a second ``U`` keeps
    the first reason. After ``S`` only ``U`` may still be recorded.
    """
    _check_cell(cell)
    if verdict not in (CLEANUP, CLEAN, UNKNOWN):
        # W is launcher-only (StartGate.mark_watchdog).
        raise ValueError(f"verdict must be {CLEANUP}, {CLEAN} or {UNKNOWN}: {verdict!r}")
    with _locked(Path(directory) / GATE_LOCK, lock_seconds):
        _commit_locked(Path(directory) / f"{cell}.verdict", cell, verdict, reason)


def self_test(directory: Path) -> None:
    """Refuse a filesystem whose ``flock`` does not behave as this gate needs.

    Checks that two file descriptions of one file conflict, and that a lock
    passed to a child outlives the parent's copy and ends with the child. NFS
    and WSL drvfs/9p mounts can fail either; the gate must not run there.
    """
    probe = Path(directory) / ".self-test.lock"
    fd = os.open(probe, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    child: subprocess.Popen[bytes] | None = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if _lock_is_free(probe):
            raise OSError("flock does not exclude a second file description")
        child = _REAL_POPEN(
            [sys.executable, "-I", "-c", "import sys; sys.stdin.read()"],
            stdin=subprocess.PIPE,
            pass_fds=(fd,),
        )
        os.close(fd)
        fd = -1
        if _lock_is_free(probe):
            raise OSError("flock was not inherited by a child process")
        assert child.stdin is not None
        child.stdin.close()
        child.wait(timeout=30)
        if not _lock_is_free(probe):
            raise OSError("flock outlived the child that held it")
    finally:
        if fd >= 0:
            os.close(fd)
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
        probe.unlink(missing_ok=True)


class StartGate:
    """Launcher side of the gate. One instance per launcher invocation.

    ``popen(cell)`` returns a ``subprocess.Popen``-compatible callable for that
    cell; it raises :class:`StartDenied` instead of starting when the gate is
    closed. After the cell's child has been reaped, call :meth:`require_clean`.
    Before terminating a cell on a watchdog, call :meth:`mark_unknown`.
    """

    def __init__(
        self,
        directory: Path,
        *,
        session: str | None = None,
        cleanup_wait_seconds: float = CLEANUP_WAIT_SECONDS,
        lock_seconds: float = LOCK_SECONDS,
        check_filesystem: bool = True,
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        if check_filesystem:
            self_test(self.directory)
        self.session = session or secrets.token_hex(8)
        self.cleanup_wait_seconds = cleanup_wait_seconds
        self.lock_seconds = lock_seconds
        #: Seconds each admitted start spent waiting on other cells' cleanup.
        self.waits: list[float] = []
        self._waits_lock = threading.Lock()

    def _cells(self) -> list[str]:
        return sorted(p.name[: -len(".session")] for p in self.directory.glob("*.session"))

    def _tag(self, cell: str) -> str:
        return f" {WATCHDOG_TAG}" if (self.directory / f"{cell}.watchdog").exists() else ""

    def _scan_locked(self) -> tuple[str | None, list[str]]:
        """(first denial reason, live cells with a pending outcome). Caller holds the lock."""
        pending: list[str] = []
        for cell in self._cells():
            verdict = _read_verdict(self.directory / f"{cell}.verdict")
            tag = self._tag(cell)
            if verdict is not None and verdict[0] == UNKNOWN:
                return f"{cell} cleanup resource state unknown: {verdict[1]}{tag}", []
            if verdict is not None and verdict[0] == CLEAN:
                continue
            owner = (self.directory / f"{cell}.session").read_text(encoding="utf-8").strip()
            if owner != self.session:
                return f"{cell} has no cleanup verdict from launcher session {owner}{tag}", []
            if _lock_is_free(self.directory / f"{cell}.lock"):
                return f"{cell} exited without a cleanup verdict{tag}", []
            if verdict is not None or (self.directory / f"{cell}.cleanup").exists():
                pending.append(cell)
        return None, pending

    def problem(self) -> str | None:
        """The reason a start would be denied now, or ``None``."""
        try:
            with _locked(self.directory / GATE_LOCK, self.lock_seconds):
                return self._scan_locked()[0]
        except Exception as error:
            return f"start gate state unreadable: {type(error).__name__}: {error}"

    def wait_for_cleanups(self, deadline: float) -> None:
        """Wait, holding no lock, until no live cell is inside cleanup.

        ``deadline`` is a ``time.monotonic()`` value. Waiting only delays a
        start; the decision is taken under the gate lock afterwards.
        """
        while time.monotonic() < deadline:
            try:
                with _locked(self.directory / GATE_LOCK, self.lock_seconds):
                    problem, pending = self._scan_locked()
            except Exception:
                return  # the start itself reports the failure under the lock
            if problem is not None or not pending:
                return
            time.sleep(POLL_SECONDS)

    def try_start(
        self,
        cell: str,
        popen: Callable[..., Any],
        args: Any,
        kwargs: Mapping[str, Any],
        *,
        deadline: float | None = None,
    ) -> Any:
        """Check the gate and start ``cell`` as one critical section.

        Raises :class:`CleanupPending` while a live cell is inside cleanup and
        ``deadline`` (``time.monotonic()``) has not passed; past it, or with no
        deadline, a pending cleanup denies the start.
        """
        _check_cell(cell)
        try:
            gate = _locked(self.directory / GATE_LOCK, self.lock_seconds)
            gate.__enter__()
        except Exception as error:
            raise StartDenied(f"start gate lock failed: {type(error).__name__}: {error}") from error
        try:
            try:
                problem, pending = self._scan_locked()
            except Exception as error:
                problem = f"start gate state unreadable: {type(error).__name__}: {error}"
                pending = []
            if problem is not None:
                raise StartDenied(problem)
            if pending:
                if deadline is not None and time.monotonic() < deadline:
                    raise CleanupPending(pending, deadline)
                raise StartDenied(
                    f"cleanup still pending after {self.cleanup_wait_seconds:g}s: "
                    + ", ".join(pending)
                )
            return self._start_locked(cell, popen, args, kwargs)
        finally:
            gate.__exit__(None, None, None)

    def _start_locked(
        self, cell: str, popen: Callable[..., Any], args: Any, kwargs: Mapping[str, Any]
    ) -> Any:
        base = self.directory / cell
        session = Path(f"{base}.session")
        lock = Path(f"{base}.lock")
        try:
            if session.exists() and not _lock_is_free(lock):
                raise StartDenied(f"{cell} is still held by an earlier attempt")
            # Only reached when the scan found no U: an old verdict is S (a clean
            # rerun under run_exp0 resume), or this session's own unfinished cell.
            Path(f"{base}.verdict").unlink(missing_ok=True)
            Path(f"{base}.watchdog").unlink(missing_ok=True)
            Path(f"{base}.cleanup").unlink(missing_ok=True)
            _write_atomic(session, self.session + "\n")
            fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        except StartDenied:
            raise
        except Exception as error:
            raise StartDenied(
                f"{cell} gate registration failed: {type(error).__name__}: {error}"
            ) from error
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(fd)
            raise StartDenied(f"{cell} lifetime lock is already held: {error}") from error
        options = dict(kwargs)
        env = options.get("env")
        env = dict(os.environ if env is None else env)
        env[GATE_DIR_ENV] = str(self.directory)
        env[GATE_CELL_ENV] = cell
        options["env"] = env
        options["pass_fds"] = (*tuple(options.get("pass_fds", ())), fd)
        try:
            process = popen(*args, **options)
        except BaseException as error:
            os.close(fd)
            # Popen can fail after the fork. A held lock means a child may run.
            if _lock_is_free(lock):
                session.unlink(missing_ok=True)
            else:
                _commit_locked(
                    Path(f"{base}.verdict"),
                    cell,
                    UNKNOWN,
                    f"launcher: start indeterminate ({type(error).__name__}: {error})",
                )
            raise
        os.close(fd)
        return process

    def start(
        self,
        cell: str,
        popen: Callable[..., Any],
        args: Any,
        kwargs: Mapping[str, Any],
    ) -> Any:
        """Start ``cell``, waiting (bounded, unlocked) while a live cell is in cleanup."""
        began = time.monotonic()
        deadline = began + self.cleanup_wait_seconds
        while True:
            try:
                process = self.try_start(cell, popen, args, kwargs, deadline=deadline)
            except CleanupPending:
                self.wait_for_cleanups(deadline)
                continue
            self.note_wait(time.monotonic() - began)
            return process

    def note_wait(self, seconds: float) -> None:
        with self._waits_lock:
            self.waits.append(seconds)

    def popen(self, cell: str, popen: Callable[..., Any] = subprocess.Popen) -> Callable[..., Any]:
        """A ``Popen``-shaped callable that starts ``cell`` through the gate."""

        def start(*args: Any, **kwargs: Any) -> Any:
            return self.start(cell, popen, args, kwargs)

        return start

    def mark_unknown(self, cell: str, reason: str) -> None:
        """Launcher-side ``U``."""
        record_verdict(self.directory, cell, UNKNOWN, reason, lock_seconds=self.lock_seconds)

    def mark_watchdog(self, cell: str) -> None:
        """Call just before terminating ``cell`` on a watchdog.

        Other starts then wait (bounded) instead of running beside a cell whose
        resources are being torn down. Only the child's cleanup can still
        commit ``S``; if it is killed first, :meth:`require_clean` commits ``U``.
        """
        _check_cell(cell)
        with _locked(self.directory / GATE_LOCK, self.lock_seconds):
            _write_atomic(self.directory / f"{cell}.watchdog", "watchdog\n")
            _commit_locked(self.directory / f"{cell}.verdict", cell, WATCHDOG, "")

    def verdict(self, cell: str) -> tuple[str, str] | None:
        return _read_verdict(self.directory / f"{_check_cell(cell)}.verdict")

    def require_clean(self, cell: str) -> None:
        """Raise unless ``cell`` committed ``S``. Call after its child was reaped.

        A missing or pending verdict is first committed as ``U`` so that every
        other launcher thread is denied too, even while descendants that
        inherited the lifetime lock are still running.
        """
        try:
            verdict = self.verdict(cell)
        except Exception as error:
            verdict = (UNKNOWN, f"launcher: verdict unreadable: {error}")
        if verdict is not None and verdict[0] == CLEAN:
            return
        if verdict is None:
            reason = "launcher: exited without a cleanup verdict"
        elif verdict[0] == CLEANUP:
            reason = "launcher: exited inside cleanup without a verdict"
        elif verdict[0] == WATCHDOG:
            reason = "launcher: terminated by the watchdog before cleanup was verified"
        else:
            reason = verdict[1]
        reason += self._tag(cell)
        try:
            self.mark_unknown(cell, reason)
        except Exception as error:
            reason += f" (launcher U record failed: {type(error).__name__}: {error})"
        raise VerdictMissing(f"{cell} cleanup resource state unknown: {reason}")


def acknowledge(directory: Path, cell: str, note: str) -> Path:
    """Move ``cell``'s records aside after a person verified its resources.

    Refused while the cell's lifetime lock is held. The records are kept under
    ``acknowledged/`` with the note; nothing is deleted.
    """
    directory = Path(directory)
    _check_cell(cell)
    if not note.strip():
        raise ValueError("an acknowledgement needs a note saying what was checked")
    with _locked(directory / GATE_LOCK):
        lock = directory / f"{cell}.lock"
        if lock.exists() and not _lock_is_free(lock):
            raise RuntimeError(f"{cell} is still held by a running process")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        target = directory / ACKNOWLEDGED / f"{stamp}-{cell}"
        target.mkdir(parents=True)
        for suffix in (".verdict", ".watchdog", ".cleanup", ".session", ".lock"):
            source = directory / f"{cell}{suffix}"
            if source.exists():
                os.replace(source, target / source.name)
        (target / "note.txt").write_text(note.strip() + "\n", encoding="utf-8")
    return target


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[0] == "ack":
        try:
            print(acknowledge(Path(argv[1]), argv[2], argv[3]))
        except Exception as error:
            print(f"start gate: not acknowledged: {error}", file=sys.stderr)
            return 1
        return 0
    if len(argv) < 2 or argv[0] != "record" or argv[1] not in (CLEANUP, CLEAN, UNKNOWN):
        print(
            "usage: start_gate.py record C|S|U [reason] | ack DIRECTORY CELL NOTE",
            file=sys.stderr,
        )
        return 2
    directory = os.environ.get(GATE_DIR_ENV)
    cell = os.environ.get(GATE_CELL_ENV)
    if not directory or not cell:
        return 0  # not launched through a gate (for example `make demo`)
    try:
        record_verdict(Path(directory), cell, argv[1], " ".join(argv[2:]))
    except Exception as error:
        print(f"start gate: verdict not recorded: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

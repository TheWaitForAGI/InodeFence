"""Cross-process start gate: every failure model with real, separate processes.

Cells are real child processes started through the gate. The test drives each
child over a stdin/stdout pipe ("record U", then wait for "done"), so ordering
comes from the protocol, never from sleeps.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from inodefence.execution import start_gate as sg

GATE_SCRIPT = Path(sg.__file__).resolve()

# A cell child: each stdin line is a command; it answers "done <rc>" per line.
#   record ARGS  -> run start_gate.py record ARGS (a separate process, like bash)
#   spawn FIFO   -> start a grandchild that inherits every fd and blocks on FIFO
#   closefds     -> close every descriptor above 2 (drops the lifetime lock)
#   mark         -> create <cell>.cleanup with O_EXCL and no lock, as the smoke trap does
#   exit         -> exit 0
CHILD = textwrap.dedent(
    """
    import os, subprocess, sys
    gate = sys.argv[1]
    keep = []
    for line in sys.stdin:
        command, _, rest = line.strip().partition(" ")
        rc = 0
        if command == "record":
            rc = subprocess.call([sys.executable, "-I", gate, "record", *rest.split(" ", 1)])
        elif command == "mark":
            directory = os.environ["INODEFENCE_START_GATE_DIR"]
            cell = os.environ["INODEFENCE_START_GATE_CELL"]
            os.close(os.open(os.path.join(directory, cell + ".cleanup"), os.O_CREAT | os.O_EXCL))
        elif command == "spawn":
            code = "import sys; open(sys.argv[1]).read()"
            keep.append(subprocess.Popen([sys.executable, "-I", "-c", code, rest], close_fds=False))
        elif command == "closefds":
            os.closerange(3, 4096)
        elif command == "exit":
            sys.exit(0)
        print("done", rc, flush=True)
    """
)


class Cell:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process

    def send(self, line: str) -> int:
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        answer = self.process.stdout.readline().split()
        assert answer[0] == "done", answer
        return int(answer[1])

    def kill(self) -> None:
        self.process.send_signal(signal.SIGKILL)
        self.process.wait(timeout=30)

    def finish(self) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write("exit\n")
        self.process.stdin.flush()
        self.process.wait(timeout=30)

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=30)


#: Every cell this module started, so a start that a broken gate wrongly allows
#: (and that the test then never keeps) is still reaped at teardown.
_STARTED: list[Cell] = []


def start_cell(gate: sg.StartGate, name: str, **options: Any) -> Cell:
    process = gate.popen(name)(
        [sys.executable, "-I", "-c", CHILD, str(GATE_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        **options,
    )
    cell = Cell(process)
    _STARTED.append(cell)
    return cell


@pytest.fixture(autouse=True)
def _reap_started_cells() -> Any:
    yield
    while _STARTED:
        _STARTED.pop().close()


@pytest.fixture
def cells() -> Any:
    started: list[Cell] = []
    yield started
    for cell in started:
        cell.close()


#: Upper bound for waiting on a lock release that the protocol guarantees; a
#: broken gate then fails the test instead of hanging the run.
RELEASE_SECONDS = 30.0


def release(fifo: Path) -> None:
    """Open the FIFO for writing once; fail (ENXIO) instead of hanging if no reader exists."""
    deadline = time.monotonic() + RELEASE_SECONDS
    while True:
        try:
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
            return
        except OSError as error:
            # The grandchild may still be starting; past the bound there is no reader.
            assert time.monotonic() < deadline, f"no reader on {fifo.name}: {error}"
            time.sleep(0.01)


def wait_until_free(path: Path, alive: subprocess.Popen[Any] | None = None) -> None:
    deadline = time.monotonic() + RELEASE_SECONDS
    while not sg._lock_is_free(path):
        if alive is not None:
            assert alive.poll() is None, "the process exited before releasing as expected"
        assert time.monotonic() < deadline, f"{path.name} still held after {RELEASE_SECONDS}s"
        time.sleep(0.01)


def gate_at(tmp_path: Path, **options: Any) -> sg.StartGate:
    return sg.StartGate(tmp_path / "gate", **options)


def test_unknown_recorded_by_live_child_denies_next_start(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    assert first.send("record U controller ownership: daemon-unreachable") == 0
    # Child "a" is still running; its runner has not returned.
    with pytest.raises(sg.StartDenied, match="a cleanup resource state unknown: controller"):
        start_cell(gate, "b")
    assert not (gate.directory / "b.session").exists()


def test_clean_verdict_allows_next_start_and_unknown_is_final(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    assert first.send("record C") == 0
    assert first.send("record S") == 0
    cells.append(start_cell(gate, "b"))
    assert cells[1].send("record U lost") == 0
    assert cells[1].send("record S") == 1  # refused: U is final
    assert gate.verdict("b") == ("U", "lost")


def test_child_killed_without_verdict_denies(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    first.kill()
    with pytest.raises(sg.StartDenied, match="a exited without a cleanup verdict"):
        start_cell(gate, "b")


def test_child_killed_inside_cleanup_denies(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    assert first.send("record C") == 0
    first.kill()
    with pytest.raises(sg.StartDenied, match="a exited without a cleanup verdict"):
        start_cell(gate, "b")
    with pytest.raises(sg.VerdictMissing, match="inside cleanup"):
        gate.require_clean("a")


def test_live_cleanup_makes_start_wait_then_proceed(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    assert first.send("record C") == 0
    with pytest.raises(sg.CleanupPending, match="a"):
        gate.try_start("b", subprocess.Popen, (["true"],), {}, deadline=time.monotonic() + 1e6)
    with pytest.raises(sg.StartDenied, match="cleanup still pending"):
        gate.try_start("b", subprocess.Popen, (["true"],), {}, deadline=None)
    assert first.send("record S") == 0
    cells.append(start_cell(gate, "b"))


def test_cleanup_wait_bound_denies(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path, cleanup_wait_seconds=0)
    first = start_cell(gate, "a")
    cells.append(first)
    assert first.send("record C") == 0
    with pytest.raises(sg.StartDenied, match="cleanup still pending after 0s: a"):
        start_cell(gate, "b")


def test_waiting_start_resumes_when_cleanup_ends(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    assert first.send("record C") == 0
    entered, outcome = threading.Event(), {}
    original = gate.wait_for_cleanups

    def observed_wait(deadline: float) -> None:
        entered.set()
        original(deadline)

    gate.wait_for_cleanups = observed_wait  # type: ignore[method-assign]

    def start_second() -> None:
        try:
            outcome["cell"] = start_cell(gate, "b")
        except BaseException as error:
            outcome["error"] = error

    waiter = threading.Thread(target=start_second)
    waiter.start()
    assert entered.wait(30)
    assert not (gate.directory / "b.session").exists()  # still waiting, nothing started
    assert first.send("record S") == 0
    waiter.join(30)
    assert "error" not in outcome
    cells.append(outcome["cell"])
    assert gate.waits and gate.waits[-1] >= 0


def test_descendant_keeps_lock_but_only_s_counts_as_clean(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    fifo = tmp_path / "release"
    os.mkfifo(fifo)
    first = start_cell(gate, "a")
    cells.append(first)
    assert first.send(f"spawn {fifo}") == 0
    first.kill()  # bash SIGKILLed; a docker-CLI-like descendant still holds the lock
    try:
        # Held lock reads as "maybe running": the gate cannot tell yet.
        assert gate.problem() is None
        with pytest.raises(sg.VerdictMissing, match="exited without a cleanup verdict"):
            gate.require_clean("a")  # the reaped runner commits U for everyone
        with pytest.raises(sg.StartDenied, match="a cleanup resource state unknown"):
            start_cell(gate, "b")
    finally:
        release(fifo)


def test_descendant_after_clean_verdict_is_clean(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    fifo = tmp_path / "release"
    os.mkfifo(fifo)
    first = start_cell(gate, "a")
    cells.append(first)
    assert first.send(f"spawn {fifo}") == 0
    assert first.send("record S") == 0
    first.kill()
    try:
        gate.require_clean("a")
        cells.append(start_cell(gate, "b"))
    finally:
        release(fifo)


def test_bash_closing_the_lock_fd_reads_as_exit_without_verdict(tmp_path: Path) -> None:
    gate = gate_at(tmp_path)
    script = (
        'for fd in /proc/$$/fd/*; do n=${fd##*/}; [ "$n" -gt 2 ] && eval "exec $n>&-"; done; '
        "read -r _"
    )
    process = gate.popen("a")(["/bin/bash", "-c", script], stdin=subprocess.PIPE, text=True)
    try:
        # Wait until bash has closed its descriptors: probe until the lock is free.
        # The probe is the gate's own check, so no timing assumption is made.
        wait_until_free(gate.directory / "a.lock", alive=process)
        with pytest.raises(sg.StartDenied, match="a exited without a cleanup verdict"):
            gate.popen("b")(["true"])
    finally:
        assert process.stdin is not None
        process.stdin.close()
        process.wait(timeout=30)


def test_failed_popen_leaves_nothing_registered(tmp_path: Path) -> None:
    gate = gate_at(tmp_path)
    with pytest.raises(FileNotFoundError):
        gate.popen("a")([str(tmp_path / "missing-executable")])
    assert not (gate.directory / "a.session").exists()
    assert gate.problem() is None


def test_popen_that_raises_after_starting_a_child_is_unknown(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    spawned: list[subprocess.Popen[str]] = []

    def popen_then_fail(*args: Any, **kwargs: Any) -> Any:
        spawned.append(subprocess.Popen(*args, **kwargs))
        raise KeyboardInterrupt("interrupted after fork")

    try:
        with pytest.raises(KeyboardInterrupt):
            gate.start(
                "a",
                popen_then_fail,
                ([sys.executable, "-I", "-c", "import sys; sys.stdin.read()"],),
                {"stdin": subprocess.PIPE, "text": True},
            )
        assert gate.verdict("a") == (
            "U",
            "launcher: start indeterminate (KeyboardInterrupt: interrupted after fork)",
        )
    finally:
        for process in spawned:
            assert process.stdin is not None
            process.stdin.close()
            process.wait(timeout=30)
    with pytest.raises(sg.StartDenied, match="start indeterminate"):
        gate.popen("b")(["true"])


def test_earlier_launcher_session_denies_until_acknowledged(tmp_path: Path) -> None:
    directory = tmp_path / "gate"
    fifo = tmp_path / "release"
    os.mkfifo(fifo)
    launcher = textwrap.dedent(
        """
        import os, subprocess, sys
        from pathlib import Path
        sys.path.insert(0, os.path.dirname(sys.argv[1]))
        import start_gate
        gate = start_gate.StartGate(Path(sys.argv[2]))
        code = "import sys; open(sys.argv[1]).read()"
        gate.popen("a")([sys.executable, "-I", "-c", code, sys.argv[3]])
        os._exit(9)  # the launcher dies abnormally; its cell keeps running
        """
    )
    crashed = subprocess.run(
        [sys.executable, "-I", "-c", launcher, str(GATE_SCRIPT), str(directory), str(fifo)],
        check=False,
    )
    assert crashed.returncode == 9
    gate = sg.StartGate(directory)
    try:
        with pytest.raises(sg.StartDenied, match="a has no cleanup verdict from launcher session"):
            gate.popen("b")(["true"])
        with pytest.raises(RuntimeError, match="still held"):
            sg.acknowledge(directory, "a", "checked")
    finally:
        release(fifo)
    wait_until_free(directory / "a.lock")  # the orphan exits once the FIFO opens
    with pytest.raises(sg.StartDenied):
        gate.popen("b")(["true"])
    moved = sg.acknowledge(directory, "a", "operator: docker ps -a and volume ls showed nothing")
    assert (moved / "a.verdict").exists() is False and (moved / "note.txt").exists()
    gate.popen("b")(["true"]).wait(timeout=30)


def test_gate_lock_held_elsewhere_denies_and_blocks_child_record(tmp_path: Path) -> None:
    gate = gate_at(tmp_path, lock_seconds=0)
    holder = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            "import fcntl, sys; f = open(sys.argv[1], 'a'); fcntl.flock(f, fcntl.LOCK_EX); "
            "print('held', flush=True); sys.stdin.read()",
            str(gate.directory / sg.GATE_LOCK),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline() == "held\n"
        with pytest.raises(sg.StartDenied, match="start gate lock failed"):
            gate.popen("a")(["true"])
        with pytest.raises(TimeoutError):
            sg.record_verdict(gate.directory, "a", "U", "x", lock_seconds=0)
    finally:
        assert holder.stdin is not None
        holder.stdin.close()
        holder.wait(timeout=30)


def test_start_and_unknown_record_are_mutually_exclusive(tmp_path: Path) -> None:
    """While a start holds the gate lock, a child's U commit cannot happen."""
    gate = gate_at(tmp_path)
    observed: list[int] = []
    attempt = textwrap.dedent(
        """
        import os, sys
        sys.path.insert(0, os.path.dirname(sys.argv[1]))
        import start_gate
        from pathlib import Path
        try:
            start_gate.record_verdict(Path(sys.argv[2]), "a", "U", "race", lock_seconds=0)
        except TimeoutError:
            sys.exit(3)
        """
    )

    def popen_under_lock(*args: Any, **kwargs: Any) -> Any:
        observed.append(
            subprocess.call(
                [sys.executable, "-I", "-c", attempt, str(GATE_SCRIPT), str(gate.directory)]
            )
        )
        return subprocess.Popen(*args, **kwargs)

    gate.popen("b", popen_under_lock)(["true"]).wait(timeout=30)
    assert observed == [3]


def test_unreadable_state_denies(tmp_path: Path) -> None:
    gate = gate_at(tmp_path)
    (gate.directory / "a.session").write_text(gate.session + "\n")
    (gate.directory / "a.verdict").write_text("garbage\n")
    with pytest.raises(sg.StartDenied, match="start gate state unreadable"):
        gate.popen("b")(["true"])


def test_record_without_gate_environment_is_a_no_op(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("INODEFENCE_START_GATE")}
    result = subprocess.run(
        [sys.executable, "-I", str(GATE_SCRIPT), "record", "S"], env=env, check=False
    )
    assert result.returncode == 0


def test_record_into_missing_directory_fails(tmp_path: Path) -> None:
    env = {
        **os.environ,
        sg.GATE_DIR_ENV: str(tmp_path / "absent"),
        sg.GATE_CELL_ENV: "a",
    }
    result = subprocess.run(
        [sys.executable, "-I", str(GATE_SCRIPT), "record", "U", "x"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "verdict not recorded" in result.stderr


def test_lock_fd_is_not_leaked_to_unrelated_children(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    lock_inode = os.stat(gate.directory / "a.lock").st_ino
    other = subprocess.run(
        [
            "/bin/sh",
            "-c",
            'for f in /proc/self/fd/*; do stat -L -c %i "$f" 2>/dev/null; done; true',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert str(lock_inode) not in other.stdout.split()
    assert not any(
        os.path.exists(f"/proc/self/fd/{fd}")
        and os.stat(f"/proc/self/fd/{fd}").st_ino == lock_inode
        for fd in range(3, 256)
    )


def test_watchdog_then_trap_verifies_cleanup_allows_next_start(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    gate.mark_watchdog("a")
    with pytest.raises(sg.CleanupPending):
        gate.try_start("b", subprocess.Popen, (["true"],), {}, deadline=time.monotonic() + 1e6)
    assert first.send("record C") == 0  # the trap enters cleanup: still pending as W
    assert gate.verdict("a") == ("W", "")
    assert first.send("record S") == 0  # ownership and absence verified by the trap
    first.finish()
    gate.require_clean("a")
    cells.append(start_cell(gate, "b"))


def test_watchdog_then_child_killed_is_unknown_and_denies(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    gate.mark_watchdog("a")
    first.kill()  # terminate ignored, killed after the grace: the trap never ran
    with pytest.raises(
        sg.StartDenied, match=r"a exited without a cleanup verdict \(after watchdog\)"
    ):
        start_cell(gate, "b")
    with pytest.raises(sg.VerdictMissing, match=r"terminated by the watchdog.*\(after watchdog\)"):
        gate.require_clean("a")
    verdict = gate.verdict("a")
    assert verdict is not None and verdict[0] == "U"


def test_watchdog_then_trap_records_unknown_denies(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    gate.mark_watchdog("a")
    assert first.send("record U volume ownership: daemon-unreachable") == 0
    with pytest.raises(
        sg.StartDenied, match=r"a cleanup resource state unknown: volume.*\(after watchdog\)"
    ):
        start_cell(gate, "b")


def test_watchdog_wait_bound_denies(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path, cleanup_wait_seconds=0)
    first = start_cell(gate, "a")
    cells.append(first)
    gate.mark_watchdog("a")
    with pytest.raises(sg.StartDenied, match="cleanup still pending after 0s: a"):
        start_cell(gate, "b")


def test_watchdog_mark_after_clean_verdict_keeps_clean(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    assert first.send("record S") == 0
    gate.mark_watchdog("a")
    assert gate.verdict("a") == ("S", "")


def test_child_cannot_record_watchdog_state(tmp_path: Path, cells: Any) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    cells.append(first)
    assert first.send("record W") == 2  # usage error: W is launcher-only
    with pytest.raises(ValueError):
        sg.record_verdict(gate.directory, "a", "W")


def test_real_watchdog_path_sigterm_trap_commits_clean(tmp_path: Path) -> None:
    """run_exp0.run_cell_with_watchdog with a 0 s limit: W, SIGTERM, trap S."""
    from scripts import run_concurrency_benchmark as bench
    from scripts.run_exp0 import WATCHDOG_RETURNCODE, run_cell_with_watchdog

    gate = gate_at(tmp_path)
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    cell = bench.planned_blocks(design, "smoke")[0].cells[0]
    fake_bash = tmp_path / "fake-bash"
    record = f"{sys.executable} -I {GATE_SCRIPT} record"
    fake_bash.write_text(
        f"#!/bin/bash\ntrap '{record} C; {record} S; exit 0' TERM\n"
        'echo ready >&"$READY_FD"\nread -r _\n'
    )
    fake_bash.chmod(0o755)
    observed: list[tuple[str, str] | None] = []

    def on_timeout() -> None:
        gate.mark_watchdog(cell.run_id)
        observed.append(gate.verdict(cell.run_id))

    output = tmp_path / "out"
    output.mkdir()
    ready_read, ready_write = os.pipe()

    def launch_when_trap_installed(*args: Any, **kwargs: Any) -> Any:
        # The 0 s limit fires right after Popen returns, so return only once the
        # child reports its TERM trap is installed.
        kwargs["env"] = {**kwargs["env"], "READY_FD": str(ready_write)}
        process = gate.popen(cell.run_id)(
            *args, stdin=subprocess.PIPE, pass_fds=(ready_write,), **kwargs
        )
        os.close(ready_write)
        with os.fdopen(ready_read) as ready:
            assert ready.readline() == "ready\n"
        return process

    result = run_cell_with_watchdog(
        cell,
        output,
        {"PATH": "/usr/bin:/bin"},
        str(fake_bash),
        limit_seconds=0,
        popen=launch_when_trap_installed,
        on_timeout=on_timeout,
    )
    assert result.returncode == WATCHDOG_RETURNCODE
    assert observed == [("W", "")]
    gate.require_clean(cell.run_id)
    assert gate.problem() is None


def test_cleanup_marker_alone_keeps_starts_waiting_then_denies(tmp_path: Path) -> None:
    """Both lock-based records fail; the unlocked O_EXCL marker still holds starts back."""
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    assert first.send("mark") == 0  # cleanup entered; C and U never get recorded
    assert gate.verdict("a") is None
    with pytest.raises(sg.CleanupPending, match="a"):
        gate.try_start("b", subprocess.Popen, (["true"],), {}, deadline=time.monotonic() + 1e6)
    first.kill()  # exits without any verdict
    with pytest.raises(sg.StartDenied, match="a exited without a cleanup verdict"):
        start_cell(gate, "b")


def test_cleanup_marker_is_cleared_on_rerun_and_moved_on_ack(tmp_path: Path) -> None:
    gate = gate_at(tmp_path)
    first = start_cell(gate, "a")
    assert first.send("mark") == 0
    assert first.send("record S") == 0
    first.finish()
    gate.popen("a")(["true"]).wait(timeout=30)  # rerun of a clean cell
    assert not (gate.directory / "a.cleanup").exists()
    sg.acknowledge(gate.directory, "a", "test: rerun had no verdict")
    assert not any(gate.directory.glob("a.*"))


class SmokeShapedProcess:
    """The real smoke script's shape seen by the watchdog: bash with an EXIT trap
    waiting on a foreground child (``cat`` on its stdin, standing in for the
    ``docker exec`` campaign). bash defers SIGTERM until that child exits.

    ``ends_in_grace``: terminate() also ends the foreground child, as a campaign
    that finishes inside the 30 s grace does. Otherwise the child never ends, so
    the grace wait certainly expires; it is shortened to keep the test fast.
    """

    def __init__(self, process: subprocess.Popen[str], ends_in_grace: bool) -> None:
        self.process = process
        self.ends_in_grace = ends_in_grace
        self.pid = process.pid

    @property
    def returncode(self) -> int | None:
        return self.process.returncode

    def poll(self) -> int | None:
        return self.process.poll()

    def terminate(self) -> None:
        self.process.terminate()
        if self.ends_in_grace:
            assert self.process.stdin is not None
            self.process.stdin.close()

    def wait(self, timeout: float | None = None) -> int:
        if not self.ends_in_grace and timeout == 30:
            timeout = 0.2  # the child cannot end: the expiry is certain, only faster
        return self.process.wait(timeout=timeout)

    def kill(self) -> None:
        self.process.kill()


@pytest.mark.parametrize("ends_in_grace", [True, False])
def test_watchdog_on_the_real_smoke_shape(tmp_path: Path, ends_in_grace: bool) -> None:
    """EXIT trap + foreground child: S if cleanup finishes inside the grace, else kill -> U."""
    from scripts import run_concurrency_benchmark as bench
    from scripts.run_exp0 import WATCHDOG_RETURNCODE, run_cell_with_watchdog

    gate = gate_at(tmp_path)
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    cell = bench.planned_blocks(design, "smoke")[0].cells[0]
    record = f"{sys.executable} -I {GATE_SCRIPT} record"
    # bash 5.2 with an EXIT trap may run the trap at once on SIGTERM (leaving the
    # foreground child running) or only after the child ends; both were observed on
    # this host. The two outcomes below hold either way: a trap that verifies
    # quickly commits S; a trap whose cleanup outlasts the grace (it blocks here, as
    # a slow docker removal would) is killed first, and the launcher commits U.
    slow = tmp_path / "slow-cleanup"
    os.mkfifo(slow)
    work = "" if ends_in_grace else f"read -r _ < {slow}; "
    fake_bash = tmp_path / "fake-bash"
    fake_bash.write_text(
        # "ready" comes from the foreground child itself, so bash is already waiting
        # on it when the watchdog's SIGTERM arrives.
        f"#!/bin/bash\ntrap '{record} C; {work}{record} S' EXIT\n"
        "/bin/bash -c 'echo ready >&\"$READY_FD\"; exec cat'\n"
    )
    fake_bash.chmod(0o755)
    ready_read, ready_write = os.pipe()
    shaped: list[SmokeShapedProcess] = []

    def launch(*args: Any, **kwargs: Any) -> Any:
        kwargs["env"] = {**kwargs["env"], "READY_FD": str(ready_write)}
        process = gate.popen(cell.run_id)(
            *args, stdin=subprocess.PIPE, pass_fds=(ready_write,), **kwargs
        )
        os.close(ready_write)
        with os.fdopen(ready_read) as ready:
            assert ready.readline() == "ready\n"
        shaped.append(SmokeShapedProcess(process, ends_in_grace))
        return shaped[-1]

    output = tmp_path / "out"
    output.mkdir()
    result = run_cell_with_watchdog(
        cell,
        output,
        {"PATH": "/usr/bin:/bin"},
        str(fake_bash),
        limit_seconds=0,
        popen=launch,
        on_timeout=lambda: gate.mark_watchdog(cell.run_id),
    )
    assert result.returncode == WATCHDOG_RETURNCODE
    try:
        if ends_in_grace:
            assert shaped[0].returncode == -15  # SIGTERM, after the trap committed S
            gate.require_clean(cell.run_id)
            assert gate.problem() is None
        else:
            assert shaped[0].returncode == -9  # killed inside its trap, before S
            with pytest.raises(
                sg.VerdictMissing, match=r"terminated by the watchdog.*after watchdog"
            ):
                gate.require_clean(cell.run_id)
            assert "after watchdog" in (gate.problem() or "")
    finally:
        stdin = shaped[0].process.stdin
        if stdin is not None and not stdin.closed:
            stdin.close()  # ends the orphaned foreground child

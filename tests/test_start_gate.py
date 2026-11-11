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


def start_cell(gate: sg.StartGate, name: str, **options: Any) -> Cell:
    process = gate.popen(name)(
        [sys.executable, "-I", "-c", CHILD, str(GATE_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        **options,
    )
    return Cell(process)


@pytest.fixture
def cells() -> Any:
    started: list[Cell] = []
    yield started
    for cell in started:
        cell.close()


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
        with fifo.open("w"):
            pass


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
        with fifo.open("w"):
            pass


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
        while not sg._lock_is_free(gate.directory / "a.lock"):
            assert process.poll() is None
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
        with fifo.open("w"):
            pass
    while not sg._lock_is_free(directory / "a.lock"):
        pass  # the orphan exits after the FIFO opens; the probe is the gate's own
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

"""Benign CLI transport helpers; these are not target-container isolation tests."""

import os
import signal
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep

import pytest

from inodefence.execution.base import BackendError
from inodefence.execution.docker_client import DockerCLI


def _assert_stopped(pid: int) -> None:
    try:
        state = Path(f"/proc/{pid}/stat").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return
    assert state.rsplit(")", 1)[1].split()[0] == "Z"


def test_ex003_deadline_stops_pipe_owner_after_direct_primary_exits(tmp_path, monkeypatch):
    """Exact frozen fork/pipe witness, with independent same-user group protection."""
    executable = tmp_path / "benign-docker-double"
    pid_file = tmp_path / "child.pid"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os,time\n"
        "child=os.fork()\n"
        "if child == 0:\n"
        "    time.sleep(30)\n"
        "    os._exit(0)\n"
        f"with open({str(pid_file)!r}, 'w') as stream:\n"
        "    stream.write(str(child))\n"
        "os.write(1, str(child).encode())\n"
        "os._exit(0)\n"
    )
    executable.chmod(0o700)
    original_popen = subprocess.Popen
    processes = []

    def tracked(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", tracked)
    with subprocess.Popen(
        (sys.executable, "-c", "import time; time.sleep(30)"), start_new_session=True
    ) as unrelated:
        try:
            start = monotonic()
            result = DockerCLI(str(executable), "audit-double").run(("version",), 0.5)
            assert result.timed_out and result.returncode == 0
            assert 0.5 <= monotonic() - start < 6
            child = int(pid_file.read_text())
            assert int(result.stdout) == child
            primary = processes[-1]
            assert primary.returncode == 0
            with pytest.raises(ChildProcessError):
                os.waitpid(primary.pid, os.WNOHANG)
            deadline = monotonic() + 2
            while True:
                try:
                    _assert_stopped(child)
                    break
                except AssertionError:
                    if monotonic() >= deadline:
                        raise
                    sleep(0.01)
            assert unrelated.poll() is None
        finally:
            unrelated.kill()
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass


@pytest.mark.parametrize("error", (FileNotFoundError, ProcessLookupError))
def test_descendant_reaping_races_are_stopped(monkeypatch, error):
    def reaped(*args, **kwargs):
        raise error("controlled inspection race")

    monkeypatch.setattr(Path, "read_text", reaped)
    _assert_stopped(123)


def test_live_descendant_is_not_stopped(monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: "123 (helper) S")
    with pytest.raises(AssertionError):
        _assert_stopped(123)


def test_descendant_inspection_permission_error_propagates(monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("controlled inspection error")

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(PermissionError):
        _assert_stopped(123)


def test_kill_permission_failure_is_bounded_and_not_success(monkeypatch, tmp_path):
    executable = tmp_path / "benign-live-helper"
    executable.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(30)\n")
    executable.chmod(0o700)
    original_popen = subprocess.Popen
    processes = []

    def tracked(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    def denied(*args, **kwargs):
        raise PermissionError("controlled group signal failure")

    monkeypatch.setattr(subprocess, "Popen", tracked)
    monkeypatch.setattr(os, "killpg", denied)
    try:
        start = monotonic()
        with pytest.raises(BackendError) as caught:
            DockerCLI(str(executable), "audit-double").run(("version",), 0.05)
        assert isinstance(caught.value.__cause__, PermissionError)
        assert monotonic() - start < 2
        assert processes[0].poll() is None
    finally:
        for process in processes:
            process.kill()
            process.wait(timeout=2)

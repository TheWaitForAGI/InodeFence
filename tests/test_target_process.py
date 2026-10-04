"""Controlled process helpers: output, timeout and same-group child shutdown."""

import os
import sys
from pathlib import Path

import pytest

from inodefence.runtime import RuntimeSandbox
from inodefence.targets._process import run_process


def _assert_child_stopped(pid: int) -> None:
    # Reaping can remove the proc path (ENOENT) or invalidate an open read (ESRCH).
    try:
        state = Path(f"/proc/{pid}/stat").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return
    assert state.split()[2] == "Z"


def test_output_and_nonzero_exit_are_evidence(sandbox: RuntimeSandbox) -> None:
    result = run_process(
        (
            sys.executable,
            "-c",
            "import sys; print('out'); print('err',file=sys.stderr); sys.exit(4)",
        ),
        sandbox.extraction_root,
        2.0,
    )
    assert result.exit_code == 4
    assert result.stdout == b"out\n" and result.stderr == b"err\n"
    assert result.duration_seconds > 0


def test_timeout_stops_worker_and_ordinary_child(sandbox: RuntimeSandbox) -> None:
    code = (
        "import os,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "print(os.getpid(),child.pid,flush=True); time.sleep(60)"
    )
    result = run_process((sys.executable, "-c", code), sandbox.extraction_root, 0.5)
    assert result.exit_code is None
    worker, child = map(int, result.stdout.split())
    with pytest.raises(ProcessLookupError):
        os.kill(worker, 0)
    _assert_child_stopped(child)
    assert result.duration_seconds >= 0.5


@pytest.mark.parametrize("error", (FileNotFoundError, ProcessLookupError))
def test_child_reaped_during_inspection_is_stopped(monkeypatch, error) -> None:
    def reaped(*args, **kwargs):
        raise error("controlled reaping race")

    monkeypatch.setattr(Path, "read_text", reaped)
    _assert_child_stopped(123)


def test_live_child_is_not_considered_stopped(monkeypatch) -> None:
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: "123 (python) S")
    with pytest.raises(AssertionError):
        _assert_child_stopped(123)


def test_other_process_inspection_errors_propagate(monkeypatch) -> None:
    def denied(*args, **kwargs):
        raise PermissionError("controlled inspection failure")

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(PermissionError):
        _assert_child_stopped(123)

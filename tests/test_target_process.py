"""Controlled process helpers: output, timeout and same-group child shutdown."""

import os
import sys
from pathlib import Path

import pytest

from inodefence.runtime import RuntimeSandbox
from inodefence.targets._process import run_process


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
    status = Path(f"/proc/{child}/stat")
    assert not status.exists() or status.read_text().split()[2] == "Z"
    assert result.duration_seconds >= 0.5

"""Linux worker lifecycle, not an OS isolation boundary."""

import math
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter


@dataclass(frozen=True, slots=True)
class ProcessOutcome:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    duration_seconds: float


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_process(command: tuple[str, ...], cwd: Path, timeout_seconds: float) -> ProcessOutcome:
    """Capture streams; kill the worker's new group and reap the direct child.

    Same-group children stop before return, including after successful completion.
    This does not contain children that deliberately detach or filesystem/network
    access. Such targets must never run without a separately validated OS boundary.
    Cleanup communication is bounded; a surviving pipe owner is a harness error.
    """
    if sys.platform != "linux":
        raise ValueError("target processes require supported Linux")
    if (
        type(timeout_seconds) not in (int, float)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be finite and positive")
    start = perf_counter()
    with subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        # Exclude caller NODE_OPTIONS/PYTHONPATH and unrelated credential variables.
        env={"PATH": os.defpath, "LANG": "C.UTF-8"},
    ) as process:
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(process.pid)
            try:
                stdout, stderr = process.communicate(timeout=5.0)
            except subprocess.TimeoutExpired as error:
                raise RuntimeError("worker pipes remained open after group termination") from error
        finally:
            _kill_group(process.pid)
            process.wait()
    return ProcessOutcome(
        None if timed_out else process.returncode, stdout, stderr, perf_counter() - start
    )

"""Process execution data, independent of targets and filesystem state."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionResult:
    """Observed process result without validation or security interpretation.

    exit_code is None when no exit code was obtained, for example on timeout.
    stdout and stderr retain the supplied process output strings unchanged.
    duration_seconds records elapsed time in seconds; timed_out records whether
    a timeout occurred. A timeout does not require exit_code to be None.
    """

    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool

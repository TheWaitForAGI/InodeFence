import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from scripts.generate_tar_fixtures import baseline_case

from inodefence.feedback import state_signature
from inodefence.model import ExecutionResult, ExecutionStatus, canonical_json
from inodefence.pipeline import run_case
from inodefence.runtime import RuntimeSandbox
from inodefence.targets import PythonTarfileTarget
from inodefence.targets import python_tarfile as target_module


@pytest.mark.parametrize("duration", [0.0, 1e-9, sys.float_info.max, 0, 7])
def test_execution_duration_accepts_finite_nonnegative_numbers(duration: float) -> None:
    result = ExecutionResult(
        "target", "version", (), ExecutionStatus.SUCCESS, 0, "", "", duration_seconds=duration
    )
    assert result.duration_seconds == duration
    assert json.loads(canonical_json(result))["value"]["duration_seconds"] == duration


@pytest.mark.parametrize("duration", [-1, math.nan, math.inf, -math.inf])
def test_execution_duration_rejects_negative_or_nonfinite_numbers(duration: float) -> None:
    with pytest.raises(ValueError, match="duration_seconds must be finite and nonnegative"):
        ExecutionResult(
            "target", "version", (), ExecutionStatus.SUCCESS, 0, "", "", duration_seconds=duration
        )


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [
        (ExecutionStatus.SUCCESS, 0),
        (ExecutionStatus.REJECTED, 2),
        (ExecutionStatus.FAILED, 3),
        (ExecutionStatus.TIMED_OUT, None),
    ],
)
def test_adapter_measures_monotonic_elapsed_for_every_status(
    sandbox: RuntimeSandbox,
    monkeypatch: pytest.MonkeyPatch,
    status: ExecutionStatus,
    exit_code: int | None,
) -> None:
    clock_readings = iter((42.0, 42.375))
    stopped = False

    def clock() -> float:
        reading = next(clock_readings)
        # The final reading must happen after completion/timeout cleanup.
        assert stopped == (reading == 42.375)
        return reading

    def execute(
        command: tuple[str, ...],
        *,
        cwd: Path,
        capture_output: bool,
        timeout: float,
        check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal stopped
        stopped = True
        if exit_code is None:
            raise subprocess.TimeoutExpired(command, timeout, output=b"out", stderr=b"err")
        return subprocess.CompletedProcess(command, exit_code, stdout=b"out", stderr=b"err")

    monkeypatch.setattr(target_module, "perf_counter", clock)
    monkeypatch.setattr(target_module.subprocess, "run", execute)
    result = PythonTarfileTarget(timeout_seconds=4.0).run(
        sandbox.archive_path, sandbox.extraction_root
    )
    assert result.status == status and result.exit_code == exit_code
    assert result.duration_seconds == 0.375
    assert result.timeout_seconds == 4.0
    assert result.stdout == "out" and result.stderr == "err"


def test_execution_duration_does_not_change_state_signature_or_case_identity() -> None:
    result = run_case(baseline_case("hardlink"), PythonTarfileTarget())
    first = replace(result, execution=replace(result.execution, duration_seconds=0.0))
    second = replace(result, execution=replace(result.execution, duration_seconds=123.5))
    assert canonical_json(first) != canonical_json(second)
    assert first.case.case_id == second.case.case_id == result.case.case_id
    assert first.archive_sha256 == second.archive_sha256
    assert first.before == second.before and first.after == second.after
    assert first.changes == second.changes and first.violations == second.violations
    assert first.signature == second.signature == state_signature(first.before, first.after)
    assert second.signature == state_signature(second.before, second.after)
    assert first.signature.schema_version == 3
    assert canonical_json(first.signature) == canonical_json(second.signature)
    assert "duration_seconds" not in canonical_json(first.signature)
    assert "duration_seconds" not in canonical_json(first.case)

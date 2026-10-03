"""Check process result representation without executing an extractor."""

from dataclasses import FrozenInstanceError

import pytest

from inodefence.model import ExecutionResult


def test_successful_process_result() -> None:
    result = ExecutionResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=0.1,
        timed_out=False,
    )

    assert result.exit_code == 0
    assert result.stdout == "ok"
    assert result.stderr == ""
    assert result.duration_seconds == 0.1
    assert result.timed_out is False


@pytest.mark.parametrize("exit_code", [2, -9])
def test_nonzero_exit_code_is_preserved(exit_code: int) -> None:
    result = ExecutionResult(
        exit_code=exit_code,
        stdout="",
        stderr="process stopped",
        duration_seconds=0.2,
        timed_out=False,
    )

    assert result.exit_code == exit_code


@pytest.mark.parametrize("exit_code", [None, -9])
def test_timeout_result(exit_code: int | None) -> None:
    result = ExecutionResult(
        exit_code=exit_code,
        stdout="partial output",
        stderr="",
        duration_seconds=1.0,
        timed_out=True,
    )

    assert result.exit_code == exit_code
    assert result.timed_out is True


def test_output_strings_are_preserved() -> None:
    stdout = "  출력\r\n\x00\tend\n"
    stderr = " warning\n\r\t\x00오류  "
    result = ExecutionResult(
        exit_code=0,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=0.1,
        timed_out=False,
    )

    assert result.stdout == stdout
    assert result.stderr == stderr


@pytest.mark.parametrize("duration_seconds", [0.0, 0.123456789, 1_000_000.5])
def test_duration_is_preserved(duration_seconds: float) -> None:
    result = ExecutionResult(
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=duration_seconds,
        timed_out=False,
    )

    assert result.duration_seconds == duration_seconds


def test_result_is_frozen() -> None:
    result = ExecutionResult(
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
        timed_out=False,
    )

    with pytest.raises(FrozenInstanceError):
        setattr(result, "exit_code", 2)  # noqa: B010

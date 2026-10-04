"""Python tarfile/data reference adapter, not a research benchmark target."""

import math
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.model.provenance import TargetProvenance
from inodefence.runtime import open_runtime_directory


def _validate_paths(archive_path: Path, extraction_root: Path) -> None:
    if (
        extraction_root.name != "extract"
        or archive_path.parent.name != "archive"
        or archive_path.parent.parent != extraction_root.parent
    ):
        raise ValueError("reference target requires a run's archive/ and extract/ layout")
    with open_runtime_directory(extraction_root), open_runtime_directory(archive_path.parent):
        if archive_path.name != "input.tar":
            raise ValueError("reference archive must be archive/input.tar")


def _text(value: str | bytes | None) -> str:
    # Surrogate escapes retain undecodable output for lossless JSON evidence.
    return value.decode("utf-8", "surrogateescape") if isinstance(value, bytes) else value or ""


@dataclass(frozen=True, slots=True)
class PythonTarfileTarget:
    """Run one trusted reference implementation in a fresh interpreter.

    data filter behavior depends on the recorded Python patch version. Modes
    accepted by the builder need not be preserved by this extraction policy.
    Duration covers subprocess execution through completion or timeout cleanup,
    including process startup and kill/wait overhead, excluding path validation.
    """

    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")

    @property
    def provenance(self) -> TargetProvenance:
        return TargetProvenance(
            "python-tarfile-data", platform.python_version(), self.timeout_seconds
        )

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        _validate_paths(archive_path, extraction_root)
        command = (
            sys.executable,
            "-m",
            "inodefence.targets._python_worker",
            str(archive_path),
            str(extraction_root),
        )
        provenance = self.provenance
        version = provenance.target_version
        start = perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=extraction_root,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            elapsed = perf_counter() - start
            # subprocess.run kills and waits for this single worker before raising.
            return ExecutionResult(
                provenance.target_id,
                version,
                command,
                ExecutionStatus.TIMED_OUT,
                None,
                _text(error.stdout),
                _text(error.stderr),
                duration_seconds=elapsed,
                timeout_seconds=self.timeout_seconds,
            )
        elapsed = perf_counter() - start
        status = (
            ExecutionStatus.SUCCESS
            if completed.returncode == 0
            else ExecutionStatus.REJECTED
            if completed.returncode == 2
            else ExecutionStatus.FAILED
        )
        return ExecutionResult(
            provenance.target_id,
            version,
            command,
            status,
            completed.returncode,
            _text(completed.stdout),
            _text(completed.stderr),
            duration_seconds=elapsed,
            timeout_seconds=self.timeout_seconds,
        )

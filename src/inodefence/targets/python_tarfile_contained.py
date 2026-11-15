"""Contained Python-``tarfile`` effect target: one runtime image, one extraction filter.

The extraction runs in a derived official runtime image (``python:X.Y.Z-slim`` + the
standard-library worker ``tools/python-tarfile/effect/worker.py`` at ``/target/worker.py``)
through the trusted ``ExecutionBackend`` -- the same container boundary as the node-tar effect
path (no network, read-only root, dropped capabilities, non-root user, the run root on the
disposable runtime volume). Nothing here changes that boundary; this module only says which
argv runs and how its exit code and per-member lines are read.

Two axes stay separate: the runtime version is fixed by the bound image (observed through
``--identify``), the extraction filter by ``policy``. A campaign binds exactly one of each.

The per-member lines are the worker's own report of what ``tarfile`` did (observed inside the
container); the C0/C1/C2 verdict and the effect events are built host-side from the real
BEFORE/AFTER snapshots (``inodefence.targets.python_tarfile_effect._build_trace``), so a lying or
broken worker can at most make a trace incomplete, never invent a violation.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from inodefence.execution.base import ContainerOutcome, ContainerRequest, ExecutionBackend
from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.model.isolation import ArtifactDigest, IsolationProvenance
from inodefence.model.provenance import TargetProvenance

from ._paths import validate_run_paths
from .isolated import identify_image

PYTHON = "/usr/local/bin/python"
WORKER = "/target/worker.py"
RUN_FORMAT = "inodefence-python-tarfile-run-v1"
POLICIES = ("data", "fully_trusted")
CONTAINER_MECHANISM = "python-tarfile-container"
_EXACT = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class MemberReport:
    """One worker line: the member at ``ordinal`` was extracted or refused (``error`` names why)."""

    ordinal: int
    succeeded: bool
    error: str | None


@dataclass(frozen=True, slots=True)
class PythonTarfileCapture:
    """One contained run: classified execution plus the worker's per-member report.

    ``report_error`` is set when the worker output could not be read (no final line, wrong
    format, out-of-order ordinals, truncated output); the members are then empty and the trace
    built from it fails closed.
    """

    execution: ExecutionResult
    members: tuple[MemberReport, ...]
    report_error: str | None


def parse_worker_output(
    stdout: bytes, truncated: bool
) -> tuple[tuple[MemberReport, ...], str | None]:
    """Strictly read the worker's member lines and final line; anything unexpected is an error."""
    if truncated:
        return (), "worker output truncated"
    try:
        lines = [json.loads(line) for line in stdout.decode("utf-8").splitlines() if line.strip()]
    except (UnicodeDecodeError, ValueError) as error:
        return (), f"worker output is not JSON lines: {error}"
    if not lines or not isinstance(lines[-1], dict) or lines[-1].get("format") != RUN_FORMAT:
        return (), f"worker printed no {RUN_FORMAT} final line"
    final = lines[-1]
    members: list[MemberReport] = []
    for index, line in enumerate(lines[:-1]):
        if (
            not isinstance(line, dict)
            or line.get("ordinal") != index
            or line.get("status") not in ("succeeded", "errored")
        ):
            return (), f"worker member line {index} is malformed"
        error = line.get("error")
        if error is not None and not isinstance(error, str):
            return (), f"worker member line {index} has a non-text error"
        members.append(MemberReport(index, line["status"] == "succeeded", error))
    if final.get("members") != len(members):
        return (), "worker final line disagrees with its member lines"
    return tuple(members), None


def worker_reported_status(stdout: str) -> str | None:
    """The worker's own final status (success/rejected/failed) if its whole report is readable.

    ``None`` means the run cannot be attributed to the extractor (crash, truncation, garbage):
    such a step has no verdict. A readable ``failed`` is the extractor's outcome -- tarfile raised
    while extracting -- and the host snapshots of that run are as valid as any other.
    """
    members, error = parse_worker_output(stdout.encode("utf-8", "surrogateescape"), False)
    del members
    if error is not None:
        return None
    final = json.loads(stdout.strip().splitlines()[-1])
    status = final.get("status")
    return status if status in ("success", "rejected", "failed") else None


@dataclass(frozen=True, slots=True)
class PythonTarfileContainedTarget:
    """Pinned contained invocation of the python-tarfile effect worker."""

    backend: ExecutionBackend
    image_id: str
    policy: str
    python_version: str
    tarfile_sha256: str
    worker_sha256: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.backend, ExecutionBackend):
            raise ValueError("python-tarfile target requires a trusted ExecutionBackend")
        if not isinstance(self.image_id, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", self.image_id
        ):
            raise ValueError("python-tarfile target requires an immutable image ID")
        if self.policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}")
        if not isinstance(self.python_version, str) or not _EXACT.fullmatch(self.python_version):
            raise ValueError("python-tarfile target needs an exact runtime X.Y.Z")
        for value in (self.tarfile_sha256, self.worker_sha256):
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                raise ValueError("python-tarfile source identities require SHA-256")
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 120
        ):
            raise ValueError("timeout must be finite, positive and at most 120 seconds")
        self.backend.validate_image(self.image_id)

    @classmethod
    def bind(
        cls,
        backend: ExecutionBackend,
        image_id: str,
        policy: str,
        *,
        expected_python: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> PythonTarfileContainedTarget:
        """Read the image's identity offline and pin it; ``expected_python`` must match if given."""
        placeholder = "0" * 64
        cls(backend, image_id, policy, "0.0.0", placeholder, placeholder, timeout_seconds)
        value = _identify(backend, image_id)
        if value.get("has_data_filter") is not True:
            raise ValueError("this runtime has no tarfile extraction filters")
        target = cls(
            backend,
            image_id,
            policy,
            value["python_version"],
            value["tarfile_sha256"],
            value["worker_sha256"],
            timeout_seconds,
        )
        if expected_python is not None and target.python_version != expected_python:
            raise ValueError(
                f"image runs python {target.python_version}, expected {expected_python}"
            )
        return target

    @property
    def target_id(self) -> str:
        return f"python-tarfile-{self.policy.replace('_', '-')}"

    @property
    def provenance(self) -> TargetProvenance:
        return TargetProvenance(
            self.target_id,
            f"python={self.python_version};filter={self.policy}",
            self.timeout_seconds,
        )

    @property
    def artifacts(self) -> tuple[ArtifactDigest, ...]:
        return (
            ArtifactDigest("python-tarfile-effect-worker", self.worker_sha256),
            ArtifactDigest("python-tarfile-module", self.tarfile_sha256),
        )

    def _verify_identity(self) -> None:
        value = _identify(self.backend, self.image_id)
        seen = (
            value.get("python_version"),
            value.get("tarfile_sha256"),
            value.get("worker_sha256"),
        )
        if seen != (self.python_version, self.tarfile_sha256, self.worker_sha256):
            raise RuntimeError("python-tarfile image identity changed after setup")

    def capture_isolation(self) -> IsolationProvenance:
        captured = self.backend.capture_isolation(self.image_id)
        self._verify_identity()
        return replace(
            captured, artifacts=self.artifacts, artifact_origin="image-identification-v1"
        )

    def command(self, archive_path: Path, extraction_root: Path) -> tuple[str, ...]:
        return (
            PYTHON,
            "-I",
            WORKER,
            "extract",
            str(archive_path),
            str(extraction_root),
            self.policy,
        )

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult:
        status = (
            ExecutionStatus.TIMED_OUT
            if outcome.exit_code is None
            else ExecutionStatus.SUCCESS
            if outcome.exit_code == 0
            else ExecutionStatus.REJECTED
            if outcome.exit_code == 2
            else ExecutionStatus.FAILED
        )
        return ExecutionResult(
            self.target_id,
            self.python_version,
            command,
            status,
            outcome.exit_code,
            outcome.stdout.decode("utf-8", "surrogateescape"),
            outcome.stderr.decode("utf-8", "surrogateescape"),
            outcome.duration_seconds,
            self.timeout_seconds,
        )

    @contextmanager
    def prepare(
        self, archive_path: Path, extraction_root: Path
    ) -> Iterator[Callable[[], PythonTarfileCapture]]:
        validate_run_paths(archive_path, extraction_root)
        self._verify_identity()
        command = self.command(archive_path, extraction_root)
        request = ContainerRequest(
            self.image_id, command, extraction_root.parent, self.timeout_seconds
        )
        with self.backend.prepare(request) as prepared:
            executed = False

            def execute() -> PythonTarfileCapture:
                nonlocal executed
                if executed:
                    raise RuntimeError("one prepared python-tarfile target executes exactly once")
                executed = True
                outcome = prepared.execute()
                execution = self.classify(outcome, command)
                members, error = parse_worker_output(outcome.stdout, outcome.output_truncated)
                return PythonTarfileCapture(execution, members, error)

            yield execute


def _identify(backend: ExecutionBackend, image_id: str) -> dict[str, Any]:
    stdout = identify_image(backend, image_id, (PYTHON, "-I", WORKER, "--identify"))
    try:
        value = json.loads(stdout)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("python-tarfile image returned invalid identity metadata") from error
    required = ("python_version", "tarfile_sha256", "worker_sha256", "has_data_filter")
    if not isinstance(value, dict) or any(key not in value for key in required):
        raise ValueError("python-tarfile image identity response is incomplete")
    return value

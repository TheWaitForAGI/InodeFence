"""Additional contained target restricted to the fixed benign fixture profile."""

import math
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from inodefence.execution.base import BackendError, ContainerOutcome, ExecutionBackend
from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import TargetProvenance
from inodefence.targets.isolated import IsolatedTarget, identify_image

from .encoding import decode, json_bytes, read_json
from .gnu_packaging import benign_profile_bytes, worker_bytes
from .verify import _digest, _read_file

PYTHON = "/usr/local/bin/python3.12"
WORKER = "/target/worker.py"
REPOSITORY = Path(__file__).resolve().parents[3]


def _binding(image_id: str, timeout: float) -> None:
    if not isinstance(image_id, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise ValueError("GNU target requires immutable image ID")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError("GNU target requires bounded positive timeout")


@dataclass(frozen=True, slots=True)
class GnuIdentity:
    python_version: str
    tar_version: str
    worker_sha256: str
    profile_sha256: str
    tar_binary_sha256: str
    python_binary_sha256: str

    def __post_init__(self) -> None:
        if self.python_version != "3.12.13" or self.tar_version != "1.34":
            raise ValueError("GNU benign target requires exact pinned runtime/version")
        for value in (
            self.worker_sha256,
            self.profile_sha256,
            self.tar_binary_sha256,
            self.python_binary_sha256,
        ):
            _digest(value)


@dataclass(frozen=True, slots=True)
class GnuTarInvocation:
    image_id: str
    identity: GnuIdentity
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        _binding(self.image_id, self.timeout_seconds)
        if not isinstance(self.identity, GnuIdentity) or (
            self.identity.worker_sha256 != sha256(worker_bytes(REPOSITORY)).hexdigest()
            or self.identity.profile_sha256 != sha256(benign_profile_bytes()).hexdigest()
        ):
            raise ValueError("GNU image must use current trusted fixed benign worker/profile")

    @classmethod
    def bind(
        cls, backend: ExecutionBackend, image_id: str, timeout_seconds: float = 10.0
    ) -> IsolatedTarget:
        if not isinstance(backend, ExecutionBackend):
            raise ValueError("trusted execution backend required")
        _binding(image_id, timeout_seconds)
        stdout = identify_image(backend, image_id, (PYTHON, WORKER, "--identify"))
        try:
            identity = decode(GnuIdentity, read_json(stdout))
            return IsolatedTarget(cls(image_id, identity, timeout_seconds), backend)
        except (ValueError, TypeError, OSError) as error:
            raise BackendError(f"invalid GNU benign target identity: {error}") from error

    @property
    def provenance(self) -> TargetProvenance:
        return TargetProvenance(
            "gnu-tar-benign",
            "gnu=1.34;python=3.12.13;profile=benign-fixtures-v1",
            self.timeout_seconds,
        )

    @property
    def artifacts(self) -> tuple[ArtifactDigest, ...]:
        return (
            ArtifactDigest("gnu-tar-binary", self.identity.tar_binary_sha256),
            ArtifactDigest("gnu-tar-profile", self.identity.profile_sha256),
            ArtifactDigest("gnu-tar-python-binary", self.identity.python_binary_sha256),
            ArtifactDigest("gnu-tar-worker", self.identity.worker_sha256),
        )

    @property
    def identity_command(self) -> tuple[str, ...]:
        return (PYTHON, WORKER, "--identify")

    def verify_identity(self, stdout: bytes) -> tuple[ArtifactDigest, ...]:
        try:
            actual = decode(GnuIdentity, read_json(stdout))
        except (ValueError, TypeError) as error:
            raise BackendError("invalid GNU identity observation") from error
        if actual != self.identity:
            raise BackendError("GNU execution identity changed after binding")
        return self.artifacts

    def command(self, archive_path: Path, extraction_root: Path) -> tuple[str, ...]:
        profile = read_json(benign_profile_bytes())
        assert isinstance(profile, dict)
        allowed = {case["archive_sha256"] for case in profile["cases"]}
        if sha256(_read_file(archive_path)).hexdigest() not in allowed or any(
            extraction_root.iterdir()
        ):
            raise BackendError("GNU target accepts only fixed benign TARs in fresh empty roots")
        return (
            PYTHON,
            WORKER,
            "--extract",
            str(archive_path),
            str(extraction_root),
            json_bytes(asdict(self.identity)).decode("ascii"),
        )

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult:
        if outcome.exit_code in {3, 4} or outcome.output_truncated:
            raise BackendError("GNU worker identity/profile/infrastructure invalid")
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
            self.provenance.target_id,
            self.provenance.target_version,
            command,
            status,
            outcome.exit_code,
            outcome.stdout.decode("utf-8", "surrogateescape"),
            outcome.stderr.decode("utf-8", "surrogateescape"),
            outcome.duration_seconds,
            self.timeout_seconds,
        )

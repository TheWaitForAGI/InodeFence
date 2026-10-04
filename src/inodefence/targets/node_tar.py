"""Node-specific command/version/status; execution is always composed containment."""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from inodefence.execution.base import (
    BackendError,
    ContainerOutcome,
    ExecutionBackend,
)
from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import TargetProvenance

from .isolated import IsolatedTarget, identify_image

NODE = "/usr/local/bin/node"
WORKER = "/target/worker.cjs"
MODULE = "/target/node_modules/tar"
LOCK = "/target/package-lock.json"


def _validate_binding(image_id: str, timeout: float) -> None:
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("target image requires an immutable SHA-256 image ID")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError("timeout_seconds must be finite, positive and at most 120 seconds")


def _identify(backend: ExecutionBackend, image_id: str) -> dict:
    stdout = identify_image(backend, image_id, (NODE, WORKER, "--identify", MODULE, LOCK))
    try:
        return json.loads(stdout)
    except ValueError as error:
        raise BackendError("node-tar image returned invalid metadata") from error


@dataclass(frozen=True, slots=True)
class NodeTarTarget:
    """Immutable expected identity; bind() discovers defaults inside its image.

    No local executable/package_root or direct subprocess API exists. The returned
    IsolatedTarget owns execution via the backend. Options remain strict=true,
    preservePaths=false and upstream defaults; metadata is never Oracle truth.
    Constructed/replaced values remain declarations. The wrapper must observe
    and verify them before provenance freeze and before archive execution.
    """

    image_id: str
    node_version: str
    tar_version: str
    worker_sha256: str
    package_lock_sha256: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        _validate_binding(self.image_id, self.timeout_seconds)
        for value in (self.node_version, self.tar_version):
            if (
                not isinstance(value, str)
                or re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", value) is None
            ):
                raise ValueError("target version must be exact semantic version text")
        for value in (self.worker_sha256, self.package_lock_sha256):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("worker/lock identity requires SHA-256")

    @classmethod
    def bind(
        cls, backend: ExecutionBackend, image_id: str, timeout_seconds: float = 10.0
    ) -> IsolatedTarget:
        if not isinstance(backend, ExecutionBackend):
            raise ValueError("target requires a trusted ExecutionBackend implementation")
        _validate_binding(image_id, timeout_seconds)
        value = _identify(backend, image_id)
        try:
            invocation = cls(
                image_id,
                value["node_version"],
                value["tar_version"],
                value["worker_sha256"],
                value["package_lock_sha256"],
                timeout_seconds,
            )
        except (KeyError, TypeError) as error:
            raise BackendError("node-tar image returned incomplete metadata") from error
        return IsolatedTarget(invocation, backend)

    @property
    def provenance(self) -> TargetProvenance:
        return TargetProvenance(
            "node-tar-strict",
            f"node={self.node_version};tar={self.tar_version}",
            self.timeout_seconds,
        )

    @property
    def artifacts(self) -> tuple[ArtifactDigest, ...]:
        """Expected digests; only verified probe output may enter isolation.artifacts."""
        return (
            ArtifactDigest("node-tar-package-lock", self.package_lock_sha256),
            ArtifactDigest("node-tar-worker", self.worker_sha256),
        )

    @property
    def identity_command(self) -> tuple[str, ...]:
        return (NODE, WORKER, "--identify", MODULE, LOCK)

    def verify_identity(self, stdout: bytes) -> tuple[ArtifactDigest, ...]:
        try:
            value = json.loads(stdout)
            observed = NodeTarTarget(
                self.image_id,
                value["node_version"],
                value["tar_version"],
                value["worker_sha256"],
                value["package_lock_sha256"],
                self.timeout_seconds,
            )
        except (ValueError, KeyError, TypeError) as error:
            raise BackendError("node-tar image returned invalid identity metadata") from error
        if observed != self:
            raise BackendError("node-tar execution identity changed after setup")
        return observed.artifacts

    def command(self, archive_path: Path, extraction_root: Path) -> tuple[str, ...]:
        return (
            NODE,
            WORKER,
            MODULE,
            str(archive_path),
            str(extraction_root),
            self.node_version,
            self.tar_version,
        )

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult:
        if outcome.exit_code == 3:
            raise RuntimeError("node-tar execution identity changed after setup")
        status = (
            ExecutionStatus.TIMED_OUT
            if outcome.exit_code is None
            else ExecutionStatus.SUCCESS
            if outcome.exit_code == 0
            else ExecutionStatus.REJECTED
            if outcome.exit_code == 2
            else ExecutionStatus.FAILED
        )
        declared = self.provenance
        return ExecutionResult(
            declared.target_id,
            declared.target_version,
            command,
            status,
            outcome.exit_code,
            outcome.stdout.decode("utf-8", "surrogateescape"),
            outcome.stderr.decode("utf-8", "surrogateescape"),
            outcome.duration_seconds,
            self.timeout_seconds,
        )

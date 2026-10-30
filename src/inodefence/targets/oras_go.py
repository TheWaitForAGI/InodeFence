"""oras-go-specific command/version/status; execution is always composed containment.

oras-go (a Go OCI registry client) is a SECOND, independent extractor for the
generality milestone (M4.1). This module is target-specific: it owns the worker
invocation, version identity probe and status classification for oras-go's
``content/file`` Store, which unpacks a directory artifact (a gzipped tar) to
disk. The generic model, Observer, Oracle and Feedback are unchanged -- oras-go's
post-extraction filesystem state is judged by the same C0/C1/C2 contracts as
node-tar. No CVE identifier, release string or answer path enters any verdict;
the release pins live only in the image recipe (``tools/oras-go/``).

``IsolatedTarget`` owns HOW-to-execute through a trusted ``ExecutionBackend``;
this descriptor only declares WHAT to execute. The worker runs the extraction
from the disposable sandbox root (isolated CWD), mirroring a caller that runs
``oras pull`` from a working directory and extracts into a subdirectory.
"""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from inodefence.execution.base import BackendError, ContainerOutcome, ExecutionBackend
from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import TargetProvenance

from .isolated import IsolatedTarget, identify_image

# Worker binary inside the pinned image (tools/oras-go/Dockerfile).
WORKER = "/target/oras-worker"
_ORAS_GO_VERSION = re.compile(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")
_GO_VERSION = re.compile(r"go\d+(?:\.\d+){1,2}(?:[a-z]+\d+)?")


def _validate_binding(image_id: str, timeout: float) -> None:
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("target image requires an immutable SHA-256 image ID")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError("timeout_seconds must be finite, positive and at most 120 seconds")


def _identify(backend: ExecutionBackend, image_id: str) -> dict:
    stdout = identify_image(backend, image_id, (WORKER, "identify"))
    try:
        return json.loads(stdout)
    except ValueError as error:
        raise BackendError("oras-go image returned invalid metadata") from error


@dataclass(frozen=True, slots=True)
class OrasGoTarget:
    """Immutable expected identity; bind() observes the pinned versions in its image.

    The returned IsolatedTarget owns execution via the backend. Versions and the
    worker digest are declarations until the wrapper observes and verifies them
    before provenance freeze and before archive execution; metadata is never
    Oracle truth. ID is oras-go, version oras-go=<exact>;go=<exact>.
    """

    image_id: str
    oras_go_version: str
    go_version: str
    worker_sha256: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        _validate_binding(self.image_id, self.timeout_seconds)
        if (
            not isinstance(self.oras_go_version, str)
            or _ORAS_GO_VERSION.fullmatch(self.oras_go_version) is None
        ):
            raise ValueError("oras-go version must be exact semantic version text (e.g. v2.6.1)")
        if not isinstance(self.go_version, str) or _GO_VERSION.fullmatch(self.go_version) is None:
            raise ValueError("go version must be exact toolchain version text (e.g. go1.25.14)")
        if not isinstance(self.worker_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.worker_sha256
        ):
            raise ValueError("worker identity requires SHA-256")

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
                value["oras_go_version"],
                value["go_version"],
                value["worker_sha256"],
                timeout_seconds,
            )
        except (KeyError, TypeError) as error:
            raise BackendError("oras-go image returned incomplete metadata") from error
        return IsolatedTarget(invocation, backend)

    @property
    def provenance(self) -> TargetProvenance:
        return TargetProvenance(
            "oras-go",
            f"oras-go={self.oras_go_version};go={self.go_version}",
            self.timeout_seconds,
        )

    @property
    def artifacts(self) -> tuple[ArtifactDigest, ...]:
        """Expected digest; only verified probe output may enter isolation.artifacts."""
        return (ArtifactDigest("oras-go-worker", self.worker_sha256),)

    @property
    def identity_command(self) -> tuple[str, ...]:
        return (WORKER, "identify")

    def verify_identity(self, stdout: bytes) -> tuple[ArtifactDigest, ...]:
        try:
            value = json.loads(stdout)
            observed = OrasGoTarget(
                self.image_id,
                value["oras_go_version"],
                value["go_version"],
                value["worker_sha256"],
                self.timeout_seconds,
            )
        except (ValueError, KeyError, TypeError) as error:
            raise BackendError("oras-go image returned invalid identity metadata") from error
        if observed != self:
            raise BackendError("oras-go execution identity changed after setup")
        return observed.artifacts

    def command(self, archive_path: Path, extraction_root: Path) -> tuple[str, ...]:
        return (WORKER, "extract", str(archive_path), str(extraction_root))

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult:
        status = (
            ExecutionStatus.TIMED_OUT
            if outcome.exit_code is None
            else ExecutionStatus.SUCCESS
            if outcome.exit_code == 0
            # Worker exit 2 = extraction refused/failed (a fixed release contains the
            # hardlink target inside the extraction root); any other nonzero = harness
            # or IO failure. The Observer/Oracle judge the actual post-state regardless.
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

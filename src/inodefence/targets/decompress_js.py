"""decompress-specific command/version/status; execution is always composed containment.

decompress (a JavaScript archive extractor, original kevva/decompress and its maintained fork
@xhmikosr/decompress) is a THIRD, independent extractor for the generality milestone (M4.2),
after node-tar and oras-go. This module is target-specific: it owns the worker invocation,
version identity probe and status classification. decompress uses the ``decompress-tar`` /
``tar-stream`` parser -- a different tar implementation than node-tar's ``tar`` -- and runs in
the same pinned-Node container tier. The generic model, Observer, Oracle and Feedback are
unchanged: decompress's post-extraction filesystem state is judged by the same C0/C1/C2
contracts. No CVE identifier, release string or answer path enters any verdict; the release
pins live only in the image recipe (``tools/decompress/``).

``IsolatedTarget`` owns HOW-to-execute through a trusted ``ExecutionBackend``; this descriptor
only declares WHAT to execute. The worker runs the extraction from the disposable sandbox root
(isolated CWD), mirroring a caller that extracts into a subdirectory.
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

# Node binary and worker inside the pinned image (tools/decompress/Dockerfile).
NODE = "/usr/local/bin/node"
WORKER = "/target/worker.cjs"
_SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")
_MODULE = re.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*")


def _validate_binding(image_id: str, timeout: float) -> None:
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("target image requires an immutable SHA-256 image ID")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError("timeout_seconds must be finite, positive and at most 120 seconds")


def _identify(backend: ExecutionBackend, image_id: str) -> dict:
    stdout = identify_image(backend, image_id, (NODE, WORKER, "identify"))
    try:
        return json.loads(stdout)
    except ValueError as error:
        raise BackendError("decompress image returned invalid metadata") from error


@dataclass(frozen=True, slots=True)
class DecompressJsTarget:
    """Immutable expected identity; bind() observes the pinned module/versions in its image.

    The returned IsolatedTarget owns execution via the backend. The decompress package name
    (``decompress`` or ``@xhmikosr/decompress``), its version, the Node version and the worker
    digest are declarations until the wrapper observes and verifies them before provenance
    freeze and before archive execution; metadata is never Oracle truth. ID is decompress,
    version decompress=<module>@<exact>;node=<exact>.
    """

    image_id: str
    decompress_module: str
    decompress_version: str
    node_version: str
    worker_sha256: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        _validate_binding(self.image_id, self.timeout_seconds)
        if (
            not isinstance(self.decompress_module, str)
            or _MODULE.fullmatch(self.decompress_module) is None
        ):
            raise ValueError("decompress module must be an npm package name")
        for value in (self.decompress_version, self.node_version):
            if not isinstance(value, str) or _SEMVER.fullmatch(value) is None:
                raise ValueError("version must be exact semantic version text (e.g. 4.2.1)")
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
                value["decompress_module"],
                value["decompress_version"],
                value["node_version"],
                value["worker_sha256"],
                timeout_seconds,
            )
        except (KeyError, TypeError) as error:
            raise BackendError("decompress image returned incomplete metadata") from error
        return IsolatedTarget(invocation, backend)

    @property
    def provenance(self) -> TargetProvenance:
        return TargetProvenance(
            "decompress",
            f"decompress={self.decompress_module}@{self.decompress_version};node={self.node_version}",
            self.timeout_seconds,
        )

    @property
    def artifacts(self) -> tuple[ArtifactDigest, ...]:
        """Expected digest; only verified probe output may enter isolation.artifacts."""
        return (ArtifactDigest("decompress-worker", self.worker_sha256),)

    @property
    def identity_command(self) -> tuple[str, ...]:
        return (NODE, WORKER, "identify")

    def verify_identity(self, stdout: bytes) -> tuple[ArtifactDigest, ...]:
        try:
            value = json.loads(stdout)
            observed = DecompressJsTarget(
                self.image_id,
                value["decompress_module"],
                value["decompress_version"],
                value["node_version"],
                value["worker_sha256"],
                self.timeout_seconds,
            )
        except (ValueError, KeyError, TypeError) as error:
            raise BackendError("decompress image returned invalid identity metadata") from error
        if observed != self:
            raise BackendError("decompress execution identity changed after setup")
        return observed.artifacts

    def command(self, archive_path: Path, extraction_root: Path) -> tuple[str, ...]:
        return (NODE, WORKER, "extract", str(archive_path), str(extraction_root))

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult:
        status = (
            ExecutionStatus.TIMED_OUT
            if outcome.exit_code is None
            else ExecutionStatus.SUCCESS
            if outcome.exit_code == 0
            # Worker exit 2 = extraction refused/failed (a fixed release contains the hardlink
            # target inside the extraction root); any other nonzero = harness/IO failure. The
            # Observer/Oracle judge the actual post-state regardless.
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

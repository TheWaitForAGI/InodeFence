"""decompress self-discovery (M4) adapter: the ``frame`` worker invocation.

This is the fuzz-target twin of ``decompress_js.DecompressJsTarget``. Where that adapter runs the
``extract`` subcommand for the controlled-reference generality differential, this one runs the
``frame`` subcommand: real decompress with its callback ``fs`` functions wrapped, emitting one
``inodefence-boundary-attempt-v1`` stdout frame (an unordered SET of per-operation boundary
attempts). That frame is the FEASIBLE observation channel for decompress self-discovery --
``experiments/repro/decompress_entry_effect_feasibility.py`` recorded (observed) that the ordered,
entry-correlated effect stream node-tar exposes is NOT exposable for decompress within the safety
boundary, while this set-based signal is.

It shares decompress's immutable image identity, version probe and status classification with
``DecompressJsTarget`` (imported, not re-derived); only the executed subcommand and the provenance
target id differ. The generic Observer/Oracle/Feedback are unchanged: the frame feeds the existing
``feedback.boundary_attempt_frame.frame_boundary_attempt_keys`` normalizer, and the C0/C1/C2 verdict
is still the production oracle on the before/after snapshots. No CVE identifier, release string or
answer path enters any verdict or the mutation vocabulary (D005/D006).
"""

import re
from dataclasses import dataclass
from pathlib import Path

from inodefence.execution.base import BackendError, ContainerOutcome, ExecutionBackend
from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import TargetProvenance

from .decompress_js import NODE, WORKER, _identify, _validate_binding
from .isolated import IsolatedTarget

# A distinct target id so the ExecutionResult/provenance never reads as the generality `extract`
# adapter; the version string keeps the same decompress=<module>@<ver>;node=<ver> identity shape.
_FRAME_TARGET_ID = "decompress-boundary-attempt-frame"
_SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")
_MODULE = re.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*")


@dataclass(frozen=True, slots=True)
class DecompressFrameTarget:
    """Immutable expected identity; ``bind`` observes the pinned module/versions in its image.

    Mirrors ``DecompressJsTarget`` (same identity fields and probe) but ``command`` runs the
    ``frame`` subcommand, so execution emits the boundary-attempt frame on stdout. The returned
    ``IsolatedTarget`` owns execution via the trusted backend; metadata is never Oracle truth.
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
            _FRAME_TARGET_ID,
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
        import json

        try:
            value = json.loads(stdout)
            observed = DecompressFrameTarget(
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
        return (NODE, WORKER, "frame", str(archive_path), str(extraction_root))

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult:
        status = (
            ExecutionStatus.TIMED_OUT
            if outcome.exit_code is None
            else ExecutionStatus.SUCCESS
            if outcome.exit_code == 0
            # Worker exit 2 = extraction refused/failed; the frame is still on stdout (a refused
            # attempt is an observed attempt). Any other nonzero = harness/IO failure. The
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

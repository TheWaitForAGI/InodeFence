"""oras-go self-discovery (M4) adapter: the ``frame`` worker invocation.

This is the fuzz-target twin of ``oras_go.OrasGoTarget``. Where that adapter runs the ``extract``
subcommand for the controlled-reference generality differential (M4.1), this one runs the
``frame`` subcommand: the SAME real oras-go ``content/file`` Store extraction, after which the
worker derives one ``inodefence-boundary-attempt-v1`` stdout frame from the OBSERVED
post-extraction filesystem state (an unordered SET of per-operation boundary attempts). That frame
is the feasible self-discovery observation channel for oras-go.

oras-go is a compiled third-party extractor, so its ``os.Link`` / ``os.Symlink`` calls cannot be
wrapped from the worker without forking oras-go (decompress could wrap its JS callback ``fs``; this
one cannot). The feasible channel is therefore the post-state SET -- narrower than decompress's
fs-wrap set, because a cleanly refused/errored link leaves no object and so is NOT observed here.
The independent Observer/Oracle before/after verdict is unaffected (the C0/C1/C2 "hit" never
depends on the frame).

It shares oras-go's immutable image identity, version probe and status classification with
``OrasGoTarget`` (imported, not re-derived); only the executed subcommand and the provenance target
id differ. The generic model, Observer, Oracle and Feedback are unchanged: the frame feeds the
existing ``feedback.boundary_attempt_frame.frame_boundary_attempt_keys`` normalizer, and the
C0/C1/C2 verdict is still the production oracle on the before/after snapshots. No CVE identifier,
release string or answer path enters any verdict or the mutation vocabulary (D005/D006).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from inodefence.execution.base import BackendError, ContainerOutcome, ExecutionBackend
from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import TargetProvenance

from .isolated import IsolatedTarget
from .oras_go import _GO_VERSION, _ORAS_GO_VERSION, WORKER, _identify, _validate_binding

# A distinct target id so the ExecutionResult/provenance never reads as the generality `extract`
# adapter; the version string keeps the same oras-go=<exact>;go=<exact> identity shape.
_FRAME_TARGET_ID = "oras-go-boundary-attempt-frame"


@dataclass(frozen=True, slots=True)
class OrasGoFrameTarget:
    """Immutable expected identity; ``bind`` observes the pinned versions in its image.

    Mirrors ``OrasGoTarget`` (same identity fields and probe) but ``command`` runs the ``frame``
    subcommand, so execution emits the boundary-attempt frame on stdout. The returned
    ``IsolatedTarget`` owns execution via the trusted backend; metadata is never Oracle truth.
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
            _FRAME_TARGET_ID,
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
            observed = OrasGoFrameTarget(
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
        return (WORKER, "frame", str(archive_path), str(extraction_root))

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult:
        status = (
            ExecutionStatus.TIMED_OUT
            if outcome.exit_code is None
            else ExecutionStatus.SUCCESS
            if outcome.exit_code == 0
            # Worker exit 2 = extraction refused/failed; the frame is still on stdout (the
            # post-state of a partial/failed extraction is still observed). Any other nonzero =
            # harness/IO failure. The Observer/Oracle judge the actual post-state regardless.
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

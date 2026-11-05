"""Rust ``tar`` crate frame adapter: the ``frame`` worker invocation (boundary-attempt channel).

This is the fuzz-target twin of ``rust_tar.RustTarTarget``, mirroring ``oras_go_effect``. Where that
adapter runs the ``extract`` subcommand (controlled reference / fixture runs), this one runs the
``frame`` subcommand: the SAME real ``Archive::unpack`` extraction, after which the worker derives
one ``inodefence-boundary-attempt-v1`` stdout frame from the OBSERVED post-extraction filesystem
state (an unordered SET of per-operation boundary attempts) -- the frame the existing oras-go frame
pipeline (``effect_pipeline_oras_go.run_oras_go_frame_case``) already parses and the sanctioned
``feedback.boundary_attempt_frame.frame_boundary_attempt_keys`` normalizer already consumes.

The crate is compiled into the worker, so its ``std::fs`` link/symlink calls cannot be wrapped
without forking it; the feasible channel is therefore the post-state SET, exactly as for oras-go
(a cleanly refused/errored link leaves no object and is NOT observed here). The independent
Observer/Oracle before/after verdict is unaffected (the C0/C1/C2 "hit" never depends on the frame).

No campaign mode is wired to this adapter: under the Tier-B discipline (D039) the target is fixture
probed and registered before any fuzzing campaign runs. It shares the immutable image identity,
version probe and status classification with ``RustTarTarget`` (imported, not re-derived); only the
executed subcommand and the provenance target id differ. No advisory identifier, release string or
answer path enters any verdict or the mutation vocabulary (D005/D006).
"""

import json
from dataclasses import dataclass
from pathlib import Path

from inodefence.execution.base import BackendError, ContainerOutcome, ExecutionBackend
from inodefence.model import ExecutionResult
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import TargetProvenance

from .isolated import IsolatedTarget
from .rust_tar import (
    WORKER,
    _identify,
    _identity_values,
    _validate_binding,
    _validate_identity,
    classify_worker_outcome,
)

# A distinct target id so the ExecutionResult/provenance never reads as the `extract` adapter; the
# version string keeps the same tar=<exact>;rustc=<exact> identity shape.
_FRAME_TARGET_ID = "rust-tar-boundary-attempt-frame"


@dataclass(frozen=True, slots=True)
class RustTarFrameTarget:
    """Immutable expected identity; ``bind`` observes the pinned versions in its image.

    Mirrors ``RustTarTarget`` (same identity fields and probe) but ``command`` runs the ``frame``
    subcommand, so execution emits the boundary-attempt frame on stdout. The returned
    ``IsolatedTarget`` owns execution via the trusted backend; metadata is never Oracle truth.
    """

    image_id: str
    tar_crate_version: str
    rustc_version: str
    cargo_lock_sha256: str
    worker_sha256: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        _validate_binding(self.image_id, self.timeout_seconds)
        _validate_identity(
            self.tar_crate_version, self.rustc_version, self.cargo_lock_sha256, self.worker_sha256
        )

    @classmethod
    def bind(
        cls, backend: ExecutionBackend, image_id: str, timeout_seconds: float = 10.0
    ) -> IsolatedTarget:
        if not isinstance(backend, ExecutionBackend):
            raise ValueError("target requires a trusted ExecutionBackend implementation")
        _validate_binding(image_id, timeout_seconds)
        value = _identify(backend, image_id)
        try:
            invocation = cls(image_id, *_identity_values(value), timeout_seconds)
        except (KeyError, TypeError) as error:
            raise BackendError("rust tar image returned incomplete metadata") from error
        return IsolatedTarget(invocation, backend)

    @property
    def provenance(self) -> TargetProvenance:
        return TargetProvenance(
            _FRAME_TARGET_ID,
            f"tar={self.tar_crate_version};rustc={self.rustc_version}",
            self.timeout_seconds,
        )

    @property
    def artifacts(self) -> tuple[ArtifactDigest, ...]:
        """Expected digests; only verified probe output may enter isolation.artifacts."""
        return (
            ArtifactDigest("rust-tar-cargo-lock", self.cargo_lock_sha256),
            ArtifactDigest("rust-tar-worker", self.worker_sha256),
        )

    @property
    def identity_command(self) -> tuple[str, ...]:
        return (WORKER, "identify")

    def verify_identity(self, stdout: bytes) -> tuple[ArtifactDigest, ...]:
        try:
            observed = RustTarFrameTarget(
                self.image_id, *_identity_values(json.loads(stdout)), self.timeout_seconds
            )
        except (ValueError, KeyError, TypeError) as error:
            raise BackendError("rust tar image returned invalid identity metadata") from error
        if observed != self:
            raise BackendError("rust tar execution identity changed after setup")
        return observed.artifacts

    def command(self, archive_path: Path, extraction_root: Path) -> tuple[str, ...]:
        return (WORKER, "frame", str(archive_path), str(extraction_root))

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult:
        # Exit 2 = extraction refused/failed; the frame is still on stdout (the post-state of a
        # partial/failed extraction is still observed).
        return classify_worker_outcome(self.provenance, self.timeout_seconds, outcome, command)

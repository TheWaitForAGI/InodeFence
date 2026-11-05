"""Rust ``tar`` crate command/version/status; execution is always composed containment.

The Rust ``tar`` crate (tar-rs) is a Tier-B extractor of a new lineage (D039, 지웅 결정 8): a
compiled Rust library, independent of node-tar, oras-go (Go), decompress (JS) and Python tarfile.
This module is target-specific: it owns the worker invocation, version identity probe and status
classification for the crate's standard ``Archive::unpack`` path with default settings. The generic
model, Observer, Oracle and Feedback are unchanged -- the crate's post-extraction filesystem state
is judged by the same C0/C1/C2 contracts as node-tar. No advisory identifier, release string or
answer path enters any verdict; the release pins live only in the image recipe
(``tools/rust-tar/``).

``IsolatedTarget`` owns HOW-to-execute through a trusted ``ExecutionBackend``; this descriptor
only declares WHAT to execute. The worker runs the extraction from the disposable sandbox root
(isolated CWD), exactly like the oras-go worker whose protocol it shares.
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

# Worker binary inside the pinned image (tools/rust-tar/Dockerfile).
WORKER = "/target/rust-tar-worker"
# Keys of the worker's ``identify`` JSON (tools/rust-tar/worker/src/main.rs).
IDENTITY_KEYS = ("tar_crate_version", "rustc_version", "cargo_lock_sha256", "worker_sha256")
_SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _validate_binding(image_id: str, timeout: float) -> None:
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("target image requires an immutable SHA-256 image ID")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError("timeout_seconds must be finite, positive and at most 120 seconds")


def _validate_identity(
    tar_crate_version: str, rustc_version: str, cargo_lock_sha256: str, worker_sha256: str
) -> None:
    if not isinstance(tar_crate_version, str) or _SEMVER.fullmatch(tar_crate_version) is None:
        raise ValueError("tar crate version must be exact semantic version text (e.g. 0.4.35)")
    if not isinstance(rustc_version, str) or _SEMVER.fullmatch(rustc_version) is None:
        raise ValueError("rustc version must be exact toolchain version text (e.g. 1.99.1)")
    for digest in (cargo_lock_sha256, worker_sha256):
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ValueError("Cargo.lock and worker identity require lowercase SHA-256")


def _identity_values(value: object) -> tuple[str, str, str, str]:
    """The four identity fields of an ``identify`` JSON object, in ``IDENTITY_KEYS`` order."""
    if not isinstance(value, dict):
        raise TypeError("identity metadata must be a JSON object")
    tar_crate, rustc, lock, worker = (value[key] for key in IDENTITY_KEYS)
    return tar_crate, rustc, lock, worker


def _identify(backend: ExecutionBackend, image_id: str) -> dict:
    stdout = identify_image(backend, image_id, (WORKER, "identify"))
    try:
        return json.loads(stdout)
    except ValueError as error:
        raise BackendError("rust tar image returned invalid metadata") from error


@dataclass(frozen=True, slots=True)
class RustTarTarget:
    """Immutable expected identity; bind() observes the pinned versions in its image.

    The returned IsolatedTarget owns execution via the backend. Versions and the lock/worker
    digests are declarations until the wrapper observes and verifies them before provenance freeze
    and before archive execution; metadata is never Oracle truth. ID is rust-tar, version
    tar=<exact>;rustc=<exact>. The Cargo.lock digest equals the committed role lock, so it doubles
    as the preregistration ``lock_digest`` binding of this target.
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
            "rust-tar",
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
            observed = RustTarTarget(
                self.image_id, *_identity_values(json.loads(stdout)), self.timeout_seconds
            )
        except (ValueError, KeyError, TypeError) as error:
            raise BackendError("rust tar image returned invalid identity metadata") from error
        if observed != self:
            raise BackendError("rust tar execution identity changed after setup")
        return observed.artifacts

    def command(self, archive_path: Path, extraction_root: Path) -> tuple[str, ...]:
        return (WORKER, "extract", str(archive_path), str(extraction_root))

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult:
        return classify_worker_outcome(self.provenance, self.timeout_seconds, outcome, command)


def classify_worker_outcome(
    declared: TargetProvenance,
    timeout_seconds: float,
    outcome: ContainerOutcome,
    command: tuple[str, ...],
) -> ExecutionResult:
    """Map the shared worker exit protocol (same as oras-go) to an ExecutionResult.

    Worker exit 2 = extraction refused/failed by the crate; any other nonzero = harness or IO
    failure; no exit code = timeout. The Observer/Oracle judge the actual post-state regardless.
    """
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
        declared.target_id,
        declared.target_version,
        command,
        status,
        outcome.exit_code,
        outcome.stdout.decode("utf-8", "surrogateescape"),
        outcome.stderr.decode("utf-8", "surrogateescape"),
        outcome.duration_seconds,
        timeout_seconds,
    )

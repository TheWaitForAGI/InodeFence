"""Infrastructure-invalid attempts, separate from target statuses and verdicts."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from inodefence.model import SnapshotPhase, StateSnapshot
from inodefence.model.provenance import SourceProvenance, TargetProvenance

from .storage import read_record, write_record
from .verify import _digest


class FailurePhase(StrEnum):
    QUALIFICATION = "qualification"
    SETUP = "setup"
    BUILD = "build"
    BEFORE = "before"
    EXECUTION = "execution"
    AFTER = "after"
    DERIVATION = "derivation"
    PUBLICATION = "publication"
    CLEANUP = "cleanup"
    UNKNOWN = "unknown"


class CleanupStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_RUN = "not_run"
    UNKNOWN = "unknown"


def _text(value: str) -> None:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("identifier/diagnostic must be nonempty text without NUL")


def _index(value: int | None) -> None:
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("step index must be nonnegative integer or unavailable")


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """Caller-recorded digest of an available artifact, not proof it still exists."""

    name: str
    sha256: str

    def __post_init__(self) -> None:
        _text(self.name)
        _digest(self.sha256)


@dataclass(frozen=True, slots=True)
class FailureContext:
    """Only evidence actually available to the caller; None means unavailable."""

    attempt_id: str
    experiment_id: str
    source: SourceProvenance
    target: TargetProvenance | None
    step_index: int | None
    phase: FailurePhase
    last_fully_completed_step: int | None = None
    config_id: str | None = None
    diagnostics: tuple[str, ...] = ()
    stdout: str | None = None
    stderr: str | None = None
    before: StateSnapshot | None = None
    after: StateSnapshot | None = None
    cleanup_status: CleanupStatus = CleanupStatus.UNKNOWN
    cleanup_diagnostics: tuple[str, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()

    def __post_init__(self) -> None:
        _text(self.attempt_id)
        _text(self.experiment_id)
        _index(self.step_index)
        _index(self.last_fully_completed_step)
        if self.config_id is not None:
            _digest(self.config_id)
        if not isinstance(self.source, SourceProvenance) or (
            self.target is not None and not isinstance(self.target, TargetProvenance)
        ):
            raise ValueError("invalid available source/target provenance")
        if not isinstance(self.phase, FailurePhase) or not isinstance(
            self.cleanup_status, CleanupStatus
        ):
            raise ValueError("explicit phase and cleanup status required")
        if (
            self.step_index is not None
            and self.last_fully_completed_step is not None
            and self.last_fully_completed_step > self.step_index
        ):
            raise ValueError("completed step cannot be after the attempted step")
        for values in (self.diagnostics, self.cleanup_diagnostics):
            if not isinstance(values, tuple):
                raise ValueError("diagnostics must be an immutable tuple")
            for value in values:
                _text(value)
        if any(
            value is not None and not isinstance(value, str) for value in (self.stdout, self.stderr)
        ):
            raise ValueError("available logs must be text or None")
        for snapshot, phase in (
            (self.before, SnapshotPhase.BEFORE),
            (self.after, SnapshotPhase.AFTER),
        ):
            if snapshot is not None and (
                not isinstance(snapshot, StateSnapshot) or snapshot.phase != phase
            ):
                raise ValueError("available snapshot has incorrect lifecycle phase")
        if (
            self.before is not None
            and self.after is not None
            and (
                self.before.sandbox_root != self.after.sandbox_root
                or self.before.protected_paths != self.after.protected_paths
            )
        ):
            raise ValueError("available snapshots must describe the same attempt")
        if (
            not isinstance(self.artifacts, tuple)
            or not all(isinstance(item, ArtifactReference) for item in self.artifacts)
            or len({item.name for item in self.artifacts}) != len(self.artifacts)
        ):
            raise ValueError("artifact references must have unique names")


@dataclass(frozen=True, slots=True)
class FailureRecord:
    classification: str
    context: FailureContext
    exception_type: str
    exception_message: str
    recorded_at: str

    def __post_init__(self) -> None:
        if self.classification != "infrastructure_invalid" or not isinstance(
            self.context, FailureContext
        ):
            raise ValueError("ledger records are infrastructure invalid, never target outcomes")
        _text(self.exception_type)
        if not isinstance(self.exception_message, str):
            raise ValueError("exception message must be text")
        timestamp = datetime.fromisoformat(self.recorded_at)
        if timestamp.utcoffset() is None:
            raise ValueError("record timestamp requires a timezone")


def failure_record(exception: Exception, context: FailureContext) -> FailureRecord:
    """Capture actual exception identity/message and current record time.

    No fabricated execution duration, after snapshot, cleanup success or
    nonviolation. Exception handling and completed evidence remain caller-owned.
    """
    if not isinstance(exception, Exception):
        raise ValueError("expected an infrastructure exception")
    kind = type(exception)
    return FailureRecord(
        "infrastructure_invalid",
        context,
        f"{kind.__module__}.{kind.__qualname__}",
        str(exception),
        datetime.now(UTC).isoformat(),
    )


def write_failure(path: Path, record: FailureRecord) -> str:
    if not isinstance(record, FailureRecord):
        raise ValueError("expected a FailureRecord")
    return write_record(path, record)


def read_failure(path: Path, *, expected_sha256: str | None = None) -> FailureRecord:
    return read_record(path, FailureRecord, expected_sha256=expected_sha256)

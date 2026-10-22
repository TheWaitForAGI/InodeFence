"""No-overwrite host-attempt evidence for the frozen Track A schedule.

The launch path must receive the pilot digest and approval reference from the
trusted human-controlled channel and revalidate the original pilot/N05 bytes.
The records written here retain that integrity binding; they do not authenticate
the named human and are not serialized admission capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from inodefence.execution.docker_client import OUTPUT_LIMIT

from .failure import ArtifactReference, _text
from .policy_repeated import PolicyRunSlot
from .repeated import RunState
from .storage import publish_bytes, read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file

if TYPE_CHECKING:
    from .track_a_admission import VerifiedTrackAAdmission
    from .track_a_exploratory import VerifiedTrackAExecution


HOST_ADMISSION_NAME = "admission/verified-admission.json"
HOST_ATTEMPT_FORMAT = "track-a-host-attempt-v1"


def _timestamp(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("timestamp requires a UTC offset")


def _absolute_path(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be explicit")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    return path


def _attempt_directory(index: int, run_id: str) -> str:
    return f"{index:02d}-{run_id}"


def _campaign_artifact(slot: PolicyRunSlot, name: str, digest: str) -> ArtifactReference:
    return ArtifactReference(f"repetitions/{slot.result_directory}/{name}", digest)


class TrackAHostAttemptStatus(StrEnum):
    COMPLETE = "complete"
    FAILED = "failed"


class TrackAHostCleanupStatus(StrEnum):
    NOT_NEEDED = "not_needed"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TrackAHostAdmissionRecord:
    """Retained launch binding; not proof of reviewer identity or approval."""

    serialization_schema: ClassVar[int] = 1

    authorization_id: str
    approval_reference: str
    pilot_authorization_path: str
    pilot_authorization_sha256: str
    output_root: str
    host_ledger_root: str
    execution: ArtifactReference
    track_a_admission: ArtifactReference
    repetition_plan: ArtifactReference
    n05_host_manifest_sha256: str
    n05_final_manifest_sha256: str
    source_revision: str
    evidence_role: str = "retained-integrity-binding-not-human-authentication"

    def __post_init__(self) -> None:
        _text(self.authorization_id)
        _text(self.approval_reference)
        _absolute_path(self.pilot_authorization_path, "pilot authorization path")
        output_root = _absolute_path(self.output_root, "Track A output root")
        host_root = _absolute_path(self.host_ledger_root, "Track A host ledger root")
        for value in (
            self.pilot_authorization_sha256,
            self.n05_host_manifest_sha256,
            self.n05_final_manifest_sha256,
        ):
            _digest(value)
        if (
            output_root == host_root
            or not isinstance(self.execution, ArtifactReference)
            or self.execution.name != "execution.json"
            or not isinstance(self.track_a_admission, ArtifactReference)
            or self.track_a_admission.name != "admission/verified-admission.json"
            or not isinstance(self.repetition_plan, ArtifactReference)
            or self.repetition_plan.name != "repetitions/plan.json"
            or self.evidence_role != "retained-integrity-binding-not-human-authentication"
        ):
            raise ValueError("invalid Track A host admission binding")
        _text(self.source_revision)


@dataclass(frozen=True, slots=True)
class TrackAHostAttemptStarted:
    serialization_schema: ClassVar[int] = 1

    attempt_id: str
    run_index: int
    run_id: str
    config_id: str
    execution_sha256: str
    plan_sha256: str
    host_admission: ArtifactReference
    output_root: str
    started_at: str
    state: str = "started"

    def __post_init__(self) -> None:
        _text(self.attempt_id)
        if type(self.run_index) is not int or self.run_index < 0:
            raise ValueError("host attempt requires a nonnegative run index")
        _text(self.run_id)
        _digest(self.config_id)
        _digest(self.execution_sha256)
        _digest(self.plan_sha256)
        if (
            not isinstance(self.host_admission, ArtifactReference)
            or self.host_admission.name != HOST_ADMISSION_NAME
            or self.state != "started"
        ):
            raise ValueError("invalid host attempt start binding")
        _absolute_path(self.output_root, "Track A output root")
        _timestamp(self.started_at)


@dataclass(frozen=True, slots=True)
class TrackAControllerTerminal:
    """Successful controller acknowledgement sent over the broker channel."""

    serialization_schema: ClassVar[int] = 1

    attempt_id: str
    run_index: int
    run_id: str
    execution_sha256: str
    plan_sha256: str
    state: RunState
    completed_steps: int
    campaign_claim: ArtifactReference
    campaign_terminal: ArtifactReference
    controller_memory_sha256: str
    classification: str = "track-a-cell-terminal-v2"

    def __post_init__(self) -> None:
        _text(self.attempt_id)
        if type(self.run_index) is not int or self.run_index < 0:
            raise ValueError("controller result requires a nonnegative run index")
        _text(self.run_id)
        _digest(self.execution_sha256)
        _digest(self.plan_sha256)
        _digest(self.controller_memory_sha256)
        if (
            self.state != RunState.COMPLETED
            or type(self.completed_steps) is not int
            or self.completed_steps < 1
            or not isinstance(self.campaign_claim, ArtifactReference)
            or not self.campaign_claim.name.endswith("/claim.json")
            or not isinstance(self.campaign_terminal, ArtifactReference)
            or not self.campaign_terminal.name.endswith("/terminal.json")
            or self.classification != "track-a-cell-terminal-v2"
        ):
            raise ValueError("invalid Track A controller terminal")


@dataclass(frozen=True, slots=True)
class TrackAHostAttemptTerminal:
    serialization_schema: ClassVar[int] = 1

    attempt_id: str
    run_index: int
    run_id: str
    execution_sha256: str
    plan_sha256: str
    host_admission: ArtifactReference
    started: ArtifactReference
    controller_stderr: ArtifactReference
    controller_stderr_size: int
    controller_stderr_truncated: bool
    controller_stderr_capture_complete: bool
    controller_launched: bool
    controller_returncode: int | None
    controller_terminal: TrackAControllerTerminal | None
    deadline_expired: bool
    cleanup_status: TrackAHostCleanupStatus
    cleanup_errors: tuple[str, ...]
    campaign_state: RunState
    campaign_claim: ArtifactReference | None
    campaign_terminal: ArtifactReference | None
    target_executions: int
    exception: str | None
    started_at: str
    ended_at: str
    status: TrackAHostAttemptStatus

    def __post_init__(self) -> None:
        _text(self.attempt_id)
        if type(self.run_index) is not int or self.run_index < 0:
            raise ValueError("host terminal requires a nonnegative run index")
        _text(self.run_id)
        _digest(self.execution_sha256)
        _digest(self.plan_sha256)
        if (
            not isinstance(self.host_admission, ArtifactReference)
            or self.host_admission.name != HOST_ADMISSION_NAME
            or not isinstance(self.started, ArtifactReference)
            or self.started.name != "started.json"
            or not isinstance(self.controller_stderr, ArtifactReference)
            or self.controller_stderr.name != "controller-stderr.bin"
            or type(self.controller_stderr_size) is not int
            or not 0 <= self.controller_stderr_size <= OUTPUT_LIMIT
            or type(self.controller_stderr_truncated) is not bool
            or type(self.controller_stderr_capture_complete) is not bool
            or type(self.controller_launched) is not bool
            or (
                self.controller_returncode is not None
                and type(self.controller_returncode) is not int
            )
            or (
                self.controller_terminal is not None
                and not isinstance(self.controller_terminal, TrackAControllerTerminal)
            )
            or type(self.deadline_expired) is not bool
            or not isinstance(self.cleanup_status, TrackAHostCleanupStatus)
            or not isinstance(self.cleanup_errors, tuple)
            or not all(isinstance(item, str) and item for item in self.cleanup_errors)
            or (self.cleanup_status == TrackAHostCleanupStatus.FAILED) != bool(self.cleanup_errors)
            or not isinstance(self.campaign_state, RunState)
            or type(self.target_executions) is not int
            or self.target_executions < 0
            or (
                self.exception is not None
                and (not isinstance(self.exception, str) or not self.exception)
            )
            or not isinstance(self.status, TrackAHostAttemptStatus)
        ):
            raise ValueError("invalid Track A host terminal")
        if self.controller_stderr_truncated and self.controller_stderr_size != OUTPUT_LIMIT:
            raise ValueError("truncated controller stderr must fill the retained bound")
        if not self.controller_launched and (
            self.controller_returncode is not None
            or self.controller_terminal is not None
            or self.deadline_expired
            or self.cleanup_status != TrackAHostCleanupStatus.NOT_NEEDED
        ):
            raise ValueError("unlaunched controller cannot have process or cleanup results")
        if self.controller_terminal is not None and self.controller_returncode != 0:
            raise ValueError("controller terminal requires a zero controller exit")
        if self.campaign_state == RunState.PENDING and (
            self.campaign_claim is not None
            or self.campaign_terminal is not None
            or self.target_executions != 0
        ):
            raise ValueError("pending campaign must retain zero target executions and no claim")
        if self.campaign_claim is None and self.campaign_terminal is not None:
            raise ValueError("campaign terminal cannot exist without a claim")
        if self.campaign_claim is not None and not self.campaign_claim.name.endswith("/claim.json"):
            raise ValueError("invalid campaign claim reference")
        if self.campaign_terminal is not None and not self.campaign_terminal.name.endswith(
            "/terminal.json"
        ):
            raise ValueError("invalid campaign terminal reference")
        _timestamp(self.started_at)
        _timestamp(self.ended_at)
        if datetime.fromisoformat(self.ended_at) < datetime.fromisoformat(self.started_at):
            raise ValueError("host attempt ended before it started")


@dataclass(frozen=True, slots=True)
class TrackAHostAttemptManifest:
    serialization_schema: ClassVar[int] = 1

    format: str
    attempt_id: str
    run_index: int
    run_id: str
    execution_sha256: str
    plan_sha256: str
    host_admission: ArtifactReference
    started: ArtifactReference
    controller_stderr: ArtifactReference
    terminal: ArtifactReference
    status: TrackAHostAttemptStatus

    def __post_init__(self) -> None:
        if self.format != HOST_ATTEMPT_FORMAT:
            raise ValueError("unsupported Track A host attempt format")
        _text(self.attempt_id)
        if type(self.run_index) is not int or self.run_index < 0:
            raise ValueError("manifest requires a nonnegative run index")
        _text(self.run_id)
        _digest(self.execution_sha256)
        _digest(self.plan_sha256)
        if (
            not isinstance(self.host_admission, ArtifactReference)
            or self.host_admission.name != HOST_ADMISSION_NAME
            or not isinstance(self.started, ArtifactReference)
            or self.started.name != "started.json"
            or not isinstance(self.controller_stderr, ArtifactReference)
            or self.controller_stderr.name != "controller-stderr.bin"
            or not isinstance(self.terminal, ArtifactReference)
            or self.terminal.name != "terminal.json"
            or not isinstance(self.status, TrackAHostAttemptStatus)
        ):
            raise ValueError("invalid Track A host attempt manifest")


@dataclass(frozen=True, slots=True)
class VerifiedTrackAHostAdmission:
    """Process value from fresh trusted-anchor validation; never serialize this object."""

    record: TrackAHostAdmissionRecord
    execution: VerifiedTrackAExecution
    original_admission: VerifiedTrackAAdmission


@dataclass(frozen=True, slots=True)
class ClaimedTrackAHostAttempt:
    started: TrackAHostAttemptStarted
    started_sha256: str
    directory: Path


@dataclass(frozen=True, slots=True)
class VerifiedTrackAHostAttempt:
    admission: TrackAHostAdmissionRecord
    admission_sha256: str
    started: TrackAHostAttemptStarted
    started_sha256: str
    terminal: TrackAHostAttemptTerminal
    terminal_sha256: str
    manifest: TrackAHostAttemptManifest
    manifest_sha256: str
    controller_stderr: bytes
    execution: VerifiedTrackAExecution


@dataclass(frozen=True, slots=True)
class TrackAHostLedgerSnapshot:
    admission: TrackAHostAdmissionRecord
    admission_sha256: str
    execution: VerifiedTrackAExecution
    attempts: tuple[VerifiedTrackAHostAttempt, ...]


def _require_next_slot(execution: VerifiedTrackAExecution, index: int) -> PolicyRunSlot:
    slots = execution.repetitions.slots
    if type(index) is not int or not 0 <= index < len(slots):
        raise ValueError("Track A run index is outside the frozen schedule")
    if any(slot.state != RunState.COMPLETED for slot in slots[:index]):
        raise ValueError("Track A execution must stop after a prior non-complete slot")
    if slots[index].state != RunState.PENDING or any(
        slot.state != RunState.PENDING for slot in slots[index:]
    ):
        raise ValueError("Track A executes the next pending cell exactly once in order")
    return slots[index]


def validate_track_a_host_admission(
    root: Path,
    *,
    expected_execution_sha256: str,
    pilot_authorization_path: Path,
    expected_pilot_authorization_sha256: str,
    trusted_approval_reference: str,
    protocol_config_path: Path | None = None,
) -> VerifiedTrackAHostAdmission:
    """Reopen the original approval/N05 graph using the launcher's trusted anchors."""
    from .track_a_admission import revalidate_retained_track_a_admission
    from .track_a_exploratory import read_track_a_execution

    try:
        execution = read_track_a_execution(
            root,
            expected_execution_sha256=expected_execution_sha256,
            protocol_config_path=protocol_config_path,
        )
        retained = execution.admission
        original = revalidate_retained_track_a_admission(
            pilot_authorization_path=pilot_authorization_path,
            expected_pilot_authorization_sha256=expected_pilot_authorization_sha256,
            retained_approval_reference=trusted_approval_reference,
            expected_n05_binding=retained.pilot_authorization.n05,
            expected_output_root=root,
            protocol_config_path=protocol_config_path,
        )
        if (
            original.pilot_authorization != retained.pilot_authorization
            or original.pilot_authorization_bytes != retained.pilot_authorization_bytes
            or original.pilot_authorization_sha256 != retained.pilot_authorization_sha256
            or original.trusted_approval_reference != retained.trusted_approval_reference
            or original.n05_authorization != retained.n05_authorization
            or original.host != retained.host
            or original.n05_preflight != retained.n05_preflight
            or original.n05_raw_manifest != retained.n05_raw_manifest
            or original.repetition_plan != retained.repetition_plan
            or original.repetition_plan_sha256 != retained.repetition_plan_sha256
            or original.protocol_config_sha256 != retained.protocol_config_sha256
        ):
            raise ValueError("original and frozen Track A admission evidence differ")
        authorization = original.pilot_authorization
        record = TrackAHostAdmissionRecord(
            authorization.authorization_id,
            trusted_approval_reference,
            str(pilot_authorization_path),
            original.pilot_authorization_sha256,
            str(root),
            authorization.track_a_host_ledger_root,
            ArtifactReference("execution.json", execution.execution_sha256),
            execution.manifest.admission_record,
            ArtifactReference("repetitions/plan.json", execution.repetitions.plan_sha256),
            authorization.n05.host_manifest_sha256,
            authorization.n05.final_manifest_sha256,
            authorization.source_revision,
        )
        return VerifiedTrackAHostAdmission(record, execution, original)
    except Exception as error:
        if isinstance(error, VerificationError) and str(error).startswith(
            "invalid Track A host admission:"
        ):
            raise
        raise VerificationError(f"invalid Track A host admission: {error}") from error


def _read_host_admission(
    root: Path, *, protocol_config_path: Path | None
) -> tuple[TrackAHostAdmissionRecord, str, VerifiedTrackAExecution]:
    from .track_a_admission import revalidate_retained_track_a_admission
    from .track_a_exploratory import read_track_a_execution

    path = root / HOST_ADMISSION_NAME
    digest = sha256(_read_file(path)).hexdigest()
    record = read_record(path, TrackAHostAdmissionRecord, expected_sha256=digest)
    execution = read_track_a_execution(
        Path(record.output_root),
        expected_execution_sha256=record.execution.sha256,
        protocol_config_path=protocol_config_path,
    )
    retained = revalidate_retained_track_a_admission(
        pilot_authorization_path=Path(record.pilot_authorization_path),
        expected_pilot_authorization_sha256=record.pilot_authorization_sha256,
        retained_approval_reference=record.approval_reference,
        expected_n05_binding=execution.admission.pilot_authorization.n05,
        expected_output_root=Path(record.output_root),
        protocol_config_path=protocol_config_path,
    )
    if (
        record.authorization_id != retained.pilot_authorization.authorization_id
        or record.approval_reference != retained.pilot_authorization.approval_reference
        or record.host_ledger_root != str(root)
        or record.execution != ArtifactReference("execution.json", execution.execution_sha256)
        or record.track_a_admission != execution.manifest.admission_record
        or record.repetition_plan
        != ArtifactReference("repetitions/plan.json", execution.repetitions.plan_sha256)
        or record.n05_host_manifest_sha256 != retained.pilot_authorization.n05.host_manifest_sha256
        or record.n05_final_manifest_sha256
        != retained.pilot_authorization.n05.final_manifest_sha256
        or record.source_revision != execution.manifest.source_revision
    ):
        raise ValueError("Track A host admission differs from authoritative evidence")
    return record, digest, execution


def validate_track_a_host_attempt_binding(
    execution: VerifiedTrackAExecution,
    index: int,
    started: TrackAHostAttemptStarted,
) -> PolicyRunSlot:
    """Bind a host-published attempt to the still-pending campaign cell."""
    _validate_track_a_host_attempt_identity(execution, index, started)
    return _require_next_slot(execution, index)


def _validate_track_a_host_attempt_identity(
    execution: VerifiedTrackAExecution,
    index: int,
    started: TrackAHostAttemptStarted,
) -> None:
    if type(started) is not TrackAHostAttemptStarted:
        raise ValueError("controller requires a typed host attempt start")
    if type(index) is not int or not 0 <= index < len(execution.repetitions.plan.runs):
        raise ValueError("Track A run index is outside the frozen schedule")
    scheduled = execution.repetitions.plan.runs[index]
    if (
        started.run_index != index
        or started.run_id != scheduled.run_id
        or started.config_id != scheduled.evaluation_config.config_id
        or started.execution_sha256 != execution.execution_sha256
        or started.plan_sha256 != execution.repetitions.plan_sha256
        or started.output_root != execution.manifest.output_root
    ):
        raise ValueError("host attempt differs from the frozen Track A schedule")


class TrackAHostLedger:
    """Single-writer host ledger; a started cell is consumed and never retried."""

    def __init__(
        self,
        admission: VerifiedTrackAHostAdmission,
        *,
        protocol_config_path: Path | None = None,
    ) -> None:
        if type(admission) is not VerifiedTrackAHostAdmission:
            raise ValueError("Track A host ledger requires fresh admission validation")
        self.admission = admission
        self.root = Path(admission.record.host_ledger_root)
        self.protocol_config_path = protocol_config_path
        if self.root.exists() or self.root.is_symlink():
            snapshot = read_track_a_host_ledger(
                self.root, protocol_config_path=protocol_config_path
            )
            if snapshot.admission != admission.record:
                raise ValueError("existing Track A host ledger has a different admission")
        else:
            if self.root.resolve() != self.root:
                raise ValueError("Track A host ledger path must be canonical")
            self.root.mkdir(parents=True, exist_ok=False)
            sync_directory(self.root.parent)
            admission_root = self.root / "admission"
            admission_root.mkdir(exist_ok=False)
            sync_directory(self.root)
            write_record(admission_root / "verified-admission.json", admission.record)
            attempts = self.root / "attempts"
            attempts.mkdir(exist_ok=False)
            sync_directory(self.root)

    def claim(self, index: int, *, attempt_id: str) -> ClaimedTrackAHostAttempt:
        snapshot = read_track_a_host_ledger(
            self.root, protocol_config_path=self.protocol_config_path
        )
        slot = _require_next_slot(snapshot.execution, index)
        scheduled = snapshot.execution.repetitions.plan.runs[index]
        _text(attempt_id)
        if any(item.started.attempt_id == attempt_id for item in snapshot.attempts):
            raise ValueError("host attempt identifier already consumed")
        directory = self.root / "attempts" / _attempt_directory(index, scheduled.run_id)
        if directory.exists() or directory.is_symlink():
            raise ValueError("Track A host cell already has an attempt")
        directory.mkdir(exist_ok=False)
        sync_directory(directory.parent)
        started = TrackAHostAttemptStarted(
            attempt_id,
            index,
            scheduled.run_id,
            slot.config_id,
            snapshot.execution.execution_sha256,
            snapshot.execution.repetitions.plan_sha256,
            ArtifactReference(HOST_ADMISSION_NAME, snapshot.admission_sha256),
            snapshot.execution.manifest.output_root,
            datetime.now(UTC).isoformat(),
        )
        digest = write_record(directory / "started.json", started)
        return ClaimedTrackAHostAttempt(started, digest, directory)

    def finish(
        self,
        claimed: ClaimedTrackAHostAttempt,
        execution: VerifiedTrackAExecution,
        *,
        controller_stderr: bytes,
        controller_stderr_truncated: bool,
        controller_stderr_capture_complete: bool,
        controller_launched: bool,
        controller_returncode: int | None,
        controller_terminal: TrackAControllerTerminal | None,
        deadline_expired: bool,
        cleanup_status: TrackAHostCleanupStatus,
        cleanup_errors: tuple[str, ...],
        error: BaseException | None,
    ) -> VerifiedTrackAHostAttempt:
        if type(claimed) is not ClaimedTrackAHostAttempt:
            raise ValueError("terminal publication requires a claimed host attempt")
        started = claimed.started
        expected_directory = (
            self.root / "attempts" / _attempt_directory(started.run_index, started.run_id)
        )
        if claimed.directory != expected_directory:
            raise ValueError("claimed host attempt directory differs from the ledger")
        retained_started = read_record(
            expected_directory / "started.json",
            TrackAHostAttemptStarted,
            expected_sha256=claimed.started_sha256,
        )
        if retained_started != started:
            raise ValueError("claimed host attempt differs from its durable start")
        if execution.execution_sha256 != started.execution_sha256:
            raise ValueError("terminal execution differs from the host attempt")
        _validate_track_a_host_attempt_identity(execution, started.run_index, started)
        slot = execution.repetitions.slots[started.run_index]
        scheduled = execution.repetitions.plan.runs[started.run_index]
        if (
            slot.run_id != started.run_id
            or scheduled.evaluation_config.config_id != started.config_id
        ):
            raise ValueError("terminal campaign slot differs from the host attempt")
        campaign_claim = None
        campaign_terminal = None
        if slot.claim is not None:
            claim_path = (
                Path(execution.manifest.output_root)
                / "repetitions"
                / slot.result_directory
                / "claim.json"
            )
            campaign_claim = _campaign_artifact(
                slot, "claim.json", sha256(_read_file(claim_path)).hexdigest()
            )
        if slot.terminal is not None:
            terminal_path = (
                Path(execution.manifest.output_root)
                / "repetitions"
                / slot.result_directory
                / "terminal.json"
            )
            campaign_terminal = _campaign_artifact(
                slot, "terminal.json", sha256(_read_file(terminal_path)).hexdigest()
            )
        controller_terminal_mismatch = controller_terminal is not None and (
            controller_terminal.attempt_id != started.attempt_id
            or controller_terminal.run_index != started.run_index
            or controller_terminal.run_id != started.run_id
            or controller_terminal.execution_sha256 != started.execution_sha256
            or controller_terminal.plan_sha256 != started.plan_sha256
            or controller_terminal.state != slot.state
            or controller_terminal.completed_steps != slot.completed_steps
            or controller_terminal.campaign_claim != campaign_claim
            or controller_terminal.campaign_terminal != campaign_terminal
            or controller_terminal.controller_memory_sha256 != slot.controller_memory_sha256
        )
        if controller_terminal_mismatch:
            mismatch_error = ValueError("controller terminal differs from the campaign claim")
            if error is None:
                error = mismatch_error
            else:
                error.add_note(str(mismatch_error))
            controller_terminal = None
        successful = (
            error is None
            and controller_launched
            and controller_returncode == 0
            and controller_terminal is not None
            and not deadline_expired
            and cleanup_status
            in {TrackAHostCleanupStatus.COMPLETE, TrackAHostCleanupStatus.NOT_NEEDED}
            and controller_stderr_capture_complete
            and slot.state == RunState.COMPLETED
        )
        status = TrackAHostAttemptStatus.COMPLETE if successful else TrackAHostAttemptStatus.FAILED
        stderr_sha256 = publish_bytes(
            claimed.directory / "controller-stderr.bin", controller_stderr
        )
        terminal = TrackAHostAttemptTerminal(
            started.attempt_id,
            started.run_index,
            started.run_id,
            started.execution_sha256,
            started.plan_sha256,
            started.host_admission,
            ArtifactReference("started.json", claimed.started_sha256),
            ArtifactReference("controller-stderr.bin", stderr_sha256),
            len(controller_stderr),
            controller_stderr_truncated,
            controller_stderr_capture_complete,
            controller_launched,
            controller_returncode,
            controller_terminal,
            deadline_expired,
            cleanup_status,
            cleanup_errors,
            slot.state,
            campaign_claim,
            campaign_terminal,
            slot.completed_steps,
            None
            if error is None
            else f"{type(error).__module__}.{type(error).__qualname__}: {error}",
            started.started_at,
            datetime.now(UTC).isoformat(),
            status,
        )
        terminal_sha256 = write_record(claimed.directory / "terminal.json", terminal)
        manifest = TrackAHostAttemptManifest(
            HOST_ATTEMPT_FORMAT,
            started.attempt_id,
            started.run_index,
            started.run_id,
            started.execution_sha256,
            started.plan_sha256,
            started.host_admission,
            ArtifactReference("started.json", claimed.started_sha256),
            ArtifactReference("controller-stderr.bin", stderr_sha256),
            ArtifactReference("terminal.json", terminal_sha256),
            status,
        )
        manifest_sha256 = write_record(claimed.directory / "manifest.json", manifest)
        return read_track_a_host_attempt(
            self.root,
            started.run_index,
            expected_manifest_sha256=manifest_sha256,
            protocol_config_path=self.protocol_config_path,
        )


def _validate_host_root(root: Path) -> None:
    if (
        not root.is_absolute()
        or root.is_symlink()
        or root.resolve() != root
        or not root.is_dir()
        or {path.name for path in root.iterdir()} != {"admission", "attempts"}
    ):
        raise ValueError("invalid Track A host ledger root")
    admission_root = root / "admission"
    attempts_root = root / "attempts"
    if (
        admission_root.is_symlink()
        or not admission_root.is_dir()
        or {path.name for path in admission_root.iterdir()} != {"verified-admission.json"}
        or (admission_root / "verified-admission.json").is_symlink()
        or attempts_root.is_symlink()
        or not attempts_root.is_dir()
    ):
        raise ValueError("invalid Track A host ledger structure")


def read_track_a_host_attempt_started(
    root: Path,
    index: int,
    *,
    expected_started_sha256: str,
    protocol_config_path: Path | None = None,
) -> tuple[TrackAHostAttemptStarted, VerifiedTrackAExecution]:
    """Read the immutable start binding before controller campaign claim."""
    try:
        _validate_host_root(root)
        admission, admission_sha256, execution = _read_host_admission(
            root, protocol_config_path=protocol_config_path
        )
        if type(index) is not int or not 0 <= index < len(execution.repetitions.slots):
            raise ValueError("Track A run index is outside the frozen schedule")
        run_id = execution.repetitions.plan.runs[index].run_id
        directory = root / "attempts" / _attempt_directory(index, run_id)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("missing Track A host attempt directory")
        allowed = {"started.json", "controller-stderr.bin", "terminal.json", "manifest.json"}
        if any(path.name not in allowed or path.is_symlink() for path in directory.iterdir()):
            raise ValueError("unexpected Track A host attempt artifact")
        started = read_record(
            directory / "started.json",
            TrackAHostAttemptStarted,
            expected_sha256=expected_started_sha256,
        )
        if (
            started.host_admission != ArtifactReference(HOST_ADMISSION_NAME, admission_sha256)
            or admission.execution.sha256 != started.execution_sha256
        ):
            raise ValueError("host attempt and admission records disagree")
        validate_track_a_host_attempt_binding(execution, index, started)
        return started, execution
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        if isinstance(error, VerificationError):
            raise
        raise VerificationError(f"invalid Track A host attempt start: {error}") from error


def _expected_host_status(terminal: TrackAHostAttemptTerminal) -> TrackAHostAttemptStatus:
    successful = (
        terminal.exception is None
        and terminal.controller_launched
        and terminal.controller_returncode == 0
        and terminal.controller_terminal is not None
        and not terminal.deadline_expired
        and terminal.cleanup_status
        in {TrackAHostCleanupStatus.COMPLETE, TrackAHostCleanupStatus.NOT_NEEDED}
        and terminal.controller_stderr_capture_complete
        and terminal.campaign_state == RunState.COMPLETED
    )
    return TrackAHostAttemptStatus.COMPLETE if successful else TrackAHostAttemptStatus.FAILED


def read_track_a_host_attempt(
    root: Path,
    index: int,
    *,
    expected_manifest_sha256: str,
    protocol_config_path: Path | None = None,
) -> VerifiedTrackAHostAttempt:
    """Verify one terminal host attempt and its current campaign prefix read-only."""
    try:
        _validate_host_root(root)
        admission, admission_sha256, execution = _read_host_admission(
            root, protocol_config_path=protocol_config_path
        )
        if type(index) is not int or not 0 <= index < len(execution.repetitions.slots):
            raise ValueError("Track A run index is outside the frozen schedule")
        run_id = execution.repetitions.plan.runs[index].run_id
        directory = root / "attempts" / _attempt_directory(index, run_id)
        expected_names = {
            "started.json",
            "controller-stderr.bin",
            "terminal.json",
            "manifest.json",
        }
        if (
            directory.is_symlink()
            or not directory.is_dir()
            or {path.name for path in directory.iterdir()} != expected_names
            or any(path.is_symlink() or not path.is_file() for path in directory.iterdir())
        ):
            raise ValueError("terminal Track A host attempt is incomplete")
        manifest_path = directory / "manifest.json"
        manifest_sha256 = sha256(_read_file(manifest_path)).hexdigest()
        if manifest_sha256 != _digest(expected_manifest_sha256):
            raise ValueError("Track A host attempt manifest checksum mismatch")
        manifest = read_record(
            manifest_path,
            TrackAHostAttemptManifest,
            expected_sha256=manifest_sha256,
        )
        started = read_record(
            directory / manifest.started.name,
            TrackAHostAttemptStarted,
            expected_sha256=manifest.started.sha256,
        )
        _validate_track_a_host_attempt_identity(execution, index, started)
        terminal = read_record(
            directory / manifest.terminal.name,
            TrackAHostAttemptTerminal,
            expected_sha256=manifest.terminal.sha256,
        )
        stderr = _read_file(directory / manifest.controller_stderr.name)
        if sha256(stderr).hexdigest() != manifest.controller_stderr.sha256:
            raise ValueError("Track A controller stderr checksum mismatch")
        shared = (
            manifest.attempt_id,
            manifest.run_index,
            manifest.run_id,
            manifest.execution_sha256,
            manifest.plan_sha256,
            manifest.host_admission,
        )
        if (
            shared
            != (
                started.attempt_id,
                started.run_index,
                started.run_id,
                started.execution_sha256,
                started.plan_sha256,
                started.host_admission,
            )
            or shared
            != (
                terminal.attempt_id,
                terminal.run_index,
                terminal.run_id,
                terminal.execution_sha256,
                terminal.plan_sha256,
                terminal.host_admission,
            )
            or manifest.started.sha256 != terminal.started.sha256
            or manifest.controller_stderr != terminal.controller_stderr
            or len(stderr) != terminal.controller_stderr_size
            or len(stderr) > OUTPUT_LIMIT
            or manifest.status != terminal.status
            or terminal.status != _expected_host_status(terminal)
            or started.host_admission != ArtifactReference(HOST_ADMISSION_NAME, admission_sha256)
            or started.execution_sha256 != admission.execution.sha256
        ):
            raise ValueError("Track A host attempt record binding is invalid")
        slot = execution.repetitions.slots[index]
        claim = None
        campaign_terminal = None
        if slot.claim is not None:
            claim_path = (
                Path(admission.output_root) / "repetitions" / slot.result_directory / "claim.json"
            )
            claim = _campaign_artifact(
                slot, "claim.json", sha256(_read_file(claim_path)).hexdigest()
            )
        if slot.terminal is not None:
            campaign_terminal_path = (
                Path(admission.output_root)
                / "repetitions"
                / slot.result_directory
                / "terminal.json"
            )
            campaign_terminal = _campaign_artifact(
                slot,
                "terminal.json",
                sha256(_read_file(campaign_terminal_path)).hexdigest(),
            )
        if (
            terminal.campaign_state != slot.state
            or terminal.campaign_claim != claim
            or terminal.campaign_terminal != campaign_terminal
            or terminal.target_executions != slot.completed_steps
        ):
            raise ValueError("host terminal differs from the campaign prefix")
        if slot.claim is not None and slot.claim.attempt_id != started.attempt_id:
            raise ValueError("host and campaign attempt identifiers differ")
        if terminal.controller_terminal is not None and (
            terminal.controller_terminal.attempt_id != started.attempt_id
            or terminal.controller_terminal.run_index != index
            or terminal.controller_terminal.run_id != run_id
            or terminal.controller_terminal.execution_sha256 != execution.execution_sha256
            or terminal.controller_terminal.plan_sha256 != execution.repetitions.plan_sha256
            or terminal.controller_terminal.state != slot.state
            or terminal.controller_terminal.completed_steps != slot.completed_steps
            or terminal.controller_terminal.campaign_claim != claim
            or terminal.controller_terminal.campaign_terminal != campaign_terminal
            or terminal.controller_terminal.controller_memory_sha256
            != slot.controller_memory_sha256
        ):
            raise ValueError("host controller result differs from the campaign prefix")
        return VerifiedTrackAHostAttempt(
            admission,
            admission_sha256,
            started,
            manifest.started.sha256,
            terminal,
            manifest.terminal.sha256,
            manifest,
            manifest_sha256,
            stderr,
            execution,
        )
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        if isinstance(error, VerificationError):
            raise
        raise VerificationError(f"invalid Track A host attempt: {error}") from error


def read_track_a_host_ledger(
    root: Path, *, protocol_config_path: Path | None = None
) -> TrackAHostLedgerSnapshot:
    """Verify all terminal attempts without modifying host, Track A or N05 evidence."""
    try:
        _validate_host_root(root)
        admission, admission_sha256, execution = _read_host_admission(
            root, protocol_config_path=protocol_config_path
        )
        attempt_paths = sorted((root / "attempts").iterdir(), key=lambda path: path.name)
        expected_names = {
            _attempt_directory(index, run.run_id)
            for index, run in enumerate(execution.repetitions.plan.runs)
        }
        if any(
            path.name not in expected_names or path.is_symlink() or not path.is_dir()
            for path in attempt_paths
        ):
            raise ValueError("unexpected Track A host attempt directory")
        attempts = []
        for path in attempt_paths:
            index_text = path.name.split("-", 1)[0]
            if not index_text.isdecimal():
                raise ValueError("invalid Track A host attempt directory")
            index = int(index_text)
            manifest_path = path / "manifest.json"
            digest = sha256(_read_file(manifest_path)).hexdigest()
            attempts.append(
                read_track_a_host_attempt(
                    root,
                    index,
                    expected_manifest_sha256=digest,
                    protocol_config_path=protocol_config_path,
                )
            )
        indices = tuple(item.started.run_index for item in attempts)
        if indices != tuple(range(len(attempts))):
            raise ValueError("Track A host attempts must form one ordered consumed prefix")
        attempt_ids = tuple(item.started.attempt_id for item in attempts)
        if len(set(attempt_ids)) != len(attempt_ids):
            raise ValueError("Track A host attempt identifiers must be unique")
        return TrackAHostLedgerSnapshot(admission, admission_sha256, execution, tuple(attempts))
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        if isinstance(error, VerificationError):
            raise
        raise VerificationError(f"invalid Track A host ledger: {error}") from error

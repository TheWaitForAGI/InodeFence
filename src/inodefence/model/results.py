"""Execution provenance and contract evidence; target outcome is not a verdict."""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from ._validation import validate_sha256
from .archive import ArchiveCase
from .effect import EffectEventTrace, EffectTargetTermination
from .filesystem import (
    Region,
    StateChange,
    StateSignature,
    StateSnapshot,
    path_region,
    validate_observed_path,
)
from .transition import (
    ArchiveEntryReference,
    ObservationKind,
    TraceTermination,
    TransitionTrace,
)


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Raw process evidence, with configured budget and actual elapsed time.

    duration_seconds is finite, nonnegative actual monotonic elapsed process
    execution time, including timeout cleanup/wait. It is not a verdict.
    """

    target_id: str
    target_version: str
    command: tuple[str, ...]
    status: ExecutionStatus
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if not all(
            isinstance(text, str) and text for text in (self.target_id, self.target_version)
        ):
            raise ValueError("execution requires target identity and version")
        if not isinstance(self.stdout, str) or not isinstance(self.stderr, str):
            raise ValueError("stdout and stderr must be decoded text")
        if (
            type(self.duration_seconds) not in (int, float)
            or not math.isfinite(self.duration_seconds)
            or self.duration_seconds < 0
        ):
            raise ValueError("duration_seconds must be finite and nonnegative")
        if self.timeout_seconds is not None and (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout must be finite and positive")
        if not isinstance(self.command, tuple) or not all(isinstance(s, str) for s in self.command):
            raise ValueError("command must be a tuple of strings")
        if not isinstance(self.status, ExecutionStatus):
            raise ValueError("status must be an ExecutionStatus")
        if self.status == ExecutionStatus.TIMED_OUT:
            if self.exit_code is not None:
                raise ValueError("timed-out executions have no completed exit code")
        elif type(self.exit_code) is not int:
            raise ValueError("completed executions require an integer exit code")
        if (self.status == ExecutionStatus.SUCCESS) != (self.exit_code == 0):
            raise ValueError("only successful executions have exit code zero")

    @property
    def succeeded(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS


class ContractId(StrEnum):
    C0 = "C0"
    C1 = "C1"
    C2 = "C2"


@dataclass(frozen=True, slots=True)
class IdentityEvidence:
    """Both lstat observations establish the actual same-object relation."""

    internal_path: str
    sentinel_path: str
    st_dev: int
    st_ino: int

    def __post_init__(self) -> None:
        validate_observed_path(self.internal_path)
        validate_observed_path(self.sentinel_path)
        if path_region(self.internal_path) != Region.EXTRACTION or (
            path_region(self.sentinel_path) != Region.EXTERNAL
        ):
            raise ValueError("identity evidence requires internal and external paths")
        if any(type(number) is not int or number < 0 for number in (self.st_dev, self.st_ino)):
            raise ValueError("identity evidence requires nonnegative device/inode integers")


@dataclass(frozen=True, slots=True)
class BoundaryIdentityEvidence:
    """An extraction object sharing lstat identity with a non-extraction object.

    Additive generalization of IdentityEvidence: the shared object may be any
    non-extraction path, including harness objects (e.g. archive/input.tar) and
    non-sentinel external objects, not only a protected external sentinel. Both
    lstat observations establish the actual same-object relation. This evidence
    is consumed by the generalized identity-confinement detector and never enters
    the C0/C1/C2 ViolationResult tuple, so existing oracle verdicts are unchanged.
    """

    internal_path: str
    external_path: str
    st_dev: int
    st_ino: int

    def __post_init__(self) -> None:
        validate_observed_path(self.internal_path)
        validate_observed_path(self.external_path)
        if path_region(self.internal_path) != Region.EXTRACTION:
            raise ValueError("boundary identity evidence requires an extraction internal path")
        if path_region(self.external_path) == Region.EXTRACTION:
            raise ValueError("boundary identity evidence requires a non-extraction shared path")
        if any(type(number) is not int or number < 0 for number in (self.st_dev, self.st_ino)):
            raise ValueError("boundary identity evidence requires nonnegative device/inode numbers")

    @property
    def external_region(self) -> Region:
        return path_region(self.external_path)


@dataclass(frozen=True, slots=True)
class ViolationResult:
    """A contract candidate within snapshot coverage, not a vulnerability claim."""

    contract_id: ContractId
    violated: bool
    evidence: tuple[StateChange | IdentityEvidence, ...]
    explanation: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.contract_id, ContractId) or type(self.violated) is not bool:
            raise ValueError("verdict requires a contract enum and bool")
        evidence_type = IdentityEvidence if self.contract_id == ContractId.C1 else StateChange
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, evidence_type) for item in self.evidence
        ):
            raise ValueError("evidence must be a tuple of the contract's evidence type")
        if not isinstance(self.explanation, str) or not self.explanation:
            raise ValueError("verdict requires an explanation")
        if not isinstance(self.limitations, tuple) or not all(
            isinstance(item, str) and item for item in self.limitations
        ):
            raise ValueError("limitations must be a tuple of nonempty text")
        if self.violated != bool(self.evidence):
            raise ValueError("violation requires evidence; a nonviolation has no evidence")


@dataclass(frozen=True, slots=True)
class RunResult:
    """Typed immutable raw run evidence that survives disposal of the sandbox.

    Construction validates field types, not cross-record derivation. The pipeline
    owns TAR correspondence, snapshot pairing, signature and oracle assembly.
    This constructor is not a deserializer or an authenticity check.
    """

    case: ArchiveCase
    archive_sha256: str
    archive_format: str
    execution: ExecutionResult
    before: StateSnapshot
    after: StateSnapshot
    changes: tuple[StateChange, ...]
    signature: StateSignature
    violations: tuple[ViolationResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case, ArchiveCase) or not isinstance(
            self.execution, ExecutionResult
        ):
            raise ValueError("run requires ArchiveCase and ExecutionResult records")
        validate_sha256(self.archive_sha256)
        if not isinstance(self.archive_format, str) or not self.archive_format:
            raise ValueError("archive format must be nonempty text")
        if not isinstance(self.before, StateSnapshot) or not isinstance(self.after, StateSnapshot):
            raise ValueError("run requires StateSnapshot records")
        if not isinstance(self.signature, StateSignature):
            raise ValueError("run requires a StateSignature record")
        if not isinstance(self.changes, tuple) or not all(
            isinstance(change, StateChange) for change in self.changes
        ):
            raise ValueError("run changes must be a tuple of StateChange records")
        if not isinstance(self.violations, tuple) or not all(
            isinstance(verdict, ViolationResult) for verdict in self.violations
        ):
            raise ValueError("run violations must be a tuple of ViolationResult records")


@dataclass(frozen=True, slots=True)
class TransitionRunResult:
    """A legacy RunResult composed with independent entry-transition evidence."""

    base_result: RunResult
    trace: TransitionTrace

    def __post_init__(self) -> None:
        if not isinstance(self.base_result, RunResult) or not isinstance(
            self.trace, TransitionTrace
        ):
            raise ValueError("transition run requires RunResult and TransitionTrace")
        if self.trace.expected_entry_count != len(self.base_result.case.entries):
            raise ValueError("trace expected entry count differs from ArchiveCase")
        first = self.trace.checkpoints[0]
        before = self.base_result.before
        if not (
            first.point.kind == ObservationKind.BEFORE
            and first.sandbox_root == before.sandbox_root
            and first.objects == before.objects
            and first.protected_paths == before.protected_paths
        ):
            raise ValueError("trace BEFORE checkpoint differs from base RunResult")
        if self.trace.final_after != self.base_result.after:
            raise ValueError("trace final AFTER differs from base RunResult")
        for checkpoint in self.trace.checkpoints[1:]:
            reference = checkpoint.point.entry
            assert isinstance(reference, ArchiveEntryReference)
            if reference.entry_index >= len(self.base_result.case.entries):
                raise ValueError("checkpoint entry ordinal exceeds ArchiveCase")
            entry = self.base_result.case.entries[reference.entry_index]
            if reference != ArchiveEntryReference(
                reference.entry_index, entry.path, entry.entry_type, entry.link_target
            ):
                raise ValueError("checkpoint entry identity differs from ArchiveCase")
        expected_termination = {
            ExecutionStatus.SUCCESS: TraceTermination.SUCCESS,
            ExecutionStatus.REJECTED: TraceTermination.TARGET_REJECTED,
            ExecutionStatus.FAILED: TraceTermination.TARGET_FAILED,
            ExecutionStatus.TIMED_OUT: TraceTermination.TARGET_TIMEOUT,
        }[self.base_result.execution.status]
        target_terminations = {
            TraceTermination.SUCCESS,
            TraceTermination.TARGET_REJECTED,
            TraceTermination.TARGET_FAILED,
            TraceTermination.TARGET_TIMEOUT,
        }
        if self.trace.termination in target_terminations and (
            self.trace.termination != expected_termination
        ):
            raise ValueError("trace termination differs from target execution status")


@dataclass(frozen=True, slots=True)
class EffectRunResult:
    """An unchanged RunResult composed with independent effect-event evidence."""

    serialization_schema: ClassVar[int] = 2

    base_result: RunResult
    trace: EffectEventTrace

    def __post_init__(self) -> None:
        if not isinstance(self.base_result, RunResult) or not isinstance(
            self.trace, EffectEventTrace
        ):
            raise ValueError("effect run requires RunResult and EffectEventTrace")
        expected_entries = tuple(
            ArchiveEntryReference(index, entry.path, entry.entry_type, entry.link_target)
            for index, entry in enumerate(self.base_result.case.entries)
        )
        if self.trace.archive_entries != expected_entries:
            raise ValueError("effect trace entry identity differs from ArchiveCase")
        if (
            self.trace.before != self.base_result.before
            or self.trace.after != self.base_result.after
        ):
            raise ValueError("effect trace snapshots differ from base RunResult")
        expected_termination = {
            ExecutionStatus.SUCCESS: EffectTargetTermination.SUCCESS,
            ExecutionStatus.REJECTED: EffectTargetTermination.REJECTED,
            ExecutionStatus.FAILED: EffectTargetTermination.FAILED,
            ExecutionStatus.TIMED_OUT: EffectTargetTermination.TIMED_OUT,
        }[self.base_result.execution.status]
        if self.trace.termination != expected_termination:
            raise ValueError("effect trace termination differs from target execution status")

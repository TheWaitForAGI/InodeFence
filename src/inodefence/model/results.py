"""Execution provenance and contract evidence; target outcome is not a verdict."""

import math
from dataclasses import dataclass
from enum import StrEnum

from .archive import ArchiveCase
from .filesystem import (
    Region,
    StateChange,
    StateSignature,
    StateSnapshot,
    path_region,
    validate_observed_path,
)


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    target_id: str
    target_version: str
    command: tuple[str, ...]
    status: ExecutionStatus
    exit_code: int | None
    stdout: str
    stderr: str
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if not all(
            isinstance(text, str) and text for text in (self.target_id, self.target_version)
        ):
            raise ValueError("execution requires target identity and version")
        if not isinstance(self.stdout, str) or not isinstance(self.stderr, str):
            raise ValueError("stdout and stderr must be decoded text")
        if self.timeout_seconds is not None and (
            not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0
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
    """Self-contained raw run evidence that survives disposal of the sandbox."""

    case: ArchiveCase
    archive_sha256: str
    archive_format: str
    execution: ExecutionResult
    before: StateSnapshot
    after: StateSnapshot
    changes: tuple[StateChange, ...]
    signature: StateSignature
    violations: tuple[ViolationResult, ...]

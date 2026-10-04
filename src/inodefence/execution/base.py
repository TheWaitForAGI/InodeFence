"""Execution request/value contract, independent of runtime command syntax."""

import math
import re
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inodefence.model.isolation import IsolationPolicy, IsolationProvenance
from inodefence.model.isolation import ResourcePolicy as ResourcePolicy
from inodefence.runtime import RUNTIME_BASE


class BackendError(RuntimeError):
    """Infrastructure failure; never an extractor exit status."""


@dataclass(frozen=True, slots=True)
class ContainerRequest:
    """Immutable content anchor, explicit argv and one existing controlled run."""

    image_id: str
    command: tuple[str, ...]
    run_root: Path
    timeout_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.image_id, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", self.image_id
        ):
            raise ValueError("target image must be an immutable local SHA-256 image ID")
        if (
            not isinstance(self.command, tuple)
            or not self.command
            or not all(isinstance(arg, str) and arg and "\0" not in arg for arg in self.command)
        ):
            raise ValueError("target command must be nonempty explicit argv")
        relative = self.run_root.relative_to(RUNTIME_BASE)
        spelling = relative.as_posix()
        if ".." in relative.parts or not re.fullmatch(
            r"(?:[a-zA-Z0-9_.-]+/)*core-run-[a-zA-Z0-9_-]+", spelling
        ):
            raise ValueError("target mounts require a disposable core-run directory")
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 120
        ):
            raise ValueError("target wall-clock timeout must be positive and at most 120 seconds")


@dataclass(frozen=True, slots=True)
class ContainerOutcome:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    duration_seconds: float
    output_truncated: bool


class PreparedExecution(Protocol):
    def execute(self) -> ContainerOutcome: ...


class ExecutionBackend(ABC):
    """Trusted implementation must enforce its boundary, not just declare it.

    Implementations validate availability/image before run allocation, prepare
    before BEFORE, stop the complete context before returning execute, and remove
    after AFTER. Implementing this class is a controller trust decision; a target
    descriptor or boolean cannot certify a new execution mechanism.
    """

    @abstractmethod
    def validate_image(self, image_id: str) -> None: ...

    @abstractmethod
    def policy(self, image_id: str) -> IsolationPolicy: ...

    @abstractmethod
    def capture_isolation(self, image_id: str) -> IsolationProvenance: ...

    @abstractmethod
    def prepare(self, request: ContainerRequest) -> AbstractContextManager[PreparedExecution]: ...


class OutputLimitError(BackendError):
    """Incomplete diagnostics abort the run; the bounded raw prefix is retained."""

    def __init__(self, outcome: ContainerOutcome) -> None:
        super().__init__("target output exceeded capture limit; run evidence is incomplete")
        self.outcome = outcome

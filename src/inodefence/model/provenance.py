"""Immutable configuration identity; never a filesystem fact or novelty key."""

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from .filesystem import validate_observed_path
from .isolation import IsolationProvenance


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError(f"{field} must be nonempty text without NUL")


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    """Git object ID and tracked/untracked dirty state; None means unavailable."""

    revision: str | None = None
    dirty: bool | None = None

    def __post_init__(self) -> None:
        if self.revision is not None and (
            not isinstance(self.revision, str)
            or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", self.revision) is None
        ):
            raise ValueError("revision must be a full lowercase Git object ID or None")
        if self.dirty is not None and type(self.dirty) is not bool:
            raise ValueError("dirty must be bool or None")
        if self.revision is None and self.dirty is not None:
            raise ValueError("unavailable revision requires unavailable dirty state")


@dataclass(frozen=True, slots=True)
class EnvironmentProvenance:
    """platform system/release/machine/python_version, captured by the caller."""

    system: str
    release: str
    machine: str
    python_version: str

    def __post_init__(self) -> None:
        for field in ("system", "release", "machine", "python_version"):
            # platform may return an empty string when a field is unavailable.
            value = getattr(self, field)
            if not isinstance(value, str) or "\0" in value:
                raise ValueError(f"{field} must be text without NUL")


class ExecutionSafety(StrEnum):
    """Adapter trust declaration, not proof of OS containment.

    Only the controlled reference implementation may run generated cases under
    today's development environment. Other targets require a separately validated
    execution isolation boundary and configured execution binding.
    """

    TRUSTED_REFERENCE = "trusted_reference"
    ISOLATION_REQUIRED = "isolation_required"


@dataclass(frozen=True, slots=True)
class TargetProvenance:
    """Adapter-declared configuration before invocation; separate from result."""

    target_id: str
    target_version: str
    timeout_seconds: float | None
    execution_safety: ExecutionSafety = ExecutionSafety.ISOLATION_REQUIRED

    def __post_init__(self) -> None:
        _text(self.target_id, "target_id")
        _text(self.target_version, "target_version")
        if not isinstance(self.execution_safety, ExecutionSafety):
            raise ValueError("execution_safety must be ExecutionSafety")
        if self.timeout_seconds is not None and (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive or None")


@dataclass(frozen=True, slots=True)
class SentinelProvenance:
    """Relative name under outside/, digest of configured bytes and mode mask."""

    name: str
    content_sha256: str
    mode: int

    def __post_init__(self) -> None:
        validate_observed_path(self.name)
        if self.name == ".":
            raise ValueError("sentinel requires a file name")
        if (
            not isinstance(self.content_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.content_sha256) is None
        ):
            raise ValueError("content_sha256 must be lowercase SHA-256 hexadecimal")
        if type(self.mode) is not int or not 0 <= self.mode <= 0o7777:
            raise ValueError("sentinel mode must be a permission mask")


@dataclass(frozen=True, slots=True)
class ExecutionProvenance:
    """Frozen before execution. CampaignConfig separately owns seed and budget."""

    serialization_schema: ClassVar[int] = 2

    source: SourceProvenance
    environment: EnvironmentProvenance
    target: TargetProvenance
    sentinels: tuple[SentinelProvenance, ...]
    isolation: IsolationProvenance | None = None

    def __post_init__(self) -> None:
        if self.isolation is not None and not isinstance(self.isolation, IsolationProvenance):
            raise ValueError("isolation requires IsolationProvenance or None")
        for field, kind in (
            ("source", SourceProvenance),
            ("environment", EnvironmentProvenance),
            ("target", TargetProvenance),
        ):
            if not isinstance(getattr(self, field), kind):
                raise ValueError(f"{field} must be {kind.__name__}")
        if (
            not isinstance(self.sentinels, tuple)
            or not self.sentinels
            or not all(isinstance(item, SentinelProvenance) for item in self.sentinels)
        ):
            raise ValueError("sentinels must be a nonempty SentinelProvenance tuple")
        names = tuple(item.name for item in self.sentinels)
        if names != tuple(sorted(set(names))):
            raise ValueError("sentinels must have sorted unique names")

"""Evaluation-owned target matrix bound to actual qualification artifacts."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from inodefence.builder import BUILDER_FORMAT
from inodefence.model.provenance import ExecutionProvenance, TargetProvenance

from .failure import ArtifactReference
from .qualification import (
    _identifier,
    read_evidence,
    verify_qualification,
)
from .storage import read_record, write_record
from .verify import VerificationError


@dataclass(frozen=True, slots=True)
class TargetRequirement:
    """Full exact version includes target/runtime components declared by its adapter.

    Expected provenance pins observed runtime, source, sentinel, image/policy and
    artifact identities. None is an explicitly unbound candidate, never READY.
    """

    target: TargetProvenance
    expected_provenance: ExecutionProvenance | None = None
    qualification: ArtifactReference | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target, TargetProvenance) or self.target.target_version.lower() in {
            "latest",
            "current",
            "installed",
        }:
            raise ValueError("target requirement must have an exact declared identity")
        if self.expected_provenance is not None and (
            not isinstance(self.expected_provenance, ExecutionProvenance)
            or self.expected_provenance.target != self.target
        ):
            raise ValueError("expected target/runtime provenance differs from target declaration")
        if self.qualification is not None and not isinstance(self.qualification, ArtifactReference):
            raise ValueError("qualification must link a checksummed artifact")


@dataclass(frozen=True, slots=True)
class ProtocolBinding:
    benchmark_id: str
    target_family: str
    a: TargetRequirement
    b: TargetRequirement
    environment_profile: str
    sentinel_profile: str
    protocol_version: str
    builder_format: str = BUILDER_FORMAT

    def __post_init__(self) -> None:
        for value in (
            self.benchmark_id,
            self.target_family,
            self.environment_profile,
            self.sentinel_profile,
            self.protocol_version,
        ):
            _identifier(value)
        if not isinstance(self.a, TargetRequirement) or not isinstance(self.b, TargetRequirement):
            raise ValueError("matrix binding requires two explicit target configurations")
        if self.builder_format != BUILDER_FORMAT:
            raise ValueError("protocol requires current pinned builder format")


@dataclass(frozen=True, slots=True)
class EvaluationCatalog:
    bindings: tuple[ProtocolBinding, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.bindings, tuple)
            or not all(isinstance(binding, ProtocolBinding) for binding in self.bindings)
            or len({binding.benchmark_id for binding in self.bindings}) != len(self.bindings)
        ):
            raise ValueError("catalog requires unique typed benchmark bindings")


class BindingStatus(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class BindingResult:
    benchmark_id: str
    status: BindingStatus
    reasons: tuple[str, ...]
    qualification_sha256: tuple[str, ...]
    target_releases: tuple[str, ...]


def _validate_binding(binding: ProtocolBinding, directory: Path) -> BindingResult:
    reasons, digests, invalid = [], [], False
    for label, requirement in (("A", binding.a), ("B", binding.b)):
        if requirement.expected_provenance is None or requirement.qualification is None:
            reasons.append(f"{label}: qualification/runtime/artifact requirements are unbound")
            continue
        reference = requirement.qualification
        try:
            read_evidence(directory, reference)
            verified = verify_qualification(
                directory / reference.name, expected_sha256=reference.sha256
            )
            digests.append(verified.report_sha256)
            context = verified.report.context
            if (
                context.environment_profile,
                context.sentinel_profile,
                context.protocol_version,
            ) != (
                binding.environment_profile,
                binding.sentinel_profile,
                binding.protocol_version,
            ) or context.requested_target != requirement.target:
                raise ValueError("qualification differs from required target/profiles/protocol")
            if context.provenance != requirement.expected_provenance:
                raise ValueError(
                    "qualification differs from pinned source/runtime/isolation/artifacts"
                )
            if not verified.ready:
                reasons.append(f"{label}: qualification is {verified.report.overall_status}")
        except (OSError, ValueError, TypeError) as error:
            invalid = True
            reasons.append(f"{label}: {error}")
    if not reasons:
        a, b = binding.a.expected_provenance, binding.b.expected_provenance
        assert a is not None and b is not None  # both qualified above
        if a.source != b.source or a.sentinels != b.sentinels:
            invalid = True
            reasons.append("pair source/sentinel configurations differ")
    status = (
        BindingStatus.INVALID
        if invalid
        else BindingStatus.NOT_READY
        if reasons
        else BindingStatus.READY
    )
    return BindingResult(
        binding.benchmark_id,
        status,
        tuple(reasons),
        tuple(digests),
        (binding.a.target.target_version, binding.b.target.target_version),
    )


def write_catalog(path: Path, catalog: EvaluationCatalog) -> str:
    if not isinstance(catalog, EvaluationCatalog):
        raise ValueError("expected an EvaluationCatalog")
    return write_record(path, catalog)


def validate_catalog(
    path: Path, *, expected_sha256: str | None = None
) -> tuple[BindingResult, ...]:
    """READY is derived from freshly verified links; no stored READY flag is trusted."""
    catalog = read_record(path, EvaluationCatalog, expected_sha256=expected_sha256)
    return tuple(_validate_binding(binding, path.parent) for binding in catalog.bindings)


def require_ready(
    path: Path, benchmark_id: str, *, expected_sha256: str | None = None
) -> BindingResult:
    matches = tuple(
        result
        for result in validate_catalog(path, expected_sha256=expected_sha256)
        if result.benchmark_id == benchmark_id
    )
    if len(matches) != 1 or matches[0].status != BindingStatus.READY:
        raise VerificationError("benchmark is not backed by fully verified qualification")
    return matches[0]

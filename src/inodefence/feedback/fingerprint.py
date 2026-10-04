"""Stable semantic contract-evidence classes, separate from raw run evidence."""

from dataclasses import dataclass

from inodefence.model import (
    ChangeField,
    ContractId,
    IdentityEvidence,
    StateChange,
    ViolationResult,
)
from inodefence.model.filesystem import (
    Region,
    path_region,
    validate_change_fields,
    validate_observed_path,
)


@dataclass(frozen=True, slots=True)
class ChangeFingerprint:
    """Changed observed path and field labels, without either raw observation.

    Labels retain identity/timestamp changes; their volatile values are omitted.
    Existence creation and deletion intentionally share the same evidence class.
    """

    path: str
    fields: tuple[ChangeField, ...]

    def __post_init__(self) -> None:
        validate_observed_path(self.path)
        validate_change_fields(self.fields)


@dataclass(frozen=True, slots=True)
class IdentityFingerprint:
    """Observed internal/sentinel relation, independent of device/inode allocation."""

    internal_path: str
    sentinel_path: str

    def __post_init__(self) -> None:
        validate_observed_path(self.internal_path)
        validate_observed_path(self.sentinel_path)
        if path_region(self.internal_path) != Region.EXTRACTION or (
            path_region(self.sentinel_path) != Region.EXTERNAL
        ):
            raise ValueError("identity fingerprint requires internal and external paths")


@dataclass(frozen=True, slots=True)
class ViolationFingerprint:
    """One contract's canonical evidence class for search novelty, not a verdict.

    Evidence is a sorted unique tuple of semantic changes or identity relations.
    An additional path/relation changes this whole-contract class. Raw evidence
    and limitations stay in RunResult for reproduction and interpretation.
    """

    contract_id: ContractId
    evidence: tuple[ChangeFingerprint | IdentityFingerprint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.contract_id, ContractId):
            raise ValueError("fingerprint requires a ContractId")
        evidence_type = (
            IdentityFingerprint if self.contract_id == ContractId.C1 else ChangeFingerprint
        )
        if (
            not isinstance(self.evidence, tuple)
            or not self.evidence
            or not all(isinstance(item, evidence_type) for item in self.evidence)
        ):
            raise ValueError("fingerprint requires a nonempty tuple of contract evidence")
        if self.evidence != tuple(sorted(set(self.evidence), key=_evidence_key)):
            raise ValueError("fingerprint evidence must be unique and sorted")


def _evidence_fingerprint(
    item: StateChange | IdentityEvidence,
) -> ChangeFingerprint | IdentityFingerprint:
    if isinstance(item, IdentityEvidence):
        return IdentityFingerprint(item.internal_path, item.sentinel_path)
    return ChangeFingerprint(item.path, item.fields)


def _evidence_key(item: ChangeFingerprint | IdentityFingerprint) -> tuple[str, ...]:
    if isinstance(item, IdentityFingerprint):
        return ("identity", item.internal_path, item.sentinel_path)
    return ("change", item.path, *(field.value for field in item.fields))


def violation_fingerprints(
    violations: tuple[ViolationResult, ...],
) -> tuple[ViolationFingerprint, ...]:
    """Summarize violated C0/C1/C2 results in deterministic, duplicate-free order.

    Consume the Oracle's existing verdicts without evaluating Security Contracts.
    C0/C2 keep path and changed-field labels; C1 keeps internal/sentinel paths.
    Device/inode allocation, timestamps, before/after values and explanation or
    limitations text are excluded. Nonviolations produce no key. New classes
    are contract-violation candidates for search, requiring later review.
    """
    fingerprints = {
        ViolationFingerprint(
            result.contract_id,
            tuple(
                sorted({_evidence_fingerprint(item) for item in result.evidence}, key=_evidence_key)
            ),
        )
        for result in violations
        if result.violated
    }
    return tuple(
        sorted(
            fingerprints,
            key=lambda fingerprint: (
                fingerprint.contract_id.value,
                tuple(_evidence_key(item) for item in fingerprint.evidence),
            ),
        )
    )

"""Stable semantic contract-evidence classes, separate from raw run evidence."""

from dataclasses import dataclass

from inodefence.model import (
    ChangeField,
    ContractId,
    IdentityEvidence,
    StateChange,
    ViolationResult,
)


@dataclass(frozen=True, slots=True)
class ChangeFingerprint:
    """Changed observed path and field labels, without either raw observation.

    Labels retain identity/timestamp changes; their volatile values are omitted.
    Existence creation and deletion intentionally share the same evidence class.
    """

    path: str
    fields: tuple[ChangeField, ...]


@dataclass(frozen=True, slots=True)
class IdentityFingerprint:
    """Observed internal/sentinel relation, independent of device/inode allocation."""

    internal_path: str
    sentinel_path: str


@dataclass(frozen=True, slots=True)
class ViolationFingerprint:
    """One contract's canonical evidence class for search novelty, not a verdict.

    Evidence is a sorted unique tuple of semantic changes or identity relations.
    An additional path/relation changes this whole-contract class. Raw evidence
    and limitations stay in RunResult for reproduction and interpretation.
    """

    contract_id: ContractId
    evidence: tuple[ChangeFingerprint | IdentityFingerprint, ...]


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

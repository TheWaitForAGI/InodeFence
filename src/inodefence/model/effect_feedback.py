"""Finite normalized feedback values derived from qualified effect evidence."""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from .archive import EntryType
from .effect import (
    CausalRelationKind,
    EffectClass,
    EffectEvidenceStrength,
    OperationOutcome,
)
from .filesystem import Region


class EffectOrdinalClass(StrEnum):
    FIRST = "first"
    EARLY = "early"
    LATE = "late"


class IdentityRelationType(StrEnum):
    NONE = "none"
    SAME_OBJECT_CREATED = "same_object_created"
    SAME_OBJECT_REMOVED = "same_object_removed"


class EffectFeedbackKeyKind(StrEnum):
    INDIVIDUAL_EFFECT = "individual_effect"
    ENTRY_EFFECT_SET = "entry_effect_set"
    CAUSAL_MOTIF = "causal_motif"
    # M3: a boundary-approach *attempt* — the target issued (or refused) a link
    # operation whose observed target path lies outside the extraction root. It is
    # the only effect key that may come from a non-SUCCESS (cleanly rejected) trace,
    # and only under the opt-in boundary-attempt arm. Additive; see effect.py.
    BOUNDARY_ESCAPE_ATTEMPT = "boundary_escape_attempt"


class BoundaryAttemptShape(StrEnum):
    """Target-agnostic shape of an attempted escaping link target.

    Bucketed from the raw link text's leading parent-traversal depth (or absolute
    prefix). It names no concrete path, protected object, sentinel, tail, CVE or
    PoC: only how the attempt steps out of the extraction root. Tail proximity to
    any specific external object is never encoded.
    """

    ABSOLUTE = "absolute"
    PARENT_1 = "parent_1"
    PARENT_2 = "parent_2"
    PARENT_3_PLUS = "parent_3_plus"


class CausalArchiveRelation(StrEnum):
    SAME_ENTRY = "same_entry"
    EARLIER_TO_LATER = "earlier_to_later"
    LATER_TO_EARLIER = "later_to_earlier"


@dataclass(frozen=True, slots=True)
class NormalizedEffectSignature:
    serialization_schema: ClassVar[int] = 2

    trigger_entry_type: EntryType
    trigger_ordinal_class: EffectOrdinalClass
    effect_class: EffectClass
    affected_regions: tuple[Region, ...]
    protected_external: bool
    identity_relation: IdentityRelationType
    identity_member_regions: tuple[Region, ...]
    operation_outcome: OperationOutcome
    evidence_strength: EffectEvidenceStrength

    def __post_init__(self) -> None:
        if not isinstance(self.trigger_entry_type, EntryType) or not isinstance(
            self.trigger_ordinal_class, EffectOrdinalClass
        ):
            raise ValueError("normalized effect requires trigger entry metadata")
        if (
            not isinstance(self.effect_class, EffectClass)
            or self.effect_class == EffectClass.OPERATION_OBSERVED
        ):
            raise ValueError("normalized effect requires a realized effect class")
        if (
            not isinstance(self.affected_regions, tuple)
            or not 1 <= len(self.affected_regions) <= 2
            or not all(isinstance(region, Region) for region in self.affected_regions)
        ):
            raise ValueError("normalized effect requires one or two path-role regions")
        if type(self.protected_external) is not bool:
            raise ValueError("normalized effect protected marker must be bool")
        if not isinstance(self.identity_relation, IdentityRelationType):
            raise ValueError("normalized effect requires an identity relation class")
        if self.identity_relation == IdentityRelationType.NONE:
            if self.identity_member_regions:
                raise ValueError("non-identity effects cannot carry identity member regions")
        elif len(self.identity_member_regions) != 2 or not all(
            isinstance(region, Region) for region in self.identity_member_regions
        ):
            raise ValueError("identity effects require two member regions")
        if self.operation_outcome != OperationOutcome.SUCCEEDED:
            raise ValueError("initial normalized effect keys require successful realized effects")
        if self.evidence_strength == EffectEvidenceStrength.OPERATION_RESULT:
            raise ValueError("operation-result evidence cannot form a realized effect key")

    def sort_key(self) -> tuple[object, ...]:
        return (
            self.trigger_entry_type.value,
            self.trigger_ordinal_class.value,
            self.effect_class.value,
            tuple(region.value for region in self.affected_regions),
            self.protected_external,
            self.identity_relation.value,
            tuple(region.value for region in self.identity_member_regions),
            self.operation_outcome.value,
            self.evidence_strength.value,
        )


@dataclass(frozen=True, slots=True)
class EntryEffectSetSignature:
    serialization_schema: ClassVar[int] = 2

    trigger_entry_type: EntryType
    trigger_ordinal_class: EffectOrdinalClass
    effects: tuple[NormalizedEffectSignature, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.trigger_entry_type, EntryType) or not isinstance(
            self.trigger_ordinal_class, EffectOrdinalClass
        ):
            raise ValueError("entry effect set requires trigger metadata")
        if (
            not isinstance(self.effects, tuple)
            or not self.effects
            or not all(isinstance(effect, NormalizedEffectSignature) for effect in self.effects)
            or len(set(self.effects)) != len(self.effects)
        ):
            raise ValueError("entry effect set requires unique normalized effects")
        if any(
            effect.trigger_entry_type != self.trigger_entry_type
            or effect.trigger_ordinal_class != self.trigger_ordinal_class
            for effect in self.effects
        ):
            raise ValueError("entry effect set members must match their trigger")
        if self.effects != tuple(sorted(self.effects, key=lambda effect: effect.sort_key())):
            raise ValueError("entry effect set members must be in canonical order")


@dataclass(frozen=True, slots=True)
class CausalMotifSignature:
    serialization_schema: ClassVar[int] = 2

    cause: NormalizedEffectSignature
    consequence: NormalizedEffectSignature
    relation_kind: CausalRelationKind
    archive_relation: CausalArchiveRelation

    def __post_init__(self) -> None:
        if not isinstance(self.cause, NormalizedEffectSignature) or not isinstance(
            self.consequence, NormalizedEffectSignature
        ):
            raise ValueError("causal motif requires normalized effect endpoints")
        if self.relation_kind not in (
            CausalRelationKind.HANDLE_PROVENANCE,
            CausalRelationKind.EXPLICIT_OPERATION_DEPENDENCY,
            CausalRelationKind.IDENTITY_PROVENANCE,
        ):
            raise ValueError("causal motif requires a qualified cross-effect relation")
        if not isinstance(self.archive_relation, CausalArchiveRelation):
            raise ValueError("causal motif requires an archive relation class")


@dataclass(frozen=True, slots=True)
class BoundaryAttemptSignature:
    """One attempted hardlink whose observed target path escapes the extraction root.

    Unlike NormalizedEffectSignature this does not require a *realized* success: it
    describes the attempt itself (the target issued or refused a link to an object
    outside the root), so it can be derived from a cleanly recorded rejected trace.
    It names no concrete path, protected object, sentinel, tail, CVE or PoC: only
    the trigger entry kind, the observed target region, the operation outcome, and a
    bounded escape shape. This is the dense boundary-approach signal that the
    all-or-nothing C0/C1/C2 verdicts miss while the escaping attempt is refused.
    """

    serialization_schema: ClassVar[int] = 1

    trigger_entry_type: EntryType
    target_region: Region
    operation_outcome: OperationOutcome
    escape_shape: BoundaryAttemptShape

    def __post_init__(self) -> None:
        if not isinstance(self.trigger_entry_type, EntryType):
            raise ValueError("boundary attempt requires a trigger entry type")
        if not isinstance(self.target_region, Region) or self.target_region == Region.EXTRACTION:
            raise ValueError("boundary attempt target region must be outside the extraction root")
        if not isinstance(self.operation_outcome, OperationOutcome):
            raise ValueError("boundary attempt requires an operation outcome")
        if not isinstance(self.escape_shape, BoundaryAttemptShape):
            raise ValueError("boundary attempt requires a bounded escape shape")

    def sort_key(self) -> tuple[object, ...]:
        return (
            self.trigger_entry_type.value,
            self.target_region.value,
            self.operation_outcome.value,
            self.escape_shape.value,
        )


EffectFeedbackSignature = (
    NormalizedEffectSignature
    | EntryEffectSetSignature
    | CausalMotifSignature
    | BoundaryAttemptSignature
)


@dataclass(frozen=True, slots=True)
class EffectFeedbackKey:
    serialization_schema: ClassVar[int] = 2

    kind: EffectFeedbackKeyKind
    signature: EffectFeedbackSignature

    def __post_init__(self) -> None:
        expected = {
            EffectFeedbackKeyKind.INDIVIDUAL_EFFECT: NormalizedEffectSignature,
            EffectFeedbackKeyKind.ENTRY_EFFECT_SET: EntryEffectSetSignature,
            EffectFeedbackKeyKind.CAUSAL_MOTIF: CausalMotifSignature,
            EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT: BoundaryAttemptSignature,
        }
        if not isinstance(self.kind, EffectFeedbackKeyKind) or not isinstance(
            self.signature, expected.get(self.kind, object)
        ):
            raise ValueError("effect feedback key kind must match its signature")

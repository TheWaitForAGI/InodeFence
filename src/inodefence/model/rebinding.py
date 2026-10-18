"""Additive v3 evidence for verified multi-operation namespace rebinding."""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from ._validation import validate_sha256
from .archive import EntryType
from .effect import (
    EffectClass,
    EffectPathEvidence,
    FilesystemEffectEvent,
    RawEvidenceReference,
    effect_is_realized,
)
from .effect_feedback import EffectFeedbackKey, EffectOrdinalClass
from .filesystem import ObjectType, Region, validate_observed_path
from .transition import ArchiveEntryReference


class RebindingDependencyKind(StrEnum):
    PRODUCER_BRANCH_CONTINUATION = "producer_branch_continuation"


class RebindingCreationKind(StrEnum):
    OBJECT = "object"
    SYMLINK = "symlink"
    HARDLINK_RELATION = "hardlink_relation"


class RebindingEvidenceLevel(StrEnum):
    DEPENDENCY_VERIFIED_STATE_CHANGE_VERIFIED = "dependency_verified_state_change_verified"


class RebindingFeedbackKeyKind(StrEnum):
    NAMESPACE_REBINDING_SEQUENCE = "namespace_rebinding_sequence"


@dataclass(frozen=True, slots=True)
class RebindingOperationDependency:
    """Producer-issued edge; sequence order alone cannot construct this record."""

    serialization_schema: ClassVar[int] = 3

    dependency_id: str
    predecessor_correlation_id: str
    successor_correlation_id: str
    predecessor_completion_sequence: int
    successor_start_sequence: int
    kind: RebindingDependencyKind
    evidence_token: str
    source_id: str
    v2_raw_stream_sha256: str
    v3_raw_stream_sha256: str
    raw_evidence: RawEvidenceReference

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (
                self.dependency_id,
                self.predecessor_correlation_id,
                self.successor_correlation_id,
                self.evidence_token,
                self.source_id,
            )
        ):
            raise ValueError("rebinding dependency requires nonempty identity fields")
        if (
            type(self.predecessor_completion_sequence) is not int
            or type(self.successor_start_sequence) is not int
            or self.predecessor_completion_sequence < 0
            or self.successor_start_sequence <= self.predecessor_completion_sequence
        ):
            raise ValueError("rebinding dependency endpoints must be ordered sequences")
        if not isinstance(self.kind, RebindingDependencyKind):
            raise ValueError("rebinding dependency requires a supported provenance kind")
        validate_sha256(self.v2_raw_stream_sha256)
        validate_sha256(self.v3_raw_stream_sha256)
        if not isinstance(self.raw_evidence, RawEvidenceReference) or (
            self.raw_evidence.source_id != self.source_id
        ):
            raise ValueError("rebinding dependency raw evidence must match its source")


@dataclass(frozen=True, slots=True)
class NamespaceRebindingSequence:
    """A verified removal-to-creation chain, distinct from v2 replacement."""

    serialization_schema: ClassVar[int] = 3

    entry: ArchiveEntryReference
    destination_path: str
    removal: FilesystemEffectEvent
    creation: FilesystemEffectEvent
    removal_destination_evidence: EffectPathEvidence
    creation_destination_evidence: EffectPathEvidence
    dependency: RebindingOperationDependency
    creation_kind: RebindingCreationKind
    hardlink_source_path: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.entry, ArchiveEntryReference):
            raise ValueError("rebinding sequence requires an archive entry")
        validate_observed_path(self.destination_path)
        if not isinstance(self.removal, FilesystemEffectEvent) or not isinstance(
            self.creation, FilesystemEffectEvent
        ):
            raise ValueError("rebinding sequence requires two v2 effect events")
        if self.removal.entry != self.entry or self.creation.entry != self.entry:
            raise ValueError("rebinding sequence endpoints must share the archive entry")
        if self.removal.effect_class != EffectClass.NAMESPACE_REMOVAL or not effect_is_realized(
            self.removal
        ):
            raise ValueError("rebinding removal must be a realized namespace removal")
        creation_classes = {
            RebindingCreationKind.OBJECT: EffectClass.NAMESPACE_CREATION,
            RebindingCreationKind.SYMLINK: EffectClass.SYMLINK_CREATION,
            RebindingCreationKind.HARDLINK_RELATION: (
                EffectClass.HARDLINK_IDENTITY_RELATION_CREATION
            ),
        }
        if (
            not isinstance(self.creation_kind, RebindingCreationKind)
            or self.creation.effect_class != creation_classes[self.creation_kind]
            or not effect_is_realized(self.creation)
        ):
            raise ValueError("rebinding creation kind must match a realized creation event")
        if (
            not isinstance(self.removal_destination_evidence, EffectPathEvidence)
            or not isinstance(self.creation_destination_evidence, EffectPathEvidence)
            or self.removal_destination_evidence.path != self.destination_path
            or self.creation_destination_evidence.path != self.destination_path
        ):
            raise ValueError("rebinding endpoint evidence must share the destination path")
        removal_evidence = self.removal_destination_evidence
        creation_evidence = self.creation_destination_evidence
        if (
            removal_evidence.before.object is None
            or removal_evidence.after.object is not None
            or creation_evidence.before.object is not None
            or creation_evidence.after.object is None
        ):
            raise ValueError("rebinding requires present-to-absent then absent-to-present")
        if self.removal.object_evidence != (self.removal_destination_evidence,):
            raise ValueError("rebinding removal evidence must be its exact v2 endpoint evidence")
        if not isinstance(self.dependency, RebindingOperationDependency) or (
            self.dependency.predecessor_correlation_id != self.removal.correlation_id
            or self.dependency.successor_correlation_id != self.creation.correlation_id
            or self.dependency.predecessor_completion_sequence != self.removal.completion_sequence
            or self.dependency.successor_start_sequence != self.creation.start_sequence
        ):
            raise ValueError("rebinding dependency must bind the exact endpoint operations")
        if self.creation_kind == RebindingCreationKind.HARDLINK_RELATION:
            if self.hardlink_source_path is None:
                raise ValueError("hardlink rebinding requires its source path")
            validate_observed_path(self.hardlink_source_path)
            if self.hardlink_source_path == self.destination_path:
                raise ValueError("hardlink source and destination must differ")
            if (
                len(self.creation.object_evidence) != 2
                or self.creation.object_evidence[0].path != self.hardlink_source_path
                or self.creation.object_evidence[1] != self.creation_destination_evidence
            ):
                raise ValueError("hardlink rebinding must use exact source/destination roles")
        elif self.hardlink_source_path is not None:
            raise ValueError("only hardlink rebinding carries a source path")
        elif self.creation.object_evidence != (self.creation_destination_evidence,):
            raise ValueError("rebinding creation evidence must be its exact v2 endpoint evidence")

    @property
    def before_object_type(self) -> ObjectType:
        before = self.removal_destination_evidence.before.object
        assert before is not None
        return before.object_type

    @property
    def after_object_type(self) -> ObjectType:
        after = self.creation_destination_evidence.after.object
        assert after is not None
        return after.object_type


@dataclass(frozen=True, slots=True)
class NamespaceRebindingSignature:
    """Finite v3 projection; raw path, identity and dependency IDs are excluded."""

    serialization_schema: ClassVar[int] = 3

    trigger_entry_type: EntryType
    trigger_ordinal_class: EffectOrdinalClass
    destination_region: Region
    protected_external: bool
    before_object_type: ObjectType
    after_object_type: ObjectType
    creation_kind: RebindingCreationKind
    hardlink_source_region: Region | None
    evidence_level: RebindingEvidenceLevel

    def __post_init__(self) -> None:
        if not isinstance(self.trigger_entry_type, EntryType) or not isinstance(
            self.trigger_ordinal_class, EffectOrdinalClass
        ):
            raise ValueError("rebinding signature requires trigger metadata")
        if (
            not isinstance(self.destination_region, Region)
            or type(self.protected_external) is not bool
        ):
            raise ValueError("rebinding signature requires destination classification")
        if self.protected_external and self.destination_region != Region.EXTERNAL:
            raise ValueError("only external destinations can be protected")
        if not isinstance(self.before_object_type, ObjectType) or not isinstance(
            self.after_object_type, ObjectType
        ):
            raise ValueError("rebinding signature requires endpoint object types")
        if not isinstance(self.creation_kind, RebindingCreationKind):
            raise ValueError("rebinding signature requires a creation kind")
        if (self.creation_kind == RebindingCreationKind.HARDLINK_RELATION) != isinstance(
            self.hardlink_source_region, Region
        ):
            raise ValueError("only hardlink signatures require a source region")
        if self.evidence_level != RebindingEvidenceLevel.DEPENDENCY_VERIFIED_STATE_CHANGE_VERIFIED:
            raise ValueError("rebinding signature requires the fixed verified evidence level")

    def sort_key(self) -> tuple[object, ...]:
        return (
            self.trigger_entry_type.value,
            self.trigger_ordinal_class.value,
            self.destination_region.value,
            self.protected_external,
            self.before_object_type.value,
            self.after_object_type.value,
            self.creation_kind.value,
            None if self.hardlink_source_region is None else self.hardlink_source_region.value,
            self.evidence_level.value,
        )


@dataclass(frozen=True, slots=True)
class NamespaceRebindingFeedbackKey:
    serialization_schema: ClassVar[int] = 3

    kind: RebindingFeedbackKeyKind
    signature: NamespaceRebindingSignature

    def __post_init__(self) -> None:
        if self.kind != RebindingFeedbackKeyKind.NAMESPACE_REBINDING_SEQUENCE or not isinstance(
            self.signature, NamespaceRebindingSignature
        ):
            raise ValueError("rebinding feedback key kind must match its signature")


@dataclass(frozen=True, slots=True)
class EffectFeedbackProjectionV3:
    """Additive projection that preserves the exact v2 key tuple."""

    serialization_schema: ClassVar[int] = 3

    v2_keys: tuple[EffectFeedbackKey, ...]
    rebinding_keys: tuple[NamespaceRebindingFeedbackKey, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.v2_keys, tuple) or not all(
            isinstance(key, EffectFeedbackKey) for key in self.v2_keys
        ):
            raise ValueError("v3 projection requires the retained v2 keys")
        if not isinstance(self.rebinding_keys, tuple) or not all(
            isinstance(key, NamespaceRebindingFeedbackKey) for key in self.rebinding_keys
        ):
            raise ValueError("v3 projection requires typed rebinding keys")

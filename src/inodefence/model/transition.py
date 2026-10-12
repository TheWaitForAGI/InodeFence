"""Target-independent entry-boundary observations and filesystem transitions."""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from .archive import EntryType
from .filesystem import (
    ChangeField,
    ExternalEffect,
    ObjectSnapshot,
    ObjectType,
    Region,
    SnapshotPhase,
    StateChange,
    StateSnapshot,
    observed_change_fields,
    path_region,
    validate_observed_path,
)


class ObservationKind(StrEnum):
    BEFORE = "before"
    ENTRY_BOUNDARY = "entry_boundary"


class ObservationCompleteness(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class TraceCompleteness(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class TraceTermination(StrEnum):
    SUCCESS = "success"
    TARGET_REJECTED = "target_rejected"
    TARGET_FAILED = "target_failed"
    TARGET_TIMEOUT = "target_timeout"
    EVENT_STREAM_MALFORMED = "event_stream_malformed"
    ENTRY_CHECKPOINT_MISMATCH = "entry_checkpoint_mismatch"
    OBSERVER_FAILURE = "observer_failure"
    EXECUTION_BACKEND_FAILURE = "execution_backend_failure"
    CLEANUP_FAILURE = "cleanup_failure"


@dataclass(frozen=True, slots=True)
class ArchiveEntryReference:
    """Logical archive occurrence identity; duplicate paths remain distinct."""

    entry_index: int
    path: str
    entry_type: EntryType
    link_target: str | None

    @classmethod
    def from_entry(
        cls, entry_index: int, path: str, entry_type: EntryType, link_target: str | None
    ) -> "ArchiveEntryReference":
        return cls(entry_index, path, entry_type, link_target)

    def __post_init__(self) -> None:
        if type(self.entry_index) is not int or self.entry_index < 0:
            raise ValueError("entry_index must be a nonnegative integer")
        if not isinstance(self.path, str) or not self.path or "\0" in self.path:
            raise ValueError("entry path must be nonempty text without NUL")
        self.path.encode("utf-8", "strict")
        if not isinstance(self.entry_type, EntryType):
            raise ValueError("entry_type must be an EntryType")
        is_link = self.entry_type in (EntryType.HARDLINK, EntryType.SYMLINK)
        if is_link != (self.link_target is not None):
            raise ValueError("only link entry references require a link target")
        if self.link_target is not None:
            if not self.link_target or "\0" in self.link_target:
                raise ValueError("link target must be nonempty text without NUL")
            self.link_target.encode("utf-8", "strict")


@dataclass(frozen=True, slots=True)
class ObservationPoint:
    """A static lifecycle kind composed with an optional dynamic entry identity."""

    kind: ObservationKind
    entry: ArchiveEntryReference | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ObservationKind):
            raise ValueError("observation kind must be an ObservationKind")
        if (self.kind == ObservationKind.ENTRY_BOUNDARY) != (self.entry is not None):
            raise ValueError("only entry-boundary observations require an entry reference")


@dataclass(frozen=True, slots=True)
class EntryCheckpoint:
    """One immutable complete filesystem observation in checkpoint order.

    Monotonic timestamps and raw object identities are evidence only. They are
    deliberately absent from normalized transition signatures.
    """

    serialization_schema: ClassVar[int] = 1

    checkpoint_index: int
    point: ObservationPoint
    sandbox_root: str
    objects: tuple[ObjectSnapshot, ...]
    protected_paths: tuple[str, ...]
    observation_started_ns: int
    observation_finished_ns: int
    completeness: ObservationCompleteness = ObservationCompleteness.COMPLETE

    def __post_init__(self) -> None:
        if type(self.checkpoint_index) is not int or self.checkpoint_index < 0:
            raise ValueError("checkpoint_index must be a nonnegative integer")
        if not isinstance(self.point, ObservationPoint):
            raise ValueError("checkpoint requires an ObservationPoint")
        if not isinstance(self.sandbox_root, str) or not self.sandbox_root.startswith("/"):
            raise ValueError("checkpoint requires an absolute sandbox root")
        if not isinstance(self.objects, tuple) or not all(
            isinstance(obj, ObjectSnapshot) for obj in self.objects
        ):
            raise ValueError("checkpoint objects must be ObjectSnapshot records")
        paths = tuple(obj.path for obj in self.objects)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("checkpoint objects must have unique sorted paths")
        if (
            not isinstance(self.protected_paths, tuple)
            or not all(isinstance(path, str) for path in self.protected_paths)
            or self.protected_paths != tuple(sorted(set(self.protected_paths)))
        ):
            raise ValueError("protected paths must be a unique sorted tuple")
        for path in self.protected_paths:
            validate_observed_path(path)
            if path_region(path) != Region.EXTERNAL:
                raise ValueError("protected paths must be external")
        if (
            type(self.observation_started_ns) is not int
            or type(self.observation_finished_ns) is not int
            or self.observation_started_ns < 0
            or self.observation_finished_ns < self.observation_started_ns
        ):
            raise ValueError("observation timestamps must be ordered nonnegative nanoseconds")
        if not isinstance(self.completeness, ObservationCompleteness):
            raise ValueError("checkpoint completeness must be explicit")

    @property
    def observation_duration_ns(self) -> int:
        return self.observation_finished_ns - self.observation_started_ns

    def get(self, path: str) -> ObjectSnapshot | None:
        return next((obj for obj in self.objects if obj.path == path), None)

    def identity_groups(self) -> tuple[tuple[str, ...], ...]:
        groups: dict[tuple[int, int], list[str]] = {}
        for obj in self.objects:
            groups.setdefault(obj.identity, []).append(obj.path)
        return tuple(sorted(tuple(paths) for paths in groups.values() if len(paths) > 1))


def _changes(previous: EntryCheckpoint, current: EntryCheckpoint) -> tuple[StateChange, ...]:
    old = {obj.path: obj for obj in previous.objects}
    new = {obj.path: obj for obj in current.objects}
    changes = []
    for path in sorted(old.keys() | new.keys()):
        before, after = old.get(path), new.get(path)
        fields = observed_change_fields(before, after)
        if fields:
            changes.append(StateChange(path, before, after, fields))
    return tuple(changes)


@dataclass(frozen=True, slots=True)
class FilesystemTransition:
    """Exact raw delta between consecutive complete checkpoints."""

    serialization_schema: ClassVar[int] = 1

    transition_index: int
    before_checkpoint_index: int
    after_checkpoint_index: int
    trigger: ArchiveEntryReference
    changes: tuple[StateChange, ...]
    identity_groups_created: tuple[tuple[str, ...], ...]
    identity_groups_removed: tuple[tuple[str, ...], ...]
    external_effects: tuple[ExternalEffect, ...]
    protected_external_effects: tuple[ExternalEffect, ...]

    def __post_init__(self) -> None:
        if type(self.transition_index) is not int or self.transition_index < 0:
            raise ValueError("transition_index must be a nonnegative integer")
        if (
            type(self.before_checkpoint_index) is not int
            or type(self.after_checkpoint_index) is not int
            or self.before_checkpoint_index < 0
            or self.after_checkpoint_index != self.before_checkpoint_index + 1
        ):
            raise ValueError("transition checkpoints must be consecutive")
        if not isinstance(self.trigger, ArchiveEntryReference):
            raise ValueError("transition requires an archive entry trigger")
        if not isinstance(self.changes, tuple) or not all(
            isinstance(change, StateChange) for change in self.changes
        ):
            raise ValueError("transition changes must be StateChange records")
        if tuple(change.path for change in self.changes) != tuple(
            sorted({change.path for change in self.changes})
        ):
            raise ValueError("transition changes must have unique sorted paths")
        for groups in (self.identity_groups_created, self.identity_groups_removed):
            if (
                not isinstance(groups, tuple)
                or groups != tuple(sorted(set(groups)))
                or not all(
                    isinstance(group, tuple)
                    and len(group) >= 2
                    and group == tuple(sorted(set(group)))
                    and all(isinstance(path, str) for path in group)
                    for group in groups
                )
            ):
                raise ValueError("identity-group deltas must be unique sorted path groups")
        if set(self.identity_groups_created).intersection(self.identity_groups_removed):
            raise ValueError("an identity group cannot be both created and removed")
        for effects in (self.external_effects, self.protected_external_effects):
            if not isinstance(effects, tuple) or not all(
                isinstance(effect, ExternalEffect) for effect in effects
            ):
                raise ValueError("external effects must be ExternalEffect records")
            if tuple(effect.path for effect in effects) != tuple(
                sorted({effect.path for effect in effects})
            ):
                raise ValueError("external effects must have unique sorted paths")
        if not set(self.protected_external_effects) <= set(self.external_effects):
            raise ValueError("protected effects must be a subset of external effects")


def derive_transition(
    previous: EntryCheckpoint, current: EntryCheckpoint, transition_index: int
) -> FilesystemTransition:
    """Build a raw transition without target or security-policy knowledge."""
    if not isinstance(previous, EntryCheckpoint) or not isinstance(current, EntryCheckpoint):
        raise ValueError("transition comparison requires EntryCheckpoint records")
    if previous.completeness != ObservationCompleteness.COMPLETE or (
        current.completeness != ObservationCompleteness.COMPLETE
    ):
        raise ValueError("incomplete observations cannot produce transitions")
    if (
        previous.sandbox_root != current.sandbox_root
        or previous.protected_paths != current.protected_paths
        or current.checkpoint_index != previous.checkpoint_index + 1
        or current.point.kind != ObservationKind.ENTRY_BOUNDARY
        or current.point.entry is None
    ):
        raise ValueError("transition requires consecutive same-run entry checkpoints")
    changes = _changes(previous, current)
    old_groups, new_groups = set(previous.identity_groups()), set(current.identity_groups())
    effects = tuple(
        ExternalEffect(change.path, change.fields)
        for change in changes
        if path_region(change.path) == Region.EXTERNAL
    )
    protected_effects = tuple(
        effect for effect in effects if effect.path in current.protected_paths
    )
    return FilesystemTransition(
        transition_index,
        previous.checkpoint_index,
        current.checkpoint_index,
        current.point.entry,
        changes,
        tuple(sorted(new_groups - old_groups)),
        tuple(sorted(old_groups - new_groups)),
        effects,
        protected_effects,
    )


def _matches_snapshot(checkpoint: EntryCheckpoint, snapshot: StateSnapshot) -> bool:
    return (
        checkpoint.sandbox_root == snapshot.sandbox_root
        and checkpoint.objects == snapshot.objects
        and checkpoint.protected_paths == snapshot.protected_paths
    )


@dataclass(frozen=True, slots=True)
class TransitionTrace:
    """Ordered completed checkpoints plus an explicit terminal observation.

    Missing checkpoints never become empty transitions. An incomplete trace can
    retain every completed prefix and the final AFTER snapshot independently.
    """

    serialization_schema: ClassVar[int] = 1

    expected_entry_count: int
    checkpoints: tuple[EntryCheckpoint, ...]
    transitions: tuple[FilesystemTransition, ...]
    final_after: StateSnapshot
    completeness: TraceCompleteness
    termination: TraceTermination

    def __post_init__(self) -> None:
        if type(self.expected_entry_count) is not int or self.expected_entry_count < 0:
            raise ValueError("expected_entry_count must be a nonnegative integer")
        if not isinstance(self.checkpoints, tuple) or not self.checkpoints:
            raise ValueError("trace requires at least the BEFORE checkpoint")
        if not all(isinstance(item, EntryCheckpoint) for item in self.checkpoints):
            raise ValueError("trace checkpoints must be EntryCheckpoint records")
        if not isinstance(self.transitions, tuple) or not all(
            isinstance(item, FilesystemTransition) for item in self.transitions
        ):
            raise ValueError("trace transitions must be FilesystemTransition records")
        if not isinstance(self.final_after, StateSnapshot) or (
            self.final_after.phase != SnapshotPhase.AFTER
        ):
            raise ValueError("trace requires an explicit final AFTER snapshot")
        if not isinstance(self.completeness, TraceCompleteness) or not isinstance(
            self.termination, TraceTermination
        ):
            raise ValueError("trace completeness and termination must be explicit")
        first = self.checkpoints[0]
        if (
            first.checkpoint_index != 0
            or first.point.kind != ObservationKind.BEFORE
            or first.point.entry is not None
            or first.completeness != ObservationCompleteness.COMPLETE
        ):
            raise ValueError("trace must start with one complete BEFORE checkpoint")
        if tuple(item.checkpoint_index for item in self.checkpoints) != tuple(
            range(len(self.checkpoints))
        ):
            raise ValueError("checkpoint indexes must be contiguous and monotonic")
        entries = tuple(item.point.entry for item in self.checkpoints[1:])
        if any(entry is None for entry in entries):
            raise ValueError("all post-BEFORE checkpoints must be entry boundaries")
        entry_indexes = tuple(entry.entry_index for entry in entries if entry is not None)
        if entry_indexes != tuple(range(len(entry_indexes))):
            raise ValueError("entry indexes must be a contiguous completed prefix")
        if len(self.transitions) != len(self.checkpoints) - 1:
            raise ValueError("every completed checkpoint edge requires one transition")
        for index, transition in enumerate(self.transitions):
            expected = derive_transition(
                self.checkpoints[index], self.checkpoints[index + 1], index
            )
            if transition != expected:
                raise ValueError("transition does not match its checkpoint observations")
        if (
            self.final_after.sandbox_root != first.sandbox_root
            or self.final_after.protected_paths != first.protected_paths
        ):
            raise ValueError("final AFTER must belong to the checkpoint run")
        complete_indexes = tuple(range(self.expected_entry_count))
        if self.completeness == TraceCompleteness.COMPLETE:
            if entry_indexes != complete_indexes:
                raise ValueError("complete trace requires every archive entry ordinal")
            if not _matches_snapshot(self.checkpoints[-1], self.final_after):
                raise ValueError("complete trace must reconcile its final checkpoint and AFTER")
        elif entry_indexes == complete_indexes and _matches_snapshot(
            self.checkpoints[-1], self.final_after
        ):
            raise ValueError("fully reconciled trace cannot be labeled incomplete")

    @property
    def reconciled(self) -> bool:
        return _matches_snapshot(self.checkpoints[-1], self.final_after)


class TransitionOrdinalClass(StrEnum):
    FIRST = "first"
    EARLY = "early"
    LATE = "late"


class RelationDeltaKind(StrEnum):
    CREATED = "created"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class TransitionObjectEffect:
    """Path-region structural effect with no raw identity or timestamp value."""

    region: Region
    before_type: ObjectType | None
    after_type: ObjectType | None
    fields: tuple[ChangeField, ...]
    protected: bool

    def __post_init__(self) -> None:
        if not isinstance(self.region, Region):
            raise ValueError("transition effect requires a Region")
        if self.before_type is not None and not isinstance(self.before_type, ObjectType):
            raise ValueError("transition before type must be ObjectType or None")
        if self.after_type is not None and not isinstance(self.after_type, ObjectType):
            raise ValueError("transition after type must be ObjectType or None")
        if (
            not isinstance(self.fields, tuple)
            or not self.fields
            or not all(isinstance(field, ChangeField) for field in self.fields)
        ):
            raise ValueError("transition effect requires change fields")
        if type(self.protected) is not bool:
            raise ValueError("transition effect protected marker must be bool")


@dataclass(frozen=True, slots=True, order=True)
class IdentityRelationEffect:
    kind: RelationDeltaKind
    member_regions: tuple[Region, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RelationDeltaKind):
            raise ValueError("identity relation effect requires a delta kind")
        if len(self.member_regions) < 2 or not all(
            isinstance(region, Region) for region in self.member_regions
        ):
            raise ValueError("identity relation effect requires at least two member regions")


def _object_effect_key(
    item: TransitionObjectEffect,
) -> tuple[str, str, str, tuple[str, ...], bool]:
    return (
        item.region.value,
        item.before_type.value if item.before_type is not None else "",
        item.after_type.value if item.after_type is not None else "",
        tuple(field.value for field in item.fields),
        item.protected,
    )


@dataclass(frozen=True, slots=True)
class TransitionSignature:
    """Normalized v1 transition class used for feedback, not raw evidence."""

    serialization_schema: ClassVar[int] = 1

    schema_version: int
    trigger_entry_type: EntryType
    trigger_ordinal_class: TransitionOrdinalClass
    object_effects: tuple[TransitionObjectEffect, ...]
    identity_relation_effects: tuple[IdentityRelationEffect, ...]
    external_effect_fields: tuple[tuple[ChangeField, ...], ...]
    outside_namespace_transition: bool
    internal_external_identity_appeared: bool
    protected_external_effect: bool

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("TransitionSignature requires schema version 1")
        if not isinstance(self.trigger_entry_type, EntryType) or not isinstance(
            self.trigger_ordinal_class, TransitionOrdinalClass
        ):
            raise ValueError("transition signature requires normalized trigger metadata")
        if not isinstance(self.object_effects, tuple) or not all(
            isinstance(item, TransitionObjectEffect) for item in self.object_effects
        ):
            raise ValueError("object effects must be TransitionObjectEffect records")
        if self.object_effects != tuple(sorted(self.object_effects, key=_object_effect_key)):
            raise ValueError("object effects must be sorted")
        if not isinstance(self.identity_relation_effects, tuple) or not all(
            isinstance(item, IdentityRelationEffect) for item in self.identity_relation_effects
        ):
            raise ValueError("identity effects must be IdentityRelationEffect records")
        if self.identity_relation_effects != tuple(sorted(self.identity_relation_effects)):
            raise ValueError("identity effects must be sorted")
        if not isinstance(self.external_effect_fields, tuple) or not all(
            isinstance(fields, tuple) and fields for fields in self.external_effect_fields
        ):
            raise ValueError("external effect classes must be nonempty field tuples")
        if self.external_effect_fields != tuple(sorted(self.external_effect_fields)):
            raise ValueError("external effect classes must be sorted")
        if any(
            type(value) is not bool
            for value in (
                self.outside_namespace_transition,
                self.internal_external_identity_appeared,
                self.protected_external_effect,
            )
        ):
            raise ValueError("transition structural flags must be bool")


@dataclass(frozen=True, slots=True)
class TransitionFeedbackKey:
    serialization_schema: ClassVar[int] = 1

    signature: TransitionSignature

    def __post_init__(self) -> None:
        if not isinstance(self.signature, TransitionSignature):
            raise ValueError("transition feedback key requires a TransitionSignature")


@dataclass(frozen=True, slots=True)
class TransitionSequenceKey:
    """Ordered auxiliary trace pattern; v1 admission uses individual keys."""

    serialization_schema: ClassVar[int] = 1

    keys: tuple[TransitionFeedbackKey, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.keys, tuple) or not all(
            isinstance(key, TransitionFeedbackKey) for key in self.keys
        ):
            raise ValueError("transition sequence requires ordered feedback keys")

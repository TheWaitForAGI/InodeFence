"""Target-independent entry-associated filesystem-effect evidence v2."""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from ._validation import validate_sha256
from .filesystem import (
    ObjectSnapshot,
    ObjectType,
    SnapshotPhase,
    StateSnapshot,
    validate_observed_path,
)
from .transition import ArchiveEntryReference


class EntryLifecycleKind(StrEnum):
    READ = "read"
    EFFECT_WORK_STARTED = "effect_work_started"
    EFFECT_WORK_SETTLED = "effect_work_settled"


class LifecycleStatus(StrEnum):
    SUCCEEDED = "succeeded"
    ERRORED = "errored"


class AssociationKind(StrEnum):
    ASYNC_CONTEXT = "async_context"
    HANDLE_PROVENANCE = "handle_provenance"


class EffectClass(StrEnum):
    OPERATION_OBSERVED = "operation_observed"
    NAMESPACE_CREATION = "namespace_creation"
    NAMESPACE_REMOVAL = "namespace_removal"
    NAMESPACE_REPLACEMENT = "namespace_replacement"
    REGULAR_FILE_CONTENT_MODIFICATION = "regular_file_content_modification"
    TRUNCATION = "truncation"
    METADATA_MODIFICATION = "metadata_modification"
    SYMLINK_CREATION = "symlink_creation"
    HARDLINK_IDENTITY_RELATION_CREATION = "hardlink_identity_relation_creation"
    IDENTITY_RELATION_REMOVAL = "identity_relation_removal"


class EffectEvidenceStrength(StrEnum):
    OPERATION_RESULT = "operation_result"
    IDENTITY_VERIFIED = "identity_verified"
    STATE_CHANGE_VERIFIED = "state_change_verified"


class EffectObservationStatus(StrEnum):
    NOT_OBSERVED = "not_observed"
    ABSENT = "absent"
    PRESENT = "present"


class ObservedOperationType(StrEnum):
    OPEN = "open"
    WRITE = "write"
    WRITEV = "writev"
    CLOSE = "close"
    MKDIR = "mkdir"
    CHMOD = "chmod"
    CHOWN = "chown"
    UTIMES = "utimes"
    FUTIMES = "futimes"
    FCHOWN = "fchown"
    UNLINK = "unlink"
    RMDIR = "rmdir"
    LINK = "link"
    SYMLINK = "symlink"
    RENAME = "rename"
    REMOVE = "remove"
    OTHER = "other"


class OperationOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    ALREADY_EXISTS = "already_exists"
    NOT_FOUND = "not_found"
    ACCESS_DENIED = "access_denied"
    INVALID = "invalid"
    OTHER_ERROR = "other_error"


class CausalRelationKind(StrEnum):
    OPERATION_INTERVAL = "operation_interval"
    ENTRY_CONTEXT_PROPAGATION = "entry_context_propagation"
    HANDLE_PROVENANCE = "handle_provenance"
    EXPLICIT_OPERATION_DEPENDENCY = "explicit_operation_dependency"
    IDENTITY_PROVENANCE = "identity_provenance"


class EffectStreamCompleteness(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


class EffectTargetTermination(StrEnum):
    SUCCESS = "success"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    NOT_STARTED = "not_started"


class ObservationFailureKind(StrEnum):
    EVENT_LOSS = "event_loss"
    DUPLICATE_SEQUENCE = "duplicate_sequence"
    BUFFER_OVERFLOW = "buffer_overflow"
    MALFORMED_IDENTITY = "malformed_identity"
    ASSOCIATION_CONFLICT = "association_conflict"
    OPERATION_CORRELATION_CONFLICT = "operation_correlation_conflict"
    INVALID_CAUSAL_EDGE = "invalid_causal_edge"
    INCOMPLETE_FLUSH = "incomplete_flush"
    SOURCE_READER_DISAGREEMENT = "source_reader_disagreement"
    OBSERVER_FAILURE = "observer_failure"
    EXECUTION_BACKEND_FAILURE = "execution_backend_failure"


class ObservedEventPointKind(StrEnum):
    LIFECYCLE = "lifecycle"
    OPERATION_START = "operation_start"
    OPERATION_COMPLETION = "operation_completion"


@dataclass(frozen=True, slots=True)
class MonotonicInterval:
    started_ns: int
    finished_ns: int

    def __post_init__(self) -> None:
        if (
            type(self.started_ns) is not int
            or type(self.finished_ns) is not int
            or self.started_ns < 0
            or self.finished_ns < self.started_ns
        ):
            raise ValueError("monotonic interval must be ordered nonnegative nanoseconds")


@dataclass(frozen=True, slots=True)
class EvidenceSourceIdentity:
    source_id: str
    mechanism: str
    version: str
    source_sha256: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (self.source_id, self.mechanism, self.version)
        ):
            raise ValueError("evidence source requires nonempty identity fields")
        validate_sha256(self.source_sha256)


@dataclass(frozen=True, slots=True)
class RawEvidenceReference:
    source_id: str
    record_id: str

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value for value in (self.source_id, self.record_id)):
            raise ValueError("raw evidence reference requires source and record IDs")


@dataclass(frozen=True, slots=True)
class EffectObjectObservation:
    status: EffectObservationStatus
    object: ObjectSnapshot | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, EffectObservationStatus):
            raise ValueError("effect object observation requires an explicit status")
        if (self.status == EffectObservationStatus.PRESENT) != (
            isinstance(self.object, ObjectSnapshot)
        ):
            raise ValueError("only present object evidence carries an ObjectSnapshot")

    @property
    def identity(self) -> tuple[int, int] | None:
        return self.object.identity if self.object is not None else None


@dataclass(frozen=True, slots=True)
class EffectPathEvidence:
    path: str
    before: EffectObjectObservation
    after: EffectObjectObservation

    def __post_init__(self) -> None:
        validate_observed_path(self.path)
        if not isinstance(self.before, EffectObjectObservation) or not isinstance(
            self.after, EffectObjectObservation
        ):
            raise ValueError("effect path evidence requires before and after observations")
        for observation in (self.before, self.after):
            if observation.object is not None and observation.object.path != self.path:
                raise ValueError("effect object evidence path must match its path record")


@dataclass(frozen=True, slots=True)
class EntryLifecycleEvent:
    serialization_schema: ClassVar[int] = 2

    sequence: int
    entry: ArchiveEntryReference
    kind: EntryLifecycleKind
    observation: MonotonicInterval
    status: LifecycleStatus
    normalized_error: str | None
    source_id: str
    raw_evidence: RawEvidenceReference

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("lifecycle sequence must be a nonnegative integer")
        if not isinstance(self.entry, ArchiveEntryReference) or not isinstance(
            self.kind, EntryLifecycleKind
        ):
            raise ValueError("lifecycle event requires an entry and lifecycle kind")
        if not isinstance(self.observation, MonotonicInterval) or not isinstance(
            self.status, LifecycleStatus
        ):
            raise ValueError("lifecycle event requires interval and status")
        if (self.status == LifecycleStatus.ERRORED) != (
            isinstance(self.normalized_error, str) and bool(self.normalized_error)
        ):
            raise ValueError("only errored lifecycle events require a normalized error")
        if not isinstance(self.source_id, str) or not self.source_id:
            raise ValueError("lifecycle event requires a source identity")
        if not isinstance(self.raw_evidence, RawEvidenceReference) or (
            self.raw_evidence.source_id != self.source_id
        ):
            raise ValueError("lifecycle raw evidence must match its source")


@dataclass(frozen=True, slots=True)
class FilesystemEffectEvent:
    serialization_schema: ClassVar[int] = 2

    start_sequence: int
    completion_sequence: int
    entry: ArchiveEntryReference
    association: AssociationKind
    effect_class: EffectClass
    evidence_strength: EffectEvidenceStrength
    affected_paths: tuple[str, ...]
    operation: ObservedOperationType
    start_observation: MonotonicInterval
    completion_observation: MonotonicInterval
    outcome: OperationOutcome
    object_evidence: tuple[EffectPathEvidence, ...]
    source_id: str
    correlation_id: str
    raw_evidence: RawEvidenceReference

    def __post_init__(self) -> None:
        if (
            type(self.start_sequence) is not int
            or type(self.completion_sequence) is not int
            or self.start_sequence < 0
            or self.completion_sequence <= self.start_sequence
        ):
            raise ValueError("effect start/completion sequences must be ordered integers")
        if not isinstance(self.entry, ArchiveEntryReference) or not isinstance(
            self.association, AssociationKind
        ):
            raise ValueError("effect event requires entry association")
        if not isinstance(self.effect_class, EffectClass) or not isinstance(
            self.evidence_strength, EffectEvidenceStrength
        ):
            raise ValueError("effect event requires class and evidence strength")
        if (
            not isinstance(self.affected_paths, tuple)
            or not 1 <= len(self.affected_paths) <= 2
            or len(set(self.affected_paths)) != len(self.affected_paths)
        ):
            raise ValueError("effect event requires one path or one ordered path pair")
        for path in self.affected_paths:
            validate_observed_path(path)
        if (
            self.effect_class
            in (
                EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
                EffectClass.IDENTITY_RELATION_REMOVAL,
            )
            and len(self.affected_paths) != 2
        ):
            raise ValueError("identity relation effects require a path pair")
        if not isinstance(self.operation, ObservedOperationType) or not isinstance(
            self.outcome, OperationOutcome
        ):
            raise ValueError("effect event requires operation and outcome")
        if not isinstance(self.start_observation, MonotonicInterval) or not isinstance(
            self.completion_observation, MonotonicInterval
        ):
            raise ValueError("effect event requires start and completion intervals")
        if self.completion_observation.started_ns < self.start_observation.finished_ns:
            raise ValueError("effect completion observation cannot precede operation start")
        if not isinstance(self.object_evidence, tuple) or not all(
            isinstance(item, EffectPathEvidence) for item in self.object_evidence
        ):
            raise ValueError("effect object evidence must be typed records")
        evidence_paths = tuple(item.path for item in self.object_evidence)
        if evidence_paths and evidence_paths != self.affected_paths:
            raise ValueError("effect object evidence must follow affected-path role order")
        if not all(
            isinstance(value, str) and value for value in (self.source_id, self.correlation_id)
        ):
            raise ValueError("effect event requires source and correlation IDs")
        if not isinstance(self.raw_evidence, RawEvidenceReference) or (
            self.raw_evidence.source_id != self.source_id
        ):
            raise ValueError("effect raw evidence must match its source")


def _present(observation: EffectObjectObservation) -> ObjectSnapshot | None:
    return observation.object if observation.status == EffectObservationStatus.PRESENT else None


def _observed(observation: EffectObjectObservation) -> bool:
    return observation.status != EffectObservationStatus.NOT_OBSERVED


def effect_is_realized(event: FilesystemEffectEvent) -> bool:
    """Return whether typed evidence supports the event's successful effect claim.

    This is an evidence-sufficiency check, not a Security Contract verdict.
    """
    if not isinstance(event, FilesystemEffectEvent):
        raise ValueError("effect realization requires a FilesystemEffectEvent")
    if event.outcome != OperationOutcome.SUCCEEDED or (
        event.effect_class == EffectClass.OPERATION_OBSERVED
    ):
        return False
    if not event.object_evidence or tuple(item.path for item in event.object_evidence) != (
        event.affected_paths
    ):
        return False

    evidence = event.object_evidence
    if event.effect_class in (
        EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
        EffectClass.IDENTITY_RELATION_REMOVAL,
    ):
        if event.evidence_strength not in (
            EffectEvidenceStrength.IDENTITY_VERIFIED,
            EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
        ):
            return False
        left, right = evidence
        before_left, before_right = _present(left.before), _present(right.before)
        after_left, after_right = _present(left.after), _present(right.after)
        if not all(
            _observed(observation) for item in evidence for observation in (item.before, item.after)
        ):
            return False
        before_same = (
            before_left is not None
            and before_right is not None
            and before_left.identity == before_right.identity
        )
        after_same = (
            after_left is not None
            and after_right is not None
            and after_left.identity == after_right.identity
        )
        if event.effect_class == EffectClass.HARDLINK_IDENTITY_RELATION_CREATION:
            return not before_same and after_same
        return before_same and not after_same

    if (
        event.evidence_strength != EffectEvidenceStrength.STATE_CHANGE_VERIFIED
        or len(evidence) != 1
    ):
        return False
    path = evidence[0]
    if not _observed(path.before) or not _observed(path.after):
        return False
    before, after = _present(path.before), _present(path.after)
    if event.effect_class == EffectClass.NAMESPACE_CREATION:
        return before is None and after is not None
    if event.effect_class == EffectClass.NAMESPACE_REMOVAL:
        return before is not None and after is None
    if event.effect_class == EffectClass.NAMESPACE_REPLACEMENT:
        return (
            before is not None
            and after is not None
            and (before.identity != after.identity or before.object_type != after.object_type)
        )
    if event.effect_class == EffectClass.SYMLINK_CREATION:
        return before is None and after is not None and after.object_type == ObjectType.SYMLINK
    if before is None or after is None:
        return False
    if event.effect_class == EffectClass.REGULAR_FILE_CONTENT_MODIFICATION:
        return (
            before.object_type == after.object_type == ObjectType.REGULAR
            and before.content_digest != after.content_digest
        )
    if event.effect_class == EffectClass.TRUNCATION:
        return (
            before.object_type == after.object_type == ObjectType.REGULAR
            and after.size < before.size
        )
    if event.effect_class == EffectClass.METADATA_MODIFICATION:
        return any(
            getattr(before, field) != getattr(after, field)
            for field in ("st_nlink", "mode", "uid", "gid", "mtime_ns", "ctime_ns")
        )
    return False


@dataclass(frozen=True, slots=True)
class CausalRelation:
    serialization_schema: ClassVar[int] = 2

    predecessor_sequence: int
    successor_sequence: int
    kind: CausalRelationKind
    source_id: str
    evidence_token: str
    raw_evidence: RawEvidenceReference

    def __post_init__(self) -> None:
        if (
            type(self.predecessor_sequence) is not int
            or type(self.successor_sequence) is not int
            or self.predecessor_sequence < 0
            or self.successor_sequence < 0
            or self.predecessor_sequence == self.successor_sequence
        ):
            raise ValueError("causal relation requires two distinct nonnegative sequences")
        if not isinstance(self.kind, CausalRelationKind):
            raise ValueError("causal relation requires a supported evidence kind")
        if not all(
            isinstance(value, str) and value for value in (self.source_id, self.evidence_token)
        ):
            raise ValueError("causal relation requires source and evidence token")
        if not isinstance(self.raw_evidence, RawEvidenceReference) or (
            self.raw_evidence.source_id != self.source_id
        ):
            raise ValueError("causal raw evidence must match its source")


@dataclass(frozen=True, slots=True)
class ObservationFrontier:
    serialization_schema: ClassVar[int] = 2

    frontier_index: int
    sandbox_root: str
    objects: tuple[ObjectSnapshot, ...]
    protected_paths: tuple[str, ...]
    observation: MonotonicInterval
    delivered_at_start: tuple[int, ...]
    delivered_at_finish: tuple[int, ...]
    namespace_stable: bool

    def __post_init__(self) -> None:
        if type(self.frontier_index) is not int or self.frontier_index < 0:
            raise ValueError("frontier index must be a nonnegative integer")
        if not isinstance(self.sandbox_root, str) or not self.sandbox_root.startswith("/"):
            raise ValueError("frontier requires an absolute sandbox root")
        if not isinstance(self.objects, tuple) or not all(
            isinstance(obj, ObjectSnapshot) for obj in self.objects
        ):
            raise ValueError("frontier objects must be ObjectSnapshot records")
        paths = tuple(obj.path for obj in self.objects)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("frontier objects must have unique sorted paths")
        if not isinstance(self.protected_paths, tuple) or self.protected_paths != tuple(
            sorted(set(self.protected_paths))
        ):
            raise ValueError("frontier protected paths must be unique and sorted")
        for path in self.protected_paths:
            validate_observed_path(path)
        if not isinstance(self.observation, MonotonicInterval):
            raise ValueError("frontier requires a monotonic observation interval")
        for delivered in (self.delivered_at_start, self.delivered_at_finish):
            if (
                not isinstance(delivered, tuple)
                or delivered != tuple(sorted(set(delivered)))
                or any(type(sequence) is not int or sequence < 0 for sequence in delivered)
            ):
                raise ValueError("frontier delivered sequences must be unique and sorted")
        if not set(self.delivered_at_start) <= set(self.delivered_at_finish):
            raise ValueError("frontier finish must retain all start-delivered sequences")
        if type(self.namespace_stable) is not bool:
            raise ValueError("frontier stability must be explicit")


@dataclass(frozen=True, slots=True)
class ObservationFailure:
    kind: ObservationFailureKind
    message: str
    source_id: str
    sequence: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ObservationFailureKind):
            raise ValueError("observation failure requires a supported kind")
        if not all(isinstance(value, str) and value for value in (self.message, self.source_id)):
            raise ValueError("observation failure requires message and source")
        if self.sequence is not None and (type(self.sequence) is not int or self.sequence < 0):
            raise ValueError("observation failure sequence must be nonnegative or None")


@dataclass(frozen=True, slots=True)
class EffectTraceProvenance:
    serialization_schema: ClassVar[int] = 2

    protocol_id: str
    protocol_version: str
    configuration_id: str
    sources: tuple[EvidenceSourceIdentity, ...]
    event_bound: int
    required_lifecycle_kinds: tuple[EntryLifecycleKind, ...]
    raw_stream_sha256: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (self.protocol_id, self.protocol_version, self.configuration_id)
        ):
            raise ValueError("effect provenance requires protocol and configuration identity")
        if (
            not isinstance(self.sources, tuple)
            or not self.sources
            or not all(isinstance(source, EvidenceSourceIdentity) for source in self.sources)
        ):
            raise ValueError("effect provenance requires evidence sources")
        source_ids = tuple(source.source_id for source in self.sources)
        if source_ids != tuple(sorted(set(source_ids))):
            raise ValueError("effect evidence sources must have unique sorted IDs")
        if type(self.event_bound) is not int or self.event_bound <= 0:
            raise ValueError("effect event bound must be a positive integer")
        if (
            not isinstance(self.required_lifecycle_kinds, tuple)
            or not self.required_lifecycle_kinds
            or not all(
                isinstance(kind, EntryLifecycleKind) for kind in self.required_lifecycle_kinds
            )
            or self.required_lifecycle_kinds
            != tuple(kind for kind in EntryLifecycleKind if kind in self.required_lifecycle_kinds)
        ):
            raise ValueError("required lifecycle kinds must be unique and in schema order")
        validate_sha256(self.raw_stream_sha256)


@dataclass(frozen=True, slots=True)
class ObservedEventPoint:
    sequence: int
    kind: ObservedEventPointKind
    entry: ArchiveEntryReference


def _entry_matches(
    reference: ArchiveEntryReference, entries: tuple[ArchiveEntryReference, ...]
) -> bool:
    return reference.entry_index < len(entries) and entries[reference.entry_index] == reference


@dataclass(frozen=True, slots=True)
class EffectEventTrace:
    """Raw observed effect graph; source order and causality remain distinct."""

    serialization_schema: ClassVar[int] = 2

    before: StateSnapshot
    archive_entries: tuple[ArchiveEntryReference, ...]
    lifecycle_events: tuple[EntryLifecycleEvent, ...]
    effect_events: tuple[FilesystemEffectEvent, ...]
    causal_relations: tuple[CausalRelation, ...]
    frontiers: tuple[ObservationFrontier, ...]
    after: StateSnapshot
    completeness: EffectStreamCompleteness
    termination: EffectTargetTermination
    provenance: EffectTraceProvenance
    last_produced_sequence: int
    last_flushed_sequence: int | None
    flush_acknowledged_sequence: int | None
    observation_failures: tuple[ObservationFailure, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.before, StateSnapshot)
            or self.before.phase != SnapshotPhase.BEFORE
            or not isinstance(self.after, StateSnapshot)
            or self.after.phase != SnapshotPhase.AFTER
            or self.before.sandbox_root != self.after.sandbox_root
            or self.before.protected_paths != self.after.protected_paths
        ):
            raise ValueError("effect trace requires matching BEFORE and AFTER snapshots")
        if not isinstance(self.archive_entries, tuple) or tuple(
            entry.entry_index for entry in self.archive_entries
        ) != tuple(range(len(self.archive_entries))):
            raise ValueError("effect trace archive entries must preserve contiguous ordinal order")
        if not all(isinstance(entry, ArchiveEntryReference) for entry in self.archive_entries):
            raise ValueError("effect trace archive entries must be typed references")
        if not isinstance(self.lifecycle_events, tuple) or not all(
            isinstance(event, EntryLifecycleEvent) for event in self.lifecycle_events
        ):
            raise ValueError("effect trace lifecycle events must be typed records")
        if tuple(event.sequence for event in self.lifecycle_events) != tuple(
            sorted(event.sequence for event in self.lifecycle_events)
        ):
            raise ValueError("lifecycle events must retain observed sequence order")
        if not isinstance(self.effect_events, tuple) or not all(
            isinstance(event, FilesystemEffectEvent) for event in self.effect_events
        ):
            raise ValueError("effect trace filesystem events must be typed records")
        if tuple(event.start_sequence for event in self.effect_events) != tuple(
            sorted(event.start_sequence for event in self.effect_events)
        ):
            raise ValueError("filesystem events must retain observed start order")
        if not all(
            _entry_matches(event.entry, self.archive_entries)
            for event in (*self.lifecycle_events, *self.effect_events)
        ):
            raise ValueError("effect trace event entry identity differs from archive entries")
        if not isinstance(self.causal_relations, tuple) or not all(
            isinstance(edge, CausalRelation) for edge in self.causal_relations
        ):
            raise ValueError("effect trace causal relations must be typed records")
        if not isinstance(self.frontiers, tuple) or not all(
            isinstance(frontier, ObservationFrontier) for frontier in self.frontiers
        ):
            raise ValueError("effect trace frontiers must be typed records")
        if tuple(frontier.frontier_index for frontier in self.frontiers) != tuple(
            range(len(self.frontiers))
        ):
            raise ValueError("effect trace frontier indexes must be contiguous")
        if any(
            frontier.sandbox_root != self.before.sandbox_root
            or frontier.protected_paths != self.before.protected_paths
            for frontier in self.frontiers
        ):
            raise ValueError("effect trace frontiers must belong to the snapshot run")
        if not isinstance(self.completeness, EffectStreamCompleteness) or not isinstance(
            self.termination, EffectTargetTermination
        ):
            raise ValueError("effect trace completeness and termination must be explicit")
        if not isinstance(self.provenance, EffectTraceProvenance):
            raise ValueError("effect trace requires provenance")
        if type(self.last_produced_sequence) is not int or self.last_produced_sequence < -1:
            raise ValueError("last produced sequence must be an integer at least -1")
        for value in (self.last_flushed_sequence, self.flush_acknowledged_sequence):
            if value is not None and (type(value) is not int or value < -1):
                raise ValueError("flush sequences must be integers at least -1 or None")
        if not isinstance(self.observation_failures, tuple) or not all(
            isinstance(failure, ObservationFailure) for failure in self.observation_failures
        ):
            raise ValueError("effect trace failures must be typed records")

        source_ids = {source.source_id for source in self.provenance.sources}
        raw_sources = (
            {event.source_id for event in (*self.lifecycle_events, *self.effect_events)}
            | {edge.source_id for edge in self.causal_relations}
            | {failure.source_id for failure in self.observation_failures}
        )
        if not raw_sources <= source_ids:
            raise ValueError("effect trace records reference undeclared evidence sources")

        points = self.observed_event_points()
        sequences = tuple(point.sequence for point in points)
        if any(sequence >= self.provenance.event_bound for sequence in sequences):
            raise ValueError("effect event sequence exceeds the declared bound")
        unique_sequences = len(set(sequences)) == len(sequences)
        contiguous = unique_sequences and tuple(sorted(sequences)) == tuple(
            range(self.last_produced_sequence + 1)
        )
        flush_matches = (
            self.last_flushed_sequence == self.last_produced_sequence
            and self.flush_acknowledged_sequence == self.last_produced_sequence
        )
        flush_failure = any(
            failure.kind == ObservationFailureKind.INCOMPLETE_FLUSH
            for failure in self.observation_failures
        )
        if not flush_matches and not flush_failure:
            raise ValueError("incomplete or mismatched flush requires explicit failure evidence")
        if self.completeness == EffectStreamCompleteness.COMPLETE:
            if self.observation_failures:
                raise ValueError("complete effect stream cannot contain observation failures")
            if not contiguous:
                raise ValueError("complete effect stream sequences must be unique and contiguous")
            if not flush_matches:
                raise ValueError("complete effect stream requires verified flush")
        elif not self.observation_failures and self.termination not in (
            EffectTargetTermination.TIMED_OUT,
            EffectTargetTermination.NOT_STARTED,
        ):
            raise ValueError("non-complete effect stream requires explicit failure evidence")

        if self.completeness == EffectStreamCompleteness.COMPLETE and (
            self.termination == EffectTargetTermination.SUCCESS
        ):
            observed = [(event.entry.entry_index, event.kind) for event in self.lifecycle_events]
            expected = [
                (entry.entry_index, kind)
                for entry in self.archive_entries
                for kind in self.provenance.required_lifecycle_kinds
            ]
            if (
                sorted(
                    observed, key=lambda item: (item[0], list(EntryLifecycleKind).index(item[1]))
                )
                != expected
            ):
                raise ValueError("complete successful trace lacks declared lifecycle coverage")

        if unique_sequences:
            self._validate_causal_relations({point.sequence: point for point in points})

    @property
    def integrity_valid(self) -> bool:
        return (
            self.completeness == EffectStreamCompleteness.COMPLETE
            and not self.observation_failures
            and self.last_flushed_sequence == self.last_produced_sequence
            and self.flush_acknowledged_sequence == self.last_produced_sequence
        )

    def observed_event_points(self) -> tuple[ObservedEventPoint, ...]:
        points = [
            ObservedEventPoint(event.sequence, ObservedEventPointKind.LIFECYCLE, event.entry)
            for event in self.lifecycle_events
        ]
        for event in self.effect_events:
            points.extend(
                (
                    ObservedEventPoint(
                        event.start_sequence, ObservedEventPointKind.OPERATION_START, event.entry
                    ),
                    ObservedEventPoint(
                        event.completion_sequence,
                        ObservedEventPointKind.OPERATION_COMPLETION,
                        event.entry,
                    ),
                )
            )
        return tuple(sorted(points, key=lambda point: point.sequence))

    def _validate_causal_relations(self, points: dict[int, ObservedEventPoint]) -> None:
        lifecycle_by_sequence = {event.sequence: event for event in self.lifecycle_events}
        effect_by_interval = {
            (event.start_sequence, event.completion_sequence): event for event in self.effect_events
        }
        effect_starts = {event.start_sequence: event for event in self.effect_events}
        effect_completions = {event.completion_sequence: event for event in self.effect_events}
        for edge in self.causal_relations:
            if edge.predecessor_sequence not in points or edge.successor_sequence not in points:
                raise ValueError("causal relation references an unknown observed sequence")
            if edge.kind == CausalRelationKind.OPERATION_INTERVAL:
                effect = effect_by_interval.get(
                    (edge.predecessor_sequence, edge.successor_sequence)
                )
                if effect is None or edge.evidence_token != effect.correlation_id:
                    raise ValueError("operation interval edge must match one correlated operation")
            elif edge.kind == CausalRelationKind.ENTRY_CONTEXT_PROPAGATION:
                lifecycle = lifecycle_by_sequence.get(edge.predecessor_sequence)
                effect = effect_starts.get(edge.successor_sequence)
                if (
                    lifecycle is None
                    or lifecycle.kind != EntryLifecycleKind.EFFECT_WORK_STARTED
                    or effect is None
                    or lifecycle.entry != effect.entry
                ):
                    raise ValueError("entry context edge must connect matching work and operation")
            elif edge.kind in (
                CausalRelationKind.HANDLE_PROVENANCE,
                CausalRelationKind.IDENTITY_PROVENANCE,
            ):
                if edge.predecessor_sequence not in effect_completions or (
                    edge.successor_sequence not in effect_starts
                ):
                    raise ValueError("provenance edge must connect completion to operation start")
            elif edge.kind == CausalRelationKind.EXPLICIT_OPERATION_DEPENDENCY:
                if edge.predecessor_sequence not in effect_completions or (
                    edge.successor_sequence not in effect_starts
                ):
                    raise ValueError(
                        "operation dependency must connect completion to operation start"
                    )
        adjacency: dict[int, set[int]] = {sequence: set() for sequence in points}
        for edge in self.causal_relations:
            adjacency[edge.predecessor_sequence].add(edge.successor_sequence)
        visiting: set[int] = set()
        visited: set[int] = set()

        def visit(sequence: int) -> None:
            if sequence in visiting:
                raise ValueError("causal relation graph must be acyclic")
            if sequence in visited:
                return
            visiting.add(sequence)
            for successor in adjacency[sequence]:
                visit(successor)
            visiting.remove(sequence)
            visited.add(sequence)

        for sequence in adjacency:
            visit(sequence)

    def causally_precedes(self, predecessor_sequence: int, successor_sequence: int) -> bool:
        if type(predecessor_sequence) is not int or type(successor_sequence) is not int:
            raise ValueError("causal query requires integer sequences")
        adjacency: dict[int, set[int]] = {}
        for edge in self.causal_relations:
            adjacency.setdefault(edge.predecessor_sequence, set()).add(edge.successor_sequence)
        pending = list(adjacency.get(predecessor_sequence, ()))
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if current == successor_sequence:
                return True
            if current not in seen:
                seen.add(current)
                pending.extend(adjacency.get(current, ()))
        return False

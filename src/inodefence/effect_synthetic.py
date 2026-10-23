"""Synthetic fixture producer — native 증거 아님.

These helpers build EffectRunResult records without executing any extractor.
Every trace carries provenance source "synthetic"; results from this module
must never be reported as node-tar (native) observations.
"""

from hashlib import sha256

from inodefence.feedback import state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntryReference,
    AssociationKind,
    CausalRelation,
    CausalRelationKind,
    EffectClass,
    EffectEventTrace,
    EffectEvidenceStrength,
    EffectObjectObservation,
    EffectObservationStatus,
    EffectPathEvidence,
    EffectRunResult,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EffectTraceProvenance,
    EntryLifecycleEvent,
    EntryLifecycleKind,
    EntryType,
    EvidenceSourceIdentity,
    ExecutionResult,
    ExecutionStatus,
    FilesystemEffectEvent,
    LifecycleStatus,
    MonotonicInterval,
    ObjectSnapshot,
    ObjectType,
    ObservedOperationType,
    OperationOutcome,
    RawEvidenceReference,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
)
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _object(
    path: str,
    *,
    kind: ObjectType = ObjectType.REGULAR,
    dev: int = 1,
    ino: int = 1,
    content: bytes = b"x",
) -> ObjectSnapshot:
    return ObjectSnapshot(
        path,
        kind,
        dev,
        ino,
        1,
        0o777 if kind == ObjectType.SYMLINK else 0o644,
        len(content),
        1000,
        1000,
        1,
        1,
        "target" if kind == ObjectType.SYMLINK else None,
        _digest(content) if kind == ObjectType.REGULAR else None,
    )


def _observation(obj: ObjectSnapshot | None) -> EffectObjectObservation:
    return EffectObjectObservation(
        EffectObservationStatus.ABSENT if obj is None else EffectObservationStatus.PRESENT,
        obj,
    )


def _raw(record: str, source: str = "synthetic") -> RawEvidenceReference:
    return RawEvidenceReference(source, record)


def _source(source: str = "synthetic") -> EvidenceSourceIdentity:
    return EvidenceSourceIdentity(source, "synthetic-test", "1", _digest(source.encode()))


def _snapshots() -> tuple[StateSnapshot, StateSnapshot]:
    root = "/var/lib/inodefence/effect-feedback"
    sentinel = _object("outside/sentinel", dev=9, ino=9, content=b"sentinel")
    return (
        StateSnapshot(root, SnapshotPhase.BEFORE, (sentinel,), ("outside/sentinel",)),
        StateSnapshot(root, SnapshotPhase.AFTER, (sentinel,), ("outside/sentinel",)),
    )


def _provenance(source: str = "synthetic") -> EffectTraceProvenance:
    return EffectTraceProvenance(
        "entry-effect-trace-v2",
        "1",
        "synthetic-feedback",
        (_source(source),),
        1024,
        (EntryLifecycleKind.READ, EntryLifecycleKind.EFFECT_WORK_STARTED),
        _digest(f"stream-{source}".encode()),
    )


def _lifecycle(
    sequence: int,
    entry: ArchiveEntryReference,
    kind: EntryLifecycleKind,
    source: str = "synthetic",
) -> EntryLifecycleEvent:
    return EntryLifecycleEvent(
        sequence,
        entry,
        kind,
        MonotonicInterval(sequence * 10, sequence * 10 + 1),
        LifecycleStatus.SUCCEEDED,
        None,
        source,
        _raw(f"lifecycle-{sequence}", source),
    )


def _creation_effect(
    start: int,
    completion: int,
    entry: ArchiveEntryReference,
    path: str,
    *,
    ino: int,
    source: str = "synthetic",
) -> FilesystemEffectEvent:
    return FilesystemEffectEvent(
        start,
        completion,
        entry,
        AssociationKind.ASYNC_CONTEXT,
        EffectClass.NAMESPACE_CREATION,
        EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
        (path,),
        ObservedOperationType.OPEN,
        MonotonicInterval(start * 10, start * 10 + 1),
        MonotonicInterval(completion * 10, completion * 10 + 1),
        OperationOutcome.SUCCEEDED,
        (EffectPathEvidence(path, _observation(None), _observation(_object(path, ino=ino))),),
        source,
        f"operation-{start}",
        _raw(f"effect-{completion}", source),
    )


def _edge(
    before: int,
    after: int,
    kind: CausalRelationKind,
    token: str,
    *,
    source: str = "synthetic",
) -> CausalRelation:
    return CausalRelation(
        before, after, kind, source, token, _raw(f"edge-{before}-{after}", source)
    )


def _trace_for_case(
    case: ArchiveCase,
    *,
    source: str = "synthetic",
    explicit_dependency: bool = False,
) -> EffectEventTrace:
    references = tuple(
        ArchiveEntryReference(index, entry.path, entry.entry_type, entry.link_target)
        for index, entry in enumerate(case.entries)
    )
    lifecycle = []
    effects = []
    edges = []
    sequence = 0
    for reference in references:
        read = sequence
        work = sequence + 1
        start = sequence + 2
        completion = sequence + 3
        lifecycle.extend(
            (
                _lifecycle(read, reference, EntryLifecycleKind.READ, source),
                _lifecycle(work, reference, EntryLifecycleKind.EFFECT_WORK_STARTED, source),
            )
        )
        path = f"extract/object-{reference.entry_index}"
        entry = case.entries[reference.entry_index]
        if entry.entry_type == EntryType.HARDLINK:
            source_path = f"extract/source-{reference.entry_index}"
            source_object = _object(source_path, dev=7, ino=100 + reference.entry_index)
            target_object = _object(path, dev=7, ino=100 + reference.entry_index)
            effect = FilesystemEffectEvent(
                start,
                completion,
                reference,
                AssociationKind.ASYNC_CONTEXT,
                EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
                EffectEvidenceStrength.IDENTITY_VERIFIED,
                (source_path, path),
                ObservedOperationType.LINK,
                MonotonicInterval(start * 10, start * 10 + 1),
                MonotonicInterval(completion * 10, completion * 10 + 1),
                OperationOutcome.SUCCEEDED,
                (
                    EffectPathEvidence(
                        source_path, _observation(source_object), _observation(source_object)
                    ),
                    EffectPathEvidence(path, _observation(None), _observation(target_object)),
                ),
                source,
                f"operation-{start}",
                _raw(f"effect-{completion}", source),
            )
        elif entry.entry_type == EntryType.SYMLINK:
            effect = FilesystemEffectEvent(
                start,
                completion,
                reference,
                AssociationKind.ASYNC_CONTEXT,
                EffectClass.SYMLINK_CREATION,
                EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
                (path,),
                ObservedOperationType.SYMLINK,
                MonotonicInterval(start * 10, start * 10 + 1),
                MonotonicInterval(completion * 10, completion * 10 + 1),
                OperationOutcome.SUCCEEDED,
                (
                    EffectPathEvidence(
                        path,
                        _observation(None),
                        _observation(
                            _object(path, kind=ObjectType.SYMLINK, ino=100 + reference.entry_index)
                        ),
                    ),
                ),
                source,
                f"operation-{start}",
                _raw(f"effect-{completion}", source),
            )
        else:
            effect = _creation_effect(
                start,
                completion,
                reference,
                path,
                ino=100 + reference.entry_index,
                source=source,
            )
        effects.append(effect)
        edges.extend(
            (
                _edge(
                    work,
                    start,
                    CausalRelationKind.ENTRY_CONTEXT_PROPAGATION,
                    "context",
                    source=source,
                ),
                _edge(
                    start,
                    completion,
                    CausalRelationKind.OPERATION_INTERVAL,
                    effect.correlation_id,
                    source=source,
                ),
            )
        )
        if explicit_dependency and reference.entry_index > 0:
            previous = effects[-2]
            edges.append(
                _edge(
                    previous.completion_sequence,
                    start,
                    CausalRelationKind.EXPLICIT_OPERATION_DEPENDENCY,
                    "qualified-dependency",
                    source=source,
                )
            )
        sequence += 4
    before, after = _snapshots()
    last = sequence - 1
    return EffectEventTrace(
        before,
        references,
        tuple(lifecycle),
        tuple(effects),
        tuple(edges),
        (),
        after,
        EffectStreamCompleteness.COMPLETE,
        EffectTargetTermination.SUCCESS,
        _provenance(source),
        last,
        last,
        last,
        (),
    )


def _result(case: ArchiveCase, *, source: str = "synthetic") -> EffectRunResult:
    trace = _trace_for_case(case, source=source)
    changes = compare_states(trace.before, trace.after)
    base = RunResult(
        case,
        _digest(case.case_id.encode()),
        "ustar",
        ExecutionResult("synthetic", "1", ("synthetic",), ExecutionStatus.SUCCESS, 0, "", "", 0.01),
        trace.before,
        trace.after,
        changes,
        state_signature(trace.before, trace.after),
        evaluate_contracts(trace.before, trace.after),
    )
    return EffectRunResult(base, trace)


def synthetic_effect_result(case: ArchiveCase) -> EffectRunResult:
    """Public EffectResultProducer for demos; output is synthetic, never native evidence."""
    return _result(case)

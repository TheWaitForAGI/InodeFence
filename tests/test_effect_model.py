from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.feedback import state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
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
    ObservationFailure,
    ObservationFailureKind,
    ObservedOperationType,
    OperationOutcome,
    RawEvidenceReference,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
    canonical_json,
    effect_is_realized,
)
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts


def _digest(value: bytes = b"x") -> str:
    return sha256(value).hexdigest()


def _object(
    path: str,
    *,
    kind: ObjectType = ObjectType.REGULAR,
    dev: int = 1,
    ino: int = 1,
    size: int = 1,
    content: bytes = b"x",
) -> ObjectSnapshot:
    return ObjectSnapshot(
        path,
        kind,
        dev,
        ino,
        1,
        0o777 if kind == ObjectType.SYMLINK else 0o644,
        size,
        1000,
        1000,
        1,
        1,
        "target" if kind == ObjectType.SYMLINK else None,
        _digest(content) if kind == ObjectType.REGULAR else None,
    )


def _observation(obj: ObjectSnapshot | None) -> EffectObjectObservation:
    if obj is None:
        return EffectObjectObservation(EffectObservationStatus.ABSENT, None)
    return EffectObjectObservation(EffectObservationStatus.PRESENT, obj)


def _source() -> EvidenceSourceIdentity:
    return EvidenceSourceIdentity("synthetic", "synthetic-test", "1", _digest(b"source"))


def _provenance(*, event_bound: int = 32) -> EffectTraceProvenance:
    return EffectTraceProvenance(
        "entry-effect-trace-v2",
        "1",
        "synthetic-config",
        (_source(),),
        event_bound,
        (EntryLifecycleKind.READ, EntryLifecycleKind.EFFECT_WORK_STARTED),
        _digest(b"stream"),
    )


def _lifecycle(
    sequence: int,
    entry: ArchiveEntryReference,
    kind: EntryLifecycleKind,
) -> EntryLifecycleEvent:
    return EntryLifecycleEvent(
        sequence,
        entry,
        kind,
        MonotonicInterval(sequence * 10, sequence * 10 + 1),
        LifecycleStatus.SUCCEEDED,
        None,
        "synthetic",
        RawEvidenceReference("synthetic", f"lifecycle-{sequence}"),
    )


def _effect(
    start_sequence: int,
    completion_sequence: int,
    entry: ArchiveEntryReference,
    *,
    effect_class: EffectClass = EffectClass.NAMESPACE_CREATION,
    paths: tuple[str, ...] = ("extract/a",),
    evidence: tuple[EffectPathEvidence, ...] = (),
    strength: EffectEvidenceStrength = EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
    operation: ObservedOperationType = ObservedOperationType.OPEN,
) -> FilesystemEffectEvent:
    return FilesystemEffectEvent(
        start_sequence,
        completion_sequence,
        entry,
        AssociationKind.ASYNC_CONTEXT,
        effect_class,
        strength,
        paths,
        operation,
        MonotonicInterval(start_sequence * 10, start_sequence * 10 + 1),
        MonotonicInterval(completion_sequence * 10, completion_sequence * 10 + 1),
        OperationOutcome.SUCCEEDED,
        evidence,
        "synthetic",
        f"operation-{start_sequence}",
        RawEvidenceReference("synthetic", f"operation-{completion_sequence}"),
    )


def _snapshots() -> tuple[StateSnapshot, StateSnapshot]:
    root = "/var/lib/inodefence/effect-model"
    sentinel = _object("outside/sentinel", dev=9, ino=9)
    before = StateSnapshot(root, SnapshotPhase.BEFORE, (sentinel,), ("outside/sentinel",))
    after = StateSnapshot(root, SnapshotPhase.AFTER, (sentinel,), ("outside/sentinel",))
    return before, after


def _complete_trace(
    entries: tuple[ArchiveEntryReference, ...],
    lifecycle: tuple[EntryLifecycleEvent, ...],
    effects: tuple[FilesystemEffectEvent, ...],
    causal: tuple[CausalRelation, ...],
) -> EffectEventTrace:
    before, after = _snapshots()
    last = max(
        [event.sequence for event in lifecycle]
        + [
            point
            for event in effects
            for point in (event.start_sequence, event.completion_sequence)
        ]
    )
    return EffectEventTrace(
        before,
        entries,
        lifecycle,
        effects,
        causal,
        (),
        after,
        EffectStreamCompleteness.COMPLETE,
        EffectTargetTermination.SUCCESS,
        _provenance(),
        last,
        last,
        last,
        (),
    )


def test_operation_success_is_not_a_verified_state_effect() -> None:
    entry = ArchiveEntryReference(0, "a", EntryType.REGULAR, None)
    operation_only = _effect(
        2,
        3,
        entry,
        strength=EffectEvidenceStrength.OPERATION_RESULT,
    )
    created = _effect(
        2,
        3,
        entry,
        evidence=(
            EffectPathEvidence(
                "extract/a",
                _observation(None),
                _observation(_object("extract/a")),
            ),
        ),
    )

    assert not effect_is_realized(operation_only)
    assert effect_is_realized(created)


def test_hardlink_effect_requires_actual_before_after_identity_relation() -> None:
    entry = ArchiveEntryReference(0, "b", EntryType.HARDLINK, "a")
    before_source = _object("extract/a", dev=7, ino=11)
    after_source = _object("extract/a", dev=7, ino=11)
    after_target = _object("extract/b", dev=7, ino=11)
    relation = _effect(
        0,
        1,
        entry,
        effect_class=EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
        paths=("extract/a", "extract/b"),
        operation=ObservedOperationType.LINK,
        strength=EffectEvidenceStrength.IDENTITY_VERIFIED,
        evidence=(
            EffectPathEvidence(
                "extract/a", _observation(before_source), _observation(after_source)
            ),
            EffectPathEvidence("extract/b", _observation(None), _observation(after_target)),
        ),
    )

    assert effect_is_realized(relation)
    mismatched = replace(
        relation,
        object_evidence=(
            relation.object_evidence[0],
            EffectPathEvidence(
                "extract/b",
                _observation(None),
                _observation(_object("extract/b", dev=7, ino=12)),
            ),
        ),
    )
    assert not effect_is_realized(mismatched)


def test_trace_preserves_observed_order_without_inventing_archive_causality() -> None:
    first = ArchiveEntryReference(0, "large", EntryType.REGULAR, None)
    later = ArchiveEntryReference(1, "small", EntryType.REGULAR, None)
    lifecycle = (
        _lifecycle(0, first, EntryLifecycleKind.READ),
        _lifecycle(1, first, EntryLifecycleKind.EFFECT_WORK_STARTED),
        _lifecycle(2, later, EntryLifecycleKind.READ),
        _lifecycle(3, later, EntryLifecycleKind.EFFECT_WORK_STARTED),
    )
    later_effect = _effect(
        4,
        5,
        later,
        paths=("extract/small",),
        evidence=(
            EffectPathEvidence(
                "extract/small",
                _observation(None),
                _observation(_object("extract/small", ino=2)),
            ),
        ),
    )
    first_effect = _effect(
        6,
        7,
        first,
        paths=("extract/large",),
        evidence=(
            EffectPathEvidence(
                "extract/large",
                _observation(None),
                _observation(_object("extract/large", ino=1)),
            ),
        ),
    )
    causal = (
        CausalRelation(
            1,
            6,
            CausalRelationKind.ENTRY_CONTEXT_PROPAGATION,
            "synthetic",
            "entry-0-context",
            RawEvidenceReference("synthetic", "edge-0"),
        ),
        CausalRelation(
            3,
            4,
            CausalRelationKind.ENTRY_CONTEXT_PROPAGATION,
            "synthetic",
            "entry-1-context",
            RawEvidenceReference("synthetic", "edge-1"),
        ),
        CausalRelation(
            4,
            5,
            CausalRelationKind.OPERATION_INTERVAL,
            "synthetic",
            later_effect.correlation_id,
            RawEvidenceReference("synthetic", "edge-2"),
        ),
        CausalRelation(
            6,
            7,
            CausalRelationKind.OPERATION_INTERVAL,
            "synthetic",
            first_effect.correlation_id,
            RawEvidenceReference("synthetic", "edge-3"),
        ),
    )

    trace = _complete_trace((first, later), lifecycle, (later_effect, first_effect), causal)

    assert trace.archive_entries == (first, later)
    assert tuple(point.sequence for point in trace.observed_event_points()) == tuple(range(8))
    assert not trace.causally_precedes(
        later_effect.completion_sequence, first_effect.start_sequence
    )
    assert not trace.causally_precedes(
        first_effect.completion_sequence, later_effect.start_sequence
    )


def test_trace_rejects_unsupported_or_cyclic_causal_edges() -> None:
    entry = ArchiveEntryReference(0, "a", EntryType.REGULAR, None)
    lifecycle = (
        _lifecycle(0, entry, EntryLifecycleKind.READ),
        _lifecycle(1, entry, EntryLifecycleKind.EFFECT_WORK_STARTED),
    )
    effect = _effect(
        2,
        3,
        entry,
        evidence=(
            EffectPathEvidence("extract/a", _observation(None), _observation(_object("extract/a"))),
        ),
    )
    valid = (
        CausalRelation(
            1,
            2,
            CausalRelationKind.ENTRY_CONTEXT_PROPAGATION,
            "synthetic",
            "context",
            RawEvidenceReference("synthetic", "edge-context"),
        ),
        CausalRelation(
            2,
            3,
            CausalRelationKind.OPERATION_INTERVAL,
            "synthetic",
            effect.correlation_id,
            RawEvidenceReference("synthetic", "edge-operation"),
        ),
    )
    trace = _complete_trace((entry,), lifecycle, (effect,), valid)

    with pytest.raises(ValueError, match="operation interval"):
        replace(
            trace,
            causal_relations=(
                CausalRelation(
                    1,
                    3,
                    CausalRelationKind.OPERATION_INTERVAL,
                    "synthetic",
                    "wrong",
                    RawEvidenceReference("synthetic", "bad-edge"),
                ),
            ),
        )
    second_effect = _effect(
        4,
        5,
        entry,
        paths=("extract/b",),
        evidence=(
            EffectPathEvidence(
                "extract/b", _observation(None), _observation(_object("extract/b", ino=2))
            ),
        ),
    )
    cycle = valid + (
        CausalRelation(
            4,
            5,
            CausalRelationKind.OPERATION_INTERVAL,
            "synthetic",
            second_effect.correlation_id,
            RawEvidenceReference("synthetic", "edge-operation-2"),
        ),
        CausalRelation(
            3,
            4,
            CausalRelationKind.EXPLICIT_OPERATION_DEPENDENCY,
            "synthetic",
            "forward-dependency",
            RawEvidenceReference("synthetic", "forward-edge"),
        ),
        CausalRelation(
            5,
            2,
            CausalRelationKind.EXPLICIT_OPERATION_DEPENDENCY,
            "synthetic",
            "back-dependency",
            RawEvidenceReference("synthetic", "back-edge"),
        ),
    )
    before, after = _snapshots()
    with pytest.raises(ValueError, match="acyclic"):
        EffectEventTrace(
            before,
            (entry,),
            lifecycle,
            (effect, second_effect),
            cycle,
            (),
            after,
            EffectStreamCompleteness.COMPLETE,
            EffectTargetTermination.SUCCESS,
            _provenance(),
            5,
            5,
            5,
            (),
        )


def test_invalid_stream_is_preserved_but_complete_stream_fails_closed() -> None:
    entry = ArchiveEntryReference(0, "a", EntryType.REGULAR, None)
    lifecycle = (_lifecycle(0, entry, EntryLifecycleKind.READ),)
    effect = _effect(2, 3, entry, strength=EffectEvidenceStrength.OPERATION_RESULT)
    before, after = _snapshots()
    failure = ObservationFailure(
        ObservationFailureKind.EVENT_LOSS,
        "source sequence 1 is missing",
        "synthetic",
        1,
    )
    invalid = EffectEventTrace(
        before,
        (entry,),
        lifecycle,
        (effect,),
        (),
        (),
        after,
        EffectStreamCompleteness.INVALID,
        EffectTargetTermination.SUCCESS,
        _provenance(),
        3,
        3,
        3,
        (failure,),
    )

    assert not invalid.integrity_valid
    with pytest.raises(ValueError, match="contiguous"):
        replace(
            invalid,
            completeness=EffectStreamCompleteness.COMPLETE,
            observation_failures=(),
        )
    with pytest.raises(ValueError, match="flush"):
        replace(invalid, last_flushed_sequence=2)


def test_effect_run_result_composes_without_changing_run_result_schema() -> None:
    case = ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, b"x"),))
    entry = ArchiveEntryReference(0, "a", EntryType.REGULAR, None)
    lifecycle = (
        _lifecycle(0, entry, EntryLifecycleKind.READ),
        _lifecycle(1, entry, EntryLifecycleKind.EFFECT_WORK_STARTED),
    )
    effect = _effect(
        2,
        3,
        entry,
        evidence=(
            EffectPathEvidence("extract/a", _observation(None), _observation(_object("extract/a"))),
        ),
    )
    causal = (
        CausalRelation(
            1,
            2,
            CausalRelationKind.ENTRY_CONTEXT_PROPAGATION,
            "synthetic",
            "context",
            RawEvidenceReference("synthetic", "edge-context"),
        ),
        CausalRelation(
            2,
            3,
            CausalRelationKind.OPERATION_INTERVAL,
            "synthetic",
            effect.correlation_id,
            RawEvidenceReference("synthetic", "edge-operation"),
        ),
    )
    trace = _complete_trace((entry,), lifecycle, (effect,), causal)
    changes = compare_states(trace.before, trace.after)
    result = RunResult(
        case,
        _digest(b"tar"),
        "ustar",
        ExecutionResult("synthetic", "1", ("synthetic",), ExecutionStatus.SUCCESS, 0, "", "", 0.1),
        trace.before,
        trace.after,
        changes,
        state_signature(trace.before, trace.after),
        evaluate_contracts(trace.before, trace.after),
    )

    composed = EffectRunResult(result, trace)

    assert composed.base_result is result
    assert '"EffectRunResult"' in canonical_json(composed)
    with pytest.raises(ValueError, match="entry identity"):
        EffectRunResult(
            replace(result, case=ArchiveCase((ArchiveEntry("other", EntryType.REGULAR, b"x"),))),
            trace,
        )

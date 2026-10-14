import random
from dataclasses import replace
from hashlib import sha256

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_scheduler import EffectAdaptiveMutationScheduler
from inodefence.feedback import (
    EffectFeedbackKeyKind,
    EffectSearchPolicy,
    EffectSearchState,
    effect_feedback_keys,
    state_signature,
)
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
)
from inodefence.mutation_scheduler import MutationSelection
from inodefence.mutator import MutationOperatorId, MutationPolicy, apply_operator
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


def _overlap_trace(
    *,
    completion_order: tuple[int, int],
    source: str,
    paths: tuple[str, str] = ("extract/first", "extract/second"),
    inodes: tuple[int, int] = (11, 12),
) -> EffectEventTrace:
    first = ArchiveEntryReference(0, "a", EntryType.REGULAR, None)
    second = ArchiveEntryReference(1, "b", EntryType.REGULAR, None)
    lifecycle = (
        _lifecycle(0, first, EntryLifecycleKind.READ, source),
        _lifecycle(1, first, EntryLifecycleKind.EFFECT_WORK_STARTED, source),
        _lifecycle(3, second, EntryLifecycleKind.READ, source),
        _lifecycle(4, second, EntryLifecycleKind.EFFECT_WORK_STARTED, source),
    )
    completion_by_entry = {completion_order[0]: 6, completion_order[1]: 7}
    first_effect = _creation_effect(
        2, completion_by_entry[0], first, paths[0], ino=inodes[0], source=source
    )
    second_effect = _creation_effect(
        5, completion_by_entry[1], second, paths[1], ino=inodes[1], source=source
    )
    edges = (
        _edge(1, 2, CausalRelationKind.ENTRY_CONTEXT_PROPAGATION, "context-0", source=source),
        _edge(4, 5, CausalRelationKind.ENTRY_CONTEXT_PROPAGATION, "context-1", source=source),
        _edge(
            2,
            first_effect.completion_sequence,
            CausalRelationKind.OPERATION_INTERVAL,
            first_effect.correlation_id,
            source=source,
        ),
        _edge(
            5,
            second_effect.completion_sequence,
            CausalRelationKind.OPERATION_INTERVAL,
            second_effect.correlation_id,
            source=source,
        ),
    )
    before, after = _snapshots()
    return EffectEventTrace(
        before,
        (first, second),
        lifecycle,
        (first_effect, second_effect),
        edges,
        (),
        after,
        EffectStreamCompleteness.COMPLETE,
        EffectTargetTermination.SUCCESS,
        _provenance(source),
        7,
        7,
        7,
        (),
    )


def test_feedback_keys_ignore_completion_permutation_raw_paths_and_identity() -> None:
    first = _overlap_trace(completion_order=(0, 1), source="first-source")
    second = _overlap_trace(
        completion_order=(1, 0),
        source="second-source",
        paths=("extract/renamed-a", "extract/renamed-b"),
        inodes=(901, 902),
    )

    first_keys = effect_feedback_keys(first)
    second_keys = effect_feedback_keys(second)

    assert first_keys == second_keys
    assert {key.kind for key in first_keys} == {
        EffectFeedbackKeyKind.INDIVIDUAL_EFFECT,
        EffectFeedbackKeyKind.ENTRY_EFFECT_SET,
    }
    encoded = canonical_json(first_keys[0])
    for excluded in ("extract/first", "st_dev", "st_ino", "sequence", "source_id"):
        assert excluded not in encoded


def test_only_supported_cross_effect_edge_creates_causal_motif() -> None:
    case = ArchiveCase(
        (
            ArchiveEntry("a", EntryType.REGULAR, b"a"),
            ArchiveEntry("b", EntryType.REGULAR, b"b"),
        )
    )
    independent = _trace_for_case(case)
    dependent = _trace_for_case(case, explicit_dependency=True)

    independent_motifs = tuple(
        key
        for key in effect_feedback_keys(independent)
        if key.kind == EffectFeedbackKeyKind.CAUSAL_MOTIF
    )
    dependent_motifs = tuple(
        key
        for key in effect_feedback_keys(dependent)
        if key.kind == EffectFeedbackKeyKind.CAUSAL_MOTIF
    )

    assert independent_motifs == ()
    assert len(dependent_motifs) == 1


def test_invalid_trace_neither_consumes_novelty_nor_enters_corpus() -> None:
    case = ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, b"a"),))
    valid = _result(case)
    invalid_trace = replace(
        valid.trace,
        completeness=EffectStreamCompleteness.INVALID,
        observation_failures=(
            ObservationFailure(
                ObservationFailureKind.EVENT_LOSS,
                "injected loss",
                "synthetic",
                2,
            ),
        ),
    )
    invalid = EffectRunResult(valid.base_result, invalid_trace)
    state = EffectSearchState((case,), EffectSearchPolicy.P1_EFFECT_RETENTION)

    rejected = state.consider(invalid)
    accepted = state.consider(valid)

    assert rejected.observation_failure and not rejected.admission_eligible
    assert rejected.new_effect_keys == ()
    assert accepted.effect_novel and accepted.retained
    assert state.stats.unique_effect_keys == len(effect_feedback_keys(valid.trace))


def test_p0_and_p1_isolate_final_state_from_effect_retention() -> None:
    first = ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, b"a"),))
    second = ArchiveCase((ArchiveEntry("b", EntryType.HARDLINK, link_target="a"),))
    p0 = EffectSearchState((first, second), EffectSearchPolicy.P0_FINAL_STATE)
    p1 = EffectSearchState((first, second), EffectSearchPolicy.P1_EFFECT_RETENTION)
    p2 = EffectSearchState((first, second), EffectSearchPolicy.P2_EFFECT_ADAPTIVE)

    p0_decisions = (p0.consider(_result(first)), p0.consider(_result(second)))
    p1_decisions = (p1.consider(_result(first)), p1.consider(_result(second)))
    p2_decisions = (p2.consider(_result(first)), p2.consider(_result(second)))

    assert tuple(decision.retained for decision in p0_decisions) == (True, False)
    assert tuple(decision.retained for decision in p1_decisions) == (True, True)
    assert tuple(decision.retained for decision in p2_decisions) == (True, True)


def test_effect_adaptive_scheduler_uses_binary_bounded_effect_reward() -> None:
    case = ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, b"a"),))
    key = effect_feedback_keys(_result(case).trace)[0]
    scheduler = EffectAdaptiveMutationScheduler(maximum_weight=8)
    operator = MutationOperatorId.ADD_ENTRY

    for _ in range(20):
        before = scheduler.weights
        selection = MutationSelection(operator, before, dict(before)[operator])
        attempt = apply_operator(case, random.Random(7), MutationPolicy.LEGACY, operator)
        evidence = scheduler.observe_outcome(selection, attempt, (key,), ())
        assert evidence.reward == 1

    assert dict(scheduler.weights)[operator] == 8
    other = MutationOperatorId.REMOVE_ENTRY
    before = scheduler.weights
    selection = MutationSelection(other, before, dict(before)[other])
    attempt = apply_operator(case, random.Random(8), MutationPolicy.LEGACY, other)
    evidence = scheduler.observe_outcome(selection, attempt, (), ())
    assert evidence.reward == 0 and evidence.weights_after == before


def test_policy_ids_and_closed_loop_campaign_are_deterministic() -> None:
    assert EffectSearchPolicy.P0_FINAL_STATE.value == (
        "final-state-v3-or-violation-v1-effect-observation-v2-uniform-mutation-v1"
    )
    assert EffectSearchPolicy.P1_EFFECT_RETENTION.value == (
        "effect-feedback-v2-or-violation-v1-uniform-mutation-v1"
    )
    assert EffectSearchPolicy.P2_EFFECT_ADAPTIVE.value == (
        "effect-feedback-v2-or-violation-v1-adaptive-mutation-v1"
    )
    seed = ArchiveCase((ArchiveEntry("seed", EntryType.REGULAR, b"seed"),))
    config = EffectCampaignConfig(
        random_seed=123,
        execution_budget=16,
        search_policy=EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
        mutation_policy=MutationPolicy.M1,
    )

    first = run_effect_campaign((seed,), _result, config)
    second = run_effect_campaign((seed,), _result, config)

    assert first == second
    for step in first.steps[1:]:
        assert step.mutation_attempt is not None
        assert step.scheduler_evidence is not None
        assert step.scheduler_evidence.parent_case_id == step.parent_case_id
        assert step.scheduler_evidence.child_case_id == step.result.base_result.case.case_id
        assert step.scheduler_evidence.selected_operator_id == step.mutation_attempt.operator_id
        assert step.scheduler_evidence.reward == int(bool(step.feedback.new_effect_keys))

import random
from dataclasses import replace

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_scheduler import EffectAdaptiveMutationScheduler
from inodefence.effect_synthetic import (
    _creation_effect,
    _edge,
    _lifecycle,
    _provenance,
    _result,
    _snapshots,
    _trace_for_case,
)
from inodefence.feedback import (
    EffectFeedbackKeyKind,
    EffectSearchPolicy,
    EffectSearchState,
    effect_feedback_keys,
)
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ArchiveEntryReference,
    CausalRelationKind,
    EffectEventTrace,
    EffectRunResult,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EntryLifecycleKind,
    EntryType,
    ObservationFailure,
    ObservationFailureKind,
    canonical_json,
)
from inodefence.mutation_scheduler import MutationSelection
from inodefence.mutator import MutationOperatorId, MutationPolicy, apply_operator


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

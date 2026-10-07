import random
from hashlib import sha256

import pytest

from inodefence.feedback import (
    SearchPolicy,
    SearchState,
    TransitionNoveltyIndex,
    TransitionSearchPolicy,
    TransitionSearchState,
    state_signature,
)
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ArchiveEntryReference,
    EntryCheckpoint,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    ObjectSnapshot,
    ObjectType,
    ObservationKind,
    ObservationPoint,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
    TraceCompleteness,
    TraceTermination,
    TransitionRunResult,
    TransitionTrace,
    derive_transition,
)
from inodefence.mutator import MutationPolicy
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.transition_campaign import (
    TransitionCampaignConfig,
    run_transition_campaign,
)

ROOT = "/var/lib/inodefence/core-run-transition-search"
PROTECTED = ("outside/sentinel",)


def _object(path: str, ino: int, content: bytes) -> ObjectSnapshot:
    return ObjectSnapshot(
        path,
        ObjectType.REGULAR,
        1,
        ino,
        1,
        0o644,
        len(content),
        1000,
        1000,
        ino,
        ino,
        content_digest=sha256(content).hexdigest(),
    )


def _checkpoint(
    index: int,
    objects: tuple[ObjectSnapshot, ...],
    entry: ArchiveEntryReference | None = None,
) -> EntryCheckpoint:
    return EntryCheckpoint(
        index,
        ObservationPoint(
            ObservationKind.BEFORE if entry is None else ObservationKind.ENTRY_BOUNDARY,
            entry,
        ),
        ROOT,
        tuple(sorted(objects, key=lambda obj: obj.path)),
        PROTECTED,
        index * 10,
        index * 10 + 1,
    )


def _result(case: ArchiveCase, *, final_tag: bytes = b"same") -> TransitionRunResult:
    sentinel = _object("outside/sentinel", 999, b"sentinel")
    checkpoints = [_checkpoint(0, (sentinel,))]
    objects = [sentinel]
    for index, entry in enumerate(case.entries):
        objects.append(_object(f"extract/entry-{index}", index + 10, final_tag))
        checkpoints.append(
            _checkpoint(
                index + 1,
                tuple(objects),
                ArchiveEntryReference(index, entry.path, entry.entry_type, entry.link_target),
            )
        )
    before = StateSnapshot(ROOT, SnapshotPhase.BEFORE, checkpoints[0].objects, PROTECTED)
    after = StateSnapshot(ROOT, SnapshotPhase.AFTER, checkpoints[-1].objects, PROTECTED)
    transitions = tuple(
        derive_transition(checkpoints[index], checkpoints[index + 1], index)
        for index in range(len(checkpoints) - 1)
    )
    trace = TransitionTrace(
        len(case.entries),
        tuple(checkpoints),
        transitions,
        after,
        TraceCompleteness.COMPLETE,
        TraceTermination.SUCCESS,
    )
    base = RunResult(
        case,
        "0" * 64,
        "synthetic-v1",
        ExecutionResult("synthetic", "1", (), ExecutionStatus.SUCCESS, 0, "", "", 0.0),
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )
    return TransitionRunResult(base, trace)


def test_transition_novelty_index_is_independent_and_deduplicates_trace_keys() -> None:
    case = ArchiveCase(
        (
            ArchiveEntry("a", EntryType.REGULAR, content=b"a"),
            ArchiveEntry("b", EntryType.REGULAR, content=b"b"),
        )
    )
    result = _result(case)
    index = TransitionNoveltyIndex()

    first = index.observe(result.trace)
    repeated = index.observe(result.trace)

    assert first.transition_novel and len(first.new_transition_keys) == 2
    assert not repeated.transition_novel and repeated.new_transition_keys == ()
    assert len(index.keys) == 2
    assert index.observations == 2 and index.novel_observations == 1


def test_p0_matches_existing_b3_final_state_admission_and_uniform_selection() -> None:
    cases = (
        ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, content=b"a"),)),
        ArchiveCase((ArchiveEntry("b", EntryType.DIRECTORY),)),
    )
    results = tuple(
        _result(case, final_tag=str(index).encode()) for index, case in enumerate(cases)
    )
    existing = SearchState(cases, SearchPolicy.B3)
    transition = TransitionSearchState(cases, TransitionSearchPolicy.P0_FINAL_ONLY)

    for result in results:
        old = existing.consider(result.base_result)
        new = transition.consider(result)
        assert (old.state_novel, old.new_violation_fingerprints, old.retained) == (
            new.full_state_novel,
            new.new_violation_fingerprints,
            new.retained,
        )

    old_rng = random.Random(91)
    new_rng = random.Random(91)
    assert [existing.select_case(old_rng) for _ in range(20)] == [
        transition.select_case(new_rng) for _ in range(20)
    ]
    assert old_rng.getstate() == new_rng.getstate()


def test_p1_admits_new_transition_when_final_state_is_not_novel() -> None:
    regular = ArchiveCase((ArchiveEntry("same", EntryType.REGULAR, content=b"x"),))
    directory = ArchiveCase((ArchiveEntry("same", EntryType.DIRECTORY),))
    regular_result = _result(regular)
    directory_result = _result(directory)
    final_only = TransitionSearchState((regular, directory), TransitionSearchPolicy.P0_FINAL_ONLY)
    transition = TransitionSearchState(
        (regular, directory), TransitionSearchPolicy.P1_TRANSITION_RETENTION
    )

    final_only.consider(regular_result)
    transition.consider(regular_result)
    p0 = final_only.consider(directory_result)
    p1 = transition.consider(directory_result)

    assert not p0.full_state_novel and not p0.retained
    assert not p1.full_state_novel and p1.transition_novel and p1.retained
    assert p1.new_violation_fingerprints == ()
    assert not any(verdict.violated for verdict in directory_result.base_result.violations)


def test_incomplete_trace_status_is_preserved_and_not_a_fake_empty_success() -> None:
    case = ArchiveCase(
        (
            ArchiveEntry("a", EntryType.REGULAR, content=b"a"),
            ArchiveEntry("b", EntryType.REGULAR, content=b"b"),
        )
    )
    complete = _result(case)
    prefix = complete.trace.checkpoints[:2]
    partial_trace = TransitionTrace(
        2,
        prefix,
        complete.trace.transitions[:1],
        complete.base_result.after,
        TraceCompleteness.INCOMPLETE,
        TraceTermination.ENTRY_CHECKPOINT_MISMATCH,
    )
    partial = TransitionRunResult(complete.base_result, partial_trace)
    state = TransitionSearchState((case,), TransitionSearchPolicy.P1_TRANSITION_RETENTION)

    decision = state.consider(partial)

    assert decision.trace_completeness == TraceCompleteness.INCOMPLETE
    assert decision.trace_termination == TraceTermination.ENTRY_CHECKPOINT_MISMATCH
    assert decision.transition_novel and decision.new_transition_keys


@pytest.mark.parametrize(
    "policy",
    (
        TransitionSearchPolicy.P0_FINAL_ONLY,
        TransitionSearchPolicy.P1_TRANSITION_RETENTION,
        TransitionSearchPolicy.P2_TRANSITION_ADAPTIVE,
    ),
)
def test_transition_campaign_runs_separated_policy_modes(
    policy: TransitionSearchPolicy,
) -> None:
    seed = ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, content=b"a"),))
    config = TransitionCampaignConfig(44, 6, policy, MutationPolicy.LEGACY)

    result = run_transition_campaign((seed,), _result, config)

    assert len(result.steps) == 6
    assert result.steps[0].parent_case_id is None
    assert all(
        step.result.base_result.case.case_id == step.feedback.case_id for step in result.steps
    )
    assert result.final_search_stats.observations == 6
    assert result.config.search_policy == policy
    assert result.steps[0].mutation_attempt is None
    assert result.steps[0].scheduler_evidence is None
    assert all(step.mutation_attempt is not None for step in result.steps[1:])
    assert all(step.scheduler_evidence is not None for step in result.steps[1:])
    if policy != TransitionSearchPolicy.P2_TRANSITION_ADAPTIVE:
        assert all(
            step.scheduler_evidence is not None
            and step.scheduler_evidence.reward == 0
            and all(weight == 1 for _, weight in step.scheduler_evidence.weights_after)
            for step in result.steps[1:]
        )


def test_transition_campaign_rejects_mismatched_producer_result() -> None:
    seed = ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, content=b"a"),))
    other = ArchiveCase((ArchiveEntry("b", EntryType.REGULAR, content=b"b"),))

    with pytest.raises(ValueError, match="requested case"):
        run_transition_campaign(
            (seed,),
            lambda _case: _result(other),
            TransitionCampaignConfig(1, 1, TransitionSearchPolicy.P1_TRANSITION_RETENTION),
        )

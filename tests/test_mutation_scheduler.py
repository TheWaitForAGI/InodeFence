import random

import pytest

from inodefence.feedback import ChangeFingerprint, ViolationFingerprint
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ChangeField,
    ContractId,
    EntryType,
    TransitionFeedbackKey,
    TransitionOrdinalClass,
    TransitionSignature,
)
from inodefence.mutation_scheduler import (
    MutationSelection,
    TransitionAdaptiveScheduler,
    UniformMutationScheduler,
)
from inodefence.mutator import (
    MutationOperatorId,
    MutationPolicy,
    apply_operator,
    m1,
    m1_addressing,
    mutate_attempt_with_policy,
    mutate_with_policy,
    operator_ids,
    operators,
)


def _case() -> ArchiveCase:
    return ArchiveCase(
        (
            ArchiveEntry("a", EntryType.REGULAR, content=b"a"),
            ArchiveEntry("b", EntryType.HARDLINK, link_target="a"),
        )
    )


def _legacy_reference(case: ArchiveCase, rng: random.Random, policy: MutationPolicy) -> ArchiveCase:
    if policy == MutationPolicy.LEGACY:
        return operators.mutate(case, rng)
    table = {
        MutationPolicy.LEGACY_NO_REORDER: operators._OPERATORS,
        MutationPolicy.M1: m1.OPERATORS,
        MutationPolicy.M1_NO_REORDER: m1.OPERATORS,
        MutationPolicy.M1_PROTECTED_COMPONENTS: m1_addressing.OPERATORS,
        MutationPolicy.M1_PROTECTED_COMPONENTS_NO_REORDER: m1_addressing.OPERATORS,
        MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK: m1_addressing.ESCAPE_OPERATORS,
        # The generic/state-aware escape policies dispatch over the generic escape set
        # here; the state-aware observed-name pool is applied only via apply_operator.
        MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK: m1_addressing.GENERIC_ESCAPE_OPERATORS,
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK: m1_addressing.GENERIC_ESCAPE_OPERATORS,
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND: m1_addressing.GENERIC_ESCAPE_OPERATORS,
    }[policy]
    operator = rng.choice(table)
    child = operator(case, rng)
    if (
        policy
        in (
            MutationPolicy.LEGACY_NO_REORDER,
            MutationPolicy.M1_NO_REORDER,
            MutationPolicy.M1_PROTECTED_COMPONENTS_NO_REORDER,
        )
        and operator is operators.reorder_entries
    ):
        return case
    return child


@pytest.mark.parametrize("policy", tuple(MutationPolicy))
def test_inspectable_uniform_dispatch_preserves_existing_rng_semantics(policy) -> None:
    case = _case()
    for seed in range(128):
        reference_rng = random.Random(seed)
        wrapper_rng = random.Random(seed)
        attempt_rng = random.Random(seed)

        expected = _legacy_reference(case, reference_rng, policy)
        wrapped = mutate_with_policy(case, wrapper_rng, policy)
        attempt = mutate_attempt_with_policy(case, attempt_rng, policy)

        assert wrapped == expected == attempt.child_case
        assert wrapper_rng.getstate() == reference_rng.getstate() == attempt_rng.getstate()
        assert attempt.parent_case_id == case.case_id
        assert attempt.applied == (attempt.child_case != case)


def test_stable_operator_id_and_no_op_attempt() -> None:
    empty = ArchiveCase(())
    attempt = apply_operator(
        empty,
        random.Random(1),
        MutationPolicy.LEGACY,
        MutationOperatorId.REMOVE_ENTRY,
    )

    assert operator_ids(MutationPolicy.M1) == tuple(MutationOperatorId)
    assert attempt.operator_id == MutationOperatorId.REMOVE_ENTRY
    assert not attempt.applied and attempt.child_case is empty


def _transition_key() -> TransitionFeedbackKey:
    return TransitionFeedbackKey(
        TransitionSignature(
            1,
            EntryType.REGULAR,
            TransitionOrdinalClass.FIRST,
            (),
            (),
            (),
            False,
            False,
            False,
        )
    )


def _violation() -> ViolationFingerprint:
    return ViolationFingerprint(
        ContractId.C0,
        (ChangeFingerprint("escape", (ChangeField.EXISTENCE,)),),
    )


def test_uniform_scheduler_matches_single_legacy_choice_and_never_rewards() -> None:
    scheduler = UniformMutationScheduler()
    expected_rng = random.Random(99)
    actual_rng = random.Random(99)
    expected = expected_rng.choice(tuple(MutationOperatorId))

    selection = scheduler.choose_operator(tuple(MutationOperatorId), actual_rng)
    attempt = apply_operator(_case(), actual_rng, MutationPolicy.LEGACY, selection.operator_id)
    evidence = scheduler.observe_outcome(selection, attempt, (_transition_key(),), (_violation(),))

    assert selection.operator_id == expected
    assert actual_rng.getstate() != expected_rng.getstate()  # operator application consumes draws
    assert evidence.reward == 0
    assert evidence.weights_before == evidence.weights_after == scheduler.weights
    assert evidence.new_transition_keys == (_transition_key(),)
    assert evidence.new_violation_fingerprints == (_violation(),)


def test_adaptive_scheduler_is_deterministic_for_equal_outcomes() -> None:
    first = TransitionAdaptiveScheduler()
    second = TransitionAdaptiveScheduler()
    first_rng = random.Random(1234)
    second_rng = random.Random(1234)
    case = _case()

    for index in range(30):
        left = first.choose_operator(tuple(MutationOperatorId), first_rng)
        right = second.choose_operator(tuple(MutationOperatorId), second_rng)
        assert left == right
        left_attempt = apply_operator(case, first_rng, MutationPolicy.M1, left.operator_id)
        right_attempt = apply_operator(case, second_rng, MutationPolicy.M1, right.operator_id)
        keys = (_transition_key(),) if index % 3 == 0 else ()
        left_evidence = first.observe_outcome(left, left_attempt, keys, ())
        right_evidence = second.observe_outcome(right, right_attempt, keys, ())
        assert left_attempt == right_attempt
        assert left_evidence == right_evidence

    assert first.weights == second.weights
    assert first_rng.getstate() == second_rng.getstate()


def test_adaptive_reward_is_transition_only_and_bounded() -> None:
    scheduler = TransitionAdaptiveScheduler(maximum_weight=8)
    case = _case()
    operator = MutationOperatorId.ADD_ENTRY

    for _ in range(20):
        before = scheduler.weights
        selected_weight = dict(before)[operator]
        selection = MutationSelection(operator, before, selected_weight)
        attempt = apply_operator(case, random.Random(7), MutationPolicy.LEGACY, operator)
        evidence = scheduler.observe_outcome(selection, attempt, (_transition_key(),), ())
        assert evidence.reward == 1
        assert 1 <= dict(evidence.weights_after)[operator] <= 8

    assert dict(scheduler.weights)[operator] == 8
    before = scheduler.weights
    other = MutationOperatorId.REMOVE_ENTRY
    selection = MutationSelection(other, before, dict(before)[other])
    attempt = apply_operator(case, random.Random(8), MutationPolicy.LEGACY, other)
    evidence = scheduler.observe_outcome(selection, attempt, (), (_violation(),))

    assert evidence.reward == 0
    assert evidence.weights_after == before


def test_scheduler_rejects_selection_application_mismatch() -> None:
    scheduler = TransitionAdaptiveScheduler()
    selection = MutationSelection(
        MutationOperatorId.ADD_ENTRY,
        scheduler.weights,
        1,
    )
    attempt = apply_operator(
        _case(), random.Random(1), MutationPolicy.LEGACY, MutationOperatorId.REMOVE_ENTRY
    )

    with pytest.raises(ValueError, match="differs"):
        scheduler.observe_outcome(selection, attempt, (), ())

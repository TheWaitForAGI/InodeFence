"""P2_EFFECT_ADAPTIVE selection must depend on effect feedback (P0-4 kill tests).

Feedback reaches the next selection through two channels: corpus admission
(parent pool) and P2 operator weights. Checks A and B2 isolate the weight channel,
B1 the admission channel. Each feedback-ignoring mutant below must fail at least one
check. Synthetic producer only; this is not node-tar (native) evidence.
"""

import random
from dataclasses import replace
from typing import Any

import pytest
from scripts.run_effect_demo import synthetic_demo_report

from inodefence import effect_campaign
from inodefence.effect_demo import compare_effect_campaign_reports
from inodefence.effect_scheduler import (
    EffectAdaptiveMutationScheduler,
    EffectUniformMutationScheduler,
)
from inodefence.effect_synthetic import _result
from inodefence.feedback import EffectSearchPolicy, EffectSearchState
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EffectFeedbackKey,
    EffectRunResult,
    EffectStreamCompleteness,
    EntryType,
    ObservationFailure,
    ObservationFailureKind,
)
from inodefence.mutation_scheduler import MutationSelection
from inodefence.mutator import MutationOperatorId, MutationPolicy, apply_operator, operator_ids

SEED_CASE = ArchiveCase((ArchiveEntry("seed", EntryType.REGULAR, b"seed"),))
REWARDED_OPERATOR = MutationOperatorId.ADD_HARDLINK
NEXT_DRAW_SEEDS = range(64)
CAMPAIGN_SEED = 123
CAMPAIGN_BUDGET = 40

NEXT_OPERATOR_IGNORES_FEEDBACK = "next P2 operator does not follow effect feedback"
P0_P2_NOT_SPLIT_BY_ADMISSION = "P0/P2 selections do not diverge through effect-key admission"
P1_P2_NOT_SPLIT_BY_REWARD = "P1/P2 selections do not diverge through effect-reward weights"


def _feedback_lost(result: EffectRunResult) -> EffectRunResult:
    trace = replace(
        result.trace,
        completeness=EffectStreamCompleteness.INVALID,
        observation_failures=(
            ObservationFailure(ObservationFailureKind.EVENT_LOSS, "injected loss", "synthetic", 2),
        ),
    )
    return EffectRunResult(result.base_result, trace)


def _next_operators(
    observe_child: bool,
) -> tuple[tuple[EffectFeedbackKey, ...], tuple[MutationOperatorId, ...]]:
    """Feed one ADD_HARDLINK child back to P2, then draw the next operator per RNG seed.

    Both branches share the seed state, parent, child case and RNG seeds; only
    whether the child's trace is feedback-eligible differs.
    """
    state = EffectSearchState((SEED_CASE,), EffectSearchPolicy.P2_EFFECT_ADAPTIVE)
    state.consider(_result(SEED_CASE))
    scheduler = EffectAdaptiveMutationScheduler()
    before = scheduler.weights
    selection = MutationSelection(REWARDED_OPERATOR, before, dict(before)[REWARDED_OPERATOR])
    attempt = apply_operator(SEED_CASE, random.Random(7), MutationPolicy.M1, REWARDED_OPERATOR)
    child = _result(attempt.child_case)
    decision = state.consider(child if observe_child else _feedback_lost(child))
    scheduler.observe_outcome(
        selection, attempt, decision.new_effect_keys, decision.new_violation_fingerprints
    )
    operators = operator_ids(MutationPolicy.M1)
    return decision.new_effect_keys, tuple(
        scheduler.choose_operator(operators, random.Random(seed)).operator_id
        for seed in NEXT_DRAW_SEEDS
    )


def _assert_next_operator_follows_effect_feedback() -> None:
    observed_keys, observed_next = _next_operators(observe_child=True)
    lost_keys, lost_next = _next_operators(observe_child=False)

    assert observed_keys and lost_keys == ()
    assert observed_next != lost_next, NEXT_OPERATOR_IGNORES_FEEDBACK
    assert observed_next.count(REWARDED_OPERATOR) > lost_next.count(REWARDED_OPERATOR), (
        NEXT_OPERATOR_IGNORES_FEEDBACK
    )


def _reports(
    left: EffectSearchPolicy,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    left_report = synthetic_demo_report(CAMPAIGN_SEED, CAMPAIGN_BUDGET, left, MutationPolicy.M1)
    right_report = synthetic_demo_report(
        CAMPAIGN_SEED, CAMPAIGN_BUDGET, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1
    )
    return left_report, right_report, compare_effect_campaign_reports(left_report, right_report)


def _divergence_source(comparison: dict[str, Any]) -> str | None:
    divergence = comparison["first_divergence"]
    return None if divergence is None else divergence["source"]


def _assert_p0_p2_split_by_effect_admission() -> None:
    p0, p2, comparison = _reports(EffectSearchPolicy.P0_FINAL_STATE)

    assert _divergence_source(comparison) == "corpus_admission", P0_P2_NOT_SPLIT_BY_ADMISSION
    # Before the parent pools differ both runs observe the same cases; P2 alone kept some
    # of them, and only because they carried new effect keys.
    corpus_step = comparison["first_corpus_difference_step"]
    shared_steps = zip(p0["steps"][:corpus_step], p2["steps"][:corpus_step], strict=True)
    p2_only = [
        (p0_step, p2_step)
        for p0_step, p2_step in shared_steps
        if p2_step["feedback"]["retained"] and not p0_step["feedback"]["retained"]
    ]
    assert p2_only
    for p0_step, p2_step in p2_only:
        assert p0_step["case_id"] == p2_step["case_id"]
        assert p2_step["feedback"]["new_effect_keys"]
        assert p2_step["feedback"]["new_violation_fingerprints"] == []
        assert not p0_step["feedback"]["full_state_novel"]


def _assert_p1_p2_split_by_effect_reward() -> None:
    p1, p2, comparison = _reports(EffectSearchPolicy.P1_EFFECT_RETENTION)

    assert _divergence_source(comparison) == "weights_feedback", P1_P2_NOT_SPLIT_BY_REWARD
    # The step before weights first differ is one shared selection with the same new effect
    # keys; only P2 turned them into reward on the selected operator.
    previous = comparison["first_weights_difference_step"] - 1
    p1_step, p2_step = p1["steps"][previous], p2["steps"][previous]
    assert p1_step["case_id"] == p2_step["case_id"]
    assert p1_step["feedback"]["new_effect_keys"] == p2_step["feedback"]["new_effect_keys"] != []
    assert p1_step["scheduler_evidence"]["reward"] == 0
    evidence = p2_step["scheduler_evidence"]
    operator = evidence["selected_operator_id"]
    assert evidence["reward"] == 1
    assert evidence["weights_after"][operator] == evidence["weights_before"][operator] + 1


def test_p2_next_operator_changes_with_effect_feedback() -> None:
    _assert_next_operator_follows_effect_feedback()


def test_p0_p2_first_divergence_comes_from_effect_key_admission() -> None:
    _assert_p0_p2_split_by_effect_admission()


def test_p1_p2_first_divergence_comes_from_effect_reward_weights() -> None:
    _assert_p1_p2_split_by_effect_reward()


def _choose_ignoring_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    def choose_operator(self, operators, rng):
        operator = rng.choice(operators)
        return MutationSelection(operator, self.weights, dict(self.weights)[operator])

    monkeypatch.setattr(EffectAdaptiveMutationScheduler, "choose_operator", choose_operator)


def _reward_ignoring_effect_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    observe_outcome = EffectAdaptiveMutationScheduler.observe_outcome

    def observe_without_reward(self, selection, attempt, new_effect_keys, fingerprints):
        evidence = observe_outcome(self, selection, attempt, (), fingerprints)
        return replace(evidence, new_effect_keys=new_effect_keys)

    monkeypatch.setattr(EffectAdaptiveMutationScheduler, "observe_outcome", observe_without_reward)


def _campaign_wires_uniform_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        effect_campaign, "EffectAdaptiveMutationScheduler", EffectUniformMutationScheduler
    )


def _p2_admits_by_final_state(monkeypatch: pytest.MonkeyPatch) -> None:
    declared_policy = EffectSearchState.policy.fget
    assert declared_policy is not None

    def admission_policy(self):
        actual = declared_policy(self)
        if actual == EffectSearchPolicy.P2_EFFECT_ADAPTIVE:
            return EffectSearchPolicy.P0_FINAL_STATE
        return actual

    monkeypatch.setattr(EffectSearchState, "policy", property(admission_policy))


@pytest.mark.parametrize(
    ("mutant", "check", "message"),
    (
        pytest.param(
            _choose_ignoring_weights,
            _assert_next_operator_follows_effect_feedback,
            NEXT_OPERATOR_IGNORES_FEEDBACK,
            id="choose-A",
        ),
        pytest.param(
            _choose_ignoring_weights,
            _assert_p1_p2_split_by_effect_reward,
            P1_P2_NOT_SPLIT_BY_REWARD,
            id="choose-B2",
        ),
        pytest.param(
            _reward_ignoring_effect_keys,
            _assert_next_operator_follows_effect_feedback,
            NEXT_OPERATOR_IGNORES_FEEDBACK,
            id="reward-A",
        ),
        pytest.param(
            _reward_ignoring_effect_keys,
            _assert_p1_p2_split_by_effect_reward,
            P1_P2_NOT_SPLIT_BY_REWARD,
            id="reward-B2",
        ),
        pytest.param(
            _campaign_wires_uniform_scheduler,
            _assert_p1_p2_split_by_effect_reward,
            P1_P2_NOT_SPLIT_BY_REWARD,
            id="wiring-B2",
        ),
        pytest.param(
            _p2_admits_by_final_state,
            _assert_p0_p2_split_by_effect_admission,
            P0_P2_NOT_SPLIT_BY_ADMISSION,
            id="admission-B1",
        ),
        pytest.param(
            _p2_admits_by_final_state,
            _assert_p1_p2_split_by_effect_reward,
            P1_P2_NOT_SPLIT_BY_REWARD,
            id="admission-B2",
        ),
    ),
)
def test_feedback_ignoring_mutant_fails_feedback_check(monkeypatch, mutant, check, message) -> None:
    mutant(monkeypatch)

    with pytest.raises(AssertionError, match=message):
        check()

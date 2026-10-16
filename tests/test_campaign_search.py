"""Policy-aware bounded campaigns retain full evidence and legacy safety gates."""

import json
import random
from dataclasses import replace

import pytest

import inodefence.campaign as campaign
from inodefence.campaign import (
    CampaignConfig,
    CampaignOrigin,
    SearchCampaignCompletedStep,
    SearchCampaignConfig,
    run_campaign,
    run_search_campaign,
)
from inodefence.feedback import FeedbackProjection, SearchPolicy, SearchState
from inodefence.model import ExecutionStatus, canonical_json
from inodefence.model.provenance import ExecutionSafety, TargetProvenance
from inodefence.mutator import (
    MutationAttempt,
    MutationOperatorId,
    MutationPolicy,
    mutate_with_policy,
)
from inodefence.runtime import SentinelSpec
from inodefence.targets.isolated import IsolatedTarget
from test_campaign import UnusedTarget
from test_campaign import _result as _empty_result
from test_feedback_corpus import _case, _creation, _result
from test_feedback_projection import _pair
from test_isolation_provenance import ControlledBackend, Invocation


def _outcome(case, index):
    result = _result(case, str(index // 3).encode())
    return replace(result, violations=(_creation(),) if index % 3 == 2 else ())


def _attempt(parent, child, policy):
    return MutationAttempt(
        MutationOperatorId.MUTATE_PATH,
        policy,
        parent.case_id,
        child,
        child != parent,
    )


@pytest.mark.parametrize("policy", tuple(SearchPolicy))
@pytest.mark.parametrize("projection", tuple(FeedbackProjection))
@pytest.mark.parametrize("mutation", tuple(MutationPolicy))
def test_composed_campaign_matches_declared_policies_rng_and_complete_feedback(
    monkeypatch, policy, projection, mutation
):
    seeds = (_case("first"), _case("second"))
    config = SearchCampaignConfig(91, 12, policy, mutation, projection)
    calls = []

    def execute(case, target, *, sentinels):
        outcome = _outcome(case, len(calls))
        calls.append(outcome)
        return outcome

    monkeypatch.setattr(campaign, "run_case", execute)
    global_state = random.getstate()
    result = run_search_campaign(seeds, UnusedTarget(), config)
    assert random.getstate() == global_state
    assert len(calls) == len(result.steps) == config.execution_budget
    assert [outcome.case for outcome in calls[:2]] == list(seeds)
    state = SearchState(seeds, policy, projection=projection)
    rng = random.Random(config.random_seed)
    for step in result.steps:
        if step.origin == CampaignOrigin.SEED:
            assert step.parent_case_id is None
        else:
            parent = state.select_case(rng)
            assert step.parent_case_id == parent.case_id
            assert step.result.case == mutate_with_policy(parent, rng, mutation)
        assert step.result is calls[step.index]
        assert state.consider(step.result) == step.feedback
    assert result.final_corpus_stats == state.stats
    assert result.unique_feedback_keys == state.unique_feedback_keys
    assert result.retained_case_ids == tuple(entry.case.case_id for entry in state.entries)
    assert result.active_case_id == (state.active_case.case_id if state.active_case else None)
    assert result.config is config
    encoded = json.loads(canonical_json(result))
    assert encoded["model"] == "SearchCampaignResult" and encoded["schema_version"] == 1
    assert encoded["value"]["config"]["search_policy"] == policy.value
    assert encoded["value"]["config"]["mutation_policy"] == mutation.value
    assert encoded["value"]["config"]["feedback_projection"] == projection.value
    assert json.loads(canonical_json(result.steps[0]))["model"] == "SearchCampaignStep"
    calls.clear()
    assert result == run_search_campaign(seeds, UnusedTarget(), config)


def test_b3_full_legacy_mutation_preserves_existing_campaign_behavior(monkeypatch):
    calls = []

    def execute(case, target, *, sentinels):
        result = _outcome(case, len(calls))
        calls.append(case)
        return result

    monkeypatch.setattr(campaign, "run_case", execute)
    seeds = (_case("a"), _case("b"))
    old = run_campaign(seeds, UnusedTarget(), CampaignConfig(12, 30))
    calls.clear()
    new = run_search_campaign(seeds, UnusedTarget(), SearchCampaignConfig(12, 30, SearchPolicy.B3))
    for actual, legacy in zip(new.steps, old.steps, strict=True):
        assert (actual.index, actual.origin, actual.parent_case_id, actual.result) == (
            legacy.index,
            legacy.origin,
            legacy.parent_case_id,
            legacy.result,
        )
        assert (actual.feedback.interesting, actual.feedback.retained) == (
            legacy.feedback.interesting,
            legacy.feedback.retained,
        )
    assert new.provenance == old.provenance
    assert new.retained_case_ids == old.retained_case_ids
    assert new.final_corpus_stats == old.final_corpus_stats
    assert json.loads(canonical_json(old))["schema_version"] == 2


@pytest.mark.parametrize("policy", tuple(SearchPolicy))
def test_violation_only_child_admission_is_independent_of_diagnostic_evidence(monkeypatch, policy):
    seed, child = _case("seed"), _case("child")
    monkeypatch.setattr(
        campaign,
        "mutate_attempt_with_policy",
        lambda parent, rng, mutation: _attempt(parent, child, mutation),
    )

    def execute(case, target, *, sentinels):
        return replace(_result(case), violations=(_creation(),) if case == child else ())

    monkeypatch.setattr(campaign, "run_case", execute)
    result = run_search_campaign((seed,), UnusedTarget(), SearchCampaignConfig(7, 2, policy))
    step = result.steps[1]
    assert step.result.violations == (_creation(),)
    assert step.feedback.interesting and not step.feedback.state_novel
    assert step.feedback.retained == (policy == SearchPolicy.B3)
    assert (child.case_id in result.retained_case_ids) == (policy == SearchPolicy.B3)


@pytest.mark.parametrize("projection", (FeedbackProjection.A1, FeedbackProjection.A2))
@pytest.mark.parametrize("policy", tuple(SearchPolicy))
def test_campaign_projection_changes_admission_key_and_keeps_full_oracle_evidence(
    monkeypatch, projection, policy
):
    first, second = _pair(projection)
    raw = canonical_json(second)
    monkeypatch.setattr(
        campaign,
        "mutate_attempt_with_policy",
        lambda parent, rng, mutation: _attempt(parent, second.case, mutation),
    )
    monkeypatch.setattr(
        campaign, "run_case", lambda case, target, **kwargs: first if case == first.case else second
    )
    config = SearchCampaignConfig(1, 2, policy, feedback_projection=projection)
    result = run_search_campaign((first.case,), UnusedTarget(), config)
    decision = result.steps[1].feedback
    assert result.steps[1].result is second and canonical_json(second) == raw
    assert decision.state_novel and not decision.feedback_key_novel
    assert decision.new_violation_fingerprints and decision.interesting
    assert decision.retained == (policy == SearchPolicy.B3)
    assert result.final_corpus_stats.unique_states == 2 and result.unique_feedback_keys == 1


def test_b0_parent_sequence_ignores_novelty_and_advances_every_child(monkeypatch):
    seeds = (_case("a"), _case("b"))
    config = SearchCampaignConfig(41, 15, SearchPolicy.B0, MutationPolicy.M1)
    runs = []
    for novel in (False, True):
        calls = []

        def execute(case, target, *, sentinels, calls=calls, novel=novel):
            result = _outcome(case, len(calls)) if novel else _result(case)
            calls.append(result)
            return result

        monkeypatch.setattr(campaign, "run_case", execute)
        runs.append(run_search_campaign(seeds, UnusedTarget(), config))
    assert [(step.parent_case_id, step.result.case) for step in runs[0].steps] == [
        (step.parent_case_id, step.result.case) for step in runs[1].steps
    ]
    for result in runs:
        assert result.retained_case_ids == () and result.final_corpus_stats.retained_cases == 0
        assert result.steps[2].parent_case_id == random.Random(41).choice(seeds).case_id
        for previous, step in zip(result.steps[2:-1], result.steps[3:], strict=True):
            assert step.parent_case_id == previous.result.case.case_id
    assert runs[0].final_corpus_stats.unique_states != runs[1].final_corpus_stats.unique_states


@pytest.mark.parametrize("policy", tuple(SearchPolicy))
@pytest.mark.parametrize("status", tuple(ExecutionStatus))
def test_noop_and_all_statuses_execute_once_and_keep_raw_results(monkeypatch, policy, status):
    calls = []

    def execute(case, target, *, sentinels):
        calls.append(case)
        return _empty_result(case, status)

    monkeypatch.setattr(campaign, "run_case", execute)
    monkeypatch.setattr(
        campaign,
        "mutate_attempt_with_policy",
        lambda case, rng, policy: _attempt(case, case, policy),
    )
    seed = _case("a")
    result = run_search_campaign((seed,), UnusedTarget(), SearchCampaignConfig(1, 6, policy))
    assert calls == [seed] * 6
    assert all(step.result.execution.status == status for step in result.steps)
    assert result.final_corpus_stats.observations == 6
    assert result.final_corpus_stats.unique_states == 1
    assert not any(step.feedback.retained for step in result.steps[1:])


@pytest.mark.parametrize("field", ("search_policy", "mutation_policy", "feedback_projection"))
def test_unknown_or_untyped_policy_is_rejected_without_silent_fallback(field):
    config = SearchCampaignConfig(1, 1, SearchPolicy.B3)
    for invalid in ("unknown-v1", getattr(config, field).value, None):
        with pytest.raises(ValueError, match=field):
            replace(config, **{field: invalid})
    for changes in ({"random_seed": True}, {"execution_budget": 0}):
        with pytest.raises(ValueError):
            replace(config, **changes)


def test_seed_only_b0_has_seed_bank_and_no_active_or_retained_parent(monkeypatch):
    monkeypatch.setattr(campaign, "run_case", lambda case, target, **kwargs: _result(case))
    seeds = (_case("a"), _case("b"))
    result = run_search_campaign(seeds, UnusedTarget(), SearchCampaignConfig(1, 2, SearchPolicy.B0))
    assert result.initial_case_ids == tuple(case.case_id for case in seeds)
    assert result.active_case_id is None and result.retained_case_ids == ()


def test_invalid_seeds_and_execution_errors_fail_without_completed_results(monkeypatch):
    calls = []

    def execute(case, target, **kwargs):
        calls.append(case)
        raise RuntimeError("controller unavailable")

    monkeypatch.setattr(campaign, "run_case", execute)
    config = SearchCampaignConfig(1, 1, SearchPolicy.B0)
    for cases in ((), (_case("a"), _case("a")), (_case("a"), _case("b"))):
        with pytest.raises(ValueError):
            run_search_campaign(cases, UnusedTarget(), config)
    assert calls == []
    with pytest.raises(RuntimeError, match="controller unavailable"):
        run_search_campaign((_case("a"),), UnusedTarget(), config)
    assert len(calls) == 1


def test_completed_step_sink_observes_each_step_before_next_execution(monkeypatch):
    calls = []
    observed = []

    def execute(case, target, **kwargs):
        calls.append(case)
        assert len(observed) == len(calls) - 1
        return _result(case)

    monkeypatch.setattr(campaign, "run_case", execute)
    seeds = (_case("a"), _case("b"))
    result = run_search_campaign(
        seeds,
        UnusedTarget(),
        SearchCampaignConfig(3, 5, SearchPolicy.B3),
        completed_step=observed.append,
    )
    assert tuple(observed) == result.steps
    assert len(calls) == 5


def test_completed_record_preserves_exact_mutation_attempts(monkeypatch):
    records = []
    monkeypatch.setattr(campaign, "run_case", lambda case, target, **kwargs: _result(case))
    seeds = (_case("a"), _case("b"))
    result = run_search_campaign(
        seeds,
        UnusedTarget(),
        SearchCampaignConfig(3, 5, SearchPolicy.B3, MutationPolicy.M1),
        completed_record=records.append,
    )
    assert all(isinstance(record, SearchCampaignCompletedStep) for record in records)
    assert tuple(record.step for record in records) == result.steps
    assert all(record.mutation_attempt is None for record in records[:2])
    assert all(record.mutation_attempt is not None for record in records[2:])
    for record in records[2:]:
        assert record.mutation_attempt.child_case == record.step.result.case
        assert record.mutation_attempt.parent_case_id == record.step.parent_case_id


def test_completed_step_sink_failure_stops_before_another_execution(monkeypatch):
    calls = []
    observed = []

    def execute(case, target, **kwargs):
        calls.append(case)
        return _result(case)

    def stop(step):
        observed.append(step)
        if step.index == 1:
            raise RuntimeError("controlled evidence sink failure")

    monkeypatch.setattr(campaign, "run_case", execute)
    with pytest.raises(RuntimeError, match="controlled evidence sink failure"):
        run_search_campaign(
            (_case("a"), _case("b")),
            UnusedTarget(),
            SearchCampaignConfig(3, 5, SearchPolicy.B3),
            completed_step=stop,
        )
    assert [step.index for step in observed] == [0, 1]
    assert len(calls) == 2


def test_invalid_completed_step_sink_fails_before_campaign_preparation(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid sink must fail before provenance or execution")

    monkeypatch.setattr(campaign, "_prepare_campaign", forbidden)
    with pytest.raises(ValueError, match="completed_step"):
        run_search_campaign(
            (_case("a"),),
            UnusedTarget(),
            SearchCampaignConfig(1, 1, SearchPolicy.B0),
            completed_step=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="completed_record"):
        run_search_campaign(
            (_case("a"),),
            UnusedTarget(),
            SearchCampaignConfig(1, 1, SearchPolicy.B0),
            completed_record=object(),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("runner", (run_campaign, run_search_campaign))
def test_shared_execution_gate_rejects_case_and_provenance_drift(monkeypatch, runner):
    config = (
        CampaignConfig(1, 2)
        if runner is run_campaign
        else SearchCampaignConfig(1, 2, SearchPolicy.B0)
    )
    for drift in ("case", "provenance"):

        def execute(case, target, drift=drift, **kwargs):
            result = _result(case)
            return (
                replace(result, case=_case("other"))
                if drift == "case"
                else replace(result, execution=replace(result.execution, target_version="other"))
            )

        monkeypatch.setattr(campaign, "run_case", execute)
        with pytest.raises(ValueError, match="case|provenance"):
            runner((_case("a"),), UnusedTarget(), config)


def test_required_isolation_and_subclass_bypass_fail_before_freeze_or_execution(monkeypatch):
    class RequiresIsolation(UnusedTarget):
        @property
        def provenance(self):
            return TargetProvenance("controlled", "test", None, ExecutionSafety.ISOLATION_REQUIRED)

    def forbidden(*args, **kwargs):
        raise AssertionError("isolation rejection must precede execution and provenance capture")

    monkeypatch.setattr(campaign, "freeze_provenance", forbidden)
    monkeypatch.setattr(campaign, "run_case", forbidden)
    bypass = type("Bypass", (IsolatedTarget,), {})(Invocation(), ControlledBackend())
    for target in (RequiresIsolation(), bypass):
        with pytest.raises(ValueError, match="requires execution isolation"):
            run_search_campaign((_case("a"),), target, SearchCampaignConfig(1, 1, SearchPolicy.B0))


def test_isolated_wrapper_provenance_and_sentinels_remain_bound(monkeypatch):
    target = IsolatedTarget(Invocation(), ControlledBackend())
    specs = (SentinelSpec("custom", b"protected"),)

    def execute(case, target, *, sentinels):
        assert sentinels is specs
        result = _result(case)
        return replace(
            result, execution=replace(result.execution, target_version="1.2.3", timeout_seconds=5)
        )

    monkeypatch.setattr(campaign, "run_case", execute)
    result = run_search_campaign(
        (_case("a"),), target, SearchCampaignConfig(1, 2, SearchPolicy.B0), sentinels=specs
    )
    assert result.provenance.target == target.provenance
    assert result.provenance.isolation is not None
    assert result.provenance.isolation.policy == target.isolation_policy

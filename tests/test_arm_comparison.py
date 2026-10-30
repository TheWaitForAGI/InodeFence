"""A/B/C/D single-path comparison fixes the arm realization and reuses metrics.

These tests use the established synthetic campaign pattern (a trusted-reference
target with a monkeypatched run_case) so no real extractor executes. They pin the
fixed arm->policy realization against the evaluation protocol, prove the common
metrics are the reused evaluation.summary arithmetic, and prove the honest
boundaries (right-censoring, B0 zero admission/growth, no effectiveness ranking).
"""

import pytest

import inodefence.campaign as campaign
from inodefence.campaign import SearchCampaignConfig, run_search_campaign
from inodefence.evaluation.arm_comparison import (
    DEFAULT_ARMS,
    Arm,
    campaign_metrics,
    comparison_markdown,
    run_abcd_comparison,
)
from inodefence.evaluation.summary import _observation_counts
from inodefence.feedback import FeedbackProjection, SearchPolicy
from inodefence.mutator import MutationPolicy
from test_campaign import UnusedTarget
from test_campaign_search import _outcome
from test_feedback_corpus import _case, _result


def _seeds():
    return (_case("first"), _case("second"))


def _violating(calls):
    """Execute that places a C0 violation at 1-based executions 3, 6, 9, ... (index % 3 == 2)."""

    def execute(case, target, *, sentinels):
        outcome = _outcome(case, len(calls))
        calls.append(outcome)
        return outcome

    return execute


def _benign(calls):
    """Execute that never observes a violation, so first-violation is right-censored."""

    def execute(case, target, *, sentinels):
        calls.append(case)
        return _result(case, str(len(calls)).encode())

    return execute


def test_default_arms_realize_protocol_abcd():
    assert set(DEFAULT_ARMS) == set(Arm)
    assert all(DEFAULT_ARMS[arm].arm == arm for arm in Arm)
    assert all(
        spec.feedback_projection == FeedbackProjection.FULL for spec in DEFAULT_ARMS.values()
    )
    realization = {
        arm: (DEFAULT_ARMS[arm].search_policy, DEFAULT_ARMS[arm].mutation_policy) for arm in Arm
    }
    assert realization == {
        Arm.A: (SearchPolicy.B0, MutationPolicy.LEGACY),
        Arm.B: (SearchPolicy.B0, MutationPolicy.M1),
        Arm.C: (SearchPolicy.B3, MutationPolicy.M1),
        Arm.D: (SearchPolicy.D, MutationPolicy.M1),
    }


def test_campaign_metrics_reuse_summary_and_match_corpus_stats(monkeypatch):
    calls = []
    monkeypatch.setattr(campaign, "run_case", _violating(calls))
    result = run_search_campaign(
        _seeds(), UnusedTarget(), SearchCampaignConfig(91, 12, SearchPolicy.B3)
    )
    metrics = campaign_metrics(result)
    counts = _observation_counts(tuple(step.result for step in result.steps))

    assert metrics.total_executions == 12 == len(result.steps)
    assert sum(metrics.status_counts.values()) == metrics.total_executions
    assert metrics.status_counts == counts["status_counts"]
    assert metrics.any_violation_executions == counts["any_contract_observed_count"]
    assert metrics.contract_observed_counts == counts["contract_observed_counts"]
    # Reused arithmetic must equal the campaign's own stats (measured identically).
    assert metrics.unique_state_signatures == counts["unique_state_signature_count"]
    assert metrics.unique_state_signatures == result.final_corpus_stats.unique_states
    assert metrics.unique_violation_fingerprints == counts["unique_violation_fingerprint_count"]
    assert (
        metrics.unique_violation_fingerprints
        == result.final_corpus_stats.unique_violation_fingerprints
    )
    # _outcome violates at indices 2, 5, 8, 11 -> first at 1-based execution 3.
    assert metrics.executions_to_first_violation == 3
    assert metrics.first_violation_censored is False
    assert metrics.right_censored_at == 12
    assert metrics.cumulative_target_seconds_to_first_violation is not None
    assert metrics.cumulative_target_seconds_to_first_violation >= 0.0


def test_first_violation_right_censored_when_no_hit(monkeypatch):
    calls = []
    monkeypatch.setattr(campaign, "run_case", _benign(calls))
    result = run_search_campaign(
        _seeds(), UnusedTarget(), SearchCampaignConfig(5, 8, SearchPolicy.B3)
    )
    metrics = campaign_metrics(result)
    assert metrics.any_violation_executions == 0
    assert metrics.executions_to_first_violation is None
    assert metrics.first_violation_censored is True
    assert metrics.right_censored_at == 8
    assert metrics.cumulative_target_seconds_to_first_violation is None


def test_arm_a_b0_has_zero_admission_and_corpus_growth(monkeypatch):
    calls = []
    monkeypatch.setattr(campaign, "run_case", _violating(calls))
    config = DEFAULT_ARMS[Arm.A].config(random_seed=3, execution_budget=10)
    metrics = campaign_metrics(run_search_campaign(_seeds(), UnusedTarget(), config))
    assert metrics.search_policy == SearchPolicy.B0
    assert metrics.admission_eligible_count == 0
    assert metrics.admission_eligible_rate == 0.0
    assert metrics.retained_end == 0
    assert metrics.corpus_growth == 0


def test_run_abcd_comparison_is_single_path_and_deterministic(monkeypatch):
    calls = []
    monkeypatch.setattr(campaign, "run_case", _violating(calls))
    seeds = _seeds()
    comparison = run_abcd_comparison(seeds, UnusedTarget(), random_seed=42, execution_budget=9)

    assert set(comparison.metrics) == set(Arm)
    assert comparison.initial_case_ids == tuple(case.case_id for case in seeds)
    assert comparison.random_seed == 42 and comparison.execution_budget == 9
    for arm in Arm:
        spec = DEFAULT_ARMS[arm]
        metric = comparison.metrics[arm]
        assert comparison.arm_specs[arm] == spec
        assert metric.total_executions == 9
        assert (metric.search_policy, metric.mutation_policy, metric.feedback_projection) == (
            spec.search_policy,
            spec.mutation_policy,
            spec.feedback_projection,
        )

    calls.clear()
    again = run_abcd_comparison(seeds, UnusedTarget(), random_seed=42, execution_budget=9)
    assert again == comparison


def test_single_arm_driver_matches_standalone_campaign(monkeypatch):
    seeds = _seeds()
    driver_calls = []
    monkeypatch.setattr(campaign, "run_case", _violating(driver_calls))
    comparison = run_abcd_comparison(
        seeds, UnusedTarget(), random_seed=7, execution_budget=9, arms=(Arm.C,)
    )
    standalone_calls = []
    monkeypatch.setattr(campaign, "run_case", _violating(standalone_calls))
    standalone = campaign_metrics(
        run_search_campaign(
            seeds, UnusedTarget(), DEFAULT_ARMS[Arm.C].config(random_seed=7, execution_budget=9)
        )
    )
    assert comparison.metrics[Arm.C] == standalone


def test_comparison_markdown_carries_caveats(monkeypatch):
    calls = []
    monkeypatch.setattr(campaign, "run_case", _benign(calls))
    comparison = run_abcd_comparison(_seeds(), UnusedTarget(), random_seed=1, execution_budget=6)
    text = comparison_markdown(comparison)
    assert "A/B/C/D single-path arm comparison" in text
    assert all(arm.value in text for arm in Arm)
    assert "> 6" in text
    assert "not known-class rediscovery" in text
    assert "no effectiveness ranking" in text
    assert "right-censored" in text


def test_run_abcd_comparison_validates_arms(monkeypatch):
    monkeypatch.setattr(campaign, "run_case", _benign([]))
    seeds = _seeds()
    with pytest.raises(ValueError):
        run_abcd_comparison(seeds, UnusedTarget(), random_seed=1, execution_budget=6, arms=())
    with pytest.raises(ValueError):
        run_abcd_comparison(
            seeds, UnusedTarget(), random_seed=1, execution_budget=6, arms=(Arm.A, Arm.A)
        )
    with pytest.raises(ValueError):
        run_abcd_comparison(
            seeds, UnusedTarget(), random_seed=1, execution_budget=6, arms=(Arm.A,), arm_specs={}
        )

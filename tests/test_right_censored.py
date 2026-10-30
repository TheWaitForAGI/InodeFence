"""Right-censored single-arm control roll-up: honest denominators and Wilson CI."""

import pytest

from inodefence.evaluation.right_censored import (
    SeedOutcome,
    right_censored_summary,
    wilson_interval,
)


def test_wilson_interval_extremes_and_midpoint():
    low0, high0 = wilson_interval(0, 5)
    assert low0 == 0.0 and 0.40 < high0 < 0.45
    low5, high5 = wilson_interval(5, 5)
    assert high5 == 1.0 and low5 > 0.5
    low, high = wilson_interval(1, 3)
    assert 0.0 < low < 1 / 3 < high < 1.0


def test_wilson_interval_validation():
    with pytest.raises(ValueError):
        wilson_interval(3, 2)
    with pytest.raises(ValueError):
        wilson_interval(0, 0)
    with pytest.raises(ValueError):
        wilson_interval(-1, 5)


def test_seed_outcome_validation():
    SeedOutcome(1, 1500, complete=True, hit=True, first_hit_executions=264)  # valid hit
    SeedOutcome(2, 1500, complete=True, hit=False, first_hit_executions=None)  # valid no-hit
    SeedOutcome(3, 1500, complete=False, hit=False, first_hit_executions=None)  # valid incomplete
    with pytest.raises(ValueError):
        SeedOutcome(
            4, 1500, complete=False, hit=True, first_hit_executions=10
        )  # hit needs complete
    with pytest.raises(ValueError):
        SeedOutcome(5, 1500, complete=True, hit=True, first_hit_executions=None)  # hit needs index
    with pytest.raises(ValueError):
        SeedOutcome(6, 1500, complete=True, hit=True, first_hit_executions=2000)  # index > budget
    with pytest.raises(ValueError):
        SeedOutcome(7, 1500, complete=True, hit=False, first_hit_executions=3)  # no-hit has index


def test_right_censored_summary_counts_ci_and_framing():
    outcomes = [
        SeedOutcome(1, 1500, complete=True, hit=True, first_hit_executions=264),
        SeedOutcome(2, 1500, complete=True, hit=False, first_hit_executions=None),
        SeedOutcome(3, 1500, complete=True, hit=False, first_hit_executions=None),
        SeedOutcome(4, 1500, complete=False, hit=False, first_hit_executions=None),
    ]
    summary = right_censored_summary(outcomes)
    assert summary["number_complete_campaigns"] == 3
    assert summary["number_incomplete_excluded"] == 1 and summary["incomplete_seeds"] == [4]
    assert summary["number_observed_target"] == 1
    proportion = summary["observed_proportion"]
    assert proportion["numerator"] == 1 and proportion["denominator"] == 3
    assert proportion["value"] == pytest.approx(1 / 3)
    low, high = proportion["wilson_95_ci"]
    assert 0.0 < low < 1 / 3 < high < 1.0
    assert summary["number_right_censored"] == 2
    assert {entry["seed"] for entry in summary["censored"]} == {2, 3}
    assert summary["first_hit_executions_observed_only"]["values"] == [264]
    assert "EN-008" in summary["comparison"]
    assert "not proof the target is unreachable" in summary["interpretation"]


def test_right_censored_summary_all_censored_is_zero_proportion():
    outcomes = [
        SeedOutcome(seed, 1500, complete=True, hit=False, first_hit_executions=None)
        for seed in range(5)
    ]
    summary = right_censored_summary(outcomes)
    assert summary["number_observed_target"] == 0
    assert summary["observed_proportion"]["value"] == 0.0
    low, high = summary["observed_proportion"]["wilson_95_ci"]
    assert low == 0.0 and high > 0.0
    assert summary["number_right_censored"] == 5

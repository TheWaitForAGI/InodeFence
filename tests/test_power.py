"""Log-rank power/sample-size (Schoenfeld): reference values hand-checked in docstrings."""

import math

import pytest

from inodefence.evaluation.power import (
    events_per_campaign,
    expected_events,
    power_for_events,
    power_from_design,
    required_campaigns_per_arm,
    required_events,
)


def test_required_events_matches_textbook_schoenfeld():
    # HR=0.5, 80% power, 5% two-sided, balanced:
    #   (1.959964 + 0.841621)^2 * 4 / ln(0.5)^2 = 7.84888 * 4 / 0.480453 = 65.35
    assert required_events(0.5, power=0.8, alpha=0.05) == pytest.approx(65.35, abs=0.05)
    # 90% power raises the requirement.
    assert required_events(0.5, power=0.9) > required_events(0.5, power=0.8)


def test_power_for_events_inverts_required_events():
    for hr, power in ((0.5, 0.8), (0.6, 0.9), (2.0, 0.75)):
        needed = required_events(hr, power=power)
        assert power_for_events(needed, hr) == pytest.approx(power, abs=1e-3)


def test_power_for_events_zero_events_is_at_most_alpha():
    assert power_for_events(0.0, 0.5, alpha=0.05) == pytest.approx(0.05)


def test_required_events_validation():
    with pytest.raises(ValueError):
        required_events(1.0)
    with pytest.raises(ValueError):
        required_events(-0.5)
    with pytest.raises(ValueError):
        required_events(0.5, power=1.5)
    with pytest.raises(ValueError):
        required_events(0.5, alpha=0.0)


def test_events_per_campaign_exposure_model():
    # hazard 2e-5 over 200 executions: 1 - exp(-0.004) = 0.0039920
    assert events_per_campaign(per_execution_hazard=2e-5, budget=200) == pytest.approx(
        1 - math.exp(-0.004)
    )
    # half the campaigns abort at half exposure (100 executions):
    #   0.5*(1-exp(-0.004)) + 0.5*(1-exp(-0.002))
    mixed = events_per_campaign(
        per_execution_hazard=2e-5, budget=200, abort_fraction=0.5, aborted_exposure_fraction=0.5
    )
    assert mixed == pytest.approx(0.5 * (1 - math.exp(-0.004)) + 0.5 * (1 - math.exp(-0.002)))


def test_expected_events_sums_both_arms():
    result = expected_events(
        campaigns_per_arm=100, per_execution_hazard=2e-5, budget=200, hazard_ratio=1.0
    )
    rate = 1 - math.exp(-0.004)
    assert result["control_expected_events"] == pytest.approx(100 * rate)
    assert result["total_expected_events"] == pytest.approx(200 * rate)


def test_power_from_design_and_required_campaigns_are_consistent():
    # size a design to 80% power, then confirm that many campaigns delivers ~80% power
    sizing = required_campaigns_per_arm(
        per_execution_hazard=2e-3, budget=200, hazard_ratio=0.5, power=0.8
    )
    assert sizing["required_events"] == pytest.approx(65.35, abs=0.05)
    assert sizing["control_campaigns"] >= sizing["control_campaigns_fractional"]
    delivered = power_from_design(
        campaigns_per_arm=sizing["control_campaigns"],
        per_execution_hazard=2e-3,
        budget=200,
        hazard_ratio=0.5,
    )
    assert delivered["power"] >= 0.8


def test_required_campaigns_fractional_relationship():
    sizing = required_campaigns_per_arm(
        per_execution_hazard=2e-5, budget=200, hazard_ratio=0.5, power=0.8
    )
    expected_fractional = sizing["required_events"] / sizing["events_per_control_campaign"]
    assert sizing["control_campaigns_fractional"] == pytest.approx(expected_fractional)
    assert sizing["control_campaigns"] == math.ceil(expected_fractional)

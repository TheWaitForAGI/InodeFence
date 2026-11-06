"""Unit tests for the oracle false-positive upper-bound analyzer.

Cover the pure Clopper-Pearson bound (exact rule-of-three at x=0, monotonicity,
endpoints) and the report-counting that feeds it. No scipy: the bound is a
dependency-free binomial-tail bisection.
"""

import math

import pytest
from scripts.analyze_oracle_fp_bound import (
    CONTRACTS,
    ReportCounts,
    clopper_pearson_upper,
    count_report,
    pool,
)


def test_zero_flagged_matches_rule_of_three() -> None:
    assert clopper_pearson_upper(0, 100) == pytest.approx(1 - 0.05 ** (1 / 100), abs=1e-6)
    assert clopper_pearson_upper(0, 30) == pytest.approx(1 - 0.05 ** (1 / 30), abs=1e-6)


def test_full_count_bound_is_one() -> None:
    assert clopper_pearson_upper(50, 50) == 1.0


def test_bound_is_monotone_in_flagged_and_tightens_with_n() -> None:
    assert clopper_pearson_upper(1, 100) > clopper_pearson_upper(0, 100)
    assert clopper_pearson_upper(0, 1200) < clopper_pearson_upper(0, 100)


def test_one_sided_beta_quantile_value() -> None:
    # Beta(1, 100) 0.95 quantile == 1 - 0.05**(1/100); the bound equals it at x=0.
    assert clopper_pearson_upper(0, 100) == pytest.approx(0.02951, abs=1e-4)
    # x=5, n=100 one-sided 95% upper is ~0.1022 (Beta(6,95) 0.95 quantile).
    assert clopper_pearson_upper(5, 100) == pytest.approx(0.1022, abs=1e-3)


@pytest.mark.parametrize("flagged,scored", [(-1, 10), (11, 10), (0, 0), (3, -2)])
def test_invalid_counts_rejected(flagged: int, scored: int) -> None:
    with pytest.raises(ValueError):
        clopper_pearson_upper(flagged, scored)


@pytest.mark.parametrize("confidence", [0.0, 1.0, -0.1, 1.5])
def test_invalid_confidence_rejected(confidence: float) -> None:
    with pytest.raises(ValueError):
        clopper_pearson_upper(0, 10, confidence)


def _step(observed: bool, violated: bool, oracle: dict[str, bool]) -> dict:
    return {"frame_observed": observed, "contract_violated": violated, "oracle": oracle}


def test_count_report_excludes_unobserved_steps() -> None:
    report = {
        "label": "demo run",
        "producer": "p",
        "config": {"random_seed": 7},
        "discovered_violation": True,
        "steps": [
            _step(True, False, {"C0": False, "C1": False, "C2": False}),
            _step(True, True, {"C0": True, "C1": False, "C2": False}),
            _step(False, True, {"C0": True, "C1": True, "C2": True}),  # unobserved -> excluded
            _step(True, True, {"C0": False, "C1": False, "C2": True}),
        ],
    }
    counts = count_report(report)
    assert counts.scored == 3
    assert counts.flagged_any == 2
    assert counts.flagged == {"C0": 1, "C1": 0, "C2": 1}
    assert counts.seed == 7
    assert counts.discovered_violation is True


def test_count_report_requires_steps_list() -> None:
    with pytest.raises(ValueError):
        count_report({"label": "x"})


def test_pool_sums_scored_and_per_contract() -> None:
    a = ReportCounts("a", "p", 1, False, 100, 0, {c: 0 for c in CONTRACTS})
    b = ReportCounts("b", "p", 2, True, 100, 1, {"C0": 1, "C1": 0, "C2": 0})
    merged = pool([a, b])
    assert merged.scored == 200
    assert merged.flagged_any == 1
    assert merged.flagged["C0"] == 1
    assert merged.discovered_violation is True
    assert clopper_pearson_upper(merged.flagged_any, merged.scored) < 0.03


def test_pool_rejects_empty() -> None:
    with pytest.raises(ValueError):
        pool([])


def test_bound_stays_in_unit_interval() -> None:
    for scored in (1, 7, 100, 999):
        for flagged in (0, scored // 2, scored):
            value = clopper_pearson_upper(flagged, scored)
            assert 0.0 <= value <= 1.0
            assert math.isfinite(value)

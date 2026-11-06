"""Arm x abort independence: Fisher exact, chi-square, and the audit-13a reporting flag.

Reference p-values are hand-computed in the test bodies from the hypergeometric mass.
"""

import pytest

from inodefence.evaluation.independence import (
    arm_abort_independence,
    arm_abort_independence_from_contingency,
    chi_square_independence,
    fisher_exact,
    is_assessable,
    monte_carlo_independence,
)


def test_fisher_exact_2x2_tea_tasting():
    # [[3,1],[1,3]] margins 4/4 x 4/4, N=8: P(a)=C(4,a)C(4,4-a)/C(8,4);
    # observed a=3 -> P=16/70; two-sided sums a in {0,1,3,4} = (1+16+16+1)/70 = 0.485714
    result = fisher_exact([[3, 1], [1, 3]])
    assert result["exact"] is True and result["number_tables_enumerated"] == 5
    assert result["p_value"] == pytest.approx(0.485714, abs=1e-5)


def test_fisher_exact_2x2_perfect_association():
    # [[10,0],[0,10]]: only a=0 and a=10 reach P=1/C(20,10); two-sided = 2/184756
    result = fisher_exact([[10, 0], [0, 10]])
    assert result["p_value"] == pytest.approx(2 / 184756, abs=1e-9)


def test_fisher_exact_uniform_is_one():
    # [[1,1],[1,1]]: P = 1/6, 4/6, 1/6; observed is the mode so every table is <= it -> p=1
    result = fisher_exact([[1, 1], [1, 1]])
    assert result["p_value"] == pytest.approx(1.0)
    assert result["number_tables_enumerated"] == 3


def test_chi_square_independence_hand_value():
    # [[10,20],[20,10]]: E=15 all; chi2 = 4*(5^2/15) = 6.6667; df=1; p ~ 0.0098
    result = chi_square_independence([[10, 20], [20, 10]])
    assert result["chi_square"] == pytest.approx(6.66667, abs=1e-4)
    assert result["degrees_of_freedom"] == 1
    assert result["p_value"] == pytest.approx(0.0098, abs=5e-4)
    assert result["low_expected_warning"] is False


def test_fisher_exact_rxc_matches_enumeration_count():
    # a 2x3 table enumerates; its probabilities must normalize (p_value is in [0,1])
    result = fisher_exact([[1, 2, 3], [3, 2, 1]])
    assert result["exact"] is True
    assert 0.0 <= result["p_value"] <= 1.0


def test_is_assessable_degenerate_cases():
    assert is_assessable([[4, 0, 0], [4, 0, 0], [4, 0, 0]])[0] is False  # one non-empty column
    assert is_assessable([[4, 0], [0, 0], [0, 0]])[0] is False  # one non-empty row
    assert is_assessable([[3, 1], [1, 3]])[0] is True


def test_chi_square_not_assessable_returns_none():
    result = chi_square_independence([[4, 0, 0], [4, 0, 0], [4, 0, 0]])
    assert result["assessable"] is False and result["p_value"] is None


def test_arm_abort_flag_not_assessable_on_zero_aborts():
    # G1 smoke contingency: every campaign complete -> abort collapse has no events
    report = arm_abort_independence([[4, 0, 0], [4, 0, 0], [4, 0, 0]], ["R", "D", "S-u"])
    assert report["flag"] == "not_assessable"
    assert report["primary_arm_vs_abort"]["assessable"] is False
    assert report["primary_arm_vs_abort"]["collapse"]["table"] == [[0, 4], [0, 4], [0, 4]]


def test_arm_abort_flag_report_sensitivity_on_dependence():
    # R never aborts, S aborts half: abort collapse [[0,10],[5,5]] -> Fisher p = 0.0325 <= 0.1
    report = arm_abort_independence([[10, 0, 0], [5, 5, 0]], ["R", "S-u"])
    assert report["primary_arm_vs_abort"]["p_value"] == pytest.approx(0.03251, abs=1e-4)
    assert report["flag"] == "report_sensitivity"


def test_arm_abort_flag_retained_on_balance():
    # symmetric aborts across arms -> Fisher p = 1.0 > 0.1 -> assumption retained
    report = arm_abort_independence([[5, 5, 0], [5, 5, 0]], ["R", "S-u"])
    assert report["primary_arm_vs_abort"]["p_value"] == pytest.approx(1.0)
    assert report["flag"] == "independence_assumption_retained"


def test_arm_abort_invalid_collapse_is_secondary():
    # invalid differs by arm but aborts are balanced: primary retained, secondary flags it
    report = arm_abort_independence([[5, 5, 0], [0, 5, 5]], ["R", "S-u"])
    assert report["secondary_arm_vs_invalid"]["collapse"]["table"] == [[0, 10], [5, 5]]
    assert report["flag"] == "independence_assumption_retained"  # driven by primary (aborts)


def test_from_contingency_object():
    contingency = {
        "abort_contingency_schema": 1,
        "arms": ["R", "D", "S-u"],
        "primary_test_input": "per_campaign",
        "per_campaign": {
            "columns": ["complete", "aborted", "invalid"],
            "matrix": [[4, 0, 0], [4, 0, 0], [4, 0, 0]],
            "unit": "campaign",
        },
        "per_event_reason": {"columns": [], "aborted": [], "invalid": [], "note": "descriptive"},
    }
    report = arm_abort_independence_from_contingency(contingency)
    assert report["flag"] == "not_assessable"
    assert report["arms"] == ["R", "D", "S-u"]


def test_monte_carlo_is_seed_reproducible():
    table = [[0, 10], [5, 5]]
    first = monte_carlo_independence(table, seed=7, resamples=3000)
    again = monte_carlo_independence(table, seed=7, resamples=3000)
    assert first["p_value"] == again["p_value"]
    # permutation p is near the exact 0.0325 for this table
    assert first["p_value"] < 0.15


def test_fisher_falls_back_to_monte_carlo_when_space_too_large():
    table = [[0, 10], [5, 5]]
    result = fisher_exact(table, max_exact_tables=1, seed=3)
    assert result["exact"] is False and result["test"] == "monte_carlo"

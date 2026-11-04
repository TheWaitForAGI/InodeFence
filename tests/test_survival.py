"""Survival roll-up for H-A T_first: KM, log-rank, A12, bootstrap, paired, zero-event.

Reference values for Kaplan-Meier, the log-rank test, and A12 are hand-computed in the
docstrings so the implementation is checked against arithmetic, not against itself.
"""

import pytest

from inodefence.evaluation.survival import (
    AbortPolicy,
    Observation,
    SeedRecord,
    a12,
    a12_first_faster,
    bootstrap_ci,
    chi_square_sf,
    kaplan_meier,
    km_median,
    logrank_test,
    observations_for_policy,
    paired_permutation_test,
    rule_of_three,
    seed_block_paired,
    seed_records_from_rows,
    sensitivity_arms,
    to_observation,
    wilcoxon_signed_rank,
    zero_event_summary,
)


def _obs(pairs):
    return [Observation(time=t, event=e) for t, e in pairs]


# --- Kaplan-Meier -----------------------------------------------------------------


def test_kaplan_meier_steps_and_median():
    # events at 2, 3, 5 with one censor at 4 (n=4):
    #   t=2: at risk 4, S = 1*(1-1/4) = 0.75
    #   t=3: at risk 3, S = 0.75*(1-1/3) = 0.5
    #   t=5: at risk 1 (the censor at 4 has left), S = 0.5*(1-1/1) = 0.0
    steps = kaplan_meier(_obs([(2, True), (3, True), (4, False), (5, True)]))
    assert [(s.time, s.at_risk, s.events) for s in steps] == [(2, 4, 1), (3, 3, 1), (5, 1, 1)]
    assert steps[0].survival == pytest.approx(0.75)
    assert steps[1].survival == pytest.approx(0.5)
    assert steps[2].survival == pytest.approx(0.0)
    assert km_median(steps) == 3


def test_kaplan_meier_tied_events_and_censored_median_is_none():
    # two events tied at 2 (n=3): t=2 at risk 3, S = 1 - 2/3 = 1/3
    steps = kaplan_meier(_obs([(2, True), (2, True), (5, False)]))
    assert len(steps) == 1 and steps[0].at_risk == 3 and steps[0].events == 2
    assert steps[0].survival == pytest.approx(1 / 3)
    assert km_median(steps) == 2
    # all censored -> no steps, no median
    censored = kaplan_meier(_obs([(10, False), (20, False)]))
    assert censored == []
    assert km_median(censored) is None


# --- chi-square tail --------------------------------------------------------------


def test_chi_square_sf_known_critical_values():
    assert chi_square_sf(0.0, 1) == 1.0
    assert chi_square_sf(3.841458820694124, 1) == pytest.approx(0.05, abs=1e-4)
    assert chi_square_sf(5.991464547107979, 2) == pytest.approx(0.05, abs=1e-4)
    assert chi_square_sf(11.344866730144373, 3) == pytest.approx(0.01, abs=1e-4)


# --- log-rank ---------------------------------------------------------------------


def test_logrank_two_arms_matches_hand_calculation():
    # arm A events {1,3}, arm B events {2,4}, no censoring.
    #   O_A = 2, E_A = 0.5 + 1/3 + 0.5 + 0 = 1.333...; dev = 0.666...
    #   V_AA = 0.25 + 2/9 + 0.25 = 0.7222...; chi^2 = dev^2 / V = 0.6153846
    result = logrank_test({"A": _obs([(1, True), (3, True)]), "B": _obs([(2, True), (4, True)])})
    assert result["degrees_of_freedom"] == 1
    assert result["observed_events"]["A"] == 2
    assert result["expected_events"]["A"] == pytest.approx(1.3333333, abs=1e-6)
    assert result["chi_square"] == pytest.approx(0.6153846, abs=1e-6)
    assert result["p_value"] == pytest.approx(0.4328, abs=1e-3)


def test_logrank_three_arms_identical_arms_is_near_zero():
    arm = _obs([(1, True), (2, True), (3, False)])
    result = logrank_test({"R": list(arm), "D": list(arm), "S": list(arm)})
    assert result["degrees_of_freedom"] == 2
    assert result["chi_square"] == pytest.approx(0.0, abs=1e-9)
    assert result["p_value"] == pytest.approx(1.0, abs=1e-9)


def test_logrank_rejects_single_arm_and_empty_arm():
    with pytest.raises(ValueError):
        logrank_test({"only": _obs([(1, True)])})
    with pytest.raises(ValueError):
        logrank_test({"A": _obs([(1, True)]), "B": []})


# --- Vargha-Delaney A12 -----------------------------------------------------------


def test_a12_raw_statistic_matches_hand_calculation():
    # a=[1,2,3], b=[2,4]: greater=1 (only 3>2), equal=1 (2==2); A = (1+0.5)/6 = 0.25
    assert a12([1, 2, 3], [2, 4]) == pytest.approx(0.25)
    assert a12([1], [2]) == 0.0
    assert a12([5], [5]) == 0.5


def test_a12_first_faster_orientation_and_censor_drop():
    # arm_a strictly smaller observed times -> faster -> A12 well above 0.5
    result = a12_first_faster(
        _obs([(1, True), (2, True), (3, True), (99, False)]),
        _obs([(2, True), (4, True)]),
    )
    assert result["a12_a_faster"] == pytest.approx(0.75)
    assert result["number_observed"] == {"a": 3, "b": 2}
    assert result["number_censored_dropped"] == {"a": 1, "b": 0}


def test_a12_first_faster_none_when_an_arm_has_no_event():
    result = a12_first_faster(_obs([(5, False)]), _obs([(2, True)]))
    assert result["a12_a_faster"] is None


# --- bootstrap --------------------------------------------------------------------


def test_bootstrap_ci_is_seed_reproducible_and_brackets_point():
    sample = [10, 12, 14, 16, 18, 20, 22, 24]
    mean = lambda xs: sum(xs) / len(xs)  # noqa: E731
    first = bootstrap_ci(mean, sample, seed=123, resamples=500)
    again = bootstrap_ci(mean, sample, seed=123, resamples=500)
    assert first["ci"] == again["ci"]
    assert first["point_estimate"] == pytest.approx(mean(sample))
    low, high = first["ci"]
    assert low <= mean(sample) <= high
    assert first["resamples_used"] == 500


def test_bootstrap_ci_rejects_empty_sample():
    with pytest.raises(ValueError):
        bootstrap_ci(lambda xs: sum(xs), [], seed=1)


# --- abort-censoring policies -----------------------------------------------------


def test_to_observation_across_policies():
    done = SeedRecord(1, 2000, "complete", None)
    assert to_observation(done, AbortPolicy.CENSOR_AT_ABORT) == Observation(2000, False)
    hit = SeedRecord(2, 2000, "abort", 300, abort_executions=500)
    assert to_observation(hit, AbortPolicy.EXCLUDE) == Observation(300, True)
    abort = SeedRecord(3, 2000, "abort", None, abort_executions=500)
    assert to_observation(abort, AbortPolicy.CENSOR_AT_ABORT) == Observation(500, False)
    assert to_observation(abort, AbortPolicy.CENSOR_AT_BUDGET) == Observation(2000, False)
    assert to_observation(abort, AbortPolicy.EXCLUDE) is None


def test_seed_record_validation():
    with pytest.raises(ValueError):
        SeedRecord(1, 2000, "complete", None, abort_executions=5)  # complete carries abort
    with pytest.raises(ValueError):
        SeedRecord(2, 2000, "abort", None, abort_executions=None)  # abort needs index
    with pytest.raises(ValueError):
        SeedRecord(3, 2000, "abort", 600, abort_executions=500)  # event after abort
    with pytest.raises(ValueError):
        SeedRecord(4, 2000, "weird", None)  # bad status


def test_sensitivity_arms_reports_each_policy():
    records_a = [
        SeedRecord(1, 2000, "complete", None),
        SeedRecord(2, 2000, "abort", None, abort_executions=400),
        SeedRecord(3, 2000, "complete", 500),
    ]
    records_b = [
        SeedRecord(1, 2000, "complete", 300),
        SeedRecord(2, 2000, "complete", None),
        SeedRecord(3, 2000, "abort", None, abort_executions=600),
    ]
    report = sensitivity_arms({"A": records_a, "B": records_b})
    assert set(report["policies"]) == {p.value for p in AbortPolicy}
    exclude = report["policies"][AbortPolicy.EXCLUDE.value]
    # under EXCLUDE the no-event aborts drop: A keeps seeds 1,3; B keeps seeds 1,2
    assert exclude["number_in_risk_set"] == {"A": 2, "B": 2}
    assert "logrank" in exclude


def test_observations_for_policy_excludes_unobserved_aborts():
    records = [
        SeedRecord(1, 100, "abort", None, abort_executions=50),
        SeedRecord(2, 100, "complete", 40),
    ]
    kept = observations_for_policy(records, AbortPolicy.EXCLUDE)
    assert kept == [Observation(40, True)]


# --- paired seed-block ------------------------------------------------------------


def test_wilcoxon_signed_rank_matches_hand_calculation():
    # diffs [1,2,-3,4,5]: ranks 1..5, W+ = 1+2+4+5 = 12; exact two-sided p = 10/32 = 0.3125
    result = wilcoxon_signed_rank([1, 2, -3, 4, 5])
    assert result["statistic_w_plus"] == pytest.approx(12.0)
    assert result["p_value"] == pytest.approx(0.3125)
    assert result["method"].startswith("exact")


def test_wilcoxon_drops_zero_differences():
    result = wilcoxon_signed_rank([0, 0, 0])
    assert result["number_nonzero"] == 0 and result["p_value"] is None


def test_paired_permutation_exact_small_sample():
    # same diffs: |sum|=9, patterns with |signed|>=9 number 10 of 32 -> 0.3125
    result = paired_permutation_test([1, 2, -3, 4, 5], seed=0)
    assert result["p_value"] == pytest.approx(0.3125)
    assert result["method"].startswith("exact")


def test_seed_block_paired_drops_censored_pairs():
    arm_a = {
        1: SeedRecord(1, 2000, "complete", 300),
        2: SeedRecord(2, 2000, "complete", 800),
        3: SeedRecord(3, 2000, "complete", None),  # censored -> drop pair
    }
    arm_b = {
        1: SeedRecord(1, 2000, "complete", 500),
        2: SeedRecord(2, 2000, "complete", 400),
        3: SeedRecord(3, 2000, "complete", 100),
    }
    result = seed_block_paired(arm_a, arm_b, seed=7)
    assert result["number_shared_seeds"] == 3
    assert result["number_pairs_both_observed"] == 2
    assert result["dropped_seeds"] == [3]
    # differences: seed1 300-500=-200, seed2 800-400=+400
    assert "wilcoxon_signed_rank" in result and "paired_permutation" in result


# --- zero-event fallback ----------------------------------------------------------


def test_rule_of_three_and_zero_event_summary():
    assert rule_of_three(30) == pytest.approx(0.1)
    summary = zero_event_summary({"R": _obs([(2000, False)] * 19), "S": _obs([(2000, False)] * 17)})
    assert summary["label"] == "exploratory"
    assert summary["arms"]["R"]["rule_of_three_upper_95"] == pytest.approx(3 / 19)
    assert summary["arms"]["S"]["number_complete_null_campaigns"] == 17


def test_zero_event_summary_rejects_observed_event():
    with pytest.raises(ValueError):
        zero_event_summary({"R": _obs([(5, True)])})


# --- runner-output adapter --------------------------------------------------------


def test_seed_records_from_rows_default_and_custom_field_map():
    rows = [
        {"seed": 1, "budget": 2000, "status": "complete", "first_event_executions": 300},
        {"seed": 2, "budget": 2000, "status": "abort", "abort_executions": 450},
    ]
    records = seed_records_from_rows(rows)
    assert records[0] == SeedRecord(1, 2000, "complete", 300)
    assert records[1] == SeedRecord(2, 2000, "abort", None, abort_executions=450)
    custom = seed_records_from_rows(
        [{"s": 9, "n": 100, "state": "complete", "t_first": 10}],
        field_map={
            "seed": "s",
            "budget": "n",
            "status": "state",
            "first_event_executions": "t_first",
        },
    )
    assert custom[0] == SeedRecord(9, 100, "complete", 10)


def test_holm_adjust_reference():
    from inodefence.evaluation.survival import holm_adjust

    # [0.01, 0.04], m=2: [2*0.01, max(0.02, 1*0.04)] = [0.02, 0.04]
    assert holm_adjust([0.01, 0.04]) == pytest.approx([0.02, 0.04])
    assert holm_adjust([0.04, 0.01]) == pytest.approx([0.04, 0.02])  # input order preserved
    assert holm_adjust([0.5, 0.6]) == pytest.approx([1.0, 1.0])  # monotone + capped
    assert holm_adjust([0.03]) == pytest.approx([0.03])
    assert holm_adjust([]) == []


def test_seed_block_logrank_permutation_no_events_is_p1():
    from inodefence.evaluation.survival import seed_block_logrank_permutation

    blocks = [(Observation(100, False), Observation(100, False)) for _ in range(3)]
    r = seed_block_logrank_permutation(blocks)
    assert r["exact"] is True and r["total_events"] == 0
    assert r["observed_chi_square"] == 0.0 and r["p_value"] == 1.0


def test_seed_block_logrank_permutation_exact_separated():
    from inodefence.evaluation.survival import seed_block_logrank_permutation

    # 4 seeds, arm_a hits@10 / arm_b censored@100: observed is max separation; only the all-a
    # and all-b label assignments tie it -> p = 2/16 = 0.125.
    blocks = [(Observation(10, True), Observation(100, False)) for _ in range(4)]
    r = seed_block_logrank_permutation(blocks)
    assert r["exact"] is True and r["number_permutations"] == 16
    assert r["total_events"] == 4 and r["observed_chi_square"] > 0
    assert r["p_value"] == pytest.approx(0.125)


def test_seed_block_logrank_permutation_mc_seed_reproducible():
    from inodefence.evaluation.survival import seed_block_logrank_permutation

    blocks = [(Observation(10, True), Observation(100, False)) for _ in range(5)]
    a = seed_block_logrank_permutation(blocks, seed=7, max_exact_blocks=3, resamples=4000)
    b = seed_block_logrank_permutation(blocks, seed=7, max_exact_blocks=3, resamples=4000)
    assert a["exact"] is False and "p_value_mc_ci95" in a
    assert a["p_value"] == b["p_value"]  # seed-fixed: reproducible


def test_seed_block_logrank_permutation_empty():
    from inodefence.evaluation.survival import seed_block_logrank_permutation

    r = seed_block_logrank_permutation([])
    assert r["p_value"] is None and r["number_blocks"] == 0


def test_seed_block_logrank_direction_sign():
    from inodefence.evaluation.survival import seed_block_logrank_permutation

    fast = [(Observation(10, True), Observation(100, False))] * 3  # arm a faster
    slow = [(Observation(100, False), Observation(10, True))] * 3  # arm b faster
    rf = seed_block_logrank_permutation(fast)
    rs = seed_block_logrank_permutation(slow)
    # identical two-sided p and chi-square, opposite direction sign
    assert rf["p_value"] == rs["p_value"]
    assert rf["observed_chi_square"] == pytest.approx(rs["observed_chi_square"])
    assert rf["observed_minus_expected_a"] > 0  # a faster
    assert rs["observed_minus_expected_a"] < 0  # b faster
    none = seed_block_logrank_permutation([(Observation(100, False), Observation(100, False))] * 2)
    assert none["observed_minus_expected_a"] == 0.0

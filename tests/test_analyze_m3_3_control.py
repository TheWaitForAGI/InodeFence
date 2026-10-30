"""The M3.3 control roll-up maps the runtime summary to an honest right-censored view."""

import pytest
from scripts.analyze_m3_3_control import (
    analyze,
    build_outcomes,
    matched_contrast,
    merge_summaries,
)

_HIT = "step oracle.C1 && feedback.contract_violated"

# Matched-contrast fixtures: two arms on the SAME three seeds at the same budget.
_A1_SHARED = {
    "task": "M3.3 powered matched (A1)",
    "arm": {"label": "A1"},
    "budget": 2000,
    "version": "7.5.2",
    "hit_criterion": _HIT,
    "seeds": [100, 101, 102],
    "completed_full_budget": [100, 101, 102],
    "right_censored_abort_seeds": [],
    "seeds_with_clean_exact_c1": [],
    "cells": [
        {"seed": seed, "clean_exact_c1": 0, "status": "completed"} for seed in (100, 101, 102)
    ],
}

# A3full: s101 is a complete-campaign hit; s102 observed a clean C1 BEFORE a fail-closed
# abort (an observed trigger, not a complete hit -- it stays out of seeds_with_clean_exact_c1).
_A3FULL_SHARED = {
    "task": "M3.3 powered matched (A3full)",
    "arm": {"label": "A3full"},
    "budget": 2000,
    "version": "7.5.2",
    "hit_criterion": _HIT,
    "seeds": [100, 101, 102],
    "completed_full_budget": [100, 101],
    "right_censored_abort_seeds": [102],
    "seeds_with_clean_exact_c1": [101],
    "cells": [
        {"seed": 100, "clean_exact_c1": 0, "status": "completed"},
        {"seed": 101, "clean_exact_c1": 3, "clean_exact_c1_first_step": 300, "status": "completed"},
        {
            "seed": 102,
            "clean_exact_c1": 21,
            "clean_exact_c1_first_step": 264,
            "censor_step": 416,
            "status": "aborted_fail_closed_obs_integrity (right-censored)",
        },
    ],
}

_BATCH1 = {
    "task": "M3.3 random control (A1)",
    "arm": {"label": "A1"},
    "budget": 2000,
    "version": "7.5.2",
    "seeds": [11, 66, 67, 68, 69, 70],
    "observed_executions": 10521,
    "clean_exact_c1_total": 0,
    "seeds_with_clean_exact_c1": [],
    "completed_full_budget": [67, 69, 70],
    "right_censored_abort_seeds": [11, 66, 68],
    "cells": [{"seed": seed} for seed in (11, 66, 67, 68, 69, 70)],
}

_BATCH2 = {
    "task": "M3.3 random control (A1) BATCH 2",
    "arm": {"label": "A1"},
    "budget": 2000,
    "version": "7.5.2",
    "seeds": [71, 72, 73, 74, 75, 76],
    "observed_executions": 9642,
    "clean_exact_c1_total": 0,
    "seeds_with_clean_exact_c1": [],
    "completed_full_budget": [71, 72, 73, 76],
    "right_censored_abort_seeds": [74, 75],
    "cells": [{"seed": seed} for seed in (71, 72, 73, 74, 75, 76)],
}


def test_build_outcomes_splits_complete_and_abort():
    outcomes = {outcome.seed: outcome for outcome in build_outcomes(_BATCH1)}
    assert {s for s, o in outcomes.items() if o.complete} == {67, 69, 70}
    assert {s for s, o in outcomes.items() if not o.complete} == {11, 66, 68}
    assert all(not outcome.hit for outcome in outcomes.values())
    assert all(outcome.budget == 2000 for outcome in outcomes.values())


def test_analyze_batch1_is_zero_over_three_complete_with_aborts_separate():
    result = analyze(_BATCH1)
    rollup = result["rollup"]
    assert rollup["number_complete_campaigns"] == 3
    assert rollup["number_observed_target"] == 0
    assert rollup["observed_proportion"]["value"] == 0.0
    low, high = rollup["observed_proportion"]["wilson_95_ci"]
    assert low == pytest.approx(0.0, abs=1e-9) and high > 0.3  # wide small-sample interval
    assert rollup["number_incomplete_excluded"] == 3
    assert set(rollup["incomplete_seeds"]) == {11, 66, 68}
    assert rollup["number_right_censored"] == 3  # the complete no-hit campaigns
    assert "EN-008" in result["framing"] and "causal contrast" in result["framing"]
    assert result["runtime_determination"]["clean_exact_c1_total"] == 0


def test_hit_seed_requires_first_hit_index():
    with_hit = {
        **_BATCH1,
        "seeds": [67],
        "completed_full_budget": [67],
        "right_censored_abort_seeds": [],
        "seeds_with_clean_exact_c1": [67],
        "cells": [{"seed": 67, "clean_exact_c1_first_step": 264}],
    }
    result = analyze(with_hit)
    assert result["rollup"]["number_observed_target"] == 1
    assert result["rollup"]["first_hit_executions_observed_only"]["values"] == [264]

    missing_index = {**with_hit, "cells": [{"seed": 67}]}
    with pytest.raises(ValueError):
        build_outcomes(missing_index)


def test_merge_summaries_pools_disjoint_batches_and_tightens_interval():
    merged = merge_summaries([_BATCH1, _BATCH2])
    assert merged["seeds"] == [11, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76]
    assert merged["completed_full_budget"] == [67, 69, 70, 71, 72, 73, 76]
    assert merged["right_censored_abort_seeds"] == [11, 66, 68, 74, 75]
    assert merged["observed_executions"] == 20163
    assert merged["clean_exact_c1_total"] == 0
    assert [batch["observed_executions"] for batch in merged["pooled_batches"]] == [10521, 9642]

    combined = analyze(merged)["rollup"]
    assert combined["number_complete_campaigns"] == 7
    assert combined["number_observed_target"] == 0
    assert combined["number_incomplete_excluded"] == 5
    assert set(combined["incomplete_seeds"]) == {11, 66, 68, 74, 75}
    assert combined["number_right_censored"] == 7
    # pooling batch 2 tightens the small-sample interval versus batch 1 alone (0/3)
    batch1_high = analyze(_BATCH1)["rollup"]["observed_proportion"]["wilson_95_ci"][1]
    combined_high = combined["observed_proportion"]["wilson_95_ci"][1]
    assert combined_high < batch1_high


def test_merge_summaries_rejects_overlapping_seeds():
    with pytest.raises(ValueError):
        merge_summaries([_BATCH1, {**_BATCH2, "seeds": [70, 71, 72, 73, 74, 75]}])


def test_merge_summaries_rejects_unlike_batches():
    with pytest.raises(ValueError):
        merge_summaries([_BATCH1, {**_BATCH2, "budget": 1500}])


def test_matched_contrast_pairs_arms_and_keeps_rate_and_observed_trigger_apart():
    result = matched_contrast(_A1_SHARED, _A3FULL_SHARED)
    assert result["arms"] == {"arm_a": "A1", "arm_b": "A3full"}
    assert result["shared_seeds"] == [100, 101, 102]

    # Each arm's rate is the committed right-censored complete-campaign roll-up.
    a = result["arm_a_shared"]
    b = result["arm_b_shared"]
    assert a["complete_campaigns"] == 3 and a["complete_campaign_hits"] == 0
    assert a["complete_hit_rate"] == 0.0
    assert a["number_observed_trigger_seeds"] == 0
    # A3full: one complete-campaign hit (s101); s102's pre-abort C1 is an observed trigger,
    # counted as a trigger but NOT a complete-campaign hit (it fail-closed-aborted).
    assert b["complete_campaigns"] == 2 and b["complete_campaign_hits"] == 1
    assert b["complete_campaign_hit_seeds"] == [101]
    assert b["observed_trigger_seeds"] == [101, 102]
    assert b["total_observed_clean_exact_c1"] == 24

    # The arm_b roll-up excludes the aborted seed from the denominator and never counts it a hit.
    assert result["arm_b_rollup"]["number_complete_campaigns"] == 2
    assert result["arm_b_rollup"]["number_observed_target"] == 1
    assert result["arm_b_rollup"]["first_hit_executions_observed_only"]["values"] == [300]
    assert 102 in result["arm_b_rollup"]["incomplete_seeds"]

    # Matched discordance: both of A3full's triggers are seeds where A1 observed none.
    assert result["matched_discordant"]["arm_b_only_observed_trigger_seeds"] == [101, 102]
    assert result["matched_discordant"]["arm_a_only_observed_trigger_seeds"] == []
    # 0/3 vs 1/2 at this sample size: wide Wilson intervals overlap, so NO rate-superiority claim.
    assert result["complete_hit_wilson_intervals_separate"] is False
    assert "EN-008" in result["framing"]

    # Per-seed matched table marks s102 as an observed trigger on an incomplete campaign.
    row102 = next(row for row in result["per_seed"] if row["seed"] == 102)
    assert row102["arm_b"]["observed_clean_exact_c1"] == 21
    assert row102["arm_b"]["complete"] is False and row102["arm_b"]["complete_hit"] is False
    assert row102["arm_a"]["observed_clean_exact_c1"] == 0


def test_matched_contrast_separates_when_intervals_do_not_overlap():
    # A hypothetical powered arm_b: 12/12 complete hits vs 0/12 complete — intervals separate.
    seeds = list(range(100, 112))
    arm_a = {
        **_A1_SHARED,
        "seeds": seeds,
        "completed_full_budget": seeds,
        "seeds_with_clean_exact_c1": [],
        "cells": [{"seed": s, "clean_exact_c1": 0} for s in seeds],
    }
    arm_b = {
        **_A3FULL_SHARED,
        "seeds": seeds,
        "completed_full_budget": seeds,
        "right_censored_abort_seeds": [],
        "seeds_with_clean_exact_c1": seeds,
        "cells": [
            {"seed": s, "clean_exact_c1": 1, "clean_exact_c1_first_step": 100} for s in seeds
        ],
    }
    result = matched_contrast(arm_a, arm_b)
    assert result["arm_a_shared"]["complete_hit_rate"] == 0.0
    assert result["arm_b_shared"]["complete_hit_rate"] == 1.0
    assert result["complete_hit_wilson_intervals_separate"] is True


def test_matched_contrast_rejects_unlike_arms():
    with pytest.raises(ValueError):
        matched_contrast(_A1_SHARED, {**_A3FULL_SHARED, "budget": 1500})


def test_matched_contrast_rejects_same_arm_label():
    with pytest.raises(ValueError):
        matched_contrast(_A1_SHARED, {**_A3FULL_SHARED, "arm": {"label": "A1"}})

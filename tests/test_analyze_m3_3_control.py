"""The M3.3 control roll-up maps the runtime summary to an honest right-censored view."""

import pytest
from scripts.analyze_m3_3_control import analyze, build_outcomes, merge_summaries

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

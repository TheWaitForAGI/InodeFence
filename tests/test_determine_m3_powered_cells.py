"""The M3 powered-run determiner turns raw cells into the eval layer's per-seed facts."""

import pytest
from scripts.determine_m3_powered_cells import (
    ARM_META,
    build_arm_summary,
    classify_cell,
)


def _step(c0: bool = False, c1: bool = False, c2: bool = False, violated: bool = False) -> dict:
    return {"oracle": {"C0": c0, "C1": c1, "C2": c2}, "feedback": {"contract_violated": violated}}


def test_classify_complete_cell_counts_clean_c1_and_1based_first_step() -> None:
    # Three steps; the second is a clean exact C1 (oracle.C1 AND contract_violated).
    steps = [_step(), _step(c1=True, violated=True), _step(c1=True, violated=True)]
    cell = classify_cell(101, "m3p-752-A3full-s101", "evidence.json", aborted=False, steps=steps)
    assert cell["status"].startswith("completed")
    assert cell["observed_steps"] == 3
    assert cell["censor_step"] is None
    assert cell["clean_exact_c1"] == 2
    assert cell["clean_exact_c1_first_step"] == 2  # 1-based ordinal of the first hit
    assert cell["c1_steps"] == 2


def test_classify_requires_both_oracle_c1_and_contract_violated() -> None:
    # oracle.C1 without a contract violation is NOT a clean exact C1.
    steps = [_step(c1=True, violated=False), _step(c1=False, violated=True)]
    cell = classify_cell(1, "r", "e.json", aborted=False, steps=steps)
    assert cell["c1_steps"] == 1
    assert cell["clean_exact_c1"] == 0
    assert cell["clean_exact_c1_first_step"] is None


def test_classify_abort_cell_marks_censor_step() -> None:
    steps = [_step(), _step(c0=True)]
    cell = classify_cell(104, "r", "e.json", aborted=True, steps=steps)
    assert cell["status"].startswith("aborted")
    assert cell["censor_step"] == 2
    assert cell["c0_steps"] == 1


def test_build_arm_summary_hits_are_complete_only() -> None:
    # s101 completes with a clean C1 (a hit); s118 sees a clean C1 then aborts (observed
    # trigger only); s100 completes with none.
    cells = [
        classify_cell(100, "r", "e.json", aborted=False, steps=[_step()]),
        classify_cell(101, "r", "e.json", aborted=False, steps=[_step(c1=True, violated=True)]),
        classify_cell(118, "r", "e.json", aborted=True, steps=[_step(c1=True, violated=True)]),
    ]
    summary = build_arm_summary("A3full", [100, 101, 118], cells)
    assert summary["arm"] == ARM_META["A3full"]
    assert summary["completed_full_budget"] == [100, 101]
    assert summary["right_censored_abort_seeds"] == [118]
    # complete-only: s118's pre-abort clean C1 is an observed trigger, not a complete hit.
    assert summary["seeds_with_clean_exact_c1"] == [101]
    assert summary["clean_exact_c1_total"] == 2  # tallied across all cells
    assert summary["hit_criterion"]


def test_build_arm_summary_rejects_unknown_arm() -> None:
    cell = classify_cell(1, "r", "e.json", aborted=False, steps=[_step()])
    with pytest.raises(ValueError, match="unknown arm"):
        build_arm_summary("ZZZ", [1], [cell])

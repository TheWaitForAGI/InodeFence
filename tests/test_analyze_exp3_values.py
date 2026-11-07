"""PR-D: values the registered tables read: I, abort policies, U_viol, dense, lost steps, damage."""

import json
from typing import Any

import pytest
from scripts.analyze_exp0 import (
    _DEFAULT_FIELD_MAP,
    build_multitarget_report,
    build_report,
    cell_from_row,
)

from inodefence.evaluation.cell_completeness import WATCHDOG_ABORT_REASON
from inodefence.evaluation.survival import Observation, informative_blocks

FIELD_MAP = dict(_DEFAULT_FIELD_MAP)
HIT = {"t_first": 20, "t_first_event": 1, "first_c1": 20, "hit_steps": 1}
ABORT = {
    "aborted": True,
    "complete": False,
    "abort_reason": "broker",
    "executions_completed": 50,
    "t_first": 50,
}


def _record(arm: str, seed: int, **over: Any) -> dict[str, Any]:
    return {
        "random_seed": seed,
        "arm": arm,
        "execution_budget": 200,
        "executions_completed": 200,
        "complete": True,
        "aborted": False,
        "abort_reason": None,
        "t_first": 200,
        "t_first_event": 0,
        "hit_steps": 0,
        "first_c0": None,
        "first_c1": None,
        "first_c2": None,
        "boundary_attempt_keys": 0,
        "rejected_executions": 0,
        "observation_failures": 0,
        "u_viol": 0,
        **over,
    }


ENTRY = {"target_id": "h", "role": "holdout", "hypothesis": "H-A", "summary": "x"}


def _cell(arm: str, seed: int, *, wrapper: dict[str, Any] | None = None, **over: Any) -> Any:
    row = {"summary": _record(arm, seed, **over), **(wrapper or {})}
    return cell_from_row(row, FIELD_MAP, entry=ENTRY)


def _damaged(arm: str, seed: int, **prefix: Any) -> Any:
    row = {
        "summary": None,
        "config_nonconformant": True,
        "invalid_reason": "ReportFormatError: record-inconsistent: no-exit-record",
        "record_inconsistent_prefix": prefix,
    }
    return cell_from_row(row, FIELD_MAP, entry={**ENTRY, "arm": arm, "seed": seed})


def _plan(*arms_b: str, threshold: int = 7) -> dict[str, Any]:
    return {
        "event_threshold": threshold,
        "confirmatory_contrasts": [
            {
                "order": order,
                "target_id": "h",
                "arm_a": "S-u",
                "arm_b": arm,
                "contrast": f"S-u-vs-{arm}",
            }
            for order, arm in enumerate(arms_b, start=1)
        ],
    }


def _report(cells: list[Any], *arms_b: str, threshold: int = 7) -> dict[str, Any]:
    return build_multitarget_report(
        cells, analysis_plan=_plan(*arms_b, threshold=threshold), field_map=FIELD_MAP, sources=["t"]
    )


def _contrast(report: dict[str, Any], index: int = 0) -> dict[str, Any]:
    return report["confirmatory"]["contrasts"][index]


def _pairs(seeds: range, a: dict[str, Any], b: dict[str, Any]) -> list[Any]:
    return [cell for s in seeds for cell in (_cell("S-u", s, **a), _cell("R", s, **b))]


def test_informative_blocks_counts_blocks_whose_arms_differ() -> None:
    same = (Observation(5, True), Observation(5, True))
    other = (Observation(5, True), Observation(6, True))
    censored = (Observation(5, True), Observation(5, False))
    assert informative_blocks([]) == 0
    assert informative_blocks([same, same]) == 0
    assert informative_blocks([same, other, censored]) == 2


def test_underpowered_reads_informative_blocks_not_total_events() -> None:
    # Many events, all in blocks where both arms agree: I is 0 though E is large.
    report = _report(_pairs(range(1, 11), HIT, HIT), "R")
    contrast = _contrast(report)
    assert (contrast["total_events"], contrast["informative_blocks"]) == (20, 0)
    assert contrast["underpowered"] is True


@pytest.mark.parametrize(("blocks", "underpowered"), [(6, True), (7, False)])
def test_the_threshold_is_exact_at_seven_informative_blocks(
    blocks: int, underpowered: bool
) -> None:
    contrast = _contrast(_report(_pairs(range(1, blocks + 1), HIT, {}), "R"))
    assert contrast["informative_blocks"] == blocks
    assert contrast["underpowered"] is underpowered
    assert ("underpowered_note" in contrast) is underpowered


def test_no_report_text_names_a_verdict_scenario() -> None:
    text = json.dumps(_report(_pairs(range(1, 4), {}, {}), "R"), ensure_ascii=False)
    assert "scenario" not in text


def test_zero_events_give_a_per_arm_bound_and_events_give_none() -> None:
    zero = _contrast(_report(_pairs(range(1, 7), {}, {}), "R"))
    assert zero["total_events"] == 0
    bound = zero["zero_event_bound"]
    assert bound["S-u"] == {
        "number_complete": 6,
        "number_campaigns": 6,
        "rule_of_three_upper_95": pytest.approx(0.5),  # 3/6 per arm, not 3/12 over both
    }
    assert bound["R"]["rule_of_three_upper_95"] == pytest.approx(0.5)
    with_events = _contrast(_report(_pairs(range(1, 7), HIT, {}), "R"))
    assert "zero_event_bound" not in with_events


def test_zero_event_bound_counts_only_complete_as_complete() -> None:
    cells = [*_pairs(range(1, 4), {}, {}), _cell("S-u", 4, **ABORT), _cell("R", 4)]
    bound = _contrast(_report(cells, "R"))["zero_event_bound"]
    assert bound["S-u"]["number_complete"] == 3 and bound["S-u"]["number_campaigns"] == 4


def test_no_paired_block_stays_undefined() -> None:
    contrast = _contrast(_report([_cell("S-u", 1, **HIT)], "R"))
    assert contrast["number_seed_blocks"] == 0
    assert contrast["campaign_unit_rule_of_three_upper95"] is None
    assert contrast["u_viol_direction"] == "없음"


def test_censor_at_abort_equals_the_primary_read() -> None:
    cells = [*_pairs(range(1, 6), HIT, {}), _cell("S-u", 6, **ABORT), _cell("R", 6, **HIT)]
    contrast = _contrast(_report(cells, "R"))
    primary = contrast["abort_policy_results"]["censor-at-abort"]
    assert primary["raw_p"] == contrast["permutation"]["p_value"]
    assert primary["holm_adjusted_p"] == contrast["holm_adjusted_p"]
    assert primary["reject_at_alpha"] == contrast["reject_at_alpha"]
    assert primary["informative_blocks"] == contrast["informative_blocks"]
    assert primary["number_seed_blocks"] == contrast["number_seed_blocks"]


def test_each_abort_policy_has_its_own_blocks_and_informative_count() -> None:
    cells = [*_pairs(range(1, 6), HIT, {}), _cell("S-u", 6, **ABORT), _cell("R", 6)]
    policies = _contrast(_report(cells, "R"))["abort_policy_results"]
    assert set(policies) == {"censor-at-abort", "censor-at-budget", "exclude"}
    # Exclude drops the aborted cell, so its whole block leaves this policy only.
    assert policies["exclude"]["number_seed_blocks"] == 5
    assert policies["censor-at-abort"]["number_seed_blocks"] == 6
    # At the budget the aborted S-u cell equals its R partner: the block informs nothing.
    assert policies["censor-at-budget"]["informative_blocks"] == 5
    assert policies["censor-at-abort"]["informative_blocks"] == 6


def test_each_policy_has_its_own_blocks_and_holm_family() -> None:
    # Every S-u cell hits, except aborted cells that only the policies treat differently.
    cells = [*_pairs(range(1, 8), HIT, {})]
    cells += [_cell("D", s) for s in range(1, 8)]
    for seed in range(8, 13):
        cells += [_cell("S-u", seed, **ABORT), _cell("R", seed), _cell("D", seed)]
    report = _report(cells, "R", "D")
    first, second = _contrast(report, 0), _contrast(report, 1)
    for name in ("exclude", "censor-at-budget", "censor-at-abort"):
        raw = first["abort_policy_results"][name]["raw_p"]
        adjusted = first["abort_policy_results"][name]["holm_adjusted_p"]
        assert adjusted == pytest.approx(min(1.0, raw * 2))  # two equal members in the family
        assert second["abort_policy_results"][name]["raw_p"] == pytest.approx(raw)
    exclude = first["abort_policy_results"]["exclude"]
    budget = first["abort_policy_results"]["censor-at-budget"]
    assert exclude["reject_at_alpha"] is True  # 7 informative blocks: p = 2/128
    assert exclude["number_seed_blocks"] == 7
    assert budget["number_seed_blocks"] == 12


def test_values_only_no_verdict_field() -> None:
    contrast = _contrast(_report(_pairs(range(1, 8), HIT, {}), "R"))
    for key in ("verdict", "judgment", "decision", "scenario"):
        assert key not in contrast


@pytest.mark.parametrize(
    ("su", "other", "direction"),
    [({"u_viol": 3}, {"u_viol": 1}, "S-u"), ({"u_viol": 1}, {"u_viol": 3}, "R"), ({}, {}, "동률")],
)
def test_u_viol_direction_reads_the_arm_means(su: dict, other: dict, direction: str) -> None:
    contrast = _contrast(_report(_pairs(range(1, 4), su, other), "R"))
    assert contrast["u_viol_direction"] == direction
    assert contrast["u_viol_mean_a"] == su.get("u_viol", 0)
    assert contrast["u_viol_mean_b"] == other.get("u_viol", 0)


def test_direction_note_names_only_which_arm_is_faster() -> None:
    note = _contrast(_report(_pairs(range(1, 4), HIT, {}), "R"))["direction_note"]
    assert "faster" in note and "scenario" not in note and "acceleration" not in note


def test_invalid_blocks_excluded_are_counted_per_contrast() -> None:
    cells = [
        *_pairs(range(1, 4), HIT, {}),
        *(_cell("D", s) for s in (1, 2)),
        _damaged("D", 3, steps=0, t_first=0, t_first_event=0),
    ]
    report = _report(cells, "R", "D")
    assert _contrast(report, 0)["number_blocks_invalid_excluded"] == 0
    assert _contrast(report, 1)["number_blocks_invalid_excluded"] == 1
    assert _contrast(report, 1)["number_seed_blocks"] == 2


def _detail(*keys: str, kinds: dict[str, int] | None = None, ineligible: int = 0) -> dict[str, Any]:
    return {
        "boundary_keys": list(keys),
        "observation_failures_by_kind": kinds or {},
        "feedback_ineligible_steps": ineligible,
        "recorded_steps": 200,
        "abort_observed_present": False,
    }


def test_dense_values_are_a_union_a_median_and_per_thousand() -> None:
    cells = [
        _cell(
            "S-u",
            1,
            boundary_attempt_keys=2,
            wrapper={"dense_detail": _detail("a", "b", kinds={"malformed": 2}, ineligible=10)},
        ),
        _cell(
            "S-u",
            2,
            boundary_attempt_keys=2,
            wrapper={"dense_detail": _detail("b", "c", kinds={"malformed": 1, "gap": 1})},
        ),
        _cell(
            "S-u",
            3,
            boundary_attempt_keys=8,
            wrapper={"dense_detail": _detail("a", ineligible=30)},
        ),
    ]
    arm = _report(cells, "R")["by_target"]["h"]["dense_signals_registered"]["by_arm"]["S-u"]
    assert arm["unique_boundary_keys_in_arm"] == 3  # the union, while the cell sum is 12
    assert arm["new_boundary_keys_per_cell"] == {"mean": 4.0, "median": 2}
    assert arm["recorded_steps"] == 600
    assert arm["observation_failures_by_kind"] == {
        "gap": {"total": 1, "per_1000_steps": pytest.approx(1 / 600 * 1000)},
        "malformed": {"total": 3, "per_1000_steps": pytest.approx(5.0)},
    }
    assert arm["feedback_ineligible_ratio"]["value"] == pytest.approx(40 / 600)


def test_dense_table_is_absent_when_a_cell_lacks_the_detail() -> None:
    cells = [_cell("S-u", 1, wrapper={"dense_detail": _detail("a")}), _cell("R", 1)]
    assert "dense_signals_registered" not in _report(cells, "R")["by_target"]["h"]


def test_the_flat_report_gets_none_of_these_keys() -> None:
    cell = _cell("S-u", 1, wrapper={"dense_detail": _detail("a")})
    report = build_report([cell], field_map=FIELD_MAP, sources=["t"])
    text = json.dumps(report, ensure_ascii=False)
    for key in ("dense_signals_registered", "number_abort_before_event", "unknown_outcome_steps"):
        assert key not in text


def test_abort_details_split_before_event_and_watchdog() -> None:
    cells = [
        _cell("S-u", 1, **ABORT),
        _cell("S-u", 2, **{**ABORT, "t_first": 20, "t_first_event": 1, "first_c1": 20}),
        _cell("S-u", 3, **{**ABORT, "abort_reason": WATCHDOG_ABORT_REASON}),
        _cell("R", 1),
    ]
    by_arm = _report(cells, "R")["by_target"]["h"]["item1_aborts"]["by_arm"]
    assert by_arm["S-u"]["number_abort_before_event"] == 2
    assert by_arm["S-u"]["number_watchdog"] == 1
    assert by_arm["R"]["number_abort_before_event"] == 0


def test_an_arm_with_only_invalid_cells_has_zero_aborts_not_a_missing_value() -> None:
    cells = [_cell("S-u", 1), _damaged("R", 1, steps=0, t_first=0, t_first_event=0)]
    by_arm = _report(cells, "R")["by_target"]["h"]["item1_aborts"]["by_arm"]
    assert by_arm["R"]["number_abort_before_event"] == 0


def test_unknown_outcome_steps_are_counted_and_never_events() -> None:
    lost = {**_detail(), "abort_observed_present": True}
    cells = [
        _cell("S-u", 1, wrapper={"dense_detail": lost}, **ABORT),
        _cell("R", 1, wrapper={"unknown_outcome_steps": 1}, **ABORT),
    ]
    report = _report(cells, "R")
    assert report["unknown_outcome_steps"] == {
        "lost_after_execution_lower_bound": 1,
        "watchdog_cut_line": 1,
    }
    assert _contrast(report)["total_events"] == 0


def test_no_damage_says_so_and_adds_nothing() -> None:
    report = _report(_pairs(range(1, 4), HIT, {}), "R")
    assert report["record_inconsistent_sensitivity"] == {
        "number_inconsistent_cells": 0,
        "summary": "어긋남 없음",
    }
    assert "record_inconsistent_sensitivity" not in _contrast(report)


def test_damage_sensitivity_trusts_the_prefix_and_says_when_the_answer_moves() -> None:
    # Seven clean blocks reject; the damaged block's prefix adds an R event earlier than S-u's.
    cells = _pairs(range(1, 7), HIT, {})
    cells += [_cell("S-u", 7), _damaged("R", 7, steps=5, t_first=5, t_first_event=1)]
    report = _report(cells, "R", threshold=1)
    contrast = _contrast(report)
    assert contrast["number_seed_blocks"] == 6
    sensitivity = contrast["record_inconsistent_sensitivity"]
    assert sensitivity["number_seed_blocks"] == 7
    assert sensitivity["total_events"] == 7  # the event inside the prefix stays an event
    assert report["record_inconsistent_sensitivity"]["number_inconsistent_cells"] == 1
    assert "어긋남 1셀" in report["record_inconsistent_sensitivity"]["summary"]


def test_a_damaged_cell_with_no_prefix_stays_out_of_the_sensitivity() -> None:
    cells = _pairs(range(1, 4), HIT, {})
    cells += [_cell("S-u", 4), _damaged("R", 4, steps=0, t_first=0, t_first_event=0)]
    sensitivity = _contrast(_report(cells, "R"))["record_inconsistent_sensitivity"]
    assert sensitivity["number_seed_blocks"] == 3


def test_damage_that_moves_the_rejection_is_named() -> None:
    # S-u wins six clean blocks and one rejecting seventh; the damage flips nothing alone, so give
    # the rejection enough blocks and let the prefix blocks run the other way.
    cells = _pairs(range(1, 9), HIT, {})  # p = 2/256: rejects
    for seed in range(9, 19):
        cells += [_cell("S-u", seed), _damaged("R", seed, steps=5, t_first=5, t_first_event=1)]
    report = _report(cells, "R", threshold=1)
    assert _contrast(report)["reject_at_alpha"] is True
    assert _contrast(report)["record_inconsistent_sensitivity"]["reject_at_alpha"] is False
    assert "기록 손상 가정에 좌우됨" in report["record_inconsistent_sensitivity"]["summary"]

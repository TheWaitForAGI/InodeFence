"""PR-E: a synthetic index of 120 seed blocks through the analyzer and the table generator.

Expected values are worked out by hand in ``SCENARIO``. Informative blocks stay at or below 16, so
every test here is enumerated and takes seconds; the Monte Carlo branch has its unit tests in
``test_survival.py``. The launcher half of the path is in ``test_run_exp0.py``.

    seed 1-8     S-u finds C1 at step 20; R and D stay censored at the budget
    seed 9       S-u aborts at step 50 with no event, and its stub says the target ran
    seed 10      R's record is inconsistent (consistent for 30 steps, no event)
    seed 11      all three arms find C1 at step 30
    seed 12      D is ended by the watchdog at step 60, one cut last line
    seed 13-116  all censored at the budget
    seed 117-120 excluded whole by the deadline
"""

import json
from pathlib import Path
from typing import Any

import pytest
from scripts import gen_exp3_tables as gen
from scripts.analyze_exp0 import _multitarget_markdown, main
from scripts.gen_exp3_tables import Inputs

from inodefence.evaluation.cell_completeness import WATCHDOG_ABORT_REASON

TARGET = "h"
ARMS = ("R", "D", "S-u")
BUDGET = 200
SEEDS = range(1, 121)
EXCLUDED = (117, 118, 119, 120)
HIT = {"t_first": 20, "t_first_event": 1, "first_c1": 20, "hit_steps": 1, "u_viol": 3}
SHARED_HIT = {"t_first": 30, "t_first_event": 1, "first_c1": 30, "hit_steps": 1, "u_viol": 1}
ABORT = {
    "aborted": True,
    "complete": False,
    "abort_reason": "broker",
    "executions_completed": 50,
    "t_first": 50,
}
WATCHDOG = {
    "aborted": True,
    "complete": False,
    "abort_reason": WATCHDOG_ABORT_REASON,
    "executions_completed": 60,
    "t_first": 60,
}
HAND = {
    "abort_split": {
        "target_not_started": 0,
        "lost_after_execution": 1,
        "first_error_unconfirmed": 1,
    },
    "operating_stop": {"fired": False},
}


def _overrides(arm: str, seed: int) -> dict[str, Any]:
    if seed in range(1, 9) and arm == "S-u":
        return HIT
    if seed == 9 and arm == "S-u":
        return ABORT
    if seed == 11:
        return SHARED_HIT
    if seed == 12 and arm == "D":
        return WATCHDOG
    return {}


def _record(arm: str, seed: int) -> dict[str, Any]:
    return {
        "random_seed": seed,
        "arm": arm,
        "execution_budget": BUDGET,
        "executions_completed": BUDGET,
        "complete": True,
        "aborted": False,
        "abort_reason": None,
        "t_first": BUDGET,
        "t_first_event": 0,
        "hit_steps": 0,
        "first_c0": None,
        "first_c1": None,
        "first_c2": None,
        "boundary_attempt_keys": 2 if seed in range(1, 9) and arm == "S-u" else 0,
        "rejected_executions": 0,
        "observation_failures": 0,
        "u_viol": 0,
        **_overrides(arm, seed),
    }


def _dense_detail(arm: str, seed: int, executions: int) -> dict[str, Any]:
    su_hit = seed in range(1, 9) and arm == "S-u"
    return {
        "boundary_keys": [f"key-{seed}", "shared"] if su_hit else [],
        "observation_failures_by_kind": {"malformed_identity": 1} if su_hit and seed == 1 else {},
        "feedback_ineligible_steps": 1 if arm == "D" and seed == 2 else 0,
        "recorded_steps": executions,
        "abort_observed_present": seed == 9 and arm == "S-u",
    }


def _wrapper(arm: str, seed: int) -> dict[str, Any]:
    if seed == 10 and arm == "R":
        return {
            "summary": None,
            "config_nonconformant": True,
            "invalid_reason": "ReportFormatError: record-inconsistent: no-exit-record",
            "record_inconsistent_prefix": {"steps": 30, "t_first": 30, "t_first_event": 0},
        }
    record = _record(arm, seed)
    executions = record["executions_completed"]
    return {
        "schema_version": 1,
        "summary": record,
        "timing": {
            "wall_seconds": 100.0,
            "step_wall_seconds": [0.5] * executions,
            "execution_mode": "per-case-container",
            "exec_per_hour": 7200.0,
            "full_step_seconds_p50": 0.5,
            "full_step_seconds_p95": 0.5,
            "full_step_seconds_max": 0.5,
        },
        "environment": {"host_machine": "x86_64", "image_id": "sha256:synthetic"},
        "dense_detail": _dense_detail(arm, seed, executions),
        "unknown_outcome_steps": 1 if seed == 12 and arm == "D" else 0,
    }


def _plan() -> dict[str, Any]:
    return {
        "event_threshold": 7,
        "confirmatory_contrasts": [
            {
                "order": order,
                "target_id": TARGET,
                "arm_a": "S-u",
                "arm_b": arm,
                "contrast": f"S-u-vs-{arm}",
            }
            for order, arm in enumerate(("R", "D"), start=1)
        ],
    }


def _write_index(tmp_path: Path) -> Path:
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    cells = []
    for seed in SEEDS:
        for arm in ARMS:
            run_id = f"{TARGET}-{arm}-s{seed}"
            (summaries / f"{run_id}.summary.json").write_text(
                json.dumps(_wrapper(arm, seed)), encoding="utf-8"
            )
            cells.append(
                {
                    "run_id": run_id,
                    "arm": arm,
                    "seed": seed,
                    "budget": BUDGET,
                    "summary": f"summaries/{run_id}.summary.json",
                    "target_id": TARGET,
                    "role": "holdout",
                    "hypothesis": "H-A",
                }
            )
    index = summaries / "index.json"
    index.write_text(
        json.dumps(
            {
                "cells": cells,
                "analysis_plan": _plan(),
                "registered": {
                    "seeds": list(SEEDS),
                    "budget": BUDGET,
                    "sentinel_count": 5,
                    "targets": [
                        {
                            "target_id": TARGET,
                            "extractor": "node-tar",
                            "version": "7.9.9",
                            "role": "holdout",
                            "budget": None,
                        }
                    ],
                },
                "deadline": {
                    "execution_deadline": "2026-11-25T12:00:00+09:00",
                    "passed": True,
                    "excluded_seeds": {TARGET: list(EXCLUDED)},
                    "causes": {f"{TARGET}-D-s{seed}": "unattempted" for seed in EXCLUDED},
                },
                "cell_completeness": {
                    "cells": 360,
                    "aborts": 2,
                    "no_record": 0,
                    "watchdog": 1,
                    "record_inconsistent": 1,
                    "unattempted": 4,
                    "infrastructure_failure_rate": 3 / 360,
                    "infrastructure_stops": [],
                    "infrastructure_resumes": [],
                },
            }
        ),
        encoding="utf-8",
    )
    return index


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    index = _write_index(tmp_path_factory.mktemp("exp2-synthetic"))
    capture = index.parent / "report.json"
    assert main(["--index", str(index), "--format", "json", "--output", str(capture)]) == 0
    return json.loads(capture.read_text(encoding="utf-8"))


def _inputs(report: dict[str, Any], tmp_path: Path) -> Inputs:
    hand = tmp_path / "hand.json"
    hand.write_text(json.dumps(HAND), encoding="utf-8")
    # T-EXP3-2 is the train table; these holdout tables never read the other two inputs.
    return Inputs(report, tmp_path / "unused.jsonl", hand, tmp_path / "unused.json")


def _contrast(report: dict[str, Any], name: str) -> dict[str, Any]:
    return next(c for c in report["confirmatory"]["contrasts"] if c["contrast"] == name)


def test_the_deadline_takes_whole_seed_blocks_out_of_every_contrast(report: dict[str, Any]) -> None:
    assert report["deadline"]["number_excluded_seeds"] == 4
    assert report["deadline"]["number_excluded_cells"] == 12
    assert 117 not in report["by_target"][TARGET]["seeds"]


@pytest.mark.parametrize(
    ("name", "blocks", "informative", "exclude_blocks"),
    [
        # Seed 10's invalid R cell leaves only this contrast. Seed 9 informs; it drops in exclude.
        ("S-u-vs-R", 115, 9, 114),
        # Seed 10 stays here as a non-informative block; seeds 9 and 12 inform and drop in exclude.
        ("S-u-vs-D", 116, 10, 114),
    ],
)
def test_contrast_blocks_events_and_policies(
    report: dict[str, Any], name: str, blocks: int, informative: int, exclude_blocks: int
) -> None:
    contrast = _contrast(report, name)
    assert contrast["number_seed_blocks"] == blocks
    assert contrast["informative_blocks"] == informative
    assert contrast["total_events"] == 10  # the eight S-u hits and seed 11's two
    assert contrast["underpowered"] is False
    assert contrast["faster_arm"] == "S-u" and contrast["u_viol_direction"] == "S-u"
    # Only the two ends of seeds 1-8 are as extreme; the censored seeds' labels change nothing
    # because every censoring is after the last event: 2 of 2^8.
    assert contrast["permutation"]["exact"] is True
    assert contrast["permutation"]["p_value"] == pytest.approx(1 / 128)
    assert contrast["holm_adjusted_p"] == pytest.approx(2 / 128)
    assert contrast["reject_at_alpha"] is True
    policies = contrast["abort_policy_results"]
    assert policies["censor-at-abort"]["raw_p"] == contrast["permutation"]["p_value"]
    assert policies["exclude"]["number_seed_blocks"] == exclude_blocks
    assert policies["censor-at-budget"]["number_seed_blocks"] == blocks
    for policy in ("exclude", "censor-at-budget"):
        assert policies[policy]["informative_blocks"] == 8
        assert policies[policy]["raw_p"] == pytest.approx(1 / 128)
        assert policies[policy]["reject_at_alpha"] is True
    for key in ("verdict", "judgment", "decision", "scenario"):
        assert key not in contrast


def test_invalid_and_lost_steps_are_counted_where_they_belong(report: dict[str, Any]) -> None:
    assert _contrast(report, "S-u-vs-R")["number_blocks_invalid_excluded"] == 1
    assert _contrast(report, "S-u-vs-D")["number_blocks_invalid_excluded"] == 0
    assert report["unknown_outcome_steps"] == {
        "lost_after_execution_lower_bound": 1,
        "watchdog_cut_line": 1,
    }
    assert report["record_inconsistent_sensitivity"]["number_inconsistent_cells"] == 1
    assert report["record_inconsistent_sensitivity"]["summary"].startswith("어긋남 1셀")
    sensitivity = _contrast(report, "S-u-vs-R")["record_inconsistent_sensitivity"]
    assert sensitivity["number_inconsistent_cells"] == 1
    assert sensitivity["number_seed_blocks"] == 116  # seed 10 returns, from its consistent prefix


def test_dense_values_are_per_arm_over_analysed_cells(report: dict[str, Any]) -> None:
    by_arm = report["by_target"][TARGET]["dense_signals_registered"]["by_arm"]
    su = by_arm["S-u"]
    assert su["number_cells"] == 116
    assert su["recorded_steps"] == 115 * BUDGET + 50  # the invalid and excluded cells are out
    assert su["new_boundary_keys_per_cell"]["mean"] == pytest.approx(16 / 116)
    assert su["new_boundary_keys_per_cell"]["median"] == 0
    assert su["unique_boundary_keys_in_arm"] == 9  # a union: eight own keys and one shared
    failures = su["observation_failures_by_kind"]["malformed_identity"]
    assert failures["total"] == 1
    assert failures["per_1000_steps"] == pytest.approx(1 / su["recorded_steps"] * 1000)
    assert by_arm["R"]["number_cells"] == 115
    assert by_arm["D"]["feedback_ineligible_ratio"]["numerator"] == 1


def test_the_markdown_report_carries_the_contrast_row(report: dict[str, Any]) -> None:
    text = _multitarget_markdown(report)
    assert "| 1 | S-u-vs-R | 115 | 9 | 10 | 0.0078 |" in text
    assert "| 2 | S-u-vs-D | 116 | 10 | 10 | 0.0078 |" in text


@pytest.mark.parametrize(
    ("artifact", "row"),
    [
        ("T-EXP2-1", "| R | 115 | 115 | 0 | 0 | 1 | 1 | 미도달 |"),
        ("T-EXP2-1", "| D | 116 | 115 | 1 | 1 | 0 | 1 | 미도달 |"),
        ("T-EXP2-1", "| S-u | 116 | 115 | 1 | 1 | 0 | 9 | 미도달 |"),
        ("T-EXP2-1", "등록 seed 블록 120, 분석 블록 116, 미완주 제외 4(unattempted 4)."),
        (
            "T-EXP2-2",
            "| S-u-vs-R | 115 | 9 | 10 | .0078 | .0156 | 기각 | S-u | S-u | 기각 | 기각 |",
        ),
        (
            "T-EXP2-2",
            "| S-u-vs-D | 116 | 10 | 10 | .0078 | .0156 | 기각 | S-u | S-u | 기각 | 기각 |",
        ),
        ("T-EXP2-2", "**판정:** (사람이 D040-D12 표를 읽어 고른다. 생성기는 채우지 않는다.)"),
        ("T-EXP2-3", "- 대비별 invalid 제외: S-u-vs-R 1, S-u-vs-D 0"),
        ("T-EXP2-3", "- 결과 미상 step: 실행 후 소실 1(스텁 하한 1), watchdog 잘린 줄 1, 합계 2"),
        ("T-EXP2-3", "- 인프라 정지 0, 재개 0"),
        ("T-EXP2-4", "| S-u | censor-at-budget | 9 | 107 | 116 | 미도달 |"),
        ("T-EXP2-4", "| S-u | exclude | 9 | 106 | 115 | 미도달 |"),
        ("T-EXP2-5", "| full step p95 (monotonic s) | 0.500 |"),
        ("T-EXP2-6", "| S-u | 0.14 | 0 | 9 | .000 | malformed_identity 1(0.04/1000) | .000 |"),
    ],
)
def test_the_tables_read_the_analyzer_itself(
    report: dict[str, Any], tmp_path: Path, artifact: str, row: str
) -> None:
    assert row in gen.render(artifact, _inputs(report, tmp_path))

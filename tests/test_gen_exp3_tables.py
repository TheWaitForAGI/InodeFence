"""EXP-3 and EXP-2 result tables, from real analyzer output with PR-D's keys added by hand."""

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from scripts import gen_exp3_tables as gen
from scripts.analyze_exp0 import (
    _DEFAULT_FIELD_MAP,
    _apply_deadline,
    _record_states,
    build_multitarget_report,
    cell_from_row,
    main,
)
from scripts.gen_exp3_tables import Inputs, TableInputError
from scripts.regenerate_paper_artifacts import ARTIFACTS

FIELD_MAP = dict(_DEFAULT_FIELD_MAP)
HIT = {"t_first": 20, "t_first_event": 1, "first_c1": 20, "hit_steps": 1, "u_viol": 3}
DEADLINE = "2026-11-25T12:00:00+09:00"


def _cell(arm: str, seed: int, target_id: str, role: str, **over: Any) -> Any:
    record = {
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
        "rejected_executions": 20,
        "observation_failures": 0,
        "u_viol": 0,
        **over,
    }
    entry = {"target_id": target_id, "role": role, "hypothesis": "H-A", "summary": "x"}
    return cell_from_row({"summary": record}, FIELD_MAP, entry=entry)


def _invalid(arm: str, seed: int, target_id: str, reason: str) -> Any:
    wrapper = {"summary": None, "config_nonconformant": True, "invalid_reason": reason}
    return cell_from_row(
        wrapper,
        FIELD_MAP,
        entry={"arm": arm, "seed": seed, "target_id": target_id, "role": "holdout"},
    )


def _registered(target_id: str, role: str) -> dict[str, Any]:
    return {
        "seeds": [1, 2, 3, 4],
        "budget": 200,
        "sentinel_count": 5,
        "targets": [
            {
                "target_id": target_id,
                "extractor": "node-tar",
                "version": "7.5.2" if role == "train" else "7.4.4",
                "role": role,
                "budget": None,
            }
        ],
    }


def _completeness(**over: Any) -> dict[str, Any]:
    return {
        "aborts": 1,
        "cells": 10,
        "unattempted": 1,
        "recorded_steps": 1800,
        "no_record": 0,
        "watchdog": 1,
        "record_inconsistent": 1,
        "infrastructure_failure_rate": 0.125,
        "infrastructure_stops": [],
        "infrastructure_resumes": [],
        **over,
    }


def _dense_keys(report: dict[str, Any], target_id: str) -> None:
    """PR-D's keys, as PR-G names them. PR-D must produce exactly these."""
    section = report["by_target"][target_id]
    section["dense_signals_registered"] = {
        "by_arm": {
            arm: {
                "new_boundary_keys_per_cell": {"mean": 2.5, "median": 2},
                "unique_boundary_keys_in_arm": 7,
                "observation_failures_by_kind": {
                    "malformed_identity": {"total": 3, "per_1000_steps": 1.5},
                },
                "feedback_ineligible_ratio": {"value": 0.25},
            }
            for arm in section["item6_dense_signals"]["by_arm"]
        }
    }
    for values in section["item1_aborts"]["by_arm"].values():
        values["number_abort_before_event"] = 0


def _train_report() -> dict[str, Any]:
    cells = [
        _cell(arm, seed, "t", "train", **(HIT if arm == "S-u" and seed < 3 else {}))
        for arm in ("S-u", "R", "D")
        for seed in (1, 2, 3)
    ]
    cells.append(_invalid("R", 3, "t", "ReportFormatError: record-inconsistent: no-exit-record"))
    report = build_multitarget_report(
        cells,
        field_map=FIELD_MAP,
        sources=["t"],
        deadline={
            "execution_deadline": DEADLINE,
            "passed": True,
            "excluded_seeds": {"t": [4]},
            "number_excluded_seeds": 1,
            "number_excluded_cells": 3,
            "causes": {"t-R-s4": "unattempted"},
        },
        registration={
            "registered": _registered("t", "train"),
            "cell_completeness": _completeness(),
        },
    )
    _dense_keys(report, "t")
    return report


def _holdout_report() -> dict[str, Any]:
    cells = [
        _cell(arm, seed, "h", "holdout", **(HIT if arm == "S-u" else {}))
        for arm in ("S-u", "R", "D")
        for seed in (1, 2, 3, 4)
    ]
    report = build_multitarget_report(
        cells,
        analysis_plan={
            "confirmatory_contrasts": [
                {
                    "order": 2,
                    "target_id": "h",
                    "arm_a": "S-u",
                    "arm_b": "D",
                    "contrast": "S-u-vs-D",
                },
                {
                    "order": 1,
                    "target_id": "h",
                    "arm_a": "S-u",
                    "arm_b": "R",
                    "contrast": "S-u-vs-R",
                },
            ]
        },
        field_map=FIELD_MAP,
        sources=["t"],
        deadline={
            "execution_deadline": DEADLINE,
            "passed": True,
            "excluded_seeds": {},
            "number_excluded_seeds": 0,
            "number_excluded_cells": 0,
            "causes": {},
        },
        registration={
            "registered": _registered("h", "holdout"),
            "cell_completeness": _completeness(aborts=0, watchdog=0, record_inconsistent=0),
        },
    )
    _dense_keys(report, "h")
    for contrast in report["confirmatory"]["contrasts"]:
        contrast["informative_blocks"] = 4
        contrast["u_viol_direction"] = "S-u"
        contrast["number_blocks_invalid_excluded"] = 0
        contrast["abort_policy_results"] = {
            "exclude": {"reject_at_alpha": False},
            "censor-at-budget": {"reject_at_alpha": False},
        }
    report["unknown_outcome_steps"] = {
        "lost_after_execution_lower_bound": 1,
        "watchdog_cut_line": 2,
    }
    report["record_inconsistent_sensitivity"] = {"summary": "어긋남 없음"}
    return report


def _add_timing(report: dict[str, Any]) -> None:
    section = report["by_target"]["h"]
    section["item2_p95_full_step"] = {
        "pooled": {"number_steps": 9, "p50_seconds": 1.0, "p95_seconds": 2.0, "max_seconds": 3.0}
    }
    section["item3_throughput"] = {
        "summed": {"number_cells": 2, "executions": 9, "exec_per_hour": 100.0}
    }


def _inputs(report: dict[str, Any], tmp_path: Path, *, hand: Any = None) -> Inputs:
    results = tmp_path / "cell-results.jsonl"
    rows = [
        {"event": "start", "clocks": {"realtime": 1000.0}},
        {"event": "end", "clocks": {"realtime": 8200.0}},
    ]
    results.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    hand_path = tmp_path / "hand.json"
    if hand is not None:
        hand_path.write_text(json.dumps(hand), encoding="utf-8")
    return Inputs(report, results, hand_path)


HAND = {
    "abort_split": {
        "target_not_started": 1,
        "lost_after_execution": 2,
        "first_error_unconfirmed": 3,
    },
    "operating_stop": {"fired": False},
}


def test_train_arm_table_bytes(tmp_path: Path) -> None:
    text = gen.render("T-EXP3-1", _inputs(_train_report(), tmp_path))
    assert text == (
        "# 표 7-B. EXP-3 `role=train` arm별 (탐색, 기노출, 확증 아님)\n"
        "\n"
        "대상 node-tar 7.5.2, k=5, budget 200. 등록 seed 블록 4, 분석 블록 3, "
        "미완주 제외 1(unattempted 1).\n"
        "\n"
        "| arm | 분석 캠페인 | 완주 | abort | 기록 어긋남 | 첫 C1∨C2 사건 | T_first KM 중앙값 | "
        "U_viol 평균(합) |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| R | 3 | 3 | 0 | 1 | 0 | 미도달 | 0.00(0) |\n"
        "| D | 3 | 3 | 0 | 0 | 0 | 미도달 | 0.00(0) |\n"
        "| S-u | 3 | 3 | 0 | 0 | 2 | 20 | 2.00(6) |\n"
    )


def test_a_train_table_has_no_test_value_and_refuses_a_confirmatory_section(
    tmp_path: Path,
) -> None:
    report = _train_report()
    for artifact in ("T-EXP3-1", "T-EXP3-2", "T-EXP3-3"):
        text = gen.render(artifact, _inputs(report, tmp_path))
        for word in ("Holm", "기각", "빠른", "순열", "HR"):
            assert word not in text
    report["confirmatory"] = {"contrasts": []}
    with pytest.raises(TableInputError, match="confirmatory"):
        gen.render("T-EXP3-1", _inputs(report, tmp_path))


def test_go_inputs_are_computed_and_the_result_stays_empty(tmp_path: Path) -> None:
    lines = gen.render("T-EXP3-2", _inputs(_train_report(), tmp_path)).splitlines()
    table = [line for line in lines[4:] if line.startswith("| ")]
    row = {line.split(" | ")[0].removeprefix("| "): line.split(" | ")[1] for line in table}
    assert row["E: train 첫 C1∨C2 캠페인(3 arm 합산, abort 포함, invalid 제외)"] == "2"
    # 1800 recorded steps over the two hours between the first start and the last end, no stop.
    assert row["r: 정지 공백을 뺀 처리량(실시간, exec/h)"] == "900"
    assert row["e: 기록/계획 step 비율"] == "1.000"
    assert row["인프라 실패 비율 (abort + 기록 어긋남)/전체 셀"] == ".125"
    assert "| 결과 |  | W3가 적용해 LOG에 남긴다 |" in lines


def test_go_capacity_follows_the_registered_formula(tmp_path: Path) -> None:
    report = _train_report()
    report["deadline"]["execution_deadline"] = (
        "1970-01-01T07:16:40+00:00"  # 5 h after the last end at 8200 s
    )
    text = gen.render("T-EXP3-2", _inputs(report, tmp_path))
    assert "| H_rem: EXP-3 종료부터 실행 마감까지 호스트 시간(실시간, h) | 5.0 | 입력 |" in text
    # floor(5.0 h * 900 exec/h / (6000 * 1.0)) = 0
    assert "| 용량 ⌊H_rem·r÷(6000·e)⌋ | 0 | ≥ 76 |" in text


def test_contrast_table_keeps_holm_order_and_leaves_the_verdict_to_people(tmp_path: Path) -> None:
    text = gen.render("T-EXP2-2", _inputs(_holdout_report(), tmp_path))
    rows = [line for line in text.splitlines() if line.startswith("| S-u-vs-")]
    assert [row.split(" | ")[0] for row in rows] == ["| S-u-vs-R", "| S-u-vs-D"]
    assert "| 4 | 4 | 4 | .1250 | .2500 | 비기각 | S-u | S-u | 비기각 | 비기각 |" in rows[0]
    assert "**판정:** (사람이 D040-D12 표를 읽어 고른다. 생성기는 채우지 않는다.)" in text
    for verdict in ("가속 주장", "반증", "GO", "NO-GO"):
        assert verdict not in text


def test_zero_events_say_none_and_a_tie_says_tie(tmp_path: Path) -> None:
    report = _holdout_report()
    contrast = report["confirmatory"]["contrasts"][0]
    contrast["faster_arm"], contrast["total_events"] = None, 0
    assert gen._faster(contrast) == "없음"
    contrast["total_events"] = 3
    assert gen._faster(contrast) == "동률"


@pytest.mark.parametrize(
    ("value", "text"),
    [(0.00009, "< .0001"), (0.0001, ".0001"), (0.04567, ".0457"), (0.5, ".5000"), (1.0, "1.0000")],
)
def test_p_format(value: float, text: str) -> None:
    assert gen._p(value) == text


def test_ratio_and_median_format() -> None:
    assert (gen._ratio(0.1234), gen._ratio(0.0), gen._ratio(1.0)) == (".123", ".000", "1.000")
    assert (gen._median(None), gen._median(20), gen._median(20.5)) == ("미도달", "20", "20.5")


@pytest.mark.parametrize(
    ("artifact", "path"),
    [
        ("T-EXP3-1", ("registered", "sentinel_count")),
        ("T-EXP3-1", ("deadline", "causes")),
        ("T-EXP3-1", ("by_target", "t", "record_states")),
        ("T-EXP3-2", ("cell_completeness", "infrastructure_failure_rate")),
        ("T-EXP3-2", ("cell_completeness", "recorded_steps")),
        ("T-EXP3-2", ("cell_completeness", "unattempted")),
        ("T-EXP3-3", ("by_target", "t", "dense_signals_registered")),
    ],
)
def test_a_missing_input_stops_the_train_table(
    tmp_path: Path, artifact: str, path: tuple[str, ...]
) -> None:
    report = copy.deepcopy(_train_report())
    holder = report
    for key in path[:-1]:
        holder = holder[key]
    del holder[path[-1]]
    with pytest.raises(TableInputError, match=path[-1]):
        gen.render(artifact, _inputs(report, tmp_path))


@pytest.mark.parametrize(
    ("artifact", "key"),
    [
        ("T-EXP2-2", "informative_blocks"),
        ("T-EXP2-2", "u_viol_direction"),
        ("T-EXP2-2", "abort_policy_results"),
        ("T-EXP2-3", "number_blocks_invalid_excluded"),
    ],
)
def test_a_missing_contrast_value_stops_the_holdout_table(
    tmp_path: Path, artifact: str, key: str
) -> None:
    report = _holdout_report()
    del report["confirmatory"]["contrasts"][0][key]
    with pytest.raises(TableInputError, match=key):
        gen.render(artifact, _inputs(report, tmp_path, hand=HAND))


def test_a_null_value_is_not_written_as_zero(tmp_path: Path) -> None:
    report = _holdout_report()
    report["confirmatory"]["contrasts"][0]["informative_blocks"] = None
    with pytest.raises(TableInputError, match="informative_blocks"):
        gen.render("T-EXP2-2", _inputs(report, tmp_path))


def test_a_real_zero_is_written_as_zero(tmp_path: Path) -> None:
    text = gen.render("T-EXP2-1", _inputs(_holdout_report(), tmp_path))
    assert "| R | 4 | 4 | 0 | 0 | 0 | 0 | 미도달 | 0.00(0) |" in text


def test_notes_need_the_hand_input_and_write_zeros(tmp_path: Path) -> None:
    report = _holdout_report()
    with pytest.raises(TableInputError, match="hand input not found"):
        gen.render("T-EXP2-3", _inputs(report, tmp_path))
    text = gen.render("T-EXP2-3", _inputs(report, tmp_path, hand=HAND))
    assert "미완주 제외 seed 0" in text and "기록 어긋남 0" in text and "watchdog 사유 0" in text
    assert "target 미시작 1, 실행 후 소실 2, 첫 오류 미확인 3" in text
    assert "실행 후 소실 2(스텁 하한 1), watchdog 잘린 줄 2, 합계 4" in text
    assert "no-record 0" in text and "인프라 정지 0, 재개 0" in text
    assert "운영 중단: 발동 없음" in text


def test_a_second_target_or_the_wrong_role_is_refused_never_pooled(tmp_path: Path) -> None:
    report = _train_report()
    report["registered"]["targets"].append({"target_id": "h", "role": "holdout"})
    with pytest.raises(TableInputError, match="exactly one"):
        gen.render("T-EXP3-1", _inputs(report, tmp_path))
    with pytest.raises(TableInputError, match="exactly one"):
        gen.render("T-EXP2-1", _inputs(_train_report(), tmp_path))
    report = _train_report()
    report["by_target"]["other"] = report["by_target"]["t"]
    with pytest.raises(TableInputError, match="not t"):
        gen.render("T-EXP3-1", _inputs(report, tmp_path))


def test_a_hand_count_below_the_stub_lower_bound_stops_the_notes(tmp_path: Path) -> None:
    report = _holdout_report()
    report["unknown_outcome_steps"]["lost_after_execution_lower_bound"] = 3
    with pytest.raises(TableInputError, match="below the stubs"):
        gen.render("T-EXP2-3", _inputs(report, tmp_path, hand=HAND))


def test_notes_count_stops_and_resumes(tmp_path: Path) -> None:
    report = _holdout_report()
    report["cell_completeness"]["infrastructure_stops"] = [{}, {}]
    report["cell_completeness"]["infrastructure_resumes"] = [{}]
    report["cell_completeness"]["no_record"] = 4
    text = gen.render("T-EXP2-3", _inputs(report, tmp_path, hand=HAND))
    assert "인프라 정지 2, 재개 1" in text and "no-record 4" in text


def _go_row(text: str, label: str) -> str:
    row = next(line for line in text.splitlines() if line.startswith(f"| {label}"))
    return row.split(" | ")[1]


def _write_results(tmp_path: Path, rows: list[Any], tail: str = "") -> Inputs:
    inputs = _inputs(_train_report(), tmp_path)
    body = "".join(json.dumps(row) + "\n" for row in rows) + tail
    inputs.cell_results.write_text(body, encoding="utf-8")
    return inputs


def _stamp(event: str, realtime: float) -> dict[str, Any]:
    return {"event": event, "clocks": {"realtime": realtime}}


STOP = {"event": "infrastructure-stop", "reason": "why", "clocks": {"realtime": 1000.0}}
RESUME = {"event": "infrastructure-resume", "approval_ref": "ok", "clocks": {"realtime": 4600.0}}
NO_GAP_ROWS = [_stamp("start", 0.0), _stamp("end", 1000.0)]
NO_GAP_ROWS += [_stamp("start", 4600.0), _stamp("end", 7200.0)]
GAP_ROWS = [*NO_GAP_ROWS[:2], STOP, RESUME, *NO_GAP_ROWS[2:]]
R_WALL_NOTE = "r_wall(참고, GO 입력 아님): 900 exec/h. 정지 공백을 포함한 값이고 판정을 뒤집는 데"


def test_no_gap_gives_r_equal_to_r_wall(tmp_path: Path) -> None:
    text = gen.render("T-EXP3-2", _write_results(tmp_path, NO_GAP_ROWS))
    assert _go_row(text, "r:") == "900"
    assert R_WALL_NOTE in text
    assert "정지 0회, 누적 공백 0.0 h(실시간). 원인은 docs/LOG.md의 W2 기록." in text


def test_a_resumed_stop_raises_r_and_keeps_r_wall_as_a_reference(tmp_path: Path) -> None:
    text = gen.render("T-EXP3-2", _write_results(tmp_path, GAP_ROWS))
    assert _go_row(text, "r:") == "1800"  # 3600 s of the 7200 s were the stop
    assert R_WALL_NOTE in text
    assert "정지 1회, 누적 공백 1.0 h(실시간)." in text


def test_a_cell_running_after_the_stop_keeps_its_time_in_r(tmp_path: Path) -> None:
    """The gap opens at the last end before the resume, not at the stop line."""
    rows = [_stamp("start", 0.0), _stamp("start", 0.0), _stamp("end", 1000.0), STOP]
    rows += [_stamp("end", 3000.0), RESUME, _stamp("start", 4600.0), _stamp("end", 7200.0)]
    text = gen.render("T-EXP3-2", _write_results(tmp_path, rows))
    # 1600 s gap: 1800 steps over 5600 s. Counting from the stop would give 1800.
    assert _go_row(text, "r:") == "1157"
    assert "누적 공백 0.4 h" in text


def test_a_resume_after_the_last_end_adds_no_gap_and_moves_h_rem(tmp_path: Path) -> None:
    stop = {**STOP, "clocks": {"realtime": 8300.0}}
    resume = {**RESUME, "clocks": {"realtime": 9000.0}}
    rows = [_stamp("start", 1000.0), _stamp("end", 8200.0), stop, resume]
    inputs = _write_results(tmp_path, rows)
    inputs.report["deadline"]["execution_deadline"] = "1970-01-01T12:00:00+00:00"
    text = gen.render("T-EXP3-2", inputs)
    assert _go_row(text, "r:") == "900"  # that gap was never in the 7200 s span
    assert "정지 1회, 누적 공백 0.0 h" in text
    assert _go_row(text, "H_rem") == "9.5"  # from the resume at 9000 s, not the last end


def test_h_rem_stays_on_the_wall_clock_and_capacity_uses_r(tmp_path: Path) -> None:
    def table(rows: list[Any]) -> str:
        inputs = _write_results(tmp_path, rows)
        # 10 h after the last end at 7200 s.
        inputs.report["deadline"]["execution_deadline"] = "1970-01-01T12:00:00+00:00"
        return gen.render("T-EXP3-2", inputs)

    with_gap, without = table(GAP_ROWS), table(NO_GAP_ROWS)
    assert _go_row(with_gap, "H_rem") == _go_row(without, "H_rem") == "10.0"
    # floor(10 * r / (6000 * 1.0)): 3 at r = 1800, 1 at r_wall = 900.
    assert (_go_row(with_gap, "용량"), _go_row(without, "용량")) == ("3", "1")


@pytest.mark.parametrize(
    ("rows", "stops", "gap"),
    [
        ([*NO_GAP_ROWS, {**STOP, "clocks": {"realtime": 7300.0}}], 1, "0.0"),
        ([*GAP_ROWS, {**STOP, "clocks": {"realtime": 7300.0}}], 2, "1.0"),
    ],
)
def test_an_unresumed_stop_leaves_the_go_cells_not_computed(
    tmp_path: Path, rows: list[Any], stops: int, gap: str
) -> None:
    text = gen.render("T-EXP3-2", _write_results(tmp_path, rows))
    for label in ("r:", "H_rem", "용량"):
        assert _go_row(text, label) == "미산출"
    assert _go_row(text, "결과") == "미산출: 인프라 정지 미재개. GO 미적용, EXP-2 미시작"
    # Measured values stay: E, e, the failure rate, r_wall, stops, resumed gaps.
    assert _go_row(text, "E:") == "2"
    assert _go_row(text, "e:") == "1.000"
    assert _go_row(text, "인프라 실패 비율") == ".125"
    assert R_WALL_NOTE in text
    assert f"정지 {stops}회, 누적 공백 {gap} h(실시간)." in text


def test_a_resume_after_an_unresumed_stop_brings_the_go_cells_back(tmp_path: Path) -> None:
    text = gen.render("T-EXP3-2", _write_results(tmp_path, GAP_ROWS))
    assert "미산출" not in text


def test_only_a_cut_last_line_of_the_exit_record_is_forgiven(tmp_path: Path) -> None:
    rows = [_stamp("start", 1000.0), _stamp("end", 8200.0)]
    text = gen.render("T-EXP3-2", _write_results(tmp_path, rows, tail='{"event": "st'))
    assert _go_row(text, "r:") == "900"
    inputs = _write_results(tmp_path, [_stamp("start", 1000.0)], tail="cut\n" + json.dumps(rows[1]))
    with pytest.raises(TableInputError, match="unreadable line 2"):
        gen.render("T-EXP3-2", inputs)


def test_the_step_ratio_plans_only_attempted_cells_and_counts_invalid_ones(tmp_path: Path) -> None:
    report = _train_report()
    # 12 cells, 2 never started: 10 attempted × budget 200 against 1500 recorded.
    report["cell_completeness"].update(cells=12, unattempted=2, recorded_steps=1500)
    assert report["registered"]["budget"] == 200
    text = gen.render("T-EXP3-2", _inputs(report, tmp_path))
    assert _go_row(text, "e:") == ".750"
    assert "| 시작하지 않은 셀 | 2 | 기록 |" in text


def test_the_empty_table_sentence_needs_every_seed_excluded(tmp_path: Path) -> None:
    report = _holdout_report()
    report["by_target"] = {}
    report["deadline"]["number_excluded_seeds"] = 3  # of 4 registered
    with pytest.raises(TableInputError, match="3 of 4 seeds excluded"):
        gen.render("T-EXP2-1", _inputs(report, tmp_path))


def test_the_figure_says_why_when_every_seed_was_excluded() -> None:
    figure = importlib.import_module("paper.figures.render_exp3_survival")
    report = _train_report()
    report["by_target"] = {}
    with pytest.raises(ValueError, match="every seed was excluded"):
        figure.arm_curves(report, "train")


def test_the_generators_inputs_are_registered_with_each_table() -> None:
    registered = {artifact.output: artifact for artifact in ARTIFACTS}
    go_inputs = registered["paper/tables/exp3-go-inputs.md"].inputs
    assert "experiments/summaries/exp3-train-cell-results.jsonl" in go_inputs
    notes = registered["paper/tables/exp2-holdout-notes.md"].inputs
    assert "experiments/summaries/exp2-holdout-hand-input.json" in notes


def test_every_seed_excluded_is_a_stated_table_not_a_failure(tmp_path: Path) -> None:
    report = _holdout_report()
    report["by_target"] = {}
    report["deadline"]["number_excluded_seeds"] = 4
    report["deadline"]["causes"] = {"h-R-s1": "unattempted"}
    text = gen.render("T-EXP2-1", _inputs(report, tmp_path))
    assert "분석 블록 0, 미완주 제외 4(unattempted 1)" in text
    assert "분석 캠페인 0: 마감으로 모든 seed가 제외됐다." in text
    contrast = report["confirmatory"]["contrasts"][0]
    contrast["permutation"]["p_value"] = None
    assert gen._permutation_p(contrast) == "미검정"


def test_every_table_renders_and_repeats_byte_for_byte(tmp_path: Path) -> None:
    for artifact in gen.TABLES:
        report = _train_report() if artifact.startswith("T-EXP3") else _holdout_report()
        if artifact == "T-EXP2-5":
            _add_timing(report)
        inputs = _inputs(report, tmp_path, hand=HAND)
        assert gen.render(artifact, inputs) == gen.render(artifact, inputs)


def test_dense_table_title_and_values(tmp_path: Path) -> None:
    text = gen.render("T-EXP3-3", _inputs(_train_report(), tmp_path))
    assert text.startswith("# EXP-3 train dense 지표 (탐색, effectiveness 아님)\n")
    assert "| S-u | 2.50 | 2 | 7 | .100 | malformed_identity 3(1.50/1000) | .250 |" in text


def test_infra_table_names_its_clock(tmp_path: Path) -> None:
    with pytest.raises(TableInputError):  # the fixture has no timing: stop rather than fill in
        gen.render("T-EXP2-5", _inputs(_holdout_report(), tmp_path))
    report = _holdout_report()
    _add_timing(report)
    text = gen.render("T-EXP2-5", _inputs(report, tmp_path))
    assert "monotonic" in text and "| full step p95 (monotonic s) | 2.000 |" in text


def test_main_check_out_and_refusal(tmp_path: Path, capsys: Any) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_train_report()), encoding="utf-8")
    out = tmp_path / "table.md"
    args = ["--artifact", "T-EXP3-1", "--report", str(report)]
    assert gen.main([*args, "--out", str(out)]) == 0
    assert gen.main([*args, "--check", str(out)]) == 0
    out.write_text(out.read_text(encoding="utf-8") + "x", encoding="utf-8")
    assert gen.main([*args, "--check", str(out)]) == 1
    flat = tmp_path / "flat.json"
    flat.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    assert gen.main(["--artifact", "T-EXP3-1", "--report", str(flat), "--out", str(out)]) == 2
    assert "use --index" in capsys.readouterr().err
    missing = tmp_path / "absent.json"
    assert gen.main(["--artifact", "T-EXP3-1", "--report", str(missing)]) == 2


def test_every_table_and_figure_is_registered_as_an_artifact() -> None:
    registered = {artifact.output: artifact for artifact in ARTIFACTS}
    for name, table in gen.TABLES.items():
        row = registered[table.output]
        assert row.optional is True and row.out_flag is True and row.verify == "byte"
        assert row.generator == "scripts/gen_exp3_tables.py"
        assert row.generator_args == ("--artifact", name)
    for figure in ("exp3-train-survival.png", "exp2-holdout-survival.png"):
        assert registered[f"paper/figures/{figure}"].optional is True


def test_figure_curves_are_of_the_one_target_and_the_train_title_says_exploratory() -> None:
    figure = importlib.import_module("paper.figures.render_exp3_survival")
    curves = figure.arm_curves(_train_report(), "train")
    assert set(curves) == {"R", "D", "S-u"} and "km_curve" in curves["R"]
    assert "not confirmatory" in figure.TITLES["train"]
    with pytest.raises(ValueError, match="exactly one"):
        figure.arm_curves(_train_report(), "holdout")


def test_figure_renders_an_arm_with_no_curve_and_no_censoring(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    figure = importlib.import_module("paper.figures.render_exp3_survival")
    report = _train_report()
    by_arm = report["by_target"]["t"]["item5_first_contract_index"]["by_arm"]
    by_arm["R"]["t_first_combined_c1_or_c2"].update(km_curve=[], censored_times=[])
    out = tmp_path / "figure.png"
    figure.render(report, "train", out)
    assert out.stat().st_size > 0


def test_figure_renders_when_matplotlib_is_present(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    figure = importlib.import_module("paper.figures.render_exp3_survival")
    out = tmp_path / "figure.png"
    figure.render(_train_report(), "train", out)
    assert out.stat().st_size > 0


def test_record_states_read_the_launcher_reason() -> None:
    cells = [
        _invalid("R", 1, "h", "ReportFormatError: record-inconsistent: no-exit-record"),
        _invalid("R", 2, "h", "ReportFormatError: no-record: no record after the retry"),
        _invalid("D", 1, "h", "ReportFormatError: config mismatch"),
    ]
    assert _record_states(["D", "R", "S-u"], cells)["by_arm"] == {
        "D": {"record_inconsistent": 0, "no_record": 0},
        "R": {"record_inconsistent": 1, "no_record": 1},
        "S-u": {"record_inconsistent": 0, "no_record": 0},
    }


def test_analyzer_carries_the_launcher_records_from_the_index(tmp_path: Path, capsys: Any) -> None:
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    entries = []
    for arm in ("S-u", "R"):
        run_id = f"h-{arm}-s1"
        record = {
            "random_seed": 1,
            "arm": arm,
            "execution_budget": 200,
            "executions_completed": 150,
            "complete": False,
            "aborted": True,
            "abort_reason": "broker",
            "t_first": 150,
            "t_first_event": 0,
            "hit_steps": 0,
            "first_c0": None,
            "first_c1": None,
            "first_c2": None,
            "boundary_attempt_keys": 0,
            "rejected_executions": 0,
            "observation_failures": 0,
            "u_viol": 0,
        }
        (summaries / f"{run_id}.summary.json").write_text(json.dumps({"summary": record}))
        entries.append(
            {
                "run_id": run_id,
                "arm": arm,
                "seed": 1,
                "summary": f"summaries/{run_id}.summary.json",
                "target_id": "h",
                "role": "holdout",
                "hypothesis": "H-A",
            }
        )
    index = summaries / "index.json"
    index.write_text(
        json.dumps(
            {
                "cells": entries,
                "deadline": {
                    "execution_deadline": DEADLINE,
                    "passed": False,
                    "excluded_seeds": {},
                    "causes": {},
                },
                "registered": _registered("h", "holdout"),
                "cell_completeness": _completeness(),
            }
        )
    )
    assert main(["--index", str(index), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["registered"]["sentinel_count"] == 5
    assert report["cell_completeness"]["record_inconsistent"] == 1


def test_apply_deadline_keeps_its_contract_for_the_tables() -> None:
    cells = [_cell("R", 1, "h", "holdout"), _cell("R", 2, "h", "holdout")]
    kept, summary = _apply_deadline(
        cells, {"execution_deadline": DEADLINE, "passed": True, "excluded_seeds": {"h": [2]}}
    )
    assert [cell.seed for cell in kept] == [1]
    assert summary is not None and summary["number_excluded_seeds"] == 1

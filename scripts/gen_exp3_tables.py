"""Generate the EXP-3 (train) and EXP-2 (holdout) result tables from ``analyze_exp0`` reports.

The output specification is ``paper/deliverables/results-artifact-requirements.md``. Its rules:

1. No verdict: the verdict line and the GO result stay for people to fill in.
2. No test value on train: a train report carrying a confirmatory section is refused.
3. No pooling: one report, one role, one target per table.
4. A missing field stops the table. Zero is written only when the value is zero. The only defined
   "no value" words are "미도달" for a null KM median and "없음" for no faster arm at zero events.
5. Fixed header wording goes with each table.
6. The same inputs give the same bytes (``--check``).
7. Time values name their clock.

    python -m scripts.gen_exp3_tables --artifact T-EXP3-1 --report <report.json> --out <table.md>
    python -m scripts.gen_exp3_tables --artifact T-EXP3-1 --report <report.json> --check <table.md>

Standard library only: ``regenerate_paper_artifacts`` runs this file by path.
"""

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SUMMARIES = REPO / "experiments/summaries"
TRAIN_REPORT = SUMMARIES / "exp3-train-report.json"
HOLDOUT_REPORT = SUMMARIES / "exp2-holdout-report.json"
TRAIN_CELL_RESULTS = SUMMARIES / "exp3-train-cell-results.jsonl"
HOLDOUT_HAND_INPUT = SUMMARIES / "exp2-holdout-hand-input.json"
MULTITARGET_CLASSIFICATION = "exp3-multitarget-measurement"
ARM_ORDER = ("R", "D", "S-u")
GO_STEP_DIVISOR = 6000  # D040-D11: capacity = floor(H_rem * r / (6000 * e)).
MONOTONIC_NOTE = "시계: monotonic 기록값이다. 이 호스트의 monotonic은 실시간이 아니다."


class TableInputError(ValueError):
    """The inputs cannot produce this table; rule 4 says stop rather than fill in."""


def _field(source: object, *path: str) -> Any:
    """A required value: a missing key or a null stops the table and names the path."""
    value = _nullable(source, *path)
    if value is None:
        raise TableInputError(f"missing value: {'.'.join(path)}")
    return value


def _nullable(source: object, *path: str) -> Any:
    """A required key whose value may be null. Only a missing key stops the table."""
    current = source
    for position, key in enumerate(path):
        if not isinstance(current, Mapping) or key not in current:
            raise TableInputError(f"missing field: {'.'.join(path[: position + 1])}")
        current = current[key]
    return current


def _p(value: float) -> str:
    """p and Holm p: four places, "< .0001" below that (rule 6)."""
    return "< .0001" if value < 0.0001 else _decimal(value, 4)


def _decimal(value: float, places: int) -> str:
    text = f"{value:.{places}f}"
    return text[1:] if text.startswith("0.") else text


def _ratio(value: float) -> str:
    return _decimal(value, 3)


def _median(value: object) -> str:
    return "미도달" if value is None else f"{value:g}"


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows),
    ]


def _arm_key(arm: str) -> tuple[int, str]:
    return (ARM_ORDER.index(arm) if arm in ARM_ORDER else len(ARM_ORDER), arm)


@dataclass(frozen=True, slots=True)
class Target:
    """The one analysed target of a report; ``section`` is ``None`` when no cell is left."""

    target_id: str | None
    section: Mapping[str, Any] | None
    registered: Mapping[str, Any]


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TableInputError(f"report not found: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("classification") != MULTITARGET_CLASSIFICATION:
        raise TableInputError(f"{path}: not a registered multi-target report (use --index)")
    return report


def _target(report: Mapping[str, Any], role: str) -> Target:
    """The report's only target, which must have ``role``; several targets are never pooled."""
    registered = _field(report, "registered", "targets")
    if len(registered) != 1 or registered[0].get("role") != role:
        raise TableInputError(f"expected exactly one registered target, with role {role}")
    target_id = _field(registered[0], "target_id")
    by_target = _field(report, "by_target")
    if not by_target:
        return Target(target_id, None, registered[0])  # the deadline excluded every seed
    if set(by_target) != {target_id}:
        raise TableInputError(f"report targets {sorted(by_target)} are not {target_id}")
    return Target(target_id, by_target[target_id], registered[0])


def _train_target(report: Mapping[str, Any]) -> Target:
    if _nullable(report, "confirmatory") is not None:
        raise TableInputError("a train report must not carry a confirmatory section")
    return _target(report, "train")


def _cause_text(causes: Mapping[str, str]) -> str:
    if not causes:
        return "없음"
    counts = Counter(causes.values())
    return ", ".join(f"{cause} {counts[cause]}" for cause in sorted(counts))


def _scope_line(report: Mapping[str, Any], target: Target) -> str:
    registered = _field(report, "registered")
    deadline = _field(report, "deadline")
    analysed = len(_field(target.section, "seeds")) if target.section is not None else 0
    budget = _nullable(target.registered, "budget") or _field(registered, "budget")
    return (
        f"대상 {_field(target.registered, 'extractor')} {_field(target.registered, 'version')}, "
        f"k={_field(registered, 'sentinel_count')}, budget {budget}. "
        f"등록 seed 블록 {len(_field(registered, 'seeds'))}, 분석 블록 {analysed}, "
        f"미완주 제외 {_field(deadline, 'number_excluded_seeds')}"
        f"({_cause_text(_field(deadline, 'causes'))})."
    )


def _t_first(section: Mapping[str, Any], arm: str) -> Mapping[str, Any]:
    return _field(section, "item5_first_contract_index", "by_arm", arm, "t_first_combined_c1_or_c2")


def _arm_rows(section: Mapping[str, Any], *, before_event: bool) -> list[list[object]]:
    rows: list[list[object]] = []
    for arm in sorted(_field(section, "item1_aborts", "by_arm"), key=_arm_key):
        aborts = _field(section, "item1_aborts", "by_arm", arm)
        states = _field(section, "record_states", "by_arm", arm)
        t_first = _t_first(section, arm)
        u_viol = _field(section, "item6_dense_signals", "by_arm", arm, "u_viol")
        row: list[object] = [
            arm,
            _field(t_first, "denominator_cells_in_risk_set"),
            _field(aborts, "number_complete"),
            _field(aborts, "number_abort") + _field(states, "no_record"),
        ]
        if before_event:
            row.append(_field(aborts, "number_abort_before_event"))
        row += [
            _field(states, "record_inconsistent"),
            _field(t_first, "number_observed"),
            _median(_nullable(t_first, "km_median_executions")),
            f"{_field(u_viol, 'mean_per_cell'):.2f}"
            f"({_field(u_viol, 'total_unique_c1_c2_fingerprints')})",
        ]
        rows.append(row)
    return rows


def _no_cells_line(report: Mapping[str, Any]) -> list[str]:
    """The empty table's sentence, true only when the deadline excluded every registered seed."""
    excluded = _field(report, "deadline", "number_excluded_seeds")
    registered = len(_field(report, "registered", "seeds"))
    if excluded != registered:
        raise TableInputError(f"no analysed cell, but {excluded} of {registered} seeds excluded")
    return ["분석 캠페인 0: 마감으로 모든 seed가 제외됐다."]


def t_exp3_1(inputs: "Inputs") -> list[str]:
    target = _train_target(inputs.report)
    lines = [
        "# 표 7-B. EXP-3 `role=train` arm별 (탐색, 기노출, 확증 아님)",
        "",
        _scope_line(inputs.report, target),
        "",
    ]
    if target.section is None:
        return [*lines, *_no_cells_line(inputs.report)]
    headers = [
        "arm",
        "분석 캠페인",
        "완주",
        "abort",
        "기록 어긋남",
        "첫 C1∨C2 사건",
        "T_first KM 중앙값",
        "U_viol 평균(합)",
    ]
    return [*lines, *_md_table(headers, _arm_rows(target.section, before_event=False))]


def _result_lines(cell_results: Path) -> list[Mapping[str, Any]]:
    """Whole lines of the exit record. Only a cut last line is forgiven; anything else stops."""
    if not cell_results.is_file():
        raise TableInputError(f"cell results not found: {cell_results}")
    lines = cell_results.read_text(encoding="utf-8").splitlines()
    records: list[Mapping[str, Any]] = []
    for position, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            if position != len(lines) - 1:
                raise TableInputError(f"{cell_results}: unreadable line {position + 1}") from error
    return records


def _run_span(records: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
    """First start and last end on the wall clock. Stop and resume lines do not end the run."""
    starts = [
        float(_field(row, "clocks", "realtime")) for row in records if row.get("event") == "start"
    ]
    ends = [
        float(_field(row, "clocks", "realtime")) for row in records if row.get("event") == "end"
    ]
    if not starts or not ends:
        raise TableInputError("cell results need start and end lines")
    return min(starts), max(ends)


def _stop_gaps(records: Sequence[Mapping[str, Any]]) -> float:
    """Seconds between each infrastructure stop and the resume that ended it."""
    total = 0.0
    stopped_at: float | None = None
    for row in records:
        if row.get("event") == "infrastructure-stop" and stopped_at is None:
            stopped_at = float(_field(row, "clocks", "realtime"))
        elif row.get("event") == "infrastructure-resume" and stopped_at is not None:
            total += float(_field(row, "clocks", "realtime")) - stopped_at
            stopped_at = None
    return total


def t_exp3_2(inputs: "Inputs") -> list[str]:
    report = inputs.report
    target = _train_target(report)
    if target.section is None:
        raise TableInputError("no analysed cell: the GO inputs cannot be computed")
    section = target.section
    events = sum(
        _field(_t_first(section, arm), "number_observed")
        for arm in _field(section, "item5_first_contract_index", "by_arm")
    )
    # Every attempted cell, not only analysed ones: an invalid cell ran and used host time. A cell
    # never started did not, so it stays out of the plan (exp3 section 5).
    completeness = _field(report, "cell_completeness")
    registered = _field(report, "registered")
    budget = _nullable(target.registered, "budget") or _field(registered, "budget")
    unattempted = _field(completeness, "unattempted")
    recorded = _field(completeness, "recorded_steps")
    planned = (_field(completeness, "cells") - unattempted) * budget
    records = _result_lines(inputs.cell_results)
    first_start, last_end = _run_span(records)
    if last_end <= first_start or not recorded or not planned:
        raise TableInputError("the run span and step counts must be positive")
    elapsed = last_end - first_start
    rate = recorded / (elapsed / 3600)
    gaps = _stop_gaps(records)
    if gaps >= elapsed:
        raise TableInputError("the stop gaps cannot exceed the run span")
    rate_without_gaps = recorded / ((elapsed - gaps) / 3600)
    ratio = recorded / planned
    deadline = datetime.fromisoformat(_field(report, "deadline", "execution_deadline"))
    remaining = (deadline.timestamp() - last_end) / 3600
    capacity = math.floor(remaining * rate / (GO_STEP_DIVISOR * ratio))
    failure_rate = _field(report, "cell_completeness", "infrastructure_failure_rate")
    rows = [
        ["E: train 첫 C1∨C2 캠페인(3 arm 합산, abort 포함, invalid 제외)", events, "≥ 1"],
        ["r: EXP-3 실경과 처리량(실시간, exec/h)", f"{rate:.0f}", "입력"],
        ["참고: 정지 공백 제외 r(실시간, exec/h)", f"{rate_without_gaps:.0f}", "GO 입력 아님"],
        ["e: 기록/계획 step 비율", _ratio(ratio), "입력"],
        ["H_rem: EXP-3 종료부터 실행 마감까지 호스트 시간(실시간, h)", f"{remaining:.1f}", "입력"],
        ["용량 ⌊H_rem·r÷(6000·e)⌋", capacity, "≥ 76"],
        ["인프라 실패 비율 (abort + 기록 어긋남)/전체 셀", _ratio(failure_rate), "≤ .45"],
        ["시작하지 않은 셀", unattempted, "기록"],
        ["결과", "", "W3가 적용해 LOG에 남긴다"],
    ]
    return ["# 표 7-B2. GO 판정 입력", "", *_md_table(["입력", "값", "기준"], rows)]


def _dense_table(title: str, report: Mapping[str, Any], target: Target) -> list[str]:
    lines = [title, "", _scope_line(report, target), ""]
    if target.section is None:
        return [*lines, *_no_cells_line(report)]
    section = target.section
    rows: list[list[object]] = []
    for arm in sorted(_field(section, "dense_signals_registered", "by_arm"), key=_arm_key):
        dense = _field(section, "dense_signals_registered", "by_arm", arm)
        rejected = _field(section, "item6_dense_signals", "by_arm", arm, "rejected_ratio", "value")
        failures = _field(dense, "observation_failures_by_kind")
        rows.append(
            [
                arm,
                f"{_field(dense, 'new_boundary_keys_per_cell', 'mean'):.2f}",
                f"{_field(dense, 'new_boundary_keys_per_cell', 'median'):g}",
                _field(dense, "unique_boundary_keys_in_arm"),
                _ratio(rejected),
                "; ".join(
                    f"{kind} {_field(failures, kind, 'total')}"
                    f"({_field(failures, kind, 'per_1000_steps'):.2f}/1000)"
                    for kind in sorted(failures)
                )
                or "0",
                _ratio(_field(dense, "feedback_ineligible_ratio", "value")),
            ]
        )
    headers = [
        "arm",
        "셀별 새 키 평균",
        "셀별 새 키 중앙값",
        "arm 안 고유 키",
        "rejected 비율",
        "관찰 실패 종류별 합(1000 step당)",
        "feedback_eligible=false 비율",
    ]
    return [*lines, *_md_table(headers, rows)]


def t_exp3_3(inputs: "Inputs") -> list[str]:
    target = _train_target(inputs.report)
    title = "# EXP-3 train dense 지표 (탐색, effectiveness 아님)"
    return _dense_table(title, inputs.report, target)


def t_exp2_1(inputs: "Inputs") -> list[str]:
    target = _target(inputs.report, "holdout")
    lines = ["# 표 7-A. EXP-2 `role=holdout` arm별", "", _scope_line(inputs.report, target), ""]
    if target.section is None:
        return [*lines, *_no_cells_line(inputs.report)]
    headers = [
        "arm",
        "분석 캠페인",
        "완주",
        "abort",
        "사건 전 abort",
        "기록 어긋남",
        "첫 C1∨C2 사건",
        "T_first KM 중앙값",
        "U_viol 평균(합)",
    ]
    return [*lines, *_md_table(headers, _arm_rows(target.section, before_event=True))]


def _rejected(value: object) -> str:
    if not isinstance(value, bool):
        raise TableInputError(f"reject_at_alpha must be true or false, not {value!r}")
    return "기각" if value else "비기각"


def _faster(contrast: Mapping[str, Any]) -> str:
    faster = _nullable(contrast, "faster_arm")
    if faster is not None:
        return faster
    return "없음" if _field(contrast, "total_events") == 0 else "동률"


def _permutation_p(contrast: Mapping[str, Any]) -> str:
    value = _nullable(contrast, "permutation", "p_value")
    return "미검정" if value is None else _p(value)


def _contrasts(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    contrasts = _field(report, "confirmatory", "contrasts")
    return sorted(contrasts, key=lambda contrast: _field(contrast, "order"))


def t_exp2_2(inputs: "Inputs") -> list[str]:
    _target(inputs.report, "holdout")
    rows = [
        [
            _field(contrast, "contrast"),
            _field(contrast, "number_seed_blocks"),
            _field(contrast, "informative_blocks"),
            _field(contrast, "total_events"),
            _permutation_p(contrast),
            _p(_field(contrast, "holm_adjusted_p")),
            _rejected(_field(contrast, "reject_at_alpha")),
            _faster(contrast),
            _field(contrast, "u_viol_direction"),
            _rejected(_field(contrast, "abort_policy_results", "exclude", "reject_at_alpha")),
            _rejected(
                _field(contrast, "abort_policy_results", "censor-at-budget", "reject_at_alpha")
            ),
        ]
        for contrast in _contrasts(inputs.report)
    ]
    headers = [
        "대비",
        "seed 블록",
        "I (정보 블록)",
        "E (사건)",
        "순열 p",
        "Holm p",
        "기각",
        "빠른 쪽",
        "U_viol 방향",
        "exclude 기각",
        "censor-at-budget 기각",
    ]
    return [
        "# 표 7-A2. 대비별 확증 결과 (Holm 순서, 1차 정책 censor-at-abort)",
        "",
        *_md_table(headers, rows),
        "",
        "**판정:** (사람이 D040-D12 표를 읽어 고른다. 생성기는 채우지 않는다.)",
    ]


def _hand_input(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise TableInputError(f"hand input not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def t_exp2_3(inputs: "Inputs") -> list[str]:
    report = inputs.report
    _target(report, "holdout")
    hand = _hand_input(inputs.hand_input)
    completeness = _field(report, "cell_completeness")
    deadline = _field(report, "deadline")
    unknown = _field(report, "unknown_outcome_steps")
    sensitivity = _field(report, "record_inconsistent_sensitivity")
    stop = _field(hand, "operating_stop")
    # The stub sees only a target whose result was dropped; docker events see the rest.
    lost = _field(hand, "abort_split", "lost_after_execution")
    lower_bound = _field(unknown, "lost_after_execution_lower_bound")
    if lost < lower_bound:
        raise TableInputError(f"hand lost_after_execution {lost} is below the stubs' {lower_bound}")
    cut = _field(unknown, "watchdog_cut_line")
    lines = [
        "# EXP-2 holdout 표 아래 병기 (0이어도 적는다)",
        "",
        f"- 미완주 제외 seed {_field(deadline, 'number_excluded_seeds')}, "
        f"셀별 원인: {_cause_text(_field(deadline, 'causes'))}",
        *(f"  - {run_id}: {cause}" for run_id, cause in sorted(_field(deadline, "causes").items())),
        f"- 기록 어긋남 {_field(completeness, 'record_inconsistent')}, "
        f"민감도: {_field(sensitivity, 'summary')}",
        "- abort 3분할(W2 손 입력, 분석기 값 아님): "
        f"target 미시작 {_field(hand, 'abort_split', 'target_not_started')}, "
        f"실행 후 소실 {lost}, "
        f"첫 오류 미확인 {_field(hand, 'abort_split', 'first_error_unconfirmed')}",
        f"- no-record {_field(completeness, 'no_record')}",
        f"- watchdog 사유 {_field(completeness, 'watchdog')}",
        f"- 결과 미상 step: 실행 후 소실 {lost}(스텁 하한 {lower_bound}), "
        f"watchdog 잘린 줄 {cut}, 합계 {lost + cut}",
        f"- 인프라 정지 {len(_field(completeness, 'infrastructure_stops'))}, "
        f"재개 {len(_field(completeness, 'infrastructure_resumes'))}",
        "- 대비별 invalid 제외: "
        + ", ".join(
            f"{_field(contrast, 'contrast')} {_field(contrast, 'number_blocks_invalid_excluded')}"
            for contrast in _contrasts(report)
        ),
        f"- 운영 중단: {'발동' if _field(stop, 'fired') else '발동 없음'}"
        + (f", 시각 {_field(stop, 'time')}" if _field(stop, "fired") else ""),
    ]
    return lines


def t_exp2_4(inputs: "Inputs") -> list[str]:
    target = _target(inputs.report, "holdout")
    lines = ["# EXP-2 holdout abort 정책 민감도", ""]
    if target.section is None:
        return [*lines, *_no_cells_line(inputs.report)]
    section = target.section
    sensitivity = _field(section, "item5_first_contract_index", "sensitivity")
    rows: list[list[object]] = []
    for arm in sorted(_field(section, "item5_first_contract_index", "by_arm"), key=_arm_key):
        t_first = _t_first(section, arm)
        rows.append(
            [
                arm,
                _field(sensitivity, "primary_policy"),
                _field(t_first, "number_observed"),
                _field(t_first, "number_right_censored"),
                _field(t_first, "denominator_cells_in_risk_set"),
                _median(_nullable(t_first, "km_median_executions")),
            ]
        )
        for policy in ("exclude", "censor-at-budget"):
            values = _field(sensitivity, "policies", policy, "by_arm", arm)
            rows.append(
                [
                    arm,
                    policy,
                    _field(values, "number_observed"),
                    _field(values, "number_right_censored"),
                    _field(values, "number_in_risk_set"),
                    _median(_nullable(values, "km_median_executions")),
                ]
            )
    headers = ["arm", "정책", "관찰 사건", "우측절단", "위험 집합", "T_first KM 중앙값"]
    lines += _md_table(headers, rows)
    independence = inputs.report.get("arm_abort_independence")
    if independence is not None:
        lines += ["", f"arm·abort 독립성: {json.dumps(independence, sort_keys=True)}"]
    return lines


def t_exp2_5(inputs: "Inputs") -> list[str]:
    target = _target(inputs.report, "holdout")
    lines = ["# EXP-2 holdout 인프라 측정", "", MONOTONIC_NOTE, ""]
    if target.section is None:
        return [*lines, *_no_cells_line(inputs.report)]
    section = target.section
    pooled = _field(section, "item2_p95_full_step", "pooled")
    summed = _field(section, "item3_throughput", "summed")
    environment = _field(section, "environment")
    rows = [
        ["full step p50 (monotonic s)", f"{_field(pooled, 'p50_seconds'):.3f}"],
        ["full step p95 (monotonic s)", f"{_field(pooled, 'p95_seconds'):.3f}"],
        ["full step 최대 (monotonic s)", f"{_field(pooled, 'max_seconds'):.3f}"],
        ["step 수", _field(pooled, "number_steps")],
        ["셀 수", _field(summed, "number_cells")],
        ["실행 수", _field(summed, "executions")],
        ["스트림당 exec/h (monotonic)", f"{_field(summed, 'exec_per_hour'):.0f}"],
        ["환경 동일", _field(environment, "homogeneous")],
    ]
    return [
        *lines,
        *_md_table(["항목", "값"], rows),
        "",
        f"환경: {json.dumps(_field(environment, 'distinct'), sort_keys=True, ensure_ascii=False)}",
    ]


def t_exp2_6(inputs: "Inputs") -> list[str]:
    target = _target(inputs.report, "holdout")
    title = "# EXP-2 holdout dense 지표 (탐색, effectiveness 아님)"
    return _dense_table(title, inputs.report, target)


@dataclass(frozen=True, slots=True)
class Inputs:
    report: Mapping[str, Any]
    cell_results: Path
    hand_input: Path


@dataclass(frozen=True, slots=True)
class Table:
    render: Callable[[Inputs], list[str]]
    report: Path
    output: str


TABLES: Mapping[str, Table] = {
    "T-EXP3-1": Table(t_exp3_1, TRAIN_REPORT, "paper/tables/exp3-train-arms.md"),
    "T-EXP3-2": Table(t_exp3_2, TRAIN_REPORT, "paper/tables/exp3-go-inputs.md"),
    "T-EXP3-3": Table(t_exp3_3, TRAIN_REPORT, "paper/tables/exp3-dense-signals.md"),
    "T-EXP2-1": Table(t_exp2_1, HOLDOUT_REPORT, "paper/tables/exp2-holdout-arms.md"),
    "T-EXP2-2": Table(t_exp2_2, HOLDOUT_REPORT, "paper/tables/exp2-holdout-contrasts.md"),
    "T-EXP2-3": Table(t_exp2_3, HOLDOUT_REPORT, "paper/tables/exp2-holdout-notes.md"),
    "T-EXP2-4": Table(t_exp2_4, HOLDOUT_REPORT, "paper/tables/exp2-abort-sensitivity.md"),
    "T-EXP2-5": Table(t_exp2_5, HOLDOUT_REPORT, "paper/tables/exp2-infra.md"),
    "T-EXP2-6": Table(t_exp2_6, HOLDOUT_REPORT, "paper/tables/exp2-dense-signals.md"),
}


def render(artifact: str, inputs: Inputs) -> str:
    return "\n".join(TABLES[artifact].render(inputs)) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, choices=sorted(TABLES))
    parser.add_argument("--report", type=Path, help="analyze_exp0 --index --format json output")
    parser.add_argument("--cell-results", type=Path, default=TRAIN_CELL_RESULTS)
    parser.add_argument("--hand-input", type=Path, default=HOLDOUT_HAND_INPUT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args(argv)
    try:
        report = _load_report(args.report or TABLES[args.artifact].report)
        text = render(args.artifact, Inputs(report, args.cell_results, args.hand_input))
    except TableInputError as error:
        print(f"{args.artifact}: {error}", file=sys.stderr)
        return 2
    if args.check is not None:
        if args.check.read_text(encoding="utf-8") == text:
            print(f"{args.artifact} byte-identical: {args.check}")
            return 0
        print(f"{args.artifact} DIFFERS from generated: {args.check}", file=sys.stderr)
        return 1
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Benchmark design v2 against frozen v1: only the listed lines moved, every threshold stayed.

The driver refuses v2's measured seeds until its pilot-seed exception lands, so these tests read
the design block directly. Parsing v2 end to end is tested with the exception itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import run_concurrency_benchmark as bench

from inodefence.evaluation.independence import arm_abort_independence

CONFIGS = Path(__file__).resolve().parents[1] / "experiments" / "configs"
V1_TEXT = (CONFIGS / "concurrency-scaling-v1.md").read_text(encoding="utf-8")
V2_TEXT = (CONFIGS / "concurrency-scaling-v2.md").read_text(encoding="utf-8")
#: A row keeps its text in v2 unless the design says why it moved.
UNCHANGED_ROWS = (
    "| V2 |",
    "| V3 |",
    "| V4 |",
    "| V6 |",
    "| V7 |",
    "| V8 |",
    "| V10 |",
    "| H1 |",
    "| H2 |",
    "| H3 |",
    "| H4 |",
    "| H5 |",
)


def _row(text: str, start: str) -> str:
    rows = [line for line in text.splitlines() if line.startswith(start)]
    assert len(rows) == 1, start
    return rows[0]


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end)]


def test_block_differs_from_v1_only_in_id_seeds_and_the_dropped_arm() -> None:
    v1, v2 = bench._parse_block(V1_TEXT), bench._parse_block(V2_TEXT)
    changed = {key for key in v1.keys() & v2.keys() if v1[key] != v2[key]}
    assert changed == {"design_id", "seeds"}
    assert v1.keys() - v2.keys() == {"arm.R-walk"}
    assert v2.keys() - v1.keys() == set()
    assert v2["design_id"] == "concurrency-scaling-v2"
    assert v2["seeds"] == "8110, 8102, 8103, 8106"
    assert v2["smoke_seed"] == "6100"


def test_a_block_stays_twelve_cells_with_the_crossed_first_stage() -> None:
    v2 = bench._parse_block(V2_TEXT)
    arms = [key for key in v2 if key.startswith(bench.ARM_PREFIX)]
    assert sorted(arms) == ["arm.D", "arm.R-restart", "arm.S-u"]
    assert len(arms) * len(v2["seeds"].split(",")) == 12
    assert v2["stage.A"] == "2,4,4,2"


@pytest.mark.parametrize("start", UNCHANGED_ROWS)
def test_decision_rows_keep_their_v1_text(start: str) -> None:
    assert _row(V2_TEXT, start) == _row(V1_TEXT, start)


def test_stop_conditions_keep_their_v1_text() -> None:
    assert _section(V2_TEXT, "## 5. 중단 조건", "## 6. 판정") == _section(
        V1_TEXT, "## 5. 중단 조건", "## 6. 판정"
    )


def test_v9_keeps_its_v1_conditions_and_adds_the_comparison_rule() -> None:
    v1_condition = _row(V1_TEXT, "| V9 |").split(" | ")[2]
    row = _row(V2_TEXT, "| V9 |")
    assert row.split(" | ")[2].startswith(v1_condition)
    assert "한 블록에서 비교 불가 셀이 2개 이상" in row
    assert "기준 블록 셀 없음" in row and "이 블록 셀 없음" in row


def test_unmeasured_reference_is_not_a_pass_and_gives_no_fallback() -> None:
    row = _row(V2_TEXT, "| H3-unmeasured |")
    assert "통과가 아니다" in row
    assert "`selected_jobs=null`" in row and "`fallback_jobs=null`" in row
    assert "`status=halted`" in row


@pytest.mark.parametrize(
    ("counts", "expected", "flagged"),
    [
        ((4, 0, 0), 0.020, True),
        ((3, 0, 0), 0.083, True),
        ((4, 1, 1), 0.278, False),
        ((2, 0, 0), 0.304, False),
    ],
)
def test_v5_examples_are_the_values_of_the_rule(
    counts: tuple[int, int, int], expected: float, flagged: bool
) -> None:
    matrix = [[8 - count, count, 0] for count in counts]
    result = arm_abort_independence(matrix, ["R-restart", "D", "S-u"])
    p_value = result["primary_arm_vs_abort"]["p_value"]
    assert p_value == pytest.approx(expected, abs=0.002)
    assert (p_value <= 0.10) is flagged
    row = _row(V2_TEXT, "| V5 |")
    assert str(counts).replace(" ", "") in row
    assert f"{expected:.3f}".rstrip("0").lstrip("0") in row


def test_rotation_sentence_names_the_seeds_that_start_with_r() -> None:
    v2 = bench._parse_block(V2_TEXT)
    seeds = [item.strip() for item in v2["seeds"].split(",")]
    arms = 3
    first = [(position, seed) for position, seed in enumerate(seeds) if position % arms == 0]
    assert [seed for _, seed in first] == ["8110", "8106"]
    assert "R-restart가 8110·8106에서 먼저 시작한다" in V2_TEXT


def test_v2_runs_nothing_under_the_v1_name() -> None:
    assert "concurrency-scaling-v1" not in V2_TEXT
    assert "DESIGN=experiments/configs/concurrency-scaling-v2.md" in V2_TEXT
    assert "OUT=$HOME/inodefence-benchmarks/concurrency-scaling-v2" in V2_TEXT
    assert "arm.R-walk" not in V2_TEXT


def test_abort_rate_stays_out_of_exp3_planning() -> None:
    sealing = _section(V2_TEXT, "### 6.6 raw 봉인", "## 7. 실행 전 점검표")
    assert "D1~D21" in sealing and "D1~D20" not in sealing
    assert "이번 a를 EXP-3 abort 추정과 n에 쓰지 않는다" in sealing
    assert "common_prefix를 파일럿 사건 위치와 결합해 재실행 사건 수를 만들지 않는다" in sealing
    assert "max(파일럿 a" not in V2_TEXT


def test_planning_abort_and_restart_condition_are_defined() -> None:
    assert "계획 a는 파일럿 .275, 상한 .43이다." in V2_TEXT
    assert "벤치마크 a는 seed를 abort 이력으로 골랐으므로 계획 a에 넣지 않는다." in V2_TEXT
    assert "용량 판단은 EXP-3 train 실측 e와 abort(GO)로 한다." in V2_TEXT
    assert "jobs=2 **24셀 전체** 값을 쓰고," in V2_TEXT
    assert "파일럿에서 abort한 6개 조합(2블록 12셀)을 뺀 12셀 값을 병기한다." in V2_TEXT
    assert "제외값이 .30 이하이면 입력 쪽을 먼저 본다" in V2_TEXT


def test_jobs_max_comes_from_this_benchmark() -> None:
    assert "`jobs_max = 2`" not in V2_TEXT
    assert "등록 초안의 `jobs_max`는 `TBD-FREEZE`이고" in V2_TEXT
    row = _row(V2_TEXT, "| `jobs_max` |")
    assert "`selected_jobs`로 채운다" in row
    assert "H3이면 `fallback_jobs` 2다" in row
    assert "H1, H2, H5, H3-unmeasured, 측정 무효로 값이 없으면 지웅 결정을 기록한다" in row


def test_operating_stop_points_to_the_adopted_rule() -> None:
    assert "처음 15캠페인에서 8건" not in V2_TEXT
    row = _row(V2_TEXT, "| **실행 중 중단** |")
    assert "D040과 D041" in row and "최근 24시간 종료 셀 20개 이상일 때 abort ≥ .60" in row
    assert "재개는 지웅 결정으로 같은 설정 또는 jobs=2로만" in row


def test_pilot_comparison_is_reported_not_a_halt() -> None:
    assert "| 파일럿 재현 |" in V2_TEXT
    section = _section(V2_TEXT, "**파일럿 대조", "### 6.6 raw 봉인")
    assert "H2에 넣지 않는다" in section
    assert "시험 안 됨" in section
    assert "자동 정지가 아니다" in section
    assert "m=0이면 재발을 언급하지 않는다" in section
    assert "스크립트는 단계 끝에 1회 돌린다" in section


def test_host_record_is_present_and_there_is_no_alternative_procedure() -> None:
    assert "재부팅 여부(기본: 재부팅 안 함)" in V2_TEXT
    assert "부록" not in V2_TEXT and "5040" not in V2_TEXT and "C′" not in V2_TEXT
    assert "대체 절차는 없다. 시작이 늦어지면 보고하고 지웅이 결정한다(D041)." in V2_TEXT

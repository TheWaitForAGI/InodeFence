"""Guards of the capstone report form fill plan. No Node, HWP file or personal value is used."""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

HWP_DIR = Path(__file__).resolve().parents[1] / "paper/deliverables/hwp"
SPEC = importlib.util.spec_from_file_location("fill_form", HWP_DIR / "fill_form.py")
assert SPEC is not None and SPEC.loader is not None
fill_form = importlib.util.module_from_spec(SPEC)
sys.modules["fill_form"] = fill_form
SPEC.loader.exec_module(fill_form)

CELL_MAP = json.loads((HWP_DIR / "cell-map.json").read_text(encoding="utf-8"))
HEADER_KEYS = [
    "단과대학",
    "주관학과",
    "담당교수",
    "교과목명",
    "분반",
    "팀명",
    "팀장",
    "팀원",
    "R- (Research)",
]


def plan_for(values: dict) -> Any:
    return fill_form.build_plan(CELL_MAP, fill_form.parse_body(fill_form.DEFAULT_BODY), values)


def written_rows(plan: Any) -> dict[int, str]:
    col = CELL_MAP["project_type_col"]
    rows = CELL_MAP["project_type_rows"].values()
    return {op["row"]: op["text"] for op in plan.cell_ops if op["col"] == col and op["row"] in rows}


def test_guard_sees_placeholders_in_cells_that_are_not_restyled() -> None:
    found = fill_form.placeholders_written(plan_for({}))
    for name in ("단과대학", "주관학과", "담당교수", "교과목명", "분반"):
        assert f"[사람:{name}]" in found
    for name in ("R 결과물", "P 결과물", "SS 결과물"):
        assert f"[사람:{name}]" in found


def test_guard_clears_header_placeholders_once_given() -> None:
    values = {key: "시험값" + str(index) for index, key in enumerate(HEADER_KEYS)}
    found = fill_form.placeholders_written(plan_for(values))
    assert not [
        text
        for text in found
        if text.startswith("[사람:") and "사용" not in text and "시작일" not in text
    ]


def test_markup_guard_covers_cells_that_are_not_restyled() -> None:
    with pytest.raises(SystemExit):
        fill_form.reject_markup(plan_for({"분반": "**1**"}))


@pytest.mark.parametrize(
    ("value", "row"),
    [
        ("문제해결", 4),
        ("비융합·문제해결", 4),
        ("비융합 지역사회연계", 6),
        ("융합·지역사회 연계", 9),
        ("지역사회 연계", 9),
    ],
)
def test_project_type_marks_only_its_row(value: str, row: int) -> None:
    marks = written_rows(plan_for({"프로젝트 유형": value}))
    assert [mark_row for mark_row, text in marks.items() if text == "○"] == [row]


@pytest.mark.parametrize(
    "value",
    ["융합·지역사회연계", "비융합·지역사회 연계", "비융합·사회맞춤형", "융합·문제해결", "없는유형"],
)
def test_project_type_mismatch_is_refused_without_echoing_the_value(value: str) -> None:
    with pytest.raises(SystemExit) as refused:
        plan_for({"프로젝트 유형": value})
    assert value not in str(refused.value)


def test_linkage_cell_is_cleared_only_for_types_that_do_not_require_it() -> None:
    row = CELL_MAP["blocks"][fill_form.LINKAGE_BLOCK]["row"]
    cleared = plan_for({"프로젝트 유형": "비융합·문제해결"}).expected[(row, 0)]
    kept = plan_for({"프로젝트 유형": "비융합·산학연계"}).expected[(row, 0)]
    section = fill_form.parse_body(fill_form.DEFAULT_BODY)[fill_form.LINKAGE_BLOCK]
    assert cleared == []
    assert kept == [line.text for line in fill_form.prose_lines(section)]

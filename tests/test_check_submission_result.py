"""Result-sentence guard of the submission checker. Uses a synthetic d12 and claim row only."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

DELIV = Path(__file__).resolve().parents[1] / "paper/deliverables"
SPEC = importlib.util.spec_from_file_location("check_submission", DELIV / "check_submission.py")
assert SPEC is not None and SPEC.loader is not None
cs = importlib.util.module_from_spec(SPEC)
sys.modules["check_submission"] = cs
SPEC.loader.exec_module(cs)

CELL = "분리 실패, HR 2 배제"
ABSTRACT = (
    "S-u는 R·D 어느 쪽과도 구분되지 않았고, "
    "위험률 비 2 이상의 가속은 구간으로 배제됐다(결함 깊이 1 벤치마크)."
)
FULL = (
    "두 대비 모두 차이를 확인하지 못했다(Holm 보정 p .9, .9). "
    "결과는 이 벤치마크에 한정되며, 일반의 결론이 아니다."
)
D12 = f'## 칸 "{CELL}" (설명)\n- abstract: 「{ABSTRACT}」\n'
ROW = f"| S-HOLDOUT | 확증 판정 | 채움(D12 칸 「{CELL}」) | 「{FULL}」 요약: 「{ABSTRACT}」 |\n"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    claims = tmp_path / "claims.md"
    claims.write_text(ROW, encoding="utf-8")
    monkeypatch.setattr(cs, "CLAIMS", claims)
    d12 = tmp_path / "d12.md"
    d12.write_text(D12, encoding="utf-8")

    def run(status: str, text: str) -> str:
        values = tmp_path / "values.json"
        values.write_text(
            json.dumps({"status": status, "d12": {"cell_proposed": CELL, "placeholders": {}}}),
            encoding="utf-8",
        )
        cs.results.clear()
        cs.check_result(values, d12, {"HWP": text}, "", final=False)
        return next(s for s, name, _ in cs.results if name == "HWP carries the result sentence")

    return run


def test_row_quotes_come_from_the_last_column_only(setup):
    assert cs.holdout_row_sentences() == [FULL, ABSTRACT]


def test_cell_name_alone_is_not_a_result_sentence(setup):
    assert setup("unsealed", f"판정표 칸은 「{CELL}」이다.") == "FAIL"


def test_full_row_sentence_passes_when_released(setup):
    assert setup("unsealed", "본문 " + FULL + " 끝") == "PASS"


def test_full_row_sentence_does_not_pass_a_sealed_run(setup):
    assert setup("미해제", "본문 " + FULL + " 끝") == "FAIL"

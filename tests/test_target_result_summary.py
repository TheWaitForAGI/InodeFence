"""One-page summary of an inodefence-target-result-v1 file: content, determinism, failures."""

from pathlib import Path

import pytest

from inodefence.target_result import (
    RUN_ERROR,
    CaseVerdict,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)
from inodefence.target_result_summary import main, render_summary, summarize_file

TAR = b"saved-input"
SHA = "a" * 40


def _write(tmp_path: Path, *cases: CaseVerdict, dirty: bool = False) -> Path:
    cases = cases or (
        CaseVerdict("toplevel_hardlink", "resolved", None, True, True),
        CaseVerdict("nested_hardlink", "declined", None, False, False),
    )
    result = TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.2"),
        mode=ResultMode.FIXTURE_REGRESSION,
        observed_contracts=("C1", "C2"),
        cases=cases,
        repro_inputs=(repro_input(cases[0].case_id, "inputs/first.tar", TAR),),
        provenance=Provenance(SHA, dirty, "inodefence-node:local", None),
    )
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "first.tar").write_bytes(TAR)
    path = tmp_path / "result.json"
    path.write_text(result.dumps(), encoding="utf-8")
    return path


def test_summary_states_target_version_verdict_and_repro(tmp_path: Path) -> None:
    text = summarize_file(_write(tmp_path))
    assert text.startswith("# 결과 한 장 요약: node-tar 7.5.2\n")
    assert "**FAIL** — 2건 중 1건에서" in text
    assert "| 대상 버전 | `7.5.2` |" in text
    assert "| 런타임 버전 | 해당 없음 |" in text
    assert "**C0** " in text and "이 실행 방식은 관찰하지 않음" in text
    assert "| `toplevel_hardlink` | `resolved` | 관찰 안 함 | **위반** | **위반** |" in text
    assert "| `nested_hardlink` | `declined` | 관찰 안 함 | 이상 없음 | 이상 없음 |" in text
    assert f"`{SHA}`를 체크아웃" in text
    assert "`inodefence-node:local`" in text
    assert "| `inputs/first.tar` |" in text
    assert "일치함을 확인했다" in text
    assert "demo run" in text


def test_summary_is_deterministic_and_has_no_absolute_paths(tmp_path: Path) -> None:
    path = _write(tmp_path)
    first = summarize_file(path)
    assert first == summarize_file(path)
    assert str(tmp_path) not in first


def test_pass_is_not_a_safety_claim_and_dirty_tree_is_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        CaseVerdict("only", "declined", None, False, False),
        dirty=True,
    )
    text = summarize_file(path)
    assert "**PASS**" in text and "안전하다는 증명은 아니다" in text
    assert "커밋 안 된 변경" in text


def test_run_error_gives_error_headline(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        CaseVerdict("ok", "declined", None, False, False),
        CaseVerdict("broken", RUN_ERROR, None, None, None),
    )
    text = summarize_file(path)
    assert "**ERROR** — 2건 중 1건이 실행 오류" in text
    assert "| `broken` | 실행 오류 | 관찰 안 함 | 관찰 안 함 | 관찰 안 함 |" in text


def test_target_text_cannot_break_the_table() -> None:
    result = TargetResult(
        target="x",
        axes=TargetAxes(),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0",),
        cases=(CaseVerdict("a|b", "out`come", False, None, None),),
        repro_inputs=(),
        provenance=Provenance(None, False),
    )
    text = render_summary(result, source_name="r.json", inputs_verified=True)
    assert "| `a\\|b` | `outʼcome` | 이상 없음 |" in text
    assert "엔진 커밋: 기록 없음" in text
    assert "저장된 입력 TAR가 없다" in text


def test_cli_writes_file_and_rejects_tampered_input(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path)
    out = tmp_path / "summary.md"
    assert main([str(path), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == summarize_file(path)

    (tmp_path / "inputs" / "first.tar").write_bytes(b"changed")
    assert main([str(path)]) == 2
    assert "hash mismatch" in capsys.readouterr().err

    assert main([str(path), "--no-verify-inputs"]) == 0
    assert "대조하지 않았다" in capsys.readouterr().out


@pytest.mark.parametrize("content", ["not json", '{"schema": "other"}'])
def test_cli_rejects_invalid_result(tmp_path: Path, content: str, capsys) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    assert main([str(path)]) == 2
    assert capsys.readouterr().err.startswith("error: ")

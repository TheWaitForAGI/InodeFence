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
    Verdict,
    repro_input,
)
from inodefence.target_result_summary import (
    main,
    render_summary,
    summarize_file,
    write_cell_summaries,
)

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
    assert text.startswith("# 결과 한 장 요약: x\n")
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


def test_title_names_runtime_and_filter_axes() -> None:
    result = TargetResult(
        target="python-tarfile",
        axes=TargetAxes(runtime_version="3.12.16", extraction_filter="data"),
        mode=ResultMode.FIXTURE_REGRESSION,
        observed_contracts=("C1", "C2"),
        cases=(CaseVerdict("only", "declined", None, False, False),),
        repro_inputs=(),
        provenance=Provenance(None, False),
    )
    text = render_summary(result, source_name="r.json", inputs_verified=True)
    assert text.startswith("# 결과 한 장 요약: python-tarfile 3.12.16 · data\n")


def test_write_cell_summaries_writes_beside_each_result_and_never_overwrites(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path)
    assert write_cell_summaries([path]) == [tmp_path / "summary.md"]
    assert (tmp_path / "summary.md").read_text(encoding="utf-8") == summarize_file(path)
    with pytest.raises(FileExistsError):
        write_cell_summaries([path])
    assert write_cell_summaries([]) == []


def test_campaign_summary_shows_aggregates_and_violations_not_per_case(tmp_path) -> None:
    from inodefence.target_result import CampaignInfo

    result = TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.8"),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cases=(CaseVerdict("step-742", "extracted", False, True, True),),  # violations only
        repro_inputs=(repro_input("step-742", "inputs/step-742.tar", b"viol"),),
        provenance=Provenance("a" * 40, False, "inodefence-node-tar-registry:7.5.8", None),
        campaign=CampaignInfo(
            seed=123,
            budget=None,
            runs_to_first_violation=742,
            runs_executed=1000,
            errors=2,
            unjudged_steps=2,
            stopped_early=True,
        ),
    )
    text = render_summary(result, source_name="result.json", inputs_verified=True)
    assert "## 탐색 결과 (집계와 위반 케이스)" in text
    assert "## 케이스별 결과" not in text  # no per-case table for a campaign
    assert "1000번 실행해 1건에서 위반" in text
    assert "멈출 때까지 (상한 없음)" in text
    assert "742번째" in text
    assert "사람이 예산 소진 전에 멈춤" in text
    assert "| `step-742` | 이상 없음 | **위반** | **위반** | `inputs/step-742.tar` |" in text


def test_campaign_summary_surfaces_unjudged_count_and_ceiling(tmp_path) -> None:
    from inodefence.target_result import CampaignInfo

    result = TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.8"),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cases=(),  # every run went un-judged: no violations kept
        repro_inputs=(),
        provenance=Provenance("a" * 40, False, "inodefence-node-tar-registry:7.5.8", None),
        campaign=CampaignInfo(
            seed=123,
            budget=None,
            runs_to_first_violation=None,
            runs_executed=8,
            errors=0,
            unjudged_steps=6,
            max_unjudged_ratio=0.5,
        ),
    )
    assert result.verdict is Verdict.ERROR  # 6/8 = 0.75 over the 0.5 ceiling
    text = render_summary(result, source_name="result.json", inputs_verified=True)
    assert "미판정 실행 | 6건 (비율 0.75)" in text
    assert "미판정 상한 | 0.5" in text
    # The narrative must say an un-judged run is not a clean one.
    assert "‘위반 없음’이 아니라 ‘보지 못함’" in text
    assert "미판정 8건·비율" not in text  # count is 6, not the run total


def test_campaign_summary_separates_termination_and_marks_repro_checks() -> None:
    from inodefence.target_result import JUDGED, CampaignInfo

    timeout_hit = CaseVerdict("step-9", JUDGED, None, True, False, "timed_out", True)
    clean_hit = CaseVerdict("step-12", JUDGED, None, False, True, "success", True)
    result = TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.1"),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cases=(timeout_hit, clean_hit),
        repro_inputs=(
            repro_input("step-9", "inputs/step-9.tar", b"t"),
            repro_input("step-12", "inputs/step-12.tar", b"s"),
        ),
        provenance=Provenance("a" * 40, False, "inodefence-node-tar-registry:7.5.1", None),
        campaign=CampaignInfo(
            seed=1,
            budget=40,
            runs_to_first_violation=10,
            runs_executed=40,
            terminations={"success": 20, "rejected": 15, "failed": 2, "timed_out": 3},
        ),
    )
    assert result.verdict is Verdict.FAIL  # 15 rejections + 3 timeouts do not make it ERROR
    text = render_summary(result, source_name="result.json", inputs_verified=True)
    assert "| 종료 상태 | 성공 20건 · 거절 15건 · 실패(비정상 종료) 2건 · 시간 초과 3건 |" in text
    assert "| 시간 초과 | 완결 | **재현 확인 필요** |" in text
    assert "| 성공 | 완결 | — |" in text
    assert "**재현 확인 필요 1건:**" in text


def test_campaign_error_headline_names_unjudged_not_terminations() -> None:
    from inodefence.target_result import RUN_ERROR, CampaignInfo

    blind = tuple(CaseVerdict(f"s{i}", RUN_ERROR, None, None, None) for i in range(4))
    result = TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.1"),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cases=blind,
        repro_inputs=(),
        provenance=Provenance("a" * 40, False, "inodefence-node-tar-registry:7.5.1", None),
        campaign=CampaignInfo(seed=1, budget=4, runs_to_first_violation=None),
    )
    assert result.verdict is Verdict.ERROR
    text = render_summary(result, source_name="result.json", inputs_verified=True)
    assert "**ERROR** — 4건 중 4건에서 오라클이 평가되지 못했다(미판정 비율 1.0)" in text
    assert "기록 없음 4건" in text  # no termination recorded for runs the harness never observed

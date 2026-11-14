"""One-page plain-language summary of an ``inodefence-target-result-v1`` file.

Input is the result file only: this module reads it with the strict reader in
:mod:`inodefence.target_result` and renders Markdown that a reader outside security research can
follow — which program and version were tested, the overall verdict, what each contract checks,
per-case results, and how to reproduce the run. It never runs a target and adds no value the file
does not hold. The output is deterministic (no clock, no absolute paths): the same file gives the
same page.

Usage::

    python -m inodefence.target_result_summary RESULT.json [-o SUMMARY.md] [--no-verify-inputs]

``make target-run`` calls :func:`write_cell_summaries` after it has written the results, so each
cell that got a verdict also has ``<cell>/summary.md`` next to its ``result.json``. A cell with no
``result.json`` (image preparation failed, image changed) gets no summary.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from inodefence.target_result import (
    CONTRACTS,
    RUN_ERROR,
    ResultMode,
    TargetResult,
    TargetResultError,
    Verdict,
    load_target_result,
)

#: Plain-language meaning of each contract (from docs/research/design/security-contracts.md).
CONTRACT_PLAIN = {
    "C0": "경로 경계 — 압축을 푼 폴더 밖에서 파일·폴더가 새로 생기거나, 지워지거나, 바뀌면 위반",
    "C1": (
        "객체 동일성 — 압축을 푼 파일이 보호 대상 외부 파일과 같은 실제 파일(inode)을 가리키면 위반"
    ),
    "C2": "외부 영향 — 보호 대상 외부 파일의 내용·크기·권한 같은 속성이 바뀌면 위반",
}

MODE_PLAIN = {
    ResultMode.FIXTURE_REGRESSION: (
        "고정 입력 회귀(fixture-regression): 미리 만든 입력 TAR를 하나씩 한 번 실행"
    ),
    ResultMode.CAMPAIGN: (
        "탐색 캠페인(campaign): 정해진 횟수 안에서 입력을 바꿔 가며 반복 실행, 한 번이 한 케이스"
    ),
}

NOT_APPLICABLE = "해당 없음"


def _cell(text: str) -> str:
    """Make target-supplied text safe inside one Markdown table cell."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _code(text: str) -> str:
    return f"`{_cell(text).replace('`', 'ʼ')}`"


def _contract_cell(value: bool | None) -> str:
    if value is None:
        return "관찰 안 함"
    return "**위반**" if value else "이상 없음"


TERMINATION_PLAIN = {
    "success": "성공",
    "rejected": "거절",
    "failed": "실패(비정상 종료)",
    "timed_out": "시간 초과",
}


def _termination_cell(value: str | None) -> str:
    return TERMINATION_PLAIN.get(value, value) if value is not None else "기록 없음"


def _observation_cell(value: bool | None) -> str:
    return {True: "완결", False: "**불완전**", None: "기록 없음"}[value]


def _termination_line(result: TargetResult) -> str:
    counts = result.termination_counts
    parts = [f"{TERMINATION_PLAIN[name]} {counts[name]}건" for name in TERMINATION_PLAIN]
    unknown = result.executed - sum(counts.values())
    if unknown > 0:
        parts.append(f"기록 없음 {unknown}건")
    return " · ".join(parts)


def _headline(result: TargetResult) -> str:
    total, errored = result.executed, result.errored
    violating = len(result.violating_cases)
    if result.verdict is Verdict.ERROR and result.campaign is not None:
        return (
            f"**ERROR** — {total}건 중 {result.unjudged_steps}건에서 오라클이 평가되지 못했다"
            f"(미판정 비율 {result.unjudged_ratio}). 보지 못한 실행이 너무 많아 위반 없음으로 "
            "읽을 수 없다. 거절·실패·시간 초과는 판정된 실행이라 이 수에 들지 않는다."
        )
    if result.verdict is Verdict.ERROR:
        return (
            f"**ERROR** — {total}건 중 {errored}건이 실행 오류로 끝나 판정을 마치지 못했다. "
            "오류 난 케이스는 관찰 결과가 없다."
        )
    if result.verdict is Verdict.FAIL:
        return f"**FAIL** — {total}건 중 {violating}건에서 보안 경계 위반(후보)이 관찰됐다."
    return (
        f"**PASS** — {total}건 모두에서 관찰한 기준의 위반이 보이지 않았다. "
        "이것이 대상 프로그램이 안전하다는 증명은 아니다."
    )


def render_summary(result: TargetResult, *, source_name: str, inputs_verified: bool) -> str:
    """Render the one-page summary. ``source_name`` should be a bare file name, not a path."""
    axes = result.axes
    lines: list[str] = []
    add = lines.append
    # Title names every axis that applies, so a runtime-version or filter cell is not version-less.
    title_axes = " · ".join(
        value
        for value in (axes.target_version, axes.runtime_version, axes.extraction_filter)
        if value is not None
    )
    title = f"{result.target} {title_axes}" if title_axes else result.target
    add(f"# 결과 한 장 요약: {_cell(title)}")
    add("")
    add(
        f"> 원본 결과 파일: {_code(source_name)} · 라벨: **{result.label}** — 데모 실행 기록이며 "
        "자격 검증이나 사전등록 실험 결과가 아니다."
    )
    add("")
    add("## 한 줄 결론")
    add("")
    add(_headline(result))
    add("")
    add("## 무엇을 시험했나")
    add("")
    add("| 항목 | 값 |")
    add("| --- | --- |")
    add(f"| 대상 프로그램 | {_code(result.target)} |")
    for label, value in (
        ("대상 버전", axes.target_version),
        ("런타임 버전", axes.runtime_version),
        ("추출 필터", axes.extraction_filter),
    ):
        add(f"| {label} | {_code(value) if value is not None else NOT_APPLICABLE} |")
    add(f"| 실행 방식 | {MODE_PLAIN[result.mode]} |")
    add(f"| 실행 수 | {result.executed}건 (실행 오류 {result.errored}건) |")
    campaign = result.campaign
    if campaign is not None:
        budget_txt = (
            "멈출 때까지 (상한 없음)" if campaign.budget is None else f"{campaign.budget}건"
        )
        add(f"| 탐색 예산(budget) | {budget_txt} |")
        add(f"| 난수 seed | {campaign.seed} |")
        first = campaign.runs_to_first_violation
        add(f"| 첫 위반까지 실행 | {f'{first}번째' if first is not None else '위반 없음'} |")
        add(f"| 위반 수 | {len(result.violating_cases)}건 |")
        add(f"| 종료 상태 | {_termination_line(result)} |")
        add(
            f"| 미판정 실행 | {result.unjudged_steps}건 (비율 {result.unjudged_ratio}) "
            "— 오라클이 평가되지 못한 실행(실행 기반 오류·관찰 없음·사후 스냅샷 없음), "
            "‘위반 없음’과 다름. 거절·실패·시간 초과는 판정된 실행이라 여기 들지 않음 |"
        )
        if campaign.max_unjudged_ratio is not None:
            add(f"| 미판정 상한 | {campaign.max_unjudged_ratio} (넘으면 판정은 ERROR) |")
        if campaign.stopped_early:
            add("| 중단 | 사람이 예산 소진 전에 멈춤 (그때까지의 결과) |")
    prep = result.preparation
    if prep is not None:
        method = (
            "공개 레지스트리에서 실행 중에 만든 lock으로 빌드(탐색용, 저장소에 커밋된 레시피 아님)"
            if prep.method == "registry"
            else "저장소에 커밋된 레시피로 빌드"
        )
        add(f"| 이미지 준비 방식 | {method} |")
        add(
            f"| 요청 버전 / 이미지 안 설치 버전 | {_code(prep.requested_version)} / "
            f"{_code(prep.installed_version)} |"
        )
        if prep.requested_spec is not None:
            add(
                f"| 요청 값 | {_code(prep.requested_spec)} → {_code(prep.requested_version)} "
                f"(해석 시각 {_code(prep.resolved_at or '')}) |"
            )
        for dep in prep.new_dependencies:
            add(
                f"| 커밋된 lock에 없던 의존(기록) | {_code(dep['name'] + '@' + dep['version'])} "
                f"{_code(dep['integrity'])} |"
            )
        for package in prep.install_scripts_disabled:
            add(f"| install script 비활성(기록) | {_code(package)} |")
        for name, value in (
            ("이미지 안 lock SHA-256", prep.lock_sha256),
            ("이미지 안 worker SHA-256", prep.worker_sha256),
            ("이미지 안 effect-producer SHA-256", prep.producer_sha256),
            ("effect-producer 오프라인 호환 확인", prep.producer_check),
            ("빌드 레시피", prep.recipe),
        ):
            add(f"| {name} | {_code(value) if value else NOT_APPLICABLE} |")
    add("")
    if prep is not None and prep.method == "registry":
        add(
            "> **탐색용 실행(exploratory demo run).** 이 버전은 저장소에 고정 lock이 없어 실행 "
            "시점의 공개 레지스트리 상태로 임시 lock을 만들고 그 lock으로 이미지를 빌드했다. "
            "**임시 생성 lock이므로, 재현하려면 저장된 lock(`preparation/package-lock.json`)과 "
            f"그 SHA-256({_code(prep.lock_sha256 or '기록 없음')})이 필요하다.** "
            "커밋된 lock으로 같은 의존 구성을 다시 만드는 검증 경로(verified)와 다르다. "
            "integrity 대조는 같은 실행에서 "
            "레지스트리가 공표한 값과 일치한다는 것까지만 보이며, 레지스트리 자체가 바뀌었거나 "
            "오염된 경우는 막지 못한다. 받은 패키지가 안전하다는 보증도 없다."
        )
        add("")
    add("## 무엇을 확인했나 (판정 기준)")
    add("")
    for name in CONTRACTS:
        observed = (
            "이번 실행에서 관찰함"
            if name in result.observed_contracts
            else "이 실행 방식은 관찰하지 않음"
        )
        add(f"- **{name}** {CONTRACT_PLAIN[name]}. _{observed}._")
    add("")
    if campaign is not None:
        # A campaign may run far more cases than it keeps; show aggregates + the violations only.
        add("## 탐색 결과 (집계와 위반 케이스)")
        add("")
        violations = len(result.violating_cases)
        add(
            f"{result.executed}번 실행해 {violations}건에서 위반을 관찰했다(미판정 "
            f"{result.unjudged_steps}건·비율 {result.unjudged_ratio}, 그중 실행 기반 오류 "
            f"{result.errored}건; 종료 상태 {_termination_line(result)}). 전 실행을 한 줄씩 담지 "
            "않고, 위반 입력만 아래에 둔다. 위반은 위반 후보이며 확정 취약점이 아니다."
        )
        if result.unjudged_steps:
            ceiling = campaign.max_unjudged_ratio
            ceiling_txt = (
                f" 미판정 비율이 상한 {ceiling}을 넘으면 판정은 자동으로 ERROR다."
                if ceiling is not None
                else ""
            )
            add("")
            add(
                f"미판정 실행 {result.unjudged_steps}건은 오라클이 평가되지 못한 실행이다. "
                "‘위반 없음’이 아니라 ‘보지 못함’이므로 조용한 PASS로 세지 않는다." + ceiling_txt
            )
        add("")
        if result.repro_inputs:
            by_id = {case.case_id: case for case in result.cases}
            add("| 위반 케이스 | C0 | C1 | C2 | 입력 TAR | SHA-256 | 종료 상태 | 관찰 | 확인 |")
            add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
            needs_check = 0
            for item in result.repro_inputs:
                case = by_id.get(item.case_id)
                cells = (
                    (_contract_cell(case.c0), _contract_cell(case.c1), _contract_cell(case.c2))
                    if case is not None
                    else ("?", "?", "?")
                )
                check = case is not None and case.needs_repro_check
                needs_check += check
                add(
                    f"| {_code(item.case_id)} | {cells[0]} | {cells[1]} | {cells[2]} | "
                    f"{_code(item.tar_path)} | {_code(item.tar_sha256)} | "
                    f"{_termination_cell(case.termination if case else None)} | "
                    f"{_observation_cell(case.observation_complete if case else None)} | "
                    f"{'**재현 확인 필요**' if check else '—'} |"
                )
            add("")
            if needs_check:
                add(
                    f"**재현 확인 필요 {needs_check}건:** 대상이 성공으로 끝나지 않았거나"
                    "(거절·실패·시간 초과) 관찰이 완결되지 않은 상태에서 난 위반이다. "
                    "위반은 위반이지만, 같은 입력을 다시 돌려 같은 위반이 나는지 먼저 확인한다."
                )
                add("")
            add('위반 입력 TAR는 결과 폴더 `inputs/`에 있다. 재현은 아래 "다시 해 보려면".')
        else:
            add("저장된 위반 입력이 없다 (위반 0건).")
    else:
        add("## 케이스별 결과")
        add("")
        if result.cases:
            add("| 케이스 | 실행 결과 | C0 | C1 | C2 |")
            add("| --- | --- | --- | --- | --- |")
            for case in result.cases:
                outcome = "실행 오류" if case.outcome == RUN_ERROR else _code(case.outcome)
                add(
                    f"| {_code(case.case_id)} | {outcome} | {_contract_cell(case.c0)} | "
                    f"{_contract_cell(case.c1)} | {_contract_cell(case.c2)} |"
                )
            add("")
            add(
                "‘관찰 안 함’은 ‘위반 없음’이 아니다. 그 기준은 이 케이스에서 보지 않았다는 뜻이다."
            )
        else:
            add("실행한 케이스가 없다.")
    add("")
    add("## 다시 해 보려면 (재현 방법)")
    add("")
    prov = result.provenance
    if prov.engine_sha is None:
        add("1. 엔진 커밋: 기록 없음 — 어느 코드로 돌렸는지 이 파일만으로는 알 수 없다.")
    else:
        add(f"1. 엔진 커밋: InodeFence 저장소에서 {_code(prov.engine_sha)}를 체크아웃한다.")
    if prov.engine_dirty:
        add(
            "   - 주의: 실행 당시 작업 트리에 커밋 안 된 변경이 있었다. 이 커밋만으로는 똑같이 "
            "재현되지 않을 수 있다."
        )
    image = ", ".join(
        part
        for part in (
            _code(prov.image_ref) if prov.image_ref else "",
            f"id {_code(prov.image_id)}" if prov.image_id else "",
        )
        if part
    )
    add(f"2. 실행 이미지: {image or '기록 없음'}.")
    version_bits = [
        f"{label} {_code(value)}"
        for label, value in (
            ("대상 버전", axes.target_version),
            ("런타임 버전", axes.runtime_version),
            ("추출 필터", axes.extraction_filter),
        )
        if value is not None
    ]
    add(
        f"3. 같은 설정으로 {_code(result.target)}를 실행한다"
        + (f" ({', '.join(version_bits)})." if version_bits else ".")
        + " 대상별 실행 명령은 해당 대상의 실행 안내를 따른다."
    )
    if result.repro_inputs:
        check = (
            "요약을 만들 때 아래 해시를 실제 파일과 대조해 일치함을 확인했다."
            if inputs_verified
            else "요약을 만들 때 아래 해시를 실제 파일과 대조하지 않았다."
        )
        add(
            "4. 저장된 입력 TAR(결과 파일이 있는 폴더 기준 상대 경로)를 그대로 넣는다. "
            f"`sha256sum <경로>` 값이 표와 같아야 같은 입력이다. {check}"
        )
        add("")
        add("| 케이스 | 입력 TAR | SHA-256 |")
        add("| --- | --- | --- |")
        for item in result.repro_inputs:
            add(f"| {_code(item.case_id)} | {_code(item.tar_path)} | {_code(item.tar_sha256)} |")
    else:
        add("4. 저장된 입력 TAR가 없다 — 입력 자체를 다시 만들 정보는 이 파일에 없다.")
    add("")
    add("## 읽을 때 주의")
    add("")
    add("- PASS는 안전 증명이 아니다. 시험한 입력과 관찰한 기준 안에서 위반이 안 보였다는 뜻이다.")
    add("- ‘위반’은 위반 후보다. 확정된 취약점으로 보려면 재현과 원인 분석이 따로 필요하다.")
    add(
        "- 이 요약은 결과 파일에서만 만들었다. 다시 만들려면: "
        f"`python -m inodefence.target_result_summary {_cell(source_name)}`"
    )
    return "\n".join(lines) + "\n"


def summarize_file(path: Path, *, verify_inputs: bool = True) -> str:
    """Load ``path`` with the strict reader and render its one-page summary."""
    result = load_target_result(path, verify_inputs=verify_inputs)
    return render_summary(result, source_name=path.name, inputs_verified=verify_inputs)


SUMMARY_NAME = "summary.md"


def write_cell_summaries(result_paths: Iterable[Path]) -> list[Path]:
    """Write ``summary.md`` beside each ``result.json``, re-read from that file alone.

    Each summary comes from the strict reader with saved-input hashes checked, so it only says what
    the written file holds. An existing ``summary.md`` is never overwritten (``FileExistsError``).
    """
    written: list[Path] = []
    for result_path in result_paths:
        text = summarize_file(result_path)
        out = result_path.parent / SUMMARY_NAME
        with out.open("x", encoding="utf-8") as handle:
            handle.write(text)
        written.append(out)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m inodefence.target_result_summary",
        description="inodefence-target-result-v1 결과 파일을 한 장 요약(Markdown)으로 바꾼다.",
    )
    parser.add_argument("result", type=Path, help="결과 JSON 파일")
    parser.add_argument("-o", "--output", type=Path, help="요약을 쓸 파일 (없으면 표준 출력)")
    parser.add_argument(
        "--no-verify-inputs",
        action="store_true",
        help="저장된 입력 TAR의 SHA-256 대조를 건너뛴다 (요약에 그 사실을 적는다)",
    )
    args = parser.parse_args(argv)
    try:
        text = summarize_file(args.result, verify_inputs=not args.no_verify_inputs)
    except (TargetResultError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

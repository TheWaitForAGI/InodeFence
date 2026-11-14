"""Generate paper/tables/m2-cross-release-evidence.md from the validated summary.

Data source: experiments/repro/evidence/summary.json (per_release_shared booleans +
fixed_pair). This generator derives ONLY the 5x2 verdict grid from that JSON and cross-checks
it; the surrounding prose and the rejection-reason strings are literal template (the reasons
are not in summary.json -- kept verbatim, documented as "manual" in the PR). Output is
byte-identical to the committed table.

    python -m scripts.gen_table_m2 --out paper/tables/m2-cross-release-evidence.md
    python -m scripts.gen_table_m2 --check paper/tables/m2-cross-release-evidence.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RELEASES = ("7.5.2", "7.5.3", "7.5.6", "7.5.7", "7.5.8")
FIXTURES = ("toplevel_hardlink", "nested_hardlink")
SHARED_CELL = "**공유** (resolved, nlink 1→2)"
REASON = {
    ("toplevel_hardlink", "7.5.3"): "linkpath contains '..'",
    ("toplevel_hardlink", "7.5.6"): "linkpath escapes extraction directory",
    ("toplevel_hardlink", "7.5.7"): "linkpath contains '..'",
    ("toplevel_hardlink", "7.5.8"): "linkpath contains '..'",
    ("nested_hardlink", "7.5.3"): "linkpath contains '..'",
    ("nested_hardlink", "7.5.7"): "linkpath contains '..'",
    ("nested_hardlink", "7.5.8"): "linkpath contains '..'",
}

PREFIX = '# 표 M2 — Cross-release identity 통제 재현 증거표\n\n> 렌더된 그림: [m2-cross-release-evidence.png](../figures/m2-cross-release-evidence.png) (생성 소스 [`render_m2_cross_release.py`](../figures/render_m2_cross_release.py))\n\nM2(§5.2)의 근거표다. verdict = "추출된 객체가 외부 참조파일의 `(st_dev, st_ino)` identity를\n공유하는가" — 이것이 C1 oracle이 평가하는 바로 그 관찰이며, 릴리스 id나 정답 경로를 판정 조건에\n넣지 않는다. 두 fixture 모두 링크 타깃은 동일한 상대 경로(추출 디렉터리를 벗어남)이고, top-level에\n두느냐 subdir 안에 두느냐만 다르다.\n\n## Provenance\n\n| 항목 | 값 |\n| --- | --- |\n| raw 조합 요약 | [`../../experiments/repro/evidence/summary.json`](../../experiments/repro/evidence/summary.json) |\n| experiment config | [`../../experiments/repro/cross_release_identity.py`](../../experiments/repro/cross_release_identity.py) |\n| validated summary | [cross-release-identity-repro-v1](../../experiments/summaries/cross-release-identity-repro-v1.md) |\n| target | node-tar (JS), 고정 릴리스 5종 (docker image `inodefence-node-tar-effect:{release}`) |\n| seed / budget | 해당 없음 — 손으로 만든 결정론적 fixture(퍼저 입력 아님), 릴리스당 1회 추출 |\n| 실행 환경 | 호스트 docker, 릴리스별 disposable Linux 컨테이너; `make check` 미수집(호스트 전용 재현) |\n| 재생성 | `python experiments/repro/cross_release_identity.py --out experiments/repro/evidence` (호스트 docker + 5개 이미지 필요) |\n\n## verdict 표 (observed)\n\n| 릴리스 | toplevel_hardlink | nested_hardlink |\n| --- | --- | --- |\n'  # noqa: E501
SUFFIX = '\n\n- **고정 쌍(fixed pair):** toplevel = (7.5.2 공유 → 7.5.3 거부) = R1 = CVE-2026-23745 (catalog N01);\n  nested = (7.5.6 공유 → 7.5.7 거부) = R2 = CVE-2026-24842 (catalog N02, GHSA-34x7-hfp2-rc4v).\n- **비단조 분포:** nested fixture는 7.5.2 공유 · 7.5.3 거부 · 7.5.6 공유 · 7.5.7 거부 · 7.5.8 거부로,\n  7.5.3에서 거부된 입력이 7.5.6에서 다시 공유되고 7.5.7에서 다시 거부됨을 보인다. R2가 R1 수정이 도입한\n  check/use mismatch 회귀라는 것은 추론이다(아래 inferred).\n\n## observed vs inferred\n\n- **observed:** 위 5×2 verdict(raw JSON에서 직접 읽음), nlink 전이, 거부 메시지, 비단조 분포.\n- **inferred:** 특정 CVE↔fixture 대응(R1↔toplevel 쌍, R2↔nested 쌍)과 "7.5.6 회귀가 R1 수정이\n  도입한 것"이라는 인과 서술. advisory 범위(24842 `<7.5.7`)와 이 **특정** fixture의 observed 거동은\n  다를 수 있어 **exact 하한은 미검증**이다.\n\n핵심: **outcome 기반 oracle 하나가 R1·R2 두 root-cause를 릴리스 id·정답 경로 하드코딩 없이\n포착한다.** 이는 통제 재현이며 퍼저의 탐색 결과가 아니다.\n'  # noqa: E501


def summary_path() -> Path:
    return (
        Path(__file__).resolve().parents[1] / "experiments" / "repro" / "evidence" / "summary.json"
    )


def build(summary: dict) -> str:
    rows = []
    for rel in RELEASES:
        cells = []
        for fx in FIXTURES:
            shared = summary[fx]["per_release_shared"][rel]
            cells.append(SHARED_CELL if shared else f"거부 `{REASON[(fx, rel)]}`")
        rows.append(f"| {rel} | {cells[0]} | {cells[1]} |")
    # cross-check fixed_pair against the JSON (raw -> table binding, not invented)
    assert tuple(summary["toplevel_hardlink"]["fixed_pair"]) == ("7.5.2", "7.5.3")
    assert tuple(summary["nested_hardlink"]["fixed_pair"]) == ("7.5.6", "7.5.7")
    return PREFIX + "\n".join(rows) + SUFFIX


def render() -> str:
    return build(json.loads(summary_path().read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the generated table here")
    parser.add_argument("--check", type=Path, help="verify a committed table is byte-identical")
    args = parser.parse_args(argv)
    text = render()
    if args.check is not None:
        committed = args.check.read_text(encoding="utf-8")
        if committed == text:
            print(f"m2 table byte-identical: {args.check}")
            return 0
        print(f"m2 table DIFFERS from generated: {args.check}", file=sys.stderr)
        return 1
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

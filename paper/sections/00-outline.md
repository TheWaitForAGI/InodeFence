# InodeFence 논문 드래프트 — 조립본 v2 (개요·읽는 순서)

이 문서는 `paper/sections/` 아래 섹션 파일을 **읽는 순서**로 엮은 조립본 개요다. 각 섹션은
독립 파일이며, 모든 주장 문장은 주장 목록의 한 행을 `[C-…]`로 가리킨다.

## 단일 기준 (이 드래프트가 새로 판정하지 않는 것)

주장의 **단일 목록**은 [`claims-evidence-status-v1.md`](claims-evidence-status-v1.md)이고, 능력·증거 수준의
단일 기준은 Capability Ledger([`../../docs/STATUS.md`](../../docs/STATUS.md))다. 이 드래프트는 그 두 문서를
**가리키며 서술만** 하고, 목록에 없는 주장은 쓰지 않는다. 숫자는 목록의 "쓸 수 있는 말"과 그 근거 파일의 값만 쓴다.
증거 수준 어휘(DESIGNED / IMPLEMENTED / TESTED / VALIDATED)와 마일스톤(M1–M4)은 Ledger 정의를 그대로 쓴다.

## 한 문단 요약

이 드래프트는 identity 오라클의 통제 차분 [C-M2], 다른 추출기 3개에 대한 오라클·어댑터 수준 적용(방식의 차이는 §5.5) [C-M4a], 실제
node-tar 루프 [C-M1], 측정 사슬 대조 [C-PC]와 사전등록 평가 절차 [C-DESIGN] [C-INFRA]를 방어한다. 상태 피드백의
탐색 효과(H-A)는 미검증이며 [C-HA], 그 자리는 본실험 결과 자리(봉인 해제 뒤 기입)다 [S-TRAIN] [S-HOLDOUT].
참신성은 확정 사실이 아니라 검증 대상 가설로 둔다.

## 읽는 순서

| # | 섹션 | 파일 |
| --- | --- | --- |
| 1 | Abstract | [`01-abstract.md`](01-abstract.md) |
| 2 | Introduction (§1) | [`02-introduction.md`](02-introduction.md) |
| 3 | Background & Threat Model (§2) | [`03-background-threat-model.md`](03-background-threat-model.md) |
| 4 | Related Work (§3) | [`04-related-work.md`](04-related-work.md) |
| 5 | Method (§4) | [`05-method.md`](05-method.md) |
| 6 | Results (§5) | [`06-results.md`](06-results.md) |
| 7 | Limitations & Discussion (§6) | [`07-limitations-discussion.md`](07-limitations-discussion.md) |
| 8 | Conclusion (§7) | [`08-conclusion.md`](08-conclusion.md) |

보조 자료:

- 표: [`../tables/m2-cross-release-evidence.md`](../tables/m2-cross-release-evidence.md),
  [`../tables/exp0-summary.md`](../tables/exp0-summary.md),
  [`../tables/exp3-go-inputs.md`](../tables/exp3-go-inputs.md),
  [`../tables/capability-ledger-summary.md`](../tables/capability-ledger-summary.md)
- 그림(렌더됨, observed): [M2 verdict](../figures/m2-cross-release-evidence.png), [EXP-0 KM](../figures/exp0-survival.png),
  [`make demo` 끝 화면](../figures/make-demo-screen.png), 생성 소스 `../figures/render_*.py`
- 주장 목록: [`claims-evidence-status-v1.md`](claims-evidence-status-v1.md)

## 결과 자리

EXP-3 train의 arm별 결과(S-TRAIN)와 EXP-2 holdout 확증 판정(S-HOLDOUT)이 들어갈 곳은 모두
`본실험 결과 자리(봉인 해제 뒤 기입)`라는 같은 문구로 둔다. 봉인 값은 어떤 칸에도 넣지 않는다.

## 형식 메모

이 드래프트는 저장소 관례(모든 문서가 Markdown, [`../README.md`](../README.md)의 "본문은 sections/")에
맞춰 Markdown으로 작성했다. `make check`에 LaTeX 단계가 없어 `.tex`는 검증되지 않으므로, 검증
가능한 형식을 택했다. 정식 제출용 조판(LaTeX/영문 번역)은 별도 작업으로 둔다.

## 불변식 (작성 시 엄수)

observed(실행 출력으로 확인)와 inferred(추론)를 문장에서 구분한다. 증거 사슬 없는 결론을 쓰지
않는다. synthetic을 native 증거로 승격하지 않는다. 비교 없이 effectiveness를 주장하지 않는다.
선행연구 포지셔닝([`../../docs/research/design/related-work-positioning.md`](../../docs/research/design/related-work-positioning.md))을
그대로 따른다.

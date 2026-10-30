# InodeFence 논문 드래프트 — 조립본 v1 (개요·읽는 순서)

이 문서는 `paper/sections/` 아래 섹션 파일을 **읽는 순서**로 엮은 조립본 개요다. 각 섹션은
독립 파일이며, 모든 정량 주장은 증거 사슬(raw → validated summary → finding → 이 드래프트 →
Capability Ledger)로 추적 가능하다.

## 단일 기준 (이 드래프트가 새로 판정하지 않는 것)

능력·증거 수준의 **단일 기준은 Capability Ledger**([`../../docs/STATUS.md`](../../docs/STATUS.md))이고,
주장↔증거 매핑은 [`claims-evidence-status-v1.md`](claims-evidence-status-v1.md)다. 이 드래프트는
그 두 문서를 **가리키며 서술만** 하고, 능력 판정을 여기서 새로 하지 않는다. 증거 수준 어휘
(DESIGNED / IMPLEMENTED / TESTED / VALIDATED)와 마일스톤(M1–M4)은 Ledger 정의를 그대로 쓴다.

## 정직 프레이밍 (한 문단 요약)

이 드래프트의 **주 주장은 두 개**다: (M2) 하나의 generic identity oracle이 릴리스 id·정답 경로
하드코딩 없이 두 root-cause를 통제 차분으로 포착한다(observed), (M3) 영향 릴리스에서 object-identity
관찰이 자율 경계위반 발견을 **인과적으로 가능케 한다**(blind 대조; 없으면 도달 불가). **rate 우위
(상태-인지 feedback이 무작위보다 빠르다/많이 찾는다)는 주 주장이 아니라 보조이며 현재 미판정이다.**
참신성은 확정 사실이 아니라 검증 대상 가설로 두고, "최초/새로운/기존연구에 없음" 류 표현은 쓰지 않는다.

## 읽는 순서

| # | 섹션 | 파일 |
| --- | --- | --- |
| 1 | Abstract | [`01-abstract.md`](01-abstract.md) |
| 2 | Introduction | [`02-introduction.md`](02-introduction.md) |
| 3 | Background & Threat Model | [`03-background-threat-model.md`](03-background-threat-model.md) |
| 4 | Related Work | [`04-related-work.md`](04-related-work.md) |
| 5 | Method | [`05-method.md`](05-method.md) |
| 6 | Results | [`06-results.md`](06-results.md) |
| 7 | Limitations & Discussion | [`07-limitations-discussion.md`](07-limitations-discussion.md) |
| 8 | Conclusion | [`08-conclusion.md`](08-conclusion.md) |

보조 자료:

- 표: [`../tables/m2-cross-release-evidence.md`](../tables/m2-cross-release-evidence.md),
  [`../tables/m3-blind-ablation.md`](../tables/m3-blind-ablation.md),
  [`../tables/capability-ledger-summary.md`](../tables/capability-ledger-summary.md)
- 그림 사양: [`../figures/m3-blind-ablation-figure-spec.md`](../figures/m3-blind-ablation-figure-spec.md)
- 주장↔증거 매핑: [`claims-evidence-status-v1.md`](claims-evidence-status-v1.md)

## 상태 범례

- **paper-ready**: 증거 사슬이 raw까지 끊김 없이 닿는 확정 주장.
- **PENDING**: powered 독립 반복이 아직 진행 중이라 수치를 비워 둔 소절. 해당 수치를 추측해 적지
  않으며, 결과가 사슬에 닿은 뒤 후속 PR에서 채운다.

### 현재 PENDING 소절

- [Results §5.3.3 rate 판정](06-results.md) — M3 powered matched A1 vs A3full (동일 budget 2000) rate 판정.
- [Results §5.4.3 decompress powered 판정](06-results.md) — M4.5 decompress 자력발견 대예산 독립 반복 판정.

## 형식 메모

이 드래프트는 저장소 관례(모든 문서가 Markdown, [`../README.md`](../README.md)의 "본문은 sections/")에
맞춰 Markdown으로 작성했다. `make check`에 LaTeX 단계가 없어 `.tex`는 검증되지 않으므로, 검증
가능한 형식을 택했다. 정식 제출용 조판(LaTeX/영문 번역)은 별도 작업으로 둔다.

## 불변식 (작성 시 엄수)

observed(실행 출력으로 확인)와 inferred(추론)를 문장에서 구분한다. 증거 사슬 없는 결론을 쓰지
않는다. synthetic을 native 증거로 승격하지 않는다. 비교 없이 effectiveness를 주장하지 않는다.
선행연구 포지셔닝([`../../docs/research/design/related-work-positioning.md`](../../docs/research/design/related-work-positioning.md))을
그대로 따른다.

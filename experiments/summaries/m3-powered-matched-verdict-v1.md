# M3.3 powered 매칭 런 판정 — A1(random) vs A3full(identity-feedback)

**대상:** node-tar 7.5.2 frozen overlay (`inodefence-node-tar-effect:7.5.2`, image_prefix
`sha256:21d8a0e3a5c5`). **예산:** 2000/campaign. **seed:** {100..119} (기존 모든 run과
disjoint). **arm 2개(동일 조건):**

- **A1 (random floor)** — search `effect-feedback-v2-or-violation-v1-uniform-mutation-v1`,
  mutation `uniform-generic-m1-escape-hardlink-v1` (uniform, gradient 없음, 토큰-clean).
- **A3full (identity-feedback)** — search
  `effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1`,
  mutation `uniform-generic-m1-state-aware-escape-hardlink-v1` (state-aware 관찰-이름 조합,
  **blind 아님**; 어휘·oracle에 대상경로/식별자/정답seed/근접보상 하드코딩 0).

두 arm 정의는 `m3-scale-full`·`m3-ablation`·`m3-3-control`과 byte-exact 동일하다.

## 사전등록과 raw

- 사전등록(실행 전 고정, 사후 변경 금지): `docs/LOG.md` 2026-10-30 12:34, 도구·사전등록 PR #187.
  고정 항목: arm, 예산 2000, seed 100-119, hit = `oracle.C1 && feedback.contract_violated`,
  **rate 주장은 Wilson 95% CI 분리 필요**(점추정 차이는 rate 아님, 감사 EN-008).
- raw: `~/inodefence-evidence/m3-powered-matched-20261030/` (호스트 로컬, 40셀 = 2 arm × 20 seed,
  각 `.json` + `.steps.jsonl`; launcher `ALL_DONE` 2026-10-31 01:32, 전 셀 rc=0).
- 판정 재현: `scripts/determine_m3_powered_cells.py`(런타임-레인 clean-C1 결정) →
  per-arm `summary.json` → `scripts/analyze_m3_3_control.py --summary` / `--contrast`
  (평가-레인 Wilson roll-up·매칭 대조, `inodefence.evaluation.right_censored` 엔진). 집계 산출물은
  `m3-powered-matched-verdict-v1.json`에 그대로 박제.

## 방법 (런타임 레인 vs 평가 레인 분리)

clean exact C1 = 한 step에서 `oracle.C1`이고 `feedback.contract_violated`(데모가 `C1 VIOLATED`로
렌더하는 바로 그 술어). 완주/abort 구분은 report stub의 `aborted` 유무(fail-closed 관찰무결성 STOP).
런타임 레인은 보존된 `.steps.jsonl`(PR #180 copy-out)에서 셀별 사실만 판정하고, 평가 레인이 그 위에
Wilson·censoring 통계를 얹는다. abort 전 관찰된 clean C1은 셀의 observed-trigger로 기록하되
complete-campaign hit으로 승격하지 않는다(hit은 complete 캠페인 필요 — `SeedOutcome` 계약).

## 결과 (observed)

| arm | 완주(complete) | abort(infra-incomplete) | 완주 clean-C1 hit | Wilson 95% | observed-trigger seed | 총 관찰 clean-C1 |
| --- | --- | --- | --- | --- | --- | --- |
| A1 random | 12 | 8 | **0** | [0, 0.242] | 없음 | 0 |
| A3full identity | 10 | 10 | **1 (s101)** | [0.018, 0.404] | s101, s118 | 66 |

- **A3full s101**(완주): 첫 clean exact C1이 1-based 실행 1720/2000에서 발생. 완주 캠페인 내 자력 발견.
- **A3full s118**(abort): 실행 229부터 clean exact C1 65건 관찰 후 실행 1020에서 fail-closed abort
  → observed-trigger(complete hit 아님).
- **A1**: 완주 12셀 전부 clean exact C1 0, observed-trigger 0.
- C0(path-boundary) step은 양 arm·전 셀 0 (escape-hardlink 문법은 C1/C2 외부 identity 겨냥, C0 아님).

## 매칭 대조 (평가 레인, 감사 EN-008)

공유 seed 20개에서 각 arm을 동일 `right_censored` 엔진으로 roll-up한 뒤 Wilson CI 분리를 본다.

- **complete_hit_wilson_intervals_separate = False.** A3full [0.018, 0.404]와 A1 [0, 0.242]가
  겹친다.
- 불일치(discordant): identity-only observed-trigger seed = {101, 118}; random-only = {}; 공통 = {}.

## 판정

1. **메커니즘 멀티-seed 일반화 (C-M3a 강화, observed).** identity-feedback이 기존 역사적 단일 seed
   s11을 넘어 **새 disjoint seed 2개(s101 완주, s118 abort 전)에서 자력 clean exact C1을 재현**했고,
   매칭 random floor(A1)는 완주 12셀에서 0이었다. 자력 발견이 단일-seed 아티팩트가 아님을 사전등록
   매칭 대조로 보였다. (blind 아님: state-aware arm은 외부 객체 하드링크에 관찰로 얻은 이름을 쓴다 —
   어휘·oracle 하드코딩 0.)
2. **rate 우위 미입증 (C-M3b, 사전등록 판정).** 완주 clean-C1 rate 점추정은 identity 쪽(0.10 vs 0.00)
   이나 매칭 Wilson 95% 구간이 겹쳐 **CI 분리 실패** → rate 우위 미입증. ~0.1 효과에 대해 검정력이
   부족하다(정답 경로가 희소: 역사적으로 ~1/729 외부시도). 이는 검정력 없는 "비결과"가 아니라
   22개 완주 캠페인의 사전등록 실측 판정이다.

**주장 매핑:** 주 주장은 C-M2(통제 재현) + C-M3a(인과 메커니즘, 이번에 멀티-seed로 강화) 그대로.
C-M3b(rate 우위)는 "미판정"에서 "사전등록 판정: CI 미분리(검정력 한계)"로 확정하되 여전히 보조·탐색적
이며 논문 본문의 주 주장으로 올리지 않는다. CI 분리된 rate 주장은 formal 대예산 pilot(M3.4, 사람 게이트:
N01 토큰·timeout 동결)이 선행돼야 한다.

## 불변식

observed(s101 완주 C1, s118 abort 전 C1, A1 0)와 inferred(인과 대조: identity 피드백이 발견을 가능케
함)를 엄격히 구분. CVE/대상경로/sentinel/정답seed 하드코딩 0(D005/D006). 교차-run arm 정의 byte-동일.
감사 EN-008 준수(점추정 차이는 rate 아님). oracle·FROZEN·격리계약 불변(분석·문서 전용).

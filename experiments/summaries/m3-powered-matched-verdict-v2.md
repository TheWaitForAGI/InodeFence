# M3.3 powered matched run — verdict v2 (pooled seeds 100–129)

**Classification:** `m3.3-powered-matched-verdict-v2-pooled` · **Date:** 2026-11-02 · node-tar 7.5.2 · budget 2000

> **v1 preserved.** `m3-powered-matched-verdict-v1.{md,json}` reports the `{100–119}` slice and is left
> unchanged. This v2 pools the **pre-declared deterministic extension `{120–129}`** (LOG 2026-10-30 12:34:
> "처리량 되면 사전선언 연장 {120..129}, 결정론적 다음 연속 seed, 사후선택 아님") onto it to raise power on
> the rate verdict. Extension campaigns ran byte-exact with #196 (frozen overlay `inodefence-node-tar-effect:7.5.2`
> `sha256:21d8a0e3a5c5…`, same controller image, identical arm policy strings).

## Arms (byte-identical to v1 / m3-scale-full / m3-ablation / m3-3-control)

- **A1** — search `effect-feedback-v2-or-violation-v1-uniform-mutation-v1` / mutation
  `uniform-generic-m1-escape-hardlink-v1` = **random floor**.
- **A3full** — search `effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1` / mutation
  `uniform-generic-m1-state-aware-escape-hardlink-v1` = **identity feedback**.
- Hit criterion: `oracle.C1 && feedback.contract_violated` (the step the demo renders as `C1 VIOLATED`).

## Extension slice {120–129} (ext120-wave1, idempotent completion-wave, 3 rounds)

| arm | complete | right-censored abort | complete-campaign hits | new observed triggers |
|---|---|---|---|---|
| A1 | 7 (s120, s121, s123, s125, s126, s127, s129) | 3 (s122, s124, s128) | 0 | 0 |
| A3full | 7 (s120, s121, s122, s123, s125, s127, s129) | 3 (s124, s126, s128) | 0 | 0 |

7 complete **null** campaigns added per arm — no new hit, no new observed trigger: pure power addition.

## Pooled matched contrast {100–129} — 30 matched seeds

| arm | complete campaigns | complete-campaign hits | hit rate | Wilson 95% CI | observed-trigger seeds |
|---|---|---|---|---|---|
| **A1** (random floor) | 19 | 0 | 0.0 | [0.0, 0.1682] | — |
| **A3full** (identity feedback) | 17 | 1 (s101) | 0.059 | [0.0105, 0.2698] | [101, 118] |

- **`complete_hit_wilson_intervals_separate = false`** — the
  intervals OVERLAP (A1 upper 0.168 > A3full lower
  0.0105).
- Matched discordant observed-triggers: **2–0 for A3full** (s101, s118; 0 for A1) — direction consistent with H1.
- A3full s101 first clean exact C1 at **1-based execution 1720/2000**; s118 = 65 clean exact C1 pre-abort
  (observed trigger, not a complete hit).

## v1 → v2 (what pooling did)

| | shared seeds | A1 | A3full | CI separated |
|---|---|---|---|---|
| v1 ({100–119}) | 20 | 0/12 [0.0, 0.2425] | 1/10 [0.0179, 0.4042] | false |
| **v2 ({100–129})** | 30 | 0/19 [0.0, 0.1682] | 1/17 [0.0105, 0.2698] | false |

Pooling tightened both intervals (A3full upper 0.404→0.27,
A1 upper 0.242→0.168) and lowered the
A3full point estimate (0.1→0.059), but did not separate them.

## Verdict

- **Rate (C-M3b):** rate superiority **NOT CI-separated** at n=30 matched seeds — honest pre-registered negative.
  Point estimate still favors identity feedback (0.059 vs 0.0),
  and the matched discordant triggers are 2–0 for A3full, but the Wilson intervals overlap. Remains exploratory,
  not a main claim (audit EN-008: a point-estimate difference is not a rate claim).
- **Mechanism (C-M3a):** unchanged / STRENGTHENED — identity feedback autonomously reproduces clean exact C1 at
  multiple disjoint seeds (s101 complete, s118 pre-abort); random floor A1 = 0 across 19
  complete campaigns. Blind-aware, not blind discovery.
- **Main claims stay C-M2 + C-M3a.**

### Recommendation

CI still overlap → still underpowered. The pre-registered next step is the deterministic continuous extension
`{130..149}`. **Power note:** separating a ~0.06 rate from 0 at 95% Wilson needs roughly **n ≥ 100 complete matched
campaigns per arm** (hits accruing near 0.06 in A3full, 0 in A1); a single +20-seed extension (~+14 completes/arm)
will **not** separate the intervals unless A3full gains several new complete-campaign hits. Recommended path: record
this as the honest pre-registered rate negative and keep the main claims C-M2 + C-M3a; pursue `{130..149}` only to
keep chipping at power with that cost understood.

### Research invariants

Observed (s101 complete C1, s118 pre-abort C1, A1 0 across all complete campaigns) vs inferred (causal direction
favors identity feedback) kept strictly separate; no CVE / answer-path / sentinel hardcoding; EN-008 respected;
arm definitions byte-identical across runs; extension seeds `{120–129}` pre-declared deterministic, not post-hoc.

## 등록 외 관찰 (2026-11-03 감사 확인, verdict 불변)

**이 절은 사전등록 밖 관찰이며 위 verdict 수치({100..129} A1 0/19 · A3full 1/17, CI 미분리)를 바꾸지 않는다.**
2026-11-03 독립 감사에서 raw(`~/inodefence-evidence/m3-powered-matched-20261030/`)를 재집계해 확인한 사실만 적는다
(observed).

### 미등록 연장 {130..149} (ext130)

- `_launcher.log` 기준 2026-11-02 01:18:24 시작 — 이 v2 verdict 커밋(bb3fd7c, 01:23:16)보다 5분 전이며 LOG에
  사전등록 항목이 없다. launcher는 2026-11-02 08:43 종료.
- A1: 20셀 = 완주 8 / abort 12, 29,180 step, hit 0.
- A3full: 12셀 실행(130–141) = 완주 3 / abort 9, 13,057 step, hit 0. s138은 1872 step에서 중단(stub 없음).
  142–149 미실행.
- 포함 시 {100..149}: A1 0/27 Wilson [0, 0.1246], A3full 1/20 [0.0089, 0.2361] — **방향 불변, CI 여전히 겹침**.
  사전등록이 없으므로 이 수치는 verdict에 넣지 않고 여기 기록만 한다.

### abort 사유 (seeds 100–149, 92셀)

| 사유 | A1 | A3full |
|---|---|---|
| observer "evidence integrity failed(malformed_identity)" | 19 | 18 |
| docker broker disconnected | 3 | 1 |
| container runtime cleanup inspect failed (s118 포함) | 1 | 2 |
| remove failed | 0 | 1 |

### s101 trace 상태

s101의 유일한 완주 hit(1-based exec 1720)는 `trace_termination=rejected`, `trace_completeness=invalid`,
`feedback_eligible=False`, `observation_failures=4`인 run이다. hit는 **post-state** oracle의 C1+C2다 — 하드링크
`/a/dir`→`../outside/sentinel.txt`가 뒤 entry가 거부되기 전에 생성돼 잔존했다. `unique_violation_fingerprints`는 0.
위에서 쓴 "clean exact C1"의 "clean"은 hit 술어(`oracle.C1 && feedback.contract_violated`)가 참이라는 뜻이며
clean trace를 뜻하지 않는다.

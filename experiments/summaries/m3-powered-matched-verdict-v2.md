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

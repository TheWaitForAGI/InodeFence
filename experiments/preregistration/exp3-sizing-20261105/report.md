# EXP-3 sizing (n, x): pre-registration planning input, not a result

Evaluation lane, 2026-11-05. Code: `compute.py` → `sizing.json` (uses `evaluation.power` / `evaluation.survival` at stack-E head f655f18, unmerged; fixed seeds; runtime 465 s).

Sources: [E0] EXP-0 report JSON (`~/inodefence-evidence/exp0-20261105-analysis-premerge/exp0-report-premerge.json`); [E0r] EXP-0 cell summaries + `.log` mtimes (`~/inodefence-evidence/exp0-20261105/`); [M3] `experiments/summaries/m3-powered-matched-verdict-v2.json`; [K] sentinel-count reach study (`sentinel-k-reach-20261104/kscale_raw.txt`); [L4] `wp-throughput-20261104/SUMMARY.md`; [D3] `origin/claude/s3-exp3-prereg-skeleton@bda2f3d:experiments/preregistration/exp3-v1.md`; [ST] `docs/STATUS.md:312-324`. "Observed" = read from evidence; "Inferred" = model output.

## Headline (inferred)
- **EXP-3 size:** n = 20 campaigns/arm/target on train 7.5.2 + holdout = 120 campaigns ≈ 2.1 quiet host-days (1 host) or ≈1.05 days (2 hosts). 7.5.6/7.5.7 and S-a do not fit at that size; run them at reduced n or after 11/20. Pre-register EXP-3 as expected to be underpowered.
- **GO-rule (EXP-2) pair:** n = 94/arm on one target (282 campaigns, 4.96 quiet host-days), x = 0.032 pooled FIRST events per campaign over R/D/S-u (≈1.6×10⁻⁵ first events per execution at risk), assuming an R/D zero floor. Two targets: n = 47, x = 0.062. Power at n=94: 0.94 at the inferred k=3 hazard; 0.88 with 20% aborts; 0.80 with 40% aborts; 0.32 at M3's observed k=1 hazard.
- **Launcher values:** `jobs_max = 2` (only measured value). `campaign_watchdog_seconds ≥ 10800`: a 2000-step campaign ≈ 3098 s at p95 step time on a quiet host, ≈ 9573 s on a busy one — EXP-0's 7200 s would cut busy-host campaigns. `event_threshold`: the draft's 5 is below what the registered exact test can act on (no rejection at α=0.025 with < 7 informative seed blocks).

## 1-host feasibility verdict
- n=20 EXP-3 fits the 11/18→11/20 window only on a quiet, dedicated host (2.1 days; n=18 within 2.0 days). Not at the conservative rate (≈4.1 days) nor busy (≈7 days).
- A powered confirmatory T_first test is NOT feasible on 1 host in that window at any evidence-based hazard: floor model n=20 needs S-u per-campaign hit probability ≥ 0.42 (0.46 with 20% aborts); evidence ≈ 0.059 (M3, k=1, observed), 0.117 (k=3, inferred), 0.145 (k=5, inferred) → power 0.000 / 0.006 / 0.019. 80% power needs ≈ 76–153 campaigns/arm on the holdout alone (4–8 host-days).

## Three most important caveats
1. **2428 exec/h is a per-stream rate.** [E0] "summed" wall (4448 s) sums per-cell walls; `.log` mtimes show pairs ran concurrently → real jobs-2 throughput ≈ **4740 exec/h** (elapsed 2278 s), consistent with lane-4's 1.79× speedup. Doubles n only on a quiet exclusive host (lane 4 measured 3.09× host-state slowdown). Per-step cost at 2000 steps is extrapolated (no drift within 200).
2. **The hazard has never been measured.** Every S-u anchor rests on one M3 hit (one sentinel, C1 only, older engine, A3full adaptive ≈ S-a), scaled by the in-process reach ratio (inferred). Holdout hazard unknown, yet it is the only confirmatory family ([D3] :209/:345). EXP-0's 0/15 aborts at budget 200 do not bound aborts at 2000 (M3: 24/60).
3. **x must be counted in first-event units; GO at n=20 is noisy.** Item-7 proxy counts hit steps: M3 A3full 66/47263 = 1.4×10⁻³ vs 2 first events (4.2×10⁻⁵) → 33× inflated. With n=20, crossing x=0.032 needs only 2 S-u events: P(GO) = 0.33 / 0.70 / 0.81 under k=1/3/5. Registered prediction HR=2 assumes D=R and is untestable under the R-floor evidence (sign test: unattainable for n ≤ 75; Schoenfeld n=94 would need R to hit 31% of campaigns).

## 1. Throughput (jobs 2, budget 2000)
| scenario | exec/h | min/campaign/slot | campaigns per host-day |
|---|---|---|---|
| quiet, measured from run elapsed [E0r] | 4740 | 50.6 | 56.9 |
| conservative per-stream ([E0] summed) | 2428 | 98.8 | 29.1 |
| busy host ([D3] (d) 0.40 c/s) | 1440 | 166.7 | 17.3 |

jobs 3: unknown (not measured). Max n per arm per target at quiet rate (conservative in parentheses); each target = 3n campaigns; Rust tar fixed-fixture only (0 campaigns); aborts stay in denominator (right-censored, not replaced).

| hosts | days | campaigns quiet (cons.; busy) | train only | +holdout | +7.5.6/7.5.7 | +py-tarfile | train+holdout+S-a |
|---|---|---|---|---|---|---|---|
| 1 | 2 | 112 (58; 34) | 37 (19) | 18 (9) | 9 (4) | 7 (3) | 14 (7) |
| 1 | 3 | 170 (86; 50) | 56 (28) | 28 (14) | 14 (7) | 11 (5) | 21 (10) |
| 1 | 4 | 226 (116; 68) | 75 (38) | 37 (19) | 18 (9) | 15 (7) | 28 (14) |
| 1 | 5 | 284 (144; 86) | 94 (48) | 47 (24) | 23 (12) | 18 (9) | 35 (18) |
| 2 | 2 | 224 (116; 68) | 74 (38) | 37 (19) | 18 (9) | 14 (7) | 28 (14) |
| 2 | 3 | 340 (172; 100) | 113 (57) | 56 (28) | 28 (14) | 22 (11) | 42 (21) |
| 2 | 4 | 452 (232; 136) | 150 (77) | 75 (38) | 37 (19) | 30 (15) | 56 (29) |
| 2 | 5 | 568 (288; 172) | 189 (96) | 94 (48) | 47 (24) | 37 (19) | 71 (36) |

Expected complete campaigns/arm = n·(1−abort): 0.8n at 0.2 (rule of three on 0/15), 0.6n at 0.4 (M3 stress).

## 2. Power (per-contrast α = 0.025 two-sided = Holm worst case; S-u must be faster; 80% power)
`survival.py` has no power/effective-n helper. Two models: block-winner exact sign test over informative blocks (blocks whose two observations differ) and `power.py` Schoenfeld. Floor check (observed, repo function): 7 one-way informative blocks → p = 0.0156; 6 → 0.0313. Enumeration matches the repo's exact path (max |Δp| = 0 over 25 cases). Schoenfeld required events: HR 2 → 79.1 at α=0.025 (65.3 at 0.05, matches [D3]); HR 3 → 31.5; HR 5 → 14.7.

R/D floor model, x needed per n:
| n/arm | 10 | 15 | 18 | 20 | 25 | 30 | 37 | 40 | 47 | 50 | 75 | 94 | 150 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| p_S needed, abort 0 | .761 | .542 | .460 | .418 | .340 | .287 | .235 | .218 | .187 | .176 | .119 | .095 | .060 |
| p_S needed, abort 0.2 | .810 | .587 | .502 | .457 | .373 | .315 | .259 | .241 | .206 | .194 | .131 | .105 | .066 |
| x, first events/campaign | .254 | .181 | .153 | .139 | .113 | .096 | .078 | .073 | .062 | .059 | .040 | .032 | .020 |
| x, first events/exec at risk (×10⁻⁵) | 15.0 | 10.0 | 8.38 | 7.55 | 6.04 | 5.04 | 4.08 | 3.78 | 3.22 | 3.02 | 2.02 | 1.61 | 1.01 |

Minimum detectable HR (λ_S/λ_R), R above floor, abort 0 (Schoenfeld / sign test; † < 5 expected events, * 5–10):
| p_R \ n | 10 | 15 | 20 | 25 | 30 | 40 | 50 |
|---|---|---|---|---|---|---|---|
| 0.02 | 23†/78 | 17†/44 | 14*/31 | 12*/24 | 11*/20 | 9.3*/15 | 8.2*/13 |
| 0.05 | 14*/37 | 10*/20 | 8.7*/15 | 7.6*/12 | 6.8/10 | 5.8/8.1 | 5.2/6.9 |
| 0.10 | 9.7*/23 | 7.3*/13 | 6.1/9.3 | 5.4/7.7 | 4.9/6.7 | 4.2/5.5 | 3.8/4.7 |
| 0.20 | 7.1*/15 | 5.4/8.9 | 4.5/6.7 | 4.0/5.6 | 3.6/4.9 | 3.2/4.0 | 2.9/3.5 |

HR=2 with D=R (Schoenfeld) required p_R: n=40 0.98, 47 0.75, 50 0.68, 75 0.41, 94 0.31, 150 0.19; sign test: unattainable for n ≤ 75, n=94 needs p_R 0.59.

Monte Carlo validation of the registered test (400 sims/point):
| point | MC power | sign test | Schoenfeld |
|---|---|---|---|
| floor, n20, p_S .45 | .870±.033 | .870 | — |
| floor, n30, p_S .30 | .828±.037 | .840 | — |
| floor, n30, p_S 1/17 | .000 | .001 | — |
| floor, n76, p_S .117 (k=3) | .772±.041 | .803 | — |
| p_R .05, n30, p_S .35 | .750±.042 | .654 | .926 |
| p_R .20, n30, HR2 | .145±.035 | .112 | .206 |
| p_R .50, n40, HR2 | .568±.049 | .344 | .583 |
| p_R .10, n50, p_S .40, abort .2 | .885±.031 | .770 | .936 |

## 3. Sensitivity (R = 0; k multipliers = [K] reach ratios, inferred)
| S-u basis | k | abort | p_S | power n20/n30/n50 | n for 80% | n if p_R = 0.02 (sign / Schoenfeld) |
|---|---|---|---|---|---|---|
| M3 1/17 | 1 | 0/.2/.4 | .059 | .000/.001/.026 (abort 0) | 153/170/191 | 506/400, 562/444, 630/498 |
| ×2.06 | 3 | 0/.2/.4 | .117 | .006/.055/.371 | 76/85/95 | 135/84, 150/93, 168/104 |
| ×2.59 | 5 | 0/.2/.4 | .145 | .019/.135/.603 | 61/68/76 | 96/55, 106/61, 119/68 |
| M3 2/30 (incl. pre-abort) | 1/3/5 | 0 | .067/.132/.164 | n50: .047/.500/.731 | 135/67/54 | 382/291, 111/66, 80/44 |

Levers: budget 2000 already applied; sentinel 3→5 needs human approval (n 76→61, −20%, inferred); more seeds scale power linearly but the 7-block floor binds when n < ≈7/p_S; a second host halves wall time.

GO-rule operating characteristic, EXP-3 n=20, one target: x=0.032 needs ≥2 S-u events → P(GO) = .33/.70/.81 under k=1/3/5; x=0.062 needs ≥4 → .03/.20/.33.

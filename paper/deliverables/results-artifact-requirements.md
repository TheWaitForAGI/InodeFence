# 결과 표·그림 요구 목록 (EXP-3 종료 후 W2 생성용)

보고서 [§7.6](capstone-report-draft.md)과 논문 §5.6을 채우는 데 필요한 산출물이다. 스키마 기준은 PR #219와 #256,
그리고 `scripts/analyze_exp0.py` #257 head(`fe872f0`)다(모두 미머지, 2026-11-06 확인).

**입력 생성.** 다중 타깃이면 `schema_version: 2` 리포트가 나오고, item은 모두 `by_target.<tid>.` 아래로 들어간다.

```bash
PYTHONPATH=src python3 scripts/analyze_exp0.py --index <run>/summaries/index.json --format json --output <out>/exp3-report.json
```

## EXP-3 산출물 (아래 `T5` = `by_target.<tid>.item5_first_contract_index`, `T` = `T5.by_arm.<arm>.t_first_combined_c1_or_c2`)

| ID | 파일 (제안) | 입력 필드 |
| --- | --- | --- |
| T-EXP3-1 타깃별 생존표 | `paper/tables/exp3-survival-by-target.md` | `by_target.<tid>.{role,hypothesis,seeds,number_cells}` · n=`T.denominator_cells_in_risk_set` · `T.{number_observed,number_right_censored,km_median_executions}` · U_viol=`by_target.<tid>.item6_dense_signals.by_arm.<arm>.u_viol.total_unique_c1_c2_fingerprints` · abort=`by_target.<tid>.item1_aborts.by_arm.<arm>.number_abort` |
| T-EXP3-2 확증 검정표 | `paper/tables/exp3-confirmatory.md` | `confirmatory.contrasts[].{order,target_id,contrast,arm_a,arm_b,number_seed_blocks,total_events,holm_adjusted_p,reject_at_alpha,faster_arm,underpowered}` · `.permutation.p_value` · `.supplementary.u_viol_a12` · `.campaign_unit_rule_of_three_upper95`(underpowered일 때만) · 머리글 `confirmatory.{alpha,event_threshold,confirmatory_test,multiplicity,primary_endpoint,confirmatory_scope}` |
| T-EXP3-3 abort 민감도 | `paper/tables/exp3-abort-sensitivity.md` | 1차=`T` · `T5.sensitivity.{primary_policy,policies.{exclude,censor-at-budget}.by_arm.<arm>.{number_observed,number_right_censored,number_in_risk_set,km_median_executions}}` · `--contingency`를 줬으면 최상위 `arm_abort_independence` |
| T-EXP3-4 인프라 참고값 | `paper/tables/exp3-infra.md` | `by_target.<tid>.{item2_p95_full_step.pooled,item3_throughput.summed,environment}` · `.item7_hazard_proxy.zero_hit`(그 타깃 hit 0일 때만). `summed.exec_per_hour`는 스트림당 값으로 표기 |
| F-EXP3-1 KM 곡선 | `paper/figures/exp3-survival-<tid>.png` | `T.{km_curve[].time,km_curve[].survival,censored_times,denominator_cells_in_risk_set}`. **타깃별 1장, 풀링 금지** |

**보고서 표 7-A/B/C 매핑.** arm·n·T_first 중앙값·U_viol은 T-EXP3-1에서 온다. p(Holm)은 arm이 아니라 대조의 값이므로
`contrast`별 `holm_adjusted_p`를 R 행(S-u vs R)과 D 행(S-u vs D)에 적는다. 확증은 holdout 패밀리의 `reject_at_alpha`뿐이고
(`confirmatory_scope`), 방향은 `faster_arm`으로 읽는다. train과 fix-verification의 p(Holm)은 "해당 없음"이다.

## EXP-0·기존 산출물

| ID | 파일 | 생성기 | 입력·상태 |
| --- | --- | --- | --- |
| T-EXP0 | `paper/tables/exp0-summary.md` | `paper/figures/render_exp0_survival.py --report <json> --no-figure` (#219) | 스키마 1 리포트. pre-merge 리포트로 표 렌더링 확인. 스택 머지 후 재생성 |
| F-EXP0 | `paper/figures/exp0-survival.png` | 같은 스크립트 (matplotlib 임시 환경) | `item5_first_contract_index.by_arm.<arm>.t_first_combined_c1_or_c2.{km_curve,censored_times}`. hit 0이므로 곡선은 사건 없이 평평하다 |
| T-M2, T-M3 | `paper/tables/m2-cross-release-evidence.md`, `m3-blind-ablation.md` | `scripts.gen_table_m2`, `scripts.gen_table_m3` (#256) | `experiments/repro/evidence/summary.json`, `node-self-discovery-mechanism-v1.md`. `--check`로 바이트 대조 |
| F-M2, F-M3 | `paper/figures/m2-cross-release-evidence.png`, `m3-blind-ablation.png` | `render_m2_cross_release.py`, `render_m3_blind_ablation.py` | 아래 공백 3·4 |

## 생성 전에 메워야 할 공백

1. **EXP-3 생성기가 없다.** #219 렌더러는 item을 최상위에서 읽어 스키마 2에서 실패한다(재현:
   `KeyError: 'item1_aborts'`, 그림은 `KeyError: 'item5_first_contract_index'`). 면책 문구도 EXP-0 전용이다. 위 EXP-3 5종은
   `by_target`을 읽는 새 생성기가 필요하다.
2. **#256 `ARTIFACTS`에 EXP-3 행이 없다.** 새 생성기와 함께 추가하고, `exp0-survival.png` 행의 "pending lane 6 #219" 메모를
   갱신한다.
3. **F-M3와 T-M3에 철회된 인과 문구가 남아 있다.** `render_m3_blind_ablation.py`의 제목(41행
   "object-identity observation enables autonomous discovery")과 캡션(54행 "Causal contrast…"), x축 라벨(21–22행
   "identity obs ON/OFF")을 2026-11-03 정정에 맞춰 고치고 재렌더한다. T-M3의 "읽는 법 (인과, rate 아님)" 문단은 #256
   `gen_table_m3.py`의 SUFFIX에도 복제돼 있다. **재렌더 전까지 보고서와 영상에 넣지 않는다.**
4. **F-M2 캡션.** "the 7.5.6 regression was introduced by the R1 fix. Observed."로 끝나지만 이 인과 서술은 §5.2 기준 inferred다.
5. **EXP-0 재생성 시 확인.** pre-merge 리포트의 `targets`가 `["unspecified"]`인데 `index.json`의 `target_id`는 `7.5.2`다.

EXP-2 산출물은 EXP-3에 GO 규칙을 적용한 뒤에 정한다(현재 TBD).

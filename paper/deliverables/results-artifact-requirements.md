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
| T-EXP3-4 인프라 참고값 | `paper/tables/exp3-infra.md` | `by_target.<tid>.{item2_p95_full_step.pooled,item3_throughput.summed,environment}` · `.item7_hazard_proxy.zero_hit`(그 타깃 hit 0일 때만). 시간 값의 표기는 공백 5 |
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
| F-M2, F-M3 | `paper/figures/m2-cross-release-evidence.png`, `m3-blind-ablation.png` | `render_m2_cross_release.py`, `render_m3_blind_ablation.py` | 2026-11-06 재렌더, 철회·혼동 문구 정정 완료 |

## 생성 전에 메워야 할 공백

1. **EXP-3 생성기가 없다.** #219 렌더러는 item을 최상위에서 읽어 스키마 2에서 실패한다(재현:
   `KeyError: 'item1_aborts'`, 그림은 `KeyError: 'item5_first_contract_index'`). 면책 문구도 EXP-0 전용이다. 위 EXP-3 5종은
   `by_target`을 읽는 새 생성기가 필요하다.
2. **#256 `ARTIFACTS`에 EXP-3 행이 없다.** 새 생성기와 함께 추가하고, `exp0-survival.png` 행의 "pending lane 6 #219" 메모를
   갱신한다.
3. **#256 `gen_table_m3.py`의 SUFFIX에 T-M3 옛 문단이 복제돼 있다.** T-M3 "읽는 법"을 2026-11-06에 정정했으므로, #265와 #256을 둘 다
   머지하면 `tests/test_gen_tables.py::test_m3_render_byte_identical_to_committed`와 `--verify` T-M3 행이 깨진다. 머지 때 SUFFIX를
   새 T-M3 본문에 맞춘다(W1). T-M2는 바꾸지 않았다.
4. **EXP-0 재생성 시 확인.** pre-merge 리포트의 `targets`가 `["unspecified"]`인데 `index.json`의 `target_id`는 `7.5.2`다.
5. **시간 값에는 clock을 표시한다.** `item2`·`item3`은 monotonic clock 기록이고 `summed.exec_per_hour`는 스트림당 값이다. 기록값과
   실시간 환산값을 나란히 적는다. EXP-0 배율 1.091(W2 확정)은 EXP-0 전용이므로 EXP-3에는 그 실행의 배율을 따로 확정해 쓴다. 호스트 전체
   처리량은 `registration.json`→`matrix.json`의 `created_at`으로 직접 계산한다. 실행 수로 세는 값은 영향이 없다.

EXP-2 산출물은 EXP-3에 GO 규칙을 적용한 뒤에 정한다(현재 TBD).

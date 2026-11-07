# 결과 표·그림 요구 목록 (EXP-3·EXP-2 종료 후 W2 생성용, W1 PR-G 출력 명세)

보고서 [§7.6·§7.7](capstone-report-draft.md)과 논문 §5.6을 채우는 데 필요한 산출물이다. 스키마 기준은 main의 `scripts/analyze_exp0.py`와
`paper/figures/render_exp0_survival.py`, `scripts/regenerate_paper_artifacts.py`다(2026-11-06 확인).

**입력 생성.** 등록 파일이 2개라 리포트도 2개다. 합치지 않는다.

```bash
PYTHONPATH=src python3 scripts/analyze_exp0.py --index <exp3-run>/summaries/index.json --format json --output <out>/exp3-train-report.json
PYTHONPATH=src python3 scripts/analyze_exp0.py --index <exp2-run>/summaries/index.json --format json --output <out>/exp2-holdout-report.json
```

**W3 확인 필요.** 이 절의 열 구성과 아래 규칙은 W4 안이고 W3 연구 검증 전이다. W3가 지정한 필수 값은 I, E, Holm p, 빠른 쪽, 미완주 수·원인, 세 정책 `reject_at_alpha`, 어긋남 수다. 값 자리는 W3 판 문서(결과 전 작성)의 `{ }`와 맞춘다.

**필드 상태.** "기존"은 main의 `analyze_exp0.py`에 있는 필드, "신규"는 D041 분석 코드 수정이나 #295에서 생기는 값이다. 신규 값의 필드 이름과 리포트 경로(`by_target.<tid>.` 여부)는 그 PR 뒤 W1이 확정해 이 표에 적는다. 아래 `T5` = `item5_first_contract_index`, `T` = `T5.by_arm.<arm>.t_first_combined_c1_or_c2`이고 타깃 1개여도 등록 대비가 있으면 `by_target.<tid>.` 아래다(#295, 미머지).

## EXP-3 train 산출물 (`exp3-train-report.json`)

| ID | 파일 | 보고서 | 열 → 입력 |
| --- | --- | --- | --- |
| T-EXP3-1 | `paper/tables/exp3-train-arms.md` | 표 7-B | 분석 캠페인=`T.denominator_cells_in_risk_set` · 완주·abort=`item1_aborts.by_arm.<arm>` · 기록 어긋남=**신규** · 첫 사건=`T.number_observed` · 중앙값=`T.km_median_executions`(null이면 "미도달") · U_viol 평균(합)=`item6_dense_signals.by_arm.<arm>.u_viol.{mean_per_cell,total_unique_c1_c2_fingerprints}` · 머리 줄 n, m, 원인=**신규**(index `deadline`, #295) |
| T-EXP3-2 | `paper/tables/exp3-go-inputs.md` | 표 7-B2 | E=세 arm `T.number_observed` 합(abort 포함, invalid 제외, D040-D11) · r=실시간 직접 계산. `matrix.json`은 호출마다 덮어써 재시작 때 어긋나므로 PR-B 뒤 `cell-results.jsonl`의 첫 start~마지막 end로 하고 W1이 확정한다 · e=**신규**(기록/계획 step) · H_rem=EXP-3 종료 시각에서 계산 · 용량=식 · 인프라 실패 비율=(abort + 어긋남)/전체 셀(D041) · 결과 칸은 비운다(W3 적용) |
| T-EXP3-3 | `paper/tables/exp3-dense-signals.md` | 논문 §5.6 | T-EXP2-6과 같은 열, 같은 제목 "탐색, effectiveness 아님"(`exp3-v1` §4). 값은 holdout과 합치지 않는다. 신규 필드 구현은 PR-D(W3 지정) |
| F-EXP3-1 | `paper/figures/exp3-train-survival.png` | 그림 | `T.{km_curve,censored_times,denominator_cells_in_risk_set}`. 제목에 "탐색, 확증 아님" |

## EXP-2 holdout 산출물 (`exp2-holdout-report.json`, GO일 때만)

| ID | 파일 | 보고서 | 열 → 입력 |
| --- | --- | --- | --- |
| T-EXP2-1 | `paper/tables/exp2-holdout-arms.md` | 표 7-A | T-EXP3-1과 같은 열 + 사건 전 abort=**신규**(abort 셀 중 abort 전 사건이 없는 수, 판 문서 붙는 문장 "abort 차이가 기각에 기여") · 머리 줄 버전=등록 값 |
| T-EXP2-2 | `paper/tables/exp2-holdout-contrasts.md` | 표 7-A2 | 대비·순서=`confirmatory.contrasts[].{contrast,order}` · seed 블록=`number_seed_blocks` · I=**신규**(D041-5, D040-D14, 총 사건으로 대체 금지) · E=`total_events` · 순열 p=`permutation.p_value` · Holm p=`holm_adjusted_p` · 기각=`reject_at_alpha` · 빠른 쪽=`faster_arm` · U_viol 방향=**신규**(D041-6, arm `mean_per_cell`의 차, `exp2-v1` §5) · exclude·censor-at-budget 기각=**신규**(D041-6) |
| T-EXP2-3 | `paper/tables/exp2-holdout-notes.md` | 표 아래 병기 | 미완주 제외 seed 수와 셀별 원인(index `deadline`, #295), 기록 어긋남 수와 민감도(**신규**), abort 3분할과 watchdog 사유 별도 줄(`exp2-v1` §8 정의: target 미시작, 실행 후 소실, 첫 오류 미확인. **분석기 값이 아니다.** W2가 docker events, `.calls.jsonl`, `error_chain`에서 손으로 옮긴 입력 파일을 읽고, 그 파일이 없으면 실패한다), 결과 미상 step(**신규**), 대비별 invalid 제외 수, 운영 중단 여부·시각(LOG 입력) |
| T-EXP2-4 | `paper/tables/exp2-abort-sensitivity.md` | 논문 §5.6 | 1차=`T` · `T5.sensitivity.{primary_policy,policies.{exclude,censor-at-budget}.by_arm.<arm>.{number_observed,number_right_censored,number_in_risk_set,km_median_executions}}` · `--contingency`를 줬으면 `arm_abort_independence` |
| T-EXP2-5 | `paper/tables/exp2-infra.md` | 논문 §5.6 | `item2_p95_full_step.pooled`, `item3_throughput.summed`, `environment`. 시간 값의 표기는 공백 5 |
| T-EXP2-6 | `paper/tables/exp2-dense-signals.md` | 논문 §5.6 | arm별 1행, 제목에 "탐색, effectiveness 아님"(D040-D20): 셀별 새 키와 arm 안 고유 키=**신규**, rejected 비율=`item6_dense_signals.by_arm.<arm>.rejected_ratio.value`, 관찰 실패 종류별 수=**신규**(지금은 `observation_failures_total`뿐), `feedback_eligible=false` 비율=**신규** |
| F-EXP2-1 | `paper/figures/exp2-holdout-survival.png` | 그림 | F-EXP3-1과 같은 필드. 풀링 금지 |

## 생성기 규칙 (PR-G)

1. **판정을 채우지 않는다.** 표 7-A2의 판정 줄과 표 7-B2의 결과 칸은 비운다. 값만 내고 판정표를 자동화하지 않는다(D041-6). 판은 사람이 W3 판 문서로 고른다.
2. **train에 검정 값을 넣지 않는다.** 표 7-B에 p, 기각, 빠른 쪽, HR 열이 없다. 생성기가 이 값을 내면 실패로 본다.
3. **합치지 않는다.** train, holdout, 파일럿, 벤치마크 값을 한 표에 넣지 않는다.
4. **값이 없으면 실패한다.** 입력 필드가 없으면 0이나 빈칸으로 채우지 않고 멈춘다. 0은 실제 0일 때만 적는다. 값 없음이 정의된 경우만 문구로 적는다: 중앙값 null은 "미도달", 사건 0 대비의 빠른 쪽은 "없음".
5. **고정 머리 문구를 함께 낸다.** 표 7-B "탐색, 기노출, 확증 아님". 그림 제목도 같다.
6. **재현한다.** 입력 JSON이 같으면 바이트가 같고 `--check`로 대조한다. `tests/test_gen_tables.py`에 합성 리포트 시험을 더한다. 소수 자릿수(W3): p와 Holm p는 넷째 자리, .0001 미만은 "< .0001", 비율은 셋째 자리. HR은 넣지 않는다.
7. **시간 값은 시계를 표기한다**(공백 5). 실행 수는 영향이 없다.

## EXP-0·기존 산출물

| ID | 파일 | 생성기 | 입력·상태 |
| --- | --- | --- | --- |
| T-EXP0 | `paper/tables/exp0-summary.md` | `paper/figures/render_exp0_survival.py --report <json> --no-figure` | 입력은 `experiments/summaries/exp0-20261105-report.json`(스키마 1). 2026-11-07 재생성 완료. `regenerate_paper_artifacts.py --regenerate`는 이 생성기를 실행하지 않으므로 직접 실행한다. 표의 p50·p95는 monotonic 기록값이다(공백 5) |
| F-EXP0 | `paper/figures/exp0-survival.png` | 같은 스크립트 (matplotlib 임시 환경) | `item5_first_contract_index.by_arm.<arm>.t_first_combined_c1_or_c2.{km_curve,censored_times}`. 2026-11-07 생성 완료. hit 0이므로 곡선은 사건 없이 평평하고 세 arm이 겹쳐 맨 위 S-u만 보인다 |
| T-M2, T-M3 | `paper/tables/m2-cross-release-evidence.md`, `m3-blind-ablation.md` | `scripts.gen_table_m2`, `scripts.gen_table_m3` (#256) | `experiments/repro/evidence/summary.json`, `node-self-discovery-mechanism-v1.md`. `--check`로 바이트 대조 |
| F-M2, F-M3 | `paper/figures/m2-cross-release-evidence.png`, `m3-blind-ablation.png` | `render_m2_cross_release.py`, `render_m3_blind_ablation.py` | 2026-11-06 재렌더, 철회·혼동 문구 정정 완료 |

## 생성 전에 메워야 할 공백

1. **명세 확정, 구현 대기: EXP-3·EXP-2 생성기.** #219 렌더러는 item을 최상위에서 읽어 스키마 2에서 실패한다(재현:
   `KeyError: 'item1_aborts'`, 그림은 `KeyError: 'item5_first_contract_index'`). 면책 문구도 EXP-0 전용이다. 위 표와 규칙이 출력 명세이고,
   구현은 W1 PR-G(PR-A·B 뒤, 11/18 전 목표)다. 구현 전까지 11/25 표 생성은 돌지 않는다.
2. **명세 확정, 구현 대기: `ARTIFACTS` 행.** 위 파일 전부를 PR-G에서 `scripts/regenerate_paper_artifacts.py`에 추가한다. `exp0-survival.png` 행의
   메모는 해소됐다(optional 행, 커밋된 PNG는 `--verify`가 크기로 확인).
3. **해소됨: 표 생성기의 옛 문구.** `gen_table_m2.py`·`gen_table_m3.py`는 2026-11-06 정정 문구로 맞춰 #256으로 머지됐다. T-M2·T-M3를 고칠 때는
   생성기 리터럴도 함께 고친다. `tests/test_gen_tables.py`와 `--verify`가 바이트로 대조한다.
4. **EXP-0 리포트의 타깃 필드.** JSON `targets`는 `["unspecified"]`이고 실제 타깃은 `7.5.2`다(공식 리포트 편차 5).
5. **시간 값에는 clock을 표시한다.** `item2`·`item3`은 monotonic clock 기록이고 `summed.exec_per_hour`는 스트림당 값이다. 기록값과
   실시간 환산값을 나란히 적는다. 배율은 실행마다, 한 실행 안에서도 변하므로(파일럿 셀별 1.00~1.10) 단일 배율로 환산하지 않는다. EXP-0 배율
   1.091(W2 확정)은 EXP-0 전용이다. EXP-3의 시간 값은 셀별 배율로 환산하고 값마다 시계를 표기한다. 호스트 전체 처리량은 실시간에서 직접
   계산한다(`registration.json`→`matrix.json`의 `created_at`). 실행 수로 세는 값은 영향이 없다.

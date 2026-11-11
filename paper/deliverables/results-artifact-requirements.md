# 결과 표·그림 요구 목록 (EXP-3 train · EXP-2 holdout)

보고서 결과 칸과 논문 §5.6을 채우는 산출물이다. 표 번호와 파일 이름의 기준은 생성기다:
`scripts/gen_exp3_tables.py`의 `TABLES`와 `scripts/regenerate_paper_artifacts.py`의 `_EXP3_TABLES`·`_EXP3_FIGURES`
(실행 SHA E `bed077a`에 있다). 이 문서와 생성기가 다르면 생성기가 맞고 이 문서를 고친다. 실데이터 실행은 아직 없다.

## 생성기 규칙

생성기 머리말이 이 문서를 출력 명세로 가리킨다. 규칙은 다음 일곱 개다.

1. 판정을 쓰지 않는다. 판정 줄과 GO 결과는 사람이 채운다.
2. train에는 검정값을 쓰지 않는다. 확증 절이 든 train 리포트는 거부한다.
3. 풀링하지 않는다. 표 하나에 리포트 하나, 역할 하나, 타깃 하나다.
4. 필드가 없으면 표를 멈춘다. 0은 값이 0일 때만 쓴다. 정의된 "값 없음" 낱말은 KM 중앙값이 null일 때의 "미도달"과 사건 0에서 빠른 arm이 없을 때의 "없음" 둘뿐이다.
5. 표마다 고정 머리 문구가 붙는다.
6. 같은 입력은 같은 바이트를 낸다(`--check`).
7. 시간 값에는 시계를 적는다.

```bash
python -m scripts.gen_exp3_tables --artifact <ID> --report <report.json> --out <table.md>
python -m scripts.gen_exp3_tables --artifact <ID> --report <report.json> --check <table.md>
```

## 표와 그림

입력 필드는 각 생성 함수(`t_exp3_1` … `t_exp2_6`)가 정한다. 여기에는 다시 적지 않는다.

| ID | 생성 표 제목(요지) | 파일 | 입력 |
| --- | --- | --- | --- |
| T-EXP3-1 | 표 7-B. train arm별(탐색, 기노출, 확증 아님) | `paper/tables/exp3-train-arms.md` | `exp3-train-report.json` |
| T-EXP3-2 | 표 7-B2. GO 판정 입력 | `paper/tables/exp3-go-inputs.md` | train 리포트 + `exp3-train-cell-results.jsonl` + `exp3-train-go-decision.json` |
| T-EXP3-3 | train dense 지표(탐색, effectiveness 아님) | `paper/tables/exp3-dense-signals.md` | train 리포트 |
| T-EXP2-1 | 표 7-A. holdout arm별 | `paper/tables/exp2-holdout-arms.md` | `exp2-holdout-report.json` |
| T-EXP2-2 | 표 7-A2. 대비별 확증 결과(Holm 순서, 1차 정책 censor-at-abort) | `paper/tables/exp2-holdout-contrasts.md` | holdout 리포트 |
| T-EXP2-3 | holdout 표 아래 병기(0이어도 적는다) | `paper/tables/exp2-holdout-notes.md` | holdout 리포트 + `exp2-holdout-hand-input.json`(abort 3분할, 손 입력) |
| T-EXP2-4 | holdout abort 정책 민감도 | `paper/tables/exp2-abort-sensitivity.md` | holdout 리포트 |
| T-EXP2-5 | holdout 인프라 측정(호스트별) | `paper/tables/exp2-infra.md` | holdout 리포트 |
| T-EXP2-6 | holdout dense 지표(탐색, effectiveness 아님) | `paper/tables/exp2-dense-signals.md` | holdout 리포트 |
| F-EXP3 | train KM 곡선 | `paper/figures/exp3-train-survival.png` | train 리포트 |
| F-EXP2 | holdout KM 곡선 | `paper/figures/exp2-holdout-survival.png` | holdout 리포트 |

입력 파일은 모두 `experiments/summaries/` 아래다.

**보고서 표 대응.** 표 7-A = T-EXP2-1, 표 7-A2 = T-EXP2-2, 표 7-B = T-EXP3-1, 표 7-B2 = T-EXP3-2.
D12 판정 칸을 고르는 근거는 T-EXP2-2(대비별 확증 결과)와 T-EXP2-4(abort 민감도)다. T-EXP3-2는 GO 입력표이고 판정 근거가 아니다.
확증은 holdout 대비의 Holm 결과뿐이고, train 표에는 검정값이 없다(규칙 2). 옛 표 7-C(fix-verification)는 D040-D3으로 없앴다.
NO-GO나 GO 미산출이면 EXP-2를 실행하지 않으므로 T-EXP2-* 와 F-EXP2는 만들지 않는다(exp2-v1 §5 "연장 금지").

## EXP-0·기존 산출물

| ID | 파일 | 생성기 | 입력·상태 |
| --- | --- | --- | --- |
| T-EXP0 | `paper/tables/exp0-summary.md` | `paper/figures/render_exp0_survival.py --report <json> --no-figure` | 입력은 `experiments/summaries/exp0-20261105-report.json`(스키마 1). 2026-11-07 재생성 완료. `regenerate_paper_artifacts.py --regenerate`는 이 생성기를 실행하지 않으므로 직접 실행한다. 표의 p50·p95는 monotonic 기록값이다(공백 5) |
| F-EXP0 | `paper/figures/exp0-survival.png` | 같은 스크립트 (matplotlib 임시 환경) | `item5_first_contract_index.by_arm.<arm>.t_first_combined_c1_or_c2.{km_curve,censored_times}`. 2026-11-07 생성 완료. hit 0이므로 곡선은 사건 없이 평평하고 세 arm이 겹쳐 맨 위 S-u만 보인다. 보고서에는 쓰지 않는다 |
| T-M2, T-M3 | `paper/tables/m2-cross-release-evidence.md`, `m3-blind-ablation.md` | `scripts.gen_table_m2`, `scripts.gen_table_m3` (#256) | `experiments/repro/evidence/summary.json`, `node-self-discovery-mechanism-v1.md`. `--check`로 바이트 대조 |
| F-M2, F-M3 | `paper/figures/m2-cross-release-evidence.png`, `m3-blind-ablation.png` | `render_m2_cross_release.py`, `render_m3_blind_ablation.py` | 2026-11-06 재렌더, 철회·혼동 문구 정정 완료 |

## 남은 공백과 주의

1. **실데이터 실행이 없다.** EXP-3·EXP-2 생성기는 합성 입력(`tests/test_exp3_synthetic_e2e.py`)으로만 돌았다. 생성 표 → HWP 칸 → 영상 자막 경로는 아직 끝까지 돌려 보지 않았다.
2. **T-EXP2-3의 abort 3분할은 손 입력이다.** 생산 도구가 없다. 입력 절차는 본실험 런북을 따른다.
3. **해소됨: 표 생성기의 옛 문구.** `gen_table_m2.py`·`gen_table_m3.py`는 2026-11-06 정정 문구로 맞춰 #256으로 머지됐다. T-M2·T-M3를 고칠 때는
   생성기 리터럴도 함께 고친다. `tests/test_gen_tables.py`와 `--verify`가 바이트로 대조한다.
4. **EXP-0 리포트의 타깃 필드.** JSON `targets`는 `["unspecified"]`이고 실제 타깃은 `7.5.2`다(공식 리포트 편차 5).
5. **시간 값에는 clock을 표시한다.** `item2`·`item3`은 monotonic clock 기록이고 `summed.exec_per_hour`는 스트림당 값이다. 기록값과
   실시간 환산값을 나란히 적는다. 배율은 실행마다, 한 실행 안에서도 변하므로(파일럿 셀별 1.00~1.10) 단일 배율로 환산하지 않는다. EXP-0 배율
   1.091(W2 확정)은 EXP-0 전용이다. EXP-3의 시간 값은 셀별 배율로 환산하고 값마다 시계를 표기한다. 호스트 전체 처리량은 실시간에서 직접
   계산한다(`registration.json`→`matrix.json`의 `created_at`). 실행 수로 세는 값은 영향이 없다.

# EXP-3 사전등록 v1 — train (탐색, 인프라 게이트)

> **상태: 동결 전 초안 (2026-11-11).** 아직 실행할 수 없다. 블록의 `TBD-FREEZE` 값이 남아 있는 동안 파서(`src/inodefence/evaluation/rds_preregistration.py`)가 `engine_sha`와 digest 형식 오류로 거부한다. 의도된 동작이다. 11/18에 [exp2-v1](exp2-v1.md)과 **함께** 동결한다(D040-D1).
>
> **기준.** [D040](../../docs/DECISIONS.md#d040--exp-3-동결-전-재판정-위험도-파일럿-4040-반영)(D1~D21), [D041](../../docs/DECISIONS.md#d041--동시-실행-벤치마크-단계-a-승인과-파일럿-seed-재사용)(마감·abort 집계·운영 중단·a 정의), [D042](../../docs/DECISIONS.md#d042--인프라-정지-규칙-연속-3셀-기록-없음)·[D043](../../docs/DECISIONS.md#d043--go-입력-r에서-등록된-인프라-정지-공백을-뺀다)(#331로 main 반영), [D044](../../docs/DECISIONS.md#d044--2호스트-동시-실행-벤치마크-설계-v3)·[D045](../../docs/DECISIONS.md#d045--holdout-상태-확인의-위반어댑터-호환-정의와-train-abort-분모), [D046](../../docs/DECISIONS.md#d046--인프라-정지-대응case-단위-재실행과-d040-d21-재개-판정)(#342로 main 반영), [노출 원장](exposure-ledger.md), [규모 산정](exp3-sizing-20261107/README.md), [D047](../../docs/DECISIONS.md#d047--본실험-선행-조건-단순화-jobs2-고정과-호스트별-적격성-검증), [호스트별 적격성 검증 v1](../configs/host-qualification-v1.md). 동시 실행 벤치마크 v3(`experiments/configs/concurrency-scaling-v3.md`)는 본실험 선행 조건이 아니다(D047). 이 초안과 D040이 다르면 D040이 맞다.
> 이전 초안(#264 `e11d302`, 11/05판)은 D040 이전 구조라 대체한다. 그 판의 한 파일 다중 타깃 구조, 7.5.6/7.5.7·py-tarfile 타깃, S-a, `sentinel_count = 3`, `event_threshold = 5`는 쓰지 않는다.
>
> **"ORCH 결정 2026-11-11"** 표시는 D040에 없던 실행 세부를 오케스트레이터가 데이터 이전에 정한 것이다. 지웅 승인은 이 PR의 머지로 한다. 이 표시에 해당하는 항목은 모두 **동결 전 초안이며, 지웅 승인 = PR 머지**다: 호스트 키(`host.<id>.*`), 할당 규칙(`seed_assignment_*`), sentinel seed 재사용, start_denied 제외, 인프라 정지 case 재실행(D046), watchdog 뒤 정지, train abort 분모(D045).

## 1. 목적과 성격

EXP-3 train은 **탐색이며 확증이 아니다**(D040-D1·D20). n=20/arm의 결합 검정력은 약 .17이다(등록 판정(순열) .174, 800회, 표준오차 .013; D040-D1). 하는 일은 셋이다.

1. node-tar 7.5.2에서 R·D·S-u의 T_first·U_viol을 탐색적으로 보고한다(판정표·확증 아님).
2. **인프라 게이트:** holdout 확증(EXP-2, [exp2-v1](exp2-v1.md))을 돌릴지 정하는 GO 입력(§5)을 실측한다.
3. 같은 `engine_sha`, k, sentinel generator, budget, arm으로 holdout과 조건을 맞춘다(D040-D1 2항).

RQ 문장은 [research-questions v2](../../docs/research/design/research-questions.md)를 유지하고, 예측은 "T_first 중앙값 2배"가 아니라 **HR ≥ 2**로 표현한다(D040 서두, D20 "RQ 예측 대체"). A12는 보조다.

## 2. 기계판독 등록 블록

```preregistration
# EXP-3 train v1. TBD-FREEZE를 모두 채워 커밋해야 실행 유효(파서가 형식 오류로 거부).
experiment_id = exp3
engine_sha = TBD-FREEZE
# D040-D1 1항: train {9006..9025}. RESERVED·기존 노출(≤1415, 6100–6103, 6200–6207(예약), 6300–6303, 7001–7002, 8001–8003, 8101–8110, 9001–9005)과 겹치지 않음.
seeds = 9006, 9007, 9008, 9009, 9010, 9011, 9012, 9013, 9014, 9015, 9016, 9017, 9018, 9019, 9020, 9021, 9022, 9023, 9024, 9025
budget = 2000
vocabulary = observed-names
# D040-D6: R = seed-restart. D3: S-a 없음.
arm.R = unretained-seed-restart-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
# 타깃 1개여도 targets.<id> 형식(D040-D1 5항). 7.5.2는 원장에 행이 있으므로 pre-exposed(D15).
targets.node-tar-7.5.2.extractor = node-tar
targets.node-tar-7.5.2.version = 7.5.2
# D18: 빌드 1회 뒤 이미지 id 고정, docker save 보관. 적격성 실행과 같은 id여야 한다.
targets.node-tar-7.5.2.image_digest = TBD-FREEZE
targets.node-tar-7.5.2.role = train
targets.node-tar-7.5.2.hypothesis = H-A
targets.node-tar-7.5.2.exposure = pre-exposed
targets.node-tar-7.5.2.exposure_ref = experiments/preregistration/exposure-ledger.md
# 두 파일 대칭(ORCH 결정 2026-11-11 #7). 11/18~25 원장 변경 금지(D040-D1 3항).
exposure_ledger = experiments/preregistration/exposure-ledger.md
exposure_ledger_sha256 = TBD-FREEZE
sentinel_generator_id = sentinel-names/seed-random-v1
# ORCH 결정 #3: EXP-0·파일럿·벤치마크와 같은 값(§7 공개).
sentinel_generator_seed = 20261104
# D040-D8: k=5.
sentinel_count = 5
observer_integrity_policy = invalid-continue
hit_definition = c1-or-c2-and-contract-violated
c0_counts_as_hit = false
denominator = all-cells-including-abort
abort_reporting = right-censored
rule_of_three_unit = campaign
primary_endpoint = t_first
execution_mode = per-case-container
# D047: 두 호스트 모두 jobs=2 고정(사람 결정, 벤치마크 선정값 아님).
jobs_max = 2
campaign_watchdog_seconds = 10800
disk_pause_fraction = 0.9
interim_analysis = forbidden
# D041: 이 시각 뒤 새 셀 금지, 실행 중 셀은 끝까지 보존.
execution_deadline = 2026-11-25T12:00:00+09:00
# --- 호스트 키(D047, §3). 현재 파서(fa8ccb4)는 두 호스트 키를 모두 요구한다. 참여 집합 P(1~2개)는 할당 파일(make_seed_assignment.py --participants)에 기록되고 그 sha로 고정된다. 게이트 강제. ---
host.HOST1.jobs = 2
host.HOST1.docker_engine = TBD-FREEZE
host.HOST2.jobs = 2
host.HOST2.docker_engine = TBD-FREEZE
# §3: 두 호스트면 alternate-v1, 한 호스트면 20 seed 전부 그 호스트. 할당 파일과 sha는 동결 시 고정.
seed_assignment_rule = alternate-v1
seed_assignment_sha256 = TBD-FREEZE
```

**블록 밖 규칙.**

- `host.<id>.jobs`, `host.<id>.docker_engine`, `seed_assignment_rule`, `seed_assignment_sha256`은 **게이트가 강제한다**(W3 구현, 검증 후 동결; ORCH 결정 #1·2026-11-11 할당 결정). 해당 호스트의 `--jobs`, 실제 Engine 버전, 할당 파일 sha 중 하나라도 등록값과 다르거나, 할당 파일이 `alternate-v1` 규칙으로 재생성한 결과와 바이트 동일하지 않으면 런처가 실행을 거부한다. 강제 구현이 검증되기 전에는 동결하지 않는다.
- `host.<id>.jobs`는 D047에 따라 2이고, `docker_engine`은 그 호스트 적격성 preflight의 고정값이다(HOST1 29.8.0, HOST2 29.9.3). 적격성은 그 호스트·그 Engine·그 실행 SHA에서만 유효하다. 적격성 시작부터 EXP-2 끝까지 Engine·Docker Desktop·WSL 버전을 바꾸지 않는다.
- `campaign_watchdog_seconds = 10800`은 적격성 실행 등록 파일과 같아야 한다.

## 3. 참여 호스트와 할당 (D047, ORCH 결정 #5)

- **참여 호스트(D047).** 참여 호스트 집합은 동결 시점(2026-11-18)에 한 번 고정하며 train과 holdout(exp2-v1) 모두에 적용한다. 참여 호스트는 동결까지 [호스트별 적격성 검증 v1](../configs/host-qualification-v1.md)을 사전 고정 기준으로 통과했고 교차 호스트 비교의 투입 보류(설명되지 않는 중대한 불일치 2셀 이상) 상태가 아닌 호스트(1개 또는 2개)다. '교차 비교 미완'(비교 가능 셀 10개 미만)이면 동결 전에 지웅이 그 호스트의 투입 여부를 정한다. 동결까지 이 조건을 충족하지 못한 호스트는 본실험 전체에 참여하지 않으며, 동결 뒤에 충족해도 합류하지 않는다. 모두 본실험 oracle 값이 없을 때 정한다. 할당 파일은 동결 때 그 집합으로 만든다: 두 호스트면 `alternate-v1`, 한 호스트면 20 seed 전부 그 호스트. 할당 sha는 동결하고 그 뒤 바꾸지 않는다. 한 호스트가 멈춰도 seed를 다른 호스트로 옮기지 않는다.
- **seed 블록 단위:** 한 seed의 R·D·S-u 세 셀은 같은 호스트에서 돈다.
- **두 호스트일 때 train 할당은 동결 시 고정하는 교대 규칙이다:** 9006→HOST1, 9007→HOST2, 9008→HOST1, …, 9025→HOST2(10/10). 할당 파일 `experiments/preregistration/exp3-v1-seed-assignment.json`을 동결 커밋에 넣고 그 sha256을 `seed_assignment_sha256`에 적는다. 벤치마크 값은 할당 입력으로 쓰지 않는다.
- **호스트 안 실행 순서:** 할당된 seed의 오름차순, seed 블록 안에서는 런처의 arm 회전 순서다. 마감에서 잘리는 것이 뒤쪽 블록뿐이게 한다(D040 "블록 순서로 실행").
- 호스트는 **기록 요인**이다. 호스트마다 jobs, Engine·Desktop·WSL 버전, mono/real 배율, 공유 실행 경로 해시(#336 `SHARED_PATH_FILES` 16개 파일)를 기록한다. 호스트 간 realtime 시계 차는 동결 시점과 GO 시점에 기록한다.
- **교차 호스트 공통 seed 비교(D047, 지웅 결정 2).** 적격성 검증의 교차 호스트 공통 seed 비교는 결과를 보고한다. 불일치 셀 ≥ 2 또는 비교 불가 셀 ≥ 2이면 각 호스트에서 해당 셀을 1회 재실행해 자기 원 실행과 대조하고, 두 호스트 모두 자기 재실행과 일치하는데 호스트 사이에만 다른 셀이 2개 이상이면(설명되지 않는 중대한 불일치) 기준 호스트(HOST1)가 아닌 호스트의 투입을 보류하고 원인을 보고한다. 보류 해제는 원인 기록과 지웅 승인으로 동결 전에만 하며, 동결 때 보류 중이면 그 호스트는 참여하지 않는다. 이 판단은 본실험 시작 전에, oracle 값은 읽지 않고, 적격성 실행의 판정값(oracle + feedback 키)을 해시로만 비교한 일치 여부로 한다. 재실행이 1회라 계통적 비결정성은 놓칠 수 있다. 재실행 뒤에도 비교 가능 셀이 10개 미만이면 '교차 비교 미완'으로 보고하며, 이는 자동 보류 사유가 아니라 동결 전 지웅 결정 항목이다. 이 비교는 비결정성과 호스트 종속을 그 자체로 구분하지 못하므로, 참여한 두 호스트 사이에 '설명 필요'였던 셀이 있으면 언제나 내는 호스트별 민감도 표와 본 분석 결과 옆에 해석 주의 문구를 붙인다. 분석 구조와 판정은 바꾸지 않는다. 호스트는 언제나 기록 요인이다.

## 4. 실행 제어

| 항목 | 규칙 | 출처 |
| --- | --- | --- |
| 재시도 | 레코드 없는 셀만 그 자리에서 즉시 1회, 셀당 최대 2회. `start`만 남은 시도도 1회로 센다. 앞 시도 파일은 `attempts/`에 보존한다. **시작 게이트가 거부한 시도(start_denied)는 실행되지 않은 것이므로 재시도 횟수에 세지 않고, 그 수를 따로 적는다**(ORCH 결정 2026-11-11, W3 배선 설계) | D042 1항 |
| case 단위 인프라 재실행 | 셀 내부 경로에서 항상 켜져 있고, 런처 셀 재시도와는 별개다. ① (D046 ① 최종 문장, #335 `95e25b6`) 한 케이스 시도가 BackendError(OutputLimitError 제외)로 실패했고 그 시도의 비정상 Docker 호출이 1개 이상이며 모두 타임아웃이면, 또는 시도가 TIMED_OUT을 냈는데 마지막 target start 뒤 첫 inspect가 created이거나 하네스 kill 없이 exited이고 데몬 FinishedAt−StartedAt가 [0, 5.0]초이면, 그 시도는 결과가 아니라 폐기한다. 데몬이 시도가 만든 모든 컨테이너(identity probe 포함)의 부재를 양성 응답으로 확인하면, 새 컨테이너·새 run root로 같은 케이스를 재실행하고 예산·RNG·step을 소비하지 않는다. 확인은 180초 이후에 새로 시작하지 않는다(진행 중 확인은 약 50초 더 걸릴 수 있다). 비정상 호출 = 예외, 타임아웃, 잘림, 또는 "no such container"가 아니면서 container start가 아닌 호출의 nonzero 응답. ② timed_out 재분류는 정지의 양성 증거가 있을 때만 한다. target start timeout 뒤 첫 inspect가 Running이면 base대로 TIMED_OUT이다. created이거나, 스스로 exited이고 데몬 실행시간이 0~5.0초이면 재실행한다. 그 밖은 base 동작이다. ③ 상한은 케이스당 2회, 캠페인당 4회, 부재 확인 180초이고, 넘으면 abort한다. 예외형 정지는 원래 예외를 다시 던지고, TIMED_OUT에서 정지로 재분류된 케이스는 runtime_call abort가 된다(base에서는 TIMED_OUT 결과였을 경우). ④ 기록 결과는 마지막 시도의 것이다. 폐기 시도는 arm별로 집계하고(보고서 `infra_reexecutions`, abort 스텁 `infra_reexecution_count`), 폐기 시도의 oracle 결과는 기록하지 않는다. 재실행이 있었던 캠페인을 뺀 민감도를 함께 내며, arm별 제외 수를 적고 확증 판정에는 쓰지 않는다. ⑤ 정지 시간은 벽시계(H_rem·처리량)에 포함한다 | D046(초안), ORCH 결정 2026-11-11 |
| 인프라 정지 | 레코드 없이 끝난 셀이 연속 3개면 새 셀과 새 재시도를 시작하지 않는다. 셀이 끝나는 순서로, 런처 잠금 안에서 센다. 레코드가 있는 셀이 끝나면 0으로 돌아간다. **호스트별 런처 단위로 독립**이다 | D042 2·3항, ORCH |
| 재개 | W2가 원인을 LOG에 적고(oracle 값 없이) 지웅이 별도 승인한다. `--resume-after-stop <승인 참조>` 필수. `--skip-build`와 W2 읽기 검증(Docker 응답, 세 이미지 id 일치)으로 하고, 같은 출력 폴더·`engine_sha`·이미지, 같은 설정 또는 jobs=2로 재개한다. `no-record`로 확정된 셀은 다시 돌리지 않는다 | D042 4항, D043 |
| 마감 | 2026-11-25 12:00 KST 뒤 새 셀 금지. 실행 중 셀은 끝까지 보존. 12:00까지 끝나지 않은 셀이 있는 seed는 블록 전체를 미완주로 제외하고, 제외 수와 원인을 보고한다. **호스트별로 독립 적용** | D041, D040-D20 |
| 운영 중단 | 최근 24시간에 끝난 셀이 20개 이상일 때 인프라 실패(abort + record-inconsistent) 비율이 .60 이상이면 멈추고 보고한다. oracle을 보지 않는다. 사람이 판단하고, 연장 사유가 아니다. **두 호스트 합산으로 판정하고, 호스트별 비율은 경보로 따로 낸다** | D040, D041, ORCH |
| 연장 금지 | 무조건이다. 마감과 n은 결과를 보고 바꾸지 않는다 | D040-D20 |
| 재시도·제한시간 조정 | D040-D21 재개 조건은 D046에서 충족 판정됐고(Stage A jobs=2 a = .333), #335 case 재실행이 들어갔다. 그 뒤 jobs 2 재측정은 호스트별 적격성 검증으로 한다(D047). 등록 뒤에는 조정하지 않는다 | D040-D21, D046, D047 |

## 5. GO 입력과 EXP-2 GO 식

GO는 자동이 아니다. EXP-2 시작 전에 W3가 train 리포트 값으로 적용하고 LOG에 남긴다(D040-D1 4항). 식은 D040-D11, 입력 정의는 D043이다.

**GO = E ≥ 1 ∧ ⌊H_rem·r ÷ (6000·e)⌋ ≥ 76 ∧ train abort ≤ .45**

- **E:** train에서 첫 C1∨C2가 있는 캠페인 수(3 arm 합산, abort 포함, invalid 제외).
- **r (2호스트, ORCH):** r = Σ_h r_h. r_h는 호스트 h의 `cell-results.jsonl` realtime으로 D043 산식을 따른다. T_up,h = T_wall,h − (그 호스트의 등록 정지 공백 g_i). 정지 공백은 **정지가 난 호스트에서만** 뺀다. 뺄 수 있는 공백은 `infrastructure-stop`·`infrastructure-resume` 기록으로 확인되는 구간뿐이다. r_wall(공백 포함)은 참고로 병기하며 GO 입력이 아니다. r은 참여 호스트(§3, 동결 때 고정)의 train r_h 합이다. 참여 호스트가 하나면 r = r_1이다. GO 식과 76·.45 임계는 바뀌지 않는다. 용량이 76 미만이면 holdout을 실행하지 않는다.
- **e:** 시도한 모든 셀(두 호스트 합집합)의 기록 step ÷ (시도한 셀 수 × budget).
- **H_rem:** 실행 마감 − max(마지막 `end`, 마지막 `infrastructure-resume`, GO 판정 시각). 실제 벽시계 값이다. GO 판정 시각은 W3가 GO 입력을 보기 전에 `experiments/summaries/exp3-train-go-decision.json`과 LOG에 적고, 적은 뒤에는 고치지 않는다(D043). 2호스트에서는 두 호스트 중 가장 늦은 시각을 쓴다.
- **train abort(분모는 D045, ORCH 결정 2026-11-11, 엄격한 쪽):** 분모는 시도한 셀(`start` 줄이 있는 run id)이고, 분자는 그중 abort + record-inconsistent + no-record다. 미시작 셀은 분모와 분자 모두에서 빼고 그 수를 병기한다. 등록 전체 셀 기준 값도 참고 줄로 함께 내며, GO 입력은 아니다.
- **미재개 정지 호스트(D047, 지웅 결정 1, D043 조건 6 개정):** GO 판정 시각에 미재개 정지 상태(마지막 인프라 사건이 미재개 `infrastructure-stop`)인 참여 호스트는 GO 산식의 r과 holdout 할당에서 제외한다. r은 가동 중인 참여 호스트의 train r_h 합이다. 제외된 호스트의 완료된 train 셀은 E, train abort, e, train 탐색 결과에 그대로 남고 r에서만 빠진다. 그 호스트의 미완주 train seed는 GO 판정 시각에 끝나지 않은 seed 블록이며, D041 마감 규칙을 준용해 train 분석에서 빼고 그 수를 보고한다. 제외된 호스트는 GO 뒤 train을 재개하지 않는다. GO 기준은 완화하지 않는다: 용량 ≥ 76(가동 호스트의 r), E ≥ 1, train abort ≤ .45(제외된 호스트의 시도 셀 포함), 가동 호스트의 train 기록 완전성 pass. 모든 참여 호스트가 미재개 정지면 GO는 미산출이고 W3는 EXP-2를 시작하지 않는다. 이 규칙은 train 결과 확인 전에 고정했다(D047, 지웅 결정 2026-11-11). "사전등록된 최소 seed 수·유효 표본 수·품질 기준"은 위 기존 GO 기준으로 읽는다(해석 (가) 확정, 지웅 #342 머지 2026-11-11).
- **GO 보류·보고(D047, 지웅 결정 1):** 다음 중 하나라도 해당하면 GO를 내지 않고 지웅 판단으로 올린다: (i) 정지 원인이 미확인이거나 인프라·외부 원인으로 분류되지 않음 (ii) 그 호스트의 train abort 전체가 입력 종속 패턴(같은 (arm, seed, step, case_id) 재발, 또는 그 호스트의 arm×abort 표에 대한 `arm_abort_independence` p ≤ .10)을 보임 (iii) 그 호스트의 cell-results·시작 게이트 상태·로그가 기록 완전성 검사를 통과하지 못하거나 증거 해시 대조가 안 됨 (iv) 정지가 oracle 값 열람 이후의 사람 판단으로 일어남. 판정 입력은 인프라 값과 기록 상태뿐이다. 보고에는 미완료 seed 수, 완주 seed 블록 수, 중단 원인, 호스트별 실제 완료 seed 목록을 적고, '부분 완료(호스트 X 미재개 정지)'로 표기하며, 'EXP-2 진행 가능(GO)'과 'holdout 전체 완료'를 따로 적는다.
- **유효 표본 기준(해석 (가) 확정, 지웅 #342 머지 2026-11-11):** 부분 GO에서 "사전등록된 최소 seed 수·유효 표본 수·품질 기준"은 이 등록의 기존 기준(GO 식, E ≥ 1, train abort ≤ .45, 기록 완전성, D041 마감 규칙)을 완화 없이 그대로 적용한다는 뜻이다. 별도의 최소 유효 표본 숫자는 등록하지 않는다. 완주 seed 블록 수는 언제나 보고한다([적격성 설계 §9.1](../configs/host-qualification-v1.md)).
- **NO-GO면** 규칙을 바꿔 다시 적용하지 않는다. EXP-3 train만 탐색 결과로 보고한다.
- 표 7-B2: r, r_wall, 정지 횟수, 누적 공백 시간, 호스트별 r_h(D043).

## 6. 측정과 분석 (탐색)

- **사건:** post-state oracle `C1 ∨ C2`이고 `contract_violated`인 step(규칙 상수, oracle 정의 C0/C1/C2 불변).
- **T_first:** 첫 사건까지의 실행 수. 완주 무사건은 budget에서, abort는 abort 시점에서 우측 중도절단한다.
- **U_viol:** `contract_id` + 정규화 evidence(dev/inode·타임스탬프·before/after 값 제외) 서명의 캠페인 안 고유 수. feedback eligibility와 무관하다.
- **통계(탐색, 판정표 없음):** 합동 2-arm 로그랭크, seed 블록 안 라벨 순열(D040-D20 "통계량 명시"), KM, A12. S-u vs R, S-u vs D를 보고한다. 이 결과로 holdout의 가설·arm·n·분석 기준을 바꾸지 않는다.
- **abort 3분할(D040-D20):** [파일럿 결과 메모](../summaries/exp3-hazard-pilot-v1-result.md) §4의 세 묶음으로 수를 낸다: (1) 컨테이너 create 뒤 start 없음, (2) 실행·종료 뒤 소실, (3) 이벤트 기록 범위 밖(미관찰). abort 정책 세 가지(`censor-at-abort` 기본, `censor-at-budget`, `exclude`; `src/inodefence/evaluation/survival.py:379-381` @bce75a2)의 민감도를 병기한다.
- **결과 미상 step(D040-D20):** 잘린 마지막 줄과 소실 step 수를 arm별로 병기한다. T_first에 영향이 있는지 셀마다 표시한다.
- **invalid:** `record-inconsistent` 셀은 재시도하지 않고, 그 arm이 든 대비에서 블록을 뺀다. 수를 따로 내며 1건부터 보고한다(D041).
- **dense 지표(EN-008, 설명용, D040-D20 "dense 지표 고정(집계 방식 포함)"):** 새 state key 수는 효과 지표가 아니다. 정의는 PR-D(#299)의 W3 정의를 따른다. arm별로 내고 합치지 않는다. 분석 셀만 쓴다(마감 제외 seed와 invalid 제외). 분모는 기록 step이다. boundary 키는 온전한 trace 기준이다(`new_effect_keys`). 고유 키는 arm 안의 합집합이다. 관찰 실패는 종류별 step 수로 세고 합산하지 않으며, 한 step이 여러 종류면 각 종류에 1회씩 센다. feedback-ineligible 비율과 rejected_ratio도 낸다. 구현은 `scripts/analyze_exp0.py`의 `_dense_registered`·`_dense_signals`와 `src/inodefence/evaluation/rds_report.py`의 `registered_dense_detail`이고, file:line은 동결 engine_sha에서 W3가 다시 확인한다. [파일럿 결과 메모](../summaries/exp3-hazard-pilot-v1-result.md) §7의 5개 지표는 R 변형 선택 근거(D6)이며 등록 지표가 아니다.
- **시계(D040-D20 "단일 시계 배율 금지"):** 처리량과 시간은 realtime 타임스탬프로 계산한다. monotonic 배율 하나로 환산하지 않는다. 호스트별 mono/real 배율은 기록만 한다.
- **호스트:** 호스트별 민감도 표(§3)를 낸다. 확증이 아니므로 호스트 간 검정은 하지 않는다.

## 7. 노출 공개와 한계

- **호스트·Engine 교란(지웅 조건부 승인 2026-11-11, Engine B안, 동결 전 초안, 지웅 승인 = PR 머지).** HOST1은 Docker Engine 29.8.0, HOST2는 29.9.3을 그대로 쓴다. 다운그레이드와 native 전환은 하지 않고, jobs는 두 호스트 모두 2다(D047). Engine과 하드웨어는 호스트에 종속된 교란요인이며, **호스트 간 성능·효과 차이를 Engine 버전만의 영향으로 해석하지 않는다.** 연구 타당성 조건 5개를 따른다.
  - ① 같은 호스트·같은 seed 블록 안에서 세 arm의 배치 균형을 유지한다(seed 블록 단위 할당, §3).
  - ② 분석에서 호스트별 효과를 구분해 확인한다(호스트별 민감도 표).
  - ③ 호스트별 결과가 크게 다르면 이질성을 보고하고 원인을 조사한다. 그 조사로 등록 분석을 바꾸지 않는다.
  - ④ 이 교란요인을 이 사전등록에 명시한다(이 문단).
  - ⑤ 사전등록한 분석·중단 기준은 결과를 확인한 뒤 바꾸지 않는다.
  - Engine B안 기술 조건(적격성 검증 v1 §11 최종본, 지웅 승인 2026-11-11)을 충족하지 못하면 "Docker 실행 환경의 중대한 불일치"가 해소되지 않은 것으로 보고 본실험을 시작하지 않는다. 연구 타당성 조건 5개는 위와 같다.

- **7.5.2 사전 노출:** 원장 7.5.2 행 전체(M2 train, M3.3, G1 smoke, EXP-0, 파일럿, 벤치마크, engineering smoke). train 타깃이라 노출이 자격을 해치지 않지만 사실대로 적는다(D15).
- **seed 9001 노출 정정(D15):** EXP-0 등록 seed 9001은 동결 전 4묶음 10런으로 노출됐다(원장 7.5.2 G1 행). EXP-3 seed와는 겹치지 않는다.
- **Rust tar(D17):** 등록 전에 고정 fixture probe(#261)가 실행돼 결과(두 버전 모두 C1·C2 0)를 이미 알았다. 그래서 사전 노출로 기록하고, holdout에서 제외하며, 등록하지 않는다. probe는 공개한다.
- **sentinel seed 재사용(ORCH 결정 #3):** `sentinel_generator_seed = 20261104`는 EXP-0·파일럿·벤치마크와 같다. 이유는 적격성 검증(인프라 자격)이 본실험과 같은 조건(대상·sentinel·budget·arm·watchdog·jobs)에서 이뤄지게 하기 위해서다. sentinel 이름은 세 arm의 어휘에 똑같이 들어가므로 재사용이 arm 사이 비대칭을 만들지 않는다. 같은 이름 집합이라는 점은 파일럿·벤치마크·적격성 실행과의 독립성을 줄이며, 이 사실을 공개한다.
- **비등록 실행 seed:** 적격성 검증 seed(8110/8102/8103/8106, 파일럿 재실행), 엔지니어링 smoke 6300–6303, 벤치마크 smoke 6100은 이 실험에 쓰지 않는다. v3 probe 6200–6207은 실행하지 않았고(D047) 예약만 유지한다. 적격성 abort 비율은 이 실험의 abort 추정에 쓰지 않는다(D041).
- **FACT③ 강등(D040-D20):** "엔진 소스에 7.5.6 참조 없음"은 grep 관찰일 뿐 훈련 노출 부재의 증거가 아니다.
- **한계:** n=20은 확증 규모가 아니다. train에서 holdout으로의 전이와 k=5 밖의 hazard는 미검증이다(D040 "D038 개정 범위").

## 8. 동결 체크리스트 (11/18)

- [ ] `engine_sha`(exp2-v1과 같음). D042·D043 결정 커밋과 host 키 게이트 구현(W3)이 그 SHA에 포함되고 검증 PASS.
- [ ] `image_digest`(D18 id, docker save 보관, 두 호스트 같은 id).
- [ ] [D042 정지·재개 smoke](../configs/stop-path-smoke-v1.md) 1차·2차 PASS와 차수별 원장 행. 순서는 런처 smoke → 정지·재개 smoke 1차 → 적격성 → 2차(최종 `engine_sha` 후보, 동결 직전) → 원장 sha 고정 → 동결이다. 1차 뒤 실행 경로가 바뀌면 2차는 필수이고 적격성도 무효다. 기준 파일의 sha256을 D042의 "sha `[동결 시 기입]`" 자리에 적는다.
- [ ] `exposure_ledger_sha256`. smoke·정지·재개 smoke(1차·2차)·적격성·D4 상태 확인 행을 먼저 반영하고(D042: 원장 sha는 2차 뒤 고정), 그 뒤 11/25까지 원장 변경 금지.
- [ ] `host.<id>.jobs = 2`(D047), `host.<id>.docker_engine`(적격성 preflight 고정값), `jobs_max = 2`. 참여 호스트 집합(적격성 PASS 기록 경로)과 그에 맞춘 할당 파일.
- [ ] 할당 파일과 `seed_assignment_sha256`.
- [ ] 임시값 사본으로 `run_exp0 --dry-run`(gate, wiring, 셀 순서) 확인(W3).
- [ ] 동결 시점의 호스트 간 realtime 시계 차 기록.
- [ ] 동결일 정의·측정 사슬 검증·E 코드 불변 확인은 [exp2-v1](exp2-v1.md) §7과 같다(2026-11-12 결과 전 개정, exp2-v1 §8).
- [ ] GO는 T-EXP3-2(arm 합산 E)만으로 낸다. train의 arm별 결과(T-EXP3-1·T-EXP3-3)는 holdout 결과 가림 해제 때까지 열지 않는다(exp2-v1 §5).

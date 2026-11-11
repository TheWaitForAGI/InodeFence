# EXP-2 사전등록 v1 — holdout 확증 (train GO 조건부)

> **상태: 동결 전 초안 (2026-11-11).** 아직 실행할 수 없다. `TBD-FREEZE` 값이 남아 있는 동안 파서가 거부한다(의도된 동작). 11/18에 [exp3-v1](exp3-v1.md)과 **함께** 동결한다(D040-D1). 실행은 exp3-v1 §5의 GO가 성립한 뒤에만 한다.
>
> **기준.** [D040](../../docs/DECISIONS.md#d040--exp-3-동결-전-재판정-위험도-파일럿-4040-반영), [D041](../../docs/DECISIONS.md#d041--동시-실행-벤치마크-단계-a-승인과-파일럿-seed-재사용), D042·D043(미머지 초안), [노출 원장](exposure-ledger.md), 동시 실행 벤치마크 v3(`experiments/configs/concurrency-scaling-v3.md`, #331 미머지). 이 초안과 D040이 다르면 D040이 맞다. **"ORCH 결정 2026-11-11"** 표시는 오케스트레이터가 데이터 이전에 정한 실행 세부이고, 지웅 승인은 이 PR의 머지로 한다.

## 1. 목적

H-A의 **유일한 확증 검정**이다. 피해 경로 이름을 아는 동일 어휘·동일 예산 아래, S-u(identity/effect/boundary-attempt retention)가 R(seed-restart)과 D(구조 커버리지)보다 holdout node-tar 버전에서 첫 경계위반까지 더 빠른가를 묻는다. 예측은 **HR ≥ 2**다(D040 서두). U_viol은 방향 일치 요구로만 쓴다(D13).

## 2. 기계판독 등록 블록

```preregistration
# EXP-2 holdout v1. TBD-FREEZE를 모두 채워 커밋해야 실행 유효.
experiment_id = exp2
# D040-D1 2항: exp3-v1과 같은 engine_sha.
engine_sha = TBD-FREEZE
# D040-D1 1항·D7: holdout {9026..9145}, 120은 상한(마감에서 잘림).
seeds = 9026, 9027, 9028, 9029, 9030, 9031, 9032, 9033, 9034, 9035, 9036, 9037, 9038, 9039, 9040, 9041, 9042, 9043, 9044, 9045, 9046, 9047, 9048, 9049, 9050, 9051, 9052, 9053, 9054, 9055, 9056, 9057, 9058, 9059, 9060, 9061, 9062, 9063, 9064, 9065, 9066, 9067, 9068, 9069, 9070, 9071, 9072, 9073, 9074, 9075, 9076, 9077, 9078, 9079, 9080, 9081, 9082, 9083, 9084, 9085, 9086, 9087, 9088, 9089, 9090, 9091, 9092, 9093, 9094, 9095, 9096, 9097, 9098, 9099, 9100, 9101, 9102, 9103, 9104, 9105, 9106, 9107, 9108, 9109, 9110, 9111, 9112, 9113, 9114, 9115, 9116, 9117, 9118, 9119, 9120, 9121, 9122, 9123, 9124, 9125, 9126, 9127, 9128, 9129, 9130, 9131, 9132, 9133, 9134, 9135, 9136, 9137, 9138, 9139, 9140, 9141, 9142, 9143, 9144, 9145
budget = 2000
vocabulary = observed-names
arm.R = unretained-seed-restart-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
# D4 규칙으로 고른 버전(§3). 게이트는 이 버전의 원장 행이 전부 qualification-only일 때만 허용(D5).
targets.node-tar-holdout.extractor = node-tar
targets.node-tar-holdout.version = TBD-FREEZE
targets.node-tar-holdout.image_digest = TBD-FREEZE
targets.node-tar-holdout.role = holdout
targets.node-tar-holdout.hypothesis = H-A
targets.node-tar-holdout.exposure = qualification-only
targets.node-tar-holdout.exposure_ref = experiments/preregistration/exposure-ledger.md
exposure_ledger = experiments/preregistration/exposure-ledger.md
exposure_ledger_sha256 = TBD-FREEZE
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = 20261104
sentinel_count = 5
observer_integrity_policy = invalid-continue
hit_definition = c1-or-c2-and-contract-violated
c0_counts_as_hit = false
denominator = all-cells-including-abort
abort_reporting = right-censored
rule_of_three_unit = campaign
# D13: T_first 단독 확증. D10: 이름 유지, 사양은 §5.
primary_endpoint = t_first
confirmatory_test = exact-logrank-permutation-v1
confirmatory_family = holdout:S-u-vs-R,S-u-vs-D
multiplicity = holm-fwer-v1
# D14: 7, 정보 블록(I) 기준.
event_threshold = 7
execution_mode = per-case-container
jobs_max = TBD-FREEZE
campaign_watchdog_seconds = 10800
disk_pause_fraction = 0.9
interim_analysis = forbidden
execution_deadline = 2026-11-25T12:00:00+09:00
# 2호스트(ORCH 결정 #1). 게이트 강제: W3 구현, 검증 후 동결.
host.HOST1.jobs = TBD-FREEZE
host.HOST1.docker_engine = TBD-FREEZE
host.HOST2.jobs = TBD-FREEZE
host.HOST2.docker_engine = TBD-FREEZE
# §4 규칙. 할당 파일은 GO 시점에 생기므로 sha 키를 두지 않는다(ORCH 결정 2026-11-11).
seed_assignment_rule = rh-proportional-v1
```

**블록 밖 규칙.**

- 공통값(`engine_sha`, k, sentinel generator, budget, arm, `campaign_watchdog_seconds`, `host.<id>.*`)은 exp3-v1과 같아야 한다. 어긋나면 train이 인프라 게이트 역할을 못 한다(D040-D1 2항).
- `host.<id>.*`는 게이트가 강제한다(W3 구현, 검증 후 동결). 등록값과 다른 호스트 `--jobs`나 Engine 버전으로는 실행하지 않는다.
- **할당 강제(ORCH 결정 2026-11-11, (a)+(b)).** holdout 할당 파일은 GO 시점에 생기므로 등록 파일에 sha를 두지 않는다. 대신 다음 두 가지를 한다.
  - (a) 게이트는 제출된 할당 파일이 등록 규칙 `rh-proportional-v1`(§4)과 GO 결정 파일(`experiments/summaries/exp3-train-go-decision.json`)의 r_h로 재생성한 결과와 **바이트 동일**할 때만 실행을 허용한다.
  - (b) 생성된 할당 파일의 sha256을 GO 결정 파일과 `docs/LOG.md`에 기록한다.
  - 할당 입력은 인프라 값뿐이다. 동결본에는 GO 시점 값을 기다리는 토큰을 남기지 않는다.
- 원장은 11/18~25에 고치지 않는다. train(exp3) 행은 holdout 완료 뒤에 넣는다(D040-D1 3항).

## 3. holdout 선정 (D4·D5)

**규칙(D040-D4, 결과 전 고정).** 후보는 minor별 최신 patch 5개 **{7.0.1, 7.1.0, 7.2.0, 7.3.0, 7.4.4}**다. 각 후보에 고정 fixture 상태 확인을 1회씩 하고, **위반이 있고 어댑터와 호환되는 후보 중 가장 높은 버전**을 holdout으로 정한다. 모두 부적격이면 **D1(D)로 자동 전환**한다. holdout은 포기하고 탐색 등록만 하며, 이 파일은 실행하지 않는다.

**D5 조건 4개.**

1. **순서:** D4 규칙이 main에 커밋된 뒤(D040, `05b26a9`) 상태 확인을 실행한다. 커밋 시각이 실행보다 앞서야 한다.
2. **전부 공개:** 후보 5개 전부의 원장 행과 결과를 적는다. 뽑히지 않은 버전도 빼지 않는다.
3. **행 내용:** `exposure_kind = qualification-only`(정확히 이 문자열; 게이트가 이 범주만 holdout에 허용), 규칙 근거 D040-D4, seed 해당 없음, 고정 fixture, 후보당 1회, 증거 경로. ERROR 재실행은 행을 따로 남긴다. 행 추가 PR은 W3가 검증한다.
4. **공개 문구(그대로):**

> holdout은 미리 고정한 규칙으로, 후보 5개의 고정 fixture 상태 확인 결과를 보고 골랐다. 규칙 입력은 버전 번호와 fixture 결과뿐이고 advisory는 쓰지 않았다. 다만 공개 advisory로 결과를 일부 예측할 수 있으므로 결과에 blind한 선택은 아니다. 후보 버전에서 탐색 실행은 하지 않았다.

**절차 세부(실행 방법, "어댑터 호환"의 판정, 이미지 빌드·allowlist 확장, 원장 행 형식)는 W3 조사 결과로 이 절에 반영한다(ORCH 2026-11-11).** 지금 저장소에서 확인된 사실은 다음뿐이다.

- 상태 확인 명령은 `make regression TAR_VERSION=<v>`다(`Makefile:95-102`, 고정 경계 fixture, 퍼징 없음).
- 후보 5개의 버전 디렉터리(`tools/node-tar/versions/`)와 이미지는 아직 없다. 지금은 7.5.2, 7.5.3, 7.5.6, 7.5.7, 7.5.8만 있다.
- 컨트롤러 버전 allowlist 확장이 필요할 수 있다(W3 확인 예정).
- "어댑터 호환"을 판정할 때 후보 버전에서 탐색(퍼징) 실행을 하면 안 된다. 하면 D5-4 공개 문구가 거짓이 된다.

이미지는 빌드 1회 뒤 id를 고정하고 docker save로 보관한다(D18). 두 호스트에서 같은 id여야 한다.

## 4. 호스트 할당 (ORCH 결정 #6)

- 한 seed의 세 arm은 같은 호스트에서 돈다.
- **N = 등록 seed 120개 전부**다. GO 시점의 r_h(exp3-v1 §5의 호스트별 r)에 비례해 나눈다. N=min(120, 용량) 같은 규칙은 쓰지 않는다.
  - N_HOST1 = round_half_down(N·r_HOST1 / (r_HOST1 + r_HOST2)), N_HOST2 = N − N_HOST1. 정수·`Fraction` 산술로 계산한다(부동소수 금지).
  - 등록 seed 순서(9026→9145)에서 앞 N_HOST1개는 HOST1, 뒤 N_HOST2개는 HOST2다.
  - 어느 r_h가 0이거나 미산출이면 할당 파일을 만들지 않고 EXP-2를 시작하지 않는다.
  - 할당 파일에 r_h, N, 분할, 생성 시각, 생성 코드 SHA를 기록하고 sha256을 GO 결정 파일과 LOG에 남긴다(§2 할당 강제 (b)). 입력은 인프라 값뿐이고 oracle 값은 쓰지 않는다.
- **마감 절단은 호스트별이다.** 각 호스트는 자기 할당 seed를 오름차순으로 돈다. 마감(2026-11-25 12:00 KST)에 끝나지 않은 셀이 있는 seed는 블록 전체를 미완주로 제외한다(D041). 남는 것은 각 호스트의 뒤쪽 블록뿐이다. 시점이 결과와 무관하게 사전 고정이므로 선택 편향은 없다(D040 운영 조건).
- 재시도, 인프라 정지, 재개, 운영 중단은 exp3-v1 §4와 같다. Guard와 마감은 호스트별 런처 단위로 독립이다. 운영 점검은 두 호스트 합산으로 판정하고 호스트별 비율은 경보로 따로 낸다.
- 호스트는 기록 요인이다. 벤치마크 v3의 X1에 따른 호스트 제외·전환 결정은 **train 첫 셀 시작 전**에 끝났어야 하며(exp3-v1 §3), EXP-2에서 새로 하지 않는다.
- 호스트 간 realtime 시계 차는 GO 시점에 기록한다.

## 5. 확증 분석

- **종단점:** T_first(exp3-v1 §6 정의). U_viol은 확증 종단점이 아니다.
- **통계량:** 합동 2-arm 로그랭크 χ². 기준 분포는 seed 블록 안 arm 라벨 순열이다. 두 호스트의 블록을 하나의 순열 집합으로 쓴다. 블록 구조(한 seed = 한 호스트)가 순열 단위이므로 호스트가 블록 안 교환 가능성을 깨지 않는다.
- **D10 사양:** 정보 블록 I(두 arm 관측이 다른 블록)이 16 이하이면 2^I 전수 열거로 p = ge/2^I를 구한다. 16을 넘으면 MC 100000회, seed 0 고정으로 p = (ge+1)/(N+1)을 구한다. 값의 출처는 `src/inodefence/evaluation/survival.py:777-779`(`seed = 0`, `max_exact_informative = 16`, `resamples = 100_000`)이고, 호출부는 `scripts/analyze_exp0.py:949`(`seed=0`)다(@`bce75a2`, 통합 브랜치 #330). **분석기 상수가 이 본문 값과 다르면 분석은 무효다.** 동결 `engine_sha`에서 같은 줄을 다시 확인한다.
- **α와 다중성:** 패밀리 α = .05 양측, Holm. 순서는 S-u vs R → S-u vs D다.
- **방향:** 기각은 양측 p로 하고, `faster_arm`(관측−기대 부호)으로 방향을 읽는다.
- **판정표(D12, 그대로).** I는 두 arm 관측이 다른 정보 블록 수, E는 대비의 총 사건 수다. "기각, X"는 Holm 기각이고 빠른 arm이 X라는 뜻이다. 두 대비의 I·E가 다르면 작은 쪽을 쓴다.

| S-u vs R | S-u vs D | 규모 | 판정 |
| --- | --- | --- | --- |
| 기각, S-u | 기각, S-u | — | ① 가속 주장 |
| 기각, S-u | 비기각 | — | ② 피드백 일반 효과만 |
| 비기각 | 기각, S-u | — | 예측 불충족, 탐색 보고 |
| 기각, R | 무관 | — | ⑧ 반증 |
| 기각 S-u 또는 비기각 | 기각, D | — | S<D: identity 특정 효과 반대 방향(⑧은 아님) |
| 비기각 | 비기각 | E ≥ 79 | 분리 실패 = HR 2 예측 반증 |
| 비기각 | 비기각 | I ≥ 7, E < 79 | 분리 실패, 반증 아님. 배제 범위 병기: E≥15→HR≥5, E≥20→HR≥4, E≥32→HR≥3 |
| 비기각 | 비기각 | I < 7 | 미검정(기각 불가능 규모) |
| 사건 0 | 사건 0 | 0 | ⑤ 미관찰, 캠페인 단위 상한만 서술 |

  E 기준은 Schoenfeld 80%, 양측 α .025 계획값이다(HR 5/4/3/2 = 14.7/19.8/31.5/79.1). 추가 두 줄(D12): 세 abort 정책(`censor-at-abort`, `censor-at-budget`, `exclude`)의 `reject_at_alpha`가 갈리면 "abort 가정에 좌우됨"으로 적는다. 예측은 HR로 평가한다.
- **①의 추가 조건(D13):** ① 가속 주장은 U_viol 방향 일치(S-u가 두 대비 모두에서 U_viol도 많음)를 함께 요구한다. α는 쪼개지 않는다. 방향 일치는 retention으로 쉽게 충족되므로 근거로 과대평가하지 않는다.
- **threshold(D14):** `event_threshold = 7`은 정보 블록 I 기준의 기각 가능성 플래그다. 최소 p는 2^(1−I)이고, 7블록에서 .0156, 6블록에서 .0313이다. 검정을 바꾸지 않는다.
- **invalid·abort·마감:** exp3-v1 §6과 같다. `record-inconsistent`는 대비에서 블록을 빼고, 마감 미완주 seed는 블록 전체를 제외하며, 제외 수와 원인을 보고한다.
- **호스트 민감도(보고만):** 호스트별 KM과 대비별 p를 표로 낸다. 판정은 합동 순열 결과로만 한다.
- **T-EXP2-5(holdout 인프라 측정 표):** monotonic 기반 값이므로 호스트별로 분리해 낸다. 처리량과 시간은 realtime으로 따로 낸다.
- **연장 금지:** 마감과 n은 결과를 보고 바꾸지 않는다. NO-GO나 미산출이면 이 파일은 실행하지 않는다.

## 6. 노출 공개와 한계

- holdout 버전의 노출은 D5 상태 확인(qualification-only)뿐이어야 한다. 그 밖의 행이 있으면 게이트가 거부한다.
- 7.5.6/7.5.7은 기노출 수정 검증 쌍이고 캠페인을 돌리지 않는다(D3, 지웅 결정 5). Rust tar는 사전 노출, holdout 제외, 미등록이다(D17). py-tarfile 캠페인은 없다(D3).
- sentinel seed 20261104 재사용은 exp3-v1 §7과 같은 이유로 공개한다. 세 arm에 같은 어휘로 들어가므로 arm 간 비대칭은 없다.
- **검정력:** n=120/arm(상한)은 holdout hazard가 train의 절반(s=.5)이거나 HR이 1.75여도 약 .76~.79다(`run-grid.log`, χ² 근사; D7). HR 1.5나 s=.25에서는 어떤 n도 창 안에서 80%가 안 되며, 그 경우는 D12 표가 처리한다. 마감 절단으로 n이 줄면 그만큼 낮아진다.
- train에서 holdout으로의 전이와 k=5 밖의 hazard는 미검증이다.
- 확증은 node-tar 한 계보의 미노출 버전에 대한 것이다. 새 계보 extractor 일반성 주장이 아니다.

## 7. 동결 체크리스트 (11/18)

- [ ] D4 상태 확인 완료, 원장 행 5개 이상(ERROR 재실행 행 포함) 머지, holdout version과 image_digest 확정(W3 절차, §3).
- [ ] `engine_sha`와 공통값이 exp3-v1과 같음.
- [ ] `exposure_ledger_sha256`이 exp3-v1과 같음.
- [ ] 할당 강제 (a) 재생성 일치 검사 게이트 구현·검증(W3, §2).
- [ ] 분석기 상수(§5 D10) 재확인.
- [ ] 임시값 사본으로 `run_exp0 --dry-run`과 holdout 버전 allowlist 확인(W3).

# EXP-2 사전등록 v1 — holdout 확증 (train GO 조건부)

> **상태: 동결 전 초안 (2026-11-11).** 아직 실행할 수 없다. `TBD-FREEZE` 값이 남아 있는 동안 파서가 거부한다(의도된 동작). 동결 시각에 [exp3-v1](exp3-v1.md)과 **함께** 동결한다(D040-D1). 실행은 exp3-v1 §5의 GO가 성립한 뒤에만 한다.
>
> **기준.** [D040](../../docs/DECISIONS.md#d040--exp-3-동결-전-재판정-위험도-파일럿-4040-반영), [D041](../../docs/DECISIONS.md#d041--동시-실행-벤치마크-단계-a-승인과-파일럿-seed-재사용), [D042](../../docs/DECISIONS.md#d042--인프라-정지-규칙-연속-3셀-기록-없음)·[D043](../../docs/DECISIONS.md#d043--go-입력-r에서-등록된-인프라-정지-공백을-뺀다), [D045](../../docs/DECISIONS.md#d045--holdout-상태-확인의-위반어댑터-호환-정의와-train-abort-분모), [D046](../../docs/DECISIONS.md#d046--인프라-정지-대응case-단위-재실행과-d040-d21-재개-판정)·[D047](../../docs/DECISIONS.md#d047--본실험-선행-조건-단순화-jobs2-고정과-호스트별-적격성-검증)(#342로 main 반영), [노출 원장](exposure-ledger.md), [호스트별 적격성 검증 v1](../configs/host-qualification-v1.md). 동시 실행 벤치마크 v3(`experiments/configs/concurrency-scaling-v3.md`)는 본실험 선행 조건이 아니다(D047). 이 초안과 D040이 다르면 D040이 맞다. **"ORCH 결정 2026-11-11"** 표시는 오케스트레이터가 데이터 이전에 정한 실행 세부이고, 지웅 승인은 이 PR의 머지로 한다. **2026-11-12 결과 전 개정(동결 묶음 A~E, §8 변경 이력)도 이 머지로 승인된다.**

## 1. 목적

H-A의 **유일한 확증 검정**이다. 피해 경로 이름을 아는 동일 어휘·동일 예산 아래, S-u(identity/effect/boundary-attempt retention)가 R(seed-restart)과 D(구조 커버리지)보다 holdout node-tar 버전에서 첫 경계위반까지 더 빠른가를 묻는다. 확증 검정(§5, Holm 두 대비)은 1차 검정 그대로다. **예측(2026-11-12 개정, §8):** 문법 몬테카를로로 사전 계산한 retention 효과의 해석적 낙관 상한은 **U_sim ≈ HR 1.1~1.3**이다(링크 생성 경로 기준, §6 측정 사슬 검증 ③). 따라서 기대되는 결말은 비기각과 **HR 2 배제(구간 상한 < 2)**다. 그 확률은 N = 120에서 두 대비 기준으로 참 HR 1.0이면 .77, 1.3이면 .35이고, holdout hazard가 절반이면 .46/.17이다. N = 160에서는 .92/.46이다(Peto, seed 블록 부트스트랩, sims 400). 그래서 '비기각, 상한 ≥ 2(판단 유보)'도 예측한 불확실성 안의 결말이다. 파일럿 점추정(노출당 사건률 비 S-u/R ≈ 2.1, 사건 6 대 4, 구간 넓음)은 U_sim 밖이고, 본실험이 둘을 가른다. 처음 예측(D040 서두 HR ≥ 2)은 이 개정으로 바꾼다. U_viol은 보고만 한다(§5).

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
# D4·D045 상태 확인 결과(2026-11-11 HOST1): 후보 5개 모두 위반 ∧ 호환 → 최고 버전 7.4.4.
targets.node-tar-holdout.version = 7.4.4
# D18: 빌드 1회 id 고정(HOST1 docker image inspect, linux/amd64, 208585417 B; lock sha256 38b636640f941953189084d01a37db2f919049d6e0c7388cf86af1bc07e19c84;
# docker save 아카이브 sha256 2adaefb2b13365ae653341ac3ded1f412aa19875f57e3ccdb7118dd6ca8763cc로 보관·전송, 재빌드 금지). HOST2에서도 같은 id여야 한다.
targets.node-tar-holdout.image_digest = sha256:f5d3e9a999cfad0a5f37002bf36802378b20777646be3684eb97baeaa4080421
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
# D047: 두 호스트 모두 jobs=2 고정(사람 결정, 벤치마크 선정값 아님).
jobs_max = 2
campaign_watchdog_seconds = 10800
disk_pause_fraction = 0.9
interim_analysis = forbidden
execution_deadline = 2026-11-25T12:00:00+09:00
# 호스트 키(D047). 현재 파서(fa8ccb4)는 두 호스트 키를 모두 요구한다. 참여 집합은 exp3-v1 §3에서 동결 때 고정하고 할당 파일(make_seed_assignment.py --participants)에 기록한다. 게이트 강제.
host.HOST1.jobs = 2
host.HOST1.docker_engine = TBD-FREEZE
host.HOST2.jobs = 2
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
- 원장은 동결 시각부터 마감(2026-11-25 12:00)까지 고치지 않는다. train(exp3) 행은 holdout 완료 뒤에 넣는다(D040-D1 3항).

## 3. holdout 선정 (D4·D5)

**규칙(D040-D4, 결과 전 고정).** 후보는 minor별 최신 patch 5개 **{7.0.1, 7.1.0, 7.2.0, 7.3.0, 7.4.4}**다. 각 후보에 고정 fixture 상태 확인을 1회씩 하고, **위반이 있고 어댑터와 호환되는 후보 중 가장 높은 버전**을 holdout으로 정한다. 모두 부적격이면 **D1(D)로 자동 전환**한다. holdout은 포기하고 탐색 등록만 하며, 이 파일은 실행하지 않는다.

**D5 조건 4개.**

1. **순서:** D4 규칙이 main에 커밋된 뒤(D040, `05b26a9`) 상태 확인을 실행한다. 커밋 시각이 실행보다 앞서야 한다.
2. **전부 공개:** 후보 5개 전부의 원장 행과 결과를 적는다. 뽑히지 않은 버전도 빼지 않는다.
3. **행 내용:** `exposure_kind = qualification-only`(정확히 이 문자열; 게이트가 이 범주만 holdout에 허용), 규칙 근거 D040-D4, seed 해당 없음, 고정 fixture, 후보당 1회, 증거 경로. ERROR 재실행은 행을 따로 남긴다. 행 추가 PR은 W3가 검증한다.
4. **공개 문구(그대로):**

> holdout은 미리 고정한 규칙으로, 후보 5개의 고정 fixture 상태 확인 결과를 보고 골랐다. 규칙 입력은 버전 번호와 fixture 결과뿐이고 advisory는 쓰지 않았다. 다만 공개 advisory로 결과를 일부 예측할 수 있으므로 결과에 blind한 선택은 아니다. 후보 버전에서 탐색 실행은 하지 않았다.

**판정 정의와 순서는 [D045](../../docs/DECISIONS.md#d045--holdout-상태-확인의-위반어댑터-호환-정의와-train-abort-분모)(main 머지, 지웅 승인 = #331)를 따른다.**

- **fixture:** `make regression TAR_VERSION=<v>`(`Makefile:95-102`)의 고정 fixture 5개다. 손 하드링크 2개와 symlink-write 3개이며 퍼징은 하지 않는다.
- **어댑터 호환:** 5개 모두 ERROR 없이 PASS 또는 FAIL 판정이 나와야 한다. ERROR가 나면 1회 재실행하고 그 결과를 별도 행으로 남긴다. 재실행도 ERROR이면 부적격이다. 후보 버전에서 탐색 실행은 하지 않는다.
- **위반(같은 위반 계열):** 후보에서 FAIL인 fixture 중 하나 이상이 기준 집합 F_train(7.5.2에서 FAIL인 fixture)에 속해야 한다. F_train은 후보보다 먼저 같은 명령으로 7.5.2를 1회 돌려 정한다. 하드링크 결과가 M2 기록과 다르거나 F_train이 비어 있으면 하네스 불일치로 보고하고 중단한다. 이때 후보는 실행하지 않는다.
- **선정과 대가:** 위반이면서 호환인 후보 중 최고 버전을 고른다. 하나도 없으면 D1(D)로 자동 전환한다. **이 정의는 (i) "아무 FAIL이나"보다 후보를 좁히므로 D1(D)로 자동 전환될 확률이 더 높다.** 이 점을 공개한다.
- **순서:** D045 머지 → lock·이미지 준비 → 7.5.2 기준 실행 → 후보 5개(버전 오름차순, 후보당 1회) → 원장 행 PR. 실행은 W3, 승인은 오케스트레이터, 행 PR 검증은 W4가 맡는다. lock 생성은 선정 규칙의 입력이 아니다.
- **allowlist:** D040-D2 "불변 표 1줄"(사람 승인 완료)을 근거로 한다.

**상태 확인 결과(관찰, 2026-11-11 15:06~15:08 KST, HOST1, Engine 29.8.0, 기존 `make regression` 수정 없음, 증거 `~/inodefence-evidence/d4-holdout-20261111/`, manifest sha `f0a57729…`, 오케스트레이터 확인).**

- 7.5.2 기준: 하드링크 2개는 C1 공유 true로 M2 기록과 같았고, symlink-write 3개는 PASS였다. 따라서 F_train = {`toplevel_hardlink`, `nested_hardlink`}이다.
- 후보 5개(7.0.1, 7.1.0, 7.2.0, 7.3.0, 7.4.4): 모두 하드링크 2개 FAIL, symlink-write 3개 PASS였다. ERROR 0, 재실행 0, 잔존 컨테이너 0이다. 다섯 후보 모두 위반이면서 호환이므로 규칙에 따라 최고 버전 **7.4.4**를 선정한다(빌드 이미지 id `f5d3e9a999cf…`, lock sha `38b636640f94…`).
- 원장 행 6개(후보 5개와 7.5.2 기준)는 W3의 PR로 추가하고 W4가 검증한다.

**선정의 성격(공개).**

- D5-4 공개 문구는 위에 적은 그대로다.
- 다섯 후보는 다섯 fixture에서 결과가 모두 같았다. 그래서 선정은 fixture 결과로 갈리지 않았고, "최고 버전" 규칙만으로 7.4.4가 정해졌다.
- 7.4.4는 train 타깃 7.5.2보다 앞선 버전이고, D045 (ii)가 의도한 대로 같은 위반 계열(하드링크 identity 공유)을 가진다. 따라서 이 holdout이 검정하는 것은 "피드백 탐색이 다른 버전·다른 seed에서도 같은 계열의 경계위반을 더 빨리 찾는가"다. **새로운 결함 계열의 발견이나 결함 계열을 넘어선 일반성은 이 실험의 주장 범위가 아니다.**
- 의존성 차이(관찰): 후보 5개의 lock은 모두 minipass 7.1.3이고, 7.5.2는 7.1.2다. 7.0.1~7.3.0에는 mkdirp 3.0.1이 추가로 있다. lock 생성 절차도 다르다. 후보는 일회용 컨테이너 안의 npm 10.9.4로 만들었고, 기존 7.5.x lock은 호스트 npm으로 만들었다. 이 차이가 탐색 hazard에 주는 영향은 미검증이다.
- 상태 확인 경로의 격리 한계(관찰): 회귀 명령의 repro 경로는 컨테이너 안에서 root로, 기본 bridge 네트워크에서, cap과 자원 제한 없이 돈다. 이번이 #218 이후 그 경로의 첫 docker 실행이다. 고정 fixture만 쓰고 호스트는 추출 대상이 아니다. 캠페인 실행 경로의 격리 계약(per-case 컨테이너 정책)과는 별개이며, 그 계약은 바뀌지 않았다.

이미지는 빌드 1회 뒤 id를 고정하고 docker save로 보관한다(D18). 두 호스트에서 같은 id여야 한다.

## 4. 호스트 할당 (ORCH 결정 #6)

- 한 seed의 세 arm은 같은 호스트에서 돈다.
- **참여 호스트(D047):** 참여 호스트는 exp3-v1 §3에서 동결 때 고정한 집합이다. r_h는 각 참여 호스트의 train 값(exp3-v1 §5)이다. 참여 호스트가 하나면 등록 seed 120개 전부를 그 호스트에 둔다. exp3-v1 §5의 미재개 정지 규칙(D047, 지웅 결정 1)이 적용되면 여기서 "참여 호스트"는 "GO 판정 시각에 재개·가동 중인 참여 호스트"를 뜻한다.
- **N = 등록 seed 전부**다. N은 동결 때 하나로 정해 seeds 목록에 적는다: 동결이 2026-11-14이고 **동결 시점의 참여 집합(exp3-v1 §3)이 두 호스트**이면 160(9026–9185), 그 밖은 120(9026–9145). 동결 뒤에 참여 호스트가 바뀌어도(§9.1 제외 포함) N은 다시 정하지 않는다. 근거는 일정 조건(적격성 실측 r의 절반에서도 마감 −72 h 전 완주)과 검정력 이득(+.11~.15)이다(동결 묶음 C). 용량에 연동하는 규칙이 아니다. GO 시점의 r_h(exp3-v1 §5의 호스트별 r)에 비례해 나눈다. N=min(120, 용량) 같은 규칙은 쓰지 않는다.
  - N_HOST1 = round_half_down(N·r_HOST1 / (r_HOST1 + r_HOST2)), N_HOST2 = N − N_HOST1. 정수·`Fraction` 산술로 계산한다(부동소수 금지).
  - 등록 seed 순서(9026→마지막 등록 seed)에서 앞 N_HOST1개는 HOST1, 뒤 N_HOST2개는 HOST2다.
  - **참여 호스트 중** 어느 r_h가 0이거나 미산출이면 할당 파일을 만들지 않고 EXP-2를 시작하지 않는다.
  - **holdout 도중 한 호스트가 멈추면(2026-11-12 공개, HOST2 전원 끄기 사례):** 할당은 바꾸지 않는다. 다른 호스트가 대신 돌리지 않는다. 멈춘 호스트는 원인 기록과 승인 뒤 같은 명령으로 재개하고, 정지 공백은 마감 안의 시간을 쓴다. 마감까지 끝내지 못한 그 호스트의 뒤쪽 seed는 블록 전체 제외다(위 마감 절단). 그래서 정지는 재개되면 '지연'이고, 재개되지 않으면 '그 호스트 몫의 미완 블록 손실'이다. N은 바뀌지 않고 분석 n이 줄 뿐이다.
  - 할당 파일에 r_h, N, 분할, 생성 시각, 생성 코드 SHA를 기록하고 sha256을 GO 결정 파일과 LOG에 남긴다(§2 할당 강제 (b)). 입력은 인프라 값뿐이고 oracle 값은 쓰지 않는다.
- **마감 절단은 호스트별이다.** 각 호스트는 자기 할당 seed를 오름차순으로 돈다. 마감(2026-11-25 12:00 KST)에 끝나지 않은 셀이 있는 seed는 블록 전체를 미완주로 제외한다(D041). 남는 것은 각 호스트의 뒤쪽 블록뿐이다. 시점이 결과와 무관하게 사전 고정이므로 선택 편향은 없다(D040 운영 조건).
- 재시도, 인프라 정지, 재개, 운영 중단은 exp3-v1 §4와 같다. Guard와 마감은 호스트별 런처 단위로 독립이다. 운영 점검은 두 호스트 합산으로 판정하고 호스트별 비율은 경보로 따로 낸다.
- 호스트는 기록 요인이다. 호스트 참여는 동결 때 고정한 참여 집합으로만 정한다(exp3-v1 §3: 적격성 통과 ∧ 투입 보류 아님). EXP-2에서 새로 정하지 않는다.
- 호스트 간 realtime 시계 차는 GO 시점에 기록한다.

## 5. 확증 분석

- **종단점:** T_first(exp3-v1 §6 정의). U_viol은 확증 종단점이 아니다.
- **통계량:** 합동 2-arm 로그랭크 χ². 기준 분포는 seed 블록 안 arm 라벨 순열이다. 두 호스트의 블록을 하나의 순열 집합으로 쓴다. 블록 구조(한 seed = 한 호스트)가 순열 단위이므로 호스트가 블록 안 교환 가능성을 깨지 않는다.
- **D10 사양:** 정보 블록 I(두 arm 관측이 다른 블록)이 16 이하이면 2^I 전수 열거로 p = ge/2^I를 구한다. 16을 넘으면 MC 100000회, seed 0 고정으로 p = (ge+1)/(N+1)을 구한다. 값의 출처는 `src/inodefence/evaluation/survival.py:777-779`(`seed = 0`, `max_exact_informative = 16`, `resamples = 100_000`)이고, 호출부는 `scripts/analyze_exp0.py:949`(`seed=0`)다(@`bce75a2`, 통합 브랜치 #330). **분석기 상수가 이 본문 값과 다르면 분석은 무효다.** 동결 `engine_sha`에서 같은 줄을 다시 확인한다.
- **α와 다중성:** 패밀리 α = .05 양측, Holm. 순서는 S-u vs R → S-u vs D다.
- **방향:** 기각은 양측 p로 하고, `faster_arm`(관측−기대 부호)으로 방향을 읽는다.
- **HR 추정량과 구간(2026-11-12 추가, §8):** 대비마다 Peto 추정 exp(U/V)를 낸다. U, V는 위 합동 2-arm 로그랭크와 같은 통계에서 나온다. 95% 구간은 seed 블록(한 seed의 세 arm) 재표집 B = 2000, 백분위 2.5/97.5로 구하고, 재표집 RNG seed는 동결 때 이 줄에 적는다. 민감도로 노출률 비 MLE를 함께 낸다. 가장자리: 한 arm의 사건이 0이면 상한을 내지 않고 '배제 불가'로 둔다. 정의되지 않는 재표집은 +∞로 센다. 두 대비를 함께 배제하려면 둘 다 상한 < 2여야 한다. 계산은 분석기 밖의 등록 스크립트로 하고, 그 sha256을 동결 때 §7에 적는다(분석기와 실행 코드는 바꾸지 않는다).
- **판정표(D12, 2026-11-12 비기각 행 개정).** I는 두 arm 관측이 다른 정보 블록 수, E는 대비의 총 사건 수다. "기각, X"는 Holm 기각이고 빠른 arm이 X라는 뜻이다. 두 대비의 I·E가 다르면 작은 쪽을 쓴다.

| S-u vs R | S-u vs D | 규모 | 판정 |
| --- | --- | --- | --- |
| 기각, S-u | 기각, S-u | — | ① 가속 주장 |
| 기각, S-u | 비기각 | — | ② 피드백 일반 효과만 |
| 비기각 | 기각, S-u | — | 예측 불충족, 탐색 보고 |
| 기각, R | 무관 | — | ⑧ 반증 |
| 기각 S-u 또는 비기각 | 기각, D | — | S<D: identity 특정 효과 반대 방향(⑧은 아님) |
| 비기각 | 비기각 | I ≥ 7, 상한 < 2 | 분리 실패, **HR 2 배제** |
| 비기각 | 비기각 | I ≥ 7, 상한 ≥ 2 | 분리 실패, **판단 유보**(반증 아님) |
| 비기각 | 비기각 | I < 7 | 미검정(기각 불가능 규모) |
| 사건 0 | 사건 0 | 0 | ⑤ 미관찰, 캠페인 단위 상한만 서술 |

  E의 Schoenfeld 계획값(80%, 양측 α .025: HR 5/4/3/2 = 14.7/19.8/31.5/79.1)은 검정력 설명으로만 남기고 판정에 쓰지 않는다. 추가 두 줄(D12): 세 abort 정책(`censor-at-abort`, `censor-at-budget`, `exclude`)의 `reject_at_alpha`가 갈리면 "abort 가정에 좌우됨"으로 적는다. **예측은 위 HR 추정량과 구간으로 평가한다.** 구간이 U_sim과 겹치면 '문법 수준 기대와 일치', 하한 > U_sim이면 '문법만으로 설명되지 않는 이득(첫 hit 출처 표로 기작 확인)', 상한 < 1이면 '역효과'로 읽는다.
- **U_viol(D13, 2026-11-12 개정):** U_viol 방향 일치는 ①의 조건에서 빼고 **보고만** 한다. S-u만 위반 입력을 보존하므로 방향 일치가 구조적으로 거의 자동이기 때문이다. 보조로 (계약, sentinel) 쌍으로 접은 unique violation을 함께 내고, 첫 hit를 C1+C2 / C2만 / 내용 변경으로 나눠 보고한다.
- **첫 hit 출처 표(필수 보조, 정의 고정, 계산은 해제 뒤):** arm별 첫 사건 step마다 operator_id, 부모 출처(seed / 보존 case), 계보 깊이(parent_case_id로 복원), 첫 계약(C1/C2), "seed 부모에서 같은 연산자로 같은 링크 대상을 만들 수 있었는가"(정적 판정)를 적는다. 스크립트 sha는 동결 때 §7에 적는다.
- **threshold(D14):** `event_threshold = 7`은 정보 블록 I 기준의 기각 가능성 플래그다. 최소 p는 2^(1−I)이고, 7블록에서 .0156, 6블록에서 .0313이다. 검정을 바꾸지 않는다.
- **invalid·abort·마감:** exp3-v1 §6과 같다. `record-inconsistent`는 대비에서 블록을 빼고, 마감 미완주 seed는 블록 전체를 제외하며, 제외 수와 원인을 보고한다.
- **호스트·Engine 교란(지웅 조건부 승인, Engine B안):** exp3-v1 §7의 조건 5개를 그대로 따른다. 호스트 간 차이를 Engine 버전만의 영향으로 해석하지 않는다.
- **호스트 민감도(보고만):** 호스트별 KM과 대비별 p를 표로 낸다. 판정은 합동 순열 결과로만 한다.
- **T-EXP2-5(holdout 인프라 측정 표):** monotonic 기반 값이므로 호스트별로 분리해 낸다. 처리량과 시간은 realtime으로 따로 낸다.
- **연장 금지:** 마감과 n은 결과를 보고 바꾸지 않는다. NO-GO나 미산출이면 이 파일은 실행하지 않는다.
- **결과 가림 해제(2026-11-12, holdout에 한해 D041 분석 수정 2번을 이 문장으로 대체):** 「holdout 결과 가림은 모든 참여 호스트의 할당 seed가 최종 상태이고 증거 무결성이 확인되면 마감 전에 푼다. 그 전에는 먼저 끝난 호스트의 결과 경로를 어떤 세션도 열지 않는다. 남은 운영 결정은 사전 고정 규칙이나 인프라 키를 근거로만 한다. 부분 GO·운영 중단·미재개 정지가 있으면 마감 시각에 푼다. 마감은 상한이다. 해제 시각, 파일 sha, 열람 감사 결과를 기록한다. 해제 시각은 분석 집합을 바꾸지 않는다.」 E의 런처는 호스트별로 모든 셀이 최종이고 무결성이 확인되면 마감 전에도 index를 가리지 않는다(`scripts/run_exp0.py:1874-1886`). 그래서 위 금지는 절차로 지키고, 해제 뒤 세션 도구 기록으로 감사한다. train의 arm별 결과도 holdout 해제 때까지 열지 않는다(GO는 합산 E만 쓴다).

## 6. 노출 공개와 한계

- holdout 버전의 노출은 D5 상태 확인(qualification-only)뿐이어야 한다. 그 밖의 행이 있으면 게이트가 거부한다.
- 7.5.6/7.5.7은 기노출 수정 검증 쌍이고 캠페인을 돌리지 않는다(D3, 지웅 결정 5). Rust tar는 사전 노출, holdout 제외, 미등록이다(D17). py-tarfile 캠페인은 없다(D3).
- sentinel seed 20261104 재사용은 exp3-v1 §7과 같은 이유로 공개한다. 세 arm에 같은 어휘로 들어가므로 arm 간 비대칭은 없다.
- **검정력:** n=120/arm(상한)은 holdout hazard가 train의 절반(s=.5)이거나 HR이 1.75여도 약 .76~.79다(`run-grid.log`, χ² 근사이고 등록 순열 검정의 값이 아니다; D7). HR 1.5나 s=.25에서는 어떤 n도 창 안에서 80%가 안 된다. 개정된 예측(§1)에서 기대 결말은 'HR 2 배제'이고, 그 확률은 §1에 적었다. 마감 절단으로 n이 줄면 그만큼 낮아진다.
- **범위 문구(2026-11-12, 외부 검토 F1·F2·M2·M5):**
  - S-u는 「파일시스템 identity·effect 상태 변화(realized effect)와, 추출 루트를 벗어나는 하드링크 대상의 모양(절대·상위 1/2/3+; 경로·꼬리·sentinel 없음)을 보존 키로 쓰는 탐색」이다. boundary 키는 특정 패턴·경로를 담지 않지만 결함 계열 수준의 사전 지식이다. 양성은 이 범위로 좁혀 읽는다.
  - 변이 정책에는 부모와 무관하게 탈출 하드링크를 만드는 연산자(슬롯 5)가 있다. 어휘는 generic 7개 + 관찰 이름(BEFORE 레이아웃에서 추론한 16개)이고 세 arm이 같다. 이 문법에서 위반은 어느 seed에서든 변이 1회 거리다.
  - holdout은 「같은 결함 계열(하드링크 identity 공유)의 다른 미노출 릴리스에서의 재현 반복」이다. 일반화 시험이라 부르지 않는다.
  - D는 「구조 커버리지 유도 퍼징의 대리. 출력 구조 키 기반이며 코드 커버리지 기준선이 아니다」.
- **측정 사슬 검증(가설 검정 아님, 동결 전):** (가) 실행 SHA E에서 run_exp0 경로로 7.5.2 S-u seed 8002를 한 번 돌린다(k = 5, budget 2000, jobs 1, `experiments/configs/positive-control-a-v1.md`). PASS = 사건 발생. (나1) 고정 픽스처로 7.5.2·7.5.3(음성 대조)·7.4.4에서 oracle 판정을 대조한다. ③ 문법 몬테카를로(저장소 밖, sha 고정)로 R-restart의 캠페인당 사건 확률을 예측한다. 예측은 .445이고 95% 구간 .38~.50(400,000 step, hit 118)이며, 파일럿 R-restart 4/10(.12~.74)과 구간으로 겹친다. 같은 도구의 입력으로 U_sim을 낸다(S-u 시뮬레이션이 아닌 해석적 낙관 상한).
- **결함 깊이 ≥ 2 후속은 이 등록과 KCSE 범위에 넣지 않는다.** 저장소 기록에 깊이 ≥ 2 위반이 통제 재현된 대상이 없다.
- train에서 holdout으로의 전이와 k=5 밖의 hazard는 미검증이다.
- 확증 범위는 node-tar 한 계보의 미노출 버전 7.4.4, 그리고 train과 같은 위반 계열(하드링크 identity 공유)이다(§3 "선정의 성격"). 새 계보 extractor로의 일반성이나 새로운 결함 계열의 발견은 주장하지 않는다.

## 7. 동결 체크리스트

동결일은 "선행 조건 완료 + 검증 24 h"(이 절 끝, 목표 2026-11-14~15)이다.

- [x] D4 상태 확인 완료(2026-11-11, 7.4.4 선정, §3).
- [ ] 원장 행 6개(후보 5개와 7.5.2 기준) PR 머지(W3 작성, W4 검증).
- [x] 7.4.4 image id 기입(`sha256:f5d3e9a9…0421`, HOST1). [ ] HOST2에서 docker load 뒤 같은 id 확인.
- [ ] `engine_sha`와 공통값이 exp3-v1과 같음.
- [ ] `exposure_ledger_sha256`이 exp3-v1과 같음.
- [ ] 할당 강제 (a) 재생성 일치 검사 게이트 구현·검증(W3, §2).
- [ ] 분석기 상수(§5 D10) 재확인.
- [ ] 임시값 사본으로 `run_exp0 --dry-run`과 holdout 버전 allowlist 확인(W3).
- [ ] 참여 호스트의 적격성 PASS 기록과 Engine B안 기술 조건(적격성 검증 v1 §11) 충족.
- [ ] D042 정지·재개 smoke 1차·2차 PASS(exp3-v1 §8과 같은 항목, 같은 `engine_sha`).
- [ ] 측정 사슬 검증 (가)·(나1) PASS(§6). 음성이 하나라도 있으면 원인 확정 전에 동결하지 않는다.
- [ ] N 확정(§4 규칙)과 seeds 목록 반영.
- [ ] 등록 스크립트 sha256 기입: HR 추정량·부트스트랩 `~/inodefence-evidence/registered-tools-20261112/exp2_hr_ci.py` `3565ea1f86c7d4a187323604e68b6495c678cfc3e22f1f8249c912c172511577`(같은 폴더 `SHA256SUMS`. selftest 출력 `exp2_hr_ci-selftest.txt`. 합성 holdout index 끝단 실행 `exp2_hr_ci-e2e-check.txt` `55692e02ca83487636be275ddb5a5affa9d9dec951a52242aee32f190c6da906`: 대비 2 × 정책 3, 블록 수가 분석기 확증 절과 `_policy_blocks`와 일치. 동결 전에 바뀌면 새 sha로 고친다), 재표집 RNG seed `<값>`, 첫 hit 출처 표 `<sha>`, 접은 U_viol `<sha>`, 문법 MC `~/inodefence-evidence/registered-tools-20261112/grammar_mc.py` `6aa8fd81e8d6dee68d2d0c58cfd97d0163c4bf4341be8f0b001c7a82c26eaad4`.
- [ ] 동결 커밋에서 `git diff --stat bed077a -- src scripts`가 빈 출력(E 코드 불변).
- [ ] **동결일 정의:** 위 선행 조건이 모두 끝난 시각 + 검증 24 h. 목표는 2026-11-14~15다.

## 8. 변경 이력

- **2026-11-12 결과 전 개정(동결 묶음 A~E, W3 작성·W4 서명, 이 PR 머지가 지웅 승인).**
  - 이유: 외부 검토(F1: 위반이 seed에서 변이 1회 거리. F3: HR ≥ 2에 추정량이 없고 비기각을 반증으로 읽음)와, E 변이기로 돌린 문법 몬테카를로.
  - 바뀐 것: 예측 문장(§1), HR 추정량·구간과 D12 비기각 행(§5), U_viol은 보고만(§5), 첫 hit 출처 표, holdout 결과 가림 해제(§5), N 결정 규칙(§4), 범위 문구·측정 사슬 검증(§6), 동결일 정의(§7).
  - 결과 전 변경인 근거: 지금까지 본 결과 값은 공개값(EXP-0, 파일럿 메모 §2·§8)과 측정 사슬 대조 결과(양성 대조 (가) 공개 셀, E′ 픽스처 7.5.2·7.5.3·7.4.4 판정)뿐이다. 측정 사슬 대조는 가설 결과가 아니다. EXP-3·EXP-2 등록 실행은 시작되지 않았다. 적격성·smoke 출력은 인프라 키만 읽었다. 실행 코드(E `bed077a`)와 분석기는 바뀌지 않는다.
  - 근거 문서(저장소 밖): 외부 검토 보고서, 팀 응답, 동결 묶음(`~/capstone-work/review-external-20261112/`).

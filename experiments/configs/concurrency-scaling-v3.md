# 동시 실행 벤치마크 설계 v3 (2호스트)

> **비등록·비합산 도구 측정.** 라벨은 `demo run`이다. 가설 검정이 아니고 EXP-0·파일럿·EXP-2·EXP-3 데이터에 합치지 않는다.
> raw의 oracle 값은 봉인한다(v2 §6.6, 두 호스트 모두). 결정 대상은 **호스트별** 본실험 동시 실행 수다. 효과 주장이 아니다.
>
> **상태:** 측정 전 설계 초안(Draft PR). 지웅 승인과 §8 점검표 충족 전에는 실행하지 않는다. 이 파일이 머지된 커밋에서 동결하고, 동결 후 변경은 새 버전 파일로만 한다.
> 결정 기록은 [D044 초안](../../docs/DECISIONS.md#d044--2호스트-동시-실행-벤치마크-설계-v3-초안)이다.
> 과거 Stage A(68af9b4)와 파일럿의 oracle 값은 이 설계를 쓰는 동안 보지 않았다. 임계는 과거 결과를 보고 다시 정하지 않았다.

**나눠 돌리기(48 = 24 + 24)를 쓰지 않은 이유.** 한 집합을 HOST1(2→4)과 HOST2(4→2)로 나누면, 각 호스트에는 수준마다 블록이 1개씩만 남는다. 그러면 v2 §6.4의 ρ1·ρ2·드리프트 d와 §6.1의 기준 바닥값 F를 정의할 수 없고, 규칙대로 두 호스트 모두 `H3-unmeasured`(`selected_jobs=null`)가 된다. 호스트를 가로질러 비교하면 jobs 효과가 호스트와 블록 순서에 완전히 섞여, 호스트별 jobs 선정도 합산 선정도 할 수 없다. 원래 요청이 "불충분하면 표본 배분을 수정하라"를 허용했으므로, 호스트마다 v2의 ABBA 48셀을 그대로 돌리는 배분(총 96셀)으로 바꿨다. 벽시계는 두 호스트가 동시에 돌므로 단일 호스트 단계 A와 같은 수준이고, 두 호스트를 차례로 재는 것의 약 절반이다.

**v2와 달라진 점.** §6의 v2 임계값은 하나도 바뀌지 않았다. 바뀐 것은 다음과 같다.

- 호스트가 2개다. 같은 manifest를 호스트마다 독립 적용하고, 선정도 호스트별로 한다.
- 실행기를 본실험과 공유한다(§4). 재시도 주입값은 0이다.
- 측정 전 엔지니어링 probe 단계를 둔다(§5).
- 강화 방향의 규칙 3개를 더한다(§6.2): V10 실시간 이중 판정, 교차 호스트 일치 X1, 교차 호스트 H2.
- v2 §9의 "2번째 호스트에는 smoke와 jobs 2·j* 각 1블록"은 이 파일로 대체한다. 그 배분으로는 F와 d를 잴 수 없다.

## 1. 질문과 원칙

각 호스트 h에서 jobs=2를 기준으로 4를 비교한다(단계 A). 최대화 대상은 v2와 같이 **시간당 정상 완료 캠페인 수**이고, 타당성과 재현성은 제약이다.
호스트 효과는 선정에 쓰지 않는다. 호스트 h의 jobs 효과는 h 안의 ABBA로만 식별한다. 호스트마다 다른 jobs가 선택될 수 있다.
**바뀌는 것은 호스트 안에서는 동시 실행 수뿐이다.** 두 호스트 사이에 다른 것(CPU, 메모리, 엔진 버전 후보, 시계 속도)은 호스트 속성으로 기록한다.

## 2. 기계판독 설계 블록

v2 블록 형식을 유지한다. 키 추가는 `host.<id>.*`, `retry_max_attempts`, `probe_*`, `v10_*`, `x1_*`이고 `docker_engine`은 호스트별 키로 옮겼다. **현재 드라이버(v2용)는 이 블록을 거부한다.** 도구 변경 목록은 §9에 있다.

```concurrency-benchmark
design_id = concurrency-scaling-v3
target_version = 7.5.2
image_digest = sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb
budget = 2000
seeds = 8110, 8102, 8103, 8106
smoke_budget = 20
smoke_seed = 6100
vocabulary = observed-names
mutation_policy = uniform-generic-m1-state-aware-escape-hardlink-fixed-baseline-v1
arm.R-restart = unretained-seed-restart-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = 20261104
sentinel_count = 5
observer_integrity_policy = invalid-continue
execution_mode = per-case-container
campaign_watchdog_seconds = 10800
disk_stop_fraction = 0.9
memory_stop_fraction = 0.1
stop_nonzero_cells = 6
preflight_load_fraction = 0.25
cooldown_seconds = 120
retry_max_attempts = 1
v10_monotonic_seconds = 7200
v10_realtime_seconds = 7200
x1_margin = 2
x1_incomparable_cells = 2
probe_seeds = 6200, 6201, 6202, 6203, 6204, 6205, 6206, 6207
probe_budget = 1000
probe_jobs = 4
probe_retry_max_attempts = 2
hosts = HOST1, HOST2
host.HOST1.run_prefix = h1
host.HOST1.docker_engine = TBD-PREFLIGHT
host.HOST2.run_prefix = h2
host.HOST2.docker_engine = TBD-PREFLIGHT
stage.smoke = 2
stage.A = 2,4,4,2
stage.B = 4,6,6,4
stage.C = 6,8,8,6
```

- `retry_max_attempts = 1`은 "첫 시도뿐, 재시도 0"이다(v2 §4 "재시도는 하지 않는다" 유지). 근거는 §4.2에 있다.
- `TBD-PREFLIGHT`는 실행 불가 값이다. smoke 전 preflight에서 실제 값(`docker version` Server)을 이 파일의 후속 커밋으로 고정하고, 고정된 SHA에서만 smoke를 시작한다. 드라이버는 `TBD-` 값을 거부해야 한다(§9).
- 단계 B와 C는 v2처럼 호스트별 별도 승인이다. 단계를 건너뛰지 않는다.

## 3. 호스트별 캠페인 할당 manifest

셀 순서는 v2 드라이버의 `planned_cells`와 같다(seed 블록, arm 회전). 블록 4개가 모두 같은 12셀을 같은 순서로 돈다. 두 호스트는 같은 manifest를 쓰고 run_id 접두만 다르다. 출력 디렉터리와 원장은 호스트별로 분리한다.

| 호스트 | 블록 | jobs | 셀(순서대로, run_id = `<prefix>-7.5.2-<arm>-s<seed>`) |
| --- | --- | --- | --- |
| HOST1 (`h1`) | block-1-j2 | 2 | R-restart·D·S-u ×8110, D·S-u·R-restart ×8102, S-u·R-restart·D ×8103, R-restart·D·S-u ×8106 |
| HOST1 | block-2-j4 | 4 | 위와 같음 |
| HOST1 | block-3-j4 | 4 | 위와 같음 |
| HOST1 | block-4-j2 | 2 | 위와 같음 |
| HOST2 (`h2`) | block-1-j2 | 2 | 위와 같음 |
| HOST2 | block-2-j4 | 4 | 위와 같음 |
| HOST2 | block-3-j4 | 4 | 위와 같음 |
| HOST2 | block-4-j2 | 2 | 위와 같음 |

호스트당 48캠페인(수준당 24), 총 96캠페인, 192,000 실행. 두 호스트는 같은 시각에 시작하는 것을 목표로 하되, 동기화는 요구하지 않는다(블록 간 비교는 호스트 안에서만 한다).

**예상 벽시계(추정, 보장 아님).** HOST1 단계 A는 v2 추정 15–20 h(오케스트레이터 추정 13–20 h)다. HOST2는 미측정(UNKNOWN)이다. 전체는 두 호스트 중 긴 쪽이다. probe는 호스트당 2 h 이내가 목표다(§5).

## 4. 실행 경로: 공유와 차이

### 4.1 공유 코드 경로 (실행 SHA에서 해시 기록)

| 층 | 파일·객체 |
| --- | --- |
| 셀 내부 | `scripts/local_node_tar_smoke.sh`, `scripts/bounded_cleanup_command.py`, `src/inodefence/execution/container.py`, `src/inodefence/execution/docker_client.py`, `scripts/container_host.py`, `scripts/container_controller.py`, 대상 이미지 `22c8734f…` |
| 실행기 | `scripts/run_exp0.py`의 `run_cell_with_watchdog`, `scripts/run_parallel_native.py`의 `cell_env`, `src/inodefence/execution/start_gate.py`(StartGate, W1), 공유 preflight·잔존 리소스 확인·샘플러(W1이 공유 함수로 분리) |

**규칙:** 벤치마크 드라이버는 본실험(`run_exp0 --jobs`)과 같은 StartGate와 공유 함수를 import해서만 셀을 시작한다. ThreadPool이나 Popen을 따로 구현하는 것은 금지한다. 드라이버는 실행 전에 위 파일의 sha256을 preflight 기록에 남긴다. 본실험 등록도 같은 목록의 해시를 남기며, 두 목록이 다르면 벤치마크 결과를 옮기지 않는다.

배경(관찰): 2026-11-11 기준 두 런처는 셀 내부 경로만 같다. 시작/정지 직렬화, cleanup UNKNOWN 처리, 시작 후 러너 실패 처리, 잔존 리소스 확인, 샘플러, Engine preflight는 벤치마크 드라이버(f0d0822)에만 있었다. 이 차이를 공유 실행기로 해소한 SHA에서만 측정한다(§8).

### 4.2 달라지는 설정과 근거 (통일하지 않음, 정책 차이로 문서화)

| 설정 | 벤치마크 | 본실험 | 근거 |
| --- | --- | --- | --- |
| 정지 정책 | v2 §5(비정상 종료 6/12, watchdog 1, 메모리, 잔존 리소스, 외부 탓 3종) | 기록 없는 셀 연속 3개면 인프라 정지, 승인 재개 | 벤치마크 정지는 "수준 탓" 판정의 입력이고, 본실험 정지는 인프라 보호다 |
| 재시도 | 0(`retry_max_attempts = 1`) | 기록 없는 시도만, 최대 2회 | 재시도는 같은 슬롯을 점유해 X(b)의 정의를 바꾼다. v2 §4와 X(b)를 그대로 두기 위해 0으로 주입한다. 재시도 경로 자체는 단위·합성 e2e 테스트와 probe(§5, 본실험 값 2)에서 검증한다 |
| 디스크 | 90%에서 정지(대기 없음) | 비율 도달 시 새 셀 대기 | 대기는 처리량을 오염시킨다(v2 §3.5) |
| watchdog 한계값 출처 | 이 파일 `campaign_watchdog_seconds` | 본실험 사전등록 값 | preflight에서 두 값이 같은지 확인한다. 다르면 벤치마크는 대표성이 없다(§4.3) |
| 원장 형식 | `block.json`·`block.incomplete.json` | `cell_results.jsonl` start/end/정지 이벤트 | 통일하지 않는다. 판정은 각자의 형식으로 한다 |

### 4.3 벤치마크 abort율이 본실험 첫 시도 abort율을 대표하는 조건

다음을 **모두** 충족할 때만 "같은 jobs에서 인프라가 견디는가"를 본실험으로 옮긴다.

1. §4.1 공유 경로의 해시가 두 실행에서 같다.
2. 같은 호스트, 엔진(·Desktop·WSL) 버전, 이미지, jobs, budget, arm·정책, watchdog 값이다.
3. 첫 시도만 센다(본실험 쪽도 첫 시도 abort로 비교한다).
4. H2(입력 종속) 음성이고 H4 미확인이 0이다. 이 경우에만 "인프라 성분"으로 읽는다.
5. preflight의 조용한 호스트 조건과 샘플러 조건이 같다.

**한계.** 측정 seed는 abort 이력으로 골랐다(D041). 그래서 a(j)는 본실험 abort율의 추정치가 아니다. EXP-3의 n·abort 추정에는 쓰지 않는다(v2 §6.6 유지). 대표성은 적격성 판단까지만이다.

### 4.4 경로가 바뀌면

- probe 뒤, smoke 전에 §4.1 경로가 바뀌면: 그 호스트는 probe부터 다시 한다.
- smoke 뒤에 바뀌면: smoke부터 다시 한다.
- 측정 블록이 하나라도 돈 뒤에 바뀌면: 그 호스트의 단계 측정은 무효이고, 단계 A를 처음부터 다시 한다. v2 §9의 "jobs 2·j* 각 1블록 재측정"보다 엄격하다. 블록 사이의 코드 변경은 ABBA 드리프트 통제를 깨기 때문이다.
- 근본 원인 수정(런타임 docker inspect/start timeout)이 셀 내부 경로에 들어올 수 있음을 전제로 한다. 그 수정이 들어간 SHA가 probe SHA이고, probe SHA가 곧 벤치마크 실행 SHA다.

## 5. 단계 순서와 엔지니어링 probe

**순서(고정):** 근본 원인 수정 → 통합 head 독립 검증(경쟁 조건 테스트, xfail·skip 잔존, 데이터·로그 보존, 경로 동일성) → 호스트별 probe → 호스트별 smoke → 호스트별 단계 A.

**probe는 비등록이고 판정 입력이 아니다.** 라벨은 `demo run`이고, 노출 원장에 기재하며, oracle을 봉인한다.

| 항목 | 값 |
| --- | --- |
| 목적 | 근본 원인 수정이 inspect/start timeout을 줄이는지, 부작용이 없는지, 재시도 경로가 실제 docker에서 도는지 확인한다 |
| 실행기 | 본실험 런처(`run_exp0 --jobs`)와 공유 실행기, 재시도 본실험 값(2) |
| 셀 | 8셀, 호스트당. seed 6200–6207 각 1셀, arm은 R-restart, D, S-u 순서로 회전(6200 R-restart, 6201 D, 6202 S-u, 6203 R-restart, 6204 D, 6205 S-u, 6206 R-restart, 6207 D) |
| budget, jobs | 1000, 4. 혼잡을 재현하고 캠페인 끝의 보고서 복사·정리를 두 wave에 걸쳐 8회 거친다 |
| 예상 | 8,000 실행. HOST1 jobs 2 실측 약 4,760 exec/h에서 가속이 없으면 약 1.7 h, 선형 가속이면 약 0.9 h(추정). HOST2는 미측정 |
| 통과 조건(사전 고정) | cleanup UNKNOWN 0, 잔존 리소스 0, 러너 실패 0, 시작 실패 0 |
| 보고만 하는 값 | docker 호출별 timeout 수, 진단 줄(`inodefence-cleanup-*`) 수, 재시도 수, 처분 집계. timeout에는 임계를 두지 않는다 |
| 금지 | probe 결과로 §6 임계, seed, 블록 구조, jobs 후보를 바꾸지 않는다. oracle 필드를 읽지 않는다 |
| 실패 시 | 보고하고 그 호스트의 벤치마크를 시작하지 않는다. 수정 후 probe부터 다시 한다 |

**probe seed 6200–6207의 근거.** 노출 원장(`experiments/preregistration/exposure-ledger.md`)과 v1·v2 설계, 드라이버의 `RESERVED_SEED_RANGES`를 대조했다. 기존 노출 ≤1415, v1 벤치마크 6100–6103(6100은 2026-11-10 engineering smoke에서 실행됨), 7001–7002, 파일럿 8001–8003·8101–8110, EXP-0 9001–9005, EXP-3 제안 블록 9006~(9001–9999 예약)과 겹치지 않는다. main의 configs·preregistration·DECISIONS에서 6200–6999를 seed로 쓴 곳도 없다(2026-11-11 확인). 실행하면 원장에 행을 추가하고, EXP-3 seed 제외 목록에 6200–6207을 넣는다.

## 6. 판정 기준 (호스트별, 실행 전 고정)

### 6.1 기본: v2 §6을 호스트마다 글자 그대로

v2 §6.1~§6.6(입력, V1~V10, H1~H5, H3-unmeasured, 멈춘 블록 처리, 기준 수준 재확인, 선택 규칙, 입력 종속, 봉인)과 D041(V9 fail-closed, H3-unmeasured)을 **각 호스트의 블록 4개에 독립 적용**한다. 임계값, 분해능(수준당 24캠페인, a 눈금 1/24, V3 8건부터 배제), 선택 규칙(ρ ≥ 1.15, 정상 비율 반영 ≥ 1.15, d ≤ .15)이 v2와 같다.

- `selected_jobs`는 호스트별(`selected_jobs[HOST1]`, `selected_jobs[HOST2]`)로 낸다. **합산 통계로 선정하지 않는다.** 본실험에 공통 jobs가 필요하면 두 값 중 작은 값을 쓴다.
- 분석기는 호스트 출력을 따로 읽는다. 한 호스트의 블록으로 다른 호스트의 규칙을 판단하지 않는다(아래 X1과 교차 호스트 H2만 예외).

### 6.2 추가 규칙 (모두 강화 방향)

| # | 규칙 | 내용 | 근거 |
| --- | --- | --- | --- |
| V10′ | watchdog 여유, 이중 시계 | 어느 arm이든 셀 시간이 monotonic 7200 s **또는** 실시간 7200 s를 넘으면 배제 | monotonic 속도가 호스트마다 반대로 어긋난다(HOST1 7–9% 빠름, HOST2 약 3.2% 느림, 관찰). monotonic만 쓰면 HOST2는 실시간 약 7440 s까지 통과한다. 둘 중 엄한 쪽을 쓴다 |
| X1 | 교차 호스트 경로 일치 | 같은 (arm, seed)의 HOST1 block-1-j2와 HOST2 block-1-j2를 V9와 같은 방식(경로와 step별 판정값 해시)으로 비교한다. 불일치 셀 수 m_x에 대해 m_x − max(F_HOST1, F_HOST2) ≥ 2, **또는** 첫 불일치 step이 한쪽에서만 `timed_out`·`failed`인 셀 ≥ 2, **또는** 비교 불가 셀 ≥ 2(1개면 보고)이면 발동한다. block-4-j2 쌍은 보고만 한다 | 아래 6.3 |
| H2′ | 입력 종속, 교차 호스트 | 어느 호스트에서든 H2가 걸리면 **두 호스트 모두** 정지한다 | 입력(seed·arm·budget)이 두 호스트에서 같으므로 입력 종속은 호스트의 문제가 아니다 |

**X1은 jobs 배제 규칙이 아니다.** 결과는 본실험 분석에만 영향을 준다(§10). 비교는 분석기 메모리 안에서 해시 일치만 보고, 값은 내보내지 않는다(v2 §6.6).

### 6.3 X1 임계의 정당화와 오탐 확률

V9가 "다른 jobs 블록과의 불일치에서 같은 수준 반복 사이의 바닥 F를 뺀 값 ≥ 2"인 것처럼, X1은 "다른 호스트와의 불일치에서 두 호스트의 바닥 중 큰 값을 뺀 값 ≥ 2"다. 비교 대상이 jobs에서 호스트로 바뀌었을 뿐 논리가 같다. 바닥을 max로 잡아 오탐 쪽을 보수적으로 했다.

**정확 계산(모형 가정, 측정 아님).** 각 셀의 실행 하나가 그 셀의 기준 경로에서 확률 r로 벗어난다(셀·실행 독립, 벗어난 경로끼리는 일치하지 않음 = 불일치 최대 가정). 4개 실행(H1b1, H1b4, H2b1, H2b4)을 셀별로 열거한 결합분포를 12셀에 걸쳐 합성했다. 공유 실행(H1b1이 m_x와 F_HOST1에 모두 들어감)의 상관을 포함한다.

| r(실행당 이탈) | 쌍 불일치 q | 오탐 P(X1 첫 조항) | H3 통과 조건부 |
| --- | --- | --- | --- |
| .01 | .020 | < .0001 | < .0001 |
| .02 | .040 | .0002 | .0002 |
| .05 | .098 | .0038 | .0030 |
| .10 | .190 | .017 | .012 |

호스트 고유 이탈 h가 HOST2 실행에 더해질 때 검출력: r=.02에서 h=.10이면 .26, .25이면 .74, .50이면 .99다(r=.05에서는 .21/.65/.97). 둘째·셋째 조항의 오탐은 계산하지 않았다. 각각 jobs=2의 `timed_out`률과 셀 손실률에 달려 있고, 이 둘은 V7과 V2가 따로 제한한다.

## 7. 시계와 엔진

- **시계.** X(b)는 v2대로 CLOCK_REALTIME이라 보정하지 않는다. 블록 시작·끝의 `clock_stamp`(realtime, monotonic, monotonic_raw)로 mono/real 비율을 블록마다 기록하고, 실시간 동기 상태(`adjtimex` 또는 `timedatectl`)를 preflight에 남긴다. watchdog(10800 s)과 타깃 제한(10 s)은 코드값이라 바꾸지 않는다. 실제 시간은 호스트마다 다르다(10800 mono는 HOST1 약 9900 s, HOST2 약 11150 s 실시간, 관찰된 배율로 추정). 이 차이는 V10′이 막는다.
- **엔진.** `host.<id>.docker_engine`은 smoke 전 preflight에서 실제 값으로 고정한다. 두 호스트를 같은 버전으로 맞출지(현재 HOST1 29.8.0, HOST2 29.9.3, 2026-11-10 관찰), 호스트 속성으로 기록만 할지는 HOST2 재측정과 HOST1 daemon 조사(어떤 daemon이 소켓을 서빙하는지 포함) 결과를 본 뒤 정한다(미정). 어느 쪽이든:
  - 벤치마크 시작부터 본실험 끝까지 그 호스트의 엔진·Docker Desktop·WSL 버전 변경을 금지한다.
  - 선정된 jobs는 그 호스트·그 엔진에서만 유효하다.
  - 대상 이미지 id `22c8734f…`는 두 호스트에서 같아야 한다(필수). 다른 id면 시작하지 않는다.

## 8. 실행 전 점검표 (v2 §7에 더함, 호스트마다)

- [ ] **공유 실행기:** 드라이버가 본실험과 같은 StartGate·공유 함수로 도는 SHA다(§4.1). 통합 head의 독립 검증 PASS.
- [ ] §4.1 경로 해시를 preflight에 기록. watchdog 값이 본실험 사전등록 값과 같다.
- [ ] 근본 원인 수정의 머지 여부를 기록하고, 그 SHA에서 probe PASS(§5).
- [ ] `host.<id>.docker_engine` 고정 커밋, `docker context show`, 소켓을 서빙하는 daemon 확인.
- [ ] 이미지 id `22c8734f…`(HOST2는 `docker save`/`load`로 옮긴 경우 id 보존을 확인).
- [ ] HOST2: WSL 메모리 상한 적용 후 가용 메모리, 디스크, load가 v2 §7 기준을 충족한다.
- [ ] 실시간 동기 상태와 mono/real 배율 기록.
- [ ] 두 호스트 모두에 봉인(§6.6)과 다른 docker 작업 금지를 통지.
- [ ] 노출 원장 계획 1줄을 LOG에(호스트, seed, budget, 수준, 봉인).
- [ ] 지웅 승인: 호스트별, 단계별.

## 9. 도구 변경 목록 (측정 전에 필요)

- 드라이버: v3 키(`hosts`, `host.<id>.*`, `retry_max_attempts`, `probe_*`, `v10_*`, `x1_*`)를 파싱하고, `TBD-` 값을 거부하며, `--host <id>`로 그 호스트의 엔진·접두를 쓴다. 셀 시작은 공유 실행기로만 한다.
- 드라이버: probe 단계(`--stage probe`, crossed 순서 검사 제외, 본실험 런처 경로)와 probe seed를 `RESERVED_SEED_RANGES`에 추가한다.
- 분석기: 호스트별 판정, V10′, X1(교차 호스트 비교, 값 미출력), H2′ 합동 정지 신호.
- 테스트: v3 블록 파싱, `TBD-` 거부, X1 경계값(m_x − max F = 1과 2, 비교 불가 1과 2), V10′ 이중 시계.

## 10. EXP-3 사전등록 문장 초안 (11/18 동결 전 반영용)

> 본실험은 두 호스트(HOST1, HOST2)에서 실행할 수 있다. 한 seed의 세 arm(seed 블록)은 같은 호스트에 배정하고, 확증 분석(seed 블록 단위 순열 검정)의 구조는 호스트와 무관하게 유지한다. 호스트는 기록 요인이다. 호스트마다 동시 실행 수, Docker 엔진·Desktop·WSL 버전, mono/real 배율, 공유 실행 경로 해시를 기록한다.
> 동시 실행 벤치마크 v3의 교차 호스트 일치 규칙 X1이 발동했으면, 확증 분석은 그대로 두고 호스트별 민감도 표(호스트별 T_first·U_viol 요약과 abort)를 추가 보고한다. 호스트 제외나 단일 호스트 전환은 지웅이 결정하며, 이 결정은 **EXP-3 train 첫 셀 시작 전에** 하고 그 시각과 근거를 `docs/LOG.md`에 기록한다. 그 뒤에는 X1을 근거로 호스트를 제외하거나 바꾸지 않는다. X1이 발동하지 않았어도 호스트는 기록 요인으로 남는다.
> 선정된 동시 실행 수는 그 호스트·그 엔진에서만 유효하다. 벤치마크 시작부터 본실험 끝까지 엔진·Desktop·WSL 버전을 바꾸지 않는다.

결정 시점 고정(train 첫 셀 시작 전, LOG 기록)은 강화 방향의 추가이며 오케스트레이터가 2026-11-11 채택했다.

## 11. 결과 보고 형식 (v2 §10에 더함)

- 호스트별 `concurrency-report.{json,md}`와, 두 호스트를 묶은 요약 1개(호스트별 판정, X1 결과, H2′ 여부, 엔진·시계·경로 해시 표).
- probe 보고: 통과 조건 4개, docker 호출별 timeout 수, 재시도 수(판정 입력 아님).
- 매니페스트(해시만)는 호스트별로 `experiments/summaries/`에 커밋하고 raw는 커밋하지 않는다.

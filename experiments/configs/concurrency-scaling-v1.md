# 동시 실행 벤치마크 설계 v1

> **비등록·비합산 도구 측정.** 라벨은 `demo run`이다. 가설 검정이 아니고 EXP-0·파일럿·EXP-2·EXP-3 데이터에 합치지 않는다.
> raw의 oracle 값은 봉인한다(§6.6). 결정 대상은 본실험의 동시 실행 수이며 효과 주장이 아니다.
>
> **상태:** 준비 단계다. 지웅 승인 전에는 실행하지 않는다. 파일럿 완료와 승인된 정리 작업(main `make check`, git 정리, 임시 브랜치 삭제)이 먼저다.
> §6 판정 기준은 W3-T8이 실행 전에 정한 것이며, 이 파일이 머지된 커밋에서 동결한다. 동결 후 변경은 새 버전 파일로만 한다.

## 1. 질문과 원칙

jobs=2를 기준으로 4·6·8을 비교한다. 최대화 대상은 실행 속도가 아니라 **시간당 정상 완료 캠페인 수**다. 타당성과 재현성은 제약이다.
같은 seed의 결과가 동시 실행 수 때문에 달라지면, 처리량이 올라가도 그 수준은 쓰지 않는다(§3.4).

**바뀌는 것은 동시 실행 수뿐이다.** 실행 모드, 대상 버전, 이미지 digest, budget, sentinel, arm, seed, 셀 순서가 모든 블록에서 같다. 드라이버는 다른 실행 모드를 거부한다.

## 2. 기계판독 설계 블록

드라이버(`scripts/run_concurrency_benchmark.py`)와 분석(`scripts/analyze_concurrency_benchmark.py`)이 읽는 유일한 입력이다. 드라이버에는 파라미터 플래그가 없다.

```concurrency-benchmark
design_id = concurrency-scaling-v1
target_version = 7.5.2
image_digest = sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb
docker_engine = 29.8.0
budget = 2000
seeds = 6101, 6102, 6103
smoke_budget = 20
smoke_seed = 6100
vocabulary = observed-names
mutation_policy = uniform-generic-m1-state-aware-escape-hardlink-fixed-baseline-v1
arm.R-walk = unretained-walk-v1-uniform-mutation-v1
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
stage.smoke = 2
stage.A = 2,4,4,2
stage.B = 4,6,6,4
stage.C = 6,8,8,6
```

**조건을 파일럿과 맞춘 이유.** budget·k·arm·watchdog이 파일럿(`exp3-hazard-pilot-v1`, #267)과 같으므로 파일럿의 jobs=2 실측을 참고값으로 나란히 볼 수 있다(합치지 않는다). budget을 200으로 줄이면 컨트롤러 메모리 증가, R-walk entry 증가, 큰 보고서 복사가 측정에서 빠지고 EXP-3 조건과도 달라진다.

**seed.** 6100(smoke), 6101–6103. 파일럿 8001–8003·8101–8110, EXP-0 9001–9005, EXP-3 제안 블록 9006~, 기존 노출 ≤1415·7001–7002와 겹치지 않는다. `scripts/run_concurrency_benchmark.py`의 `RESERVED_SEED_RANGES`와 테스트가 고정한다. W3 격리 검토 승인. seed가 3개라 입력 다양성은 낮지만 재발 검정에는 유리하다.

**블록 크기.** 4 arm × 3 seed = 12캠페인, 24,000 실행. 12는 2·4·6으로 나누어떨어진다. jobs 8에서는 마지막 4셀이 낮은 점유로 돌아 더 빠르므로, 처리량 판정은 **슬롯이 찬 구간**의 exec/h로 한다(§4).

**arm.** D6에서 R-walk를 쓰지 않기로 정해지면 실행 전에 arm에서 뺀다. 이 파일은 머지로 동결되므로 **새 버전 파일과 W3 재검증이 필요하다.** 결과를 본 뒤에는 빼지 않는다. R-walk만 watchdog에 걸려도 그 수준은 배제된다(V1).

## 3. main 실행 구조 분석

기준: main `0844147`. 코드를 읽은 결과이며 실행으로 확인한 것은 따로 표시한다.

### 3.1 `jobs_max`가 적용되는 지점

- `jobs_max`는 **상한 검사일 뿐이다**: `src/inodefence/evaluation/rds_preregistration.py:721-725`.
- 실제 동시 실행 수는 `--jobs`다: `scripts/run_exp0.py:1318` `ThreadPoolExecutor(max_workers=args.jobs)`.
- 슬롯 하나가 캠페인 하나다. 캠페인 안에서는 직렬이다. 따라서 Docker 입장의 동시성은 컨트롤러 J개 + 타깃 최대 J개다.
- EXP-3 초안은 `jobs_max = 2`다(`exp3-v1.md:224`, #264, 미머지). 다른 값을 쓰려면 재작성 때 함께 바꿔야 한다(§9).

### 3.2 컨테이너 생성·실행·종료·정리 경로

| 시점 | 동작 | 근거 |
| --- | --- | --- |
| 캠페인 시작 | 볼륨 생성, 컨트롤러 실행, `chown`, **`pip install pytest`**, git 설정 | `scripts/local_node_tar_smoke.sh:197-209` |
| 케이스마다 | image inspect(10 s) → create(20 s) → inspect(10 s) → `start --attach`(타깃 제한 10 s) → inspect → wait(10 s) → inspect → cleanup inspect(10 s) → `rm --force --volumes`(10 s) → inspect(10 s) | `src/inodefence/execution/container.py:39-50,116,121,215,307-345` |
| 캠페인 끝 | `docker exec test`, 보고서·steps `docker cp`, 컨트롤러·볼륨 제거 | `scripts/local_node_tar_smoke.sh:118-155` |

- 케이스당 Docker CLI 호출이 위 표만으로 **10회**이고, 호출마다 호스트 브로커(`scripts/container_host.py`)가 프로세스를 띄운다(`execution/docker_client.py:108`). step이 약 1.3 s이므로 슬롯당 약 8회/s, jobs 8이면 약 60회/s로 추정한다(추론, 측정 전).
- 모든 호출에 **고정 제한시간**이 있고, 시간 초과는 곧 `BackendError`다(`container.py:31-36`). 혼잡이 abort로 바뀌는 지점이 여기다.

### 3.3 병목 가능성

| 자원 | 근거 | 판단 |
| --- | --- | --- |
| Docker daemon | LOG 2026-10-31: WSL2에서 step별 컨테이너 생성이 직렬화되어 conc 10 이상에서 붕괴, conc 6이 처리량 천장(decompress, budget 1500). LOG 2026-10-26: jobs 5 과부하로 한 wave 약 4.9 h(맥) | **가장 유력.** 다른 타깃·호스트의 관찰이라 그대로 옮기지 않는다 |
| CPU·커널 | 레인 4: system 97.5 s ≫ user 29.8 s, 12코어 중 load 4에서도 느려짐. 2026-10-31 Windows CPU 약 92% | syscall/IO 바운드. 코어 수가 상한이 아니다 |
| 메모리 | 컨트롤러 42 MiB → 150 MiB 이상 선형 증가(파일럿 §9), 타깃 peak 34–51 MiB, 상한 512 MiB(`model/isolation.py:11`). jobs 8 약 1.6 GiB, 타깃이 상한까지 차는 최악 약 5.6 GiB, 가용 약 22 GiB | 병목 가능성 낮음(추론) |
| 디스크 | 캠페인당 약 70–108 MB(파일럿 추정). wave가 끝날 때 `docker cp`가 몰린다 | 용량은 문제없음. 복사 시간은 측정한다 |
| 시작 폭주 | J개 캠페인이 동시에 `pip install`과 컨트롤러 생성을 시작한다 | 블록 시작의 no-record 위험. 네트워크에도 의존한다 |

처리량은 호스트 상태에 약 3배 민감하다(레인 4, `wp-throughput-20261104`). 그래서 조용한 호스트, 교차 순서, 블록 간 드리프트 보고가 필요하다.

### 3.4 타당성 위험: 혼잡이 abort가 아니라 결과를 바꾼다

**abort 수만 보면 놓치는 위험이다.** 코드로 확인했고 실제 발생은 미관찰이다.

- 타깃 제한 10 s(`targets/node_tar_effect.py:98`)가 `docker start --attach`에 그대로 전달된다(`container.py:307-309`). 이 시간에는 **daemon의 시작 지연이 포함된다.**
- 시간 초과는 `exit_code None` → `TIMED_OUT`이고(`node_tar_effect.py:244`), **abort가 아니라 target 결과다.** 피드백과 다음 입력 선택에 들어간다.
- 즉 과부하에서 정상 추출이 `timed_out`으로 기록되면 탐색 경로가 동시 실행 수에 따라 달라진다. 캠페인은 "정상 완료"로 보인다.

대응(도구에 구현): 같은 arm·seed의 경로를 단계 첫 블록과 비교한다(§4). abort 셀은 공통 앞부분까지 비교한다. `timed_out` step 수와 `target_seconds` 분위수도 낸다. 다만 관찰 무결성 abort에는 동시성과 무관한 비결정성 전력이 있다(LOG 2026-10-30, 14셀 중 3셀 불일치, 이전 정책). 그래서 **같은 단계 기준 수준 두 블록 사이의 불일치를 바닥값 F로 삼는다**(§6).

**동시 실행이 arm에 다른 영향을 줄 경로(W3-T8, 추론).** `feedback_eligible=false`면 입회가 없으므로 관찰 실패의 손해는 S-u·D에만 간다. R은 원래 입회가 없다. 혼잡이 관찰 실패를 늘리면 S-u vs R을 S-u 불리로 민다. 그래서 관찰 오류를 arm별로 낸다(V8).

### 3.5 watchdog·disk pause·cleanup 예외

- **watchdog:** 셀 단위 `process.wait(timeout)`이고 monotonic 기준이다(`scripts/run_exp0.py:862-907`). 이 호스트의 monotonic은 실시간보다 빠르다(EXP-0 당일 1.091). 그래서 10800은 실시간 약 9900 s다. 초과하면 SIGTERM → 30 s 뒤 SIGKILL이다. 혼잡할수록 `docker cp`가 30 s를 넘겨 SIGKILL될 수 있고, 그러면 컨트롤러와 볼륨이 남는다. 같은 RUN_ID는 다음 실행에서 거부된다(`local_node_tar_smoke.sh:166-171`). R-walk가 가장 느리므로 **arm에 치우친 중도절단**이 먼저 나타날 수 있다.
- **disk pause:** 새 셀 시작 때만 검사하고 대기한다(`run_exp0.py:841-859,1305`). 벤치마크에서는 대기가 처리량을 오염시키므로 대기하지 않고 중단한다.
- **cleanup 예외가 첫 오류를 덮는다(W2가 파일럿 abort 3건에서 확인):** `container.py:288-290`의 `finally: remove_owned(...)`가 예외를 던지면 진행 중이던 첫 오류를 대체한다. 보고서 사유는 `str(error)`만 쓰고(`scripts/run_effect_demo.py:355`) 분류도 그 문자열을 쓴다(`scripts/container_controller.py:94`).
  - 그 결과 관찰 오류나 start 실패 같은 첫 오류가 `cleanup_inspect`·`cleanup_remove`로 기록된다. 이 두 범주는 재시도 대상 인프라 사유다(`evaluation/abort_classification.py:98-105`). 그래서 `cleanup_*`만 보면 입력 무관이라고 적을 수 없다.
  - **#271(머지됨)이 격리 경계 파일을 고치지 않고 첫 오류를 얻는다.** Python이 남긴 `__context__` 체인을 `aborted.error_chain`으로 기록한다. 수정하지 않은 `prepare()`로 재현해 확인했다. **실제 docker에서는 미확인이다.** budget 20 smoke에는 abort가 거의 없으므로 첫 실제 확인은 벤치마크의 첫 abort가 될 가능성이 크다. `case_shape`(abort step의 entry 수·종류·바이트)도 함께 들어왔다. 위 줄 번호는 #271 전 기준이다.
  - **미확인 판정(H4):** 보고서 없음, 체인 잘림, 체인 없는 cleanup 사유다. 체인이 끝까지 있으면 마지막이 cleanup이어도 확인이다. 덮인 오류가 있었다면 체인에 더 있기 때문이다. 체인이 없어도 cleanup이 아닌 사유는 덮는 경로가 아니므로 확인으로 센다.
  - **이전 가능성:** 어떤 예외를 올릴지만 바꾸는 수정이면 처리량·timed_out·관찰 오류·경로 일치·abort 수를 옮길 수 있고 smoke로 충분하다. abort 원인 분류는 옮기지 못한다. 재시도·제한시간·정리 순서가 바뀌면 옮길 수 있는 것이 없고 jobs 2·j* 각 1블록을 다시 잰다. 격리 경계 파일 수정은 필요할 때 사람 승인을 받은 별도 PR로 한다.

### 3.6 per-case-container와 worker-pool

- 벤치마크는 **per-case-container만** 쓴다. 실행 모드와 동시 실행 수를 섞지 않는다.
- worker-pool은 main에서 live 실행이 불가능하다. `run_exp0`가 smoke 스크립트의 `DEMO_EXECUTION_MODE` 소비를 요구하는데(`run_exp0.py:725-729`) 스크립트에 없다. `--emit-parity` 배선도 main에 없다(#233 C 묶음).
- 1셀 측정에서 처리량은 동등했다(speedup 1.002, 50 step). 절약되는 것은 캠페인당 컨트롤러 시작 약 10 s뿐으로 보인다. 케이스별 타깃 컨테이너 수명 주기는 그대로이므로, daemon 병목을 풀 가능성은 낮다(추론).

## 4. 측정

**순서와 반복.** 단계 안에서 ABBA 교차로 수준당 2블록이다. 블록 사이 쿨다운은 120 s다. A(2,4,4,2) → B(4,6,6,4) → C(6,8,8,6) 순서이며, 드라이버가 분석 보고서의 판정을 읽어 이전 단계가 통과하지 않으면 다음 단계를 거부한다(§6). 단계마다 별도 승인을 받는다. 앞 단계의 상위 수준이 다음 단계의 기준이다. C는 B가 통과했고 필요한 용량이 아직 부족할 때만 돈다.

**정상 완료 캠페인.** 종료 코드 0, abort 기록 없음, 계획한 step 전부 존재, config·이미지·sentinel 일치, steps 파일이 보고서와 일치. 처분은 `normal` · `abort` · `incomplete` · `no-record` · `unreadable` · `nonconformant` · `integrity-failure`다. 재시도는 하지 않는다. **실패도 데이터다.**

| 지표 | 출처 | 비고 |
| --- | --- | --- |
| **X(b)** | 블록의 슬롯이 찬 구간 실시간 exec/h | 판정 지표. 구간 끝은 (N − jobs + 1)번째 셀 종료 |
| **N(j)** | 수준 전 블록을 합친 정상 캠페인 비율 | 판정 지표. 첫 불일치 step이 한쪽에서만 `timed_out`·`failed`인 셀은 정상에서 뺀다 |
| G | X(b) ÷ budget × 그 블록의 정상 비율 | 보고 칸. 판정에 쓰지 않는다 |
| 전체 경과, 시간당 실행 수, 정상 완료 캠페인 수, 노출 | `block.json`의 CLOCK_REALTIME | 병기 |
| abort·timeout 발생률, abort step과 노출 | 셀 보고서, 반환 코드 | arm별 |
| abort 원인 | `aborted.error_chain`, 분류기, 하네스 `FAILED at step` | 첫 오류 확인 여부(H4) |
| abort 재발·동시 발생·사례 대조 | §6.5 | 입력 종속 판별 |
| target 결과, 관찰 오류 | `trace_termination`, `feedback_eligible`, `observation_failures[].kind` | arm별, oracle 아님 |
| `target_seconds` | 보고서 `timing.per_case` | arm별 p50·p99·p99.9. **abort 셀은 보고서에 없다** |
| 셀 시간 | 실시간, monotonic 최대 | arm별 |
| 경로 불일치 | 단계 첫 블록과 비교 | 블록별 m, `case_sequence`는 arm별, 첫 불일치 step과 양쪽 `trace_termination`. 판정값만 다른 셀은 수준 합계만 |
| 컨테이너 생성·실행·정리 시간 | `docker events` | 엔진 수정 없음, daemon 시계 |
| CPU·RAM·디스크·압력 | `/proc` 30 s, 디스크 사용률 | WSL2는 VM 공유라 Docker 작업 포함 |
| Docker 응답성 | `docker ps` 지연 60 s | 수준과 무관하게 같은 낮은 부하 |
| 결과물·실행기록 무결성 | steps와 보고서 일치 | 처분 `integrity-failure` |

**샘플러 영향.** 이전 측정에서 무거운 샘플러가 처리량을 0.79배로 낮췄다(레인 4). 그래서 `/proc`만 30 s마다 읽고 `docker stats`는 쓰지 않는다. `docker events`는 스트림 1개다. 이 비용이 수준별로 다른지는 측정하지 않았다.

**이 측정이 말할 수 없는 것.** 수준당 48,000 실행이다. abort 0이어도 실행당 상한은 6.3e-5, budget 2000 캠페인 환산 약 12%다. 기준 abort .22에서 abort 2배를 잡을 확률은 약 .29다(W3-T8 정확 계산). **드문 abort의 동등성은 증명하지 못한다.** 처리량, timeout, 관찰 오류, 경로 일치와 큰 악화만 가려낸다. 그래서 선택 규칙은 낮은 수준 쪽으로 기울어 있고, EXP-3에는 실행 중 중단 규칙이 따로 필요하다(§9). 호스트 한 대, 이 이미지, 이 정책에 대한 측정이다. holdout 버전의 혼잡 민감도로 옮기는 것은 미검증이다.

## 5. 중단 조건

드라이버가 새 셀 시작을 멈추고(진행 중인 셀은 끝낸다) 단계를 끝낸다.

| 조건 | 값 |
| --- | --- |
| 블록 내 비정상 종료 셀 | 6개 이상(12셀의 절반). 파일럿 수준 a=.22에서 발동 .03, a=.50에서 .61(W3-T8). 3은 a=.22에서 .51이라 결과에 따른 조기 중단이 된다 |
| watchdog 종료 | 1개 |
| 가용 메모리 | 총량의 10% 미만 |
| 디스크 사용률 | 90% 이상(대기하지 않음) |
| 다른 컨테이너 등장 | 1개 |
| 블록 뒤 잔여 컨테이너·볼륨 | 1개 |

시작 조건: checkout SHA와 clean, 엔진 버전, 이미지 id, 실행 중 컨테이너 0, 잔여 자원 0, load < 코어의 25%. 어긋나면 시작하지 않는다. 멈춘 수준은 배제로 기록한다(§6).

## 6. 판정 기준 (실행 전 고정)

W3-T8이 실행 전에 정했다. 임계값은 W3의 판단이며 측정값이 아니다. `scripts/analyze_concurrency_benchmark.py`가 이 규칙을 기계적으로 적용해 `decision`을 내고, 드라이버는 그 판정으로 다음 단계를 허용한다.

### 6.1 입력

수준 j는 동시 실행 수이고, ref는 같은 단계의 낮은 수준이다(A: 2→4, B: 4→6, C: 6→8). 블록은 ABBA 순서로 12캠페인이다.

- **a(j):** 그 수준의 전 블록에서 abort 캠페인 비율.
- **A(j):** 그 수준의 전체 abort 수. 비교는 같은 단계의 두 블록끼리 한다.
- **X(b):** 블록 b의 슬롯이 찬 구간 실시간 exec/h. abort 수에 거의 흔들리지 않는 처리량 값이다.
- **N(j):** 수준 j의 전 블록을 합친 정상 캠페인 비율. 정상의 정의는 §4를 따르고, 첫 불일치 step이 한쪽에서만 `timed_out`·`failed`인 셀은 뺀다.
- **F:** 같은 단계 ref 두 블록 사이의 결정론 불일치 셀 수(바닥값).

### 6.2 배제 규칙

하나라도 걸리면 그 수준을 배제하고 **더 높은 수준으로 올라가지 않는다.** 중단 조건(§5)으로 멈춘 수준도 배제다.

| # | 항목 | 배제 조건 | 근거 |
| --- | --- | --- | --- |
| V1 | watchdog | 종료 1건 이상 | arm에 치우친 중도절단이 먼저 나타나는 경로다(§3.5). R-walk만 걸려도 배제한다 |
| V2 | 기타 비정상 | no-record·incomplete·unreadable·nonconformant·integrity-failure 합계 2건 이상. 1건은 보고 | 1건은 시작 폭주·`pip install` 같은 일회성일 수 있다(추론) |
| V3 | abort 절대 | a(j) > .30 | 노출 .84로 n=76→91(+20%). 24캠페인이면 8건부터 배제. 참 a=.22면 통과 .86, .30이면 .56, .40이면 .19 |
| V4 | abort 상대 | 단측 정확 조건부 검정 p ≤ .05. A(ref)=0이면 A(j)≥5, 1이면 ≥7, 2이면 ≥9 | 상한만으로는 ref 대비 악화를 못 본다 |
| V5 | arm 치우침 | 수준의 arm×abort에 `arm_abort_independence` p ≤ .10이고 ref보다 abort가 많음. arm당 6캠페인에서 (3,0,0,0)은 .04, (4,1,1,0)은 .089로 걸리고, (3,1,1,0)은 .314, (2,0,0,0)은 .217로 안 걸린다 | 기존 모듈을 재사용한다. 값은 정확 계산 |
| V6 | 타깃 시간 | 어느 arm이든 `target_seconds` p99.9 > 5 s | 제한 10 s의 절반. 10 s를 넘으면 abort가 아니라 `timed_out` 결과가 된다 |
| V7 | timed_out | 어느 arm이든 1,000 step당 1건 초과, 또는 수준 합계가 V4와 같은 표로 ref보다 유의하게 많음 | 결과값 자체가 바뀌는 경로라 abort보다 직접적이다 |
| V8 | 관찰 오류 | arm별 `feedback_eligible=false`율이 ref의 1.25배 초과이고 정확 p ≤ .05, 또는 1,000 step당 20건 초과 | EXP-0 기록: D invalid 8 + failed 4, S-u 3 + 6, R 0(각 1,000 step). 사건이 많아 RR 1.5도 잡는다 |
| V9 | 경로 불일치 | 블록별 불일치 m과 F에 대해 max(m) − F ≥ 2, 또는 첫 불일치 step이 한쪽에서만 `timed_out`·`failed`인 셀이 2개 이상 | 처리량이 올라도 같은 seed의 경로가 바뀌면 쓰지 않는다 |
| V10 | watchdog 여유 | 어느 arm이든 셀 monotonic 최대 > 7200 s(제한의 2/3) | 10800은 실시간 약 9900 s다 |

**핵심 배제는 V7과 V9다.** 혼잡이 `timed_out`으로 기록되면 캠페인은 정상 완료로 보이면서 탐색 경로만 바뀐다. abort 규칙으로는 이 경로를 잡지 못한다.

### 6.3 멈추고 보고하는 경우 (수준 선택을 하지 않음)

| # | 조건 | 처리 |
| --- | --- | --- |
| H1 | jobs=2가 V3을 넘음 | 전제 실패. abort 원인을 먼저 찾는다 |
| H2 | abort가 입력에 종속(§6.5) | 동시 실행 수 문제가 아니다. 벤치마크를 멈추고 EXP-3의 중도절단 처리부터 결정한다 |
| H3 | F ≥ 3 (12셀 중) | 동시 실행과 무관한 비결정성이 커서 V9가 판별력이 없다. 선택은 하지 않는다(`status=halted`, `selected_jobs=null`). EXP-3는 측정된 안전값 jobs=2로 간다(`fallback_jobs=2`). 비결정성을 보고한다 |
| H4 | abort 첫 오류 미확인 비율 > 0 | 미확인 abort는 입력 종속으로 간주해 V3·V4에 그대로 세고, 결과에 그 수를 병기한다. 미확인은 보고서 없음, 체인 잘림, 체인 없는 cleanup 사유다. **체인이 끝까지 있으면 마지막이 cleanup이어도 확인이다**(덮인 오류가 없다는 뜻) |

### 6.4 선택 규칙

한 단계 올라가려면 다음을 모두 만족해야 한다.

1. 상위 수준이 V1~V10을 통과한다.
2. ABBA 반쪽별 비율 ρ1 = X(블록2)/X(블록1), ρ2 = X(블록3)/X(블록4)에서 min(ρ1, ρ2) ≥ 1.15.
3. 정상 비율까지 반영해도 이득이 남는다: min(ρ1, ρ2) × N(j)/N(ref) ≥ 1.15.
4. 드리프트 d = max(|X(블록4)/X(블록1) − 1|, |X(블록3)/X(블록2) − 1|) ≤ .15.

**2026-11-07 W3 정정(실행 전, 데이터 없음).** 첫 규칙은 ρ와 d를 블록별 G(정상 비율 포함)로 계산했다. 12셀 블록은 abort 잡음이 커서, a=.22에서 처리량이 실제로 2배여도 통과 .29, 드리프트 무효 약 .70이었다(정확 계산, 호스트 잡음 제외). 그래서 ρ와 d는 X로 재고 정상 비율은 수준 합계로 한 번만 쓴다. 호스트 잡음을 뺀 통과 확률은 a=.22에서 이득 1.0/1.2/1.5/1.75/2.0일 때 0/.57/.95/.99/1.00이고, abort가 .44로 2배가 되면 1.2/1.5/1.75/2.0에서 .07/.37/.66/.84다. 첫 규칙의 "min(ρ) − 1 > d"는 잉여라서 뺐다.

드리프트가 .15를 넘으면 그 단계의 처리량 판정은 무효이고 재실행은 별도 승인이다. **최종 값은 이 절차로 도달한 가장 높은 수준이다. 어느 단계도 통과하지 못하면 jobs=2다.** jobs=2는 측정된 값이므로 이것도 정상 결론이다.

**단계 건너뛰기 금지.** C는 B가 통과했고 필요한 용량이 아직 부족할 때만 돈다. 기준 밖 선택을 하려면 사람 결정으로 기록하고, 이 기준에 따른 선택이라고 적지 않는다.

**이 규칙이 쓰지 않는 것:** C0·C1·C2의 값과 방향, hit, T_first, U_viol. 단 경로 불일치 m과 F에는 step별 판정값 해시가 같은지 여부가 들어간다. 분석기는 이 비교를 위해 raw의 oracle 필드를 메모리에서 읽고 값을 내보내지 않는다.

분석기의 `decision.status`는 `selected`, `provisional`(통과한 단계까지의 수준, 다음 단계 미실행), `pending`, `halted`다. `pending`과 `halted`에서는 `selected_jobs`를 내지 않는다. `fallback_jobs`는 H3만 걸렸을 때만 낸다. 비교로 고른 값이 아니다.

### 6.5 abort가 입력에 종속되는가

같은 seed를 블록마다 반복하므로 입력이 같다. 이것이 가장 강한 검정이다.

| 신호 | 입력 종속 | 입력 무관 |
| --- | --- | --- |
| **재발** | 같은 (arm, seed, step, case_id)가 2개 블록 이상에서 abort | 재발 0 |
| 동시 발생 | 무관 | 병행 셀의 abort나 daemon 이상이 ±60 s 안에 겹침 |
| 단계 | 추출·관찰 단계 | archive 읽기 전 |
| 사례 대조 | abort step의 entry 수·종류가 같은 셀의 다른 step과 다름. 연산은 다른 블록의 공통 앞부분에 있는 같은 step으로 본다. `content_bytes`는 정상 step에 없어 대조 없이 기록만 한다 | 차이 없음 |

- **판정:** 일정 hazard(1.24e-4/step)에서 우연히 같은 step이 재발할 확률은 abort당 약 4e-4다. 그래서 **재발 1건이면 입력 종속으로 본다**(H2). `case_id`가 내용 주소이므로 경로가 갈라진 셀은 자동으로 제외된다.
- **입력 무관으로 적을 수 있는 조건:** 재발 0, 첫 오류 전부 확인, 다수가 archive 읽기 전 단계. 이때도 "이 seed·이 정책 범위에서"로만 적는다. **재발 0에는 분모를 붙인다:** abort 난 case가 다른 블록의 같은 위치에서 abort 없이 지나간 횟수 m과 그 95% 상한(1 − .05^(1/m))을 함께 적는다. 경로가 갈라져 다시 나온 적이 없으면 재발 0은 아무것도 말하지 않는다.
- **정보용:** `case_id`만 같고 arm·seed·step이 다른 abort는 함께 내지만 H2에 넣지 않는다. 흔한 case는 우연히 겹칠 수 있다.
- **도구 한계:** 단계는 하네스 `FAILED at step`과 첫 오류 문자열로 사람이 읽는다. 도구는 "archive 읽기 전"을 자동 판별하지 않는다.

### 6.6 raw 봉인

12 시드-arm 조합은 파일럿 40캠페인의 약 30%에 해당하는 hazard 정보이고, 값이 raw에 있다. 불리언 출력만으로는 부족하다.

- **봉인:** EXP-3 동결 전까지 어떤 세션도 raw의 oracle 필드를 읽지 않는다. 해시 계산과 이 분석기만 허용한다.
- **금지:** n, x, k, R 변형, D1~D20, EXP-2 GO/NO-GO의 입력으로 쓰지 않는다. 파일럿·EXP 데이터와 합치지 않는다.
- **공개:** 벤치마크의 존재, seed, 봉인 상태를 EXP-3 사전등록에 적는다. 동결 후 hit 유무를 별도 항목으로 공개하고 추정에는 넣지 않는다.
- **허용:** arm별 `trace_termination`·관찰 실패는 oracle이 아니다. 다만 동시 실행 판정에만 쓰고 D6 근거로 쓰지 않는다.
- **남는 누출:** 경로 불일치는 "그 셀의 어딘가가 달랐다"를 알려 준다. 판정값만 다른 셀은 arm 없이 수준 합계로만 낸다. 블록별 m에는 포함된다.

## 7. 실행 전 점검표

- [ ] 파일럿 완료 통지, W2 raw 매니페스트 완료.
- [ ] main 전체 `make check`, git 정리, `w1/*` 삭제 완료(승인된 선행 작업).
- [ ] 지웅 승인 기록(단계별). §6 동결 커밋 확인.
- [ ] 실행 SHA에 #271(`error_chain`, `case_shape`)이 들어 있는지 확인(머지됨). 필드의 실제 동작은 abort가 있어야 보이므로 smoke로는 확인되지 않을 수 있다. 첫 abort 때 확인하고, 그 전까지 미확인으로 적는다.
- [ ] D6 결과 확인: R-walk를 쓰지 않기로 했으면 동결 전에 arm에서 뺀다.
- [ ] 노출 원장: 실행 전 LOG에 계획 1줄(seed, budget, 수준, oracle 봉인).
- [ ] 봉인 규칙(§6.6) 전 세션 통지.
- [ ] 다른 세션 docker·`make check`·대용량 pytest 동결 통지.
- [ ] 이 파일과 도구가 main에 머지됨, 그 SHA에 detached worktree, `uv.lock` 없음, clean.
- [ ] `docker ps -a` 잔여 없음, `docker volume ls` 잔여 없음, 이미지 id `22c8734f…`, 엔진 29.8.0.
- [ ] Docker 엔진이 Desktop 쪽인지 확인(`docker context show`). 파일럿과 같아야 한다.
- [ ] 디스크 여유 20 GB 이상, 가용 메모리 15 GiB 이상, load < 3.
- [ ] Windows 절전·재부팅 차단, `adjtimex` 값 기록.
- [ ] `--dry-run`으로 계획 확인, 출력 경로가 증거 트리 밖인지 확인.

## 8. 실행 명령과 승인 요청 정보

`<SHA>`는 머지된 main SHA, `<APPROVAL>`은 승인 기록이다.

```bash
git worktree add --detach /home/linux/Projects/wt/conc-bench <SHA>
cd /home/linux/Projects/wt/conc-bench
export PYTHONPATH=src
DESIGN=experiments/configs/concurrency-scaling-v1.md
OUT=$HOME/inodefence-benchmarks/concurrency-scaling-v1

python3.12 -m scripts.run_concurrency_benchmark --design "$DESIGN" --output "$OUT" --stage A --dry-run
python3.12 -m scripts.run_concurrency_benchmark --design "$DESIGN" --output "$OUT" --stage smoke \
  --expected-head <SHA> --approval-ref "<APPROVAL>"
python3.12 -m scripts.run_concurrency_benchmark --design "$DESIGN" --output "$OUT" --stage A \
  --expected-head <SHA> --approval-ref "<APPROVAL>"
python3.12 -m scripts.analyze_concurrency_benchmark --design "$DESIGN" --output "$OUT"
# 결과 보고 → 별도 승인 → --stage B, 다시 승인 → 필요하면 --stage C
# 끝난 뒤: 매니페스트(해시만)를 만들어 experiments/summaries/에 PR로 커밋한다. raw는 커밋하지 않는다.
python3.12 scripts/make_raw_manifest.py --root "$OUT" --host win --date <YYYYMMDD> \
  --out <main worktree>/experiments/summaries/raw-manifest-concurrency-<YYYYMMDD>.sha256
```

진행 확인은 `--status`다. 블록 기록만 읽고 셀 파일은 읽지 않는다.

**승인 요청 7항목**

1. **명령:** 위와 같다. 단계마다 승인한다.
2. **예상 소요(추정).** jobs 2 기준 4760 exec/h(EXP-0 실경과)로 블록 약 5.0 h. 상위 수준은 미측정이라 범위로 적는다: 하한은 선형 가속, 상한은 가속 없음.

   | 단계 | 블록 순서 | 예상 |
   | --- | --- | --- |
   | smoke | jobs 2, 4셀, budget 20 | 약 5분 |
   | A | 2,4,4,2 | 15–20 h |
   | B | 4,6,6,4 | 8–20 h |
   | C | 6,8,8,6 | 6–20 h |

3. **시드:** smoke 6100, 측정 6101–6103. 전 블록 공통.
4. **순서·반복:** 단계당 ABBA 2회, 수준당 2블록, 블록당 12캠페인. 2→4 먼저, 안정 확인 후 6, 필요 시 8.
5. **중단 조건:** §5.
6. **예상 자원(추정):** 메모리 jobs 8에서 약 1.6 GiB, 최악 약 5.6 GiB. 디스크 블록당 약 0.9–1.3 GB, 전 단계 최대 약 17 GB. CPU는 상위 수준에서 포화에 가까울 수 있다(2026-10-31 conc 6에서 약 92%). 벤치마크 동안 호스트의 다른 docker 작업은 금지다.
7. **데이터 분리:** raw는 `~/inodefence-benchmarks/`이며 증거 트리와 저장소 안은 드라이버가 거부한다. 해시만 담은 매니페스트를 `experiments/summaries/`에 커밋한다. 라벨은 `demo run`이고 oracle 필드는 봉인한다(§6.6). 7.5.2 외 버전은 실행하지 않아 holdout 후보는 건드리지 않는다.
   **노출 원장 절차:** 도구는 원장을 고치지 않는다.
   1. 실행 전: LOG에 계획 1줄(seed, budget, 수준, oracle 봉인).
   2. 실행 후, **EXP-3의 `exposure_ledger_sha256` 고정 전:** standalone PR로 7.5.2에 행 추가. `exposure_kind = concurrency benchmark (oracle 봉인)`, seed, budget, jobs 수준, 이미지 digest, 경로, 매니페스트 sha.
   3. EXP-3 seed 제외 목록(`exp3-v1.md:149`)에 6100–6103을 넣는다.
   4. 고정 뒤에 실행하면 원장이 바뀌어 사전등록이 fail-closed로 재등록돼야 한다. 그래서 순서를 강제한다.

**선행 조건:** #271은 머지됐다. 격리 경계 파일 수정이 필요 없어져 사람 승인 항목에서 빠졌다.

## 9. EXP-3 반영 시 변경 목록

**코드 변경이 필요하다.**

- **런처 셀 순서:** `scripts/run_exp0.py:285-286`은 arm→seed 순서로 셀을 만든다. 벤치마크는 seed 블록·arm 회전이라 혼잡 구성이 다르고, 현재 런처로는 시간과 arm이 섞인다(EXP-0도 그랬다). **이 결과를 옮기려면 EXP-3 동결 전에 런처를 seed 블록·회전으로 바꾼다.** EXP-0·파일럿 기록은 그대로 두고 공개한다.
- **실행 경로 변경과 재측정:** 벤치마크와 EXP-3의 실행 경로(`scripts/container_*`, `run_effect_demo.py`, `local_node_tar_smoke.sh`, `execution/`, `targets/`, `observer/`, `feedback/`, `mutator/`)가 달라지면 결과를 그대로 옮기지 않는다.
  - 기록 필드만 추가, 또는 어떤 예외를 올릴지만 바꿈: smoke.
  - step당 Docker 호출, 재시도, 제한시간, 정리 순서, 오류 처리 변경: jobs 2·j* 각 1블록 재측정.
  - #122·#233·#255 등이 머지되면 해당 여부를 판단한다.

**사전등록 값(동결 전 변경, 동결 후 금지).**

| 항목 | 처리 |
| --- | --- |
| `jobs_max` | 선택값으로 변경(`exp3-v1.md:223-224`의 "jobs 3 미측정" 주석 포함). 동결 후 상향은 게이트가 거부한다 |
| 실제 `--jobs` | `jobs_max`는 상한뿐이므로 **등록 문서에 정확한 값을 명시**한다. 하향은 아래 중단 규칙으로만 |
| `campaign_watchdog_seconds` | 선택 수준의 셀 시간과 monotonic 배율로 다시 계산한다 |
| `execution_mode` | per-case 외 모드는 이 벤치마크가 뒷받침하지 않는다 |
| Docker 엔진·VM CPU/메모리 | 기록한다. 다르면 결과를 옮기지 않는다 |
| 호스트 | 호스트별 결과다. 2번째 호스트에는 smoke + jobs 2·j* 각 1블록 |
| **실행 중 중단(새로 등록)** | arm을 보지 않는 pooled abort. 처음 15캠페인에서 8건 이상이면 새 셀을 멈추고 원인을 본다. 참 a=.22면 발동 .008, .50이면 .50. 재개는 동일 설정 또는 jobs=2로만 |

**그 밖.**

- 규모 산정: `exp3-v1.md:311-322`의 처리량, 파일럿 규칙 C의 호스트-일 용량을 선택 수준의 실시간 처리량으로 바꾼다. 계획 abort a = max(파일럿 a, 이 벤치마크의 a(j*)). a는 oracle이 아니다. **순서는 j*를 먼저, 그다음 n이다.** 둘 다 hit를 보지 않는다.
- 사전등록: 벤치마크의 존재, seed, 봉인 상태를 적고 seed 제외 목록(`exp3-v1.md:149`)에 6100–6103을 넣는다. 원장 sha 고정 전에 끝낸다(§8-7).
- EXP-2의 k가 5가 아니면 smoke로 확인한다.
- 논문: `05-method.md` §4.6.3 일정, `paper/deliverables/capstone-report-draft.md`의 소요 서술.
- 운영: EXP-3 런북의 jobs, 호스트 동결 시간, 중단 조건.
- 결과를 EXP-3 데이터와 합치지 않는다.

## 10. 결과 보고서 형식

`analyze_concurrency_benchmark`가 `concurrency-report.{json,md}`를 쓴다. 판정(상태, 선택 수준, 중단 조건, 단계별 배제와 ρ·드리프트·F), 블록 표, arm 표, abort 목록이다.

보고에는 다음을 덧붙인다.

- 호스트 상태(load, 다른 세션 유무), monotonic/실시간 배율.
- H4 수치와, 입력 무관이라고 적을 수 있는지(§6.5).
- 측정이 말할 수 없는 것(§4).
- 저장소에는 요약과 매니페스트(해시만)만 `experiments/summaries/`에 커밋하고 raw는 커밋하지 않는다.
- 봉인을 지켰음을 적는다(§6.6).

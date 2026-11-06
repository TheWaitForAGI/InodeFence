# 동시 실행 벤치마크 설계 v1

> **비등록·비합산 도구 측정.** 라벨은 `demo run`이다. 가설 검정이 아니고 EXP-0·파일럿·EXP-2·EXP-3 데이터에 합치지 않는다.
> oracle 값을 읽지 않는다. 결정 대상은 본실험의 동시 실행 수이며 효과 주장이 아니다.
>
> **상태:** 준비 단계다. 지웅 승인 전에는 실행하지 않는다. 파일럿 완료와 승인된 정리 작업(main `make check`, git 정리, 임시 브랜치 삭제)이 먼저다.
> 판정 기준은 W3 방법론 문서를 따른다(§6). 이 파일은 동결 전 초안이며 W3 정합을 받은 뒤 고정한다.

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
stop_nonzero_cells = 3
preflight_load_fraction = 0.25
cooldown_seconds = 120
stage.smoke = 2
stage.A = 2,4,4,2
stage.B = 4,6,6,4
stage.C = 6,8,8,6
```

**조건을 파일럿과 맞춘 이유.** budget·k·arm·watchdog이 파일럿(`exp3-hazard-pilot-v1`, #267)과 같으므로 파일럿의 jobs=2 실측을 참고값으로 나란히 볼 수 있다(합치지 않는다). budget을 200으로 줄이면 컨트롤러 메모리 증가, R-walk entry 증가, 큰 보고서 복사가 측정에서 빠지고 EXP-3 조건과도 달라진다.

**seed.** 6100(smoke), 6101–6103. 파일럿 8001–8003·8101–8110, EXP-0 9001–9005, EXP-3 제안 블록 9006~, 기존 노출 ≤1415·7001–7002와 겹치지 않는다. `scripts/run_concurrency_benchmark.py`의 `RESERVED_SEED_RANGES`와 테스트가 고정한다. **W3 격리 검토 대상이다.**

**블록 크기.** 4 arm × 3 seed = 12캠페인, 24,000 실행. 12는 2·4·6으로 나누어떨어진다. jobs 8에서는 마지막 4셀이 낮은 점유로 돌므로, 전체 처리량과 함께 슬롯이 찬 상태의 추정치(`jobs × 3600 / 평균 셀 실시간 초`)를 낸다.

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

대응(도구에 구현): 같은 arm·seed의 보고서를 블록 간에 `check_native_determinism.compare_report_pair`로 비교하고, `timed_out` step 수와 `target_seconds` 최대값을 낸다. 비교 결과는 불리언만 남기므로 oracle 값은 노출되지 않는다. 다만 관찰 무결성 abort에는 동시성과 무관한 비결정성 전력이 있다(LOG 2026-10-30, 14셀 중 3셀 불일치). 그래서 **기준 수준(jobs 2) 두 블록 사이의 불일치를 바닥값으로 함께 본다.**

### 3.5 watchdog·disk pause·cleanup 예외

- **watchdog:** 셀 단위 `process.wait(timeout)`이고 monotonic 기준이다(`scripts/run_exp0.py:862-907`). 이 호스트의 monotonic은 실시간보다 빠르다(EXP-0 당일 1.091). 그래서 10800은 실시간 약 9900 s다. 초과하면 SIGTERM → 30 s 뒤 SIGKILL이다. 혼잡할수록 `docker cp`가 30 s를 넘겨 SIGKILL될 수 있고, 그러면 컨트롤러와 볼륨이 남는다. 같은 RUN_ID는 다음 실행에서 거부된다(`local_node_tar_smoke.sh:166-171`). R-walk가 가장 느리므로 **arm에 치우친 중도절단**이 먼저 나타날 수 있다.
- **disk pause:** 새 셀 시작 때만 검사하고 대기한다(`run_exp0.py:841-859,1305`). 벤치마크에서는 대기가 처리량을 오염시키므로 대기하지 않고 중단한다.
- **cleanup 예외가 첫 오류를 덮는다(W2가 파일럿 abort 3건에서 확인):** `container.py:288-290`의 `finally: remove_owned(...)`가 예외를 던지면 진행 중이던 첫 오류를 대체한다. Python은 원래 오류를 `__context__`에 두지만 보고서 사유는 `str(error)`만 쓴다(`scripts/run_effect_demo.py:355`). 분류도 그 문자열을 쓴다(`scripts/container_controller.py:94`).
  - 그 결과 관찰 오류나 start 실패 같은 첫 오류가 `cleanup_inspect`·`cleanup_remove`로 기록된다. 혼잡할수록 두 오류가 겹치기 쉽다.
  - 이 두 범주는 재시도 대상 인프라 사유다(`evaluation/abort_classification.py:98-105`). 잘못 분류되면 비인프라 오류까지 재시도 대상으로 읽힌다.
  - **벤치마크 영향:** `cleanup_*` 사유만으로는 첫 원인을 알 수 없다. 분석은 이런 abort에 `first_error_may_be_masked`를 표시한다. **원인 분류는 부분적으로만 가능하다.**
  - **수정은 이 PR 밖이다.** 격리 경계 파일이라 사람 승인을 받은 별도 PR로 한다. 수정이 들어오면 엔진이 바뀌므로, 벤치마크 전에 넣을지 먼저 결정해야 한다(§8 승인 항목 8).

### 3.6 per-case-container와 worker-pool

- 벤치마크는 **per-case-container만** 쓴다. 실행 모드와 동시 실행 수를 섞지 않는다.
- worker-pool은 main에서 live 실행이 불가능하다. `run_exp0`가 smoke 스크립트의 `DEMO_EXECUTION_MODE` 소비를 요구하는데(`run_exp0.py:725-729`) 스크립트에 없다. `--emit-parity` 배선도 main에 없다(#233 C 묶음).
- 1셀 측정에서 처리량은 동등했다(speedup 1.002, 50 step). 절약되는 것은 캠페인당 컨트롤러 시작 약 10 s뿐으로 보인다. 케이스별 타깃 컨테이너 수명 주기는 그대로이므로, daemon 병목을 풀 가능성은 낮다(추론).

## 4. 측정

**순서와 반복.** 단계 안에서 ABBA 교차로 수준당 2블록이다. 블록 사이 쿨다운은 120 s다. A(2,4,4,2) → B(4,6,6,4) → C(6,8,8,6) 순서이며, 드라이버가 이전 단계가 깨끗하지 않으면 다음 단계를 거부한다. 단계마다 별도 승인을 받는다. 앞 단계의 상위 수준이 다음 단계의 기준이다.

**정상 완료 캠페인.** 종료 코드 0, abort 기록 없음, 계획한 step 전부 존재, config·이미지·sentinel 일치, steps 파일이 보고서와 일치. 처분은 `normal` · `abort` · `incomplete` · `no-record` · `unreadable` · `nonconformant` · `integrity-failure`다. 재시도는 하지 않는다. **실패도 데이터다.**

| 지표 | 출처 | 비고 |
| --- | --- | --- |
| 전체 경과, 시간당 실행 수, **시간당 정상 완료 캠페인 수** | `block.json`의 CLOCK_REALTIME | 슬롯 포화 추정치 병기 |
| abort·timeout 발생률 | 셀 보고서, 반환 코드 | 사건 0이면 실행당 rule-of-three 상한 |
| abort 단계·원인 | 보고서 `aborted`, 하네스 `FAILED at step`, 분류기 | 가려짐 표시(§3.5) |
| target 결과 분포, invalid, 관찰 실패 | `feedback.trace_termination`, `validity`, `trace` | oracle 아님 |
| 컨테이너 생성·실행·정리 시간 | `docker events` | 엔진 수정 없음, daemon 시계 |
| CPU·RAM·디스크·압력 | `/proc` 30 s, 디스크 사용률 | WSL2는 VM 공유라 Docker 작업 포함 |
| Docker 응답성 | `docker ps` 지연 60 s | 수준과 무관하게 같은 낮은 부하 |
| 결과물·실행기록 무결성 | steps와 보고서 일치, 블록 간 결정론 | §3.4 |
| arm별 편차 | 정상 셀의 실시간 s/step | 느린 arm 치우침 확인 |

**샘플러 영향.** 이전 측정에서 무거운 샘플러가 처리량을 0.79배로 낮췄다(레인 4). 그래서 `/proc`만 30 s마다 읽고 `docker stats`는 쓰지 않는다. `docker events`는 스트림 1개다. 이 비용이 수준별로 다른지는 측정하지 않았다.

**이 측정이 말할 수 없는 것.** 수준당 48,000 실행이다. abort 0이어도 실행당 상한은 6.3e-5, budget 2000 캠페인 환산 약 12%다. **드문 abort의 동등성은 증명하지 못한다.** 큰 악화와 처리량만 가려낸다. 호스트 한 대, 이 이미지, 이 정책에 대한 측정이다.

## 5. 중단 조건

드라이버가 새 셀 시작을 멈추고(진행 중인 셀은 끝낸다) 단계를 끝낸다.

| 조건 | 값 |
| --- | --- |
| 블록 내 비정상 종료 셀 | 3개 이상(12셀의 25%) |
| watchdog 종료 | 1개 |
| 가용 메모리 | 총량의 10% 미만 |
| 디스크 사용률 | 90% 이상(대기하지 않음) |
| 다른 컨테이너 등장 | 1개 |
| 블록 뒤 잔여 컨테이너·볼륨 | 1개 |

시작 조건: checkout SHA와 clean, 엔진 버전, 이미지 id, 실행 중 컨테이너 0, 잔여 자원 0, load < 코어의 25%. 어긋나면 시작하지 않는다.

## 6. 판정

기준값은 **W3 방법론 문서**가 정한다. 도구는 아래 입력을 낸다.

- 수준별 정상 캠페인/h(블록별 값과 드리프트), abort, watchdog, timed_out, invalid, 관찰 실패.
- 결정론 불일치 셀 수(기준 수준의 바닥값 포함), 무결성 문제, arm 편차, 자원 최대치.

제안(W3 확정 전 초안): 타당성 조건을 만족하는 수준 중 정상 캠페인/h가 가장 높은 수준을 고르되, 다음 단계로 올라간 이득이 두 블록의 드리프트보다 작으면 낮은 수준을 택한다.

## 7. 실행 전 점검표

- [ ] 파일럿 완료 통지, W2 raw 매니페스트 완료.
- [ ] main 전체 `make check`, git 정리, `w1/*` 삭제 완료(승인된 선행 작업).
- [ ] 지웅 승인 기록(단계별), W3 방법론 문서 SHA.
- [ ] 격리 경계 수정의 선행 여부 결정(§3.5).
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
python3.12 scripts/make_raw_manifest.py --root "$OUT" --host win --date <YYYYMMDD> \
  --out "$OUT/raw-manifest.sha256"
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
7. **데이터 분리:** 출력은 `~/inodefence-benchmarks/`이며 증거 트리와 저장소 안은 드라이버가 거부한다. 매니페스트도 그 안에 둔다. 라벨은 `demo run`이고 분석은 oracle을 읽지 않는다. 노출 원장은 sha가 동결 대상이라 **이 도구가 수정하지 않는다.** seed 6100–6103을 원장에 어떻게 기록할지는 W3 결정이다. 7.5.2 외 버전은 실행하지 않아 holdout 후보는 건드리지 않는다.

**추가 결정 1건:** 격리 경계 수정(§3.5)을 벤치마크 전에 넣을지. 권장은 **먼저 넣기**다. abort 원인을 가려내려는 측정이고, EXP-3가 쓸 엔진과 같아야 결과를 옮길 수 있기 때문이다.

## 9. EXP-3 반영 시 변경 목록

- 사전등록: `jobs_max`와 그 주석(`exp3-v1.md:223-224` "jobs 3 미측정"), `--jobs` 실행 명령. 산출 근거로 이 결과를 인용한다.
- 사전등록: `campaign_watchdog_seconds`. 선택한 수준의 셀 실시간과 monotonic 배율로 다시 계산한다.
- 규모 산정: `exp3-v1.md:311-322`의 처리량, 파일럿 규칙 C의 호스트-일 용량. 선택 수준의 실시간 처리량으로 교체한다.
- 논문: `05-method.md` §4.6.3 일정, `paper/deliverables/capstone-report-draft.md`의 소요 서술.
- 운영: EXP-3 런북의 jobs, 호스트 동결 시간, 중단 조건.
- 코드 변경은 없어야 한다. `run_exp0`는 이미 `--jobs`를 받는다. 격리 경계 수정이 들어오면 `engine_sha`가 바뀌므로 smoke를 다시 돈다.
- 벤치마크 seed는 EXP-3 seed에서 제외한다. 결과를 EXP-3 데이터와 합치지 않는다.

## 10. 결과 보고서 형식

`analyze_concurrency_benchmark`가 `concurrency-report.{json,md}`를 쓴다. 표 두 개(수준별 비교, 블록별 자원)와 abort 목록이다.

보고에는 다음을 덧붙인다.

- 선택 수준과 판정 근거(W3 기준 그대로).
- 호스트 상태(load, 다른 세션 유무), monotonic/실시간 배율.
- 드리프트와 기준 수준의 결정론 바닥값.
- 측정이 말할 수 없는 것(§4).
- 저장소에는 요약만 `experiments/summaries/`에 커밋하고 raw는 커밋하지 않는다.

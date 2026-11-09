# H1 runtime failure assessment — 2026-11-09

## 목적과 범위

MacBook에서 GitHub 코드와 기존 보고를 읽고 concurrency-scaling-v2 H1 중단의 실행 경로,
호스트 가설, Windows 후속 진단을 정리했다. M3 실행 인프라의 분석 기록이며 원인 확정,
수정 승인, 실험 재개 승인 또는 H1 해결 선언이 아니다. 이번 분석에서 48개 원본, 캠페인
oracle과 steps는 열지 않았고 Docker나 벤치마크를 실행하지 않았다. 수치는 아래에서 별도
표시한 기존 보고의 재인용이며 독립 재검증하지 않았다.

## 기준 revision

| 대상 | 확인한 head SHA | 역할 |
| --- | --- | --- |
| main | `2278dffb95e2148f0cfe892322abb512f756589f` | 코드·설계 분석 기준 |
| [#306](https://github.com/TheWaitForAGI/InodeFence/pull/306) | `07c66352e8465336127607948ae728c470a8fb5f` | host/broker 상관 분석 |
| [#307](https://github.com/TheWaitForAGI/InodeFence/pull/307) | `fa3e80f7b31dc24921e5ad7353f8a31a000354a3` | cleanup inspect 재조회 후보 |
| [#309](https://github.com/TheWaitForAGI/InodeFence/pull/309) | `fe4a4afaea544592539959d51846b3a05d51be85` | 조건부 broker 지연 분석, #306 위 |
| [#310](https://github.com/TheWaitForAGI/InodeFence/pull/310) | `0274b95a69396bb247cb084fb6e272a7b69169e9` | broker parser guard, #309 위 |

모두 조사 당시 head다. #306→#309→#310은 분석 도구 스택이며 #307은 독립 draft다.

## CONFIRMED — 코드와 기존 보고에서 확인한 내용

### 기존 보고의 수치: 재인용, 원본 미검증

- concurrency-scaling-v2: 48캠페인 중 abort 17, jobs=2는 8/24, jobs=4는 9/24.
- 최초 예외 체인 기준 runtime inspect 14, cleanup inspect 2, 제거 확인 1. runtime inspect
  14건 중 10건에서 선행 start timeout이 보고됐다. 출처: [#307](https://github.com/TheWaitForAGI/InodeFence/pull/307).
- Docker broker timeout은 inspect 30회, start 10회로 보고됐다. 호출 수와 캠페인 수는
  다르다. 출처: [#309](https://github.com/TheWaitForAGI/InodeFence/pull/309).
- 복수 캠페인의 timeout 동시 발생과 23.04초 `docker ps` 지연이 사용자 전달 관찰로
  보고됐다. 출처: [#306](https://github.com/TheWaitForAGI/InodeFence/pull/306).

### 실행과 cleanup 계약

[`PreparedContainer.execute()`](../../src/inodefence/execution/container.py)는 단일 실행
가드를 세운 뒤 `start --attach`를 한 번 호출하고 `ContainerExecutionBackend.inspect()`로
상태를 확인한다. start timeout은 예외가 아닌 `CommandResult.timed_out`이며 타깃 실행,
시작·연결 지연, CLI 출력 drain을 포함한다. CLI 프로세스 종료는 컨테이너 종료를 뜻하지
않는다. [`DockerCLI._run_validated()`](../../src/inodefence/execution/docker_client.py)와
[`container_host._broker_response()`](../../scripts/container_host.py)를 따른다.

첫 runtime inspect가 timeout되면 `checked()`가 `BackendError`를 발생시킨다. 이때 타깃은
created, running 또는 exited일 수 있고 `execute()`의 kill/wait에 도달하지 않는다.
`prepare()`의 `finally`가 `remove_owned()`를 호출하고 host broker도 자기 호출에서 기록한
이름에 대해 후속 cleanup을 시도한다. 제거 전 소유권 확인 실패, 소유권 불일치, 강제 제거
실패 또는 제거 후 부재 확인 실패에서는 정리 완료를 보장할 수 없다. CLI 연결 실패는 부재가
아니다. cleanup 오류가 진행 중이던 최초 예외를 대체할 수 있으며
[`exception_chain()`](../../scripts/run_effect_demo.py)은 제한된 길이로 원인을 기록한다.
start timeout 자체는 반환값이므로 예외 체인만으로 복원되지 않는다.

created에서 start timeout이면 지연된 start 가능성 때문에 소유 컨테이너 제거 및 부재 확인
후에만 timeout outcome을 반환한다. start timeout 후 running이면 kill·wait 및 최종 inspect를
거친다. timeout 없이 attach가 끝났는데 running이면 오류로 중단한다.
exited여도 wait 및 최종 inspect가 필요하다. 최종 상태는 `Running=false`, `Pid=0`,
`Status=exited`여야 하며 정상 attach라면 종료 코드도 일치해야 한다. unknown을 exited로
간주하지 않는다. 실패는 실행 결과를 만들어내지 않고 abort로 전파된다. cleanup이 실패하면
외부 리소스 잔존 가능성을 배제할 수 없다.

[#307 변경](https://github.com/TheWaitForAGI/InodeFence/pull/307/files)은 제거 전 소유권
조회와 제거 후 부재 확인의 cleanup inspect가 timeout일 때에만 최대 1회 재조회한다.
runtime inspect, start, kill, wait 또는 host 정체는 해결하지 않는다. #307은 H1 해결책으로
판정되지 않았다.

### Hazard 파일럿과 실험 영향

[파일럿 결과 메모](../../experiments/summaries/exp3-hazard-pilot-v1-result.md)의 재인용:
탐색·비등록·비합산 40셀 중 abort 11, jobs=2, 실경과 15.17시간. 기록 구간의 6건은
create 뒤 start 없이 destroy됐고, 별도 2건은 실행·종료 후 inspect 실패와 시간상 대응했다.
나머지 3건은 기록기 시작 전이라 상태가 불명이다. Docker Desktop 로그 회전으로 첫 실패
경로를 확정하지 못했다. 이 관찰을 H1 17건에 자동 적용하지 않는다.

[concurrency-scaling-v2](../../experiments/configs/concurrency-scaling-v2.md) §6의 H1은
jobs=2가 V3을 넘으면 원인 조사 후 중단하는 규칙이다. 현재 보고된 결정은 `halted`,
`selected_jobs=null`, `fallback_jobs=null`이다. 이 결과는 그대로 유지한다. 혼잡은 abort
외에도 target timeout 결과와 이후 탐색 경로를 바꿀 수 있다. 현 상태에서 EXP-3 동시성 및
처리량 기반 용량을 확정할 수 없고 조건부 EXP-2에도 일정 위험이 전파된다. 지연 일수는
미확정이다.

## INFERENCE — 경쟁 가설과 판별

| 가설 | 지지할 관찰 | 약화할 관찰 또는 한계 |
| --- | --- | --- |
| CLI·pipe·클라이언트 지연 | daemon은 요청을 제때 처리했으나 CLI 종료 또는 pipe drain이 지연된 시간 일치 기록 | daemon 요청 처리 자체가 지연됐다면 CLI 단독 설명은 약해진다 |
| daemon/API 정체 | 여러 캠페인과 독립 host probe의 동시간 지연, daemon 요청 처리 지연 | 해당 시각 daemon이 정상 처리했다는 신뢰할 수 있는 기록. 동시성만으로 결함 확정 불가 |
| Desktop 백엔드 정체 | Desktop 경계의 시간 일치 지연과 다른 계층의 정상 기록 | 대상 시간 Desktop 로그가 없으면 구분 불가 |
| WSL2·호스트 자원 압박 | 같은 시간 CPU·메모리·I/O pressure, load, Windows/WSL 이벤트 | 정상 샘플은 가능성을 낮추지만 샘플 간 짧은 spike를 배제하지 못한다 |
| 입력 또는 InodeFence 경로 상호작용 | 동일 입력의 반복 실패와 최초 예외·호출 순서 일치, 호스트 상태 정상 | 여러 독립 캠페인의 동시 정체는 입력만의 설명을 약화하나 작은 입력 효과는 배제하지 못한다 |

broker는 전체 지연 표본이 아니다. 정상 start는 느려도 일반적으로 기록되지 않고 빠른 정상
호출도 빠진다. `summary.calls`, 기록 누락 및 drop을 함께 살펴야 한다. 기록된 호출의
p50/p95/p99는 전체 호출의 분위수가 아니다. [#309](https://github.com/TheWaitForAGI/InodeFence/pull/309),
[#310](https://github.com/TheWaitForAGI/InodeFence/pull/310),
[`broker_call_log.py`](../../scripts/broker_call_log.py)를 따른다.

## UNRESOLVED — 수정 NO-GO와 후속 판단

runtime inspect timeout 후 read-only 재조회는 중복 start를 하지 않지만, 타깃이 살아 있으면
그동안 종료 조치가 지연될 수 있다. 타깃 실행시간 상한을 보장하는 안전한 재조회 설계가
확정되지 않아 **runtime inspect 수정은 NO-GO**다. 현재 fail-closed 동작을 유지한다.
최초 오류와 cleanup 오류의 별도 진단 개선은 독립 검토할 수 있지만 abort 해결을 뜻하지 않는다.

최초 장애 계층, 각 컨테이너의 실제 상태와 최종 제거, 입력 기여도, 호스트 개선 효과 및
안전한 jobs 값은 미확정이다. 유효한 Docker 응답을 코드가 잘못 판정하거나 종료·소유권·
부재 보장을 위반하는 것이 재현되면 코드 수정을 검토해야 한다. 안전한 호스트 조건에서도
동일 실패가 지속되는 경우에도 안전 계약을 만족하는 별도 설계와 검증이 필요하다.

호스트만 개선한 뒤의 재검증은 환경·버전·자원·격리를 기록하고 별도 연구 검토와 실행 승인을
받은 새 측정이어야 한다. 기존 48개에 합산하지 않는다. 설계 §9는 step당 Docker 호출,
retry, 제한시간, cleanup 순서 또는 오류 처리 변경 시 jobs=2와 선택 후보 j* 각각 한 블록의
재측정을 요구한다. 현재 j*는 없으며 구체 절차는 별도 결정이 필요하다. 엔진 또는 VM 자원
설정이 다르면 기존 결과를 그대로 옮기지 않는다. 원본 oracle 봉인은 유지한다.

## Windows 귀가 후 진단 체크리스트

실행 중인 실험이 없는지 먼저 확인한다. 다음 Docker 명령은 읽기 전용이지만 daemon에 부하를
주므로 별도 운영 승인 후에만 실행한다. 어떤 명령도 여기서 실행하지 않았다.

1. 기존 비-oracle 보고, `block.json`, broker `*.calls.jsonl`, host events/samples의 시간대,
   header/summary, drop 및 write failure를 확인한다. campaign JSON과 steps는 열지 않는다.
2. PowerShell에서 `Get-Date -Format o`, `wsl.exe --status`, `wsl.exe --list --verbose`,
   `Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime,FreePhysicalMemory,TotalVisibleMemorySize`를
   확인한다. 재시작이나 설정 변경은 하지 않는다.
3. WSL에서 `date -Is`, `uname -a`, `uptime`, `free -h`, `df -h`,
   `cat /proc/pressure/cpu`, `cat /proc/pressure/memory`, `cat /proc/pressure/io`를
   확인한다. 현재 상태와 과거 장애 시각의 샘플을 구분한다.
4. 승인 후 `docker context show`, `docker version`,
   `docker info --format '{{.ServerVersion}} {{.OSType}} {{.NCPU}} {{.MemTotal}}'`,
   `docker ps -a --no-trunc --format '{{.ID}} {{.Names}} {{.Status}}'`,
   `docker volume ls --format '{{.Name}}'`로 현재 상태를 읽는다. 실패는 부재가 아니며
   잔존 항목을 발견해도 이 단계에서 제거하지 않는다.
5. 호출 시간·ID를 host events/samples 및 보존된 Desktop/WSL 로그와 대조한다. 대상 로그가
   회전으로 없다면 미확인으로 둔다. 로그와 원본을 수정하지 않고 민감한 출력의 공유를 피한다.

H1은 halted이며 벤치마크 재실행, EXP-3/EXP-2 시작, runtime retry, PR 병합은 이 문서로
승인되지 않는다. 향후 측정은 별도 승인과 새 출력 경로가 필요하다.

## 2026-11-09 Windows 원본 재분석 — #306/#310

### 범위와 입력

실제 Windows 11 / WSL2 Ubuntu 24.04 호스트에서 기존 `concurrency-scaling-v2`
원본의 **비-oracle host/broker 메타데이터만** 대상으로 #306/#310 분석기를 실행했다.
분석 코드 revision은 `0274b95a69396bb247cb084fb6e272a7b69169e9`이며 입력 원본은
`/home/linux/inodefence-benchmarks/concurrency-scaling-v2`, 진단 출력은
`/home/linux/inodefence-h1-diagnostics-20261109`였다. 원본 캠페인/oracle/steps 및 oracle
상태는 열람하거나 변경하지 않았고, Docker 및 벤치마크도 재실행하지 않았다.

위의 MacBook 분석은 GitHub 코드와 기존 보고만 읽었고 원본을 직접 읽지 않은 분석이었다.
이번 Windows 재분석은 허용된 host/broker 메타데이터를 실제 원본에서 읽어 검증한 후속
분석이다. 따라서 위의 기존 수치 재인용·독립 미검증 진술은 당시 MacBook 분석 범위로
유지하며, 아래 수치에 소급 적용하지 않는다.

### 원본 완전성 및 캠페인 결과

- 캠페인 48개: abort 17, normal 31.
- Broker log coverage: 48/48 complete.
- 분석 JSON 유효성 검사: PASS.
- #306과 #310의 캠페인별 timeout 횟수는 전부 일치했다.
- jobs=2: 8/24 abort (33.33%); jobs=4: 9/24 abort (37.50%).
- jobs=2 중 파일럿 abort 이력 조합을 제외한 집합: 6/12 abort (50.00%).

이 재분석으로 H1 판정은 바뀌지 않는다: `status=halted`, `selected_jobs=null`,
`fallback_jobs=null`.

### Docker 호출 및 동시 timeout

전체 Docker 호출 1,631,478회 중 조건부 기록된 비정상·지연 호출은 41회였다. 기록된
timeout은 Docker CLI 40회(그중 container inspect 30, container start 10)이며, timeout이
기록된 abort 캠페인은 17/17, 정상 완료 캠페인에서 기록된 비정상 호출은 0/31이었다.

broker는 정상 호출의 모든 지연을 기록하지 않는다. 따라서 이 조건부 표본의 p50/p95/p99를
전체 Docker 호출의 지연 분위수로 해석할 수 없으며, 이 집계만으로 원인과 결과의 인과관계를
확정하지 않는다.

KST 기준 동시 Docker timeout 군집 4개:

1. 2026-11-07 18:02:58 — block 1, jobs=2; 서로 다른 캠페인 2개에서 start/inspect timeout.
2. 2026-11-07 21:32:08 — block 3, jobs=4; 서로 다른 캠페인 4개에서 inspect timeout.
3. 2026-11-07 21:32:18 — block 3, jobs=4; 앞서 언급한 네 캠페인에서 inspect timeout 재발.
4. 2026-11-08 03:02:07 — block 4, jobs=2; 서로 다른 캠페인 2개에서 inspect timeout.

block 4에서는 2026-11-08 03:02:22 KST경 시작한 host `docker ps`가 23.0356초 지연됐다.
이는 공통 Docker 호출 경로의 응답 정체를 뒷받침하지만 Docker CLI, daemon, Desktop, WSL2 중
최초 장애 계층을 특정하지 않는다.

### Docker events와 해석 한계

17개 abort 모두 events coverage가 present였고 `bad_rows=0`이었다. 그러나 `near_end`는 각
abort 종료 시각 전후 60초의 **호스트 이벤트 집계**다. 집계를 더하거나 단순 비교해 개별
컨테이너의 최종 제거 성공 여부를 판정할 수 없다. 각 컨테이너의 최종 cleanup 상태와 최초
장애 계층은 여전히 미확정이다.

이 관찰은 복수 캠페인에서 동시 timeout이 나타나고 독립 host `docker ps` 지연도 기록됐다는
점에서 공통 Docker 호출 경로 정체와 부합한다. 인과관계, 최초 실패 계층, 개별 컨테이너의
최종 상태를 증명하지는 않는다.

### 출력 무결성

아래 SHA-256은 Windows WSL2 원본 측 계산값과 전달된 JSON의 계산값이 일치했다.

| 출력 | SHA-256 |
| --- | --- |
| `h1-host-correlation.json` | `6700187b534925b23e8c2681a912da2fe6c661d9f9225d34995eec4bc4e6ed1d` |
| `h1-call-latency.json` | `b09e61c65f044ec1f45aae0c391cf35f92cb1549ad87d3ac8ff0c32cea71d2c2` |

요청된 Google Drive 보존 위치는 `2026-2학기/캡스톤디자인/InodeFence-handoff-20261108/`
`h1-windows-reanalysis-20261109`이다. 백업 성공 여부는 확인되지 않았으므로 이 문서는 Drive
저장 완료를 주장하지 않는다.

### 남은 원인과 후속 Windows 호스트 진단

아직 미확정인 것은 최초 장애 계층(CLI, daemon, Docker Desktop, WSL2 또는 호스트 자원), 각
컨테이너의 최종 cleanup 상태, 그리고 기록된 timeout과 abort 사이의 인과관계다. H1은 계속
halted이며 이 재분석은 안전한 jobs 값 선택, H1 해결 선언, 벤치마크 재실행 또는 EXP-3/EXP-2
실행을 정당화하지 않는다.

다음 진단은 실행 중 실험이 없는 시점에 읽기 전용으로 진행한다: 해당 시점의 Docker Desktop·
WSL 로그 및 Windows 이벤트 로그를 보존 여부와 함께 대조하고, WSL/호스트 CPU·메모리·I/O
pressure 및 Docker daemon 응답 시각을 상관시킨다. 과거 로그가 없으면 최초 장애 계층은
미확인으로 남긴다. 현재 Docker 상태를 조회할 필요가 있으면 daemon 부하를 고려해 별도 운영
승인을 받고 읽기 전용 명령만 수행하며, 실패를 부재로 간주하거나 항목을 제거하지 않는다.
새 측정은 별도 승인 및 새 출력 경로를 사용하고 기존 48개 결과에 합산하지 않는다.

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

## 2026-11-09 Windows 후속 호스트 진단 — Hyper-V 이벤트·PSI·Docker 로그

이 절은 위 Windows 원본 재분석 이후 사용자가 제공한 **Windows PowerShell의 읽기 전용 진단
출력**을 근거로 한다. Windows 이벤트 로그, Docker Desktop 로그 파일 목록 및 벤치마크
`host/samples.jsonl`의 해당 시간 주변 샘플만 조사했다. 원본 캠페인·steps·oracle은 열람하지
않았고, Docker 시작·재설정, 벤치마크 재실행, runtime 코드 변경은 하지 않았다. 여기에 기재한
시간 일치와 자원 지표는 원인 계층의 확정이나 H1 해소 증명이 아니다.

### Hyper-V Event 285: 발생 시각은 일치하지만 배경 빈도가 높음

Windows `Microsoft-Windows-Hyper-V-VmSwitch-Operational`에서 `OID_GEN_STATISTICS`에
관한 경고 Event 285가 2026-11-07 18:03:46 KST와 2026-11-08 03:02:36 KST에 기록됐다.
후자는 같은 날 03:02:22경 시작해 23.0356초 소요된 독립 `docker ps` 구간에 포함된다.
그러나 21:32의 네 캠페인 동시 inspect timeout 시각에는 직접 일치하는 Hyper-V 이벤트가
관찰되지 않았다.

2026-11-06~09 조회 범위에서 Event 285는 총 1,668건이었고 일별 집계는 각각
366·603·589·110건이었다(11/06 및 11/09의 기록·관찰 시간은 온전한 24시간이라는 보장이
없음). 11/07~08에는 매시간 대체로 20~40건으로 **장애 외 시점에도 상시 발생**했다.
따라서 장애 시각의 두 이벤트는 특이적 인과 증거가 아니며, 이 경고만으로 가상 스위치나
NIC 드라이버를 H1 원인이라고 판단할 수 없다. 메시지의 `NicFriendlyName`은
`Default Switch`였지만 현재 별도 `WSL (Hyper-V firewall)` 스위치도 존재하고,
이름·현재 어댑터 목록만으로 과거 Docker/WSL 호출이 어느 스위치를 통과했는지는 알 수 없다.

### 사고 주변 host samples 및 같은 블록 비교 구간

| 구간 (KST) | host 관찰 | 해석 한계 |
| --- | --- | --- |
| block 1, 11/07 18:01~18:04 (jobs=2) | CPU PSI some avg10 약 0.75~3.24%, 메모리 가용 약 22GB, 인근 독립 `docker ps` 약 0.04~0.07초 | start/inspect timeout 전후에 지속적인 CPU·메모리 압박이 뚜렷하지 않음; 정상 `ps`가 다른 Docker 요청의 성공을 뜻하지는 않음 |
| block 3, 11/07 21:24~21:27 (jobs=4, 비교) | CPU PSI some avg10 12.80~15.03%, 메모리 가용 약 21.73~21.92GB, 독립 `docker ps` 약 0.05~0.074초 | 장애 이전부터 CPU 대기가 높았으므로 21:32의 약 14%를 사고 시점의 고유 급증으로 볼 수 없음 |
| block 3, 11/07 21:30~21:34 (jobs=4, 사고) | 사고 직전 CPU PSI some avg10 최대 14.70%, 이후 7.49→0.91%, 메모리 PSI 0%, `docker ps` 최대 0.703초 | CPU 경쟁의 기여 가능성은 있으나 inspect timeout의 최초 원인 증거는 아님 |
| block 4, 11/08 02:45~02:48 (jobs=2, 비교) | CPU PSI some avg10 약 2.72~3.10%, 독립 `docker ps` 약 0.037~0.078초 | 같은 블록의 평상시 비교값 |
| block 4, 11/08 03:02 (jobs=2, 사고) | CPU PSI some avg10 0.80%, I/O PSI 0.42%, 메모리 PSI 0%, 가용 메모리 약 21.96GB, 독립 `docker ps` **23.036초** | 긴 Docker 지연이 지속적인 Linux PSI 상승과 함께 나타나지는 않음; 샘플 간 짧은 spike는 배제 불가 |

PSI `some avg10`은 최근 10초 동안 적어도 일부 작업에 자원 대기가 발생한 시간의
비율이지 CPU 사용률이 아니다. `DockerPsSec=0` 샘플은 샘플러의 미조회 표기일 수 있으므로
실측 0초 응답으로 간주하지 않는다. 표의 값은 약 27~30초 간격 샘플에서 추출한 것으로,
Docker daemon 내부 잠금·Desktop IPC·CLI 파이프 지연을 직접 관측한 것은 아니다.

### Docker Desktop 진단 로그의 보존 범위

Windows `%LOCALAPPDATA%\Docker\log`가 존재했고, `vm/init.log`(약 962KB),
`host/com.docker.backend.exe.log*`, `host/monitor.log*`, 11/07 `electron` 로그 등을
확인했다. 약 1MB 크기의 회전 로그 다수가 존재한다. 관련 로그 29개에 대해 장애 시각의
UTC/KST 문자열을 검색했으나 **일치하는 줄은 0개**였다. 이는 지정된 문자열에 관한
음성 결과일 뿐, 로그 포맷의 차이·회전·소실 가능성을 구분하지 못하므로 해당 시각의
daemon 로그가 완전히 없었다고 확정하지 않는다. 원본 로그 파일은 GitHub에 올리지 않았다.

### 종합 판단 및 다음 게이트

세 장애 블록에서 공통된 지속적 CPU·메모리·I/O 자원 고갈은 관찰되지 않았고,
block 3의 CPU PSI 상승은 사고 전에도 있었다. 여러 캠페인에서 동시 발생한 Docker CLI
start/inspect timeout과 독립 `docker ps` 지연은 공유 Docker 호출 경로의 일시적 정체와
계속 부합하지만, **Docker CLI·daemon·Desktop·WSL2·호스트 중 최초 실패 계층은 미확정**이다.
Event 285는 높은 배경 빈도 때문에 원인 증거로 채택하지 않는다. 개별 컨테이너 최종
cleanup 상태도 여전히 미확정이다.

추가 조사가 필요하면 각 Docker 로그의 실제 타임스탬프 형식·보존 시작/끝을 먼저
확인하고, 확보 가능한 시간 일치 daemon/Desktop 오류만 상관분석한다. 원본이 회전되어
검증 불가하면 `미확인`으로 남기고 **별도 승인된 호스트 조건의 새 출력 경로**에서
재검증 절차를 결정해야 한다. 원래 48개 결과와 새 측정은 합산하지 않는다.

**H1은 계속 `halted`, `selected_jobs=null`, `fallback_jobs=null`이다.**
이 절은 runtime retry 도입, #307 병합, 벤치마크 또는 EXP-3/EXP-2 실행을 승인하지 않는다.

## 2026-11-09 Docker Desktop 로그 보존 최종 대조 — 추가 전달 결과

이 절은 앞 절 이후 Windows 호스트에서 수행한 **읽기 전용 조사 결과의 전달 보고**를
기록한다. 로그 원본이나 `events.jsonl`을 이 작업 환경에서 직접 열거나 독립 재해시하지
않았다. 따라서 아래 파일 범위·이벤트 시각·소유권은 Windows 측 조사자의 보고로 귀속하며,
원본을 GitHub에 올리지 않는다. 모든 표의 시각은 **UTC**이다.

### 활성·회전 로그 보존 범위

활성 파일은 Windows에서 `FileShare.ReadWrite`로 열어 첫/마지막 타임스탬프를 확인했다.
마지막 시각은 조사 중에도 갱신될 수 있는 관측 시점 값이다.

| 로그 계열 | 확인된 회전 파일 범위 (UTC) | 확인된 활성 파일 범위 (UTC) |
| --- | --- | --- |
| `vm/init.log*` | 11/08 00:24:15.676~07:17:26.513 | 11/08 07:17:26.513~11/09 09:14:53.749 |
| `host/com.docker.backend.exe.log*` | 11/08 07:16:46.525~11/09 07:54:47.493 | 11/09 07:54:47.493~09:22:24.249 |
| `host/monitor.log*` | 11/08 07:16:50.341~11/09 07:54:47.049 | 11/09 07:54:47.049~09:22:24.249 |

세 H1 장애 시각은 11/07 09:02:58, 12:32:08~18, 18:02:07~45 UTC이다.
확인한 `vm/init.log*`의 최초 기록은 마지막 장애로부터 약 6시간 22분 뒤이므로,
**확인된 Windows Docker 로그 집합에는 장애 당시 `dockerd`/`containerd` 직접 기록이
보존되어 있지 않다.** 다른 백업·미확인 저장소까지 부정하는 결론은 아니다. backend 및
monitor의 확인된 보존 범위도 모든 H1 장애 이후에 시작한다. 과거 단순 UTC/KST 문자열
검색 0건은 로그 전체 부재의 근거가 아니었다.

한편 `host/electron-2026-11-07.log`에는 block 1 주변 1건, block 3 주변 4건,
`host/electron-2026-11-08.log`에는 block 4 주변 11건이 확인됐다. B1·B3의 기록은
`[VOLUMES] 1 new volume seen, will fetch size` 정보 메시지였으며, 이 자체는 오류 또는
최초 정체 계층의 증거가 아니다.

### Block 4: 제거 이후 두 컨테이너에 대한 HTTP 404

전달된 기존 비-oracle 이벤트 기록(`A/block-4-j2/host/events.jsonl`의 해당 항목)에서
다음 두 ID는 `inodefence-` 이름과 `org.inodefence.execution-owner` 소유권 라벨이
확인됐다. 두 개별 컨테이너의 이벤트 순서는 다음과 같다.

| 컨테이너 ID 접두어 | create | start | die (exit 0) | destroy | 최초 HTTP 404 |
| --- | --- | --- | --- | --- | --- |
| `369bf2896bcb` | 18:03:34.944 | 18:03:35.187 | 18:03:35.290 | 18:03:35.475 | 18:03:37.286 |
| `eb1683c742b8` | 18:03:35.774 | 18:03:36.075 | 18:03:36.209 | 18:03:36.408 | 18:03:37.282 |

Electron `GET /containers/{id}/json` 오류(11/08 일자 로그의 379행 이후)는 두 ID에
대해 `404 Not Found`를 반복 기록했다. **각 `destroy` 이벤트가 최초 404보다 앞선다.**
이 순서는 제거된 컨테이너에 대한 Desktop 측 후속 조회와 부합한다. 다만 조회한 UI의
정확한 내부 경로, 제거를 수행한 주체, 전체 캠페인의 cleanup 완료는 확인되지 않는다.
두 컨테이너의 정상 종료·제거 기록을 전체 17개 abort의 cleanup 증거로 일반화하지 않는다.

Block 4의 최초 Docker CLI timeout은 18:02:07 UTC였고, 독립 `docker ps`는
18:02:22 UTC경 시작해 23.0356초 걸렸다. 위 두 컨테이너는 **그 뒤에 생성됐고**
404도 이후에 기록됐다. 따라서 이 404를 최초 timeout의 원인이라고 볼 직접 증거는 없다.
반대로 이 시각의 404만으로 Docker 호출 경로가 사고 당시 정상적이었다고 소급할 수도 없다.

### 조사 종료 판정과 재검증 전제

현재 확인 가능한 마지막 직접 증거는 조건부 broker CLI timeout 기록, 호스트 샘플·독립
`docker ps` 지연, 그리고 위 시간대의 제한적인 Desktop/Electron 및 Docker 이벤트다.
장애 당시 daemon/backend 직접 로그는 확인된 보존 집합에 없고, 최초 정체 계층이
Docker CLI, Desktop, daemon/containerd, WSL2 또는 Windows 중 어디인지는 **미확정**이다.
컨테이너별 전체 cleanup 완료도 **미확정**이다. Event 285의 높은 배경 발생률과
CPU PSI 관찰만으로 원인을 단정하지 않는다. 동일한 로그에 대한 추가 추정만으로는
판별력이 늘지 않으므로 **이번 과거 로그 조사는 종료**한다.

신규 실행은 이 문서로 승인하지 않는다. 별도 승인 전에 다음 최소 조건을 검토한다.

1. **동결:** 기존 실행 SHA 및 벤치마크 설계·Docker Engine/Desktop 버전·WSL 커널·
   이미지 digest·호스트 자원과 부하 조건을 확인하고 새 측정의 실행 SHA를 고정한다.
   변경된 실행 경로나 다른 호스트의 결과를 이전할 때는 별도 동일성 심사를 거친다.
2. **계측:** controller 요청·broker 수신/반환·Docker CLI 프로세스 시작/종료·파이프
   drain/kill-reap의 벽시계와 monotonic 시간을 분리 기록하고, 보존 가능한 Desktop·
   daemon 로그 및 이벤트와 시간을 대조한다. 정상 호출의 지연 표본도 정의하며 계측
   자체의 간섭을 확인한다. 로그에 daemon 요청별 ID가 없으면 인과 분리를 주장하지 않는다.
3. **안전:** 타깃 실행시간 상한, watchdog, 타임아웃 후 kill/wait, 소유권·최종 부재
   확인을 사전에 검증한다. 컨테이너·볼륨 잔존, 첫 오류 미확인, 계측 실패와 외부 부하
   변화는 명시된 중단·abort 규칙대로 처리한다. runtime inspect retry, 임의 timeout
   연장 및 cleanup 순서 변경은 별도 설계와 안전성 승인 없이는 하지 않는다.
4. **격리:** 원본 `concurrency-scaling-v2` 48캠페인과 oracle을 봉인하고 별도 출력
   디렉터리에서 smoke 및 새 측정을 계획한다. 측정 전후 버전·설정·해시·종료·잔존
   확인을 남기며 기존 결과와 새 결과를 합산하지 않는다.
5. **연구 동일성:** A/B/C의 어휘·예산·seed·실행 및 판정 경로가 유지되는지 검토한다.
   Docker 호출·retry·제한시간·정리·오류처리 변경은 `timed_out`과 탐색 경로에 영향을
   줄 수 있으므로 벤치마크 설계 v2 §9의 재측정 범위를 먼저 결정한다. 기존 H1/H5/V3
   기준을 사후 완화하지 않고, jobs 값이나 EXP-2/3 재개는 새 승인과 검증 결과로만 정한다.

**최종 상태는 `status=halted`, `selected_jobs=null`, `fallback_jobs=null`이다.**
이 후속 기록은 H1 해결, #307 병합, 실제 재실행 또는 EXP-2/EXP-3 시작 승인이 아니다.

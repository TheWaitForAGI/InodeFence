# `inodefence` 사용 안내

[README](../README.md)의 [빠른 시작](../README.md#빠른-시작) 다음에 읽는 상세 안내입니다. 설치 방식별 차이,
설정과 출력 위치, 대상별 검증 수준, 탐색·도중 확인·위반 케이스 읽기, 재실행, 종료 코드, 한계를 다룹니다.
명령과 옵션의 기준은 각 명령의 `--help`입니다. 아래 본문은 README에 있던 문장을 그대로 옮긴 것이며(예외: 호스트 이름·버전 라벨·실제 저장소 URL 표기 정정, 측정 시점 명시, CHANGELOG에서 옮긴 `make target-run` 예시), 실측 수치는
각 절에 적힌 확인 시점·호스트·커밋 기준입니다. 개발용 명령(`make check`, `make demo`, 등록 실험 러너)은 [START_HERE](START_HERE.md)와
[CONTRIBUTING](../CONTRIBUTING.md)에 있습니다.

## 설치

Python 3.12와 저장소 클론이 필요합니다. 대상 실행 드라이버(`inodefence.drivers`)는 패키지에 들어 있지만,
이미지 레시피(`tools/`), 컨트롤러 셸 런처(`scripts/local_*.sh`), 어댑터가 쓰는 고정 입력 모듈
(`experiments/repro/`)은 들어 있지 않습니다.

```bash
git clone https://github.com/TheWaitForAGI/InodeFence.git InodeFence && cd InodeFence
python3.12 -m venv .venv && . .venv/bin/activate   # WSL2 Ubuntu 24.04는 python3 = 3.12
pip install -e .            # 개발까지 하려면 make install (= pip install -e '.[dev]')
inodefence --version
inodefence doctor           # 무엇이 준비됐고 무엇이 빠졌는지, 고치는 법
inodefence targets          # 추출기와 각 추출기가 지원하는 것(옵션·탐색) 표
```

설치 후에는 저장소 밖 어느 폴더에서 실행해도 됩니다. 설치 방식에 따라 되는 명령이 다릅니다
(2026-11-16, Python 3.12 깨끗한 venv·저장소 밖 폴더·빈 환경에서 확인, 후속 작업 커밋 e71a534에서 다시 확인):

| 명령 | `pip install -e .`(클론에서) | `pip install .`(wheel)만 | wheel + `INODEFENCE_HOME=<클론>` |
| --- | --- | --- | --- |
| `--version`, `status`, `summary` | 됨 | 됨 | 됨 |
| `doctor` | 됨 | 실행되지만 repository `FAIL`(종료 1) | 됨 |
| `targets`, `verify`, `explore`, `replay` | 됨 | 안 됨: "repository not found", 종료 3 | 됨 |

- Python 3.13에서는 `pip`이 설치를 거부합니다("requires a different Python"). 3.12만 지원합니다.
- `INODEFENCE_HOME`을 상대 경로로 주면 그 시점의 작업 폴더 기준 절대 경로로 풀어, 세 설치 방식 모두 그 클론의
  코드를 돌립니다(171b0ba 이전 editable 설치는 자기 클론의 코드를 돌렸습니다). 작업 폴더에 따라 가리키는
  클론이 바뀌므로 `doctor`는 `WARN`입니다.
- wheel에 든 드라이버를 직접(`python -m inodefence.drivers.run_target`) 돌리면 클론이 없어 종료 3으로 거부하고
  `inodefence verify / explore / replay`로 돌리라고 안내합니다.

대상을 돌리는 명령은 이미지 레시피(`tools/`)와 셸 런처(`scripts/`)가 있는 **저장소 클론이 꼭 필요**합니다.
wheel로 설치했다면 `INODEFENCE_HOME`(환경 변수 또는 아래 설정 파일)으로 클론 위치를 알려 줍니다. 이때 `targets`·`verify`·`explore`·`replay`는
그 클론을 작업 폴더로 하고 클론의 `src`를 먼저 읽는 하위 프로세스(`python -m inodefence.drivers.…`)에서 돌므로,
드라이버·엔진·이미지 레시피가 모두 그 클론의 것입니다. 결과의 `engine_commit`·`engine_sha`는 그 클론의 `git rev-parse HEAD`(추적 파일 수정이나 `src`·`scripts`·`tools` 아래 추적 안 된 파일이 있으면 `-dirty`)입니다.
`status`·`summary`·`doctor`는 설치된 패키지 코드로 돌고, 대상 드라이버(`run_target`·어댑터)를 import하지 않습니다.
이 셋이 `drivers` 안에서 쓰는 것은 표준 라이브러리만 쓰는 `drivers/repo.py`(저장소 위치)와 `drivers/runtime/health.py`(Docker·호스트 점검)뿐입니다.
`targets`도 `verify`·`explore`와 같은 clone 코드로 돕니다(이전에는 CLI 프로세스 안에서 설치본 엔진과 clone 드라이버가 섞였습니다).
고른 clone에 `src/inodefence/__init__.py`와 `src/inodefence/drivers/`가 둘 다 있어야 합니다. 하나라도 없으면(손상된 clone, 또는 `src/inodefence`는 있지만 `drivers/`가 없는 이 버전 이전 레이아웃의 clone) 다른 설치본으로 대신 돌리지 않고 종료 3으로 거부하며, 그 clone을 갱신(`git pull`)하거나 `INODEFENCE_HOME`을 최신 clone으로 바꾸라고 안내합니다.

`doctor`는 각 항목을 `OK`·`FAIL`·`WARN`·`INFO`·`UNKNOWN`으로 출력합니다. 확인하지 못한 것은 `OK`가
아니라 `UNKNOWN`입니다. 로컬 `inodefence-*` 이미지는 있으면 `OK`로 이름을 나열하고, 없으면 `INFO`
(처음 쓸 때 `--auto-prepare`로 빌드)입니다. 다만 어느 이미지가 어느 대상·버전용으로 바로 쓸 수 있는지는
`doctor`가 판단하지 않고, `inodefence verify --target node-tar --version 7.5.2 --dry-run`(읽기 전용)이
셀마다 재사용/준비 계획을 보여 줍니다. 이미지가 없으면 `--auto-prepare`를 줄 때만 Docker로 빌드합니다
(네트워크 필요). `explore`는 실제 실행에 `--auto-prepare`가 필수이고(없으면 아무것도 실행하지 않고 이유를
출력), `--dry-run`에는 필요 없습니다. `$INODEFENCE_RUNTIME_ROOT`(기본 `/var/lib/inodefence`)는 `make check`·
테스트용 개발 전제라 `doctor`에서 없으면 `WARN`이고, `/var/lib/inodefence` 밖이나 symlink로 설정돼 있으면
`FAIL`입니다(그 규칙은 바뀌지 않았습니다).

`doctor`는 Docker 점검 줄 바로 뒤, 마지막 `runtime directory` 줄 앞에 세 줄을 더 출력합니다. 모두 읽기만 하며 아무것도 바꾸거나 지우지 않습니다.

- **남은 컨테이너·볼륨:** InodeFence 소유 라벨(`org.inodefence.smoke-owner`·`org.inodefence.execution-owner`)이
  붙었거나 이름이 런처의 컨트롤러·볼륨 이름(`inodefence-local-controller`, `inodefence-decompress-controller`,
  `inodefence-oras-go-runtime` 등)인 것을 조회합니다. 있으면 `WARN`과 함께 확인 명령
  (`docker container inspect <이름>`)과, 내 것이고 쓰는 실행이 없을 때만 쓸 제거 명령을 보여 줍니다. 도구가
  직접 지우지는 않습니다. Docker가 답하지 않으면 `UNKNOWN`입니다(정리됐다고 보지 않습니다).
- **출력 폴더 디스크 여유:** 2 GiB 미만이면 `WARN`입니다(거부하지 않습니다).
- **Docker 메모리 여유:** 항상 `UNKNOWN`입니다. Windows + WSL2에서 Docker Desktop backend의 메모리는 Windows
  커밋 한도에 걸리는데, WSL 안에서는 그 한도를 볼 수 없습니다(2026-11-16 HOST2 정지 4: WSL 쪽 여유는 충분했지만
  Windows 쪽 가상 메모리 부족과 함께 backend가 사라졌습니다). 이 `UNKNOWN`은 종료 코드에 영향이 없습니다.

## 설정과 출력 위치

| 무엇 | 기본값 | 바꾸는 법 |
| --- | --- | --- |
| 출력 폴더 | `verify`: `~/inodefence-target-run`, `explore`: `~/inodefence-explore` | `--out <폴더>`(상대 경로는 **명령을 실행한 폴더** 기준), 또는 `INODEFENCE_OUTPUT_DIR=<기준 폴더>` → `<기준>/inodefence-target-run`, `<기준>/inodefence-explore` |
| 저장소 위치 | editable 설치면 자동 | `INODEFENCE_HOME=<클론 경로>` |

두 값은 환경 변수로 주거나, [`.env.example`](../.env.example)을 `~/.config/inodefence/config.env`로
복사해 적습니다(환경 변수가 파일보다 우선, 다른 파일은 `INODEFENCE_CONFIG`로 지정하며 그 파일이 없거나
디렉터리면 오류). 저장소 루트의 `.env`는 읽지 않습니다. 파일은 `KEY=VALUE` 줄로 읽기만 하고 셸로 실행하지
않습니다.

현재 적용된 값과 출처는 `inodefence doctor`가 보여 줍니다.

- `user config` 줄: 읽은 설정 파일 경로(없으면 "not present", 기본값 사용). 파일 오류는 몇 번째 줄인지와 함께
  `FAIL`이고, 이때 `doctor` 말고 다른 명령은 실행 전에 거부합니다(대상 명령은 종료 3).
- `repository` 줄: 고른 클론과 그 출처(`INODEFENCE_HOME from the environment`, `INODEFENCE_HOME from <설정 파일>`,
  또는 설치한 클론). 환경 변수가 설정 파일 값을 덮으면 덮인 값을 함께 적고, 설치한 클론과 다른 클론을 고르면
  대상 명령이 그 클론의 코드로 돈다고 적습니다. `INODEFENCE_HOME`이 클론이 아니면 그 값과 출처를 적어 `FAIL`,
  클론이지만 실행할 코드(`src/inodefence/drivers/`)가 없으면 대상 명령과 같은 거부 문구로 `FAIL`, 상대 경로면
  (실행한 폴더에 따라 바뀌므로) `WARN`입니다.
- `output folder base` 줄: 출력 기준 폴더와 출처, 그리고 `verify`·`explore`의 기본 `--out` 두 개. 기준 폴더가
  이미 있는 파일이면 `FAIL`입니다.
- `inodefence code running doctor / status / summary` 줄(`runtime directory` 줄 바로 앞): 지금 돌고 있는
  `inodefence` 패키지 폴더(`INFO`). `PYTHONPATH`가 설정돼 있고 패키지가 그 아래에서 읽혔으면, 설치본이 아니라
  그 경로의 코드가 돈다는 `WARN`입니다. 이 줄은 종료 코드에 영향이 없고, `PYTHONPATH`를 무시하거나 막지 않습니다.

설정 파일에서 다음은 짐작하지 않고 오류로 거부합니다(그대로 받으면 사용자가 뜻한 것과 다른 경로가 조용히 쓰임).

- 값 뒤 주석(`INODEFENCE_OUTPUT_DIR=/data/if # 메모`): 주석은 따로 한 줄에 쓰거나 값을 따옴표로 감쌉니다.
- 한쪽만 있는 따옴표(`INODEFENCE_OUTPUT_DIR='/data/if`).
- 상대 경로 `INODEFENCE_OUTPUT_DIR`(환경 변수도 같음): `doctor`는 `FAIL`, `verify`·`explore`는 `--out` 없이
  부르면 종료 3으로 거부합니다(실행한 폴더에 따라 출력 위치가 바뀌지 않도록). `--out`으로 직접 준 상대
  경로는 지금처럼 실행한 폴더 기준입니다. `~`로 시작하는 값은 홈 폴더로 풉니다.

빈 값(`INODEFENCE_OUTPUT_DIR=`)은 파일·환경 변수 모두 "설정 안 함"이고 다음 출처(파일, 기본값)가 쓰입니다. 공백이
든 경로는 따옴표 없이도, 따옴표로 감싸도 됩니다. UTF-8 BOM이 붙은 파일(Windows 메모장 저장)과 CRLF 줄 끝도 읽습니다.

`verify`·`explore`는 출력 폴더(`--out` 또는 기본값)를 쓸 수 없으면 `--dry-run`이어도 실행 전에 종료 3으로
거부합니다: 이미 있는 파일이거나, 그 위 폴더 중 하나가 파일이거나, 만들 위치에 쓰기 권한이 없을 때입니다.

- **출력은 저장소 밖이어야 합니다.** `--out`이나 기준 폴더가 저장소 안이면 실행 전에 거부합니다
  (위반 입력이 공개 저장소에 섞이지 않도록). 클라우드 동기화 폴더(Google Drive 등)도 피하세요.
  `doctor`와 `verify`·`explore`는 경로에 `Drive`(예: `~/Drive`)·Google Drive·OneDrive·Dropbox 등의 폴더 이름이 보이면
  경고하지만(실행은 막지 않음), 이름이 다른 동기화
  폴더는 알아채지 못합니다.
- **설정 파일로 실험 조건을 바꿀 수 없습니다.** 설정 파일은 위 두 키만 받고, 그 밖의 키(예: seed·budget,
  `INODEFENCE_RUNTIME_ROOT`)는 오류로 거부합니다. seed·arm·budget·실행 SHA·격리 정책은 명령 옵션이나
  동결된 사전등록 파일(`experiments/preregistration/`)에서만 오고, 실험 runtime 폴더
  `INODEFENCE_RUNTIME_ROOT`는 지금처럼 환경 변수로만 정합니다.

## 지원 환경과 확인 수준

- 이 절의 실측은 이전 커밋(RC #457, `a5499de`)의 측정이며, 현재 head에서는 대상 실행을 하지 않았습니다.
- **이전 커밋 `a5499de`에서 확인한 호스트:** Windows + WSL2(Ubuntu 24.04, x86_64) + Docker Desktop
  4.99.0 / Engine 29.9.3 호스트 한 대. **macOS는 이 후보에서 확인하지 않았습니다**(아래 #400 기록만 있음).
  그 밖의 Linux 호스트도 확인하지 않았습니다.
- **대상별 검증 수준 (이전 커밋 실측: 위 호스트, demo run, 2026-11-16 08:00~08:04 KST, 엔진 커밋 a5499de, seed 123,
  순차 실행).** "실행 성공"은 하너스가 실행을 끝내고 결과를 남긴 수, "유효 추출"은 추출기가 `success`로 끝난
  수입니다.

  | 대상·버전 | 모드 | 실행 성공 | 유효 추출 | 미판정 | 위반 | replay | 지원 수준 |
  | --- | --- | --- | --- | --- | --- | --- | --- |
  | node-tar 7.5.23 | verify | 5/5 | 0/5 (전부 declined) | 0 | 0 | — | 고정 입력 회귀 (exploratory 버전) |
  | node-tar 7.5.23 | explore 20 | 20/20 | 17/20 (rejected 3) | 0 | 0 | 지원, 실제 위반 E2E 미검증 | 탐색 |
  | python-tarfile 3.12.16 `data` | verify | 5/5 | 0/5 (전부 declined) | 0 | 0 | — | 고정 입력 회귀 |
  | python-tarfile 3.12.16 `data` | explore 20 | 20/20 | 12/20 (failed 5, rejected 3) | 0 | 0 | 미지원 | 탐색 |
  | decompress `@xhmikosr/decompress@11.1.4` | verify | 5/5 | 0/5 (전부 declined) | 0 | 0 | — | 고정 입력 회귀 |
  | decompress `@xhmikosr/decompress@11.1.4` | explore 20 | 20/20 | 11/20 (rejected 9) | 0 | 0 | 미지원 | 탐색 |
  | oras-go 2.6.2 | verify | 6/6 | 0/6 (전부 declined) | 0 | 0 | — | 고정 입력 회귀 |
  | oras-go 2.6.2 | explore 20 | 20/20 | **0/20** (전부 rejected, "추출 성공 0건" 경고) | 0 | 0 | 미지원 | **실험적 — 유의미한 보안 커버리지를 주장하지 않음**(공통 seed가 `d/` 접두 없이 생성돼 대부분 거부) |

  - python-tarfile의 failed 5건은 worker가 보고한 예외(IsADirectoryError 3, FileExistsError 1, KeyError 1)가 종료
    상태와 일치해 판정을 유지했습니다(D1 편차, 아래 판정 규칙).
  - **위반 0은 안전성 증명이 아닙니다.**
  - **고정 입력 회귀의 한계:** `verify`의 고정 입력은 모두 공격 형태이고 정상 입력 대조군이 없습니다. 네 대상 모두
    모든 입력을 거부(declined)했는데, 이것만으로는 모든 입력을 거부하는 고장 난 추출기와 구분할 수 없습니다.
    같은 대상의 탐색에서 나온 유효 추출 수로 보완해 읽으세요.
  - **replay:** 현재 node-tar만 지원하고, 나머지 세 대상은 `replay`가 미지원으로 보고합니다(종료 4). 실제 위반
    케이스에 대한 E2E 재실행은 검증하지 않았고(이 실측에서 위반이 없었음), 합성 사례에 대한 기능 테스트만 있습니다.
  - **macOS:** 이 후보에서는 확인하지 않았습니다.
  - RC 이전 커밋(61afb3f·c55b7ef)에서도 같은 조건의 engineering smoke를 돌렸고 판정은 같았습니다(위반 0).
- **이전 기록:** #400 브랜치의 `make target-run`(같은 드라이버)으로 macOS(arm64)와 WSL2에서 네 대상 고정 입력
  결과를 확인한 기록이 [CHANGELOG](../CHANGELOG.md)에 있습니다(2026-11-14, 이 후보에서 재실행 안 함).
- 이 문서의 실행 예는 모두 `demo run` 수준이며 사전등록 실험이나 자격 검증 결과가 아닙니다.

## 탐색 돌리기

```bash
# node-tar의 최신 버전을 준비해 탐색. --out은 반드시 저장소 밖(위반 입력이 섞일 수 있어
# 공개 저장소 안이면 실행 전 거부됩니다). --dry-run이면 계획만 출력하고 아무것도 실행하지 않습니다.
inodefence explore --target node-tar --version latest --budget 400 --seed 7 \
  --out ~/inodefence-explore --auto-prepare

# decompress는 버전 칸에 패키지까지 씁니다: <패키지>@<X.Y.Z> (11.1.4만 주면 --dry-run에서도 종료 3으로 거부)
inodefence explore --target decompress --version @xhmikosr/decompress@11.1.4 --budget 20 \
  --out ~/inodefence-explore --auto-prepare
```

`--version`은 `latest`나 정확한 버전, `--budget`은 실행 수(seed 케이스 수 이상), `--seed`는 난수
seed입니다. 탐색 정책·sentinel 구성은 등록 실험 설정을 기본값으로 쓰며, 끝나면 공통 형식
`result.json`(`inodefence-target-result-v1`, mode=campaign)과 한 장짜리 `summary.md`를 씁니다.
`--profile fast`(기본 `strict`)는 실행마다 하는 공용 이미지 재빌드만 건너뛰는 선택 옵션이며, 조건·기록·측정값은
[한계와 주의](#한계와-주의)의 "실행 프로필"에 있습니다.

node-tar 탐색(`--version 7.5.23 --seed 123 --budget 20`, engineering smoke 2026-11-16)에서 실제로 생긴 구조:

```text
<--out>/target-explore/
  7.5.23-123-20/live/                 실행 중 갱신: progress.json, fetch.json, violations/run-NNNNNN/
  7.5.23-123-20-result/               끝난 뒤: result.json, summary.md, inputs/
  inodefence-effect-explore-7.5.23-123-20.json (.steps.jsonl, .calls.jsonl)   엔진 원시 기록
```

(`<버전>-<seed>-<budget>` 이름은 node-tar에서 관찰한 것입니다. 다른 대상의 폴더 이름은 아직 실측으로 대조하지 않았습니다.)

## 실행 중 터미널 진행 표시

`inodefence explore`는 기본으로 진행 줄을 **stderr**에 출력합니다. 숫자는 `inodefence status`와 같은 파일
(`live/progress.json`, 위반 케이스 폴더, 끝난 뒤 `result.json`)에서 읽으므로 둘은 같은 값을 보여 줍니다. 컨테이너
안에는 아무것도 더하지 않고, 호스트에서 작은 파일 하나를 주기적으로 읽을 뿐입니다. `progress.json`·`result.json`·
원시 기록의 형식은 그대로입니다.

```text
[explore] node-tar 7.5.23(requested) profile=strict seed=321 budget=40; results: <--out>; launcher output: <--out>/runtime/explore-launcher-<UTC>-<pid>.log (--verbose shows it here)
[explore] running step=effect-demo-explore runs=29/40 | success=15 rejected=14 failed=0 timed_out=0 un-judged=0 | violations=0 C0=0 C1=0 C2=0 | 0.476 runs/s eta~23s | elapsed=76s
[explore] completed verdict=PASS runs=40/40 | node-tar 7.5.23 profile=strict seed=321 | success=24 rejected=16 failed=0 timed_out=0 un-judged=0 | violations=0 C0=0 C1=0 C2=0 | 0.486 runs/s | elapsed=94s | out=<--out>
```

(2026-11-17 node-tar 7.5.23 seed 321 budget 40 engineering smoke(demo run)를 폭 200 터미널에서 돌린 실제 출력이며 경로만
`<--out>`으로 줄였습니다. 가운데 줄은 제자리 갱신되는 줄의 한 시점입니다. 성능 측정이 아닙니다.)

| 옵션 | 진행 줄 | 런처 원시 출력(이미지 빌드·컨트롤러 단계) |
| --- | --- | --- |
| (기본) | 출력 | `<--out>/runtime/explore-launcher-<UTC>-<pid>.log`에 저장(경로를 첫 줄에 출력) |
| `--quiet` | 없음 | 같은 로그 파일에 저장 |
| `--verbose` | 없음 | 터미널에 그대로(이 기능 이전과 같은 출력) |

세 경우 모두 종료 코드, stdout의 `TARGET-EXPLORE …` 결과 줄과 `result: …` 줄, stderr의 오류·진단 줄은 같습니다.
`--quiet`와 `--verbose`는 함께 줄 수 없습니다(종료 3). 드라이버를 직접 부르거나(`python -m
inodefence.drivers.run_target_explore`) 옛 `scripts/` 경로로 부르면 기본은 `--verbose`와 같은 출력(`--output stream`)입니다.

- **표시 방식.** stderr가 터미널이고 `TERM`이 `dumb`이 아니면 한 줄을 `\r`로 제자리 갱신합니다(1초마다, 터미널
  폭에 맞춰 덜 중요한 칸부터 생략). 그 밖(파이프·파일·CI)에는 줄 단위로 출력합니다: 단계가 바뀔 때 즉시, 숫자나 런처 단계가
  바뀌었으면 마지막 줄에서 30초가 지난 뒤, 아무 변화가 없어도 300초마다 한 줄. 색과 이스케이프 문자는 쓰지 않으므로
  `NO_COLOR`와 무관하게 같은 출력입니다.
- **단계.** `prepare`(이미지 확인·준비) → `running`(런처 실행 중; 탐색 루프 전의 컨트롤러 준비도 포함하며
  `step=`이 런처가 출력한 현재 단계 이름을 보여 줌) → `cleanup`(루프가 끝났거나 보고서가 호스트에 도착, 결과 기록
  중) → `completed` 또는 `aborted`.
- **모르는 값은 `?`입니다(0이 아님).** live 폴더는 현재 node-tar만 씁니다. python-tarfile·decompress·oras-go는
  실행 중 모든 수가 `?`이고(`step=`과 경과 시간만 갱신), 마지막 줄만 `result.json`에서 읽습니다. 그 줄의 처리량은
  `result.json`에 없으므로 `? runs/s`입니다.
- **C0/C1/C2.** `progress.json`에는 계약별 수가 없어서 호스트에 있는 위반 케이스 폴더(`case.json`)를 셉니다. 위반
  실행 전부가 폴더로 있으면 정확한 수이고, fingerprint당 저장 상한이나 아직 가져오지 않은 케이스가 있으면 하한
  (`C1>=2`)으로 표시합니다. 위반은 oracle이 표시한 후보이며 확인된 취약점이 아닙니다.
- **처리량과 ETA.** 처리량은 스냅샷의 `runs_per_second`(`status`가 보여 주는 값)입니다. ETA는 루프가 도는 동안,
  budget을 알고, 10회 이상 실행했고, 서로 다른 스냅샷 두 개의 처리량 차이가 25% 이내일 때만
  `(budget - 실행 수) / 처리량`으로 표시하고, 그 밖에는 표시하지 않습니다.
- **숫자의 시점.** 스냅샷은 25회마다 또는 30초마다(위반 직후 즉시) 쓰이고 호스트는 15초마다 가져오므로, 실행 중
  숫자는 최대 수십 초 전 것입니다(`snapshot=21s ago`). 같은 폴더에 남은 이전 실행의 스냅샷은 무시합니다.
- **멈췄을 때.** `[explore] aborted … | cause: <오류 한 줄> [stage=… category=…]` 한 줄(기존 실행 진단의 단계·분류를
  그대로 인용)과 로그 파일 경로, 로그의 마지막 15줄을 stderr에 출력합니다.

## 도중 확인

긴 탐색은 끝나기를 기다리지 않고 실행 중에 봅니다. `--out`에 준 폴더, 그 아래 `target-explore`, 실행 폴더
하나(`…/7.5.23-123-20`), 결과 폴더(`…-result`) 중 아무것이나 줄 수 있습니다.

```bash
inodefence status ~/inodefence-explore   # 진행 스냅샷 + 위반 케이스 목록 (+ 끝났으면 판정 한 줄)
```

끝난 실행에서 `host pull: … failed`가 보일 수 있습니다. 컨트롤러가 뜨기 전이나 지워진 뒤의 복사 실패로,
호스트 쪽 live 사본에 관한 것이고 판정 오류가 아닙니다(`status`가 그 설명을 함께 출력합니다).

탐색은 실행 중에 출력 폴더의 `…/<run>/live/`에 두 가지를 씁니다.

- `progress.json` — 주기적으로(실행 N회마다·일정 시간마다·위반 직후) 갱신되는 한 시점 스냅샷:
  실행 수, 초당 실행, **종료 상태별 수(success·rejected·failed·timed_out)**, 미판정 수와 비율,
  위반 step 수와 고유 fingerprint 수, 쓰기 오류. `status`는 갱신이 오래 멈추면 `STALE`로 경고합니다.
- `violations/run-NNNNNN/` — 위반이 난 케이스를 **발생 즉시** 기록합니다(끝을 기다리지 않음).
  같은 fingerprint의 반복은 개수만 세고 파일은 fingerprint당 처음 몇 개만 남깁니다. 탐색이
  중간에 죽어도 그때까지 쓴 파일은 남습니다.

컨트롤러 컨테이너 안에서 돈 탐색은 호스트가 주기적으로 그 폴더를 가져오므로, 실행 중에도
호스트의 출력 폴더에서 진행과 위반 케이스를 볼 수 있습니다. 가져오기 실패는 탐색을 멈추지 않고
`fetch.json`에 남습니다.

## 위반 케이스 폴더 읽기

각 `violations/run-NNNNNN/`에는 `input.tar`(그 실행에 쓴 정확한 입력)와 `case.json`이 있습니다.
`case.json`에는 케이스·seed·부모·적용된 변이, C0/C1/C2 판정, 종료 상태와 관찰 완결 여부,
fingerprint, 입력의 SHA-256, 그리고 **그 한 건을 같은 이미지에서 다시 돌리는 명령**이 들어 있습니다.

## 종료 상태와 판정은 별개입니다

추출기가 어떻게 끝났는가(종료 상태: success·rejected·failed·timed_out)와 오라클이 무엇을
보았는가(판정: C0/C1/C2)는 서로 다른 축입니다. 오라클은 실행 전후 파일시스템 스냅샷을 비교하므로,
**위반이 보이면 종료 상태와 상관없이 그 실행은 위반으로 판정**되고 FAIL로 잡힙니다(입력도 보존).

위반이 보이지 않은 실행을 "깨끗한 음성"으로 셀지는 탐색(`explore`)에서 다음 규칙(사용자 결정 D1,
2026-11-16)을 따릅니다. 이렇게 세지 않는 실행은 **미판정**입니다.

| 대상 | 위반 없음이 판정(깨끗한 음성)으로 남는 실행 | 미판정이 되는 실행 |
| --- | --- | --- |
| node-tar, decompress | `rejected`; trace가 온전한 `success` | `failed`, `timed_out`; trace가 온전하지 않은 `success` (decompress는 worker 기록이 없는 실행도) |
| python-tarfile | `rejected`; worker 보고가 종료 상태와 일치하는 `failed`(tarfile이 예외로 거부한 것, D1과의 의도된 편차); trace가 온전한 `success`; 빈 아카이브 | `timed_out`; worker 보고가 없거나 종료 상태와 어긋나는 실행; trace가 온전하지 않은 `success` |
| oras-go | `success`, `rejected` | 그 밖의 모든 실행 |

캠페인 판정: 위반이 하나라도 있으면 FAIL. 판정된 실행이 하나도 없거나 미판정 비율이 상한
(`--max-unjudged-ratio`, 기본 0.2)을 넘으면 ERROR. oras-go는 더 엄격해서 미판정이 하나라도 있으면
ERROR입니다(상한 옵션으로 완화되지 않음). 그 밖에는 PASS입니다. 그래서 거절이 많은 것만으로는 ERROR가
되지 않지만, 실패·시간 초과가 많으면 ERROR가 될 수 있습니다. 이 규칙은 탐색 결과 기록에만 적용되며
탐색 루프와 피드백, 등록 실험 경로는 바뀌지 않습니다.

**추출 성공 0건 경고.** 탐색의 모든 실행이 `success` 없이 끝나면(예: 전부 `rejected`) 판정·종료 코드는 그대로 두고
`summary.md`, 탐색 출력 줄(`TARGET-EXPLORE WARNING`), `inodefence status`에 "추출 성공 0건 … 위반 없음의 근거가
제한적" 경고를 붙입니다. 이때의 PASS는 아카이브를 실제로 풀어 본 실행이 없다는 뜻이므로 약한 근거입니다.

**깨끗하게 끝나지 않은 실행에서 난 위반은 "재현 확인 필요"로 구분해 표시합니다.** 성공으로 끝나지
않았거나 관찰이 완결되지 않은 상태에서 난 위반은 그대로 위반이지만, 같은 입력을 다시 돌려 같은
위반이 나는지 먼저 확인하는 것이 맞습니다.

## 위반 후보 재실행(재현 확인)

위반은 **위반 후보**이지 확정된 취약점이 아닙니다. 처리 규칙은 "같은 입력을 같은 조건에서 다시
돌려 재현되는지 본다"입니다.

```bash
# 위반 케이스 폴더 하나를 그 case.json이 가리키는 정확한 이미지에서 3회(기본) 다시 돌립니다.
inodefence replay ~/inodefence-explore/target-explore/<실행>/live/violations/run-NNNNNN --rounds 3   # <실행> 예: 7.5.23-123-20
```

재실행은 탐색과 같은 격리로 돌고, 회차별 판정과 **같은 계약을 다시 위반한 비율**·**fingerprint가
일치한 비율**을 케이스 폴더 **옆** `run-NNNNNN.replay-<UTC>/replay.json`에 씁니다(원본 폴더는
건드리지 않습니다). `case.json`에 기록된 이미지 id가 이 호스트에 없으면 **다시 준비하거나 다른
이미지로 바꾸지 않고 멈춥니다**(다른 이미지로 돌린 것을 재현이라고 적지 않기 위해서). 재실행에는
탐색의 실행 설정이 `case.json`에 있어야 하며, 없는 옛 케이스는 거부합니다.

- **이미지 확인은 세 상태입니다.** 있음, 없음(Docker가 "No such image"라고 답함), 판정 불가(시간 초과, daemon
  없음)입니다. 판정 불가면 "이미지가 없다"고 하지 않고 "Docker가 답하지 않았다"고, `docker info`로 멈춘 daemon인지
  꺼진 daemon인지를 덧붙여 출력하고 종료 3으로 멈춥니다(준비하지 않습니다).
- **증거 보존:** 재실행 컨트롤러가 돌려준 보고서와 회차 기록(`*.steps.jsonl`)을 `run-NNNNNN.replay-<UTC>/evidence/`에
  함께 남깁니다. 끝까지 못 돈 재실행은 `replay.json`의 `replay.diagnosis`에 멈춘 단계(`controller-setup`·`loop`·
  `cleanup`)와 범주(공유 abort 분류기 범주, 모르면 `UNKNOWN`)를 적고, 같은 내용을 `REPLAY DIAGNOSIS:` 한 줄로
  출력합니다. 인프라 정지는 "재현 안 됨"이 아닙니다(비율은 판정된 회차로만 셉니다).
- **실행한 클론:** `replay.repository`에 `checkout_id`(클론 경로의 SHA-256 앞 12자리)와 수정된 추적 파일 수를
  적습니다. 경로 자체는 파일에 쓰지 않습니다. `checkout_id`는 같은 클론인지 구분하는 용도이지 비밀 보호 수단이
  아닙니다(짐작 가능한 경로는 해시를 대조해 알아낼 수 있습니다).
- **실행 세션:** 재실행도 탐색과 같은 STRICT 실행 세션을 거칩니다. 같은 실행 이름의 컨트롤러·볼륨
  (`inodefence-local-controller-replay-…`)이 이미 있으면 런처를 돌리지 않고 `REPLAY STOPPED: run-resources-exist: …`
  한 줄과 종료 3으로 멈추며, 재실행 폴더를 만들지 않습니다. 실행이 끝나면 그 이름이 남았는지 조회해
  `RUNTIME DIAGNOSTIC WARN leftover-resources`로 알립니다(지우지 않음). 진단 줄은 `REPLAY DIAGNOSIS` 하나뿐입니다.
  세션 기록(프로필, 실행별 종료 코드·분류·진단 결과, 경로 없음)은 원본 케이스 폴더가 아니라 새 재실행 폴더의
  `evidence/runtime-record.json`에 같은 발행(한 번의 rename)으로 들어갑니다. 발행에 실패하면 이 기록은
  stderr에 `REPLAY RUNTIME RECORD (not published; publish failed): …` 한 줄로 나옵니다.
- 같은 케이스를 같은 초에 두 번 재실행하면 두 번째 폴더는 `….replay-<UTC>-2`가 됩니다(덮어쓰지 않음).
  기록을 폴더에 쓰지 못하면 기록 전체를 표준 출력에 내고 종료 1로 끝냅니다(이미 돈 회차를 잃지 않기 위해).

## 결과 요약과 재현 정보 남기기

별도의 "내보내기" 명령은 없습니다. 공유·보고에 쓰는 것은 출력 폴더의 파일과 `summary`입니다.

```bash
# result.json 하나를 한 장짜리 Markdown 요약으로(입력 TAR의 SHA-256을 다시 대조; 생략은 --no-verify-inputs)
inodefence summary ~/inodefence-explore/target-explore/<실행>-result/result.json -o ~/report.md
```

- **재현 정보:** 위반 케이스마다 `case.json`(입력 SHA-256, 이미지 id, 다시 돌리는 명령)과 `input.tar`,
  재실행 결과는 그 옆 `run-NNNNNN.replay-<UTC>/replay.json`에 있습니다.
- 보고서나 케이스 폴더를 밖으로 보낼 때는 위반 입력이 들어 있다는 점을 기억하세요(아래 책임 있는 공개).

## 종료 코드

| 코드 | `verify`·`explore` | `replay` | `targets` | `doctor` | `status`·`summary` |
| --- | --- | --- | --- | --- | --- |
| 0 | PASS | 재실행 완료 | 정상 | FAIL 없음(`UNKNOWN`은 있을 수 있음) | 정상 |
| 1 | FAIL(위반 판정) | 재실행 미완료(끝난 회차는 남음) | — | FAIL 하나 이상 | — |
| 2 | ERROR 판정. `explore`는 컨트롤러가 시작된 뒤의 중단(런처 비정상 종료, 루프 abort, 루프 보고서 없음)도 2이며 결과를 발행하지 않음(네 대상 공통) | 같은 입력·조건으로 재실행 불가 | 사용법 오류 | 사용법 오류 | 읽기·쓰기 실패 / 사용법 오류 |
| 3 | 실행 전 거부 — 판정 없음: 사용법 오류(없는 옵션 값, `--budget 0` 등), 저장소 안 `--out`, 쓸 수 없는 `--out`(파일이거나 권한 없음), 상대 경로 `INODEFENCE_OUTPUT_DIR`, `--auto-prepare` 없음, 설정 파일 오류, 이미지·준비 문제, Docker가 이미지 질문에 답하지 않음(준비하지 않음), 같은 `--out`에 이 실행의 결과가 이미 있음(덮어쓰지 않음) 등 | 사용법 오류(`--rounds 0` 등), 이미지가 이 호스트에 없음, Docker가 이미지 질문에 답하지 않음, 같은 실행 이름의 컨트롤러·볼륨이 이미 있음, 저장소 안 폴더, 저장소를 못 찾음, 설정 파일 오류 | 저장소를 못 찾음, 설정 파일 오류 | — | — |
| 4 | — | 이 대상은 재실행 미지원 | — | — | — |

`verify`·`explore`·`replay`는 종료 코드가 결과를 싣기 때문에 사용법 오류를 2로 내지 않고, 아무것도 실행하지
않았다는 뜻의 3으로 냅니다(대상 드라이버와 같은 규칙). 판정을 싣지 않는 명령의 사용법 오류와, 하위
명령 없이 `inodefence`만 잘못 부른 경우는 argparse 관례대로 2입니다. `make`를 거쳐 부르면 `make` 자체는 실패 시
2로 끝나므로, 판정 코드는 `inodefence`를 직접 부를 때의 값을 보세요.

`inodefence verify`와 `make target-run`은 같은 드라이버(`inodefence.drivers.run_target`)를 부릅니다(개발용 경로, CHANGELOG @ 2b06730에서 옮김).

```bash
make target-run TARGET=node-tar TARGET_VERSIONS="7.5.2 7.5.3" AUTO_PREPARE=1 PYTHON=python3.12   # WSL2: PYTHON=python3
```

종료 코드: 0 PASS, 1 FAIL, 2 ERROR(셀 중 가장 나쁜 판정), 3 일부 또는 모든 셀이 판정되지 않음(거부된 입력, 이미 있는 결과,
설정·준비·이미지 문제).

`make`는 실패하면 항상 2로 끝나므로, 판정 코드는 `make: *** … Error N`의 N으로 읽습니다.

## 한계와 주의

- **oras-go 탐색의 "위반 없음"은 근거가 제한적입니다.** oras-go 탐색은 공통 seed가 oras-go 디렉터리
  아티팩트 제목 접두(`d/`) 없이 만들어져 대부분의 실행이 oras-go에서 거부됩니다(위 WSL2 호스트, seed 123·budget 20에서
  20/20 거부, 2026-11-15 맥북 실행 budget 60에서 성공 6건·9건). 엔트리를 `d/` 아래로 옮기는 변경은 탐색 대상의
  의미를 바꾸므로 사용자 결정 전까지 하지 않습니다.
- **알려진 표시 문제:** `live/`와 결과가 함께 있는 폴더에서 `inodefence status`는 "추출 성공 0건" 경고를 진행 블록과
  결과 줄에 두 번 출력합니다(판정·종료 코드에는 영향 없음).
- **스냅샷 판정은 지속 상태만 봅니다.** 오라클은 실행 전후의 파일시스템 상태를 비교하므로,
  실행 도중에만 존재한 일시적 operation이나 sandbox 밖의 상태는 증명하지 못합니다. 위반은
  재현과 원인 분석이 따로 필요한 후보입니다.
- **이어 하기(resume)는 아직 없습니다.** 멈춘 탐색을 중간부터 이어서 돌릴 수는 없습니다.
  다만 그때까지 캡처된 위반 케이스는 남습니다. 자동 재시도와 멈춘 실행의 강제 종료도 없습니다. `status`는
  오래 진척이 없으면 몇 초째인지와 함께 `STALE` 경고만 출력하고, 실행 중에는 처리량(runs/min)과 남은 예산의
  예상 시간을 보여 줍니다(관찰만).
- **실행 프로필(`explore --profile`):** 기본은 STRICT(검증된 실행 그대로)이고, `--profile fast`는 사용자가 직접
  골라야만 켜집니다. FAST가 바꾸는 것은 한 가지입니다. 런처가 실행마다 다시 하는 공용 이미지 두 개(컨트롤러·helper)의
  빌드를, 그 이미지가 이 checkout의 빌드 입력(Dockerfile 두 개와 helper 한 파일의 SHA-256)으로 런처 자신이 빌드한
  것임이 확인된 경우에만 건너뜁니다(`SKIP_BUILD=1`). 확인 기록은 사용자 캐시(`$XDG_CACHE_HOME/inodefence/`,
  기본 `~/.cache`)에 Docker context별로 남고 24시간 동안만 유효하며, 입력·이미지 ID가 달라지면 무효입니다. 확인이
  안 되면 런처의 빌드 전용 실행으로 먼저 빌드해 확인하고, 그런 실행이 없는 python-tarfile 런처는 STRICT와 똑같이
  실행하면서 그 사실을 `TARGET-EXPLORE RUNTIME: profile=fast reuse_shared_images=not-applied (…)`로 알리고
  기록합니다(조용히 STRICT로 돌지 않음). 빌드가 실패하면 아무것도 실행하지 않고 종료 3입니다. 입력·판정(C0·C1·C2)·격리·
  결과 형식·종료 코드는 STRICT와 같고, 적용 내역은 실행 기록과 결과 폴더의 `runtime-record.json`(FAST일 때만)에
  남습니다. `replay`는 항상 STRICT입니다.
  **얻는 것은 작습니다.** WSL2 호스트 한 대의 engineering smoke(demo run, node-tar 7.5.23, seed 123, budget 20, 같은
  코드로 번갈아 5회씩, 2026-11-17)에서 FAST는 컨트롤러 준비 전 구간을 실행당 평균 1.5 s(짝지은 차이 1.0~2.0 s) 줄였고(STRICT 평균 2.78 s[2.25~3.43],
  FAST 1.33 s[1.16~1.52]), 케이스당 시간은 그대로였습니다(STRICT 1.96 s, FAST 1.92 s). 전체 실행 시간은 호스트 부하에 따른
  편차(STRICT 42~61 s, FAST 42~56 s)가 이 차이보다 커서 구분되지 않았습니다. 케이스당 비용(약 2 s, docker CLI 호출 약 23회)은 보호
  영역인 격리 실행 경로 안에 있어 이 프로필이 건드리지 않습니다. REPLAY는 프로필이 아니라 위
  재실행 절차이며, node-tar만 지원하고 탐색과 같은 STRICT 실행 세션으로 돕니다.
- **인프라 중단의 표시:** `explore`가 깨끗하게 끝나지 않으면(런처 종료 코드가 0이 아니거나 중단됨) 종료 코드와
  판정은 그대로 두고 stderr에 한 줄을 더 냅니다.
  `TARGET-EXPLORE DIAGNOSIS: stage=<controller-setup|loop|cleanup|UNKNOWN> category=<범주> result=<written|not-written> evidence=<남은 파일>; <설명>`.
  (런처 실행 전의 Docker 무응답·이미지 판정 불가는 이 줄이 아니라 `TARGET-EXPLORE SETUP:` 사유로 나옵니다.)
  범주는 컨트롤러 보고서의 `aborted.category`(공유 abort 분류기 값, 예: `cleanup_inspect`), 없으면 같은 분류기로
  분류한 사유, Docker가 답하지 않으면 `daemon-timeout`·`daemon-unreachable`, 그래도 모르면 `UNKNOWN`입니다. 루프
  보고서는 완주했는데 런처가 실패한 경우는 `stage=cleanup`이며 정리 상태 불명으로 보고 성공으로 치지 않습니다. 실행
  기록(프로필, 실행마다 종료 코드·분류·진단 결과, 경로 없음)은 `<--out>/runtime/<run_id>-<UTC>.json`에 남습니다
  (덮어쓰지 않고, 이름이 겹치면 `.1`, `.2`). 같은 실행의 컨트롤러·볼륨 이름이 이미 있으면 런처가 이미지를 빌드하기
  전에 `TARGET-EXPLORE SETUP: run-resources-exist: …`, 종료 3으로 멈춥니다(런처가 원래 종료 1로 멈추던 조건을
  앞당긴 것이며, 아무것도 지우지 않습니다). 진단은 런처의 종료 코드와 남은 파일만 보고 판단합니다. 런처의 터미널 출력은 캡처하거나
  해석하지 않으므로, 출력에만 나온 원인(예: node-tar 런처의 `INODEFENCE_CLEANUP_UNKNOWN`)은 범주 `UNKNOWN`으로
  남습니다. 종료 코드는 네 대상이 같습니다: 컨트롤러가 시작된 뒤의 중단(런처 비정상 종료, 루프 abort,
  루프 보고서 없음)은 `TARGET-EXPLORE ERROR`, 종료 2이고 결과를 발행하지 않으며(루프 보고서가 완주했어도
  런처가 실패하면 발행하지 않음), 실행 전 거부만 종료 3입니다. 런처가 0으로 끝났는데 루프 보고서가 없으면
  `stage=UNKNOWN`(어디서 멈췄는지 파일로는 알 수 없음)으로 진단하고 역시 종료 2입니다. python-tarfile에서 종료 3으로
  남은 경우는 둘입니다: 루프 보고서에 단계가 하나도 없음, 보고서가 다른 runtime·extraction filter의 것. 이전
  python-tarfile은 루프 abort와 보고서 없음을 `SETUP` 3으로, 완주 보고서 + 런처 실패를 PASS로 보고했습니다.
- **decompress·oras-go·python-tarfile 런처의 정리:** 이 세 셸 런처는 컨트롤러·볼륨 제거 실패를 종료 코드에
  반영하지 않고, 소유 라벨도 붙이지 않으며, docker 호출에 시간 제한이 없습니다. 그래서 정리 상태가 불명확해도
  실행이 성공으로 끝날 수 있습니다. 제품 계층은 실행이 끝날 때마다 그 실행의 컨트롤러·볼륨 이름이 아직 있는지
  조회해 `RUNTIME DIAGNOSTIC WARN leftover-resources`로 알리고(`inodefence doctor`도 같은 이름으로 조회),
  거기까지만 합니다. 지우지 않으며, 런처 수정은 격리 인접 변경이라 방향만 승인됐고 실행은 보류 중입니다(2026-11-16 결정).
- **미공개로 보이는 문제를 찾으면 공개 저장소에 올리기 전에 해당 추출기의 유지보수자에게 먼저
  알립니다**(책임 있는 공개). 위반 입력과 결과는 저장소 밖 출력 폴더에만 두고, 위반 입력 자체를
  커밋하지 않습니다.

> 공개 권고문의 영향 범위 안에 있는 특정 버전에서 나온
> 탐색 수치(위반 수·종료 상태 분포 등)는 이 문서에 적지 않습니다.

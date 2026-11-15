# Changelog

이 파일은 InodeFence의 릴리스별 변경을 적는다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를,
버전은 [Semantic Versioning](https://semver.org/lang/ko/)의 0.x 규칙(0.x에서는 하위 호환을 약속하지 않음)을 따른다.

## [0.2.0] — 미발행

첫 번째로 태그를 다는 릴리스다. `pyproject.toml`은 2026-10-03부터 `0.1.0`이었지만 그 번호로 태그나 릴리스를 낸 적이
없고, 그동안 개발 중인 모든 상태가 `0.1.0`으로 설치됐다. 같은 번호가 서로 다른 코드를 가리키지 않도록 첫 태그는
`0.2.0`으로 한다.

### 설치와 `inodefence` 명령

클론에서 `pip install -e .`로 설치하면 `inodefence` 명령이 생긴다(README "설치"). 하위 명령: `targets`(대상과
지원 기능 표), `doctor`(환경 점검), `verify`(고정 입력 회귀 검사, 아래 `make target-run`과 같은 드라이버),
`explore`·`status`·`replay`(탐색·도중 확인·재실행, 아래 "후속 검증"), `summary`(결과 한 장 요약).

- `--version`으로 패키지 버전을 출력한다.
- 출력 폴더: `--out`의 상대 경로는 명령을 실행한 폴더 기준으로 풀고, 저장소 안이면 `verify`·`explore` 모두 실행 전
  거부한다(`--dry-run` 포함). 기본값은 `~/inodefence-target-run`·`~/inodefence-explore`, 사용자 설정
  `INODEFENCE_OUTPUT_DIR`로 기준 폴더를 바꾼다.
- 사용자 설정(`~/.config/inodefence/config.env`, 예시 `.env.example`)은 `INODEFENCE_HOME`·`INODEFENCE_OUTPUT_DIR`만
  받고 다른 키(seed·budget·`INODEFENCE_RUNTIME_ROOT` 등)는 오류로 거부한다. `INODEFENCE_CONFIG`로 지정한 파일이
  없으면 오류다. 실험 조건과 runtime 폴더는 설정 파일로 바뀌지 않는다.
- `doctor`는 Python, 사용자 설정, 저장소, 출력 폴더, Docker CLI와 daemon 접근(`docker info`), 로컬 `inodefence-*`
  이미지(있으면 `OK`로 나열, 없으면 `INFO`), runtime 폴더(없으면 `WARN`, `/var/lib/inodefence` 밖·symlink면 `FAIL`)를
  출력한다. 어느 이미지가 어느 대상·버전용으로 준비됐는지는 판단하지 않고 `verify --dry-run`을 안내한다.
- `explore`는 `--auto-prepare` 없이 실제 실행을 요청하면 아무것도 실행하지 않고 이유를 출력한다(종료 코드 3, 드라이버의
  "판정 없음"과 같음). 저장소 안 `--out`·설정 파일 오류, 그리고 `verify`·`explore`·`replay`의 사용법 오류(예:
  `--budget -5`)도 3이다 — 이 명령들에서 2는 결과(ERROR 판정, 재실행 불가)에만 쓴다. 드라이버의 오류 메시지는
  `inodefence verify` 같은 명령 이름으로 나오고, 이미지 준비 안내도 `AUTO_PREPARE=1` 대신 `--auto-prepare`로 나온다.
- `--budget`·`--rounds`는 1 이상만 받는다(대상별 최소 예산 — 탐색 루프의 seed 수 이상 — 은 드라이버가 `--dry-run`에서도 검사해 3으로 거부한다).
  `status`는 `--out` 폴더 자체도 받고, 읽을 수 없는 `result.json`이 있으면 2로 끝나며, 끝난 실행의 host pull 실패에는
  판정 오류가 아니라는 설명을 붙인다. `summary -o`는 쓸 수 없는 경로면 traceback 대신 오류 메시지와 2로 끝난다.
- `INODEFENCE_HOME`으로 클론을 가리키면 대상 실행 코드는 그 클론에서 돌고, 결과의 엔진 커밋은 그 클론의 HEAD다.

**이 RC에서 실제로 확인한 것(2026-11-16, Windows + WSL2 x86_64, Docker Engine 29.9.3).** 깨끗한 venv에
`pip install .`과 `pip install -e .`을 각각 하고 저장소 밖 폴더에서 `--version`·`doctor`·`targets`·`status`·`summary`,
`explore`/`verify --dry-run`, 저장소 안 `--out` 거부, 설정 파일의 `INODEFENCE_HOME`·금지 키 거부를 실행했다. 이미지가
0개이던 때 `doctor`는 daemon 접근 `OK`, runtime 폴더 없음 `WARN`으로 그 호스트 상태를 그대로 보였다. 이 확인에서
W2가 Docker로 이미지를 준비하거나 대상을 실행하지는 않았다.

**HOST4 engineering 검증(demo run, 2026-11-16).** WSL2 Ubuntu 24.04, Docker Desktop 4.99.0 / Engine 29.9.3, seed 123,
순차 실행. 모두 **D1 판정 규칙(아래) 반영 전 커밋**에서 돌렸다.

| 대상·버전 | 엔진 | `verify` (고정 입력) | `explore` | 탐색 종료 상태 |
| --- | --- | --- | --- | --- |
| oras-go 2.6.2 | c55b7ef | PASS, 위반 0/6, 오류 0 | 20회 PASS, 위반 0, 미판정 0 | rejected 20, success 0 |
| python-tarfile 3.12.16 `data` | c55b7ef | PASS, 위반 0/5, 오류 0 | 20회 PASS, 위반 0, 미판정 0 | success 12, failed 5, rejected 3 |
| decompress `@xhmikosr/decompress@11.1.4` | c55b7ef | PASS, 위반 0/5, 오류 0 | 20회 PASS, 위반 0, 미판정 0 | success 11, rejected 9 |
| node-tar 7.5.23 | 61afb3f | 이 후보에서 실행 안 함 | 20회·60회 PASS, 위반 0, 미판정 0 | (20회) success 17, rejected 3 |

실행 후 컨테이너·볼륨 잔여 0. 증거는 HOST4 로컬에 sha256 목록과 함께 보관(저장소 밖). **위반 0은 안전성 증명이
아니다.** oras-go는 추출 성공 0건이라 근거가 특히 약하다(알려진 한계). 위반 케이스가 없어 **`replay`의 실제 위반
재실행(E2E)은 검증하지 않았다.** **macOS는 이 후보에서 확인하지 않았다.** node-tar 산출물로 `inodefence status`·
`summary`가 동작하는 것을 확인했고, README의 출력 폴더 구조는 그 산출물에 맞췄다.

### 탐색 결과의 판정 규칙(D1, 사용자 결정 2026-11-16)

탐색(`explore`) 결과 기록에서, 위반이 보인 실행은 종료 상태와 상관없이 위반으로 판정한다. 위반이 보이지 않은 실행은
다음일 때 **미판정**이다(깨끗한 음성으로 세지 않음).

- node-tar·decompress: `failed`, `timed_out`, trace가 온전하지 않은 `success`(decompress는 worker 기록이 없는 실행도).
  `rejected`는 판정 유지.
- python-tarfile: `timed_out`, worker 보고가 없거나 종료 상태와 어긋나는 실행, trace가 온전하지 않은 `success`.
  **편차:** worker 보고가 종료 상태와 일치하는 `failed`(tarfile이 예외로 거부)는 판정 유지 — 문자 그대로의 D1이면
  `data` 필터의 정상 거부가 미판정 상한(0.2)을 넘어 ERROR가 되기 때문(로컬 측정 seed 1·7·123에서 8%·8%·28%).
- oras-go: `success`·`rejected`만 판정, 그 밖은 미판정이며 미판정이 하나라도 있으면 ERROR(상한 옵션으로 완화 안 됨).
- 캠페인: 위반이 있으면 FAIL, 판정된 실행이 0이거나 미판정 비율이 상한을 넘으면 ERROR, 그 밖은 PASS. 종료 코드는
  0 PASS / 1 FAIL / 2 ERROR / 3 실행 전 거부(판정 없음). 탐색 루프·피드백·등록 실험 경로는 바뀌지 않았다.

### 고정 입력 회귀 검사

대상 프로그램과 버전을 주면 한 명령으로 다음을 끝낸다(docker가 도는 셸, Docker 필요; `inodefence verify`와
`make target-run`은 같은 드라이버다):

1. 대상 이미지가 없으면 `AUTO_PREPARE=1`일 때 커밋된 레시피로 준비하고, 이미지 안의 설치 버전이 요청한 버전과 같은지
   확인한다. 이미지가 있으면 그대로 다시 쓴다.
2. 대상마다 일회용 격리 컨테이너에서 고정 입력 TAR를 하나씩 압축 해제한다.
3. 보호 대상 외부 파일과의 객체 동일성(C1)과 외부 영향(C2)을 판정한다.
4. 셀마다 공통 형식 `inodefence-target-result-v1` 파일(`result.json`), 입력 TAR(SHA-256 포함), 원시 기록, 비전공자용
   한 장 요약 `summary.md`(대상·버전·판정·케이스별 결과·재현 방법)를 남긴다. 기존 결과는 덮어쓰지 않는다.

```bash
make target-run TARGET=node-tar TARGET_VERSIONS="7.5.2 7.5.3" AUTO_PREPARE=1 PYTHON=python3.12   # WSL2: PYTHON=python3
```

종료 코드: 0 PASS, 1 FAIL, 2 ERROR(셀 중 가장 나쁜 판정), 3 일부 또는 모든 셀이 판정되지 않음(거부된 입력, 이미 있는 결과,
설정·준비·이미지 문제).

### 지원 대상과 이전 브랜치에서 확인한 범위(이 RC에서 미재확인)

모두 `demo run`이며, #400 브랜치의 `make target-run`으로 2026-11-14에 관찰한 것이다. **이 RC(`inodefence verify`)에서는 다시 실행하지 않았다.** 아래 "확인"은 이 고정 입력에서 이 결과가 나왔다는 관찰이며, 그 밖의
입력이나 버전에 대한 주장이 아니다.

| 대상 | 바꾸는 축 | 확인한 셀과 결과 |
| --- | --- | --- |
| `node-tar` | 대상 버전 | 7.5.2: 5건 중 2건 위반(하드링크 입력 2건, C1·C2). 7.5.3: 5건 모두 거부, 위반 0. 같은 시점 `make regression`과 입력별 결과 10/10 일치 |
| `python-tarfile` | 추출 필터 또는 런타임 버전(한 번에 하나만) | 3.12.16 `fully_trusted`: 5건 모두 위반. 3.12.16 `data`: 위반 0. `data` 고정 3.12.3·3.12.16: 둘 다 위반 0 |
| `oras-go` | 대상 버전 | 2.6.1: 6건 중 1건 위반(작업 디렉터리 기준 하드링크 입력). 2.6.2: 위반 0 |
| `decompress` | 버전 칸에 패키지까지(`decompress@4.2.1` 원본, `@xhmikosr/decompress@11.1.4` 유지보수 fork) | 원본 4.2.1: 5건 중 3~4건 위반(입력 1건은 실행마다 달라짐; 하드링크 2건 C1·C2와 심볼릭 링크 뒤 쓰기 C2). FAIL 판정 자체는 결정적인 하드링크 입력 2건 때문에 안정적이다. fork 11.1.4: 5건 모두 거부, 위반 0 |

**확인한 환경.** macOS(arm64) + Docker Desktop과 Windows + WSL2(x86_64) + Docker Desktop.
- WSL2(#405 브랜치 기준, 팀 확인): `AUTO_PREPARE=1`로 네 대상의 준비 → 버전 확인 → 실행 → 판정이 맥북(arm64)과 같은
  결과였다. 다시 실행하면 이미지를 모두 재사용했고, 미지원 버전은 거부됐으며, `--dry-run`은 아무것도 바꾸지 않았다.
  `make check`는 4874 passed, 8 skipped. 맨 WSL에서는 `PYTHON`을 지정하지 않아도 `python3`(3.12)을 자동으로 쓴다.
- 이미지 준비는 빌드 캐시가 있을 때 대상당 10초 안팎이었고, 처음 빌드는 더 걸린다(성능 측정이 아니다).

**독립 재현(맥북, 2026-11-14).** 새 폴더에 받은 깨끗한 클론에서 README에 적힌 것만 따라, 기존 태그를 건드리지 않도록
`IMAGE_TAG_SUFFIX`로 이미지가 하나도 없는 상태를 만든 뒤 `AUTO_PREPARE=1` 한 줄씩으로 네 대상 여덟 셀을 준비→실행했다.
여덟 셀 모두 위 표와 같은 판정이었고(decompress 4.2.1은 이번에 4/5), 셀마다 `result.json`(엄격한 읽기와 입력 TAR
해시 재대조 통과), 입력 TAR 5~6개, 원시 기록, 결과 파일만으로 다시 만든 것과 같은 `summary.md`가 생겼다. 이미지를
직접 빌드하던 이전 절차(빌드 6줄 + 실행 4줄 + 결과마다 요약 명령)는 대상당 한 줄, 모두 4줄이 됐다. 이 맥에는 빌드
캐시가 남아 있어 준비는 대상당 몇 초였다. python 이미지는 이미 받아 둔 공식 태그를
다시 태그했다.

### 이미지 자동 준비 (`AUTO_PREPARE=1`)

| 대상 | 자동 준비 지원 범위(커밋된 레시피가 있는 버전) | #400 브랜치에서 준비·실행까지 확인한 버전(2026-11-14, 이 RC 미재확인) |
| --- | --- | --- |
| node-tar | 커밋된 lock이 있는 10개: 7.0.1·7.1.0·7.2.0·7.3.0·7.4.4·7.5.2·7.5.3·7.5.6·7.5.7·7.5.8 | 7.5.2·7.5.3(준비→실행), 7.4.4(준비·버전 확인만). 나머지 7개(7.0.1·7.1.0·7.2.0·7.3.0·7.5.6·7.5.7·7.5.8)는 레시피가 있지만 이 릴리스에서 실행 확인 안 함 |
| python-tarfile | 정확한 `X.Y.Z`의 공식 `python:X.Y.Z-slim`(다른 저장소는 거부) | 3.12.16(준비→실행, `fully_trusted`·`data`), 3.12.10(pull·버전 확인만) |
| oras-go | 2.6.1·2.6.2(커밋된 `go.mod`·`go.sum`) | 2.6.1·2.6.2(준비→실행) |
| decompress | 원본 `decompress@4.2.1`, fork `@xhmikosr/decompress@11.1.4`(패키지 이름까지 일치해야 함) | 둘 다(준비→실행) |

node-tar를 뺀 세 대상은 표에 없는 버전을 거부하며(종료 코드 3), 지원한다고 하지 않는다. node-tar는 아래 exploratory
경로를 따른다.
node-tar 7.0.1·7.1.0·7.2.0·7.3.0·7.4.4는 진행 중인 실험과 겹쳐, 이 릴리스 준비 기간에는 `make target-run`으로 실행하거나
새로 준비하지 않는다(위의 7.4.4 준비·확인은 이 결정 전 기록이다). 예제와 재현은 7.5.x로만 한다.

- 자동 준비한 이미지는 같은 버전을 같은 커밋된 레시피로 새로 빌드(python은 공식 이미지를 pull)한 것이다. 예전 증거
  실행에 쓴 이미지와 같다고 하지 않는다. image id는 빌드마다 다르고, 결과 파일 `provenance.image_id`가 실제로 쓴
  이미지를 남긴다. 준비 단계는 이미지 안의 설치 버전을 읽어 요청한 버전과 정확히 같을 때만 태그를 만든다.
- node-tar에서 커밋된 lock이 없는 정확한 버전(또는 `latest`)은 이 RC에서 거부하지 않고 **exploratory** 셀이 된다:
  npm registry에서 그 버전의 lock을 받아 점검한 뒤 커밋된 레시피로 `inodefence-node-tar-registry:<버전>` 이미지를
  준비한다. 결과 폴더 이름에 `-exploratory`가 붙고, 커밋된 lock 버전과 한 번에 섞어 실행하지 않는다. 이 경로의 실제
  준비·실행 결과는 이 릴리스 노트에 싣지 않았다(후속 검증).
- 기존 이미지 태그는 항상 다시 쓰고, 자동 준비는 이미지가 없을 때만 한다.

### 알려진 한계

- **oras-go 탐색의 "위반 없음"은 근거가 제한적이다.** oras-go 탐색은 공통 seed가 oras-go 디렉터리 아티팩트 제목
  접두(`d/`) 없이 만들어져 대부분의 실행이 oras-go에서 거부된다(HOST4 seed 123·budget 20에서 20/20 거부,
  2026-11-15 맥북 실행 budget 60에서 성공 6건·9건). 엔트리를 `d/` 아래로 옮기는 변경은 탐색 대상의 의미를 바꾸므로
  사용자 결정 전까지 하지 않는다.

- **입력은 하드링크 중심이다.** 고정 입력은 하드링크 2건과 심볼릭 링크 뒤 쓰기 3건(oras-go는 하드링크 1건 추가)뿐이고,
  `make target-run`은 입력을 바꿔 가며 탐색하지 않는다. node-tar와 oras-go에서 나온 위반은 모두 하드링크 입력이다.
- **decompress 4.2.1의 입력 1건(`nested_symlink_write`)은 실행마다 결과가 다르다.** 대상 프로그램 자체의 확인과 사용
  사이 경쟁 때문이며(판정기의 비결정성이 아니다, #406), 같은
  조건 10회 중 8회 위반(C2)·2회 거부였다(fork는 10회 모두 거부, 나머지 입력은 안정). 그래서 4.2.1의 위반 건수는
  실행에 따라 4/5 또는 3/5가 될 수 있다.
- **python-tarfile 결과는 필터 설정 비교다.** `fully_trusted`와 `data`의 차이는 같은 런타임 안의 설정 차이이고, Python
  버전 간 비교가 아니다. 런타임 버전 축으로 본 3.12.3·3.12.16(`data`)은 둘 다 위반 0이었다.
- **통과(PASS)는 안전 증명이 아니다.** 시험한 입력과 관찰한 기준 안에서 위반이 안 보였다는 뜻이다. 위반은 위반
  후보이며, 확정 취약점으로 보려면 재현과 원인 분석이 따로 필요하다.
- **C0(경로 경계)는 이 명령에서 관찰하지 않는다.** 결과 파일에 `null`(관찰 안 함)로 남고, "위반 없음"으로 읽으면 안 된다.
- **실행은 `demo run` 수준이다.** 사전등록 실험이나 자격 검증 결과가 아니다.
- **이미지는 환경마다 준비한다.** arm64와 x86_64 사이에 옮겨 쓸 수 없다. 처음 준비할 때는 네트워크가 필요하고(빌드·pull),
  빌드 캐시 없이 처음부터 빌드할 때 걸리는 시간은 재지 않았다.
- **이 기능은 취약점 자동 발견도, C0/C1/C2 전체 검증도 아니다.** 고정 입력에 대한 C1/C2 관찰이다.
- **docker가 도는 셸(macOS 터미널 또는 WSL 셸)에서 실행한다.** Dev Container 안에는 docker가 없다.
- **`make`의 종료 상태는 실패면 언제나 2다.** 판정 코드(0/1/2/3)는 `make: *** … Error N`의 N이거나, 스크립트를 직접
  불렀을 때의 종료 코드다.
- **호스트에 Python 3.12가 필요하다.** `PYTHON`을 주지 않으면 `python`, 없으면 `python3`을 쓰는데, macOS 기본
  `python3`(3.9)은 실행 전 점검 없이 ImportError로 멈춘다. macOS에서는 `PYTHON=python3.12`를 준다(WSL2 Ubuntu 24.04의
  `python3`은 3.12).
- WSL2가 아닌 Linux 호스트에서는 따로 확인하지 않았다.

### 후속 검증(이 릴리스에서 확인 결과를 싣지 않은 것)

- **탐색 `explore`와 `status`·`replay`.** 네 대상 모두 탐색 hook이 등록돼 있고(`inodefence targets`), 명령은
  이 RC에 들어 있다. 실제 탐색은 위 HOST4 검증(네 대상 각 한 버전, seed 123, D1 반영 전 커밋)만 확인했다. D1 반영
  후 커밋에서의 재실행, 위반 케이스가 있는 실행의 `replay`, macOS는 아직 확인 결과가 없다.
- **이어 하기(resume)는 없다.** 멈춘 탐색을 중간부터 이어서 돌릴 수 없다.
- **위 고정 입력 회귀 결과는 #400 브랜치의 `make target-run`으로 확인한 것이다.** 같은 드라이버를 부르는
  `inodefence verify`로 이 RC에서 다시 실행하지는 않았다.
- **wheel 설치만으로 대상을 돌리는 것은 지원하지 않는다.** 드라이버와 레시피가 패키지에 없어 클론과
  `INODEFENCE_HOME`이 필요하다.

### 라이선스

MIT License(D048, #392). 실험 대상 extractor와 의존성은 각자의 라이선스를 따른다.

# Changelog

이 파일은 InodeFence의 버전별 사용자 관점 변경을 적는다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를,
버전은 [Semantic Versioning](https://semver.org/lang/ko/)의 0.x 규칙(0.x에서는 하위 호환을 약속하지 않음)을 따른다.
실험 결과와 호스트별 반복 로그 전문은 싣지 않고, 각 버전의 검증은 요약과 출처만 둔다. 실행별 기록은
[docs/LOG.md](docs/LOG.md)·[docs/STATUS.md](docs/STATUS.md)·PR 본문에 있다.

## [Unreleased]

### 추가된 사용자 기능
- `inodefence explore --mutation-policy uniform-b-grammar-v2-freeze-3-fixed-baseline-v1`: node-tar 탐색에서 v2 문법
  변이 정책(탐색용)을 고른다. 받는 값은 이것 하나이고(v2.1 seed 코퍼스 변형은 열지 않음), 다른 대상은 실행 전 종료 3으로
  거부한다. 옵션을 주면 `result.json`의 `campaign.mutation_policy`에 적는다(루프 보고서가 그 정책을 돌렸는지 확인한 뒤).
  기본값은 바뀌지 않는다. [USAGE](docs/USAGE.md#탐색-돌리기)
- `result.json` 선택 키 `campaign.build_invalid`: TAR로 만들 수 없어 추출하지 않은 실행 수(v2 정책에서만, 0이면 키 없음).
  `summary.md`에 한 줄로 보인다. 수는 루프 보고서의 실행 수 − 종료 상태 합이고, 셀 수 없거나 live 스냅숏과 어긋나면
  결과 없이 종료 2다(키를 빼서 비율을 낮게 적지 않는다).

### 변경된 동작과 호환성
- 탐색 드라이버(네 대상 모두)가 호출자 환경의 `DEMO_MUTATION_POLICY`를 런처에 넘기지 않는다. 전에는 node-tar와
  python-tarfile 탐색에서 이 변수가 그대로 전달돼, 문서에 없는 방법으로 변이 정책이 바뀌고 `result.json`에는 남지 않았다.
  정책을 바꾸려면 `--mutation-policy`를 쓴다. 이 변수가 설정돼 있으면 무시하면서 stderr에 경고 한 줄
  (`TARGET-EXPLORE WARNING: environment variable DEMO_MUTATION_POLICY=… is ignored; use --mutation-policy …`)을 낸다.
- 같은 방식으로 호출자 환경의 `DEMO_POLICY`(search 정책)도 넘기지 않고 경고 한 줄을 낸다. 전에는 node-tar와 python-tarfile
  탐색의 search 정책이 이 변수로 바뀌었다. 탐색의 search 정책은 대상마다 고정이며 고르는 옵션은 없다.
- 미판정 비율(`campaign.unjudged_ratio`)의 분모에서 build-invalid 실행을 뺀다(분모 = 실행 수 − `build_invalid`). 이 키가
  없는 결과(기본 정책의 모든 실행과 0.2.0이 쓴 파일)는 값이 그대로다. 옵션 없는 실행의 `result.json`·`summary.md`는
  `main`(`fccdf35`) 코드가 같은 입력으로 쓴 것과 바이트 동일하다(node-tar 탐색 4경우, python-tarfile 탐색, verify 셀;
  `tests/test_explore_mutation_policy.py`). 예외는 아래 #533 항목(python-tarfile 탐색이 빈 아카이브를 만나는 경우)이다.
- `--profile fast`가 이미지 신원 확인 컨테이너를 케이스마다가 아니라 캠페인 시작·200건마다·끝에만 띄운다(네 대상,
  [D064](docs/DECISIONS.md)). 실행 컨테이너와 격리·판정은 그대로이고, 끝 확인이 실패하면 결과 없이 종료 2다. FAST 결과에는
  `campaign.identity_checks`(확인 기록)가 남고 runtime 기록에 `identity_check_every`가 남는다. 기본(`strict`)과 `replay`는
  그대로다. N=200은 고정이고 고르는 옵션은 없다. 호출자 환경의 `DEMO_IDENTITY_CHECK_EVERY`는 무시하고 경고 한 줄을 낸다.
  확인 사이에 남는 보호는 대상마다 다르다. node-tar는 실행 컨테이너 안의 worker가 매번 다시 확인하고, 나머지 셋은
  고정된 이미지 ID뿐이다. 시간 효과는 아직 재지 않았다.
- python-tarfile 탐색이 실행 중 스텝 전체(스냅숏·trace)를 메모리에 쌓지 않는다(#542). `result.json`과 `summary.md`는
  그대로다. 엔진 원시 보고서(`inodefence-python-tarfile-explore-*.json`)에서는 `steps` 배열이 빠지고 `streaming: true`가 붙는다.
  스텝 기록은 옆의 `.steps.jsonl`에 있다.
- python-tarfile 탐색의 케이스 번호(`step-N`, `run_index`)와 `campaign.runs_to_first_violation`을 추출 횟수가 아니라
  build-invalid를 포함한 루프 step 수로 센다(node-tar와 같은 단위, D060). v2 정책에서만 드러나는 번호 정합이다: build-invalid
  step이 없는 실행(기본 정책 전부)은 번호가 그대로이고, 이미 기록된 결과는 다시 세지 않는다.
- 새 선택 키가 든 `result.json`은 이 버전 이상의 `inodefence status`·`summary`로 읽는다([호환 약속](docs/USAGE.md#호환-약속)).

### 고친 문제
- `inodefence verify`·`explore`: `-`로 시작하는 `--image-tag-suffix`(예: `--image-tag-suffix=-win`)가 드라이버로 넘어가며
  두 인자로 나뉘어 실행 전에 거부되던 문제([#528](https://github.com/TheWaitForAGI/InodeFence/issues/528)). 이제 하나의
  값으로 전달된다. 공백 형식(`--image-tag-suffix -win`)은 여전히 받을 수 없고, 거부 메시지(종료 3)가 `=` 형식을 안내한다.
  옵션을 주지 않은 실행과 `-`로 시작하지 않는 값의 동작은 그대로다.
- `inodefence replay`의 표시 두 가지([#494](https://github.com/TheWaitForAGI/InodeFence/issues/494)).
  python-tarfile·decompress·oras-go 재실행의 런처 마지막 줄이 `PASSED: node-tar replay`로 나오던 것을 실제 대상
  이름으로 보여 준다(공유 런처는 그대로, 재실행 쪽에서 그 한 줄만 바꿈). 원래 기록에 fingerprint가 없을 때(결과 폴더
  재실행) `replay.json`의 `same_fingerprints`·`fingerprint_match_rate`를 0 대신 `null`로 적고 새 키
  `fingerprints_comparable: false`를 더하며, 터미널은 `fingerprints n/a`로 보여 준다. 재현 판정(`conclusion`), 종료 코드,
  `result.json`은 바뀌지 않는다.
- python-tarfile 판정: entry가 0개인 아카이브를 오류 없이 끝낸 실행이 trace 미완결(`execution_backend_failure`)로 기록돼,
  탐색에서는 예외 조항으로 판정되면서 루프 보고서의 step은 무효(`observer_integrity`)로 갈리던 문제
  ([#533](https://github.com/TheWaitForAGI/InodeFence/issues/533)). 이제 `success`의 trace는 모든 entry가 성공하고 worker가
  보고한 처리 member 수가 entry 수와 같을 때 완결이다. 빈 아카이브는 worker가 `members: 0`을 보고하면 완결·유효이고, 탐색에서
  피드백 대상이 될 수 있다(새 효과 키는 없다). worker 보고가 없거나 읽을 수 없는 `success`는 entry 수와 상관없이 미완결이다.
  탐색 규칙의 빈 아카이브 예외는 없앴다. C0/C1/C2 판정은 바뀌지 않는다. 같은 seed의 python-tarfile 탐색이 빈 아카이브를
  만나는 경우 이전 결과와 바이트가 같다고 보장하지 않는다.

## [0.2.0] — 2026-11-18

첫 릴리스다. 아래 내용은 `main`에 있다(착지 [#484](https://github.com/TheWaitForAGI/InodeFence/pull/484), 그 뒤
[#489](https://github.com/TheWaitForAGI/InodeFence/pull/489)·[#506](https://github.com/TheWaitForAGI/InodeFence/pull/506)).
태그 `v0.2.0`와 GitHub Release는 지웅이 만든다. 범위와 릴리스 조건은 [D049](docs/DECISIONS.md)에 있고, 조건 6개의 근거는 다음과 같다.

| 조건 | 근거 |
| --- | --- |
| 1 oras-go 탐색에서 실제 추출 | 제품 탐색 입력을 아티팩트 디렉터리 `d/` 아래로 보냄. 2.6.2 demo run에서 11/20 추출 |
| 2 네 대상 E2E가 CI에 있고 통과 | CI `product-e2e` job(`scripts/dev/product_e2e.py`) |
| 3 런처의 Docker 시간 제한과 정리 실패 종료 코드 | 아래 「변경된 동작과 호환성」의 런처 항목, `tests/test_target_launchers_bounded.py` |
| 4 실제 위반 케이스 `replay` 기록 | 2026-11-18 정정된 문구 기준. 알려진 취약 버전 `decompress@4.2.1` 탐색의 C0 위반 케이스를 3회 재실행해 3/3 재현(통제 재현, demo run). node-tar·oras-go·python-tarfile은 케이스를 얻지 못함([USAGE](docs/USAGE.md#지원-환경과-확인-수준)) |
| 5 호환 약속 고정 | 아래 「호환 약속」, `tests/test_result_contract.py` |
| 6 두 번째 호스트 | 맥북의 Ubuntu 24.04 arm64 VM에서 깨끗한 클론으로 USAGE 그대로 실행(2026-11-18, demo run) |

확인한 환경은 Windows + WSL2(x86_64) + Docker Desktop 한 대와 Ubuntu 24.04 arm64 VM 한 대다. x86_64 네이티브 Linux와 macOS는
이 릴리스에서 확인하지 않았다. 위반 0은 안전성 증명이 아니다.

버전 번호: `pyproject.toml`은 2026-10-03부터 `0.1.0`이었지만 그 번호로 태그나 릴리스를 낸 적이 없고, 그동안 개발 중인
모든 상태가 `0.1.0`으로 설치됐다. 같은 번호가 서로 다른 코드를 가리키지 않도록 첫 태그는 `0.2.0`으로 한다.
`pyproject.toml`의 버전은 이미 `0.2.0`이다.

### 추가된 사용자 기능

- **`inodefence` 명령.** 하위 명령 `targets`(대상과 지원 기능 표), `doctor`(환경 점검), `verify`(고정 입력 회귀 검사),
  `explore`(피드백 탐색), `status`(실행 중·끝난 탐색 확인), `replay`(탐색 케이스 재실행, 네 대상), `summary`(결과
  한 장 요약). `--version`은 패키지 버전을 출력한다. (#457)
- **고정 입력 회귀 검사(`verify`).** 대상과 버전을 주면 이미지를 준비하거나 다시 쓰고(`--auto-prepare`), 일회용 격리
  컨테이너에서 고정 입력 TAR를 하나씩 풀어 보호 대상 외부 파일과의 객체 동일성(C1)과 외부 영향(C2)을 판정한다. 셀마다
  `inodefence-target-result-v1` 형식 `result.json`, 입력 TAR(SHA-256 포함), 원시 기록, 한 장 요약 `summary.md`를 남기고
  기존 결과는 덮어쓰지 않는다. `make target-run`은 같은 드라이버를 부른다. (#457)
- **탐색(`explore`)과 판정 규칙(D1, 2026-11-16 결정).** 네 대상 모두 탐색 hook이 있다. 위반이 보인 실행은 종료 상태와
  상관없이 위반이다. 위반이 보이지 않은 실행은 다음일 때 **미판정**이며 깨끗한 음성으로 세지 않는다.
  - node-tar·decompress: `failed`, `timed_out`, trace가 온전하지 않은 `success`(decompress는 worker 기록이 없는 실행도).
    `rejected`는 판정 유지.
  - python-tarfile: `timed_out`, worker 보고가 없거나 종료 상태와 어긋나는 실행, trace가 온전하지 않은 `success`.
    **편차:** worker 보고가 종료 상태와 일치하는 `failed`(tarfile이 예외로 거부)는 판정 유지. 문자 그대로의 D1이면
    `data` 필터의 정상 거부가 미판정 상한(0.2)을 넘어 깨끗한 탐색이 ERROR가 되기 때문이다(로컬 측정 seed 1·7·123에서
    8%·8%·28%).
  - oras-go: `success`·`rejected`만 판정, 그 밖은 미판정이며 하나라도 있으면 ERROR(상한 옵션으로 완화 안 됨).
  - 캠페인: 위반이 있으면 FAIL, 판정된 실행이 0이거나 미판정 비율이 상한을 넘으면 ERROR, 그 밖은 PASS. 탐색 루프·피드백·
    등록 실험 경로는 바뀌지 않았다.
  - 추출 성공 0건 경고: 모든 실행이 `success` 없이 끝나면 `summary.md`·탐색 출력 줄·`status`에 "위반 없음의 근거가
    제한적" 경고를 붙인다(판정·종료 코드 불변). (#457)
- **`status`.** 실행 중 폴더(`live/`)와 끝난 결과를 읽는다. `--out` 폴더 자체도 받고, 실행 중 처리량 줄과 STALE 경과
  시간을 보여 준다. 끝난 실행의 host pull 실패에는 판정 오류가 아니라는 설명을 붙인다. (#457, #466)
- **`explore` 실행 중 터미널 진행 표시.** 대상·정확한 버전·프로필·seed·budget, 실행 수, 종료 상태별 수와 미판정 수,
  위반 후보(C0/C1/C2), 처리량, 근거가 충분할 때만 ETA, 현재 단계를 한 줄로 보여 준다. `status`와 같은 파일을 읽고
  모르는 값은 `?`로 표시한다. 런처 원시 출력은 `<--out>/runtime/`의 로그 파일로 가고 `--verbose`가 이전 출력을,
  `--quiet`가 진행 줄 없는 출력을 낸다. 종료 코드와 결과 줄은 같다. live 폴더가 없는 세 대상은 실행 중 수가 `?`다.
- **`replay`(node-tar).** 입력 SHA·이미지 ID·컨트롤러 보고서를 다시 대조하고, 원본 case 폴더는 바꾸지 않으며 새 폴더에
  발행한다. 재현 증거(컨트롤러 보고서·단계 기록·호출 기록)와 실행 기록을 replay 폴더 `evidence/`에 보존한다. (#457, #466)
- **네 대상 `replay`와 `verify` 정상 입력 대조군(PR-B, REPLAY 레인).** `replay`가 python-tarfile·decompress·oras-go도
  받는다: 탐색 결과 폴더의 저장 입력(`<결과 폴더> --case step-N`)을 SHA-256 대조 뒤, 기록된 정확한 이미지와 그 대상의
  조건(추출 필터·런타임, `<패키지>@<버전>`, oras-go 버전; `fully_trusted`는 거부, oras-go 입력은 고치지 않음)으로 그
  대상 탐색의 실행 함수·판정 규칙 그대로 다시 돌린다. 회차마다 분류(위반 재현 / 재현 안 됨 / 위반 없음 / 새 위반 /
  미판정 / 실행 기반 오류)와 원자료 위치를 남긴다. `verify`는 같은 실행·같은 이미지에서 정상 아카이브 하나를 먼저
  풀어 `BENIGN-CONTROL` 한 줄과 `result.json`의 `benign_control`로 기록하고, 풀리지 않으면 PASS 대신 ERROR(종료 2)다.
  실제 위반 케이스의 native 재실행은 실행하지 않았다(통제·합성 테스트만). 상세는 [사용 안내](docs/USAGE.md).

### 제품 CLI와 설치 방식

- **설치.** 클론에서 `pip install -e .`. wheel로 설치할 수도 있지만 대상 실행(`targets`·`verify`·`explore`·`replay`)에는
  클론이 필요하다. 드라이버는 패키지에 들어 있지만(#465) `tools/` 이미지 레시피, 컨트롤러 셸 런처
  `scripts/local_*.sh`, `experiments/repro/`는 패키지에 없다. `--version`·`--help`·`doctor`·`status`·`summary`는 클론 없이 동작한다.
  Python은 3.12만 받는다(`requires-python >=3.12,<3.13`; 3.13에서는 pip이 설치를 거부한다).
- **클론 선택.** `INODEFENCE_HOME`(환경 변수 → 사용자 설정 파일) → editable 설치가 속한 checkout. 작업 폴더로 추측하지
  않는다. CLI는 고른 클론의 코드를 그 클론의 `src`를 앞에 둔 하위 프로세스로 실행하므로, 실행 코드·레시피·결과의 엔진
  커밋이 같은 트리에서 온다. 상대 경로 `INODEFENCE_HOME`은 명령을 시작한 폴더 기준 절대 경로로 푼다. (#465, #467)
- **드라이버 위치.** 제품 드라이버 22개가 `scripts/`에서 `src/inodefence/drivers/`로 옮겨졌다(`python -m
  inodefence.drivers.run_target` 등). 설치본의 드라이버를 직접 실행하면 클론 밖이라 거부한다(종료 3). (#465)
- **사용자 설정.** `~/.config/inodefence/config.env`(또는 `$XDG_CONFIG_HOME/…`, `INODEFENCE_CONFIG`로 지정, 예시
  `.env.example`)는 `KEY=VALUE`로 파싱만 하고 실행하지 않는다. 키는 `INODEFENCE_HOME`·`INODEFENCE_OUTPUT_DIR` 둘뿐이고,
  seed·budget·`INODEFENCE_RUNTIME_ROOT` 등 다른 키는 오류로 거부한다. 우선순위는 환경 변수 → 설정 파일 → 기본값.
  (#457, #467)
- **출력 폴더.** `--out`의 상대 경로는 명령을 실행한 폴더 기준이다. 저장소 안, 쓸 수 없는 폴더, 이미 있는 파일은
  `--dry-run`을 포함해 실행 전에 거부한다. 기본값은 `~/inodefence-target-run`·`~/inodefence-explore`이고
  `INODEFENCE_OUTPUT_DIR`로 기준 폴더를 바꾼다. (#457, #467)
- **`doctor`.** Python, 사용자 설정(값의 출처 포함), 저장소(대상 명령과 같은 판정), 실행 중인 코드 위치, 출력 폴더, Docker
  CLI와 daemon 접근, 로컬 `inodefence-*` 이미지, 잔존 컨테이너·볼륨(조회만), 디스크 여유(2 GiB 미만이면 WARN), 메모리(항상
  UNKNOWN, 종료 코드 무관), runtime 폴더를 출력한다. 어느 이미지가 어느 대상·버전용인지는 판단하지 않고 `verify --dry-run`을 안내한다. (#457,
  #466, #467)
- **`--help`.** 기본값·필수 여부와 명령별 종료 코드를 보여 준다. 드라이버의 오류 메시지는 `inodefence verify` 같은 명령
  이름으로 나오고, 이미지 준비 안내는 `--auto-prepare`로 나온다. (#457, #467)

설치 방식별 동작(#467, 깨끗한 Python 3.12 venv, 클론 밖 작업 폴더, `PYTHONPATH` 비움). 값은 종료 코드.

| 명령 | editable | wheel만 | wheel + `INODEFENCE_HOME` |
| --- | --- | --- | --- |
| `--version`, `--help`, `status`, `summary` | 0 | 0 | 0 |
| `doctor` | 0 | 1 (repository not found) | 0 |
| `targets`, `verify --dry-run`, `explore --dry-run` | 0 | 3 (클론 필요) | 0 |

### 지원 대상과 실행 범위

| 대상 | 바꾸는 축 | 이미지 자동 준비(`--auto-prepare`) 범위 | 탐색 | replay |
| --- | --- | --- | --- | --- |
| node-tar | 대상 버전 | 커밋된 lock이 있는 10개(7.0.1·7.1.0·7.2.0·7.3.0·7.4.4·7.5.2·7.5.3·7.5.6·7.5.7·7.5.8). 그 밖의 정확한 버전·`latest`는 exploratory | 지원 | 지원(실제 위반 E2E 미검증) |
| python-tarfile | 추출 필터 또는 런타임 버전(한 번에 하나) | 정확한 `X.Y.Z`의 공식 `python:X.Y.Z-slim` | 지원(`fully_trusted` 필터는 탐색 보류) | 지원: 결과 폴더 `--case`(실제 위반 E2E 미검증) |
| decompress | 패키지와 버전(`decompress@4.2.1` 원본, `@xhmikosr/decompress@11.1.4` fork) | 두 패키지 버전 | 지원 | 지원: 결과 폴더 `--case`(실제 위반 E2E 미검증) |
| oras-go | 대상 버전 | 2.6.1·2.6.2 | 입력 이름을 `d/` 아래로 옮겨 보냄(아래 알려진 제한) | 지원: 결과 폴더 `--case`(실제 위반 E2E 미검증) |

- node-tar를 뺀 세 대상은 표에 없는 버전을 거부한다(종료 3). node-tar에서 커밋된 lock이 없는 정확한 버전이나 `latest`는
  **exploratory** 셀이 된다: npm registry에서 그 버전의 lock을 받아 점검한 뒤 커밋된 레시피로
  `inodefence-node-tar-registry:<버전>`을 준비하고, 결과 폴더 이름에 `-exploratory`가 붙으며, 커밋된 lock 버전과 한 번에
  섞어 실행하지 않는다.
- 자동 준비한 이미지는 같은 버전을 커밋된 레시피로 새로 빌드한 것이다(python은 공식 이미지 pull). 예전 증거 실행에 쓴
  이미지와 같다고 하지 않는다. 결과 파일 `provenance.image_id`가 실제로 쓴 이미지를 남기고, 준비 단계는 이미지 안의 설치
  버전이 요청과 정확히 같을 때만 태그를 만든다. 이미 있는 태그는 다시 쓰고, 자동 준비는 이미지가 없을 때만 한다.
- node-tar 7.0.1·7.1.0·7.2.0·7.3.0·7.4.4는 진행 중인 실험과 겹쳐, 이 릴리스 준비 기간에는 실행하거나 새로 준비하지
  않는다. 예제와 재현은 7.5.x로만 한다.
- 실행은 docker가 도는 셸(macOS 터미널 또는 WSL 셸)에서 한다. Dev Container 안에는 docker가 없다. 이미지는 환경마다
  준비하며 arm64와 x86_64 사이에 옮겨 쓸 수 없고, 처음 준비에는 네트워크가 필요하다.

### Runtime 진단·신뢰성 개선 (#466)

- 모든 컨트롤러 실행(explore·replay)이 하나의 Runtime 세션을 거친다. 기본 실행 프로필은 **STRICT**(검증된 Docker 실행을
  그대로 씀)이다.
- **`explore --profile fast`(PR-B, 선택 옵션, 기본은 strict).** 런처가 실행마다 하는 공용 이미지 두 개(컨트롤러·helper)
  재빌드를, 그 이미지가 이 checkout의 빌드 입력으로 런처가 빌드한 것임이 확인된 때에만 건너뛴다(확인은 Docker
  context별 24시간, 입력·이미지 ID가 바뀌면 무효). 확인이 안 되면 런처의 빌드 전용 실행으로 먼저 빌드하고, 그런 실행이
  없는 python-tarfile 런처는 STRICT처럼 실행하되 그 사실을 출력·기록하며, 빌드 실패는 종료 3이다. 입력·판정·격리·결과
  형식·종료 코드는 STRICT와 같고 `replay`는 항상 STRICT다. 실측(WSL2 한 대, node-tar 7.5.23, budget 20, 번갈아 5회씩):
  컨트롤러 준비 전 구간이 실행당 평균 1.5 s(2.78 s → 1.33 s) 줄고 케이스당 시간(약 1.9 s)과 전체 처리량은 그대로다. 케이스당 비용은 격리 실행 경로 안에 있어 이
  프로필의 범위 밖이다. ([사용 안내](docs/USAGE.md#한계와-주의))
- 실행 기록 `<out>/runtime/<run_id>-<UTC>.json`(replay는 `evidence/runtime-record.json`)을 실패·중단에도 쓰고 덮어쓰지
  않는다. 절대 경로와 사용자 환경은 기록하지 않는다. 기존 결과 파일은 바뀌지 않는다.
- Docker 응답을 정상 / 연결 불가 / 시간 초과로 구분하고, 이미지 조회를 있음 / 없음 / 판정 불가로 구분한다. 판정 불가면
  이미지를 준비하지 않고 멈춘다(이전에는 "없음"으로 보고 빌드로 넘어갔다). explore에 Docker 사전 점검이 생겨 Docker가 없을
  때 이미지 준비 전에 종료 3으로 멈춘다.
- 깨끗하지 않은 종료에서 `TARGET-EXPLORE DIAGNOSIS: stage=… category=… result=… evidence=…` 한 줄을 출력한다(단계:
  preflight / image / controller-setup / loop / cleanup, 못 정하면 UNKNOWN). 진단은 관찰·기록만 하고 판정과 종료 코드를
  바꾸지 않는다.
- replay는 이미지를 있음 / 없음 / 판정 불가로 구분해 판정 불가면 실행 전 종료 3이고, 미완료에는 `REPLAY DIAGNOSIS` 한
  줄을 출력한다. `replay.json`에 `replay.diagnosis`와 `replay.repository`(`checkout_id`, 수정된 추적 파일 수, 경로
  원문 없음)가 추가됐다. 같은 초에 만든 replay 폴더는 `-2`·`-3` 접미로 구분한다(이전에는 traceback).
- 실행 전 이번 실행 이름의 컨트롤러·볼륨이 남아 있거나, 같은 `--out`에 이 실행의 보고서·결과가 있으면 컨트롤러를 띄우기
  전에 종료 3(이전에는 루프를 다 돈 뒤 traceback). 실행 후 잔존 자원은 경고만 하고 삭제하지 않는다. 자동 재시도·강제 종료
  watchdog·탐색 재개는 없다.

### 변경된 동작과 호환성

**호환 약속(D049).** 0.2.x 안에서는 아래 종료 코드와 `result.json`(`inodefence-target-result-v1`)의 필수 키를 바꾸지 않는다.
그 밖의 출력(터미널 문구, `summary.md`, `live/`·`runtime/` 파일, `replay.json`, 폴더 이름)은 약속하지 않는다
([USAGE 호환 약속](docs/USAGE.md#호환-약속)). `inodefence targets`는 `replay` 열을 보여 주고, `auto-prepare`·`replay` 값을
대상 어댑터에서 읽는다(이전에는 `auto-prepare`가 항상 yes였다. 지금 등록된 네 대상의 값은 그대로 yes다).

**python-tarfile·decompress·oras-go 런처의 Docker 시간 제한과 정리 실패(D049 조건 3).** 세 대상의 호스트 런처는 탐색
본체와 로컬 CLI 조회(`docker context show`)를 뺀 모든 Docker 데몬 호출에 시간 제한을 둔다(조회 30초, 설정 exec 60초, pip 300초, 생성 60초, 이미지 build 1800초,
정리는 node-tar와 같은 값). 컨트롤러와 볼륨에는 실행별 소유 label이 붙고, 정리는 그 label이 있는 것만 지운다. 정리가
실패하거나 시간을 넘기거나 제거를 확인하지 못하면 `INODEFENCE_CLEANUP_UNKNOWN`/`FAILED cleanup` 줄을 남기고, 성공이던
런처 종료를 125로 바꾼다. `explore`는 그 경우 ERROR(종료 2)로 끝나고 결과를 발행하지 않는다(이전에는 정리 실패가 무시돼
PASS/FAIL이 그대로 나왔다). 컨트롤러의 격리 인자는 소유 label 하나 외에 바뀌지 않았다.
컨트롤러의 루프 보고서를 호스트로 옮길 때 이미 있는 파일을 덮어쓰지 않는다(같은 폴더의 임시 파일에서
하드링크, 하드링크가 안 되는 파일시스템에서는 덮어쓰지 않는 이름 바꾸기). 같은 이름의 보고서가 이미 있으면
정리 실패로 보고 125가 된다(`inodefence explore`는 실행 전에 같은 출력이 있으면 거부하므로 보통 생기지 않는다).

종료 코드(`--help`에도 표시):

| 명령 | 0 | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- | --- |
| `verify`, `explore` | PASS | FAIL(위반 판정) | ERROR(판정 없음; 컨트롤러 시작 뒤 중단 포함, 결과 미발행) | 실행 전 거부(인자 오류, 클론 없음, 이미지 없음, 기존 결과, 쓸 수 없는 `--out`, 설정 오류) | — |
| `replay` | 모든 회차 실행 | 일부 회차만 실행(끝난 회차 보존) | replay 불가 | 실행 전 중지(이미지 없음, Docker 무응답, 실행 이름 사용 중) | 미지원 대상 |
| `doctor` | 실패 없음(UNKNOWN은 실패 아님) | FAIL 줄 있음 | — | — | — |
| `status`, `summary` | 표시·작성함 | — | 읽을 수 없는 결과, 쓸 수 없는 출력, 사용법 오류 | — | — |

`verify`·`explore`·`replay`에서는 사용법 오류도 3이다(2는 결과에만 쓴다). `make`는 실패면 언제나 2로 끝나므로 판정 코드는
`make: *** … Error N`의 N이나 드라이버를 직접 부른 종료 코드로 읽는다.

RC(#457) 이후 스택에서 의도적으로 바뀐 동작:

- **#464** 분석·개발·운영 도구 10개가 `scripts/analysis/`·`scripts/dev/`·`scripts/ops/`로 옮겨졌고 옛 경로는 동작하지
  않는다(호환 wrapper 없음, 이동표는 PR 본문과 [scripts/README.md](scripts/README.md)). `make` target과 CLI는 그대로다.
- **#465** 옛 `scripts/` 드라이버 경로 중 7개는 별칭으로 남고 15개는 사라졌다. `targets`는 레지스트리를 대상 명령과 같은
  클론 코드의 하위 프로세스에서 읽는다(출력 동일). 표식만 있고 `src/inodefence/drivers/`가 없는 클론(이전 레이아웃)은
  대상 명령이 종료 3으로 거부한다.
- **#466** 컨트롤러가 시작된 뒤의 중단은 네 대상 모두 ERROR(종료 2)이고 결과를 발행하지 않는다. 이전에는 python-tarfile이
  SETUP(3)으로 표시했고, 런처가 1·125·137로 끝나도 완주 보고서가 있으면 PASS `result.json`을 발행했다. 중단(aborted)
  보고서와 보고서 없음도 종료 2다. `doctor`에 잔존 자원·디스크·메모리 3줄, explore·verify·replay에 위 진단 문구가
  추가됐다.
- **#467** 상대 `INODEFENCE_HOME`이 editable 설치에서 지목한 클론이 아니라 자기 checkout을 실행하던 결함을 고쳤다.
  `doctor`가 이전 레이아웃 클론을 OK가 아니라 FAIL(종료 1)로 보고한다. 쓸 수 없는 `--out`과 상대 경로·리터럴 `$HOME`
  `INODEFENCE_OUTPUT_DIR`은 dry-run에서도 종료 3이다(이전 0). 설정 값 뒤 ` # 주석`·짝 없는 따옴표는 줄 번호와 함께
  거부하고, UTF-8 BOM과 CRLF 줄 끝은 받으며, 디렉터리를 가리키는 `INODEFENCE_CONFIG`는 그렇다고 말한다. `INODEFENCE_HOME`이 클론이 아니면 값·출처·빠진 것을 말한다. `PYTHONPATH`가 설치본을 가리면
  `doctor`가 WARN한다(종료 코드 불변). 빌드 설정은 SPDX `license = "MIT"`와 `setuptools>=77`로 바뀌어 빌드 경고가 없다.

### 알려진 제한

- **결과의 의미.** 통과(PASS)·위반 0은 안전 증명이 아니라 시험한 입력과 관찰 기준 안에서 위반이 안 보였다는 뜻이다. 위반은
  위반 후보이며 확정 취약점으로 보려면 재현과 원인 분석이 따로 필요하다. C0(경로 경계)는 관찰하지 않고 결과에 `null`로
  남는다. 이 기능은 취약점 자동 발견도, C0/C1/C2 전체 검증도 아니다. 실행은 `demo run` 수준이며 사전등록 실험이나 자격
  검증 결과가 아니다.
- **고정 입력의 한계.** 고정 입력은 하드링크 2건과 심볼릭 링크 뒤 쓰기 3건(oras-go는 하드링크 1건 추가)뿐이고 모두 공격
  형태라 정상 입력 대조군이 없다. 모든 입력을 거부(declined)한 결과만으로는 모든 입력을 거부하는 고장 난 추출기와 구분할
  수 없다(탐색의 추출 성공 수로 보완). node-tar와 oras-go에서 관찰된 위반은 모두 하드링크 입력이다.
- **decompress 4.2.1의 `nested_symlink_write`는 실행마다 결과가 다르다.** 대상 프로그램의 확인과 사용 사이 경쟁 때문이며
  (판정기의 비결정성이 아니다, #406), 같은 조건 10회 중 8회 위반(C2)·2회 거부였다. 그래서 4.2.1의 위반 건수는 4/5 또는
  3/5가 될 수 있다(fork는 10회 모두 거부).
- **python-tarfile 결과는 필터 설정 비교다.** `fully_trusted`와 `data`의 차이는 같은 런타임 안의 설정 차이이고 Python 버전
  간 비교가 아니다.
- **oras-go 탐색은 입력 이름을 `d/` 아래로 옮겨 보낸다(P-3).** 이전에는 공통 seed에 oras-go 아티팩트 제목 접두(`d/`)가
  없어 대부분 거부됐다(seed 123·budget 20에서 20/20 거부). 이제 제품 탐색은 케이스는 그대로 두고 넘기는 TAR에서만
  상대 경로 엔트리 이름 앞에 `d/`를 붙인다. 엔트리 이름으로 추출 영역을 벗어나려면 `../`가 하나 더 필요하다. 확인은
  2.6.2에서 demo run 1회(추출 11/20, 위반 0)뿐이고 2.6.1은 실행하지 않았다. 연구 쪽 실행 경로는 옵션이 꺼진 채로
  이전과 같다. 컨트롤러는 failed·timed_out 실행의 위반 입력을 저장하지 않는다(판정은 ERROR로 닫힘).
- **replay**는 네 대상 모두 지원하지만, 실제 위반 케이스의 Docker 재현 E2E는 검증하지 않았다(합성 사례 기능 테스트만).
  네 대상 각각의 실제 실행은 0.2.0 릴리스 조건이다(D049).
- **탐색 재개(resume)는 없다.** 멈춘 탐색을 중간부터 이어 돌릴 수 없다.
- **표시 문제:** `live/`와 결과가 함께 있는 폴더에서 `status`가 "추출 성공 0건" 경고를 두 번 출력한다(판정·종료 코드 영향
  없음).
- **Runtime 계층의 한계(#466).** decompress·oras-go·python-tarfile 셸 런처는 정리 실패를 종료 코드에 반영하지 않고 Docker
  호출에 시간 제한이 없다(제품 계층은 사후 조회로 "정리 불명"을 경고). 런처 전체 실행에 시간 제한이 없다. Ctrl-C 때
  컨트롤러 쪽 `BrokenPipeError` traceback이 그대로 나온다. decompress의 개발용 직접 진입점은 Runtime 세션 없이 실행된다.
  python-tarfile의 "loop report has no steps"·"different runtime or filter"는 아직 종료 3이다.
- **환경.** 호스트에 Python 3.12가 필요하다. macOS 기본 `python3`(3.9)으로 `make`를 부르면 실행 전 점검 없이
  ImportError로 멈추므로 `PYTHON=python3.12`를 준다. `doctor`의 메모리 줄은 항상 UNKNOWN이다(종료 코드 무관). 클라우드 동기화
  폴더 감지는 폴더 이름 추측이다. `python -m inodefence`는 지원하지 않는다.

### 확인된 테스트·검증 범위

**병합 전 RC 스택 head에서 확인한 것**(#467, 독립 QA clean checkout `e71a534`; `e71a534..2b06730`은 README만):

- `make check` 5765 passed / 4 skipped, 기존 nodeid 삭제·상태 변화 0. GitHub CI(`check`, `container-integration`)는
  `e71a534`·`2b06730`에서 통과.
- 사용자 CLI 47건의 종료 코드가 PR 3 head `eca9bf8`과 같고, 출력 차이는 의도된 `--help` 6개와 `doctor`뿐이다.
- 위 설치 방식별 동작, 설정 파일 37경우, 실제 Docker를 대상으로 한 dry-run 25건(읽기 전용 조회만).
- 보호 영역(`src/inodefence/execution`·`model`, `scripts/`, `tools/`, `experiments/`, `.claude/`) diff 0, 공유 경로 해시
  16개와 레시피 지문 동일.
- **실제 대상 실행(Docker)은 이 head에서 하지 않았다.** 런처 인자·환경과 드라이버 실행부가 #466 이후 바뀌지 않아 아래 PR 3
  smoke로 대체했다.

**스택의 이전 커밋·브랜치에서만 확인한 것**(모두 engineering smoke 또는 demo run, WSL2 x86_64 호스트 한 대, Docker Engine
29.9.3, seed 123; 등록 실험 아님):

| 커밋 | 범위 | 결과 | 근거 |
| --- | --- | --- | --- |
| `a5499de` (RC와 코드 동일) | 네 대상 verify + explore 20회 | 위반 0, 미판정 0. 고정 입력은 네 대상 모두 전부 거부. 탐색 추출 성공 node-tar 17·python-tarfile 12·decompress 11·oras-go 0(경고) | [#457](https://github.com/TheWaitForAGI/InodeFence/pull/457) |
| `0e8e6c5` (PR 1) | 같은 범위 | RC와 판정·종료 분포·이미지 ID 동일. python-tarfile explore 1차는 `cleanup_inspect` 중단(종료 3, 결과 없음), 재실행 동일 | [#464](https://github.com/TheWaitForAGI/InodeFence/pull/464) |
| `b21ba0c` (PR 2) | 같은 범위 | 12/12 종료 0, RC와 판정·종료 분포·이미지 ID 동일 | [#465](https://github.com/TheWaitForAGI/InodeFence/pull/465) |
| `9a8d846` (PR 3) | 네 대상 explore 20회 | PR 2와 판정·종료 분포·이미지 ID·case-id 순서 동일, 추가 파일은 실행 기록뿐, 잔존 0 | [#466](https://github.com/TheWaitForAGI/InodeFence/pull/466) |

- 비정상 런처 종료(#466)는 네 대상 × 여덟 시나리오를 가짜 런처와 회귀 테스트로 확인했다(실제 Docker 아님). Ctrl-C·같은
  `--out` 재실행·잔존 이름 충돌은 PR 3 검증에서 실제 Docker로 확인했다(#466 본문).
- **고정 입력의 위반 관찰(#400 브랜치 `make target-run`, 2026-11-14, 이 스택에서는 다시 실행하지 않음):** node-tar 7.5.2 5건 중 2건 위반(하드링크, C1·C2), 7.5.3 위반 0(같은 시점 `make regression`과 입력별
  10/10 일치). python-tarfile 3.12.16 `fully_trusted` 5건 모두 위반, `data` 위반 0, `data` 고정 3.12.3·3.12.16 둘 다 위반 0.
  oras-go 2.6.1 6건 중 1건 위반(하드링크), 2.6.2 위반 0. decompress 4.2.1 5건 중 3~4건 위반, fork 11.1.4 위반 0. 맥북에서는
  새 클론으로 README 절차만 따라 이미지가 없는 상태부터 네 대상 여덟 셀을 준비→실행해 같은 판정을 얻었고, WSL2(#405
  브랜치)에서도 같은 결과와 `make check` 4874 passed / 8 skipped였다. 이 관찰들은 해당 고정 입력에 대한 것이며 다른
  입력·버전에 대한 주장이 아니다. 기록: [docs/LOG.md](docs/LOG.md) 2026-11-14 항목.
- 자동 준비는 #400 브랜치에서 node-tar 7.5.2·7.5.3(준비→실행)·7.4.4(준비·버전 확인만), python 3.12.16(준비→실행)·
  3.12.10(pull·버전 확인만), oras-go 2.6.1·2.6.2, decompress 두 패키지를 확인했다. node-tar의 나머지 lock 7개와
  exploratory registry 경로의 실제 실행 결과는 싣지 않는다.

**CI의 제품 E2E(`product-e2e`, P-2).** `pip install -e .`로 설치한 `inodefence`를 네 대상의 실제 추출기에 돌려 종료 코드와
`result.json`을 확인한다(`scripts/dev/product_e2e.py`, demo run). 네 대상 모두 추출 성공이 1건 이상이어야 통과한다.

**릴리스 시점에 확인하지 않은 것:** macOS 실행, x86_64 네이티브 Linux(WSL2가 아닌 Linux는 Ubuntu arm64 VM 한 대에서만 확인),
Python 3.11 이하, 여러 seed·예산·버전의 탐색, node-tar·oras-go·python-tarfile에서의 실제 위반 케이스 `replay`(decompress 한 건만
확인), README 빠른 시작을 문장 그대로 따라 한 실행(확인한 것은 USAGE의 설치 절차와 같은 명령들이다). 병합 전 RC 스택에서는
`replay`의 실제 Docker E2E도 확인하지 않았고, 그 뒤 2026-11-17~18의 깨끗한 클론 실행에서 `verify`·`explore`·`replay`의 실제
Docker 실행을 확인했다.

### 상세 문서

- [README.md](README.md): 설치, 빠른 시작, 설정, 종료 코드
- [docs/USAGE.md](docs/USAGE.md): 설치 방식별 차이, 설정과 출력 위치, 탐색·재실행, 종료 코드(`make target-run` 포함), 한계
- [docs/START_HERE.md](docs/START_HERE.md), [docs/STATUS.md](docs/STATUS.md): 현재 상태와 다음 할 일
- [docs/LOG.md](docs/LOG.md): 작업·검증 기록
- [scripts/README.md](scripts/README.md): `scripts/` 분류와 옮긴 경로
- [src/inodefence/README.md](src/inodefence/README.md): 패키지 구조
- PR 본문: [#457](https://github.com/TheWaitForAGI/InodeFence/pull/457),
  [#464](https://github.com/TheWaitForAGI/InodeFence/pull/464), [#465](https://github.com/TheWaitForAGI/InodeFence/pull/465),
  [#466](https://github.com/TheWaitForAGI/InodeFence/pull/466), [#467](https://github.com/TheWaitForAGI/InodeFence/pull/467)

### 라이선스

MIT License(D048, #392). 실험 대상 extractor와 의존성은 각자의 라이선스를 따른다.

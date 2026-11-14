# Changelog

이 파일은 InodeFence의 릴리스별 변경을 적는다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를,
버전은 [Semantic Versioning](https://semver.org/lang/ko/)의 0.x 규칙(0.x에서는 하위 호환을 약속하지 않음)을 따른다.

## [0.2.0] — 미발행

첫 번째로 태그를 다는 릴리스다. `pyproject.toml`은 2026-10-03부터 `0.1.0`이었지만 그 번호로 태그나 릴리스를 낸 적이
없고, 그동안 개발 중인 모든 상태가 `0.1.0`으로 설치됐다. 같은 번호가 서로 다른 코드를 가리키지 않도록 첫 태그는
`0.2.0`으로 한다.

### 할 수 있는 것

대상 프로그램과 버전을 주면 한 명령으로 다음을 끝낸다(호스트 터미널, Docker 필요):

1. 대상마다 일회용 격리 컨테이너에서 고정 입력 TAR를 하나씩 압축 해제한다.
2. 보호 대상 외부 파일과의 객체 동일성(C1)과 외부 영향(C2)을 판정한다.
3. 결과를 공통 형식 `inodefence-target-result-v1` 파일(`result.json`)과 입력 TAR(SHA-256 포함), 원시 기록으로 남긴다.
   기존 결과는 덮어쓰지 않는다.
4. 결과 파일 하나를 비전공자용 한 장 요약(Markdown: 대상·버전·판정·케이스별 결과·재현 방법)으로 바꾼다.

```bash
make target-run TARGET=node-tar TARGET_VERSIONS="7.5.2 7.5.3" PYTHON=python3.12   # WSL2: PYTHON=python3
PYTHONPATH=src python3.12 -m inodefence.target_result_summary <결과 폴더>/node-tar-7.5.2/result.json
```

### 지원 대상과 실제로 확인한 범위

모두 `demo run`이다(2026-11-14). 아래 "확인"은 이 고정 입력에서 이 결과가 나왔다는 관찰이며, 그 밖의
입력이나 버전에 대한 주장이 아니다.

| 대상 | 바꾸는 축 | 확인한 셀과 결과 |
| --- | --- | --- |
| `node-tar` | 대상 버전 | 7.5.2: 5건 중 2건 위반(하드링크 입력 2건, C1·C2). 7.5.3: 5건 모두 거부, 위반 0. 같은 시점 `make regression`과 입력별 결과 10/10 일치 |
| `python-tarfile` | 추출 필터 또는 런타임 버전(한 번에 하나만) | 3.12.16 `fully_trusted`: 5건 모두 위반. 3.12.16 `data`: 위반 0. `data` 고정 3.12.3·3.12.16: 둘 다 위반 0 |
| `oras-go` | 대상 버전 | 2.6.1: 6건 중 1건 위반(작업 디렉터리 기준 하드링크 입력). 2.6.2: 위반 0 |
| `decompress` | 버전 칸에 패키지까지(`decompress@4.2.1` 원본, `@xhmikosr/decompress@11.1.4` 유지보수 fork) | 원본 4.2.1: 5건 중 4건 위반(하드링크 2건 C1·C2, 심볼릭 링크 뒤 쓰기 C2). fork 11.1.4: 5건 모두 거부, 위반 0. 입력 1건은 실행마다 결과가 다름(한계 참고) |

**확인한 환경.** macOS(arm64) + Docker Desktop과 Windows + WSL2(x86_64) + Docker Desktop. node-tar·python-tarfile·
oras-go의 판정은 두 환경에서 모두 같았고, WSL2에서도 `make check`가 통과하고 한 장 요약이 정상으로 나왔다.
decompress는 맥북에서만 확인했다.

맥북의 깨끗한 클론에서 README 빠른 시작 순서 그대로 위 표의 node-tar·oras-go·decompress 여섯 셀과 python-tarfile
3.12.16 두 필터를 다시 돌려 같은 건수를 얻었다. 이미지는 이 맥에 이미 있던 것을 썼고, 같은 클론에서 README의 이미지
빌드 여섯 줄이 모두 성공하는 것은 따로 확인했다(새로 빌드한 이미지의 image id는 기존 이미지와 달랐다).

### 알려진 한계

- **입력은 하드링크 중심이다.** 고정 입력은 하드링크 2건과 심볼릭 링크 뒤 쓰기 3건(oras-go는 하드링크 1건 추가)뿐이고,
  `make target-run`은 입력을 바꿔 가며 탐색하지 않는다. node-tar와 oras-go에서 나온 위반은 모두 하드링크 입력이다.
- **decompress 4.2.1의 입력 1건(`nested_symlink_write`)은 실행마다 결과가 다르다.** 동시 쓰기 경쟁 때문이며, 같은
  조건 10회 중 8회 위반(C2)·2회 거부였다(fork는 10회 모두 거부, 나머지 입력은 안정). 그래서 4.2.1의 위반 건수는
  실행에 따라 4/5 또는 3/5가 될 수 있다.
- **python-tarfile 결과는 필터 설정 비교다.** `fully_trusted`와 `data`의 차이는 같은 런타임 안의 설정 차이이고, Python
  버전 간 비교가 아니다. 런타임 버전 축으로 본 3.12.3·3.12.16(`data`)은 둘 다 위반 0이었다.
- **통과(PASS)는 안전 증명이 아니다.** 시험한 입력과 관찰한 기준 안에서 위반이 안 보였다는 뜻이다. 위반은 위반
  후보이며, 확정 취약점으로 보려면 재현과 원인 분석이 따로 필요하다.
- **C0(경로 경계)는 이 명령에서 관찰하지 않는다.** 결과 파일에 `null`(관찰 안 함)로 남고, "위반 없음"으로 읽으면 안 된다.
- **실행은 `demo run` 수준이다.** 사전등록 실험이나 자격 검증 결과가 아니다.
- **대상 이미지는 로컬에 있어야 한다.** node-tar·oras-go·decompress 이미지는 각 환경에서 저장소의 Dockerfile로 직접
  빌드한다(arm64와 x86_64 사이에 옮겨 쓸 수 없다). 새로 빌드한
  이미지는 팀이 기록에 쓴 이미지와 image id가 다를 수 있고, 결과 파일의 `provenance.image_id`가 그 차이를 남긴다.
- **docker가 도는 셸(macOS 터미널 또는 WSL 셸)에서 실행한다.** Dev Container 안에는 docker가 없다.
- **호스트에 Python 3.12가 필요하다.** macOS 기본 `python3`(3.9)로는 돌지 않는다(WSL2 Ubuntu 24.04의 `python3`은 3.12).
- WSL2가 아닌 Linux 호스트에서는 따로 확인하지 않았다.

### 라이선스

MIT License(D048, #392). 실험 대상 extractor와 의존성은 각자의 라이선스를 따른다.

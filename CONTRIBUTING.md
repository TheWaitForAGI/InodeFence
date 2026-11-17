# 기여 가이드

사람과 코딩 에이전트가 함께 쓰는 개발 절차다. 에이전트의 행동 규칙·권한·병합 운영·안전·연구 무결성은
[AGENTS.md](AGENTS.md)에 있고, 여기서는 개발 환경과 검사 명령, 브랜치에서 병합 요청까지의 흐름만 다룬다.
처음이면 [docs/START_HERE.md](docs/START_HERE.md) → [docs/STATUS.md](docs/STATUS.md) → [AGENTS.md](AGENTS.md) 순으로
읽는다. 용어는 [docs/GLOSSARY.md](docs/GLOSSARY.md), 설계 이유는 [docs/DECISIONS.md](docs/DECISIONS.md)에 있다.

```text
Issue / Task Contract → Branch → 구현 → 로컬 검사(make check) → PR → CI → 독립 검증 → 권한 있는 병합
```

## 개발 환경

- 기준 환경은 저장소 Dev Container(Ubuntu 24.04, Python 3.12)다. 컨테이너를 만들 때 `.devcontainer/post-create.sh`가
  `pip install -e '.[dev]'`와 `make target-tools`를 실행한다. 직접 설치할 때는 `make install`(개발 의존성 포함
  editable 설치)과 `make target-tools`(`tools/node-tar`의 고정 의존성, Node 필요)를 쓴다.
- 환경 확인은 `make env-check`다. filesystem 실험 공간은 `$INODEFENCE_RUNTIME_ROOT`(기본 `/var/lib/inodefence`)이며
  소스 bind mount를 실험 공간으로 쓰지 않는다.
- Docker로 대상을 실행하는 명령(`inodefence verify`·`explore`, `make demo` 등)은 docker가 도는 호스트 셸에서 실행한다.
  Dev Container 안에는 docker가 없다. 사용법은 [docs/USAGE.md](docs/USAGE.md)에 있다.
- 모든 텍스트 파일은 LF 줄바꿈을 쓴다. Python은 `pathlib.Path`와 표준 라이브러리 filesystem API를 우선하고, 셸 고유
  동작에 기대지 않는다.

## Issue와 Task Contract

[Issue Forms](.github/ISSUE_TEMPLATE/)로 목표, 수정 가능·금지 영역, 입력·출력, 완료 조건을 정한다. 사람이 직접 준
작업 명세도 Task Contract로 쓸 수 있으며, 그 출처를 PR에 남긴다. 병렬 작업은 담당 영역을 미리 나누고 서로의
interface 변경은 PR로 알린다. 하위 폴더의 scoped `AGENTS.md`가 있으면 함께 따른다.

## 브랜치와 PR

- `main`에서 직접 개발하지 않는다. 브랜치 이름과 스택 PR 규칙은 [AGENTS.md의 PR 절](AGENTS.md#pr)을 따른다.
- 한 PR에는 한 목적만 둔다. 관계없는 문서 수정·refactor·기능을 섞지 않는다(예: model·mutator·oracle·README를 한
  PR에 몰아 넣지 않는다).
- PR 설명의 첫 항목은 "이 PR을 병합하면 무엇을 실제로 실행하거나 검증할 수 있게 되는가"에 대한 답이다. 그 밖에 관련
  Issue, 실제로 실행한 검사와 결과, 실행하지 않은 검사, 사람이 확인한 설계 판단을 적는다.

## 로컬 검사

PR 전에 Dev Container에서 실행한다.

```bash
make check
```

`make check`는 다음을 순서대로 실행하며 CI의 `check` job과 같은 명령이다.

| 단계 | 개별 명령 | 실제로 하는 일 |
| --- | --- | --- |
| lint | `make lint` | `ruff check .` |
| format | `make format-check` | `ruff format --check .` |
| 타입 | `make typecheck` | `pyright` |
| 테스트 | `make test` | `pytest` |
| 환경 | `make env-check` | `scripts/check_dev_env.py` |
| 문서 | `make docs-check` | 필수 문서와 Markdown 상대 링크 경로 확인(`scripts/dev/check_docs.py`, 앵커는 검사하지 않음) |
| 증거 연결 | `make evidence-chain` | validated summary의 raw 포인터가 커밋된 manifest·파일을 가리키는지 확인 |

안전한 TAR baseline 재생성은 `make fixtures`, 수동 관찰은 `make probe CASE=hardlink`(기본 `regular-file`, 네 baseline
case만 허용)다.

## CI

`.github/workflows/ci.yml`의 `CI` workflow가 모든 PR과 `main` push에서 돈다.

- **`check`**: Ubuntu 24.04, Python 3.12, `INODEFENCE_RUNTIME_ROOT=/var/lib/inodefence`에서 `make target-tools` →
  `make install` → `make check`. 실패하면 로컬에서 같은 `make` 단계를 다시 실행해 재현한다.
- **`container-integration`**: 신뢰된 컨트롤러를 만들어 실제 컨테이너 경계 회귀, 고정 Node 이미지의 효과 producer smoke
  (`make node-tar-effect-check`), 작은 node-tar 효과 demo를 실행하고 산출 증거를 artifact로 올린다. Docker가 필요해 Dev
  Container에서는 재현되지 않으므로, 실패 단계 이름과 올라온 증거를 먼저 읽고 docker 호스트에서 재현한다.
- **`product-e2e`** (대상별 4개): `pip install -e .`로 설치한 `inodefence` 명령을 실제 추출기에 돌린다
  (`scripts/dev/product_e2e.py`). 대상마다 고정 버전 하나에 `verify` → 작은 `explore`(budget 20) → `status` → `summary`를
  실행하고 종료 코드와 `result.json`을 확인한다. 사용자와 같은 드라이버·런처를 쓰며 demo run이다. 공개 로그이므로
  FAIL 판정이 나오면 사실만 출력하고 케이스 내용은 출력하지 않는다. Docker 호스트에서
  `python scripts/dev/product_e2e.py --target <대상> --out <빈 폴더>`로 재현한다.
  **이 job을 병합 요청의 필수 조건으로 채택할지는 아직 정하지 않았다**(지웅 결정 대기). 지금의 필수 조건은 위 두 job이다
  ([AGENTS.md PR 절](AGENTS.md#pr)). 이 job은 Docker 데몬과 이미지 준비용 외부 네트워크에 의존하므로, 필수로 삼으면 코드와
  무관한 레지스트리·네트워크 장애도 병합을 막는다. 실패하면 원인이 코드인지 인프라인지 PR에 적는다.
- `repro-evidence`·`experiment-fanout`은 수동 실행(`workflow_dispatch`) workflow이며 PR 검사가 아니다.

CI가 실패한 상태로 병합을 요청하지 않는다.

## 독립 검증과 병합

- CI를 통과한 PR은 작성자가 아닌 검토자(verifier 에이전트 또는 사람)가 architecture 경계와 연구 규칙을 확인한다.
- PR의 HEAD SHA가 바뀌면(커밋 추가, merge-in) 이전 검증 결과를 재사용하지 않고 최신 SHA에서 CI와 변경분을 다시
  검증한다([D037](docs/DECISIONS.md#d037--수술-기간-병합-정책github-브랜치-보호)).
- 병합은 권한 있는 사람이 한다(현재는 지웅). 운영 규칙은 [AGENTS.md의 PR 절](AGENTS.md#pr), 결정 원문은
  [D037](docs/DECISIONS.md#d037--수술-기간-병합-정책github-브랜치-보호)에 있다.

## 리뷰 완료 조건

검토자가 PR 설명과 diff만 보고 다음에 답할 수 있어야 한다. 답할 수 없으면 병합 전에 구조나 문서를 단순하게 만든다.

- 목적이 하나이고, 무엇을 실행·검증할 수 있게 되는지 명확한가.
- 이 코드는 어느 계층(pipeline 단계, 드라이버, CLI)에 속하고, 입력·출력은 무엇인가. 아키텍처 경계를 지키는가.
- target-specific 로직이나 CVE별 처리가 generic module(mutation·observer·oracle·feedback)에 섞이지 않았는가.
- 어떤 Security Contract와 관련 있고, 실패하면 어느 테스트가 잡는가. 새 동작에 테스트가 있는가.
- `make check`가 통과했고, 실행하지 않은 검사는 그렇다고 적혀 있는가.
- 아래 문서 변경 기준에 해당하는 문서가 같은 PR에서 갱신됐는가.

## 문서 변경 기준

공통 data model·interface, Security Contract, target 우선순위, 실험 방법론, 프로젝트 범위, 큰 설계 결정, 현재 단계·다음
작업, 프로젝트 이해 흐름이 바뀌면 코드만 병합하지 않고 관련 문서를 같은 PR에서 고친다. 어느 문서를 고치는지는
[AGENTS.md의 변경 영향 규칙](AGENTS.md#변경-영향-규칙)에, 작업 기록 방식(STATUS 갱신·LOG 한 줄)은
[AGENTS.md의 금지 절](AGENTS.md#금지)에 있다. 실험 결과는 [summaries 규칙](experiments/summaries/README.md)에 따라
raw → validated summary → finding으로 연결하고, 공개 전 finding은 [SECURITY.md](SECURITY.md)를 따른다.

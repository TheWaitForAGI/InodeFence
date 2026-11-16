# InodeFence

**TAR 압축 해제 뒤의 filesystem 보안 상태(객체 identity·외부 영향)를 관찰하고 판정하는 extractor 검사 도구이자,
그 상태를 탐색 feedback으로 쓰는 연구 프로토타입**

InodeFence는 TAR 입력을 만들고 변형해 실제 extractor(압축 해제 프로그램)를 격리 컨테이너에서 실행하고, 실행 전후의
filesystem 상태를 관찰해 보안 경계 위반을 판정합니다. 사용자 진입점은 `inodefence` 명령(`doctor`, `targets`,
`verify`, `explore`, `status`, `replay`, `summary`)입니다. 버전은 0.2.0 (릴리스 후보, 태그·릴리스 없음)입니다.
이 문서는 0.2.0 릴리스 후보 브랜치 기준이며 태그·릴리스 전입니다.

[빠른 시작](#빠른-시작) · [사용 안내](docs/USAGE.md) · [현재 상태(Capability Ledger)](docs/STATUS.md) ·
[시작 안내](docs/START_HERE.md) · [Security Contracts](docs/research/design/security-contracts.md) ·
[개발 참여](CONTRIBUTING.md) · [보안 정책](SECURITY.md)

## 어떤 보안 문제를 푸는가

TAR는 파일 내용과 함께 경로, 링크, 처리 순서를 담고, 압축 해제는 이 정보로 실제 filesystem을 바꿉니다. 신뢰할 수
없는 archive를 풀 때는 지정된 extraction root(압축 해제 목적지) 밖의 파일이 보호되어야 합니다. 기본 질문은
"archive 안의 경로가 extraction root 밖으로 나갔는가?"입니다. InodeFence는 한 가지를 더 묻습니다.

> 경로가 내부에 있어 보여도, 결과적으로 외부 파일 객체와 연결되거나 외부 상태에 영향을 준 것은 아닌가?

```text
extract/result.txt ─┐
                   ├── 같은 filesystem object      (개념 예, 실제 취약점 재현 아님)
outside/sentinel ──┘
```

두 경로가 같은 파일 객체를 가리키면 내부 파일에 대한 쓰기가 외부 파일에도 닿습니다. hardlink가 대표적인 예이고,
symlink도 경로가 실제로 향하는 대상을 바꿉니다. `outside/sentinel`은 실제 사용자 파일이 아니라 disposable
sandbox(실행 후 버리는 실험 공간) 안의 **실험용 보호 파일**입니다.

## 경로 중심 검사와 무엇이 다른가

경로 문자열만 보는 검사는 "어디에 썼는가"를 봅니다. InodeFence의 Observer는 **객체 사이의 관계와 변화**를
기록합니다. 판정은 압축 해제 전후 snapshot으로 하고, 탐색 feedback은 그에 더해 entry별 중간 상태(trace)도 근거로
씁니다. 기록하는 것: path·type, `st_dev`/`st_ino`(같은 객체인가), `st_nlink`, mode·size, symlink
link text(`lstat`만, referent를 따라가지 않음), content hash, 보호 sentinel의 전후 상태. raw inode 번호보다
"내부 파일과 외부 sentinel이 같은 객체다", "외부 sentinel의 내용이 변했다" 같은 관계가 판정과 탐색에 쓰입니다.

Oracle은 이 관찰을 일반화된 Security Contract와 비교합니다. 특정 CVE 식별자나 PoC byte sequence를 조건으로
쓰지 않습니다. 정확한 정의는 [security-contracts.md](docs/research/design/security-contracts.md)가 기준입니다.

| ID | Contract | 뜻 | 상태 |
| --- | --- | --- | --- |
| C0 | Path Boundary Confinement | extraction root 밖의 persistent namespace 생성·삭제·identity/type 교체가 없어야 함 | 구현 (기본 검사, 신규 기여로 주장하지 않음) |
| C1 | Object Identity Confinement | 내부 객체가 보호된 외부 sentinel과 같은 객체를 공유하면 안 됨 | 구현 (post-state `lstat` identity) |
| C2 | External Effect Noninterference | 외부 sentinel의 내용·metadata가 의도치 않게 변하면 안 됨 | 구현 (sentinel 전후 비교) |
| C3 | Extraction Root Integrity | 목적지 자체가 교체·redirect되면 안 됨 | 설계만, 미구현 |
| C4 | Check/Use Coherence | 검증한 대상과 실제 operation 대상이 일관되어야 함 | instrumentation이 필요한 후속 단계 |

C0/C1/C2는 **persistent snapshot** 판정입니다. 두 capture 사이의 일시적 operation, sandbox 밖 접근, direct-use,
symlink referent identity, inode 재사용은 완전히 판정하지 못합니다. **위반 없음(`violated=False`)은 관찰 범위 안에
증거가 없다는 뜻이며 안전성 증명이 아닙니다.**

탐색 루프와 책임 분리:

```text
Seed / ArchiveCase → Structure Mutator → TAR Builder → Target Adapter
  → State Observer → Security Oracle → Feedback / Corpus → 다음 mutation
```

**Observer = 사실 기록 · Oracle = 계약 판정 · Feedback = 탐색 가치 판단.** 새롭거나 탐색 가치가 있는 상태가 곧
취약점은 아닙니다(Interesting ≠ Vulnerable). 대상별 실행 로직은 adapter에 두고 generic mutation·observer·oracle·
feedback에 특정 target/CVE 로직을 섞지 않습니다. 상세는 [architecture.md](docs/research/design/architecture.md),
모듈 지도와 내부 API 예는 [src/inodefence/README](src/inodefence/README.md)에 있습니다.

## 지금 구현·검증된 것

능력과 증거 수준의 단일 기준은 [STATUS의 Capability Ledger](docs/STATUS.md)입니다. 수준 어휘(DESIGNED ·
IMPLEMENTED · TESTED · VALIDATED)는 [Research Contract](docs/research/design/research-contract-v1.md)를 따릅니다.
아래 다섯 종류의 주장은 서로 다르며, 섞어 읽지 않습니다.

| 종류 | 현재 상태 | 근거 |
| --- | --- | --- |
| (1) 알려진 CVE의 **통제 재현** | TESTED. node-tar 5 릴리스 × 고정 입력 2개의 통제 차분: 최상위 hardlink는 7.5.2에서 외부 참조 파일과 inode 공유(nlink 1→2)·7.5.3 거부, 중첩 hardlink는 7.5.6 공유·7.5.7 거부(7.5.8도 거부). 판정은 observed이고, 각각 CVE-2026-23745·CVE-2026-24842에 대응한다는 것과 회귀 원인은 inferred. **통제 재현이며 퍼저의 탐색 결과가 아닙니다.** | [`experiments/repro/evidence/summary.json`](experiments/repro/evidence/summary.json) → [cross-release-identity-repro-v1](experiments/summaries/cross-release-identity-repro-v1.md) → Ledger M2 |
| (2) generic Oracle이 **알려진 위반을 판정** | TESTED. identity oracle 하나가 위 두 쌍을 릴리스 id·정답 경로 하드코딩 없이 구분하고, 손 probe 판정과 production Observer+Oracle 판정이 일치. oracle·adapter 수준에서 3 추출기에 적용: Python `tarfile`은 필터 토글 비교(`fully_trusted` → C1+C2, `data` → 거부), oras-go·decompress는 adapter 통제 차분(#176·#177) | `tests/test_cross_release_oracle_agreement.py`, `tests/test_python_tarfile_generality.py`, Ledger M2.2·M4 |
| (3) 퍼저의 **자력 발견** | 본실험 결과 자리(봉인 해제 뒤 기입) | [사전등록](experiments/preregistration/) exp3-v1·exp2-v1, Ledger M3 |
| (4) 통계적으로 입증된 **성능 우위** | 주장하지 않음. 본실험 결과 자리(봉인 해제 뒤 기입) | — |
| (5) **미검증 기능·가설** | C3·C4 미구현. entry 단위 native 전이 관찰은 관찰 경계를 확보하지 못해 미구현(honest negative). `replay`의 실제 위반 케이스 E2E는 미검증. FAST 실행 프로필 없음. macOS·기타 Linux 호스트는 이 후보에서 미확인 | Ledger, [사용 안내 한계](docs/USAGE.md#한계와-주의) |

그 밖에 TESTED인 것: 실제 node-tar 루프(입력 → 격리 실행 → entry별 중간 상태 관찰 → C0/C1/C2 → feedback → 다음
mutation 선택)가 `make demo`(node-tar 7.5.22, 정상 입력)로 돌고 같은 seed·budget이면 재현됩니다. 이 데모의 정상
입력에서 위반은 0건입니다. 위 어느 것도 퍼저가 취약점을 찾았거나 재발견했다는 주장이 아닙니다.

## 지원 대상과 검증 수준

`inodefence targets`가 지원 목록의 기준입니다. 네 대상 모두 고정 입력 회귀(`verify`)·이미지 자동 준비·탐색
(`explore`)을 지원하고, 위반 케이스 재실행(`replay`)은 현재 node-tar만 지원합니다.

| 대상 | 대상 옵션 | `replay` | 비고 |
| --- | --- | --- | --- |
| node-tar | — | 지원 (실제 위반 E2E 미검증) | 7.5.23은 `verify`에서 exploratory 버전으로 표시 |
| python-tarfile | `--extraction-filter` | 미지원(종료 4) | |
| decompress | — | 미지원(종료 4) | `--version`에 패키지까지: `@xhmikosr/decompress@11.1.4` |
| oras-go | — | 미지원(종료 4) | **실험적**: 공통 seed가 `d/` 접두 없이 생성돼 탐색 실행 대부분이 거부됨. 유의미한 보안 커버리지를 주장하지 않음 |

대상 실행을 확인한 호스트는 **Windows + WSL2(Ubuntu 24.04, x86_64) + Docker Desktop 호스트 한 대**입니다. macOS와
그 밖의 Linux 호스트는 이 후보에서 확인하지 않았습니다. 네 대상의 실제 실행은 이 스택 head가 아니라 **이전 커밋
(`a5499de`; 이후 PR 1·2 커밋에서 같은 범위, PR 3 커밋에서는 `explore`만 재확인)에서의 engineering smoke(demo run)**입니다(seed 123, `verify` 5~6
입력·`explore` budget 20). 그때 네 대상 모두 실행을 끝냈고 위반 0건이었습니다. 이후 변경은 런처 인자·환경과 드라이버
실행부를 바꾸지 않았고, 이 head에서는 실제 대상 실행을 하지 않았습니다([CHANGELOG](CHANGELOG.md)의 검증 범위). **위반 0은 안전성 증명이 아니며**, `verify`의 고정
입력은 모두 공격 형태라 정상 입력 대조군이 없습니다. 대상별 수치·종료 상태 분포·한계는
[사용 안내: 지원 환경과 확인 수준](docs/USAGE.md#지원-환경과-확인-수준)에 있습니다. 이 문서의 실행 예는 모두 `demo run`
수준이며 사전등록 실험이나 자격 검증 결과가 아닙니다.

## 설치 요구사항

- **Python 3.12** (`requires-python >=3.12,<3.13`; 3.13에서는 `pip`이 설치를 거부합니다).
- **Docker**: 대상 실행(`verify`·`explore`·`replay`)과 이미지 준비에 필요합니다. `--dry-run`·`status`·`summary`에는
  필요 없습니다.
- **저장소 클론**: 대상을 돌리는 명령은 이미지 레시피(`tools/`)와 셸 런처(`scripts/`)가 있는 클론이 꼭 필요합니다.

| 명령 | `pip install -e .`(클론에서) | `pip install .`(wheel)만 | wheel + `INODEFENCE_HOME=<클론>` |
| --- | --- | --- | --- |
| `--version`, `status`, `summary` | 됨 | 됨 | 됨 |
| `doctor` | 됨 | 실행되지만 repository `FAIL`(종료 1) | 됨 |
| `targets`, `verify`, `explore`, `replay` | 됨 | 안 됨: "repository not found", 종료 3 | 됨 |

설치 방식별 세부(어느 코드가 도는지, 이전 레이아웃 클론 거부 등)는 [사용 안내: 설치](docs/USAGE.md#설치)에 있습니다.

## 빠른 시작

처음 한 번은 이 순서로 갑니다. 대상 실행을 확인한 호스트는 Windows + WSL2(Ubuntu 24.04, x86_64) + Docker Desktop 호스트 한 대뿐입니다.

```bash
# 1. 설치: 저장소 클론에서, Python 3.12
git clone https://github.com/TheWaitForAGI/InodeFence.git InodeFence && cd InodeFence
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e .

# 2. 환경 점검: FAIL 줄은 그 줄의 안내대로 고치고 다시 실행합니다(종료 0 = FAIL 없음)
inodefence doctor

# 3. 추출기와 각 추출기가 지원하는 것
inodefence targets

# 4. 계획만 보기: 아무것도 내려받거나 빌드하거나 실행하지 않습니다
inodefence verify  --target node-tar --version 7.5.23 --dry-run
inodefence explore --target node-tar --version 7.5.23 --budget 20 --seed 123 --dry-run

# 5. 실제 실행(Docker 필요). 이미지가 없으면 --auto-prepare가 Docker로 빌드합니다(네트워크 사용)
inodefence verify  --target node-tar --version 7.5.23 --auto-prepare
inodefence explore --target node-tar --version 7.5.23 --budget 20 --seed 123 --auto-prepare

# 6. 결과 보기(기본 출력 폴더; 바꾸려면 --out 또는 INODEFENCE_OUTPUT_DIR)
inodefence status ~/inodefence-target-run
inodefence status ~/inodefence-explore
inodefence summary ~/inodefence-explore/target-explore/7.5.23-123-20-result/result.json
```

- 출력은 저장소 밖에 씁니다. 같은 출력 폴더에 같은 실행의 결과가 이미 있으면 덮어쓰지 않고 종료 3으로
  거부하므로, 다시 돌릴 때는 `--out`을 바꿉니다.
- `explore`의 실제 실행에는 `--auto-prepare`가 필수입니다(없으면 아무것도 실행하지 않고 이유를 출력). `verify`는
  이미지가 없을 때 `--auto-prepare`가 있어야 빌드합니다. 빌드는 Docker와 네트워크를 씁니다.
- node-tar 7.5.23은 `verify`에서 exploratory 버전(고정 입력의 기대값이 이 버전용으로 확정되지 않음)으로 표시됩니다.

## 주요 CLI 명령

| 명령 | 하는 일 | 종료 코드 |
| --- | --- | --- |
| `inodefence doctor` | 환경 점검(`OK`·`FAIL`·`WARN`·`INFO`·`UNKNOWN`)과 고치는 법. 확인하지 못한 것은 `OK`가 아니라 `UNKNOWN`. 읽기만 함 | 0 FAIL 없음, 1 FAIL 있음 |
| `inodefence targets [--json]` | 추출기와 각 추출기가 지원하는 것 | 0 정상, 3 저장소 없음·설정 파일 오류 |
| `inodefence verify --target T --version V` | 고정 입력 회귀(`--version` 반복 가능) | 0 PASS, 1 FAIL, 2 ERROR, 3 실행 전 거부 |
| `inodefence explore --target T --version V [--budget N] [--seed S] [--quiet\|--verbose]` | 상태 기반 feedback 탐색(기본 budget 20, seed 123). 실행 중 진행 줄을 stderr에 출력(`--quiet` 없음, `--verbose` 런처 원시 출력) | 0 PASS, 1 FAIL, 2 ERROR, 3 실행 전 거부 |
| `inodefence status <폴더>` | 실행 중 진행·위반 케이스, 끝난 뒤 판정 | 0 표시, 2 보일 것 없음·읽기 실패 |
| `inodefence replay <위반 케이스 폴더> [--rounds 3]` | 위반 케이스를 같은 이미지에서 다시 돌려 재현 비율 기록 | 0 완료, 1 미완료, 2 재실행 불가, 3 실행 전 멈춤, 4 미지원 |
| `inodefence summary <result.json> [-o 파일]` | 결과를 한 장짜리 Markdown 요약으로(입력 TAR SHA-256 재대조) | 0 작성, 2 읽기·쓰기 실패 |

공통 옵션: `--dry-run`(계획만), `--out <폴더>`(저장소 밖), `--auto-prepare`, `--image-tag-suffix`. 각 명령의 옵션과
종료 코드는 `--help` 끝에 있습니다. 판정(0 PASS·1 FAIL·2 ERROR)과 실행 전 거부(3)는 다른 뜻이며, `verify`·
`explore`·`replay`는 사용법 오류도 "아무것도 실행하지 않음"인 3으로 냅니다. 전체 표는
[사용 안내: 종료 코드](docs/USAGE.md#종료-코드)에 있습니다.

## 출력 결과와 재현

`explore`는 실행 중 `<--out>/target-explore/<실행>/live/`에 진행 스냅샷 `progress.json`과 위반 케이스
`violations/run-NNNNNN/`을 **발생 즉시** 쓰고, 끝나면 `<실행>-result/`에 공통 형식 `result.json`
(`inodefence-target-result-v1`)과 `summary.md`를 씁니다. 탐색이 중간에 멈춰도 그때까지 쓴 위반 케이스는 남습니다
(이어 하기는 아직 없습니다).

- 위반 케이스 폴더에는 그 실행의 정확한 입력 `input.tar`와 `case.json`(케이스·seed·적용된 변이, C0/C1/C2 판정,
  종료 상태, fingerprint, 입력 SHA-256, 이미지 id, 다시 돌리는 명령)이 있습니다.
- 추출기의 종료 상태(success·rejected·failed·timed_out)와 오라클 판정은 별개 축입니다. 위반이 보이면 종료 상태와
  상관없이 위반이고, 위반 없음을 깨끗한 음성으로 셀 수 없는 실행은 **미판정**으로 셉니다. 대상별 규칙은
  [사용 안내](docs/USAGE.md#종료-상태와-판정은-별개입니다)에 있습니다.
- **위반은 위반 후보이지 확정된 취약점이 아닙니다.** `inodefence replay`가 `case.json`에 기록된 정확한 이미지에서
  다시 돌려 같은 계약 위반·fingerprint 일치 비율을 케이스 폴더 옆 `run-NNNNNN.replay-<UTC>/replay.json`에 씁니다.
  그 이미지가 없으면 다른 이미지로 바꾸지 않고 멈춥니다.

도중 확인, 케이스 폴더 읽기, 재실행 증거 보존, 인프라 중단 진단 줄의 상세는 [사용 안내](docs/USAGE.md)에 있습니다.

## 설정

설정은 두 키뿐입니다: `INODEFENCE_HOME`(클론 위치; editable 설치면 자동)과 `INODEFENCE_OUTPUT_DIR`(출력 기준
폴더, 절대 경로; 기본 출력은 `~/inodefence-target-run`·`~/inodefence-explore`). 환경 변수가 설정 파일보다
우선하고, 설정 파일은 `~/.config/inodefence/config.env`(또는 `$XDG_CONFIG_HOME/inodefence/config.env`, 다른 파일은
`INODEFENCE_CONFIG`)입니다. 형식은 [`.env.example`](.env.example)에 있습니다. 저장소 루트의 `.env`는 읽지 않고,
파일을 셸로 실행하지 않습니다. 적용된 값과 출처는 `inodefence doctor`가 보여 줍니다.

**설정 파일로 실험 조건을 바꿀 수 없습니다.** 그 밖의 키(seed·budget, `INODEFENCE_RUNTIME_ROOT` 등)는 오류로
거부합니다. seed·arm·budget·실행 SHA·격리 정책은 명령 옵션이나 동결된 사전등록 파일에서만 옵니다. 거부 규칙
전체는 [사용 안내: 설정과 출력 위치](docs/USAGE.md#설정과-출력-위치)에 있습니다.

## 보안 및 실행 제한

- 실제 host의 민감 파일, SSH key, 사용자 문서, secret을 실험 대상으로 쓰지 않습니다. disposable sandbox와 실험용
  sentinel만 쓰고, 파괴적인 filesystem 작업은 runtime sandbox 안으로 제한합니다.
- 대상 추출기는 격리 컨테이너에서 돕니다. 지원하는 실행 프로필은 STRICT 하나이며 격리를 완화하는 옵션은 없습니다.
- **출력은 저장소 밖이어야 합니다.** `--out`이 저장소 안이면 실행 전에 거부합니다(위반 입력이 공개 저장소에 섞이지
  않도록). 클라우드 동기화 폴더도 피하세요.
- **책임 있는 공개:** 미공개로 보이는 문제를 찾으면 공개 저장소에 올리기 전에 해당 추출기의 유지보수자에게 먼저
  알립니다. 확인되지 않은 finding은 공개 Issue에 올리지 않고, vendor coordination 전 exploit/PoC를 public branch에
  commit하지 않습니다. Git 이력과 CI 로그도 공개될 수 있는 자료로 취급합니다. 기준은 [SECURITY.md](SECURITY.md)입니다.
- 탐색 수치 중 공개 권고문의 영향 범위 안에 있는 특정 버전의 것(위반 수·종료 상태 분포 등)은 문서에 적지 않습니다.
- 에이전트·개발자가 지키는 안전 규칙과 연구 불변식은 [AGENTS.md](AGENTS.md)에 있습니다.

## 연구 질문, 성과와 한계

핵심 연구 질문([research-questions v2](docs/research/design/research-questions.md)):

> 피해 경로 이름을 아는 **동일 어휘·동일 예산** 아래서, filesystem security state(C1 identity·C2 effect)를
> retention·스케줄링 피드백으로 쓰는 탐색이 **무작위 탐색**과 **구조 커버리지 탐색**보다 첫 경계위반까지의
> 실행 수를 줄이고 고유 위반 입력을 더 많이 찾는가?

위협 모델은 공격자가 피해 경로 이름(보호 대상 외부 객체의 추출 루트 기준 상대 경로)을 알고, 세 arm 어휘에 그
이름이 똑같이 들어간다고 전제합니다. blind 발견을 주장하지 않으며, CVE PoC·고정 공격 패턴·대상 경로·sentinel 이름은
oracle·feedback에 넣지 않고, 알려진 CVE PoC를 탐색의 기본 seed로도 쓰지 않습니다.

- **H-A (주 가설):** 어휘·seed·예산·이미지·oracle·operator 선택(uniform)이 같고 retention 정책만 다른 세 arm —
  **R**(무작위), **D**(구조 커버리지), **S-u**(identity/effect/boundary-attempt 상태 retention) — 을 비교합니다.
  1차 지표는 **T_first**(첫 C1 ∨ C2까지 실행 수, 우측중도절단 생존분석)와 **U_viol**(정규화 서명 기준 고유 위반
  입력 수)입니다. 사전등록(EXP-3·EXP-2)은 Git에 동결돼 있습니다. 결과: 본실험 결과 자리(봉인 해제 뒤 기입).
- **H-B:** CVE 문자열·버전·PoC 바이트를 넣지 않은 generic C0/C1/C2가 여러 추출기의 취약/수정 쌍을 손 fixture로
  구분하는가 — 위 (1)·(2)의 통제 차분이 그 근거입니다.
- **H-C (보조):** 어휘 음성 통제. 감사 이후 이를 검정한 실행은 없습니다.

초기 비교는 arm 간 어휘가 달라 폐기했습니다(이전 기록은 [STATUS archive](docs/archive/pre-20261103-results.md)).

**새롭다고 주장하지 않는 것.** 다음 각각은 그 자체로 InodeFence의 기여가 아닙니다: TAR fuzzing, feedback-guided
fuzzing, hardlink·symlink 공격, path traversal, entry order mutation, filesystem-state observation, outside-root write
detection. Jana & Shmatikov, ZIPDiff, LinkZard, Wormholes 등이 관련 요소를 이미 다룹니다. 기여 여부는 선행연구 비교,
baseline, ablation, 사전등록 실험으로 평가하며, 그 전에는 우위나 새로움을 주장하지 않습니다
([related-work-positioning](docs/research/design/related-work-positioning.md)).

**범위.** TAR extraction, Linux filesystem 의미론, regular file·directory·hardlink·필요한 범위의 symlink, entry
path·type·link target·순서·의존 관계 변형. 연구 MVP 대상은 node-tar 7.5.2/7.5.3·7.5.6/7.5.7과 Python `tarfile`
`fully_trusted`/`data`이고, 자력 발견 실험 대상은 node-tar 하나입니다. decompress는 확장, oras-go는 oracle 일반성
증거로만 씁니다(D038). GNU tar, entry 전이 관찰 계열, 모든 archive format, Windows NTFS, kernel 취약점 일반, 전체
TOCTOU/race 분석, full symbolic execution은 다루지 않습니다. 실행 중 외부 process가 filesystem을 바꾸는 race 모델도 제외합니다
([project-scope](docs/research/design/project-scope.md), [threat-model](docs/research/design/threat-model.md)).

**raw 결과 ≠ 논문 주장.** 실행 로그에 보인 현상을 바로 연구 결론으로 쓰지 않습니다. 위반 후보는 재현·최소화·원인
분석을 거치고, 측정 결과는 설정과 원본 근거(raw + SHA-256 목록)를 연결해 검토한 뒤 씁니다
([experiments](experiments/README.md), [findings](findings/README.md), [paper](paper/README.md)).

## 문서, 개발 참여, 라이선스

| 읽는 목적 | 문서 |
| --- | --- |
| `inodefence` 상세 사용법(설정, 출력, 탐색·도중 확인, 재실행, 종료 코드, 한계) | [docs/USAGE.md](docs/USAGE.md) |
| 처음 프로젝트 이해하기, 개발용 명령(`make demo` 등) | [START_HERE](docs/START_HERE.md) |
| 현재 능력과 다음 작업 | [STATUS](docs/STATUS.md) · [BACKLOG](docs/BACKLOG.md) |
| 실제 실행 기록 | [LOG](docs/LOG.md) |
| 변경 내역 | [CHANGELOG](CHANGELOG.md) |
| 연구 계약·질문·선행연구 | [Research Contract v1](docs/research/design/research-contract-v1.md) · [research-questions](docs/research/design/research-questions.md) · [related-work-positioning](docs/research/design/related-work-positioning.md) |
| 시스템 구조와 보안 판정 기준 | [architecture](docs/research/design/architecture.md) · [security-contracts](docs/research/design/security-contracts.md) |
| 엔진 모듈·스크립트 지도 | [src/inodefence](src/inodefence/README.md) · [scripts](scripts/README.md) · [문서 지도](docs/README.md) |
| 개발 참여, PR·병합 규칙, 에이전트 규칙 | [CONTRIBUTING](CONTRIBUTING.md) · [DECISIONS](docs/DECISIONS.md) · [AGENTS](AGENTS.md) |
| 개발 환경(Dev Container) | [.devcontainer](.devcontainer/README.md) |
| finding 검토와 공개 | [SECURITY](SECURITY.md) · [findings](findings/README.md) |

**개발 환경.** 개발 명령(`make install`, `make check` 등)은 저장소를 VS Code Dev Container(Ubuntu 24.04 + Python
3.12)로 열어 실행합니다. 호스트 Python에서 바로 돌리는 경로는 지원하지 않습니다(`make check`의 환경 검사는 Linux
runtime 디렉터리 `$INODEFENCE_RUNTIME_ROOT`의 hardlink·symlink 의미론을 요구합니다). 사용자 명령 `inodefence`는
별개로 호스트 셸의 venv에 설치해 씁니다. 작업 흐름과 PR 전 검사는 [CONTRIBUTING](CONTRIBUTING.md)을 따릅니다.

README는 프로젝트의 입구입니다. 세부 정의는 각 기준 문서를 따르며, 연구 메모나 계획을 검증된 성과로 취급하지 않습니다.

[MIT License](LICENSE). 실험 대상 extractor(node-tar 등)와 의존성은 각자의 라이선스를 따릅니다.

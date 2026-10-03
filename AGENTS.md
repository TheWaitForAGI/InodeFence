# InodeFence 에이전트 가이드

이 문서는 InodeFence 저장소에서 사람과 코딩 에이전트가 공통으로 따라야 할 규칙을 정의한다.

## 가장 먼저 할 일

코딩 에이전트는 작업을 시작하기 전에 다음 순서로 문맥을 확인한다.

1. `docs/START_HERE.md`
2. `docs/STATUS.md`
3. 이 `AGENTS.md`
4. 작업과 직접 관련된 design 문서만 추가로 읽는다.

모든 연구 문서를 무조건 읽고 과도하게 구현하지 않는다.

현재 Layer보다 앞선 기능을 임의로 추가하지 않는다.

## 프로젝트 목적

InodeFence는 TAR 압축 해제 보안을 연구하기 위한 프로토타입이다.

핵심 연구 질문:

> 특정 CVE PoC나 고정된 공격 패턴을 하드코딩하지 않고, filesystem security state(특히 object identity와 external effect)를 feedback으로 사용하면 archive extraction의 보안 경계 위반을 더 효과적으로 탐색할 수 있는가?

이 프로젝트는 TAR fuzzing, hardlink, symlink, entry order, filesystem-state fuzzing, outside-root write 자체가 새롭다고 주장하지 않는다.

## 연구 포지셔닝

새로움(novelty)은 이미 확정된 사실이 아니라 **검증해야 할 가설**로 취급한다.

관련 선행연구는 이미 중요한 부분을 다루고 있다.

- Jana & Shmatikov: TAR 공격을 포함한 file-processing semantic gap
- ZIPDiff: feedback-guided archive differential fuzzing
- LinkZard: link 관련 상태를 포함한 feedback-driven file-state fuzzing
- Wormholes: symlink composition, hardlink, path resolution, creation order를 이용한 archive extraction 공격

현재 InodeFence는 다음 가능성을 검증한다.

> generic TAR-entry mutation + filesystem-security-state feedback

관련 문헌 근거가 명확하지 않은 상태에서 "최초", "새로운", "기존 연구에 없음" 같은 표현을 만들지 않는다.

## 연구 규칙

1. CVE 식별자를 oracle 조건에 직접 하드코딩하지 않는다.
2. 알려진 CVE PoC를 rediscovery 실험의 기본 fuzzing seed로 사용하지 않는다.
3. Known CVE는 benchmark ground truth와 root-cause 분석에는 사용할 수 있다.
4. 보안 판정은 가능한 한 일반화된 Security Contract로 표현한다.
5. 관찰된 사실과 가설/예상 결과를 구분한다.
6. raw experiment output과 논문에 사용할 결론을 분리한다.
7. 성능 관련 논문 주장은 기록된 실험 설정과 결과로 재현 가능해야 한다.

## Security Contract 우선순위

1. **Path Boundary Confinement**
   - 가장 기본적인 path 경계 sanity/baseline
   - 중요하지만 InodeFence의 novelty는 아님

2. **Object Identity Confinement**
   - extraction 내부 object가 보호된 외부 sentinel과 의도하지 않게 동일 filesystem identity를 공유하면 안 됨

3. **External Effect Noninterference**
   - archive extraction으로 인해 보호된 외부 sentinel의 content/metadata가 의도하지 않게 변경되면 안 됨

4. **Extraction Root Integrity**
   - 최소 pipeline 이후 확장

5. **Check/Use Coherence**
   - instrumentation이 필요한 후속 단계

정의는 `docs/research/design/security-contracts.md`를 따른다.

## 범위

### 초기 범위에 포함

- TAR extraction
- Linux filesystem semantics
- regular file, directory, hardlink, 필요한 범위의 symlink
- entry path, link target, type, order, dependency mutation
- filesystem object identity
- external effect
- feedback-guided corpus evolution
- known vulnerability rediscovery
- 여러 extractor 간 적용 가능성 평가

### 초기 범위에서 제외

- 모든 archive format
- Windows NTFS semantics
- 일반적인 kernel filesystem vulnerability
- 전체 TOCTOU/race-condition 분석
- 완전한 symbolic execution
- Wormholes의 모든 bypass 재구현
- 전체 archive-parser ambiguity 분석

## 개발 환경

지원 환경:

- macOS + 저장소 Dev Container
- Windows + WSL2 + 동일 Dev Container

기준 container는 Ubuntu 24.04 + Python 3.12이다.

소스:

`/workspaces/InodeFence`

Filesystem-security 실험:

`$INODEFENCE_RUNTIME_ROOT`

현재 값:

`/var/lib/inodefence`

소스 bind mount를 filesystem semantics 실험 공간으로 사용하지 않는다.

환경 확인:

```bash
python scripts/check_dev_env.py
```

## 안전 규칙

- `/etc/passwd`, SSH key, 사용자 문서, host secret 같은 실제 민감 파일을 공격 대상으로 사용하지 않는다.
- disposable sandbox와 sentinel만 사용한다.
- 테스트와 실험은 host를 손상시키지 않고 재현 가능해야 한다.
- 파괴적인 filesystem operation은 runtime sandbox 내부로 제한한다.

## 바이브코딩 규칙

이 프로젝트는 코딩 에이전트를 적극 사용한다.

그래서 에이전트는 단순히 "작동하는 코드"를 만드는 것보다 다음을 지켜야 한다.

- 현재 Layer의 책임 안에서만 구현한다.
- 변경 이유를 사람이 이해할 수 있는 이름/구조로 남긴다.
- generic logic과 target-specific logic을 분리한다.
- 숨은 magic value보다 명시적인 data model/config를 사용한다.
- 복잡한 추상화보다 읽기 쉬운 작은 interface를 우선한다.
- 새 공통 개념을 만들면 문서 또는 docstring으로 의미를 남긴다.
- 기존 architecture를 임의로 재설계하지 않는다.
- 모호하면 기존 결정은 `docs/DECISIONS.md`를 우선한다.

## 변경 영향 규칙

다음이 바뀌면 코드만 수정하지 않는다.

- 공통 data model/interface → 관련 design 문서 갱신
- Security Contract → `security-contracts.md` 갱신
- 큰 설계 결정 → `docs/DECISIONS.md` 갱신
- 현재 단계/다음 작업 → `docs/STATUS.md` 갱신
- 프로젝트 이해 흐름 → `docs/START_HERE.md` 갱신

## 코드 품질

PR 전에 실행:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

모든 텍스트 파일은 LF 줄바꿈을 사용한다.

권장:

- `pathlib.Path`
- Python 표준 라이브러리 filesystem API
- 명시적인 data model과 typed interface
- 재현 가능한 experiment seed/configuration

Python API로 충분한 경우 불필요한 shell-specific 동작을 피한다.

## 아키텍처 경계

상위 pipeline:

```text
Seed Generator
    -> Structure Mutator
    -> TAR Builder
    -> Target Adapter
    -> State Observer
    -> Security Oracle
    -> Feedback / Corpus
    -> next mutation
```

각 책임을 분리한다.

특정 target/CVE 로직이 generic mutation, observer, oracle, feedback 모듈에 섞이지 않도록 한다.

## Git 작업 규칙

- `main`에서 직접 개발하지 않는다.
- 작업 단위별 branch를 만든다.
- `main` 대상 PR을 생성한다.
- 한 PR에는 가능하면 하나의 목적만 둔다.
- 관계없는 문서 수정, refactor, feature를 한 PR에 섞지 않는다.

자세한 workflow는 `CONTRIBUTING.md`를 따른다.

## 문서 우선순위

문서가 많아져도 읽는 순서는 단순하게 유지한다.

```text
START_HERE
    ↓
STATUS
    ↓
AGENTS
    ↓
필요한 design 문서
    ↓
research notes / CVE analysis
```

- `docs/research/`: 연구 근거, 설계, 선행연구, CVE 분석
- `experiments/`: 실험 설정과 결과
- `paper/`: 실제 논문에 사용할 준비가 된 내용

연구 메모가 자동으로 논문 주장이 되는 것은 아니다.

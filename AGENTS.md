# InodeFence 에이전트 가이드

이 문서는 InodeFence 저장소에서 사람과 코딩 에이전트가 공통으로 따라야 할 규칙을 정의한다.

## 프로젝트 목적

InodeFence는 TAR 압축 해제 보안을 연구하기 위한 프로토타입이다.

핵심 연구 질문은 다음과 같다.

> 특정 CVE PoC나 고정된 공격 패턴을 하드코딩하지 않고, filesystem security state(특히 object identity와 external effect)를 feedback으로 사용하면 archive extraction의 보안 경계 위반을 더 효과적으로 탐색할 수 있는가?

이 프로젝트는 TAR fuzzing, hardlink, symlink, entry order, filesystem-state fuzzing, outside-root write 자체가 새롭다고 주장하지 않는다.

## 연구 포지셔닝

새로움(novelty)은 이미 확정된 사실이 아니라 **검증해야 할 가설**로 취급한다.

관련 선행연구는 이미 중요한 부분을 다루고 있다.

- Jana & Shmatikov: TAR 공격을 포함한 file-processing semantic gap
- ZIPDiff: feedback-guided archive differential fuzzing
- LinkZard: link 관련 상태를 포함한 feedback-driven file-state fuzzing
- Wormholes: symlink composition, hardlink, path resolution, creation order를 이용한 archive extraction 공격

현재 InodeFence는 이 연구들 사이에 남아 있는 가능성을 검증한다.

> generic TAR-entry mutation + filesystem-security-state feedback

관련 문헌 근거가 명확히 정리되지 않은 상태에서 "최초", "새로운", "기존 연구에 없음" 같은 표현을 사용하지 않는다.

## 연구 규칙

1. CVE 식별자를 oracle 조건에 직접 하드코딩하지 않는다.
2. 알려진 CVE PoC를 rediscovery 실험의 기본 fuzzing seed로 사용하지 않는다.
3. Known CVE는 benchmark ground truth와 root-cause 분석에는 사용할 수 있다.
4. 보안 판정은 가능한 한 일반화된 security contract로 표현한다.
5. 관찰된 사실과 가설/예상 결과를 구분한다.
6. raw experiment output과 논문에 사용할 결론을 분리한다.
7. 성능 관련 논문 주장은 기록된 실험 설정과 결과로 재현 가능해야 한다.

## 초기 Security Contract

초기 구현은 다음 두 contract를 우선한다.

1. **Object Identity Confinement**
   - extraction 내부 object가 보호된 외부 sentinel과 의도하지 않게 동일한 filesystem identity를 공유하면 안 된다.

2. **External Effect Noninterference**
   - archive extraction으로 인해 보호된 외부 sentinel의 내용이나 metadata가 의도하지 않게 변경되면 안 된다.

Extraction Root Integrity, Check/Use Coherence 같은 추가 contract는 최소 pipeline이 안정된 뒤 확장한다.

## 범위

### 초기 범위에 포함

- TAR extraction
- Linux filesystem semantics
- Regular file, directory, hardlink, 필요한 범위의 symlink
- Entry path, link target, type, order, dependency mutation
- Filesystem object identity
- External effect
- Feedback-guided corpus evolution
- Known vulnerability rediscovery
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

지원하는 개발 환경:

- macOS + 저장소 Dev Container
- Windows + WSL2 + 동일 Dev Container

기준 container 환경은 Ubuntu 24.04 + Python 3.12이다.

소스 코드는 다음 경로에 있다.

`/workspaces/InodeFence`

Filesystem-security 실험은 반드시 다음 runtime root를 사용한다.

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
- disposable sandbox directory와 sentinel file만 사용한다.
- 테스트와 실험은 host를 손상시키지 않고 재현 가능해야 한다.
- 파괴적인 filesystem operation은 runtime sandbox 내부로 제한한다.

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

의도한 상위 pipeline:

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

각 책임을 분리한다. 특정 target/CVE에만 해당하는 로직이 generic mutation, observer, oracle, feedback 모듈에 섞이지 않도록 한다.

## Git 작업 규칙

- `main`에서 직접 개발하지 않는다.
- 작업 단위별로 별도 branch를 만든다.
- `main` 대상 PR을 생성한다.
- PR은 아키텍처 또는 연구 책임 단위로 리뷰 가능한 크기를 유지한다.
- 관계없는 문서 수정, refactoring, feature 구현을 한 PR에 섞지 않는다.

## 문서 관리 규칙

- `docs/research/`: 연구 메모, 설계 결정, 선행연구 분석, CVE 분석
- `experiments/`: 실험 설정과 처리된 결과
- `paper/`: 실제 논문에 들어갈 준비가 된 내용

연구 메모가 자동으로 논문 주장으로 승격되는 것은 아니다.

# InodeFence

InodeFence는 **TAR extraction을 대상으로 filesystem security state를 feedback으로 사용하는 fuzzing 연구 프로토타입**이다.

고정된 공격 패턴, 출력 경로, crash, code coverage만 사용하는 대신, 특히 **filesystem object identity와 external effect** 같은 보안 관련 상태를 이용해 archive fuzzing을 유도할 수 있는지 검증한다.

## 핵심 연구 질문

> 특정 CVE PoC나 고정된 공격 순서를 하드코딩하지 않고, generic TAR-entry mutation과 filesystem-security-state feedback을 결합하면 archive-extraction 보안 경계 위반을 효과적으로 탐색할 수 있는가?

이 문장은 아직 검증 전의 **연구 가설**이다. 이미 성능이나 novelty가 입증됐다는 의미가 아니다.

## 현재 상태

**Layer 0 — 재현 가능한 개발환경: 완료**

검증 환경:

- macOS / ARM64 + 저장소 Dev Container
- Windows / WSL2 / x86_64 + 동일 Dev Container

Container 기준:

- Ubuntu 24.04
- Python 3.12
- pytest
- Ruff
- filesystem semantics 실험용 전용 Linux runtime volume

**Layer 1 — 연구 문맥/범위/아키텍처 정의: 완료**

아직 실제 fuzzer 구현은 시작하지 않았다.

## 전체 Pipeline

```text
Seed Generator
    ↓
Structure Mutator
    ↓
TAR Builder
    ↓
Target Adapter
    ↓
State Observer
    ↓
Security Oracle
    ↓
Feedback / Corpus
    └──────────────→ next mutation
```

## 초기 연구 범위

첫 구현에서 집중하는 범위:

- TAR
- Linux filesystem semantics
- regular file / directory / hardlink / 필요한 범위의 symlink
- filesystem object identity
- 보호된 external sentinel
- extraction 전/후 state observation
- security-state-guided corpus selection

초기 target 순서:

1. node-tar
2. oras-go
3. 일정이 허용하면 GNU tar

## InodeFence가 새롭다고 주장하지 않는 것

다음 요소 자체는 신규 기여라고 주장하지 않는다.

- TAR fuzzing
- hardlink/symlink 공격
- entry-order 공격
- filesystem-state fuzzing
- outside-root write
- feedback-guided fuzzing

연구 기여는 반드시 선행연구 비교와 실험 결과로 뒷받침해야 한다.

관련 문서:

- `docs/research/design/project-scope.md`
- `docs/research/design/research-questions.md`
- `docs/research/design/security-contracts.md`
- `docs/research/design/threat-model.md`
- `docs/research/design/related-work-positioning.md`
- `docs/research/design/architecture.md`
- `AGENTS.md`

## 개발 환경

저장소를 Dev Container로 연다.

환경 확인:

```bash
python scripts/check_dev_env.py
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

Filesystem-security 실험은 다음 경로에서만 수행한다.

```text
/var/lib/inodefence
```

실제 host의 민감 파일은 실험 대상으로 사용하지 않는다.

## 저장소 구조

```text
src/inodefence/
├── generator/
├── mutator/
├── targets/
├── observer/
├── oracle/
└── feedback/

docs/research/   연구/설계/선행연구 문서
experiments/     실험 설정과 결과
paper/           논문 작성용 자료
findings/        의도적으로 저장한 finding
scripts/         개발/실험 보조 도구
tests/           자동 테스트
```

## 작업 방식

- `main`에서 직접 개발하지 않는다.
- 기능별 branch를 사용한다.
- PR을 통해 `main`에 merge한다.
- generic 연구 로직과 target-specific CVE 로직을 분리한다.

저장소 전체 규칙은 `AGENTS.md`를 따른다.

# InodeFence

InodeFence는 **TAR extraction을 대상으로 filesystem security state를 feedback으로 사용하는 fuzzing 연구 프로토타입**이다.

고정된 공격 패턴, 출력 경로, crash, code coverage만 사용하는 대신, 특히 **filesystem object identity와 external effect** 같은 보안 관련 상태를 이용해 archive fuzzing을 유도할 수 있는지 검증한다.

## 처음 왔다면

모든 문서를 읽을 필요는 없다.

먼저 이 세 개만 읽는다.

1. [docs/START_HERE.md](docs/START_HERE.md) — 프로젝트를 5분 안에 이해하기
2. [docs/STATUS.md](docs/STATUS.md) — 지금 어디까지 했고 다음에 뭘 하는지
3. [AGENTS.md](AGENTS.md) — 사람/코딩 에이전트가 지켜야 할 규칙

용어가 헷갈리면 [docs/GLOSSARY.md](docs/GLOSSARY.md), 큰 설계 결정의 이유는 [docs/DECISIONS.md](docs/DECISIONS.md)를 본다.

> 이 프로젝트에서는 문서도 구현의 일부다. AI가 만든 코드를 팀원이 설명할 수 없는 상태는 완료로 보지 않는다.

## 핵심 연구 질문

> 특정 CVE PoC나 고정된 공격 순서를 하드코딩하지 않고, generic TAR-entry mutation과 filesystem-security-state feedback을 결합하면 archive-extraction 보안 경계 위반을 효과적으로 탐색할 수 있는가?

이 문장은 아직 검증 전의 **연구 가설**이다. 이미 성능이나 novelty가 입증됐다는 의미가 아니다.

## 현재 상태

상세 최신 상태는 [docs/STATUS.md](docs/STATUS.md)를 기준으로 한다.

현재 큰 단계:

```text
Layer 0 — 재현 가능한 개발환경          ✅
Layer 1 — 연구 문맥/범위/아키텍처       ✅
Layer 2 — 공통 Data Model              ← 다음
Layer 3 — Minimal Pipeline
Layer 4 — Mutation
Layer 5 — Feedback / Corpus
Layer 6 — Experiment / Paper
```

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

## Security Contract 요약

초기 계약:

1. **Path Boundary Confinement** — 가장 기본적인 path 경계 sanity/baseline
2. **Object Identity Confinement** — 내부 object가 보호된 외부 object와 같은 identity를 공유하지 않아야 함
3. **External Effect Noninterference** — 외부 sentinel의 content/metadata가 바뀌지 않아야 함
4. **Extraction Root Integrity** — extraction root의 실제 의미가 공격적으로 redirect되지 않아야 함
5. **Check/Use Coherence** — 검증한 대상과 실제 operation에 사용한 대상의 의미가 일관되어야 함

자세한 정의는 [docs/research/design/security-contracts.md](docs/research/design/security-contracts.md)를 본다.

## 관련 연구 문서

필요할 때만 읽는다.

- `docs/research/design/project-scope.md`
- `docs/research/design/research-questions.md`
- `docs/research/design/security-contracts.md`
- `docs/research/design/threat-model.md`
- `docs/research/design/related-work-positioning.md`
- `docs/research/design/architecture.md`
- `docs/research/design/development-environment.md`

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

폴더별 책임은 [문서 지도](docs/README.md)와 [엔진 모듈 지도](src/inodefence/README.md)에서 확인한다. 상세 설계의 기준은 [architecture.md](docs/research/design/architecture.md)다. 엔진은 현재 빈 패키지이며 `model/`에는 안내 문서만 있다.

```text
src/inodefence/
├── model/       공통 모델 계획 (README만 있음)
├── generator/
├── mutator/
├── targets/
├── observer/
├── oracle/
└── feedback/

docs/            처음 읽는 문서 + 연구/설계 문서
experiments/     실험 설정과 결과
paper/           논문 작성용 자료
findings/        의도적으로 저장한 finding
artifacts/       의도적으로 보존할 생성물
scripts/         개발/실험 보조 도구
tests/           자동 테스트
```

## 작업 방식

환경과 협업 설정은 [.devcontainer](.devcontainer/README.md), [.github](.github/README.md)를 본다. 작업별 안내는 [tests](tests/README.md), [scripts](scripts/README.md), [experiments](experiments/README.md), [findings](findings/README.md), [artifacts](artifacts/README.md), [paper](paper/README.md)에 있다.

자세한 작업 방식은 [CONTRIBUTING.md](CONTRIBUTING.md)를 따른다.

핵심만 요약하면:

- `main`에서 직접 개발하지 않는다.
- 한 PR에는 가능하면 하나의 목적만 둔다.
- generic 연구 로직과 target-specific CVE 로직을 분리한다.
- 공통 interface나 연구 가정이 바뀌면 문서도 같이 수정한다.

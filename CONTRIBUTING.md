# InodeFence 작업 방법

이 프로젝트는 팀원 모두가 코딩 에이전트를 적극적으로 사용하는 것을 전제로 한다.

따라서 목표는 "AI가 코드를 많이 생성하는 것"이 아니라 **여러 사람이 같은 설계와 연구 가정을 유지하면서 빠르게 개발하는 것**이다.

## 작업 시작 전

먼저 읽는다.

1. `docs/START_HERE.md`
2. `docs/STATUS.md`
3. `AGENTS.md`

용어가 헷갈리면 `docs/GLOSSARY.md`, 설계 이유가 궁금하면 `docs/DECISIONS.md`를 본다.

## Issue와 Task Contract

[Issue Forms](.github/ISSUE_TEMPLATE/)로 작업을 생성하고 목표, 현재 Layer,
수정 가능/금지 영역, 입력/출력과 완료 조건을 확정한다. 병렬 작업은 담당 영역을
Issue에서 합의하고 서로의 interface 변경을 PR로 공유한다. 관련 scoped AGENTS도 읽는다.
확정된 Issue 명세를 Codex 또는 사람에게 그대로 전달한다. 직접 전달된 작업 명세는
Task Contract로 사용할 수 있으며 PR에 출처를 남긴다.

```text
Issue → Task Contract 확정 → branch → AI / 사람 구현 → make check
      → PR → GitHub Actions CI → review(verifier 에이전트 또는 사람) → squash merge
```

GitHub Project를 운영한다면 Backlog → Ready → In Progress → PR → Done의
5단계를 권장한다. 이 안내는 실제 board를 생성하거나 repository 설정을 변경하지 않는다.

## Branch

`main`에서 직접 개발하지 않는다.

예:

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/archive-entry-model
```

권장 prefix:

- `chore/`
- `feat/`
- `fix/`
- `test/`
- `docs/`
- `refactor/`
- `experiment/`

## 한 PR의 원칙

한 PR에는 가능하면 하나의 목적만 둔다.

좋은 예:

- ArchiveEntry model 추가
- node-tar adapter 추가
- Identity Oracle 추가

피해야 할 예:

- model + mutator + oracle + README 전부 한 번에 구현

## AI에게 맡기기 전

다음 다섯 가지를 명확히 한다.

1. 현재 Layer
2. 이번 작업의 목적
3. 수정 가능한 파일/모듈
4. 건드리면 안 되는 영역
5. 완료 조건

## AI가 만든 코드 리뷰

최소한 팀원이 다음 질문에 답할 수 있어야 한다.

- 이 파일은 어느 Layer인가?
- 입력은 무엇인가?
- 출력은 무엇인가?
- 어떤 Security Contract와 관련 있는가?
- target-specific인가 generic인가?
- 실패하면 어떤 테스트에서 잡히는가?

답할 수 없다면 merge 전에 문서나 코드 구조를 더 단순하게 만든다.

## PR 전 검사

Dev Container 안에서:

```bash
make check
```

`make check`는 lint, format-check, Pyright, pytest, 환경 검사와 문서 검사의
canonical command다. 최초 의존성 설치는 `make install`을 사용한다.
CI도 Ubuntu Linux / Python 3.12와 `/var/lib/inodefence`에서 같은 명령을 실행한다.
개별 검사는 `make lint`, `make format-check`, `make typecheck`, `make test`,
`make env-check`, `make docs-check`로 실행할 수 있다.
안전한 baseline 재생성은 `make fixtures`, 수동 관찰은 `make probe CASE=hardlink`로 실행한다
(기본 CASE는 regular-file; 기존 네 baseline case만 허용).

PR에는 관련 Issue, 실제 검증 결과, 사람이 이해하고 확인한 AI 설계 판단을 적는다.
CI 통과 후 architecture와 연구 규칙을 검토한다(autoloop의 verifier 에이전트 또는 사람). 통과한 PR은
작성자(사람 또는 에이전트)가 squash merge하고 branch를 삭제한다. 머지는 사람 게이트가 아니다(D035).
사람 승인이 필요한 예외: BREAKING(oracle 판정 변경), 가드·격리·allowlist 설정, FROZEN 변경, 외부 공개.

실험은 [summaries 규칙](experiments/summaries/README.md)에 따라 raw → validated summary
→ finding / paper evidence를 연결한다. 미공개 finding은 [SECURITY.md](SECURITY.md)를 따른다.

## 문서도 함께 수정해야 하는 경우

다음이 바뀌면 코드만 merge하지 않는다.

- 공통 data model/interface
- Layer 책임
- Security Contract
- target 우선순위
- experiment methodology
- 프로젝트 범위
- 이미 합의한 큰 결정

관련 문서를 같은 PR에서 갱신한다.

## 완료 정의

기능 PR은 최소한 다음을 만족해야 한다.

- 목적이 명확함
- architecture 경계를 지킴
- CVE-specific hack이 generic module에 없음
- 테스트 존재
- formatter/linter 통과
- 필요한 문서 갱신
- reviewer가 PR 설명만 보고 변경 이유를 이해 가능

## Merge 후

큰 단계가 바뀌었다면 `docs/STATUS.md`를 갱신한다.

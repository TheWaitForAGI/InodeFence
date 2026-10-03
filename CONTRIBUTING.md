# InodeFence 작업 방법

이 프로젝트는 팀원 모두가 코딩 에이전트를 적극적으로 사용하는 것을 전제로 한다.

따라서 목표는 "AI가 코드를 많이 생성하는 것"이 아니라 **여러 사람이 같은 설계와 연구 가정을 유지하면서 빠르게 개발하는 것**이다.

## 작업 시작 전

먼저 읽는다.

1. `docs/START_HERE.md`
2. `docs/STATUS.md`
3. `AGENTS.md`

용어가 헷갈리면 `docs/GLOSSARY.md`, 설계 이유가 궁금하면 `docs/DECISIONS.md`를 본다.

## Branch

`main`에서 직접 개발하지 않는다.

예:

```bash
git switch main
git pull origin main
git switch -c feat/archive-entry-model
```

권장 prefix:

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
python scripts/check_dev_env.py
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

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

---
name: inodefence-implementation
description: Implement an InodeFence Issue or Task Contract without crossing architecture, research, or layer boundaries. Use for feature, fix, refactor, and test work in this repository.
---

# InodeFence Implementation

InodeFence에서 실제 코드를 구현할 때 사용한다.

목표는 "작동하는 코드"가 아니라 **Task Contract를 최소 범위로 만족하면서 연구 의미와 architecture 경계를 보존하는 코드**다.

## 1. 시작 전에 문맥 고정

반드시 다음 순서로 읽는다.

1. `docs/START_HERE.md`
2. `docs/STATUS.md`
3. `AGENTS.md`
4. 현재 작업의 Issue 또는 사용자가 준 Task Contract
5. 작업과 직접 관련된 design 문서와 scoped `AGENTS.md`

다음 항목을 한 문장씩 정리한 뒤 구현한다.

- 현재 Layer
- 작업 목표
- 수정 가능한 파일/모듈
- 수정 금지 영역
- 입력과 출력
- 관련 Security Contract
- 완료 조건

Task Contract가 모호해도 기존 architecture를 넓게 재설계하지 않는다. 가장 작은 일관된 해석을 선택하고 그 가정을 PR에 남긴다.

## 2. 변경 범위 설계

구현 전에 변경을 다음 세 종류로 분류한다.

- **generic core**: target/CVE와 무관한 model, mutation, observer, oracle, feedback logic
- **target adapter**: 특정 extractor 실행과 결과 수집
- **experiment/research**: benchmark, configuration, evidence, report

generic core에 다음을 넣지 않는다.

- 특정 CVE 번호
- 알려진 PoC byte sequence
- 특정 vulnerable version을 전제로 한 조건
- 특정 target만의 workaround
- 논문 결과를 미리 가정한 heuristic

공통 interface를 바꾸면 관련 design 문서와 downstream 영향을 먼저 찾는다.

## 3. 테스트 우선

새 동작 또는 버그 수정에는 가능하면 먼저 실패하는 테스트를 만든다.

테스트는 구현 세부보다 contract를 검증해야 한다.

예:

- ArchiveCase order/duplicate 보존
- raw path/link spelling 보존
- 동일 RNG state의 deterministic mutation
- `(st_dev, st_ino)` identity 의미
- sentinel before/after 변화
- suspicious state와 confirmed violation 구분

알려진 CVE를 테스트할 때도 CVE 식별자를 generic oracle 조건으로 사용하지 않는다.

## 4. 구현

작은 interface와 명시적 data model을 우선한다.

권장:

- `pathlib.Path`
- Python 표준 library filesystem API
- typed interface
- caller-provided deterministic RNG
- explicit config
- immutable/value-oriented model where appropriate
- raw evidence와 normalized signature 분리

피한다:

- hidden global state
- 임의 path normalization
- magic value
- shell 동작에 불필요하게 의존
- observer와 oracle의 결합
- mutation과 feedback policy의 결합
- target adapter 내부에서 보안 판정 수행

## 5. 연구 의미 확인

코드가 다음 질문에 답할 수 있어야 한다.

- 이 변경은 어느 Layer 책임인가?
- 어떤 입력을 받아 어떤 출력을 만드는가?
- security evidence를 생성하는가, 판정하는가, feedback으로 요약하는가?
- target-specific인가 generic인가?
- 실패하면 어떤 테스트가 잡는가?
- 결과가 논문 claim을 직접 의미하는가, 아니면 raw observation일 뿐인가?

마지막 질문의 답이 불명확하면 코드나 문서에서 용어를 분리한다.

## 6. 문서 영향

다음이 바뀌면 코드만 수정하지 않는다.

- common data model/interface
- Layer 책임
- Security Contract
- experiment methodology
- target priority
- 프로젝트 범위
- 큰 architecture decision

해당 시 `docs/DECISIONS.md`, `docs/STATUS.md`, design 문서를 필요한 범위만 갱신한다.

## 7. 완료 검증

가능한 경우 Dev Container에서 실행한다.

```bash
make check
git diff --check
```

관련 테스트를 별도로 실행해 실패/성공 상태를 확인한다.

완료 보고에는 반드시 실제로 실행한 검증만 적는다. 실행하지 않은 검사는 PASS라고 쓰지 않는다.

## 8. PR 준비

PR 설명에는 최소한 다음을 포함한다.

- 목적
- Task Contract 또는 Issue
- 변경 범위
- architecture/Layer 경계
- 관련 Security Contract
- 테스트 및 validation 실제 결과
- 명시적으로 하지 않은 것

한 PR에는 가능한 한 하나의 목적만 유지한다.

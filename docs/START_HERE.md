# InodeFence — 여기서 시작

이 문서는 **처음 프로젝트를 보는 사람과 코딩 에이전트가 가장 먼저 읽는 문서**다.

모든 문서를 처음부터 읽을 필요는 없다.

## 1. 이 프로젝트가 뭔가?

InodeFence는 TAR 압축 해제 프로그램을 대상으로 하는 보안 퍼저 연구다.

핵심 아이디어는 간단하다.

```text
TAR를 조금 바꾼다
    ↓
실제 extractor에 풀어본다
    ↓
파일시스템 상태를 본다
    ↓
처음 보는 위험한 상태면 그 TAR를 남긴다
    ↓
그 TAR를 다시 바꾼다
```

우리가 특히 보는 상태는 다음이다.

- 어떤 path가 생겼는가
- file type이 무엇인가
- 두 path가 같은 filesystem object를 가리키는가
- hardlink 관계가 생겼는가
- 외부 sentinel이 바뀌었는가

## 2. 왜 하는가?

단순히 path 문자열이 안전해 보여도 실제 filesystem object 관계는 위험할 수 있다.

예:

```text
/extract/result.txt ─┐
                     ├── 같은 inode
/outside/sentinel ───┘
```

이 상태라면 extraction 내부 파일을 수정했는데 외부 sentinel도 같이 바뀔 수 있다.

InodeFence는 이런 **object identity와 external effect를 fuzzing feedback으로 사용할 가치가 있는지** 실험한다.

## 3. 무엇이 새롭다고 주장하는가?

아직 확정하지 않는다.

다음은 이미 선행연구에 존재하므로 이것 자체를 novelty라고 말하면 안 된다.

- TAR fuzzing
- hardlink
- symlink
- entry order
- filesystem-state fuzzing
- feedback-guided fuzzing
- outside-root write

현재 검증할 가설은 다음이다.

> 고정된 공격 recipe 없이 generic TAR mutation을 수행하면서 filesystem security state를 feedback으로 쓰면 보안 경계 위반을 더 잘 탐색할 수 있는가?

## 4. 현재 어디까지 했는가?

항상 최신 상태는 [STATUS.md](STATUS.md)를 본다.

현재 큰 단계:

```text
Layer 0  개발환경                  ✅
Layer 1  연구 범위/규칙/아키텍처   ✅
Layer 2  공통 Data Model           ← 다음
Layer 3  Minimal Pipeline
Layer 4  Mutation
Layer 5  Feedback / Corpus
Layer 6  Experiment / Paper
```

## 5. 코딩하기 전에 딱 이것만 읽기

### 모든 작업 공통

1. 이 문서
2. [STATUS.md](STATUS.md)
3. [../AGENTS.md](../AGENTS.md)

### 용어가 헷갈리면

- [GLOSSARY.md](GLOSSARY.md)

### 왜 이렇게 설계했는지 궁금하면

- [DECISIONS.md](DECISIONS.md)

### 연구 내용을 깊게 볼 때만

- [research/design/project-scope.md](research/design/project-scope.md)
- [research/design/architecture.md](research/design/architecture.md)
- [research/design/security-contracts.md](research/design/security-contracts.md)
- [research/design/research-questions.md](research/design/research-questions.md)
- [research/design/related-work-positioning.md](research/design/related-work-positioning.md)

## 6. 파일을 어디에 만들까?

```text
src/inodefence/generator/   TAR 생성
src/inodefence/mutator/     TAR entry 변형
src/inodefence/targets/     node-tar / oras-go / GNU tar 실행
src/inodefence/observer/    filesystem 상태 관찰
src/inodefence/oracle/      security contract 판정
src/inodefence/feedback/    state signature / corpus 선택

tests/                      코드 테스트
scripts/                    개발/실험 보조 명령
docs/research/              연구 근거와 설계
experiments/                실험 설정과 결과
findings/                   재현 가능한 finding
paper/                      논문에 실제로 사용할 자료
```

## 7. AI에게 작업시킬 때 기본 요청 형식

복잡한 프롬프트가 필요하지 않다. 최소한 다음 정보를 준다.

```text
현재 Layer:
작업 목표:
수정 가능한 모듈:
건드리면 안 되는 모듈:
완료 조건:
관련 contract:
```

예:

```text
현재 Layer: 2
작업 목표: ArchiveEntry data model 초안
수정 가능한 모듈: src/inodefence/model/
건드리면 안 되는 모듈: mutator, oracle
완료 조건: pytest 통과 + 타입 필드 설명 문서화
관련 contract: 아직 직접 적용 없음
```

## 8. 한 작업의 완료 조건

코드가 "돌아간다"만으로 끝내지 않는다.

최소한:

- 현재 architecture를 깨지 않았는가
- target-specific hack이 generic module에 들어가지 않았는가
- 새 동작을 테스트했는가
- 필요한 문서를 같이 고쳤는가
- Ruff/pytest가 통과하는가
- 팀원이 PR 설명만 보고 왜 바꿨는지 알 수 있는가

## 9. 가장 중요한 원칙

> **AI가 코드를 많이 만드는 것보다, 팀원이 그 코드가 프로젝트의 어느 Layer에 있고 왜 필요한지 설명할 수 있는 상태를 유지한다.**

이 프로젝트에서는 문서도 구현의 일부다.

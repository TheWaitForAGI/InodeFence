# Generic Mutation v1

## 이 폴더는 무엇인가

Layer 4에서 기존 archive case를 generic 규칙으로 변형한다.

```text
ArchiveCase
    ↓
Mutation operator
    ↓
ArchiveCase'
```

## 입력

기존 immutable `ArchiveCase`와 호출자가 전달하는 `random.Random`.

## 출력

기존 모델의 invariant를 만족하는 `ArchiveCase`. 원본 case와 entry를 변경하지 않는다.
적용할 수 없는 operator는 원본 case를 반환한다.

## Public API

`inodefence.mutator`에서 다음 함수들을 export한다. 모든 함수의 signature는
`(case: ArchiveCase, rng: random.Random) -> ArchiveCase`이다.

| 함수 | 동작 | Empty / 적용 불가 |
| --- | --- | --- |
| `mutate` | 8개 operator 중 하나를 동일 확률로 선택하고 한 번 적용 | 선택한 operator의 no-op 유지, 재시도 없음 |
| `add_entry` | 짧은 raw path, 0~16 bytes content, mode `0o644`인 REGULAR 추가 | Empty에도 추가 |
| `remove_entry` | 선택한 entry 하나 삭제, 나머지 상대 순서 유지 | Empty는 no-op |
| `duplicate_entry` | 선택한 entry를 그대로 임의 위치에 한 번 더 삽입 | Empty는 no-op |
| `reorder_entries` | 값이 다른 두 entry를 교환하여 순서 변경 보장 | 0~1개 또는 모든 entry가 exact duplicate이면 no-op |
| `mutate_path` | entry 하나의 path만 변형 | Empty는 no-op |
| `add_hardlink` | 기존 entry의 raw path를 target으로 HARDLINK 추가, mode `0o644` | Empty는 no-op |
| `add_symlink` | 기존 raw path 또는 짧은 generic raw target으로 SYMLINK 추가, mode `0o777` | Empty에도 generic target으로 추가 |
| `mutate_link_target` | HARDLINK 또는 SYMLINK 하나의 link target만 변형 | Link가 없으면 no-op |

추가 operator는 마지막에 append한다. 복제는 임의 위치에 삽입한다.
Hardlink/symlink의 content는 `None`이며 target은 nonempty raw text다.
Path collision, exact duplicate, entry order, 아직 존재하지 않는 link target을 허용한다.
Dependency를 자동으로 보정하거나 entry를 dedup/sort하지 않는다.

## Raw text와 재현성

Path와 link target은 filesystem path가 아니라 untrusted logical text다.
새 path는 작은 stem 집합과 `""`, `./`, `../`, `/` 접두 문자열로 짧게 생성한다.
기존 path/target 변형은 `../`, `./`, `/`를 앞에 붙이거나 `/..`, `x`를 뒤에 붙인다.
기존 문자를 모두 보존하고 한 번에 최대 3개의 ASCII 문자만 추가하므로 빈 문자열,
NUL, surrogate를 만들거나 문자열을 크게 복제하지 않는다.

`../outside`, `./a`, `a//b`, `/absolute-looking` 같은 raw spelling을 그대로
사용한다. `resolve`, `normpath`, `pathlib.Path`에 의한 normalization을 하지 않는다.
기존 긴 입력을 줄이거나 USTAR 길이에 맞추지 않는다. TAR 표현 가능 여부는 builder의 책임이다.

Operator 선택, entry/index 선택, raw text 생성, content 생성 모두 전달받은 `rng`만
사용한다. 같은 case와 같은 RNG 초기 상태(seed 및 동일 호출 순서)는 같은 결과를 낸다.
전역 random state를 읽거나 변경하지 않는다.

## Layer boundary

현재 mutation은 generic archive transformation이며 deterministic RNG 기반,
filesystem-independent, target-independent다. 의존성은 Python 표준 라이브러리와
canonical archive model뿐이다.

Mutator는 `StateSnapshot`, `StateSignature`, `Corpus`, feedback/score, `Oracle`,
`ViolationResult`, Security Contract, UCB, `TargetAdapter`, `ExecutionResult`,
target execution, filesystem observation, TAR byte encoding을 알지 못한다.
Observer/oracle/feedback/targets/pipeline을 import하지 않는다.

향후 Corpus/Feedback layer가 선택한 case로 Mutator를 호출할 수 있다.
Dependency 방향은 **상위 → Mutator → archive model**이며 Mutator가 Feedback/Corpus를
import하지 않는다. 변형 결과를 builder에 전달하는 책임도 호출자에게 있다.

[mutator 단위 검사](../../../tests/test_mutator.py)와 별도
[constructor/builder integration 검사](../../../tests/test_mutator_builder.py)를 둔다.
Integration 검사는 caller 수준에서 raw spelling/순서/중복, deterministic encoding과
명시적인 USTAR 길이 거부를 확인하며 mutator 구현에 builder 의존성을 추가하지 않는다.
이 검증은 feedback-driven corpus scheduling이나 연구 효과를 입증하지 않는다.

초기 seed 생성, CVE-specific recipe/known PoC mutation, TAR byte/encoding mutation,
corpus persistence, feedback-guided selection, scheduler/energy assignment, fuzzing loop,
testcase minimization, mutation history DB는 이번 범위에 포함하지 않는다.

## Versioned M1 API

`MutationPolicy`와 `mutate_with_policy`는 legacy `uniform-generic-v1` 및
`uniform-generic-m1-v1`을 명시적으로 선택한다. 기존 `mutate`는 그대로다.
M1의 nested/raw path, controlled name reuse, insertion, type replacement와 link composition은
[grammar와 RNG 계약](../../../docs/research/design/mutation-m1-v1.md)을 따른다.
M1은 current USTAR의 conservative text bound를 지키며 multi-step builder 검사를 제공한다.
Campaign/config binding은 documented dependency이며 core API와 별도다.

# InodeFence 엔진 모듈

상세 구조와 데이터 흐름은 [architecture](../../docs/research/design/architecture.md)가 canonical source다.

## 실제 입력 하나의 경로

`pipeline.run_case(ArchiveCase, TargetAdapter, sentinels=...) -> RunResult`

```text
builder.build_tar → disposable runtime → before snapshot
→ TargetAdapter.run → after snapshot → compare_states
→ C0/C1/C2 Oracle + StateSignature → RunResult → cleanup
```

입력은 immutable case와 명시적인 target/sentinel 설정이다. 결과에는 case, TAR hash/format, target/version/command/timeout, 전후 snapshot, 변화와 typed evidence가 남는다. [root 사용 예](../../README.md)를 따른다.

## 책임 배치

| 위치 | 책임 |
| --- | --- |
| [model](model/README.md) | 공통 입력과 결과, canonical JSON |
| [builder.py](builder.py) | 결정적 USTAR 직렬화 |
| [runtime.py](runtime.py) | Linux runtime와 sentinel lifecycle |
| [pipeline.py](pipeline.py) | 실행 순서 연결 |
| [generator](generator/README.md) | 초기 case 생성 정책, 후속 구현 |
| [mutator](mutator/README.md) | Generic Mutation v1, 8개 독립 ArchiveCase 변형 operator |
| [targets](targets/README.md) | 실제 extractor 실행 |
| [observer](observer/README.md) | filesystem 사실 관찰과 비교 |
| [oracle](oracle/README.md) | Security Contract 판정 |
| [feedback](feedback/README.md) | 초기 signature; corpus 선택은 후속 구현 |

Observer는 사실만 기록하고 Oracle은 사실에 계약을 적용한다. Signature 계산은 계약 판정과 독립적이다. Pipeline은 각 알고리즘을 호출할 뿐 target 옵션이나 mutation 전략을 소유하지 않는다.

## 현재 상태와 한계

Layer 2, 최소 Layer 3와 Generic Mutation v1이 구현됐다. Feedback-driven corpus scheduling과 fuzzing loop, 연구 효과 검증은 후속 작업이다. Python tarfile/data target은 architecture/reference용이며 최종 benchmark target이 아니다. Unsafe target에는 추가 OS 실행 격리가 필요하다. Disposable runtime directory 자체는 OS sandbox가 아니다.

Snapshot의 `violated=False`는 관찰 범위에서 위반 증거가 없다는 뜻이다. Transient operation, sandbox 밖의 상태, symlink referent identity와 full C0 direct-use는 증명하지 못한다. 관찰 실패는 harness 오류로 올리며 passing result를 만들지 않는다.

[tests](../../tests/README.md)는 semantics를 검증하고 [experiments](../../experiments/README.md)는 연구 실험을 담당한다. Runtime 결과를 소스에 넣지 않는다. 새 공통 interface는 design 문서와 함께 갱신한다.

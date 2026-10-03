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
| [pipeline.py](pipeline.py) | 입력 하나의 실행 순서 연결 |
| [campaign.py](campaign.py) | 명시적 seed와 실행 budget으로 select → mutate → run → consider 연결 |
| [generator](generator/README.md) | 초기 case 생성 정책, 후속 구현 |
| [mutator](mutator/README.md) | Generic Mutation v1, 8개 독립 ArchiveCase 변형 operator |
| [targets](targets/README.md) | 실제 extractor 실행 |
| [observer](observer/README.md) | filesystem 사실 관찰과 비교 |
| [oracle](oracle/README.md) | Security Contract 판정 |
| [feedback](feedback/README.md) | signature v2, 독립 violation novelty, in-memory Corpus v1과 uniform parent 선택 |

Observer는 사실만 기록하고 Oracle은 사실에 계약을 적용한다. Signature 계산은 계약 판정과 독립적이다. Pipeline은 각 알고리즘을 호출할 뿐 target 옵션이나 mutation 전략을 소유하지 않는다.

Layer 5는 `RunResult → Corpus.consider → FeedbackDecision`을 연결한다. Novel normalized
state 또는 새 semantic violation class면 interesting이며, 같은 case_id의 parent는 한 번만
보존한다. `Corpus.select_case(rng)`의 결과를 Mutator에 전달하는 책임은 caller에게 있다.
Corpus가 실행/변형하거나 full RunResult를 저장하지 않는다. 상세 public API와 campaign
context 한계는 [feedback](feedback/README.md)를 따른다.

## 현재 상태와 한계

Layer 2, 최소 Layer 3, Generic Mutation v1과 Layer 5 Feedback / Corpus v1이 구현됐다. Corpus는 in-memory이며 caller RNG 기반 uniform baseline 선택만 제공한다. Bounded deterministic campaign은 구현됐으며 adaptive scheduler, persistence와 연구 효과 검증은 후속 작업이다. Python tarfile/data target은 architecture/reference용이며 최종 benchmark target이 아니다. Unsafe target에는 추가 OS 실행 격리가 필요하다. Disposable runtime directory 자체는 OS sandbox가 아니다.

Snapshot의 `violated=False`는 관찰 범위에서 위반 증거가 없다는 뜻이다. Transient operation, sandbox 밖의 상태, symlink referent identity와 full C0 direct-use는 증명하지 못한다. 관찰 실패는 harness 오류로 올리며 passing result를 만들지 않는다.

[tests](../../tests/README.md)는 semantics를 검증하고 [experiments](../../experiments/README.md)는 연구 실험을 담당한다. Runtime 결과를 소스에 넣지 않는다. 새 공통 interface는 design 문서와 함께 갱신한다.

## Bounded campaign v1

`run_campaign(initial_cases, target, CampaignConfig(random_seed, execution_budget), sentinels=...)`는
새 Corpus로 시작한다. Initial cases는 nonempty/unique case IDs이며 모두 budget에 포함한다.
선언 순서의 seed 실행 후 한 campaign RNG로 parent 선택과 mutation을 순서대로 수행한다.
No-op/rejected/failed/timed-out도 실행 하나로 기록하며 harness 오류는 전달한다.
`CampaignResult`는 config/initial IDs, immutable steps, final stats와 admission-order retained IDs다.
Zero-based step은 origin/parent ID/full RunResult/FeedbackDecision을 보존한다. 메모리는
O(execution_budget)이며 개별 evidence 크기에도 비례한다. Semantic feedback이 같을 때 lineage가
재현되며 raw inode/timestamp/duration은 재현을 요구하지 않는다. Disk export/resume는 없다.

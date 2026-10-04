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
| [campaign_export.py](campaign_export.py) | 완료된 결과의 manifest JSON / canonical step JSONL |
| [provenance.py](provenance.py) | 실행 전 source/environment/target/sentinel configuration 고정 |
| [experiment_config.py](experiment_config.py) | strict JSON config / SHA-256 ID / seed-target binding |
| [generator](generator/README.md) | explicit deterministic minimal_seed_corpus |
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

Layer 2, 최소 Layer 3, Generic Mutation v1과 Layer 5 Feedback / Corpus v1이 구현됐다. Corpus는 in-memory이며 caller RNG 기반 uniform baseline 선택만 제공한다. Bounded deterministic campaign은 구현됐으며 adaptive scheduler, persistence와 연구 효과 검증은 후속 작업이다. Python tarfile/data target은 architecture/reference용이며 최종 benchmark target이 아니다. Node-tar adapter는 정상 fixture 검증만 제공한다. Unsafe target에는 추가 OS 실행 격리가 필요하다. Disposable runtime directory 자체는 OS sandbox가 아니다.

Snapshot의 `violated=False`는 관찰 범위에서 위반 증거가 없다는 뜻이다. Transient operation, sandbox 밖의 상태, symlink referent identity와 full C0 direct-use는 증명하지 못한다. 관찰 실패는 harness 오류로 올리며 passing result를 만들지 않는다.

[tests](../../tests/README.md)는 semantics를 검증하고 [experiments](../../experiments/README.md)는 연구 실험을 담당한다. Runtime 결과를 소스에 넣지 않는다. 새 공통 interface는 design 문서와 함께 갱신한다.

## Bounded campaign v1

`run_campaign(initial_cases, target, CampaignConfig(random_seed, execution_budget), sentinels=...)`는
새 Corpus로 시작한다. Initial cases는 nonempty/unique case IDs이며 모두 budget에 포함한다.
선언 순서의 seed 실행 후 한 campaign RNG로 parent 선택과 mutation을 순서대로 수행한다.
No-op/rejected/failed/timed-out도 실행 하나로 기록하며 harness 오류는 전달한다.
`CampaignResult`는 config/initial IDs, immutable steps, final stats와 admission-order retained IDs,
실행 전 immutable provenance다. CampaignTarget은 stable target configuration property를 요구한다.
첫 실행 전에 freeze하며 supplied provenance의 target/sentinel 일치를 확인한다. Adapter 선언 또는
result의 target/version/timeout drift는 중단하고 configuration을 덮어쓰지 않는다.
Zero-based step은 origin/parent ID/full RunResult/FeedbackDecision을 보존한다. 메모리는
O(execution_budget)이며 개별 evidence 크기에도 비례한다. Semantic feedback이 같을 때 lineage가
재현되며 raw inode/timestamp/duration은 재현을 요구하지 않는다. `campaign_export.export_campaign(result, destination)`은 별도 완료-result writer다. Resume는 없다.

## Campaign export v1

TargetProvenance의 execution_safety는 default ISOLATION_REQUIRED다. Campaign은 explicit
TRUSTED_REFERENCE만 허용하고 그 밖의 target/미선언 adapter는 runtime 이전에 거부한다.
현재 OS isolation helper가 없으며 low-level run_case는 controlled fixture caller 책임이다.

Writer는 model/campaign만 의존하고 target을 실행하거나 feedback을 재판정하지 않는다.
Manifest schema v2는 stored execution_provenance, config/initial IDs, steps count/stats/retained order, 결과의 execution contexts와
JSONL SHA-256을 담는다. `steps.jsonl`은 기존 `canonical_json(CampaignStep)`을 그대로 사용한다.
Exporter environment는 writer process의 정보이며 execution environment/source revision을
추정하지 않는다. Execution environment/source는 실행 전 stored provenance에 있다.
같은 result/exporter 환경은 동일 bytes를 만든다. 별도 run의 raw allocation/time은
보존하므로 byte equality를 요구하지 않는다. IO/encoding 오류는 전달하고 partial output이 남을
수 있다. Writer/reader/resume는 별도 개념이며 현재는 writer만 제공한다.

ExperimentConfig v1은 seed/profile/policy/target/sentinel/environment-profile 조건을 실행 전에 검증한다.
Stored experiment_config_id는 manifest에 보존하며 actual source/platform provenance와 분리한다.
현재 config CLI는 safe reference만 실행한다. [설정 계약](../../experiments/configs/README.md)을 따른다.

현재 준비 상태는 ENGINEERING FOUNDATION이다. Reference engine 경로의 구현/검증과
third-party benchmark readiness를 구분한다. Node-tar 정상 fixture는 통과했지만 validated OS
isolation과 Node campaign smoke는 없다. [준비 상태와 다음 작업](../../docs/STATUS.md)을 따른다.

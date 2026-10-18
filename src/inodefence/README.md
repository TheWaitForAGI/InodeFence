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
| [effect_pipeline.py](effect_pipeline.py) | contained node-tar v2 producer와 unchanged final-state 결과 조합 |
| [campaign.py](campaign.py) | 명시적 seed와 실행 budget으로 select → mutate → run → consider 연결 |
| [effect_campaign.py](effect_campaign.py) | caller-owned synthetic v2 producer로 effect policy closed loop 검증 |
| [effect_scheduler.py](effect_scheduler.py) | v2 uniform/adaptive scheduler와 lineage/reward evidence |
| [campaign_export.py](campaign_export.py) | 완료된 결과의 manifest JSON / canonical step JSONL |
| [provenance.py](provenance.py) | 실행 전 source/environment/target/sentinel configuration 고정 |
| [experiment_config.py](experiment_config.py) | strict JSON config / SHA-256 ID / seed-target binding |
| [generator](generator/README.md) | explicit deterministic minimal_seed_corpus |
| [mutator](mutator/README.md) | Generic Mutation v1, 8개 독립 ArchiveCase 변형 operator |
| [targets](targets/README.md) | 실제 extractor 실행 |
| [observer](observer/README.md) | filesystem 사실 관찰과 비교 |
| [oracle](oracle/README.md) | Security Contract 판정 |
| [feedback](feedback/README.md) | legacy state feedback와 별도 normalized effect-feedback v2 core |
| [minimizer.py](minimizer.py) | bounded deterministic generic/USTAR reduction and evidence binding |
| [evaluation](evaluation/README.md) | verified raw/config, passive ledger/journal, qualification/matrix, datasets/statistics |
| [replay](replay/README.md) | allowlisted benign fresh-runtime reproduction |

Observer는 사실만 기록하고 Oracle은 사실에 계약을 적용한다. Signature 계산은 계약 판정과 독립적이다. Pipeline은 각 알고리즘을 호출할 뿐 target 옵션이나 mutation 전략을 소유하지 않는다.

Layer 5는 `RunResult → Corpus.consider → FeedbackDecision`을 연결한다. Novel normalized
state 또는 새 semantic violation class면 interesting이며, 같은 case_id의 parent는 한 번만
보존한다. `Corpus.select_case(rng)`의 결과를 Mutator에 전달하는 책임은 caller에게 있다.
Corpus가 실행/변형하거나 full RunResult를 저장하지 않는다. 상세 public API와 campaign
context 한계는 [feedback](feedback/README.md)를 따른다.

Effect Gate 2는 별도 `EffectRunResult`와 v2 policy ID를 사용해 synthetic producer에서
normalization → novelty → retention → parent/operator selection → next case 관계를 검증한다.
Gate 3은 별도 contained node-tar worker/adapter, bounded terminal frame, class-specific evidence
변환과 no-overwrite raw export를 구현했다. Gate 4 independent reader와 고정 qualification
runner도 구현되어 portable tests를 통과했다. Clean revision `36ff7fd`에서 contained producer
10개 검사와 480회 qualification을 실행하고 독립적으로 재검증했다. Replacement coverage가
실패해 NOT_QUALIFIED이므로 이 경로를 native feedback이나 campaign에 사용하지 않는다.
별도 v3 모듈은 complete/successful v2 trace와 strict raw dependency envelope를 교차 검증해
same-entry/same-path removal→creation rebinding composite를 만들고, unchanged v2 keys 옆에 finite
tagged key를 추가한다. Synthetic reader/nonredundancy tests만 통과했으며 native producer나
qualification/campaign에 연결되지 않았다.

## 현재 상태와 한계

Capability baseline은 main `8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`다.
Layer 2–5와 Layer 6 infrastructure가 구현됐다. `run_search_campaign` / `SearchCampaignConfig`가
B0/B1/B3 × FULL/A1/A2 × legacy/M1/protected-component/A3를 실행하고 별도 PolicyEvaluationConfig/completed export가
source/runtime/target/profile/protocol를 binding한다. Legacy ExperimentConfig는 B3/legacy만 허용한다.
Reader/journal/replay/minimizer와 policy datasets/statistics가 존재하지만 automatic policy journal,
interrupted-prefix return과 known-class classification은 완성된 pipeline이 아니다. Final-state policy
runner의 optional completed-step callback과 별도 full-step monotonic timing evidence/reader는 구현됐지만
publication/failure 시간을 포함하지 않고 formal timed dataset 또는 결과를 만들지 않는다.

Python reference는 architecture용이다. Contained node-tar 7.5.22의 benign full path는 TESTED이나
historical qualification/rediscovery/formal effectiveness는 NOT_RUN이고 취약점을 주장하지 않는다.
첫 intended qualification은 N01 7.5.2/7.5.3이다. GNU는 benign allowlist에 제한되며 ORAS는 없다.
[Research Contract](../../docs/research/design/research-contract-v1.md)와 [STATUS](../../docs/STATUS.md)를 따른다.
Disposable runtime 자체는 OS isolation이 아니다.

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

TargetProvenance의 execution_safety는 default ISOLATION_REQUIRED다. Campaign은 explicit TRUSTED_REFERENCE 또는 정확한 IsolatedTarget/backend binding만 허용한다.
미선언/uncontained adapter는 runtime 이전에 거부한다. Node invocation은 직접 실행 경로가 없으며
low-level run_case도 contained target의 prepare/execute/AFTER/cleanup 순서를 유지한다.

Writer는 model/campaign만 의존하고 target을 실행하거나 feedback을 재판정하지 않는다.
Manifest schema v4는 stored execution/isolation_provenance, config/initial IDs, steps count/stats/retained order, 결과의 execution contexts와
JSONL SHA-256을 담는다. `steps.jsonl`은 기존 `canonical_json(CampaignStep)`을 그대로 사용한다.
Exporter environment는 writer process의 정보이며 execution environment/source revision을
추정하지 않는다. Execution environment/source는 실행 전 stored provenance에 있다.
같은 result/exporter 환경은 동일 bytes를 만든다. 별도 run의 raw allocation/time은
보존하므로 byte equality를 요구하지 않는다. Optional pre-read config JSON은 stored config ID와
비교하고 experiment.json/checksum으로 같은 bundle에 기록한다. Linux staging/flush/fsync/checksum
검증 후 renameat2(RENAME_NOREPLACE)로 공개하므로 기존/동시 destination을 덮어쓰지 않는다.
공개 전 오류는 final absent/staging cleanup이며 공개 후 parent fsync 오류는 complete bundle을 남기고
전달한다. Hard interruption은 staging을 남길 수 있다. 지원되지 않는 OS/libc/filesystem에는 fallback이 없다. Writer/reader/resume는 별도 개념이다. Evaluation reader는 구현됐지만 resume는 제공하지 않는다.

ExperimentConfig v1/v2는 seed/profile/policy/target/sentinel/environment-profile 조건을 실행 전에 검증한다.
Stored experiment_config_id는 manifest에 보존하며 actual source/platform provenance와 분리한다.
현재 config CLI는 safe reference만 실행한다. [설정 계약](../../experiments/configs/README.md)을 따른다.

역사적 audit/smoke summaries는 자체 SHA와 checksums의 기록으로 보존한다. 현재 capabilities와
remaining validation은 [STATUS](../../docs/STATUS.md)를 따른다. Engineering PASS는
benchmark qualification이나 vulnerability claim으로 승격되지 않는다.

# Search-policy core v1

Layer 5의 독립 API는 `feedback.SearchState(initial_cases, SearchPolicy)`다.
기존 `Corpus`, `FeedbackDecision`, bounded campaign과 manifest v4/step v1은 그대로다.
B0/B1/B3는 `run_search_campaign`의 explicit caller configuration으로 실행 가능하다.
Capability baseline은 main `8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`다.
별도 completed policy export/reader, PolicyEvaluationConfig, dataset/statistics binding이 구현됐다.
Legacy ExperimentConfig / manifest v4 / journal binding은 이 policy 경로가 아니다.
Automatic policy journal/repetition은 아직 연결되지 않았다. 연구 효과를 검증한 결과가 아니다.
[Research Contract](research-contract-v1.md)와 [STATUS](../../STATUS.md)를 따른다.

| Policy ID | Admission | Seed phase 이후 parent |
| --- | --- | --- |
| `unretained-walk-v1` (B0) | 없음 | 첫 선택은 seed bank에서 균등, 이후 이전 observed child |
| `state-v3-uniform-parent-v1` (B1) | unseen feedback key (default: full StateSignature) | retained unique cases에서 균등 |
| `state-v2-or-violation-v1-uniform-parent-v1` (B3 legacy ID) | unseen feedback key OR violation fingerprint | retained unique cases에서 균등 |

선언한 immutable initial cases는 nonempty / unique case ID여야 한다. `consider`는
먼저 seed results를 선언 순서로 요구한다. Seed phase가 끝나기 전 selection은 RNG를
소비하지 않고 거부한다. B1/B3 seed admission도 선택한 projection의 key novelty 규칙을 사용한다.
B0는 seed bank와 active case 한 개만 parent로 사용하며 retained entries는 항상 없다.
Diagnostic state/fingerprint indexes는 B0에서도 누적되므로 전체 메모리가 O(1)은 아니다.
모든 status와 no-op child를 동등하게 관찰한다. Oracle/target 정보를 selection에 넣지 않는다.

`SearchDecision`은 별도의 frozen/slots record다. Full `state_novel`,
`new_violation_fingerprints`, `already_retained`, explicit `admission_eligible`과
`feedback_key_novel`을 담는다.
`interesting`은 항상 full state OR violation novelty이며, 실제 `retained`는
`admission_eligible AND NOT already_retained`다. 기존 FeedbackDecision의 B3 의미나
serialized shape를 수정하지 않는다. SearchDecision은 자기 model name과 envelope v2를
가지며 CampaignStep에 묵시적으로 넣지 않는다. RunResult/raw snapshots/verdict는 그대로
caller에게 남는다. 동일 case의 새로운 outcome은 indexes를 갱신하되 parent를 복제하지 않는다.

`Corpus`와 SearchState는 private full-evidence novelty index를 공유한다. Core B3와 기존
Corpus의 admission metadata, diagnostics, counters, uniform parent sequence와 RNG state를
테스트에서 비교한다. B0의 RNG는 초기 parent draw 후 mutation caller만 소비한다.
Paired seeds는 동일 mutation stream을 보장하지 않는다.

## Legacy evidence 경계와 구현된 separate policy binding

현재 `evaluation.verify`, `evaluation.journal`, `evaluation.dataset`은 manifest v4,
CampaignStep v1과 B3-only Corpus replay / previously retained parent rule에 고정돼 있다.
Search 담당은 이 파일들을 변경하지 않는다. 아래 계약은 separate policy export/reader에 구현됐으며 legacy journal/config에는 묵시적으로 적용되지 않는다:

1. Versioned step은 SearchDecision의 full diagnostics와 policy admission을 함께 보존한다.
2. Versioned manifest/result에는 explicit feedback/mutation policy ID, retained IDs와 B0
   working-set accounting을 넣는다. 기존 B3 config JSON/config ID를 보존한다.
3. Separate completed policy reader는 declared policy로 admission을 검증한다. Legacy journal의 policy 지원은 없다. B0 첫 parent는 declared seed
   bank, 이후 parent는 이전 child이며 status/novelty filtering은 없다.
4. A1/A2는 feedback-only projected key를 쓰고 full signature/oracle evidence와 full
   diagnostic indexes를 보존한다. Projected-key count와 full-state count를 구분한다.
5. Config parser는 implemented-and-bound ID만 허용한다. 알려진 core ID라는 이유로
   현재 B3 runner에 silent fallback하지 않는다.

현재 [policy_evidence](../../../src/inodefence/evaluation/policy_evidence.py)와
[policy_binding](../../../src/inodefence/evaluation/policy_binding.py)이 completed result의
model/policy/admission/raw derivations와 explicit config/provenance를 검증한다.
[Policy dataset](../../../src/inodefence/evaluation/policy_dataset.py) 및
[statistics](../../../src/inodefence/evaluation/policy_statistics.py)도 있다.
이는 actual RNG/mutation execution, known-class qualification 또는 interrupted-run recovery의 증거가 아니다.

## A1/A2 feedback projection

`SearchState(..., projection=FeedbackProjection.FULL)`의 default key는 full signature다.
`state-v3-no-identity-groups-key-v1` (A1)은 identity_groups만,
`state-v3-no-external-effects-key-v1` (A2)은 external_effects만 key에서 제외한다.
`feedback_key`는 policy-tagged FeedbackKey를 만들고 원본 signature/snapshot/verdict를
변경하지 않는다. Regular nlink, object content/path/type, protected paths와 다른 field는
유지한다. 따라서 해당 field 외의 정보로 유사 관계를 구별할 가능성은 남는다.

`state_novel`과 CorpusStats.unique_states는 항상 full diagnostic state를 센다.
`feedback_key_novel`과 SearchState.unique_feedback_keys는 projected admission key를 센다.
B1은 key novelty만, B3는 key novelty OR violation novelty를 사용한다. A1/A2에서도
violation fingerprints는 그대로이므로 새로운 violation만으로 B3 admission은 가능하다.
B0는 두 novelty channel과 projection에 관계없이 이전 child로 진행한다.

SearchDecision에 feedback_key_novel을 추가하여 core envelope를 v2로 올렸다.
Legacy FeedbackDecision/Corpus/CampaignStep/manifest/config schema와 ID는 바꾸지 않았다.
Projection ID는 SearchCampaignConfig와 separate completed policy evidence/config binding에 보존된다. Legacy ExperimentConfig는 여전히 대안 projection을 허용하지 않는다. Baseline 비교 실험은 실행하지 않았다.

## Bound config compatibility and composed baseline checks

ExperimentConfig의 기존 B3/legacy mutation constants는 SearchPolicy.B3와 MutationPolicy.LEGACY의
versioned ID를 사용한다. Serialized strings, JSON schema와 기존 config ID는 그대로다.
Fixed target version의 golden config ID로 compatibility를 검사한다.
Unknown ID와 B0/B1/M1/A3 ID는 legacy ExperimentConfig에서 즉시 거부한다. 별도 SearchCampaignConfig / PolicyEvaluationConfig 경로는 지원한다.
이 검사는 alternative policies가 ExperimentConfig에 연결됐다는 의미가 아니다.

All execution statuses에서 semantic state가 같으면 novelty/admission이 생기지 않는다.
반대로 completed observation의 새로운 semantic state는 status와 무관하게 B1/B3에서 admission
후보가 된다. B0/B1/B3 × FULL/A1/A2 × M1/A3의 caller-level composition은 shared RNG, seed order,
no-op child, violation novelty를 함께 검사한다. Raw dev/inode/timestamp를 바꿔도 같은 semantic
outcomes이면 logical parent/child lineage, diagnostics, entries, stats와 final RNG state가 같다.
이 unit composition은 configured baseline campaign/evaluation 실행 결과가 아니다.

## Policy-aware bounded campaign caller

`campaign.run_search_campaign(initial_cases, target, SearchCampaignConfig(...))`는 기존
single-case pipeline과 SearchState/mutate_with_policy를 조합한다. Legacy runner와 seed validation,
exact IsolatedTarget requirement, isolation availability/attestation, pre-execution provenance freeze,
sentinel binding 및 매 trial의 target/case drift 검증을 공유한다. Wrapper subclass나 supplied
provenance로 isolation requirement를 낮출 수 없다. Infrastructure exception은 전달한다.

Frozen `SearchCampaignConfig`는 integer random_seed/execution_budget, explicit SearchPolicy,
MutationPolicy와 FeedbackProjection을 가진다. Unknown/string 값은 fallback 없이 즉시 거부하며
외부 문자열 ID는 해당 enum constructor로 명시적으로 검증해야 한다. B3/legacy mutation/FULL
조합은 기존 campaign의 parent/child lineage, raw results, retention, counters와 RNG 동작을 유지한다.
기존 CampaignConfig/ExperimentConfig serialization과 ID는 바꾸지 않는다.

Seed phase는 선언 순서이며 RNG를 소비하지 않는다. Seed-inclusive execution budget에 no-op,
duplicate case와 모든 returned status가 포함된다. 한 owned RNG로 selection 후 mutation을 수행한다.
B0는 seed bank에서 한 번 뽑은 후 이전 child를 사용하고 corpus admission은 하지 않는다.
B1/B3는 policy-admitted unique parents를 균등 선택한다. A1/A2는 projected key만 바꾸며 full
snapshot/signature/verdict가 모든 step에 남는다. A3는 versioned mutation dispatch의 probability
slot과 draw semantics를 그대로 사용한다. Adaptive scheduler나 effectiveness 판단은 없다.

새 `SearchCampaignResult`/`SearchCampaignStep`는 각각 자기 model name의 canonical envelope v1이다.
Result는 config의 세 policy ID, full steps, full-state CorpusStats, retained IDs,
unique_feedback_keys, active_case_id와 frozen ExecutionProvenance를 보존한다. B0 retained count는
zero이며 seed-only budget에서는 active_case_id도 None이다. Seed IDs와 active child는 retained
corpus와 구분한다. Diagnostic indexes와 full step evidence는 budget에 비례한 메모리를 사용한다.

이 API는 in-memory evidence를 반환하며 separate policy export/reader/config/dataset 경로가
완료된 결과를 보존/검증한다. Legacy exporter/journal/dataset에 묵시적으로 넣지 않는다.
Core callback/partial result가 없어 automatic incremental attachment는 여전히 불가하다.
Compatibility/statistics 구현은 formal durable campaign orchestration이나 effectiveness proof가 아니다.
Unit tests는 policy/projection/mutation 조합과 legacy B3 parity를 확인한다. Tiny Python reference
integration은 기존 runtime에서 full pipeline/archive hash binding을 확인하며 benchmark 결과나
정책 효과의 증거가 아니다.

## Independent transition-retention core

Entry-transition track은 기존 B0/B1/B3 enum, admission, evidence shape를 수정하지 않는다.
`TransitionSearchPolicy`의 P0
`final-state-v3-or-violation-v1-uniform-mutation-v1`과 P1
`transition-v1-or-violation-v1-uniform-mutation-v1`, P2
`transition-v1-or-violation-v1-adaptive-mutation-v1`을 별도 API로 제공한다.

P0는 FULL B3와 같은 StateSignature v3 OR violation admission 및 caller RNG uniform parent
selection을 재현한다. P1은 final-state admission만 unique TransitionFeedbackKey admission으로
대체하며 violation channel과 uniform parent/mutation은 유지한다. `TransitionSearchDecision`은
full-state, violation, transition novelty와 trace completeness를 분리한다. Adaptive operator
selection은 P2에만 적용된다. P2 admission은 P1과 같고, 새 transition key가 하나 이상인
attempt에만 bounded binary reward를 준다. P0/P1의 uniform scheduler는 outcome에 관계없이
모든 operator weight를 1로 유지한다.

Native node-tar completion boundary가 qualification에 실패했으므로 transition campaign은
caller-owned `TransitionRunResult` producer를 조합하는 in-memory core다. Existing isolated
target gate, ExperimentConfig, exporter/reader를 우회하거나 formal experiment readiness를
주장하지 않는다. Synthetic sequence에서 P0/P1/P2 실행 가능성, P0/B3 admission/parent RNG
parity, legacy uniform mutation RNG parity와 adaptive weight bound를 테스트했다.
Effectiveness는 **NOT_RUN**이다.

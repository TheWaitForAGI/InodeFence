# Generic archive minimizer v1

Search-policy core 이후의 독립 reduction API는
`minimize_case(case, evaluate, preserves, execution_budget=...)`다.
Policy ID는 `greedy-archive-reduction-v1`이며 target/CVE/replay infrastructure에 의존하지 않는다.
Caller는 ArchiveCase를 실행해 RunResult를 반환하는 evaluator와 bool evidence predicate를
제공한다. 실행 isolation, target/config/provenance binding과 연구 condition 정의도 caller가 소유한다.

## Preservation condition

Baseline도 실행 budget에 포함하며 predicate를 만족해야 한다. 이후 trial은 같은 predicate를
만족할 때만 채택한다. 예를 들어 baseline의 semantic violation fingerprint tuple을 고정하고
각 RunResult의 fingerprint가 같은지 확인할 수 있다. Predicate가 허용한 equivalence 이상의
root-cause 동일성이나 실제 취약점 유지를 core가 주장하지 않는다.

Execution status는 자동 novelty 또는 preservation 조건이 아니다. Reject/failed/timeout도
full result로 보존하며 caller의 evidence condition만 사용한다. Evaluator가 다른 case의 결과를
반환하거나 predicate가 bool 이외 값을 반환하면 거부한다. Infrastructure/callback exception은
전달하고 completed result를 만들어내지 않는다. 실패한 baseline도 completed minimization이 아니다.

## Deterministic reduction order

1. 각 entry를 하나씩 삭제한다. 남은 order/duplicate/link spelling은 유지하며 dependency를 repair하지 않는다.
2. Regular content를 empty, half prefix, 마지막 byte 제거 순으로 축소한다.
3. Raw path를 `a`, 마지막 component, leading `./` 또는 `../` 제거, 첫 `//` 축소 후보로 만든다.
4. Mode를 zero, special bits 제거, 가장 낮은 set bit 제거 후보로 만든다.
5. Raw link target에 path와 같은 text reduction을 적용한다.

Text 후보는 nonempty이며 UTF-8 byte 길이가 엄격하게 감소해야 한다. 모든 transformation은
entry 수, content byte 수, path/target byte 수, mode set-bit 수의 lexicographic measure를 줄인다.
No-op와 동일 case ID 후보는 한 candidate round 안에서만 제외한다. 실행 evidence를 cache하거나
다른 round의 이전 결과로 추정하지 않는다. Candidate 채택 후 고정 순서의 새 round를 시작한다.
RNG가 없으며 같은 evaluator/predicate outcomes에서 trial lineage가 재현된다.

이 문자열 연산은 archive 의미를 보존하는 normalization이 아니다. Semantics가 바뀌면 caller
predicate가 거부해야 한다. Generic v1에서는 builder 지원 여부가 caller evaluator의 책임이다.
Runtime rejection과 evidence condition은 모든 policy에서 evaluator/predicate의 책임이다.
기본 M1-compatible case의 모든 reduction candidate에 대한 builder composition을 테스트한다.

## Result / limits

Frozen MinimizationResult는 policy ID, budget, original/final case, 모든 MinimizationStep과
termination을 담는다. Step은 index, transformation, full RunResult, accepted flag를 보존한다.
Budget는 baseline과 rejected trial을 모두 센다. Exhaustion이면 마지막 accepted case를 반환한다.
Local fixed point는 선언한 transformation 후보 중 더 채택할 수 없다는 뜻이며 global minimum이 아니다.
Full evidence memory는 trial 수와 각 result 크기에 비례한다. Export/checkpoint/replay integration은 없다.

Unit tests는 semantic violation condition 유지, 실패/timeout, deterministic lineage, duplicate/order,
negative budget/callback/binding과 rejected evidence 보존을 검사한다. 기존 Linux disposable runtime의
Python reference integration은 benign observed-content predicate의 end-to-end composition만 검증한다.
이 검증은 benchmark qualification, 취약점 발견 또는 연구 효과의 증거가 아니다.

## Exact violation condition and archive binding

`minimize_violation(case, evaluate, execution_budget=...)`는 기존 generic reduction engine을
사용하면서 baseline의 모든 semantic violation fingerprints를 explicit frozen
`ViolationCondition`으로 고정한다. Policy ID는 `exact-violation-fingerprints-v1`이다.
Canonical fingerprint set이 정확하게 일치해야 채택하며 extra/missing contract, path relation,
changed-field label도 다른 condition이다. Raw dev/inode/timestamp values는 fingerprint 의미에
포함하지 않는다. 이것은 선언한 evidence class 보존이며 root-cause 동일성 보장은 아니다.

각 trial의 candidate를 current deterministic USTAR builder로 먼저 직렬화하고 SHA-256을
계산한다. Evaluator의 returned case, archive format과 hash가 정확하게 일치해야 preservation을
판단한다. Baseline은 한 번만 실행하며 budget에 포함한다. Unknown condition policy, empty
fingerprints, nonviolating baseline과 archive/case drift는 명시적으로 거부한다. Execution status로
violation condition을 대체하지 않는다. Existing arbitrary-predicate `minimize_case` API는 그대로다.

`ViolationMinimizationResult` envelope v1은 reduction의 모든 full trial RunResult와 versioned
condition을 함께 보존한다. `final_result`는 마지막 accepted case의 raw evidence이며 뒤따르는
rejected trials와 구분한다. Stored ArchiveCase로 TAR를 재생성해 recorded hash와 비교할 수 있다.
Evaluator isolation, target/config/source provenance와 evidence authenticity는 caller 책임이다.
이 binding은 external replay infrastructure와 독립적이며 replay certification을 주장하지 않는다.

## USTAR-compatible reduction policy

`ReductionPolicy.GENERIC`의 ID는 기존 `greedy-archive-reduction-v1`이며 `minimize_case`와
`reduction_candidates`의 default candidate 순서/exception 동작을 유지한다.
`ReductionPolicy.USTAR`는 `greedy-ustar-archive-reduction-v1`이다. Baseline을 현재 builder로
검증하고, 같은 raw 후보 순서에서 lossless USTAR로 표현 불가능한 후보만 evaluator 호출 전에
제외한다. 예를 들어 `.//` 뒤 100-byte name은 표현 가능하지만 leading `./`를 제거한 101-byte
absolute spelling은 name/prefix split에서 raw spelling을 잃는다. Byte-length 감소만으로는
builder compatibility를 보장하지 못한다. ASCII/UTF-8 field 경계에서 이를 검증한다.

Unknown/string policy는 enum coercion이나 fallback 없이 거부한다. Unsupported baseline은
실행 전에 실패한다. Builder의 representation ValueError만 candidate filter에서 처리하며
evaluator/predicate의 모든 exception은 이전과 같이 전달한다. Filtering은 path normalization,
dependency repair 또는 target rejection이 아니다. Skip한 후보에 RunResult나 fake status를
만들지 않으며 execution budget은 baseline과 실제 evaluated trials만 센다. Full raw evidence와
trial index는 실제 실행 순서대로 남는다. Candidate omissions는 선언한 policy와 stored case로
재생성할 수 있으며 fixed point도 해당 policy의 후보 집합에 대한 의미다.

`minimize_violation`의 default reduction policy는 USTAR다. Result의 `reduction.policy_id`에
이를 명시하며, `reduction_policy=ReductionPolicy.GENERIC`으로 최초 raw candidate/exception
동작을 재현할 수 있다. Preservation condition의 version과 기존 result record shape는 같다.

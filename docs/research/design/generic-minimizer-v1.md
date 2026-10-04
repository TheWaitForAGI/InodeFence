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
predicate가 거부해야 한다. Builder 지원 여부와 runtime rejection도 caller evaluator의 책임이다.
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

# 연구 질문과 가설

[Research Contract v1](research-contract-v1.md)의 G0 freeze는 main
`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`의 구현을 기준으로 한다.
DESIGNED / IMPLEMENTED / TESTED / EXPERIMENTALLY VALIDATED를 구분한다.
현재는 code/tests/benign engineering evidence가 있으며, **historical rediscovery와
formal comparative evaluation은 NOT_RUN이다. 현재 취약점을 주장하지 않는다.**

## RQ1 — Known Vulnerability Rediscovery

해당 CVE PoC를 search seed로 제공하지 않고 일반 TAR-entry mutation으로 알려진
persistent C0/C1/C2 boundary violation을 재발견할 수 있는가?

첫 intended qualification은 **N01 node-tar 7.5.2 / 7.5.3의 hardlink arm**이다.
아직 pair의 runtime/strict behavior, generation reachability와 matching affected/fixed effect를
독립적으로 qualify하지 않았다. [Benchmark Set](../benchmarks/benchmark-set-v1.md)의
나머지 Node 및 cross-implementation candidates는 조건부 planning scope다.
Catalog selection/source verification은 실행·재발견 증거가 아니다.

## RQ2 — Feedback Effectiveness

동일한 benign initial corpus, mutation policy, setup, target/version과 execution budget에서
B3 filesystem-state OR violation-novelty search는 다음 실행 가능한 비교군보다
의미 있는 state/contract evidence를 더 효율적으로 탐색하는가?

- B0: unretained multi-step random walk; feedback diagnostics는 다음 parent에 영향 없음.
- B1: full StateSignature key novelty만 admission에 사용; violation novelty는 diagnostics만 유지.
- B3: full StateSignature key OR violation fingerprint novelty로 admission; uniform retained parents.

B0는 retention과 parent distribution을 함께 바꾸는 whole-search baseline이다.
B1/B3는 violation-novelty admission의 기여를 비교한다. B1은 path-only가 아니다.
**Path-only와 fixed attack-recipe comparator는 구현되지 않았으며 이 RQ의 비교 대상이 아니다.**
Search API가 IMPLEMENTED/TESTED인 것과 effectiveness가 EXPERIMENTALLY VALIDATED인 것은 다르다.

측정은 [프로토콜](../benchmarks/evaluation-protocol-v1.md)의 unique full semantic states,
generic fingerprints, executions to first observed contract evidence와 status/corpus counts를
공통 정의로 보고한다. Qualified known-class confirmation 뒤에만 rediscovery success 및
first confirmed rediscovery를 보고한다. Full-pipeline timing이 없는 현재 target duration을
time-to-first-violation/throughput 대신 사용하지 않는다.

## RQ3 — Feedback / Mutation Ablation

B3 대비 다음 구현된 좁은 ablation이 탐색에 어떤 기여를 하는가?

- A1: feedback key에서 identity_groups만 제외; regular nlink와 C1 fingerprints는 남음.
- A2: feedback key에서 external_effects labels만 제외; sentinel object/digest와 C2 fingerprints는 남음.
- A3: reorder operator slot을 같은 RNG draws를 소비하는 executed no-op로 바꿈;
  append/insertion/duplicate로 생기는 order variation은 남음.

모든 arm은 raw snapshot, oracle, full-signature analysis와 fingerprints를 보존한다.
A1/A2는 모든 identity/effect information의 제거가 아니며 A3는 모든 order variation의 제거가 아니다.
기존 F0–F3 path-only ladder와 fixed-recipe 비교를 이 실행 가능한 비교로 대체한다.
Exact IDs, assumptions와 provisional subsets는 [baselines/ablations](../benchmarks/baseline-and-ablation-v1.md)를 따른다.

## RQ4 — Cross-Implementation Generality

같은 representation과 generic C0/C1/C2를 독립적으로 qualified된 여러 TAR extractor에
적용할 수 있는가? Contained node-tar가 현재 research adapter이고 Python reference는
architecture 검증용이다. GNU route는 allowlisted benign fixtures만 지원하며 ORAS adapter는 없다.
Source-selected second-family candidates는 실행 증거가 아니다. 두 family의 qualification 없이
generality를 주장하지 않는다. 이 freeze는 새 adapter를 승인하지 않는다.

## RQ5 — Unknown-State Discovery

G1–G4와 frozen evaluation을 통과한 후 latest supported stable target에서
아직 분류하지 않은 persistent contract evidence가 나타나는가?

이는 exploratory stretch question이다. New vulnerability/CVE는 프로젝트 성공의 필수조건이 아니다.
현재 discovery campaign이나 vulnerability claim은 없다. Candidate는 재현, 영향/문서화된 동작 검토,
minimization, affected-version/root-cause 분석과 [private disclosure](../../../SECURITY.md)를 요구한다.

## H1 — State-Guided Search

고정된 조건과 budget에서 B3가 B0/B1보다 meaningful state 탐색 또는 confirmed known-class
rediscovery를 개선할 수 있다는 가설이다. Null/negative result도 정당한 결과다.
A1/A2/A3는 명시한 component의 좁은 marginal contribution을 검증한다.
아직 실험 결과가 없으며 path-only/fixed-recipe superiority로 해석하지 않는다.

## H2 — Generic Security Contract

CVE 문자열, version 또는 PoC bytes를 oracle에 넣지 않은 일반 C0/C1/C2가
qualified extractor들의 유사한 persistent effect를 관찰할 수 있다는 가설이다.
Snapshot limits 때문에 transient effect와 check/use coherence는 이 가설의 측정 범위가 아니다.

## Evaluation 원칙

같은 target/version, initial seed IDs/order, mutation grammar, controlled sentinel/setup,
limits, source revision과 oracle를 유지한다. 각 campaign은 fresh state/corpus, owned deterministic RNG,
all-status seed-inclusive budget을 사용한다. 동일 seed는 identical evolved input을 뜻하지 않는다.
Paired seeds, independent repetitions, denominator/censor flag, negative/invalid results를 보존한다.

[Evaluation protocol](../benchmarks/evaluation-protocol-v1.md)의 median/IQR, success counts/intervals와
censored first-hit 정의를 따른다. Budget/repetition 숫자는 pilot 후 별도 experiment freeze에서 확정한다.
효과를 입증하기 전에 결과를 예상하거나 favorable outcome 뒤에 methodology를 바꾸지 않는다.

# Search-policy core v1

Layer 5의 독립 API는 `feedback.SearchState(initial_cases, SearchPolicy)`다.
기존 `Corpus`, `FeedbackDecision`, bounded campaign과 manifest v4/step v1은 그대로다.
B0/B1은 core에서 구현됐지만 ExperimentConfig / campaign binding은 아직 제공하지 않는다.
연구 효과를 검증한 결과가 아니다.

| Policy ID | Admission | Seed phase 이후 parent |
| --- | --- | --- |
| `unretained-walk-v1` (B0) | 없음 | 첫 선택은 seed bank에서 균등, 이후 이전 observed child |
| `state-v3-uniform-parent-v1` (B1) | unseen full StateSignature | retained unique cases에서 균등 |
| `state-v2-or-violation-v1-uniform-parent-v1` (B3 legacy ID) | unseen full signature OR violation fingerprint | retained unique cases에서 균등 |

선언한 immutable initial cases는 nonempty / unique case ID여야 한다. `consider`는
먼저 seed results를 선언 순서로 요구한다. Seed phase가 끝나기 전 selection은 RNG를
소비하지 않고 거부한다. B1/B3 seed admission도 동일한 novelty 규칙을 사용한다.
B0는 seed bank와 active case 한 개만 parent로 사용하며 retained entries는 항상 없다.
Diagnostic state/fingerprint indexes는 B0에서도 누적되므로 전체 메모리가 O(1)은 아니다.
모든 status와 no-op child를 동등하게 관찰한다. Oracle/target 정보를 selection에 넣지 않는다.

`SearchDecision`은 별도의 frozen/slots record다. Full `state_novel`,
`new_violation_fingerprints`, `already_retained`와 explicit `admission_eligible`을 담는다.
`interesting`은 항상 full state OR violation novelty이며, 실제 `retained`는
`admission_eligible AND NOT already_retained`다. 기존 FeedbackDecision의 B3 의미나
serialized shape를 수정하지 않는다. SearchDecision은 자기 model name과 envelope v1을
가지며 CampaignStep에 묵시적으로 넣지 않는다. RunResult/raw snapshots/verdict는 그대로
caller에게 남는다. 동일 case의 새로운 outcome은 indexes를 갱신하되 parent를 복제하지 않는다.

`Corpus`와 SearchState는 private full-evidence novelty index를 공유한다. Core B3와 기존
Corpus의 admission metadata, diagnostics, counters, uniform parent sequence와 RNG state를
테스트에서 비교한다. B0의 RNG는 초기 parent draw 후 mutation caller만 소비한다.
Paired seeds는 동일 mutation stream을 보장하지 않는다.

## Evaluation ownership에 전달할 interface 요구사항

현재 `evaluation.verify`, `evaluation.journal`, `evaluation.dataset`은 manifest v4,
CampaignStep v1과 B3-only Corpus replay / previously retained parent rule에 고정돼 있다.
Search 담당은 이 파일들을 변경하지 않는다. Alternative campaign binding 전 필요한 계약:

1. Versioned step은 SearchDecision의 full diagnostics와 policy admission을 함께 보존한다.
2. Versioned manifest/result에는 explicit feedback/mutation policy ID, retained IDs와 B0
   working-set accounting을 넣는다. 기존 B3 config JSON/config ID를 보존한다.
3. Reader/journal은 declared policy로 admission을 검증한다. B0 첫 parent는 declared seed
   bank, 이후 parent는 이전 child이며 status/novelty filtering은 없다.
4. A1/A2는 feedback-only projected key를 쓰고 full signature/oracle evidence와 full
   diagnostic indexes를 보존한다. Projected-key count와 full-state count를 구분한다.
5. Config parser는 implemented-and-bound ID만 허용한다. 알려진 core ID라는 이유로
   현재 B3 runner에 silent fallback하지 않는다.

이 통합은 Evaluation 영역 변경 없이는 완료할 수 없으므로 skip한다. Core APIs는 독립
검증할 수 있다. 새 campaign/export schema 지원 여부는 main에서 다시 확인한다.

# Generic Mutation M1 v1

Layer 4의 `mutate_with_policy(case, rng, MutationPolicy.M1)`은 explicit
`uniform-generic-m1-v1` API다. `uniform-generic-v1`은 기존 `mutate`와 RNG draws를
그대로 유지한다. 문자열 ID는 `MutationPolicy(id)`로 strict 변환하며 unknown ID는 거부한다.
Target/oracle/feedback를 입력이나 import로 사용하지 않는다.

M1은 기존 8개 uniform operator slot을 유지한다. Add/remove/duplicate/reorder/path/
hardlink/symlink/link-target 순서이며 적용 불가와 bounded miss는 한 번의 no-op다.
재시도는 없다. `MutationOperatorId`와 `MutationAttempt`가 이 선택을 inspectable하게
기록한다. 기존 wrapper의 uniform 선택은 원래 function table을 `rng.choice()`에 전달해
기존 RNG 의미를 유지한다. 별도 transition campaign의 scheduler만 explicit operator를
선택하며 mutator 함수 자체는 weight나 feedback을 알지 못한다.

- Fresh text: prefix `""`, `./`, `../`, `/`; depth 1–4; separator `/` 또는 `//`;
  component `a`, `b`, `dir`, `file`, `item`, `.`, `..`.
- Existing names가 있으면 첫 boolean draw로 절반은 existing entry occurrence를 재사용한다.
  Duplicate name도 occurrence별로 선택된다. Link entry의 path도 dependency 후보에 포함한다.
- Add entry는 regular/directory type을 선택하며 regular content는 0–16 random bytes다.
  모든 신규 entry는 0..len(entries) 삽입 위치를 독립적으로 선택한다.
- Hardlink는 existing path를 가리킨다. Symlink는 fresh/reused raw path를 가리킨다.
  Link-to-link composition, forward reference, collision/type replacement를 허용한다.
  Dependency correction, path normalization, deduplication은 하지 않는다.
- Link target 변형은 bounded raw path 선택 또는 기존 spelling에 affix 추가다.
  UTF-8 100-byte bound를 넘는 affix 결과는 추가 draw 없이 원본을 반환한다.

Draw 순서는 함수/docstring에서 명시한다. Fresh path는 prefix → depth → separator →
각 component이며, reused path는 boolean → entry occurrence다. Empty/inapplicable branch는
operator 내부 draw를 하지 않는다. Caller-owned RNG만 사용한다.

## Builder와 identity

새 path와 target은 current USTAR의 보수적인 single-field UTF-8 100-byte bound를 지킨다.
Existing path 재사용은 이 bound를 만족하는 occurrence만 후보로 둔다. Remove/duplicate/
reorder는 기존 표현을 유지한다. Starting case가 builder-representable이면 M1의 multi-step
case도 표현 가능하다. 이미 unsupported인 input을 자동으로 고치지는 않는다.
Builder를 mutator에서 import하지 않으며 encoding 검증은 caller-level integration tests다.
Case identity는 기존 canonical ArchiveCase content address를 사용한다.

## Campaign binding dependency

Main `8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`의 `run_search_campaign` /
`SearchCampaignConfig`는 M1/A3를 실행하고 completed policy export/reader와
PolicyEvaluationConfig/dataset/statistics는 명시한 IDs를 보존/검증한다.
Legacy ExperimentConfig는 여전히 B3/legacy mutation만 허용하며 M1로 silent fallback하지 않는다.
Automatic policy journal/repetition과 aborted-prefix evidence는 연결 완료되지 않았다.
이 API 검증은 baseline 비교 실험 결과나 historical rediscovery가 아니다.

M1의 component tuple은 고정돼 있고 setup-derived dictionary API는 없다.
Default `outside/sentinel.txt`는 이 finite vocabulary와 benign seeds로 생성하지 못한다.
따라서 structural composition 구현과 selected benchmark reachability를 구분한다.
[Research Contract](research-contract-v1.md)의 첫 N01 qualification도 아직 NOT_RUN이다.

## A3 reorder contribution ablation

`uniform-generic-no-reorder-v1`과 `uniform-generic-m1-no-reorder-v1`은 각각 legacy/M1의
8개 slot을 같은 순서와 확률로 선택한다. Reorder slot도 원래 operator의 RNG draws를
소비하지만 계산된 child를 버리고 원본 case를 반환한다. 다른 slot의 결과는 그대로다.
재시도나 weight 재분배가 없으며 no-op child도 caller가 한 번 실행한다.

동일 input/RNG state에서 full/A3는 같은 slot과 같은 RNG 소비를 보장한다. 이후 campaign은
서로 다른 parent state 때문에 다른 draw stream을 가질 수 있으므로 campaign 전체의
draw 동일성을 주장하지 않는다. MutationPolicy에 명시적인 versioned ID를 저장한다.
M1/A3 ID는 SearchCampaignConfig와 completed policy evidence/config binding에 기록된다. Legacy ExperimentConfig 및 automatic policy journal/repetition 경계는 위와 같다.

## Transition scheduler boundary

P0/P1의 `UniformMutationScheduler`는 모든 operator weight를 1로 유지한다. P2의
`TransitionAdaptiveScheduler`는 normalized transition novelty만 binary reward로 받아
1..8 integer weight와 caller-owned `rng.randrange(total)`로 선택한다. Violation은 scheduler
evidence에 남지만 reward가 아니다. 정확한 정책과 evidence는
[transition-mutation-scheduler-v1.md](transition-mutation-scheduler-v1.md)를 따른다.

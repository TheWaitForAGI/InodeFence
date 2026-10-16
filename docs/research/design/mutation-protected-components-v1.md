# Generic protected-component addressing v1

## Status and claim boundary

- Current Layer: **Layer 4 Structure Mutator**
- Engineering status: **IMPLEMENTED / TESTED**
- Historical extractor qualification: **NOT_RUN**
- N01 rediscovery and feedback effectiveness: **NOT_RUN**

이 계약은 기존 M1의 출력 언어가 default controlled sentinel
`outside/sentinel.txt`의 두 component를 만들 수 없다는 generation blocker를 해결한다.
이는 target 실행, known-CVE positive control, benchmark admission 또는 취약점 재발견 결과가
아니다. 기존 `uniform-generic-m1-v1`의 grammar와 RNG 의미는 변경하지 않는다.

## Task Contract

### Objective

원래 네 benign seed에서 target/CVE와 무관한 bounded mutation을 통해 default controlled
sentinel의 상대 주소를 구성할 수 있게 하고, exact parent/child case identity와 TAR hash를
보존하는 constructive proof를 제공한다.

### Allowed changes

- M1의 기존 여덟 operator slot을 재사용하는 별도 versioned mutation policy;
- 기존 controlled runtime 이름에서 가져온 finite component tuple;
- `SearchCampaignConfig`와 transition/effect synthetic campaign이 이미 사용하는
  `MutationPolicy` binding;
- deterministic unit/integration tests와 관련 설계·상태 문서.

### Prohibited changes

- 기존 M1/legacy policy ID, component order, RNG draw 또는 output 변경;
- target/version/CVE/PoC 문자열이나 oracle 결과를 mutator 입력으로 사용;
- `SentinelSpec`, runtime layout, target adapter, Observer, C0/C1/C2 또는 feedback 의미 변경;
- 생성된 case의 path를 build/export 이후 runtime path로 치환;
- logical reachability를 historical execution이나 rediscovery로 표현.

### Acceptance criteria

1. 새 policy는 기존 여덟 slot과 uniform selection/no-retry 의미를 유지한다.
2. vocabulary는 finite하고 explicit하며 target/CVE 지식을 포함하지 않는다.
3. 원래 benign hardlink seed에서 `../outside/sentinel.txt` link target까지의 한 finite
   construction이 exact lineage와 deterministic TAR bytes로 검증된다.
4. 동일 seed/RNG는 동일 cases와 RNG state를 만들고 모든 결과는 current builder로 표현된다.
5. no-reorder ablation은 같은 slot/draw를 유지하고 reorder child만 버린다.
6. legacy `ExperimentConfig`는 새 policy로 silent fallback하지 않는다.

## Versioned policy and grammar

새 enum과 serialized ID는 다음과 같다.

| Enum | Policy ID | 의미 |
| --- | --- | --- |
| `M1_PROTECTED_COMPONENTS` | `uniform-generic-m1-protected-components-v1` | M1 slots + controlled protected component tuple |
| `M1_PROTECTED_COMPONENTS_NO_REORDER` | `uniform-generic-m1-protected-components-no-reorder-v1` | 같은 grammar에서 reorder contribution만 draw-preserving no-op |

Fresh path 생성의 prefix, depth, separator, reuse branch, byte bound와 draw 순서는 M1과
동일하다. Component tuple만 다음 값으로 고정한다.

```text
a, b, dir, file, item, ., .., outside, sentinel.txt
```

`outside`와 `sentinel.txt`는 현재 public controlled runtime의 default `SentinelSpec`에서
온 setup component다. 이 tuple에는 target ID, release, CVE, known PoC byte/string 또는
run-specific absolute path가 없다. Policy ID와 sentinel profile은 비교 실험 config에서 모든
arm에 동일하게 binding해야 한다. 다른 sentinel layout에는 새 versioned contract가 필요하며
runtime 이름을 암묵적으로 주입하지 않는다.

## Constructive engineering evidence

`minimal_seed_corpus()[2]`의 original hardlink seed에서
`MUTATE_LINK_TARGET` 한 번과 declared draws로 다음 child가 생성된다.

| Evidence | Value |
| --- | --- |
| Parent case ID | `de8ddc5ca4c15fccb638257bbbe671c4fcc9c707962cb92de6589a09f6418620` |
| Selected operator | `mutate_link_target` |
| Child link target | `../outside/sentinel.txt` |
| Child case ID | `55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87` |
| Deterministic USTAR SHA-256 | `2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6` |

이 표는 output-language reachability의 engineering proof다. Node-tar가 이 link target을
어떻게 해석하는지, target-visible mount/CWD가 frozen setup과 일치하는지, affected/fixed
release가 기대한 C1/C2 차이를 내는지는 별도 contained qualification에서 검증해야 한다.
Seed-phase C1/C2 cleanliness와 실제 hit probability도 아직 측정하지 않았다.

## Comparison and evidence boundary

`SearchCampaignConfig`는 모든 B0/B1/B3 arm에서 같은 새 policy를 선택할 수 있고 completed
policy evidence는 exact enum ID를 직렬화한다. P0/P1/P2 synthetic callers도 같은 dispatch
table을 사용할 수 있다. 별도 final-state journal/repetition 경로는 exact policy/operator와
full-step timing/interrupted prefix를 보존한다. 이 연결은 formal campaign configuration freeze,
historical reachability 또는 effectiveness를 완성하지 않는다.

기존 M1은 capability baseline과 과거 evidence 재현을 위해 계속 default-addressing 불가
상태로 남는다. 새 결과를 untouched M1의 성과로 표현하지 않는다.

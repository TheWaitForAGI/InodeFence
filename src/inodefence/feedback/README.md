# Feedback / Corpus v1

## 현재 입력과 출력

`state_signature(before, after) -> StateSignature`는 v3 normalization API다.
Layer 5는 `RunResult → Corpus.consider → FeedbackDecision`과
`Corpus.select_case(rng) → ArchiveCase`를 추가한다. 한 번의 실행은 여전히
`pipeline.run_case()`가 담당하며 Corpus는 실행이나 mutation을 호출하지 않는다.

[초기 signature](signature.py)는 Oracle과 독립적으로 snapshot을 정규화한다. **StateSnapshot = full raw observation/evidence**, **StateSignature = normalized security-state representation for feedback/corpus**다. Observer는 sandbox 전체를 기록하며 archive digest/harness metadata를 raw evidence에서 제거하지 않는다.

Schema version 3는 공통 Region에서 EXTRACTION/EXTERNAL object만 선택한다. `.`과 `archive/**` HARNESS object/metadata는 제외하며 **ArchiveCase identity와 TAR artifact identity를 직접 포함하지 않는다.** EXTERNAL은 `outside/**`와 root-level `escape.txt` 등 모든 unreserved extraction 밖 경로를 포함한다. Sorted path/type/mode, regular nlink/size/content digest, textual symlink target, scoped same-object groups, external change field labels 및 protected_paths를 담는다. Identity group도 선택한 object scope로 projection하고 singleton을 제거하여 harness path가 dangling relation을 만들지 않는다. 삭제된 sentinel의 보호 설정과 내부↔sentinel relation은 유지한다.

**Region.HARNESS는 security trust boundary가 아니다.** 이 제외는 input/harness novelty 오염을 막는 normalization 정책이고 C0의 extraction-boundary policy는 Oracle이 별도로 소유한다. `archive/escaped.txt`가 실행 중 생겨도 signature는 같을 수 있지만 C0는 violation이다. Corpus는 signature와 violation novelty를 독립적으로 계산하여 이 후보를 보존한다. Snapshot actor attribution은 runner/adapter lifecycle에 의존하고 transient operation/direct use/sandbox 밖 접근의 한계는 유지한다.

Raw st_dev/st_ino는 같은 run 안의 group 관계를 계산할 때만 사용한다. Signature에는 숫자 identity, timestamp/uid/gid 원값과 nonregular size가 없다. `SignatureObject.st_nlink`는 regular만 정수, directory/symlink/other는 None이다. Directory link count의 filesystem 차이를 key에 넣지 않지만 raw nlink/C2 metadata 비교와 external nlink-change labels는 보존한다. 이는 모든 filesystem의 effect pattern이 같다는 보장은 아니다. 모든 symlink target은 tag한다. Absolute run prefix가 일치하면 `run:<raw suffix>`, 그 외에는 `literal:<raw target>`이다. Exact root는 `run:`이며 repeated slash와 `..`는 그대로 보존한다. 따라서 literal relative `$RUN/...`과 `run:...`은 absolute run anchor와 구분된다. Extraction symlink의 harness target text도 유지하며 referent digest를 추가하지 않는다. 이는 path resolution이나 symlink referent identity 추론이 아니다.

정렬된 tuple과 [canonical JSON](../model/README.md)으로 cross-run key를 만들 수 있다. Envelope schema v1/case encoding과 signature 내부 v3는 별개다. 이전 signature와 key 호환성을 주장하지 않는다. [실제 E2E regression](../../../tests/test_pipeline.py)은 독립 regular entry의 순서를 바꿔 case ID/TAR SHA-256이 달라도 동일 semantic state의 signature/canonical JSON은 같음을 검증한다. 다른 inode allocation/PYTHONHASHSEED의 기존 테스트도 유지한다. Corpus v1은 현재 v3 value equality를 사용한다. V2의 untagged `$RUN` normalization과 key 호환성이나 migration을 제공하지 않는다. 최종 representation의 연구 가치는 evaluation/ablation에서 검증해야 한다.

## Public API

`inodefence.feedback.__all__`은 다음 API를 명시적으로 export한다.

| API | 의미 |
| --- | --- |
| `state_signature(before, after)` | 기존 normalized StateSignature v3 |
| `violation_fingerprints(violations)` | violated 결과의 sorted unique semantic fingerprint tuple |
| `ChangeFingerprint(path, fields)` | C0/C2의 observed path와 ChangeField labels |
| `IdentityFingerprint(internal_path, sentinel_path)` | C1의 내부↔sentinel 관계 |
| `ViolationFingerprint(contract_id, evidence)` | 한 contract의 전체 canonical evidence class |
| `FeedbackDecision(case_id, state_novel, new_violation_fingerprints, already_retained)` | 한 observation의 novelty와 admission 설명 |
| `CorpusEntry(case, admission_signature, admission_violation_fingerprints)` | mutation parent와 최초 admission metadata |
| `CorpusStats(observations, interesting_observations, retained_cases, unique_states, unique_violation_fingerprints)` | immutable search/reporting counters |
| `Corpus()` | in-memory evolving search state |

모든 노출 record는 frozen/slots dataclass와 tuple collection이다. `Corpus`만 evolving mutable object다.

Signature/effect, semantic fingerprint, FeedbackDecision와 CorpusEntry의 public constructor는
text/enum/bool과 nested typed tuple을 runtime에서 검증한다. Fingerprint는 해당 contract의
sorted unique evidence type을 요구한다. 이 검증은 evidence가 실제 Oracle에서 왔음을
증명하지 않으며 novelty/admission의 cross-record 관계는 Corpus가 생성한다.
CorpusStats는 Corpus-produced trusted counter snapshot이다. 임의 직접 construction의
counter arithmetic을 검증하는 reader/ingest API는 제공하지 않는다.

## 독립 novelty channel

`Corpus.consider(result: RunResult) -> FeedbackDecision`은 다음을 계산한다.

```text
state_novel = StateSignature가 이 Corpus에서 처음 관찰됨
new_violation_fingerprints = 처음 관찰한 semantic violation class들
interesting = state_novel OR bool(new_violation_fingerprints)
retained = interesting AND NOT already_retained
```

Seen state/violation indexes는 모든 observation에서 갱신한다. `case_id`는 이미 보존한
parent의 중복 방지에만 사용하며 novelty가 아니다. 다른 case/TAR가 같은 signature와
이미 본 violation class를 만들면 보존하지 않는다. 같은 retained case가 새 outcome을
만들면 `interesting=True`, `retained=False`, `already_retained=True`가 가능하다.
이때도 seen indexes와 interesting-observation count는 증가한다.

Entry에는 최초 admission observation의 signature와 **모든** violation fingerprints를
보존한다. `FeedbackDecision`의 새 fingerprint subset과 다르다. 이후 재관찰은 entry를
추가하거나 admission metadata를 덮어쓰지 않는다. Full RunResult, snapshot, 실행 로그나
mutation history는 entry에 넣지 않으며 raw evidence 보존은 campaign caller의 책임이다.

새 signature는 novel normalized state이고, 새 fingerprint는 새 contract-violation
evidence class/candidate다. 어느 것도 자동으로 vulnerability를 확정하지 않는다.
Retention은 다음 mutation parent로 보존할 가치가 있다는 뜻이다.

## Stable violation fingerprints

[fingerprint.py](fingerprint.py)는 Oracle의 기존 violated verdict만 소비한다.
Contract를 재판정하거나 observed/raw archive path를 normalize하지 않는다.

- C0/C2: `StateChange.path`, `StateChange.fields`만 사용한다. Before/after
  ObjectSnapshot, 실제 timestamp/content/mode 값이나 dev/inode 숫자는 제외한다.
- C1: `IdentityEvidence.internal_path`, `sentinel_path`만 사용한다.
  Raw `(st_dev, st_ino)`는 동일 run의 Oracle evidence에 남으며 cross-run key에는 없다.
- Contract ID도 key에 포함하여 C0와 C2의 같은 path/fields를 구분한다.
  Explanation/limitations text와 execution status/exit code/duration은 사용하지 않는다.
- Evidence는 schema-ordered field labels와 sorted unique path/relation tuple이다.
  Results도 contract/evidence 기준 sorted unique tuple이며 incidental iteration order와
  중복 evidence에 영향받지 않는다. Nonviolation은 fingerprint를 만들지 않는다.

한 fingerprint는 **한 violated contract의 전체 evidence tuple**이다. Path/relation이
추가되면 다른 class가 된다. EXISTENCE creation/deletion은 같은 class이고, 서로 다른
변경 값도 같은 path/fields라면 같은 class다. 필요 시 normalized resulting state는
별도 StateSignature channel에서 구분하며, raw reproduction evidence는 RunResult에 남는다.
Fingerprint equality는 동일 root cause나 finding임을 증명하지 않는다.

## Selection과 stats

`Corpus.select_case(rng: random.Random) -> ArchiveCase`는 insertion order의 retained
entries에서 균등 선택한다. 같은 insertion order와 caller RNG state는 같은 parent를
선택한다. Global random이나 implicit seed를 쓰지 않는다. Empty corpus는 명시적인
`ValueError`를 발생시키며 RNG를 소비하거나 seed를 생성하지 않는다.
이는 baseline selector이며 adaptive scheduler 또는 검증된 연구 전략이 아니다.

`Corpus.entries`는 admission order의 tuple snapshot이고 `len(corpus)`는 retained case
수다. `Corpus.stats`는 새 immutable snapshot이며 selection으로 바뀌지 않는다.

| Counter | 의미 |
| --- | --- |
| `observations` | consider한 RunResult 수 |
| `interesting_observations` | decision.interesting이 True인 observation 수 |
| `retained_cases` | 현재 mutation 가능한 unique case 수 |
| `unique_states` | 관찰한 StateSignature 수 |
| `unique_violation_fingerprints` | 관찰한 stable violation class 수 |

이 counters는 search/reporting state이며 paper metric이나 연구 결과가 아니다.

## Caller 수준의 조합

```python
import random

from inodefence.feedback import Corpus
from inodefence.mutator import mutate
from inodefence.pipeline import run_case

# case와 target은 호출자가 정한다. 개별 API의 caller 수준 조합 예다.
corpus = Corpus()
result = run_case(case, target)
decision = corpus.consider(result)
rng = random.Random(1234)
parent = corpus.select_case(rng)
child = mutate(parent, rng)
```

Corpus는 parent를 선택하고 Mutator는 case를 변형한다. Mutator → Feedback dependency는
없으며 Corpus도 Mutator/pipeline/target/runtime/observer/oracle/builder를 import하지 않는다.
기존 `state_signature`의 snapshot normalization 의존성은 그대로 유지한다.

## Campaign context와 현재 한계

**한 Corpus instance는 한 caller-controlled campaign context에 속한다.** RunResult에는
완전한 stable campaign key가 없다. Formal runner가 InodeFence commit, target/version과
설정, OS/kernel/architecture, seed/budget/timeout과 dependency version을 기록해야 한다.
Corpus는 dynamic command path를 hash하거나 false campaign ID를 만들지 않는다.
Cross-target persistence safety를 주장하지 않으며 이번 v1에는 disk persistence가 없다.

[Bounded campaign](../campaign.py)은 상위 caller에 구현됐다. Third-party campaign은
validated backend와 enforced IsolatedTarget composition을 요구하며 contained Node의
tiny benign configured campaign을 검증했다. Snapshot 관찰 범위와 runtime/kernel trust 및
portability 한계는 유지한다. Adaptive scheduler, persistence/checkpoint, 추가 adapters,
C3/C4, lineage DB와 historical/formal effectiveness 검증은 후속 작업이다. Generic minimizer와 evaluation infrastructure는 상위 모듈에 구현됐다. A1/A2/A3는 구현/테스트됐지만 효과는 미검증이다. 계약 정의는
[Oracle](../oracle/README.md)과 canonical contract 문서에 둔다.

[단위 테스트](../../../tests/test_feedback_corpus.py)는 semantic fingerprint, 독립 novelty,
duplicate-case behavior, stats와 immutable records/caller RNG를 검증한다.
[Integration regression](../../../tests/test_feedback_corpus_integration.py)은 실제 `run_case`
관찰 구간의 C0/HARNESS same-signature admission, input/process/raw-allocation isolation과
caller 수준의 select → mutate → 단일 실행 조합을 검증한다.

## Versioned search-policy core

`SearchPolicy`, `SearchState(initial_cases, policy)`, `SearchDecision`은 독립 B0/B1/B3
policy API다. Full diagnostic novelty와 explicit admission을 분리하고 B0는 이전 child로
전진한다. Legacy Corpus/B3 campaign serialization은 유지한다.
[Core 계약과 campaign/Evaluation 통합 요구사항](../../../docs/research/design/search-policy-core-v1.md)을
따른다. `run_search_campaign` / `SearchCampaignConfig`는 이 IDs를 실행하며 separate completed
policy export/reader/config/dataset binding도 구현됐다. Legacy ExperimentConfig는 여전히 B3/legacy만
지원한다. Automatic policy journal/repetition은 연결 완료되지 않았으며 silent fallback은 없다.
Capability baseline과 claim 범위는 [Research Contract](../../../docs/research/design/research-contract-v1.md)를 따른다.

`FeedbackProjection` / `feedback_key`는 A1/A2 admission-key ablation을 제공한다.
SearchDecision v2는 full-state novelty와 projected-key novelty를 구분한다.
Raw RunResult evidence와 legacy FeedbackDecision은 유지한다.

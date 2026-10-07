# 시스템 아키텍처

이 문서는 InodeFence의 **상세 시스템 아키텍처에 대한 canonical source**다.

하위 README는 자기 폴더의 책임과 탐색 경로만 설명한다. Security Contract의 정확한 정의는 [security-contracts.md](security-contracts.md), 큰 설계 결정의 이유는 [../../DECISIONS.md](../../DECISIONS.md), 현재 구현 단계는 [../../STATUS.md](../../STATUS.md)를 따른다.

이 문서의 목적은 단순히 “어떤 폴더가 있다”를 설명하는 것이 아니다. 팀원과 코딩 에이전트가 다음 질문에 같은 답을 하게 만드는 것이 목적이다.

- InodeFence가 무엇을 탐색하는가?
- testcase는 내부에서 어떤 형태로 흐르는가?
- 각 모듈은 무엇을 입력받고 무엇을 출력하는가?
- filesystem의 어떤 사실을 관찰하는가?
- 관찰과 보안 판정은 왜 분리하는가?
- 어떤 testcase를 다시 mutation 대상으로 남기는가?
- finding과 raw result와 paper claim은 어떻게 구분하는가?
- 지금 구현해야 하는 것과 미래 확장을 어떻게 구분하는가?

---

## 1. 현재 상태와 용어

현재는 **개발 Layer 2, 최소 Layer 3, Layer 4 Generic Mutation v1과 Layer 5 Feedback / Corpus v1 구현** 단계다. Feature branch의 구현 상태 표시는 main merge를 의미하지 않는다.

ArchiveCase → 결정적 USTAR → Python reference worker → pre/post snapshot → C0/C1/C2 evidence의 실제 API가 있다. Generic Mutation v1은 별도 ArchiveCase → ArchiveCase API다. Layer 5는 RunResult의 독립 state/violation novelty에 따른 in-memory retention과 uniform caller-RNG parent selection을 제공한다. Bounded campaign v1은 명시적 seed와 execution budget으로 API를 조합한다. Minimal seed generator는 기존 4종 정상 baseline을 명시적으로 제공한다. Node-tar는 별도 contained target으로 정상 fixture와 tiny benign configured campaign을 검증했다. 추가 adapters, adaptive scheduler/persistence 및 evaluation은 후속 단계다.

Pre-audit freeze, Audit Phases 1–2와 Global Findings Freeze v1을 완료했고 Phase-3 Runtime #45 / Engine #46 fixes는 main `d1982e4`에 병합됐다. 현재는 Phase-4 global closeout 대기 단계다. Container-backed target,
frozen isolation/config/provenance와 benign Node full-path, lifecycle 및 staged export를 검증했다.
EN-001–004의 functional engine fixes는 최종 검증을 통과했다. Audited main의 잔여 EN-005 navigation drift는 [final audit #47](https://github.com/TheWaitForAGI/InodeFence/pull/47)에 기록했고 이 PR #35에서 문서 correction을 제안한다. Global verdict나 benchmark readiness를 앞당기지 않는다. Development tests/smoke는
evaluation 결과가 아니다. [현재 상태](../../STATUS.md)와 [실제 검증 기록](../../../experiments/summaries/pre-audit-readiness-v1.md)을 따른다.

아래 개념 그림에는 lineage, tracing, corpus 등 미래 설계도 포함한다. 현재 확정된 field/API는 **7.8 현재 구현 경계**를 따른다. Python reference는 최종 benchmark target이 아니다.

### 개발 Layer와 Runtime Stage를 구분한다

프로젝트 진척도는 **개발 Layer**로 표현한다.

```text
Layer 0  재현 가능한 개발환경
Layer 1  연구 문맥 / 범위 / 아키텍처
Layer 2  공통 Data Model
Layer 3  Minimal End-to-End Pipeline
Layer 4  Generic Mutation
Layer 5  Feedback / Corpus
Layer 6  Experiment / Paper
```

반면 testcase 하나가 실제로 흘러가는 책임 순서는 **Runtime Stage**로 표현한다.

```text
Stage A  Seed / Case Generation
Stage B  Structure Mutation
Stage C  TAR Serialization
Stage D  Target Execution
Stage E  State Observation
Stage F  Security Evaluation
Stage G  Feedback / Corpus
```

예를 들어 “Generator는 Stage A”이지 “개발 Layer 1”이라는 뜻이 아니다.

---

## 2. 한 문장으로 보는 InodeFence

> InodeFence는 TAR testcase의 구조를 generic rule로 변화시키고, 실제 extractor가 만든 filesystem security state를 관찰한 뒤, 보안적으로 의미 있는 새로운 상태를 다음 탐색의 feedback으로 사용하는 archive-extraction security fuzzing 연구 프로토타입이다.

핵심은 단순 crash 탐지가 아니다.

```text
TAR 구조
  ↓
실제 extractor 실행
  ↓
filesystem에 생긴 상태 관찰
  ↓
Security Contract와 비교
  ↓
새롭고 의미 있는 상태인지 평가
  ↓
다음 mutation의 출발점으로 보존
```

---

## 3. 전체 시스템은 세 Plane으로 본다

~~~mermaid
flowchart TB
    subgraph R["Research Plane"]
        RQ["Research Question"]
        TM["Threat Model"]
        SC["Security Contracts"]
        RW["Related Work / CVE Analysis"]
        ED["Experiment Design"]
        RQ --> TM --> SC
        RW --> RQ
        SC --> ED
    end

    subgraph E["Runtime Engine"]
        C["Case Generation"]
        M["Mutation"]
        B["TAR Serialization"]
        T["Target Execution"]
        O["State Observation"]
        Q["Security Evaluation"]
        F["Feedback / Corpus"]
        C --> M --> B --> T --> O --> Q --> F
        F -. next case .-> M
    end

    subgraph V["Evidence Plane"]
        RAW["Raw Experiment"]
        PF["Potential Finding"]
        RP["Reproduction / Minimization"]
        AG["Aggregated Result"]
        PP["Paper Evidence"]
        RAW --> PF --> RP
        RAW --> AG
        RP --> PP
        AG --> PP
    end

    SC --> Q
    ED --> E
    E --> RAW
~~~

### Research Plane

무엇을 연구하는지와 무엇을 위반으로 보는지를 정의한다.

### Runtime Engine

실제 TAR testcase를 생성·변형·실행·관찰·판정·선택한다.

### Evidence Plane

실행 결과를 재현 가능한 finding과 실험 결과로 정제하고, 그중 검토된 내용만 논문 근거로 사용한다.

**raw 결과가 곧 논문 주장은 아니다.**

---

## 4. Runtime 전체 Pipeline

~~~mermaid
flowchart LR
    S["Seed / ArchiveCase"] --> M["Structure Mutator"]
    M --> B["TAR Builder"]
    B --> T["Target Adapter"]
    T --> X["Real Extractor"]
    X --> O["State Observer"]
    O --> SS["StateSnapshot"]
    SS --> Q["Security Oracle"]
    SS --> SG["State Signature"]
    Q --> VR["ViolationResult"]
    SG --> F["Feedback"]
    VR --> F
    F -->|interesting| C["Corpus"]
    C --> M
    F -->|not interesting| D["Discard / Deprioritize"]
~~~

이 그림은 최종 목표 구조다.

현재 구현은 **공통 Data Model → 최소 관찰 경로**, 별도 Generic Mutation v1과 Feedback / Corpus v1이다. Bounded campaign v1은 명시적 seed/budget과 parent lineage/full RunResult를 보존한다. 연구 효과를 검증한 단계는 아니다.

---

## 5. Repository와 Runtime 책임 연결

| 책임 | 현재 위치 | 핵심 질문 |
| --- | --- | --- |
| 공통 Data Model | [model/](../../../src/inodefence/model/README.md) | 모듈끼리 무엇을 주고받는가? |
| Seed Generator | [generator/](../../../src/inodefence/generator/README.md) | 최초 case는 어떻게 생기는가? |
| Structure Mutator | [mutator/](../../../src/inodefence/mutator/README.md) | 기존 case를 어떤 generic rule로 바꾸는가? |
| TAR Builder | [builder.py](../../../src/inodefence/builder.py) | 논리 case를 실제 TAR로 어떻게 표현하는가? |
| Target Adapter | [targets/](../../../src/inodefence/targets/README.md) | 실제 extractor를 어떻게 실행하는가? |
| State Observer | [observer/](../../../src/inodefence/observer/README.md) | filesystem에 실제로 무슨 일이 생겼는가? |
| Security Oracle | [oracle/](../../../src/inodefence/oracle/README.md) | 관찰 상태가 어떤 Contract를 위반하는가? |
| Feedback / Corpus | [feedback/](../../../src/inodefence/feedback/README.md) | 다음 탐색에 남길 가치가 있는가? |

단일 실행 Runner는 [pipeline.py](../../../src/inodefence/pipeline.py), runtime lifecycle은 [runtime.py](../../../src/inodefence/runtime.py)에 둔다. Builder/Runner는 작은 module이며 Corpus v1은 기존 feedback package의 corpus.py에 둔다. **필요성이 생기기 전에는 빈 추상화와 디렉터리를 미리 만들지 않는다.**

---

## 6. 핵심 Data Flow

~~~mermaid
flowchart TD
    AE["ArchiveEntry"] --> AC["ArchiveCase"]
    AC --> TAR["TAR Artifact"]
    TAR --> ER["ExecutionResult"]
    PRE["Pre-State"] --> SS["StateSnapshot"]
    ER --> POST["Post-State"]
    POST --> SS
    SS --> SIG["StateSignature"]
    SS --> VR["ViolationResult"]
    SIG --> FD["Feedback Decision"]
    VR --> FD
    AC --> FD
~~~

중요한 점은 다음 두 결과가 `StateSnapshot`에서 **갈라진다**는 것이다.

```text
StateSnapshot
   ├──→ StateSignature     "이 상태는 이전과 어떻게 다른가?"
   └──→ ViolationResult    "이 상태는 Contract를 위반했는가?"
```

`Interesting`과 `Vulnerable`은 같은 뜻이 아니다.

---

# 7. 공통 Data Model 설계

아래 개념 구조는 모델의 의미적 책임과 미래 확장 후보를 설명한다. 현재 Python field와 type은 7.8 및 [model](../../../src/inodefence/model/README.md)을 따른다.

## 7.1 ArchiveEntry

TAR 내부의 **entry 하나**를 논리적으로 표현한다.

초기 entry type 후보:

- regular file
- directory
- hardlink
- 필요한 범위의 symlink

개념 구조:

```text
ArchiveEntry
├── path
├── entry_type
├── content
├── link_target
├── mode
├── uid / gid
└── metadata
```

ArchiveEntry는 raw TAR header나 byte buffer 그 자체가 아니다.

목표는 다음과 같다.

- 사람이 읽을 수 있다.
- mutation이 쉽다.
- TAR encoding 세부사항과 분리된다.
- target-specific 정보가 들어가지 않는다.

---

## 7.2 ArchiveCase

한 번의 fuzzing 입력 전체를 표현한다.

```text
ArchiveCase
├── case_id
├── entries[]
├── parent_case_id
├── mutation_history
└── generation_metadata
```

예:

```text
ArchiveCase
├── Entry 0: a.txt [REGULAR]
└── Entry 1: b.txt [HARDLINK → a.txt]
```

가능하면 mutation은:

```text
ArchiveCase
    ↓
generic transformation
    ↓
ArchiveCase
```

형태를 유지한다.

---

## 7.3 ExecutionResult

Target Adapter가 extractor를 실행한 **프로세스 실행 결과**다.

현재 필드:

```text
ExecutionResult
├── target_id
├── target_version
├── command
├── status
├── exit_code
├── stdout
├── stderr
├── duration_seconds
└── timeout_seconds
```

`ExecutionResult`와 filesystem 상태는 같은 것이 아니다.

`exit_code == 0`이어도 Security Contract 위반이 있을 수 있고, `exit_code != 0`이어도 남겨진 filesystem state가 분석 가치가 있을 수 있다.

**ExecutionResult = process evidence, not security verdict.** `ExecutionStatus.TIMED_OUT`가 authoritative이고 별도 timed_out bool은 없다. Configured timeout과 actual monotonic elapsed duration의 현재 contract와 측정 구간은 7.8을 따른다.

---

## 7.4 ObjectSnapshot

filesystem object 하나에 대한 관찰 결과다.

초기 후보:

```text
ObjectSnapshot
├── relative_path
├── object_type
├── st_dev
├── st_ino
├── st_nlink
├── mode
├── size
├── symlink_target
└── selected_content_hash
```

여기서 핵심은 path 문자열뿐 아니라 **object identity 관계**를 관찰할 수 있는 정보다.

Linux에서 초기 identity 기준은 주로:

```text
(st_dev, st_ino)
```

관계다.

---

## 7.5 StateSnapshot

특정 시점의 sandbox 전체를 나타낸다. **StateSnapshot = full raw observation/evidence**이며 harness artifact도 관찰한다.

```text
StateSnapshot
├── sandbox_root
├── phase
├── objects (extraction / harness / external 전체)
└── protected_paths (sentinel 삭제 후에도 유지)
```

초기 구현은 syscall 전체 trace보다 다음을 우선한다.

```text
Pre-State
   +
extractor execution
   +
Post-State
```

이 방식으로 먼저 관찰 가능한 contract부터 검증한다.

---

## 7.6 StateSignature

**StateSignature = normalized security-state representation for future feedback/corpus**다. Feedback을 위해 security-relevant filesystem state를 비교 가능한 형태로 정규화한다. Snapshot 전체를 그대로 key로 바꾸지 않는다.

ArchiveCase identity와 TAR artifact identity는 signature에 직접 포함하지 않는 invariant를 따른다. 입력 순서/bytes가 달라도 같은 semantic filesystem/security state와 effect를 만들면 signature는 같아야 한다. HARNESS object와 metadata는 제외하지만 raw evidence에서는 보존한다.

실행마다 달라질 수 있는 raw inode 번호 자체를 corpus key로 사용하면 안 된다.

피해야 할 예:

```text
inode = 482913
```

선호하는 관계 표현:

```text
inside_A and inside_B share identity
inside_A shares identity with protected sentinel
symlink_A resolves toward path class B
external sentinel content changed
```

signature 후보 축:

- object type pattern
- identity relation pattern
- link relation pattern
- path relation pattern
- external-effect pattern
- contract-relevant state class

현재 normalized representation은 7.8의 StateSignature v3로 고정하며 Corpus v1은 이
value equality를 사용한다. 후속 evaluation/ablation은 representation의 연구 가치를 검증한다.

---

## 7.7 ViolationResult

Security Oracle의 판정 결과다.

개념 구조:

```text
ViolationResult
├── violated
├── contract_id
├── evidence
├── explanation
└── optional classification
```

예:

```text
Contract: C1 Object Identity Confinement

Evidence:
extract/result.txt
outside/sentinel

share:
st_dev = X
st_ino = Y
```

판정 결과에는 사람이 재현하고 설명할 수 있는 evidence가 남아야 한다.

---

## 7.8 현재 구현 경계

모델은 frozen/slots dataclass, enum과 ordered tuple을 사용한다. Model은 실행/관찰/판정 모듈을 import하지 않는다.

| 모델 | 현재 field / 의미 |
| --- | --- |
| ArchiveEntry | path, entry_type, content, link_target, mode; raw input text 보존 |
| ArchiveCase | entries tuple; canonical logical representation의 SHA-256 case_id property |
| ExecutionResult | target_id/version, command, status, exit_code, stdout/stderr, duration_seconds(actual), timeout_seconds(budget) |
| ObjectSnapshot | canonical sandbox-relative path, ObjectType, dev/inode/nlink, permission/special mode bits/size, uid/gid, mtime/ctime ns, raw link text, regular content_digest(SHA-256 lowercase hex) |
| StateSnapshot | full raw observation: absolute sandbox_root provenance, BEFORE/AFTER phase, harness 포함 sorted objects, protected_paths |
| StateChange | path, before/after ObjectSnapshot 또는 None, actual difference와 정확히 일치하는 ordered ChangeField tuple |
| StateSignature | schema v3, EXTRACTION/EXTERNAL normalized objects, scoped same-object groups, external field-change labels, protected_paths |
| ViolationResult | contract_id, violated, typed evidence, explanation, limitations |
| RunResult | case, archive_sha256/format, execution, before/after, changes, signature, violations |
| ExecutionProvenance | 실행 전 source(revision/dirty), environment(platform strings), declared target(ID/version/timeout/execution_safety), sorted sentinel(name/content SHA-256/mode) |

Archive input은 `Path.resolve()`/normalization을 거치지 않는다. NUL, surrogate code point, 잘못된 entry field 조합은 model boundary에서 거부한다. regular content는 immutable bytes이며 directory는 content/target을 가지지 않는다. link는 nonempty target 필수다. Duplicate entry와 entry 순서는 그대로 유지한다. Long name은 model에 허용하지만 현재 builder가 표현할 수 없는 USTAR 값은 명시적으로 거부한다.

Public immutable evidence constructor는 scalar type와 nested tuple/member type를 검증한다.
StateChange는 exact raw difference labels를 요구한다. RunResult의 cross-record TAR/snapshot/
signature/verdict correspondence는 pipeline-owned trusted assembly다. CampaignStep/Result와
CorpusStats도 runner/Corpus의 trusted derived output이며 임의 construction은 evidence ingest가
아니다. [Model boundary](../../../src/inodefence/model/README.md)를 따른다.

ExecutionResult의 `timeout_seconds`는 configured execution budget이고 필수 `duration_seconds`는 실제 monotonic elapsed process execution evidence다. Duration은 bool을 제외한 int/float 값으로 finite/0 이상이어야 하며 0.0과 numeric int 값도 허용한다. Python reference는 `perf_counter()`로 subprocess.run 직전부터 완료 또는 timeout exception 처리 진입 직후까지 측정한다. Process startup과 timeout kill/wait overhead를 포함하며 path validation, snapshot, oracle/signature 계산과 cleanup 시간은 제외한다. Timeout 설정값을 duration으로 복사하지 않는다. 모든 반환 status에 기록하고 RunResult의 execution을 통해 canonical JSON으로 보존한다. Observer/Oracle/Feedback은 duration을 security verdict로 사용하지 않으며 StateSignature v3와 case ID에도 포함하지 않는다.

**Archive input path != Observed filesystem path.** `ArchiveEntry.path`/`link_target`은 `../` 및 absolute-looking spelling을 보존하는 untrusted raw logical input이며 normalization하지 않는다. `ObjectSnapshot.path`는 Observer가 만든 canonical sandbox-relative evidence다. Absolute path, 빈/`.`/`..` component는 거부한다(루트 자체의 `.`는 허용). StateSnapshot.objects는 canonical path 기준 unique/sorted이며 ArchiveCase의 duplicate/order semantics를 적용하지 않는다. Malformed TAR encoding fuzzing은 향후 Builder/encoding mutation layer의 책임이며 ObjectSnapshot/StateSnapshot invariant를 느슨하게 만들지 않는다.

ObjectSnapshot은 ObjectType enum, nonnegative integer dev/inode/nlink/size/uid/gid, integer mtime/ctime ns를 검증한다. `mode = stat.S_IMODE(st_mode)`는 permission/special mode bits(`0..0o7777`)이며 object type bits를 포함하지 않는다. `content_digest`는 regular file content의 SHA-256 lowercase hexadecimal evidence(64자)이며 regular에 필수, 다른 type에는 None이다. Symlink에만 nonempty raw readlink target이 필수이며 resolve하지 않는다. Identity는 `(st_dev, st_ino)`다. Hardlink는 별도 type이 아닌 same-identity regular object 관계이고 symlink identity는 referent가 아닌 lstat object 자체다. Snapshot에 없는 path는 부재이며, sentinel 설정은 삭제 후에도 남는다. IO 오류는 부재로 바꾸지 않고 ObservationError로 올린다.

Region은 model의 `path_region`에서 공통으로 정의하며 Observer/Oracle/Feedback에 별도 path 예외를 두지 않는다.

`path_region()`은 아래 namespace 분류를 따르는 현재 runtime-layout policy이며 filesystem object의 intrinsic property가 아니다. 향후 target/runtime layout 확장 시 함께 검토한다.

| Region | namespace scope |
| --- | --- |
| EXTRACTION | `extract`, `extract/**` |
| HARNESS | `.`, `archive`, `archive/**`; 입력과 harness bookkeeping |
| EXTERNAL | 나머지 모든 canonical sandbox-relative path; `outside/**` 및 root-level `escape.txt` 포함 |

Region.HARNESS는 normalization role이며 security trust boundary나 creator attribution이 아니다. Model의 `is_extraction_path`는 `extract`/`extract/**` membership만 정의한다. Oracle의 `_is_c0_namespace_transition`은 그 밖의 모든 경로에서 EXISTENCE/IDENTITY/OBJECT_TYPE 전이를 검사한다. 따라서 HARNESS object는 signature에서 제외되어도 C0에서 면제되지 않는다. `archive/escaped.txt` 생성과 archive/input.tar 삭제·replacement도 evidence다. Content/metadata-only effect는 기존 C0/C2 separation을 유지한다.

StateSnapshot은 세 region 전체와 TAR content digest를 보존한다. StateSignature v3는 HARNESS object를 제외하며 case ID/TAR SHA-256을 직접 포함하지 않는다. Path/type/mode, regular nlink/size/content digest, textual link target, same-object path group과 external change 종류를 담는다. Identity group은 signature object scope로 projection한 뒤 singleton을 제거하므로 제외된 harness path가 dangling relation을 만들지 않는다. Protected paths는 sentinel 삭제 뒤에도 유지한다.

`SignatureObject.st_nlink`는 `int | None`이며 regular만 정수, directory/symlink/other는 None이다. Raw dev/inode, timestamp/ownership 값과 nonregular size도 제외한다. Raw nlink는 Observer와 C2에 그대로 남고 외부 metadata-change labels도 보존하므로 cross-filesystem effect equivalence까지 보장하지는 않는다. Raw identity는 run 안에서 group을 계산하거나 identity 변경을 감지할 때만 쓴다. Symlink target은 absolute sandbox prefix가 일치하면 `run:<raw suffix>`, 그 외에는 `literal:<raw target>`으로 tag한다. Exact root의 suffix는 비어 있고 slash와 `..` 철자는 유지한다. Literal `$RUN/...` 또는 `run:...`은 absolute run anchor와 구분된다. Resolution/reachability는 추론하지 않는다. Extraction symlink가 harness를 가리키는 link text는 유지하되 harness referent digest/identity를 포함하지 않는다. 이 representation은 초기 후보이며 Layer 5의 baseline/ablation 정책을 미리 확정하지 않는다.

실제 `run_case()` regression은 동일 content/mode의 독립 regular entry 두 개를 반대 순서로 추출한다. Case ID/TAR SHA-256은 다르지만 signature와 canonical representation은 같아야 한다. 다른 inode allocation/PYTHONHASHSEED의 기존 regression도 유지한다.

`canonical_json(model)`의 기본 envelope schema version은 1이며 ExecutionProvenance/CampaignResult는 명시적으로 v2다. Model type, sorted JSON keys, ordered tuple 배열은 유지한다. Signature 내부 schema version은 3이며 이전 signature와 key 호환성을 주장하지 않는다. Bytes는 base64로 lossless export한다. Raw run evidence는 run-specific inode/times를 보존하고 cross-run key는 logical case 또는 normalized signature로 만든다. Deserialize/database layer는 아직 없다. Campaign은 실행 전 InodeFence commit/dirty와 process OS/kernel/platform 정보를 ExecutionProvenance에 고정한다. ExperimentConfig v1/v2는 explicit 설정과 stable ID를 제공한다. Contained Node는 immutable image ID와 실제 worker/lock digest를 기록한다. 전체 controller/Python executable/dirty patch contents attestation은 제공하지 않는다.

현재 내부 API:

```text
build_tar(case) -> bytes
disposable_sandbox(sentinels) -> context manager[RuntimeSandbox]
TargetAdapter.run(archive_path, extraction_root) -> ExecutionResult
capture_state(root, phase, protected_paths) -> StateSnapshot
compare_states(before, after) -> tuple[StateChange, ...]
evaluate_contracts(before, after) -> tuple[ViolationResult, ...]
state_signature(before, after) -> StateSignature
run_case(case, target, sentinels=...) -> RunResult
```

Generic pipeline이 target CLI, vulnerability recipe, mutation/corpus 정책을 소유하지 않는다. Oracle은 filesystem에 접근하지 않는다. Snapshot 비교는 사실만 반환하며, signature와 계약 판정은 이를 독립적으로 사용한다. 실제 [사용 예](../../../README.md)는 reference adapter를 주입한다.

Layer 5의 추가 public records는 model을 재설계하지 않고 feedback package에 둔다.

| Record | 현재 field / 의미 |
| --- | --- |
| ChangeFingerprint | path, fields; raw ObjectSnapshot/value 제외 |
| IdentityFingerprint | internal_path, sentinel_path; raw dev/inode 제외 |
| ViolationFingerprint | contract_id, sorted unique semantic evidence tuple |
| FeedbackDecision | case_id, state_novel, new_violation_fingerprints, already_retained; interesting/retained는 derived properties |
| CorpusEntry | case, admission_signature, admission_violation_fingerprints; 최초 admission의 모든 fingerprints |
| CorpusStats | observations, interesting_observations, retained_cases, unique_states, unique_violation_fingerprints |

```text
violation_fingerprints(violations) -> tuple[ViolationFingerprint, ...]
Corpus.consider(result: RunResult) -> FeedbackDecision
Corpus.select_case(rng: random.Random) -> ArchiveCase
Corpus.entries -> tuple[CorpusEntry, ...]
Corpus.stats -> CorpusStats
len(corpus) -> retained case count
```

기존 StateSnapshot/StateSignature/ViolationResult/RunResult와 single-case `run_case()` 책임은
유지한다. Corpus는 실행/관찰/계약 판정/변형을 수행하지 않는다. 상세 정책은 16을 따른다.

---

# 8. Execution Sandbox

별도 [container backend](../../../src/inodefence/execution/README.md)는 trusted Linux
controller → explicit host stdio broker → disposable target container 경계를 구현한다.
Current run의 named-volume subpath만 공유해 Observer inode identity와 sentinel evidence를
유지한다. 준비 context는 BEFORE 이전 생성/정책 확인, execution은 stopped PID namespace
이후 반환, context exit는 AFTER 이후 removal이다. Backend는 target/Oracle/feedback을
알지 않는다. Dev Container 자체를 target sandbox로 바꾸지 않는다. 아래 campaign gate는
exact IsolatedTarget composition과 frozen isolation policy/attestation에 연결됐다.

현재 enforced safety contract는 TargetProvenance.execution_safety의 ExecutionSafety enum이다.
Default ISOLATION_REQUIRED이며 Python reference는 TRUSTED_REFERENCE를 선언한다. Campaign은
explicit trusted reference 또는 exact contained composition을 허용한다. 미선언/uncontained
isolation-required target은 provenance capture/runtime/
첫 run_case 이전에 거부한다. Caller의 supplied provenance가 requirement를 낮출 수 없다.
선언은 OS containment 증명이 아니다. Contained campaign에는 enforced backend와 frozen
policy/attestation이 필요하며 config가 있으면 actual policy와 exact binding을 검증한다.
Low-level contained adapter.run/run_case도 backend를 강제한다. Configured contained campaign은
현재 승인된 tiny benign smoke로 검증했으며 security evaluation은 full audit 이후 별도 Task Contract다.

Dev Container와 CI는 source/설정된 volume/동일 사용자 파일/network 접근을 포함하는 development
환경이다. Runtime directory, subprocess, data filter, cleanup은 이를 privilege sandbox로 바꾸지
않는다. Future adapter campaign은 검증된 process/filesystem/credential/network/resource 경계와
timeout 후 전체 자식 process 종료를 제공해야 한다. 정상 fixture adapter integration과 hostile-input
campaign readiness는 별도다. Requirement는 stored provenance/export에 남고 C0/C1/C2와 무관하다.

filesystem security 연구에서는 **어디에서 실행하는가** 자체가 설계의 일부다.

기본 runtime root:

```text
$INODEFENCE_RUNTIME_ROOT
/var/lib/inodefence
```

source bind mount인 `/workspaces/InodeFence`는 filesystem semantics 실험 공간으로 사용하지 않는다.

한 testcase 실행 공간의 개념 구조:

```text
/var/lib/inodefence/
└── runs/
    └── <run-id>/
        ├── archive/
        │   └── input.tar
        ├── extract/
        ├── outside/
        │   └── sentinel
        └── metadata/
```

정확한 directory layout은 구현 시 조정할 수 있지만 다음 경계는 유지한다.

```text
extract/
──────────── security boundary
outside/
```

현재 layout은 runtime root의 `core-run-<random>/archive/input.tar`, `extract/`, `outside/`다. Runtime root는 기존 Linux `/var/lib/inodefence` 또는 그 하위의 명시적 환경 설정만 허용한다. Configuration path의 모든 component는 O_NOFOLLOW로 검증한다. Sentinel은 safe relative name/bytes/mode로 생성하고, 정상·실패 종료 모두 symlink-resistant cleanup을 적용한다. Case path는 이 검증 과정에 넣어 변형하지 않는다.

### Observation window와 baseline ownership

Harness-owned baseline은 `.`, archive, archive/input.tar, extract, outside, controlled sentinel 등 BEFORE에 존재하는 실제 object다. Region이 실제 생성 주체를 증명하지는 않는다. 현재 lifecycle은 다음과 같다.

```text
disposable_sandbox: layout / sentinel setup
→ run_case: input.tar 생성
→ BEFORE (완료된 baseline)
→ target.run (종료/timeout 회수)
→ AFTER (target effects 관찰)
→ 순수 비교 / oracle / signature / RunResult
→ bookkeeping이 필요하면 이 시점 이후 / cleanup
```

정상 setup은 BEFORE에 포함되어 namespace transition이 아니므로 C0 오탐이 아니다. TargetAdapter.run은 관찰 구간의 실행 책임이며 harness log/setup/bookkeeping의 namespace write를 하지 않아야 한다. 현재 Python reference는 stdout/stderr를 memory에 수집해 ExecutionResult로 반환한다. 관찰은 atime을 기록하지 않으며 security verdict를 결정하지 않는다.

| 설계 질문 | 코드 기준 결정 / 한계 |
| --- | --- |
| Q1. Snapshot으로 target/harness 생성 주체를 아는가? | 알 수 없다. BEFORE/AFTER는 순서와 상태만 기록하며 actor provenance는 없다. |
| Q2. 현재 AFTER 전 harness mutation이 있는가? | run_case와 reference adapter에는 없다. Layout/sentinel/input 생성은 BEFORE 전, cleanup은 AFTER 후다. |
| Q3. 향후 adapter bookkeeping이 들어올 수 있는가? | 가능하다. Diagnostics는 ExecutionResult에 두고 setup/bookkeeping은 관찰 구간 밖에서 해야 한다. 이를 지킬 수 없다면 별도 provenance/관찰 설계가 필요하다. |
| Q4. HARNESS 전이를 C0로 보면 legitimate false positive는? | 관찰 구간의 adapter log 생성·삭제·교체처럼 lifecycle 계약을 어긴 harness 동작을 target 효과로 오인할 수 있다. |
| Q5. Provenance 없이 이를 면제하면? | archive namespace의 실제 target escape도 숨긴다. 경로 whitelist 대신 lifecycle 계약과 명시적 attribution limitation을 유지한다. |

기존 harness-only 테스트는 setup 완료 후 BEFORE를 찍어 nonviolation을 유지하고, 같은 setup 변화를 잘못된 baseline으로 비교하면 C0 evidence가 생긴다고 명시한다. Controlled adapter E2E는 archive namespace 생성·삭제·identity/type 교체를 탐지하면서 HARNESS signature exclusion이 유지됨을 검증한다. 이는 actor attribution instrumentation이나 취약한 extractor의 재현을 구현했다는 뜻이 아니다.

Disposable directory는 harness storage/cleanup 경계이며 임의 executable에 OS 접근 권한을 제한하지 않는다. 현재 검증은 Linux controller의 Python reference/data filter와 별도 contained Node target의 benign 입력으로 한다. Isolation-required invocation은 validated backend를 사용하며 종료 후 전체 PID context가 멈춘 상태를 확인한다. Snapshot은 sandbox 밖의 접근을 관찰하지 않으며 완전한 containment를 입증하지 않는다.

---

## 9. Sentinel Model

External Effect와 Object Identity Contract를 검증하려면 extraction root 밖에 **실험용 protected object**가 필요하다.

이 object를 sentinel이라고 부른다.

중요:

> sentinel은 실제 host 민감 파일이 아니다.

사용하지 않는 대상:

- `/etc/passwd`
- SSH key
- 실제 사용자 문서
- 실제 credential
- host secret

sentinel은 disposable sandbox 안에서 실험을 위해 생성한다.

### Sentinel lifecycle

~~~mermaid
flowchart TD
    C["Create disposable sentinel"] --> P["Capture pre-state"]
    P --> E["Run extractor"]
    E --> Q["Capture post-state"]
    Q --> D["Compare identity / content / metadata"]
    D --> X["Destroy sandbox or preserve evidence"]
~~~

초기 비교 후보:

- `st_dev / st_ino`
- content hash
- size
- mode
- 필요한 metadata

---

# 10. Stage A — Seed Generator

위치:

```text
src/inodefence/generator/
```

현재 `minimal_seed_corpus() -> tuple[ArchiveCase, ...]`는 regular, directory/file,
regular/hardlink, regular/symlink 순서의 기존 정상 baseline을 반환한다. 고정 content/path/mode와
immutable model만 사용하며 IO/RNG/feedback/pipeline/target/TAR encoding에 의존하지 않는다.
Fixture script가 이 API를 공유한다. Campaign은 caller가 seeds를 명시적으로 전달해야 한다.

역할:

- 작고 정상적인 초기 case 생성
- 사람이 이해할 수 있는 seed 유지
- 실험의 안정적인 출발점 제공

초기 seed는 복잡한 공격 payload보다 다음처럼 작아야 한다.

```text
Case A
a.txt

Case B
dir/
dir/a.txt

Case C
a.txt
b.txt → hardlink a.txt
```

Generator가 하지 않는 일:

- extractor 실행
- security 판정
- corpus scheduling
- target-specific CVE recipe 생성

Known CVE PoC는 benchmark ground truth와 root-cause 분석에 사용할 수 있지만 기본 seed로 하드코딩하지 않는다.

---

# 11. Stage B — Structure Mutator

위치:

```text
src/inodefence/mutator/
```

Mutator는 archive의 **구조적 의미**를 변화시킨다.

현재 [Generic Mutation v1](../../../src/inodefence/mutator/README.md)은 add/remove/duplicate/reorder/path/hardlink/symlink/link-target 8개 함수를 독립적으로 export한다. 각 함수는 `(case: ArchiveCase, rng: random.Random) -> ArchiveCase`이며 caller-owned RNG만 사용한다. Uniform `mutate()`는 baseline convenience 함수다. 향후 adaptive scheduler는 개별 함수를 직접 선택할 수 있으며 mutator는 Observer/Oracle/Feedback/StateSignature/TargetAdapter/pipeline/corpus 또는 TAR encoding에 의존하지 않는다. Constructor와 builder의 조합 검사는 별도 integration test에 둔다.

현재 v1과 후속 확장 후보를 포함한 mutation 축:

- entry type
- entry path
- link target
- entry order
- entry 추가
- entry 삭제
- entry 복제
- dependency relation
- target 존재 여부

예:

```text
Before

1. a.txt
2. b.txt → hardlink a.txt

Mutation

reorder entries

After

1. b.txt → hardlink a.txt
2. a.txt
```

좋은 mutation API는 일반적인 transformation을 표현한다.

```text
reorder_entries
change_entry_type
change_link_target
duplicate_entry
delete_entry
```

피해야 할 방향:

```text
make_exact_CVE_payload
apply_node_tar_bypass_3
```

InodeFence가 특정 알려진 공격 recipe의 재생기가 되지 않게 한다.

---

# 12. Stage C — TAR Builder

TAR Builder는 논리적인 `ArchiveCase`를 실제 TAR artifact로 직렬화한다.

```text
ArchiveCase
    ↓
TAR Builder
    ↓
input.tar
```

Mutator와 Builder를 분리하는 이유:

```text
Mutator
"무엇을 바꿀 것인가?"

Builder
"그 구조를 TAR 형식으로 어떻게 표현할 것인가?"
```

즉:

```text
Mutation Policy ≠ TAR Encoding
```

현재 builder는 [builder.py](../../../src/inodefence/builder.py)의 `build_tar`다. `ustar-utf8-v1` format, strict UTF-8, zero mtime/uid/gid와 empty uname/gname을 고정한다. Directory name의 trailing slash도 입력 철자를 보존한다. Fixture script가 같은 builder를 사용하며 기존 baseline bytes를 유지한다.

USTAR의 실제 name/prefix header에서 복원한 raw UTF-8 bytes는 model input과 정확히 일치해야
한다. Empty-prefix split처럼 spelling을 바꾸는 경우 indexed ValueError로 실패한다.
이 rejection-only guard는 기존 valid encoding bytes와 format ID를 유지한다.

표준 라이브러리로 충분한 초기 단계와, 향후 비정상 TAR encoding을 직접 다뤄야 하는 단계의 요구가 달라질 수 있으므로 실제 필요가 생길 때 경계를 고정한다.

---

# 13. Stage D — Target Adapter

위치:

```text
src/inodefence/targets/
```

Target Adapter는 generic InodeFence pipeline과 실제 extractor 사이의 경계다.

초기 target 우선순위:

1. node-tar
2. oras-go
3. 일정이 허용하면 GNU tar

위 순서는 연구 benchmark adapter 우선순위다. 현재 Python tarfile/data reference는 architecture/integration 검증용 예외이며 benchmark 우선순위를 바꾸지 않는다. 별도 Python worker의 filter rejection/parser failure/timeout도 execution 결과로 반환하고 이후 snapshot을 관찰한다. Filter가 metadata를 제한할 수 있으므로 TAR encoding 보존과 target extraction policy를 구분한다.

개념 interface:

```text
run(
    archive,
    extraction_root,
    configuration
) -> ExecutionResult
```

target-specific로 허용되는 정보:

- 실행 command
- runtime
- version
- environment
- target-specific option
- stdout / stderr
- exit code
- timeout

generic Mutation, Observer, Oracle, Feedback에 node-tar 전용 처리 로직을 섞지 않는다.

---

## Node-tar adapter v1의 현재 integration 경계

Target-specific Node worker는 targets/에 있고 exact setup identity/worker pre-extraction version
check, strict=true/preservePaths=false와 streams/status를 소유한다. Invocation은 IsolatedTarget과
ExecutionBackend에 composition으로 연결하며 local subprocess fallback은 없다.
Generic run_case/Observer/Oracle/StateSignature/Corpus/mutation의 책임은 바꾸지 않는다.
[Target 안내](../../../src/inodefence/targets/README.md)와 [locked tooling](../../../tools/node-tar/README.md)을
따른다. Node 22.22.0/tar 7.5.22에서 ordinary controlled fixtures만 검증한다. ISOLATION_REQUIRED는
고정이고 uncontained campaign은 계속 거부한다. Contained composition은 config/policy/
attestation binding 뒤에만 campaign이 허용한다. Actual fixtures는
별도 target container에서만 실행하고 setup/cleanup은 BEFORE/AFTER 구간 바깥에 둔다.

---

# 14. Stage E — State Observer

위치:

```text
src/inodefence/observer/
```

Observer의 질문은 하나다.

> filesystem에 실제로 무엇이 존재하고, extraction 전후 무엇이 달라졌는가?

초기 관찰 후보:

- relative path
- object type
- `st_dev`
- `st_ino`
- `st_nlink`
- mode
- size
- symlink target
- 선택 object의 content hash
- sentinel state

예:

```text
a.txt
st_dev = 10
st_ino = 555
st_nlink = 2

b.txt
st_dev = 10
st_ino = 555
st_nlink = 2
```

Observer가 말할 수 있는 것:

> a.txt와 b.txt는 같은 filesystem identity를 공유한다.

Observer가 말하면 안 되는 것:

> 이것은 취약점이다.

후자의 책임은 Oracle이다.

---

# 15. Stage F — Security Oracle

위치:

```text
src/inodefence/oracle/
```

Oracle은 관찰된 state를 Security Contract와 비교한다.

~~~mermaid
flowchart LR
    S["StateSnapshot"] --> O["Security Oracle"]
    C["Security Contract"] --> O
    O --> V["ViolationResult"]
~~~

정확한 Contract 정의는 [security-contracts.md](security-contracts.md)가 기준이다.

초기 우선순위:

1. **C0 Path Boundary Confinement** — baseline/sanity
2. **C1 Object Identity Confinement**
3. **C2 External Effect Noninterference**
4. **C3 Extraction Root Integrity** — 이후 확장
5. **C4 Check/Use Coherence** — instrumentation 이후

### Observer와 Oracle 경계 예시

```text
Observer:
inside/result.txt과 outside/sentinel의
(st_dev, st_ino)가 같다.

Oracle:
보호 대상 설정상 이 identity 공유는
C1을 위반한다.
```

Oracle은 filesystem을 직접 변형하거나 target을 실행하지 않는다.

---

# 16. Stage G — Feedback / Corpus

위치:

```text
src/inodefence/feedback/
```

Feedback의 질문:

> 이 testcase가 다음 탐색의 출발점으로 남길 만큼 새로운 security-relevant state를 만들었는가?

중요:

```text
Interesting ≠ Vulnerable
```

Contract violation이 없더라도 처음 보는 identity/link/effect 관계라면 향후 탐색 가치가 있을 수 있다.

현재 v1은 [corpus.py](../../../src/inodefence/feedback/corpus.py)의 in-memory Corpus와
[fingerprint.py](../../../src/inodefence/feedback/fingerprint.py)의 pure semantic fingerprints다.
StateSignature v3 equality와 violation novelty를 서로 독립적인 seen indexes로 관리한다.

~~~mermaid
flowchart TD
    R["RunResult"] --> S["StateSignature v3 equality"]
    R --> V["Semantic violation fingerprints"]
    S --> N{"New state OR new violation class?"}
    V --> N
    N -->|No| D["No admission"]
    N -->|Yes| I["Interesting observation"]
    I --> K{"Case already retained?"}
    K -->|No| C["Append compact CorpusEntry"]
    K -->|Yes| A["Preserve existing entry"]
    R --> U["Advance both seen indexes and observation stats"]
    C --> M["Caller RNG uniform parent selection"]
~~~

**Signature equality는 raw evidence equality나 안전성 판정이 아니다.** `archive/**`는
HARNESS라서 signature scope에서 제외되므로 관찰 구간에 `archive/escaped.txt`가 생성되어도 signature는
같을 수 있다. 그러나 C0는 이 namespace effect를 판정한다. Corpus는 같은 signature의 새
violation fingerprint도 interesting으로 취급해 이 evidence를 잃지 않는다.

Violation fingerprints는 이미 판정된 violated 결과만 소비하며 contract를 정의/재평가하지 않는다.
C0/C2는 contract ID와 StateChange.path/fields, C1은 contract ID와 internal/sentinel path를
사용한다. C0와 C2의 동일 path/fields는 다른 class다. Raw dev/inode allocation,
timestamp/content/mode 원값, ObjectSnapshot, explanation/limitations는 key에서 제외한다.
Changed-field labels는 보존하며 raw identity 판정과 reproduction evidence는 Oracle/RunResult에
남긴다. Evidence/result는 sorted unique tuple로 canonicalize한다. 한 violated contract의 전체
semantic evidence tuple이 하나의 class이고, 추가 path/relation은 다른 class다. EXISTENCE
creation/deletion은 같은 class이며 실제 결과 차이는 독립 state channel/raw evidence에서 본다.

```text
interesting = state_novel OR bool(new_violation_fingerprints)
retained = interesting AND NOT already_retained
```

Case/TAR/input digest/HARNESS metadata와 execution status/exit code/duration은 novelty가 아니다.
Case_id는 retained parent 중복 방지에만 사용한다. 다른 case가 같은 normalized state와 이미 본
violation class를 만들면 보존하지 않는다. 같은 retained case가 새 state/class를 만들면
interesting observation 수와 seen indexes는 증가하지만 entry를 중복 추가하지 않는다.

CorpusEntry는 case와 최초 admission signature/모든 semantic fingerprints만 보존한다. Full
RunResult/raw logs/mutation history는 저장하지 않으며 최초 metadata를 나중에 덮어쓰지 않는다.
Entries는 admission order의 immutable tuple snapshot이고 stats는 immutable search/reporting
snapshot이다. Observations는 consider 호출 수, interesting_observations는 interesting decision 수,
retained_cases는 현재 parent 수, unique_states/unique_violation_fingerprints는 seen index 크기다.
이 숫자는 연구 효과나 paper result가 아니다.

Parent selection은 retained entries에 균등한 caller-owned random.Random baseline이다.
같은 insertion order와 RNG state는 같은 selection을 만든다. Global RNG/implicit seed는 없고,
empty corpus는 RNG 소비 없이 ValueError다. Corpus는 mutation operator 선택이나 mutation을
실행하지 않는다. Caller가 선택한 ArchiveCase를 Mutator에 전달한다.

한 Corpus는 한 caller-controlled campaign context에 속한다. RunResult에는 complete stable
campaign key가 없으므로 false identifier/dynamic command hash를 만들지 않는다. Formal runner는
commit, target/version/config, OS/kernel/architecture, seed/budget/timeout, dependency version과
raw evidence 기록을 소유한다. Cross-target persistence safety를 주장하지 않는다.

Adaptive scheduler, reward/energy, persistence/resume, benchmark adapters와
research effectiveness는 후속 작업이다. 현재 Corpus는 기존 feedback package에 둔다.
정책 근거는 D016과 [feedback API 안내](../../../src/inodefence/feedback/README.md)를 따른다.

---

# 17. Orchestration / Runner

전체 pipeline을 연결하는 orchestration 책임이 필요해질 수 있다.

개념적으로:

```text
prepare run sandbox
→ prepare sentinel
→ build TAR
→ observe pre-state
→ execute target
→ observe post-state
→ evaluate contracts
→ calculate signature
→ return structured result
```

중요한 점은 Runner 자체가 알고리즘을 소유하지 않는 것이다.

Runner에 들어가면 안 되는 것:

- mutation 전략
- contract 정의
- target-specific 취약점 규칙
- state normalization 정책의 핵심 알고리즘

Runner는 순서를 연결하는 역할만 한다.

현재 orchestration은 [pipeline.py](../../../src/inodefence/pipeline.py)의 `run_case`다. Builder/environment/Observer/예상하지 못한 adapter 오류는 harness exception으로 전달하고 PASS를 만들지 않는다. Target 결과는 success/rejected/failed/timed_out으로 반환하며 모든 결과에서 after snapshot을 시도한다. Result는 sandbox 삭제 후에도 case와 evidence를 기록할 수 있다.

`run_case()`는 의도적으로 한 번만 실행한다. Mutation strategy, corpus scheduling/adaptive
feedback, target selection과 CVE logic을 넣지 않는다. 현재 [campaign.py](../../../src/inodefence/campaign.py)의 `run_campaign`이 별도 caller로
Corpus.select_case, Mutator, run_case, Corpus.consider를 조합한다.

CampaignConfig는 frozen/slots의 integer random_seed와 positive integer execution_budget이다.
Initial cases는 명시적으로 받으며 nonempty, unique case IDs와 budget >= seed count를 실행 전에
검증한다. Seed를 선언 순서대로 실행하고 consider하며 search RNG를 소비하지 않는다. 이후
하나의 random.Random(seed)으로 select → mutate → execute → consider 순서를 지킨다. No-op도
재시도 없이 한 execution이고 SUCCESS/REJECTED/FAILED/TIMED_OUT 모두 budget에 포함한다.
Infrastructure exception은 전달하며 완료되지 않은 campaign을 정상 결과로 만들지 않는다.

CampaignStep은 zero-based index, SEED/MUTATION origin, seed에는 None인 parent_case_id,
full RunResult와 FeedbackDecision이다. CampaignResult는 config/initial IDs/steps/final stats와
admission-order retained IDs와 실행 전 ExecutionProvenance의 immutable snapshot이다.
CampaignTarget은 TargetAdapter에 pre-execution TargetProvenance property를 추가한다. 첫 run_case
전에 source/environment와 target/sentinel config를 freeze하며 supplied provenance는 target/sentinel
일치를 확인한다. Supplied source/environment 정확성은 caller 책임이다. Adapter 선언 또는 result의
target/version/timeout drift는 harness 오류로 중단한다. Model에는 capture logic이 없고 상위
provenance.py가 Git/platform/config를 읽는다. Sentinel order는 name 기준이며 content는 digest다.
이 값은 StateSignature, Corpus novelty나 Security Contract evidence에 들어가지 않는다.
Full evidence 보존으로 메모리는
O(execution_budget)이며 run당 evidence 크기에 비례한다. Semantic feedback이 같은 조건에서
lineage를 재현하며 raw inode/timestamp/duration equality는 요구하지 않는다. Persistence,
checkpoint/resume, adaptive scheduling과 default seed 선택은 없다.
완료된 결과의 structured writer는 별도 campaign_export.py에 둔다.

---

## Explicit ExperimentConfig v1/v2

상위 experiment_config.py는 기존 CampaignConfig/TargetProvenance/SentinelSpec을 재사용해 필수
JSON 설정과 stable config_id를 표현한다. Exact target/version/timeout/safety, ordered seed IDs/profile,
RNG seed/budget, mutation/feedback policy, sentinels와 expected environment profile을 요구한다.
Config wrapper는 caller seeds/target binding을 실행 전에 검증하고 existing campaign API에 명시적인
config ID를 전달한다. CampaignResult/manifest의 stored ID는 사후 reconstruction이 아니다.
None은 formal config 없이 실행한 API를 뜻하며 low-level caller는 supplied reference 정확성에 책임이 있다.
Canonical config에는 actual source/platform/runtime/result가 없고 frozen execution provenance에 따로
있다. [Config semantics](../../../experiments/configs/README.md)를 따른다. Configured CLI는 safe Python
reference만 지원하며 generic engine/StateSignature/novelty/oracle 정의를 바꾸지 않는다.

---

# 18. 한 testcase의 상세 Sequence

~~~mermaid
sequenceDiagram
    participant C as Corpus/Seed
    participant M as Mutator
    participant B as TAR Builder
    participant R as Run Sandbox
    participant O as Observer
    participant T as Target Adapter
    participant Q as Oracle
    participant F as Feedback

    C->>M: ArchiveCase
    M->>B: Mutated ArchiveCase
    B->>R: input.tar
    R->>R: create protected sentinel
    R->>O: capture pre-state
    O-->>R: Pre Snapshot
    R->>T: run archive in extract/
    T-->>R: ExecutionResult
    R->>O: capture post-state
    O-->>R: Post Snapshot
    R->>Q: StateSnapshot + contract context
    Q-->>R: ViolationResult
    R->>F: Case + StateSignature + ViolationResult
    F-->>C: retain / discard / priority
~~~

이 sequence에서 pre-state가 extractor 실행보다 앞선다는 점이 중요하다.

---

# 19. 실패도 데이터다

Extractor 실행이 실패했다고 testcase를 무조건 버리지 않는다.

구분해야 할 최소 상태 후보:

```text
SUCCESS
EXPECTED_REJECTION
PARSER_FAILURE
TARGET_CRASH
TIMEOUT
ENVIRONMENT_FAILURE
INODEFENCE_INTERNAL_ERROR
```

예를 들어 parser failure 이후에도 일부 filesystem object가 남을 수 있다.

따라서 실행 종료 상태와 filesystem 관찰 결과를 분리한다.

또한 다음 둘을 반드시 구분해야 한다.

```text
target behavior / target bug
≠
our harness / environment bug
```

---

# 20. Testcase Lineage

Bounded campaign v1은 steps의 parent_case_id와 origin을 기록한다. 아래 상세 mutation history는 후속 설계이며 Corpus v1에는 mutation-history DB를 넣지 않는다.

최종 finding만 저장하면 “어떻게 그 상태에 도달했는가”를 설명하기 어렵다.

각 case는 가능한 한 계보를 추적할 수 있어야 한다.

```text
Case 0001
Seed
  ↓ change_entry_type
Case 0312
  ↓ reorder_entries
Case 0441
  ↓ change_link_target
Case 0814
Potential Violation
```

필요한 관계:

- current case id
- parent case id
- applied mutation
- mutation parameters
- random seed
- target/version
- state signature
- violation result

이 정보는 debugging뿐 아니라 실험 분석과 finding 최소화에도 사용된다.

---

# 21. Determinism과 Reproducibility

같은 case를 같은 조건에서 반복했을 때 가능한 한 같은 의미적 결과가 나와야 한다.

논문용 실험에서 최소 기록 후보:

- InodeFence Git commit
- target name/version
- experiment config
- random seed
- OS / architecture
- 중요한 runtime dependency version
- timeout/budget
- corpus 시작 상태

raw inode 번호처럼 실행마다 달라질 수 있는 값 자체가 아니라 **관계 기반 상태**를 중심으로 비교한다.

---

# 22. Finding Lifecycle

모든 interesting case가 finding은 아니다.

~~~mermaid
flowchart TD
    G["Generated Case"] --> I["Interesting Case"]
    I --> P["Potential Violation"]
    P --> R["Reproduce"]
    R --> M["Minimize"]
    M --> A["Root Cause Analysis"]
    A --> C["Confirmed Finding"]
~~~

`findings/`에는 마지막 단계에 가까운 재현 가능한 자료를 둔다.

finding 후보를 확인하기 전에는 “새 취약점”이나 “제로데이”로 단정하지 않는다.

---

# 23. Evidence Pipeline

코드 실행 결과가 논문 주장으로 가는 과정:

~~~mermaid
flowchart LR
    A["Raw Execution"] --> B["Validated Result"]
    B --> C["Reproducible Finding"]
    B --> D["Aggregated Measurement"]
    C --> E["Figure / Table / Discussion"]
    D --> E
    E --> P["Paper Claim"]
~~~

Repository 역할:

- [experiments/](../../../experiments/README.md): 설정과 raw/aggregated 실험 결과
- [findings/](../../../findings/README.md): 재현·분석 가능한 개별 사례
- [artifacts/](../../../artifacts/README.md): 의도적으로 보존한 생성물
- [paper/](../../../paper/README.md): 검토된 표·그림·논문 문장

연구 메모가 자동으로 paper evidence가 되지 않는다.

---

# 24. Evaluation 설계

InodeFence의 연구 가치는 실제 비교 실험으로 검증한다.

현재는 **가설 단계**이므로 아래 항목은 evaluation design 후보이며 결과를 미리 가정하지 않는다.

## 24.1 Baseline 후보

```text
Baseline A
generic/random mutation

Baseline B
structure-aware mutation

InodeFence
structure-aware mutation
+
filesystem security-state feedback
```

비교 질문 예:

- 같은 execution budget에서 security-relevant state diversity가 어떻게 다른가?
- Contract violation 후보에 도달하는 데 필요한 실행 수가 어떻게 다른가?
- known-vulnerability benchmark rediscovery가 가능한가?
- target을 바꿔도 feedback representation이 의미를 유지하는가?

---

## 24.2 Ablation 후보

Feedback의 어떤 구성요소가 실제로 기여하는지 분리해서 본다.

```text
Full InodeFence

vs

without identity-relation feedback

vs

without external-effect feedback

vs

without corpus evolution
```

ablation 항목은 pilot experiment 후 실제 구현에 맞게 확정한다.

---

## 24.3 Metric 후보

정확한 metric은 실험 전에 정의해야 한다.

가능한 후보:

- unique normalized state signatures
- security-relevant relation diversity
- violation candidate count
- executions-to-first-violation
- rediscovery rate under fixed budget
- reproducibility rate
- testcase minimization size
- executions / second

단순히 숫자가 많다고 좋은 metric으로 채택하지 않는다.

연구 질문과 직접 연결되는지 먼저 본다.

---

# 25. Logging과 Structured Evidence

사람이 보는 로그와 분석 프로그램이 읽는 데이터는 분리한다.

사람용 예:

```text
case=124
target=node-tar
entries=4
exit=0
interesting=yes
violation=C1
```

분석용 데이터는 JSON/JSONL 같은 구조화 형식을 우선한다.

후보 필드:

- case id
- parent id
- mutation history
- target/version
- execution status
- timing
- state signature
- violation result
- environment/config reference

실험 분석이 stdout 문자열 parsing에 의존하지 않게 한다.

현재 [campaign_export.py](../../../src/inodefence/campaign_export.py)의
`export_campaign(result, destination, *, experiment_config_json=None) -> tuple[Path, Path]`는 완료된 결과를
새 directory의 manifest.json/steps.jsonl로 기록한다. 기존 destination은 거부하고 IO/encoding
오류는 전달한다. Step별 existing canonical_json envelope/schema/bytes-base64 encoding을
그대로 사용하며 result(raw evidence)와 feedback(decision)은 별도 field로 유지한다. Lineage,
모든 execution status, snapshots, signature와 verdict/evidence를 보존한다.

Manifest schema v4는 optional experiment_config_file/experiment_config_sha256과 nullable isolation을 포함한 stored execution_provenance, format/classification, config, initial IDs, step count/final stats/retained
order와 결과에서 얻은 target ID/version/builder format/timeout contexts를 기록한다. Context는
first-occurrence order의 unique tuple이며 변동 provenance를 첫 step 값으로 숨기지 않는다.
steps_file/steps_sha256으로 실제 JSONL을 연결한다. export_environment는 writer process의
Python version/system/release/architecture다. Target 실행 환경이나 source commit을 추정하지
않는다. Execution provenance는 실행 전 stored 값이고 exporter는 재구성하지 않는다. Source
revision은 full Git ID/dirty 또는 명시적 None이다. Platform의 release는 kernel/platform 문자열이며
environment는 harness process를 설명한다. Dirty state는 source patch를 보존하지 않는다.

동일한 완료 result와 exporter environment는 destination과 무관하게 같은 sorted-key ASCII JSON,
LF bytes를 만든다. 별도 campaign의 raw inode/timestamp/duration equality는 요구하지 않는다.
한 step씩 encode하므로 full campaign encoding을 추가로 memory에 만들지 않는다. Manifest는
마지막에 쓴다. Optional pre-read config JSON은 stored experiment_config_id의 SHA-256과 일치해야
하며 같은 bundle로 공개한다. 각 파일 flush/fsync, JSONL checksum/read-back, staging directory fsync
후 같은 parent 안에서 Linux renameat2(RENAME_NOREPLACE)로 atomic no-overwrite publication하고
parent를 fsync한다. 기존 destination 및 동시 생성된 empty directory도 덮어쓰지 않는다.
공개 전 실패는 최종 destination absent/staging cleanup을 보장하고 예외를 전달한다. Parent
생성은 rollback하지 않는다. Hard interruption은 staging을 남길 수 있고, 공개 후 parent fsync 실패는
complete bundle을 남기고 오류를 전달한다. Unsupported OS/libc/kernel/filesystem에는 fallback이 없다.
이 publication은 database transaction, reader/deserializer, resume/checkpoint 또는 validated analysis가 아니다.

---

# 26. 모듈 의존 방향

공통 Data Model은 가능한 한 가장 아래 계층에 둔다.

```text
             generator
                 │
                 ▼
model ← mutator / targets / observer / oracle / feedback
```

원칙:

- `model`이 `oracle`을 import하지 않는다.
- `observer`가 target-specific policy를 가지지 않는다.
- `oracle`이 mutation을 수행하지 않는다.
- `feedback`이 Security Contract 정의를 소유하지 않는다.
- `mutator`가 node-tar command를 알지 않는다.
- `targets`가 generic feedback policy를 결정하지 않는다.

현재 Layer 5의 corpus/fingerprint production modules는 표준 라이브러리와 model/semantic
fingerprint types만 import한다. Pipeline/targets/runtime/observer/oracle/mutator/builder 구현을
import하지 않는다. 기존 state_signature의 snapshot 비교 의존성은 유지한다. Mutator는 archive
model만 의존하고 Feedback을 import하지 않는다. Campaign runner가 세 API를 caller 수준에서 조합한다.

순환 의존이 생기면 책임 경계가 무너진 신호로 본다.

---

# 27. 모듈별 Invariant

## Generator

```text
입력 없이 또는 명시적 config로
작고 설명 가능한 ArchiveCase를 만든다.
```

## Mutator

```text
ArchiveCase의 구조를 바꾸되
target-specific vulnerability recipe를 소유하지 않는다.
```

## Builder

```text
논리 구조를 TAR 표현으로 바꾸되
mutation 선택을 하지 않는다.
```

## Target Adapter

```text
실제 extractor를 실행하되
filesystem security 의미를 판정하지 않는다.
```

## Observer

```text
사실을 기록하되
취약 여부를 판단하지 않는다.
```

## Oracle

```text
Contract를 적용하되
filesystem을 실행하거나 mutation하지 않는다.
```

## Feedback

```text
탐색 가치 여부를 판단하되
"interesting"을 "confirmed vulnerability"와 동일시하지 않는다.
```

---

# 28. Minimal End-to-End Pipeline

개발 Layer 3의 목표는 완전한 fuzzer가 아니다.

다음 경로 하나가 안정적으로 동작하면 된다.

~~~mermaid
flowchart LR
    K["Small Known ArchiveCase"] --> T["TAR"]
    T --> X["One Real Target"]
    X --> S["Disposable Sandbox"]
    S --> O["Pre/Post Snapshot"]
    O --> Q["C0/C1/C2 Oracle"]
    Q --> R["Structured Result"]
~~~

이때 mutation loop와 advanced feedback이 없어도 된다.

먼저 **관찰 경로가 정확한지**를 검증한다.

---

# 29. 구현 순서

Milestone 1~3은 core foundation, 4는 Generic Mutation v1, 5는 Feedback / Corpus v1으로
구현·검증했다. 아래는 개발 순서이며 evaluation을 앞당겨 구현하지 않는다.

## Milestone 1 — Common Data Model

첫 구현 대상:

- `ArchiveEntry`
- `ArchiveCase`

그 뒤 필요한 모델을 작은 단위로 확정한다.

## Milestone 2 — 최소 관찰 경로

```text
Known TAR
→ one target
→ sandbox
→ pre/post snapshot
→ path / identity / external-effect oracle
```

## Milestone 3 — Generic TAR 생성

내부 ArchiveCase를 실제 TAR로 안정적으로 serialize한다.

## Milestone 4 — Generic Mutation

구조 변화 operator를 추가한다.

## Milestone 5 — Feedback / Corpus v1

기존 StateSignature v3와 독립 semantic violation novelty로 in-memory corpus evolution을 구현한다.
Uniform caller-RNG selection은 baseline이다. Bounded campaign v1이 상위 caller로 실행 budget과
lineage를 기록한다. 이 구현은 연구 효과 검증 완료를 뜻하지 않는다.

## Milestone 6 — Evaluation

baseline, ablation, known-vulnerability rediscovery, current-version campaign을 수행한다.

---

# 30. PR 단위 권장

바이브코딩이 커져도 한 PR에 모든 Layer를 넣지 않는다.

예:

```text
PR A
ArchiveEntry / ArchiveCase

PR B
TAR fixture / serialization

PR C
Target Adapter

PR D
Observer snapshot

PR E
C0/C1/C2 Oracle

PR F
Mutation operators

PR G
StateSignature / Feedback
```

공통 interface가 바뀌면 관련 design README도 같이 수정한다.

---

# 31. 현재 하지 않는 것

현재 초기 범위에서 바로 구현하지 않는다.

- 모든 archive format 지원
- Windows NTFS semantics
- full symbolic execution
- 모든 TOCTOU/race 분석
- 복잡한 kernel instrumentation
- eBPF/fanotify 기반 full trace
- 모든 target 동시 지원
- Wormholes의 모든 bypass 재구현
- CVE-specific payload factory
- 성능 최적화부터 시작하기

C4 Check/Use Coherence처럼 instrumentation이 필요한 문제는 초기 snapshot pipeline 검증 후 다룬다.

---

# 32. 설계 변경 규칙

다음이 바뀌면 코드만 수정하지 않는다.

- 공통 Data Model / interface → 관련 design 문서
- Security Contract → `security-contracts.md`
- 큰 설계 결정 → `../../DECISIONS.md`
- 현재 개발 Layer / 다음 작업 → `../../STATUS.md`
- 프로젝트 진입 흐름 → `../../START_HERE.md`

아키텍처와 코드가 다르면 팀원이 설명할 수 없게 되고 AI Agent도 잘못된 방향으로 확장하기 쉽다.

---

# 33. 최종 Mental Model

팀원은 최소한 다음 그림을 머릿속에 가지고 개발한다.

```text
[연구]
무엇을 위험하다고 볼 것인가?
        │
        ▼
Security Contract
        │
        ▼

[실행]
ArchiveCase
    ↓
Generic Mutation
    ↓
TAR
    ↓
Real Extractor
    ↓
Filesystem
    ↓
Observer
    ↓
StateSnapshot
   /           \
  ▼             ▼
Oracle       StateSignature
  │             │
  ▼             ▼
Violation     Feedback
    \           /
     \         /
      ▼       ▼
       Corpus
         │
         └────→ next mutation

[증거]
Potential Violation
    ↓
Reproduce
    ↓
Minimize
    ↓
Analyze
    ↓
Finding
    ↓
Experiment Evidence
    ↓
Paper
```

이 세 흐름 — **연구 정의, Runtime 탐색, Evidence 검증** — 을 섞지 않는 것이 InodeFence 전체 설계의 중심 원칙이다.


### Prepared target execution

`TargetInvocation` describes image/argv/version/status; `IsolatedTarget` composes it
with the narrow `ExecutionBackend`. Node's descriptor has no ordinary subprocess
fallback. Pipeline calls `PreparedTarget.prepare` outside its snapshot pair and
executes the yielded invocation exactly once. Preparation precedes BEFORE,
complete execution-context stop precedes AFTER, removal follows AFTER, including
on observer exceptions. Trusted reference adapters without preparation retain the
existing one-run path. No campaign loop or contract verdict enters this boundary.


### Isolation/config evidence versions

ExperimentConfig v1 identity is preserved without isolation; v2 requires complete
IsolationPolicy v1 and actual target/backend equality. Before archive execution,
Campaign captures backend runtime/image facts and target artifact digests, then freezes
ExecutionProvenance. Only the exact IsolatedTarget composition satisfies required
isolation; subclasses/declarations cannot substitute execution. Availability/mismatch
fails before campaign runtime and first case; policy/artifact drift fails before next case.

ExecutionProvenance/CampaignResult canonical envelopes are v2; manifest is v4 and
serializes stored nullable isolation. ArchiveCase, RunResult and CampaignStep canonical envelopes remain unchanged.
StateSignature now uses internal v3 tagged target encoding; its novelty policy is unchanged. Runtime/PID/temp paths never enter config or feedback.
No campaign-to-Docker implementation import exists: the campaign sees the enforced
composition, while concrete runtime command construction stays in execution/container.

Invocation artifact digests are **declarations/expectations**. `bind()` discovery does
not authorize later constructed/replaced values. The wrapper executes the invocation's
identity probe through the inspected backend image and verifies versions/digests before
campaign freeze and before each standalone/prepared archive execution. Nonempty artifact
declarations without an observation protocol are rejected. Node compares its fixed
worker/package-lock probe output against every declared identity field; mismatches abort
before extraction, including when ExperimentConfig matches the false declaration.

`IsolationProvenance` v2 stores only those verified artifact observations, with
`artifact_origin="image-identification-v1"` (or null with no artifacts). Policy image ID
remains anchored to backend inspection and the prepared container's actual image.
ExecutionProvenance/CampaignResult envelopes remain v2 and manifest remains v4; export
preserves the stored origin and digests without a new backend query. Existing historical
isolation v1 records are unchanged and do not retroactively gain verified-origin meaning.
Image contents/probe implementation remain trusted; this is evidence integrity within
that trust model, not independent verification of a malicious image or an isolation escape.


### Pre-audit integration freeze

Container/image/config/provenance/lifecycle and tiny benign full-path validation are complete.
Completed manifest v4 publication is staged and atomic no-overwrite on supported Linux.
The limited dependency review found no forbidden reverse imports; target-specific invocation
remains separate from generic execution, Campaign, Observer/Oracle and feedback. Image ID
and worker/lock digests anchor target contents; dirty patches and exact reference Python
binary contents are not preserved. C0/C1/C2, signature/feedback and RNG/budget are unchanged.
The [actual conditions, checksums, policy and limits](../../../experiments/summaries/pre-audit-readiness-v1.md)
are engineering evidence. Architecture is READY FOR FULL CODE / ARCHITECTURE AUDIT, not
evaluated research. Feature expansion stops until that full audit and a later Task Contract.

## Independent search-policy core

Layer 5의 별도 SearchState API는 B0/B1/B3 policy admission과 full diagnostics를 분리한다.
`run_search_campaign`은 explicit search/mutation/projection config로 기존 pipeline을 조합하고
legacy runner의 execution safety/provenance gate를 공유한다. Legacy Corpus/campaign/evidence
shape는 유지한다. [새 caller API와 Evaluation binding 요구사항](search-policy-core-v1.md)을 따른다.

## Generic archive reduction

Search 이후 caller-level `minimizer.minimize_case`는 ArchiveCase 후보를 줄이고 caller가 제공한
RunResult evidence predicate로 채택 여부를 판단한다. Mutation/observer/oracle responsibilities는
유지하며 replay tooling이나 특정 target 규칙을 core에 넣지 않는다.
[Versioned API, budget, evidence와 한계](generic-minimizer-v1.md)를 따른다.

## Generic entry-transition model

Layer 2/5의 독립 모델은 `ObservationPoint`와 archive ordinal을 포함한
`ArchiveEntryReference`, complete `EntryCheckpoint`, consecutive
`FilesystemTransition`, ordered `TransitionTrace`를 제공한다. Legacy
`SnapshotPhase.BEFORE/AFTER`, `RunResult`, `run_case()`와 C0/C1/C2 의미는 바꾸지 않는다.
`TransitionRunResult`는 기존 final evidence와 transition evidence를 composition한다.

TransitionSignature v1은 raw inode/device/timestamp/runtime/target/CVE 값을 제외하고
entry type/ordinal class, region별 object effect, identity relation delta와 external
effect category를 보존한다. Individual `TransitionFeedbackKey`가 향후 primary novelty
단위이며 ordered `TransitionSequenceKey`는 auxiliary evidence다. 이 generic 구현과
synthetic sequence test는 실제 extractor의 entry completion boundary qualification이나
feedback effectiveness 결과가 아니다. 정확한 계약은
[transition-feedback-v1.md](transition-feedback-v1.md)를 따른다.

Transition novelty는 final StateSignature/violation novelty와 독립된 seen-key channel이다.
P0 final-state retention과 P1 transition retention은 같은 uniform parent/mutation 경로를
사용하며 별도 versioned ID를 가진다. P1은 final-state admission 대신 transition key를 쓰고
violation admission은 공통으로 유지한다. 모든 channel과 incomplete trace status는 evidence에
남는다. Native target binding이 없으므로 현재 runner는 caller-owned transition result producer를
조합하는 in-memory core이며 formal contained campaign/export가 아니다.

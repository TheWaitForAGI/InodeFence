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

현재는 **개발 Layer 1 완료 → Layer 2 공통 Data Model 시작 직전**이다.

현재 main에는 개발환경, smoke test, 연구 설계 문서와 모듈별 README가 있다. 기존 엔진 하위 패키지는 대부분 빈 `__init__.py`만 있으며, `model/`은 안내 문서만 있고 Python Data Model은 아직 구현되지 않았다.

따라서 아래에 등장하는 `ArchiveCase`, `ExecutionResult`, `StateSnapshot` 등의 이름은 **설계 후보**다. 이미 실행 가능한 API가 존재한다는 뜻이 아니다.

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

현재 바로 다음 구현은 이 전체 루프가 아니라 **공통 Data Model → 최소 관찰 경로**다.

---

## 5. Repository와 Runtime 책임 연결

| 책임 | 현재 위치 | 핵심 질문 |
| --- | --- | --- |
| 공통 Data Model | [model/](../../../src/inodefence/model/README.md) | 모듈끼리 무엇을 주고받는가? |
| Seed Generator | [generator/](../../../src/inodefence/generator/README.md) | 최초 case는 어떻게 생기는가? |
| Structure Mutator | [mutator/](../../../src/inodefence/mutator/README.md) | 기존 case를 어떤 generic rule로 바꾸는가? |
| TAR Builder | 위치 미확정 | 논리 case를 실제 TAR로 어떻게 표현하는가? |
| Target Adapter | [targets/](../../../src/inodefence/targets/README.md) | 실제 extractor를 어떻게 실행하는가? |
| State Observer | [observer/](../../../src/inodefence/observer/README.md) | filesystem에 실제로 무슨 일이 생겼는가? |
| Security Oracle | [oracle/](../../../src/inodefence/oracle/README.md) | 관찰 상태가 어떤 Contract를 위반하는가? |
| Feedback / Corpus | [feedback/](../../../src/inodefence/feedback/README.md) | 다음 탐색에 남길 가치가 있는가? |

Builder, Runner, Corpus를 별도 패키지로 분리할 가능성은 있지만 **필요성이 생기기 전에는 빈 추상화와 디렉터리를 미리 만들지 않는다.**

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

정확한 Python field와 type은 개발 Layer 2에서 결정한다. 아래 내용은 각 모델이 담당해야 할 의미적 책임이다.

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

개념 필드:

```text
ExecutionResult
├── target
├── target_version
├── exit_code
├── stdout
├── stderr
├── duration
├── timed_out
├── archive_path
├── extraction_root
└── execution_metadata
```

`ExecutionResult`와 filesystem 상태는 같은 것이 아니다.

`exit_code == 0`이어도 Security Contract 위반이 있을 수 있고, `exit_code != 0`이어도 남겨진 filesystem state가 분석 가치가 있을 수 있다.

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

특정 시점의 sandbox 상태를 나타낸다.

```text
StateSnapshot
├── extraction_root objects
├── protected sentinel objects
├── snapshot timing
└── observation metadata
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

Feedback을 위해 filesystem state를 **비교 가능한 형태로 정규화**한다.

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

정확한 정규화 schema는 개발 Layer 5에서 실험을 통해 고정한다.

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

# 8. Execution Sandbox

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

초기 mutation 축:

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

현재 별도 builder package 위치는 확정하지 않았다.

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

~~~mermaid
flowchart TD
    R["Executed Case"] --> S["StateSignature"]
    S --> K{"Seen equivalent state?"}
    K -->|No| C["Retain in corpus"]
    K -->|Yes| D["Discard or deprioritize"]
    C --> M["Schedule for next mutation"]
~~~

향후 Corpus 책임이 커지면 독립 package가 필요할 수 있지만 현재는 미확정이다.

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

현재 package 위치는 미확정이다.

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

## Milestone 5 — Feedback Loop

StateSignature와 corpus evolution을 추가한다.

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

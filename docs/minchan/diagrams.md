# 중간 상태 관찰 구조도

기준 revision과 근거는 [보고서](intermediate-observation-report.md), [색인](evidence-index.md)에 있다.
실선은 현재 구현 관계, 점선은 제안 연결이다. 그림은 새 실행 로그가 아니다.

## 전체 구조: 확인된 구현과 미완성 연결

```mermaid
flowchart TD
  A[ArchiveCase: ordered entries] --> M[Generic mutation]
  M --> B[USTAR builder]
  B --> T[Contained node-tar 7.5.22]
  T --> O[BEFORE / AFTER snapshot]
  O --> Q[Final C0 / C1 / C2]
  O --> F[Final StateSignature]
  T --> W[v2 source-guarded fs wrappers]
  W --> R[Raw start / completion / error]
  R --> V[v2 independent reader]
  V --> E[Effect trace / finite v2 keys]
  T -. proposed branch hook .-> D[v3 dependency envelope: NOT_IMPLEMENTED]
  D -. native connection pending .-> C[v3 strict reader / composite]
  V --> C
  C --> K[Additive finite v3 keys: synthetic tested]
  F --> S[Corpus / scheduler]
  E -. native qualification blocked .-> S
  K -. native qualification NOT_RUN .-> S
  S --> M
```

## 가상 타임라인: 입력 소비와 작업 완료 분리

다음은 이해를 위한 **가상 예시**다. 지연을 넣어 실행한 실험이 아니다. B는 A와 독립 경로다.

```mermaid
sequenceDiagram
  participant P as TAR Parser
  participant U as Unpack / reservations
  participant FS as Filesystem APIs
  participant O as Observer
  P->>U: entry 0 A (large regular)
  U->>FS: A open/write started
  P->>U: entry 0 body end; entry 1 B
  U->>FS: B mkdir started
  FS-->>U: B mkdir callback complete
  U->>O: entry 1 settled
  FS-->>U: A write / metadata / close complete
  U->>O: entry 0 settled
  Note over FS,O: A callback 시점 snapshot에 B가 이미 존재할 수 있음
```

## 과거 관측 기록의 순서

출처: #87 private snapshot summary, #88 causal-effect summary. 이번 raw 재관측이 아니다.

```mermaid
flowchart LR
  A[Archive ordinals: 0 → 1 → 2 → 3] --> B[Independent-files]
  B --> C[#87 snapshot: 0 → 1 → 3 → 2, 18/20]
  B --> D[#88 effects: 0 → 1 → 3 → 2, 20/20]
  D --> E[162 later-ordinal ops before earlier completion]
```

이 숫자는 callback/operation 관측 관계다. timestamp만으로 모든 물리 effect의 총순서를 복원하지 않는다.

## P0·P1·P2의 변경 변수

```mermaid
flowchart TD
  X[Same generic input / execution budget design] --> P0[P0: final-state OR violation admission]
  X --> P1[P1: transition OR violation admission]
  X --> P2[P2: same admission as P1]
  P0 --> U[Uniform parent + uniform operator]
  P1 --> U
  P2 --> A[Uniform parent + weighted operator]
  A --> R[New transition? binary reward, weight 1..8]
  R --> A
```

## v1 → v2 → v3 모델 변화

```mermaid
flowchart LR
  V1[v1 ordered complete checkpoints] --> N1[Native blocked: later effects contaminate prefix]
  N1 --> V2[v2 operation effects + evidence-supported partial order]
  V2 --> N2[Native NOT_QUALIFIED: replacement coverage absent]
  N2 --> V3[v3 separate rebinding sequence]
  V3 --> C[Same entry/path + explicit absence + direct branch dependency + conflict-free gap]
  C --> S[Generic synthetic tested]
  S -. pending .-> N3[Native dependency producer / qualification]
```

v3는 v2 판정을 소급 변경하지 않는다. v1 private qualification의 실험 번호 v3와도 다르다.

## 기존 연구와의 비교 축

```mermaid
flowchart TD
  Z[ZIPDiff] --> Z1[ZIP output differential + feedback]
  W[Wormholes] --> W1[Symlink semantics / composition / creation order]
  L[LinkZard] --> L1[Windows state-query feedback + API sequence graph]
  I[InodeFence] --> I1[Linux TAR object / external-effect feedback hypothesis]
  I1 --> I2[Intermediate observation qualification + v3 synthetic composite]
```

이 그림은 분류이며 성능 순위가 아니다. 원문·한계·확인되지 않은 항목은 보고서 비교표를 따른다.

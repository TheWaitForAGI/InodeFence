# 시스템 아키텍처

## 설계 목표

처음부터 완전한 퍼저를 만들지 않는다.

먼저 **가장 작은 end-to-end pipeline**을 만들고, 이후 feedback-guided fuzzer로 확장한다.

전체 mutation space나 복잡한 runtime tracing부터 시작하지 않는다.

## 상위 Pipeline

```text
Seed Generator
    ↓
Structure Mutator
    ↓
TAR Builder
    ↓
Target Adapter
    ↓
State Observer
    ↓
Security Oracle
    ↓
Feedback / Corpus
    └──────────────→ next mutation
```

## Layer 1 — Seed Generator

역할:

- 작고 정상적인 TAR test case 생성
- 사람이 이해할 수 있는 seed 유지
- 실험의 안정적인 초기 입력 제공

초기 seed 기능은 최소화한다.

## Layer 2 — Structure Mutator

역할:

- entry type 변경
- path 변경
- link target 변경
- entry 순서 변경
- entry 추가/삭제/복제
- target 존재 여부와 dependency 변경

중요:

Mutation operator는 generic해야 한다. 특정 CVE PoC나 Wormholes의 특정 bypass 번호를 그대로 encoding하지 않는다.

## Layer 3 — TAR Builder

역할:

- 내부 archive representation을 실제 TAR 파일로 serialize
- mutation 정책과 archive 생성 로직을 분리

## Layer 4 — Target Adapter

역할:

- 공통 interface로 실제 extractor 실행
- target마다 다른 실행 방식을 격리

초기 target 순서:

1. node-tar
2. oras-go
3. 일정이 허용하면 GNU tar

Target-specific 로직은 이 Layer에 둔다. generic oracle이나 mutation 코드에 섞지 않는다.

## Layer 5 — State Observer

역할:

- extraction 전/후의 보안 관련 filesystem state를 snapshot

초기 관찰 정보:

- relative path
- object type
- `st_dev`
- `st_ino`
- `st_nlink`
- mode
- size
- symlink target
- 선택된 object의 content hash
- 보호된 sentinel state

초기 버전은 full operation trace 대신 pre/post snapshot을 사용한다.

## Layer 6 — Security Oracle

역할:

- generic security contract 위반 여부 판정

초기 구현 순서:

1. Path Boundary Confinement — sanity/baseline
2. Object Identity Confinement
3. External Effect Noninterference
4. Extraction Root Integrity
5. 이후 instrumentation이 추가되면 Check/Use Coherence

## Layer 7 — Feedback / Corpus

역할:

- 관찰된 state를 안정적인 signature로 변환
- test case가 interesting한지 판정
- 새로운 security-relevant state를 만든 입력 보존
- 보존한 seed를 다음 mutation 대상으로 스케줄링

이 Layer가 InodeFence의 핵심 연구 메커니즘이다.

## 계획 중인 공통 Data Flow

```text
ArchiveCase
    ↓
build / run
    ↓
ExecutionResult
    ↓
observe
    ↓
StateSnapshot
    ↓
signature
    ↓
StateSignature
    ↓
oracle
    ↓
ViolationResult
    ↓
feedback
    ↓
Interesting / Boring
```

정확한 Python data model은 각 책임이 합의된 뒤 다음 구현 Layer에서 고정한다.

## 구현 순서

### Milestone 1 — 최소 관찰 경로

```text
작은 Known TAR
    → 하나의 target
    → sandbox
    → pre/post snapshot
    → path + identity + effect oracle
```

### Milestone 2 — Generic TAR 생성

내부 data model로 동일한 TAR case를 생성한다.

### Milestone 3 — Mutation

generic structural mutation을 추가한다.

### Milestone 4 — Feedback Loop

interesting security state를 보존하고 다시 mutation 대상으로 사용한다.

### Milestone 5 — Evaluation

baseline, ablation, known-vulnerability rediscovery, current-version campaign을 수행한다.

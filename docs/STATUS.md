# 현재 프로젝트 상태

이 문서는 **현재 main이 어디까지 왔고 다음에 무엇을 할지**만 기록한다.

설계 근거나 긴 설명은 다른 문서에 둔다.

## 현재 단계

**Layer 1 완료 → Layer 2 시작 직전**

```text
Layer 0 — 개발환경                         ✅ 완료
Layer 1 — 연구 기반/범위/아키텍처          ✅ 완료
Layer 2 — 공통 Data Model                  ⏭ 다음
Layer 3 — Minimal End-to-End Pipeline      ⬜
Layer 4 — Generic Mutation                 ⬜
Layer 5 — Feedback / Corpus                ⬜
Layer 6 — Baseline / Evaluation / Paper    ⬜
```

## 완료된 것

### 개발환경

- Ubuntu 24.04 Dev Container
- Python 3.12
- Mac/OrbStack 검증
- WSL2/x86_64 검증
- Linux runtime volume
- hardlink/symlink self-check
- LF line ending 통일
- Ruff / pytest

### 연구 기반

- 프로젝트 범위
- 연구 질문 / 가설
- 위협 모델
- 선행연구 포지셔닝
- Security Contract
- 전체 architecture
- 개발환경 정책
- AGENTS 규칙

### Data Model 구현 전 기초 예제

- regular file / directory / hardlink / symlink TAR fixture 4종과 결정적 재생성 script
- Linux runtime sandbox에서 extraction 후 metadata를 출력하는 수동 probe
- [TAR baseline 실행·관찰 안내](examples/tar-baseline.md)와 filesystem 의미론 테스트

Layer 2의 공통 Data Model과 자동 pipeline은 아직 구현하지 않았다.

## 다음 작업

다음 구현 Layer에서는 **공통 Data Model**만 정의한다.

우선 후보:

- `ArchiveEntry`
- `ArchiveCase`
- `ExecutionResult`
- `ObjectSnapshot`
- `StateSnapshot`
- `StateSignature`
- `ViolationResult`

아직 모든 모델을 한 번에 구현하지 않는다.

첫 시작점은 `ArchiveEntry`와 `ArchiveCase` 정의다.

## 지금 하지 않을 것

- 본격 fuzzing loop
- CVE-specific payload generator
- 복잡한 symlink chain generator
- eBPF/fanotify instrumentation
- coverage-guided fuzzing
- multi-target 동시 지원
- 성능 최적화

## 현재 핵심 Research Contract

초기 구현 우선순위:

1. Path Boundary Confinement — baseline/sanity
2. Object Identity Confinement
3. External Effect Noninterference
4. Extraction Root Integrity — 이후
5. Check/Use Coherence — 이후

## 이 문서를 언제 갱신하나?

다음 중 하나가 main에 merge되면 갱신한다.

- Layer가 넘어갈 때
- 공통 interface가 확정될 때
- 연구 범위가 바뀔 때
- target 우선순위가 바뀔 때
- 큰 blocker가 생길 때

작은 refactor나 단순 버그 수정 때마다 갱신할 필요는 없다.

# 현재 프로젝트 상태

이 문서는 **현재 checkout에서 구현·검증한 범위와 다음 작업**을 기록한다. Feature branch의 완료 표시는 main merge를 의미하지 않으며, 사람의 review와 merge가 필요하다.

설계 근거나 긴 설명은 다른 문서에 둔다.

## 현재 단계

**Layer 2 완료 + Layer 3 최소 pipeline 완료 → Layer 4 Generic Mutation 준비**

```text
Layer 0 — 개발환경                         ✅ 완료
Layer 1 — 연구 기반/범위/아키텍처          ✅ 완료
Layer 2 — 공통 Data Model                  ✅ 완료
Layer 3 — Minimal End-to-End Pipeline      ✅ Python reference / snapshot 범위
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
- `make check`: Ruff / Pyright / pytest / 환경 검사 / 문서 integrity 검사
- PR/main CI, Issue Forms와 scoped AGENTS 기반 협업 규칙
- finding disclosure 정책과 검증된 experiment summary 보관 규칙

### 연구 기반

- 프로젝트 범위
- 연구 질문 / 가설
- 위협 모델
- 선행연구 포지셔닝
- Security Contract
- 전체 architecture
- 개발환경 정책
- AGENTS 규칙

### 기초 예제와 regression

- regular file / directory / hardlink / symlink TAR fixture 4종과 결정적 재생성 script
- Linux runtime sandbox에서 extraction 후 metadata를 출력하는 수동 probe
- [TAR baseline 실행·관찰 안내](examples/tar-baseline.md)와 filesystem 의미론 테스트

Fixture generator는 core builder를 사용하며 기존 TAR bytes와 probe behavior를 유지한다.

### Core engine foundation

- 순서·중복·raw path/link 의미를 보존하는 immutable ArchiveEntry/ArchiveCase
- ExecutionResult, lstat ObjectSnapshot/StateSnapshot, StateSignature, typed ViolationResult/RunResult
- 고정 metadata, strict UTF-8, USTAR builder와 format provenance/SHA-256
- TargetAdapter Protocol과 별도 process의 Python tarfile/data reference adapter
- `/var/lib/inodefence` 내 disposable runtime, 보호 sentinel, symlink를 따라가지 않는 관찰·cleanup
- Before/after 생성·삭제·identity·내용·metadata 변화 비교
- C0 persistent 외부 namespace 변화, C1 lstat identity 공유, C2 sentinel 변화 판정
- raw inode/timestamp 없는 관계 signature; 최종 feedback 정책은 후속 작업
- versioned canonical JSON으로 case·실행·snapshot·판정 근거 export
- 실제 Linux filesystem, reject/partial extraction/timeout, E2E와 기존 baseline regression 테스트

Python reference는 architecture 검증과 integration baseline용이며 최종 연구 benchmark가 아니다.
C0의 direct path use 전체와 transient state는 snapshot만으로 판정할 수 없다. 관찰 실패를 PASS로 처리하지 않는다.

## 다음 작업

다음 Task Contract는 **Layer 4의 Generic Mutation** 범위를 확정한다. 기존 ArchiveCase를 입력/출력으로 사용하고, entry type/path/link/order/dependency를 일반 규칙으로 변형한다.
이후 Layer 5에서 signature schema와 corpus 선택 정책을 실험용으로 고정한다.
Benchmark adapter 우선순위는 node-tar → oras-go → 선택 GNU tar를 유지한다. Unsafe target 연결 전에는 OS 수준 실행 격리와 target/version 설정을 함께 검토해야 한다.

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

다음 변경을 담는 PR에서 구현 상태를 함께 갱신한다. main에서의 완료는 해당 PR merge 후 성립한다.

- Layer가 넘어갈 때
- 공통 interface가 확정될 때
- 연구 범위가 바뀔 때
- target 우선순위가 바뀔 때
- 큰 blocker가 생길 때

작은 refactor나 단순 버그 수정 때마다 갱신할 필요는 없다.

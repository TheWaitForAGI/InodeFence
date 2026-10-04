# 현재 프로젝트 상태

이 문서는 **현재 checkout에서 구현·검증한 범위와 다음 작업**을 기록한다. Feature branch의 완료 표시는 main merge를 의미하지 않으며, 사람의 review와 merge가 필요하다.

설계 근거나 긴 설명은 다른 문서에 둔다.

## 현재 단계

**Layer 2 완료 + Layer 3 최소 pipeline 완료 + Layer 4 Generic Mutation v1 + Layer 5 Feedback / Corpus v1 구현**

```text
Layer 0 — 개발환경                         ✅ 완료
Layer 1 — 연구 기반/범위/아키텍처          ✅ 완료
Layer 2 — 공통 Data Model                  ✅ 완료
Layer 3 — Minimal End-to-End Pipeline      ✅ Python reference / snapshot 범위
Layer 4 — Generic Mutation                 ✅ v1: 독립 operator / uniform baseline
Layer 5 — Feedback / Corpus                ✅ v1: 독립 novelty / in-memory / uniform 선택
Layer 6 — Baseline / Evaluation / Paper    ⬜
```

## 실행 준비 상태

**READY FOR FULL CODE / ARCHITECTURE AUDIT** — pre-audit infrastructure 작업을 완료했다.
Full repository audit와 security evaluation은 아직 수행하지 않았다.

Trusted Linux controller → explicit host stdio Docker broker → disposable untrusted target
container 경계를 구현·검증했다. 기존 Dev Container의 권한은 변경하지 않았다. Target에는
현재 controlled run의 named-volume subpath만 노출하고 source/home/host bind/runtime socket을
전달하지 않는다. Network none, read-only rootfs, non-root uid/gid, cap-drop ALL, NNP,
private PID/IPC/cgroup, memory/PID/nofile/per-file FSIZE/tmpfs bounds를 적용한다.
[정확한 policy와 실행 명령](../src/inodefence/execution/README.md)을 따른다.

Pinned Node22.22.0/tar7.5.22 image, contained invocation, fail-closed gate, frozen isolation
provenance와 ExperimentConfig v2 binding을 연결했다. Clean main에서 tiny benign configured
campaign8회를 실행했다: SUCCESS8, Corpus observations8/interesting6/retained6/unique-states6,
violation fingerprints0, observed C0/C1/C2 violated verdict0, container9/9 제거 및 runtime 정리.
Actual seed content, prior retained-parent lineage, stored config/provenance와 checksum을 검증했다.

Focused lifecycle review와 static dependency 검사(40 modules/97 internal imports/forbidden edges0)를
완료했다. Completed export는 manifest v4와 config/steps를 staged fsync/checksum 검증 후 Linux
no-overwrite atomic publication한다. Full suite614와 별도 실제 container CI가 통과했다.
[검증 기록·정확한 checksum·attestation assessment·한계](../experiments/summaries/pre-audit-readiness-v1.md)를 따른다.

| 기준 | 현재 상태 | 범위 |
| --- | --- | --- |
| ENGINE READY | 준비 | bounded engine/config/provenance/evidence와 기존 semantics regression |
| BENCHMARK INFRASTRUCTURE READY | 준비 | contained Node의 tiny benign full-path 및 lifecycle 검증 |
| READY FOR FULL CODE / ARCHITECTURE AUDIT | 준비 | 다음 작업은 repository-wide audit; full audit를 했다는 뜻은 아님 |
| EVALUATION READY | 아님; EVALUATION NOT YET RUN | benchmark/CVE 평가 전 full audit와 별도 연구 Task Contract 필요 |

Actual path: ExperimentConfig → target/policy binding → safety gate → backend attestation →
frozen ExecutionProvenance → bounded Campaign/Corpus/mutation → run_case → target container →
Observer → C0/C1/C2 + Signature → Feedback → CampaignResult → staged structured evidence export.
Source/provenance, isolation policy와 config ID는 feedback novelty가 아니다.

PR34의 in-Dev-Container namespace EPERM/cgroup read-only는 [역사적 환경 지원 기록](../experiments/summaries/linux-isolation-support-v1.md)이다.
그 환경을 약화하지 않고 별도 container backend를 선택했다. Snapshot-only observation,
runtime/kernel trust/portability, total storage/CPU bounds, dirty patch 미보존 및 persistence의
hard-interruption 한계는 계속 명시한다. ENGINEERING FOUNDATION에서 audit 준비 단계로 이동했으며
feature expansion은 여기서 멈춘다.

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
- PR #13/#16/#17/#18과 PR #15의 model contract reconciliation: E2E schema/frozen-slots invariant 유지, raw archive input과 canonical observed path의 경계 명시
- ExecutionResult는 process evidence이며 security verdict가 아님; 네 status의 actual duration_seconds를 monotonic `perf_counter()`로 기록하고 configured timeout_seconds와 분리
- ObjectSnapshot의 permission/special mode bits와 regular SHA-256 lowercase hex evidence 의미 및 current runtime-layout Region policy 명시
- 고정 metadata, strict UTF-8, USTAR builder와 format provenance/SHA-256
- TargetAdapter Protocol과 별도 process의 Python tarfile/data reference adapter
- `/var/lib/inodefence` 내 disposable runtime, 보호 sentinel, symlink를 따라가지 않는 관찰·cleanup
- Before/after 생성·삭제·identity·내용·metadata 변화 비교
- C0 HARNESS 포함 extraction root 밖 persistent namespace 변화, C1 lstat identity 공유, C2 sentinel 변화 판정
- `StateSnapshot`: archive/input.tar digest와 harness metadata를 포함한 sandbox 전체 raw evidence
- `StateSignature` v2: EXTRACTION/EXTERNAL의 normalized security state; HARNESS(`.`, `archive/**`)와 case/TAR identity 제외
- scope 안의 identity group과 sentinel effect 보존, regular-only nlink(nonregular는 None), raw inode/timestamp 값 제외; 연구 효과와 최종 feedback 정책 평가는 후속 작업
- versioned canonical JSON으로 case·실행·snapshot·판정 근거 export
- 실제 Linux filesystem, reject/partial extraction/timeout, E2E와 기존 baseline regression 테스트
- 서로 다른 case/TAR SHA-256의 동일 semantic state가 같은 signature라는 실제 `run_case()` regression
- harness-only 변화의 signature novelty 제외, 정상 setup baseline의 C0 nonviolation, root-level external 생성·삭제·교체 regression
- archive namespace 생성 및 input.tar 삭제·identity/type 교체의 실제 `run_case()` C0 evidence와 signature isolation regression
- C0의 namespace/content-effect 구분, identity-group projection과 directory nlink 정규화 유지
- BEFORE는 setup 이후, AFTER는 target 종료 후 bookkeeping/cleanup 이전; adapter 관찰 구간 내 harness namespace write 금지

Python reference는 architecture 검증과 integration baseline용이며 최종 연구 benchmark가 아니다.
C0의 direct path use 전체와 transient state는 snapshot만으로 판정할 수 없다. Snapshot은 actor provenance가 없으며 target attribution은 runner/adapter lifecycle 계약에 의존한다. 관찰 실패를 PASS로 처리하지 않는다.

### Generic Mutation v1

- canonical ArchiveCase → ArchiveCase 변형: add/remove/duplicate/reorder/path/hardlink/symlink/link-target 8개 독립 operator
- caller-owned `random.Random`만 사용하며 원본 불변성, raw spelling, 순서·중복과 적용 불가 시 deterministic no-op 유지
- uniform `mutate()`는 baseline convenience API; 향후 scheduler가 개별 operator를 직접 선택 가능
- constructor와 deterministic USTAR builder의 경계를 별도 integration test로 검증

### Feedback / Corpus v1

- 기존 StateSignature v2 equality와 stable semantic violation fingerprints의 독립 novelty channel
- C0/C2는 path/changed-field labels, C1은 internal/sentinel path 관계; raw dev/inode/timestamp/값/prose 제외
- 같은 signature의 새 C0/HARNESS evidence도 interesting으로 보존하는 실제 run_case regression
- inspectable FeedbackDecision: interesting observation과 새 retained entry를 구분
- in-memory Corpus: 같은 case_id는 한 번만 보존하되 이미 보존한 case의 새 outcome도 seen indexes에 반영
- compact frozen CorpusEntry: ArchiveCase와 최초 admission signature/fingerprints; full RunResult/raw logs는 저장하지 않음
- immutable CorpusStats/entries snapshot, insertion order와 caller-owned RNG를 사용하는 uniform baseline parent 선택
- case/TAR/input digest, HARNESS metadata, execution status/exit code/duration과 raw inode allocation의 novelty 유출 방지
- caller 수준의 Corpus.select_case → Mutator → 단일 run_case → Corpus.consider 조합 regression
- 한 Corpus는 한 caller-controlled campaign context; complete campaign key/persistence를 제공하지 않음

Bounded deterministic campaign v1과 node-tar adapter의 정상 fixture integration은 구현됐다. Adaptive scheduler/persistence는 후속 작업이며 Node-tar의 tiny benign configured campaign은 검증했으며 ORAS와 security evaluation campaign은 현재 범위 밖이다. Known-vulnerability rediscovery, new vulnerability discovery, research effectiveness와 evaluation/ablation 결과는 아직 없다. C3/C4와 Layer 6도 후속 단계다. Corpus retention/stats는 연구 효과나 취약점 확정의 증거가 아니다.

## 다음 작업

**Full repository-wide code, architecture, security-contract, reproducibility, maintainability
and test-quality audit.** 그 audit 이후에만 benchmark/CVE evaluation을 별도 Task Contract로 진행한다.

[Pre-audit freeze](../experiments/summaries/pre-audit-readiness-v1.md)는 제한된 integration review이며
전체 code audit가 아니다. [이전 infrastructure review](../experiments/summaries/infrastructure-readiness-v1.md),
[이전 engineering audit](../experiments/summaries/final-engineering-audit-v1.md)와
[reference pilot](../experiments/summaries/reference-campaign-pilot-v1.md)은 해당 revision의 역사적 기록이다.

Backend는 narrow execution contract를 제공한다. Future ORAS/GNU-tar는 target invocation/image를
추가하는 위치가 명시돼 있으나 구현하지 않았다. C0/C1/C2/Signature/feedback/RNG/budget semantics는
변경하지 않았다. Image ID/worker/lock digest를 content anchor로 사용하며 massive dependency hashing은
추가하지 않았다. Dirty patch/exact Python binary/image availability의 한계는 다음 audit에서 검토한다.

## 지금 하지 않을 것

- 대규모/parallel fuzzing campaign
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

## Bounded deterministic campaign v1

- `campaign.run_campaign`: explicit seeds → select → mutate → one-case run → consider
- Positive integer execution budget, nonempty initial cases, sufficient budget, duplicate initial ID 거부
- Seed 실행부터 모두 budget에 포함; seed는 search RNG를 소비하지 않음
- 한 campaign RNG, no-op 재시도 없음, 모든 target status 보존, harness exception 전달
- Frozen config/step/result, zero-based index와 parent lineage, final CorpusStats/admission order
- Full RunResult를 steps에 보존하므로 O(budget) memory; persistence/resume 없음
- Unit contract와 Linux Python reference semantic-repeatability integration 검사


[Contained benign Node smoke](../experiments/summaries/benign-node-container-smoke-v1.md)는
실제 정책/versions/config/checksum/stats/cleanup과 제한을 기록한다. Unexpected evidence는
보존 후 중단하며 security evaluation이나 effectiveness 결과로 해석하지 않는다.

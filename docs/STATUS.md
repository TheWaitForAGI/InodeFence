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

전체 분류는 **ENGINEERING FOUNDATION**이다.

Pre-audit infrastructure 작업은 **Work Package A의 실행 환경 지원에서 차단**됐다.
2026-10-04 확인한 nonprivileged Dev Container에서 uid 1000의 namespace 생성 8개 probe는 모두
EPERM으로 실패했고 cgroup v2는 read-only였다. `make isolation-support`가 사실과 실패를 JSON으로
기록한다. 진단 성공도 validated execution boundary가 아니다. 환경 정책을 먼저 결정한 뒤 A의
실제 격리 구현·검증을 재개한다. A/B merge 전 Node configured campaign은 계속 0 executions이며
B–G 완료 또는 READY FOR FULL CODE / ARCHITECTURE AUDIT로 표시하지 않는다.
[Blocker 기록](../experiments/summaries/linux-isolation-support-v1.md)에 근거와 후속 조건이 있다.

| 기준 | 현재 상태 | 근거 / 남은 조건 |
| --- | --- | --- |
| ENGINE READY | trusted Python reference 범위에서 준비 | bounded runner, explicit seeds, frozen provenance, config binding, raw export와 Linux regression |
| BENCHMARK READY | 아직 아님 | Node adapter의 정상 fixture는 통과했지만 validated OS isolation과 안전한 Node campaign smoke가 없음 |
| EVALUATION READY | 아직 아님; EVALUATION NOT YET RUN | benchmark boundary 승인, 별도 연구 Task Contract, baseline/ablation/반복 계획이 필요 |

현재 실행 경로는 strict ExperimentConfig → explicit seeds/target binding → campaign safety gate
→ frozen ExecutionProvenance → bounded reference campaign → raw export다. Node-tar는 별도의
controlled fixture integration 경로만 사용한다. [인프라 검증 기록](../experiments/summaries/infrastructure-readiness-v1.md)은
실제 설정/원본 checksum/반복 결과/한계와 audit 범위를 기록한다.

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

Bounded deterministic campaign v1과 node-tar adapter의 정상 fixture integration은 구현됐다. Adaptive scheduler/persistence는 후속 작업이며 Node-tar/ORAS generated-input campaign은 미구현/금지다. Known-vulnerability rediscovery, new vulnerability discovery, research effectiveness와 evaluation/ablation 결과는 아직 없다. C3/C4와 Layer 6도 후속 단계다. Corpus retention/stats는 연구 효과나 취약점 확정의 증거가 아니다.

## 다음 작업

Provenance/configuration 이후 [인프라 audit](../experiments/summaries/infrastructure-readiness-v1.md)을
완료했다. 기존 [engineering audit](../experiments/summaries/final-engineering-audit-v1.md)은 이전 revision의 역사적 기록이다.
Execution Provenance v1은 source revision/dirty, 실행 환경, explicit sentinel/adapter 설정을
첫 실행 전에 고정하며 campaign 결과와 manifest v2에 보존한다. Target execution safety contract는
explicit trusted reference campaign만 허용하며 isolation-required/미선언 target을 runtime 이전에
거부한다. Disposable runtime/Dev Container는 OS 격리가 아니고 검증된 isolation helper는 없다.
Node-tar adapter engineering은 정상 fixture 범위에서 완료됐으며 generated-input campaign은 금지한다.
ExperimentConfig v1은 필수 JSON 설정/정규화된 config ID와 pre-execution seed/target binding을
제공한다. Safe reference config CLI가 실행 전 config ID를 campaign/manifest에 보존한다.
다음 PR의 우선순위는 Linux target execution의 검증 가능한 OS isolation boundary다. Process/filesystem,
credential/network/resource 제한, child 종료와 관찰 구간을 정상 controlled helper로 검증해야 한다.
그 뒤에만 설정 기반의 아주 작은 benign Node campaign smoke를 수행한다. 현재 Node campaign은
runtime/provenance capture/첫 run_case 이전에 거부됐으며 실행 수는 0이다. Requirement를 낮추지 않았다.
Structured export v1은 완료된 campaign을 manifest.json/canonical steps.jsonl로 기록한다. Resume/reader/database는 없다.
`generator.minimal_seed_corpus()`는 기존 정상 baseline 4종을 deterministic immutable tuple로
반환한다. Fixture script도 이 API를 사용하며 campaign의 explicit-seed 계약은 유지한다.
Safe Python reference의 7개 작은 campaign/400 executions 개발 pilot을 완료했다. Repeat의
semantic lineage/feedback과 budget/cleanup을 검증했으며 효과 평가는 아니다.
기록은 [개발 pilot 요약](../experiments/summaries/reference-campaign-pilot-v1.md)을 따른다.
Campaign은 config/initial IDs/lineage/full RunResult를 memory에 보존한다. Structured writer는
결과에 있는 observed target/version/builder/timeout과 exporter 환경을 별도 기록한다. 실행 전
provenance는 stored 값이며 supplied source/environment 정확성은 caller 책임이다. Adaptive scheduler/persistence,
추가 benchmark adapters와 evaluation/ablation은 이후 작업이다. Layer 5 구현과 단위/integration test
통과를 feedback 효과의 증명으로 해석하지 않는다.
Benchmark adapter 우선순위는 node-tar → oras-go → 선택 GNU tar를 유지한다. Unsafe target 연결 전에는 OS 수준 실행 격리와 target/version 설정을 함께 검토해야 한다.
Known-vulnerability rediscovery/PoC/long security campaign은 격리·benchmark 설정에 대한 사람의 검토와
별도 연구 Task Contract가 필요하다. 현재의 engineering smoke를 paper-ready evidence로 사용하지 않는다.

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

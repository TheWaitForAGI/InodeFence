# 현재 프로젝트 상태

상태 갱신일: **2026-10-22**. G0 capability baseline은 main
**`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`**다. 이 SHA는 G0 문서 동결이
검토한 구현 revision이며 최신 main을 뜻하지 않는다. #77–#84 연구 stack은 main에
통합됐다. Internal completion qualification v3의 clean harness revision은 `9ea306f7`이고,
causal filesystem-effect qualification v4의 clean harness revision은 `72bccfa`다.

## 현재 단계와 연구 판정

Layer 2–5 core와 Layer 6 evaluation infrastructure가 구현돼 있다. Layer 6 전체나
paper/effectiveness 검증이 완료된 것은 아니다. [Research Contract
v1](research/design/research-contract-v1.md)의 G0 문서 동결과 transition synthetic stack은
통합됐지만, G1 이후 historical qualification/experiment readiness는 별개다.
과거 Phase-4 global-closeout 대기 문구는 현재 구현 상태로 사용하지 않는다.
[역사적 감사](research/benchmarks/engine-contract-audit.md)와
[handoff](research/benchmarks/post-audit-backlog.md)는 해당 revision의 기록이다.

**N01 historical automated replay는 exact 7.5.2/7.5.3 image에서 8건 readiness와
10건 pair를 완료했고 independent reader가 PASS했다. 최종 상태는
`AWAITING_HUMAN_CORRESPONDENCE_REVIEW`다. Rediscovery와 formal comparison은 NOT_RUN이며,
재발견한 역사적 취약점이나 현재 취약점을 주장하지 않는다.**
상세 identity와 claim boundary는
[N02 qualification report](research/diagnostics/n02-autonomous-integration-and-qualification.md)를 따른다.
N03의 별도 [machine correspondence audit](research/diagnostics/n03-n01-machine-correspondence-audit.md)는
retained evidence와 automated token의 consistency를 PASS로 재확인했지만 human review를 대체하지 않는다.
[N04 독립 retained-evidence 감사](research/diagnostics/n04-n01-independent-evidence-audit.md)는
원본 checksum을 다시 확인하고 별도 Linux 사본에서 current-main reader를 재실행해 같은 automated
PASS를 재구성했다. 단, 원 N02 root에는 npm tarball bytes가 없어 선언된 package digest의 직접
재해시는 **NOT_VERIFIABLE**이다. 이 결과도 machine evidence이며 human qualification token을
발급하지 않는다.
[B0/B1/B3 pilot proposal](research/benchmarks/n03-b0-b1-b3-pilot-task-proposal.md)은 exact candidate
schedule과 5초/10초 mismatch를 기록하며 **PROPOSED / NOT_AUTHORIZED / NOT_RUN**이다.

N04의 별도 [5초 preflight Task Contract](research/benchmarks/n04-five-second-preflight-task-contract-v1.md)는
사용자가 직접 승인한 최대 8건의 benign readiness 범위였다. 2026-10-18 KST 단일 attempt는
target 실행 전 host-only Docker metadata 요청이 transport allowlist에서 거부되어
**PREFLIGHT_INCONCLUSIVE / ATTEMPT CONSUMED**로 종료됐다. target extraction과 oracle control은
각각 0건이며 5초 readiness는 **NOT_EVALUATED**이다. 원본 host ledger와 판정은
[N04 preflight result](research/diagnostics/n04-five-second-preflight-result.md)에 고정했다.
후속 transport 수정은 구현·synthetic 검증 대상일 뿐 재실행 승인이 아니다. 4,000회 B0/B1/B3
pilot과 native P0/P1/P2 campaign은 계속 **NOT_AUTHORIZED / NOT_RUN**이다.

N05의 [독립 critical-path 검토](research/diagnostics/n05-native-qualification-critical-path.md)는
retained N04 host ledger를 재해시해 같은 `PREFLIGHT_INCONCLUSIVE`를 재구성했고, host-only
metadata transport correction의 실제 caller/allowlist를 bounded Linux tests로 확인했다. 별도
draft PR #112는 controller stderr의 1 MiB bounded prefix와 truncation을 checksummed host ledger에
결합하지만 새 attempt/mode를 만들지 않는다. 그 위의 독립 N05 구현 후보는
`preflight-node-n05-5s-v2`, 새 attempt/path, 실제 authorization JSON의 반복 검증,
source/controller/target admission, 최대 8건의 benign schedule, 독립 reader와 fail-closed host
ledger를 추가했다. 합성 Linux 회귀만 수행했으며 historical target은 실행되지 않았다.
[새 5초 preflight 계약 초안](research/benchmarks/n05-five-second-preflight-task-contract-draft.md)의
상태는 **IMPLEMENTED CANDIDATE / SYNTHETIC TESTED / NOT_AUTHORIZED / NOT_RUN / AWAITING
EXECUTION-SOURCE AND CONTROLLER FREEZE**다. PR #108은 아직 실제 preflight/authorization
record를 읽지 않고 digest 문자열만 기록하므로 verified N05 evidence의 소비자는 아니다.

MID-03의 Track A consumer Units 1–3 구현 후보는 합성 N05 evidence에서 original pilot/N05
재검증, process-local admission capability를 요구하는 freeze, retained-evidence reader와
host-attempt ledger를 연결한다. Host가 controller launch 전에 attempt ID와 `started.json`을
no-overwrite로 발행하고, controller/campaign claim은 같은 ID만 사용한다. 발행된 host attempt는
spawn/출력/exit/watchdog/cleanup 실패에도 소비되며 terminal/manifest가 없거나 cleanup이 불완전하면
성공으로 읽지 않는다. 이 상태는 target-free engineering evidence일 뿐이며, controller에서
authoritative host/Track A/pilot/N05/protocol 경로를 실제로 다시 열 수 있게 하는 배치 연결과 Unit 4
final-manifest/analysis 결합은 남아 있다. N05와 4,000회 Track A pilot은 **NOT_RUN**이다.

같은 검토는 node-tar 7.5.22의 실제 `CHECKFS2` unlink callback → `MAKEFS` branch를 exact
package bytes에서 식별했다. 이는 native-v3 feasibility 근거지만 dependency producer evidence는
아니다. [native-v3 qualification 계약 초안](research/benchmarks/n05-native-rebinding-v3-qualification-task-contract-draft.md)은
positive/negative fixture와 perturbation gate를 제안하며 **NOT_AUTHORIZED / NOT_RUN**이다.
Native producer/image는 여전히 **NOT_IMPLEMENTED / NOT_FROZEN**이고 기존 v2 판정과 policy ID는
변하지 않는다.

## DESIGNED / IMPLEMENTED / TESTED / EXPERIMENTALLY VALIDATED

[Evidence 용어](research/design/research-contract-v1.md)는 각 수준을 독립적으로 기록한다.
아래 TESTED는 지정된 범위의 engineering evidence이며 research effectiveness를 뜻하지 않는다.

| 영역 | DESIGNED | IMPLEMENTED in current source | TESTED evidence / 범위 | EXPERIMENTALLY VALIDATED research claim |
| --- | --- | --- | --- | --- |
| C0/C1/C2 | [계약](research/design/security-contracts.md) | persistent BEFORE/AFTER namespace, identity, sentinel effects | [oracle tests](../tests/test_state_semantics.py), [observer](../tests/test_observer.py), [real pipeline](../tests/test_pipeline.py) | N01 exact pair에서 7.5.2 C1/C2 5/5, 7.5.3 0/5; final human disposition pending |
| Linux execution | fresh runtime + container-required third-party boundary | backend / prepared invocation / verified artifact admission; N01 exact wrapper locks and bounded pair orchestration | [container integration](../tests/README.md); pinned Node benign smoke; N01 8+10 real historical runs와 independent reader PASS | N01 automated replay complete; final qualification pending |
| Mutation | legacy / M1 / protected-component / A3 contracts | eight slots; M1 nested/reused names/dependencies; versioned default-sentinel component policy; no-reorder versions | [mutator tests](../tests/test_mutator.py), [constructive addressing](../tests/test_mutator_addressing.py), [search composition](../tests/test_campaign_search.py) | logical address generation만 TESTED; historical effect 미검증 |
| Search / feedback | B0/B1/B3 and A1/A2 | `SearchState`, `run_search_campaign`, explicit policy config | [policy checks](../tests/test_feedback_search_contracts.py), [trusted reference integration](../tests/test_campaign_search_integration.py) | 비교 효과 미검증 |
| Entry transitions | P0 final-state, P1 transition retention, P2 transition-adaptive mutation; separately versioned v3 rebinding composite | v1 model/search/evaluation; v2 event model/feedback, bounded node-tar producer/raw export, independent reader and qualification runner; additive v3 composite model/strict reader/finite feedback | synthetic tests plus node-tar/libarchive controlled qualification; v2 producer 10 checks PASS and 480-run matrix independently verified at `36ff7fd`; v3 22 synthetic checks and canonical 1,584-test suite PASS | v1 `BLOCKED_NATIVE_OBSERVATION`; v2 `V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED` (replacement coverage); v3 native producer NOT_IMPLEMENTED and qualification/effectiveness NOT_RUN |
| Minimization | bounded deterministic generic/USTAR reduction | core and exact-fingerprint evidence binding | [minimizer tests](../tests/test_minimizer.py), [USTAR checks](../tests/test_minimizer_ustar.py) | historical/unknown candidate 없음 |
| Evaluation / reproduction | explicit provenance, immutable raw → verified derivation | reader, pair records, failure ledger/legacy journal, policy journal/timing/repetition/controller HWM, candidate 3+3 raw replay, N01 machine matcher, qualification/matrix, benign replay, completed policy export/config/dataset/statistics | [evaluation tests](../tests/evaluation/), [benign replay tests](../tests/replay/) | HWM/matcher는 controlled TESTED; historical pilot memory/candidate assessment / human known-class judgment / formal dataset 없음 |
| C3/C4 / generality | 후속 contracts / RQ4 | C3/C4와 ORAS adapter 없음; GNU route는 benign allowlist만 | broader scope의 실행 증거 없음 | 미검증 |

## 기준 main의 검증 근거

[main CI run 37248955432](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37248955432)
은 `8ad07b8`에서 check와 container-integration을 통과했다. 해당 baseline의 canonical
`make check`는 **1,304 tests PASS**, Ruff/Pyright/environment/docs 검사를 포함한다.
이는 고정 revision의 검증 기록이지 이후 checkout에 적용되는 live test count가 아니다.
Contained **node-tar 7.5.22 benign smoke PASS**는 실제 extractor를 실행한 engineering
증거다. Historical 7.5.2/7.5.3 execution이나 rediscovery 증거로 승격하지 않는다.
과거 [pre-audit](../experiments/summaries/pre-audit-readiness-v1.md) 및
[benign Node 요약](../experiments/summaries/benign-node-container-smoke-v1.md)은 각자의
revision/config/checksum을 유지한다. 그 수치를 현재 실험 결과로 옮기지 않는다.

## 실제 실행 및 evidence 경계

`pipeline.run_case`는 TAR/layout/sentinel과 target 준비 뒤 BEFORE를 찍고, target 종료 뒤
bookkeeping/cleanup 전에 AFTER를 찍는다. 양쪽 cleanup이 끝나야 결과가 반환된다.
Disposable directory는 OS sandbox가 아니다. Third-party target은 검증된 `IsolatedTarget`이
필수이며 Linux runtime volume `/var/lib/inodefence`를 source bind mount와 분리한다.

[Security Contract](research/design/security-contracts.md)의 C0는 HARNESS까지 포함한
sandbox 내 extraction 밖 persistent namespace 변화다. C1은 post-state lstat identity,
C2는 지정 sentinel의 전후 content/metadata 변화다. Transient effect, sandbox 밖 접근,
symlink referent, inode reuse, direct-use/tracing은 판정하지 못한다. 관찰 실패는 오류이며
nonviolation을 만들지 않는다. `violated=False`는 safety proof가 아니다.

`run_search_campaign` / `SearchCampaignConfig`는 **B0/B1/B3 × FULL/A1/A2 ×
legacy/M1/protected-component/A3**를 명시적으로 실행한다. B0는 unretained walk, B1은 key novelty admission,
B3는 key OR violation novelty admission이다. A1/A2는 feedback key만 투영한다.
A3는 reorder draw를 유지한 no-op이며 insertion/duplicate의 order variation은 남는다.
[정확한 비교 범위](research/benchmarks/baseline-and-ablation-v1.md)를 따른다.
Path-only와 fixed-recipe baseline은 없으며 RQ2/RQ3의 비교로 주장하지 않는다.

The generic entry-transition model preserves exact archive ordinal/path/type/link-target
association, complete raw checkpoints, derived filesystem deltas and normalized transition
keys without changing `RunResult` or final C0/C1/C2 semantics. Its current evidence is a
deterministic synthetic file → hardlink → replacement sequence. The separate P0/P1
campaign core keeps uniform parent/mutation behavior constant while replacing P0 final-state
admission with P1 transition-key admission; full-state, transition, violation and incomplete
trace diagnostics remain independent. P2 keeps P1 retention and uniform parent selection,
then adapts explicit operator weights from 1 through 8 using only binary new-transition-key
reward. Violations remain diagnostic and do not receive scheduler reward. A native extractor
completion producer and transition effectiveness are still not implemented results.
[The exact contract](research/design/transition-feedback-v1.md) keeps synthetic model/search
correctness separate from native observation qualification.

`TransitionEvaluationConfig` binds the policy IDs and frozen provenance to a separate
checksummed result bundle. Its reader replays parent/operator/mutation/admission/scheduler
decisions before summaries or P0/P1/P2 arm statistics are accepted. This is TESTED with a
deterministic synthetic producer; it does not make native target effectiveness a result.

Pinned node-tar 7.5.22 public async/sync events, Linux inotify, strace and fresh-process
prefix replay were tested with benign regular/directory/hardlink/symlink/duplicate-path
fixtures. Public events precede common write/close/metadata completion; event receipt
snapshots can include later effects or fail coherent capture; syscall completion order is
not archive order; prefix replay is a separate counterfactual execution. A separate
libarchive 3.7.2 public write-disk qualification associated all ordinal/path markers but
applied directory metadata only during final writer close.

A third source-guarded qualification wrapped node-tar's actual bundled private `checkFs2`
callback. All 440 marker/snapshot callbacks had exact entry association, but mixed snapshot
completion was out of archive order in 20/20 runs, independent-files was out of order in
18/20, callback snapshots included later-entry effects, and one of 220 snapshot callbacks
recorded a consistency failure. Snapshot median target time was 1.336×–1.660× stock in the
three benign cases and marker/snapshot scheduling distributions differed. Final semantic
states remained equal, which is insufficient to establish intermediate neutrality. All
three controlled candidate sets are **QUALIFIED FAIL** for the current complete
ordered-checkpoint contract. No native producer is implemented, and P0/P1/P2 target
effectiveness remains **NOT_RUN**. See the
[qualification decision](research/design/entry-transition-observation-v1.md) and retained
[node-tar](../experiments/summaries/node-transition-observation-qualification-v2.md) /
[libarchive](../experiments/summaries/libarchive-entry-boundary-qualification-v1.md) /
[internal completion](../experiments/summaries/node-internal-completion-qualification-v3.md)
summaries.

A fourth source-guarded candidate propagated entry identity through Node async resources
and recorded callback-based filesystem operation completions instead of treating a callback
snapshot as a checkpoint. Its clean 480-process run preserved all expected outcomes and
final semantic states. All 1,020 operation events had exact entry association and there were
no observation failures. Independent-files nevertheless completed `0,1,3,2` in 20/20
effects runs and recorded 162 successful later-ordinal operations before earlier entry
completion. The context-only and effects scheduling distributions differed, and effects
median target duration was 1.152×–1.308× stock across fixtures. Partial rejection was
preserved after ordinal 0 completion in 20/20 effects runs. The fixed rule therefore gives
**QUALIFIED FAIL** and the native v1 gate is **BLOCKED_NATIVE_OBSERVATION**. No producer or
target P0/P1/P2 run exists. The [v4 summary](../experiments/summaries/node-causal-effect-qualification-v4.md)
retains exact evidence. The separate
[partial-order/effect-event v2 observation contract](research/design/entry-effect-observation-v2.md),
[architecture](research/design/entry-effect-architecture-v2.md),
[normalized feedback contract](research/design/entry-effect-feedback-v2.md) and
[design review](research/design/entry-effect-design-review-v2.md) now pass Design Gate 1.
The immutable generic lifecycle/effect/identity/causal trace model, separate
`EffectRunResult`, finite normalized keys, fail-closed P0-v2/P1-v2/P2-v2 search, bounded
scheduler and caller-owned closed loop are IMPLEMENTED and TESTED synthetically. Synthetic
Gate 2 is PASS. Gate 3 now has a source-guarded bounded worker, contained adapter, controller
flush verification before AFTER, class-specific evidence conversion and no-overwrite raw
export. The WSL recovery task retained the Gate 4 base `5575169` and fixed two target-side
integration defects on a separate branch. At clean revision `36ff7fd`, the contained Gate 3
suite passed 10/10 checks and canonical `make check` passed 1,387 tests. Gate 4 completed all
480 runs: 420 success and 60 expected rejection. Fresh controller and host readers each
verified all 320 native bundles and 160 stock records. Thirteen of fourteen mandatory
criteria passed; replacement coverage failed because duplicate-path reused the same inode
and truncated it in 20/20 full runs. The exact decision is
`V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`. Immutable raw evidence, checksums and audit
reports are retained in the [v2 summary](../experiments/summaries/node-native-effect-observation-qualification-v2.md).
Target campaign remains blocked and NOT_RUN.

후속 node-tar 진단은 exercised archive-only/precreated cases의 실제 namespace rebinding이
단일 operation이 아니라 `unlink -> create/link/symlink`로 구성됨을 확인했다. 18/18 complete
native diagnostic bundle에서 v2 `namespace_replacement`는 0건이었으며, 이는 reader가 frozen
계약을 잘못 분류했다는 근거가 아니다. v2 판정은 그대로다. 별도
[v3 rebinding semantics 제안](research/design/entry-effect-rebinding-v3-proposal.md)은 composite
dependency/evidence 조건에 대해 기술 검토됐고, 별도
[Task Contract](research/benchmarks/n04-namespace-rebinding-sequence-v3-task-contract.md)에 따라
generic model, strict independent reader와 additive finite feedback이 **IMPLEMENTED / SYNTHETIC
TESTED**됐다. Same-path/explicit-absence/conflict-free dependency gap이 v2 normalized keys에 없는
구분을 추가함을 synthetic nonredundancy fixture로 확인했다. Native dependency producer는
**NOT_IMPLEMENTED**, qualification/effectiveness는 **NOT_RUN**이며 어떤 native campaign도
허가하지 않는다. 상세 결과는 [N04 v3 synthetic verification](research/diagnostics/n04-namespace-rebinding-sequence-v3-synthetic-verification.md)에 고정한다.

Legacy `ExperimentConfig` v1/v2는 여전히 B3/legacy mutation만 허용한다. 별도
`PolicyEvaluationConfig`와 completed policy export/reader/config/dataset/statistics가 구현됐다.
Reader는 raw derivations와 admission/parent binding을 검증하되 실제 RNG/mutation 실행을
재구성하지 않는다. 별도 policy journal은 exact RNG parent/operator/mutation/feedback을 replay하고
중단 prefix/failure를 보존한다. Policy repetition schedule은 exact config slot을 claim하고
complete/failed terminal digest를 결합하며 STARTED slot을 retry하지 않는다. Full result는
O(budget) memory다. Legacy runner에는 completed-step callback이 없다.
Final-state policy runner의 `policy-full-step-monotonic-v1` evidence/reader는 동기 journal
publication까지 포함한 step offsets를 보존한다. Existing result/policy schema와 target duration은
변경하지 않는다. Final publication timing, timed dataset pooling과 known-class adjudication은
완성된 자동 pipeline이 아니다. Target duration으로 전체 latency나 throughput을 대신하지 않는다.
별도 `linux-proc-self-vmhwm-v1`은 terminal slot에 controller process-lifetime peak RSS를 결합하고
측정 slot 사이 process identity 재사용을 거부한다. 이는 campaign delta나 target-container memory가
아니며 historical pilot 측정값은 아직 없다.
[Candidate pair replay](research/design/candidate-pair-replay-v1.md)는 verified policy evidence의
exact case를 counterbalanced affected/fixed 3+3 raw execution에 binding하고 complete/failed/interrupted
prefix를 보존한다. 이는 N01 class match나 human root-cause 판정이 아니다.
[실험 안내](../experiments/README.md)를 따른다.

## 다음 연구 gate

Native entry-transition work cannot proceed to v1 Phase B/C/D. Reopening it requires the
separate v2 qualification Task Contract; v1 policy IDs and evidence cannot be silently reused.
This blocker does not promote or invalidate the independent final-state historical plan.

The v2 contained qualification has completed with a retained negative decision. Replacement
coverage must be established under a separate frozen Task Contract before another matrix.
Native campaign integration remains blocked until the exact
`V2_NATIVE_EFFECT_OBSERVATION_QUALIFIED` decision is retained. The initial v2 policy rejects
incomplete/invalid streams and target-rejection prefixes for admission/reward.
The runtime diagnosis selected the multi-operation branch for the exercised node-tar cases.
The separately versioned v3 generic representation passed its synthetic engineering gate.
The next v3 step is not an implicit campaign: a native dependency producer and qualification
matrix require a new frozen contract and explicit authorization. Alternatively, v2 can only
reopen with a genuine one-operation positive under its own contract.

N03 independent closeout은 [structured report](research/diagnostics/n03-autonomous-research-advancement.md)에
기록한다. Final-state journal/timing/repetition infrastructure는 IMPLEMENTED / TESTED지만 pilot과
known-class adjudication은 완료되지 않았다. Generic v3 rebinding은 synthetic engineering
검증만 완료했으며 v2 negative decision이나 P0-v2/P1-v2/P2-v2 gate를 변경하지 않는다.

**첫 historical qualification인 N01 node-tar 7.5.2 / 7.5.3 hardlink arm은 automated
replay를 완료했고 final human correspondence review를 기다린다.**
두 exact [wrapper locks](../experiments/benchmarks/locks/README.md)는 공통 historical production
closure로 준비하고 portable validator를 통과했으며, N02 attempt에서 image build/runtime/
options/setup admission도 통과했다. M1은 composition을 지원하지만 기존 finite vocabulary가 default
`outside/sentinel.txt`를 생성하지 못한다. 별도 versioned
[protected-component policy](research/design/mutation-protected-components-v1.md)는 original benign
seed에서 해당 상대 주소까지의 deterministic logical reachability를 TESTED했다. 이는 target-visible
setup, historical affected/fixed behavior 또는 rediscovery를 검증하지 않으므로 contained setup과
pair qualification 전 unknown-vulnerability campaign으로 넘어가지 않는다.
[2026-10-15 execution progress](research/diagnostics/n01-historical-execution-progress-2026-10-15.md)는
두 변경의 tested integration revision, N01 contract technical review와 후속 implementation gate를
기록한다. Human authorization은 2026-10-15에 기록됐다. N01 전용 구현은
normal `7.5.22` validator와 분리된 metadata admission, 정확히 8건의 readiness,
counterbalanced 10-run pair, result-first publication과 fresh-process independent reader를 포함한다.
이 구현의 controlled-adapter tests와 별개로 clean `e987c855` source와 trusted
macOS/OrbStack controller에서 두 historical image를 immutable ID로 admission했고, 8건
readiness와 10건 pair를 한 번 실행했다. Independent reader는
`N01_PAIR_AUTOMATED_REPLAY_COMPLETE`를 재계산했다. 7.5.2는 C1/C2 5/5, 7.5.3은
C1/C2 0/5와 strict rejection 5/5였다. Frozen contract의 human correspondence disposition이
남아 final token은 없으며 pilot과 B0/B1/B3는 **NOT_RUN**이다. 전체 evidence는
[N02 report](research/diagnostics/n02-autonomous-integration-and-qualification.md)에 기록한다.
[Benchmark Set](research/benchmarks/benchmark-set-v1.md)과
[catalog](../experiments/benchmarks/README.md)의 15개 G0 planning record는 여전히 정적
`NOT_RUN` 값이며 READY는 없다. 이 값은 별도 N01 qualification evidence의 live 상태를 대신하지 않는다.

순서를 유지한다: G0 정의 → oracle → harness → fuzzer correctness → synthetic →
historical qualification → pilot → experiment freeze → main experiments → candidate triage →
analysis → paper → independent reproduction. 현재 다음 독립 gate는 N01 historical
qualification이다.

[Evaluation protocol](research/benchmarks/evaluation-protocol-v1.md)의 budgets/subsets는
pilot 이전의 제안이며 main-experiment freeze가 아니다. Negative result, qualification failure,
rejection/timeout와 infrastructure-invalid attempts를 모두 보존한다. Raw data는 수동 수정하지 않는다.
11월 2일 발표는 working implementation과 검증된 pilot 범위를 구분해야 하며, 11월 9일
experiment freeze와 11월 30일 최종 artifact는 별도 승인/증거가 필요하다.

## 변경 범위와 문서 우선순위

현재 범위는 Linux TAR/USTAR, C0/C1/C2, fresh extract와 controlled sentinels다.
이 G0 freeze는 ORAS, C3/C4, PAX/GNU encoding, 새 mutation operators 또는 discovery를 추가하지 않는다.
새 기능이나 methodology 변경에는 별도 Task Contract와 영향 문서 검토가 필요하다.

현재 상태는 이 문서, G0 정의는 [Research Contract](research/design/research-contract-v1.md),
C0/C1/C2 의미는 [Security Contracts](research/design/security-contracts.md), 비교/측정 정의는
[연구 질문](research/design/research-questions.md)과 [프로토콜](research/benchmarks/evaluation-protocol-v1.md)을
따른다. Historical audit/summary는 자체 날짜와 SHA의 기록으로만 읽는다.

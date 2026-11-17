# 현재 프로젝트 상태

2026-11-03 이전 결과 기록(중간발표 P0 표, 2026-10-24 한눈에 보기, Ledger·마일스톤의 옛 M3·M4 캠페인 서술)은 [pre-20261103-results](archive/pre-20261103-results.md)로 옮겼다.

## Capability Ledger (살아있는 증거 원장)

이 표가 **현재 능력의 단일 기준**이다. 각 줄은 "능력 → 증거 수준 → 증거 포인터"이고,
현실이 바뀌면 바로 갱신한다(죽은 커밋에 고정하지 않는다). 증거 수준은
[Research Contract](research/design/research-contract-v1.md)의 어휘를 그대로 쓴다:
**DESIGNED**(정의/가설만) · **IMPLEMENTED**(실행 경로 존재) · **TESTED**(명시된 한계 안에서 테스트/검증) ·
**VALIDATED**(고정 조건·반복·raw 증거로 연구 주장 뒷받침). observed(실행 출력로 확인)와
inferred(추론)를 구분하고, synthetic은 native 증거로 승격하지 않는다.

| 능력 | 수준 | 증거 포인터 |
| --- | --- | --- |
| 실제 node-tar 루프(입력→실행→entry별 관찰→C0/C1/C2→feedback→다음 mutation) | TESTED | `make demo` 호스트, LOG 2026-10-24; budget 20/100 완주 |
| entry별 중간 FS 상태 관찰(trace, observed/derived 구분) | TESTED | demo report schema 2 `trace`; native 20/20 step |
| C0/C1/C2 oracle 판정이 fixture와 일치 | TESTED | `scripts.oracle_fixture_check` 4/4 |
| feedback→mutation 연결(corpus admission + operator 가중치) | TESTED | demo `selection`; `test_effect_feedback_sensitivity` |
| 중단 내성(끝난 step이 `.steps.jsonl`에 보존) | TESTED | PR #143; 강제 중단 테스트 |
| producer 견고성(조용한 exit 0 → failed 프레임/lifecycle 기록) | TESTED | PR #144; 호스트 budget 100 100/100 |
| **실제 경계위반을 통제 재현 + affected/fixed 구분**(node-tar 하드링크→외부 참조파일 = C1 identity 공유 + nlink 증가, 이후 릴리스 거부) | TESTED | 재현 스크립트+raw 증거 `experiments/repro/`(5 릴리스 sweep): 최상위 하드링크 7.5.2 공유(nlink 1→2)·7.5.3 거부 = CVE-2026-23745(catalog N01·R1), 중첩 하드링크 7.5.6 공유·7.5.7 거부(7.5.8도 거부) = CVE-2026-24842(CVE-2026-23745 수정이 도입한 check/use 회귀; catalog N02·R2). 동일 outcome oracle이 두 root-cause(R1·R2)를 포착, 릴리스 id/정답경로 하드코딩 없음. **퍼징 자력 발견은 아님**. **M2.2 박제**: 같은 외부-sentinel 하드링크를 production Observer+Oracle로 판정해 손 probe 판정과 일치함을 additive 테스트로 고정 — CI는 7.5.2 공유 post-state를 재현해 generic C1+C2 일치 검증(`tests/test_cross_release_oracle_agreement.py`, run_case 경로 + M2.1 증거 바인딩), native effect-pipeline(`run_node_tar_effect_case`) closure는 container_integration 체크(`tests/container_integration/check_cross_release_oracle_agreement.py`, 호스트 docker+이미지). oracle/fixture/N01 불변, 릴리스 문자열은 증거 키일 뿐 판정 조건 아님 |
| 퍼저가 경계위반을 찾는가(H-A, R/D/S-u) | 본실험 결과 자리(봉인 해제 뒤 기입) | 초기 비교는 arm 간 어휘가 달라 폐기했고, 어휘를 맞춘 R/D/S-u 설계로 다시 실험했다. 이전 기록은 [archive](archive/pre-20261103-results.md) |
| entry-transition native 관찰 | DESIGNED / NOT_IMPLEMENTABLE (honest negative) | native completion boundary 미확보 → NOT_IMPLEMENTED. **ordered-transition 경계접근 gradient**(none<external_namespace<cross_boundary_identity, Region·ChangeField만·answer-agnostic=protected/sentinel 근접 미보상)를 설계했으나, 그 rung이 요구하는 ordered·entry-correlated 경계가 **fundamental하게 관찰 불가**(node-tar: public/OS/private snapshot·causal 전부 QUALIFIED FAIL; decompress: 엔트리 동시·재정렬 기록·컨텍스트 미전파 = 동류; oras-go 더 어려움 — generality-m4 feasibility, observed 2026-10-30). → 구현 코드(`feedback/transition_gradient.py`·`TransitionBoundaryProximity`)는 **dead로 제거**(소비자 0, EN-008); **설계+negative 발견은 transition-feedback-v1.md에 보존**. 2번째 extractor로 실제 일반화되는 건 generality lane canonical `feedback/boundary_attempt_frame.py`(`inodefence-boundary-attempt-v1` frame→M3.1 키 emit+normalize, main M3.1+주언 metrics 소비), 이 transition 경로 아님. transition **모델**(checkpoint/transition/novelty/retention)은 불변. 상세 jiwoong/m3-transition-gradient-signal, transition-feedback-v1.md |
| cross-implementation(2번째 extractor에 generic oracle 적용) | 일부 TESTED(oracle 수준) | **Python stdlib tarfile 통제 차분**: C1 하드링크 fixture를 Python tarfile로 돌려 fully_trusted(영향)=외부 sentinel inode 공유로 production oracle이 C1+C2 발화, data(PEP 706 완화)=거부·위반 0. oracle 코드 불변, target-agnostic 확인. `tests/test_python_tarfile_generality.py` 4 passed. **단 node-tar 결과·fuzzer 자력 발견 아님**(oracle·adapter 수준 일반성 증거). **oras-go(Go)·decompress(JS) adapter 구현 완료**(#176·#177): 동일 generic oracle로 affected/fixed digest-pinned 통제 reference 차분 + container-integration generality 체크 통과 → python-tarfile 포함 **3개 독립 extractor**에서 adapter 수준 일반성 확인(target 로직은 adapter/worker/recipe에 격리, generic 모듈 불변). Ledger M4 |
| 실험 campaign 병렬/클라우드 팬아웃(단일 호스트 직렬화 해소) | IMPLEMENTED/TESTED | **단일 호스트**: `scripts/run_parallel_native.py`(version×arm×seed, `--jobs` 세마포어, RUN_ID 격리)를 라이브 검증 — demo 2셀 각 ~24.7s 병렬·evidence 생성·격리 OK(observed). **클라우드**: GHA ubuntu-24.04 러너가 잠긴 하너스를 그대로 돈다(observed — CI `container-integration`이 매 실행 이미지 3개 빌드 + trusted 컨트롤러 + effect-demo) → `workflow_dispatch` `.github/workflows/experiment-fanout.yml`가 러너 플릿으로 캠페인 팬아웃(plan=`run_parallel_native --emit-github-matrix`로 셀 매트릭스 → fanout=셀별 독립 러너가 CI와 동일 경로로 1캠페인+evidence artifact; historical effect 이미지는 committed 레시피 `tools/node-tar/effect/Dockerfile`로 러너 빌드, 외부 publish 0). Claude 클라우드 에이전트 env는 devcontainer에 docker-in-docker 미포함 → 하너스 실행 불가(inferred, Dev Container와 동일). 격리·**클라우드 GHA fanout의 budget 상한 100(하드캡; native controller의 `MAX_NATIVE_BUDGET=2000`과 별개 — 상한 값 자체는 불변)**·trusted 컨트롤러·완화 플래그 0 모두 불변. **처리량 infra이며 effectiveness·발견 주장 아님.** host-broker는 여전히 non-build(지휘관 C+ 유지). |

### 마일스톤 (날짜 아님 — 증거가 모이면 찍는다)

- **M1 — 루프가 실제 node-tar에서 돈다.** 상태: **완료**(위 Ledger 1~6행).
- **M2 — 실제 경계위반 통제 재현 + 버전 구분 (2-CVE 차분).** 상태: **실증됨 + 박제 완료**. 재현 스크립트+raw 증거 2쌍(`experiments/repro/`)이 **동일한 generic identity oracle**(추출객체가 외부 참조파일 inode 공유)로 서로 다른 root-cause 2개를 관통한다: ① 최상위 하드링크 7.5.2 공유→7.5.3 거부 = **CVE-2026-23745**(linkpath sanitation 누락; catalog N01·R1), ② 중첩 하드링크 7.5.6 공유→7.5.7 거부 = **CVE-2026-24842**(검증 base ≠ 생성 base의 check/use mismatch, CVE-2026-23745 수정이 **도입한** 회귀; catalog N02·R2, GHSA-34x7-hfp2-rc4v). 관찰된 공유 분포는 **비단조**(중첩: 7.5.2 O·7.5.3 X·7.5.6 O·7.5.7/7.5.8 X)로 7.5.3이 고친 것을 7.5.6이 되돌렸음을 보인다. advisory 범위(24842 `<7.5.7`)와 이 특정 fixture의 observed 거동은 다를 수 있어 exact 하한은 미검증(observed/inferred 구분). 핵심: **outcome 기반 oracle 하나가 R1·R2 두 root-cause를 릴리스 id/정답경로 하드코딩 없이 모두 포착.** 재발견(자력 발견, M3)과는 구분. **M2.2(박제 완료, claude/m2-2-oracle-path-7d09f3)**: 손 probe 판정 == production Observer+Oracle 판정 일치를 additive 테스트로 고정 — CI는 run_case로 7.5.2 공유 post-state를 재현해 generic C1+C2 일치 + M2.1 증거 바인딩, native closure는 container_integration의 `run_node_tar_effect_case` 체크(호스트 docker+이미지, make check 미수집). observed(실제 node-tar=M2.1 증거) vs reproduced(통제 extractor post-state) 구분, oracle/fixture/N01 불변.
- **M3 — 퍼저가 자력으로 그 위반을 찾는다.** 초기 비교는 arm 간 어휘가 달라 폐기했고, 어휘를 맞춘 R/D/S-u 설계로 다시 실험했다. 상태: 본실험 결과 자리(봉인 해제 뒤 기입). 이전 기록은 [archive](archive/pre-20261103-results.md).
- **M4 — 일반성.** 태스크: 2번째 extractor 동일 모델 적용. 상태: **oracle+adapter 수준 일반성 3 extractor 확보**(python-tarfile·oras-go·decompress). 동일 generic C0/C1/C2 oracle(코드 불변)이 **Python stdlib tarfile**에서도 경계위반을 포착함을 통제 reference 차분으로 보임(fully_trusted=영향 → C1+C2, data=PEP 706 완화 → 거부; `tests/test_python_tarfile_generality.py` 4 passed). 이는 oracle의 target-agnostic성 증거이며 **fuzzer 자력 발견·effectiveness 주장 아님**. **oras-go·decompress adapter 구현 완료**(#176·#177): 동일 generic oracle이 python-tarfile·oras-go·decompress 3개 독립 extractor에서 adapter로 경계위반을 포착(affected/fixed 통제 reference 차분 + container-integration 체크 통과).

특정 날짜를 문서에 박제하지 않는다. 기한은 팀 일정으로 관리하고 이 문서는 능력만 추적한다.

---

### 역사적 기록 (현재 제약 아님 — provenance용)

아래부터는 **과거 특정 리비전의 기록**이다. 현재 능력은 위 Capability Ledger가 기준이고,
아래는 "왜 이렇게 됐는가"를 찾을 때만 본다. 이 절과 `docs/audits/`, `docs/research/diagnostics/`,
`docs/research/benchmarks/`의 감사·자격·task-proposal 문서는
[archive 안내](archive/README.md)가 정리한 **동결 기록**이며, 새 작업의 게이트가 아니다.
G0 capability baseline SHA `8ad07b8…`도 그 동결 리뷰가 본 리비전일 뿐 최신 main이 아니다.

특히 아래 문장들은 **Ledger/BACKLOG로 대체됐다. 문구 그대로 현재 범위·게이트로 읽지 않는다**:
"현재 다음 독립 gate는 N01 historical qualification", 11월 2일·11월 9일·11월 30일 날짜,
"이 G0 freeze는 ORAS·C3/C4·새 mutation operators·discovery를 추가하지 않는다 … 별도 Task Contract 필요".
현재 작업은 아래 '다음 연구 gate'의 수술 기준 절과 [BACKLOG](BACKLOG.md) 수술 큐를 따른다.

상태 갱신일: **2026-10-18**. G0 capability baseline은 main
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

N04의 별도 [5초 preflight Task Contract](research/benchmarks/n04-five-second-preflight-task-contract-v1.md)는
사용자가 직접 승인한 최대 8건의 benign readiness 범위였다. 2026-10-18 KST 단일 attempt는
target 실행 전 host-only Docker metadata 요청이 transport allowlist에서 거부되어
**PREFLIGHT_INCONCLUSIVE / ATTEMPT CONSUMED**로 종료됐다. target extraction과 oracle control은
각각 0건이며 5초 readiness는 **NOT_EVALUATED**이다. 원본 host ledger와 판정은
[N04 preflight result](research/diagnostics/n04-five-second-preflight-result.md)에 고정했다.
후속 transport 수정은 구현·synthetic 검증 대상일 뿐 재실행 승인이 아니다.

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
| C3/C4 / generality | 후속 contracts / RQ4 | C3/C4 없음; oras-go adapter 구현됨(#176, `targets/oras_go*.py`, Ledger M4); GNU route는 benign allowlist만 | oras-go·decompress·python-tarfile은 Ledger M4 행 참조 | C3/C4 미검증 |

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

### 수술 기준 (2026-11-03 ~ 11-30)

**수술 기간의 계획 기준은 Claude Doc 「InodeFence 독립 연구 감사 및 실험 설계 재정립」(https://claude.ai/artifact/JJtsK3VowEGuBFN3YXZDFq)이다.**
이 문서와 STATUS·BACKLOG가 다르면 문서가 맞고 STATUS는 그에 맞춰 갱신 중이다. 실험 실행 기준은 Git에
동결된 사전등록 파일(`experiments/preregistration/`), 증거 기준은 raw + SHA-256 목록
(`experiments/summaries/raw-manifest-mac-20261103.sha256`; 기준선 태그 `audit-baseline-20261103` = `bb3fd7c`)이다.
**원본 백업 상태(2026-11-03): 미완료** — 맥 raw는 체크섬 목록만 저장소에 있고 raw 자체는 호스트 로컬, 윈도우 raw
미반입, 외부/공유 저장소 백업 없음.
연구 질문·가설은 [research-questions v2](research/design/research-questions.md), 결정은 [D038](DECISIONS.md),
작업 큐는 [BACKLOG 수술 절](BACKLOG.md)을 따른다. 이 절의 이전 본문(v1/v2/v3 entry-transition 재개 조건,
N01 human correspondence, N03/N04 NOT_AUTHORIZED 서술)은 LOG·diagnostics에 남고 더 이상 다음 gate가 아니다.

### MVP 범위

- **타깃:** node-tar 7.5.2/7.5.3·7.5.6/7.5.7(취약/수정 쌍 2개) + Python tarfile `fully_trusted`/`data`.
- **자력발견(H-A) 타깃은 node-tar 하나.** decompress는 확장, oras-go는 oracle 일반성(H-B) 증거로만 쓴다.
- **범위 밖:** entry-transition 계열(v1/v2/v3·P0/P1/P2, BACKLOG M3.6 폐기, 이전 기록은 [archive](archive/pre-20261103-results.md)), GNU tar, Windows.
- **비교군(H-A):** R(무작위·uniform) / D(구조 커버리지 retention·uniform) / **S-u**(identity·effect·boundary-attempt
  retention·**uniform**) — operator 정책을 uniform으로 통제해 retention 효과만 분리한다. adaptive 스케줄러 S-a는
  탐색적 ablation(선택)이며 주 비교가 아니다.

### 실험 순서

**2026-11-14 기준:** EXP-0 등록 실행 완료(#262·#268). hazard 파일럿 실행 완료(#267). D1~D21은 D040으로 채택됐다. 동시 실행 벤치마크는 D047로 본실험 선행 조건에서 제외됐다(설계와 도구는 보존, D044). EXP-3·EXP-2 사전등록은 2026-11-13 동결됐다(F `72de299`, #332; LOG 2026-11-13). EXP-3 train과 GO/NO-GO 판정 기록(#368)을 마쳤고 EXP-2 holdout이 실행 중이다(LOG 2026-11-14).

1. **EXP-0 파일럿** — 5 seed × budget 200 × R/D/S, 인프라 측정(abort율·p95·처리량·dense 중간상태 신호).
   검정력 입력은 **dense 신호·처리량·abort율**이고, hazard proxy는 **참고값으로만 기록하며 검정력·판정 입력이 아니다**
   (사전등록 v2 (a)·(b)). 가설 검증 아님,
   formal 추정에 합산 금지. zero-hit이 기본 결과이며 hazard는 hit로 추정하지 않는다. 사전등록
   [exp0-pilot-v2](../experiments/preregistration/exp0-pilot-v2.md)(v1 대체; 엔진 SHA·이미지 digest·policy ID는
   G1 동결 시 v2.1).
   **완료(2026-11-05):** [exp0-pilot-v2.1](../experiments/preregistration/exp0-pilot-v2.1.md), seed 9001–9005 × R/D/S-u,
   budget 200, 15/15 complete, abort 0, invalid 셀 0(invalid trace 11 step은 편차 2: D 8, S-u 3, R 0), 어휘 동일 true.
   인프라 측정이며 가설 검정이 아니다. hit 0은 hazard 0이 아니다. [리포트](../experiments/summaries/exp0-20261105-report.md).
   - 1a. **hazard 파일럿** — 동결 전 탐색, 비등록, 비합산, `demo run`, 타깃 7.5.2뿐. 완료(2026-11-07): 40/40 셀, 첫 C1∨C2
     사건 R-walk 1, R-restart 4, D 4, S-u 6(arm당 10캠페인, 신뢰구간은 크게 겹치고 abort 가정에 따라 순서가 바뀐다),
     abort 11/40(인프라 사유, 첫 실패 경로 미확인). 조건 4 `R=D=0` 폐기. 규칙 C 기계 출력 "가능"(n/arm 114). 등록 통계량으로
     다시 낸 n/arm 약 76~80은 **계획 입력**이고 결과가 아니다. 확증 검정력 주장이 아니며 holdout 전이는 미검증 가정이다.
     [결과 메모](../experiments/summaries/exp3-hazard-pilot-v1-result.md).
   - 1b. **동시 실행 벤치마크** — [설계](../experiments/configs/concurrency-scaling-v1.md)(#270, §6 동결). 도구만 머지됐고, D047로 본실험 선행 조건에서 제외됐다(설계와 도구는 보존, D044).
2. **사전등록 고정** — EXP-3 본실험 + EXP-2 GO/NO-GO 규칙. 2026-11-13 동결(F `72de299`, #332): [exp3-v1](../experiments/preregistration/exp3-v1.md), [exp2-v1](../experiments/preregistration/exp2-v1.md).
3. **EXP-3 train** — 규모·지표는 [exp3-v1](../experiments/preregistration/exp3-v1.md). 실행 완료.
4. **규칙 기계 적용** — EXP-3 결과에 사전등록된 GO/NO-GO 규칙을 그대로 적용. 판정 기록 완료(#368).
5. **EXP-2 holdout** — GO일 때만. 실행 중([exp2-v1](../experiments/preregistration/exp2-v1.md)).

### 게이트

| 게이트 | 늦어도 | 조건 | 상태 |
| --- | --- | --- | --- |
| G1 구현 수리 | 11/10 (늦어도 11/13) | R/D/S × budget 50 완주, 어휘 동등 테스트(세 arm 동일 어휘), 10캠페인 smoke abort ≤ 1, 워커풀 ↔ per-case 컨테이너 parity | PASS(2026-11-04, 아래 게이트 상태) |
| EXP-0 | 11/14 | 파일럿 완료, GO/NO-GO x·n 확정 | 파일럿 완료(#262·#268). GO/NO-GO 규칙은 사전등록 동결(#332)로 고정 |
| 사전등록 고정 | 11/18 | EXP-3 + EXP-2 규칙 커밋(SHA·digest·policy ID 채움) | 완료(2026-11-13 동결, #332) |
| G2 | 11/26 | EXP-3(및 조건부 EXP-2) 완료·분석·논문 반영 | EXP-3 train·GO/NO-GO 판정 완료(#368), EXP-2 실행 중 |
| 제출 | 11/26 | 결과보고서·영상 공식 제출(지웅 확인 2026-11-14, 개최 안내의 11/30은 실제 제출일이 아님) | 대기 |

**게이트 상태(2026-11-07 기록, EXP-0 줄은 2026-11-14 갱신).**

- **G1:** 조건 1~3 PASS(2026-11-04, demo run, 비등록, R/D/S-u, budget 50: completion 3/3, smoke 12/12, abort 0, 어휘 동등 true; `~/inodefence-evidence/g1-20261104/{completion,smoke}/`). 조건 4 parity PASS(도구 검증, 비등록: R-walk, seed 9001, budget 50 3런(a1, a2, b), 4차원 일치, 재시도 0, self-determinism PASS; `~/inodefence-evidence/wp-parity-20261104/{workerpool,selfdet}/wp-parity-result.json`). 범위 한계: R-walk 1 arm, seed 1, 50 step이며 D·S-u는 미측정. 단 배선(#233, 열림, 배선 미도달)이 main에 없어 현재 main에서는 재현할 수 없고, 등록 실행은 per-case만 쓴다.
- **EXP-0:** 파일럿 완료. GO/NO-GO 규칙은 D040 재판정을 거쳐 사전등록 동결(2026-11-13, #332)로 고정됐다.

### 산출물 체크리스트 (감사 Report 2 꼭지 15 확정 조건)

감사 문서가 요구한 12개 산출물을 확인 명령 또는 파일 경로와 함께 둔다. 상태 구분: **구현**(코드·문서가 main 또는 verifier-PASS PR에 있음) / **검증**(독립 verifier가 최신 SHA에서 확인) / **실험**(사전등록된 native 실험 결과가 있음). 세 가지를 섞어 쓰지 않는다. (2026-11-07, main `b5beb48` 기준; 로컬 `make check`는 `89b4470`에서 2850 passed, 5 skipped. 검증 칸의 레인·verifier 판정은 당시 기록 그대로다)

| # | 산출물 | 확인 명령 / 경로 | 구현 | 검증 | 실험 |
| --- | --- | --- | --- | --- | --- |
| ① | 프로토타입 — `make check` 녹색 + 3-arm을 한 명령으로 돌리는 러너 | `make check`; `scripts/run_rds_cell.py`(합성)·`scripts/run_g1_smoke.py`(native, #212) | ✓ main | ✓ G1 15셀 native(레인 10 재현) | ✓ EXP-0 15셀 native(#262) |
| ② | 재현 환경 — 이미지 digest 고정 + 다른 호스트에서 같은 seed로 같은 case_id 시퀀스 1회 | `docker image inspect inodefence-node-tar-effect:7.5.2 --format '{{.Id}}'` = v2.1 `image_digest`; 타 호스트 재현 기록 없음 | ✓ digest(#238·#258) | ✓ 호스트 Id 일치(레인 4) | ✗ 타 호스트 재현 미수행 |
| ③ | 실험 실행기 — 사전등록 파일을 입력으로 매트릭스 실행 + raw+체크섬 | `python -m scripts.run_exp0 --preregistration <file> --dry-run` | ✓ main(#223·#230·#236·#244·#245) | ✓ 게이트 거부/통과 독립 재현(레인 10) | ✓ EXP-0 사전등록 입력 실행, 매니페스트 66항목(#262) |
| ④ | oracle — fixture 매트릭스 재발견률 + 위양성 상한 | `tests/container_integration/check_oracle_fn_matrix.py`(#214); FP 상한 `src/inodefence/sentinel_set.py`(#205) | ✓ main | ✓ #205/#214 PASS | 부분(FN 0/5·FP n=1200 보정값) |
| ⑤ | 비교군 — R/D/S 어휘 동등성 단위테스트 | `pytest tests/evaluation/test_rds.py tests/test_run_g1_smoke.py -k vocabulary` | ✓ main(#206·#212) | ✓ G1 셀별 equality=true | ✓ EXP-0 어휘 동일 true |
| ⑥ | 결과 — KM 곡선·표(표본·중도절단·abort 분리) | `paper/figures/render_exp0_survival.py`(#219) + `scripts/analyze_exp0.py`(#209) | ✓ main(#202 `884dc78`, #209 `a4f2a1c`, #219 `347a273`); 재생성 그림·표 #272 `e17bfc3` | ✓ 리허설 체인 결함 0(레인 6) | ◑ EXP-0 리포트(#268, 가설 검정 아님). 본실험 결과 자리(봉인 해제 뒤 기입) |
| ⑦ | 증거 — raw 압축본 + SHA-256 목록 + 재생 스크립트 | `experiments/summaries/raw-manifest-*.sha256`; `make replay`(#208); `scripts/make_evidence_bundle.py`(#215) | ✓ main(#208, #215 `5b82624`, #251 `1a00828`) | ✓ #251 verifier PASS(2026-11-06 재판정, PR 코멘트; 282항목 `raw-manifest-win-20261104-2317.sha256`); 141은 레인 8 `--verify` + 번들 round-trip 218/218 | 부분(Mac 1,614 raw 미이관). EXP-0 66항목, hazard 파일럿 123항목(비등록) |
| ⑧ | 통계 — 스크립트 하나가 모든 표·그림을 raw에서 생성 | `make paper-artifacts --verify`(#232·#256) | ◑ main(#232 `4d6f4c0`, #256 `01a913d`; M2 표 BYTE-MATCH, 그림 size-only, ledger exists-only) | ✓ #256 PASS (2026-11-06 재판정, PR 코멘트, head 7dfd21f) | — |
| ⑨ | 한계·실패 — abort 사유 표, 음성 결과 전부 | `scripts/analyze_abort_rollup.py`(#210·#227); `paper/sections/06-results.md` §5.4 | ✓ main(#210 `d07d547`, #227 `c21e22f`) | ✓ PASS | ✓ EXP-0 abort 0/15(budget 200). hazard 파일럿 abort 11/40(비등록, 첫 실패 경로 미확인) |
| ⑩ | 문서 — STATUS 1페이지 현황 | 이 파일 | ✗ 미축소(수술 종료 후) | — | — |
| ⑪ | 논문 — 영문 6–8쪽 + AI 도구 사용 절 | `paper/sections/05-method.md` §4.7(#216) | ◑ 초안 main(#216 `36b251d`, #225 `0ba50c0`, #247 `9bc8600`, #253 `86c617d`), §5.6 EXP-0 수치(#269), EXP-3·EXP-2 결과 자리(봉인 해제 뒤 기입) | ◑ verifier 판정은 각 PR 코멘트 기준(2026-11-06 재판정: #216 · #225 · #253 · #247) | 대기 |
| ⑫ | 유지보수자용 회귀 명령 | `make regression TAR_VERSION=7.5.2` (#218) | ✓ main(#218 `d7ab2a6`, 2026-11-05 머지) | ✓ #218 PASS | ✓ 고정 fixture native(M2.1) |

꼭지 1~15 전체의 구현/검증/실험 대조는 LOG 2026-11-05(레인 9 대조표)와 BACKLOG 수술 보강 큐(S-08·S-11·S-UV·S-15)에 둔다.

### 문서 모순 (감사 확인 12건)

| # | 문서 주장 | 코드·증거 | 상태 |
| --- | --- | --- | --- |
| 1 | README·`src/inodefence/README.md`·STATUS Ledger(C3/C4 행)·architecture.md "ORAS adapter 없음" | `targets/oras_go*.py` 존재, Ledger M4 구현 완료(#176) | 완료(PR #221): README·`src/inodefence/README.md`·architecture.md 정정(oras-go adapter 구현 #176, Ledger M4; adapter 수준 일반성) |
| 2 | Makefile·smoke 스크립트·experiment-fanout.yml "budget 상한 100" | `scripts/run_effect_demo.py` `MAX_NATIVE_BUDGET=2000` | 완료(PR #221): STATUS fanout 행 문장 정정(GHA fanout 하드캡 100 ≠ native MAX_NATIVE_BUDGET 2000 명시; 상한 값 불변) |
| 4 | `src/inodefence/README.md` "native producer NOT_QUALIFIED라 캠페인에 안 씀" | `make demo`가 native producer로 돈다 | 완료(PR #221): `src/inodefence/README.md` 정정(M1 native effect producer가 make demo로 실행) |
| 6 | STATUS "다음 연구 gate" entry-transition 재개 조건 | BACKLOG M3.6 폐기, 이전 기록은 [archive](archive/pre-20261103-results.md)(honest negative) | 이 PR에서 해소(이 절 교체) |
| 11 | `src/inodefence/README.md` "Node campaign CLI 없음" | `container_host` 컨트롤러 모드로 실행됨 | 완료(PR #221): README 정정(실제 캠페인은 container_host 컨트롤러 모드) |
| 12 | `evaluation/n04_preflight.py` L68–76 호스트 절대경로 하드코딩 | 이식 불가 | 5단계 |

## 변경 범위와 문서 우선순위

현재 범위는 Linux TAR/USTAR, C0/C1/C2, fresh extract와 controlled sentinels다.
이 G0 freeze는 ORAS, C3/C4, PAX/GNU encoding, 새 mutation operators 또는 discovery를 추가하지 않는다.
새 기능이나 methodology 변경에는 별도 Task Contract와 영향 문서 검토가 필요하다.
이 G0 문단은 v2(D038)로 대체된 역사 기록이다. 현재 비교 설계는 R/D/S-u다.

현재 상태는 이 문서, G0 정의는 [Research Contract](research/design/research-contract-v1.md),
C0/C1/C2 의미는 [Security Contracts](research/design/security-contracts.md), 비교/측정 정의는
[연구 질문](research/design/research-questions.md)과 [프로토콜](research/benchmarks/evaluation-protocol-v1.md)을
따른다. Historical audit/summary는 자체 날짜와 SHA의 기록으로만 읽는다.

## Phase 2 조사 기록

- **P2-a C1 일반화 영향 조사 (2026-10-23, `jiwoong/p2-a-c1-impact`) — 판정: 안전(additive).**
  C1을 "extraction object ↔ 지정 sentinel" 대신 "extraction object ↔ EXTERNAL object 전체"와
  비교하도록 일반화하는 변경안을 **임시 패치(미커밋, 되돌림)**로 Dev Container에서 실행해 영향만 확인했다.
  기존 C0/C1/C2 판정·oracle fixture 4/4·N01 경로·전체 pytest가 모두 불변이고(전체 1722 passed,
  1 failed는 C1과 무관한 기존 container-backend 환경 실패), extraction↔비-sentinel EXTERNAL identity
  공유 탐지만 **추가**된다. `archive/input.tar`(HARNESS)는 일반화 후에도 C1이 되지 않으며(의도),
  HARNESS까지 포함하는 확장은 `IdentityEvidence`의 EXTERNAL 제약 때문에 additive가 아니다(별도 모델
  변경 필요, P2-b 범위). 코드 판정은 바꾸지 않았다(소스 변경 0). 상세는 [LOG](LOG.md)와
  [BACKLOG](BACKLOG.md) P2-a.

아래는 2026-10-18 기준 상세 기록이다.

상태 갱신일: **2026-10-18**. G0 capability baseline은 main
**`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`**다. 이 SHA는 G0 문서 동결이
검토한 구현 revision이며 최신 main을 뜻하지 않는다. #77–#84 연구 stack은 main에
통합됐다. Internal completion qualification v3의 clean harness revision은 `9ea306f7`이고,
causal filesystem-effect qualification v4의 clean harness revision은 `72bccfa`다.

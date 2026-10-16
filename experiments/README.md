# 실험 설정과 raw 결과

## 이 폴더는 무엇인가

재현 가능한 설정과 가공 전 evidence를 보관하고, 검증된 요약을 findings/paper에 연결한다.
G0 capability baseline은 main **`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`**다.
[Research Contract](../docs/research/design/research-contract-v1.md)의
DESIGNED / IMPLEMENTED / TESTED / EXPERIMENTALLY VALIDATED를 구분한다.

## 입력과 출력

입력은 explicit seed/config, exact target/version/artifact, 실행 전 source/runtime/isolation/
sentinel provenance다. 출력은 immutable config, raw canonical records, checksum manifest와
검증된 별도 summary다. **Historical qualification, rediscovery와 formal comparison은 NOT_RUN이며
현재 취약점을 주장하지 않는다.** Engineering summaries와 synthetic statistics tests는 결과가 아니다.

## 현재 구현과 evidence 범위

- `run_campaign`과 strict JSON ExperimentConfig v1/v2는 legacy B3/mutation 경로다.
  Manifest v4 writer와 [verified reader](../src/inodefence/evaluation/README.md)가 있다.
- `run_search_campaign` / `SearchCampaignConfig`는 B0/B1/B3 × FULL/A1/A2 × legacy/M1/A3를 실행한다.
  별도 `PolicyEvaluationConfig`가 initial IDs, full provenance, profiles와 protocol를 completed
  result에 binding한다. [Policy export/reader](../src/inodefence/evaluation/policy_evidence.py),
  [summary](../src/inodefence/evaluation/policy_summary.py),
  [dataset](../src/inodefence/evaluation/policy_dataset.py),
  [statistics](../src/inodefence/evaluation/policy_statistics.py)가 구현/테스트됐다.
- Generic failure ledger, passive legacy journal/controller, final-state policy journal/repetition,
  pair records, qualification/matrix와 allowlisted benign replay가 있다.
  [Evaluation](../src/inodefence/evaluation/README.md) 및
  [replay](../src/inodefence/replay/README.md)는 각 API의 소유권과 한계를 설명한다.
- Completed-only reader는 checksums, case/TAR identity, raw derivations, config/provenance와
  declared-policy admission/eligible-parent consistency를 검증한다. 별도 journal reader는
  actual RNG parent/operator/mutation을 replay한다. 어느 쪽도 assessor assertion의 truth,
  authorship, known-class rediscovery 또는 paper readiness를 증명하지 않는다.
- Full results/readers는 O(budget) memory다. Final-state policy runner의 completed-record callback,
  journal과 versioned timing evidence는 cleanup/feedback/동기 record publication까지의 monotonic
  offsets와 accessible aborted prefix를 보존한다. Policy repetition schedule은 claimed slot을
  complete/failed/STARTED로 보존하고 자동 retry하지 않는다. Final bulk publication timing,
  timed dataset pooling과 known-class adjudication은 통합 완료되지 않았다. Target duration은
  complete-step latency가 아니며 completed-only policy stats는 invalid attempts를 추론하지 않는다.
- Pinned node-tar의 public/OS/syscall/prefix, private completion callback, causal filesystem-
  effect와 별도 libarchive entry-boundary qualification은 모두 current archive-ordered
  transition producer에 **QUALIFIED FAIL**했다. Exact marker/operation association도 native
  P0/P1/P2 결과가 아니며 현재 v1 gate는 **BLOCKED_NATIVE_OBSERVATION**이다.

ExecutionProvenance v2는 실행 전 source/environment/adapter/sentinel과 nullable isolation을 고정한다.
IsolationProvenance internal v2는 실제 image probe의 verified worker/lock digest와 origin을 기록한다.
Legacy manifest v4는 stored configuration, actual execution contexts와 exporter environment를 분리한다.
Policy evidence는 별도 versioned schemas며 legacy manifest에 묵시적으로 넣지 않는다.
Config identity 자체는 결과나 OS isolation의 증거가 아니다. Dirty source SHA는 patch를 보존하지 않는다.

## 보존 규칙

설정은 configs/, raw는 ignored raw/ 또는 results/에 두되 **immutable shared storage URI와
checksums를 별도로 기록**한다. Raw output은 수동 수정하지 않고 versioned analysis derivative를 만든다.
실행 전에 engine SHA, target pin/locks/image, OS/kernel/runtime/architecture/filesystem, exact command/options,
config, initial corpus, seed, all-status execution budget/timeout, oracle/feedback/mutation IDs, schedule/protocol,
start/end timestamps와 raw path를 기록한다. 실패·timeout·negative result·qualification failure를 삭제하지 않는다.
Missing/incomplete/infrastructure-invalid evidence는 no-hit으로 분류하지 않는다.

[Summaries 규칙](summaries/README.md)에 따라 raw → verified summary → finding/measurement →
analysis script → figure/table → paper claim을 추적한다. Formal dataset/figure reproduction은 아직 검증되지 않았다.
민감한 candidate는 [SECURITY](../SECURITY.md)를 따르며 ignored path는 access control을 대체하지 않는다.

## 역사적 engineering 기록과 benchmark 계획

[Reference 개발 pilot](summaries/reference-campaign-pilot-v1.md),
[infrastructure](summaries/infrastructure-readiness-v1.md),
[pre-audit](summaries/pre-audit-readiness-v1.md)와
[benign Node smoke](summaries/benign-node-container-smoke-v1.md)는 각각 기록된 revision/config/checksum의
engineering evidence다. Current main capability나 vulnerability rediscovery의 근거로 수치를 재사용하지 않는다.
Baseline main의 canonical/container checks와 **node-tar 7.5.22 benign smoke PASS**는
[STATUS](../docs/STATUS.md)의 pinned CI evidence를 따른다.

[Static catalog](benchmarks/README.md)는 source-derived planning metadata다.
**N01 node-tar 7.5.2 / 7.5.3**가 첫 intended historical qualification이며 아직 READY가 아니다.
All 15 executions remain NOT_RUN. Actual qualification/matrix evidence는 별도 evaluation API가 처리하며
static catalog selection/source facts를 실행 결과로 자동 승격하지 않는다.

N01 pair contract의 human authorization은 2026-10-15에 기록됐고, 별도 historical
admission/readiness/pair/independent-reader 구현은 engineering test를 가진다. 현재 checkout
환경에는 trusted-host Docker CLI가 없어 historical image build·8 benign·10 pair는
계속 **NOT_RUN**이다. Controlled-adapter test 8+10을 historical evidence로 승격하지
않는다. 실제 evidence는 `scripts.container_host ... qualify-node-n01`의 새 runtime-volume
경로에서만 게시하고, fresh-process reader와 human correspondence review를 거쳐야 한다.
[Protocol](../docs/research/benchmarks/evaluation-protocol-v1.md)의 B0/B1/B3, A1/A2/A3 budgets/subsets는
pilot 후 experiment freeze 이전까지 provisional이다. Path-only/fixed-recipe baseline은 없다.

## Completed export publication

Legacy manifest v4는 closed/flushed/fsynced staging, checksum/read-back 후 Linux
`renameat2(RENAME_NOREPLACE)`로 공개한다. 기존/동시 destination을 덮어쓰지 않는다.
Before-publication error는 final absent/staging cleanup이며 parent directories는 남을 수 있다.
Hard interruption은 staging을 남길 수 있고 post-publication parent-fsync error는 complete bundle을
남긴 채 전달한다. 이것은 atomic publication이며 resume/database/crash-proof storage가 아니다.
Separate evaluation records/policy binding markers도 partial publication을 검증된 complete evidence로
승격하지 않는다. [Storage/evidence API](../src/inodefence/evaluation/README.md)를 따른다.

Historical manifest schemas 1/2/3, signature v2와 legacy config IDs는 현재 schema 지원과 구분한다.
State keys는 tagged v3이고 old key migration/attestation을 제공하지 않는다.

# 역사적 기록 (archive)

여기 적힌 문서들은 **과거 특정 리비전의 감사·자격·제안 기록**이다. 당시의 검증 수치와 근거를
보존하려고 남겨두지만, **현재 작업의 게이트도 제약도 아니다.** 현재 능력의 단일 기준은
[STATUS의 Capability Ledger](../STATUS.md)이고, 할 일은 [BACKLOG](../BACKLOG.md)의 마일스톤이다.

이 문서들을 읽을 때:

- "NOT_RUN / BLOCKED / NOT_QUALIFIED / AWAITING_…" 같은 상태는 **그 리비전 시점의 말**이다.
  지금 상태로 읽지 않는다(예: 2026-10-24 기준 M1 완료, M2 실증됨 — Ledger 참조).
- `8ad07b8…` 등 고정 SHA는 그 동결이 본 리비전일 뿐 최신 main이 아니다.
- 새 감사/계획 문서를 만들어 늘리지 않는다(AGENTS 금지). 새 사실은 Ledger 갱신 또는 LOG 한 줄로.

## 동결로 간주하는 기록

아직 파일은 원래 위치에 있다(가드 R1이 `audit`/`qualification` 경로의 이동을 사람 작업으로 두기 때문).
물리적으로 `docs/archive/` 아래로 옮기는 것은 사람이 `git mv`로 한다. 그 전까지 아래 목록이
"동결로 간주하는 집합"의 기준이다.

### `docs/audits/`
- `final-engine-research-audit-v1.md`, `final-runtime-integration-audit-v1.md`,
  `engine-findings-fix-v1.md`, `final_engine_reproductions_v1.py`

### `docs/research/diagnostics/`
- N01/N02/N03/N04 자율 실행·자격·독립 감사 기록 전부
  (`n01-*`, `n02-autonomous-integration-and-qualification.md`, `n03-*`, `n04-*`,
  `node-tar-replacement-report.md`)

### `docs/research/benchmarks/` 중 감사·자격·제안 계열
- `engine-contract-audit.md`, `effect-coverage-engine-audit.md`, `post-audit-backlog.md`,
  `artifact-qualification-v1.md`, `candidate-matrix.md`,
  `n01-candidate-machine-match-v1.md`, `n01-pair-qualification-contract-v1.md`,
  `n03-b0-b1-b3-pilot-task-proposal.md`, `n04-five-second-preflight-task-contract-v1.md`,
  `n04-namespace-rebinding-sequence-v3-task-contract.md`,
  `effect-replacement-qualification-task-proposal.md`

## 계속 살아있는 참고 문서 (archive 아님)

방법론·정의는 M3 이후에도 쓰므로 그대로 둔다:
[benchmark-set](../research/benchmarks/benchmark-set-v1.md)(단, G1~G8 admission gate 절은
역사적 틀이고 현재는 Ledger로 대체),
[baseline-and-ablation](../research/benchmarks/baseline-and-ablation-v1.md)(정책 ID),
[evaluation-protocol](../research/benchmarks/evaluation-protocol-v1.md)(지표·censoring),
[taxonomy-and-reachability](../research/benchmarks/taxonomy-and-reachability.md),
[catalog](../../experiments/benchmarks/README.md)(소스 pin).
설계 문서([architecture](../research/design/architecture.md),
[security-contracts](../research/design/security-contracts.md),
[research-questions](../research/design/research-questions.md),
[project-scope](../research/design/project-scope.md))와 [DECISIONS](../DECISIONS.md)도 살아있다.

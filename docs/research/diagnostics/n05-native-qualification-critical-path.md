# N05 final-state readiness, native-v3 feasibility and research critical path

Date: **2026-10-18**. Review baseline: origin/main
`8d29982c26cebfcce7a413b3ba9177fcd28078de` after merged PRs #107, #109, #110 and
#111. This is an evidence-grounded engineering assessment and prospective plan, not human
scientific approval or experiment authorization.

No historical extractor, qualification matrix, pilot or fuzzing campaign was run. The consumed
N04 attempt was not retried. PRs #92, #106 and #108 and the primary checkout's existing
`.devcontainer/devcontainer.json` modification were not changed.

## Evidence and claim levels

Observed facts below come from repository source, retained checksummed evidence, exact upstream
package bytes or executed engineering tests. Derived decisions apply the existing contracts.
Proposed native mechanisms and future outcomes remain hypotheses. Nothing in this report is
paper-ready effectiveness evidence.

## Track 1 — final-state preflight readiness

### Retained attempt reconstruction

The retained N04 host ledger at
`/Users/choijiwng/Projects/InodeFence-n04-5s-preflight-20261016T130000Z-host-ledger`
still contains exactly three read-only files:

| File | Recomputed SHA-256 |
| --- | --- |
| `started.json` | `1dab6f33e22d80ab5a525d4f8f87eb88539a555a5f061a49d7c015f851633074` |
| `terminal.json` | `39a3e8e2e7e85be9bcc756b8f5c5dfcb690f7dd3385ff8c425c21907f5dc18fc` |
| `manifest.json` | `a59901f3938c105717f437faf05853f3f5698b65e6e57b955fd2a34d713136b0` |

The current reader reconstructed `PREFLIGHT_INCONCLUSIVE`, null Linux raw/final manifest
digests, zero target names, `cleanup_status=not_needed`, no deadline expiry and the exact
`BackendError: invalid trusted Docker command request`. There was no Linux evidence root, target
extraction or oracle control. These are observed facts; they do not say anything about five-second
target readiness.

### Transport correction and bounded regression evidence

Main separates `docker info` and the exact volume-consumer listing into
`DockerCLI.run_host_inspection()`. `StdioDockerClient` exposes no corresponding method, and the
ordinary controller-visible command validator still rejects both forms. A real fake-executable
test now exercises the host method rather than testing only a mock. The host allowlist rejects
partial forms and path-like volume-filter injection.

Draft PR #112 at `0eca90f44a249d3ab1e66966b7ab3cfe80f79055` additionally closes the
unretained controller-stderr gap. Its versioned ledger extension drains the exact byte stream,
retains at most the first 1 MiB, records truncation, binds the bytes through terminal and manifest
digests and rejects tampering. The consumed v1 ledger remains readable under its strict original
schema and digest. Focused Linux tests cover the trust split, exact allowlists, early-failure
publication, stderr bound/truncation/tamper, one-attempt destinations, consumed source gates and
cleanup downgrade.

This is engineering evidence only. No broker request reached a historical target.

### Final-state readiness decision

**STOP — implementation is not ready for a separately authorized preflight.** PR #112 removes
the two verified transport/evidence defects, but deliberately supplies no new attempt ID, mode,
constants, evidence destinations or authorization gate. The only executable preflight mode remains
source-gated as consumed. There is consequently no exact clean runnable source SHA for a new
attempt, and no new controller image bound to such a source.

The proposed [N05 preflight contract](../benchmarks/n05-five-second-preflight-task-contract-draft.md)
freezes a new attempt ID, paths, target identities, five-second timeout, containment, controls and
fail-closed rules, while recording the missing runnable source identity as an admission blocker.
The smallest next engineering action is an independently reviewed N05 mode/reader wiring change
against that contract. The next target execution still requires a separate human authorization.

## Track 2 — native-v3 feasibility

### Current producer and generic model

The current native v2 producer (`_node_effect_producer.cjs`, SHA-256
`6c9a05a8420e800281e2e8662c17b176648fef13dc2182332ce063bb117aa5f4`)
associates Node callback operations with exact entries, records globally sequenced operation
start/completion, and captures stable object evidence before and after the callback. Its reader
constructs only single-operation v2 effects and evidence-supported operation/context/handle edges.
It does not emit a cross-operation unlink-to-create branch edge.

The merged generic v3 model requires two realized v2 events plus a separately producer-issued
`producer_branch_continuation` dependency. Its strict reader is externally digest-bound after PR
#111's forgery repair. It rejects absent dependencies, endpoint mismatch, incomplete/rejected
traces, destination-binding interleaving and raw/manifest tamper. This is IMPLEMENTED / SYNTHETIC
TESTED, not native evidence.

### Exact native source branch

The downloaded official node-tar 7.5.22 tarball rehashed to SHA-256
`b792c2d1c7fc770910522ca1ffc29eee02ee38de4fa3a01e7832eb705879c6c6`; its
SHA-512 equals the committed lock integrity. The exact CommonJS `unpack.js` SHA-256 is
`03515ed98f5df6ec0f23177b7016274f8cdc91b038d0dcd036f438a70e614eed`.

For this source only, `CHECKFS2` lines 609–679 lstat the destination. A present non-directory
that is not reusable takes line 678: `unlinkFile(..., er => this[MAKEFS](...))`. `MAKEFS` lines
688–706 dispatch the same entry to FILE, HARDLINK, SYMLINK or DIRECTORY. LINK lines 708–718
call `fs.link`/`fs.symlink`; FILE lines 439–517 construct fs-minipass `WriteStream`, whose exact
4.0.1 CommonJS `_open()` at lines 273–275 calls `fs.open`. This is a real callback continuation,
not an inference from archive order.

The viable instrumentation point is the existing v2 wrapper at producer lines 369–371: it emits
the predecessor completion before invoking the target callback. A dedicated continuation context
can wrap only that original callback; the first eligible same-entry/same-path binding operation
can consume and emit the producer record. If the context is missing, mismatched or already
consumed, no dependency exists. The reader must not create one.

### Independent corroboration and perturbation risk

Native qualification must independently recompute v2 endpoints, require explicit PRESENT→ABSENT
and ABSENT→PRESENT observations, compare exact destination strings/entry identities, verify the raw
producer edge, and reject any globally observed intervening destination binding. A separate
qualification-only syscall trace may corroborate unlink/create return order but cannot supply the
dependency. Final snapshots corroborate the final binding only, never transient absence.

Instrumentation may change execution. The current full v2 profile already performs synchronous
lstat/content probes at callback boundaries. A new `AsyncLocalStorage.run`, branch-record emission
and larger bounded frame add synchronous callback work and allocation; those can change event-loop
scheduling or filesystem interleaving even without an explicit wait. Prior node-tar qualifications
already observed profile-specific scheduling changes, so source inspection and final-state equality
alone are insufficient. The proposed native contract therefore compares unchanged v2-full and
v3-full lifecycle/operation-order histograms and fails qualification on any difference.

### Native-v3 decision

**STOP before native qualification.** The exact source branch is feasible to observe and the
generic consumer is strict, but no native dependency producer, raw protocol, immutable image or
contained qualification runner exists. No token may be synthesized from the retained v2 matrix.
The [native-v3 Task Contract draft](../benchmarks/n05-native-rebinding-v3-qualification-task-contract-draft.md)
defines positive/negative fixtures, 600 proposed target slots, tamper controls, corroboration,
neutrality checks and exact fail criteria. A separately frozen implementation and authorization are
required before the first native target run.

## Track 3 — research critical-path matrix

The dates below use 2026-10-18 as the review date: 15 days to the November 2 presentation,
22 days to the November 9 experiment freeze and 43 days to the November 30 final artifact.

| RQ | Current verified evidence | Missing evidence | Smallest required next experiment | Required approval | Pass / fail / stop | November risk |
| --- | --- | --- | --- | --- | --- | --- |
| RQ1 known vulnerability rediscovery | Exact N01 7.5.2/7.5.3 same-input automated replay: affected persistent C1 plus metadata-only C2 5/5; fixed strict rejection and no C1/C2 5/5. Independent readers agree. This is a positive control/correspondence record, not search rediscovery. Candidate replay/matcher are synthetic-tested. | Human correspondence disposition; five-second admission; any search-generated candidate; historical candidate 3+3 replay and human root-cause adjudication. | First the 8-extraction N05 benign preflight (readiness only). If PASS and separately authorized, the already proposed 20-cell/4,000-step pilot is the smallest existing plan that can produce a search-origin N01 candidate; only then run the predeclared 3+3 candidate replay. | Human N01 correspondence; reviewed N05 source/contract and one-attempt preflight authorization; then separate pilot and replay/adjudication approvals. | PASS requires a mutation-origin candidate with complete generic C1 evidence, affected 3/3 and fixed 0/3 under exact setup, plus human class correspondence. No hit is censored pilot evidence, not safety. Any identity/containment/evidence failure stops as invalid. | **High for Nov 2; critical for Nov 9.** No search run exists and the readiness mode is not runnable. |
| RQ2 B0/B1/B3 effectiveness | B0/B1/B3 semantics, protected-component reachability, journal/timing/repetition/controller-memory and readers pass engineering tests. Effectiveness remains NOT_RUN. | Qualified timeout/setup, authorized repeated target runs, known-class adjudication, invalid/STARTED denominators and any paired effect estimate. | Proposed pilot: affected B0/B1/B3 plus fixed B3, 5 seeds × 200 seed-inclusive steps = 20 cells / 4,000 executions. It is feasibility evidence, not the formal 1,000-step × 20-seed design. | Same final-state gates as RQ1 plus explicit pilot schedule/source/output/resource authorization. | GO to formal freeze only if all 20 cells are accounted for, independent readers agree, controls stay clean and no trust/cleanup drift occurs. Any missing slot is invalid, never dropped. Pilot success cannot itself establish superiority. | **Critical for Nov 9.** Even a prompt preflight leaves little time to review pilot evidence and freeze formal cells. |
| RQ3 A1/A2/A3 ablations | Frozen A1/A2 feedback projections and A3 no-reorder policy are implemented and synthetic/reference tested. No ablation target run exists. | Qualified benchmark subsets, paired B3 data, verified key nonredundancy in native runs, repeated outcomes and effect estimates. | After RQ2 feasibility, the smallest predeclared targeted arm is A2 versus reused B3 on N04: 20 seeds × 1,000 = 20,000 added executions. A1 and A3 each require their predeclared 40,000 added executions. No smaller post-outcome subset should be invented. | Main-experiment freeze approving candidate readiness, exact subsets, budgets, schedule and analysis plan. | PASS is a complete paired dataset with common full-state metrics and retained redundancy diagnostics. Stop on unqualified candidate/setup, seed-phase contract hit, missing denominator or projection drift. Null results remain valid. | **Critical.** N04 and the prerequisite B3 dataset are not qualified; RQ3 is unlikely to support a November 9 frozen result without scope triage by the research owner. |
| RQ6 P0/P1/P2 transition effectiveness | Generic v1 and v2 P0/P1/P2 machinery/readers are synthetic-tested. Native v1 is blocked; native v2 retained `NOT_QUALIFIED`; generic rebinding v3 is synthetic-tested only. No native P0/P1/P2 campaign ran. | Native producer qualification, observation/policy version binding, native closed-loop pilot, repeated P1−P0 and P2−P1 outcomes. | The 600-slot native-v3 qualification proposal is the smallest execution-dependent gate now specified. It is qualification, not effectiveness. A later bounded P0/P1/P2 pilot needs a new versioned contract; existing identifiers cannot be relabeled for v3. | Human design approval, exact producer/image contract and native qualification authorization; after QUALIFIED, separate policy/methodology freeze and campaign authorization. | Qualification PASS requires producer-issued dependency, explicit endpoints, negative controls, unchanged v2 keys/final semantics and no scheduling-histogram change. Any manufactured/inferred edge or perturbation is NOT_QUALIFIED. Effectiveness remains NOT_RUN even after qualification. | **Critical / likely STOP for November effectiveness.** A defensible negative feasibility result is nearer than a valid P0/P1/P2 estimate. |

## Critical sequence and recommendations

```text
merge/review PR #112
  -> implement and review exact N05 preflight mode (no targets)
  -> separate one-attempt N05 authorization
  -> 8 benign readiness extractions
  -> if PASS: separate 4,000-step final-state pilot authorization
  -> candidate replay/human adjudication
  -> formal RQ1/RQ2 freeze

native-v3 producer implementation and synthetic/contained checks
  -> separate 600-slot qualification authorization
  -> if QUALIFIED: new policy-version contract
  -> only then any RQ6 pilot
```

Final-state and native-v3 work are independent until they compete for review/runtime resources.
Do not block the final-state pilot on native-v3, and do not use final-state positive-control evidence
to qualify a transition producer.

Recommendations:

- **Track 1: STOP now; conditional GO after exact N05 mode/source review and new authorization.**
  PR #112 removes verified code defects but is not a runnable attempt.
- **Track 2: STOP.** Implement the producer under the proposed contract, then seek qualification
  authorization; do not run from the v2 image or infer dependencies from old records.
- **RQ1/RQ2: conditional GO is still scientifically useful, but schedule risk is critical.** Prioritize
  the eight-run readiness gate and retain a no-hit/invalid pilot honestly.
- **RQ3: STOP pending qualified subsets and reusable B3 data.** Do not shrink subsets after seeing
  results.
- **RQ6: STOP for effectiveness.** Treat native-v3 qualification itself as the next defensible result.

## Actual validation and failures

| Revision / environment | Command | Result |
| --- | --- | --- |
| main `8d29982` / macOS Python 3.12 | `python3.12 -m pytest ...` | Initial invocation failed before collection: `pytest` unavailable. |
| main `8d29982` / macOS Python 3.12 isolated venv | focused 143-test suite | 94 passed; 12 failed and 37 errored because Linux-only publication/container gates correctly reject Darwin. Not used as regression evidence. |
| main `8d29982` / Ubuntu 24.04 arm64 non-root validation container | focused preflight/transport/v3 suite | **143 passed**. No target image/socket mounted. |
| PR #112 `0eca90f` / same Linux container | focused suite after bounded stderr change | **146 passed**. |
| PR #112 `0eca90f` / first `make check` setup | host macOS Ruff entered container | Failed before lint completion with Mach-O `Exec format error`; replaced by Linux-only venv. |
| PR #112 `0eca90f` / Linux-only venv, network disabled | `make check` | Ruff/format/Pyright and **1,587 pytest passed**, environment PASS; docs check alone failed because the worktree's external Git metadata was not mounted. |
| PR #112 `0eca90f` / same container with read-only Git metadata mount | `make check` | **PASS**: Ruff, 357-file format, Pyright 0 errors, 1,587 pytest, environment, 128-document check. |
| Retained N04 ledger / current reader | `verify_n04_host_ledger(..., expected_manifest_sha256="a599...36b0")` | Reconstructed `PREFLIGHT_INCONCLUSIVE`; null Linux digests. |
| Official source packages | `npm pack` plus SHA-256/SHA-512 rehash | node-tar 7.5.22 and fs-minipass 4.0.1 bytes matched committed lock integrities; source was inspected only, not executed as a target. |

The validation containers used the source bind only for code, a separate tmpfs at
`/var/lib/inodefence`, non-root UID/GID and no target Docker socket. The final validation had
network disabled. No historical archive or extractor was invoked.

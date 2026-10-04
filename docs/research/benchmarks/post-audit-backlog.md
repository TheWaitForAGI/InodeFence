# Research handoff and post-audit implementation backlog

**Planning only; benchmark execution NOT_RUN. Engineering validation is recorded separately.**
Task Contracts: original maintainer-supplied parallel research preparation and the
current Phase-4B Final Engine / Security Contracts / Research Semantics re-audit/refresh specification.
Owned lane: landscape, taxonomy, selection, observability/reachability,
evaluation, catalog and handoff. No production path changed, no PoC executed,
no exploit archive generated, no target installed or vulnerable fuzzing run.

## Current integrated context and history-preserving refresh

Audited integrated main: `d1982e4cf3174e28d4eeb73af7b32829f6751b30` (2026-10-04).
Existing Draft [PR #35](https://github.com/TheWaitForAGI/InodeFence/pull/35), branch
`research/benchmark-evaluation-prep-v1`, was refreshed from actual remote head
`5b3745e40e5d43c3b79fa9fe7ca1872f1d2e1106` by merging exact main, preserving all
published history. The earlier #39 review at `efe1dbb…` remains historical evidence
in the [engine audit](engine-contract-audit.md), with explicit superseding statuses.

Pre-audit freeze, Phase-1 audits, Phase-2 cross-review/Global Findings Freeze v1 and
Phase-3 Runtime #45 / Engine #46 fixes are completed. Verified artifact observation,
actual invocation checks, Docker CLI descendant lifecycle, lossless-or-reject USTAR,
public evidence validation, exact StateChange labels, tagged v3 signatures and
EX-004 fsync regression strengthening already exist. Do not reimplement them.
EC-01/EC-02 are RESOLVED by #45; EC-03 remains RESOLVED by #42.

The [Phase-4B final audit #47](https://github.com/TheWaitForAGI/InodeFence/pull/47)
completed before this refresh and found no new Blocker/Major/Minor. Functional
EN-001–EN-004 are CLOSED. Audited main still has residual EN-005 current navigation
drift, so unconditional global closeout remains NO-GO pending disposition. This
unmerged Draft proposes EN-005/006 current-state corrections. It does not change
that main verdict or assert completion of the Runtime/global final audit.

[Artifact research](artifact-qualification-v1.md) retains its static source/pin
qualification, uncertainty and NOT_RUN history. All 15 execution fields remain
NOT_RUN; no benchmark is READY. Engineering CI is not candidate qualification.
P01–P11 remain future Task Contracts after accepted global Phase-4 closeout.
At later meaningful main changes, re-audit affected assumptions and refresh the
catalog engine_revision; never infer execution authorization from a completion signal.

## Engine gap report

These are source-backed research-readiness gaps, not discovered production bugs.
Do not independently patch hot files. The primary engineer and audit own
isolation correctness and architectural changes.

| Priority / necessity | Gap and motivating evidence | Minimum resolution after audit |
| --- | --- | --- |
| BLOCKING / remaining closeout gate | Phase-3 fixes and benign full path exist; audited-main EN-005/current planning disposition and global Phase-4 acceptance remain pending | Review documentation corrections and Runtime/Engine global final dispositions; no duplicate implementation |
| BLOCKING / required for selected sentinel benchmarks | Mutation output language cannot spell controlled outside/default sentinel components; N01/N03/N04 not fully reachable | M1 finite generic component dictionary/recombination, explicit target-visible path mapping/config; same policy for every arm; logical reachability evidence |
| BLOCKING / required for ORAS primary | O01 requires external process CWD and public file.Store unpack path; no ORAS adapter/config today | Offline public API wrapper, deterministic title-prefix/gzip transport, pinned modules/compiler, explicit controlled CWD; setup before BEFORE; never private helper bypass |
| BLOCKING / required for formal comparison | Config permits only full feedback; B0/B1 and projections do not exist | Small explicit search-policy binding after audit, versioned policy identifiers, identical execution plumbing and validation |
| IMPORTANT / required for time metric | Per-execution duration excludes setup/observation; no full-step monotonic timestamp in current export | Record elapsed pipeline/evidence-completion offsets, retain execution duration separately; never label sum of target durations wall-clock time-to-hit |
| IMPORTANT / required for failed-run interpretability | Infrastructure exception aborts without CampaignResult; exporter only completed runs | Exception-safe ledger/incremental evidence at future orchestration/export layer, preserve last complete step and failure reason; do not fabricate results |
| IMPORTANT / required for qualification | Official package/module identity now verified statically; benchmark locks/images/worker pins, runtime compatibility and actual namespace mapping still pending | Pin artifacts; benign checks and later separately authorized class qualification, matched runtime/options and namespace mapping |
| IMPORTANT / required for replay/statistics | No current raw reader/replay/aggregation tool, raw input exists only as serialized evidence | Separate research tooling rebuilding case/TAR and verifying hashes, replay lifecycle, per-seed/invalid/censor summaries with raw traceability |
| OPTIONAL | N03 bounded discoverability may remain weak after M1 | M2 generic chain proposals only with measured pilot evidence; no recipe-specific scheduler |
| OPTIONAL | Broader GNU cases need existing-state/root flexibility | Defer until G01 source pair/root mapping or G02 CLI conditions qualify; no generalized setup engine solely for excluded G03 |

C0/C1/C2 already cover selected persistent aliases and effects with controlled
setup. Observer captures persistent state and raises on incomplete evidence.
Multiple sentinels already work via tuple SentinelSpec/protected_paths; additional
multi-sentinel API is **not needed**. Name/subpath setup supports ordinary external
sentinels; an external CWD is a target invocation setting, not permission to
plant attack symlinks inside extraction. Selected primary cases require no
pre-existing internal filesystem objects, no new entry types, no PAX/GNU
encoding, no mode mutation, no attack-specific initial case and no C3/C4 or
operation tracing. Benchmark-specific *environment* profiles are needed;
benchmark-specific attack seeds are not.

## Recommended target order after audit

1. **Node-tar primary pairs**: existing adapter reduces integration cost, patch
   commits and exact releases are identified, and three distinct classes cover
   identity, composition and external write. Start with N01 sanitation, then
   N04 cache transition and N03 composed links. Qualification must not assume
   the locked benign tar 7.5.22 is a vulnerable target or that strict mode always
   preserves advisory behavior.
2. **ORAS Go O01**: direct C1 effect, documented Linux context, identified
   c463c654 fix and 2.6.2 release. Public offline Store wrapper and CWD settings
   cost more than Node version swapping but add independent implementation
   value. Use oras-go module pins rather than conflate ORAS CLI versions with
   library versions; defer title-only O03 and unconfirmed O02 fix.
3. **GNU tar, optional**: adds native CLI diversity, but G01 exact upstream pair
   and boundary, G02 selected-member invocation, G03 documented-use dispute
   prevent a clean primary today. Investigate G01 first for state relevance;
   consider G02 if a simple controlled pair qualifies. No GNU adapter work is
   justified merely by historical preference or CVE title.

This retains the historical family order for explicit evidence-backed reasons.
It does not redefine D009 or change existing target APIs. If Node/ORAS cannot
qualify, document RQ4 as unevaluated instead of claiming diversity from an
unqualified GNU run.

## Ordered implementation tickets after audit fixes

**P00 — completed engineering prerequisites, remaining global closeout:** retain
existing backend/Node composition, prepared lifecycle, verified artifact/invocation
checks, frozen policy/provenance, config v2 and exact-wrapper admission. Benign
configured smoke/pre-audit freeze, Phase-1/2 audits and Phase-3 fixes are complete.
EN-001–EN-004 functional re-audit passes; this Draft proposes residual EN-005/006
documentation correction. Await accepted Runtime/global Phase-4 verdict before
P01–P11. No P00 production implementation remains in this research package.

Each row is a proposed separate Task Contract/Issue, not implementation in this
PR. Scope estimates are relative: S = focused helper/config addition; M = one
module boundary plus integration/documentation checks. They are not deadlines.
Affected modules are ownership handoff suggestions; audit may choose placement.

| Order / purpose | Motivating benchmark | Affected area / scope | Dependency | Acceptance criterion |
| --- | --- | --- | --- | --- |
| P01 Freeze benchmark environment/pins | All primaries | Target tooling, configs, provenance; S–M | Accepted global Phase-4 closeout | Candidate-specific exact artifacts/locks/build/runtime profile and target-visible uid/device/path mapping; benign compatibility for both releases; reuse #45/#46 binding/attestation rather than reimplement; separate execution contract |
| P02 Make protected objects generically addressable | N01/N03/N04, O01 generic setup | Mutator/config docs; M | P01 frozen path vocabulary | Explicit CVE-independent dictionary and component operations; logical constructive reachability for selected structures from benign seeds; no target/oracle dependency or implicit remapping |
| P03 Bind comparison search policies | All feedback comparisons | Feedback/corpus caller, ExperimentConfig, campaign boundary; M | Audit API freeze, P02 | B0/B1/B3 semantics and StateSignature v3-based A1/A2 keys match plan; config rejects unknown IDs; constants/budgets identical; current v3 state OR violation B3 unchanged on controlled results |
| P04 Add complete timing/failure evidence | All formal metrics | Campaign/provenance/export or research wrapper; M | Audit decisions about lifecycle/export | Monotonic full-step offsets, invalid-attempt ledger and export checksums; failures/partial evidence cannot be called no-hit; controlled exception regression |
| P05 Add hash-verified replay/adjudication tools | All primary pairs | Research scripts / summaries, existing builder/model reader; M | P01–P04 | Exact case IDs and TAR hashes reconstruct; separate vulnerable/fixed fresh replay records; per-input 3/3 vs 0/3 classifications; no CVE oracle conditions |
| P06 Qualify Node benchmark pairs | N01, N04, N03 | Target configs/tooling and experiments; M | P01–P05 and explicit benchmark execution contract | Evidence of Linux compatibility, stable mapping, known-class effect and fixed comparison; seed-phase clean; no PoC attack input becomes search seed; failed qualification retained |
| P07 Implement/qualify offline ORAS adapter | O01 | targets/ plus pinned Go tooling/config; M | P01–P05, isolated invocation contract | Public Store path with fixed title/unpack annotation, deterministic gzip/title-prefix mapping and input hashes, external controlled CWD, no network; same-device sentinel, safe benign adapter checks, qualified 2.6.0/2.6.2 pair |
| P08 Freeze protocol/dataset and run pilot | Admitted primaries | Experiment configs/raw, analysis tools; S–M | P06/P07 qualification | All 5 pilot seeds/settings stored; measured latency/volume/memory justify formal budget; any amendment written before formal runs |
| P09 Execute formal baseline blocks | RQ1/RQ2, qualified primaries | experiments/, no new generic semantics; M | P08 plus explicit execution approval/contract | 20 scheduled seeds each, B3 pair and B0/B1 vulnerable; all failures/censors/raw retained; counts/provenance/checksums validated |
| P10 Targeted ablations and validated summaries | N03/O01/N04, RQ3 | Feedback-only projections/config and analysis; S–M | P03, P09, pinned projection policy | A1/A2 and optionally A3 match declared subset/budgets; no evidence removal; empty tables filled only from independently validated raw dataset |
| P11 Investigate GNU admission, optional | G01 then G02 | Source research and later targets/ config; M | Primary set qualified; schedule permits | Exact upstream/patch pair and invocation/root mapping resolved before adapter or formal run; no silent replacement of rejected cases |

P01–P05 are the remaining initial work after accepted global Phase-4 closeout. Node/ORAS qualification
precedes effectiveness claims; policy/timing helpers may be reviewed before any
vulnerable target is executed. No uncontrolled CVE archive is required to
validate these helper implementations.

## Ticket evidence, tests and research-contract impact

The gap report and engine audit provide source evidence; this table attaches
specific taxonomy scope and tests to the ordered acceptance criteria above.
Every P01–P11 item requires a **new Task Contract**. Execution items additionally
need explicit authorization covering the qualified target, setup and evidence.
No item changes C0/C1/C2 verdict definitions; a later need to change those requires
separate security-contract review and canonical-document updates.

| Ticket | Gap evidence / affected IDs | Smallest implementation and concrete module boundary | Required tests before acceptance | Research-contract change? |
| --- | --- | --- | --- | --- |
| P01 | Generic verified image/worker/lock origin already exists (#45); candidate locks/images/mapping and runtime qualification absent; N01/N03/N04/O01, S09/S12/S14 | Freeze candidate artifacts and environment profile in tooling/config and execution provenance; reuse verified P00 binding, actual invocation and export | Pin drift rejected; benign versions compatible; root/device/uid mapping recorded; no mutable version/tag fallback | YES reproducibility/setup profile; no oracle change |
| P02 | Affix-only operators cannot spell outside/sentinel; N01/N03/N04/O01, S02/S05/S07/S10/S11/S13/S14 | Finite dictionary plus component replacement/splicing in mutator/operators.py and explicit config; retain eight operator slots unless policy revision says otherwise | Pure logical constructive reachability, raw order/duplicates/immutable input, deterministic RNG, byte-limit counted no-op, no target-specific imports | YES grammar/dictionary/versioned mutation policy |
| P03 | Config/Corpus supports B3 only; all primaries, S01–S14 feedback | Small policy binding at campaign/feedback/config; no duplicate runner | Synthetic outcomes prove B0 independent of novelty, B1 state-only admission, B3 unchanged, bootstrap/seen indexes and uniform selection; projection-only A1/A2 and A3 RNG/no-op checks | YES search policy/config; preserve raw signature/oracle |
| P04 | ExecutionResult excludes full pipeline time; exceptions lose completed campaign export; all primaries | Monotonic orchestration offsets plus append-only completed-step/failure ledger in campaign/export or research wrapper; existing EX-004 fsync regressions are not that ledger | Controlled clock/exception/export/cleanup failures; last complete step retained; no-hit and infrastructure abort distinct; checksums verify | YES evidence/timing interface; no verdict change |
| P05 | Export has no reader/replay; all primaries, S01–S14 | Research reader rebuilds ArchiveCase/TAR with builder and verifies canonical IDs/hashes; separate adjudication records | Benign round-trip, bytes/order preserved, tamper/hash mismatch rejection, deterministic nomination deduplication, mocked 3/3 versus 0/3 classification | NO security contract; YES analysis/reproduction schema |
| P06 | No selected Node pair qualified; N01/N04/N03, R1/R4/R3, S03/S04/S06/S13/S14 | Pinned Node benchmark profiles and reviewed qualification records, using P00/P01–P05 | Benign fixture smoke first; later authorized Linux effect/fixed comparator qualification; strict-mode failure blocks admission; no attack seeds | NO oracle change; YES benchmark ground truth/admission |
| P07 | ORAS adapter absent; backend CWD fixed to extract; O01/R2, S03/S10/S12/S14 | Offline public file.Store adapter under targets/, exact Go sums/compiler, deterministic transport and explicit isolated CWD within controlled run; add invocation binding only as required | Benign public API/annotation integration; pin/network/CWD rejection; same-device observation lifecycle; later authorized pair qualification | YES target invocation/provenance/setup, no oracle change |
| P08 | Formal cost unmeasured; admitted primaries | Freeze schedule/config/artifact/protocol hashes and separate pilot orchestration | All planned cells accounted for; pilot separated from formal data; feasibility thresholds/amendment recorded before formal run | YES freeze experiment protocol; no engine verdict change |
| P09 | No effectiveness dataset; admitted primaries/RQ1/RQ2 | Execute declared blocks with existing qualified policies and immutable raw storage | Validate every scheduled repetition, all outcomes/failures, censored indices, paired blocks and raw checksums | NO implementation contract; instantiate frozen protocol |
| P10 | No ablation/summary data; N03/O01/N04, S06/S11/S14 | Configured feedback projections and research aggregation with traceable raw refs | Analysis fixtures include zero hits, censoring, invalid and pending cases; common full-state counts unaffected; no success-only statistics | YES declared projection/dataset revision if newly introduced |
| P11 | GNU pair/invocation/root UNKNOWN; G01/G02, R7/R1, S07/S09/S12/S14 | Source/pin/invocation admission research first; adapter only after gates pass | Static source/pin checks; later benign boundary tests; failed gate remains failed with no silent substitution | YES only if later set/invocation/boundary scope admitted |

P01/P02 depend on accepted global closeout; P03/P04 may proceed independently
once audit APIs and P02 vocabulary are frozen. P05 consumes their evidence
interfaces. P06/P07 qualify targets before P08; P09/P10 follow protocol freeze.
Optional M2/M3 remain deferred: smallest additions are a generic relationship
proposal or literal-backslash dictionary respectively, each with its own policy
revision, logical tests and Task Contract. No generalized pre-existing-tree,
PAX/GNU parser, C3/C4, race or attack-generator work is required for primary v1.

## Full-audit benchmark handoff

| Kind | Audit input / required confirmation |
| --- | --- |
| Engine assumptions | Enforced exact-wrapper execution, immutable actual image/policy, trusted broker separation, no exposed source/home/socket/neighbor runs; no fallback; stable pre-execution configuration. Retain verified artifact/invocation fixes; EC-01/02 and EC-03 are resolved. Review final residual documentation/global dispositions. |
| Benchmark-critical contracts | Same device/inode between target and controller; setup before BEFORE; complete target/descendant termination before AFTER; removal after AFTER; observer/cleanup failure invalidates the result; C0 includes HARNESS, C1 uses dev+ino, C2 compares protected pre/post state; execution/isolation metadata stays outside novelty while signature filesystem fields retain their documented meaning. |
| Missing implementation after audit | M1 finite address vocabulary; B0/B1 and truthful policy decisions; full timing/failure ledger; hash-verified reader/replay/adjudication; selected-version locks/images/profiles; ORAS public wrapper/transport/CWD. |
| Research-only assumptions | Node 22.22.0 static engine compatibility is not runtime qualification; N01 relative arm correspondence, N03 Linux behavior, N04 strict/cache behavior and O01 offline effect remain predictions. Budget throughput/storage cost is unmeasured. |
| Unresolved source/version facts | G01 exact CVE repair/backport association, affected range/released fixed pair/root mapping UNKNOWN. ORAS upstream advisory is narrower than current ecosystem range; selected exact pair supported, older range untested. |
| Explicit deferrals | All vulnerable builds/executions, qualification campaigns, M1/policy/timing/replay implementations, ORAS/GNU adapters, attack inputs, minimization, C3/C4/races, baselines/ablation/formal evaluation. New Task Contracts follow accepted global Phase-4 closeout. |

Research preparation is reviewable planning; keep PR OPEN/DRAFT and auto-merge disabled.
This refresh addresses current package/navigation drift after the completed engine
re-audit. It does not grant global GO, merge approval or benchmark execution.
Review final dispositions, then create new contracts for only the remaining gaps.

## Historical #39 review and validation record

PR-review checked Task Contract/scope, architecture, tests and documentation.
Security-contract review checked lifecycle attribution, raw evidence versus
normalized novelty and C0/C1/C2; C3/C4 remain deferred. Experiment-validation
checked identity, repeatability gates, raw retention, paired comparisons,
failures and claim limits. Static source facts are not experimental findings.

On the merged efe1dbb engine, `PYTHONPATH=src make check` passed Ruff/format,
Pyright (zero errors/warnings), 585 pytest tests, Linux runtime environment and
docs-check. PYTHONPATH selects this worktree instead of the older editable
installation. Catalog validation and targeted negative metadata checks passed;
document links/diff/LF/scope were checked. Exact checkpoint results are reported
in PR #35; local session journal is uncommitted outside the repository.
Real container suites were source-reviewed, not locally rerun by this lane.
Inherited CI/engineering evidence is scoped separately and is not qualification.

**EVALUATION NOT_RUN.** Qualification, pilot, rediscovery, same-input replay,
baselines, ablation and formal benchmark execution remain NOT_RUN. No affected
version was executed, vulnerable image built or exploit archive constructed.

## Phase-4 refresh validation and delivery

History-preserving merge: `3300ad240238790612baddfdc8580803ea9e0b2d`, with parents
`5b3745e40e5d43c3b79fa9fe7ca1872f1d2e1106` (actual PR #35 remote head) and
`d1982e4cf3174e28d4eeb73af7b32829f6751b30` (audited integrated main).
Both ancestry checks passed. No rebase, force push or competing research PR is used.

Refresh changes current planning/navigation and catalog engine_revision only.
Production source, tests, CI, runnable configs and fixture bytes match integrated
main; original static catalog/schema/validator remain planning-only. The historical
engine review and source qualification/NOT_RUN record are retained separately from
current capabilities. All 15 catalog records are unchanged except top-level
engine_revision; every execution remains NOT_RUN and no candidate is READY.

Full validation in the existing clean research worktree, supported Linux Dev
Container / Python 3.12.3 / runtime `/var/lib/inodefence`:

- `PYTHONPATH=src make check`: PASS, Ruff/format, Pyright 0 errors/warnings,
  **803 pytest tests in 25.85s**, filesystem/environment check and **74 Markdown docs**.
  PYTHONPATH selects this worktree rather than the root editable installation.
- Static catalog: PASS, **15 planning records**; **14 negative metadata/state cases
  rejected**; assertions verify original source/pin/qualification fields unchanged.
- `git diff --check`, source/test/CI/config/fixture equality, LF and ancestry: PASS.
- Exact-main [canonical CI 37197933974](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37197933974):
  check and real container-integration PASS. This refresh lane reads that evidence;
  it does not claim a local Docker rerun or historical candidate qualification.

Keep existing PR #35 OPEN/DRAFT/unmerged with auto-merge disabled. Current-package
EN-006 drift is corrected in the submitted Draft, while final acceptance and main
documentation/global closeout remain pending. **Benchmark execution NOT_RUN**;
no P01–P11 implementation, vulnerable install/image/campaign or rediscovery claim.

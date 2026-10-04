# Research handoff and post-audit implementation backlog

**Planning complete; engineering/benchmark execution not performed.**
Task Contract: maintainer's directly supplied parallel research specification.
Owned lane: landscape, taxonomy, selection, observability/reachability,
evaluation, catalog and handoff. No production path changed, no PoC executed,
no exploit archive generated, no target installed or vulnerable fuzzing run.

## Final repository context and moving-main audit

Audited main: `f02024cc520868056c26919b128d18628012e8f2` (2026-10-04), a
targeted delta review from full capability-audit base a22d201. The branch contains
the previously merged `a22d20127d8e01bc539363764582ef907d51cbf1`; f02024c was
inspected through Git snapshots without merging, as required by the follow-up
Task Contract. No new research or production changes belong to this follow-up.
Research branch: `research/benchmark-evaluation-prep-v1`; Draft
[PR #35](https://github.com/TheWaitForAGI/InodeFence/pull/35), base main.
Main was merged into this branch without rewriting published history, preserving
all existing research work. Branch HEAD is available from Git/PR metadata; it is
not embedded in its own tracked contents.

[PR #36](https://github.com/TheWaitForAGI/InodeFence/pull/36) is now merged and
adds a disposable Linux container backend, helper regressions and a separate CI
container-integration job. The [engine audit](engine-contract-audit.md) supersedes
the older no-backend assumptions. Helper validation is implemented platform
engineering evidence, and PR #37 adds a pinned benign Node image with
metadata-only container checks. PR #38/f02024c implements Node invocation/backend
composition and prepared pipeline lifecycle, with eight benign real-container
fixture checks in passing main CI. Frozen isolation/config/provenance and
configured campaign admission remain NOT_IMPLEMENTED; the completed low-level
binding must be reused rather than rebuilt. The run volume is mounted at the same
random absolute controller path; no stable alias or arbitrary CWD setting is promised.

[STATUS at f02024c](https://github.com/TheWaitForAGI/InodeFence/blob/f02024cc520868056c26919b128d18628012e8f2/docs/STATUS.md)
remains ENGINEERING FOUNDATION; Node configured
campaigns have zero executions, and benchmark/evaluation readiness remain false.
Primary engineering owns remaining configured integration, benign campaign smoke
and the pre-audit freeze. Full audit and required fixes precede the proposed tickets.
This capability audit does not assert that the full architecture audit occurred.

At coherent milestones fetch origin, compare the last audited main to origin/main,
merge relevant changes at a clean point and re-audit affected execution, binding,
config, provenance, campaign, observation, oracle, feedback/export and readiness
claims. Refresh catalog engine_revision with the audit. Any later main change
invalidates only the affected assumptions, not retained external source evidence.
No completion signal grants this lane benchmark execution authorization.

## Engine gap report

These are source-backed research-readiness gaps, not discovered production bugs.
Do not independently patch hot files. The primary engineer and audit own
isolation correctness and architectural changes.

| Priority / necessity | Gap and motivating evidence | Minimum resolution after audit |
| --- | --- | --- |
| BLOCKING / required prerequisite | Campaign rejects all isolation-required targets despite the implemented backend and low-level Node binding; frozen campaign binding is absent | Reuse prepared Node execution, freeze image/config/provenance and campaign admission, benign configured Node validation, full audit and fixes |
| BLOCKING / required for selected sentinel benchmarks | Mutation output language cannot spell controlled outside/default sentinel components; N01/N03/N04 not fully reachable | M1 finite generic component dictionary/recombination, explicit target-visible path mapping/config; same policy for every arm; logical reachability evidence |
| BLOCKING / required for ORAS primary | O01 requires external process CWD and public file.Store unpack path; no ORAS adapter/config today | Offline public API wrapper, pinned modules, explicit CWD under observed sandbox, setup before BEFORE; never private helper bypass |
| BLOCKING / required for formal comparison | Config permits only full feedback; B0/B1 and projections do not exist | Small explicit search-policy binding after audit, versioned policy identifiers, identical execution plumbing and validation |
| IMPORTANT / required for time metric | Per-execution duration excludes setup/observation; no full-step monotonic timestamp in current export | Record elapsed pipeline/evidence-completion offsets, retain execution duration separately; never label sum of target durations wall-clock time-to-hit |
| IMPORTANT / required for failed-run interpretability | Infrastructure exception aborts without CampaignResult; exporter only completed runs | Exception-safe ledger/incremental evidence at future orchestration/export layer, preserve last complete step and failure reason; do not fabricate results |
| IMPORTANT / required for qualification | Exact package hashes, locked old-version compatibility, container inode/device views and actual per-run addresses not established by research | Pin artifacts; benign checks and later separately authorized class qualification, matched runtime/options and namespace mapping |
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

**P00 — primary lane prerequisite, before the tickets below:** reuse the
implemented Node/backend binding and prepared BEFORE/AFTER lifecycle; freeze
isolation/config/provenance/export identity and connect campaign admission,
retaining fail-closed ISOLATION_REQUIRED enforcement,
validate an explicitly benign configured full path, publish pre-audit freeze,
finish the full audit and fixes. Relevant boundaries are
[execution](../../../src/inodefence/execution/README.md),
[pipeline.py](../../../src/inodefence/pipeline.py),
[campaign.py](../../../src/inodefence/campaign.py),
[config](../../../src/inodefence/experiment_config.py) and provenance/export.
The [f02024c composition](https://github.com/TheWaitForAGI/InodeFence/blob/f02024cc520868056c26919b128d18628012e8f2/src/inodefence/targets/isolated.py)
and [prepared pipeline](https://github.com/TheWaitForAGI/InodeFence/blob/f02024cc520868056c26919b128d18628012e8f2/src/inodefence/pipeline.py)
already provide the low-level lifecycle; adding a second runner is unnecessary.
Tests must reject missing runtime/image, policy drift, unsafe binding and failed
cleanup before reporting success, preserve shared sentinel identity and prove
all target children stop before AFTER. Update stale adapter/safety documentation.
Acceptance: approved immutable binding plus benign raw smoke evidence, full-audit
record and resolved required findings. Impacts every primary/S class; changes
execution/config/provenance contracts, not C0/C1/C2. Requires its own primary-lane
Task Contract; no P00 implementation belongs to this research PR.

Each row is a proposed separate Task Contract/Issue, not implementation in this
PR. Scope estimates are relative: S = focused helper/config addition; M = one
module boundary plus integration/documentation checks. They are not deadlines.
Affected modules are ownership handoff suggestions; audit may choose placement.

| Order / purpose | Motivating benchmark | Affected area / scope | Dependency | Acceptance criterion |
| --- | --- | --- | --- | --- |
| P01 Freeze benchmark environment/pins | All primaries | Target tooling, configs, provenance; S–M | Isolation, benign Node campaign, full audit and audit fixes | Exact digest/lock/target-visible paths and uid/device semantics recorded; benign compatibility for both releases; no benchmark execution before separate authorization |
| P02 Make protected objects generically addressable | N01/N03/N04, O01 generic setup | Mutator/config docs; M | P01 frozen path vocabulary | Explicit CVE-independent dictionary and component operations; logical constructive reachability for selected structures from benign seeds; no target/oracle dependency or implicit remapping |
| P03 Bind comparison search policies | All feedback comparisons | Feedback/corpus caller, ExperimentConfig, campaign boundary; M | Audit API freeze, P02 | B0/B1/B3 semantics and A1/A2 keys match plan; config rejects unknown IDs; constants/budgets identical; current B3 unchanged on controlled results |
| P04 Add complete timing/failure evidence | All formal metrics | Campaign/provenance/export or research wrapper; M | Audit decisions about lifecycle/export | Monotonic full-step offsets, invalid-attempt ledger and export checksums; failures/partial evidence cannot be called no-hit; controlled exception regression |
| P05 Add hash-verified replay/adjudication tools | All primary pairs | Research scripts / summaries, existing builder/model reader; M | P01–P04 | Exact case IDs and TAR hashes reconstruct; separate vulnerable/fixed fresh replay records; per-input 3/3 vs 0/3 classifications; no CVE oracle conditions |
| P06 Qualify Node benchmark pairs | N01, N04, N03 | Target configs/tooling and experiments; M | P01–P05 and explicit benchmark execution contract | Evidence of Linux compatibility, stable mapping, known-class effect and fixed comparison; seed-phase clean; no PoC attack input becomes search seed; failed qualification retained |
| P07 Implement/qualify offline ORAS adapter | O01 | targets/ plus pinned Go tooling/config; M | P01–P05, isolated invocation contract | Public Store path with fixed title/unpack annotation, external controlled CWD, no network; same-device sentinel, safe benign adapter checks, qualified 2.6.0/2.6.2 pair |
| P08 Freeze protocol/dataset and run pilot | Admitted primaries | Experiment configs/raw, analysis tools; S–M | P06/P07 qualification | All 5 pilot seeds/settings stored; measured latency/volume/memory justify formal budget; any amendment written before formal runs |
| P09 Execute formal baseline blocks | RQ1/RQ2, qualified primaries | experiments/, no new generic semantics; M | P08 plus explicit execution approval/contract | 20 scheduled seeds each, B3 pair and B0/B1 vulnerable; all failures/censors/raw retained; counts/provenance/checksums validated |
| P10 Targeted ablations and validated summaries | N03/O01/N04, RQ3 | Feedback-only projections/config and analysis; S–M | P03, P09, pinned projection policy | A1/A2 and optionally A3 match declared subset/budgets; no evidence removal; empty tables filled only from independently validated raw dataset |
| P11 Investigate GNU admission, optional | G01 then G02 | Source research and later targets/ config; M | Primary set qualified; schedule permits | Exact upstream/patch pair and invocation/root mapping resolved before adapter or formal run; no silent replacement of rejected cases |

P01–P05 are the exact initial work after audit fixes. Node/ORAS qualification
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
| P01 | Provenance lacks image/locks/mapping; N01/N03/N04/O01, S09/S12/S14 | Freeze candidate artifacts and environment profile in tooling/config and execution provenance; reuse P00 binding | Pin drift rejected; benign versions compatible; root/device/uid mapping recorded; no mutable version/tag fallback | YES reproducibility/setup profile; no oracle change |
| P02 | Affix-only operators cannot spell outside/sentinel; N01/N03/N04/O01, S02/S05/S07/S10/S11/S13/S14 | Finite dictionary plus component replacement/splicing in mutator/operators.py and explicit config; retain eight operator slots unless policy revision says otherwise | Pure logical constructive reachability, raw order/duplicates/immutable input, deterministic RNG, byte-limit counted no-op, no target-specific imports | YES grammar/dictionary/versioned mutation policy |
| P03 | Config/Corpus supports B3 only; all primaries, S01–S14 feedback | Small policy binding at campaign/feedback/config; no duplicate runner | Synthetic outcomes prove B0 independent of novelty, B1 state-only admission, B3 unchanged, bootstrap/seen indexes and uniform selection; projection-only A1/A2 and A3 RNG/no-op checks | YES search policy/config; preserve raw signature/oracle |
| P04 | ExecutionResult excludes full pipeline time; exceptions lose completed campaign export; all primaries | Monotonic orchestration offsets plus append-only completed-step/failure ledger in campaign/export or research wrapper | Controlled clock/exception/export/cleanup failures; last complete step retained; no-hit and infrastructure abort distinct; checksums verify | YES evidence/timing interface; no verdict change |
| P05 | Export has no reader/replay; all primaries, S01–S14 | Research reader rebuilds ArchiveCase/TAR with builder and verifies canonical IDs/hashes; separate adjudication records | Benign round-trip, bytes/order preserved, tamper/hash mismatch rejection, deterministic nomination deduplication, mocked 3/3 versus 0/3 classification | NO security contract; YES analysis/reproduction schema |
| P06 | No selected Node pair qualified; N01/N04/N03, R1/R4/R3, S03/S04/S06/S13/S14 | Pinned Node benchmark profiles and reviewed qualification records, using P00/P01–P05 | Benign fixture smoke first; later authorized Linux effect/fixed comparator qualification; strict-mode failure blocks admission; no attack seeds | NO oracle change; YES benchmark ground truth/admission |
| P07 | ORAS adapter absent; backend CWD fixed to extract; O01/R2, S03/S10/S12/S14 | Offline public file.Store adapter under targets/, exact Go sums, explicit isolated CWD within controlled run; add invocation binding only as required | Benign public API/annotation integration; pin/network/CWD rejection; same-device observation lifecycle; later authorized pair qualification | YES target invocation/provenance/setup, no oracle change |
| P08 | Formal cost unmeasured; admitted primaries | Freeze schedule/config/artifact/protocol hashes and separate pilot orchestration | All planned cells accounted for; pilot separated from formal data; feasibility thresholds/amendment recorded before formal run | YES freeze experiment protocol; no engine verdict change |
| P09 | No effectiveness dataset; admitted primaries/RQ1/RQ2 | Execute declared blocks with existing qualified policies and immutable raw storage | Validate every scheduled repetition, all outcomes/failures, censored indices, paired blocks and raw checksums | NO implementation contract; instantiate frozen protocol |
| P10 | No ablation/summary data; N03/O01/N04, S06/S11/S14 | Configured feedback projections and research aggregation with traceable raw refs | Analysis fixtures include zero hits, censoring, invalid and pending cases; common full-state counts unaffected; no success-only statistics | YES declared projection/dataset revision if newly introduced |
| P11 | GNU pair/invocation/root UNKNOWN; G01/G02, R7/R1, S07/S09/S12/S14 | Source/pin/invocation admission research first; adapter only after gates pass | Static source/pin checks; later benign boundary tests; failed gate remains failed with no silent substitution | YES only if later set/invocation/boundary scope admitted |

P01/P02 depend on P00 freeze and audit fixes; P03/P04 may proceed independently
once audit APIs and P02 vocabulary are frozen. P05 consumes their evidence
interfaces. P06/P07 qualify targets before P08; P09/P10 follow protocol freeze.
Optional M2/M3 remain deferred: smallest additions are a generic relationship
proposal or literal-backslash dictionary respectively, each with its own policy
revision, logical tests and Task Contract. No generalized pre-existing-tree,
PAX/GNU parser, C3/C4, race or attack-generator work is required for primary v1.

## Review and validation record

Contract mappings were checked against the canonical security-contract document
and actual oracle, normalization and lifecycle code. Experiment-validation was
applied to the planning design: benign seeds, generic verdicts, equal budgets,
repetition, censoring, replay and raw-evidence gates. Scope review checks that
research metadata stays separate from production changes and exploit material.
Capability gaps are not asserted vulnerability findings.

Original package validation on the research branch's a22d201 engine base: **make check PASS**,
Ruff and format PASS, Pyright zero errors/warnings, **532 pytest tests passed**, Linux runtime
environment PASS and docs-check PASS (70 Markdown files). A supplemental local
path/anchor check passed all 70 documents and 16 local anchor references. Catalog
validation passed 15 planning records; 12 negative checks rejected duplicate IDs/
keys, missing/unknown fields, unsupported contracts/enums/taxonomy, missing primary
pins and fabricated readiness/execution/binding. `git diff --check` passed.
The original package diff against a22d201 contains research/navigation documents
and static metadata validation only; no production source, tests, tooling or CI changes.

The f02024c follow-up checks only that commit's changed assumptions. It updates
the engine audit, this handoff, candidate execution wording and catalog revision/
state explanation. Model/generation, observer/oracle, feedback, config/campaign
and provenance/export source are unchanged. The local branch retains the older
engine, so its checks do not reproduce f02024c's new Node/backend tests.
[Main CI at f02024c](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37180369305)
passed `check` and `container-integration`, including the explicit benign Node
target suite. This is inherited engineering evidence, not a research execution.
Follow-up validation re-ran **make check PASS (532 tests)**, catalog validation
(15 unchanged candidate records), docs-check and all 16 local anchors across 70
documents. All eight immutable f02024c source-link paths exist in the reviewed
snapshot. Scope/LF and diff checks passed: only five affected planning files;
all candidate metadata other than engine_revision and every NOT_RUN state are
unchanged.

Canonical tests use existing locked benign Node tooling; no new target version
was installed. Local container integration was not executed by this lane: it
requires the approved host broker/runtime. Current-head CI is authoritative in
[PR checks](https://github.com/TheWaitForAGI/InodeFence/pull/35/checks), with both
`check` and `container-integration` accounted for. Static validation is not
benchmark evidence; helper/image/fixture CI success is not Node configured
campaign readiness.

**EVALUATION NOT RUN.** Benchmark qualification, pilot, known-class rediscovery,
identical-input validation replay, baseline comparisons, ablations and formal
benchmark execution are all NOT_RUN. The primary Node configured smoke also
remains NOT_RUN at the audited main. Existing reference/fixture/helper engineering
records remain separately scoped historical evidence.

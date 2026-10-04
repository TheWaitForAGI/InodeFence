# Research handoff and post-audit implementation backlog

**Planning complete; engineering/benchmark execution not performed.**
Task Contract: maintainer's directly supplied parallel research specification.
Owned lane: landscape, taxonomy, selection, observability/reachability,
evaluation, catalog and handoff. No production path changed, no PoC executed,
no exploit archive generated, no target installed or vulnerable fuzzing run.

## Final repository context and moving-main audit

Final refresh reference: `433ffb0f49f82476b1c3d152e647a5c9a9710485`.
Research branch: `research/benchmark-evaluation-prep-v1`; Draft
[PR #35](https://github.com/TheWaitForAGI/InodeFence/pull/35), base main.
Independent worktree: `/tmp/inodefence-research`; shared main remains at
`/workspaces/InodeFence`. Branch SHA is Git/PR head, not embedded in its own
tracked contents (which would be self-referential).

At landscape, protocol and final checkpoints origin/main remained unchanged.
No merged architecture drift to merge. Primary-engineer
[PR #36](https://github.com/TheWaitForAGI/InodeFence/pull/36) is open for a
disposable Linux container backend; its body reports benign shared-volume
identity/lifecycle validation, while campaign/config/provenance integration and
Node full-path readiness remain later work. This is an unmerged implementation,
not an updated main contract or an independently reproduced boundary result.
Its execution README was inspected: one named-volume run subdirectory is mounted
at its identical random absolute controller path; the run is writable, rootfs
read-only, and preparation/cleanup bracket BEFORE/AFTER. No stable mount alias
is promised. The plan prefers relative protected-name addressing, preserves
HARNESS C0 scope and does not ask this lane to alter that backend.
Final source/status check still says
ENGINEERING FOUNDATION, no validated third-party campaign isolation, and Node
campaign count zero. No primary pre-audit completion signal observed; leave PR
Draft and unmerged. When that signal arrives, fetch, inspect significant changes,
merge latest origin/main at a clean milestone, reconcile these assumptions, run
checks and refresh this record before human review. That future refresh is not
benchmark execution authorization.

## Engine gap report

These are source-backed research-readiness gaps, not discovered production bugs.
Do not independently patch hot files. The primary engineer and audit own
isolation correctness and architectural changes.

| Priority / necessity | Gap and motivating evidence | Minimum resolution after audit |
| --- | --- | --- |
| BLOCKING / required prerequisite | Current campaign rejects all isolation-required targets; infrastructure owner is working on container execution | Approved implemented boundary, benign Node full-path validation, full audit and fixes; research branch supplies no competing backend |
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

## Review and validation record

Security-contract-review applied to the mapping: C0 namespace versus content
separation, C1 lstat/ref identity, C2 metadata, HARNESS independence and snapshot
limits checked. Experiment-validation applied to the design: benign seeds,
version-independent verdicts, equal budgets, repetition, censoring, replay and
raw evidence gates checked. PR-review applied to Task Contract, changed-file
scope, sources/version uncertainty, architecture boundaries and claim limits.
No code/audit finding is asserted merely from a research capability gap.

Local final validation: catalog syntax/schema/IDs/contracts PASS (15 records);
negative metadata checks reject duplicate ID/key, missing field, unknown contract,
bad enum, unknown field and missing primary pin; git diff --check and docs-check
PASS (69 Markdown files). Canonical make check PASS: Ruff, format, Pyright,
**474 pytest tests**, Linux runtime environment and docs. The first make check
failed 13 existing Node tests because this independent worktree lacked ignored
node_modules; it passed after a temporary link to already installed main tooling
with matching package/lock hashes. No target was installed. That validation link
was removed after checks. Environment was Ubuntu/Python 3.12.3 on Linux x86_64
WSL2 kernel 6.18.33.2-microsoft-standard-WSL2, runtime /var/lib/inodefence.

Documentation/catalog checks demonstrate static integrity only;
canonical make check demonstrates inherited engineering regressions at this
revision, not benchmark success or production coverage added by this work.

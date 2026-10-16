# N03 autonomous research advancement — 2026-10-16

```text
TRACK A MACHINE CORRESPONDENCE: PASS; HUMAN DISPOSITION PENDING
TRACK B PILOT INFRASTRUCTURE: IMPLEMENTED / TESTED; EXECUTION NOT_RUN
TRACK C NATIVE V2 OBSERVATION: V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED
TRACK C ROOT CAUSE: MULTI-OPERATION REBINDING OBSERVED; V3 PROPOSAL BLOCKED_FOR_REVIEW
P0-v2/P1-v2/P2-v2 EFFECTIVENESS: NOT_RUN / NOT_EVALUATED
CENTRAL RESEARCH HYPOTHESIS: NOT_EVALUATED
```

This report records the independent work completed under N03 without inventing scientific
approval. It keeps historical persistent-state evidence, final-state policy experiments and
intermediate effect-feedback experiments as three separate tracks.

## 1. Initial and final revisions

The starting main revision was
`919d723b7eb3bf13b060d3ae34b083499590b4fc` (N02 report merge). The report publication merged
as `21e05a8e5749f22c9f3b92b7c8bdf00ffa6c0d04` (PR #101). The subsequent candidate-replay
engineering merged as `2f84b56cd9edf979d564c58215c97cec400f7d3d` (PR #102). Later machine-matcher
implementation was evaluated at repaired functional head
`016d8957951526ea41d8ac29e25fbae36d83a46a` (PR #103). These are publication/engineering
facts, not retroactive historical or pilot execution revisions.

The original developer checkout remained on its local `main` and retained its pre-existing
unstaged `.devcontainer/devcontainer.json` modification. It was never staged, overwritten,
stashed, reset or discarded. All N03 changes used clean isolated worktrees.

## 2. PRs opened, reviewed, repaired and merged

| PR | Reviewed head | Contribution | Merge commit | Independent disposition |
| --- | --- | --- | --- | --- |
| [#97](https://github.com/TheWaitForAGI/InodeFence/pull/97) | `6dcb8eca9b7d0c303ae5e1d786fa06c19655a59b` | full-step policy timing | `5ef167b369e85ddcec3e650d71ca523233a050a7` | **MERGED / TESTED** |
| [#98](https://github.com/TheWaitForAGI/InodeFence/pull/98) | `c7fde5edc128327423c16eaae41ae6f4fcf7c80c` | incremental mutation/policy journal and reader | `cac9286b17fdc54b5355e157632685aa9fadddaf` | **MERGED / TESTED** |
| [#99](https://github.com/TheWaitForAGI/InodeFence/pull/99) | `817bd2d1ebb27ae18ca1cc41197511b8bbcf2555` | exact repeated policy schedule and terminal accounting | `1bd387e86be44b034307fa4886409acde9524928` | **MERGED / TESTED** |
| [#100](https://github.com/TheWaitForAGI/InodeFence/pull/100) | `3e0ef26d89a1a1f93867a6641822c37d5b9ee5ce` | separately versioned v3 namespace-rebinding proposal | `da42c805b391ca842543dcf0db77f6edbce96b1e` | **MERGED / PROPOSED, NOT IMPLEMENTED** |
| [#101](https://github.com/TheWaitForAGI/InodeFence/pull/101) | `99ad171cd90e1f632e8f5e47e901ee544d54be09` | N03 report, machine audit and pilot proposal | `21e05a8e5749f22c9f3b92b7c8bdf00ffa6c0d04` | **MERGED / AUDITED** |
| [#102](https://github.com/TheWaitForAGI/InodeFence/pull/102) | `e53289752c0e82e989245208b72b5a8787f2a535` | exact policy-candidate 3+3 raw replay and independent reader | `2f84b56cd9edf979d564c58215c97cec400f7d3d` | **MERGED / TESTED** |
| [#103](https://github.com/TheWaitForAGI/InodeFence/pull/103) | `016d8957951526ea41d8ac29e25fbae36d83a46a` | N01 mutation-origin relation matcher and 3/3 versus 0/3 reader | containing PR | **REVIEWED / TESTED, HISTORICAL USE NOT_RUN** |

Each diff received an adversarial review for schema/version drift, hidden retry or missing
denominators, C0/C1/C2 changes, timing-boundary misstatement, target-specific leakage and
scientific overclaim. Blocking findings were repaired on the relevant branch before final
validation. GitHub ancestry, required checks and mergeability were rechecked immediately
before each autonomous merge. No branch protection was bypassed and nothing was pushed
directly to main. The unrelated pre-existing PR #92 was not modified or merged.

PR #102 was adversarially repaired after review found that a run linked before a later
directory-sync error could be omitted from failure-prefix accounting. The repaired reader
derives the available run prefix and verifies failure source, target, configuration, phase and
cleanup fields. PR #102 subsequently passed both required jobs and merged cleanly.
PR #103 review found that accepting a caller-selected case ID left pre-replay candidate
enumeration outside the runnable path. The repair scans all verified mutation steps in original
order, deduplicates replay work by exact case ID and independently reconstructs the selected
relation during assessment. The reviewed functional head above includes this repair; its
follow-up commit only records review and reproduction identity because a PR cannot embed its own
future merge commit.

## 3. Canonical validation

PRs #97 through #102 passed GitHub `check` and `container-integration` jobs. Local canonical
Linux validation passed on the exact branch content:

| Milestone | Ruff lint/format | Pyright | pytest | env/docs |
| --- | --- | --- | ---: | --- |
| PR #97 | PASS | 0 errors | 1,490 PASS | PASS |
| PR #98 | PASS | 0 errors | 1,497 PASS | PASS |
| PR #99 | PASS | 0 errors | 1,504 PASS | PASS |
| PR #100 | PASS | 0 errors | 1,504 PASS | PASS |
| PR #101 initial publication content | PASS | 0 errors | 1,504 PASS | PASS |
| PR #102 repaired reviewed head | PASS | 0 errors | 1,509 PASS | PASS |
| PR #103 repaired functional head (tree `eb9d5eddb4b1491f4836860c847d44fc546aeaf6`) | PASS | 0 errors | 1,513 PASS | PASS |

One PR #98 Linux run initially encountered a transient unrelated process-reaping failure.
The isolated check passed and a complete clean rerun passed; no assertion or contract was
weakened. The first PR #102 canonical run observed the same existing timeout/reaping race;
the isolated test passed 5/5 and the complete clean rerun passed. These are engineering tests,
not fuzzing or native qualification results.

## 4. N01 independent machine correspondence audit

Verdict: **PASS (AUTOMATED) / HUMAN DISPOSITION PENDING**. The separate
[machine audit](n03-n01-machine-correspondence-audit.md) read the immutable N02 artifacts
without re-executing either historical release.

Evidence root:
`/Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z`.

| Artifact | SHA-256 |
| --- | --- |
| raw manifest | `2a05b5c92cdc679b73b79630102f2cedc238369c1f8167d8eeee6448e0a3cfac` |
| independent verification | `5c8c5a1841d9b55e3b1470d07e850ec7edafcaa6c826ab1136cec41317cf72ae` |
| final manifest | `0665f739f5aa37ab13953c043f321edb409e821ecb65c303d40db93f6c58bf59` |

**FACT:** exact 7.5.2/7.5.3 package, lock, worker, image and arm64 platform identities match
the retained admissions. **FACT:** the same case/TAR ran in five counterbalanced pairs.
**FACT:** affected runs produced persistent equal `(st_dev, st_ino)` between alias and
sentinel in 5/5, with nlink 1 -> 2 and ctime change; C0 was 0/5 and content was unchanged.
**FACT:** fixed runs produced exact exit-2 linkpath rejection in 5/5, alias absence and
C0/C1/C2 0/5. **FACT:** controls and readiness were complete, isolation/cleanup held, and the
reader reconstructed `N01_PAIR_AUTOMATED_REPLAY_COMPLETE` from 2 admissions, 2 controls,
8 readiness runs, 10 pair runs and 5 comparisons.

**INFERENCE:** source, input and post-state evidence consistently explain the affected
persistent identity plus metadata-only effect and fixed rejection for this exact pair.

**UNRESOLVED:** only a human can accept the frozen correspondence decision.

**FAIL:** no machine correspondence item failed. **INCONCLUSIVE:** the evidence says nothing
about search hit probability, feedback effectiveness or release-wide safety.

## 5. Human correspondence gate

Status: **BLOCKED / AWAITING_HUMAN_CORRESPONDENCE_REVIEW**. The final manifest still records
`human_disposition=pending_human_correspondence_review`. N03 did not manufacture a signature,
human scientific approval or `N01_RELATIVE_HARDLINK_PAIR_QUALIFIED` token. This gate blocks
the dependent historical pilot but not independent engineering or Track C diagnosis.

## 6. B0/B1/B3 pilot engineering readiness

Status: **IMPLEMENTED / TESTED**, with execution and known-class claims separately blocked.
The real path now has tested interfaces for:

- B0/B1/B3 parent-selection and admission semantics;
- the versioned protected-component mutation grammar and exact operator provenance;
- deterministic USTAR build, isolated target execution, persistent C0/C1/C2 and feedback;
- exact initial-case IDs, source/target/environment/isolation/sentinel configuration;
- per-completed-step journal publication before the next execution;
- independent RNG parent/operator/mutation/feedback replay;
- full-step monotonic timing through cleanup, feedback and synchronous journal write;
- immutable complete/failed/invalid/STARTED repetition slots without automatic retry; and
- completed evidence, dataset and summary readers;
- exact policy-case nomination plus counterbalanced three-affected/three-fixed raw replay with
  complete, infrastructure-invalid and hard-interrupted evidence states; and
- a separate N01 machine matcher that deterministically selects a mutation-origin source C1
  relation, enumerates/deduplicates candidates from every raw mutation step and reconstructs
  affected 3/3 versus fixed 0/3 while leaving human review pending.

The exact four benign seeds are unchanged. The protected vocabulary can construct the
controlled relative target without a PoC seed or frozen positive-control injection. This is
constructive reachability only; no historical search hit has been observed.

## 7. Pilot contract and execution status

The [N03 pilot Task Contract proposal](../benchmarks/n03-b0-b1-b3-pilot-task-proposal.md)
specifies the candidate 20-cell schedule: seeds 9001-9005, 200 seed-inclusive executions,
affected B0/B1/B3 plus fixed B3, full projection, protected-component mutation and scheduling
seed 4242. Total candidate workload is 4,000 search executions.

Status: **PROPOSED / NOT_AUTHORIZED / NOT_RUN**. Exact blockers are:

1. the N01 human correspondence token remains pending;
2. the protocol's proposed 5-second target timeout differs from the N01 admitted/replayed 10-second
   setting and needs fresh admission/readiness or a pre-run versioned amendment;
3. no human has frozen the pilot plan/revision/digest/output root;
4. generic candidate replay and the N01-specific mechanical matcher are implemented, but
   historical matcher use and human root-cause adjudication remain NOT_RUN; and
5. controller peak-memory measurement for pilot feasibility is not yet frozen.

No pilot target was executed. The N02 positive-control archive never entered an initial
corpus. B0, B1 and B3 results remain **NOT_RUN**.

## 8. Native v2 observation failure root cause

Verdict: **TESTED DIAGNOSTIC / QUALIFICATION FAIL RETAINED**. The frozen v2
`namespace_replacement` class requires one correlated successful operation whose endpoint is
present before and present afterward with changed identity or object type. The duplicate-path
fixture instead used node-tar's reusable-file path: the second regular entry opened the same
regular inode with `O_TRUNC`. The original matrix observed same-inode truncation in 20/20 full
runs and v2 replacement in 0/20.

Source and runtime diagnosis showed node-tar's non-reusable cases replace a path through
distinct successful operations: `unlink` followed by open/create, mkdir, link or symlink.
The unchanged reader correctly emits removal and creation/link-specific effects separately.
It must not merge them into the single-operation v2 replacement class.

This is a fixture/effect-vocabulary reachability limitation for the exercised scope, not a
shown producer or reader defect. The finite cases do not prove that every possible accepted
node-tar input lacks a genuine one-operation v2 replacement.

## 9. Candidate replacement-coverage resolution

The evidence-supported branch is multi-operation namespace rebinding. PR #100 records a
separately versioned [v3 proposal](../design/entry-effect-rebinding-v3-proposal.md) rather
than weakening v2. A future `namespace_rebinding_sequence` would require explicit absence,
successful removal and creation/link completion, the same entry/path, global sequence bounds,
a producer-supported dependency edge, no intervening binding operation, complete raw trace
and independent reconstruction.

Status: **PROPOSED / BLOCKED_FOR_REVIEW / NOT_IMPLEMENTED / NOT_QUALIFIED**. Approval would
authorize only a new implementation Task Contract. It would not qualify v2, reuse P0-v2/
P1-v2/P2-v2 identifiers or authorize a native campaign.

## 10. Implemented observer or fixture changes

Status: **NOT_IMPLEMENTED** for native semantics and fixtures. N03 found no evidence-grounded
v2 implementation defect to repair. It changed no observer schema, producer, reader, fixture,
coverage rule, feedback key, scheduler or C0/C1/C2 oracle. Original v2 artifacts remain
immutable.

N03 did implement independent final-state campaign timing, journaling and repetition
accounting in PRs #97-#99. Those changes belong to Track B and cannot be counted as Track C
observer work.

## 11. Focused qualification evidence

Static/source-level analysis and retained bounded diagnostics establish:

- duplicate regular entries take the reusable same-inode truncation path;
- file-to-directory, file-to-symlink, file-to-hardlink and hardlink-anchor cases use
  unlink then a distinct creation/link operation;
- the v2 reader preserves those events without false replacement aggregation;
- all 18 independently verified complete native diagnostic bundles contained zero v2
  replacement events; and
- inode-number reuse across unlink/create makes separated equal device/inode tuples
  insufficient proof of continuous identity.

These are **TESTED diagnostic facts**, not a new qualification matrix. No full 480-run
matrix was repeated. The original raw matrix was not present on the current macOS host, so
N03 relied on its immutable report and hashes rather than claiming a new raw-file audit.

## 12. Native v2 qualification verdict

No new qualification was authorized or executed. The exact decision remains
**`V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`**. The original matrix completed 480/480 runs
(420 success, 60 expected rejection), with 13/14 criteria passing and replacement coverage
failing.

| Retained artifact | SHA-256 |
| --- | --- |
| `qualification.json` | `ca2dae9150813c6df14df10e16de65b1139550a7ecd761a30122c717e4575a90` |
| controller independent reader | `2bb348cfb1c4ffa398ed118ff87c035f2af1c825933215b9d5c8bb7fadd293aa` |
| host independent reader | `657c07a509acd0437ee57387baced1ba5e7c23debb8da4bfaa7cf5574329b573` |
| audit script | `b968ab672acff40d884f6a4add3838639663a9b76bbb4b295cdeb135f73ab3ba` |
| 1,180-file checksum list | `59b0fb74a402ffb41200639e5c5e36c6b8e53dd83f9704cf463775a5be05d1bf` |
| raw archive | `6b0a5b31d52d00347259342683941692181e93515d7f82384df86d9fb1cab1e5` |

New native v2 qualification: **NOT_RUN**. New verdict: **NOT ISSUED**.

## 13. P0-v2/P1-v2/P2-v2 readiness

The generic v2 model, normalization, evidence reader and closed-loop policy machinery remain
**IMPLEMENTED / SYNTHETICALLY TESTED**. Native comparison readiness is **BLOCKED** because the
required observation qualification token does not exist.

The intended independent variables remain unchanged: P1-v2 versus P0-v2 estimates the effect
of intermediate-effect retention; P2-v2 versus P1-v2 estimates adaptive scheduling on top of
that retention. Target, initial seeds, mutation grammar, oracle, runtime constraints and
budget must otherwise be comparable. B0/B1/B3 data cannot answer either comparison.

No native P0-v2, P1-v2 or P2-v2 campaign was scheduled or executed. Their experimental status
is **NOT_RUN** and their effectiveness is **NOT_EVALUATED**.

## 14. Actual experimental results

There are no new fuzzing-effectiveness or native intermediate-feedback results in N03.

- Track A: retained historical automated replay, independently machine-audited **PASS**;
  human qualification pending.
- Track B: infrastructure engineering **IMPLEMENTED / TESTED**; B0/B1/B3 pilot **NOT_RUN**.
- Track C: diagnostic root cause supported; v2 qualification remains negative; new matrix and
  native effectiveness campaigns **NOT_RUN**.

The central hypothesis—intermediate filesystem-effect feedback may improve useful mutation
selection under a controlled budget—is **NOT_EVALUATED**.

## 15. Supported and unsupported scientific claims

Supported:

- N02's immutable records consistently distinguish this exact affected/fixed N01 behavior,
  and a separate machine audit agrees with its automated token.
- Affected C2 is nlink/ctime metadata evidence; sentinel content did not change.
- node-tar duplicate-path behavior in the v2 qualification matrix was truncation, not replacement.
- the exercised genuine namespace changes are multi-operation rebinding sequences that v2
  deliberately does not aggregate.
- the final-state campaign runner can preserve deterministic mutation/search provenance,
  per-step elapsed time and incomplete/failed repetition accounting in engineering tests; and
- the N01 offline reader can reconstruct deterministic source relation nomination and the
  3/3 versus 0/3 mechanical rule with controlled adapters, without a human token.

Unsupported:

- human N01 qualification, fuzzing rediscovery or feedback advantage;
- any B0/B1/B3 effect size, success rate or latency result;
- v2 native observation qualification or P0/P1/P2 effectiveness;
- treating feedback-key novelty as vulnerability discovery;
- sentinel content corruption in N01;
- universal impossibility of single-operation replacement in node-tar;
- a new vulnerability, general release safety or cross-platform generality; and
- retroactive reclassification of the original v2 evidence under proposed v3 semantics.

## 16. Reproduction instructions

Reproduce engineering validation from a clean worktree at the evaluated revision:

```bash
git worktree add --detach /tmp/inodefence-n03-review \
  016d8957951526ea41d8ac29e25fbae36d83a46a
cd /tmp/inodefence-n03-review
make check
```

Re-run only the N02 reader, not the historical targets:

```bash
PYTHONPATH=src python -m inodefence.evaluation.n01_reader \
  /Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z \
  --raw-manifest-sha256 \
  2a05b5c92cdc679b73b79630102f2cedc238369c1f8167d8eeee6448e0a3cfac
```

Verify completed policy/repetition artifacts when they exist:

```bash
PYTHONPATH=src python -m inodefence.evaluation.policy_repeated \
  <repetition-root> --plan-sha256 <trusted-plan-sha256>
PYTHONPATH=src python -m inodefence.evaluation.policy_journal \
  <repetition-root>/run-00000000/evidence
PYTHONPATH=src python -m inodefence.evaluation.candidate_replay \
  <candidate-replay-root> <source-policy-evidence> \
  --completion-sha256 <trusted-completion-sha256>
PYTHONPATH=src python -m inodefence.evaluation.n01_candidate_match \
  <candidate-replay-root> <source-policy-evidence> \
  --completion-sha256 <trusted-completion-sha256>
```

The native v2 report contains its original WSL/controller reproduction commands and raw
hashes. Do not launch another matrix without a new frozen execution Task Contract.

## 17. Remaining blockers

1. Human N01 source/input/runtime correspondence disposition.
2. Pilot timeout decision and exact historical target re-admission at that setting.
3. Pilot plan authorization, peak-memory measurement, historical N01 matcher execution and
   human known-class adjudication.
4. Human scientific decision on the v3 rebinding proposal, followed by a separate
   implementation contract if approved.
5. New finite qualification fixtures/rule and authorization before any native matrix.
6. Exact native observation qualification before P0/P1/P2-v2 campaigns.

These are scientific or authorization gates, not reasons to relabel engineering tests as
experiments.

## 18. Next research milestone

The next independent decision is human review of the v3 rebinding proposal and the N01
correspondence record. If N01 qualifies, first freeze the 5-second versus 10-second pilot
choice and review the versioned N01 machine-matcher rule before running the 20 proposed cells.
If v3 is approved, implement its composite in a new versioned contract and perform the
smallest bounded fixture/reader checks before proposing any qualification matrix. If either
decision is rejected, retain the negative result and revise the research scope explicitly;
do not weaken the existing gates.

# Proposed Task Contract: N03 B0/B1/B3 historical pilot

Status: **PROPOSED / NOT_AUTHORIZED / NOT_RUN**. This document makes the existing planning
parameters concrete enough to review. It does not freeze them, issue the pending N01 human
qualification token, authorize historical execution, or convert the N02 positive-control
archive into a fuzzing seed.

## Objective and evidence boundary

The proposed pilot asks whether the complete final-state search path can execute reproducibly
against the exact N01 historical pair and retain evidence adequate for a later controlled
B0/B1/B3 comparison. It is a feasibility and qualification pilot, not a formal estimate.

The search path under review is:

```text
SearchPolicy -> parent selection -> protected-component mutation -> USTAR builder
  -> IsolatedTarget -> run_case -> persistent C0/C1/C2 -> SearchState
  -> B0 active child or B1/B3 retained corpus -> journal/timing export
  -> repetition ledger -> independent readers -> offline candidate adjudication
```

This is Track B final-state feedback. It does not exercise, qualify or estimate the Track C
P0-v2/P1-v2/P2-v2 intermediate-effect policies.

### Allowed work after explicit approval

- Re-admit the exact immutable historical images at the finally selected timeout and source
  revision.
- Execute the four original benign seeds and the declared bounded policy cells once each.
- Retain all complete, failed, interrupted and invalid attempts without retry or denominator
  removal.
- Passively nominate generic matching observations and, under a separate recorded validation
  budget, execute the declared three affected plus three fixed replays.
- Produce verified raw summaries and feasibility measurements. Pilot data stays separate from
  formal estimates.

### Prohibited work

- Adding the N02 positive-control case/TAR, a PoC-derived case, or a guaranteed-hit recipe to
  the initial corpus.
- Putting a CVE, package version or expected target outcome into the oracle, feedback key,
  mutator or scheduling reward.
- Replacing B0/B1/B3 with P0/P1/P2 identifiers or making an intermediate-effect claim.
- Retrying a claimed slot, discounting no-ops/rejections/failures/timeouts, changing a budget
  after observing a hit, or stopping a campaign after a hit.
- Executing from a dirty source, source bind mount runtime, mutable image tag, unmatched
  target identity, missing human gate or unapproved contract revision.

## Candidate immutable inputs

The initial corpus is exactly `minimal_seed_corpus()` in this order. Its current canonical
case IDs are:

| Index | Logical seed | Case ID |
| ---: | --- | --- |
| 0 | one regular file | `c56da02197b3e8959e46c08c476c7fb15a13763ce9d8d57ac5151f4b1d709fd8` |
| 1 | directory plus regular child | `cdcc8045e37293498ff2d8e69e6e5638ee470f1bd11b1d0b8f16f1f9e783208f` |
| 2 | regular plus internal hardlink | `de8ddc5ca4c15fccb638257bbbe671c4fcc9c707962cb92de6589a09f6418620` |
| 3 | regular plus internal symlink | `842bdde9b083096d6f5f1c93c93efb3ff35d141b7311571dab281c771d83c0d1` |

The shared mutation policy candidate is
`uniform-generic-m1-protected-components-v1`. It retains the generic eight-slot uniform
draw/no-retry behavior and adds only the finite controlled components `outside` and
`sentinel.txt`. A constructive engineering test proves that this grammar can transform seed
2 into a hardlink target `../outside/sentinel.txt` with deterministic USTAR bytes. That test
does not inject its child into this pilot and does not estimate the probability of reaching
it under the declared RNG streams.

All arms use the full feedback projection and the default controlled sentinel
`outside/sentinel.txt`, content SHA-256
`caed2ac112733b3f5e3f56d9372f7ce6ba88dfafd57eb58807bb29f16548e36b`, mode `0600`.

## Candidate target binding

These N02 image identities are starting candidates. The approved pilot must re-bind them at a
clean pilot source revision and record fresh target/isolation provenance; the N02 admission
record is not copied forward as pilot admission.

| Binding | affected arm | fixed arm |
| --- | --- | --- |
| Target | Node 22.22.0 / node-tar 7.5.2 | Node 22.22.0 / node-tar 7.5.3 |
| npm tarball SHA-256 | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` |
| lock SHA-256 | `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` | `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24` |
| image ID | `sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520` | `sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f` |
| arm64 platform manifest | `sha256:b5ae7f5d2f85f12fa417ecece3e9089001266cc6bf4a997724c225a40ce8b542` | `sha256:3a1bcf4dffcd21ddc4fa6645980bebd96dceda4ceee0ddfe033abd0d50dd6ee0` |

Both candidates bind worker SHA-256
`feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b`,
`strict:true`, `preservePaths:false`, network none, non-root UID/GID 1000, read-only rootfs,
capabilities dropped, no-new-privileges and a fresh runtime-volume subpath per execution.

The evaluation protocol proposes a **5 second** per-target timeout, but N01 admission and
correspondence evidence used **10 seconds**. This difference is a hard configuration mismatch.
Before authorization, reviewers must choose and freeze one of these paths without consulting
pilot outcomes:

1. qualify both exact images, readiness and isolation at 5 seconds under the pilot revision;
   or
2. version the pilot contract to use 10 seconds and amend the planning protocol before any
   pilot run.

The current proposal prefers path 1 to retain the predeclared comparison candidate, but no
choice is approved by this document.

## Candidate cells, budgets and order

Candidate campaign seeds are 9001 through 9005. The seed-inclusive budget is 200 executions:
four ordered seed executions and 196 mutation executions. There are 20 campaigns and 4,000
total search executions.

| Arm ID | Target | Search policy | Campaigns | Purpose limit |
| --- | --- | --- | ---: | --- |
| `affected-b0` | 7.5.2 | `unretained-walk-v1` | 5 | unretained-walk feasibility |
| `affected-b1` | 7.5.2 | `state-v3-uniform-parent-v1` | 5 | state-only retention feasibility |
| `affected-b3` | 7.5.2 | `state-v2-or-violation-v1-uniform-parent-v1` | 5 | full final-state policy feasibility |
| `fixed-b3` | 7.5.3 | same B3 identifier | 5 | target discrimination/inventory feasibility |

Fixed B0/B1 are outside this pilot. The vulnerable B3 cells are reused for both inventory and
policy comparison; they are not rerun. Every cell uses identical initial IDs/order, mutation
policy, builder, sentinel, timeout, resource limits, isolation, persistent C0/C1/C2 and total
budget. Search policy is the only declared independent variable in the affected comparison;
target package version is the only target-pair difference in B3.

Base order is seed-major with arm order `affected-b0`, `affected-b1`, `affected-b3`,
`fixed-b3`. Applying Python standard-library `random.Random(4242).shuffle` once produces this
complete schedule. Scheduling RNG is separate from campaign RNG.

| Position | Run ID | Position | Run ID |
| ---: | --- | ---: | --- |
| 0 | `n01-affected-b3-9002` | 10 | `n01-fixed-b3-9002` |
| 1 | `n01-fixed-b3-9003` | 11 | `n01-affected-b0-9003` |
| 2 | `n01-affected-b3-9004` | 12 | `n01-affected-b3-9001` |
| 3 | `n01-affected-b1-9003` | 13 | `n01-affected-b3-9005` |
| 4 | `n01-fixed-b3-9001` | 14 | `n01-affected-b1-9002` |
| 5 | `n01-fixed-b3-9005` | 15 | `n01-affected-b0-9005` |
| 6 | `n01-affected-b1-9001` | 16 | `n01-affected-b0-9004` |
| 7 | `n01-fixed-b3-9004` | 17 | `n01-affected-b0-9001` |
| 8 | `n01-affected-b3-9003` | 18 | `n01-affected-b0-9002` |
| 9 | `n01-affected-b1-9005` | 19 | `n01-affected-b1-9004` |

Execute one campaign at a time. A proposed two-hour host watchdog applies to each campaign;
it is an infrastructure stop, not a substitute execution budget. A completed campaign runs
all 200 steps even after a candidate observation.

## Runnable evidence path and current readiness

The generic caller infrastructure is **IMPLEMENTED / TESTED**:

- `SearchCampaignConfig` rejects untyped/unknown policy combinations and keeps the budget
  seed-inclusive.
- `run_search_campaign` performs the real seed -> selection -> mutation -> build -> isolated
  `run_case` -> C0/C1/C2 -> feedback loop.
- `PolicyEvaluationConfig` binds each complete campaign to exact initial IDs, target/source/
  environment/isolation/sentinel provenance and stable protocol profiles.
- `PolicyRepetitionPlan` records the exact ordered cells. Its controller durably claims a
  slot once and never retries a STARTED or terminal slot.
- The journal publishes each completed step before the next execution and independently
  replays RNG parent selection, operator, mutation and feedback. Ordinary exceptions become
  infrastructure-invalid terminal evidence; hard interruption leaves a verified STARTED
  prefix.
- `policy-full-step-monotonic-v1` measures preflight through cleanup, feedback and synchronous
  journal publication for each step. Final bulk publication and adjudication are outside the
  interval and must be reported separately.
- Completed policy readers reconstruct case/TAR, provenance, state/oracle, policy admission,
  lineage and counters. Repetition-ledger states must be joined to completed-only summaries so
  failed/invalid/STARTED slots cannot disappear.

Target construction and scientific authorization deliberately remain caller-owned. No
historical broker mode will be added or invoked until the exact approved contract supplies a
clean revision, selected timeout, plan digest, target/image IDs and new output root.

## Candidate nomination and offline adjudication

All completed raw steps are inspected in ascending original index, regardless of corpus
admission. Candidate identity is the exact `case_id` plus TAR SHA-256 and original campaign/
step occurrence. Deduplicate identical cases only for replay; retain every occurrence.

For N01, nomination requires complete generic evidence containing the persistent selected C1
relation to the controlled sentinel. C2 nlink/ctime may corroborate it, but content change is
not required and C2 alone is not the N01 match. C0, rejection, crash, timeout, novel state or
an unrelated violation alone is not a nomination.

Each nominated case requires, under a separately recorded validation budget:

1. three fresh affected replays with matching persistent N01 evidence in 3/3;
2. three fresh fixed replays with matching evidence absent in 3/3;
3. identical logical input/TAR and equivalent selected setup across arms;
4. preservation of every negative, rejected, failed, timed-out or incomplete replay; and
5. a human root-cause disposition connecting archive semantics and source behavior.

The generic [candidate replay layer](../design/candidate-pair-replay-v1.md) binds a selected
case to verified campaign occurrences, executes the counterbalanced 3+3 schedule and preserves
complete/failed/interrupted raw evidence plus three `PairComparison` records. The separate
[N01 machine matcher](n01-candidate-machine-match-v1.md) now implements deterministic
all-step mutation-origin C1 candidate enumeration, exact N01 target/setup checks and affected
3/3 versus fixed 0/3 reconstruction. It remains TESTED only with controlled adapters. Human root-cause
disposition is unperformed, so neither layer can report confirmed known-class rediscovery.

## Failure, censoring and evidence rules

- Every returned target status consumes one execution. No-op mutation, duplicate case,
  rejection, failure and timeout remain in the denominator.
- PENDING means never claimed. STARTED means durably claimed without a terminal
  acknowledgement and is never automatically retried. FAILED/INVALID are infrastructure
  outcomes, not no-hit. COMPLETED alone supplies an ordinary full-budget hit/no-hit record.
- A campaign with fewer than 200 complete steps is invalid/incomplete. It is not censored as
  a normal no-hit at the available prefix.
- Record scheduled/claimed/completed/failed/invalid/STARTED counts and completed-step counts
  for all 20 slots. Dataset statistics must not infer these from completed bundles.
- A no-hit completed pilot is **INCONCLUSIVE** for the hypothesis and remains separate from
  any later formal dataset.
- No data, corpus, RNG state, retained parent or candidate replay is shared into another
  campaign condition.

## Feasibility assessment

The proposed search workload is finite: 4,000 executions. At the 5-second target timeout the
target-time ceiling is 20,000 seconds (5.56 hours) before setup/observation/publication;
twenty two-hour watchdogs are only independent stall bounds, not an expected runtime.
The 200-step result and journal are O(budget), and target containers retain the existing
512 MiB limit.

Actual median/p95 full-step time, rejection/timeout rates, final evidence bytes and controller
peak memory are unavailable because the pilot is NOT_RUN. Per-step timing and exact byte
counts are implemented. A reviewed controller peak-memory measurement method is still needed;
target lifecycle duration cannot substitute for full-step time. These measurements decide
whether the larger formal plan is feasible and cannot be invented from N02's ten pair runs.

## Authorization and stop gates

Execution remains **BLOCKED / NOT_RUN** until all of the following are recorded:

1. a human disposition issues the exact N01 qualification token required by the frozen
   contract;
2. one timeout path above is versioned, reviewed and qualified;
3. the clean source SHA, target/image/artifact identities, controller/runtime/filesystem and
   resource profile are frozen;
4. this candidate schedule/budget is accepted in an explicitly authorized revision with its
   exact plan SHA-256 and new immutable evidence root;
5. fresh benign readiness and oracle controls pass at that exact setup;
6. peak-memory measurement and independent reader commands are frozen; and
7. the intended claim is chosen: generic feasibility only, or confirmed rediscovery after
   historical matcher execution and the human adjudication gate pass.

If any gate fails, preserve its evidence and do not begin or continue the 20 policy cells.
Current execution verdict: **NOT_RUN**. Current Track B hypothesis verdict:
**NOT_EVALUATED**.

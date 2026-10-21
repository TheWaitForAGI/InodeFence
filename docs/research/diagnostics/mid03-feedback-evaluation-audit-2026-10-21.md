# MID-03 feedback evaluation and pilot audit

Date: **2026-10-21 UTC**. Owner scope: **MID-03 / Fuzzing and Evaluation**.

Overall decision: **ENGINEERING TEST PASS / HISTORICAL PREFLIGHT NOT READY /
B0/B1/B3 PILOT NOT_AUTHORIZED / NOT_RUN**.

This report audits current `origin/main`, the Git-visible heads and merge refs for PRs #108 and
#112–#114, and the existing policy/evaluation tests. It records no historical target extraction,
no policy effectiveness result and no vulnerability rediscovery. Synthetic and trusted-reference
checks below are engineering evidence only.

## 1. Source, worktree and access boundary

| Item | Observed fact | Disposition |
| --- | --- | --- |
| Initial branch / worktree | clean `main`; no tracked or untracked changes | preserved |
| `HEAD` / `origin/main` | `8d29982c26cebfcce7a413b3ba9177fcd28078de`; ahead/behind `0/0` after fetch | exact current base |
| Audit branch | `docs/mid03-feedback-evaluation-audit` | documentation-only result |
| Environment | Linux WSL2 `6.18.33.2-microsoft-standard-WSL2`, `x86_64`, Python 3.12.3 | not the frozen arm64 historical host |
| Runtime root | `/var/lib/inodefence`; hardlink, symlink and shared-object checks PASS | local semantics only |
| Docker / retained inputs | Docker socket absent; N02 raw root, N05 Linux evidence and N05 host ledger absent | historical execution unavailable |
| GitHub metadata | `gh` unavailable and the private REST endpoint was unauthenticated; authenticated Git supplied heads/merge refs | UI review/check labels not independently verified |

No existing worktree content was reset or overwritten. Temporary detached worktrees were used to
test the GitHub merge refs against current main. The presence of a remote head and merge ref is a
Git-observable fact, not a claim about GitHub UI approval.

## 2. “N05” disambiguation

Two unrelated identifiers currently use `N05`:

1. **Benchmark catalog N05** is the secondary node-tar 6.1.0 → 6.1.1 repeated-absolute-root
   path-confinement candidate (CVE-2021-32804). It remains implementation-blocked and NOT_RUN.
2. **Process-gate N05** in PRs #113/#114 is the proposed five-second final-state preflight v2 for
   the already selected N01 node-tar 7.5.2/7.5.3 pair. It is the N05 referenced by the current
   pilot critical path. It performs at most eight benign extractions and is not a fuzzing campaign.

Current main contains only the consumed N04 five-second attempt. That attempt stopped before an
oracle control or target extraction because the trusted Docker transport rejected a host-only
metadata request. Its exact result remains `PREFLIGHT_INCONCLUSIVE / ATTEMPT CONSUMED`, with
five-second readiness `NOT_EVALUATED`.

PR #114 adds an implementation candidate for process-gate N05, but its own contract says
`NOT_AUTHORIZED / NOT_RUN / AWAITING EXECUTION-SOURCE AND CONTROLLER FREEZE`. The PR title or code
existence must not be read as human execution approval.

## 3. Pull-request dependency audit

| PR | Git-visible revision and content | Dependency / current gate |
| --- | --- | --- |
| #108 | head `64a7a164`; current-main merge ref `4b6b661`; Track A protocol/config, 20-cell controller, final manifest and analysis | independent of #112–#114; not in main; preparation accepts caller-supplied digest strings rather than verifying N05/authorization records |
| #112 | head `0eca90f`; bounded controller-stderr retention and host-ledger binding | direct ancestor of #114; does not create or authorize a new attempt |
| #113 | head `00356e4`; N05 preflight/native-v3 drafts and critical-path documentation | direct ancestor of #114; documentation does not authorize execution |
| #114 | head `f7aaa33`; current-main merge ref `4fc0cd5`; contains #112 and #113 plus N05 mode/reader/authorization-record admission | implementation candidate only; exact clean integration SHA, controller image and separate human authorization absent |

Git ancestry confirms #112 and #113 are included in #114. PR #108 and #114 are independent; a
Git tree merge is conflict-free, but the semantic integration is incomplete. PR #114 explicitly
records that PR #108:

- does not open and verify the retained N05 host/Linux evidence;
- does not parse and retain a complete separate pilot authorization record; and
- still names the N04 environment profile.

Therefore merging either code path alone would not open the pilot gate. The correct next change is
a small Track A consumer integration after the N05 revision is reviewed, not a duplicate N05
runner or a second pilot implementation.

## 4. B0/B1/B3 policy audit

The executable policies are implemented in `SearchState` and `run_search_campaign`. Every arm
keeps the full `RunResult`, final StateSignature v3 diagnostics and generic C0/C1/C2 verdicts.

| Policy | Intentional independent-variable behavior | What is not changed |
| --- | --- | --- |
| B0 `unretained-walk-v1` | no corpus admission; first post-seed parent is selected uniformly from the immutable seed bank, then every observed child becomes the next parent regardless of status or novelty | mutation vocabulary, target, oracle, raw evidence and budget |
| B1 `state-v3-uniform-parent-v1` | admit a unique case only when its declared feedback key is new; select uniformly from retained unique cases | violation fingerprints are still observed but do not admit a parent |
| B3 `state-v2-or-violation-v1-uniform-parent-v1` | admit a unique case when its feedback key or a generic violation fingerprint is new; select uniformly from retained unique cases | same full state/oracle evidence; the legacy ID does not mean a v2 state key |

`interesting` is a full-diagnostic field (`full state OR violation novelty`), not the policy
admission count. `feedback_key_novel`, `admission_eligible` and `retained` must be reported
separately. B0 intentionally has no retained corpus; its active working child is separate from
diagnostic novelty indexes.

### Exact common values in the proposed Track A pilot

PR #108's machine-readable protocol has SHA-256
`88ed4fde6e3f926099a9e28d978b583c5eedcb4b4074b37a4b1e7bca1c26f19c` and independently
reproduces the declared `random.Random(4242).shuffle` schedule.

| Field | Frozen candidate value |
| --- | --- |
| Initial corpus | the four ordered `minimal_seed_corpus()` cases; no PoC or positive-control input |
| Mutation | `uniform-generic-m1-protected-components-v1`, uniform eight-slot behavior |
| Feedback projection | full StateSignature v3 for all four pilot arms |
| Oracle | unchanged persistent C0/C1/C2 |
| Sentinel | `outside/sentinel.txt`, frozen content/mode |
| Per-target timeout | exactly 5 seconds |
| Campaign RNG seeds | 9001, 9002, 9003, 9004, 9005 |
| Per-campaign budget | 200 executions including four seed executions and all returned statuses/no-ops |
| Repetitions | five campaigns per arm |
| Scheduling RNG | independent seed 4242; one immutable 20-cell order |
| Campaign watchdog | 7,200 seconds; an infrastructure stop is not an ordinary no-hit |

The 4,000-run proposal is **4,000 total search executions**, not 4,000 per policy:

```text
affected B0: 5 × 200 = 1,000
affected B1: 5 × 200 = 1,000
affected B3: 5 × 200 = 1,000
fixed B3:    5 × 200 = 1,000
total:      20 × 200 = 4,000
```

Within affected 7.5.2, search policy is the intended differing factor. In the affected/fixed B3
pair, target package/artifact identity is the intended differing factor. Fixed B0/B1 are outside
this exploratory plan.

### Same values versus same rules

The exact corpus, policy vocabulary, timeout, budget, oracle, sentinel, source/environment class
and resource limits must have equal values where the protocol declares them common. The following
must instead follow equal rules while their realized values may legitimately diverge:

- parent selection applies each policy's declared rule;
- one caller-owned RNG is seeded equally for paired campaign IDs, but B0 and B1/B3 consume RNG
  differently because parent selection differs;
- feedback changes the retained corpus and therefore later parents/children;
- all returned `SUCCESS`, `REJECTED`, `FAILED` and `TIMED_OUT` results consume budget and remain
  observable;
- no-op and duplicate cases consume budget; duplicate cases do not become duplicate parents; and
- campaigns continue to the full budget after an observation or nomination.

Dummy RNG calls or shared evolved corpora would change the experiment and are prohibited.

## 5. A1/A2/A3 disposition

| Ablation | Actual implementation | Evidence status |
| --- | --- | --- |
| A1 | remove only `identity_groups` from the admission key; preserve regular nlink, objects and C1 fingerprints/raw verdicts | IMPLEMENTED / ENGINEERING TESTED / target effect NOT_RUN |
| A2 | remove only `external_effects` labels from the admission key; preserve sentinel objects and C2 fingerprints/raw verdicts | IMPLEMENTED / ENGINEERING TESTED / target effect NOT_RUN |
| A3 | keep the reorder operator draw and internal draws but execute that slot as a no-op; insertion/duplication can still alter order | IMPLEMENTED / ENGINEERING TESTED / target effect NOT_RUN |

The 4,000-run PR #108 pilot uses FULL projection and the ordinary protected-component mutation
policy, so it is a B0/B1/B3 feasibility run, not an A1/A2/A3 experiment. No ablation effect may be
reported from it.

## 6. Evidence and aggregation audit

The completed policy path and PR #108 Track A layer preserve raw evidence separately from derived
summaries:

```text
immutable plan/config
  -> no-overwrite claim
  -> per-step policy journal and full RunResult
  -> timing + controller process-lifetime HWM
  -> terminal repetition state
  -> completed policy bundle / final manifest
  -> verified derived JSON analysis
```

Accounting rules verified by source and tests:

- `PENDING`: never claimed; not an attempted campaign and not a no-hit.
- `STARTED`: durable claim with no valid terminal acknowledgement; interrupted prefix is retained,
  never automatically retried and never an ordinary censor.
- `FAILED` / `INVALID`: infrastructure terminal states; preserved and excluded from completed-run
  effect denominators without disappearing from scheduled denominators.
- `COMPLETED`: exact-budget journal plus verified terminal evidence. Only this can provide an
  ordinary full-budget hit/no-hit campaign record.
- Target `FAILED` or `TIMED_OUT` is different from campaign infrastructure failure: a returned
  complete `RunResult` consumes one execution and its observable state remains in the campaign.
- Missing, corrupt, extra, symlinked or checksum-mismatched artifacts fail closed.
- Duplicate raw executions cannot be pooled as independent observations even if outer labels or
  random seeds are changed.
- Completed-only statistics do not infer missing/invalid repetition counts; Track A joins the
  repetition ledger explicitly.

The PR #108 analyzer reports raw state/fingerprint growth curves at declared checkpoints, all
target statuses, generic C0/C1/C2 observation counts, first generic contract observation, mutation
attempt/applied/no-op counts, full-step timing, controller HWM and evidence bytes. It labels its
output `RAW ONLY`; N01-like machine nominations are not confirmed rediscovery and require separate
3+3 replay plus human correspondence.

No publication graph was produced because there is no historical pilot dataset. Producing a curve
from safe synthetic/reference fixtures and presenting it as a target result would cross the claim
boundary.

## 7. Executed engineering validation

| Revision / scope | Command | Result |
| --- | --- | --- |
| main `8d29982` | focused B0/B1/B3, A1/A2/A3, evidence, dataset, journal, repetition, timing and HWM tests | **285 passed** |
| audit branch from main `8d29982` | `make check` | Ruff PASS; format 358 files; Pyright 0 errors; **1,584 pytest passed**; environment PASS; docs PASS (129 Markdown files) |
| PR #108 current-main merge ref `4b6b661` | `make check` | Ruff PASS; format 363 files; Pyright 0 errors; **1,592 pytest passed**; environment PASS; docs PASS (130 Markdown files) |
| PR #108 protocol | independent JSON schedule/digest check | 20 unique campaigns, five per arm, four per seed, shuffle seed 4242 match, 4,000 total |
| PR #114 current-main merge ref `4fc0cd5` | focused N05, N04 ledger and container-backend tests | **134 passed** |
| PRs #108/#112/#113/#114 | `git diff --check` | PASS |

An initially combined hand-picked pytest invocation in the temporary PR #108 worktree reported one
fixture-resolution collection error; the same test file passed alone and the canonical full suite
then passed all 1,592 tests. It is retained here as a validation-command artifact, not treated as a
product failure or hidden from the record.

## 8. Execution gate decision

| Gate | Required state | Current evidence | Decision |
| --- | --- | --- | --- |
| N01 human correspondence | exact frozen human disposition | machine replay/audits only; pending | BLOCKED |
| Five-second runner | reviewed clean N05 integration revision and controller image | PR #114 candidate only; not in main/frozen | BLOCKED |
| N05 authorization | explicit human record for exact attempt ID/source/host/images/budget | absent | NOT_AUTHORIZED |
| N05 result | retained host/Linux records and independent `PREFLIGHT_PASS` | absent | NOT_RUN |
| Track A consumer | verify N05 records and complete pilot authorization, bind same source/target/timeout/isolation | PR #108 accepts digest strings only | BLOCKED |
| Pilot authorization | separate explicit 20-cell/4,000-execution approval | absent; this task explicitly does not replace it | NOT_AUTHORIZED |
| Current runtime | trusted arm64/OrbStack controller, exact images/packages and retained inputs | x86_64 WSL2; Docker/evidence unavailable | UNAVAILABLE |

Final experiment record for this audit:

```text
experiment_id: track-a-final-state-exploratory-feasibility-v1
source_candidate: PR #108 head 64a7a1645c03512d50ff5e0246108d297d1e6aa8
target_candidate: node-tar 7.5.2 / 7.5.3
scheduled_campaigns: 20
scheduled_executions: 4000
attempted_campaigns: 0
attempted_executions: 0
completed_campaigns: 0
valid_campaigns: 0
failed_campaigns: 0
interrupted_campaigns: 0
violation_candidates: NOT_EVALUATED
state_novelty: NOT_EVALUATED
result: NOT_RUN
evidence_grade: no experimental evidence
```

Zero attempted executions are not reported as zero violations, zero novelty or a no-hit result.

## 9. Handoff and presentation-safe claims

### FACT

- Current main implements B0/B1/B3, A1/A2/A3 and the common C0/C1/C2 final-state pipeline.
- The exact candidate pilot is 20 campaigns and 4,000 total seed-inclusive executions.
- PR #108's current-main merge view passes canonical engineering validation.
- N04 was inconclusive before target execution; process-gate N05 and the Track A pilot are NOT_RUN.

### ENGINEERING TEST

- Policy semantics, exact schedule, seed/budget binding, raw evidence readers, missing/corrupt/
  duplicate rejection, interruption accounting and synthetic/reference aggregation are tested.
- These checks establish implementation consistency, not historical target readiness or policy
  effectiveness.

### EXPERIMENT

- No B0/B1/B3 target campaign, comparative result, first-hit result, growth curve or A1/A2/A3
  target ablation result exists.

### FUTURE WORK

1. Runtime owner: complete human N01 correspondence and review/freeze the N05 integration source,
   controller image and exact one-attempt authorization; execute N05 only under that authority.
2. MID-03: after a retained N05 PASS, update PR #108's preparation path to verify the actual N05
   host/Linux evidence and parse a complete separate pilot authorization instead of accepting
   digest strings alone.
3. Research/presentation owner: approve or reject the exact 20-cell schedule and resource bounds.
4. MID-03: only then execute cells sequentially, preserve every terminal/prefix state, independently
   verify the final manifest, and generate derived tables/curves from the retained raw root.

Presentation-safe summary for the research lead:

> The final-state comparison machinery and a reproducible 4,000-execution exploratory protocol are
> engineering-tested. Historical five-second readiness and separate pilot authorization are still
> absent, so B0/B1/B3 effectiveness, first-hit and state-growth results remain NOT_EVALUATED. The
> defensible result today is verified experiment readiness plus an explicit execution-gate map, not
> a performance claim.

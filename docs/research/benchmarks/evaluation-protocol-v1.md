# Controlled rediscovery and evaluation protocol v1

**PREDECLARED PLAN — NO HISTORICAL REDISCOVERY OR FORMAL COMPARATIVE RESULTS.**
Capability baseline is main `8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`; definitions
are frozen by the [G0 contract](../design/research-contract-v1.md), not an accepted
main-experiment schedule. B0/B1/B3, A1/A2/A3, journaled full-step timing, explicit
repetition accounting and completed policy evidence/analysis APIs are IMPLEMENTED
and engineering TESTED. Human historical disposition, formal pilot authorization
and known-class adjudication remain prerequisites. No vulnerability is claimed.

**N01 node-tar 7.5.2 / 7.5.3 is the first intended historical qualification pair.**
Other [Set v1](benchmark-set-v1.md) cells/subsets remain conditional. Follow
oracle → harness → fuzzer → synthetic → historical validation → pilot →
experiment freeze before formal runs. This documentation freeze does not execute
PoCs, install historical versions or authorize discovery. [Baselines](baseline-and-ablation-v1.md)
fix the exact executable comparison; apply experiment-validation before promoting raw evidence.

## Experimental unit and independent variables

| Research question | Measurement connection | Interpretation limit |
| --- | --- | --- |
| RQ1 Rediscovery | Confirmed success, censored first-hit index and identical-input affected/fixed replay | Only admitted classes/releases and declared grammar |
| RQ2 Feedback effectiveness | Paired B3 versus B0/B1 success and first-hit summaries | B0 changes overall search policy; B1 isolates violation admission; no path-only/fixed-recipe comparison |
| RQ3 Ablation | A1/A2/A3 versus B3 on declared subsets, common full-state counts | Redundant nlink/fingerprint signals remain; projections preserve security evidence |
| RQ4 Generality | Independently qualified extractor families under the same oracle | No second arbitrary-input family qualified; ORAS absent, GNU benign-only; no generality claim |
| RQ5 Unknown-state discovery | Preserve unrelated contract candidates separately | Exploratory; no new vulnerability or zero-day requirement |
| RQ6 Entry-transition feedback | P0/P1/P2 transition keys, retention and operator-yield metrics | Requires a qualified native completion boundary; transition novelty is not a violation |

State/fingerprint/corpus counts explain search behavior; **more state signatures
!= more vulnerabilities**. Throughput is an infrastructure feasibility metric
including setup/observation, not just target process time.

One campaign = benchmark × exact target version × search policy × RNG seed ×
frozen environment/setup profile. Fresh runtime for each input, new search corpus
for each campaign. The same logical seeds, grammar, dictionary, oracle, setup,
limits and engine commit are used on both versions and all feedback comparisons.
Only target package version changes in a vulnerable/fixed pair. Only declared
search policy changes in a baseline comparison. No corpus is shared across
conditions. Random seed equality does not imply identical evolved inputs:
feedback changes parent pools. Record lineage and actual generated cases.

### Entry-transition extension — NOT_RUN

The generic P0/P1/P2 policy and checksummed evidence reader are **IMPLEMENTED** and
synthetically **TESTED**, but no formal transition campaign is authorized. Pinned
node-tar 7.5.22 `onReadEntry` and entry-stream `end` failed completion-boundary
qualification, so `NATIVE_ENTRY_TRANSITION = NOT_IMPLEMENTED`. Prefix replay is not
used. A future target adapter must prove that each checkpoint follows the completed
filesystem effect before this extension can enter qualification or the schedule.

When that gate is met, run P0 final-state+uniform, P1 transition+uniform and P2
transition+adaptive with the same target/version, initial seed IDs/order, execution
budget, timeout, sentinel, mutation policy/vocabulary, final C0/C1/C2 oracle,
environment and protocol. P1−P0 estimates transition-retention effect; P2−P1
estimates scheduler effect. The existing B0/B1/B3 experiment remains a separate
question and its identifiers or historical results must not be relabeled P0/P1/P2.

Transition evidence retains ordered checkpoints/transitions, final RunResult,
trace completeness/termination, operator attempt, weights before/after, reward and
lineage. Derived metrics include unique transition keys and sequences, novelty rate,
censored executions to first novel transition, per-operator attempts/yield, reward
distribution, mean scheduler weight-distribution entropy, empirical operator-selection
entropy, checkpoint count/time and serialized
checkpoint bytes. Peak memory is currently unavailable and recorded as such. These
metrics explain search behavior; they do not count vulnerabilities.

## Budget, repetition and scheduling

Numeric values below are **proposed planning parameters, not frozen runnable
configuration or measured results**. Freeze only after isolated full-path
qualification, safe throughput/storage/memory evidence and complete experiment binding.
Lock the protocol revision and complete schedule before formal runs. SearchCampaignConfig
supports these policies; legacy ExperimentConfig does not. Numeric values are not execution evidence.

- Qualification pilot: 5 independent seeds 9001–9005, 200 executions per
  admitted condition. Pilot data is separate, never added to formal estimates.
  Establish environment, runtime compatibility, export feasibility and throughput;
  no PoC-derived seeds or guaranteed-hit recipes. A no-hit pilot is inconclusive.
- Formal v1: 20 independent campaign seeds 1001–1020, **1,000 executions per
  campaign, inclusive of all four initial seeds**. The 996 mutation executions
  include deterministic no-ops, repeated cases, safe rejections, target failures
  and timeouts. No replacement mutation, free retries or invalid-input discounts.
- Per-target execution timeout: **5 seconds** for every primary condition,
  with identical CPU/memory/process/filesystem limits and container startup
  accounting within each comparison. Container resource values are taken from
  the audited infrastructure profile, frozen before pilot, and recorded exactly.
  Do not invent an isolation setting that current backend does not implement.
- No search warm-up and no discarded initial steps. Image builds/package fetches
  and one benign operational readiness check per version occur before measurement;
  measure full per-input isolation/setup/observation costs during campaigns.
- Run to the full execution budget even after a candidate hit. Replay and
  adjudication happen afterward with a separate recorded validation budget.
  A host watchdog of 2 hours per campaign detects stalled infrastructure; an
  abort below 1,000 results is incomplete data, never ordinary no-hit censoring.
- Execute one campaign at a time on the chosen host. In each benchmark/RNG block,
  use an explicitly saved schedule shuffled with independent scheduling seed 4242
  to distribute version/policy order; it must not consume campaign RNG.

Use B3 vulnerable/fixed for RQ1/discrimination: 4×2×20 = 160 campaigns.
Add B0/B1 vulnerable only for feedback effectiveness: 4×2×20 = 160 campaigns.
Reuse vulnerable B3 results; do not rerun them for a favorable comparison.
This is 320,000 formal search executions before targeted ablations. Fixed
B0/B1 campaigns are optional extra cells, not required for the primary feedback
question; same-input cross-version replay supplies the stronger discrimination
check. Exact ablation subsets add 100,000 executions (see plan), total 420,000.

At 1 second full-step latency this is about 117 hours serially; a 5-second
all-timeout workload exceeds 24 days before overhead. Pilot median/p95 full-step
latency, rejection/timeout rate, raw bytes and peak memory decide feasibility.
If infeasible, amend the plan **before any formal run** using throughput/resource
facts, e.g. uniformly reduce budget to 500 and defer mutation ablation. Record
old/new version, reason and all scheduled cells. Do not adapt budgets per
benchmark based on pilot hit rate or keep successful formal runs while changing
others. A later 10,000-execution extension, if justified, is a separate protocol
and reports all original no-hit cells, not only promising seeds.

## What counts as rediscovery

A known-class rediscovery requires all of the following:

1. A mutated input generated from the declared benign seeds (seed-phase hit is
   a qualification/setup anomaly, not credited as discovery).
2. Complete generic C0/C1/C2 raw evidence for the candidate's selected effect.
3. The exact input reproduces the matching relation/effect on the vulnerable
   version in **3 of 3 fresh independent replays**, with the same setup.
4. The exact input produces **no matching known-class evidence in 3 of 3
   fresh replays on the selected fixed version**, with equivalent configuration.
5. Human root-cause review links archive semantics, patch behavior and surviving
   effect to the benchmark class; generic oracle never tests CVE/version IDs.

For identity cases N01/N03/O01, persistent C1 is sufficient; C2 metadata is
corroboration, bytes need not change. C2-only nlink/ctime is not automatically
class evidence when the alias no longer exists. For N04 accept protected-file
C2 content/size effect or C0 external namespace effect with matching cache
transition semantics. A harmless internal link, dangling external symlink,
interesting state, nonzero exit, crash or timeout is insufficient. An input
that hits another known class is reported as other-class evidence, not credited
to its scheduled benchmark. No post-extraction application writes are inserted
to manufacture C2.

No rediscovery = complete valid campaign exhausts budget with no subsequently
confirmed matching input. This does not assert absence of the vulnerability.
Ambiguous = flakiness, insufficient root-cause match, incomplete observation or
matching evidence on both selected versions. Preserve all generic violations
and classify separately; a fixed release can still have unrelated known issues.
Infrastructure failure = invalid/missing target pin, configuration drift,
boundary failure, missing observation, export loss, engine exception, host
watchdog or failed cleanup. It is not an extractor security verdict or no-hit.

## False-positive and interpretation flow

```mermaid
flowchart TD
    A[Campaign observation] --> B{Complete contract evidence?}
    B -->|No| C[Interesting state or process outcome only]
    B -->|Yes| D[Preserve exact input and pre/post raw evidence]
    D --> E{Lifecycle and attribution valid?}
    E -->|No| F[Infrastructure invalid; retain reason]
    E -->|Yes| G[Three fresh vulnerable replays]
    G --> H{Matching persistent effect in all three?}
    H -->|No| I[Flaky or ambiguous candidate]
    H -->|Yes| J[Three fresh fixed replays]
    J --> K{Matching class absent in all three?}
    K -->|No| L[Pair ambiguous; inspect configuration and patch match]
    K -->|Yes| M[Human root-cause review]
    M --> N{Known-class match?}
    N -->|Yes| O[Validated benchmark rediscovery]
    N -->|No| P[Other contract finding; separate review]
```

Review actor attribution and observation completeness first: HARNESS writes by
adapters, unmapped container paths, unrelated baseline changes and unfinished
children invalidate interpretation. Inspect actual dev+inode pairs, not inode
alone; distinguish lstat symlink objects from referents; inspect C2 field labels
and values. Ctime-only changes may be real contract evidence but do not prove
bytes changed. Never edit raw results to suppress inconvenient fields.
Interesting observation ≠ violation ≠ rediscovery ≠ new vulnerability. Follow
[SECURITY.md](../../../SECURITY.md) for any unclassified finding; no exploitability
escalation or automatic public disclosure is part of adjudication.

## Exact metrics

Let N=1,000 configured executions, E=number of complete valid RunResults, K=20
scheduled campaigns per cell, V=number of complete infrastructure-valid campaigns,
H=number with a validated matching rediscovery, I=admission-eligible observations
under a variant's declared key/policy, R=retained unique mutation parents. Seeds contribute
to E, I and representation counts; rediscovery hits must be mutation-origin.
Report scheduled/complete/invalid counts beside every aggregate. Let A be
complete campaigns with unresolved/ambiguous candidate classification. Show
confirmed yield H/V as a lower bound and (H+A)/V as a possible upper bound when
A>0; do not report unresolved candidates as confirmed ordinary no-hit. Their
time-to-hit values remain pending, rather than receiving ordinary no-hit censor
labels. Cumulative confirmed-hit fractions include them conservatively as not
confirmed, with unresolved counts shown. Final ordinary censor quantiles require
adjudication completion or an explicit pending-data limitation.

| Metric | Numerator / denominator; unit | No hit / target failure / timeout / infrastructure handling |
| --- | --- | --- |
| Rediscovery success proportion | H/V complete campaigns; also H/K scheduled campaigns as conservative yield; percent and counts | Complete no-hit = 0; returned timeout/failure remains eligible if complete matching evidence; invalid runs excluded from H/V but shown in H/K and reason counts |
| Executions to first confirmed class evidence | 1-based original campaign index of earliest subsequently validated matching case; denominator one campaign; executions | Complete no-hit right-censored at N, reported `>N`; never give it a fictitious hit at N. Invalid truncated campaign separate |
| Time to first confirmed class evidence | Monotonic seconds from first seed pipeline setup through completed return/cleanup of earliest confirmed original step; one campaign | No-hit right-censored at completed campaign elapsed; target timeout costs included. Post-campaign replay/adjudication time excluded and reported separately. Current ExecutionResult.duration_seconds alone is insufficient |
| Unique StateSignatures | Count of distinct full v3 signature values over E; states/campaign; auxiliary count/E states per execution | All returned statuses included; no novelty from missing snapshot. Raw count is not number of bugs and digest/path novelty can inflate it |
| Unique violation fingerprints | Distinct canonical generic fingerprints over E; classes/campaign; auxiliary count/E | No-hit can still have unrelated violations. Values omit effect direction; count is not vulnerability count |
| Corpus growth | R_end − R_after_seed; parents/campaign; auxiliary growth/(E−4) | Report R_after_seed and R_end; fixed-seed policy has zero growing corpus; never compare raw size as effectiveness |
| Admission-eligible observation rate | I/E from SearchDecision.admission_eligible; percent | All seed/no-op/reject/failed/timed-out complete steps; B0 eligibility is zero. Diagnostic interesting is full-state OR fingerprint novelty and is reported separately; neither is effectiveness |
| Repeatability | Successful fresh vulnerable replays / 3 per candidate; full semantic campaign repeats on pilot / scheduled pilot repeats | 3/3 required for confirmation; record each failure; do not demand equal raw inodes/timestamps |
| Paired vulnerable/fixed discrimination | Count of identical candidate inputs with matching vulnerable 3/3 and fixed 0/3 / all deduplicated matching inputs nominated for review; percent | Replay failure or incomplete evidence = unresolved, reported in denominator and category count. Also report per-seed campaign hit/no-hit pairs, with invalid pairs separate |
| Process and infrastructure outcomes | Each returned status count/E; infrastructure-invalid campaign count/K; percentages/counts | Failures/timeouts are not successes by themselves. Keep all statuses and exception reasons; no discounts |

All nomination cases receive deterministic adjudication in ascending original
step order; deduplicate by case_id within benchmark/environment and record all
original occurrences. Earliest confirmed occurrence determines hit index.
If validation resources run out, mark unresolved cases and the campaign
classification pending; never relabel them as no-hit or drop them from tables.

Keep analysis representation counts based on full unablated v3/fingerprints for
all variants, independently of feedback eligibility. Distinguish these common
analysis counts from each policy's own seen-key counts and admission-eligible I/E; full diagnostic interesting is separate. Report diagnostic
throughput E/full campaign seconds, useful bytes retained and malformed/rejected
rate, without ranking effectiveness by archive rejection or raw novelty alone.

## Censoring and summaries

A right-censored no-hit means only “later than the observed budget,” not a
missing observation. Publish every seed's hit/censor flag and index; plot
cumulative confirmed-hit fraction at 100, 250, 500 and 1,000 executions using
all V complete campaigns. Use empirical event-time quantiles over all campaigns:
if the hit fraction never reaches 0.25/0.50/0.75, report that quartile as
`>1,000` / not reached. Do not average or take a median only over successful
campaigns. Conditional successful-run latency may be supplemental and must say
its denominator. For time-to-hit use a descriptive Kaplan–Meier curve with
no-hits censored at actual elapsed time; state independent-censoring limitations
and do not claim significance from differing campaign durations.

Success proportions show counts and 95% Wilson intervals for V complete
independent RNG trials. Seeds are independent pseudo-random trials, not proof
of representativeness beyond this set. Show paired B3−B0/B1 success differences
and discordant seed counts; no significance claim or large multiple-testing
matrix is predeclared. Median/IQR suit complete per-campaign descriptive counts
and throughput. Report benchmarks separately; an optional macro mean gives
each benchmark equal weight and never pools executions across targets.

Record initial incomplete attempts as invalid in a separate ledger. After a
verified infrastructure fix rerun the **whole benchmark/seed comparison block**
under a new dataset revision; archive prior attempts. Published denominators
cannot silently grow until success. Unknown observer/harness exceptions are
triaged before the next run. Cross-host datasets stay stratified unless their
configuration and effects are independently shown comparable.

## Provenance and evidence retention

Before the first run freeze clean InodeFence Git SHA; target source/tag/package
hash, Node or Go compiler version, complete dependency locks; worker command,
options, actual CWD; container image digest/backend version/validated boundary
profile; OS/kernel/architecture; CPU model/count and resource allocation; memory;
filesystem type/mount flags/device relation; uid/gid/umask/protected_hardlinks;
sentinel names/content digest/mode; actual target-visible root mapping; grammar,
dictionary, seed IDs, RNG implementation/seed, policy IDs, budget/timeout;
schedule and protocol/catalog revision hashes; start/end UTC plus monotonic
durations. Environment labels and config IDs alone are not this evidence.

Retain immutable experiment configuration, manifest, all full canonical steps,
inputs/regeneration information and TAR checksums, stdout/stderr, before/after
snapshots, violations, feedback decisions, lineage and failure ledger. Logical
case bytes are available in RunResult; existing legacy/policy readers rebuild the
same TAR and verify its hash. The final-state policy runner exposes a completed-record
boundary; its separate journal durably publishes accessible steps, mutation provenance
and ordinary infrastructure failures, while a hard interruption leaves a verified
non-resumable prefix. The repetition ledger preserves complete, failed, invalid and
STARTED slots without automatic retry. Completed full results remain O(budget); pilot
determines whether memory and export volume fit the limits.
Record immutable shared raw storage URI, SHA-256 manifest for every artifact and
analysis script/source revision. Retain raw data through review and paper
submission; no deletions before maintainer agrees an archival location.

Derived summaries live in experiments/summaries only after validation; empty
[table templates](../../../experiments/benchmarks/result-templates.md) stay
planning. Do not fill paper/ with unvalidated or fabricated numbers.

## Claims this design could support

With successful controlled evidence: representative Linux TAR extraction
filesystem-state violations can be rediscovered from benign seeds; under these
fixed policies, budgets and versions, feedback may improve rediscovery yield or
latency over the specified unretained/state-only baselines; common contracts can
express effects in separately qualified extractor families (none beyond benign Node is established). Declare any M1 extension when
stating these results; do not attribute them to untouched Generic Mutation v1.

It cannot establish universal archive coverage, superiority over all fuzzers,
a zero-day, guaranteed extractor safety, first-ever state fuzzing, actual secret
exfiltration, general race detection, or causal proof of check/use coherence.
No-hit fixed runs support only absence of observed matching evidence in this
budget. B1 is full StateSignature novelty, **not path-only feedback**.
RQ2/RQ3 are defined by B0/B1/B3 and A1/A2/A3. Path-only/fixed-recipe comparisons
are absent and excluded; no superiority over them is claimed.

## Implemented evidence infrastructure and remaining measurement gaps

[PreparedContainer.execute](../../../src/inodefence/execution/container.py) records
target lifecycle duration, including attached start/draining/verified termination.
That excludes TAR building, sentinel setup, container preparation, BEFORE/AFTER,
oracle/feedback, normal cleanup and corpus selection/mutation. No policy step
may substitute this target duration for the protocol's latency definition. The separate
`policy-full-step-monotonic-v1` wrapper records final-state policy campaign origin,
contiguous cleanup/feedback-complete step offsets and final in-memory result completion,
with UTC start/end. When attached to the policy journal, each offset includes synchronous
record verification/publication; final bundle publication remains outside the interval.
Its exporter/reader binds those bytes to the existing policy result/configuration.
Known-class adjudication offsets, compatible timed-dataset aggregation and formal
measurements remain NOT_RUN / unimplemented dependencies.

[Policy journal](../../../src/inodefence/evaluation/policy_journal.py) receives the
completed-record boundary before the next execution, durably preserves each accessible
step and independently replays RNG parent/operator/mutation/feedback. Ordinary exceptions
become infrastructure-invalid journals; hard interruptions leave explicit incomplete
prefixes. [Policy repetition](../../../src/inodefence/evaluation/policy_repeated.py)
binds exact `PolicyEvaluationConfig` cells to durable claims and complete/failed terminal
digests without retrying STARTED slots. The legacy ledger/journal/controller remain separate.
Policy completed-only statistics still cannot infer repetition invalid/STARTED counts;
formal aggregation must join the verified repetition ledger rather than dropping them.
Torn/uncertain evidence and infrastructure errors remain invalid attempts, not no-hit
censoring or extractor nonviolations.

[Policy export/reader](../../../src/inodefence/evaluation/policy_evidence.py),
[configuration binding](../../../src/inodefence/evaluation/policy_binding.py),
[dataset checks](../../../src/inodefence/evaluation/policy_dataset.py) and
[statistics](../../../src/inodefence/evaluation/policy_statistics.py) preserve and
verify completed full raw SearchCampaignResult evidence. They recompute case/TAR,
state, oracle, key/admission/eligible-parent and counters; checksums do not prove
authorship or RNG/proposal execution. Compatibility/clean-source checks precede
pooling; differing policy/target/setup cells remain separate. First observed
C0/C1/C2 indexes and generic hit/censor summaries are **not known-class rediscovery**.

## Replay, qualification and known-class adjudication boundary

[Benign replay](../../../src/inodefence/replay/README.md) verifies exact input/TAR
hashes and runs only the fixed four allowlisted benign cases in fresh runtimes,
retaining real results and failed attempts. [Pair records](../../../src/inodefence/evaluation/pair.py)
preserve caller-produced identical-input results; they do not execute six replays
or classify CVEs. Generic qualification/matrix APIs check linked evidence and
bindings, while assessor assertions require independent verification. Neither the
static catalog nor a structurally valid report qualifies a historical effect.

The generic candidate replay layer can now bind a selected case to verified policy
occurrences and retain the fixed three affected plus three fixed fresh schedule with
complete/failed/interrupted evidence. It has not run against the historical pair. The
versioned [N01 machine reader](n01-candidate-machine-match-v1.md) implements deterministic
mutation-origin relation nomination and the mechanical 3/3 versus 0/3 decision with exact
target/setup checks. Controlled-adapter tests are not historical matching evidence; actual
N01 candidate assessment and human root-cause review remain unexecuted. Candidates must be
selected from all completed raw
steps, irrespective of corpus admission, and tied to original step/index. Each replay must
match its own frozen artifact/config/image, verify fresh lifecycle and retain negative/error
results. Pair invariants are setup/options/runtime/policy, not equality of full config IDs
across versions. No version/CVE match enters the oracle. Benign replay tests and synthetic
verification do not supply historical classification evidence.

All numeric budgets, subsets and confirmation criteria above retain the existing
predeclared plan. This G0 correction reconciles metric terminology with actual
SearchDecision fields; it does not supply results, approve conditional targets
or change budgets after outcomes.

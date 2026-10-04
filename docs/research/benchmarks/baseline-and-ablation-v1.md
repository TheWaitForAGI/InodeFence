# Baselines and ablations v1

**PROPOSED POLICIES, NOT IMPLEMENTED CONFIGURATION.** Current
[Corpus](../../../src/inodefence/feedback/corpus.py) implements only B3;
[ExperimentConfig](../../../src/inodefence/experiment_config.py) rejects alternative
policy IDs. This branch changes neither. Post-audit implementation should expose
one small explicit policy boundary, keeping execution, observation and oracle
identical, rather than copying campaign engines or hiding flags in adapters.

A baseline is a complete alternative search policy. An ablation removes one
specified component to test its marginal contribution. Comparing several CVEs
or several target versions alone is neither a feedback baseline nor an ablation.

## IMPLEMENTED NOW versus REQUIRES FUTURE IMPLEMENTATION

| ID | Implementation at audited main | Configuration representation | Comparison purpose / isolated measurement |
| --- | --- | --- | --- |
| B3 | IMPLEMENTED NOW, trusted reference and exact contained wrapper | Existing `state-v2-or-violation-v1-uniform-parent-v1` with `uniform-generic-v1` | Combined retention control; no measured effectiveness |
| B0 | NOT_IMPLEMENTED | Proposed `unretained-walk-v1`; rejected today | Guided evolving corpus versus unguided multi-step walk; success/censored first-hit; changes parent selection and retention together |
| B1 | NOT_IMPLEMENTED | Proposed `state-v3-uniform-parent-v1`; rejected today | Marginal violation-novelty admission with uniform evolving parents constant; success/censored first-hit |
| B2 | NOT_IMPLEMENTED; optional | Proposed `violation-v1-seed-bank-uniform-parent-v1`; seed-bank comparator revision required | Post-hit violation guidance; not a primary first-hit comparison |
| A1 | NOT_IMPLEMENTED | Proposed `state-v3-no-groups-or-violation-v1-uniform-parent-v1` | Identity-group key contribution only; full evidence/other signals constant |
| A2 | NOT_IMPLEMENTED | Proposed `state-v3-no-effects-or-violation-v1-uniform-parent-v1` | External changed-field key contribution only; object content/C2 constant |
| A3 | NOT_IMPLEMENTED | Proposed mutation `uniform-generic-no-reorder-v1`, same B3 feedback | Swap contribution with its probability slot retained; append/duplicate remain |

B3's accepted `state-v2-or-violation-v1-uniform-parent-v1` is a legacy config
identifier preserved for stable config IDs; its actual state keys are tagged v3.
It promises no v2 key compatibility. Proposed B0/B1/ablation identifiers are not
accepted JSON options. This refresh implements none of them. M1 grammar and
dictionary binding is also NOT_IMPLEMENTED and must be constant in every arm.
No general fresh-archive uniform generator exists beyond four minimal seeds;
one-step-from-seed search would cap depth and is not substituted for B0. Adaptive
scheduling and a path-only key are also absent. Existing `mutate()` is a uniform
operator convenience API; it does not implement an unguided campaign mode.
B0 tests the complete search policy, not a retention-only causal change.

## Smallest useful baseline set

Use B0, B1 and B3 for the formal vulnerable-version feedback experiment.
B0 answers whether feedback-guided retention helps versus unretained search.
B1 answers whether adding violation novelty helps beyond normalized-state
novelty (particularly C0/HARNESS effects that signatures intentionally omit).
B3 is the implemented state OR violation policy. This set does not answer
“identity versus path-only”; signature projections below ask narrower questions.

| Policy | Parent selection after seed phase | Retention and seen-index behavior | RNG and budget |
| --- | --- | --- | --- |
| B0 Unretained random walk | Initially uniformly select one of the four immutable initial seeds; then previous executed child is the next parent, irrespective of status/novelty | No growing corpus; hold only one active child and seed bank. Analysis records full state/fingerprint novelty, but never influences selection or acceptance | Same Random(seed), one initial selection then same uniform mutation API each step; no resets, retries or best-case filtering; 1,000 executions |
| B1 StateSignature novelty only | Uniform over retained unique cases, insertion order and same caller RNG | Admit case iff full v3 signature unseen and case not retained. Update state and violation diagnostic seen indexes on every result; violation novelty never admits a parent | Same seed-phase order, same select→mutate schedule as B3, same budget/no-ops |
| B2 Violation novelty only, optional diagnostic | Uniform over explicit immutable initial seed bank plus later violation-novel unique cases, deduplicated by case_id | Admit mutations only for new generic fingerprints; initial bank required because benign seeds provide no violation parents | Same source RNG and budget; seed bank rule must be explicit and applied to comparison control if B2 enters a formal experiment |
| B3 Full InodeFence | Uniform over Corpus retained cases, insertion order | Admit new case for unseen full v3 state OR unseen fingerprint. Seen indexes always advance; repeated case outcomes can be interesting without adding entry | Existing shared Random(seed), seed-inclusive budget, one selection and mutation per step |

B0 is a walk so multi-step structures can accumulate without feedback. A
one-mutation-from-initial-seed-only search would impose an artificial depth cap;
exclude it as primary. Parent rules necessarily differ; they are part of the
independent search policy, not an accidental implementation difference. B0
advances to rejected/failed child too; validity filtering would give it another
undeclared feedback channel. Report its active working-set size separately
from growing corpus counts; its novelty diagnostic counts never affect search.

B2 has almost no useful pre-violation gradient and needs a seed-bank semantic
exception to current retention. It mostly asks how to explore *after* a hit,
not whether intermediate filesystem state helps reach the first hit. It adds
implementation and interpretation cost, so omit it from the minimal formal set.
If later needed, compare using the same pinned initial bank for all conditions
and version the changed B3 policy; do not call an empty violation-only corpus a
working baseline or silently use state novelty as a bootstrap.

For B1/B3, execute all four benign seeds through the same pipeline before
selection, and use declared novelty retention on their outcomes. Require
nonempty parent pools; log per-seed admission differences. Prefer qualification
showing equivalent seed admissions before comparing feedback; any seed-phase
contract hit invalidates benchmark setup rather than granting B3 a head start.
Do not inject known attack inputs or candidate-specific mutated seed cases.

## Constants and randomness

All baseline cells share engine revision, seed IDs/order, M1 dictionary/grammar,
operator weights, sentinel contents/names/mode, runtime/image options, target
version, observer/oracle, budget, timeout and hardware block. Count no-ops,
rejections, failure and timeout equally, and retain all raw evidence independent
of feedback. B0 may generate different RNG streams because it lacks subsequent
parent-selection calls; equal seeds supply reproducible paired stochastic
trials, **not common identical mutation choices**. Record actual inputs and
lineage. Do not add dummy RNG calls to claim identical streams or seed one arm
from another arm's findings. Separate schedule RNG from campaign RNG.

B3 vulnerable/fixed campaigns run first as the inventory/discrimination layer;
B0/B1 vulnerable campaigns add a paired effectiveness comparison using the
same scheduled seeds. For exact-input vulnerable/fixed behavior, replay identical
generated candidate cases offline after campaigns; evolved streams need not
match between versions. Full fixed B0/B1 cells remain an optional extension.

## Prioritized ablations

All verdicts/raw observations remain unmodified. Project only the key used for
retention. Keep common full v3/fingerprint analysis metrics so count definitions
do not change between arms. Each new key/policy has a new config/provenance ID.
Do not remove evidence from the oracle to make an ablation look effective.

| Ablation / hypothesis | Exact later code/config change | Comparator and subset | Metrics / interpretation |
| --- | --- | --- | --- |
| A1 Identity-group information has marginal search value for composed/CWD aliases | Feedback-only projection replaces signature.identity_groups with empty tuple; preserves objects (including regular nlink), effects, protected paths and violation fingerprints; B3 OR logic unchanged | B3; N03 and O01, seeds 1001–1020, 1,000 each (40,000 added executions) | Rediscovery proportion and censored first-hit index. Tests groups specifically; nlink/C1 fingerprints remain redundant identity signals |
| A2 External-effect labels aid discovery of write-state transitions | Feedback-only projection replaces signature.external_effects with empty tuple; keeps sentinel object data, groups and all C2 fingerprints; B3 OR unchanged | B3; N04, same 20 seeds/budget (20,000 added executions) | Rediscovery and corpus evolution; tests changed-field labels, not removal of all external information |
| A3 Order mutation helps dependency-sensitive discovery | Keep 8-slot uniform operator draw; selected reorder_entries slot returns unchanged case and consumes its usual operator-internal draws, then executes the no-op. Do not redistribute its probability to other operators | B3; N03 and N04, same 20 seeds/budget (40,000 added executions) | Rediscovery and no-op rate; removes swaps while append/duplicate insertion still change relative placement. It is not removal of all order variation |

These are 3 targeted, nonfactorial comparisons, not a combinatorial matrix.
A1/A2 null results may reflect redundancy or digest/path novelty dominating the
key; they do not establish identity/effect information is unhelpful generally.
A follow-up state-only projection against B1 could isolate that masking, but is
not included in formal v1. Inspect each projection's actual seen-key differences
before interpreting performance. These limitations are scientifically relevant,
not reasons to alter data after seeing results.

The B1/B3 baseline already removes violation-novelty admission and doubles as
that component ablation; reuse its data rather than run a duplicate condition.
HARNESS handling stays canonical because excluding HARNESS from C0 would alter
security truth. Hardlink/symlink-disabled campaigns trivially destroy required
benchmark prerequisites and mostly measure zero reachability, so are not useful
primary feedback ablations. No oracle/C3/C4, target-options or PoC-seed ablations.

## Later implementation acceptance

Policy unit checks must establish independent seen indexes, initial bootstrap,
unique-case admission and uniform parents, including same-signature new C0
fingerprints. Use controlled synthetic RunResults and logical mutations, not
vulnerable-target tests, to verify B0 cannot read novelty, B1 cannot admit on
violations alone, B3 matches current behavior, and A1/A2 alter only feedback keys.
Record no-op operator slots/draw consumption for A3. Experiment binding must
reject unsupported policy IDs rather than silently select full feedback.

## Policy seam revalidation after container admission

Reviewed integrated-main Campaign still creates `Corpus()` once, calls `consider(result)`
for each completed seed/child, and calls `select_case(rng)` before mutation.
Contained admission/frozen identity wraps that unchanged search. The smallest
future seam is parent selection plus post-observation admission/diagnostics at
those calls, sharing the existing execute function and evidence steps. B0 also
needs previous-child state, so a retention switch alone cannot implement it.
ExperimentConfig's explicit `feedback_policy` is a suitable versioned binding
point, but the current parser accepts only B3 and has no policy dispatcher.

A concrete model limitation remains: FeedbackDecision.interesting is hardcoded
as state OR violation novelty, and retained as interesting AND not already retained.
B1 cannot truthfully report a new violation while declining admission with this
unchanged value; B0 cannot report diagnostic novelty and zero corpus admission.
Future work must distinguish policy admission from full analysis novelty in a
reviewed decision/evidence representation. Hiding fingerprints, claiming an
unretained child was retained or filtering oracle evidence would corrupt reports.
This requires an explicit model/config/serialization contract, not a copied runner.

B1/B3 retain uniform selection and the same unique-case/insertion/seen rules.
B0's active walk intentionally changes the parent distribution; interpret B0 as
a whole-search comparator, not an isolated retention effect. Require clean and
equivalent seed admissions, log parent pool sizes/admissions, count every returned
status/no-op and keep full raw states for all arms. RNG calls differ after the
seed phase; paired seeds are reproducible blocks, not identical mutated inputs.
Container creation/timeout/cleanup, target options and observer/oracle stay
identical. No policy implementation or alternative config is enabled here.

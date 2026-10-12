# Baselines and ablations v1

Capability baseline: main **`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`**.
The executable comparison is **B0/B1/B3 and A1/A2/A3**. APIs and engineering tests
exist; **effectiveness is not EXPERIMENTALLY VALIDATED**. No historical case has
been rediscovered and no vulnerability is claimed. See [G0 contract](../design/research-contract-v1.md)
for evidence levels, scope and qualification order.

A baseline is a complete alternative search policy. An ablation removes one
specified component to test its marginal contribution. Comparing several CVEs
or target versions alone is neither a feedback baseline nor an ablation.

## Implementation, configuration and evidence

| ID | IMPLEMENTED / configuration at baseline | TESTED evidence | Comparison purpose / interpretation |
| --- | --- | --- | --- |
| B0 | `SearchPolicy.B0`: `unretained-walk-v1` | [search tests](../../../tests/test_campaign_search.py), [reference integration](../../../tests/test_campaign_search_integration.py) | Unguided multi-step walk; changes retention and parent distribution together |
| B1 | `SearchPolicy.B1`: `state-v3-uniform-parent-v1` | Same policy/composition and reference tests | Marginal violation-novelty admission versus B3, uniform evolving parents constant |
| B3 | `SearchPolicy.B3`: `state-v2-or-violation-v1-uniform-parent-v1` | Legacy parity plus policy/reference checks | State key OR violation novelty admission; no measured effectiveness |
| A1 | `FeedbackProjection.A1`: `state-v3-no-identity-groups-key-v1` | [projection tests](../../../tests/test_feedback_projection.py), campaign composition | Identity-group key contribution only; regular nlink/C1 fingerprints remain |
| A2 | `FeedbackProjection.A2`: `state-v3-no-external-effects-key-v1` | Same projection/composition checks | Effect-label key contribution only; object content/C2 fingerprints remain |
| A3 | `uniform-generic-no-reorder-v1` / `uniform-generic-m1-no-reorder-v1` | [mutation ablation tests](../../../tests/test_mutator_ablation.py), campaign composition | Swap contribution; draw-preserving executed no-op, insertion/duplicate remain |

[run_search_campaign](../../../src/inodefence/campaign.py) accepts frozen
`SearchCampaignConfig` with the explicit search/mutation/projection enums.
[PolicyEvaluationConfig](../../../src/inodefence/evaluation/policy_binding.py)
separately binds source/runtime/target/seed/protocol conditions to completed
policy exports. [Policy evidence](../../../src/inodefence/evaluation/policy_evidence.py),
[dataset](../../../src/inodefence/evaluation/policy_dataset.py) and
[statistics](../../../src/inodefence/evaluation/policy_statistics.py) readers exist.
Legacy `ExperimentConfig` v1/v2 still rejects alternative policies and M1; this
is a separate API path, not a missing search implementation or silent fallback.
The policy journal/repeated controller/full-step timing are not automatically
integrated with this path. Completed statistics are contract observations,
not confirmed known-class rediscovery or vulnerability counts.

B3's legacy identifier preserves old config IDs; actual state keys are tagged
v3 with no v2 compatibility. [M1](../design/mutation-m1-v1.md) and its no-reorder
version are implemented, but the finite grammar has no configurable component
dictionary and cannot address the default `outside/sentinel.txt`. A shared,
qualified generation/setup profile is still required before benchmark execution.
B2, adaptive scheduling, a general fresh-archive generator, a path-only key and
fixed-recipe baseline are absent and excluded from this executable comparison.

## Entry-transition causal extension

The following versioned policies are **IMPLEMENTED** and **TESTED** as generic,
in-memory infrastructure. Native node-tar entry observation and formal benchmark
execution remain **NOT_RUN**.

| ID | Retention | Mutation scheduler | Causal comparison |
| --- | --- | --- | --- |
| P0 `final-state-v3-or-violation-v1-uniform-mutation-v1` | final state OR violation novelty | uniform eight-slot vocabulary | final-state control |
| P1 `transition-v1-or-violation-v1-uniform-mutation-v1` | transition key OR violation novelty | same uniform vocabulary | P1−P0: intermediate transition retention |
| P2 `transition-v1-or-violation-v1-adaptive-mutation-v1` | identical to P1 | bounded transition reward | P2−P1: scheduler adaptation |

All three retain final C0/C1/C2 evidence and record full-state, transition and
violation novelty separately. P2 starts weights at 1, caps them at 8 and rewards
only whether an attempt produced at least one new transition key. It does not reward
violations or contain target/CVE recipes. The evaluation reader replays parent and
operator selection before accepting raw evidence. Transition counts are not
vulnerability counts.

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
| B3 Full InodeFence | Uniform over Corpus retained cases, insertion order | Admit new case for unseen full v3 state OR unseen fingerprint. Seen indexes always advance; repeated case outcomes can be interesting without adding entry | Existing shared Random(seed), seed-inclusive budget, one selection and mutation per step |

B0 is a walk so multi-step structures can accumulate without feedback. A
one-mutation-from-initial-seed-only search would impose an artificial depth cap;
exclude it as primary. Parent rules necessarily differ; they are part of the
independent search policy, not an accidental implementation difference. B0
advances to rejected/failed child too; validity filtering would give it another
undeclared feedback channel. Report its active working-set size separately
from growing corpus counts; its novelty diagnostic counts never affect search.

B2 is not implemented and is not a formal v1 comparison.

For B1/B3, execute all four benign seeds through the same pipeline before
selection, and use declared novelty retention on their outcomes. Require
nonempty parent pools; log per-seed admission differences. Prefer qualification
showing equivalent seed admissions before comparing feedback; any seed-phase
contract hit invalidates benchmark setup rather than granting B3 a head start.
Do not inject known attack inputs or candidate-specific mutated seed cases.

## Constants and randomness

All baseline cells share engine revision, seed IDs/order, declared M1 finite grammar/setup vocabulary,
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

| Ablation / hypothesis | Implemented code/key change | Proposed comparator and subset (not qualified/frozen) | Metrics / interpretation |
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

## Engineering acceptance and remaining experiment gates

[SearchState](../../../src/inodefence/feedback/search.py) separates full diagnostic
`interesting = full state OR violation novelty` from policy `admission_eligible`
and projected `feedback_key_novel`. B0 retains no parents even if interesting;
B1 does not admit on a new fingerprint alone; B3 admits on key OR fingerprint.
Do not treat the diagnostic interesting count as a projected-key admission rate.
[Contract tests](../../../tests/test_feedback_search_contracts.py),
[campaign tests](../../../tests/test_campaign_search.py) and
[policy export tests](../../../tests/evaluation/test_policy_evidence.py) cover
these distinctions, parent eligibility, all statuses/no-ops and legacy parity.
Reference integration executes a real safe Python worker. These tests do not
run historical node-tar or establish comparison effectiveness.

The verifier reconstructs raw derivations, keys, admission and valid parent
membership; it does not prove actual RNG/mutator execution. Exact proposal/operator
provenance is not a stored step trace. Completed policy bundles cannot supply
interrupted-attempt counts. Passive legacy journals and repetition/ledger primitives
exist, but automatic policy attachment and full-pipeline timing remain gaps.

The provisional subsets/budgets above retain the existing protocol plan. N01
7.5.2/7.5.3 is the first intended historical qualification; no listed subset is
READY. Freeze admitted cells only after oracle/harness/fuzzer/synthetic validation,
historical qualification and pilot feasibility. Keep full raw observations,
explicit no-hit/invalid denominators and deterministic source/config binding;
never label path-only/fixed-recipe superiority from these comparisons.

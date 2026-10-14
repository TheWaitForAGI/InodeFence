# Entry-associated filesystem-effect feedback v2

## Status and claim boundary

- Design Gate 1: **GO for synthetic implementation only**
- Generic event evidence model: **IMPLEMENTED**, **TESTED**
- Normalized feedback/search/scheduler and caller-owned campaign: **IMPLEMENTED**, **TESTED**
- Synthetic Gate 2: **PASS**
- Native node-tar producer: **IMPLEMENTED**, portable contract tests **PASS**;
  contained Gate 3 suite **10/10 PASS** at clean revision `36ff7fd`
- Independent reader and fixed qualification runner: **IMPLEMENTED**, portable tests **PASS**;
  contained matrix **480/480 completed**, **NOT_QUALIFIED** for replacement coverage
- P0-v2/P1-v2/P2-v2 native campaigns: **NOT_RUN**
- H1/H2 effectiveness: **HYPOTHESIS**, not a result

This contract defines how qualified entry-associated filesystem-effect evidence may become
bounded fuzzing feedback. It does not promote the callback records from qualification v4 to
a native producer. It does not change `TransitionTrace` v1, `RunResult`, C0/C1/C2, or any v1
policy/evidence identifier.

## Research question and hypotheses

**RQ-v2:** Under the same TAR seeds, mutation vocabulary, target and execution budget, does
entry-associated filesystem-effect feedback explore more diverse security-relevant states
and meaningful violation candidates than final-filesystem-state feedback alone?

The question is split before measurement:

- **H1 — Effect feedback retention:** with uniform mutation, does admission by normalized
  effect novelty increase useful state exploration relative to final-state admission?
- **H2 — Effect-adaptive mutation:** with the same effect-retention rule, does bounded reward
  for operators that yield new effect keys improve exploration efficiency relative to
  uniform operator selection?

Neither hypothesis asserts superiority before a qualified, repeated comparison.

## Inputs and evidence eligibility

The normalization input is one `EffectEventTrace` plus its unchanged `RunResult`. The trace
is eligible to change a corpus or scheduler only when all of the following are true:

1. target termination and the terminal AFTER snapshot are present;
2. the event stream is complete and independently integrity-validated;
3. source sequences are unique and contiguous within the declared stream bound;
4. every effect has one exact archive-entry association;
5. every operation start/completion pair has a validated correlation;
6. the flush acknowledgement covers the last accepted source sequence;
7. there is no loss, overflow, malformed identity, association conflict, causal-edge
   validation failure, backend failure or observer failure; and
8. the target completed successfully under the initial v2 feedback policy.

Item 8 is a conservative pre-decision. A completely flushed prefix followed by target
rejection remains raw evidence and a diagnostic, but is not admitted or rewarded until a
separate qualification fixes that policy before a comparison. Timeout and forced
termination are never eligible. Ineligible observations do not update the effect novelty
index; otherwise an invalid trace could consume novelty that a later valid trace should own.

Existing C0/C1/C2 verdicts remain available as independent diagnostics. An observation
failure is not a nonviolation, and an effect key is not a contract violation.

## What counts as an effect

A `FilesystemEffectEvent` represents one correlated operation interval associated with one
archive entry. It records the observed operation and may claim one of these generic effect
classes only to the evidence level established by the producer:

| Effect class | Minimum evidence for a successful realized-effect key |
| --- | --- |
| namespace creation | relevant path observed absent before and present after the correlated operation |
| namespace removal | relevant path observed present before and absent after |
| namespace replacement | same path observed with a different object identity or object type across the operation |
| regular-file content modification | qualified before/after content evidence differs; callback success alone is insufficient |
| truncation | qualified size/content evidence establishes truncation; open flags or callback success alone are insufficient |
| metadata modification | a declared metadata field differs in qualified before/after evidence |
| symlink creation | absent-to-symlink evidence plus retained raw link text |
| hardlink identity relation creation | source and destination post-evidence have equal actual `(st_dev, st_ino)`, with the destination relation absent before |
| identity relation removal | a previously evidenced relation is absent afterward, with removal/replacement evidence that excludes a mere missing observation |

`open`, `write`, `rename`, `link`, or another callback returning successfully is an observed
operation result. It is not, by itself, proof of the corresponding complete object-state
change. Operation-only records stay in raw evidence and coverage accounting but do not
produce successful realized-effect keys. Failed operations retain a bounded normalized
outcome for diagnostics; they are not realized effects under the initial admission policy.

The producer must declare its coverage by operation/effect class. Absence of an event means
only “not observed by this declared mechanism,” never “the effect did not occur.”

## Three independent orders

The model never collapses these relations:

1. **Archive order** is the ordinal order of immutable `ArchiveEntryReference` values.
2. **Observed order** is the global source sequence assigned to lifecycle records and to
   operation start/completion observations.
3. **Supported causality** is a separately validated directed acyclic graph whose edges name
   their evidence kind and raw evidence reference.

Timestamp proximity, equal path strings, archive ordinal, callback delivery order, and a
post-run sort do not create causal edges. Sorting effect records by archive ordinal is
forbidden for derivation and serialization. If independent operations settle in either
order, the trace preserves the observed order but the feedback key does not reward the
permutation.

## Finite normalization vocabulary

The feedback projection uses only finite enums and bounded sets:

- trigger entry type: existing `EntryType`;
- ordinal class: `first` (0), `early` (1–3), `late` (4+);
- generic effect class: the nine declared classes above;
- affected path-role regions: ordered source/destination roles, each mapped to existing
  `EXTRACTION`, `HARNESS`, or `EXTERNAL`;
- protected marker: whether an affected external path is a declared protected path;
- identity relation: `none`, `same_object_created`, `same_object_removed`, with the ordered
  member-region classes retained;
- operation outcome: `succeeded`, `already_exists`, `not_found`, `access_denied`, `invalid`,
  `other_error`; raw error codes remain evidence only;
- evidence strength: `operation_result`, `identity_verified`, `state_change_verified`;
- causal edge kind: the qualified finite edge vocabulary in the architecture contract; and
- archive relation between motif endpoints: `same_entry`, `earlier_to_later`, or
  `later_to_earlier`.

The projection excludes exact path strings, raw device/inode numbers, timestamps, source
sequence numbers, process/runtime IDs, operation correlation IDs, archive hashes, target
version, source hashes and CVE identifiers. These values remain in the trace.

The finite key universe follows from finite enums, a maximum path-pair arity of two, a
unique per-entry set rather than unbounded multiplicity, and motifs limited to one qualified
causal edge between two normalized endpoints. Trace length and event count cannot create an
unbounded new key dimension.

## Feedback units

`EffectFeedbackKey` v2 has three tagged variants. A campaign uses the union of their unique
values; occurrence counts and delivery positions are diagnostics only.

### 1. Individual normalized realized effect

This unit retains the trigger entry type/ordinal class, effect class, path-role regions,
protected marker, identity-relation class, normalized outcome and sufficient evidence
strength. Multiple callbacks that normalize to the same effect contribute one key.

This is the minimum security-state-connected unit. It can represent, for example, a
verified hardlink relation between EXTRACTION and EXTERNAL without retaining either path or
inode value.

### 2. Per-entry normalized effect relation

This unit is the sorted unique set of individual realized-effect signatures caused by one
entry, paired with the entry type and ordinal class. It preserves combinations such as
“hardlink relation creation followed by replacement work for the same logical entry” while
discarding callback multiplicity and same-entry delivery order.

The set is bounded by the finite individual-signature universe. Empty and operation-only
sets do not produce a key.

### 3. Bounded causal motif

This unit represents one validated causal edge between two normalized realized-effect
endpoints. It retains the edge evidence class and coarse archive relation, not raw IDs,
timestamps, paths or sequence distance. Examples that can become keys only with the stated
evidence are:

- an identity-provenance edge into hardlink relation creation;
- a qualified dependency from shared-object creation to later replacement;
- a descriptor-provenance edge from object opening/creation work to later data/metadata
  effect work; and
- a qualified cross-entry dependency.

Overlap without a supported causal edge is not a dependency motif. A diagnostic
`overlap_without_known_dependency` count may measure instrumentation scheduling, but it is
excluded from admission and reward. Thus parallel completion-order permutations cannot
dominate novelty.

## Event novelty versus state novelty

The primary feedback value is a **set of normalized semantic keys**, not an event sequence
hash. It deliberately makes these traces feedback-equivalent:

- the same verified effects delivered in different orders without causal edges;
- one write represented by one callback versus several callbacks when both establish the
  same bounded effect class;
- different exact paths in the same region with the same protected relation; and
- different inode allocation, timestamps, runtime IDs, target versions or source IDs.

It deliberately distinguishes a final-state collision when qualified intermediate evidence
differs, such as creation and later removal versus no realized effect, or hardlink identity
creation and later replacement versus an independent final object. This distinction is the
subject of H1, not proof that the former case is vulnerable.

Qualification must repeat the same fixture under `minimal` and `full` observation and
report key-set stability. Keys attributable only to scheduling-distribution changes block
native qualification or require a pre-registered normalization amendment; they are not
silently accepted as useful novelty.

## Independent result channels

Every search decision preserves three noninterchangeable outcomes:

- `interesting`: at least one policy-relevant novelty channel fired;
- `contract_violation`: existing C0/C1/C2 violation fingerprints are present; and
- `observation_failure`: trace integrity or observation semantics failed.

An observation failure makes the step admission-ineligible. `interesting` never implies
`contract_violation`, and a violation candidate is not automatically a vulnerability.

## Retention policies

These identifiers are new and must be serialized exactly:

| Arm | Policy ID | Admission | Operator selection |
| --- | --- | --- | --- |
| P0-v2 | `final-state-v3-or-violation-v1-effect-observation-v2-uniform-mutation-v1` | unseen final `StateSignature` v3 OR new existing violation fingerprint | uniform |
| P1-v2 | `effect-feedback-v2-or-violation-v1-uniform-mutation-v1` | unseen eligible `EffectFeedbackKey` v2 OR new existing violation fingerprint | uniform |
| P2-v2 | `effect-feedback-v2-or-violation-v1-adaptive-mutation-v1` | exactly P1-v2 | bounded effect reward |

All three arms execute the same qualified full instrumentation and pay its cost. P0-v2
computes and records effect keys but ignores them for admission. This keeps H1 about the
retention variable rather than observer overhead. Parent selection remains uniform over
retained cases in all arms.

Duplicate case IDs are not retained twice. Final-state, effect-key and violation novelty
indices are independent and are all reported in every arm.

## Effect-adaptive scheduler

P2-v2 reuses the existing stable eight mutation operator IDs and bounded integer mechanism,
but uses new v2 evidence types and policy IDs. Every operator starts at weight 1 and is
capped at 8. One eligible attempt that yields one or more previously unseen effect keys
gives binary reward 1 to the selected operator; the number of new keys cannot amplify the
reward. No new key gives reward 0.

Violation novelty, final-state novelty, callback count, execution speed, overlap count and
failed/incomplete streams never change weights. P0-v2/P1-v2 use uniform weights. An
inapplicable mutation remains one recorded attempt with `applied=false`.

## Closed-loop causal evidence

For each mutation step, immutable evidence must bind:

```text
parent TAR A result
  -> validated EffectEventTrace
  -> exact derived EffectFeedbackKey set
  -> novelty decision and admission
  -> retained-parent selection
  -> scheduler weights before/operator draw
  -> mutation attempt and child TAR B case ID
  -> scheduler reward and weights after
  -> TAR B execution
```

The campaign records random seed, mutation policy/operator, parent/child IDs, full key
derivation input, novelty decision, scheduler evidence, target result and provenance. “A
new effect appeared” and “that novelty affected the next choice” are separate claims; only
the complete chain supports the second.

## Fair comparison and metrics

P0-v2/P1-v2/P2-v2 use identical initial cases, mutation vocabulary, seed-inclusive execution
budget, target/options, timeout, runtime/sentinel layout, instrumentation profile and
qualification revision. Comparisons report all statuses and preserve failures/timeouts.

At minimum report unique final states, unique effect keys by variant, unique violations,
corpus growth, per-operator attempts/yield/reward, first-novel observations with censoring,
full-pipeline duration and serialized evidence size. Target duration is not substituted for
full-pipeline cost. Formal H1/H2 analysis requires repeated frozen runs and is outside the
synthetic implementation gate.

## Failure and qualification contract

Any event loss, sequence gap/duplicate, bound overflow, association conflict, invalid
identity evidence, unsupported effect claim, cyclic/unsupported causal edge, incomplete
flush or source/reader disagreement fails closed. The raw record and reason are retained;
no effect novelty is consumed, no corpus admission occurs, and no scheduler reward is
issued.

Native feedback work is authorized only after the separate qualification reports exactly:

- `V2_NATIVE_EFFECT_OBSERVATION_QUALIFIED`, or
- `V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`.

The first value authorizes campaign integration, not an effectiveness claim. The second
blocks native P0-v2/P1-v2/P2-v2 execution while preserving synthetic engineering tests.

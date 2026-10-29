# Entry transition model and normalized feedback v1

## Status

- Generic checkpoint/transition model: **IMPLEMENTED**, **TESTED**
- Synthetic file → hardlink → replacement sequence: **TESTED**
- Native node-tar entry completion observation: **NOT_IMPLEMENTED** after public/OS/private
  snapshot and causal-effect qualification failures
- Transition novelty/retention core: **IMPLEMENTED**, **TESTED**
- Adaptive scheduling core: **IMPLEMENTED**, **TESTED**
- Boundary-approach gradient (`TransitionBoundaryProximity`,
  `feedback.transition_gradient`): **IMPLEMENTED**, synthetic **TESTED**; not wired into
  any campaign (gated on a native entry-completion boundary)
- Checksummed evaluation config/export/reader/replay verifier/metrics: **IMPLEMENTED**, **TESTED**
- Effectiveness or benchmark result: **NOT_RUN**, **HYPOTHESIS**

This document defines target-independent evidence. It does not claim that an
extractor exposes a usable entry-completion boundary or that transition feedback
improves search.

The pinned node-tar public events were separately investigated and rejected as
completion boundaries. See
[entry-transition-observation-v1.md](entry-transition-observation-v1.md).

## Evidence model

`ObservationPoint` composes a static `BEFORE` or `ENTRY_BOUNDARY` kind with an
optional `ArchiveEntryReference`. The reference always includes archive ordinal,
raw path, entry type and link target. Duplicate paths therefore remain distinct.
Dynamic ordinals are not added to the legacy `SnapshotPhase` enum.

`EntryCheckpoint` records the checkpoint index, point, complete lstat object set,
protected paths, monotonic capture interval and explicit observation completeness.
Raw device/inode/timestamp values remain evidence. An incomplete checkpoint cannot
produce a `FilesystemTransition`.

`FilesystemTransition` links consecutive checkpoint indices and retains exact
`StateChange` values plus identity-group creation/removal, external effects and the
protected subset. `compare_states(BEFORE, AFTER)` keeps its legacy invariant;
`compare_observations` is the separate dynamic API.

`TransitionTrace` contains one complete BEFORE checkpoint, every completed entry
checkpoint, exact consecutive transitions, the independent final AFTER snapshot,
expected entry count, termination and completeness. A complete trace requires all
archive ordinals and semantic reconciliation between its final checkpoint and AFTER.
An incomplete trace preserves its completed prefix and never invents an empty edge.

`TransitionRunResult` composes an unchanged `RunResult` with a trace. It verifies
ArchiveCase ordinal/path/type/target mapping and final evidence correspondence.
Legacy `RunResult` serialization is unchanged.

## Normalized representation

`TransitionSignature` schema v1 includes:

- trigger entry type and bounded ordinal class (`first`, `early`, `late`)
- object creation/deletion/type/identity/link-count/mode/content/symlink-field classes
  by EXTRACTION/HARNESS/EXTERNAL region
- identity-group creation/removal as ordered region relations
- external change-field classes
- structural flags for outside namespace transition, new internal↔external identity
  relation and protected external effect

It excludes exact paths, raw device/inode values, timestamp values, runtime IDs,
archive hashes, process timing, target/version and CVE identifiers. Change-field
labels such as `mtime_ns` may remain as effect categories; their raw values do not.
Repeated equal structural effects preserve multiplicity.

`TransitionFeedbackKey` represents one transition. `TransitionSequenceKey` preserves
the ordered full trace as auxiliary evidence only. V1 parent admission will use the
bounded set of unique individual keys rather than every growing prefix sequence.

## Independent novelty and retention

`TransitionNoveltyIndex` owns a distinct seen set. One observation returns the
ordered first occurrence of every previously unseen `TransitionFeedbackKey` and a
separate `transition_novel` flag. It does not read final-state novelty or oracle
verdicts. Repeated keys inside one trace count once. Completed transitions from an
explicitly incomplete trace remain evidence; trace completeness and termination are
preserved in the search decision and never rewritten as success.

`TransitionSearchDecision` reports these channels independently:

- `new_transition_keys` / `transition_novel`
- `full_state_novel`
- `new_violation_fingerprints`
- policy admission and duplicate-case retention
- trace completeness and termination

Transition novelty means only a previously unseen normalized transition class. It
is not a vulnerability, contract violation or finding.

Three causally separated policies are independently executable through the in-memory
`run_transition_campaign` core:

| Policy ID | Parent admission | Parent/operator selection |
| --- | --- | --- |
| `final-state-v3-or-violation-v1-uniform-mutation-v1` (P0) | unseen final StateSignature v3 OR new violation fingerprint | retained parents uniform; existing uniform mutation policy |
| `transition-v1-or-violation-v1-uniform-mutation-v1` (P1) | unseen TransitionFeedbackKey OR new violation fingerprint | retained parents uniform; same existing uniform mutation policy |
| `transition-v1-or-violation-v1-adaptive-mutation-v1` (P2) | same transition/violation rule as P1 | retained parents uniform; bounded transition-reward scheduler |

P0 mirrors existing B3 full-key admission and uniform parent RNG behavior without
changing B3 or its ID. P1 replaces only the final-state admission channel with
transition-key admission; the violation channel is common. Full final-state and
violation diagnostics remain recorded under all three policies.

P2 keeps P1 admission unchanged. Its operator scheduler starts every stable
operator at weight 1, gives one bounded reward when an attempt yields any new
transition key and caps weights at 8. Violation novelty is diagnostic only and
does not change weights. Exact selection and evidence semantics are defined in
[transition-mutation-scheduler-v1.md](transition-mutation-scheduler-v1.md).

The campaign accepts a caller-owned `TransitionRunResult` producer because no native
target adapter is qualified. The separate `TransitionEvaluationConfig` and evidence
bundle preserve this boundary: they passively export a completed result, verify every
final RunResult/provenance binding, and replay parent selection, mutation dispatch,
novelty and scheduler evidence. They do not execute a target, bypass the contained
campaign gate or qualify an entry boundary. The synthetic producer tests causal
policy composition and evidence ingest only.

Derived summaries record unique keys/sequences, novelty rate, first-novel censoring,
operator attempts/yield/reward, mean scheduler weight-distribution entropy, empirical
operator-selection entropy and checkpoint cost. Serialized
checkpoint bytes are an evidence-size measure; peak memory is explicitly unavailable.
Cross-run statistics require identical controls and group only by explicit P0/P1/P2
policy ID. A transition count remains distinct from a vulnerability count.

## Security meaning

Intermediate transitions are transition evidence and may expose transient
security-relevant state. They are not C0/C1/C2 verdicts. Existing final BEFORE/AFTER
oracle evaluation remains authoritative for the current persistent contracts.

## Extension boundary

The model and normalization import no node-tar code. A target adapter may report a
proven completion boundary, while the generic observer captures filesystem state and
the generic feedback layer derives keys. Future observers may replace full snapshots
without changing the target event or normalized feedback contracts.

## Boundary-approach gradient (additive, pre-wired for a native boundary)

`TransitionSignature` records three *unordered* structural flags, so transition
novelty admission answers only "is this transition class new?". It cannot order two
intermediate sequences by how close each came to a boundary violation, and the final
BEFORE/AFTER C0/C1/C2 oracle is likewise all-or-nothing. That missing ordering is the
documented ceiling on adaptive search: a refused escaping attempt that never realizes a
violation is indistinguishable from an input that never approached the boundary.

`feedback.transition_gradient` adds one comparable rung per transition and the closest
rung a whole trace ever reached. It is the transition-path analogue of the effect-path
`boundary_attempt_keys`/`external_resolve_keys` rungs, derived from the richer per-entry
transition signal rather than a single final/rejected effect trace.

`TransitionBoundaryProximity` (ascending severity):

| Rung | Meaning (the realized-violation shape it matches) |
| --- | --- |
| `none` | only extraction-region effects, or no change |
| `external_namespace` | a namespace field changed on a path outside `extract/` (the C0 shape) |
| `cross_boundary_identity` | a newly created identity group spans EXTRACTION and EXTERNAL (the C1 shape against any external object) |
| `protected_effect` | a declared protected external path changed (the realized C2 shape) |

`transition_proximity(transition)` returns the maximum rung whose condition holds;
`transition_proximities(trace)` returns the ordered per-transition rungs (diagnostic);
`trace_proximity(trace)` returns the max over transitions — the single comparable
gradient value for a trace. Each rung reuses the exact region/field classification
already proven in `transition_signature`, so no new judgment semantics are introduced.

The rung is target-agnostic: it is derived only from `Region` classes, `ChangeField`
categories and the declared-protected marker in the generic model — never a concrete
path, raw device/inode value, timestamp, sentinel, CVE or PoC. It is transition
evidence, never a C0/C1/C2 verdict and never a vulnerability.

### Integration path when a native entry-completion boundary arrives

The derivation consumes only the generic `FilesystemTransition` / `TransitionTrace`,
which is exactly what a qualified entry-completion boundary already produces through the
generic observer. No target-specific code is involved, so the same signal applies to a
second extractor that exposes per-entry checkpoints (the generality lane's adapter).
The wiring, when that boundary is qualified, is additive and leaves every existing
channel unchanged:

```text
adapter entry-completion boundary (target-agnostic EntryCheckpoint producer)
  -> generic observer per-entry checkpoints
  -> derive_transition -> FilesystemTransition sequence (unchanged)
  -> transition_signature / TransitionFeedbackKey  (admission, UNCHANGED)
  -> trace_proximity -> TransitionBoundaryProximity (NEW: ordered reward signal)
```

- **Admission** stays the existing unseen-`TransitionFeedbackKey`-or-violation rule. The
  gradient does not change what is retained, so H1 (retention) stays about the key.
- **Reward** gains the gradient: the P2 bounded scheduler may reward a child whose
  `trace_proximity` rank is strictly greater than its retained parent's, i.e. its
  intermediate sequence got closer to the boundary. Reward stays bounded and binary
  (one step reaching a strictly higher max rung), never scaled by rung count, so the
  existing cap/weight mechanism is unchanged. This is the first monotone gradient the
  adaptive search receives; it is a search signal, not a verdict.
- The `trace_proximity` scalar is finite (four rungs) and introduces no unbounded key
  dimension, so the fair-comparison and finite-normalization guarantees hold.

Until a native entry-completion boundary is qualified, this module is dormant: nothing
in any live campaign consumes it, and admission/reward behavior is byte-for-byte
unchanged. Enabling the reward channel is a pre-registered scheduler amendment under the
same gate as the rest of this contract, flagged for human review wherever it ships.

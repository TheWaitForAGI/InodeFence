# Entry transition model and normalized feedback v1

## Status

- Generic checkpoint/transition model: **IMPLEMENTED**, **TESTED**
- Synthetic file → hardlink → replacement sequence: **TESTED**
- Native node-tar entry completion observation: **NOT_IMPLEMENTED** after qualification failure
- Transition novelty/retention core: **IMPLEMENTED**, **TESTED**
- Adaptive scheduling core: **IMPLEMENTED**, **TESTED**
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
target adapter is qualified. It is in-memory engineering infrastructure, not an
ExperimentConfig/export/formal runner and does not bypass the existing contained
campaign gate. The synthetic producer is used to test causal policy composition.

## Security meaning

Intermediate transitions are transition evidence and may expose transient
security-relevant state. They are not C0/C1/C2 verdicts. Existing final BEFORE/AFTER
oracle evaluation remains authoritative for the current persistent contracts.

## Extension boundary

The model and normalization import no node-tar code. A target adapter may report a
proven completion boundary, while the generic observer captures filesystem state and
the generic feedback layer derives keys. Future observers may replace full snapshots
without changing the target event or normalized feedback contracts.

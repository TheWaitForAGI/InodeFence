# Entry transition model and normalized feedback v1

## Status

- Generic checkpoint/transition model: **IMPLEMENTED**, **TESTED**
- Synthetic file → hardlink → replacement sequence: **TESTED**
- Native node-tar entry completion observation: **NOT_IMPLEMENTED** after qualification failure
- Transition retention/adaptive scheduling: **NOT_RUN** in this model PR
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

## Security meaning

Intermediate transitions are transition evidence and may expose transient
security-relevant state. They are not C0/C1/C2 verdicts. Existing final BEFORE/AFTER
oracle evaluation remains authoritative for the current persistent contracts.

## Extension boundary

The model and normalization import no node-tar code. A target adapter may report a
proven completion boundary, while the generic observer captures filesystem state and
the generic feedback layer derives keys. Future observers may replace full snapshots
without changing the target event or normalized feedback contracts.

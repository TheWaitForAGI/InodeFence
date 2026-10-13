# Partial-order filesystem-effect observation v2

## Status and authority

- Design status: **GATE 1 REVIEWED TASK CONTRACT**
- Generic v2 evidence model: **IMPLEMENTED**, **TESTED synthetically**
- Native v2 producer: **IMPLEMENTED**, portable contract tests **PASS**; contained fixture
  execution **NOT_RUN** at this revision
- V2 feedback key, retention and scheduler policy: **IMPLEMENTED / TESTED synthetically**
- Qualification and target campaign: **NOT_RUN**
- Current v1 model: unchanged; it remains the synthetic tested contract

This document is the native-observation qualification contract required after node-tar
7.5.22 failed the archive-ordered checkpoint feasibility gate. The generic architecture and
normalization semantics are defined separately in
[entry-effect-architecture-v2.md](entry-effect-architecture-v2.md) and
[entry-effect-feedback-v2.md](entry-effect-feedback-v2.md); their audit and executable work
plan are in [entry-effect-design-review-v2.md](entry-effect-design-review-v2.md). This
document does not replace
[TransitionTrace v1](transition-feedback-v1.md), qualify the v4 probe as a producer or
authorize P0/P1/P2 effectiveness claims.

The Gate 3 implementation uses a separate source-guarded node-tar worker. It records one
bounded global sequence across entry lifecycle and filesystem-operation start/completion
records, retains class-specific lstat/content evidence when stable, and emits one terminal
stdout frame with a record digest and synchronous-write marker. The controller binds the
producer, package lock, bundled entrypoint and readable unpack source, verifies the terminal
frame after target termination, and records that result before capturing AFTER. The exact raw
frame and the derived `EffectRunResult` can be exported with checksums and no overwrite.

Portable tests exercise framing, evidence conversion and fail-closed errors. They do not
qualify real node-tar coverage or perturbation. The mandatory contained fixture suite is
`validate-node-effect-producer`; it remains NOT_RUN until executed through the host broker
with a freshly built immutable target image. Independent reading and the 20-repeat profile
matrix remain Gate 4.

## Why a separate model is required

`TransitionTrace` v1 is a total sequence:

```text
BEFORE → entry 0 checkpoint → entry 1 checkpoint → ... → AFTER
```

Every checkpoint must be a complete archive-prefix state. The associated transition is
the exact tree delta attributed to that archive ordinal.

The retained node-tar qualifications establish different observed facts:

- archive entries are read in header order;
- independent filesystem work overlaps;
- effect completion and callback observation can be out of archive order;
- later-ordinal namespace/data operations can complete before an earlier entry marker;
- directory metadata in another extractor can be deferred until global close; and
- a tree walk while work is active can be inconsistent or include later effects.

Relabelling an out-of-order callback as an archive-ordered checkpoint would make the v1
trigger false. Sorting events after execution would also invent states that did not occur.
The alternative therefore records observed effects and their supported ordering relations,
rather than pretending that every entry owns one complete state transition.

## Proposed evidence model

The names below are design vocabulary, not committed Python APIs.

### Entry reference

`ArchiveEntryReference` remains reusable. It preserves exact ordinal, raw path, entry type
and link target, including duplicate paths. Archive order is a relation over these immutable
references and is never inferred from completion order.

### Entry lifecycle event

An `EntryLifecycleEvent` records one adapter-observed lifecycle fact:

- contiguous source event index;
- exact `ArchiveEntryReference`;
- lifecycle kind such as `READ`, `EFFECT_WORK_STARTED`, `EFFECT_WORK_SETTLED`;
- capture interval on one monotonic clock;
- success/error observation supplied by the target integration; and
- exact source mechanism/version identity.

`EFFECT_WORK_SETTLED` means only the qualified target hook's work-set meaning. It is not a
tree checkpoint and does not imply that earlier ordinals settled first.

### Filesystem effect event

A `FilesystemEffectEvent` records one start/completion-correlated, causally associated
operation:

- distinct global start/completion source indexes and monotonic observation intervals;
- exact associated `ArchiveEntryReference`;
- generic effect class: namespace create/remove/replace, data write/truncate, metadata
  change, symlink create or hardlink identity creation;
- sandbox-relative affected path or path pair;
- success/error result;
- available object identity evidence before/after the operation; and
- target-specific raw record retained outside the normalized key.

An adapter must not promote an operation callback to a realized generic effect class when it
cannot establish that class's required identity/state evidence. Operation-only records may
remain raw evidence but cannot produce successful effect feedback. Missing path, entry
association, correlation or result is an observation failure, not an `unknown` success
event. Exact evidence sufficiency is fixed in the feedback contract.

### Observation frontier

An `ObservationFrontier` is an optional consistency-checked whole-sandbox snapshot anchored
to an event interval. It records the set of lifecycle/effect event indexes known delivered
at capture start and finish and whether the namespace changed during capture.

A frontier is not assigned to one entry. If work overlaps the capture, the frontier is
incomplete and cannot create a state-delta feedback key. The terminal AFTER remains the
existing stopped-target `StateSnapshot` and retains current C0/C1/C2 meaning.

### Partial-order trace

An `EffectEventTrace` contains:

- one existing BEFORE snapshot;
- archive entry references in header order;
- entry lifecycle events;
- filesystem effect events;
- optional observation frontiers;
- one existing terminal AFTER snapshot;
- explicit stream completeness, termination and observation failures; and
- source/protocol/configuration identity.

It preserves three orders separately:

1. **Archive order**: header ordinal relation.
2. **Observed event order**: the contiguous global source sequence across lifecycle records
   and operation start/completion points.
3. **Supported causality**: an operation was started within an entry's propagated context,
   or a file descriptor/object handle was created by such an operation and used later.

Wall-clock proximity, callback receipt order, archive ordinal and equal paths do not create
extra causal edges. A target-specific reservation dependency may be retained as raw evidence
but cannot enter the generic graph until separately qualified. The finite initial edge
vocabulary and evidence rules are defined in the architecture contract.

## Completeness and failure rules

The event transport must be lossless within a declared bound. Sequence gaps, duplicate
sequence numbers, buffer overflow, malformed identities, association conflict, out-of-order
flush acknowledgement or target exit before evidence flush make the trace invalid.

The adapter records target success, rejection, failure and timeout separately from observer
or backend failure. Rejection after completed effects retains those raw events and the final
AFTER snapshot; it is never rewritten as success. A timeout or forced termination records
which evidence was flushed and marks the stream incomplete.

For the first v2 qualification, incomplete or invalid traces are never eligible for corpus
admission or mutation reward. The initial feedback contract also makes a completely flushed
prefix ending in target rejection ineligible. Any later change requires qualification and a
pre-registered contract revision before a comparison run.

Final reconciliation does not require replaying effect events into the terminal tree: the
events may omit unqualified operation classes and concurrent effects need not form a serial
state history. It does require that every claimed successful namespace/object effect is
compatible with retained raw evidence and that contradictions are explicit validation
failures.

## Security and feedback boundary

Existing C0/C1/C2 continue to use BEFORE/AFTER and are unchanged. Effect events are
intermediate observation evidence, not persistent Security Contract verdicts.

V1 `FilesystemTransition`, `TransitionFeedbackKey`, policy IDs P1/P2 and their evaluation
schemas cannot consume v2 traces. `EffectFeedbackKey` v2 and the new P0-v2/P1-v2/P2-v2
identifiers normalize effect classes, entry type/ordinal class, path region, identity
relation and bounded evidence-supported causal motifs while excluding raw inode values,
timestamps, target/version and exact paths. Novelty, violation and observation-failure
channels remain separate.

P0 final-state behavior is reused only behind the new P0-v2 policy ID and the same qualified
v2 instrumentation. The existing P1/P2 results/export names must not be used for v2 because
their retention and reward inputs are `TransitionFeedbackKey` v1.

## Native v2 qualification Task Contract

### Current Layer

Target-specific observation feasibility and evidence validation. No search-effectiveness
work is in scope.

### Objective

Produce a loss-detecting, source-guarded `EffectEventTrace` from the same complete TAR and
the existing node-tar 7.5.22 `tar.x({strict: true, preservePaths: false})` invocation, then
determine whether its event meanings and instrumentation cost are stable enough to support
a separate feedback design.

### Inputs and outputs

Input is an `ArchiveCase`, deterministic USTAR bytes, isolated target binding, BEFORE state,
sentinel layout and explicit event bound. Output is a raw v2 trace plus the unchanged
`RunResult`. No `TransitionRunResult` or v1 key is produced.

### Allowed changes

- new generic v2 evidence types and strict serialization/reader validation;
- node-tar source-guarded event production inside the target adapter/worker;
- bounded IPC or post-exit evidence transfer with sequence/loss/flush proof;
- qualification scripts, controlled fixtures, tests and evidence documentation; and
- new v2 design/evaluation identifiers.

### Prohibited changes

- weakening or reinterpreting `TransitionTrace` v1;
- changing C0/C1/C2, `RunResult` or legacy serialization;
- putting node-tar/version/CVE conditions in generic observer, oracle or feedback code;
- serializing node-tar work or changing extractor options to manufacture archive order;
- using prefix replay or per-member extraction as native full-execution evidence; and
- rewarding an incomplete, lossy or malformed event stream.

### Mandatory fixtures

Use the v4 regular, directory-metadata, hardlink-identity, symlink, duplicate-path,
directory-child, independent-files and partial-rejection fixtures. Add controlled timeout,
event-buffer overflow, missing event, duplicate event, malformed identity, association and
operation-correlation conflict, invalid causal edge and evidence-flush interruption cases.
The fixed `stock`, `minimal` and `full` profiles need at least 20 repetitions for every
normal fixture.

### Acceptance criteria

All of the following must pass before a native producer can supply feedback or campaign
integration:

1. The same complete TAR follows the existing contained target path with exact target and
   source hashes.
2. Every entry lifecycle and claimed effect has exact ordinal/path/type/link-target
   association, including duplicate paths.
3. Operation coverage for the declared effect vocabulary is demonstrated for regular data,
   link identity, symlink, replacement, directory metadata and failure cleanup.
4. The global lifecycle/operation-boundary sequence is contiguous; operation starts and
   completions correlate exactly; loss/overflow/backpressure/flush failures are explicit.
5. Target outcome, observer failure and backend failure remain distinguishable.
6. BEFORE and terminal AFTER have existing pipeline meaning and no harness bookkeeping
   enters their namespace window.
7. Stock/minimal/full profiles have equal expected outcome and final semantic state in every
   repetition, while scheduling distributions and overhead are reported separately.
8. Rejection, timeout and interrupted flush preserve available evidence without success or
   reward promotion.
9. A reader independently recomputes associations, sequence/correlation integrity, effect
   evidence sufficiency, partial-order edges, normalized keys and final compatibility from
   immutable raw evidence.
10. The result is called engineering qualification only; no transition-feedback advantage
    or vulnerability result is claimed.

Failure of any required criterion records
`V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`. Passing every criterion records
`V2_NATIVE_EFFECT_OBSERVATION_QUALIFIED` and authorizes a separate campaign-integration
gate, not automatic P1/P2 reuse or an effectiveness claim.

## Reusable v1 components

| Existing component | V2 disposition |
| --- | --- |
| `ArchiveCase`, builder, mutation vocabulary | Reuse unchanged |
| Isolated target/backend and final `run_case` semantics | Reuse/composition required |
| BEFORE/AFTER observer and C0/C1/C2 | Reuse unchanged |
| `ArchiveEntryReference` | Reuse if its API remains sufficient |
| `TransitionTrace`, `FilesystemTransition`, v1 keys | Do not reuse as v2 evidence |
| P0 final-state policy core | Candidate comparator under a new campaign contract |
| P1/P2 retention/reward policy IDs | Do not reuse; meanings differ |
| Bounded operator scheduler implementation | Reusable only behind new v2 reward evidence |
| Checksummed export/reader patterns | Reuse patterns with new schemas and verification |

## Claim boundary

The v4 result supports the engineering conclusion that the tested node-tar execution and
passive archive-ordered v1 checkpoint requirement are incompatible. Gate 1 now supplies a
reviewed v2 proposal, not an implementation or qualification. Whether partial-order effect
feedback is sound in the native producer, implementable without unacceptable perturbation,
or more effective than final-state feedback is unverified.

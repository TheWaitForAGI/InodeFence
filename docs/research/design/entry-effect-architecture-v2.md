# Entry-associated filesystem-effect architecture v2

## Status

- Architecture: **DESIGNED**
- Design Gate 1: **GO for generic synthetic implementation**
- Generic immutable evidence model and `EffectRunResult`: **IMPLEMENTED**, **TESTED**
- Generic normalization/search/scheduler: **NOT_IMPLEMENTED** at this revision
- Native producer and reader: **NOT_IMPLEMENTED / NOT_QUALIFIED**
- Campaign integration and experiments: **BLOCKED by later gates**

This architecture composes the existing full-run pipeline with a separate effect-evidence
plane. It does not insert archive-ordered checkpoints into asynchronous extraction and does
not change the legacy pipeline result.

## End-to-end data flow

```text
ArchiveCase
  -> existing deterministic TAR builder
  -> existing isolated complete target invocation
       |-> BEFORE StateSnapshot
       |-> bounded target-specific raw event stream
       |      -> entry association
       |      -> operation start/completion correlation
       |      -> qualified identity/state evidence
       |      -> explicit causal-edge evidence
       |-> target termination + verified evidence flush
       |-> AFTER StateSnapshot
  -> unchanged RunResult and C0/C1/C2 verdicts
  -> generic EffectEventTrace validation
  -> normalized EffectFeedbackKey set
  -> P0-v2/P1-v2/P2-v2 search decision
  -> corpus/parent/operator decision
  -> next ArchiveCase
```

TAR B is chosen only after TAR A terminates and its evidence is validated. The architecture
does not mutate an in-flight TAR or serialize node-tar entry work.

## Task Contract

- **Current Layer:** Layer 2 evidence model plus Layer 5 synthetic feedback composition;
  target qualification remains a later Layer 3/6 task.
- **Objective:** represent qualified entry-associated operation/effect evidence without
  inventing archive-prefix states, and prove normalization/search mechanics synthetically.
- **Allowed modules:** new v2 model, normalization, novelty, search, scheduler, synthetic
  campaign/tests and the directly related design/status documents.
- **Forbidden modules/semantics:** v1 transition types/IDs, `RunResult`, legacy serialization,
  C0/C1/C2, mutation vocabulary, target invocation options and CVE-specific logic.
- **Input:** `ArchiveCase`, unchanged BEFORE/AFTER/`RunResult`, and a bounded raw v2 event
  stream whose source semantics are declared.
- **Output:** validated `EffectEventTrace`, independent effect keys/search decisions and
  lineage/scheduler evidence; no vulnerability or effectiveness result.
- **Security Contract:** C0/C1/C2 remain persistent BEFORE/AFTER verdicts; effect evidence is
  a feedback observation channel only.
- **Completion:** Gate 1 documents are internally consistent and Gate 2 contract tests prove
  schema, partial-order, normalization, fail-closed retention and scheduler causality.

## Generic evidence model

The implemented Python API uses immutable dataclasses/enums and preserves the following
semantic records under serialization schema 2. Its tests are synthetic engineering evidence,
not native observation qualification.

### `EntryLifecycleEvent`

Required fields:

- one global source sequence number;
- exact `ArchiveEntryReference`;
- kind: `READ`, `EFFECT_WORK_STARTED`, or `EFFECT_WORK_SETTLED`;
- monotonic observation interval start/finish;
- explicit success/error status with bounded normalized status and raw evidence reference;
- instrumentation source identity.

Meanings are deliberately narrow:

- `READ`: the declared source observed the logical entry at its qualified read/admission
  hook. It says nothing about filesystem work completion.
- `EFFECT_WORK_STARTED`: the declared target hook began or admitted the work-set associated
  with that entry. It is not a filesystem operation and need not occur in completion order.
- `EFFECT_WORK_SETTLED`: the source's qualified work-set accounting reached its terminal
  callback for that entry. It is not a tree checkpoint, does not imply archive-prefix state,
  and does not prove that uninstrumented kernel effects are complete.

Every meaning is tied to an exact source/version/digest contract. A producer may omit a
lifecycle kind it cannot qualify, but trace completeness requirements must declare the
expected kinds before execution.

### `FilesystemEffectEvent`

One record represents a correlated asynchronous operation interval and contains:

- distinct global start and completion source sequences;
- exact associated `ArchiveEntryReference` and association evidence kind;
- generic effect class plus evidence strength;
- one affected sandbox-relative path or an ordered source/destination pair;
- generic observed operation type and target-specific raw operation record reference;
- monotonic start and completion observation intervals;
- normalized operation outcome plus raw result/error evidence;
- typed before/after identity/state evidence when available;
- source provenance and operation-correlation reference.

The global sequence space includes lifecycle event sequences and both operation boundary
sequences. For a complete stream it is exactly `0..N-1`, with no duplicate owner. A start
must precede its correlated completion in observed sequence and monotonic interval order.
Completion order is preserved as observed and is never rewritten by archive ordinal.

An operation record and a realized effect claim are distinct. An adapter may retain a
successful `write` callback with `operation_result` strength, but generic validation rejects
a claimed content-modification effect key unless its declared before/after evidence supports
that stronger statement.

### Identity and state evidence

Identity evidence is tri-state at each observation point: `not_observed`, `absent`, or
`present(dev, ino)`. This distinguishes lack of evidence from observed absence. Optional
typed state evidence may retain object type, content digest, size, mode, ownership and
mtime/ctime fields only when the observation mechanism qualifies them.

The raw `(st_dev, st_ino)` pair is run-local evidence. It enters neither normalized keys nor
cross-run equality. A hardlink-creation claim requires a real post-operation equality
between source and destination identities and evidence that the destination relation was
not already present. Callback success alone is insufficient. Relation removal likewise
requires observed prior equality and supported post-operation loss of that relation.

Inode reuse cannot be excluded by two disconnected snapshots. Any causal identity edge
requires a qualified continuity/provenance argument in addition to numeric equality.

### `CausalRelation`

Each directed edge names predecessor sequence, successor sequence, evidence kind, source
identity and raw evidence reference. Initially admissible generic edge kinds are:

- `OPERATION_INTERVAL`: correlated start precedes completion for the same operation;
- `ENTRY_CONTEXT_PROPAGATION`: a qualified async context associates an entry work-start
  observation with an operation start;
- `HANDLE_PROVENANCE`: a successful handle/descriptor-producing completion supplies the
  same qualified handle used by a later operation start;
- `EXPLICIT_OPERATION_DEPENDENCY`: a separately qualified target record says one operation
  could not be issued before another completed; and
- `IDENTITY_PROVENANCE`: qualified continuous object-identity evidence connects effects.

`OBSERVED_BEFORE` is not a causal edge kind; it is already represented by source sequence.
Archive order, same path, timestamp proximity, callback order, common entry association and
equal inode numbers alone cannot create an edge. Target-private reservations may be kept in
raw evidence but require their own qualification before becoming
`EXPLICIT_OPERATION_DEPENDENCY`.

Validation requires referenced sequences to exist, predecessor to differ from successor,
the edge evidence to match its kind, and the causal graph to be acyclic. No transitive edge
is invented for serialization. Reachability may be computed as a derived query.

### `ObservationFrontier`

An optional frontier retains a consistency-checked sandbox snapshot, capture interval,
source sequences known at capture start/finish, and a stability result. It belongs to the
trace, not an entry. A frontier captured during overlapping work cannot create a state-delta
feedback key. Only a frontier whose qualified stability conditions pass may support a
declared before/after effect claim.

### `EffectEventTrace`

The trace contains:

- existing BEFORE and AFTER snapshots;
- the full immutable archive-entry reference tuple in archive order;
- lifecycle events and filesystem effect events in source-record form;
- explicit causal relations and optional frontiers;
- expected source bound, last produced/flushed sequence and flush acknowledgement;
- target termination, stream completeness and integrity status;
- source/protocol/configuration/version/digest provenance; and
- typed observation failures.

A complete success trace requires a stopped successful target, AFTER capture after verified
flush, all declared lifecycle coverage, a contiguous bounded stream, valid associations and
correlations, a valid causal DAG, and no observation failure. Rejection may have a complete
stream but remains feedback-ineligible under the initial policy. Timeout/forced termination
is incomplete. Invalid evidence is preserved and never repaired by dropping records.

### `EffectRunResult`

The new composition contains one unchanged `RunResult` and one `EffectEventTrace`. It checks
case entry identities, BEFORE/AFTER equality, protected paths, sandbox root, and compatible
target termination. It does not subclass, mutate or reserialize `RunResult` as a new legacy
schema.

## Ordering and partial-order derivation

The trace exposes three APIs with different meanings:

```text
archive_entries()       -> ordinal order only
observed_event_points() -> exact source delivery/start/completion sequence
causal_graph()          -> only validated explicit edges
```

Normalization reads event records and direct validated causal edges. It may compute endpoint
archive relation (`same_entry`, `earlier_to_later`, `later_to_earlier`) but never uses ordinal
to add reachability. Operations with no path/handle/identity dependency remain unordered in
the causal graph even when one callback arrived first.

Overlapping intervals are observational evidence of overlap, not proof of concurrency at the
kernel effect point and not proof of independence. Completion timestamp is callback delivery
time, not kernel commit time. These limitations remain in trace provenance and reports.

## Generic and target-specific interfaces

### Generic core owns

- immutable v2 evidence types and invariant validation;
- archive-entry correspondence and sequence/correlation/DAG checks;
- effect-evidence sufficiency checks independent of target names;
- normalized feedback derivation;
- novelty, corpus, bounded reward and synthetic campaign composition; and
- canonical serialization plus later independent reader verification.

### Target adapter/producer owns

- the exact lifecycle hooks, async-context propagation and operation wrappers;
- mapping target paths into canonical sandbox-relative paths;
- operation/handle correlation and raw records;
- bounded transport, overflow/loss signalling and flush protocol;
- exact source/entrypoint/lock/worker digests;
- target status mapping and evidence handoff before AFTER; and
- a coverage declaration for every claimed operation/effect class.

Node-tar function names, private symbols, version workarounds and source guards stay in its
adapter/worker. They never enter generic effect enums, normalization or scheduler logic.

### Existing observer/oracle own

The existing stopped-target observer still creates BEFORE/AFTER. Existing oracle code alone
decides C0/C1/C2. The v2 producer does not issue a security verdict, and the oracle does not
infer unobserved events.

## Flush and observation window

The target-specific transport declares a finite maximum record count before execution. It
must fail explicitly before overwriting or dropping a record. Target exit initiates a flush
handshake carrying the last produced sequence, record count and content digest. The
controller verifies the full stream, acknowledges the same terminal sequence/digest and
only then captures AFTER. Missing/mismatched acknowledgement or an interrupted handoff is an
observation failure.

Harness bookkeeping and evidence files must remain outside the observed namespace window or
in a transport that cannot alter the runtime tree. The native design must demonstrate this;
the generic model does not assume it.

## Provenance and serialization

V2 uses new model/schema/policy identifiers. Canonical evidence retains:

- engine revision/dirty state and exact config ID;
- target ID/version/options/image/invocation;
- package lock, actual bundled entrypoint, readable source and worker/producer digests;
- observation protocol/source IDs and coverage declaration;
- OS/kernel/architecture/filesystem/runtime root and event bound;
- exact case ID/TAR hash, sentinel configuration and random seed; and
- raw stream digest, flush digest/status and reader version.

Raw path, inode, timestamp and source IDs are serialized as evidence but excluded from
feedback keys. Export follows the existing immutable no-overwrite/checksum pattern with new
v2 filenames and schemas. A reader must recompute, not trust, entry mapping, sequence
integrity, effect sufficiency, causal edges, normalized keys, novelty, admission and reward.

## Legacy v1 compatibility

| Existing component | V2 rule |
| --- | --- |
| `ArchiveCase`, `ArchiveEntryReference`, USTAR builder | reuse unchanged |
| mutation operator vocabulary and stable IDs | reuse unchanged |
| isolated target/backend and complete TAR invocation | compose unchanged |
| BEFORE/AFTER observer and C0/C1/C2 | reuse unchanged |
| `RunResult` and legacy serialization | compose, never modify |
| `TransitionTrace`/checkpoint derivation | do not call or reinterpret |
| v1 transition keys/policy IDs/evidence | do not reuse |
| bounded 1–8 scheduler mechanism | reuse behavior behind new v2 types |
| completed export/reader/replay patterns | copy pattern with new schema and verification |

No converter from an effect trace to `TransitionTrace` is defined. V4 raw callbacks are not
accepted as a v2 trace because they lack the new coverage, start/completion, state-effect,
bounded-loss and flush proofs.

## Gate boundaries

1. **Gate 1 — Design:** this contract, feedback contract and review report agree. GO only
   authorizes generic synthetic work.
2. **Gate 2 — Synthetic:** test schema invariants, reordered independent completions,
   supported/unsupported causal edges, identity sufficiency, stable normalization,
   fail-closed novelty/corpus and P0-v2/P1-v2/P2-v2 lineage/reward.
3. **Gate 3 — Native observer:** implement bounded source-guarded transport in the existing
   isolated complete target path. No campaign integration.
4. **Gate 4 — Qualification:** execute the fixed matrix and independent reader. Publish one
   exact qualification token.
5. **Gate 5 — Campaign integration:** only the qualified producer may feed a configured
   native v2 campaign.
6. **Gate 6 — Bounded integration experiment:** verify the pipeline/evidence under equal
   budgets; do not claim formal effectiveness or rediscovery.

Failure or incompleteness at one gate blocks every later gate. Synthetic correctness cannot
substitute for native observation qualification.

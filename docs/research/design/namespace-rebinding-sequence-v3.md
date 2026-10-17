# Namespace rebinding sequence observation v3

## Status and claim boundary

- Design review: **GO for generic synthetic implementation**
- Native dependency producer: **NOT_IMPLEMENTED**
- Native qualification and effectiveness: **NOT_RUN / NOT_EVALUATED**

This design is an additive observation layer over entry-effect v2. It does not change v2
`namespace_replacement`, C0/C1/C2 or any security verdict. The implementation scope and stop
conditions are frozen by the
[N04 Task Contract](../benchmarks/n04-namespace-rebinding-sequence-v3-task-contract.md).

## Layering

```text
validated complete v2 EffectEventTrace
        +
strict v3 raw operation-dependency envelope
        |
        v
independent endpoint/dependency cross-check
        |
        v
NamespaceRebindingSequence v3
        |
        +--> retained v2 keys (unchanged)
        +--> finite rebinding key v3
```

The v3 envelope is not an alternative source of filesystem truth. It supplies the explicit
producer branch-continuation provenance that v2 deliberately does not infer. Endpoint object
states must independently agree with already validated v2 raw-derived events.

## Composite semantics

One sequence binds:

- one immutable `ArchiveEntryReference`;
- one canonical destination path;
- one successful realized v2 namespace removal;
- one successful realized v2 namespace creation, symlink creation or hardlink relation
  creation, using the hardlink destination role;
- exact start/completion bounds and correlation IDs for both operations;
- present-before/absent-after removal evidence and absent-before/present-after creation evidence;
- one raw v3 dependency record and producer-issued branch token; and
- the v2 raw-stream digest/source plus the v3 dependency-envelope digest/source.

The edge must connect removal completion directly to creation start. A graph path through
context or timing edges is not accepted. Another successful namespace-binding operation for the
same destination whose interval intersects the open gap invalidates the composite. Operations on
other paths remain visible and do not invalidate it.

The sequence means only that one observed namespace binding was removed and later re-established
by a producer-verified continuation of the same entry branch. It does not mean atomic rename,
continuous identity, a Security Contract violation or exploitability.

## Independent reconstruction

The reader accepts bytes plus an already integrity-valid v2 trace. It strictly validates the
v3 protocol/version, source identity, record count, unique record IDs, trace raw digest and the
two complete endpoint records. Each endpoint's entry, path role, operation, outcome, sequences,
correlation ID and object observations must equal the matching v2 event. The dependency record
must then bind those exact endpoints. Unknown or extra fields fail closed.

The reader derives the composite; it does not trust a producer-supplied composite label. This
synthetic gate verifies reconstruction mechanics only. A native implementation must later prove
that its branch token is emitted at the actual target control-flow dependency and qualify that
producer separately.

## Finite feedback projection and nonredundancy

The v3 key retains only:

- trigger entry type and existing first/early/late ordinal class;
- destination region and protected-external marker;
- before-removal and after-creation object types;
- creation kind: object, symlink or hardlink relation;
- hardlink source region when applicable; and
- fixed evidence level `dependency_verified_state_change_verified`.

Exact paths, identities, sequence/correlation IDs, timestamps, raw tokens, archive hashes and
target/source identities remain evidence only. Duplicate normalized composites collapse to one
key.

V2 can already represent a removal effect, a creation effect and an explicit dependency motif.
It intentionally normalizes away exact paths and does not require a conflict-free same-path gap.
Consequently, a same-entry dependency from removal at path A to creation at path B can have the
same v2 keys as a same-path A-to-A rebinding. V3 distinguishes them by whether a composite key is
present, without putting path A into that key. This is the bounded additional discrimination to
be verified synthetically; it is not an effectiveness result.

## Compatibility and later gates

V2 events and keys are returned unchanged and remain independently inspectable. Old raw evidence
is never upgraded because it lacks the v3 dependency envelope. The current node-tar producer
therefore yields no native v3 claim.

A later native gate must separately freeze producer source guards, dependency-token semantics,
archive-only fixtures, at least 20 repetitions, stock/minimal/full profiles, image/options/source
digests, limits, evidence paths and failure injections. Only that future matrix can qualify the
observation mechanism. Effectiveness and historical rediscovery require later contracts again.

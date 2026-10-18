# Entry-associated namespace rebinding v3 proposal

Status: **REVIEWED / GENERIC SYNTHETIC IMPLEMENTATION COMPLETE / NATIVE NOT_IMPLEMENTED /
NOT_QUALIFIED**. This document records the original scientific-method proposal. The N04
[implementation Task Contract](../benchmarks/n04-namespace-rebinding-sequence-v3-task-contract.md)
approved only the separate generic model, strict reader and synthetic suite. It did not amend
the v2 contracts or permit a native campaign.

The recorded technical decision is **GO for generic synthetic implementation**. The bounded
additional distinction is a producer-dependent, conflict-free same-path absence gap that the
normalized v2 key set does not encode. The implementation and synthetic result are documented
in the [v3 design](namespace-rebinding-sequence-v3.md) and
[verification report](../diagnostics/n04-namespace-rebinding-sequence-v3-synthetic-verification.md).

## Decision requested

The recommended direction is to add a separately named, multi-operation
`namespace_rebinding_sequence` observation in a future v3 contract. It would describe a
verified interval in which one archive entry removes a path binding and later creates a new
binding at the same path. It must not be called or counted as the v2 single-operation
`namespace_replacement` class.

Reviewers must approve or reject all of these choices before implementation:

1. whether multi-operation rebinding is a security-state observation worth exposing to the
   feedback comparison;
2. whether it is a new composite record/key rather than a change to
   `FilesystemEffectEvent` v2;
3. whether v3 retains the two underlying realized v2 events in addition to one bounded
   rebinding key; and
4. which archive-only fixtures and minimum repetitions form a new qualification matrix.

Approval would authorize only a separate implementation Task Contract. It would not qualify
v3, unblock P0/P1/P2-v2 or authorize effectiveness experiments.

## Task Contract and evidence boundary

Research objective: make the verified node-tar namespace behavior representable without
weakening the failed v2 gate. Current Layer: entry-effect observation/feedback methodology
before implementation. Root cause: the target performs replacement as more than one
filesystem operation, while v2 deliberately assigns each effect event to one correlated
operation interval.

Allowed output is this review proposal and status/document routing updates. Prohibited
changes include schemas, producer/reader code, policy identifiers, v2 acceptance criteria,
raw evidence, C0-C4 meanings, qualification fixtures and campaign execution. The stop
condition is human scientific approval or rejection.

The evidence basis is the retained
[node-tar diagnosis](../diagnostics/node-tar-replacement-report.md):

- the default duplicate regular-file fixture reused and truncated one inode in 20/20 full
  qualification runs, so it was not replacement;
- controlled archive-only and precreated cases exercised successful
  `unlink -> open/mkdir/link/symlink` rebinding;
- the unchanged reader reconstructed removal followed by creation or a link-specific class;
- all 18 independently verified complete native diagnostic bundles contained zero v2
  `namespace_replacement` events; and
- inode-number reuse occurred across unlink/create, so equal `(st_dev, st_ino)` observations
  at separated checkpoints do not prove continuous object identity.

This is reproducible diagnostic evidence, not effectiveness evidence or a vulnerability.
The finite cases also do not prove that a true single-operation replacement is impossible
for every input accepted by the pinned target.

## Invariants that v3 must preserve

- `FilesystemEffectEvent` v2 continues to mean one correlated operation interval.
- v2 `namespace_replacement` continues to require present-before and present-after with
  changed identity or object type across that one operation.
- The 480-run decision remains exactly
  `V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`; no old raw bundle is reclassified.
- A missing observation never proves absence. Both absence checkpoints used by a rebinding
  claim must be explicit and valid.
- Operation order, timestamp proximity, equal paths and equal entry ordinals alone do not
  establish causality.
- Raw operations and their individual v2 realized effects remain available. Aggregation
  cannot delete, rewrite or conceal them.
- C0/C1/C2 and future C3/C4 verdicts remain independent from observation novelty. A rebinding
  key is not a violation or vulnerability finding.
- Incomplete, invalid, rejected, failed or timed-out traces produce no successful feedback
  keys under the initial policy. Their evidence remains diagnostic.
- v1/v2 schemas, protocol strings and policy IDs cannot be reused for v3 output.

## Proposed composite evidence

A future `NamespaceRebindingSequence` should be separate from the single-operation event
type and bind, at minimum:

- immutable archive entry reference and one destination path;
- one realized removal event and one realized creation, symlink-creation or hardlink-relation
  event from the same trace and evidence source;
- both operation correlation IDs and start/completion sequence bounds;
- the endpoint object before removal, explicit absence after removal, explicit absence before
  creation and the object after creation;
- an explicit producer-supported operation-dependency edge from removal completion to the
  creation start, with raw evidence references; and
- the exact source/target trace and archive provenance already required by v2.

The following predicates are all mandatory:

1. The removal and creation are associated with the same archive entry and same normalized
   destination path. For a two-path hardlink event, the destination role must match.
2. Removal completed successfully and is independently realized as present-to-absent.
3. Creation completed successfully and is independently realized as absent-to-present or as
   a verified link relation whose destination changed from absent to present.
4. Removal completion precedes creation start in the retained global sequence.
5. A validated dependency edge, not adjacency or timing, proves that the creation is the
   continuation of that removal branch. The current v2 records are insufficient if this
   edge cannot be reconstructed; v3 must then add a bounded producer provenance token.
6. No successful intervening namespace-binding operation for the same path occurs inside
   the dependency chain. Unrelated work on other paths may interleave and remains visible.
7. The full trace is complete and integrity-valid, and independent reconstruction agrees
   with the producer-derived composite.

The composite means that the namespace binding was absent and then re-established. It does
not claim atomic replacement. A changed endpoint type or identity can strengthen the
description, but equality of separated inode tuples cannot negate rebinding because the
diagnostic evidence demonstrates inode reuse. Successful unlink plus explicit absence plus
qualified creation is the required continuity break.

## Proposed finite feedback projection

If approved, v3 should retain the underlying v2 individual keys and add one tagged composite
key. Its finite fields should be limited to:

- trigger entry type and existing first/early/late ordinal class;
- destination region and protected-path marker;
- before and after object-type enums;
- creation kind: regular/directory, symlink or hardlink relation;
- source region for a hardlink relation; and
- a fixed `dependency_verified/state_change_verified` evidence level.

Exact paths, inode/device values, sequence numbers, correlation IDs, timestamps, archive
hashes, target versions and callback counts remain raw evidence only. Multiple qualifying
chains that normalize identically contribute one key. Scheduling permutations and unrelated
interleavings cannot create novelty. No v2 key or policy output is changed retroactively.

The final v3 policy identifiers and serialization layout must be selected in the approved
implementation contract. Reusing `P0-v2`, `P1-v2`, `P2-v2` or the v2 evidence classification
would make unlike observation policies appear comparable and is prohibited.

## Qualification impact and required negative tests

A v3 implementation would restart the relevant design, synthetic and native qualification
gates under new identifiers. Before any matrix, synthetic independent-reader tests must
reject at least:

- same-inode truncation without removal;
- removal with no later creation;
- creation whose before state was not explicitly absent;
- same path and entry with no dependency edge;
- different entries or different destination paths;
- failed removal or creation;
- an intervening same-path namespace operation;
- incomplete/invalid streams and target rejection; and
- fabricated replacement based only on different or equal endpoint inode tuples.

Candidate archive-only positive controls from the diagnosis are file-to-directory,
file-to-symlink, file-to-hardlink and hardlink-anchor rebinding. The duplicate-path fixture
must remain a truncation negative control. The final fixture set, stock/minimal/full profiles,
at-least-20 repetition minimum, image/options/source hashes, resource limits and evidence
paths require a separately frozen execution contract. Precreated-state controls are useful
diagnostics but must not silently replace archive-constructed qualification cases.

Passing that future matrix would qualify only the v3 observation mechanism. It would not
validate feedback effectiveness, historical rediscovery or any security claim. Native
P0/P1/P2-style comparisons remain NOT_RUN until their exact v3 gate and experiment contract
are separately approved.

## Review outcome and next dependency

- **Approve as written:** create a narrow implementation Task Contract for the composite
  model, dependency provenance, independent reader and synthetic rejection suite.
- **Request changes:** revise this proposal without modifying code or old evidence.
- **Reject multi-operation feedback:** retain v2 unchanged and either investigate a genuine
  one-operation native positive or accept that this target cannot qualify the mandatory v2
  replacement cell. The native campaign remains blocked.

The generic implementation outcome is recorded; a native producer, new qualification matrix
and every effectiveness campaign remain separately unauthorized and **NOT_RUN**.

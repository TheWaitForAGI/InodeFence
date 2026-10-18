# N04 namespace rebinding sequence v3 implementation Task Contract

Status: **GENERIC SYNTHETIC IMPLEMENTATION COMPLETE / NATIVE NOT AUTHORIZED**.
Contract version: **v1**.
Frozen base: `4b8453f905cc8a5442e1c77fb8e175b16ce7a116`.
Authorization source: the N04 research-owner request. This is an AI-assisted technical
decision, not human expert approval and not authorization for target execution.

## Objective and decision

Implement the smallest target-independent v3 representation that can distinguish a verified
multi-operation namespace rebinding from v2's one-operation `namespace_replacement`. The
implementation must consume, preserve and cross-check realized v2 removal/creation evidence;
it must not rewrite or reclassify any v2 event or historical bundle.

The design decision is **GO for synthetic implementation** because a composite can add one
bounded distinction not represented by the existing normalized v2 causal motif: both endpoints
must affect the same canonical destination path, with explicit absence on both sides of the gap
and no successful conflicting namespace-binding operation in that dependency interval. Exact
paths remain raw evidence and do not enter the finite v3 key.

This decision is not a native-observation PASS. The current node-tar v2 producer does not emit
the required branch-continuation dependency record, so native v3 remains NOT_IMPLEMENTED and
NOT_QUALIFIED.

## Allowed changes

- a separate immutable `NamespaceRebindingSequence` schema and dependency-provenance schema;
- derivation from an integrity-valid, successfully terminated v2 `EffectEventTrace`;
- a strict v3 raw dependency-envelope reader that independently cross-checks both endpoint
  operations and their state observations against the validated v2 trace;
- one finite tagged v3 feedback projection which is additive to, and does not mutate, v2 keys;
- deterministic synthetic positive and negative fixtures/tests;
- the v3 design, decision, routing and status documentation required by those interfaces.

No repository Issue currently names this task. This user-approved Task Contract is therefore the
controlling implementation scope under `AGENTS.md`.

## Required predicates

A composite exists only when all predicates pass:

1. The removal and creation/link operations refer to the same immutable archive entry and the
   same canonical sandbox-relative destination path.
2. The removal completed successfully and its realized v2 evidence is present to absent.
3. The creation completed successfully and its destination evidence is absent to present.
   Hardlink evidence uses the destination role, never the source role.
4. Removal completion is globally observed before creation start.
5. A separate v3 raw record names both correlations/sequences and carries a bounded
   producer-branch continuation token. Timing, adjacency, matching path text, archive ordinal or
   an existing v2 context edge is not a substitute.
6. No other successful realized namespace-binding event for the destination overlaps the open
   interval from removal completion to creation start.
7. The v2 trace is complete, integrity-valid and successfully terminated. The v3 raw envelope is
   strict, digest-bound to that trace's raw stream, and the independent reconstruction agrees
   with every endpoint field.

Separated endpoint inode equality neither proves nor disproves a composite. Successful removal,
two explicit absence observations and qualified creation establish the continuity break.

## Version and compatibility boundary

- `FilesystemEffectEvent.serialization_schema == 2` and every v2 enum/meaning stay unchanged.
- `EffectEventTrace`, `effect_feedback_keys`, P0-v2/P1-v2/P2-v2 identifiers and old evidence
  serialization stay byte/semantics compatible.
- v3 types use schema `3`, protocol `inodefence-namespace-rebinding-sequence`, version `3.0.0`
  and an independently named tagged feedback key.
- C0/C1/C2 remain final BEFORE/AFTER oracle verdicts. A rebinding sequence is observation
  feedback, not a violation or vulnerability finding.
- Raw operations, v2 realized effects and v2 feedback keys remain available alongside v3 output.

## Synthetic acceptance suite

The tests must establish one positive file-to-file rebinding and reject at least:

- same-inode truncation without removal;
- removal without creation;
- creation without explicit pre-creation absence;
- equal entry/path and temporal adjacency without the v3 dependency record;
- mismatched entry or destination path;
- failed/unrealized removal or creation;
- a successful intervening same-path namespace binding;
- incomplete, invalid, rejected or timed-out traces;
- tampered raw provenance, sequence, correlation, state or trace digest; and
- any decision based only on equal or unequal endpoint inode tuples.

The nonredundancy test must construct two feedback-eligible traces with equal v2 key sets, one
with a qualified same-path rebinding and one without it, and show that only the former receives
the tagged v3 composite key. If that test cannot be established without adding exact paths or
unbounded identifiers to the key, implementation stops and reports the design as redundant.

## Validation and stop conditions

Required before PR review: Ruff check/format, Pyright, pytest, environment/document validation,
`make check`, GitHub `check`, GitHub `container-integration` and independent adversarial review.
Stop without weakening predicates if raw dependency provenance cannot be independently bound,
if v2 behavior changes, or if v3 adds no finite observable distinction.

No target image, native extractor, qualification matrix, effectiveness campaign, historical
replay or P0/P1/P2 arm may run under this contract. A later native task requires a new frozen
source/image/protocol/fixture/resource/evidence contract and explicit authorization.

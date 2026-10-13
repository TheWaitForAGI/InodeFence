# Entry-effect v2 design review and executable work plan

Review date: **2026-10-13**. Reviewed base: PR #88 head
`dd8dd15b2b4a8ce697e3ef38567883f2602cfb15`, based on qualification harness
`72bccfafe5f9f7e8ff06d850fb62a43fa6ed75d8`. Remote `main` was
`931899209bc1de29f249d9e2f3d451438ddf1d22` when fetched for this review.

## Sources and consistency audit

The review covered the current research contract, v1 feedback/scheduler contracts, v1
native-observation decision, the PR #88 v2 observation draft, retained v4 summary, current
generic model/search/scheduler APIs and the root/research/source/experiment agent rules.

The new [feedback contract](entry-effect-feedback-v2.md) and
[architecture contract](entry-effect-architecture-v2.md) preserve these existing boundaries:

- `TransitionTrace` remains a complete archive-prefix checkpoint sequence and is not
  weakened, reordered or populated from effect callbacks;
- v2 uses new evidence/key/policy identifiers and cannot enter v1 evaluation bundles;
- existing `RunResult` and C0/C1/C2 remain persistent BEFORE/AFTER evidence;
- v4 is feasibility evidence only and is not promoted to a producer;
- target/version/private-hook logic stays outside the generic model/feedback layer; and
- native campaigns remain blocked until a new producer passes the full qualification.

One wording conflict in the PR #88 draft required correction: qualification was said to be
required “before feedback design.” The present task explicitly requires feedback semantics
to be designed and synthetically tested before native qualification. Qualification is now
the gate before **native campaign integration**, not before generic design.

## Answers to the seven required questions

### 1. Exactly which filesystem effects are observed?

The raw channel observes only declared target operations with correlated start/completion,
paths/results and available evidence. The semantic channel recognizes nine bounded classes:
namespace create/remove/replace, regular content modification, truncation, metadata change,
symlink creation, hardlink identity-relation creation and identity-relation removal.

A class is a realized effect only when its class-specific evidence rule passes. Operation
callbacks that cannot prove a state change remain raw operation evidence. Coverage is per
declared operation/effect class; it is not exhaustive syscall coverage.

### 2. How is an effect associated with a TAR entry?

The target adapter propagates the immutable `ArchiveEntryReference` through a qualified
async context. Descriptor/handle operations may inherit the exact entry from a separately
validated handle-ownership record. The independent reader checks ordinal/path/type/link
target against the `ArchiveCase`, rejects missing or conflicting associations and validates
the stated association evidence. Path equality and callback timing are never substitutes.

### 3. How are observed completion order and causality separated?

Every lifecycle point and operation start/completion owns a global source sequence, which
preserves observed delivery order. Causality is a separate DAG containing only typed,
evidence-backed edges. Archive ordinals are a third independent relation. No postprocessing
sort creates a state history, and unordered operations stay unordered.

### 4. What supports claims about inode identity or state change?

Identity is supported by actual lstat `(st_dev, st_ino)` observations with explicit
present/absent/not-observed state and class-specific before/after checks. Hardlink creation
requires post-operation equality plus evidence the relation was absent before. Content,
truncation and metadata claims require qualified differing fields, not an operation name or
return value. Numeric equality across disconnected observations does not prove continuity
and raw identity never enters cross-run feedback.

### 5. Why is normalized feedback not event-count or scheduling noise?

Keys exclude sequence, timestamps, correlation IDs, callback count and completion order.
Repeated equal effects collapse to a unique signature; per-entry relations are finite sets;
motifs contain one validated causal edge. Mere overlap/completion permutation is diagnostic
only. Qualification compares key sets across repetitions/profiles and blocks keys generated
only by instrumentation-induced scheduling changes.

### 6. How can feedback causally affect the next mutation?

Each step binds result → validated trace → exact key set → novelty/admission → retained
parent selection → weights/operator draw → mutation attempt → child ID → reward/updated
weights. P1-v2 changes retention relative to P0-v2; P2-v2 changes only scheduler weights
relative to P1-v2. This chain, rather than co-occurrence, is the evidence that TAR A affected
the choice of TAR B.

### 7. Is comparison with final-state feedback fair at the same budget?

Yes at the design level: all arms use identical full instrumentation, seeds, target/options,
mutation vocabulary, seed-inclusive execution budget and status accounting. P0-v2 computes
but ignores effect keys for admission; P1-v2 changes retention; P2-v2 keeps P1 retention and
changes only bounded operator scheduling. Formal fairness remains an experiment result to be
validated, not a consequence of this document.

## Qualification fixtures and acceptance matrix

Normal fixtures run `stock`, `minimal` and `full` profiles at least 20 times each. `stock`
has no effect producer, `minimal` has association/lifecycle context and integrity framing,
and `full` adds the declared operation/effect evidence. All profiles execute the same whole
TAR through the pinned target invocation.

| Fixture | Required semantic coverage | Acceptance evidence beyond common checks |
| --- | --- | --- |
| regular file | operation correlation; content/truncation claim boundary | raw open/write/close association; any content/truncation class has qualified before/after evidence |
| directory metadata | namespace creation and deferred metadata | metadata event/evidence is not assigned to an earlier false checkpoint; final state equal across profiles |
| hardlink identity | link operation and identity relation | real source/destination identity equality after link and prior relation absence |
| symlink | symlink namespace/object evidence | created object is lstat symlink and raw link text is retained |
| duplicate path | replacement versus data work | duplicate ordinals remain distinct; replacement requires before/after identity/type evidence |
| directory + child | dependent paths with overlapping work | no causal edge inferred from path prefix alone; any dependency edge has qualified provenance |
| independent files | out-of-order completion | observed permutations preserved; no invented causal edges; feedback key set stable across permutations |
| partial rejection | completed prefix plus later target error | rejected status preserved; flush/integrity assessed; initial policy emits no admission/reward |

Common normal-fixture acceptance requires exact target/source digests, exact entry and
operation associations, contiguous bounded streams, start/completion correlation, valid DAG,
no observation failure, equal expected target outcomes/final semantic states across profiles,
and per-fixture overhead/order distributions rather than only an aggregate mean.

| Failure injection | Expected trace/result | Admission/reward |
| --- | --- | --- |
| timeout/forced termination | target timeout, incomplete stream, available prefix retained | forbidden |
| event-buffer overflow | explicit overflow before overwrite/drop; invalid/incomplete trace | forbidden |
| missing sequence/event loss | reader detects gap/count/digest mismatch | forbidden |
| duplicate sequence | reader rejects nonunique source position | forbidden |
| malformed identity | typed parse/semantic failure, raw bytes retained | forbidden |
| entry association conflict | conflict records both claims; trace invalid | forbidden |
| operation correlation conflict | unmatched/duplicate start or completion rejected | forbidden |
| invalid/cyclic causal edge | reader rejects edge/DAG | forbidden |
| flush interruption/mismatch | last-produced/flushed/ack values do not reconcile | forbidden |
| source/reader disagreement | qualification fails and preserves both reports | forbidden |

Additional qualification outputs:

- effect-class coverage table with supported/unsupported operations;
- stock/minimal/full outcome and semantic-state equality per repetition;
- fixture/profile duration distributions and evidence sizes;
- observed completion-order distributions;
- normalized key-set stability and schedule-only diagnostic variation; and
- exact token `V2_NATIVE_EFFECT_OBSERVATION_QUALIFIED` only if every mandatory cell passes,
  otherwise `V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`.

## Independent stacked PR plan

Each item has one purpose and a predecessor gate. Later items are not silently folded into an
earlier PR.

1. **PR V2-DESIGN** — this review plus architecture/feedback contracts and reconciliation of
   the PR #88 observation draft. Base: PR #88 while it is unmerged.
2. **PR V2-MODEL** — immutable generic lifecycle/effect/identity/causal/trace types,
   `EffectRunResult`, strict invariant tests and canonical serialization checks. No target.
3. **PR V2-FEEDBACK** — finite normalization, three key variants, fail-closed novelty/search,
   new policy IDs, bounded scheduler evidence and deterministic synthetic campaign tests.
4. **PR V2-NATIVE-PRODUCER** — source-guarded bounded node-tar producer/transport and raw
   export only. No campaign.
5. **PR V2-READER-QUALIFICATION** — independent reader, eight fixtures, failure injection,
   profile repetitions, coverage/stability/overhead analysis and gate report.
6. **PR V2-CAMPAIGN** — qualified producer integration, new config/export/replay schemas and
   full closed-loop evidence. Requires the exact qualified token.
7. **PR V2-PILOT** — frozen bounded P0-v2/P1-v2/P2-v2 integration comparison. It validates
   pipeline/evidence only; formal effectiveness and historical rediscovery stay later gates.

## Review classifications

### FACT

- The fetched remote SHAs matched the task: main `9318992`, PR #88 `dd8dd15`.
- V4 ran 480 processes, associated 320/320 instrumented entries and 1,020/1,020 recorded
  filesystem operations, and observed 162 later-ordinal operations before earlier completion
  markers within its declared fixtures/mechanism.
- V4 records callback completions and exact associations but does not provide the v2 loss,
  state-effect, start-event, production flush or reader proofs.
- Existing v1 code assumes complete archive-prefix checkpoints and uses separate v1 policy
  and evidence schemas.

### INFERENCE

- Exact async-context/descriptor association is a viable candidate primitive for v2, because
  it was exact in the retained bounded fixtures; it still requires a new qualification.
- A set-based effect projection with explicit causal edges can avoid rewarding observed
  completion permutations while preserving evidence not present in final state.
- Equal instrumentation in all arms is necessary to avoid conflating observer overhead with
  feedback benefit.

### HYPOTHESIS

- H1: effect-key retention improves useful exploration over final-state retention.
- H2: effect-key reward improves efficiency over uniform mutation under the same retention.
- The proposed native mechanism can meet coverage, integrity, perturbation and stability
  gates at acceptable cost.

### OPEN QUESTION

- Which successful operation/state probes can be qualified without unacceptable scheduling
  perturbation for every declared effect class?
- Can identity continuity be proven strongly enough for cross-entry identity-provenance
  edges, or must those motifs remain unsupported?
- Will normalized key sets remain stable across full-profile repetitions despite observed
  instrumentation scheduling changes?
- After qualification, should a completely flushed rejected prefix become feedback-eligible?
  The initial policy says no and any change requires a pre-registered contract revision.
- What event bound and transport provide loss detection without backpressure that changes
  target semantics beyond the accepted qualification threshold?

## Decision

**PASS — Gate 1 design and Gate 2 synthetic implementation.** Immutable schema/partial-order
tests and normalized feedback/search/scheduler/campaign tests cover state-evidence sufficiency,
completion-order permutation stability, explicit-edge-only motifs, fail-closed invalid streams,
P0-v2/P1-v2 retention separation, P1-v2/P2-v2 retention equality, deterministic lineage and
binary bounded reward. This is engineering evidence only and does not claim native coverage.

**IMPLEMENTED, CONTAINED RUN NOT_RUN — Gate 3; NOT STARTED — Gate 4; BLOCKED — Gates 5–6.**
The bounded source-guarded producer, controller-side terminal verification, typed conversion,
raw export and portable failure tests are present on the Gate 3 branch. The actual contained
eight-fixture suite remains NOT_RUN in the current environment, so this is not the exact
`GATE3_NATIVE_PRODUCER_IMPLEMENTED` completion token and native observation is not qualified.
V4 remains feasibility evidence rather than production evidence. Native campaign integration
and any H1/H2 or vulnerability claim remain blocked until Gate 4 passes with retained evidence.

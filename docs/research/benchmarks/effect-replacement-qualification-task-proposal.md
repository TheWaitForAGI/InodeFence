# Proposed Task Contract: native replacement coverage

Status: **DIAGNOSTIC BRANCH 2 OBSERVED / SUPERSEDED FOR NEXT ACTION**. This is a review artifact from the
[engine audit](effect-coverage-engine-audit.md), not authorization for a new Gate 4,
Gate 5 or campaign. The original observation/feedback contracts and historical result
remain unchanged. The later runtime investigation established multi-operation namespace
rebinding for the exercised cases. The separately versioned
[v3 proposal](../design/entry-effect-rebinding-v3-proposal.md) is **BLOCKED_FOR_REVIEW**.

## Problem and objective

The frozen `duplicate-path` input is two regular files at the same path. The retained
node-tar 7.5.22 full observations prove same-inode truncation in 20/20 cases and no
replacement. The qualification requirement correctly remains mandatory; its association
with this particular input does not demonstrate reachability.

Current Layer: target-specific feasibility / Layer 6 qualification design. Objective:
determine whether the unchanged native full-execution target can produce and observe a
known-positive replacement under the existing **one correlated operation** meaning,
then propose a frozen fixture extension and explicit coverage mapping for review.

Input: exact target/source/image/options, deterministic complete TAR, disposable layout,
raw correlated operations, independent identity/type ground truth and existing historical
matrix. Output: reachability verdict, evidence-qualified positive fixture candidate or
explicit inability, reviewed fixture/coverage specification and reproducibility package.
No QUALIFIED decision is an output of this preparatory task.

## Allowed scope and unchanged requirements

- Analysis and bounded contained feasibility controls with explicit repetition budgets
  fixed before execution; new fixtures/tests/raw output only in separate locations.
- Preserve `duplicate-path` as a same-inode truncation control. Preserve its original
  historical case ID and result; introduce a separately named replacement positive
  candidate rather than rewriting the old evidence.
- A proposed future coverage map may assign the same mandatory replacement class to
  that positive fixture. Such a map must be explicitly reviewed/frozen as a new
  qualification configuration, never applied to the historical run. No coverage class,
  repetition minimum, evidence requirement or acceptance threshold may be removed.
- The same complete TAR and existing `strict: true, preservePaths: false` target path
  must run. No unlink option, target serialization, prefix replay, per-entry extraction
  or worker-generated extra filesystem operation may manufacture a native positive.
- Generic model/observer/oracle/feedback, C0/C1/C2, v1 identifiers and native campaign
  authorization remain unchanged. Any implementation defect requires a separately
  evidenced minimal regression and fix within the reviewed scope.

## Decision branches requiring Runtime evidence

1. **Single-operation native replacement reachable:** demonstrate the exact operation
   with present-to-present different identity/type on the affected path, sufficient
   association/correlation, lossless transport and independent reader agreement. Provide
   exact fixture/TAR hashes and repeated stock/minimal/full final outcome equality.
   Submit the new fixture and coverage map for freeze before scheduling another matrix.
2. **Only multi-operation namespace rebinding reachable:** preserve unlink/remove and
   create/link evidence separately. Do not label these callbacks replacement. Submit a
   separate versioned semantics proposal defining the observation interval, required
   causal provenance, intermediate states, inode reuse/overlap exclusions, independent
   reconstruction and normalized keys. This expands the current one-operation meaning
   and cannot be applied without review; its effects on Gate 1/2/3 and qualification
   identifiers must be decided before implementation.
3. **No qualified native positive established:** retain NOT_QUALIFIED, document the
   mechanism's unsupported coverage and keep integration/campaign blocked. A synthetic
   rename control cannot supply the missing native cell.

The retained [runtime diagnosis](../diagnostics/node-tar-replacement-report.md) resolves the
exercised cases to branch 2: archive-only and precreated controls produced removal followed
by creation/link, and 18/18 independently verified complete native bundles produced zero
single-operation replacement events. This is not an exhaustive proof that branch 1 is
unreachable for every accepted input. It is sufficient to show that a fixture-only change
cannot turn the observed cases into v2 replacement coverage.

## Completion / review criteria

The handoff must contain original/pinned target identities and options, fixture IDs and
exact TAR bytes/hashes, fresh sandbox setup, timing and raw operation evidence, actual
before/after `(st_dev, st_ino)` and object types, entry and descriptor provenance,
failure outcomes, repetitions and all negative attempts. It must explicitly distinguish
source expectations, observed facts, independent derivations and unproved claims.

A replacement-positive candidate is accepted for a future qualification only after
Runtime and Engine agree on its native ground truth and the reader demonstrates the
required class from those native raw bytes. Any contract amendment must be reviewed
and versioned before new evidence generation. Full matrix size follows the frozen
fixture set × stock/minimal/full × at least 20 repetitions; adding a fixture can increase
the matrix size. It must never silently relabel the original 480-run matrix.

After preparatory review, a **separate execution Task Contract** must pin revision,
fixture map, image/options/source hashes, resource limits, output paths and acceptance
before another Gate 4. This audit does not execute that task. Gate 5, native fuzzing,
threshold changes and automatic merging remain prohibited.

# Engine / qualification effect-coverage audit

Audit date: **2026-10-14**. Task Contract: the user's “Engine and Qualification
Audit”, Phases A–D. Baseline: `fix/native-effect-qualification-wsl`,
`0eb527f88aa8a4015544d2f6b0eabfebe079bf18`; historical execution:
`36ff7fdb0e31db72b3e581fd1c089b712b4a7b4e`; original draft: [PR #89](https://github.com/TheWaitForAGI/InodeFence/pull/89).
Audit branch: `diag/effect-coverage-audit`, separate worktree
`/home/linux/Projects/InodeFence-effect-audit`.

## Engine verdict and evidence boundary

**The tested engine can classify and independently reconstruct a replacement when
one correlated operation has sufficient present-to-present identity/type evidence.**
Real filesystem controls establish same-inode content modification/truncation and
atomic rename replacement, including regular-to-symlink replacement. Their operation
frames, entry associations, source identities and execution metadata are constructed
test inputs, not native node-tar observations. They establish **TESTED engineering
behavior**, not native qualification, a security violation or feedback effectiveness.

The historical **480/480**, **13/14** and
**`V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`** remain unchanged. Duplicate-path
has truncation **20/20**, replacement **0/20** in full observations. Gate 5 and native
campaigns remain **BLOCKED / NOT_RUN**. This audit did not execute node-tar or another
Gate 4 matrix.

Two reader defects were independently reproduced and minimally corrected: lossy raw
stat-number coercion in both conversion paths, and the adapter accepting mismatched
operation association kinds. Neither occurred in the retained matrix and neither
explains its missing replacement coverage. The fixture/acceptance mismatch requires
the separate [Task Contract proposal](effect-replacement-qualification-task-proposal.md),
which is **PROPOSED / NOT APPLIED**. Actual native replacement reachability and the
qualification of its operation-level evidence remain **PENDING_RUNTIME_EVIDENCE**.

## Qualification decision data flow

The authority is [observation v2](../design/entry-effect-observation-v2.md), especially
acceptance criteria 2–4 and 9, and the successful-effect sufficiency table in
[feedback v2](../design/entry-effect-feedback-v2.md). C0/C1/C2 still use final
BEFORE/AFTER snapshots under [Security Contracts](../design/security-contracts.md).
Effect classification is not an oracle verdict.

| Stage / implementation | Input → output | Actual validation / meaning |
| --- | --- | --- |
| `scripts.qualify_node_causal_effects.qualification_cases()`; `builder.build_tar()` | ordered `ArchiveCase` → deterministic complete USTAR bytes | duplicate ordinals/path/content remain distinct; v2 runner reuses the eight v4 fixtures |
| `scripts.qualify_node_effect_observation.run_qualification()`; `effect_pipeline.run_node_tar_effect_case()`; `NodeTarEffectTarget.prepare()` and its `execute()` closure | case + pinned target/profile/bound → `NativeEffectRun` | contained full extraction, unchanged BEFORE/AFTER and `RunResult`; source/artifact/archive binding; `_verify_transport_frame()` verifies terminal transport before AFTER |
| `_node_effect_producer.cjs`: `run()`, `onReadEntry`, patched `checkFs2`, `installEffectWrappers()` | target lifecycle and callback requests/results → globally sequenced raw records | ordinal/path/type/link target comes from `onReadEntry`; async context or owned descriptor associates each operation; conflicting owners are recorded |
| `effect_trace_from_capture()`, `_entry()`, `_effect_event()` | raw starts/completions + expected archive references → typed lifecycle/effect events | pair by correlation ID; require matching entry, operation, association, paths and start sequence; reject gaps, duplicates, unmatched records, conflict, overflow and flush failure |
| worker `observePaths()`, `captureObject()`, `digestRegular()`; adapter `_object()`, `_observation()`, `_path_observations()` | callback-boundary probes → ordered `EffectPathEvidence` | stable lstat/content/readlink probes; explicit PRESENT / ABSENT / NOT_OBSERVED; actual device/inode retained as exact BigInt decimal text; IO failure is not absence |
| adapter `_candidate_effect()` then model `effect_is_realized()` | operation + tri-state object evidence → realized class or `OPERATION_OBSERVED` | class-specific sufficiency and successful outcome required; rename uses destination evidence; identity/type replacement takes priority over open truncation and write modification |
| `export_native_effect_run()`; `verify_native_effect_evidence()`; `reconstruct_native_effect_trace()` / `_reconstruct_trace()` / `_reconstruct_effect()` / `_independent_effect_candidate()` | immutable raw/result/manifest → `VerifiedNativeEffectEvidence` | checksums and exact archive/command/source/coverage/stdout binding; independently parses records, correlation, association and causality; reconstructs trace and compares it to producer derivation; runs `verify_run()` on final-state results |
| `feedback.effect_feedback_eligible()`, `effect_feedback_keys()`, `normalized_effect_signature()` | complete valid successful trace → unique finite key set | only `effect_is_realized()` events produce individual/per-entry/motif keys; unsuccessful/incomplete/invalid traces produce none; inode values, paths and event order are excluded from keys |
| runner `_coverage_acceptance()`, `_summarize()` | independently verified per-run classes/operations → coverage booleans → exact decision token | only full-profile rows count for coverage; all 14 mandatory criteria must pass; any failed criterion produces NOT_QUALIFIED |

The independent candidate classifier is separate from the adapter classifier, but both
use the generic `effect_is_realized()` sufficiency predicate and generic model invariants.
It is an independent raw reconstruction, not an independent second kernel observer.
`verify_run()` verifies final derivations; it does not replay concurrent effects into a
serial final tree or prove that a constructed frame came from a native execution.

## Namespace replacement and evidence sufficiency

For one affected path, `effect_is_realized()` requires successful outcome,
`STATE_CHANGE_VERIFIED`, matching path evidence, observations on both sides, and existing
objects on both sides. It then requires **different `(st_dev, st_ino)` OR different
`ObjectType`**. Equal paths, changed contents, open flags, entry duplication and a
successful callback do not establish replacement. Both components of identity matter.

For same-object regular files, changed digests on write/writev establish content
modification; reduced observed size on open establishes truncation. Namespace replacement
has classifier priority when identity/type changed. A successful open with unchanged
size/evidence does not prove truncation. Missing object evidence remains operation-only;
missing/malformed required identity fields invalidate the trace/frame. Neither produces
successful effect keys.

The contract is **one correlated operation**, not an arbitrary entry-level history.
`unlink(p)` may prove PRESENT→ABSENT and a later `open(p)` / `mkdir(p)` / `symlink(p)`
may prove ABSENT→PRESENT. Those events establish removal and creation; the current
classifier does not combine them into a replacement event. A final path with a changed
type/identity does not supply the absent intermediate operation's evidence. Association
with the same entry or equality of path names alone does not qualify a cross-operation
causal edge. Whether node-tar can produce a single operation with the required evidence
is **PENDING_RUNTIME_EVIDENCE**.

Object identity remains run-local snapshot evidence; inode reuse and arbitrary concurrent
actor attribution are outside the existing snapshot guarantee. No additional guarantee is
introduced by these tests.

## Known-positive and negative controls

[Engine controls](../../../tests/test_effect_coverage_audit.py) use a disposable Linux
runtime volume, independent of the source bind mount. The four filesystem cases retain
real full snapshots, build constructed operation frames from their object evidence, and
round-trip through checksummed export and independent verification.

| Control | Expected / verified behavior |
| --- | --- |
| equal-length write through existing file handle | same identity, differing digest → `regular_file_content_modification` |
| truncate existing file to zero | same identity, size 5→0 → `truncation`, never replacement |
| rename separate regular inode over existing path | old object removed from destination and different inode connected → `namespace_replacement` |
| rename symlink inode over regular path | actual identity and object type change → `namespace_replacement` |
| missing before, after or both observations, callback successful | valid raw operation remains `operation_observed`; no realized effect or keys |
| missing inode, wrong entry/path, wrong start sequence, explicit owner conflict | adapter trace invalid; independent reconstruction rejects; no keys |
| completion association kind differs from start | adapter now invalidates; independent reader already rejected |
| Boolean/float in each of eight BigInt stat fields, tested separately in each reader | both paths now reject instead of manufacturing integer evidence |
| decimal identities above `2**60`, differing by one, with negative mtime text | exact identities/timestamps preserved; replacement reconstructed |
| 20 full duplicate-path rows contain truncation only | only `required_effect_coverage` fails; decision remains NOT_QUALIFIED |
| replacement appears only in stock/minimal rows | cannot satisfy full-profile replacement coverage |

The original synthetic `_complete_matrix()` test also checks the decision function's
all-criteria branch. Its invented replacement labels do not show that `qualification_cases()`
actually produces replacement. Similarly, successful verification of the constructed
filesystem controls means their schema/derivation is valid, not that the native producer
has been qualified. No synthetic evidence was added to the historical matrix.

## Verified defects and minimal patch

1. Adapter `_object()` and independent `_raw_object()` passed raw fields directly to
   `int()`. For example, a post-inode `10.75` became `10`, hiding a purported identity
   difference; `True` became `1`, permitting fabricated identity/state evidence. Both
   readers could accept the altered raw frame with a recomputed digest and matching
   captured stdout. Required stat fields now validate the worker's exact decimal-text
   encoding before conversion. This is schema enforcement, not a change to identity
   semantics, evidence thresholds or protocol identifiers.
2. Adapter `_effect_event()` checked entry/operation/path agreement but not association
   kind agreement. A start marked `async_context` and completion marked
   `handle_provenance` could yield a valid adapter trace although independent
   `_reconstruct_effect()` rejected it. A two-line agreement check restores fail-closed
   consistency.

The production delta is 18 added lines in two reader/converter files. Generic model,
oracle, feedback, worker, fixtures, target options and qualification acceptance are
unchanged. The malformed controls prove these defects independently; all historical
bundles still reconstruct identically after the patch.

## Fixture / acceptance mismatch and historical revalidation

`qualification_cases()["duplicate-path"]` contains regular `duplicate` with `first`,
then regular `duplicate` with `second`. This fixes a duplicate-name overwrite input,
not an inode/type-replacement outcome. `_coverage_acceptance()` requires
`NAMESPACE_REPLACEMENT` in that fixture's full-profile effect union because the frozen
native contract mandates replacement vocabulary coverage. The union is across full
repetitions; it is not a per-repetition threshold and is not weakened here.

Observed raw evidence for all 20 second opens has the same device/inode and regular
type across the operation, size **5→0**, followed by the second write. Full repetition
0 uses raw sequences **13→14**, correlation `operation-4`, ordinal 1 and path
`extract/duplicate`, identity **(2112, 366972)** on both sides. Its post-open digest is
SHA-256 of empty content. The observed open/write sequence supports truncation and
content modification, not replacement. There are no unlink/rename callbacks in these
20 duplicate-path full streams. Runtime source-level explanation and alternative native
replacement ground truth are **PENDING_RUNTIME_EVIDENCE**.

Two fresh read-only analyses, before and after the patch, each independently verified
**320 native bundles + 160 stock records**, all per-run recorded derivations, invalid-frame
injections and terminal timeout/overflow rejection. Both reproduced the exact historical
summary and NOT_QUALIFIED decision. Backend failure evidence is retained from the original
runner; this audit did not manufacture or rerun it.

The original 1,180 files match their checksum manifest. Historical qualification JSON
SHA-256 remains `ca2dae9150813c6df14df10e16de65b1139550a7ecd761a30122c717e4575a90`;
session archive remains `6b0a5b31d52d00347259342683941692181e93515d7f82384df86d9fb1cab1e5`.
Locations and full source/environment/image identities remain in the
[historical summary](../../../experiments/summaries/node-native-effect-observation-qualification-v2.md).
New reader report digests: before
`062c33db30a5b89c09033d6008383757ff0733d82c83379ed632805c291051c0`, after
`9b6fa1561c240a280504f6b3fbd9e69fbdb8ef42b5fb7433284368f85caee8e0`.
The final non-root reader also reproduces the same result; report SHA-256:
`ff9da82edeb6f48bd12f5866a07af2a5475d26998d9ef4f6577c89fb558d22a8`.

## Validation and reproduction

Validation uses the repository's Ubuntu 24.04 / Python 3.12.3 Dev Container, uid/gid
1000, and dedicated `inodefence-effect-audit-runtime` mounted at `/var/lib/inodefence`.
Dependencies installed for this audit: pytest 9.1.1, Ruff 0.17.0, Pyright 1.1.414.
The helper image is derived from existing Dev Container image `ed77dcacf690`, not a
changed target image. A detached baseline worktree at `0eb527f` isolates baseline checks.

- Baseline related tests: **42 PASS**.
- Corrected new tests before production patch: **33 FAIL / 11 PASS** (32 lossy-number
  cases plus one association-kind case). Early fixture-harness errors were corrected
  before recording this regression result; they were not classified as engine defects.
- Final related tests: **89 PASS** (45 audit controls plus 44 existing/extended related tests).
- Initial root-user `make check`: **1 FAIL / 1,386 PASS**; controller requires non-root
  Linux. This is an environment attempt, not the regression failure.
- Non-root clean baseline canonical `make check`: **PASS**, 1,387 tests, Ruff,
  format, Pyright, environment and docs.
- Non-root patched canonical `make check`: **PASS**, 1,434 tests, Ruff,
  format, Pyright, environment and docs. Baseline and patched suite durations were
  197.42 s and 191.30 s; these are engineering validation timings, not target overhead.

From the audit checkout in the Dev Container:

```bash
python -m pytest tests/test_effect_coverage_audit.py tests/test_node_effect_producer.py \
  tests/test_node_effect_qualification.py tests/test_effect_model.py tests/test_effect_feedback.py -q
make check
git diff --check
```

For historical read-only reconstruction, use the original retained
`audit_qualification.py` (SHA-256
`b968ab672acff40d884f6a4add3838639663a9b76bbb4b295cdeb135f73ab3ba`) from the session
archive. Run it with this audit checkout on `PYTHONPATH=src:.`, the historical
`qualification` directory as input, and a **new** runtime report path as `--output`.
Do not invoke `run_qualification()` or `qualify-node-effect-v2` for this audit.
Logs and newly derived reader reports are retained in the dedicated audit runtime
volume and mirrored locally under the ignored audit-worktree directory
`artifacts/effect-coverage-audit/`; original raw evidence is untouched. These reports
are new verification derivatives, not a new target execution dataset.

## Runtime ground truth and prerequisites before another Gate 4

Required Runtime handoff: pinned target/source/image/options/TAR digest and full raw
operation sequence for each proposed positive; independent lstat device/inode/type
evidence before/after the exact operation; association/descriptor/correlation proof;
actual removal/create/rename boundaries and errors; repeated contained stock/minimal/full
controls without serializing target work. Report whether a replacement is one correlated
operation or several operations, and whether probes demonstrably observe it. All of this
is **PENDING_RUNTIME_EVIDENCE**, not inferred from the control frames.

Before another matrix, review/freeze the separate proposal, establish native known-positive
coverage under the unchanged invocation, resolve any multi-operation semantic mismatch,
complete Gate 3 and reader checks on the frozen revision, pin new fixture IDs and hashes,
and allocate new evidence/run/report locations. Preserve this historical negative record
and report new qualification separately. Native integration still requires a subsequently
retained exact QUALIFIED token; this audit supplies none.

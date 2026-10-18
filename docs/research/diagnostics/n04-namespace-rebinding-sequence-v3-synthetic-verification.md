# N04 namespace rebinding sequence v3 synthetic verification

Date: **2026-10-18 KST**
Frozen base: `4b8453f905cc8a5442e1c77fb8e175b16ce7a116`
Task Contract: [v1](../benchmarks/n04-namespace-rebinding-sequence-v3-task-contract.md)
Result: **GENERIC SYNTHETIC ENGINEERING PASS / NATIVE NOT_IMPLEMENTED / NOT_QUALIFIED**

## Question and decision

The review asked whether a separately versioned `namespace_rebinding_sequence` can represent a
verified multi-operation removal→creation/link chain without changing v2's single-operation
`namespace_replacement`. The technical decision is **GO for generic synthetic implementation**.

The additional distinction is bounded and nonredundant. V2 finite keys can retain a realized
removal, creation and supported dependency motif while normalizing away whether their exact raw
destination paths are equal and whether the open absence gap contains a conflicting binding.
V3 derives one composite only when the raw endpoints share the canonical destination, expose
absence after removal and before creation, have a producer-issued branch-continuation record and
have no intervening successful same-path binding. Exact path and provenance identifiers remain
raw evidence and never enter the finite key.

## Implemented evidence boundary

- Schema 3 immutable types retain both v2 endpoint events and one separate dependency record.
- The strict protocol `inodefence-namespace-rebinding-sequence` version `3.0.0` binds the v3
  envelope to a pinned source and the validated v2 raw-stream digest.
- The independent reader rejects duplicate/unknown fields and records, incomplete terminal
  metadata, invalid/rejected/failed/timed-out v2 traces, endpoint drift, provenance/digest/state
  tampering and unsupported endpoint roles. It derives the composite instead of trusting a
  producer label.
- Derivation requires same entry/path, successful realized removal and creation/link, both
  explicit absence observations, exact dependency sequence/correlation binding and no
  overlapping successful same-path namespace-binding effect.
- The feedback projection returns the exact v2 key tuple plus deduplicated finite tagged v3
  keys. No v2 type, enum, protocol, policy ID or C0/C1/C2 meaning changed.

The producer-issued dependency record is sufficient v3 provenance; temporal adjacency and a v2
context edge are neither required nor accepted as substitutes. A future native producer must
prove that the record is emitted from the actual target branch continuation. Synthetic source
identity and digest binding do not establish that native fact.

## Synthetic checks

`tests/test_rebinding_v3.py` contains **18 PASS** checks covering:

- object, symlink and hardlink-destination positive chains;
- equal and unequal separated endpoint inode values;
- truncation without removal, absent dependency, different entry/path, failed operations,
  missing absence and intervening same-path binding negatives;
- incomplete and rejected v2 traces failing closed;
- raw source, v2 digest, correlation, sequence, state, record digest and endpoint tampering; and
- nonredundancy: two traces with equal v2 key sets, where only the qualified same-path trace
  receives a v3 key.

The fixtures are synthetic and in-memory. They are not node-tar PoCs, native raw evidence,
qualification runs or effectiveness measurements.

## Validation record

The final canonical validation used the local immutable check image ID
`sha256:8ea6aad0328af475f0060809bf9bf642399edecee818cb9b771eb19ac635ac09`, Linux aarch64,
Python 3.12.3, Node 22.22.0, user `vscode` UID/GID 1000 and a disposable executable tmpfs at
`/var/lib/inodefence`. The isolated worktree was bind-mounted for validation, while repository
metadata and target-tool dependencies were read-only; filesystem-semantic tests used only the
separate runtime tmpfs.

Final pre-PR result:

- Ruff check: **PASS**
- Ruff format check: **PASS** (357 files)
- Pyright: **PASS** (0 errors)
- pytest: **PASS** (1,580 tests, including 18 v3 checks)
- environment validation: **PASS** (hardlink, symlink and shared-object effect)
- documentation validation: **PASS** (128 Markdown files)

Setup failures were not converted into passing evidence. A macOS full-suite attempt hit the
expected Linux-only boundary (1,075 pass, 233 fail, 2 skip, 271 errors). Linux setup attempts
also exposed missing dependencies, root-only controller assumptions, non-executable temporary
storage and a named runtime volume whose ownership was reset by existing Docker-boundary tests.
The last named-volume attempt produced 1,111 pass, 199 fail and 270 errors; a subsequent tmpfs
run passed all 1,580 tests but documentation validation could not resolve the copied worktree's
host `.git` pointer. The final bind-mounted worktree run above resolved only that validation
harness issue and passed the complete `make check` command. The two dedicated temporary Docker
volumes were then removed.

## Scientific result and exclusions

This work reduces uncertainty about representability: a strict, finite, target-independent v3
composite can distinguish the required same-path dependency gap without weakening v2 or relying
on inode inequality. It does **not** evaluate whether this feedback improves fuzzing, whether the
current node-tar instrumentation can emit trustworthy dependency records, or whether any
security boundary is violated.

- V2 native decision: unchanged `V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`.
- V3 generic implementation: **IMPLEMENTED / SYNTHETIC TESTED**.
- V3 native producer and qualification: **NOT_IMPLEMENTED / NOT_RUN / NOT_EVALUATED**.
- P0/P1/P2 effectiveness, B0/B1/B3 pilot and historical rediscovery: **NOT_RUN** under this
  contract.
- Human expert approval: **not claimed**.

The next v3 action, if authorized, is a separately frozen native dependency-producer and
archive-only qualification contract. It must pin source guards, images, branch-token semantics,
fixtures, repetitions, resource limits, evidence paths and failure injections. It must not be
combined with an effectiveness campaign.

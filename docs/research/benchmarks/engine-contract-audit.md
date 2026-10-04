# Engine capabilities and research assumptions

**Implementation audit, not an experiment result or full repository audit.**
Audited main: `a22d20127d8e01bc539363764582ef907d51cbf1` (2026-10-04), merged
into the published research branch without rebasing. This supersedes the original
`433ffb0f49f82476b1c3d152e647a5c9a9710485` audit. Current source and tests take
precedence over historical readiness summaries and stale adapter docstrings.

Evidence levels apply only to the explicitly bounded claim:

- **A — implemented and tested:** direct source plus relevant regression coverage.
- **B — implemented, partially validated:** narrower validation exists; the
  intended benchmark or environment has not been qualified.
- **C — design/documentation only:** proposed behavior with no executable binding.
- **D — NOT_IMPLEMENTED:** required capability absent from the audited code.

Reachability conclusions are source-derived analysis, not measured search results.
External advisory facts belong to the [candidate matrix](candidate-matrix.md).
Predictions, future work and future measurements are separate from these facts.

| Capability / bounded assertion | Level | Direct source and regression evidence |
| --- | --- | --- |
| Immutable raw-text ordered archive model | A | [archive.py](../../../src/inodefence/model/archive.py), [model tests](../../../tests/test_core_model.py) |
| Deterministic UTF-8 USTAR; explicit encoding rejection | A | [builder.py](../../../src/inodefence/builder.py), [builder tests](../../../tests/test_builder.py), [mutation/builder tests](../../../tests/test_mutator_builder.py) |
| Four benign seeds and eight uniform independent operators | A | [generator tests](../../../tests/test_generator.py), [mutation tests](../../../tests/test_mutator.py) |
| Controlled-run lstat snapshots and C0/C1/C2 persistent evidence | A | [observer tests](../../../tests/test_observer.py), [semantic tests](../../../tests/test_state_semantics.py), [pipeline tests](../../../tests/test_pipeline.py) |
| Signature v2, fingerprints, independent novelty and unique-case retention | A | [semantic tests](../../../tests/test_state_semantics.py), [corpus tests](../../../tests/test_feedback_corpus.py), [corpus integration](../../../tests/test_feedback_corpus_integration.py) |
| Seed-inclusive trusted-reference campaigns and lineage | A | [campaign tests](../../../tests/test_campaign.py), [campaign integration](../../../tests/test_campaign_integration.py) |
| Strict config binding, frozen provenance and completed raw export | A | [config tests](../../../tests/test_experiment_config.py), [provenance tests](../../../tests/test_provenance.py), [export tests](../../../tests/test_campaign_export.py) |
| Direct-process Node adapter for controlled benign fixtures | A | [Node tests](../../../tests/test_node_tar.py); no generated-input campaign |
| Container policy, lifecycle and fail-closed transport logic | A | [backend unit tests](../../../tests/test_container_backend.py); fake-runtime tests cannot establish real isolation |
| Container helper boundary on documented Docker/OrbStack platform | B | [execution validation scope](../../../src/inodefence/execution/README.md), [six real-runtime regressions](../../../tests/container_integration/check_boundary.py); inherited platform evidence, not a new benchmark run |
| Pinned benign Node target image and metadata validation | B | [image packaging](../../../tools/node-tar/README.md), [metadata-only regression](../../../tests/container_integration/check_node_image.py); no archive execution |
| Node backend/config/provenance/full campaign integration | D | Campaign still rejects ISOLATION_REQUIRED; no container binding in pipeline/config |
| General component replacement, alternative policies, incremental failure export | C/D | Proposed here; absent from production mutator/config/campaign/export |
| C3/C4 and operation tracing | C/D | Canonical definitions exist; no oracle implementation |
| Benchmark qualification, rediscovery and comparative evaluation | D | No such execution is performed by this package |

## Inputs the engine can represent and generate

[ArchiveEntry](../../../src/inodefence/model/archive.py) represents regular,
directory, hardlink and symlink entries. Order, duplicates, absolute-looking
paths and unresolved link text survive in ArchiveCase. NUL and surrogate text
are rejected. [Builder](../../../src/inodefence/builder.py) emits deterministic
strict UTF-8 USTAR with fixed owner/time metadata; no PAX/GNU extension headers,
malformed headers or byte-level parser differentials are generated.

The model accepts empty cases, arbitrary bytes for regular-file content and
permission/special mode bits in `0..0o7777`. Directory/link entries cannot carry
content. There are no device/FIFO/sparse/header-extension entry types or uid/gid/
mtime fields. ArchiveCase does not describe pre-existing trees, target invocation
or multi-archive sessions. Entry spelling is input text, not an observed canonical
path. USTAR path names need a valid name/prefix split (100/155 UTF-8 byte fields);
link targets have the 100-byte linkname limit. Model acceptance alone does not
guarantee serializability. Over-limit text raises at the builder; current Campaign
does not turn that exception into a counted no-op or target rejection.

[Minimal seeds](../../../src/inodefence/generator/minimal.py) are four benign
cases in fixed order: regular file, directory plus file, regular plus internal
hardlink, regular plus internal symlink. Links refer to preceding internal files.
These are development baselines, not known-vulnerability recipes.

[Mutation v1](../../../src/inodefence/mutator/operators.py) has exactly eight
operators: add_entry, remove_entry, duplicate_entry, reorder_entries,
mutate_path, add_hardlink, add_symlink, mutate_link_target. The convenience
mutate API samples uniformly, once, including inapplicable no-ops. New entries
are appended except duplicates, which are inserted at random positions.
There is no arbitrary type conversion or new-directory constructor.
There is no content or mode mutation of an existing entry; random content is
introduced only by add_entry. Seeds are independent campaign inputs, not a
merged archive containing all four structures. A directory-bearing descendant
can only inherit, duplicate or rename the directory present in its ancestor seed.

New names come from `a`, `b`, `file`, `dir/item`, with empty, dot-relative,
parent-relative or root prefixes. Existing text only receives `../`, `./`, `/`
prefixes or `/..`, `x` suffixes. This preserves all original characters: it
cannot substitute arbitrary path components or spell any requested sentinel
name. Link target selection can copy an existing entry path, but cannot compose
an arbitrary multi-component target. Reordering alone cannot create missing
names, filesystem state or relationships.

## What current C0/C1/C2 actually classify

Canonical definitions are [security-contracts](../design/security-contracts.md);
implementation is [oracle/contracts.py](../../../src/inodefence/oracle/contracts.py).
Every returned process status is followed by observation; exit status is not a
security verdict.

| Contract | Evidence accepted now | Important blind spot |
| --- | --- | --- |
| C0 | Before/after existence, identity or type transition at any observed path outside extract/, including HARNESS | External in-place content/metadata changes alone; transient effects; paths outside the observed sandbox; direct path-use events |
| C1 | Post-state internal object and configured external sentinel have equal `(st_dev, st_ino)` | Symlink referent identity, aliases removed before AFTER, external objects that are not protected sentinels |
| C2 | Configured sentinel existence, type, identity, digest, size, mode, nlink, uid/gid, mtime/ctime changes | Unprotected external objects; atime (deliberately excluded); effects reverted between snapshots |

Creating an internal hardlink can produce C1 **and C2 metadata evidence** because
sentinel nlink/ctime change even without writing its bytes. C0 need not fire:
the new directory entry is internal, and nlink alone is not a namespace change.
An internal symlink pointing outside produces no C1 merely by existing; lstat
observes the link itself. Do not claim all symlink poisoning is detected.

[Observer](../../../src/inodefence/observer/snapshot.py) walks the complete run
sandbox with lstat and no symlink following, hashes regular files, and raises
ObservationError on incomplete capture. It cannot reconstruct an operation
sequence or identify its actor. All setup must precede BEFORE; all target
children must finish before AFTER; bookkeeping must follow AFTER. Any violation
of that lifecycle invalidates attribution, rather than earning a path exemption.

## What normalization discards, and retention preserves

[StateSignature v2](../../../src/inodefence/feedback/signature.py) discards
HARNESS objects/identity members, case/TAR identity, raw device/inode values,
timestamp values, uid/gid and nonregular size/nlink. It retains scoped paths,
types, modes, regular size/digest/nlink, symlink text, non-singleton identity
groups, protected paths and EXTERNAL changed-field labels. Run-root-prefixed
absolute symlink text is normalized textually, without referent resolution.
Consequently random file contents and ever-growing path spellings can create
novel states without advancing toward a vulnerability.

[Fingerprints](../../../src/inodefence/feedback/fingerprint.py) keep contract ID
and observed path/changed-field labels (C0/C2), or internal/sentinel relations
(C1). Raw values, process status, duration and prose are discarded. One
fingerprint summarizes the whole evidence tuple of one violated contract;
creation and deletion with identical path/field labels can share a fingerprint.
Counts measure representation diversity, not distinct bugs.

[Corpus](../../../src/inodefence/feedback/corpus.py) tracks state and violation
novelty independently: interesting = new state OR new fingerprint. It advances
seen indexes even for already retained cases, admits each case_id once, keeps
only first-admission signature/fingerprints and selects uniformly with caller
RNG. Full RunResult and lineage belong to CampaignResult, not CorpusEntry.

All returned process statuses use the same feedback. SUCCESS is not a retention
requirement, and neither reject nor timeout is a security verdict. No path-only,
state-only, violation-only, adaptive or persistent Corpus mode is configurable.

## Campaign, configuration and export constraints

[Campaign](../../../src/inodefence/campaign.py) executes the ordered initial
seeds first, consuming budget but no search RNG. One Random(seed) serves parent
selection and mutation thereafter. No-op, reject, failure and timeout consume
one execution when a result returns. Infrastructure exceptions propagate; an
aborted run does not return a partial CampaignResult. Memory is O(budget) full
run evidence. The exporter writes completed manifest v2/steps JSONL; no reader,
checkpoint or resume exists.

[ExperimentConfig](../../../src/inodefence/experiment_config.py) currently
accepts exactly minimal-generic-v1, uniform-generic-v1 and
state-v2-or-violation-v1-uniform-parent-v1. Merely naming a baseline in JSON
cannot enable it. Config ID is configuration identity, separate from frozen
source/environment/target/sentinel provenance. Image/dependency locks, CPU,
filesystem/mount properties, CWD and environment qualification need explicit
supplemental evidence where not supplied by infrastructure work.

`run_configured_campaign` binds the exact ordered IDs of all four minimal seeds
and adapter TargetProvenance before Campaign. Lower-level Campaign accepts other
explicit unique cases, but that does not make them a supported configured seed
profile. Config rejects unknown fields/policies and version placeholders
`latest`, `installed`, `current`; an exact version string is not an artifact hash.
The reference CLI selects only the Python adapter. Frozen provenance contains
source revision/dirty, four platform strings, target ID/version/timeout/trust
declaration and sentinel name/digest/mode; it has no container image/backend/
resource-policy identity. Manifest v2 separately records stored execution
provenance and exporter environment; exporting later cannot attest the earlier
environment. Raw steps retain logical content for reconstruction, but no
deserialize/replay reader exists.

[Targets](../../../src/inodefence/targets/README.md) declares node-tar
ISOLATION_REQUIRED. Locked benign tooling is Node 22.22.0 / tar 7.5.22, not a
vulnerable benchmark pin. Adapter options are strict=true, preservePaths=false;
other defaults remain upstream. Campaign still rejects third-party execution
before runtime/provenance capture. ORAS and GNU benchmark adapters do not exist.

## Container helper/image validation versus Node configured integration

The second coherent refresh includes merged PR #37. Main now packages the benign
Node 22.22.0/tar 7.5.22 target in a [digest-pinned multistage image](../../../tools/node-tar/Dockerfile).
The build stage installs committed npm locks; the distroless runtime contains
Node/modules/worker/lock without shell/package-manager/build tools at the standard
paths checked by the test. `--identify` reports exact versions and worker/lock
SHA-256. The [metadata-only real-container test](../../../tests/container_integration/check_node_image.py)
verifies those identities through the backend and cleanup. CI now runs it after
helper boundary checks. It executes no archive and establishes neither candidate
version compatibility nor campaign readiness. Mutable tags are build conveniences;
execution requests require a local immutable image ID. Image contents are pinned
inputs, but bit-for-bit image rebuild equality is not claimed (D023).

Main now implements [execution/container.py](../../../src/inodefence/execution/container.py)
and an explicit trusted host broker. [D022](../../DECISIONS.md) and the
[execution README](../../../src/inodefence/execution/README.md) are canonical for
policy and platform limits. The controller validates its actual Linux container
identity/volume binding. Requests pin a local SHA-256 image ID, explicit argv,
current disposable run and timeout. One volume subpath is mounted at the identical
absolute run path; no stable mount alias is implemented.

Preparation/policy verification happen before BEFORE; execution verifies stopped
PID namespace before AFTER; removal follows AFTER. Targets see the whole writable
controlled run (including archive and outside), while source/home/adjacent runs/
runtime socket are excluded. The backend enforces network-none, read-only rootfs,
non-root uid/gid, dropped capabilities, no-new-privileges, private namespaces,
memory/PID/file-size/open-file/tmpfs limits and bounded captured streams. It has
no direct-process fallback. Infrastructure failures raise BackendError, and
ownership-checked cleanup cannot fabricate a completed observation.

**Inherited validation:** the execution README records Docker 29.4.0/OrbStack
Linux arm64 helper validation, with six real-runtime cases for policy, shared
sentinel identity, exit/failure, detached descendants, timeout, startup failure
and output bounds. [CI](../../../.github/workflows/ci.yml) adds a distinct
`container-integration` job; `make check` alone does not run that suite. Results
on one kernel/runtime do not qualify every deployment or benchmark image.
Per-file FSIZE is not a total storage quota; CPU/file count/volume use are not
fully bounded. Procfs/devices/ephemeral mounts are outside snapshot evidence.
Hard broker kill or daemon loss may prevent cleanup. These limits require review
for future budgets; they do not justify changing controls in this PR.

**NOT_IMPLEMENTED integration:** pipeline still calls TargetAdapter.run inside
the observation window and has no prepared-container lifecycle hook. NodeTarTarget
uses its existing direct-process benign-fixture worker. Campaign has no binding
that proves the backend meets ISOLATION_REQUIRED, ExperimentConfig has no image/
backend policy fields, and ExecutionProvenance/export have no frozen container
configuration. The rejection diagnostic still says no validated boundary is
available; it describes the campaign path, not the newly present helper backend.
Older ExecutionSafety/Node docstrings also predate the helper. These are follow-up
documentation/integration gaps, not permission to bypass the gate.

[STATUS](../../STATUS.md) remains ENGINEERING FOUNDATION: benchmark and evaluation
readiness are false; Node configured campaigns have zero executions. Primary
engineering must finish backend/config/provenance binding to the pinned image
and a small benign full-path smoke, then freeze for full audit and required fixes. Selected benchmark
grammar, policies, independent qualification and evaluation still require the
[post-audit tasks](post-audit-backlog.md) and a new Task Contract.

## Moving-main review rule

At each research milestone fetch origin/main and inspect HEAD..origin/main.
Re-read changes to target contract, isolation, ExperimentConfig, provenance,
CampaignResult and export before updating assumptions. At a clean milestone
merge origin/main if needed (never overwrite main or rebase unfinished edits).
Record the final checked SHA in [handoff](post-audit-backlog.md).

Re-audit only affected assertions after a coherent main update. Generation,
observer/oracle, signature, policy IDs, lifecycle and provenance claims can all
become stale. Refresh the catalog's engine_revision and handoff alongside this
document. External-source dates and release claims have their own evidence ledger.
A future primary completion signal is not benchmark execution authorization.

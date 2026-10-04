# Engine capabilities and research assumptions — Phase-4 refresh

**Current implementation review and planning, not benchmark results.**
Audited integrated main: `d1982e4cf3174e28d4eeb73af7b32829f6751b30` (2026-10-04).
This existing PR #35 branch incorporates that main with a history-preserving merge
from its actual published head `5b3745e40e5d43c3b79fa9fe7ca1872f1d2e1106`.
The [Phase-4B final audit #47](https://github.com/TheWaitForAGI/InodeFence/pull/47)
controls current Engine/Security Contract/Research dispositions. It completed before
this refresh, found no new Blocker/Major/Minor, and closed EN-001–EN-004 in code.

Audited main still has residual EN-005 navigation drift. The audit recommends
**NO-GO for unconditional global Phase-4 closeout** pending documentation disposition.
This Draft proposes those navigation corrections and closes EN-006 planning drift
on its branch; it does not retroactively fix main or replace the Runtime/global
final verdict. The code foundation permits this safe refresh. Neither benchmark
implementation nor evaluation readiness is asserted.

Pre-audit freeze (#40–#42), Phase-1 audits, Phase-2 cross-review/Global Findings
Freeze v1 and Phase-3 Runtime #45 / Engine #46 fixes are completed. No item below
asks to repeat those fixes. Global closeout and new P01–P11 Task Contracts remain
future. All 15 candidate executions remain **NOT_RUN**; no candidate is READY.

## Current disposition of historical review incidents

| Historical ID | Canonical finding | Current disposition and direct evidence |
| --- | --- | --- |
| EC-01 | CR-001 / Runtime EX-001 | RESOLVED by #45: IsolatedTarget observes/verifies versions and worker/lock identity before freeze and each archive; false direct/replaced declarations fail; [Node tests](../../../tests/test_node_tar.py) and [isolation tests](../../../tests/test_isolation_provenance.py) |
| EC-02 | CR-002 / Runtime EX-002 | RESOLVED by #45: actual prepared Entrypoint/Cmd/WorkingDir/Env checked before start; [backend mismatch/omission/order tests](../../../tests/test_container_backend.py) |
| EC-03 | Earlier STATUS incident | RESOLVED by #42; not reopened by EN-005 residual current navigation |
| EN-001 | Frozen Major | CLOSED in code by #46/final re-audit: raw path bytes preserved in actual USTAR header or entry-indexed failure before execution; [builder regressions](../../../tests/test_builder.py) |
| EN-002/003 | Frozen Minors | CLOSED in code: public typed immutable evidence and exact difference labels; [evidence validation](../../../tests/test_evidence_validation.py), shared model/comparison helper |
| EN-004 | Frozen Minor | CLOSED in code: disjoint tagged internal StateSignature v3, raw snapshots preserved, no referent resolution or v2 compatibility |
| EN-005 | Frozen navigation Minor | Original three locations fixed; additional integrated-main remnants corrected by this unmerged planning/navigation proposal; final acceptance remains separate |
| EN-006 | PR #35 drift Minor | This refresh supersedes #39 engine/capability/backlog claims; delivery and validation recorded in [handoff](post-audit-backlog.md) |
| EX-003 / EX-004 | Runtime Minor / uncounted gap | CLI descendant lifecycle fixed; actual export fsync/order/readback regression coverage strengthened, respectively. Neither supplies a campaign failure ledger. |

The historical #39 review and its synthetic incident record are retained below,
with explicit superseding statuses. Its old counts, v2 keys and pending smoke/fix
statements describe that old revision only. No benchmark NOT_RUN record is erased.

## Implemented now, with bounded evidence

Evidence A = implemented with source/regressions; B = narrower platform validation,
not general benchmark qualification; C/D = planning or absent implementation.

| Capability | Level / present evidence | Remaining distinction |
| --- | --- | --- |
| Raw ordered immutable ArchiveCase / deterministic strict UTF-8 USTAR | A; model, builder and fixture tests | Builder rejects lossy delegated splits even if another split might be possible; not a general archive encoding fuzzer |
| Four benign seeds / eight uniform operator slots | A; generator/mutation tests | Finite affix/stem grammar still cannot spell outside/default sentinel; P02 remains needed |
| Full raw lstat BEFORE/AFTER / exact StateChange / C0/C1/C2 | A; observer/state/pipeline tests | Persistent controlled-run effects only; actor/transient/referent/inode-reuse limits remain |
| Tagged StateSignature v3 / whole-contract fingerprints / independent novelty Corpus | A; state and feedback tests | State OR violation retention; interesting and fingerprints are not vulnerabilities; B0/B1/projections absent |
| Bounded seed-inclusive campaigns / uniform retained parents / lineage | A; campaign tests | No operator record, full-step clock, partial failure ledger, reader/replay/checkpoint/resume |
| Strict ExperimentConfig v1/v2 / stored ExecutionProvenance envelope v2 | A; config/provenance tests | Config identity is not full runtime attestation; dirty patch/Python binary/full closure limits remain |
| Container policy v1 / IsolationProvenance internal v2 / verified artifact origin | A; Node/backend/isolation regressions | Image/probe code, Docker/runtime/kernel and broker progress remain trusted |
| Manifest v4 / optional same-bundle config / staged fsync/readback/no-replace export | A; export unit/integration tests, EX-004 strengthening | Complete results only; sync regressions do not prove power-loss recovery or persist aborted campaigns |
| Real helper / pinned Node image / fixture and benign configured full path | B; [exact-main CI 37197933974](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37197933974) | 6 boundary, 2 image, 10 Node-target and 1 benign campaign checks passed; this is not historical pair qualification |
| Candidate images/locks/profiles and Linux effect/fixed qualification | D; all catalog execution states NOT_RUN | Static registry/source checks remain static; P01/P06+ future |
| ORAS/GNU adapters, M1 dictionary, B0/B1 and projections, P04/P05 tooling, C3/C4 | C/D | Not implemented by this research refresh |

## Signature/config/export compatibility

StateSignature internal schema is **v3**, with `run:<raw suffix>` for exact current
run root or textual descendants and `literal:<raw target>` otherwise. Exact root,
repeated slash and `..` spelling remain meaningful text. Literal `$RUN/...`,
`run:...` and sibling absolute paths do not collide with a run anchor. Raw snapshots
remain unchanged and no referent lookup occurs. Equality is stable across allocation
roots for equivalent run-anchored text. ArchiveCase IDs and basic canonical envelope
v1 are unchanged; no v2 key reader, migration or compatibility is provided.

ExperimentConfig's accepted B3 identifier remains
`state-v2-or-violation-v1-uniform-parent-v1` to preserve its existing config IDs.
That is a **legacy identifier**, not a claim that the actual signature remains v2.
Current B3 compares v3 state OR generic violation novelty and selects uniformly over
retained unique cases. B0/B1 and projection IDs below are future specifications.
A future policy revision must explicitly bind the representation and decision model;
no hidden parser fallback or renamed production ID is introduced here.

IsolationPolicy stays v1; IsolationProvenance is internal v2 with
`artifact_origin=image-identification-v1` for verified artifacts. ExecutionProvenance
and CampaignResult envelopes stay v2, RunResult/step/basic envelopes v1, manifest v4.
Historical isolation v1 evidence is not upgraded into verified facts retroactively.
Config JSON can be exported as optional experiment.json in the same complete bundle,
with stored ID/checksum validation. Unconfigured exports can still omit it. Original
logical bytes/order and TAR hash/format remain in complete raw steps; no general
reader/replay or P04 failure ledger exists.

## Current research meaning and remaining backlog

The real/reference pipeline remains case → mutate → lossless-or-reject build →
target → BEFORE/AFTER → comparison → C0/C1/C2 and v3 state → fingerprints → Corpus
→ uniform parent → next mutation. Mutator is target independent, Oracle contains
no known-CVE/version predicates, and target status does not determine contract truth.
Retention/stats are search evidence, not paper results. Whole-contract fingerprint
classes are not root-cause or bug counts. Novel benign bytes/paths can dominate
states. Snapshot coverage and runtime trust are unchanged (EN-007–EN-011 remain valid).

P01 freezes candidate-specific pins/setup using existing binding and attestation;
P02 supplies generic protected-component addressability; P03 adds alternative policy
binding and truthful admission diagnostics; P04 adds full-step timing/infrastructure
failure records; P05 adds hash-verified reader/replay/adjudication. P06+ qualification,
pilot and formal evaluation remain NOT_RUN. No speculative replacement architecture,
new oracle contract or CVE recipe is introduced. See the [ordered backlog](post-audit-backlog.md).

## Validation scope

Integrated-main final re-audit: engine selection 545 passed, runtime-seam selection
242 passed, explicit acceptance witnesses 18 passed, make check 803 passed plus
Ruff/format/Pyright/environment/docs. Canonical exact-main CI passed both jobs; real
container logs record 18/18 removed benign-campaign contexts. The audit lane read
CI evidence rather than claiming a local Docker rerun. Refresh-branch full validation
is recorded separately in the handoff. None is benchmark evidence.

<details>
<summary>Historical #39 implementation review — superseded current-state claims</summary>

This retained body refers to `efe1dbb5ec3787dee42eadb643646be2b326b489`.
Old pending/OPEN/version statements below are historical, governed by the current
disposition table above. For immutable original content and original code context,
use the [published pre-refresh record](https://github.com/TheWaitForAGI/InodeFence/blob/5b3745e40e5d43c3b79fa9fe7ca1872f1d2e1106/docs/research/benchmarks/engine-contract-audit.md).
Relative source links in the retained body now resolve to this branch's current tree.

# Engine capabilities and research assumptions

**Implementation audit, not an experiment result or full repository audit.**
Last independently reviewed main: `efe1dbb5ec3787dee42eadb643646be2b326b489` (2026-10-04).
The research branch now contains this main revision. Review scope: current #36–#39
execution/backend/broker, Node image and invocation, pipeline/runtime lifecycle,
isolation/config/provenance/campaign admission/export, and their tests/docs.
PR titles, bodies, base/head and changed-file lists were checked against the
maintainer Task Contract. This replaces the older f02024c delta-only review.
Generation, observer/oracle and Corpus were read for contract/architecture fit;
this is not a full repository audit or candidate execution qualification.

#39 implements frozen container policy, pre-execution runtime/image facts,
worker/lock records, ExperimentConfig v2, exact-wrapper campaign admission and
manifest v3. Its normal bind path is implemented; EC-01 below remains an
independent Major about public artifact composition. Node configured smoke and
pre-audit freeze are still pending in the reviewed STATUS. Local canonical
validation passed 585 tests on this merged engine using `PYTHONPATH=src make check`;
container suites were source-reviewed, not run locally by this lane.

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
| Node invocation descriptor, enforced backend composition and prepared pipeline lifecycle | A | [Node descriptor/binding](https://github.com/TheWaitForAGI/InodeFence/blob/f02024cc520868056c26919b128d18628012e8f2/src/inodefence/targets/node_tar.py), [composition](https://github.com/TheWaitForAGI/InodeFence/blob/f02024cc520868056c26919b128d18628012e8f2/src/inodefence/targets/isolated.py), [portable Node tests](https://github.com/TheWaitForAGI/InodeFence/blob/f02024cc520868056c26919b128d18628012e8f2/tests/test_node_tar.py), [pipeline lifecycle tests](https://github.com/TheWaitForAGI/InodeFence/blob/f02024cc520868056c26919b128d18628012e8f2/tests/test_pipeline.py); fake backends do not validate containment |
| Container policy, lifecycle and fail-closed transport logic | A | [backend unit tests at f02024c](https://github.com/TheWaitForAGI/InodeFence/blob/f02024cc520868056c26919b128d18628012e8f2/tests/test_container_backend.py); fake-runtime tests cannot establish real isolation |
| Container helper boundary on documented Docker/OrbStack platform | B | [execution validation scope](../../../src/inodefence/execution/README.md), [six real-runtime regressions](../../../tests/container_integration/check_boundary.py); inherited platform evidence, not a new benchmark run |
| Pinned benign Node target image and metadata validation | B | [image packaging](../../../tools/node-tar/README.md), [metadata-only regression](../../../tests/container_integration/check_node_image.py); no archive execution |
| Controlled benign Node fixtures through the real container backend and pipeline | B | [explicit container fixture suite](https://github.com/TheWaitForAGI/InodeFence/blob/f02024cc520868056c26919b128d18628012e8f2/tests/container_integration/check_node_target.py), [main CI](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37180369305); not a configured campaign or candidate qualification |
| Frozen isolation/config/provenance and contained campaign admission | A with EC-01 limitation | [isolation/admission/export tests](../../../tests/test_isolation_provenance.py), [pure values](../../../src/inodefence/model/isolation.py); real configured Node smoke remains NOT_RUN |
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
run evidence. The exporter writes completed manifest v3/steps JSONL; no reader,
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
The reference CLI selects only the Python adapter. ExperimentConfig v2 adds the
complete explicit IsolationPolicy and binds it to the composed target before
campaign execution. Reference v1 JSON/config ID remains unchanged. Campaign freezes
ExecutionProvenance v2 once before the first case: source/environment/target/
sentinels plus policy, runtime/API/platform/image facts and descriptor artifacts.
Each step rejects policy/artifact/target drift against that stored value.
Manifest v3 exports the stored provenance without querying current defaults;
exporter environment remains separate. Policy facts never enter StateSignature
or violation fingerprints. Image base/build identity and full dependency closure
still require the supplemental artifact ledger. EC-01 qualifies the artifact
attestation claim. Raw steps retain logical content and TAR SHA-256; no reader/
replay or failure ledger exists.

[Targets](../../../src/inodefence/targets/README.md) declare node-tar
ISOLATION_REQUIRED. Benign packaging uses Node 22.22.0 / tar 7.5.22, unrelated to
selected historical pins. Adapter options remain strict=true, preservePaths=false.
Campaign admits only the exact IsolatedTarget for isolation-required declarations;
subclasses, uncontained descriptors and unavailable/mismatched boundary facts fail
before campaign setup. Public run_case is a low-level trusted adapter API, with
no independent campaign admission gate: caller-supplied adapter code is trusted.
The actual Node descriptor has no run/prepare path, so run_case cannot give it a
local subprocess fallback. A new target descriptor/backend is trusted controller
implementation, not something archive bytes can select. ORAS/GNU adapters are absent.

## Container helper/image/fixture validation versus Node configured integration

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
PID namespace before AFTER; normal removal follows AFTER. In f02024c, a start
deadline expiring while the container remains created instead removes and verifies
its absence before AFTER, preventing a delayed daemon start; controlled run paths
remain available to observation. Targets see the whole writable
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

**Implemented in f02024c (D024):** NodeTarTarget is an immutable invocation
descriptor with no direct-process/run fallback. `bind(backend, image_id, timeout_seconds)`
identifies exact Node/tar versions and worker/lock digests inside the immutable
image and returns IsolatedTarget. The trusted ExecutionBackend owns containment;
the descriptor owns argv and process classification. The
[prepared pipeline](https://github.com/TheWaitForAGI/InodeFence/blob/f02024cc520868056c26919b128d18628012e8f2/src/inodefence/pipeline.py)
enters setup before BEFORE; execution returns with the target context stopped
before AFTER, and context exit cleans up after AFTER, including on observation
errors. The Python reference retains its existing run path. IsolatedTarget raises OutputLimitError
on truncated output, preserving the bounded raw prefix; incomplete evidence is
an infrastructure exception, not a completed RunResult or security verdict.

**Inherited validation, not execution by this research lane:** main CI at
f02024c passed both `check` and `container-integration`. The latter now explicitly
runs eight benign Node fixture checks: four minimal seeds with identity/link
assertions, ordinary invalid-format rejection, timeout, version drift and AFTER
failure cleanup. This validates the low-level contained invocation on that CI
platform; it does not exercise run_configured_campaign or any catalog candidate.

**Implemented in #39 (D025):** frozen isolation/config/provenance and exact-wrapper
campaign admission. These are no longer missing infrastructure. The approved benign
configured Node smoke is still NOT_RUN in this reviewed main. Historical fixture
CI does not supply that evidence. STATUS remains ENGINEERING FOUNDATION, with
benign full-path smoke, pre-audit freeze, full audit and fixes preceding benchmark
work. No selected candidate was qualified or executed.

## Independent execution review

All assertions below refer to the last-reviewed SHA above. Source links resolve
to its merged implementation. Tests were inspected, including real-runtime
suites and failure cases; fake Docker responses do not establish containment.

| Question / invariant | Observed implementation and limit |
| --- | --- |
| Public Node fallback/bypass | NodeTarTarget has no run or subprocess API; IsolatedTarget requires ExecutionBackend. Campaign rejects uncontained/subclass paths before freeze/setup. Low-level run_case trusts custom adapter implementations, as described above. |
| Filesystem exposure | create_command mounts exactly one current-run volume subpath at the same absolute path; prepare inspects that policy and rejects implicit image volumes. Source/home/socket/neighbor paths are absent by design and helper canaries test this on the documented platform. The complete controlled run is writable/observed. |
| Network/privileges | network=none, cap-drop ALL, no-new-privileges, positive non-root UID/GID, read-only rootfs and private PID/IPC/cgroup namespace policies are passed/inspected; helper checks live effects. |
| Resource enforcement | PID/memory/swap/nofile/fsize/tmpfs/shm passed and inspected; output transport drains and retains bounded prefixes. FSIZE is per file; total storage/file count/CPU quotas are absent and documented. |
| Image/command defaults | Immutable local ID required; image/created-container IDs match. Entry point/workdir/environment overrides are generated. Actual Config.Entrypoint/Cmd/WorkingDir/Env are not rechecked in prepare: EC-02 test gap. |
| Broker/control separation | Host/controller use a dedicated trusted stdio channel; target streams are encoded as base64 fields. No target output is parsed as Docker requests. DockerCLI retains at most 1 MiB per stream and drains the rest; StdioDockerClient bounds its response line. |
| Timeout/start race | Created-at-deadline state destroys/verifies identity before returning; running deadline kills/waits and verifies exited/Pid=0. No AFTER on unverified execution. |
| Detached descendants | PID namespace termination precedes returned execution; real suite exercises setsid child/grandchild and checks stopped context. Kernel/runtime correctness remains trusted. |
| Cleanup ownership/reuse | Random per-container name plus broker invocation owner; cleanup inspects label then removes full returned ID and verifies absence. No prune/name-wide destruction. Concurrent malicious daemon/controller identity replacement is outside the trusted-runtime model. |
| Observation failures | Backend context surrounds BEFORE/execute/AFTER; finally cleans up on either snapshot exception. Normal remove follows AFTER; startup-race removal is the documented exception and changes no controlled-run files. |
| Bookkeeping and attribution | Open runtime FDs and container preparation precede BEFORE; target stops before AFTER; normal backend/runtime removal follows AFTER. Worker uses pipes, no observation-window harness logs. C0 includes HARNESS; C1/C2 retain raw pre/post identity/effects. |
| Cleanup failure | Removal failure raises BackendError; no completed RunResult escapes that context. Host broker has ownership-checked fallback. Hard broker kill/daemon outage can prevent verified cleanup; documented operational limit, not proof of safe termination. |
| Architecture | Campaign knows generic IsolatedTarget, not Docker; backend has no Node branches; observer/oracle/feedback/mutator do not import Docker/Node/CVE metadata. ORAS/GNU can compose new invocation/image; ORAS needs a declared controlled CWD extension. |

### EC-01 — unverified worker/lock facts on public composition

- **Severity:** Major. **Reviewed main:** efe1dbb5ec3787dee42eadb643646be2b326b489.
- **Affected:** targets/node_tar.py::NodeTarTarget constructor/bind;
  targets/isolated.py::IsolatedTarget.capture_isolation; campaign.py::run_campaign.
- **Observed:** bind identifies image contents, but the public frozen descriptor
  can be reconstructed/replaced with different digest values (or moved to another
  same-version image). capture_isolation replaces the backend artifacts with the
  descriptor values. Campaign freezes them and checks subsequent consistency only
  against that declaration. Worker invocation checks version text, not digests.
- **Evidence:** using only tests/test_node_tar.py::ControlledBackend, bind returns
  worker `b` repeated 64 times; construct
  `IsolatedTarget(replace(bound.invocation, worker_sha256="d" * 64), bound.backend)`
  and call run_campaign with the four benign seeds/budget=4. It returns four fake
  steps and frozen `node-tar-worker` SHA-256 `d` repeated 64 times. No extraction,
  container, affected package, PoC or exploit archive was executed. The same
  unverified assignment is visible statically on the real backend path.
- **Why it matters:** exported worker/dependency facts can disagree with the
  immutable image used; future benchmark provenance/replay cannot treat them as
  attested identities. This is not an isolation escape or a defect in ordinary bind.
- **Expected invariant:** values labeled actual artifact facts match the bound
  image, including supported public composition paths; asserted metadata is distinct.
- **Suggested direction:** primary engineering should enforce verified binding
  or re-identify/check artifacts before freezing. Regression must reject changed
  worker/lock digests and stale artifacts after same-version image replacement,
  before the first campaign case. Existing tests validate normal bind and later
  drift, but do not challenge this pre-freeze composition.
- **Historical status at #39:** OPEN; now RESOLVED by #45 (CR-001). Originally escalated in [PR #35 comment](https://github.com/TheWaitForAGI/InodeFence/pull/35#issuecomment-5977145667).
  No production patch contributed by this lane.

### EC-02 — command/default inspection coverage

- **Severity:** Minor (test gap). **Reviewed main:** same SHA.
- **Affected:** execution/container.py::prepare/create_command;
  tests/test_container_backend.py::FakeDocker and policy regression.
- **Observed:** generated argv overrides entrypoint, workdir and image env, but
  prepare does not compare those actual Config fields. FakeDocker omits them;
  the portable command test checks env clearing but not entrypoint/workdir.
- **Why it matters / reasoning:** a future incorrect worker/CWD override could
  survive this portable suite; ORAS depends on exact CWD. Current Docker argv is
  correct and no live mismatch is established, so this is not Major.
- **Expected invariant:** command/CWD/env actually used agree with the invocation.
- **Suggested direction:** negative Config mismatch tests plus explicit argv
  assertions; consider actual inspection before start. Real helper/Node behavior
  provides narrower current coverage, not a general arbitrary-CWD contract.
- **Historical status at #39:** OPEN; now RESOLVED by #45 (CR-002 actual invocation verification and regressions).

### EC-03 — contradictory primary status paragraph

- **Severity:** Minor. **Reviewed main:** same SHA.
- **Affected:** docs/STATUS.md, execution-readiness versus Next work paragraph.
- **Observed / evidence:** readiness and the later D025 summary correctly say
  contained admission/policy binding is implemented; the older Next work paragraph
  still says only trusted references can campaign and campaign binding is absent.
- **Why it matters:** research could mistakenly plan to reimplement completed
  infrastructure. The explicit latest summary is used for this handoff.
- **Expected invariant:** implementation status is consistent within STATUS.
- **Suggested direction:** primary's freeze documentation should reconcile the
  historical paragraph with #39; source/tests are unchanged by that correction.
- **Historical status at #39:** OPEN; RESOLVED by #42. The separate EN-005 navigation remnants are not this incident.

### Deliberate incorrect-variant reasoning

| Incorrect variant | Existing evidence that should catch it (source reasoning, no sabotage run) |
| --- | --- |
| Remove campaign safety gate | uncontained/descriptor/subclass tests in test_node_tar and test_isolation_provenance |
| Add local Node fallback | descriptor-has-no-run test and ExecutionBackend type checks; actual Node has no subprocess import |
| Accept mutable image tag | request/policy/binding negative tests and actual image-ID equality |
| Mount whole runtime/source/home/socket or bridge network | exact mount and network inspections, wrong-policy test, real helper canaries/network assertion |
| Remove cap-drop/no-new-privileges/rootfs/user | command assertions, actual inspect policy, live helper privileges/rootfs checks |
| Omit a resource from config identity | per-resource identity/strict schema tests; command enforcement is separately checked by live helper |
| Skip cleanup on AFTER exception | portable preparation lifecycle plus real Node AFTER-error cleanup test |
| Recompute provenance during export | test_frozen_before_execution_and_export_ignores_changed_backend_defaults |
| Put execution/container metadata into novelty | signature/corpus semantic regressions exclude execution/config/TAR identity; no container-specific same-state comparison yet |
| Forge descriptor artifacts before freeze | NOT caught: EC-01 reproduction accepted |
| Lose command/CWD override | Partial coverage only: EC-02 |

### Isolation/provenance readiness mapping

| Required fact | Implemented / frozen before first case / exported / config-bound |
| --- | --- |
| Immutable target image ID | Yes / Yes / Yes / v2 IsolationPolicy |
| Backend implementation and runtime/API/architecture | Yes / Yes / Yes / implementation policy bound; actual runtime version is provenance, not config ID |
| Network, filesystem view, UID/GID, capabilities, no-new-privileges, rootfs | Yes / Yes / Yes / complete v2 policy |
| PID/memory/swap/nofile/fsize/tmpfs/shm/capture limits | Yes / Yes / Yes / resources and fixed policy values; no CPU/total storage quota |
| Target version and timeout | Yes / Yes / Yes / TargetProvenance; worker checks version |
| Worker and npm lock identity | Normal bind Yes; EC-01 / descriptor values frozen / Yes / absent from ExperimentConfig; anchored indirectly by image only |
| Base image, build recipe, npm SRI/transitive closure, compiler | Packaging/source or future pin ledger / no complete automatic capture / no dedicated fields / supplemental research freeze required |
| Explicit ORAS process CWD / input transport identity | Not implemented / absent / absent / post-audit requirement |

No Blocker found in this reviewed scope. One open Major, one Minor test gap and one Minor documentation drift;
full repository merge-readiness is not asserted. C3/C4/transient effects remain
outside implemented oracle scope. Experiment-validation classifies no new
benchmark outcome: all candidate execution fields remain NOT_RUN.

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

</details>

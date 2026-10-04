# Pre-audit infrastructure readiness v1

Classification: READY FOR FULL CODE / ARCHITECTURE AUDIT. This is a limited integration
freeze and engineering validation, not the full audit or a benchmark/evaluation result.
Evidence level: **REPRODUCIBLE (engineering plumbing only)**; no validated vulnerability
finding or paper-ready evidence is claimed.

## Implemented trust and execution path

Trusted controller → explicit synchronous host Docker broker → disposable untrusted target
container. The controller owns cases, campaign/Corpus/mutation, observations/security truth,
configuration, provenance and export. The runtime/backend is a trusted execution mechanism.
The target receives only its runtime image and current controlled run; no repository/home,
host bind, credentials, network or runtime socket is passed into it. The existing Dev Container
is unchanged. PR34's failed in-container namespaces remain a historical supported-environment fact.

ExperimentConfig v1/v2 → actual target/policy binding → fail-closed campaign gate → backend
runtime/image/artifact attestation → frozen ExecutionProvenance → explicit minimal seeds →
bounded Campaign → Corpus/mutation → run_case → prepared target container → stopped PID
context → AFTER Observer → C0/C1/C2 + Signature → Feedback → CampaignResult → staged evidence.
Target identification precedes this path and executes metadata only in its own contained context.

Each run_case remains one archive/execution/BEFORE-AFTER pair. Preparation is before BEFORE;
container removal and runtime deletion are after AFTER, also on observation errors. A deadline
before daemon launch removes that identity before AFTER to prevent delayed execution. Backend
errors remain exceptions; target SUCCESS/REJECTED/FAILED/TIMED_OUT remain distinct outcomes.

## Implemented boundary

| Setting | Enforced configuration |
| --- | --- |
| Runtime | Docker-compatible Linux, explicit host context/controller/volume binding |
| Image | Immutable local SHA-256 image ID; optional actual repository digests, no tag fallback |
| Filesystem | Only current core-run named-volume subpath at identical absolute Linux path |
| Writable controlled run | archive/input.tar, extract/, outside/sentinels; HARNESS is observable |
| Root filesystem | Read-only; tmpfs /tmp32MiB noexec/nosuid/nodev and private shm16MiB |
| Network | none; helper verifies only loopback/outbound ENETUNREACH |
| Credentials | Non-root actual controller uid/gid, locally1000:1000; cap-drop ALL; NNP enabled |
| Namespaces | Private PID/IPC/cgroup; no host namespaces/privilege grants |
| Limits | Memory512MiB including swap; PIDs64; nofile1024; per-file FSIZE64MiB |
| Wall time | Explicit bounded target timeout, smoke10s; trusted Docker operations separately bounded |
| Environment | Image values cleared; explicit PATH/LANG only |
| Diagnostics | First1MiB per stream; drain overflow, truncated evidence aborts visibly |
| Lifecycle | Unique UUID/name ownership, stop/wait/verify before AFTER, remove by full ID/verify absence |

The benign helper covers controlled visibility/canaries, read-only root, credentials/caps/NNP,
network, limits, shared sentinel identity, normal/failure/timeout/startup-error, detached child
and grandchild with explicit synchronization, and bounded output. Container removal does not
rely on process-group or host-PID identity. While target PID1 lives, orphan reaping is its responsibility.

## Actual validation and changes

| PR | Engineering purpose | Canonical tests | Real container checks |
| --- | --- | --- | --- |
| [36](https://github.com/TheWaitForAGI/InodeFence/pull/36) | Backend, host/controller broker, benign boundary/CI | 532 | Helper6 |
| [37](https://github.com/TheWaitForAGI/InodeFence/pull/37) | Pinned minimal Node/tar distroless image | 532 | Helper6 + image1 |
| [38](https://github.com/TheWaitForAGI/InodeFence/pull/38) | Contained invocation, prepared pipeline, startup-timeout fix | 535 | Helper6 + image1 + target8 |
| [39](https://github.com/TheWaitForAGI/InodeFence/pull/39) | Frozen isolation provenance, config identity, fail-closed admission | 585 | Helper6 + image2 + target8 |
| [40](https://github.com/TheWaitForAGI/InodeFence/pull/40) | Actual benign configured campaign, stop/raw retention/CI | 598 | Helper6 + image2 + target8 + campaign1 |
| [41](https://github.com/TheWaitForAGI/InodeFence/pull/41) | Atomic no-overwrite completed export, optional config bundle | 614 | Helper6 + image2 + target8 + campaign1 |

All merge heads require both CI jobs, focused tests, make check and diff-check. Filesystem
probes regular-file/directory/hardlink/symlink and small Python-reference campaigns passed
where relevant. Portable mocks are separated from actual container checks, never used as
containment evidence. Wrong variants omitted network, removed the subclass admission guard,
excluded config resource identity, ordinary rename, and omitted config binding were detected
by relevant regressions; production source was restored. No existing safety or race test was
weakened. The seven previous Node fixtures were moved intact into the mandatory real backend suite.

Local validated smoke: Node22.22.0/tar7.5.22, Docker29.4.0/API1.54/Linuxarm64, fixed RNG11/budget8,
four ordinary minimal seeds plus four mutations. Config ID
5fe3249f599d74259fd4f76aeb6da085e66e7e075d00053cd1ba1b4b9c88ee13;
image sha256:4b73ec653ee295ce63c58b9bac6db7dd9e5d584e12704ee4db740a307b8f1697.
Actual seed content, indexes0–7, prior retained-parent lineage, exact metadata/policy/config,
frozen provenance, canonical JSONL, stopped/absent contexts and root cleanup were asserted.
Eight SUCCESS; Corpus observations8/interesting6/retained6/unique-states6/fingerprints0;
C0/C1/C2 had no violated verdict in the observed scope. Nine contexts (one identify/eight
archives) were created and removed; all roots removed. Interesting is not vulnerable.

Manifest v4 clean-main local bundle: experiments/raw/benign-node-container-20261004-clean-main/
(ignored raw evidence, source ee76fa285808cc1d5f0bcc52281fbdbb29709823/dirty=false).
SHA-256 steps 312e1265b17e894a08960584dbdabdf57270433db6949c8547f5e9f02289beed;
manifest c065b31853151f36add9432e469919cb457d9955d66db12995531974ca80f551;
experiment b0920e91776e9493dd5d5fc30b950e82b19d2e060fa7b36dffb1e2090445bec2.
Read-only comparison of three preserved local runs confirmed identical indexes/origins/
parent lineage, feedback decisions, normalized signatures and statuses; source revisions/export
implementation changed as recorded, while raw allocation/timing bytes remain distinct.
Earlier raw checksums/conditions and the re-run command are in the
[benign smoke record](benign-node-container-smoke-v1.md). CI independently runs amd64
Docker28.0.4/API1.48 and retains actual produced artifacts. Platform/build image and config
identities differ; raw inode/time/duration bytes are not expected to repeat.

An unexpected C0/C1/C2 verdict stops the approved validation after preserving raw RunResult,
already-frozen provenance and immutable config; no automatic vulnerability analysis follows.
The regression uses an intentional disposable sentinel mode change, not an exploit archive.

## Focused lifecycle and architecture review

Direct process helpers, Python/Node adapters, runtime, pipeline, backend/transport/broker and
campaign were inspected for cleanup order, orphan/zombie behavior, PID reuse, timeouts,
closed pipes/stream deadlock, double waits, ownership, partial deletion and AFTER errors.
No further reproduced lifecycle defect remained after the startup-timeout regression in PR38.
The legacy same-group helper is used only by controlled tests and explicitly cannot contain
detached children; it is not the production Node execution path. The trusted Python worker
creates no descendants. ESRCH/ENOENT inspection races, readable live-child detection and
permission-error propagation remain tested.

Static AST import inspection covered40 Python modules/97 internal import edges; no prohibited
reverse dependencies were found. Focused code inspection confirms model stays pure; mutator
has no feedback/target dependency; Oracle has no target/backend dependency; feedback/Observer
have no target/container dependency; generic execution contains no Node policy; Campaign
imports the narrow composition rather than concrete Docker command construction. A future
ORAS/GNU-tar implementation supplies its invocation/image/version/classification and can
reuse the backend without Campaign/Oracle/Observer/Corpus changes. Replacing the backend
requires a separately validated trusted implementation, not target-specific generic branches.

## Attestation and export assessment

The image ID anchors complete runtime image content compactly; exact Node/tar metadata,
image architecture/available repository digests and actual worker/lock SHA-256 accompany it.
This is sufficient infrastructure identification for the next full audit. No massive recursive
hashing or machine-specific executable hashes were added to config identity. Python patch
version/source/environment identify the reference path, not exact Python binary contents.
Target image and raw artifact retention/availability remain caller responsibilities; pinned
build inputs do not promise bit-for-bit rebuilding or independent runtime attestation.

Config v1 bytes/IDs remain compatible; v2 binds complete isolation policy. Provenance/result
envelopes are v2, manifest writer is v4, historical schemas remain historical. Step JSONL,
ArchiveCase/RunResult/signature/feedback encodings and campaign RNG/budget are unchanged.
Exporter serializes only stored provenance. Optional pre-read config JSON must hash to the
stored ID. Files are flushed/fsynced/read-back verified in a sibling stage, synced, published
via Linux renameat2(RENAME_NOREPLACE), then parent-synced. Existing/concurrent destinations
are never overwritten. This follows the [Linux rename manual](https://man7.org/linux/man-pages/man2/rename.2.html).

## Remaining limits and next task

- Snapshot-only persistent controlled-run evidence; no transient-event/actor attribution,
  symlink referent/full direct-use tracing or sandbox-wide OS evidence. C3/C4 remain unimplemented.
- Runtime/kernel/image and trusted controller/broker are trusted; no kernel/container-escape proof.
  Volume-subpath and Linux/libc/filesystem support are required. Podman/remote workers, other
  kernels/platforms and WSL2 container backend have not been independently validated here.
- Per-file FSIZE/PID/memory/open-file bounds are enforced; no total-volume/file-count/CPU quota.
- Dirty source bit is recorded, but dirty patch contents and exact Python executable are not
  preserved. Local image ID does not provide a remote image distribution/retention guarantee.
- Hard broker SIGKILL/daemon loss can defeat cleanup; visible errors are not manufactured success.
  No broad scavenger exists. Output truncation aborts incomplete evidence and timeout retains prefixes.
- Pre-publication export exceptions clean staging/final absence. Hard interruption can leave
  staging; post-publication parent-fsync error leaves a complete bundle and propagates; parent
  creation is not rolled back. Unsupported publication has no fallback. Emergency unexpected
  evidence writes can remain partial on I/O failure. CI artifacts/local raw retention are finite.

ENGINE READY and BENCHMARK INFRASTRUCTURE READY within this implemented benign execution
path. READY FOR FULL CODE / ARCHITECTURE AUDIT. EVALUATION NOT YET RUN. No CVE rediscovery,
GNU-tar/ORAS implementation, unknown-vulnerability campaign or effectiveness claim was added.

Next task: full repository-wide code, architecture, security-contract, reproducibility,
maintainability and test-quality audit before any benchmark/CVE evaluation begins.

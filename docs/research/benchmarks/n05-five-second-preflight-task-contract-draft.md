# Proposed Task Contract: N05 five-second final-state preflight v2

Status: **IMPLEMENTED CANDIDATE / SYNTHETIC TESTED / NOT_AUTHORIZED / NOT_RUN /
AWAITING EXECUTION-SOURCE AND CONTROLLER FREEZE**.

This is a new attempt proposal. It does not amend or reopen the consumed N04 attempt, and it
does not authorize a historical target invocation. The exact attempt identifier and destinations
below are reserved by this draft, but no ledger or evidence directory may be created until a
separate human authorization freezes a runnable source revision.

## Objective and claim boundary

Current Layer: Layer 6 historical-target readiness and evidence validation.

The only question is whether the exact retained node-tar 7.5.2 and 7.5.3 images remain
correctly identified, contained and benign-ready with an exact five-second target timeout.
Allowed terminal decisions are `PREFLIGHT_PASS`, `PREFLIGHT_FAIL` and
`PREFLIGHT_INCONCLUSIVE`. None is a rediscovery, feedback-effectiveness, native-transition or
human-correspondence result.

## Frozen attempt and destinations

| Field | Exact proposed value |
| --- | --- |
| Attempt ID | `n05-five-second-preflight-v2-attempt-001` |
| Mode ID | `preflight-node-n05-5s-v2` |
| Linux evidence root | `/var/lib/inodefence/evidence/n05-five-second-preflight-v2-attempt-001` |
| Host ledger root | `/Users/choijiwng/Projects/InodeFence-n05-five-second-preflight-v2-attempt-001-host-ledger` |
| Optional read-only host copy | `/Users/choijiwng/Projects/InodeFence-n05-five-second-preflight-v2-attempt-001` |
| Runtime volume | `inodefence-n05-preflight-runtime-v2-attempt-001` |
| Target timeout | exactly 5 seconds per archive |
| Attempt wall ceiling | 30 minutes, including inspection, readers and cleanup |
| Target archive budget | 8 benign extractions; no retry |

All four destinations must be absent at admission. Authorization, invocation, clean-source and
loaded host-code origin checks run before host-ledger creation and Docker access; rejection there
does not consume the attempt. Once those checks pass, creation of the host ledger consumes the one
attempt even if later Docker identity, containment or metadata admission fails. The consumed N04
ledger/evidence paths and attempt ID are forbidden inputs and must remain unchanged.

## Exact source and image identities

The audited repository baseline is main
`8d29982c26cebfcce7a413b3ba9177fcd28078de` (merged PR #111). The bounded host-only
transport/stderr correction candidate is draft PR #112 at
`0eca90f44a249d3ab1e66966b7ab3cfe80f79055`.

Draft PR #112 at `0eca90f` deliberately leaves the N04 mode consumed. The dependent N05
implementation candidate adds `preflight-node-n05-5s-v2`, its independent reader, actual
authorization-record admission and the destinations above. **There is still no authorized
execution-source SHA in this draft.** Review must first finish on one clean integration commit.
The separate authorization record then freezes that full commit, every executable file named by
the implementation and the controller image before the host ledger may be created. A branch name,
mutable tag or digest-only claim is not an admitted source or authorization.

The target candidates remain exact and do not depend on that missing execution source:

| Binding | affected | fixed |
| --- | --- | --- |
| Node / node-tar | 22.22.0 / 7.5.2 | 22.22.0 / 7.5.3 |
| Image ID | `sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520` | `sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f` |
| arm64 platform manifest | `sha256:b5ae7f5d2f85f12fa417ecece3e9089001266cc6bf4a997724c225a40ce8b542` | `sha256:3a1bcf4dffcd21ddc4fa6645980bebd96dceda4ceee0ddfe033abd0d50dd6ee0` |
| npm tarball SHA-256 | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` |
| lock SHA-256 | `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` | `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24` |
| build record SHA-256 | `960b28e0699af5c6ac35709d2d14d7a8818ea8cfed0039f86b3b0217c68997ef` | `e6adeae1456771dce3e0d20acb3e231ceefd5e726a4c8bf554fc402f62ac8960` |

Both images must report worker SHA-256
`feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b`.
The candidate controller image remains
`sha256:8ea6aad0328af475f0060809bf9bf642399edecee818cb9b771eb19ac635ac09`;
it must be re-inspected and re-frozen with the eventual execution source rather than assumed
available. Mutable tags are never identities.

The only admitted host package paths are a new nonsymlink directory dedicated to this attempt:

```text
/Users/choijiwng/Projects/InodeFence-n05-package-inputs-v2-attempt-001/tar-7.5.2.tgz
/Users/choijiwng/Projects/InodeFence-n05-package-inputs-v2-attempt-001/tar-7.5.3.tgz
```

The retained N02 `build/affected` and `build/fixed` directories may be read only after their
per-file and build-record identities are reverified. The N02 evidence root contains no npm
tarball bytes, so package identity must come from the two newly retained exact tarballs.

## Trust boundary and command policy

The trusted route is `/usr/local/bin/docker` on the macOS/OrbStack host, Docker context `orbstack`,
to one fresh unprivileged
Linux arm64 controller. Host-only metadata may use only these exact read-only forms through
`DockerCLI.run_host_inspection()`:

```text
docker info --format {{json .}}
docker container ls --all --no-trunc --filter volume=<exact-volume> --format {{.ID}}
```

They must never cross the controller-visible stdio transport. The stdio transport retains the
existing lifecycle-only allowlist (`version`, image/volume/container inspect and bounded
container create/start/wait/kill/rm/top). No arbitrary `exec`, shell, file read, tag resolution,
daemon-wide listing or caller-provided Docker option is admitted.

The host must retain the exact first 1 MiB of controller stderr while continuing to drain the
pipe. It records byte count, SHA-256 and a required truncation boolean in the terminal record
and host manifest. Missing stderr capture after controller launch, an undrained pipe, malformed
UTF-8-independent byte handling or a digest mismatch is infrastructure-invalid and
`PREFLIGHT_INCONCLUSIVE`.

The host reads the canonical authorization JSON from the one frozen nonsymlink host path before
creating the attempt ledger. It verifies the caller-supplied checksum against those bytes, parses
and validates the complete record, copies the bytes into the host ledger and transports the same
checksum-bound bytes to the controller. The controller publishes them into Linux evidence and the
independent reader parses them again. The record binds the attempt/mode, human decision text,
clean source revision and executable-file digests, exact fresh controller ID, controller and target
image identities, Docker daemon ID/version/API and context, source/evidence/ledger/volume paths,
five-second timeout, eight-extraction budget,
wall-clock bound and both isolation profiles. `pilot_authorized` is always false. The human name
field records attribution but is not a cryptographic signature; its trust remains an external
review responsibility.

Before creating that ledger, the host also binds the active `scripts/container_host.py` entry and
the loaded N05 host-side project modules (`n05_preflight`, container backend and Docker client) to
their exact canonical nonsymlink paths under the authorized worktree and rehashes those actual
origin files against the authorization. This applies equally to `python -m` and imported-module
test execution. An unknown origin, source-less loader, alternate checkout/install, editable-install
path drift or symlink is rejected. The controller entry and independent reader are not imported
merely for host attestation; their bytes remain frozen by the complete executable-file list and are
executed later from the same read-only source mount. This is project-file provenance, not Python
interpreter or third-party-library attestation. No evidence schema changes result from this guard.

The controller has no Docker socket/CLI, uses network `none`, read-only rootfs, UID/GID 1000,
cap-drop `ALL`, no-new-privileges, no devices, private PID/IPC/cgroup namespaces, 1 GiB memory
and swap, 256 PIDs and a 256 MiB `nosuid,nodev` tmpfs. Its only source mount is the eventual
exact clean execution clone, read-only at `/workspaces/InodeFence`. The dedicated local volume
is mounted at `/var/lib/inodefence`, carries a new N05 owner label, has no options, is at most
15 minutes old and has only that controller as consumer.

Target containers retain `docker-volume-subpath-v1`: network none, read-only rootfs, UID/GID
1000, cap-drop `ALL`, no-new-privileges, private namespaces, 512 MiB memory/swap, 64 PIDs,
1,024 open files, 64 MiB file-size limit, 32 MiB `/tmp`, 16 MiB `/dev/shm`, one fresh runtime
subpath and at most 1 MiB per captured target stream. Target descendants must be stopped before
AFTER, and the runtime root must be absent after return.

## Controls and exact schedule

Before any target archive:

1. the unchanged oracle control must produce C0/C1/C2 all false;
2. the harness hardlink control must produce C0 false and C1/C2 true; and
3. source, host, controller, volume, package, build and both image admissions must pass.

Then execute `minimal_seed_corpus()` once in its existing order on affected and once in the
same order on fixed: four plus four extractions. The runner recomputes the four logical case IDs
and deterministic USTAR digests. There is no mutation, known-class/positive-control replay,
candidate matching, corpus evolution or retry. All target executions use exactly five seconds.

Readiness passes only when all eight results are SUCCESS without timeout, preserve input TAR
bytes, show no C0/C1/C2 observation, reproduce the expected benign namespace/identity state,
bind the exact provenance above and prove cleanup. A complete unexpected target outcome is
`PREFLIGHT_FAIL`; missing/corrupt evidence, identity/containment mismatch, observer error,
deadline, stderr-capture failure or cleanup uncertainty is `PREFLIGHT_INCONCLUSIVE`.

## Publication, cleanup and independent decision

The host ledger is created before Docker inspection and publishes `started.json`, a bounded
`controller-stderr.bin`, `terminal.json` and `manifest.json` without overwrite. An ordinary
failure must still publish the actual exception, invoked target names, deadline state and cleanup
status. The Linux runner publishes every completed prefix and a checksummed raw manifest; a fresh
process independently reads it. The host verifier rehashes both Linux manifests, stderr and the
cleanup terminal before an overall PASS is possible.

Fallback cleanup may inspect and remove only exact invocation-owned target names. Ownership
mismatch, uncertain removal or any cleanup error is retained and downgrades the result to
`PREFLIGHT_INCONCLUSIVE`. It never triggers a retry.

## Fail-closed conditions and authorization gate

Stop before host-ledger creation until a reviewed clean N05 integration source and controller image
are frozen in the separate authorization record. Also stop before ledger creation and without
consuming the attempt when the running host entry or loaded approved host module cannot be tied to
that source by canonical path and digest. Stop before target execution on any dirty/unreviewed
source, missing exact authorization record, wrong package/image/controller/platform identity,
mutable reference, unexpected host command, controller-visible host inspection,
privilege/mount/resource drift, evidence-path existence, reader unavailability or containment
mismatch.

Authorization requires all of the following:

- an exact clean implementation commit and executable file digests;
- a reviewed immutable controller image bound to that source;
- canonical Linux `make check` and focused mocked broker/ledger regressions;
- independent adversarial review; and
- an explicit human authorization for this attempt ID and no other.

This contract cannot emit a human N01 token or a pilot token. It does not authorize the
4,000-execution B0/B1/B3 pilot, a historical positive-control replay, native-v3 qualification,
P0/P1/P2 effectiveness, a ten-second fallback or reuse of the N04 attempt.

The current PR #108 Track A preparation path is not yet a consumer of this evidence: it accepts
caller-supplied SHA-256 strings without opening either the preflight host/Linux records or the
pilot authorization record, and it names the N04 environment profile. Before Track A preparation,
that path must call the N05 host verifier on the actual retained records, require an overall
`PREFLIGHT_PASS`, parse and retain the complete separate pilot authorization, bind the same clean
source/target/timeout/isolation identities, and admit the pilot controller/volume conditions. This
is an integration gate, not permission to change B0/B1/B3, C0/C1/C2, A1/A2/A3 or P0/P1/P2.

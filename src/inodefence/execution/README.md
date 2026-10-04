# Disposable Linux target containers v1

Trusted InodeFence controller → explicit stdio host broker → Docker-compatible
runtime → disposable untrusted target container. The current Dev Container keeps
its existing privileges and receives neither Docker CLI nor runtime socket.
`scripts.container_host` executes the trusted controller as `vscode`; only the host
broker uses Docker. The broker is a synchronous CLI process, not a network daemon.
Its authority is the operator's existing Docker context; controller code and the
runtime are trusted. Target stdout/stderr are base64 response data and cannot
become broker instructions.

`ContainerRequest` binds an immutable local SHA-256 image ID, explicit argv, an
existing disposable run root and timeout. `ContainerExecutionBackend.prepare()`
creates and checks the container before BEFORE. `PreparedContainer.execute()`
starts it once, captures bounded output and verifies stopped state before AFTER.
Context exit removes the container after AFTER, including on observation errors.
If the start deadline expires in created state, removal and absence verification
precede AFTER to prevent a delayed daemon start; no controlled-run paths are changed.
Missing runtime/image, creation/startup, policy mismatch and cleanup failures are
visible `BackendError`s. No direct-process fallback exists. Production Node invocation uses the narrow ExecutionBackend/IsolatedTarget
composition and pipeline preparation contract. Campaign admission
and frozen container provenance remain subsequent work; the current
third-party campaign safety rejection is unchanged.

## Enforced view and policy

- One named-volume subdirectory: the current `core-run-*` at its identical Linux
  absolute path. No source/home/host bind or runtime socket is passed to a target.
  Backend construction checks the controller's volume mount at `/var/lib/inodefence`.
  The controller must use Docker's default ID-based hostname; a different controller
  ID/custom hostname is rejected before runtime creation. Run path components are
  restricted to unambiguous ASCII mount-option spelling and opened without symlinks.
  No image-declared anonymous volumes are accepted.
- Entire controlled run is writable, including `archive/`, `extract/`, `outside/`.
  This preserves namespace and sentinel effects for C0/C1/C2; archive/ is not an
  Oracle exemption. Adjacent runs and the parent volume are not exposed.
- Network `none`, read-only rootfs, non-root controller uid/gid, cap-drop ALL,
  no-new-privileges, separate PID/IPC/cgroup namespaces; no host namespaces or
  additional privileges. PID mode is Docker's checked empty/default private mode.
- Memory 512 MiB with memory+swap limit also 512 MiB; 64 PIDs; RLIMIT_NOFILE 1024;
  RLIMIT_FSIZE 64 MiB per file; `/tmp` tmpfs 32 MiB/noexec/nosuid/nodev; private
  `/dev/shm` 16 MiB. Values are explicit immutable `ResourcePolicy` settings.
- Image environment values are cleared; only explicit PATH and LANG are supplied.
  Image entrypoint/workdir/user are replaced with the request/policy.
- Target runs as container PID 1. PID-namespace destruction stops detached
  descendants on primary exit or SIGKILL timeout. There is no additional init
  wrapper that could disguise an executable startup error as target failure.
  While the primary is alive, orphan reaping remains its responsibility.
- No daemon log persistence (`log-driver=none`). Attached output retains the first
  1 MiB per stream, drains the remainder and marks truncation in the outcome.
  IsolatedTarget aborts incomplete output with OutputLimitError retaining that prefix.
  Timeout retains the captured prefix; it need not contain final buffered bytes.
  CLI deadlines include pipe draining and waiting even after both pipes close.
- Unique names and invocation UUID labels. Cleanup checks ownership, removes by
  full identity, verifies absence and never prunes other executions. The host
  broker repeats that same cleanup contract if the controller crashes/disconnects.

## Actual runtime validation

On the host, from the repository, with Python 3.12:

```bash
docker build -f tools/container-helper/Dockerfile -t inodefence-helper:v1 .
IF_HELPER_IMAGE=$(docker image inspect inodefence-helper:v1 --format '{{.Id}}')
PYTHONPATH=src python3.12 -m scripts.container_host --context orbstack \
  --controller <running-dev-container-ID> --volume inodefence-runtime \
  --image "$IF_HELPER_IMAGE" validate
```

The exact immutable ID is supplied, never inferred from a mutable tag at execution.
The benign helper image is pinned to Python 3.12.13/bookworm by base manifest digest.
Six explicit real-runtime checks cover view/network/read-only rootfs, uid/gid,
capabilities/NNP, limits and shared sentinel identity, normal/failed execution,
detached child/grandchild, timeout, startup failure and bounded output. These are
in `tests/container_integration/check_boundary.py`, outside default unit collection;
the host runner invokes them explicitly with pytest capture disabled for the
reserved broker channel. Unavailable runtime is an error, never a skipped PASS.

## Limits

Validated on Docker 29.4.0/OrbStack Linux arm64 with the repository Ubuntu/Python
controller. CI runs the same real-runtime suite separately. Docker volume-subpath
support is required; unsupported runtimes fail at creation. No Podman/remote-worker/
other-kernel guarantee is claimed. Container runtime/kernel and image contents
remain trusted mechanisms; this is not proof against kernel/container escape.
Device/procfs and ephemeral container mounts are not part of snapshot evidence.
C0/C1/C2 still cover persistent controlled-run state, not all filesystem operations.
FSIZE is per-file, not a total volume quota; file count/storage/CPU are not fully
bounded. Hard host-broker SIGKILL or daemon loss can prevent cleanup; errors cannot
manufacture cleanup evidence or a completed campaign. No global scavenger exists.

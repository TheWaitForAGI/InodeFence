# Contained node-tar replacement diagnostics

These tools investigate runtime behavior and existing effect classifications.
They neither run Gate 4/5 nor change qualification fixtures, options or criteria.
The Python controller loads the **unchanged** native adapter/reader from a separate
reference checkout at `0eb527f88aa8a4015544d2f6b0eabfebe079bf18`. Reference source
hashes are checked against that revision before execution and audit.

## Preparation

Use a diagnostic worktree and a separate detached reference worktree. Build the
native target using the reference checkout's `tools/node-tar/Dockerfile`. Build a
Dev Container from `.devcontainer/Dockerfile`, resolve both image IDs and create a
**new** Linux named volume. Do not reuse a qualification volume/controller/tag.

Build the sibling diagnostic image from the resolved local images. BuildKit's
`FROM` expects image references, not bare local `sha256:...` IDs; use the local
repository reference **with its resolved digest**, for example:

```bash
docker build -f tools/node-tar/diagnostics/Dockerfile \
  --build-arg TARGET_IMAGE=inodefence-node-tar:diagnostic-native@sha256:<resolved-digest> \
  --build-arg CHECK_IMAGE=inodefence-dev:diagnostic@sha256:<resolved-digest> \
  -t inodefence-node-tar:diagnostic-probe .
```

The sibling copies the unchanged producer from the pinned image, so this PR does
not require unmerged producer files in its own source tree. Native extraction
uses the native target image; stock/branch/strace extraction uses the sibling.
This environment difference precludes instrumentation overhead comparisons.

Start a **new** trusted Dev Container. Bind this diagnostic checkout at
`/workspaces/InodeFence`, the reference checkout read-only at
`/workspaces/reference`, and the new volume at `/var/lib/inodefence`. Worktree Git
metadata must be readable at the absolute path in each worktree's `.git` file;
bind the common Git directory read-only there. Give UID/GID 1000 ownership of
the new volume root, and install `.[dev]` in this new container. Do not run the
repository's post-create script against shared existing runtime/Codex volumes.
The controller requires neither a Docker CLI nor a socket.

## Execution

On the trusted WSL host with Python 3.12 and Docker:

```bash
python3 tools/node-tar/diagnostics/investigate.py run \
  --reference /workspaces/reference \
  --output /var/lib/inodefence/<new-diagnostic-directory> \
  --controller <full-new-controller-ID> --volume <new-volume> \
  --native-image sha256:<resolved-native-ID> \
  --image sha256:<resolved-probe-ID> \
  --broker-log <new-host-broker-jsonl> --repetitions 2
```

`--reference` is a **controller path** for `run` and a local path for `audit`.
The controller checks runtime/volume binding through the existing trusted
backend. Each target receives only its own fresh sandbox subpath. Baseline
profiles preserve strict=true/preservePaths=false, with other options omitted.
The unchanged producer is not run for unlink/keep/newer option controls.
Strace uses an explicit `seccomp=unconfined` exception; UID 1000, cap-drop ALL,
no-new-privileges, read-only rootfs, network none and resource bounds remain.
Synchronous branch probes and strace can perturb scheduling. Neither is a
qualified completion observer; no prefix replay or descriptor pins are used.

Each of 12 cases runs twice under stock/branches/syscalls; nine default-option
cases also run twice under the unchanged native full producer: **90 targets**.
Archive-only compositions and independently precreated-state controls are
separate cases. Input TARs, Python lstat/digests, checkpoints, exact stdout/stderr,
commands, exits and native evidence bundles are retained outside observed trees.
Existing evidence paths cannot be overwritten. On failure, preserve the partial
directory and broker log, inspect any invocation-owned target containers, and
start any subsequent attempt in a new output directory.

## Independent verification

Copy the completed directory to a new ignored host evidence directory. In a
fresh host process and a fresh controller process, run:

```bash
python3 tools/node-tar/diagnostics/investigate.py audit \
  --reference <local-reference-checkout> --output <retained-runs> \
  --audit-output <new-audit-json>
python3 tools/node-tar/diagnostics/analyze.py <retained-runs> <new-summary-json>
```

Audit uses the unchanged independent reader, checks input hashes and compares
each native bundle's BEFORE/AFTER with the separate Python observer. That
observer records root contents; only the canonical snapshot includes `.`.
The analyzer requires all expected runs and equal exit/semantic outcomes across
profiles/repetitions, including file identity equivalence classes. It checks
unchanged sentinels/input and native trace integrity. Exact inode/timestamp
values are preserved in raw files but excluded from cross-sandbox comparisons.
Inspect the retained kernel syscall lines to distinguish same-object truncation,
unlink followed by creation and inode recycling. Checksum and preserve raw files
before deriving a report. A changed reporting script does not rewrite raw runs.

Run `make check` in a new Dev Container and `git diff --check` before handoff.
See [the runtime investigation report](../../../docs/research/diagnostics/node-tar-replacement-report.md).

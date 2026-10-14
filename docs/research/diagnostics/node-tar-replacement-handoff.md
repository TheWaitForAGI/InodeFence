# node-tar replacement investigation — WIP / WSL handoff

Stopped at the user's request on 2026-10-14. **Phase A is partial; Phase B has not
run; Phase C has no final verdict.** This document is a handoff, not an experiment
summary or a qualification decision. No replacement or vulnerability is claimed.

## Preserved state and scope

- Investigation baseline: `0eb527f88aa8a4015544d2f6b0eabfebe079bf18`.
- Historical qualification revision: `36ff7fdb0e31db72b3e581fd1c089b712b4a7b4e`.
- Original checkout was already clean on `diag/node-tar-replacement` at the baseline.
  Its files and branch ref were preserved. A separate worktree was created at
  `/tmp/inodefence-node-tar-replacement-20261014` on
  `diag/node-tar-replacement-20261014` to avoid changing that checkout.
- PR #89 was inspected read-only: OPEN / Draft, head
  `fix/native-effect-qualification-wsl`, base main. It was not edited.
- WSL raw evidence and the WSL controller were unavailable on this Mac. Their
  prior results were read from the existing summary, not independently verified
  again. The Mac's `experiments/raw/` contains only `.gitkeep`.
- No Gate 3/4 rerun, Gate 5, extraction experiment, fixture change, criterion
  change, generic model change or scheduler change was performed.
- This branch inherits the unmerged baseline stack. A future independent Draft
  PR must separate the diagnostic delta from that stack; do not merge it into #89.

Task Contract: the user's Runtime Root-Cause Investigation request. Allowed work
is source investigation, disposable contained minimal experiments and diagnostic
documentation/scripts. Original controller/images/fixtures/raw artifacts, the
qualification runner, acceptance rules and generic engine are outside the edit scope.

## Source facts checked so far

References below are to the installed tar **7.5.22** readable CommonJS source.
Runtime `require('/target/node_modules/tar')` actually resolves to the bundled
`dist/commonjs/index.min.js`; the diagnostic probe guards both file hashes and
locates the matching private symbols in the actual runtime class.

| Code | Checked behavior |
| --- | --- |
| `unpack.js:208–219` | `newer`, `keep`, `unlink` use boolean coercion; omitted values are false. |
| `unpack.js:370–387` | Supported entry types reach `CHECKFS`. |
| `unpack.js:601–607` | `PEND`; reserve entry path and link target; invoke `CHECKFS2`. |
| `unpack.js:640–651` | `lstat`; keep/newer skip first; lstat error or reusable state goes directly to `MAKEFS`. |
| `unpack.js:593–598` | Reusable iff `entry.type === 'File' && !this.unlink && st.isFile() && st.nlink <= 1 && !isWindows`. |
| `unpack.js:653–678` | Directory-to-directory reuses directory; other existing directory uses `rmdir`; other nonreusable object uses `unlinkFile`, then `MAKEFS`. Errors prevent creation. |
| `unpack.js:104–106` | Linux `unlinkFile` calls `fs.unlink`; Windows rename workaround is outside this task. |
| `unpack.js:688–705` | File/OldFile/ContiguousFile use `FILE`; Link/SymbolicLink/Directory select different creation paths. Only exact `File` can pass `ISREUSABLE`. |
| `unpack.js:439–446` | `FILE` constructs fs-minipass WriteStream with `getWriteFlag(entry.size)` and `autoClose:false`. |
| `get-write-flag.js:18–30` | Linux flags include `O_NOFOLLOW | O_TRUNC | O_CREAT | O_WRONLY`. |
| `@isaacs/fs-minipass/dist/commonjs/index.js:273–292` | `fs.open` callback supplies fd, then flushes pending data. |
| `unpack.js:484–506`, `470–479` | Finish schedules metadata actions; after their completion, close callback unpends and releases the reservation via `fullyDone`. |
| `path-reservations.js:91–105`, `107–165` | Only first queued reservation runs; release starts eligible queued work. Independent paths may overlap. |
| `extract.js:59–82` | Full asynchronous extraction Promise rejects on error and resolves on unpack close. |

The unchanged duplicate fixture is two regular entries at `duplicate`, contents
`first` then `second`: [qualification_cases](../../../scripts/qualify_node_causal_effects.py)
lines 67–71. The unchanged producer options are strict=true/preservePaths=false,
with unlink/keep/newer omitted: [_node_effect_producer.cjs](../../../src/inodefence/targets/_node_effect_producer.cjs)
lines 432–461. These source facts predict inode reuse for the normal existing
single-link regular file. A fresh minimal extraction has **not** confirmed that
prediction in this investigation.

An additional source-backed question needs testing: the reader's
`_independent_effect_candidate`, [native_effect_evidence.py](../../../src/inodefence/evaluation/native_effect_evidence.py)
lines 288–353, only derives `namespace_replacement` when one correlated operation
has present before/after objects with changed identity/type. An actual
`unlink → create` sequence can instead yield removal plus creation. LINK and
SYMLINK have earlier dedicated classifications. Thus a candidate's actual path
replacement does not by itself establish Gate 4 replacement-class coverage.
Do not change this meaning or the acceptance criterion in the diagnostic task.

## Read-only target metadata actually executed

A contained metadata-only Node command ran on the Mac's existing immutable image
`sha256:c0dde2b06b3cd079d7922960a05e8a84e26f2d1121ea8cad05691a4f104b8636`:

- Node 22.22.0, tar 7.5.22, Linux arm64.
- unpack SHA-256: `03515ed98f5df6ec0f23177b7016274f8cdc91b038d0dcd036f438a70e614eed`.
- actual bundled entrypoint SHA-256: `b9464172723801f6ad013a1a819b5f31838753559d56c879202d7fb3c1326167`.
- lock SHA-256: `28dc7696eda4a36462e927d5d42c1e764646631aed21d3e004999a7c24db8930`.

All three hashes matched the local pinned files. This was **not extraction** and
does not reproduce the WSL qualification image
`sha256:30620f2d43af5782dd5e61aef06b87b44d1a9350154273f2cd2300cd24318ff3`.
The Mac Docker context is orbstack, Linux kernel
`7.2.9-orbstack-00391-g2b298d05fbd4`, Engine 29.8.2, aarch64. Do not pool its
metadata probe with WSL experiment observations.

## Unfinished diagnostic files

- [Diagnostic Dockerfile](../../../tools/node-tar/diagnostics/Dockerfile): builds a
  sibling image from explicitly supplied immutable target/check images. Does not
  mutate either original image or tag. **Not built or execution-tested.**
- [replacement-probe.cjs](../../../tools/node-tar/diagnostics/replacement-probe.cjs):
  stock complete asynchronous tar.x, or read-only `branches` hooks logging actual
  ISREUSABLE result, stat identity/nlink and checkFs2 start/done object observations.
  Guards Node/tar and source hashes. Does not serialize target work, write evidence
  inside extraction, or pin descriptors. **Not extraction-tested.**

The synchronous diagnostic observations may perturb scheduling; they are not a
qualified producer or an independent ground-truth implementation. Continue with
stock syscall traces plus independent Python lstat/digests and unchanged native
producer traces. Preserve all stdout/stderr/exit codes. No Python runner was added.

`make check` and an experiment suite were **not run** before the requested stop.
Host `node --check tools/node-tar/diagnostics/replacement-probe.cjs` and the staged
`git diff --check` passed. These validate syntax/whitespace only. The push is WIP,
not a tested completed investigation.

## WSL continuation commands

First create a fresh worktree without switching the existing #89 checkout:

```bash
cd /path/to/InodeFence
git status --short --branch
git fetch origin diag/node-tar-replacement-20261014
IF_DIAG_WORKTREE="$HOME/inodefence-node-tar-replacement-wsl"
git worktree add --detach "$IF_DIAG_WORKTREE" origin/diag/node-tar-replacement-20261014
cd "$IF_DIAG_WORKTREE"
git switch -c diag/node-tar-replacement-wsl
git rev-parse HEAD
git status --short --branch
```

Use a new local branch name if that name already exists. Do not force an existing
branch or checkout. Read START_HERE, STATUS, AGENTS and this handoff. Inspect the
original raw bundles read-only if available; record their actual hashes/access.

Resolve the existing WSL pins; these are read-only discovery commands:

```bash
docker context show
docker ps --no-trunc --format '{{.ID}} {{.Image}} {{.Names}}'
IF_DIAG_TARGET_IMAGE=sha256:30620f2d43af5782dd5e61aef06b87b44d1a9350154273f2cd2300cd24318ff3
docker image inspect "$IF_DIAG_TARGET_IMAGE" --format '{{.Id}} {{.Architecture}}'
docker inspect adoring_noyce --format '{{.Id}} {{.Image}} {{json .Mounts}}'
```

If the named image/controller is absent, report it and resolve the actual pinned
target through inspection; do not claim the historical environment was reused.
For a diagnostic sibling build, the check image must provide Python 3.12 and
strace; resolve the existing controller's immutable image ID and verify its tools.
Never modify the controller or install into the original target image.

```bash
IF_DIAG_CHECK_IMAGE=$(docker inspect adoring_noyce --format '{{.Image}}')
docker build -f tools/node-tar/diagnostics/Dockerfile \
  --build-arg TARGET_IMAGE="$IF_DIAG_TARGET_IMAGE" \
  --build-arg CHECK_IMAGE="$IF_DIAG_CHECK_IMAGE" \
  -t inodefence-node-tar:diag-replacement-wsl .
IF_DIAG_IMAGE=$(docker image inspect inodefence-node-tar:diag-replacement-wsl --format '{{.Id}}')
IF_DIAG_VOLUME="inodefence-node-replacement-$(date -u +%Y%m%dT%H%M%SZ)-$$"
docker volume create "$IF_DIAG_VOLUME"
```

Build/run commands are templates, not previously verified execution. Prepare
controlled TARs and fresh sandbox directories only inside that new Linux volume,
then execute the probe with input `/var/lib/inodefence/<new-run>/input.tar`, cwd
`/var/lib/inodefence/<new-run>/extract`, profile `stock` or `branches`, final argument
`'{}'` (baseline) or explicitly documented diagnostic options. The image's entrypoint
already selects the probe. Use UID 1000, read-only rootfs, network none, cap-drop ALL,
no-new-privileges, resource bounds and tmpfs scratch. Keep source mounts out of the
filesystem semantics workspace. Stock strace can use entrypoint `/usr/bin/strace`
with `-f -v -yy -e trace=%file,write,writev,close` and the full Node/probe command.
Record the ptrace/seccomp configuration separately if it needs adjustment.

Minimum candidate plan, not observed results:

1. File(`duplicate`, `first`) → File(`duplicate`, `second`), default options.
2. File at a path → Directory / SymbolicLink / Link at that same path, safe targets.
3. File(`a`, `first`) → Link(`alias` → `a`) → File(`a`, `second`); retained alias
   independently anchors the old inode and should expose nlink=2 at the third entry.
4. Duplicate File sequence with unlink=true as an explicitly altered diagnostic
   condition, never a silent new qualification baseline.
5. Useful negative controls: keep=true; nonempty directory replaced by File.

For every run retain exact entry sequence/TAR hash/options, pre/post lstat identity,
nlink/type/digest, intermediate checkpoints, syscall operation evidence, exit status
and failure details. A new inode number alone is insufficient. Account for inode
recycling, observation races and differences between complete archives and explicitly
precreated-state controls. Do not call prefix replay native full-execution evidence.

Run `make check` in a **new diagnostic Dev Container** using this worktree, and
`git diff --check`. Do not point the original controller at a different checkout or
execute Gate 4/5 commands. Complete H1–H4 adjudication and the requested source/result
tables only after retained experiments support them. If the effect definition needs
changing, report the mismatch/options and stop before implementing a contract change.

## Prompt for the next WSL session

```text
Continue the InodeFence Runtime Root-Cause Investigation from
docs/research/diagnostics/node-tar-replacement-handoff.md on the pushed
diag/node-tar-replacement-20261014 WIP branch. Read START_HERE, STATUS and AGENTS.
The original baseline is 0eb527f; actual old qualification was 36ff7fd; #89 and
original controller/images/fixtures/raw evidence must remain unchanged.
Phase A is partial; no Phase B extraction experiment has run. Metadata-only
verification on Mac is not WSL reproduction. Diagnostic code is unfinished.
Use a separate worktree/branch and a new Linux named volume. Finish source call-path
analysis and bounded minimal experiments on Node 22.22.0/tar 7.5.22. Compare independent
lstat/digest/syscall ground truth with the unchanged native producer/reader. Investigate
both ISREUSABLE and the distinction between unlink+creation and the reader's single-op
namespace_replacement class. Do not assume a replacement candidate passes coverage.
Collect exact TAR entries/options, before/after dev+ino/nlink/type/digest, operation
evidence, exit status/failure reason, source hashes/environment and immutable raw data.
Adjudicate H1–H4 as SUPPORTED/REFUTED/UNRESOLVED within evidence limits.
Do not rerun full Gate 4, run Gate 5, change qualification criteria/fixtures, generic
models or scheduler, modify main/stacked branch refs, or claim PASS/vulnerability.
If a research contract change is needed, explain why and alternatives, then stop.
Run applicable checks in a new Dev Container. Prepare an independent diagnostic Draft
PR with only this task's delta; don't merge into #89. Final report order: root cause,
source evidence, minimal results, verified conditions, unresolved questions, Engine
handoff, changed files/tests/Draft PR status. Handle minor choices autonomously.
```

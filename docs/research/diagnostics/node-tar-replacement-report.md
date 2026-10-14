# InodeFence Runtime Root-Cause Investigation: node-tar replacement

## Root cause and decision

**Observed:** the fixed duplicate-path fixture performs same-object truncation,
not a namespace replacement, on Node **22.22.0 / node-tar 7.5.22 / Linux** with
the existing default options. The second `File` sees a regular object with
`nlink=1`, passes `ISREUSABLE`, and opens it with `O_TRUNC`. The native reader's
`truncation` classification agrees with independently retained syscall evidence.

**A second, separate limitation:** a real path replacement through
`unlink → open/mkdir/link/symlink` is represented by distinct correlated
operations. The unchanged reader emits removal plus creation or a dedicated
link class. It does not aggregate that sequence into the existing single-operation
`namespace_replacement` class. All **18** complete native diagnostic bundles
contained **zero** events of that class, including cases with independently
demonstrated path replacement. This is an effect-vocabulary/fixture feasibility
question; it is not evidence that the reader misclassified its frozen contract.

The historical Gate 4 decision at `36ff7fd` remains
**`V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`**. Gate 5 and native campaigns
remain blocked/NOT_RUN. No qualification criterion, fixture, generic model,
scheduler, C0–C4 contract or native producer/reader was changed. These benign
contained experiments establish reproducible diagnostic behavior; they make no
vulnerability, rediscovery, safety, performance or feedback-effectiveness claim.

## Scope, provenance and source evidence

Task Contract: the user's Runtime Root-Cause Investigation continuation on
2026-10-14. Layer: target-specific runtime diagnosis and evidence validation.
Allowed changes: diagnostic tools/tests/documentation. Inputs: fixed deterministic
complete USTARs plus explicitly identified precreated-state controls. Outputs:
immutable raw process/state/syscall evidence and a bounded diagnosis. Existing
C0/C1/C2 and entry-effect contracts are consulted without changing their meaning.

Investigation baseline: `0eb527f88aa8a4015544d2f6b0eabfebe079bf18`.
Historical qualification revision: `36ff7fdb0e31db72b3e581fd1c089b712b4a7b4e`.
Inherited WIP: `062ee51a3bf9e568756b7e71eac3c5da68a3b24c`.
Clean executed harness revision: `2e31ea9a724186e615d4d1d69a27cb3bdd5b3fc4`.
Reference core/adapter/producer/reader/qualification files match the baseline;
their actual SHA-256 values are retained in `config.json`.

The fresh execution window was **2026-10-14 03:35:26.501376–03:36:39.297923 UTC**.
WSL kernel `6.18.33.2-microsoft-standard-WSL2`, x86_64, Python 3.12.3, Docker Desktop
4.91.0, Engine 29.8.0/API 1.56, context `default`. The original qualification
controller/image/volume and host raw mirror were absent from the active Docker
daemon/checkouts. Earlier Docker discovery observed a different local daemon
inventory (Engine 29.8.1); experiments used the resolved 29.8.0 inventory below.
No old raw bundle was independently reverified in this session. The prior
negative decision is read from its retained historical report, not pooled with
this experiment. The Mac metadata-only handoff is also separate evidence.

| Binding | Exact identity |
| --- | --- |
| New runtime volume | `inodefence-node-replacement-20261014-runtime` |
| New controller | `6c853b5abed2ba3dc9a1557740cb77b6d810df33f36bf3213a058e88bd9dab24` |
| New Dev Container base image | `sha256:baad44b902bc3abc637612c00da14b04447e9fbe6feb8fa916f901dcfd211081` |
| New native image | `sha256:97c0573d7c6c610ccefd6af02c78731faddb54f7dcda3b93443dadde38ff88fb` |
| Executed sibling diagnostic image | `sha256:5e73fc55256572f8ba4cf701f01679406570fa83656b73af97f797c59c141e0c` |
| Unchanged producer SHA-256 | `6c9a05a8420e800281e2e8662c17b176648fef13dc2182332ce063bb117aa5f4` |
| Package lock SHA-256 | `28dc7696eda4a36462e927d5d42c1e764646631aed21d3e004999a7c24db8930` |
| Actual bundled entrypoint SHA-256 | `b9464172723801f6ad013a1a819b5f31838753559d56c879202d7fb3c1326167` |
| Readable unpack source SHA-256 | `03515ed98f5df6ec0f23177b7016274f8cdc91b038d0dcd036f438a70e614eed` |

Installed source is retained in the raw session's `pinned-node_modules`. Runtime
`require('/target/node_modules/tar')` loads `dist/commonjs/index.min.js`; the
readable source and actual bundle are both hashed. Private hooks use unique
symbols found in that runtime class. Source references below are **installed
7.5.22 CommonJS line numbers**, not approximate upstream TypeScript references.

| Source / lines | Verified behavior and consequence |
| --- | --- |
| `extract.js:59–82` | One complete async extraction Promise rejects on error and resolves on unpack close; no member-by-member execution or prefix replay. |
| `unpack.js:208–219` | Omitted keep/newer/unlink coerce to false. `strict:true` raises entry errors; `preservePaths:false` retains path protections. |
| `unpack.js:370–387,601–607` | Supported entries reach CHECKFS; PEND and path/link-target reservations precede CHECKFS2. |
| `path-reservations.js:91–105,107–165` | Work runs only when first in relevant queues. Release starts eligible queued work; independent names may overlap. |
| `unpack.js:640–651` | lstat result is checked for keep/newer **before** reuse. lstat error or successful reuse calls MAKEFS directly. An error does not guarantee later creation succeeds. |
| `unpack.js:593–598` | Reuse iff exact `File`, unlink false, existing regular file, nlink ≤1, and non-Windows. No CVE or fixture condition participates. |
| `unpack.js:653–678;104–106` | Directory→Directory reuses a directory; other existing directories use rmdir. A non-directory/nonreusable destination uses Linux fs.unlink, then MAKEFS. |
| `unpack.js:688–705,395–405` | Removal error blocks creation and enters strict entry-error handling. File/OldFile/ContiguousFile choose FILE; only exact File is reusable. Link/SymbolicLink/Directory choose their own paths. |
| `unpack.js:439–446`; `get-write-flag.js:18–30` | WriteStream uses O_NOFOLLOW/O_TRUNC/O_CREAT/O_WRONLY on Linux, autoClose=false. |
| `@isaacs/fs-minipass/dist/commonjs/index.js:273–292` | Callback-based fs.open supplies fd, then buffered data is flushed. |
| `unpack.js:470–506` | File finish schedules timestamp/ownership operations; after completion, fs.close callback unpends and releases reservation. |
| `unpack.js:550–562,708–717` | Link target validation precedes fs.link/fs.symlink. Link success unpends/resumes before done. |
| Baseline `_node_effect_producer.cjs:280–379,432–461` | One operation start/completion pair retains before/after object evidence; native extraction options are unchanged. |
| Baseline `native_effect_evidence.py:288–353,448–475` | LINK/SYMLINK get dedicated candidates first; replacement needs present-before/present-after with changed identity/type **in one correlated operation**. Insufficient evidence falls back to operation_observed. |

The baseline source references are available at
[the frozen repository revision](https://github.com/TheWaitForAGI/InodeFence/tree/0eb527f88aa8a4015544d2f6b0eabfebe079bf18).

## Minimal experiment results

Each of **12** cases ran twice under stock, branches and stock+strace. Nine
default-option cases also ran twice under the unchanged native full producer:
**90** fresh target processes, **82 exit 0**, **8 exit 2** (all nonempty-directory).
All expected runs are retained. There were no experiment retries, timeouts or
discarded target runs. Every case had identical exit and final semantic state
across its profiles/repetitions. Each process has timeout 10 seconds, memory
512 MiB, PID limit 64, nofile 1024, file size 64 MiB, tmpfs 32 MiB and native
event bound 256. RNG/mutation/campaign: none.

All target containers use UID/GID 1000, network none, read-only rootfs,
cap-drop ALL, no-new-privileges and only their fresh run's volume subpath.
Syscall runs additionally use `seccomp=unconfined`, without CAP_SYS_PTRACE.
Native runs use the rebuilt distroless target; stock/branch/syscall runs use the
Ubuntu diagnostic sibling with identical Node/package bytes. That difference,
synchronous hook observations and strace overhead mean these are not scheduling
neutrality or performance comparisons.

Notation: F(path,content)=File, D=Directory, L=hardlink, S=symlink. Entries occur
in the exact written order, all modes default 0644 and deterministic builder
mtime=0. Baseline options: strict=true/preservePaths=false, unlink/keep/newer
omitted. Every change to these options is explicit below. Precreated controls
are distinct whole-archive runs, never archive-prefix evidence.

| Case / exact entries and setup | Branch / syscall evidence (2/2) | Unchanged native full reader (2/2 unless N/A) |
| --- | --- | --- |
| duplicate-default: F(duplicate,first), F(duplicate,second) | Reusable=true; nlink=1; second O_TRUNC open, no unlink; first→second digest | ordinal 1 open=truncation, write=content modification |
| file-directory: F(p,first), D(p) | Reusable=false; unlink(p)→mkdir(p); regular→directory | removal→creation |
| file-symlink: F(safe,safe), F(p,first), S(p,safe) | Reusable=false; unlink(p)→symlink(safe,p) | removal→symlink_creation |
| file-hardlink: F(source,source), F(p,first), L(p,source) | Reusable=false; unlink(p)→link(source,p); final p/source share identity, nlink=2 | removal→hardlink_identity_relation_creation |
| hardlink-anchor: F(a,first), L(alias,a), F(a,second) | Third entry sees nlink=2, reusable=false; link→unlink(a)→create(a); alias retains old object/content | hardlink identity creation, removal→creation |
| duplicate-unlink: same duplicate TAR, unlink=true | Reusable=false despite regular/nlink=1; unlink→create; **same inode number recycled at branch checkpoints** | N/A: native producer options remain unchanged |
| duplicate-keep: same duplicate TAR, keep=true | Second entry skipped before ISREUSABLE; no second writable open/unlink; final first | N/A |
| nonempty-directory: D(p), F(p/child,child), F(p,second) | Reusable=false; rmdir(p) fails ENOTEMPTY; no replacement file creation; exit 2 | failed rmdir=operation_observed; complete rejected trace, zero feedback keys |
| precreated-single: existing F(p,first); TAR F(p,second) | Reusable=true/nlink=1; Python before/after same identity; O_TRUNC, first→second | truncation→content modification |
| precreated-hardlink: existing F(p,first), alias→p; TAR F(p,second) | Reusable=false/nlink=2; Python alias pins old object; unlink→create p; alias retains first | removal→creation |
| precreated-symlink: existing F(safe,first), p→safe; TAR F(p,second) | Reusable=false/isFile=false; unlink symlink→create regular; safe content unchanged | removal→creation |
| precreated-newer: existing F(p,first), mtime=1800000000; TAR F(p,second), newer=true | Skipped before ISREUSABLE; first content/identity retained, no writable open | N/A |

The independent Python observer records every sandbox object's lstat identity,
nlink/type/mode/size/timestamps and regular-file SHA-256 without following symlinks.
Transient branch observations include exact entry identity and aliases. Stock
strace retains `statx(...AT_SYMLINK_NOFOLLOW...)`, unlink/link/open/write/close
operations and successful/error return values. Native raw records retain the
absence between removal and creation. No observer holds an old object descriptor
across extraction; the hardlink is an explicit fixture entry/setup.

Representative **stock repetition 0 Python evidence** (dev=2112 throughout):

| Control | Before `(ino,nlink,type,content)` | After |
| --- | --- | --- |
| precreated-single p | `(273642,1,regular,first)` | `(273642,1,regular,second)` |
| precreated-hardlink p and alias | both `(274013,2,regular,first)` | p `(274073,1,regular,second)`; alias `(274013,1,regular,first)` |
| precreated-symlink p | `(274194,1,symlink,target=safe)` | `(274194,1,regular,second)`; safe retains `(274157,1,regular,first)` |
| archive-only hardlink-anchor | both paths absent | a `(273009,1,regular,second)`; alias `(272990,1,regular,first)` |

`first` SHA-256 is `a7937b64b8caa58f03721bb6bacf5c78cb235febe0e70b1b84cd99541461a08e`;
`second` is `16367aacb67a4a017c8da8ab95682ccb390863780f7114dda0a0e0c55644c7c4`.
Every raw file retains full digests. In the archive-only branch run, a/alias share
`(2112,273008)` with nlink=2 after link, then a becomes `(2112,273019)` while alias
stays `(2112,273008)` with first. Stock strace independently sees nlink=2 followed
by successful unlink(a), writable create(a), and write(second).

Recycling is directly observed, not merely hypothetical: duplicate-unlink branch
repetitions retain inode 273151 and 273200 respectively across first/second
checkpoints despite unlink→create. The precreated symlink→regular control also
recycles inode 274194. Equal dev/ino across time therefore cannot establish
continuous identity. A retained alias plus successful syscall sequence avoids
this ambiguity for the hardlink controls.

TAR SHA-256 (all profiles/repetitions within each group match):

| Input group | SHA-256 |
| --- | --- |
| duplicate default/unlink/keep | `a0fe138b9c322dc9d28081edd839e10c3522547a7e716a7256aab814452f2f3d` |
| file-directory | `91035a7b31441e97bdb8d8ef77b3236129d7c932fddf35e31aabe5feaf222877` |
| file-symlink | `b35122e4a3116bfbe9abea8b869516c5db8ffb8b817aed880c00f3c24521eac8` |
| file-hardlink | `bcfc7273ff56b98e36ae695c5e9974bacea9c84b8960443324a418fe8ee5b094` |
| hardlink-anchor | `626c9d06b67943673144b30fc98023a9509f73abb401585829a58cdddfd43755` |
| nonempty-directory | `6acdebc31397ed99162a1fecff5851276969a5a46a3741d634044cfab2f7b463` |
| all precreated controls | `9dcc3cb22e82a58f343d40f4deb5147d67b20ea1cf2422a15d3bd71c386f82b6` |

The duplicate default bytes match the unchanged qualification fixture's builder
output. New cases reside only in the diagnostic runner, not the qualification suite.

## Verified conditions and H1–H4

The handoff names H1–H4 but does **not** retain their original definitions. The
following are explicit operational labels for this report, not an attribution of
unavailable earlier wording. Exact original-label correspondence is UNRESOLVED.

| Hypothesis | Verdict | Evidence boundary |
| --- | --- | --- |
| H1: default duplicate regular File reuses a single-link regular inode and truncates it | **SUPPORTED** | source conjunction, 2/2 branch results, stock syscall opens/writes, native truncation; precreated-single Python confirms same identity |
| H2: a later entry at an existing path necessarily replaces its namespace object | **REFUTED** | default duplicate reuses; keep/newer skip; nonempty directory removal fails |
| H3: retaining an alias raises nlink and causes regular-file unlink→create while preserving the old object at the alias | **SUPPORTED** | full archive composition and separate precreated control, each 2/2; syscall nlink=2/link/unlink/create and independent alias digest/identity |
| H4: real unlink→create replacement automatically satisfies the existing single-operation namespace_replacement coverage | **REFUTED** | every applicable native replacement sequence is removal+creation/link class; 0 namespace_replacement among 18 independently verified complete bundles |

Dynamic evidence exercises exact File versus Directory/Link/SymbolicLink,
regular versus symlink destination, nlink=1 versus 2, unlink=false versus true,
and earlier keep/newer skipping. OldFile/ContiguousFile and the Windows branch
are source-only observations, not executed conditions. No nlink=0 case was run.
Successful unlink is necessary in tested nonreusable non-directory cases but
does not prove that subsequent creation/validation will succeed in all layouts.

## Remaining questions and Engine handoff

1. Is a true single-operation replacement reachable in this pinned async TAR
   extractor under the fixed options? Source paths studied use unlink then
   creation; no overwrite-rename was observed. These finite cases are not an
   exhaustive unreachability proof.
2. Does the intended research vocabulary require a multi-operation replacement
   motif in addition to the existing atomic operation class? A new fixture alone
   cannot make the observed removal+creation qualify under current semantics.
3. Original H1–H4 wording and access to old qualification raw evidence remain
   unavailable. Their provenance cannot be reconstructed from this session.
4. Two repetitions establish limited reproducibility of these controlled cases;
   they do not qualify instrumentation, scheduling neutrality or effectiveness.

Engine should retain the existing negative token and keep campaign admission
blocked. It can inspect the retained event pairs and independently anchored old
identity without changing the core. No patch to producer/reader/model/scheduler
is proposed by this diagnostic PR.

If replacement semantics must change, that requires a **separate research Task
Contract before implementation**. Alternatives are: retain the single-operation
definition and investigate a reachable target/operation; define an additional
evidence-supported unlink→creation motif with explicit absent intermediate state,
entry/path correlation and inode-recycling rules; or separately justify revising
the fixed qualification coverage objective. The latter two change methodology
and require frozen definitions, reader/normalization tests and later independent
qualification. This task stops at that implementation boundary. It does not
silently loosen the criterion or launch another matrix.

## Evidence, verification and PR isolation

Primary fresh-volume evidence:
`/var/lib/inodefence/node-replacement-20261014-attempt1`.
Host mirror/session:
`/home/linux/Projects/InodeFence-node-replacement-runtime/experiments/raw/node-replacement-20261014-session`.
It includes all 90 run directories, input TARs, exact stdout/stderr/syscalls,
independent before/after/checkpoints, 18 native manifests/results/raw streams,
the complete broker log, installed source, mechanical summary and fresh audits.
Raw files are ignored by Git. Checksum identities and validation results are
listed in the final evidence closeout below.

Fresh host and controller processes each verified all 18 native bundles with the
**unchanged** independent reader, plus input hashes and every independently
observed object field (root contents; canonical `.` is excluded only from this
cross-observer equality check). All 18 traces are complete/integrity-valid;
rejected traces retain failure evidence and emit zero feedback keys. The
mechanical analyzer verifies all 90 expected runs, exact TAR consistency,
unchanged protected sentinel/input, and final exit/semantic equality.

Experiment validation level: **REPRODUCIBLE**, bounded diagnostic evidence.
Not a validated vulnerability finding or paper-ready effectiveness comparison.
The experiment-validation skill kept raw observations, reader derivations and
interpretation separate; the implementation skill confined changes to diagnosis.

The independent Draft PR is based on remote main `931899209bc1de29f249d9e2f3d451438ddf1d22`
and contains only diagnostic tools, tests and this report. It does not inherit
the unmerged v2 stack or update PR #89, original main or stacked branch refs.
The reference checkout is an explicit runtime dependency, not a hidden change
to this PR's generic source. The inherited WIP handoff is preserved on its
existing branch; this report supersedes its incomplete experimental status.


### Evidence closeout and validation

| Artifact (host session unless noted) | SHA-256 |
| --- | --- |
| Primary `runs/config.json` | `d3ed0ad5e8aefe5b24e6144d665fc39ff7f6c4e989df0727058e099721ca206f` |
| Mechanical `summary.json` (regenerated byte-identically) | `7a7fbdff850a70bac8b032b4b6f3f17cc6da27d5b093ecfc7537d07f116f1d21` |
| Fresh host/controller audit reports (identical bytes) | `82a2cfb0e82532a70f44d9da4e77f2fb0b0ba866eb3938c40c3bf0635abb7e7d` |
| Exact broker JSONL | `1cb0e416ddc643fe393e1cd3227093c74289dc3ee118bc62868a9efc03acc76c` |
| Preserved executed harness source (matches run config) | `eb0e2844bce7b87408cb9708027de54de7d653a421166b8782b29c982973ddfb` |
| Sibling `node-replacement-20261014-session.sha256` (952 files) | `0b9d99c8c15822be1e1ddd43663f39aa2e7b82e5f841b6fd62c3cff3b856f5fa` |
| Sibling `node-replacement-20261014-session.tar.gz` | `eae2eb45925c560c7821997ff8b42a6ccae9634c26ea7462d34685f4b6679355` |

The checksum inventory verifies every listed file. The completed primary
directory, host session, inventory and archive are preserved read-only.
The exact executed harness/probe/Dockerfile are also retained in the session;
later audit/reporting changes do not alter their run provenance. The final
Dockerfile copies the producer from the pinned image rather than unmerged
source. Its sibling image
`sha256:adfdb363c0208168feb593a5109bc0988f005cb700f01e73b875598ce351e773`
built successfully and passed source/version identification and Node syntax
checks; it was not used for additional extraction or substituted for the
recorded executed image.

Actual validation:

- New reference Dev Container: complete `make check` **PASS**, **1,390 tests**,
  Ruff/format/Pyright/environment/docs passed.
- Separate main-based PR Dev Container: complete `make check` **PASS**,
  **1,343 tests**, including three new diagnostic tests; all canonical checks
  passed. Full log is `make-check-independent-pr.log`.
- Explicit Pyright for diagnostic tools: zero errors/warnings; Node probe syntax
  and final sibling build/identity checks passed.
- Host/controller independent readers: **18/18 each**; cross-observer lstat,
  identity, nlink, type, mode, size, digest, timestamps and symlink text matched.
  Mechanical summary regeneration was byte-identical; duplicate fixture bytes
  match the original builder output.
- `git diff --check` and final local Markdown links passed. The PR diff contains
  seven diagnostic/report/test files and no generic or native-source changes.

Preflight corrections are recorded in `validation-notes.json`: an unavailable
Docker inventory, a BuildKit bare-ID resolution failure, an initial Dev
Container docs-check failure due to missing worktree Git metadata, and the
explicit root-object difference in the separate observer's audit. They caused
no discarded/retried extraction, raw edits or change to the native reader.

Changed files: this report; diagnostic
[instructions](../../../tools/node-tar/diagnostics/README.md),
[Dockerfile](../../../tools/node-tar/diagnostics/Dockerfile),
[branch probe](../../../tools/node-tar/diagnostics/replacement-probe.cjs),
[runner/auditor](../../../tools/node-tar/diagnostics/investigate.py),
[mechanical analyzer](../../../tools/node-tar/diagnostics/analyze.py), and
[portable diagnostic tests](../../../tests/test_node_replacement_diagnostics.py).
The tests check independently retained hardlink identity/content, symlink
non-following, semantic comparison of identity relations and no-overwrite
evidence publication.

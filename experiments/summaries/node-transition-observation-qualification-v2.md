# Native entry-transition observation qualification v2

Classification: **BENIGN VALIDATED qualification evidence**. The decision for the
pinned node-tar target and the candidate set below is **QUALIFIED FAIL**. This is
not a security finding, a vulnerability-discovery result or an evaluation of
transition feedback.

## Research question and decision rule

Can a filesystem checkpoint be associated with every logical TAR entry after that
entry's filesystem effects are complete, without changing the pinned target's
behavior?

The working hypothesis was that one of a public node-tar lifecycle event, a passive
Linux filesystem event, syscall-return evidence or fresh-process prefix replay would
provide that boundary. Qualification required all of the following:

1. exact archive ordinal/path/type/link-target association, including duplicate paths;
2. completion of write, close and entry metadata work before the snapshot;
3. a coherent snapshot that does not silently include unlabelled later-entry effects;
4. preservation of the pinned target invocation and scheduling behavior; and
5. repeatable evidence with explicit observation failures.

None of the executed candidates met all five conditions. The decision is scoped to
the tested target and methods; it is not a proof that every possible extractor or
future upstream API lacks a usable boundary.

## Starting state

| Item at source revision | Classification |
| --- | --- |
| Generic `EntryCheckpoint` / `TransitionTrace` / `TransitionSignature` | IMPLEMENTED, TESTED |
| P0 final-state retention / P1 transition retention | IMPLEMENTED, TESTED |
| P2 bounded adaptive scheduler | IMPLEMENTED, TESTED |
| Checksummed transition evaluation export/reader/replay verifier | IMPLEMENTED, TESTED |
| Native node-tar entry-completion producer | NOT_IMPLEMENTED |
| Native P0/P1/P2 comparison | NOT_RUN |
| Transition feedback improves security-boundary discovery | HYPOTHESIS |

The checkout started at PR #83 HEAD `98e257aa0b83018b0b660bc38d78dab5375dc4e6`.
The qualification harness was committed as
`06ace942f6abbd06b027f691a418698fa3c0539b` before the formal run.

## Controlled method

The fixture contains five ordered entries: regular `regular` with content `first`,
directory `dir`, hardlink `hard` to `regular`, symlink `sym` to `regular`, and a
duplicate regular `regular` with replacement content `second`. It exercises file
write/close, directory metadata, link identity, symlink creation and replacement.
No CVE, exploit recipe or external protected object is involved.

The formal run used 20 repetitions, a 10-second per-process timeout and 201 node-tar
extractions: 20 each for public async, public sync, baseline, inotify and strace;
one straced sync probe; and 100 fresh-process prefix extractions. Four Python
`tarfile` reference extractions exercised per-member and whole-archive behavior.
Every target process completed. Seven inotify receipt-time snapshots explicitly
failed consistency capture and remain in the evidence.

| Control | Exact value |
| --- | --- |
| InodeFence source | `06ace942f6abbd06b027f691a418698fa3c0539b`, clean |
| Node / node-tar | `22.22.0` / `7.5.22` |
| Target mode | `strict=true`, `preservePaths=false`; existing worker defaults |
| OS / architecture | Linux `7.0.14-orbstack-00380-ga7e0a2dc9535` / aarch64 |
| Python / strace | `3.12.3` / `6.8` |
| Runtime filesystem | named-volume btrfs at `/var/lib/inodefence` |
| Process boundary | uid/gid 1000, capabilities 0, NNP 1, seccomp 2 |
| Fixture case ID | `afed1f31830c860e9c1354c3afc5e1549a5faf818ccf371ea660135213e14c1b` |
| Fixture TAR SHA-256 | `653a9584135b973ad2f20159635c717b92e55375b21672a5bfd2fef33df3688d` |
| Random seed | N/A; fixed deterministic fixture, no mutation |

Target source and invocation identities are embedded in the raw record. In
particular, the package lock, existing worker, node-tar `unpack.js` and `parse.js`,
and the public probe each have a recorded SHA-256.

## Executed candidate results

### Public node-tar events

The async public probe reproduced the earlier failure across 20 runs:

| Observation | Result |
| --- | --- |
| first regular at `onReadEntry` | absent 20/20 |
| first regular at entry stream `end` | absent 1/20; empty file 19/20 |
| duplicate path at `onReadEntry` | prior `first` object 20/20 |
| duplicate path at entry stream `end` | empty replacement file 20/20 |
| directory/hardlink/symlink at entry stream `end` | materialized 20/20 |

The entry stream event is therefore type-dependent and precedes regular-file write
completion. It cannot be the common completion boundary.

With upstream `sync=true`, all five entry `end` observations looked materialized in
20/20 runs. The straced sync run showed the observer opening, reading and closing
the first regular file after target `write`, but before target `utimensat` and before
the target write descriptor `close`. The observation still preceded completion.
It also changes the existing target from asynchronous to synchronous execution.
Both public-event variants are **QUALIFIED FAIL**.

The whole `tar.x()` return/promise resolution remains a valid final-state boundary.
It supplies no per-entry boundary.

### Linux inotify

Each run produced eleven root-child events and no queue overflow. Event sequence was
not deterministic: three orderings occurred with frequencies 14, 5 and 1. In
particular, the relative order of the directory attribute event and first regular
`close_write` varied.

Receipt-time tree snapshots failed 7/220 times: four detected a changing regular
object and three raced with replacement so the symlink target disappeared during
capture. At the first regular `close_write`, every successfully captured snapshot
already contained the later archive entry `dir`; in 2/20 runs the regular file also
had link count 2, meaning the still later hardlink effect was already visible when
the event was consumed.

`close_write` is useful evidence for a particular writable descriptor. It does not
provide a common directory/hardlink/symlink completion point, an archive ordinal, or
an atomic state snapshot. Queue coalescing and overflow also prevent a general
one-event-per-effect assumption. The inotify candidate is **QUALIFIED FAIL**.

The descriptive mean target duration was 18.721 ms with inotify versus 17.128 ms for
the separate baseline runs, a 1.093 ratio. This small benign timing sample is only an
observer-cost signal, not a benchmark or proof of behavior preservation.

### strace syscall evidence

The traces identify successful filesystem syscall returns and target descriptors.
Using the first regular target descriptor close after its metadata call and the
directory `utimensat` return as effect-completion proxies, directory completion came
first in 19/20 runs and regular completion came first in 1/20. Archive order was
regular then directory, so archive order does not define a stable effect-completion
order for this target.

strace provides no logical TAR ordinal by itself and no atomic filesystem snapshot.
It uses ptrace stops to control the tracee, so it is not behavior-neutral. Mean
duration was 22.452 ms versus the same 17.128 ms baseline, a 1.311 ratio. It remains
valuable offline qualification evidence and is **QUALIFIED FAIL** as a native
checkpoint producer.

### Fresh-process prefix replay

All five archive prefixes produced one stable semantic final state across 20 runs.
The first prefix contained only `regular`. In the actual full extraction, every
receipt-time snapshot at the first regular `close_write` already contained `dir`,
and 2/20 also contained the later hardlink identity effect. Prefix replay therefore
answers a counterfactual question: the final state of an independently extracted
archive prefix. It does not reproduce checkpoints from one asynchronous full run.

Prefix replay is **QUALIFIED FAIL** as native transition evidence. It remains usable
only as an explicitly labelled, separate counterfactual/reference experiment.

### Python reference and other extractor candidates

Calling public `TarFile.extract()` once per member provides a synchronous boundary
for that distinct invocation. It is not equivalent to `extractall()` or node-tar.
The main five-entry fixture happened to end in equal selected semantics. A controlled
directory-plus-child counterexample did not: `extractall()` restored the directory
mtime after all members, while the per-member loop left the child's creation-time
effect. Python documents this deferred directory handling. The per-member loop is
**QUALIFIED FAIL** as a behavior-preserving substitute, though it can be declared as
a separate reference target.

GNU tar checkpoints are archive-record checkpoints rather than entry-effect
completion boundaries, so they do not meet the association requirement. libarchive's
public read/write-disk loop includes `archive_write_finish_entry()` and is the most
concrete separate-target candidate. Neither extractor was executed in this run;
their native entry-boundary qualification remains **NOT_RUN**.

fanotify can report close-write events and process/thread identity under supported
configurations. It still needs an archive-entry association strategy and coverage
for non-write effects. The approved target sandbox had no capabilities and this
candidate was not enabled; fanotify qualification is **NOT_RUN**. Raising target
privilege solely to obtain observation would require a separate isolation review.

## Order definitions

- **Archive order** is the ordinal sequence of TAR headers.
- **Effect-completion order** is the order in which the target's filesystem work for
  entries reaches a stated completion criterion, such as metadata application plus
  write-descriptor close.
- **Observation order** is callback delivery or monitor queue consumption order.

Observation may lag an effect and a receipt-time snapshot may include later effects.
The experiment therefore does not convert event timestamps into security verdicts
or incomplete snapshots into transitions.

## Evidence and reproducibility

The local raw copy is
`experiments/raw/node-transition-observation-qualification-v2-06ace94.json`; repository
rules intentionally ignore it. An additional copy remains in the disposable Docker
volume at
`/var/lib/inodefence/node-transition-observation-qualification-v2-06ace94.json`.

| Raw property | Value |
| --- | --- |
| Size | 1,273,450 bytes |
| SHA-256 | `7bd32802ab670c27b62248332d3d5f9698a685078991b28ae59bb8b94688a2a9` |
| UTC interval | 2026-10-09 15:09:33.473764–15:09:37.439470 |
| Raw tier | `RAW_ONLY` |

Re-run from a clean checkout of the recorded source revision, after installing the
pinned node-tar tools, with a fresh output name:

```bash
docker run --rm --user vscode --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 256 --memory 1g --cpus 2 \
  --tmpfs /tmp:rw,exec,nosuid,nodev,mode=1777,size=256m \
  --mount type=bind,src="$PWD",dst=/workspaces/InodeFence,readonly \
  --mount type=volume,src=inodefence-transition-qual-v2,dst=/var/lib/inodefence \
  --workdir /workspaces/InodeFence \
  --env INODEFENCE_RUNTIME_ROOT=/var/lib/inodefence \
  vsc-inodefence-bc8d8c5f18eb139d6df3f1ebeba88e54793a9303c2661cec498ecaf6bad52f52:latest \
  sh -lc 'PYTHONPATH=src /usr/bin/python3.12 scripts/qualify_node_transition_observation.py \
    --repetitions 20 --timeout-seconds 10 \
    --output /var/lib/inodefence/<new-output>.json'
```

The locally resolved image ID was
`sha256:59464488f5ee95e8fc3ecd81812c10a5a0d4ba9b5d917cd532ce8311957c10c1`.
The raw record's target source hashes are the stronger target-content anchors.

The callback counts are stored under each `mechanical_summary`. Other summary
values were derived without modifying the raw file using these rules:

- event sequences: group each run by ordered `(name, mask_names)` pairs;
- failed snapshots: count events where `snapshot_complete` is false;
- first-close state: select the first `regular` event containing `close_write`, then
  count path sets and the observed regular-file link count;
- duration: arithmetic mean of `duration_ns`; ratios use the separate baseline mean;
- syscall ordering: compare trace timestamps for the first target regular-file close
  and directory `utimensat` return;
- prefix stability: group selected semantic fields (`path`, kind, content, link count,
  and hardlink identity equality) by prefix length.

## Consequence

No native `TransitionRunResult` producer was added. Existing C0/C1/C2 final-state
semantics and serialization remain unchanged. Because the native observation gate
failed, the P0/P1/P2 target comparison is **NOT_RUN** and the effectiveness claim
remains **HYPOTHESIS**.

The current blocker is the absence of a behavior-preserving producer for complete,
entry-associated checkpoints. Repeating the rejected node-tar callbacks cannot clear
it. To resume, first qualify a separately versioned target with a public post-entry
boundary, then add the smallest target-specific producer and re-run the existing
evaluation verifier before any P0/P1/P2 comparison. Observation completeness must be
an explicit controlled factor in that comparison.

The next independent technical task is a separate-target qualification of a public
post-entry API, starting with libarchive `archive_write_finish_entry()`. A future
node-tar release may be re-evaluated if it exposes a documented post-filesystem entry
hook carrying logical entry identity. Either task must repeat the behavior-preservation
and snapshot-consistency checks before integration.

## Primary references

- [node-tar public API](https://github.com/isaacs/node-tar/blob/main/README.md)
- [Linux inotify semantics](https://man7.org/linux/man-pages/man7/inotify.7.html)
- [Linux fanotify semantics](https://man7.org/linux/man-pages/man7/fanotify.7.html)
- [strace ptrace architecture](https://github.com/strace/strace/blob/master/doc/INTERNALS.md)
- [Python 3.12 tarfile extraction semantics](https://docs.python.org/3.12/library/tarfile.html)
- [GNU tar checkpoints](https://www.gnu.org/software/tar/manual/tar.html#Checkpoints)
- [libarchive extraction example](https://github.com/libarchive/libarchive/blob/master/examples/untar.c)

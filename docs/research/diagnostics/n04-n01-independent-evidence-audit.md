# N04 independent N01 retained-evidence audit

Audit date: **2026-10-16**. Source revision:
`21e317281a2d2a7faf6198f66302f3912b429011` (`origin/main`).

```text
RETAINED RAW EVIDENCE ACCESS: PASS
CHECKSUM / INTEGRITY RECONSTRUCTION: PASS
EXACT-INPUT AFFECTED/FIXED CORRESPONDENCE: PASS (MACHINE)
TARGET PACKAGE TARBALL BYTE REHASH: NOT_VERIFIABLE (BYTES NOT RETAINED)
FROZEN HUMAN QUALIFICATION: PENDING / NOT ISSUED
B0/B1/B3 REDISCOVERY OR EFFECTIVENESS: NOT_RUN / NOT_EVALUATED
```

This is an AI-assisted, read-only technical audit of the retained N02 evidence. It is not a
new historical-target execution, a human correspondence review or permission to issue
`N01_RELATIVE_HARDLINK_PAIR_QUALIFIED`.

## Evidence and source boundary

The original host evidence was accessible at
`/Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z`. The directory was a
nonsymlink, read-only directory containing 43 files (452 KiB). No symlinks were found.

| Artifact | Recomputed SHA-256 | Result |
| --- | --- | --- |
| `raw-manifest.json` | `2a05b5c92cdc679b73b79630102f2cedc238369c1f8167d8eeee6448e0a3cfac` | PASS |
| retained `independent-verification.json` | `5c8c5a1841d9b55e3b1470d07e850ec7edafcaa6c826ab1136cec41317cf72ae` | PASS |
| retained final `manifest.json` | `0665f739f5aa37ab13953c043f321edb409e821ecb65c303d40db93f6c58bf59` | PASS |

The raw manifest binds clean source `e987c855eee522008443002ee7da5bb6919d64f9`, Linux
aarch64, Python 3.12.3, kernel `7.2.9-orbstack-00391-g2b298d05fbd4`, retained lock, worker,
build and image identities, declared target package-tarball digests, and a 10-second target
timeout. This audit used the current main reader without changing the frozen evidence or its
declared configuration.

### Retained package-byte limitation

The 43-file N02 evidence root contains the build contexts and records listed above but no npm
`.tgz` artifact. The manifest declares SHA-256
`22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` for 7.5.2 and
`9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` for 7.5.3, but the
original tarball byte streams cannot be rehashed from this retained root. Direct correspondence
between those declared digests and the package bytes used during the historical Docker builds is
therefore **NOT_VERIFIABLE** in this audit.

This limitation does not change the retained image IDs, the lock/worker/build record checks, the
runtime target-version metadata or the exact generated archive correspondence reconstructed below.
It does narrow “checksum / integrity reconstruction” to files actually retained in the evidence
root and prevents treating the declared package-tarball digest as independently rehashed evidence.

## Independent reader execution

The reader writes a new verification and final manifest, so it was not pointed at a writable
original. A byte-preserving copy excluding only those two derived output files was created at
`/Users/choijiwng/Projects/InodeFence-n04-n01-reader-20261016.EVle7X`. Its
`raw-manifest.json` retained the exact expected digest. The copy is an audit workspace, not a
replacement evidence root.

The successful read ran in a fresh, removed-after-return Linux container using immutable
controller image
`sha256:470e82d0541507e58ad8daf4f4371a44a99f7e8cafa2001138cbb41c00b44a1a`, with network
disabled, read-only rootfs, all capabilities dropped, `no-new-privileges`, 512 MiB memory,
64 PIDs and a 32 MiB `/tmp`. The source worktree was mounted read-only. The original evidence
digests were recomputed afterward and remained unchanged.

Reader result:

```json
{"final_manifest_sha256":"ba871ac7bce59b5bba849c32c2032987e0ef1e933f32363f24fe6a80a8b1f70a","final_status":"AWAITING_HUMAN_CORRESPONDENCE_REVIEW","independent_status":"PASS","qualification_verdict":"N01_PAIR_AUTOMATED_REPLAY_COMPLETE"}
```

The new verification digest is
`6aaa74b3b3d6d98854cb6e72514227fca84d424d3ab2cb56a10123987bf7526c`.
The reader independently reconstructed 2 admissions, 2 oracle controls, 8 readiness runs,
10 pair runs and 5 comparisons.

Two failed invocations are retained as audit facts:

- Direct macOS invocation failed closed before publication with
  `NotImplementedError: evidence publication requires Linux`.
- The first Linux-copy invocation failed before publication because the copied directory
  inherited the original read-only mode. Making only the copy's root writable resolved the
  publication precondition; no evidence predicate or source code changed.

Neither failure executed a target or modified the original evidence.

## Exact-input and affected/fixed result

All ten pair records use child case
`55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87` and TAR SHA-256
`2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6`. The archive digest
was identical before and after every run. Pair order was counterbalanced and no retry is
recorded.

| Arm | Complete outcomes | C0 | C1 | C2 | Persistent result |
| --- | ---: | ---: | ---: | ---: | --- |
| node-tar 7.5.2 | 5/5 success | 0/5 | 5/5 | 5/5 | `extract/b.txt` and sentinel shared the same after-state `(st_dev, st_ino)` |
| node-tar 7.5.3 | 5/5 rejected, exit 2 | 0/5 | 0/5 | 0/5 | alias absent; sentinel unchanged |

Every fixed-arm stderr was exactly the retained JSON diagnostic whose message is
`TAR_ENTRY_ERROR: linkpath contains '..'`. Process status alone was not used to establish the
contrast.

For each affected run, the sentinel and `extract/b.txt` had equal after-state device/inode
identity and link count 2. The sentinel changed from link count 1 to 2 and its ctime changed.
Its content digest remained
`caed2ac112733b3f5e3f56d9372f7ce6ba88dfafd57eb58807bb29f16548e36b`, and size remained
30 bytes. Therefore C2 is **metadata-only corroboration** of hardlink creation, not evidence
of content modification. For each fixed run the sentinel identity, link count, ctime, size and
content digest were unchanged.

## Controls, readiness, failure and cleanup accounting

- The unchanged oracle control produced C0/C1/C2 false.
- The harness hardlink control produced C0 false and C1/C2 true; it is not target behavior.
- Both targets completed all four original benign seeds: 8/8 success, no timeout, no C0/C1/C2,
  byte-identical per-seed TARs across targets and cleanup true.
- The raw manifest records 18 started and 18 completed extractions, no infrastructure failure,
  and cleanup true for all readiness and pair runs.
- Each run used a fresh runtime root; the retained records mark the root absent after return.
  The source mount and runtime volume were distinct in the admitted isolation provenance.

The reader's missing/tampered fail-closed behavior is established by the retained N02 test
evidence, but this audit did not mutate the retained root to repeat those destructive controls.

## Technical disposition and claim boundary

Observed facts and the independent reader support **PASS (machine evidence correspondence)**
for the exact generated TAR input, retained target image pair, 10-second configuration and retained
run set. The package-tarball byte correspondence limitation above remains **NOT_VERIFIABLE**. The
evidence stage is **REPRODUCIBLE retained machine evidence** for the retained artifacts, not
paper-ready feedback-effectiveness evidence.

The source/input/runtime explanation is technically consistent with persistent hardlink
identity on 7.5.2 and linkpath rejection on 7.5.3. This is an AI-assisted interpretation.
The final frozen contract state remains
`AWAITING_HUMAN_CORRESPONDENCE_REVIEW`; this audit does not issue or impersonate the required
human disposition. It does not establish fuzzing rediscovery, B0/B1/B3 performance, general
release safety, content corruption or the central research hypothesis.

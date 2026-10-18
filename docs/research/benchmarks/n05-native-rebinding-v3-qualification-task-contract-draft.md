# Proposed Task Contract: node-tar native namespace-rebinding v3 qualification

Status: **PROPOSED / NOT_AUTHORIZED / NOT_RUN / NATIVE PRODUCER NOT_IMPLEMENTED**.

This contract proposes a bounded native qualification only. It does not reclassify the retained
v2 negative decision, generate a dependency token synthetically, promote synthetic v3 evidence
to native evidence, or authorize a P0/P1/P2 effectiveness campaign.

## Objective and immutable boundaries

The question is whether pinned node-tar 7.5.22 can issue independently verifiable evidence for
one real target branch in which a successful namespace removal continues to a successful
create/link operation for the same archive entry and destination path.

The accepted semantic shape remains the generic v3 model merged in PR #111:

```text
realized v2 removal: present -> absent
    + producer-issued branch-continuation edge
    + realized v2 create/link: absent -> present
    + same entry and destination path
    + no intervening destination-binding operation
    -> namespace_rebinding_sequence
```

V2 `namespace_replacement`, C0/C1/C2 and every frozen B0/B1/B3, A1/A2/A3 and P0/P1/P2
identifier remain byte-for-byte unchanged. A v3 result cannot issue
`V2_NATIVE_EFFECT_OBSERVATION_QUALIFIED`.

## Exact feasibility baseline

| Identity | Exact value / status |
| --- | --- |
| Repository baseline | `8d29982c26cebfcce7a413b3ba9177fcd28078de` |
| Generic v3 implementation head | `44e115b177d8b3aed7b06141c0523f567e0772c9` |
| Generic v3 merge | `8d29982c26cebfcce7a413b3ba9177fcd28078de` |
| Node | `22.22.0` |
| node-tar | `7.5.22` |
| node-tar package-lock SHA-256 | `28dc7696eda4a36462e927d5d42c1e764646631aed21d3e004999a7c24db8930` |
| node-tar npm tarball SHA-256 | `b792c2d1c7fc770910522ca1ffc29eee02ee38de4fa3a01e7832eb705879c6c6` |
| node-tar npm integrity | `sha512-MFO/QzvtAOmJbkhOaCTvbGcFN9L9b+JunIsDwaKljSOdcLMea3NJ1k9Usz/rjdfSXTq4dfzfeS7W4p4YOAAHeA==` |
| `dist/commonjs/unpack.js` SHA-256 | `03515ed98f5df6ec0f23177b7016274f8cdc91b038d0dcd036f438a70e614eed` |
| package entrypoint SHA-256 | `b5c4c31f353da9fe11ed352a95c6c247946549fec4f1326e871a3cd32158f9bf` |
| current v2 producer SHA-256 | `6c9a05a8420e800281e2e8662c17b176648fef13dc2182332ce063bb117aa5f4` |
| `@isaacs/fs-minipass` | `4.0.1`, lock integrity `sha512-wgm9Ehl2jpeqP3zw/7mo3kRHFp5MEDhqAdwy1fTGkHAwnkGOVsgpvQhL8B5n1qlb01jV3n/bI0ZfZp5lWA1k4w==` |
| fs-minipass tarball SHA-256 | `7ac286e3cccc1ea8980e79e2039def6bb97d3182e17951cd9094f0400ed98236` |
| fs-minipass CommonJS source SHA-256 | `2c934649bd1f847982fc06b02721244cb3271bf254afd71f23f9d20c14f9b59a` |
| Retained v2 qualification image | `sha256:30620f2d43af5782dd5e61aef06b87b44d1a9350154273f2cd2300cd24318ff3` — evidence reference only |

There is no native-v3 producer commit or immutable image ID. The retained v2 image does not
contain a v3 producer and is forbidden as a substitute. Therefore this proposal is not an
executable contract. A reviewed revision must freeze the new producer SHA-256, source commit,
image ID/platform manifest, controller identity, output root and authorization before any native
run.

## Exact native branch locations

The source locations below are meaningful only for the exact `unpack.js` digest above:

- `dist/commonjs/unpack.js:104-106`: on Linux, `unlinkFile(path, cb)` invokes
  `fs.unlink(path, cb)` without a timestamp-derived continuation.
- `unpack.js:609-679`: asynchronous `CHECKFS2`; for a present, non-directory, non-reusable
  destination, line 678 passes the actual unlink callback directly to
  `this[MAKEFS](er ?? null, entry, done)`.
- `unpack.js:688-706`: `MAKEFS` dispatches the same `entry` to FILE, HARDLINK, SYMLINK or
  DIRECTORY after the removal callback succeeds.
- `unpack.js:708-718`: LINK invokes `fs.link` or `fs.symlink` and completes the same entry.
- `unpack.js:439-517` plus exact fs-minipass `dist/commonjs/index.js:236-275`: FILE constructs
  the write stream, whose `_open()` invokes `fs.open` for the same destination.
- `src/inodefence/targets/_node_effect_producer.cjs:272-380`: the current v2 producer wraps
  callback operations and records before/after object evidence.
- `_node_effect_producer.cjs:369-371`: the current wrapper records operation completion and
  then invokes the target-supplied callback. This is the only proposed point for propagating a
  genuine callback-continuation provenance context.

Archive ordinal, operation timestamp adjacency or entry order alone is not a dependency.

## Required producer design

The native producer must remain source-guarded and target-specific. It may add a dedicated
`AsyncLocalStorage` continuation context around invocation of the original successful
`unlink`/`rmdir` callback. That context contains the already emitted predecessor correlation ID,
completion sequence, exact entry identity and destination path. The first eligible create/link
operation started by the target callback may emit one raw `producer_branch_continuation` record
when all of these match:

- same entry ordinal/path/type/link target;
- same sandbox-relative destination path;
- successful predecessor completion exists;
- successor is an eligible `open` creating a regular file, `mkdir`, `link` or `symlink`;
- the context has not already been consumed; and
- both operation records remain within the declared bounds.

The producer-issued record ID is the evidence token. A reader or adapter must not mint a token,
join operations from time/order, or fill a missing context. The producer must not pause, await,
acknowledge, serialize or reorder target callbacks. It performs no filesystem write except the
target's existing extraction and emits evidence only after the target terminates.

The transport must retain an exact v2 frame and a separate bounded v3 dependency frame. The
outer manifest binds both raw SHA-256 values. The existing v2 reader reconstructs endpoints;
the v3 reader receives the externally trusted v3 raw digest, joins exact endpoint records to the
producer dependency, and rederives the composite. Unknown/missing/duplicate records, overflow,
timeout, rejection prefixes and digest disagreement fail closed with no v3 feedback key.

## Independent corroboration

Qualification must keep four checks distinct:

1. **V2 endpoints:** a fresh Python process replays the current v2 reader from the retained raw
   frame and requires realized removal and creation/link events.
2. **Explicit absence:** removal completion must contain present-to-absent lstat evidence and the
   successor start must independently contain absent-before evidence. `NOT_OBSERVED` is not
   absence.
3. **Same-path semantics:** the reader compares canonical sandbox-relative destination strings and
   exact endpoint path evidence; hardlink source and destination roles remain separate.
4. **Dependency/interleaving:** only the producer callback-continuation record establishes the
   cross-operation edge. Global source sequence is used solely to reject an intervening realized
   destination binding. A qualification-only syscall trace may corroborate successful unlink then
   create/link return order, but cannot supply the dependency or feedback key.

Final stock/v2/v3 namespace snapshots and target outcomes must agree. Final state cannot replace
the transient absence evidence.

## Frozen fixture matrix proposal

All archives are deterministic, benign-contained qualification fixtures; none is a historical PoC,
fuzzing seed or CVE-specific recipe.

Positive fixtures, each expected to produce exactly one composite in every complete v3-full run:

1. regular destination -> unlink -> hardlink creation;
2. regular destination -> unlink -> symlink creation;
3. multiply-linked regular destination -> unlink -> regular-file open/create; and
4. the hardlink case with independent other-entry operations interleaved outside the dependency.

Negative fixtures, each expected to produce zero composites:

1. duplicate single-link regular file reusing the inode through truncation;
2. absent destination with creation only;
3. removal and creation endpoints belonging to different entries or paths;
4. failed removal;
5. successful removal followed by failed creation; and
6. target rejection/partial prefix.

Run `stock`, unchanged `v2-full` and proposed `v3-full` for every fixture, 20 repetitions each,
counterbalanced by a frozen schedule: **10 fixtures × 3 profiles × 20 = 600 target runs**.
Target timeout is 10 seconds, v2 event bound remains 256, v3 dependency bound is 64, and each raw
frame is at most 1 MiB. No slot is retried. Timeout, overflow, invalid, backend failure and at least
12 dependency/endpoint/digest tamper injections are retained outside the 600-run denominator.

Container policy remains the v2 qualification policy: Linux, UID/GID 1000, immutable image,
network none, read-only rootfs, cap-drop `ALL`, no-new-privileges, private namespaces, 512 MiB
memory/swap, 64 PIDs, 1,024 open files, 64 MiB file-size limit, separate runtime volume and fresh
subpath per run. Exact host/controller/output identities must be added before authorization.

## Acceptance and stop criteria

Issue `V3_NATIVE_REBINDING_OBSERVATION_QUALIFIED` only if all conditions pass:

- all 600 scheduled slots and every invalid-control slot are accounted for without retry;
- expected target outcome and final semantic state are identical across stock/v2/v3 profiles in
  every repetition;
- every v2/v3 frame is complete, bounded, flush-acknowledged, checksum-valid and independently
  reconstructed;
- each positive v3-full cell produces exactly one dependency-backed composite in 20/20;
- every negative, rejected, timed-out, overflowed or tampered cell produces no admitted v3 key;
- v3 preserves the exact v2 endpoint-event tuple and v2 feedback-key tuple;
- no composite is inferred from time, sequence adjacency, archive order or equal inode numbers;
- no realized same-destination binding operation intervenes between selected endpoints;
- for each fixture, the histogram of lifecycle ordinal completion sequences and v2 operation-order
  classes is exactly equal between v2-full and v3-full across the 20 counterbalanced repetitions;
- source inspection confirms no new await, delay, acknowledgment or target package modification;
  and
- independent controller and host readers reproduce the same decision from immutable raw bytes.

Duration and evidence size are reported for every run, but final-state equality or a favorable
median alone cannot establish neutrality. Any profile-specific outcome/state change, scheduling
histogram difference, observation failure, source drift, reader disagreement or incomplete cleanup
is `V3_NATIVE_REBINDING_OBSERVATION_NOT_QUALIFIED` or infrastructure-inconclusive as appropriate.
Do not weaken a criterion after observing the matrix.

## Authorization and downstream boundary

Before execution, a reviewed contract revision must supply the exact native producer commit/hash,
new immutable image/platform identity, source-cleanliness record, controller/host identities,
schedule/config digest, evidence roots and a one-attempt human authorization. Canonical Linux
`make check`, bounded contained producer checks and independent adversarial review must pass first.

Even a qualified decision authorizes no campaign. It does not change or reuse frozen P0/P1/P2
identifiers. A later effectiveness experiment needs its own versioned observation/policy contract,
budget, comparisons and approval. A negative result is retained as a feasibility result and stops
native-v3 campaign work.

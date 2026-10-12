# node-tar internal completion qualification v3

Classification: **BENIGN VALIDATED qualification evidence**. The candidate is
**QUALIFIED FAIL** for the current complete archive-ordered checkpoint contract.
This is not a security finding or a P0/P1/P2 effectiveness result.

## Question and method

Can node-tar 7.5.22's private filesystem completion callback provide exact entry
association and a coherent state after each archive ordinal without changing target
behavior?

The source-guarded probe wraps the actual `Unpack` class exported by the package
entrypoint. It does not edit the installed package, pause path reservations or serialize
the extractor. Three profiles use the same benign archives and target options:

- `stock`: unmodified `tar.x` and one final tree observation;
- `marker`: `onReadEntry` identity plus a minimal `checkFs2` completion marker; and
- `snapshot`: the same marker plus a synchronous consistency-checked tree walk before
  the path reservation is released.

The fixed cases cover regular files, directory metadata, hardlink, symlink, duplicate
path replacement, a directory with a child, and independent file work. Qualification
requires exact ordinal/path/type/link-target association, every entry's completed prefix
in archive order, no later-entry effect in a checkpoint, no observation failure, equal
final semantics across profiles, and all repetitions passing. The fixed input has no
random seed.

## Provenance

| Item | Exact value |
| --- | --- |
| Harness source | `9ea306f7ad20b8f479126360baf21192e0e86fdb`, clean |
| Analysis source | `5b2352ad13ef4b4d3dac9880e9ddc61d7eec6e8a` |
| Node / node-tar | `22.22.0` / `7.5.22` |
| Target options | `strict=true`, `preservePaths=false`, asynchronous |
| Package lock SHA-256 | `28dc7696eda4a36462e927d5d42c1e764646631aed21d3e004999a7c24db8930` |
| Actual package entrypoint SHA-256 | `b9464172723801f6ad013a1a819b5f31838753559d56c879202d7fb3c1326167` |
| Readable `unpack.js` SHA-256 | `03515ed98f5df6ec0f23177b7016274f8cdc91b038d0dcd036f438a70e614eed` |
| Probe SHA-256 | `45a3c732b7cd7ebfba549b6982257c5e7be1f9a0a7f0c9d5a612c1bf45c8e82b` |
| Environment | Linux `7.0.14-orbstack-00380-ga7e0a2dc9535`, aarch64, Python 3.12.3 |
| Process | uid/gid 1000, effective capabilities 0, seccomp 2 |
| Runtime | `/var/lib/inodefence`, separate from source checkout |
| Budget | 3 cases × 3 profiles × 20 repetitions = 180 processes |
| Per-process timeout | 10 seconds |
| UTC interval | 2026-10-12 00:35:40.758455–00:35:44.709124 |

The actual package entrypoint matters: node-tar's CommonJS default is the bundled
`index.min.js`, whose exported `Unpack` class is distinct from the readable standalone
`unpack.js` class. Both artifacts are guarded, and instrumentation targets the class
that `tar.x` actually constructs.

## Results

All 180 processes completed without target error or timeout. All 440 completion callbacks
across marker and snapshot profiles had exact logical-entry association. Every case had
one final semantic state, equal across stock, marker and snapshot profiles.

| Case / profile | Completion-order observations | Snapshot result |
| --- | --- | --- |
| directory-child / marker | `0,1`: 20/20 | marker only |
| directory-child / snapshot | `0,1`: 20/20 | 20/20 individually qualified |
| independent-files / marker | archive order 3/20; `0,1,3,2` 16/20; `0,3,1,2` 1/20 | marker only |
| independent-files / snapshot | archive order 2/20; `0,1,3,2` 18/20 | 0/20 qualified; one explicit snapshot failure |
| mixed / marker | archive order 2/20; `1,0,2,3,4` 18/20 | marker only |
| mixed / snapshot | `1,0,2,3,4`: 20/20 | 0/20 qualified |

In the mixed case, every ordinal-0 regular-file snapshot already contained the later
ordinal-1 directory. In the independent-files case, all 19 successfully captured first
completion snapshots already contained paths introduced by all four archive entries.
The remaining independent-files observation failed explicitly because `empty-dir`
changed after capture; it remains in the denominator. These observations show that an
exactly associated callback can still be delivered after other physical effects have
become visible.

The snapshot callback also changed the observed scheduling distribution relative to the
minimal marker. Stock has no completion markers, so scheduling equivalence cannot be
established by the stock profile. Final-state equivalence is therefore necessary but not
sufficient evidence of instrumentation neutrality.

Descriptive median target durations were:

| Case | Marker / stock | Snapshot / stock |
| --- | ---: | ---: |
| directory-child | 1.058× | 1.336× |
| independent-files | 1.008× | 1.660× |
| mixed | 1.032× | 1.433× |

These 20-run benign ratios are observation-cost signals, not throughput claims or formal
effect estimates. No confidence interval is attached and they are not combined with a
campaign dataset.

## Decision

The private callback is a useful, exact entry-completion marker, but it is not a qualified
producer for the current `TransitionTrace` model. Independent work completes out of archive
order, callback-time tree walks include effects from later ordinals, one walk detected an
active consistency race, and the snapshot callback measurably perturbs scheduling. The
global decision is therefore **QUALIFIED FAIL**, despite the simpler directory-child case
passing in isolation.

A future partial-order or deferred-effect model would be a new research contract. Merely
labelling callbacks with a completed-entry set is insufficient because filesystem effects
can be visible before their callback is delivered. No generic model condition is weakened,
no native producer is added, and P0/P1/P2 target effectiveness remains **NOT_RUN**.

This is the second materially different node-tar observation approach after public/OS/
syscall/prefix candidates, in addition to the separate libarchive qualification. Further
repetition in the same direction is not justified without a new mechanism or target API;
the next independent gate is the final-state N01 historical qualification.

## Evidence and reproduction

The immutable local raw record is
`experiments/raw/node-internal-completion-qualification-v3-9ea306f.json`:

| Property | Value |
| --- | --- |
| Raw size | 1,455,856 bytes |
| Raw SHA-256 | `ecb40154776e2f09883ecad6edb8f63abb57edc7becb3cd062863eb7e2a60cf0` |
| Evidence tier | `RAW_ONLY` |
| Validated derivative | [JSON](node-internal-completion-qualification-v3.json), SHA-256 `0bf6e6efde6bb78ec62aa60f0b42d4b57f049602940b75304953dc5ceddce710` |

The raw directory is intentionally ignored. Preserve or obtain those exact bytes before
re-analysis; the summary is not a replacement for raw evidence.

Re-run at the harness revision in the Linux Dev Container after installing the exact lock:

```bash
npm --prefix tools/node-tar ci --ignore-scripts --no-audit --no-fund
PYTHONPATH=src python scripts/qualify_node_internal_completion.py \
  --repetitions 20 --timeout-seconds 10 \
  --output experiments/raw/<new-node-internal-completion-run>.json
```

Recompute and verify the stored mechanical summary without executing the target:

```bash
PYTHONPATH=src:. python scripts/analyze_node_internal_completion.py \
  experiments/raw/node-internal-completion-qualification-v3-9ea306f.json
```

Limitations: this fixed benign qualification ran in the Dev Container with zero effective
capabilities and seccomp enabled, but `NoNewPrivs` was 0 and it was not an independently
network-disabled target container. It did not use a protected external sentinel or invoke
the Security Oracle. Those constraints do not turn it into security-effect evidence.

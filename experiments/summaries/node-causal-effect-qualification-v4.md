# node-tar causal filesystem-effect qualification v4

Classification: **BENIGN VALIDATED qualification evidence**. The candidate is
**QUALIFIED FAIL** for current archive-ordered `TransitionTrace` feasibility. The
repository-level decision is **BLOCKED_NATIVE_OBSERVATION**. This is not a security
finding, native producer, P0/P1/P2 target run or effectiveness result.

## Question and method

Can exact entry identity propagated through Node async resources, together with
causally attributed callback-based filesystem-operation completions, identify a clean
archive-ordered point after every node-tar entry effect?

This mechanism is separate from the v3 callback-time snapshot attempt. It does not use
an entry callback as a checkpoint or walk the tree while extraction is active. It records
successful `fs` operation completions and uses the private entry completion callback only
as an end marker. The installed package, target options and archive scheduling are not
patched or serialized.

Three profiles execute each entire TAR through one `await tar.x(...)` call:

- `stock`: no lifecycle or operation instrumentation;
- `context`: exact entry identity and completion markers with `AsyncLocalStorage`; and
- `effects`: context markers plus callback-based operation completion records.

The decision rule was committed before the retained run. Every normal effects run had to
preserve stock outcome/final semantics, associate every entry and operation exactly,
complete in archive order without a later ordinal's operation completing before an earlier
entry marker, and report no observation failure. The rejection case had to preserve an
explicit rejected outcome and an already completed entry. One overlap was sufficient to
fail feasibility because a passive marker-time snapshot cannot remove an effect already
present in the namespace.

## Fixtures and provenance

The eight fixed fixtures separately cover regular data, directory metadata, hardlink
identity, symlink creation, duplicate-path replacement, directory plus child, independent
files and a hardlink error after a prior duplicate-path regular entry completed.

| Item | Exact value |
| --- | --- |
| Harness source | `72bccfafe5f9f7e8ff06d850fb62a43fa6ed75d8`, clean |
| Node / node-tar | `22.22.0` / `7.5.22` |
| Target options | `strict=true`, `preservePaths=false`, asynchronous |
| Package lock SHA-256 | `28dc7696eda4a36462e927d5d42c1e764646631aed21d3e004999a7c24db8930` |
| Actual package entrypoint SHA-256 | `b9464172723801f6ad013a1a819b5f31838753559d56c879202d7fb3c1326167` |
| Readable `unpack.js` SHA-256 | `03515ed98f5df6ec0f23177b7016274f8cdc91b038d0dcd036f438a70e614eed` |
| Probe SHA-256 | `eca0bd96a016ae9ff9424328bbaf43b17d97f1be5740884d23dd5df8af51166b` |
| Environment | Linux `7.0.14-orbstack-00380-ga7e0a2dc9535`, aarch64, Python 3.12.3 |
| Process | uid/gid 1000, effective capabilities 0, seccomp 2 |
| Runtime | `/var/lib/inodefence`, separate from source checkout |
| Budget | 8 cases × 3 profiles × 20 repetitions = 480 processes |
| Per-process timeout | 10 seconds |
| UTC interval | 2026-10-13 00:21:16.545334–00:21:34.927523 |

## Results

All 480 processes returned a structured observation. The seven normal fixtures produced
420 expected successful outcomes; all 60 partial-rejection profile runs produced the
expected rejected outcome. There were no timeout, malformed record or observation failure
runs. Final semantic state, including hardlink identity groups, was equal across profiles
in every fixture.

All 320 context/effects runs had exact entry association. All 1,020 operation events in the
160 effects runs had exact entry association. The single-entry and dependent fixtures met
the causal feasibility conditions in all 20 effects runs. The global candidate failed on
independent work:

| Independent-files observation | Context | Effects |
| --- | ---: | ---: |
| Archive-order completion `0,1,2,3` | 1/20 | 0/20 |
| Completion `0,1,3,2` | 19/20 | 20/20 |
| Later-ordinal operations before earlier completion | not recorded | 162 |
| Exact entry association | 20/20 | 20/20 |
| Exact operation association | n/a | 20/20 |
| Observation failures | 0 | 0 |

Every effects run had at least three later-ordinal operations before ordinal 0's completion.
In a representative retained run, ordinal 1 `small-a` had completed `open` and `write`, and
ordinal 2 `small-b` had completed `open`, before the ordinal 0 `large` entry completion
marker. These are effects from later archive entries already completed in the real namespace,
rather than paths inferred from a receipt-time tree walk.

The rejection fixture was also explicit: in all 20 context and effects runs ordinal 0
completed, ordinal 1's missing-target hardlink recorded a target error, and the process was
classified rejected. No completed evidence was relabelled as success.

Descriptive median target-duration ratios were:

| Fixture | Context / stock | Effects / stock |
| --- | ---: | ---: |
| regular-file | 1.080× | 1.187× |
| directory-metadata | 1.050× | 1.152× |
| hardlink-identity | 1.102× | 1.275× |
| symlink | 1.097× | 1.279× |
| duplicate-path | 1.107× | 1.285× |
| directory-child | 1.181× | 1.281× |
| independent-files | 1.092× | 1.207× |
| partial-rejection | 1.116× | 1.308× |

The effects profile also changed the independent-files completion distribution from one
archive-order context run to none. These bounded timings and order counts are instrumentation
cost/neutrality warnings, not throughput estimates or formal effects.

## Decision

The causal effect candidate is **QUALIFIED FAIL** for current v1 feasibility. Exact entry
and operation association does not create an archive-prefix checkpoint when later entry
effects complete before an earlier entry marker. A marker-time full snapshot would therefore
repeat the already failed contamination mode. The effects profile also lacks evidence of
scheduling neutrality.

No native `TransitionRunResult` producer is added. Native P0/P1/P2 runs, smoke comparison
and effectiveness evaluation remain **NOT_RUN**. The synthetic transition model, scheduler,
evaluation export and replay remain reusable, but their v1 feedback keys cannot be assigned
to this effect-event evidence without changing the contract.

This is bounded evidence for node-tar 7.5.22 and the tested mechanism, not a proof that no
extractor or future public API can expose entry checkpoints. A separate partial-order/effect-
event v2 design is the minimum compatible alternative.

## Evidence and reproduction

The immutable local raw record is
`experiments/raw/node-causal-effect-qualification-v4-72bccfa.json`:

| Property | Value |
| --- | --- |
| Raw size | 2,392,080 bytes |
| Raw SHA-256 | `8addce903e418e04274993fe909f2053c8f44504d0b3bfe8fb4c65216fcdb07b` |
| Evidence tier | `RAW_ONLY` |
| Validated derivative | [JSON](node-causal-effect-qualification-v4.json), SHA-256 `7d6f0219cf7269c891c1feb2a76c7a2c04e51e6a27d097dbeef46f5367aec126` |

The raw directory is intentionally ignored. Preserve or obtain those exact bytes before
re-analysis; the committed derivative and this summary do not replace raw evidence.

Re-run from the clean harness revision in the Linux Dev Container:

```bash
npm --prefix tools/node-tar ci --ignore-scripts --no-audit --no-fund
PYTHONPATH=src python scripts/qualify_node_causal_effects.py \
  --repetitions 20 --timeout-seconds 10 \
  --output experiments/raw/<new-node-causal-effect-run>.json
```

Recompute and verify the mechanical summary:

```bash
PYTHONPATH=src:. python scripts/analyze_node_causal_effects.py \
  experiments/raw/node-causal-effect-qualification-v4-72bccfa.json
```

Limitations: the probe covers Node callback-based `fs` operations reached by these fixed
fixtures. It does not claim exhaustive syscall interception, a complete tree checkpoint,
production IPC reliability, target-container qualification or security-effect evidence.

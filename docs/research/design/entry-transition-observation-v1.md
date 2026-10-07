# node-tar entry-transition observation qualification v1

## Status

- Pinned source/API investigation: **IMPLEMENTED**, **TESTED**
- Benign regular/directory/hardlink/symlink/duplicate timing probe: **BENIGN VALIDATED**
- `onReadEntry` / deprecated `onentry` as completion boundary: **QUALIFIED FAIL**
- entry stream `end` as completion boundary: **QUALIFIED FAIL**
- Native entry-transition mode: **NOT_IMPLEMENTED**
- Prefix replay: **NOT_IMPLEMENTED**
- Transition-feedback effectiveness: **NOT_RUN**, **HYPOTHESIS**

`QUALIFIED FAIL` here means that the candidate lifecycle event does not establish
the required observation meaning. It is not a target security failure and says
nothing about transition-feedback effectiveness.

## Exact inspected target

The investigation used the repository pin Node `22.22.0`, node-tar `7.5.22`.

| Input | SHA-256 |
| --- | --- |
| `tar/dist/commonjs/unpack.js` | `03515ed98f5df6ec0f23177b7016274f8cdc91b038d0dcd036f438a70e614eed` |
| `tar/dist/commonjs/parse.js` | `c90f3771fa6c839b81c1d24961786463a195dfb8a59a8f190da30d33e7e1f769` |
| `tools/node-tar/package-lock.json` | `28dc7696eda4a36462e927d5d42c1e764646631aed21d3e004999a7c24db8930` |
| existing `_node_worker.cjs` | `feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b` |

The existing worker still calls one `await tar.x(...)`. No node-tar source or
worker extraction option was patched for this investigation.

## Source lifecycle finding

`Parser` emits `entry` when a `ReadEntry` becomes the parser's active entry. Its
`end` event advances the parser queue after archive body consumption. In `Unpack`,
the public `onReadEntry` listener is registered by `Parser` during `super(opt)`;
the internal `entry => this[ONENTRY](entry)` filesystem handler is registered only
afterward. Node EventEmitter listener order therefore calls the public callback
before node-tar starts `CHECKFS` for that entry.

Filesystem completion has a different lifecycle:

- regular files call `UNPEND` and release the path reservation only after stream
  finish, metadata operations and file descriptor close;
- directories call `UNPEND` after mkdir and scheduled metadata work;
- hardlinks/symlinks call `UNPEND` from the filesystem link callback;
- global finish/end is delayed until parser end and the internal pending count is zero.

There is no public event that carries the logical entry identity at the common
post-`UNPEND` point. The internal pending counter/path reservation callbacks are
implementation details. Wrapping them would depend on private symbols and a
pause/ack protocol would alter scheduling and possibly extraction semantics.
That path is not qualified as observation-only instrumentation.

## Reproducible benign probe

Run after installing the pinned target tools:

```bash
make target-tools
make node-entry-timing-probe
```

The probe archive contains, in order:

1. regular `regular` with content `first`
2. directory `dir`
3. hardlink `hard` to `regular`
4. symlink `sym` to `regular`
5. duplicate regular `regular` with replacement content `second`

The probe uses the public `tar.x({onReadEntry})` API and read-only lstat/content
checks. It does not modify node-tar or delay/ack entry processing.

Observed on 2026-10-07:

| Entry | At `onReadEntry` | At entry `end` | At `tar.x` resolution |
| --- | --- | --- | --- |
| first regular | absent | absent or 0-byte across repeated probes | replaced by final 6-byte content |
| directory | absent | directory present | directory present |
| hardlink | absent | link object present, nlink 2 | present, later nlink 1 after replacement |
| symlink | absent | symlink present | symlink present |
| duplicate regular | prior 5-byte object present | 0-byte object / empty digest | final 6-byte `second` content |

The regular and duplicate observations are decisive regressions: entry `end` can
occur before write completion/file close/final metadata, and the first regular's
observed race varied between absent and an empty file in two consecutive probes.
An event that happens to
show the expected effect for directories or links cannot serve as a common entry
completion boundary.

## Conservative decision

`NATIVE_ENTRY_TRANSITION = NOT_IMPLEMENTED` for node-tar 7.5.22. The generic
transition model remains usable by deterministic synthetic adapters and any future
target adapter that can prove a completion event without changing target semantics.

No event-aware execution API is added without a valid producer. This avoids an
unused protocol being mistaken for qualified native evidence. Prefix replay is
also absent; no fresh-process prefix result is called an entry-level transition.

Future work may re-evaluate a documented upstream completion hook or a separately
qualified observation-only mechanism. Any mechanism that serializes node-tar's
normally overlapping work, pauses internal reservations, or changes cache/queue
behavior must fail qualification unless semantic equivalence is demonstrated.

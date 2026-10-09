# libarchive public entry-boundary qualification v1

Classification: **BENIGN VALIDATED qualification evidence**. The public
`archive_write_finish_entry()` boundary in the tested write-disk reference target is
**QUALIFIED FAIL** as a common complete filesystem-effect boundary.

This is a separate reference target qualification. It is not evidence about node-tar
behavior, a vulnerability finding or a P0/P1/P2 effectiveness result.

## Research question

Does libarchive's public read/write-disk loop provide a behavior-preserving boundary
that carries exact logical entry identity and occurs after every filesystem effect of
that entry is complete?

The hypothesis was that a successful `archive_write_finish_entry()` return would
satisfy that contract. A failure required reproducible evidence that a filesystem
effect belonging to an entry occurred after its marker.

## Method and controls

The probe follows the upstream public loop:

```text
archive_read_next_header
  -> archive_write_header
  -> archive_write_data_block
  -> archive_write_finish_entry
  -> ordinal/path marker
  -> next entry
archive_write_close
```

It does not modify libarchive. The traced mode writes an ordinal/path marker only
after each successful `finish_entry`, plus markers immediately before and after
writer close. The quiet baseline executes the same API calls without markers.
strace records filesystem syscall returns and marker writes in one process order.

Two deterministic benign cases were each run 20 times in quiet baseline mode and 20
times under strace, for 80 total extractions and a 10-second per-process timeout:

1. regular, directory, hardlink, symlink and duplicate regular replacement;
2. mode-0555 directory `locked` followed by `locked/child`.

| Control | Exact value |
| --- | --- |
| InodeFence source | `99828fa4c83eab64476477d78c5932dfacd8e1ab`, clean |
| Target | public libarchive write-disk reference loop |
| Runtime / development package | `libarchive13t64` / `libarchive-dev` `3.7.2-2ubuntu0.9` |
| Runtime-reported library | `libarchive 3.7.2`, version number `3007002` |
| Compiler | GCC `13.3.0-6ubuntu2~24.04` |
| Probe source SHA-256 | `caf506ee78db47f26f9b8b849b2f55a73b7635a8c901f289e9cfff8277e99a46` |
| Probe binary SHA-256 | `f3f0e2e3b238368d81f703de8c0004767e4f77a56a35f635b29741687b60cc3b` |
| Qualification image ID | `sha256:3e12bcd8a99e32bd1ea04dbc7d423edd61236ae5f62c6e2406da0b73cc6dadda` |
| Base image ID | `sha256:59464488f5ee95e8fc3ecd81812c10a5a0d4ba9b5d917cd532ce8311957c10c1` |
| OS / architecture | Linux `7.0.14-orbstack-00380-ga7e0a2dc9535` / aarch64 |
| Process boundary | uid/gid 1000, capabilities 0, NNP 1, seccomp 2, network none |
| Random seed | N/A; fixed deterministic cases |

## Verified result

All 80 target executions succeeded with no timeout. Every traced run emitted the
expected ordinal/path sequence. Quiet and traced final snapshots had one selected
semantic variant per case, covering path, kind, link count, mode, size, symlink target
and regular content digest.

The directory effect ordering was decisive:

| Case / directory | Exact markers | Runs with metadata after `BEFORE_CLOSE` |
| --- | ---: | ---: |
| mixed effects / ordinal 1 `dir` | 20/20 | 20/20 |
| directory-child / ordinal 0 `locked` | 20/20 | 20/20 |

For both directories, `archive_write_finish_entry()` returned after creation and the
probe emitted the entry marker. After all entry markers and the `BEFORE_CLOSE` marker,
`archive_write_close()` opened the directory, applied its archived mtime with
`utimensat`, applied its archived mode with `fchmod`, and closed it. Only then did the
probe emit `AFTER_CLOSE`.

The mixed-effect trace also showed regular-file write, mtime and target descriptor
close before its marker; hardlink creation before its marker; and symlink creation and
mtime before its marker. These observations do not repair the common boundary because
directory effects are explicitly deferred.

The hypothesis is rejected for the tested API/options/version. The public function
provides exact entry association and a useful per-entry progress point, but its return
does not mean every filesystem effect for a directory is complete.

## Behavior and overhead limits

The baseline/traced final semantic equality shows no final-state difference for these
fixtures. It does not prove equivalence for every archive. Marker writes add work and
strace uses ptrace stops, so the traces are qualification evidence rather than a
behavior-neutral production observer.

Descriptive timing, including process launch:

| Case | Quiet mean | strace mean | Mean ratio |
| --- | ---: | ---: | ---: |
| mixed effects | 1.062 ms | 6.281 ms | 5.915 |
| directory-child | 0.750 ms | 5.516 ms | 7.355 |

These tiny-process measurements are not extractor-performance benchmarks.

## Evidence and reproduction

The local raw copy is
`experiments/raw/libarchive-entry-boundary-qualification-v1-99828fa.json`; repository
rules intentionally ignore it. A second copy remains in the disposable runtime
volume at
`/var/lib/inodefence/libarchive-entry-boundary-qualification-v1-99828fa.json`.

| Raw property | Value |
| --- | --- |
| Size | 420,013 bytes |
| SHA-256 | `d5703a2cf3d143caad9938a029340d79dc2b80bdf59665281c6e321007ccbff5` |
| UTC interval | 2026-10-09 15:27:42.198410–15:27:42.502296 |
| Evidence tier | `RAW_ONLY` |

Build the pinned qualification image and resolve immutable IDs:

```bash
docker build -f tools/libarchive/Dockerfile.qualification \
  -t inodefence-libarchive-qualification:3.7.2-2ubuntu0.9 .
LIBARCHIVE_IMAGE_ID=$(docker image inspect \
  inodefence-libarchive-qualification:3.7.2-2ubuntu0.9 --format '{{.Id}}')
BASE_IMAGE_ID=$(docker image inspect \
  vsc-inodefence-bc8d8c5f18eb139d6df3f1ebeba88e54793a9303c2661cec498ecaf6bad52f52:latest \
  --format '{{.Id}}')
```

Then run with a fresh output name:

```bash
docker run --rm --user vscode --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 128 --memory 512m --cpus 2 \
  --tmpfs /tmp:rw,exec,nosuid,nodev,mode=1777,size=128m \
  --mount type=bind,src="$PWD",dst=/workspaces/InodeFence,readonly \
  --mount type=volume,src=inodefence-transition-qual-v2,dst=/var/lib/inodefence \
  --workdir /workspaces/InodeFence \
  --env INODEFENCE_RUNTIME_ROOT=/var/lib/inodefence \
  inodefence-libarchive-qualification:3.7.2-2ubuntu0.9 \
  sh -lc "PYTHONPATH=src /usr/bin/python3.12 \
    scripts/qualify_libarchive_entry_boundary.py \
    --repetitions 20 --timeout-seconds 10 \
    --image-id '$LIBARCHIVE_IMAGE_ID' --base-image-id '$BASE_IMAGE_ID' \
    --output /var/lib/inodefence/<new-output>.json"
```

The raw `mechanical_summary` supplies success, exact-marker, semantic-variant and
deferred-directory counts. Every traced run also preserves the relevant syscall lines
and the mechanically selected post-`BEFORE_CLOSE` directory metadata lines.

## Decision and model consequence

`LIBARCHIVE_FINISH_ENTRY_BOUNDARY = QUALIFIED FAIL` for libarchive 3.7.2 with the
recorded write-disk options. No target adapter or `TransitionRunResult` producer is
added.

The experiment also confirms a model constraint: archive order, per-entry progress
order and actual effect-completion order cannot be represented as one ordered sequence
when an earlier directory's metadata completes only at global close. Supporting this
target would require an explicit deferred/finalization event model or a weaker
checkpoint meaning. Either change affects the generic transition contract and needs a
separate research justification before implementation.

The native P0/P1/P2 comparison remains **NOT_RUN** and transition-feedback
effectiveness remains **HYPOTHESIS**.

## Primary references

- [libarchive public API declarations](https://github.com/libarchive/libarchive/blob/master/libarchive/archive.h)
- [libarchive write-disk implementation](https://github.com/libarchive/libarchive/blob/master/libarchive/archive_write_disk_posix.c)
- [libarchive public extraction example](https://github.com/libarchive/libarchive/blob/master/examples/untar.c)

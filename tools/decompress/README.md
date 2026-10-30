# decompress (JS) generality target (M4.2)

A third, independent extractor — [decompress](https://www.npmjs.com/package/decompress) (Node.js)
— exercised through the **same unchanged** generic C0/C1/C2 oracle as node-tar and oras-go. This
is a controlled reference differential that shows the oracle is target-agnostic; it is **not** a
fuzzer self-discovery and makes no effectiveness claim. The generic model/Observer/Oracle/Feedback
modules are untouched; only the target-specific adapter (`src/inodefence/targets/decompress_js.py`)
and worker are new.

## Why decompress (selection rationale)

Of the M4.2 candidates (decompress, adm-zip, Archive::Tar, HF datasets, borg), decompress is the
cleanest generic-oracle reuse:

- **JavaScript** → reuses the pinned-Node container tier the project already runs for node-tar
  (no new toolchain).
- **CVE-2026-39243 is a hardlink bug** → the same **C1+C2** inode-aliasing signal the frozen
  oracle already evaluates (the direct analog of node-tar's and oras-go's hardlink escapes), so
  no new oracle contract is needed.
- decompress extracts tar via **`decompress-tar` / `tar-stream`** — a different parser than
  node-tar's `tar` — so it is a genuinely independent extractor, not a second node-tar.

(The decompress symlink CVE-2026-39246 would additionally exercise C0 / the symlink-referent
detector; that is left as future work.)

## What is pinned

| role | package | behaviour on the controlled fixture |
| --- | --- | --- |
| `affected` | `decompress` 4.2.1 | CVE-2026-39243 / GHSA-jwp9-9v96-94mx: a tar hardlink `Linkname` is passed to `fs.link` without validation, so a relative target is resolved against the process CWD and aliases an external file beside the extraction root. |
| `fixed` | `@xhmikosr/decompress` 11.1.4 | the maintained fork redirects the hardlink target inside the extraction root, so the escaping link is refused. |

The original kevva/`decompress` is unmaintained at 4.2.1 with no in-package fix, so the fixed side
uses the maintained fork (`@xhmikosr/decompress`) — the real ecosystem fix path. Both roles pin an
exact checksum-verified module graph via the committed `affected/` and `fixed/` `package-lock.json`
(`npm ci`), and the base image is `@sha256:` digest-pinned. `worker/worker.cjs` auto-detects which
package the image installed (from `/target/package.json`) and loads it by dynamic `import`
(`.default` is `module.exports` for the CJS original, the default export for the ESM fork). The
worker imports none of InodeFence's generic model or oracle.

## The controlled fixture and geometry

One hardlink entry `evil` whose link target is `outside/sentinel.txt` (no `..`). The disposable
sandbox places the protected sentinel at `outside/sentinel.txt`, a sibling of the extraction root,
and the extractor runs from the sandbox root (the isolated CWD). On 4.2.1, `fs.link` resolves
`outside/sentinel.txt` against that CWD and lands on the sentinel, so `extract/evil` shares the
sentinel's inode (**C1**) and the sentinel gains a hard link (**C2**). On the fixed fork the target
is redirected inside the extraction root (`extract/outside/sentinel.txt`, which does not exist), so
the link is refused and no violation remains. The release string is only an evidence key, never a
verdict condition (D005/D006).

## Build and run

```bash
docker build -f tools/decompress/Dockerfile --build-arg ROLE=affected -t inodefence-decompress:4.2.1 .
docker build -f tools/decompress/Dockerfile --build-arg ROLE=fixed    -t inodefence-decompress:11.1.4 .

# capability probe: build images, run real decompress both releases, record evidence
PYTHONPATH=src python3 experiments/repro/decompress_hardlink.py --out experiments/repro/evidence
```

The probe runs each release in a disposable, network-isolated, read-only container (writable
`/work` and `/tmp` tmpfs only, `--cap-drop ALL`, non-root), with the whole sandbox and sentinel
built **inside** the ephemeral container — the host is never the extraction target. No
isolation-relaxing flag is used. The CI-runnable oracle agreement is
`tests/test_decompress_generality.py`; the adapter's portable binding/classification is
`tests/test_decompress_adapter.py`; the production-path native closure is
`tests/container_integration/check_decompress_generality.py` (host Docker, out of `make check`).

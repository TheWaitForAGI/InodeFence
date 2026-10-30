# oras-go generality target (M4.1)

A second, independent extractor — [oras-go](https://oras.land) (Go, OCI registry
client) — exercised through the **same unchanged** generic C0/C1/C2 oracle as
node-tar. This is a controlled reference differential that shows the oracle is
target-agnostic; it is **not** a fuzzer self-discovery and makes no effectiveness
claim. The generic model/Observer/Oracle/Feedback modules are untouched; only this
target-specific adapter (`src/inodefence/targets/oras_go.py`) and worker are new.

## What is pinned

| role | oras-go | behaviour on the controlled fixture |
| --- | --- | --- |
| `affected` | v2.6.1 | CVE-2026-50163 / GHSA-fxhp-mv3v-67qp: a tar hardlink whose `Linkname` passes oras-go's containment check is still resolved by `os.Link` against the **process CWD**, so it aliases an external file beside the extraction root. |
| `fixed` | v2.6.2 | the patch resolves the hardlink target inside the extraction root, so the escaping link is not created. |

The build pins the exact release per role via committed `affected/` and `fixed/`
`go.mod` + `go.sum` (so `go mod download` fetches a checksum-verified module graph),
and pins both base images by `@sha256:` digest. `worker/main.go` is the shared
extraction source: it drives oras-go's `content/file` Store `Push` with the
`io.deis.oras.content.unpack` annotation and reports raw bytes/outcome only — it
imports none of InodeFence's generic model or oracle.

## The controlled fixture and geometry

One hardlink entry `d/evil` whose link target is `outside/sentinel.txt` (no `../`,
so it passes oras-go's lexical containment check). The disposable sandbox places
the protected sentinel at `outside/sentinel.txt`, a sibling of the extraction root,
and the extractor runs from the sandbox root (the isolated CWD). On v2.6.1,
`os.Link("outside/sentinel.txt", …)` resolves against that CWD and lands on the
sentinel, so `extract/d/evil` shares the sentinel's inode (**C1**) and the sentinel
gains a hard link (**C2**). On v2.6.2 the target is redirected inside the extraction
root (`extract/d/outside/sentinel.txt`, which does not exist), so the link is refused
and no violation remains. This is exactly the relation the oracle already evaluates;
the release string is only an evidence key, never a verdict condition (D005/D006).

## Build and run

```bash
# build both pinned target images (context = repo root)
docker build -f tools/oras-go/Dockerfile --build-arg ROLE=affected -t inodefence-oras-go:2.6.1 .
docker build -f tools/oras-go/Dockerfile --build-arg ROLE=fixed    -t inodefence-oras-go:2.6.2 .

# capability probe: build images, run real oras-go both releases, record evidence
PYTHONPATH=src python3 experiments/repro/oras_go_cwd_hardlink.py --out experiments/repro/evidence
```

The probe runs each release in a disposable, network-isolated, read-only container
(writable `/work` and `/tmp` tmpfs only, `--cap-drop ALL`, non-root), with the whole
sandbox and sentinel built **inside** the ephemeral container — the host is never the
extraction target. No isolation-relaxing flag (`--privileged`, cap-add, seccomp opt)
is used. The CI-runnable oracle agreement is `tests/test_oras_go_generality.py`; the
adapter's portable binding/classification is `tests/test_oras_go_adapter.py`.

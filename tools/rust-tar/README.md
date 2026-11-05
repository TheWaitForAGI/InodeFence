# Rust `tar` crate target (Tier-B, D039)

A new-lineage extractor — the Rust [`tar`](https://crates.io/crates/tar) crate (tar-rs), a compiled
Rust library independent of node-tar, oras-go (Go), decompress (JS) and Python tarfile — added under
지웅 결정 8 (2026-11-05, [D039](../../docs/DECISIONS.md)): "B 승인 — Rust `tar` 1개 조건부 추가. 11월 18일
사전등록을 지연시키면 A로 복귀." It is exercised through the **same unchanged** generic C0/C1/C2
oracle as node-tar. The generic model/Observer/Oracle/Feedback modules are untouched; only this
image recipe, the worker and the target-specific adapters (`src/inodefence/targets/rust_tar.py`,
`rust_tar_effect.py`) are new.

**Status: implemented + demo-run validated; no registered campaign has run.** After EXP-0 finished
(2026-11-05, see `docs/LOG.md`): both role `Cargo.lock` files are committed (libc pinned to 0.2.189,
see the build notes below), both images were built (0.4.35 `sha256:fe2da8c5…`, 0.4.36
`sha256:5cf1bc7c…`, as logged in `docs/LOG.md`; full ids in the probe evidence), `identify` matched 3 ways
(`cargo_lock_sha256` = committed lock, `tar_crate_version`, `worker_sha256` = the copied-out binary)
and the fixed-fixture probe ran ([evidence](../../experiments/repro/evidence/rust_tar_fixture_probe.json)):
no C1/C2 on any role fixture for either version, so the preregistered rule gives
`role_by_rule = fix-verification / H-B` for both. This is a demo run / fixture probe — not a
campaign, not qualification and not a registration.

## Tier-B discipline

Same rules as the EXP-3 preregistration's hold-out section: the target is **unexposed** (no prior
InodeFence run of any kind), it is **registered before any result**, only **fixed fixtures** run
before registration (**no fuzzing campaign**, no campaign mode is wired), and the outcome is **not
predicted**. The role comes from the fixture probe by the rule fixed in that preregistration: any
C1/C2 on a role fixture → `role=holdout`, hypothesis H-A; none → `role=fix-verification`, H-B.

## What is pinned

| role | `tar` crate | source |
| --- | --- | --- |
| `affected` | `=0.4.35` | last release in the advisory's affected range `<0.4.36` |
| `fixed` | `=0.4.36` | the advisory's patched release |

Ground truth for the pair (research rule 3: benchmark ground truth / root cause only — never an
oracle, feedback, vocabulary or seed input): **RUSTSEC-2021-0080** (CVE-2021-38511,
GHSA-62jx-8vmh-4mcw), affected function `tar::Archive::unpack`. The advisory text: "When unpacking a
tarball that contains a symlink the `tar` crate may create directories outside of the directory
it's supposed to unpack into. The function errors when it's trying to create a file, but the folders
are already created at this point." Fixed by tar-rs PR #259, published as 0.4.36
(<https://rustsec.org/advisories/RUSTSEC-2021-0080.html>). This is the advisory's claim, not an
InodeFence observation.

### Why this advisory (selection rule, applied 2026-11-05)

Rule: the **latest** RUSTSEC advisory for the `tar` crate about path/link confinement during unpack
whose affected effect the **unchanged** C0/C1/C2 contracts can observe. RustSec lists four `tar`
advisories and GitHub lists two more without a RUSTSEC id (both checked 2026-11-05).

| advisory | effect | observable by unchanged C0/C1/C2? |
| --- | --- | --- |
| GHSA-3pv8-6f4r-ffg2 (2026-05, fixed 0.4.46) | PAX header desynchronization | no — parser ambiguity, out of scope |
| GHSA-747h-hw98-c42x (2026-05, informational) | concurrent filesystem mutation | no — TOCTOU/race, out of scope |
| RUSTSEC-2026-0068 / CVE-2026-33055 (fixed 0.4.45) | PAX size header ignored | no — parser ambiguity, out of scope |
| RUSTSEC-2026-0067 / CVE-2026-33056 (fixed 0.4.45) | symlink then same-name directory → `chmod` of an external **directory** | no — a metadata-only change on a non-sentinel directory: C0 counts only existence/identity/type changes outside the extraction root and C2 covers the protected regular-file sentinels only; observing it would need a contract or sandbox change (out of this lane) |
| **RUSTSEC-2021-0080** / CVE-2021-38511 (fixed 0.4.36) | symlink → directories created outside the destination | **yes** — new objects outside the extraction root are a C0 namespace transition |
| RUSTSEC-2018-0002 / CVE-2018-20990 (fixed 0.4.16) | links overwrite existing files | yes, but older |

The selection looks only at what the advisory's effect is and whether the frozen contracts can see
it; it does not use (and could not use) any InodeFence result for this crate. If 지웅 prefers a
different pair, only the two `Cargo.toml` pins, the probe's `ROLES` and this table change — but that
was a pre-result option: now that the probe has run, changing the pair because of its outcome would
be post-hoc target selection and is not proposed (#239 hold-out rule).

## Worker protocol (same as `tools/oras-go/worker`)

`worker/src/main.rs` (Rust std + the pinned `tar` crate only; SHA-256, base64 and JSON output are
small local helpers so the locked graph stays the crate's own):

| subcommand | behaviour |
| --- | --- |
| `identify` | JSON `{tar_crate_version, rustc_version, cargo_lock_sha256, worker_sha256}`: the `tar` version from the embedded committed `Cargo.lock`, the compiler version seen by `build.rs`, the lock's SHA-256 (build-recipe provenance, checked against the committed lock — the preregistration binds the image id as `targets.<id>.image_digest`, like node-tar/oras-go/decompress) and the worker binary's own SHA-256 |
| `extract <archive> <dest>` | `tar::Archive::new(..).unpack(dest)` with the crate's **default settings** (no `set_*` call), CWD = sandbox root; exit 0 success, 2 crate refused/failed (REJECTED), 3 harness/IO |
| `frame <archive> <dest>` | same extraction, then one `inodefence-boundary-attempt-v1` frame on stdout derived from the observed post-state (region-based, no sentinel/advisory names), exactly the oras-go channel |
| `probe` | self-contained fixture probe in the node-tar regression geometry (`/work/extract`, external `/work/ext/reference.bin`; `TAR_B64`/`REF_B64`): reference lstat before/after, extracted objects sharing its inode, objects created/removed/changed outside the extraction root — raw only |

The adapters: `RustTarTarget` (`extract`, target id `rust-tar`) and `RustTarFrameTarget` (`frame`,
target id `rust-tar-boundary-attempt-frame`), version `tar=<exact>;rustc=<exact>`, artifacts
`rust-tar-cargo-lock` + `rust-tar-worker`, `ISOLATION_REQUIRED`. `effect_pipeline_oras_go.
run_oras_go_frame_case` takes any bound frame `IsolatedTarget`, so the frame target needs no new
pipeline code; no campaign mode drives it before registration.

## Build and run (post-EXP-0; requires Docker)

```bash
# 0. generate and commit each role's Cargo.lock with the pinned toolchain (network on, once)
RUST_IMAGE=rust:1.99.1-bookworm@sha256:c9155318d07341301a78b45ecdd81af2e43b8b297d64e8fd4c5e80d7735607c3
for role in affected fixed; do
  docker run --rm --user "$(id -u):$(id -g)" -e CARGO_HOME=/tmp/cargo \
    -v "$PWD/tools/rust-tar:/w" -w "/w/$role" "$RUST_IMAGE" cargo generate-lockfile
done
sha256sum tools/rust-tar/{affected,fixed}/Cargo.lock

# 1. build both pinned images (context = repo root); fails without the committed lock
docker build -f tools/rust-tar/Dockerfile --build-arg ROLE=affected -t inodefence-rust-tar:0.4.35 .
docker build -f tools/rust-tar/Dockerfile --build-arg ROLE=fixed    -t inodefence-rust-tar:0.4.36 .

# 2. identify: tar/rustc versions, lock digest (must equal sha256sum above), worker digest
docker run --rm --network none --read-only --cap-drop ALL inodefence-rust-tar:0.4.35 identify
docker run --rm --network none --read-only --cap-drop ALL inodefence-rust-tar:0.4.36 identify

# 3. fixed-fixture probe (role input; no fuzzing): plan first, then the real run
PYTHONPATH=src:. python3 experiments/repro/rust_tar_fixture_probe.py --dry-run
PYTHONPATH=src:. python3 experiments/repro/rust_tar_fixture_probe.py --skip-build --out experiments/repro/evidence
```

> **libc 핀 (2026-11-05 실측):** `tar`의 기본 의존성 `xattr 0.2.3`은 `libc >= 0.2.190`에서 `ENOATTR` 미정의로 컴파일이 깨진다(E0425). 따라서 `generate-lockfile` 직후 같은 고정 rust 이미지 안에서 각 role에 `cargo update -p libc --precise 0.2.189`를 적용한 lock을 커밋한다(현재 committed lock이 그 상태; 0.2.150~0.2.189 컴파일 확인, 0.2.190/0.2.191 실패). lock을 재생성하면 이 단계를 반드시 다시 적용한다.

Every probe run uses a disposable, network-isolated, read-only container (writable `/work` and
`/tmp` tmpfs only, all capabilities dropped, non-root distroless `cc-debian12`), with the whole
sandbox and reference file built **inside** the ephemeral container — the host is never the
extraction target. No isolation-relaxing flag is used. Base images are pinned by `@sha256:` index
digest (multi-arch: amd64 and arm64).

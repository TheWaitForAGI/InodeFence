# Track A read-only environment audit — 2026-10-16

```text
ORIGIN MAIN: 21e317281a2d2a7faf6198f66302f3912b429011
TRACK A WORKTREE: CLEAN AT AUDIT START
N04 RETAINED N01 READER AUDIT: AVAILABLE IN PR #107; 10-SECOND HISTORICAL SCOPE ONLY
N02 RAW ROOT IN THIS ENVIRONMENT: HOST_RAW_NOT_ACCESSIBLE
EXACT TARGET IMAGE INSPECTION: NOT_VERIFIABLE
5-SECOND PREFLIGHT: NOT_AUTHORIZED / NOT_RUN
20-CELL PILOT: NOT_AUTHORIZED / NOT_RUN
```

This Phase R audit performed no archive extraction, image build, package fetch, target launch,
Preflight or fuzzing. It is an environment/readiness record, not experiment evidence.

## GitHub and worktree facts

- `git fetch origin main` left `origin/main` at
  `21e317281a2d2a7faf6198f66302f3912b429011`, the requested initial main.
- Active remote merge refs observed through authenticated Git were PR #92, #106 and #107.
- PR #106 head `38f914f43f5ef230b19b6a13cf2a0da8263a77ad` contains the prospective
  five-second/exploratory-path proposal and is not in main.
- PR #107 head `a842a72c74ec833a76c89f4efb21bc62a839bf61` records an independent read of
  retained N02 evidence. It confirms the exact 10-second historical machine evidence while
  leaving human disposition pending; it contains no 5-second Preflight result.
- Draft PR #92 head `f8be20a37ea5ffdd64c2b56fbc7bfd14218ab595` was read only and not changed.
- The separate worktree `/tmp/inodefence-track-a-exploratory-pilot` was created from main on
  branch `experiment/track-a-exploratory-pilot`. The primary checkout remained untouched.

GitHub CLI was unavailable. Private web URLs returned 404, so status was obtained from
authenticated Git refs; no claim is made about UI review/check labels beyond those refs.

## Current environment facts

| Check | Observed result | Disposition |
| --- | --- | --- |
| OS/kernel | Linux WSL2 `6.18.33.2-microsoft-standard-WSL2` | recorded |
| Architecture | `x86_64` | **MISMATCH** with historical arm64/aarch64 evidence |
| Controller user | UID/GID 1000, non-root | PASS for this local fact only |
| Python | 3.12.3 | PASS for version fact only |
| Runtime root | `/var/lib/inodefence`, directory owned by UID/GID 1000 | available; no target use |
| Docker CLI | absent | **NOT_VERIFIABLE** image/runtime boundary |
| N02 raw root | `/Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z` absent | `HOST_RAW_NOT_ACCESSIBLE` |

Because target images cannot be inspected and the runtime/architecture differs, current
identity correspondence is not established. The run stops before Preflight as required.

## Static identity checks

The checked source bytes at base main matched the N01 records:

| Artifact | Recomputed SHA-256 | Result |
| --- | --- | --- |
| node-tar 7.5.2 lock | `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` | PASS |
| node-tar 7.5.3 lock | `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24` | PASS |
| Node worker | `feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b` | PASS |

The four benign case IDs remained the frozen values. Deterministic USTAR SHA-256 values were:

| Seed | Case ID | TAR SHA-256 |
| ---: | --- | --- |
| 0 | `c56da02197b3e8959e46c08c476c7fb15a13763ce9d8d57ac5151f4b1d709fd8` | `a80171f86279bce96ae232a7a720b318c9fdf1e64728a2f585e497e2701401d8` |
| 1 | `cdcc8045e37293498ff2d8e69e6e5638ee470f1bd11b1d0b8f16f1f9e783208f` | `9b82e0b00bc6da3760316311b59f1c1cee1d23f9fa87aa89fd544d7638af52c3` |
| 2 | `de8ddc5ca4c15fccb638257bbbe671c4fcc9c707962cb92de6589a09f6418620` | `3a8a8f4ca31ea5c73c61f683112166644a49575ff1b5d55ac9306182d3487b42` |
| 3 | `842bdde9b083096d6f5f1c93c93efb3ff35d141b7311571dab281c771d83c0d1` | `6cf67bab5248e3d0ecf3ec797a2f0f73273e999a32286a1446420b84cac432f1` |

These are static/build facts only. They do not admit either image, establish benign readiness,
execute C0/C1/C2 controls or demonstrate search reachability on node-tar.

## Blockers and next authorized action

1. Obtain a recorded bounded authorization for N04's exact five-second Preflight on the
   trusted arm64 macOS/OrbStack controller.
2. Run and independently verify that Preflight; preserve a failure and stop if any identity,
   containment, readiness, cleanup or reader check fails.
3. Obtain a separate authorization for the 20 cells, with its immutable authorization digest.
4. Freeze the clean execution SHA, Preflight digest, exact target provenance and 20-cell plan
   into the new Track A evidence root before the first campaign.

Current evidence stage: **RAW ONLY (readiness audit)**. There are no B0/B1/B3 experimental
results to analyze.

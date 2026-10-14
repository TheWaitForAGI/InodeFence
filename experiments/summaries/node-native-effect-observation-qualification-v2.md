# node-tar native effect observation qualification v2

Decision: **`V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`**. The fixed 480-run matrix
completed on **2026-10-13** with 420 successful runs and 60 expected rejections. Thirteen of
fourteen mandatory criteria passed. `required_effect_coverage` failed because the fixed
duplicate-path fixture produced truncation of the existing inode in 20/20 full-profile runs,
and namespace replacement in 0/20. The retained runner classification is **RAW_ONLY**.
Independent verification establishes the recorded negative engineering qualification; it
does not qualify the producer for feedback or make a research effectiveness claim.

## Source and environment

- Task Contract: recover and execute Gate 3/4 on WSL using the existing trusted host/controller
  broker, with the fixed fixtures/profiles/repetitions and acceptance rules unchanged.
- Gate 4 starting revision: `55751696a59e8ee4e278625d24fe320973395399`.
- Clean qualification revision: `36ff7fdb0e31db72b3e581fd1c089b712b4a7b4e`, on
  `fix/native-effect-qualification-wsl`. Two scoped fixes follow the starting revision.
- WSL2/Linux kernel: `6.18.33.2-microsoft-standard-WSL2`, x86_64; Python 3.12.3;
  controller execution UID/GID 1000/1000.
- Docker Desktop 4.85.0, Engine/CLI 29.6.2, API 1.55; context `default`, endpoint
  `unix:///var/run/docker.sock` on the WSL host.
- Existing controller: `adoring_noyce`, full ID
  `45830e39b8f59e9519d53f9efa2d0f9b01bea77990e79ab04d6ce46453ed4e02`. It was already running.
  `/workspaces/InodeFence` binds the requested repository; `/var/lib/inodefence` uses the
  separate named volume `inodefence-runtime`.
- Target: Node 22.22.0/node-tar 7.5.22, fixed digest-pinned Dockerfile and lockfile.
  Rebuilt image ID:
  `sha256:30620f2d43af5782dd5e61aef06b87b44d1a9350154273f2cd2300cd24318ff3`.
- Producer SHA-256: `6c9a05a8420e800281e2e8662c17b176648fef13dc2182332ce063bb117aa5f4`.
  All package/entrypoint/unpack digests and enforced isolation are retained in the raw report.
- Extraction options: complete asynchronous `tar.x({strict: true, preservePaths: false})`.
  Event bound 256; timeout 10 seconds; memory 512 MiB, PID limit 64, open files 1024,
  file-size limit 64 MiB, temporary filesystem 32 MiB.
- Target containers use UID/GID 1000, read-only rootfs, network none, all capabilities dropped,
  no-new-privileges and only the current run's volume subpath. The controller has no Docker
  CLI/socket; Docker requests cross the existing explicit stdio broker.
- Random seed: not applicable; all eight fixtures and TAR bytes are deterministic, with no
  mutation or campaign. Config, case IDs and source cleanliness are retained in the report.
- Recorded start/end: `2026-10-13T05:57:03.931313+00:00` /
  `2026-10-13T06:09:22.974771+00:00`.

## Recovery and Gate 3

The original image passed both image checks, but all eight normal Gate 3 fixtures failed
association validation. Their first raw operation was the extractor's read-only open of
`archive/input.tar`, before any entry existed. Eight invalid raw bundles and their manifest
digests were retained. The independent reader rejects this original unassociated evidence.

Commit `66cd9f6` excludes only that exact read-only input open with no entry context/handle
owner from the entry-effect channel. Other unassociated sandbox path operations still fail
closed. It also preserves invalid Gate 3 raw evidence before assertion. A new image was built
with the existing Dockerfile; the old image/tag was retained.

The first Gate 4 attempt then stopped before any matrix run: the adapter supplied unsorted
artifact digests and an unsupported origin to the shared `IsolationProvenance` model. Commit
`36ff7fd` fixes the adapter's artifact ordering and uses the existing image-identification
origin. A regression test reproduces the original failure; the shared model was unchanged.
The failed attempt directory and log remain separate from the completed matrix.

On the clean fixed revision, **Gate 3 PASS — `GATE3_NATIVE_PRODUCER_IMPLEMENTED`**:
`validate-node-effect-producer` passed all 10 contained checks, including eight fixtures,
overflow and timeout. Related portable tests passed 30/30. Canonical `make check` passed
Ruff, format, Pyright, **1,387 tests**, environment and documentation checks.

## Fixed matrix and independent verification

Each of regular-file, directory-metadata, hardlink-identity, symlink, duplicate-path,
directory-child, independent-files and partial-rejection ran 20 times under each of stock,
minimal and full: **480/480**, with 160 runs per profile. Expected outcomes and final semantic
states matched in every repetition. All 320 minimal/full streams passed association,
correlation, sequence, evidence and causal reconstruction. Normalized keys were stable per
fixture/profile; all rejected prefixes emitted no feedback keys.

All 10 required derived invalid-stream injections were rejected. Actual forced timeout and
event overflow evidence remained incomplete/invalid and were rejected by the reader. The
injected backend failure remained distinct. These are additional checks outside the 480-run
matrix. The container-suite test's `1 passed` means the runner produced a valid decision;
the decision itself is **NOT_QUALIFIED**.

Fresh controller and host processes each verified all 160 stock records and reconstructed all
320 native bundles, checked artifact hashes and regenerated the mechanical summary. Both
reproduced the retained decision. Timeout/overflow raw bundles and every derived invalid frame
were rechecked. Backend failure classification remains evidence from the actual runner's
injection; the audit does not rerun a target or manufacture backend evidence.

## Failed criterion and interpretation

Only **`required_effect_coverage`** failed. All required operation checks passed; the failed
realized-effect cell is duplicate-path → `namespace_replacement`. The second regular-file
open retained the same `(st_dev, st_ino)` and qualified as truncation in all 20 full runs.
The pinned unpack source's `ISREUSABLE` path reuses an existing regular file with link count
at most one when unlink mode is disabled. The fixed fixture therefore does not demonstrate
the required replacement class. No option, fixture or acceptance rule was changed to turn
this result into a pass.

Independent-files full completion was `0,1,3,2` in 20/20 runs; minimal was `0,1,2,3` in 12/20
and `0,1,3,2` in 8/20. This observed scheduling difference is retained, while normalized key
sets stayed stable. Per-fixture median full-pipeline full/stock ratios ranged from 1.017 to
1.166. These include controller/container execution and evidence work, and are not estimates
of instrumentation-only or campaign overhead. Per-run target/full durations and evidence
sizes remain in `qualification.json`.

## Immutable evidence

Primary controller directory:
`/var/lib/inodefence/node-native-effect-observation-qualification-v2-20261013-36ff7fd-AA8cvq`.

WSL mirror: `experiments/raw/node-effect-gates-20261013-AA8cvq/qualification`.
Session directory: `experiments/raw/node-effect-gates-20261013-AA8cvq`, including failed Gate 3
raw bundles, both Gate 4 attempt logs, build/preflight/check logs, independent reader reports,
the audit script and duplicate/rejection analysis. The completed primary directory and host
session were made read-only. No existing raw evidence was overwritten.

| Artifact | SHA-256 |
| --- | --- |
| `qualification/qualification.json` | `ca2dae9150813c6df14df10e16de65b1139550a7ecd761a30122c717e4575a90` |
| `independent-reader.json` (controller audit) | `2bb348cfb1c4ffa398ed118ff87c035f2af1c825933215b9d5c8bb7fadd293aa` |
| `independent-reader-host.json` | `657c07a509acd0437ee57387baced1ba5e7c23debb8da4bfaa7cf5574329b573` |
| `audit_qualification.py` | `b968ab672acff40d884f6a4add3838639663a9b76bbb4b295cdeb135f73ab3ba` |
| `experiments/raw/node-effect-gates-20261013-AA8cvq.sha256` (1,180 files) | `59b0fb74a402ffb41200639e5c5e36c6b8e53dd83f9704cf463775a5be05d1bf` |
| `experiments/raw/node-effect-gates-20261013-AA8cvq.tar.gz` | `6b0a5b31d52d00347259342683941692181e93515d7f82384df86d9fb1cab1e5` |

The checksum list was verified against every retained file. Raw evidence remains ignored by
Git; this summary records its locations and identities.

## Reproduction and next gate

Use the clean qualification revision and the existing trusted controller/broker. Rebuild the
fixed Dockerfile, resolve the actual Docker context/controller/image IDs, and use a fresh
absolute output directory:

```bash
PYTHONPATH=src:. python3 -m scripts.container_host \
  --context "$IF_DOCKER_CONTEXT" --controller "$IF_CONTROLLER_ID" \
  --volume inodefence-runtime --image "$IF_NODE_IMAGE_ID" \
  validate-node-effect-producer

PYTHONPATH=src:. python3 -m scripts.container_host \
  --context "$IF_DOCKER_CONTEXT" --controller "$IF_CONTROLLER_ID" \
  --volume inodefence-runtime --image "$IF_NODE_IMAGE_ID" \
  --evidence <new-absolute-controller-directory> qualify-node-effect-v2

PYTHONPATH=src:. python3 \
  experiments/raw/node-effect-gates-20261013-AA8cvq/audit_qualification.py \
  experiments/raw/node-effect-gates-20261013-AA8cvq/qualification \
  --output <new-audit-file>
```

The infrastructure blocker is resolved. Gate 5 remains **BLOCKED / NOT_RUN** because Gate 4
did not qualify. A separate Task Contract must establish actual replacement coverage and
freeze any fixture extension before another complete qualification. The present result
cannot establish feedback advantage, rediscovery, a target vulnerability or paper effectiveness.

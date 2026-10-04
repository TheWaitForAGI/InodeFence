# node-tar adapter validation dependency

Node 22.22.0 and npm-lockfile `tar` 7.5.22 are the benign integration baseline.
The package lock records transitive versions/integrities. Install in supported Linux:

```bash
make target-tools
make check
```

Dev Container post-create and CI install this dependency using `npm ci --ignore-scripts`.
Node is pinned in both environment definitions; an existing container may need rebuilding.
Python distribution includes the CJS worker, while this external dependency root remains
an explicit `NodeTarTarget(package_root=...)` argument. No dependency installation occurs
inside an extraction observation window. node_modules is ignored.

This is adapter engineering with ordinary controlled fixtures. `NodeTarTarget` always
declares ISOLATION_REQUIRED; generated-input campaigns remain rejected. Process-group
cleanup is not an OS sandbox. No benchmark security evaluation or vulnerable-version
selection is provided. API/options follow [upstream node-tar](https://github.com/isaacs/node-tar).

## Disposable target image v1

[Dockerfile](Dockerfile) pins the Node 22.22.0/bookworm build stage and distroless
Debian 12 C++ runtime by manifest digest. `npm ci --ignore-scripts --no-audit --no-fund`
uses the committed lock; only Node, locked modules, the lock and the small worker
are copied into the runtime. No shell, npm, Git, SSH, curl or compiler is present
at the standard executable paths. This is checked inside the actual target image.
Build-time package managers and cache do not enter that image.

```bash
docker build -f tools/node-tar/Dockerfile -t inodefence-node-tar:v1 .
IF_NODE_IMAGE=$(docker image inspect inodefence-node-tar:v1 --format '{{.Id}}')
PYTHONPATH=src python3.12 -m scripts.container_host --context orbstack \
  --controller <running-dev-container-ID> --volume inodefence-runtime \
  --image "$IF_NODE_IMAGE" validate-node-image
```

The tag is a build convenience; execution requires the resolved immutable local
SHA-256 image ID. The metadata-only check uses the enforced container backend,
records exact Node/tar versions and verifies worker/lock SHA-256 against source.
It does not execute an archive or enable campaign execution. Image packaging is
not a bit-for-bit reproducibility claim: platform, builder and attestation metadata
can change the resulting image identity. Config/provenance binding follows next.

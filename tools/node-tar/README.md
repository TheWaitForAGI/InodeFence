# node-tar adapter validation dependency

Node 22.22.0 and lockfile tar 7.5.22 are the benign integration baseline.
The lock records transitive versions/integrities for the image build. The production
adapter no longer resolves a controller-local Node/module or launches it directly.
`NodeTarTarget.bind(backend, immutable_image_id)` returns the contained adapter.
Worker version guards and strict=true/preservePaths=false remain target-specific.
Campaign admission requires the enforced wrapper and frozen isolation/config binding.
The fixed Dockerfile remains the approved tiny benign infrastructure smoke baseline.
The separately authorized N01 qualification uses committed pair-specific locks,
`inodefence.evaluation.node_packaging`, immutable image IDs and the same enforced backend;
it does not turn this directory into a general vulnerable-version selector.
API/options follow [upstream node-tar](https://github.com/isaacs/node-tar).

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
That mode does not execute an archive or enable campaign execution.
`validate-node-target` separately executes eight mandatory ordinary fixture/lifecycle cases. Image packaging is
not a bit-for-bit reproducibility claim: platform, builder and attestation metadata
can change the resulting image identity. Isolation/config/provenance binding and the
tiny benign configured campaign's full path have been validated; see the
[recorded smoke scope and limits](../../experiments/summaries/benign-node-container-smoke-v1.md).
Snapshot observation, runtime/kernel trust and portability limits remain. N01 qualification
is a known-class ground-truth gate, not a formal search-policy evaluation or evidence of
research effectiveness.

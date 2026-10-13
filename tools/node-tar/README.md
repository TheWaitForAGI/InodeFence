# node-tar adapter validation dependency

Node 22.22.0 and lockfile tar 7.5.22 are the benign integration baseline.
The lock records transitive versions/integrities for the image build. The production
adapter no longer resolves a controller-local Node/module or launches it directly.
`NodeTarTarget.bind(backend, immutable_image_id)` returns the contained adapter.
Worker version guards and strict=true/preservePaths=false remain target-specific.
Campaign admission requires the enforced wrapper and frozen isolation/config binding.
Only the approved tiny benign infrastructure smoke is within the current Task Contract.
No benchmark security evaluation or vulnerable-version selection is provided.
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
Snapshot observation, runtime/kernel trust and portability limits remain. Benchmark/security
evaluation and research effectiveness have not been evaluated.

## Causal effect qualification probe

`causal-effect-probe.cjs`는 production worker가 아니다. 고정된 package entrypoint와 readable
`unpack.js`의 hash를 확인한 뒤, qualification profile에서만 entry async context와 callback 기반
filesystem operation completion을 연결한다. Installed node-tar source, extraction options 또는
archive processing을 serialize하지 않는다. stdout의 종료 후 JSON 외에는 관찰 namespace에
bookkeeping을 쓰지 않는다.

이 probe의 effect event는 실제 callback 반환 전에 해당 filesystem operation이 완료됐다는
evidence이지만 완전한 tree snapshot은 아니다. 특히 archive order, effect-completion order,
observation order를 동일시하지 않으며 native `TransitionRunResult` producer로 사용하지 않는다.

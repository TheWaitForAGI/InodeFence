# node-tar native effect observation qualification v2

Classification: **NOT_RUN**. Gate 3 producer code and the Gate 4 independent reader/fixed
qualification runner are implemented and pass portable contract tests. This revision has no
Docker CLI or `/var/run/docker.sock`, so neither the contained producer suite nor the required
480-run qualification matrix was executed. No native raw evidence, checksum or exact Gate 4
decision token exists yet.

## Fixed scope

The runner uses pinned Node 22.22.0/node-tar 7.5.22 and preserves the existing complete
asynchronous `tar.x({strict: true, preservePaths: false})` invocation. It executes regular-file,
directory-metadata, hardlink-identity, symlink, duplicate-path, directory-child,
independent-files and partial-rejection cases under stock, minimal and full profiles for 20
repetitions each.

Each minimal/full run exports the exact raw stdout frame, canonical `EffectRunResult` and
manifest. The independent reader reconstructs entry associations, lifecycle/effect events,
operation correlation, class-specific evidence, causal edges, terminal integrity, final-state
derivations and normalized keys. The matrix also retains actual timeout and overflow bundles,
programmatically derived invalid frames for every required reader failure, and an injected
backend failure. Scheduling distributions and full-pipeline/evidence-size overhead are reported
without assuming zero perturbation.

The acceptance logic emits `V2_NATIVE_EFFECT_OBSERVATION_QUALIFIED` only when every mandatory
criterion passes. Any evaluated failure emits `V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`.
Because the matrix did not run, neither token describes this revision.

Portable validation on this checkout passed `make check`: Ruff, format, Pyright, 1,386 tests,
development-environment checks and documentation checks. These checks validate engineering
contracts and do not substitute for the contained matrix.

## Reproduction

Run from a clean checkout of the Gate 4 commit on the trusted Linux host/controller setup. Use
a new absolute evidence destination; the writer refuses overwrite.

```bash
docker build -f tools/node-tar/Dockerfile -t inodefence-node-tar:22.22.0-7.5.22 .
IMAGE_ID=$(docker image inspect inodefence-node-tar:22.22.0-7.5.22 --format '{{.Id}}')

PYTHONPATH=src:. python -m scripts.container_host \
  --context "$DOCKER_CONTEXT" \
  --controller "$CONTROLLER_ID" \
  --volume inodefence-runtime \
  --image "$IMAGE_ID" \
  validate-node-effect-producer

PYTHONPATH=src:. python -m scripts.container_host \
  --context "$DOCKER_CONTEXT" \
  --controller "$CONTROLLER_ID" \
  --volume inodefence-runtime \
  --image "$IMAGE_ID" \
  --evidence /var/lib/inodefence/node-native-effect-observation-qualification-v2 \
  qualify-node-effect-v2

sha256sum \
  /var/lib/inodefence/node-native-effect-observation-qualification-v2/qualification.json
```

Read any completed minimal/full bundle independently with its retained manifest digest:

```bash
PYTHONPATH=src:. python scripts/verify_node_effect_evidence.py \
  /var/lib/inodefence/node-native-effect-observation-qualification-v2/runs/regular-file/full-0 \
  --manifest-sha256 <manifest-sha256>
```

## Claim boundary and next gate

This is an engineering observation qualification. It cannot establish feedback advantage,
rediscovery, a target vulnerability or a paper effectiveness result. Gate 5 native campaign
integration stays blocked unless a reviewed immutable report retains the exact qualified token.


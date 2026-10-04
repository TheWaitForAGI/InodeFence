# Exact-lock Node target packaging

This independent tooling consumes operator-supplied npm lockfile-v3 releases.
It preserves the existing benign `tools/node-tar` 7.5.22 path unchanged. It
does not choose vulnerable releases, generate archive inputs or run evaluations.

```bash
python -m inodefence.evaluation.node_packaging prepare \
  tools/node-tar/package-lock.json /tmp/node-tar-7.5.22-build --repository .
python -m inodefence.evaluation.node_packaging build \
  /tmp/node-tar-7.5.22-build --docker-context default
```

Prepare several supplied release locks in distinct directories using the same
pinned source checkout. Each context captures the same source worker bytes,
Node 22.22.0, Node base digest and distroless runtime digest as the benign baseline.
All resolved package versions/integrities are exact. No ranges/tags as root
release, local/link dependencies, host npm install or mutable base tags are used.
`npm ci --ignore-scripts --engine-strict` installs the exact supplied lock only
inside the build stage. Dependency-declared semver ranges remain metadata; locked
resolved versions and integrity are the install anchors.

`packaging.json` is a checksummed completion marker for the fixed build inputs.
Missing/partial/corrupt/floating contexts fail validation; unrelated files may
not enter the Docker context. Context files and build records are never overwritten.
`build.json` preserves actual build logs and the inspected immutable image ID,
architecture, package-lock/worker/package/Dockerfile identities and package/runtime
releases. Invoke existing contained adapter binding with that image ID, not a tag.

The build is packaging evidence, not target qualification or research results.
Qualification separately verifies the actual image's worker/package-lock probe
and target/runtime identity through the existing execution backend. Supplied lock
authenticity is operator-owned; npm verifies declared package integrity. Source
dirty/unavailable state is recorded, not silently promoted to a clean pin. Hard
interruption can leave a partial context/build record, which must be inspected;
there is no build resume or power-loss durability guarantee. Run the Python tool
with repository dependencies and Docker on the host/controller, as appropriate;
no target receives the Docker socket or source mount.

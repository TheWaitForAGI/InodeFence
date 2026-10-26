# Effect-capable node-tar image for the Phase-2 rediscovery probe.
#
# Parameterized by TAR_VERSION so one Dockerfile builds each FROZEN_TARGETS
# version (7.5.2 affected, 7.5.3 fixed) from the committed, hash-pinned lock in
# tools/node-tar/versions/<version>/. It is SEPARATE from the n01 reproduction
# image (inodefence.evaluation.node_packaging) and from the 7.5.22 effect image
# (tools/node-tar/Dockerfile); it changes neither and reuses the same base pins.
#
# Unlike the node_packaging reproduction build, this image carries BOTH the
# effect producer and the benign worker, so the feedback loop gets the identical
# observation apparatus as the 7.5.22 effect image.
#
# Requires BuildKit for the TAR_VERSION-parameterized COPY source. Build context
# is the repository root. Build with, e.g.:
#   docker build -f tools/node-tar/effect/Dockerfile --build-arg TAR_VERSION=7.5.2 .
ARG TAR_VERSION

# Build dependencies never enter the runtime image.
FROM node:22.22.0-bookworm-slim@sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94 AS dependencies
ARG TAR_VERSION
WORKDIR /target
COPY tools/node-tar/versions/${TAR_VERSION}/package.json tools/node-tar/versions/${TAR_VERSION}/package-lock.json ./
RUN npm ci --ignore-scripts --engine-strict --no-audit --no-fund
RUN test "$(node --version)" = "v22.22.0" && \
    node -e "if(require('./node_modules/tar/package.json').version !== '${TAR_VERSION}') process.exit(1)"

FROM gcr.io/distroless/cc-debian12:nonroot@sha256:9dac0a79194e45a7da0158a9c6da57b217585af0786db3845d1f0ec1a0dd182f
COPY --from=dependencies /usr/local/bin/node /usr/local/bin/node
COPY --from=dependencies /target/node_modules /target/node_modules
COPY --from=dependencies /target/package-lock.json /target/package-lock.json
COPY src/inodefence/targets/_node_worker.cjs /target/worker.cjs
COPY src/inodefence/targets/_node_effect_producer.cjs /target/effect-producer.cjs
USER 1000:1000
ENTRYPOINT ["/usr/local/bin/node", "/target/worker.cjs"]

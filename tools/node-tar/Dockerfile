# Build dependencies never enter the runtime image.
FROM node:22.22.0-bookworm-slim@sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94 AS dependencies
WORKDIR /target
COPY tools/node-tar/package.json tools/node-tar/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

FROM gcr.io/distroless/cc-debian12:nonroot@sha256:9dac0a79194e45a7da0158a9c6da57b217585af0786db3845d1f0ec1a0dd182f
COPY --from=dependencies /usr/local/bin/node /usr/local/bin/node
COPY --from=dependencies /target/node_modules /target/node_modules
COPY --from=dependencies /target/package-lock.json /target/package-lock.json
COPY src/inodefence/targets/_node_worker.cjs /target/worker.cjs
USER 1000:1000
ENTRYPOINT ["/usr/local/bin/node", "/target/worker.cjs"]

# Diagnostic sibling: existing target and controller images are never modified.
ARG TARGET_IMAGE
ARG CHECK_IMAGE
FROM ${TARGET_IMAGE} AS pinned
FROM ${CHECK_IMAGE}
USER root
COPY --from=pinned /usr/local/bin/node /usr/local/bin/node
COPY --from=pinned /target/node_modules /target/node_modules
COPY --from=pinned /target/package-lock.json /target/package-lock.json
COPY --from=pinned /target/effect-producer.cjs /target/effect-producer.cjs
COPY tools/node-tar/diagnostics/replacement-probe.cjs /target/replacement-probe.cjs
USER 1000:1000
ENTRYPOINT ["/usr/local/bin/node", "/target/replacement-probe.cjs"]

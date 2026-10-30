# Throwaway feasibility-probe image (InodeFence M4 follow-up): real decompress 4.2.1 with the
# fs-wrap effect probe. Build context = this directory. Demonstrator only, not a qualified target
# (npm install is version-pinned but not lockfile-reproducible; the pinned-digest node base is).
FROM node:22.23.4-bookworm-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da
WORKDIR /target
RUN npm init -y >/dev/null 2>&1 \
    && npm install decompress@4.2.1 --ignore-scripts --no-audit --no-fund --loglevel=error
COPY fswrap_probe.cjs ./fswrap_probe.cjs
USER 1000:1000
ENTRYPOINT ["/usr/local/bin/node", "/target/fswrap_probe.cjs"]

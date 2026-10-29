# decompress (JS) generality target image (InodeFence M4.2). Build context = repo root.
#
# ROLE selects the pinned decompress package/release; the worker auto-detects it from the
# copied /target/package.json, so no runtime env is needed:
#   docker build -f tools/decompress/Dockerfile --build-arg ROLE=affected -t inodefence-decompress:4.2.1 .
#   docker build -f tools/decompress/Dockerfile --build-arg ROLE=fixed    -t inodefence-decompress:11.1.4 .
#
# affected = decompress 4.2.1 (CVE-2026-39243 / GHSA-jwp9-9v96-94mx: a tar hardlink Linkname is
# passed to fs.link unvalidated, so a relative target is resolved against the process CWD).
# fixed = @xhmikosr/decompress 11.1.4, the maintained fork's patched release -- the original
# kevva/decompress is unmaintained at 4.2.1 with no in-package fix. Both roles pin an exact
# checksum-verified module graph via the committed package-lock.json (npm ci).
ARG ROLE=affected

# Node base pinned by both the patched tag (22.23.4 fixes CVE-2026-111497, the Brotli decoder
# out-of-bounds write) and the immutable digest; the two resolve to the same image.
FROM node:22.23.4-bookworm-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da
ARG ROLE
WORKDIR /target
COPY tools/decompress/${ROLE}/package.json tools/decompress/${ROLE}/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY tools/decompress/worker/worker.cjs ./worker.cjs
USER 1000:1000
ENTRYPOINT ["/usr/local/bin/node", "/target/worker.cjs"]

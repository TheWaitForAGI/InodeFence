# Rust `tar` crate (tar-rs) Tier-B target image (InodeFence D039, 지웅 결정 8).
#
# Build context is the repository root. ROLE selects the pinned `tar` crate release:
#   docker build -f tools/rust-tar/Dockerfile --build-arg ROLE=affected -t inodefence-rust-tar:0.4.35 .
#   docker build -f tools/rust-tar/Dockerfile --build-arg ROLE=fixed    -t inodefence-rust-tar:0.4.36 .
#
# affected = tar 0.4.35, fixed = tar 0.4.36 (RUSTSEC-2021-0080 / CVE-2021-38511 /
# GHSA-62jx-8vmh-4mcw: `Archive::unpack` of a tarball containing a symlink may create directories
# outside the destination; patched in 0.4.36). The advisory is ground truth for the pair only; it
# is never an oracle/feedback condition (D005/D006). See tools/rust-tar/README.md.
#
# Each role commits Cargo.toml (exact `=` pin) AND Cargo.lock, and the build is
# `cargo build --locked`, so the same role always resolves the same checksum-verified crate graph.
# The build FAILS when the role's Cargo.lock is absent: the COPY below names it explicitly, the RUN
# re-checks it, and build.rs refuses too. Generate it once with this pinned toolchain
# (tools/rust-tar/README.md) and commit it -- never let the image build resolve dependencies ad hoc.
ARG ROLE=affected

FROM rust:1.99.1-bookworm@sha256:c9155318d07341301a78b45ecdd81af2e43b8b297d64e8fd4c5e80d7735607c3 AS build
ARG ROLE
COPY tools/rust-tar/${ROLE}/Cargo.toml tools/rust-tar/${ROLE}/Cargo.lock /build/${ROLE}/
COPY tools/rust-tar/worker/ /build/worker/
WORKDIR /build/${ROLE}
RUN test -s Cargo.lock \
    && cargo build --locked --release \
    && install -D -m 0755 target/release/rust-tar-worker /out/rust-tar-worker

# glibc runtime matching the bookworm builder (distroless cc = glibc + libgcc, no shell), non-root.
FROM gcr.io/distroless/cc-debian12:nonroot@sha256:9dac0a79194e45a7da0158a9c6da57b217585af0786db3845d1f0ec1a0dd182f
COPY --from=build /out/rust-tar-worker /target/rust-tar-worker
ENTRYPOINT ["/target/rust-tar-worker"]

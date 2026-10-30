# oras-go generality target image (InodeFence M4.1).
#
# Build context is the repository root. ROLE selects the pinned oras-go release:
#   docker build -f tools/oras-go/Dockerfile --build-arg ROLE=affected -t inodefence-oras-go:2.6.1 .
#   docker build -f tools/oras-go/Dockerfile --build-arg ROLE=fixed    -t inodefence-oras-go:2.6.2 .
#
# affected = oras-go v2.6.1 (CVE-2026-50163 / GHSA-fxhp-mv3v-67qp: a tar hardlink
# whose Linkname passes the containment check is still resolved by os.Link against
# the process CWD, escaping the extraction root). fixed = v2.6.2.
#
# Both go.mod/go.sum are committed per role, so `go mod download` fetches the exact
# checksum-verified module graph: same role => same pinned oras-go version.
ARG ROLE=affected

FROM golang:1.25-bookworm@sha256:3b4a11519ad929d1e1d261a12cff056f0c85b735253d7d861346b9c6f8b36437 AS build
ARG ROLE
WORKDIR /build
COPY tools/oras-go/${ROLE}/go.mod tools/oras-go/${ROLE}/go.sum ./
COPY tools/oras-go/worker/main.go ./
RUN go mod download && CGO_ENABLED=0 go build -trimpath -o /oras-worker .

FROM gcr.io/distroless/static-debian12:nonroot@sha256:afa5c872c891853ca7fcf1f12c3edb23f7eeef36189728842dd51042ff57f7ab
COPY --from=build /oras-worker /target/oras-worker
ENTRYPOINT ["/target/oras-worker"]

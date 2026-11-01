#!/usr/bin/env bash
# M4 self-discovery native run: the effect campaign loop over REAL oras-go (3rd extractor).
#
# Usage: scripts/local_oras_go_selfdiscover.sh
#   Builds the controller/helper images and the pinned AFFECTED oras-go image
#   (inodefence-oras-go-selfdiscover:affected, from tools/oras-go/Dockerfile ROLE=affected -- the
#   oras-worker with the `frame` subcommand), creates a trusted non-root Linux controller, and runs
#   the `oras-go-effect-campaign` controller mode: mutate (generic) -> real oras-go (frame worker)
#   -> generic C0/C1/C2 oracle (the hit) -> set-based boundary-attempt / violation feedback. The
#   JSON report (incl. discovered_violation + per-step oracle/feedback) is copied to the host.
#
# This mirrors scripts/local_decompress_selfdiscover.sh: the target runs only inside the controller
# through the production ContainerExecutionBackend (hardened isolation, NO isolation-relaxing flag);
# this host script only builds images, prepares the controller and delegates through
# scripts.container_host.
#
# Overrides: INODEFENCE_DOCKER_CONTEXT, PYTHON (default python3.12),
# INODEFENCE_EVIDENCE_DIR (default ~/inodefence-evidence), ORAS_GO_ROLE (default affected),
# DEMO_SEED, DEMO_BUDGET, DEMO_MUTATION_POLICY (campaign arm; e.g. the state-aware identity arm
# uniform-generic-m1-state-aware-escape-hardlink-v1, or the random control uniform-generic-v1).
# Parallel-safe: set RUN_ID to a unique token (e.g. m4sd-oras-<arm>-<seed>); the controller, volume
# and evidence filename all carry that suffix, so concurrent arms never collide and each removes
# only what it created. SKIP_BUILD=1 reuses prebuilt images; BUILD_ONLY=1 builds and exits.
set -euo pipefail

RUN_ID="${RUN_ID:-}"
SKIP_BUILD="${SKIP_BUILD:-}"
BUILD_ONLY="${BUILD_ONLY:-}"
ORAS_GO_ROLE="${ORAS_GO_ROLE:-affected}"
if [ -n "$RUN_ID" ] && ! [[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "RUN_ID must match [A-Za-z0-9][A-Za-z0-9_.-]* (got: $RUN_ID)" >&2
  exit 2
fi
if [ "$SKIP_BUILD" = 1 ] && [ "$BUILD_ONLY" = 1 ]; then
  echo "SKIP_BUILD=1 and BUILD_ONLY=1 are mutually exclusive" >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found: real oras-go runs only from the host terminal (macOS + OrbStack, WSL2)." >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3.12}"
CONTEXT="${INODEFENCE_DOCKER_CONTEXT:-$(docker context show)}"
EVIDENCE_DIR="${INODEFENCE_EVIDENCE_DIR:-$HOME/inodefence-evidence}"

CONTROLLER_IMAGE=inodefence-controller:local
HELPER_IMAGE=inodefence-helper:local
ORAS_GO_IMAGE="inodefence-oras-go-selfdiscover:${ORAS_GO_ROLE}"
CONTROLLER="inodefence-oras-go-controller${RUN_ID:+-$RUN_ID}"
VOLUME="inodefence-oras-go-runtime${RUN_ID:+-$RUN_ID}"

STAMP="$(date +%Y%m%d-%H%M%S)"
LABEL="${RUN_ID:-$STAMP}"
CONTROLLER_EVIDENCE="/tmp/inodefence-oras-go-selfdiscover-$LABEL.json"
HOST_EVIDENCE="$EVIDENCE_DIR/inodefence-oras-go-selfdiscover-$LABEL.json"

STEP="setup"
CREATED_VOLUME=0
CREATED_CONTROLLER=0

dk() { docker --context "$CONTEXT" "$@"; }
step() { STEP="$1"; echo "==> [$STEP]"; }
host() {
  (cd "$REPO_ROOT" && PYTHONPATH=src "$PYTHON" -m scripts.container_host \
    --context "$CONTEXT" --controller "$CONTROLLER" --volume "$VOLUME" "$@")
}

cleanup() {
  local status=$?
  set +e
  if [ "$status" -ne 0 ]; then
    echo "FAILED at step: $STEP (exit $status)" >&2
  fi
  if [ "$CREATED_CONTROLLER" -eq 1 ] && dk exec "$CONTROLLER" test -e "$CONTROLLER_EVIDENCE"; then
    mkdir -p "$EVIDENCE_DIR"
    if dk cp "$CONTROLLER:$CONTROLLER_EVIDENCE" "$HOST_EVIDENCE" >/dev/null; then
      echo "evidence: $HOST_EVIDENCE"
    else
      echo "evidence copy failed: $CONTROLLER_EVIDENCE" >&2
    fi
  fi
  if [ "$CREATED_CONTROLLER" -eq 1 ]; then
    dk rm -f "$CONTROLLER" >/dev/null
  fi
  if [ "$CREATED_VOLUME" -eq 1 ]; then
    dk volume rm "$VOLUME" >/dev/null
  fi
  if [ "$status" -eq 0 ]; then
    echo "PASSED: oras-go self-discovery (context=$CONTEXT role=$ORAS_GO_ROLE)"
  fi
  exit "$status"
}
trap cleanup EXIT

step "preflight"
echo "context=$CONTEXT engine=$(dk version --format '{{.Server.Version}}') role=$ORAS_GO_ROLE"
command -v "$PYTHON" >/dev/null || { echo "host Python not found: $PYTHON" >&2; exit 1; }
if [ "$BUILD_ONLY" != 1 ] && { dk container inspect "$CONTROLLER" >/dev/null 2>&1 ||
  dk volume inspect "$VOLUME" >/dev/null 2>&1; }; then
  echo "stale $CONTROLLER or $VOLUME exists; inspect and remove it manually:" >&2
  echo "  docker --context $CONTEXT rm -f $CONTROLLER; docker --context $CONTEXT volume rm $VOLUME" >&2
  exit 1
fi

if [ "$SKIP_BUILD" = 1 ]; then
  step "reuse prebuilt images"
  echo "SKIP_BUILD=1: reusing $CONTROLLER_IMAGE / $HELPER_IMAGE / $ORAS_GO_IMAGE"
else
  step "build images"
  export BUILDX_NO_DEFAULT_ATTESTATIONS=1
  BUILD_FLAGS=(--quiet)
  [ "${VERBOSE:-0}" = 1 ] && BUILD_FLAGS=()
  dk build "${BUILD_FLAGS[@]}" -f "$REPO_ROOT/.devcontainer/Dockerfile" -t "$CONTROLLER_IMAGE" "$REPO_ROOT"
  dk build "${BUILD_FLAGS[@]}" -f "$REPO_ROOT/tools/container-helper/Dockerfile" -t "$HELPER_IMAGE" "$REPO_ROOT"
  dk build "${BUILD_FLAGS[@]}" --build-arg "ROLE=$ORAS_GO_ROLE" \
    -f "$REPO_ROOT/tools/oras-go/Dockerfile" -t "$ORAS_GO_IMAGE" "$REPO_ROOT"
fi

if [ "$BUILD_ONLY" = 1 ]; then
  echo "BUILD_ONLY=1: shared images ready (context=$CONTEXT role=$ORAS_GO_ROLE); no controller created"
  exit 0
fi

step "prepare controller"
dk volume create "$VOLUME" >/dev/null
CREATED_VOLUME=1
dk run -d --name "$CONTROLLER" --user vscode --workdir /workspaces/InodeFence \
  --env PYTHONPATH=/workspaces/InodeFence/src \
  --mount "type=bind,src=$REPO_ROOT,dst=/workspaces/InodeFence,readonly" \
  --mount "type=volume,src=$VOLUME,dst=/var/lib/inodefence" \
  "$CONTROLLER_IMAGE" sleep infinity >/dev/null
CREATED_CONTROLLER=1
dk exec --user root "$CONTROLLER" chown vscode:vscode /var/lib/inodefence
dk exec "$CONTROLLER" python -m pip install --quiet --disable-pip-version-check pytest
dk exec --workdir / "$CONTROLLER" git config --global --add safe.directory /workspaces/InodeFence

IF_ORAS_GO_IMAGE="$(dk image inspect "$ORAS_GO_IMAGE" --format '{{.Id}}')"

step "oras-go-effect-campaign"
DEMO_ARGS=()
[ -n "${DEMO_SEED:-}" ] && DEMO_ARGS+=(--seed "$DEMO_SEED")
[ -n "${DEMO_BUDGET:-}" ] && DEMO_ARGS+=(--budget "$DEMO_BUDGET")
[ -n "${DEMO_MUTATION_POLICY:-}" ] && DEMO_ARGS+=(--mutation-policy "$DEMO_MUTATION_POLICY")
host --image "$IF_ORAS_GO_IMAGE" --evidence "$CONTROLLER_EVIDENCE" \
  ${DEMO_ARGS[@]+"${DEMO_ARGS[@]}"} oras-go-effect-campaign

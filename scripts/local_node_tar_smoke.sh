#!/usr/bin/env bash
# Local replay of the CI container-integration job (.github/workflows/ci.yml).
#
# Usage: scripts/local_node_tar_smoke.sh [smoke|effect|demo|demo-historical]
#   smoke  (default) validate, validate-node-image, validate-node-target, benign-node-smoke
#   effect           validate-node-effect-producer
#   demo             effect-demo: feedback loop on real node-tar, JSON copied to the host
#                    (plus <name>.steps.jsonl: steps finished so far, kept even on abort)
#   demo-historical  effect-demo-historical: state-aware loop on a prebuilt frozen historical
#                    node-tar effect image (catalog pair 7.5.2/7.5.3), JSON copied to the host
#
# The real target runs only inside the trusted non-root Linux controller; this host
# script only builds images, prepares that controller and delegates through
# scripts.container_host. It removes only the controller/volume it created itself.
#
# Overrides: INODEFENCE_DOCKER_CONTEXT (default: `docker context show`),
# PYTHON (default: python3.12), INODEFENCE_EVIDENCE_DIR (default: ~/inodefence-evidence).
# demo only: DEMO_POLICY, DEMO_MUTATION_POLICY, DEMO_SEED, DEMO_BUDGET (controller defaults
# P2 adaptive, M1, 123, 20; budget is capped at 100 in code).
# demo-historical only: TAR_VERSION (required, 7.5.2|7.5.3), HISTORICAL_IMAGE (default
# inodefence-node-tar-effect:$TAR_VERSION; must already exist), DEMO_SEED, DEMO_BUDGET
# (defaults P2 adaptive + escape-hardlink in code; budget capped at 100 in code).
#
# Parallel runs on one host: set RUN_ID to a unique token (e.g. <version>-<arm>-<seed>)
# and the controller, volume and evidence filename all carry that suffix, so independent
# campaigns never collide and each still removes only the controller/volume it created.
# Empty RUN_ID keeps the original single-run names. SKIP_BUILD=1 reuses already-built
# images; BUILD_ONLY=1 builds the shared images and exits without creating a controller.
# scripts/run_parallel_native.py drives a version/arm/seed matrix this way under a
# concurrency cap (it builds once with BUILD_ONLY, then fans out with SKIP_BUILD).
set -euo pipefail

MODE="${1:-smoke}"
case "$MODE" in
  smoke | effect | demo | demo-historical) ;;
  *)
    echo "usage: $0 [smoke|effect|demo|demo-historical]" >&2
    exit 2
    ;;
esac

RUN_ID="${RUN_ID:-}"
SKIP_BUILD="${SKIP_BUILD:-}"
BUILD_ONLY="${BUILD_ONLY:-}"
# RUN_ID keeps concurrent campaigns from colliding; validate it before it reaches a
# container/volume name. The pattern matches Docker's own name grammar.
if [ -n "$RUN_ID" ] && ! [[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "RUN_ID must match [A-Za-z0-9][A-Za-z0-9_.-]* (got: $RUN_ID)" >&2
  exit 2
fi
if [ "$SKIP_BUILD" = 1 ] && [ "$BUILD_ONLY" = 1 ]; then
  echo "SKIP_BUILD=1 and BUILD_ONLY=1 are mutually exclusive" >&2
  exit 2
fi

# Builtins only up to here, so the Dev Container gets guidance instead of a setup failure.
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found: real node-tar runs only from the host terminal (macOS + OrbStack, WSL2)." >&2
  if [ "$MODE" = demo ]; then
    echo "inside the Dev Container run the synthetic demo (not node-tar): make demo-synthetic" >&2
  fi
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3.12}"
CONTEXT="${INODEFENCE_DOCKER_CONTEXT:-$(docker context show)}"
EVIDENCE_DIR="${INODEFENCE_EVIDENCE_DIR:-$HOME/inodefence-evidence}"

CONTROLLER_IMAGE=inodefence-controller:local
HELPER_IMAGE=inodefence-helper:local
NODE_IMAGE=inodefence-node-tar:local
# A non-empty RUN_ID suffixes the per-run resources so parallel campaigns never
# share a controller or volume; empty keeps the original single-run names.
CONTROLLER="inodefence-local-controller${RUN_ID:+-$RUN_ID}"
VOLUME="inodefence-local-runtime${RUN_ID:+-$RUN_ID}"

STAMP="$(date +%Y%m%d-%H%M%S)"
# Evidence filename label: RUN_ID is deterministic and parallel-safe; without it the
# timestamp keeps the original single-run filenames unchanged.
LABEL="${RUN_ID:-$STAMP}"
if [ "$MODE" = demo ]; then
  CONTROLLER_EVIDENCE="/tmp/inodefence-effect-demo-native-$LABEL.json"
  HOST_EVIDENCE="$EVIDENCE_DIR/inodefence-effect-demo-native-$LABEL.json"
elif [ "$MODE" = demo-historical ]; then
  CONTROLLER_EVIDENCE="/tmp/inodefence-effect-demo-historical-$LABEL.json"
  HOST_EVIDENCE="$EVIDENCE_DIR/inodefence-effect-demo-historical-$LABEL.json"
else
  CONTROLLER_EVIDENCE="/tmp/inodefence-node-smoke-$LABEL"
  HOST_EVIDENCE="$EVIDENCE_DIR/inodefence-node-smoke-$LABEL"
fi

STEP="setup"
CREATED_VOLUME=0
CREATED_CONTROLLER=0

dk() {
  docker --context "$CONTEXT" "$@"
}

step() {
  STEP="$1"
  echo "==> [$STEP]"
}

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
  if [ "$CREATED_CONTROLLER" -eq 1 ] && [ "$MODE" != effect ] &&
    dk exec "$CONTROLLER" test -e "$CONTROLLER_EVIDENCE"; then
    mkdir -p "$EVIDENCE_DIR"
    if dk cp "$CONTROLLER:$CONTROLLER_EVIDENCE" "$HOST_EVIDENCE"; then
      echo "evidence: $HOST_EVIDENCE"
    else
      echo "evidence copy failed: $CONTROLLER_EVIDENCE" >&2
    fi
  fi
  # demo: the per-step JSONL written before each next case (scripts/container_controller.py).
  if [ "$CREATED_CONTROLLER" -eq 1 ] && [ "$MODE" = demo ] &&
    dk exec "$CONTROLLER" test -e "${CONTROLLER_EVIDENCE%.json}.steps.jsonl"; then
    mkdir -p "$EVIDENCE_DIR"
    if dk cp "$CONTROLLER:${CONTROLLER_EVIDENCE%.json}.steps.jsonl" "${HOST_EVIDENCE%.json}.steps.jsonl"; then
      echo "completed steps: ${HOST_EVIDENCE%.json}.steps.jsonl"
    else
      echo "steps copy failed: ${CONTROLLER_EVIDENCE%.json}.steps.jsonl" >&2
    fi
  fi
  if [ "$CREATED_CONTROLLER" -eq 1 ]; then
    dk rm -f "$CONTROLLER" >/dev/null
  fi
  if [ "$CREATED_VOLUME" -eq 1 ]; then
    dk volume rm "$VOLUME" >/dev/null
  fi
  if [ "$status" -eq 0 ]; then
    echo "PASSED: node-tar $MODE (context=$CONTEXT)"
  fi
  exit "$status"
}
trap cleanup EXIT

step "preflight"
echo "context=$CONTEXT engine=$(dk version --format '{{.Server.Version}}') mode=$MODE"
command -v "$PYTHON" >/dev/null || {
  echo "host Python not found: $PYTHON" >&2
  exit 1
}
# Never remove resources this run did not create; ask the operator instead.
# BUILD_ONLY only builds shared images (no controller), so it skips this guard.
if [ "$BUILD_ONLY" != 1 ] && { dk container inspect "$CONTROLLER" >/dev/null 2>&1 ||
  dk volume inspect "$VOLUME" >/dev/null 2>&1; }; then
  echo "stale $CONTROLLER or $VOLUME exists; inspect and remove it manually:" >&2
  echo "  docker --context $CONTEXT rm -f $CONTROLLER; docker --context $CONTEXT volume rm $VOLUME" >&2
  exit 1
fi

if [ "$SKIP_BUILD" = 1 ]; then
  step "reuse prebuilt images"
  echo "SKIP_BUILD=1: reusing $CONTROLLER_IMAGE / $HELPER_IMAGE (+ $NODE_IMAGE for non-historical)"
else
  step "build images"
  # Build logs are noise on a demo screen; VERBOSE=1 restores docker's full progress.
  BUILD_FLAGS=(--quiet)
  [ "${VERBOSE:-0}" = 1 ] && BUILD_FLAGS=()
  dk build "${BUILD_FLAGS[@]}" -f "$REPO_ROOT/.devcontainer/Dockerfile" -t "$CONTROLLER_IMAGE" "$REPO_ROOT"
  dk build "${BUILD_FLAGS[@]}" -f "$REPO_ROOT/tools/container-helper/Dockerfile" -t "$HELPER_IMAGE" "$REPO_ROOT"
  # The historical effect image is prebuilt and frozen out of band; never build it here.
  if [ "$MODE" != demo-historical ]; then
    dk build "${BUILD_FLAGS[@]}" -f "$REPO_ROOT/tools/node-tar/Dockerfile" -t "$NODE_IMAGE" "$REPO_ROOT"
  fi
fi

if [ "$BUILD_ONLY" = 1 ]; then
  echo "BUILD_ONLY=1: shared images ready (context=$CONTEXT mode=$MODE); no controller created"
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
# --workdir /: a git worktree checkout has a .git file pointing outside the mount,
# and git dies on repository discovery even for --global config.
dk exec --workdir / "$CONTROLLER" git config --global --add safe.directory /workspaces/InodeFence

IF_HELPER_IMAGE="$(dk image inspect "$HELPER_IMAGE" --format '{{.Id}}')"
if [ "$MODE" != demo-historical ]; then
  IF_NODE_IMAGE="$(dk image inspect "$NODE_IMAGE" --format '{{.Id}}')"
fi

if [ "$MODE" = demo-historical ]; then
  step "effect-demo-historical"
  : "${TAR_VERSION:?set TAR_VERSION to a catalog-registered historical node-tar (7.5.2 or 7.5.3)}"
  HISTORICAL_IMAGE="${HISTORICAL_IMAGE:-inodefence-node-tar-effect:$TAR_VERSION}"
  IF_HISTORICAL_IMAGE="$(dk image inspect "$HISTORICAL_IMAGE" --format '{{.Id}}')"
  DEMO_ARGS=()
  [ -n "${DEMO_POLICY:-}" ] && DEMO_ARGS+=(--policy "$DEMO_POLICY")
  [ -n "${DEMO_MUTATION_POLICY:-}" ] && DEMO_ARGS+=(--mutation-policy "$DEMO_MUTATION_POLICY")
  [ -n "${DEMO_SEED:-}" ] && DEMO_ARGS+=(--seed "$DEMO_SEED")
  [ -n "${DEMO_BUDGET:-}" ] && DEMO_ARGS+=(--budget "$DEMO_BUDGET")
  host --image "$IF_HISTORICAL_IMAGE" --tar-version "$TAR_VERSION" \
    --evidence "$CONTROLLER_EVIDENCE" ${DEMO_ARGS[@]+"${DEMO_ARGS[@]}"} effect-demo-historical
  exit 0
fi

if [ "$MODE" = demo ]; then
  step "effect-demo"
  DEMO_ARGS=()
  [ -n "${DEMO_POLICY:-}" ] && DEMO_ARGS+=(--policy "$DEMO_POLICY")
  [ -n "${DEMO_MUTATION_POLICY:-}" ] && DEMO_ARGS+=(--mutation-policy "$DEMO_MUTATION_POLICY")
  [ -n "${DEMO_SEED:-}" ] && DEMO_ARGS+=(--seed "$DEMO_SEED")
  [ -n "${DEMO_BUDGET:-}" ] && DEMO_ARGS+=(--budget "$DEMO_BUDGET")
  host --image "$IF_NODE_IMAGE" --evidence "$CONTROLLER_EVIDENCE" ${DEMO_ARGS[@]+"${DEMO_ARGS[@]}"} effect-demo
  exit 0
fi

if [ "$MODE" = effect ]; then
  step "validate-node-effect-producer"
  host --image "$IF_NODE_IMAGE" validate-node-effect-producer
  exit 0
fi

step "validate"
host --image "$IF_HELPER_IMAGE" validate
step "validate-node-image"
host --image "$IF_NODE_IMAGE" validate-node-image
step "validate-node-target"
host --image "$IF_NODE_IMAGE" validate-node-target
step "benign-node-smoke"
host --image "$IF_NODE_IMAGE" --evidence "$CONTROLLER_EVIDENCE" benign-node-smoke

#!/usr/bin/env bash
# python-tarfile exploration: the shared effect loop over ONE prepared python runtime image and
# ONE extraction filter, inside a disposable controller (exploratory demo run).
#
# Usage: EXPLORE_IMAGE=<prepared producer image> RUNTIME_VERSION=X.Y.Z EXTRACTION_FILTER=data \
#          scripts/local_python_tarfile_explore.sh
#   EXPLORE_IMAGE is the image scripts/python_tarfile_producer.py prepared and checked (official
#   python:X.Y.Z-slim + /target/worker.py); this script never builds or pulls it and stops if it is
#   missing. It builds only the controller/helper images, creates a trusted non-root controller,
#   and runs the `python-tarfile-effect-campaign` controller mode. The report and its per-step
#   journal are copied to the host.
#
# This mirrors scripts/local_decompress_selfdiscover.sh: the target runs only inside the controller
# through the production ContainerExecutionBackend (hardened isolation, NO isolation-relaxing
# flag); this host script only prepares the controller and delegates through scripts.container_host.
#
# Overrides: INODEFENCE_DOCKER_CONTEXT, PYTHON (default python3.12), INODEFENCE_EVIDENCE_DIR
# (default ~/inodefence-explore, outside the confirmatory-evidence tree), DEMO_SEED, DEMO_BUDGET,
# DEMO_POLICY, DEMO_MUTATION_POLICY, RUN_ID (unique suffix for controller/volume/evidence),
# SKIP_BUILD=1 (reuse controller/helper images).
set -euo pipefail

RUN_ID="${RUN_ID:-}"
SKIP_BUILD="${SKIP_BUILD:-}"
: "${EXPLORE_IMAGE:?set EXPLORE_IMAGE to the prepared python-tarfile producer image}"
: "${RUNTIME_VERSION:?set RUNTIME_VERSION to the exact python X.Y.Z inside EXPLORE_IMAGE}"
: "${EXTRACTION_FILTER:?set EXTRACTION_FILTER to one filter (data)}"
if [ -n "$RUN_ID" ] && ! [[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "RUN_ID must match [A-Za-z0-9][A-Za-z0-9_.-]* (got: $RUN_ID)" >&2
  exit 2
fi
if ! [[ "$RUNTIME_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "RUNTIME_VERSION must be exact X.Y.Z (got: $RUNTIME_VERSION)" >&2
  exit 2
fi
case "$EXTRACTION_FILTER" in
  data | fully_trusted) ;;
  *)
    echo "EXTRACTION_FILTER must be one of: data fully_trusted (got: $EXTRACTION_FILTER)" >&2
    exit 2
    ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found: python-tarfile exploration runs only from the host terminal." >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3.12}"
CONTEXT="${INODEFENCE_DOCKER_CONTEXT:-$(docker context show)}"
EVIDENCE_DIR="${INODEFENCE_EVIDENCE_DIR:-$HOME/inodefence-explore}"

CONTROLLER_IMAGE=inodefence-controller:local
HELPER_IMAGE=inodefence-helper:local
CONTROLLER="inodefence-python-tarfile-controller${RUN_ID:+-$RUN_ID}"
VOLUME="inodefence-python-tarfile-runtime${RUN_ID:+-$RUN_ID}"

STAMP="$(date +%Y%m%d-%H%M%S)"
LABEL="${RUN_ID:-$STAMP}"
CONTROLLER_EVIDENCE="/tmp/inodefence-python-tarfile-explore-$LABEL.json"
CONTROLLER_STEPS="/tmp/inodefence-python-tarfile-explore-$LABEL.steps.jsonl"
HOST_EVIDENCE="$EVIDENCE_DIR/target-explore/inodefence-python-tarfile-explore-$LABEL.json"
HOST_STEPS="$EVIDENCE_DIR/target-explore/inodefence-python-tarfile-explore-$LABEL.steps.jsonl"

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
  if [ "$CREATED_CONTROLLER" -eq 1 ]; then
    mkdir -p "$EVIDENCE_DIR/target-explore"
    for pair in "$CONTROLLER_EVIDENCE:$HOST_EVIDENCE" "$CONTROLLER_STEPS:$HOST_STEPS"; do
      src="${pair%%:*}"
      dst="${pair#*:}"
      if dk exec "$CONTROLLER" test -e "$src"; then
        if dk cp "$CONTROLLER:$src" "$dst" >/dev/null; then
          echo "evidence: $dst"
        else
          echo "evidence copy failed: $src" >&2
        fi
      fi
    done
    dk rm -f "$CONTROLLER" >/dev/null
  fi
  if [ "$CREATED_VOLUME" -eq 1 ]; then
    dk volume rm "$VOLUME" >/dev/null
  fi
  exit "$status"
}
trap cleanup EXIT

step "preflight"
echo "context=$CONTEXT engine=$(dk version --format '{{.Server.Version}}')"
command -v "$PYTHON" >/dev/null || { echo "host Python not found: $PYTHON" >&2; exit 1; }
IF_EXPLORE_IMAGE="$(dk image inspect "$EXPLORE_IMAGE" --format '{{.Id}}' 2>/dev/null)" || {
  echo "missing $EXPLORE_IMAGE; prepare it first (scripts/python_tarfile_producer.py)" >&2
  exit 1
}
if dk container inspect "$CONTROLLER" >/dev/null 2>&1 || dk volume inspect "$VOLUME" >/dev/null 2>&1; then
  echo "stale $CONTROLLER or $VOLUME exists; inspect and remove it manually:" >&2
  echo "  docker --context $CONTEXT rm -f $CONTROLLER; docker --context $CONTEXT volume rm $VOLUME" >&2
  exit 1
fi

if [ "$SKIP_BUILD" = 1 ]; then
  step "reuse controller/helper images"
else
  step "build controller/helper images"
  export BUILDX_NO_DEFAULT_ATTESTATIONS=1
  dk build --quiet -f "$REPO_ROOT/.devcontainer/Dockerfile" -t "$CONTROLLER_IMAGE" "$REPO_ROOT"
  dk build --quiet -f "$REPO_ROOT/tools/container-helper/Dockerfile" -t "$HELPER_IMAGE" "$REPO_ROOT"
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

step "python-tarfile-effect-campaign"
DEMO_ARGS=(--runtime-version "$RUNTIME_VERSION" --extraction-filter "$EXTRACTION_FILTER")
[ -n "${DEMO_SEED:-}" ] && DEMO_ARGS+=(--seed "$DEMO_SEED")
[ -n "${DEMO_BUDGET:-}" ] && DEMO_ARGS+=(--budget "$DEMO_BUDGET")
[ -n "${DEMO_MUTATION_POLICY:-}" ] && DEMO_ARGS+=(--mutation-policy "$DEMO_MUTATION_POLICY")
[ -n "${DEMO_POLICY:-}" ] && DEMO_ARGS+=(--policy "$DEMO_POLICY")
host --image "$IF_EXPLORE_IMAGE" --evidence "$CONTROLLER_EVIDENCE" \
  "${DEMO_ARGS[@]}" python-tarfile-effect-campaign

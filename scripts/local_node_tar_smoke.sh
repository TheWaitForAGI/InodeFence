#!/usr/bin/env bash
# Local replay of the CI container-integration job (.github/workflows/ci.yml).
#
# Usage: scripts/local_node_tar_smoke.sh [smoke|effect|demo|demo-historical|explore|replay]
#   smoke  (default) validate, validate-node-image, validate-node-target, benign-node-smoke
#   effect           validate-node-effect-producer
#   demo             effect-demo: feedback loop on real node-tar, JSON copied to the host
#                    (plus <name>.steps.jsonl: steps finished so far, kept even on abort)
#   demo-historical  effect-demo-historical: state-aware loop on a prebuilt frozen historical
#                    node-tar effect image (catalog pair 7.5.2/7.5.3), JSON copied to the host
#                    (plus <name>.steps.jsonl: steps finished so far, kept even on abort)
#   explore          effect-demo-explore: state-aware loop on an arbitrary prebuilt node-tar
#                    registry image (host-prepared out of band; TAR_VERSION = resolved version,
#                    EXPLORE_IMAGE default inodefence-node-tar-registry:$TAR_VERSION). Labelled
#                    an exploratory, non-qualification run; evidence under target-explore/.
#   replay           effect-replay-case: re-run ONE recorded case N times on the exact image it
#                    was explored on (REPLAY_IMAGE = sha256:... id, never built here; REPLAY_INPUT
#                    = absolute path of the one-line input from inodefence.case_replay). Requires
#                    INODEFENCE_EVIDENCE_DIR (never the confirmatory-evidence tree). Driven by
#                    `inodefence replay`; JSON + <name>.steps.jsonl (rounds so far) copied back.
#
# The real target runs only inside the trusted non-root Linux controller; this host
# script only builds images, prepares that controller and delegates through
# scripts.container_host. It removes only the controller/volume it created itself.
#
# Image IDs: BuildKit's default provenance/SBOM attestations carry build timestamps, so
# every rebuild (even fully cached) produced a new image ID and the demo report's image_id
# differed per run. Attestations are disabled here (BUILDX_NO_DEFAULT_ATTESTATIONS=1), so a
# rebuild from the same checkout on the same host/builder gives the same image ID. This is
# same-host determinism only, not a cross-platform bit-for-bit claim.
#
# Overrides: INODEFENCE_DOCKER_CONTEXT (default: `docker context show`),
# PYTHON (default: python3.12), INODEFENCE_EVIDENCE_DIR (default: ~/inodefence-evidence;
# explore mode defaults to ~/inodefence-explore, outside the confirmatory-evidence tree).
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
  smoke | effect | demo | demo-historical | explore | replay) ;;
  *)
    echo "usage: $0 [smoke|effect|demo|demo-historical|explore|replay]" >&2
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
# explore evidence must not land inside the confirmatory-evidence tree; its default is a
# separate folder (other modes keep ~/inodefence-evidence). An explicit
# INODEFENCE_EVIDENCE_DIR still wins for every mode.
if [ "$MODE" = explore ] && [ -z "${INODEFENCE_EVIDENCE_DIR:-}" ]; then
  EVIDENCE_DIR="$HOME/inodefence-explore"
fi

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
elif [ "$MODE" = explore ]; then
  CONTROLLER_EVIDENCE="/tmp/inodefence-effect-explore-$LABEL.json"
  HOST_EVIDENCE="$EVIDENCE_DIR/target-explore/inodefence-effect-explore-$LABEL.json"
elif [ "$MODE" = replay ]; then
  # A replay re-runs a possibly violating input: never default into ~/inodefence-evidence.
  : "${INODEFENCE_EVIDENCE_DIR:?replay requires INODEFENCE_EVIDENCE_DIR (outside the evidence tree)}"
  # Checked here, before any build or controller: the exact image and the input are required.
  : "${REPLAY_IMAGE:?set REPLAY_IMAGE to the exact image id (sha256:...) the case was explored on}"
  : "${REPLAY_INPUT:?set REPLAY_INPUT to the absolute path of the one-line replay input}"
  case "$REPLAY_INPUT" in
    /*) ;;
    *) echo "REPLAY_INPUT must be an absolute path (got: $REPLAY_INPUT)" >&2; exit 2 ;;
  esac
  CONTROLLER_EVIDENCE="/tmp/inodefence-case-replay-$LABEL.json"
  HOST_EVIDENCE="$EVIDENCE_DIR/inodefence-case-replay-$LABEL.json"
else
  CONTROLLER_EVIDENCE="/tmp/inodefence-node-smoke-$LABEL"
  HOST_EVIDENCE="$EVIDENCE_DIR/inodefence-node-smoke-$LABEL"
fi
# Written by the host broker, which runs from the repository root: keep it absolute.
case "$HOST_EVIDENCE" in
  /*) HOST_CALL_LOG="${HOST_EVIDENCE%.json}.calls.jsonl" ;;
  *) HOST_CALL_LOG="$PWD/${HOST_EVIDENCE%.json}.calls.jsonl" ;;
esac

STEP="setup"
CREATED_VOLUME=0
# Set before `volume create`: the CLI can fail after the daemon created the volume.
VOLUME_ATTEMPTED=0
CREATED_CONTROLLER=0
# Set before `docker run -d`: the CLI can fail after the daemon created the container.
CONTROLLER_ATTEMPTED=0
OWNER_TOKEN=""

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

# Engineering deadlines, in seconds: metadata/exec 30, evidence copy 300,
# removal 60. They bound client time, not the daemon's completion.
cleanup_dk() {
  local deadline="$1"
  shift
  "$PYTHON" "$REPO_ROOT/scripts/bounded_cleanup_command.py" "$deadline" \
    docker --context "$CONTEXT" "$@"
}

# Start gate (src/inodefence/execution/start_gate.py). A launcher that runs cells
# concurrently injects INODEFENCE_START_GATE_DIR/_CELL; without them these are
# no-ops. C = cleanup entered, U = resource state unknown (recorded before the
# marker is printed), S = cleanup verified. S is written only when no U was
# seen and every earlier record succeeded; anything else leaves no S, which the
# launcher reads as "do not start".
GATE_UNKNOWN=0
GATE_RECORD_FAILED=0
gate_record() {
  [ -n "${INODEFENCE_START_GATE_DIR:-}" ] || return 0
  if ! "$PYTHON" -I "$REPO_ROOT/src/inodefence/execution/start_gate.py" record "$@"; then
    GATE_RECORD_FAILED=1
    echo "start gate: $1 not recorded" >&2
  fi
}

# The marker is printed even when the record fails; a log with the marker
# therefore never precedes the U record when the record succeeds.
cleanup_unknown() {
  GATE_UNKNOWN=1
  gate_record U "$1"
  echo "INODEFENCE_CLEANUP_UNKNOWN: $1" >&2
}

# First act of cleanup, before any lock: an exclusive create the gate reads as C.
# It keeps other cells waiting even if both lock-based records (C, U) fail.
gate_mark_cleanup() {
  [ -n "${INODEFENCE_START_GATE_DIR:-}" ] || return 0
  if ! (set -C; : > "$INODEFENCE_START_GATE_DIR/$INODEFENCE_START_GATE_CELL.cleanup") 2>/dev/null; then
    GATE_RECORD_FAILED=1
    echo "start gate: cleanup marker not created" >&2
  fi
}

cleanup() {
  local status=$? rc inspection temporary source destination container_id label controller_owned=0
  set +e
  gate_mark_cleanup
  gate_record C
  if [ "$status" -ne 0 ]; then
    echo "FAILED at step: $STEP (exit $status)" >&2
  fi
  if [ "$CONTROLLER_ATTEMPTED" -eq 1 ] && [ "$CREATED_CONTROLLER" -eq 0 ]; then
    # The run did not report success. Absent is the expected outcome; a container
    # carrying this run's owner label was created anyway and is removed below;
    # anything else (another owner, an unanswered inspect) is unknown.
    inspection=$(cleanup_dk 30 container inspect --format \
      '{{.Id}} {{index .Config.Labels "org.inodefence.smoke-owner"}}' "$CONTROLLER" 2>&1)
    rc=$?
    read -r container_id label <<< "$inspection"
    if [ "$rc" -eq 0 ] && [ -n "$OWNER_TOKEN" ] && [ "$label" = "$OWNER_TOKEN" ] &&
       [[ "$container_id" =~ ^[0-9a-f]{64}$ ]]; then
      CREATED_CONTROLLER=1
    else
      case "$inspection" in
        "Error: No such object: $CONTROLLER"|"Error: No such container: $CONTROLLER"|"Error response from daemon: No such container: $CONTROLLER"|$'[]\n'"Error response from daemon: No such container: $CONTROLLER")
          [ "$rc" -eq 1 ] || cleanup_unknown "controller creation outcome: $inspection" ;;
        *) cleanup_unknown "controller creation outcome: $inspection" ;;
      esac
    fi
  fi
  if [ "$CREATED_CONTROLLER" -eq 1 ]; then
    inspection=$(cleanup_dk 30 container inspect --format \
      '{{.Id}} {{index .Config.Labels "org.inodefence.smoke-owner"}}' "$CONTROLLER" 2>&1)
    rc=$?
    read -r container_id label <<< "$inspection"
    if [ "$rc" -ne 0 ] || [ "$label" != "$OWNER_TOKEN" ] ||
       ! [[ "$container_id" =~ ^[0-9a-f]{64}$ ]]; then
      cleanup_unknown "controller ownership: $inspection"
      [ "$status" -ne 0 ] || status=125
    else
      controller_owned=1
    fi
  fi
  if [ "$controller_owned" -eq 1 ] && [ "$MODE" != effect ]; then
    for source in "$CONTROLLER_EVIDENCE" "${CONTROLLER_EVIDENCE%.json}.steps.jsonl"; do
      if [ "$source" != "$CONTROLLER_EVIDENCE" ] && [ "$MODE" != demo ] &&
         [ "$MODE" != demo-historical ] && [ "$MODE" != explore ] && [ "$MODE" != replay ]; then
        continue
      fi
      inspection=$(cleanup_dk 30 exec "$container_id" sh -c \
        'if test -e "$1"; then printf PRESENT; else printf ABSENT; fi' sh "$source")
      rc=$?
      if [ "$rc" -ne 0 ] || { [ "$inspection" != PRESENT ] && [ "$inspection" != ABSENT ]; }; then
        echo "FAILED cleanup evidence inspection: $source (exit $rc)" >&2
        [ "$rc" -ne 0 ] || rc=125
        [ "$status" -ne 0 ] || status=$rc
        continue
      fi
      [ "$inspection" = PRESENT ] || continue
      destination="$HOST_EVIDENCE"
      [ "$source" = "$CONTROLLER_EVIDENCE" ] || destination="${HOST_EVIDENCE%.json}.steps.jsonl"
      if ! mkdir -p "$EVIDENCE_DIR"; then
        [ "$status" -ne 0 ] || status=125
        continue
      fi
      temporary=$(mktemp "$EVIDENCE_DIR/.inodefence-copy.XXXXXXXX")
      rc=$?
      if [ "$rc" -ne 0 ]; then
        [ "$status" -ne 0 ] || status=$rc
        continue
      fi
      cleanup_dk 300 cp "$container_id:$source" "$temporary" >/dev/null
      rc=$?
      if [ "$rc" -eq 0 ]; then
        ln "$temporary" "$destination"
        rc=$?
      fi
      rm -f "$temporary"
      if [ "$rc" -ne 0 ]; then
        echo "FAILED cleanup evidence copy: $source (exit $rc)" >&2
        [ "$status" -ne 0 ] || status=$rc
      else
        echo "evidence: $destination"
      fi
    done
  fi
  if [ "$CREATED_CONTROLLER" -eq 1 ]; then
    if [ "$controller_owned" -eq 1 ]; then
      cleanup_dk 60 rm -f "$container_id" >/dev/null
      rc=$?
      if [ "$rc" -ne 0 ]; then
        echo "FAILED cleanup: controller $CONTROLLER (exit $rc)" >&2
        [ "$status" -ne 0 ] || status=$rc
      fi
    fi
    inspection=$(cleanup_dk 30 container inspect "$CONTROLLER" 2>&1)
    rc=$?
    case "$inspection" in
      "Error: No such object: $CONTROLLER"|"Error: No such container: $CONTROLLER"|"Error response from daemon: No such container: $CONTROLLER"|$'[]\n'"Error response from daemon: No such container: $CONTROLLER")
        [ "$rc" -eq 1 ] || rc=125 ;;
      *) rc=125 ;;
    esac
    if [ "$rc" -ne 1 ]; then
      cleanup_unknown "controller $CONTROLLER: $inspection"
      [ "$status" -ne 0 ] || status=125
    fi
  fi
  if [ "$VOLUME_ATTEMPTED" -eq 1 ] && [ "$CREATED_VOLUME" -eq 0 ]; then
    # The create did not report success. Absent is the expected outcome; a volume
    # carrying this run's owner label was created anyway and is removed below;
    # anything else (another owner, an unanswered inspect) is unknown.
    inspection=$(cleanup_dk 30 volume inspect --format \
      '{{index .Labels "org.inodefence.smoke-owner"}}' "$VOLUME" 2>&1)
    rc=$?
    if [ "$rc" -eq 0 ] && [ -n "$OWNER_TOKEN" ] && [ "$inspection" = "$OWNER_TOKEN" ]; then
      CREATED_VOLUME=1
    else
      case "$inspection" in
        "Error: No such volume: $VOLUME"|"Error: No such object: $VOLUME"|"Error response from daemon: get $VOLUME: no such volume"|$'[]\n'"Error response from daemon: get $VOLUME: no such volume")
          [ "$rc" -eq 1 ] || cleanup_unknown "volume creation outcome: $inspection" ;;
        *) cleanup_unknown "volume creation outcome: $inspection" ;;
      esac
    fi
  fi
  if [ "$CREATED_VOLUME" -eq 1 ]; then
    inspection=$(cleanup_dk 30 volume inspect --format \
      '{{index .Labels "org.inodefence.smoke-owner"}}' "$VOLUME" 2>&1)
    rc=$?
    if [ "$rc" -ne 0 ] || [ "$inspection" != "$OWNER_TOKEN" ]; then
      cleanup_unknown "volume ownership: $inspection"
      [ "$status" -ne 0 ] || status=125
    else
      cleanup_dk 60 volume rm "$VOLUME" >/dev/null
      rc=$?
      if [ "$rc" -ne 0 ]; then
        echo "FAILED cleanup: volume $VOLUME (exit $rc)" >&2
        [ "$status" -ne 0 ] || status=$rc
      fi
    fi
    inspection=$(cleanup_dk 30 volume inspect "$VOLUME" 2>&1)
    rc=$?
    case "$inspection" in
      "Error: No such volume: $VOLUME"|"Error: No such object: $VOLUME"|"Error response from daemon: get $VOLUME: no such volume"|$'[]\n'"Error response from daemon: get $VOLUME: no such volume")
        [ "$rc" -eq 1 ] || rc=125 ;;
      *) rc=125 ;;
    esac
    if [ "$rc" -ne 1 ]; then
      cleanup_unknown "volume $VOLUME: $inspection"
      [ "$status" -ne 0 ] || status=125
    fi
  fi
  if [ "$GATE_UNKNOWN" -eq 0 ] && [ "$GATE_RECORD_FAILED" -eq 0 ]; then
    gate_record S
  fi
  if [ "$GATE_RECORD_FAILED" -ne 0 ] && [ "$status" -eq 0 ]; then
    status=125
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
  # No provenance/SBOM attestation manifests: same checkout + same builder => same image ID.
  export BUILDX_NO_DEFAULT_ATTESTATIONS=1
  BUILD_FLAGS=(--quiet)
  [ "${VERBOSE:-0}" = 1 ] && BUILD_FLAGS=()
  dk build "${BUILD_FLAGS[@]}" -f "$REPO_ROOT/.devcontainer/Dockerfile" -t "$CONTROLLER_IMAGE" "$REPO_ROOT"
  dk build "${BUILD_FLAGS[@]}" -f "$REPO_ROOT/tools/container-helper/Dockerfile" -t "$HELPER_IMAGE" "$REPO_ROOT"
  # The historical effect image is prebuilt and frozen out of band; never build it here.
  if [ "$MODE" != demo-historical ] && [ "$MODE" != explore ] && [ "$MODE" != replay ]; then
    dk build "${BUILD_FLAGS[@]}" -f "$REPO_ROOT/tools/node-tar/Dockerfile" -t "$NODE_IMAGE" "$REPO_ROOT"
  fi
fi

if [ "$BUILD_ONLY" = 1 ]; then
  echo "BUILD_ONLY=1: shared images ready (context=$CONTEXT mode=$MODE); no controller created"
  exit 0
fi

step "prepare controller"
OWNER_TOKEN="$("$PYTHON" -c 'import secrets; print(secrets.token_hex(16))')"
VOLUME_ATTEMPTED=1
dk volume create --label "org.inodefence.smoke-owner=$OWNER_TOKEN" "$VOLUME" >/dev/null
CREATED_VOLUME=1
volume_owner="$(cleanup_dk 30 volume inspect --format \
  '{{index .Labels "org.inodefence.smoke-owner"}}' "$VOLUME")" || volume_owner=""
if [ "$volume_owner" != "$OWNER_TOKEN" ] || [ -z "$OWNER_TOKEN" ]; then
  cleanup_unknown "volume creation ownership could not be verified"
  exit 1
fi
CONTROLLER_ATTEMPTED=1
dk run -d --name "$CONTROLLER" --label "org.inodefence.smoke-owner=$OWNER_TOKEN" \
  --user vscode --workdir /workspaces/InodeFence \
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
if [ "$MODE" != demo-historical ] && [ "$MODE" != explore ] && [ "$MODE" != replay ]; then
  IF_NODE_IMAGE="$(dk image inspect "$NODE_IMAGE" --format '{{.Id}}')"
fi

if [ "$MODE" = explore ]; then
  step "effect-demo-explore"
  : "${TAR_VERSION:?set TAR_VERSION to the resolved node-tar version of the prepared image}"
  EXPLORE_IMAGE="${EXPLORE_IMAGE:-inodefence-node-tar-registry:$TAR_VERSION}"
  IF_EXPLORE_IMAGE="$(dk image inspect "$EXPLORE_IMAGE" --format '{{.Id}}')"
  DEMO_ARGS=()
  [ -n "${DEMO_POLICY:-}" ] && DEMO_ARGS+=(--policy "$DEMO_POLICY")
  [ -n "${DEMO_MUTATION_POLICY:-}" ] && DEMO_ARGS+=(--mutation-policy "$DEMO_MUTATION_POLICY")
  [ -n "${DEMO_SEED:-}" ] && DEMO_ARGS+=(--seed "$DEMO_SEED")
  [ -n "${DEMO_BUDGET:-}" ] && DEMO_ARGS+=(--budget "$DEMO_BUDGET")
  [ -n "${DEMO_SENTINEL_COUNT:-}" ] && DEMO_ARGS+=(--sentinel-count "$DEMO_SENTINEL_COUNT")
  [ -n "${DEMO_SENTINEL_SEED:-}" ] && DEMO_ARGS+=(--sentinel-seed "$DEMO_SENTINEL_SEED")
  [ -n "${DEMO_OBSERVER_INTEGRITY_POLICY:-}" ] &&
    DEMO_ARGS+=(--observer-integrity-policy "$DEMO_OBSERVER_INTEGRITY_POLICY")
  # Explore only: the controller writes live progress/violation snapshots here (tmpfs, writable
  # under the read-only root); the host pulls this folder with docker cp while the loop runs.
  [ -n "${DEMO_LIVE_DIR:-}" ] && DEMO_ARGS+=(--live-dir "$DEMO_LIVE_DIR")
  [ -n "${DEMO_ENGINE_COMMIT:-}" ] && DEMO_ARGS+=(--engine-commit "$DEMO_ENGINE_COMMIT")
  host --image "$IF_EXPLORE_IMAGE" --tar-version "$TAR_VERSION" --call-log "$HOST_CALL_LOG" \
    --evidence "$CONTROLLER_EVIDENCE" ${DEMO_ARGS[@]+"${DEMO_ARGS[@]}"} effect-demo-explore
  exit 0
fi

if [ "$MODE" = replay ]; then
  step "effect-replay-case"
  # The exact image only: a tag or another id would not be the same conditions.
  IF_REPLAY_IMAGE="$(dk image inspect "$REPLAY_IMAGE" --format '{{.Id}}')"
  if [ "$IF_REPLAY_IMAGE" != "$REPLAY_IMAGE" ]; then
    echo "REPLAY_IMAGE $REPLAY_IMAGE resolves to $IF_REPLAY_IMAGE, not the same image id" >&2
    exit 2
  fi
  host --image "$IF_REPLAY_IMAGE" --replay-input "$REPLAY_INPUT" \
    --evidence "$CONTROLLER_EVIDENCE" effect-replay-case
  exit 0
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
  [ -n "${DEMO_SENTINEL_COUNT:-}" ] && DEMO_ARGS+=(--sentinel-count "$DEMO_SENTINEL_COUNT")
  [ -n "${DEMO_SENTINEL_SEED:-}" ] && DEMO_ARGS+=(--sentinel-seed "$DEMO_SENTINEL_SEED")
  [ -n "${DEMO_OBSERVER_INTEGRITY_POLICY:-}" ] &&
    DEMO_ARGS+=(--observer-integrity-policy "$DEMO_OBSERVER_INTEGRITY_POLICY")
  host --image "$IF_HISTORICAL_IMAGE" --tar-version "$TAR_VERSION" --call-log "$HOST_CALL_LOG" \
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
  [ -n "${DEMO_SENTINEL_COUNT:-}" ] && DEMO_ARGS+=(--sentinel-count "$DEMO_SENTINEL_COUNT")
  [ -n "${DEMO_SENTINEL_SEED:-}" ] && DEMO_ARGS+=(--sentinel-seed "$DEMO_SENTINEL_SEED")
  [ -n "${DEMO_OBSERVER_INTEGRITY_POLICY:-}" ] &&
    DEMO_ARGS+=(--observer-integrity-policy "$DEMO_OBSERVER_INTEGRITY_POLICY")
  host --image "$IF_NODE_IMAGE" --call-log "$HOST_CALL_LOG" --evidence "$CONTROLLER_EVIDENCE" \
    ${DEMO_ARGS[@]+"${DEMO_ARGS[@]}"} effect-demo
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

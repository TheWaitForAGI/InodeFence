# shellcheck shell=bash
# Bounded Docker calls and owned cleanup for the python-tarfile, decompress and oras-go controller
# launchers (D049 release condition 3). Sourced, never executed.
#
# This is the node-tar launcher's cleanup rule (scripts/local_node_tar_smoke.sh `cleanup_dk` and
# `cleanup`), without its start gate (concurrent registered cells only):
#
# * every host Docker daemon call except the campaign itself (and the local, daemon-free
#   `docker context show` the launcher runs before sourcing this) has a client deadline, through
#   scripts/bounded_cleanup_command.py (called unchanged: on a deadline it kills the CLI's process
#   group and returns 124; a CLI that cannot start returns 125). A deadline bounds the client, not
#   the daemon's completion;
# * the volume and the controller carry this run's owner label, and cleanup removes only a
#   resource that still carries it;
# * a cleanup that fails, times out or cannot confirm the resource is gone prints
#   `FAILED cleanup: ...` or `INODEFENCE_CLEANUP_UNKNOWN: ...` and turns a successful run's exit
#   status into 125. A run that already failed keeps its own status.
#
# The controller's isolation (user, workdir, environment, the two mounts, image, command) is the
# caller's, unchanged; this file only adds the owner label and the deadlines.
#
# The caller sets before sourcing: REPO_ROOT, PYTHON, CONTEXT, CONTROLLER, VOLUME; and defines
# `step` (setting STEP). It then calls `launcher_cleanup <status> <src>:<dst>...` from its EXIT
# trap and exits with LAUNCHER_STATUS.

LAUNCHER_OWNER_LABEL="org.inodefence.launcher-owner"
OWNER_TOKEN=""
# Set before the create call: the CLI can fail after the daemon created the resource.
VOLUME_ATTEMPTED=0
CREATED_VOLUME=0
CONTROLLER_ATTEMPTED=0
CREATED_CONTROLLER=0
LAUNCHER_STATUS=0

# Engineering deadlines, in seconds (D049 condition 3; cleanup values are node-tar's).
DEADLINE_QUERY=30     # version, inspect, exec test
DEADLINE_EXEC=60      # exec chown / git config
DEADLINE_PIP=300      # exec pip install (network)
DEADLINE_CREATE=60    # volume create, run -d
DEADLINE_BUILD=1800   # image build
DEADLINE_COPY=300     # evidence copy
DEADLINE_REMOVE=60    # rm -f, volume rm

# bdk <deadline> <docker args...>: one Docker CLI call with a client deadline.
bdk() {
  local deadline="$1"
  shift
  "$PYTHON" "$REPO_ROOT/scripts/bounded_cleanup_command.py" "$deadline" \
    docker --context "$CONTEXT" "$@"
}

cleanup_unknown() {
  echo "INODEFENCE_CLEANUP_UNKNOWN: $1" >&2
}

# A failed cleanup step turns a successful run into 125; a failed run keeps its status.
cleanup_failed() {
  [ "$LAUNCHER_STATUS" -ne 0 ] || LAUNCHER_STATUS=125
}

launcher_new_owner_token() {
  OWNER_TOKEN="$("$PYTHON" -c 'import secrets; print(secrets.token_hex(16))')"
}

launcher_create_volume() {
  VOLUME_ATTEMPTED=1
  bdk "$DEADLINE_CREATE" volume create --label "$LAUNCHER_OWNER_LABEL=$OWNER_TOKEN" "$VOLUME" >/dev/null
  CREATED_VOLUME=1
}

# launcher_run_controller <docker run arguments after the name and label...>
launcher_run_controller() {
  CONTROLLER_ATTEMPTED=1
  bdk "$DEADLINE_CREATE" run -d --name "$CONTROLLER" --label "$LAUNCHER_OWNER_LABEL=$OWNER_TOKEN" \
    "$@" >/dev/null
  CREATED_CONTROLLER=1
}

_no_such_container() {
  case "$1" in
    "Error: No such object: $CONTROLLER" | "Error: No such container: $CONTROLLER" | \
      "Error response from daemon: No such container: $CONTROLLER" | \
      $'[]\n'"Error response from daemon: No such container: $CONTROLLER")
      return 0 ;;
  esac
  return 1
}

_no_such_volume() {
  case "$1" in
    "Error: No such volume: $VOLUME" | "Error: No such object: $VOLUME" | \
      "Error response from daemon: get $VOLUME: no such volume" | \
      $'[]\n'"Error response from daemon: get $VOLUME: no such volume")
      return 0 ;;
  esac
  return 1
}

# launcher_cleanup <status> [<controller path>:<host path>]...
# Copies the named evidence out of an owned controller, removes the owned controller and volume,
# confirms both are gone and leaves the final exit status in LAUNCHER_STATUS.
launcher_cleanup() {
  local rc inspection container_id label controller_owned=0 pair source destination temporary
  LAUNCHER_STATUS="$1"
  shift
  if [ "$LAUNCHER_STATUS" -ne 0 ]; then
    echo "FAILED at step: $STEP (exit $LAUNCHER_STATUS)" >&2
  fi

  if [ "$CONTROLLER_ATTEMPTED" -eq 1 ] && [ "$CREATED_CONTROLLER" -eq 0 ]; then
    # The run did not report success: absent is expected; one carrying this run's label was
    # created anyway and is removed below; anything else is unknown.
    inspection=$(bdk "$DEADLINE_QUERY" container inspect --format \
      "{{.Id}} {{index .Config.Labels \"$LAUNCHER_OWNER_LABEL\"}}" "$CONTROLLER" 2>&1)
    rc=$?
    read -r container_id label <<< "$inspection"
    if [ "$rc" -eq 0 ] && [ -n "$OWNER_TOKEN" ] && [ "$label" = "$OWNER_TOKEN" ] &&
      [[ "$container_id" =~ ^[0-9a-f]{64}$ ]]; then
      CREATED_CONTROLLER=1
    elif ! { [ "$rc" -eq 1 ] && _no_such_container "$inspection"; }; then
      cleanup_unknown "controller creation outcome: $inspection"
      cleanup_failed
    fi
  fi

  if [ "$CREATED_CONTROLLER" -eq 1 ]; then
    inspection=$(bdk "$DEADLINE_QUERY" container inspect --format \
      "{{.Id}} {{index .Config.Labels \"$LAUNCHER_OWNER_LABEL\"}}" "$CONTROLLER" 2>&1)
    rc=$?
    read -r container_id label <<< "$inspection"
    if [ "$rc" -ne 0 ] || [ "$label" != "$OWNER_TOKEN" ] ||
      ! [[ "$container_id" =~ ^[0-9a-f]{64}$ ]]; then
      cleanup_unknown "controller ownership: $inspection"
      cleanup_failed
    else
      controller_owned=1
    fi
  fi

  if [ "$controller_owned" -eq 1 ]; then
    for pair in "$@"; do
      source="${pair%%:*}"
      destination="${pair#*:}"
      inspection=$(bdk "$DEADLINE_QUERY" exec "$container_id" sh -c \
        'if test -e "$1"; then printf PRESENT; else printf ABSENT; fi' sh "$source")
      rc=$?
      if [ "$rc" -ne 0 ] || { [ "$inspection" != PRESENT ] && [ "$inspection" != ABSENT ]; }; then
        echo "FAILED cleanup evidence inspection: $source (exit $rc)" >&2
        cleanup_failed
        continue
      fi
      [ "$inspection" = PRESENT ] || continue
      if ! mkdir -p "$(dirname "$destination")" ||
        ! temporary=$(mktemp "$(dirname "$destination")/.inodefence-copy.XXXXXXXX"); then
        echo "FAILED cleanup evidence copy: $source (no host folder)" >&2
        cleanup_failed
        continue
      fi
      bdk "$DEADLINE_COPY" cp "$container_id:$source" "$temporary" >/dev/null
      rc=$?
      if [ "$rc" -eq 0 ]; then
        # Publish without replacing an existing file: a hard link from the temporary file in the
        # same folder; where the filesystem has no hard links, a no-clobber rename instead.
        if [ -e "$destination" ]; then
          echo "evidence destination already exists: $destination" >&2
          rc=1
        elif ! ln "$temporary" "$destination" 2>/dev/null; then
          mv -n "$temporary" "$destination" && [ ! -e "$temporary" ]
          rc=$?
        fi
      fi
      rm -f "$temporary"
      if [ "$rc" -ne 0 ]; then
        echo "FAILED cleanup evidence copy: $source (exit $rc)" >&2
        cleanup_failed
      else
        echo "evidence: $destination"
      fi
    done
  fi

  if [ "$CREATED_CONTROLLER" -eq 1 ]; then
    if [ "$controller_owned" -eq 1 ]; then
      bdk "$DEADLINE_REMOVE" rm -f "$container_id" >/dev/null
      rc=$?
      if [ "$rc" -ne 0 ]; then
        echo "FAILED cleanup: controller $CONTROLLER (exit $rc)" >&2
        cleanup_failed
      fi
    fi
    inspection=$(bdk "$DEADLINE_QUERY" container inspect "$CONTROLLER" 2>&1)
    rc=$?
    if ! { [ "$rc" -eq 1 ] && _no_such_container "$inspection"; }; then
      cleanup_unknown "controller $CONTROLLER: $inspection"
      cleanup_failed
    fi
  fi

  if [ "$VOLUME_ATTEMPTED" -eq 1 ] && [ "$CREATED_VOLUME" -eq 0 ]; then
    inspection=$(bdk "$DEADLINE_QUERY" volume inspect --format \
      "{{index .Labels \"$LAUNCHER_OWNER_LABEL\"}}" "$VOLUME" 2>&1)
    rc=$?
    if [ "$rc" -eq 0 ] && [ -n "$OWNER_TOKEN" ] && [ "$inspection" = "$OWNER_TOKEN" ]; then
      CREATED_VOLUME=1
    elif ! { [ "$rc" -eq 1 ] && _no_such_volume "$inspection"; }; then
      cleanup_unknown "volume creation outcome: $inspection"
      cleanup_failed
    fi
  fi

  if [ "$CREATED_VOLUME" -eq 1 ]; then
    inspection=$(bdk "$DEADLINE_QUERY" volume inspect --format \
      "{{index .Labels \"$LAUNCHER_OWNER_LABEL\"}}" "$VOLUME" 2>&1)
    rc=$?
    if [ "$rc" -ne 0 ] || [ "$inspection" != "$OWNER_TOKEN" ]; then
      cleanup_unknown "volume ownership: $inspection"
      cleanup_failed
    else
      bdk "$DEADLINE_REMOVE" volume rm "$VOLUME" >/dev/null
      rc=$?
      if [ "$rc" -ne 0 ]; then
        echo "FAILED cleanup: volume $VOLUME (exit $rc)" >&2
        cleanup_failed
      fi
    fi
    inspection=$(bdk "$DEADLINE_QUERY" volume inspect "$VOLUME" 2>&1)
    rc=$?
    if ! { [ "$rc" -eq 1 ] && _no_such_volume "$inspection"; }; then
      cleanup_unknown "volume $VOLUME: $inspection"
      cleanup_failed
    fi
  fi
}

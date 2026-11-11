"""Host-only guard of scripts/local_node_tar_smoke.sh (make demo, node-tar-smoke)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "local_node_tar_smoke.sh"


def run_without_docker(
    mode: str, tmp_path: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    # An empty PATH hides docker even on CI runners that have it installed.
    env = {"PATH": str(tmp_path), **(extra_env or {})}
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), mode],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_demo_without_docker_points_to_host_and_synthetic_demo(tmp_path: Path) -> None:
    result = run_without_docker("demo", tmp_path)

    assert result.returncode == 2
    assert "host terminal" in result.stderr
    assert "make demo-synthetic" in result.stderr
    assert "FAILED at step" not in result.stderr


@pytest.mark.parametrize("mode", ("smoke", "effect"))
def test_other_modes_without_docker_point_to_host_only(mode: str, tmp_path: Path) -> None:
    result = run_without_docker(mode, tmp_path)

    assert result.returncode == 2
    assert "host terminal" in result.stderr
    assert "demo-synthetic" not in result.stderr


def test_invalid_run_id_is_rejected_early(tmp_path: Path) -> None:
    result = run_without_docker("demo", tmp_path, {"RUN_ID": "bad id!"})

    assert result.returncode == 2
    assert "RUN_ID must match" in result.stderr
    assert "host terminal" not in result.stderr  # rejected before the docker check


def test_skip_build_and_build_only_conflict(tmp_path: Path) -> None:
    result = run_without_docker("demo", tmp_path, {"SKIP_BUILD": "1", "BUILD_ONLY": "1"})

    assert result.returncode == 2
    assert "mutually exclusive" in result.stderr


def test_valid_run_id_still_reaches_host_guidance(tmp_path: Path) -> None:
    result = run_without_docker("demo", tmp_path, {"RUN_ID": "7.5.2-default-s123"})

    assert result.returncode == 2
    assert "host terminal" in result.stderr  # a valid RUN_ID does not short-circuit the flow


@pytest.mark.parametrize(
    ("controller_error", "volume_error", "host_error", "expected"),
    [
        (0, 0, 0, 0),
        (41, 0, 0, 41),
        (0, 42, 0, 42),
        (41, 42, 0, 41),
        (0, 0, 37, 37),
        (41, 42, 37, 37),
    ],
)
def test_cleanup_reports_failures(
    tmp_path: Path, controller_error: int, volume_error: int, host_error: int, expected: int
) -> None:
    result, calls = run_fake_docker(tmp_path, controller_error, volume_error, host_error)
    assert result.returncode == expected, (result.stdout, result.stderr)
    assert ("PASSED:" in result.stdout) == (expected == 0)
    assert f"rm -f {'a' * 64}" in calls
    assert "volume rm inodefence-local-runtime-test" in calls
    if host_error:
        assert "FAILED at step: effect-demo (exit 37)" in result.stderr
    if controller_error:
        assert "controller" in result.stderr and "41" in result.stderr
    if volume_error:
        assert "volume" in result.stderr and "42" in result.stderr


def run_fake_docker(
    tmp_path: Path,
    controller_error: int = 0,
    volume_error: int = 0,
    host_error: int = 0,
    create_error: str = "",
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Execute the complete host script with a closed PATH and inert executables."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("dirname", "date", "rm", "mkdir", "mktemp", "ln"):
        (bin_dir / name).symlink_to(Path("/usr/bin") / name)
    docker = bin_dir / "docker"
    docker.write_text("""#!/bin/bash
[ "$1" = --context ] || exit 99
shift 2
if { [ "$TIMEOUT_OPERATION" = "$1 $2" ] || [ "$TIMEOUT_OPERATION" = "$1" ]; } &&
   { [ "$1" != exec ] || [ "$3" = sh ]; }; then
  exit 124
fi
printf '%s\\n' "$*" >> "$FAKE_LOG"
case "$1 $2" in
  "container inspect")
    [ "$INSPECT_UNKNOWN" != 1 ] || { echo daemon-unreachable >&2; exit 1; }
    [ "$CONTAINER_ABSENT" != 1 ] || { echo "Error: No such object: ${!#}" >&2; exit 1; }
    if [ "$3" = --format ]; then
      printf '%064d %s\n' 0 "$CONTAINER_OWNER" | /usr/bin/tr 0 a; exit 0
    fi
    echo "Error: No such object: $3" >&2; exit 1 ;;
  "volume inspect")
    [ "$INSPECT_UNKNOWN" != 1 ] || { echo daemon-unreachable >&2; exit 1; }
    [ "$VOLUME_ABSENT" != 1 ] || { echo "Error: No such volume: ${!#}" >&2; exit 1; }
    if [ "$3" = --format ]; then printf '%s\n' "$VOLUME_OWNER"; exit 0; fi
    echo "Error: No such volume: $3" >&2; exit 1 ;;
  "volume create") [ "$CREATE_ERROR" != volume ] || exit 43 ;;
  "run -d") [ "$CREATE_ERROR" != controller ] || exit 44 ;;
  "exec "*) if [ "$EVIDENCE_PRESENT" = 1 ]; then printf PRESENT; else printf ABSENT; fi; exit 0 ;;
  "cp "*) [ "$COPY_ERROR" = 0 ] || exit "$COPY_ERROR"; printf evidence > "$3" ;;
  "rm -f") exit "$CONTROLLER_ERROR" ;;
  "volume rm") exit "$VOLUME_ERROR" ;;
esac
exit 0
""")
    docker.chmod(0o755)
    python = bin_dir / "fake-python"
    python.write_text(
        '#!/bin/bash\ncase "$1" in -c) echo test-owner; exit 0;; '
        '*/bounded_cleanup_command.py) exec /usr/bin/python3 "$@";; '
        '-I) echo "GATE RECORD ${*:4}" >&2; exec /usr/bin/python3 "$@";; '
        'esac\nexit "$HOST_ERROR"\n'
    )
    python.chmod(0o755)
    log = tmp_path / "calls"
    env = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path),
        "FAKE_LOG": str(log),
        "INODEFENCE_DOCKER_CONTEXT": "fake",
        "INODEFENCE_EVIDENCE_DIR": str(tmp_path),
        "PYTHON": str(python),
        "SKIP_BUILD": "1",
        "RUN_ID": "test",
        "CONTROLLER_ERROR": str(controller_error),
        "VOLUME_ERROR": str(volume_error),
        "HOST_ERROR": str(host_error),
        "CREATE_ERROR": create_error,
        "INSPECT_UNKNOWN": "0",
        "EVIDENCE_PRESENT": "0",
        "COPY_ERROR": "0",
        "CONTAINER_OWNER": "test-owner",
        "VOLUME_OWNER": "test-owner",
        "VOLUME_ABSENT": "0",
        "CONTAINER_ABSENT": "0",
        "TIMEOUT_OPERATION": "",
        **(extra_env or {}),
    }
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), "demo"], env=env, text=True, capture_output=True, check=False
    )
    return result, log.read_text().splitlines()


def test_cleanup_unknown_fails_closed(tmp_path: Path) -> None:
    result, _ = run_fake_docker(tmp_path, extra_env={"INSPECT_UNKNOWN": "1"})
    assert result.returncode != 0
    assert "INODEFENCE_CLEANUP_UNKNOWN" in result.stderr
    assert "PASSED:" not in result.stdout


def test_existing_volume_with_different_owner_is_never_used_or_removed(tmp_path: Path) -> None:
    result, calls = run_fake_docker(tmp_path, extra_env={"VOLUME_OWNER": "other-owner"})
    assert result.returncode != 0
    assert "INODEFENCE_CLEANUP_UNKNOWN" in result.stderr
    assert not any(call.startswith(("run -d", "volume rm")) for call in calls)
    assert sum(call.startswith("volume inspect ") for call in calls) >= 3


def test_replaced_controller_is_not_removed(tmp_path: Path) -> None:
    result, calls = run_fake_docker(tmp_path, extra_env={"CONTAINER_OWNER": "other-owner"})
    assert result.returncode != 0
    assert "INODEFENCE_CLEANUP_UNKNOWN: controller ownership" in result.stderr
    assert not any(call.startswith(("rm -f ", "cp ")) for call in calls)


@pytest.mark.parametrize("operation", ["exec", "cp", "rm -f", "volume rm"])
def test_cleanup_cli_timeout_never_reports_success(tmp_path: Path, operation: str) -> None:
    result, _ = run_fake_docker(
        tmp_path, extra_env={"TIMEOUT_OPERATION": operation, "EVIDENCE_PRESENT": "1"}
    )
    assert result.returncode == 124
    assert "PASSED:" not in result.stdout


def test_copy_failure_preserves_original_exit(tmp_path: Path) -> None:
    result, _ = run_fake_docker(
        tmp_path, host_error=37, extra_env={"EVIDENCE_PRESENT": "1", "COPY_ERROR": "42"}
    )
    assert result.returncode == 37
    assert "FAILED cleanup evidence copy" in result.stderr


def test_copy_never_replaces_existing_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "inodefence-effect-demo-native-test.json"
    evidence.write_text("existing")
    result, _ = run_fake_docker(tmp_path, extra_env={"EVIDENCE_PRESENT": "1"})
    assert result.returncode != 0
    assert evidence.read_text() == "existing"


@pytest.mark.parametrize(
    ("failure", "expected", "removals", "env"),
    [
        # A failed create that the daemon did not perform: nothing to remove.
        ("volume", 43, [], {"VOLUME_ABSENT": "1"}),
        ("controller", 44, ["volume rm inodefence-local-runtime-test"], {"CONTAINER_ABSENT": "1"}),
    ],
)
def test_cleanup_only_removes_created_resources(
    tmp_path: Path, failure: str, expected: int, removals: list[str], env: dict[str, str]
) -> None:
    result, calls = run_fake_docker(tmp_path, create_error=failure, extra_env=env)
    assert result.returncode == expected
    assert [call for call in calls if call.startswith(("rm -f ", "volume rm "))] == removals
    assert "INODEFENCE_CLEANUP_UNKNOWN" not in result.stderr


def test_failed_volume_create_that_the_daemon_performed_is_removed(tmp_path: Path) -> None:
    # The CLI reported failure, but a volume with this run's owner label exists.
    result, calls = run_fake_docker(tmp_path, create_error="volume")
    assert result.returncode == 43
    assert "volume rm inodefence-local-runtime-test" in calls
    assert "INODEFENCE_CLEANUP_UNKNOWN" not in result.stderr


def test_failed_volume_create_with_a_foreign_owner_is_unknown_and_kept(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    gate.mkdir()
    result, calls = run_fake_docker(
        tmp_path, create_error="volume", extra_env={"VOLUME_OWNER": "other", **gate_env(gate)}
    )
    assert result.returncode == 43
    assert "volume rm inodefence-local-runtime-test" not in calls
    assert "INODEFENCE_CLEANUP_UNKNOWN: volume creation outcome: other" in result.stderr
    assert (gate / "cell.verdict").read_text().startswith("U volume creation outcome")


def test_failed_volume_create_with_unanswered_inspect_is_unknown(tmp_path: Path) -> None:
    result, calls = run_fake_docker(
        tmp_path, create_error="volume", extra_env={"INSPECT_UNKNOWN": "1"}
    )
    assert result.returncode == 43
    assert "volume rm inodefence-local-runtime-test" not in calls
    assert "INODEFENCE_CLEANUP_UNKNOWN: volume creation outcome: daemon-unreachable" in (
        result.stderr
    )


def test_failed_controller_run_that_the_daemon_performed_is_removed(tmp_path: Path) -> None:
    # `docker run -d` reported failure, but a container with this run's label exists.
    result, calls = run_fake_docker(tmp_path, create_error="controller")
    assert result.returncode == 44
    assert f"rm -f {'a' * 64}" in calls
    assert "volume rm inodefence-local-runtime-test" in calls
    assert "INODEFENCE_CLEANUP_UNKNOWN" not in result.stderr


def test_failed_controller_run_with_a_foreign_owner_is_unknown_and_kept(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    gate.mkdir()
    result, calls = run_fake_docker(
        tmp_path,
        create_error="controller",
        extra_env={"CONTAINER_OWNER": "other", **gate_env(gate)},
    )
    assert result.returncode == 44
    assert not any(call.startswith("rm -f ") for call in calls)
    assert "INODEFENCE_CLEANUP_UNKNOWN: controller creation outcome:" in result.stderr
    assert (gate / "cell.verdict").read_text().startswith("U controller creation outcome")


def test_failed_controller_run_with_unanswered_inspect_is_unknown(tmp_path: Path) -> None:
    # Only the container inspects go unanswered; the volume path still works.
    result, calls = run_fake_docker(
        tmp_path,
        create_error="controller",
        extra_env={"TIMEOUT_OPERATION": "container inspect"},
    )
    assert result.returncode == 44
    assert not any(call.startswith("rm -f ") for call in calls)
    assert "INODEFENCE_CLEANUP_UNKNOWN: controller creation outcome:" in result.stderr


def gate_env(directory: Path) -> dict[str, str]:
    return {"INODEFENCE_START_GATE_DIR": str(directory), "INODEFENCE_START_GATE_CELL": "cell"}


def test_gated_clean_cleanup_records_cleanup_then_clean(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    gate.mkdir()
    result, _ = run_fake_docker(tmp_path, extra_env=gate_env(gate))
    assert result.returncode == 0, result.stderr
    records = [line for line in result.stderr.splitlines() if line.startswith("GATE RECORD")]
    assert records == ["GATE RECORD C", "GATE RECORD S"]
    assert (gate / "cell.verdict").read_text() == "S\n"


def test_gated_unknown_is_recorded_before_the_marker(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    gate.mkdir()
    result, _ = run_fake_docker(tmp_path, extra_env={"INSPECT_UNKNOWN": "1", **gate_env(gate)})
    assert result.returncode != 0
    lines = result.stderr.splitlines()
    first_record = next(i for i, line in enumerate(lines) if line.startswith("GATE RECORD U"))
    first_marker = next(
        i for i, line in enumerate(lines) if line.startswith("INODEFENCE_CLEANUP_UNKNOWN:")
    )
    assert first_record < first_marker
    assert "GATE RECORD S" not in lines
    assert (gate / "cell.verdict").read_text().startswith("U volume creation ownership")


def test_gated_record_failure_still_prints_marker_and_never_passes(tmp_path: Path) -> None:
    missing = tmp_path / "missing-gate"  # the record cannot reach the gate
    clean, _ = run_fake_docker(tmp_path, extra_env=gate_env(missing))
    assert clean.returncode == 125
    assert "PASSED:" not in clean.stdout
    assert "start gate: C not recorded" in clean.stderr
    assert "GATE RECORD S" not in clean.stderr
    assert not missing.exists()


def test_gated_record_failure_with_unknown_keeps_marker(tmp_path: Path) -> None:
    missing = tmp_path / "missing-gate"
    result, _ = run_fake_docker(tmp_path, extra_env={"INSPECT_UNKNOWN": "1", **gate_env(missing)})
    assert result.returncode != 0
    assert "INODEFENCE_CLEANUP_UNKNOWN: volume creation ownership" in result.stderr
    assert "start gate: U not recorded" in result.stderr

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
    assert calls[-2:] == [
        "rm -f inodefence-local-controller-test",
        "volume rm inodefence-local-runtime-test",
    ]
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
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Execute the complete host script with a closed PATH and inert executables."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("dirname", "date"):
        (bin_dir / name).symlink_to(Path("/usr/bin") / name)
    docker = bin_dir / "docker"
    docker.write_text("""#!/bin/bash
[ "$1" = --context ] || exit 99
shift 2
printf '%s\\n' "$*" >> "$FAKE_LOG"
case "$*" in
  "exec "*" test -e "*) exit 1 ;;
esac
case "$1 $2" in
  "container inspect"|"volume inspect") exit 1 ;;
  "volume create") [ "$CREATE_ERROR" != volume ] || exit 43 ;;
  "run -d") [ "$CREATE_ERROR" != controller ] || exit 44 ;;
  "rm -f") exit "$CONTROLLER_ERROR" ;;
  "volume rm") exit "$VOLUME_ERROR" ;;
esac
exit 0
""")
    docker.chmod(0o755)
    python = bin_dir / "fake-python"
    python.write_text('#!/bin/bash\nexit "$HOST_ERROR"\n')
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
    }
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), "demo"], env=env, text=True, capture_output=True, check=False
    )
    return result, log.read_text().splitlines()


@pytest.mark.parametrize(
    ("failure", "expected", "removals"),
    [
        ("volume", 43, []),
        ("controller", 44, ["volume rm inodefence-local-runtime-test"]),
    ],
)
def test_cleanup_only_removes_created_resources(
    tmp_path: Path, failure: str, expected: int, removals: list[str]
) -> None:
    result, calls = run_fake_docker(tmp_path, create_error=failure)
    assert result.returncode == expected
    assert [call for call in calls if call.startswith(("rm -f ", "volume rm "))] == removals

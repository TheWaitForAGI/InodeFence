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

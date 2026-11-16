"""`make target-explore` needs an explicit TARGET_VERSIONS; `make target-run` keeps its default.

The recipes call `$(PYTHON) -m inodefence.cli ...`. A stub PYTHON prints its argv instead, so no
Docker, network or real run is involved.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")


@pytest.fixture
def stub_python(tmp_path: Path) -> Path:
    stub = tmp_path / "python-stub"
    stub.write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done\n')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub


# Variables the Makefile exports: under `make check` the outer make passes them down, and they
# would look like caller-given values to the make under test.
MAKE_VARIABLES = (
    "TARGET",
    "TARGET_VERSIONS",
    "TARGET_FILTERS",
    "TARGET_OUT",
    "IMAGE_TAG_SUFFIX",
    "AUTO_PREPARE",
    "TARGET_ARGS",
    "PYTHON",
    "BUDGET",
    "SEED",
    "EXPLORE_OUT",
    "TAR_VERSION",
    "MAKEFLAGS",
    "MFLAGS",
    "MAKELEVEL",
)


def run_make(
    target: str, stub: Path, home: Path, *args: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key not in MAKE_VARIABLES}
    env["HOME"] = str(home)
    env.update(env_extra or {})
    return subprocess.run(
        ["make", "-s", "-C", str(ROOT), target, f"PYTHON={stub}", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def versions(stdout: str) -> list[str]:
    lines = stdout.splitlines()
    return [lines[i + 1] for i, line in enumerate(lines) if line == "--version"]


def test_explore_without_versions_is_refused_before_the_cli(
    stub_python: Path, tmp_path: Path
) -> None:
    result = run_make("target-explore", stub_python, tmp_path)
    assert result.returncode != 0
    assert "TARGET_VERSIONS is required" in result.stderr
    assert result.stdout == ""  # the stub (stand-in for `inodefence`) never ran


def test_explore_dry_run_without_versions_is_also_refused(
    stub_python: Path, tmp_path: Path
) -> None:
    result = run_make("target-explore", stub_python, tmp_path, "TARGET_ARGS=--dry-run")
    assert result.returncode != 0
    assert result.stdout == ""


def test_explore_with_an_empty_value_is_refused(stub_python: Path, tmp_path: Path) -> None:
    result = run_make("target-explore", stub_python, tmp_path, "TARGET_VERSIONS=")
    assert result.returncode != 0
    assert result.stdout == ""


def test_explore_tar_version_alone_does_not_count(stub_python: Path, tmp_path: Path) -> None:
    result = run_make("target-explore", stub_python, tmp_path, "TAR_VERSION=7.5.3")
    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.parametrize("given", ["latest", "7.5.2"])
def test_explore_with_versions_on_the_command_line(
    stub_python: Path, tmp_path: Path, given: str
) -> None:
    result = run_make("target-explore", stub_python, tmp_path, f"TARGET_VERSIONS={given}")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[:4] == ["-m", "inodefence.cli", "explore", "--target"]
    assert versions(result.stdout) == [given]
    assert lines[lines.index("--budget") + 1] == "20"
    assert lines[lines.index("--seed") + 1] == "123"
    assert lines[lines.index("--out") + 1] == str(tmp_path / "inodefence-explore")


def test_explore_with_versions_from_the_environment(stub_python: Path, tmp_path: Path) -> None:
    result = run_make(
        "target-explore", stub_python, tmp_path, env_extra={"TARGET_VERSIONS": "7.5.2"}
    )
    assert result.returncode == 0, result.stderr
    assert versions(result.stdout) == ["7.5.2"]


def test_explore_with_several_versions(stub_python: Path, tmp_path: Path) -> None:
    result = run_make(
        "target-explore", stub_python, tmp_path, "TARGET_VERSIONS=7.5.2 7.5.3", "AUTO_PREPARE=1"
    )
    assert result.returncode == 0, result.stderr
    assert versions(result.stdout) == ["7.5.2", "7.5.3"]
    assert "--auto-prepare" in result.stdout.splitlines()


def test_target_run_keeps_its_default_version(stub_python: Path, tmp_path: Path) -> None:
    result = run_make("target-run", stub_python, tmp_path)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[:4] == ["-m", "inodefence.cli", "verify", "--target"]
    # TARGET_VERSIONS ?= $(TAR_VERSION), TAR_VERSION ?= 7.5.2
    assert versions(result.stdout) == ["7.5.2"]
    assert lines[lines.index("--out") + 1] == str(tmp_path / "inodefence-target-run")


def test_target_run_follows_tar_version(stub_python: Path, tmp_path: Path) -> None:
    result = run_make("target-run", stub_python, tmp_path, "TAR_VERSION=7.5.3")
    assert result.returncode == 0, result.stderr
    assert versions(result.stdout) == ["7.5.3"]

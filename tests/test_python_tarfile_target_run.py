"""Python tarfile target run (no docker).

The container program is executed with the local interpreter inside ``tmp_path`` (``WORK``), so
the extraction and its ``../ext`` escape stay in the disposable test directory. ``docker`` itself
is replaced by a runner that does exactly that, which also exercises the command/parse path.
"""

from __future__ import annotations

import base64
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import scripts.regression_check as rc
import scripts.run_python_tarfile_target as rpt
from experiments.repro import python_tarfile_identity as pti

from inodefence.target_result import load_target_result

RUNTIME = platform.python_version()
_FIXTURES = {f.name: f for f in rc.build_fixtures()}


def _local_runner(work_root: Path):
    """Stand-in for ``docker run``: run PY_PROGRAM here with the container's env, in a fresh dir."""
    counter = iter(range(1000))

    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert cmd[:3] == ["docker", "run", "--rm"]
        env = {k: v for k, v in (cmd[i + 1].split("=", 1) for i, a in enumerate(cmd) if a == "-e")}
        env["WORK"] = str(work_root / f"cell{next(counter)}")
        return subprocess.run([sys.executable, "-I", "-c", cmd[-1]], env=env, check=False, **kwargs)

    return runner


def _raw(tmp_path: Path, name: str, flt: str) -> dict[str, Any]:
    tar_b64 = base64.b64encode(_FIXTURES[name].tar).decode()
    return pti.run_one(RUNTIME, flt, tar_b64, runner=_local_runner(tmp_path))


def test_docker_command_is_disposable_offline_and_pins_runtime_image() -> None:
    cmd = pti.docker_command("3.12.16", "data", "AAAA")
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "python:3.12.16-slim" in cmd
    assert "EXTRACTION_FILTER=data" in cmd
    assert "-v" not in cmd and "--volume" not in cmd and "--mount" not in cmd


@pytest.mark.parametrize("bad", ["3.12", "3.12.x", "", "3.12.16-slim"])
def test_runtime_version_must_be_exact(bad: str) -> None:
    with pytest.raises(ValueError, match="exact"):
        pti.docker_command(bad, "data", "AAAA")


def test_unknown_filter_is_refused() -> None:
    with pytest.raises(ValueError, match="extraction_filter"):
        pti.docker_command("3.12.16", "tar", "AAAA")


def test_fully_trusted_hardlink_shares_reference_inode(tmp_path: Path) -> None:
    run = rpt.case_from_raw(
        _FIXTURES["toplevel_hardlink"], _raw(tmp_path, "toplevel_hardlink", "fully_trusted")
    )
    assert run.raw["runtime"] == RUNTIME
    assert run.raw["shared_identity"] == ["extract/link"]
    assert (run.verdict.c0, run.verdict.c1, run.verdict.c2) == (None, True, True)


def test_data_filter_declines_the_external_hardlink(tmp_path: Path) -> None:
    run = rpt.case_from_raw(
        _FIXTURES["toplevel_hardlink"], _raw(tmp_path, "toplevel_hardlink", "data")
    )
    assert run.raw["declined"] is not None
    assert run.verdict.outcome == "declined"
    assert (run.verdict.c1, run.verdict.c2) == (False, False)


def test_runtime_mismatch_is_a_run_error_not_a_result() -> None:
    out = json.dumps({"runtime": "3.11.0", "shared_identity": []})
    raw = pti.parse_output(out, "3.12.16")
    assert raw is not None and raw["_run_error"] is True
    run = rpt.case_from_raw(_FIXTURES["toplevel_hardlink"], raw)
    assert run.verdict.is_run_error
    assert (run.verdict.c1, run.verdict.c2) == (None, None)


def test_filter_unsupported_runtime_is_a_run_error() -> None:
    out = json.dumps({"runtime": "3.10.0", "filter_unsupported": True})
    raw = pti.parse_output(out, "3.10.0")
    assert raw is not None and raw["_run_error"] is True


def test_docker_failure_is_a_run_error() -> None:
    def failing(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd, 1)

    raw = pti.run_one("3.12.16", "data", "AAAA", runner=failing)
    assert raw["_run_error"] is True


def test_compared_axis_never_mixes_the_two_axes() -> None:
    assert rpt.compared_axis(["3.12.16"], ["fully_trusted", "data"]) == "extraction_filter"
    assert rpt.compared_axis(["3.12.10", "3.12.16"], ["data"]) == "runtime_version"
    assert rpt.compared_axis(["3.12.16"], ["data"]) is None
    with pytest.raises(ValueError, match="one axis"):
        rpt.compared_axis(["3.12.10", "3.12.16"], ["fully_trusted", "data"])


def test_cli_refuses_varying_both_axes(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--runtime-version", "3.12.10", "--runtime-version", "3.12.16"]
    argv += ["--extraction-filter", "fully_trusted", "--extraction-filter", "data", "--dry-run"]
    with pytest.raises(SystemExit) as exc:
        rpt.main(argv)
    assert exc.value.code == 2
    assert "one axis" in capsys.readouterr().err


def test_dry_run_reports_compared_and_fixed_axes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--runtime-version", "3.12.16"]
    argv += ["--extraction-filter", "fully_trusted", "--extraction-filter", "data", "--dry-run"]
    assert rpt.main(argv) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["compared_axis"] == "extraction_filter"
    assert plan["fixed_axes"] == {"runtime_version": "3.12.16"}
    assert set(plan["cells"]) == {
        "python-tarfile-py3.12.16-fully_trusted",
        "python-tarfile-py3.12.16-data",
    }
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("flt", ["fully_trusted", "data"])
def test_cell_writes_common_result_with_axes_in_separate_fields(tmp_path: Path, flt: str) -> None:
    cell = rpt.Cell(RUNTIME, flt)
    runs = rpt.run_cell(cell, runner=_local_runner(tmp_path / "sandbox"))
    prov = rpt.Provenance(engine_sha=None, engine_dirty=True, image_ref=pti.image_ref(RUNTIME))
    result = rpt.build_result(cell, runs, prov)
    path = rpt.write_result(tmp_path / "out" / cell.dirname, result, runs)

    loaded = load_target_result(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["target"] == "python-tarfile"
    assert data["axes"] == {
        "target_version": None,
        "runtime_version": RUNTIME,
        "extraction_filter": flt,
    }
    assert data["mode"] == "fixture-regression"
    assert data["observed_contracts"] == ["C1", "C2"]
    assert all(case["c0"] is None for case in data["cases"])
    assert loaded.executed == len(rc.build_fixtures())
    assert loaded.errored == 0
    if flt == "fully_trusted":
        assert "toplevel_hardlink" in loaded.violating_cases
    else:
        assert loaded.violating_cases == ()
    with pytest.raises(FileExistsError):
        rpt.write_result(tmp_path / "out" / cell.dirname, result, runs)

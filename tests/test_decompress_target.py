"""decompress adapter -> inodefence-target-result-v1 (no docker; the container runner is faked)."""

import base64
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.regression_check as rc
import scripts.run_decompress_target as dt
import scripts.run_target as rt

from inodefence.target_result import RUN_ERROR, Provenance, Verdict, load_target_result

ORIGINAL = "decompress@4.2.1"
FORK = "@xhmikosr/decompress@11.1.4"
REF = {"dev": "1", "ino": "5", "nlink": 1, "size": 30, "type": "reg"}


def _raw(package: str, version: str, *, shared: bool) -> dict[str, Any]:
    after = {**REF, "nlink": 2} if shared else REF
    return {
        "package": package,
        "package_version": version,
        "declined": None if shared else {"message": "refused"},
        "reference_before": REF,
        "reference_after": after,
        "shared_identity": ["extract/link"] if shared else [],
    }


@pytest.fixture(autouse=True)
def _registered(monkeypatch: pytest.MonkeyPatch) -> None:
    # Registration in TARGETS is a later, separate change; tests register it locally.
    monkeypatch.setitem(rt.TARGETS, "decompress", "scripts.run_decompress_target:ADAPTER")
    monkeypatch.setattr(
        rt, "engine_provenance", lambda image: Provenance("c" * 40, False, image, "sha256:def")
    )


def test_spec_names_package_and_version() -> None:
    assert dt.parse_spec(ORIGINAL) == ("decompress", "4.2.1")
    assert dt.parse_spec(FORK) == ("@xhmikosr/decompress", "11.1.4")
    for bad in ("4.2.1", "decompress@4.2", "tar@1.0.0", "decompress@latest"):
        with pytest.raises(ValueError):
            dt.parse_spec(bad)


def test_pinned_recipes_exist_for_both_packages() -> None:
    assert dt.pinned_recipe("decompress", "4.2.1") is not None
    assert dt.pinned_recipe("@xhmikosr/decompress", "11.1.4") is not None
    assert dt.pinned_recipe("decompress", "11.1.4") is None  # package and version must both match


def test_docker_command_keeps_the_existing_isolation() -> None:
    # The whole argument list before the program is fixed: exactly the flags of
    # decompress_hardlink.run_probe (no mounts, no extra capability or user override).
    cmd = dt.docker_command("4.2.1", "AAAA")
    ref_b64 = base64.b64encode(dt.REFERENCE_CONTENT).decode()
    assert cmd[: cmd.index("-e", cmd.index("inodefence-decompress:4.2.1"))] == [
        "docker", "run", "--rm", "--pull", "never", "--network", "none", "--read-only",
        "--tmpfs", "/work:rw,size=16m,mode=1777", "--tmpfs", "/tmp:rw,size=16m,mode=1777",
        "--cap-drop", "ALL",
        "-e", "TAR_B64=AAAA", "-e", f"REF_B64={ref_b64}",
        "--entrypoint", "/usr/local/bin/node", "inodefence-decompress:4.2.1",
    ]  # fmt: skip
    assert cmd[-1] == dt.JS_PROGRAM


def test_package_mismatch_is_run_error() -> None:
    out = json.dumps(_raw("@xhmikosr/decompress", "11.1.4", shared=False))
    raw = dt.parse_output(out, "decompress", "4.2.1")
    assert raw is not None and raw["_run_error"] is True
    assert dt.parse_output("not json\n", "decompress", "4.2.1") is None


def test_runner_failure_is_run_error() -> None:
    def runner(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 125, "", "Unable to find image")

    raw = dt.run_one("decompress", "4.2.1", "AAAA", runner=runner)
    assert raw["_run_error"] is True and raw["_rc"] == 125


def test_version_pair_writes_common_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def run_one(package: str, version: str, tar_b64: str, **_: Any) -> dict[str, Any]:
        return _raw(package, version, shared=(package == "decompress"))

    monkeypatch.setattr(dt, "run_one", run_one)
    argv = ["--target", "decompress", "--version", ORIGINAL, "--version", FORK]
    assert rt.main([*argv, "--out", str(tmp_path)]) == 1

    original = load_target_result(tmp_path / "decompress-4.2.1" / "result.json")
    fork = load_target_result(tmp_path / "decompress-xhmikosr-decompress-11.1.4" / "result.json")
    assert original.verdict is Verdict.FAIL and fork.verdict is Verdict.PASS
    # The package is part of the version field, so the two packages are told apart.
    assert (original.axes.target_version, fork.axes.target_version) == (ORIGINAL, FORK)
    assert original.axes.runtime_version is None and original.axes.extraction_filter is None
    assert [c.case_id for c in original.cases] == [f.name for f in rc.build_fixtures()]
    assert all(c.c0 is None for c in original.cases)
    assert fork.provenance.image_ref == "inodefence-decompress:11.1.4"
    fixture = rc.build_fixtures()[0]
    saved = tmp_path / "decompress-4.2.1" / "inputs" / f"{fixture.name}.tar"
    assert saved.read_bytes() == fixture.tar
    assert "TARGET-RUN FAIL target=decompress version=decompress@4.2.1" in capsys.readouterr().out


def test_unobservable_run_is_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dt, "run_one", lambda *_, **__: {"_run_error": True, "_rc": 125})
    assert rt.main(["--target", "decompress", "--version", ORIGINAL, "--out", str(tmp_path)]) == 2
    result = load_target_result(tmp_path / "decompress-4.2.1" / "result.json")
    assert {(c.outcome, c.c1, c.c2) for c in result.cases} == {(RUN_ERROR, None, None)}


def test_dry_run_shows_install_step_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*_: object, **__: object) -> dict[str, Any]:
        raise AssertionError("dry-run must not run a container")

    monkeypatch.setattr(dt, "run_one", forbidden)
    assert rt.main(["--target", "decompress", "--version", FORK, "--dry-run"]) == 0
    cell = json.loads(capsys.readouterr().out)["cells"]["decompress-xhmikosr-decompress-11.1.4"]
    install, *fixtures = cell["would_run"]
    assert install["install_step"].startswith("docker build -f tools/decompress/Dockerfile")
    assert len(fixtures) == len(rc.build_fixtures())


@pytest.mark.parametrize(
    "argv",
    [
        ["--target", "decompress", "--version", "4.2.1", "--dry-run"],  # package missing
        ["--target", "decompress", "--version", "decompress@9.9.9", "--dry-run"],  # not pinned
        ["--target", "decompress", "--version", ORIGINAL, "--extraction-filter", "data"],
    ],
)
def test_rejects_bad_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        rt.main(argv)

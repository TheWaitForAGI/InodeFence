"""run_target: node-tar adapter -> inodefence-target-result-v1 files (no docker; run_one mocked)."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.regression_check as rc
import scripts.run_target as rt
from scripts import check_dev_env

from inodefence.target_result import RUN_ERROR, Provenance, Verdict, load_target_result

SHARED = {
    "declined": None,
    "shared_identity": ["extract/link"],
    "reference_before": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
    "reference_after": {"ino": "5", "nlink": 2, "size": 10, "type": "reg"},
}
DECLINED = {
    "declined": {"code": "TAR_ENTRY_ERROR", "message": "linkpath escapes extraction directory"},
    "shared_identity": [],
    "reference_before": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
    "reference_after": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
}


def _fake_run_one(raw_by_version: dict[str, dict[str, Any]]):
    def run_one(release: str, tar_b64: str) -> dict[str, Any]:
        return raw_by_version[release]

    return run_one


REAL_PREFLIGHT = rt.preflight


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    # No docker in the test environment: setup checks pass; the runner is faked per test.
    monkeypatch.setattr(rt, "preflight", lambda *_: [])
    monkeypatch.setattr(
        rt, "engine_provenance", lambda image: Provenance("b" * 40, False, image, "sha256:abc")
    )


def test_pair_writes_common_results_with_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt.cri, "run_one", _fake_run_one({"7.5.2": SHARED, "7.5.3": DECLINED}))
    code = rt.main(
        ["--target", "node-tar", "--version", "7.5.2", "--version", "7.5.3", "--out", str(tmp_path)]
    )
    assert code == 1  # worst verdict across versions: FAIL

    affected = load_target_result(tmp_path / "node-tar-7.5.2" / "result.json")
    fixed = load_target_result(tmp_path / "node-tar-7.5.3" / "result.json")
    assert affected.verdict is Verdict.FAIL and fixed.verdict is Verdict.PASS
    assert affected.axes.target_version == "7.5.2" and affected.axes.extraction_filter is None
    assert affected.observed_contracts == ("C1", "C2")
    names = [f.name for f in rc.build_fixtures()]
    assert [c.case_id for c in affected.cases] == names
    assert all(c.c0 is None for c in affected.cases)  # C0 not observed on this path
    assert {(c.c1, c.c2) for c in affected.cases} == {(True, True)}
    assert {(c.outcome, c.c1, c.c2) for c in fixed.cases} == {("declined", False, False)}
    assert affected.provenance.image_ref == "inodefence-node-tar-effect:7.5.2"

    # The saved inputs are exactly the regression fixtures; raw observations are kept unchanged.
    fixture = rc.build_fixtures()[0]
    saved = tmp_path / "node-tar-7.5.2" / "inputs" / f"{fixture.name}.tar"
    assert saved.read_bytes() == fixture.tar
    raw = json.loads((tmp_path / "node-tar-7.5.3" / "raw" / f"{fixture.name}.json").read_text())
    assert raw == DECLINED

    out = capsys.readouterr().out
    assert "TARGET-RUN FAIL target=node-tar version=7.5.2" in out
    assert "TARGET-RUN PASS target=node-tar version=7.5.3" in out


def test_unobservable_case_is_error_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = {"_run_error": True, "_rc": 125, "_stderr": "no such image"}
    monkeypatch.setattr(rt.cri, "run_one", _fake_run_one({"9.9.9": broken}))
    assert rt.main(["--target", "node-tar", "--version", "9.9.9", "--out", str(tmp_path)]) == 2
    result = load_target_result(tmp_path / "node-tar-9.9.9" / "result.json")
    assert result.verdict is Verdict.ERROR
    assert {(c.outcome, c.c1, c.c2) for c in result.cases} == {(RUN_ERROR, None, None)}


def test_missing_reference_state_is_error() -> None:
    raw = {"declined": None, "shared_identity": [], "reference_before": None}
    case = rt.fixture_case(rc.build_fixtures()[0], raw)
    assert case.verdict.outcome == RUN_ERROR and case.verdict.c2 is None


def test_refuses_to_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt.cri, "run_one", _fake_run_one({"7.5.3": DECLINED}))
    args = ["--target", "node-tar", "--version", "7.5.3", "--out", str(tmp_path)]
    assert rt.main(args) == 0
    with pytest.raises(SystemExit):
        rt.main(args)


def test_dry_run_runs_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*_: object) -> dict[str, Any]:
        raise AssertionError("dry-run must not run a container")

    monkeypatch.setattr(rt.cri, "run_one", forbidden)
    assert rt.main(["--target", "node-tar", "--version", "7.5.2", "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    cell = plan["cells"]["node-tar-7.5.2"]
    assert cell["image"] == "inodefence-node-tar-effect:7.5.2"
    assert cell["axes"] == {
        "target_version": "7.5.2",
        "runtime_version": None,
        "extraction_filter": None,
    }
    assert len(cell["would_run"]) == len(rc.build_fixtures())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--target", "node-tar", "--version", "latest", "--dry-run"],
        ["--target", "node-tar", "--version", "7.5.2", "--version", "7.5.2", "--dry-run"],
        ["--target", "gnu-tar", "--version", "1.35", "--dry-run"],
        ["--target", "node-tar", "--version", "7.5.2"],  # no --out
        # node-tar has no filter axis
        ["--target", "node-tar", "--version", "7.5.2", "--extraction-filter", "data", "--dry-run"],
        # python-tarfile needs a filter, an exact runtime, a known filter, and one varied axis
        ["--target", "python-tarfile", "--version", "3.12.16", "--dry-run"],
        [
            "--target",
            "python-tarfile",
            "--version",
            "3.12",
            "--extraction-filter",
            "data",
            "--dry-run",
        ],
        [
            "--target",
            "python-tarfile",
            "--version",
            "3.12.16",
            "--extraction-filter",
            "tar",
            "--dry-run",
        ],
        [
            "--target",
            "python-tarfile",
            "--version",
            "3.12.3",
            "--version",
            "3.12.16",
            "--extraction-filter",
            "fully_trusted",
            "--extraction-filter",
            "data",
            "--dry-run",
        ],
    ],
)
def test_rejects_bad_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        rt.main(argv)


def _fake_py_run_one(raw_by_cell: dict[tuple[str, str], dict[str, Any]]):
    def run_one(runtime: str, extraction_filter: str, tar_b64: str, **_: Any) -> dict[str, Any]:
        return raw_by_cell[(runtime, extraction_filter)]

    return run_one


def test_python_tarfile_filter_axis_through_common_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import scripts.run_python_tarfile_target as pyt

    monkeypatch.setattr(
        pyt.pti,
        "run_one",
        _fake_py_run_one({("3.12.16", "fully_trusted"): SHARED, ("3.12.16", "data"): DECLINED}),
    )
    argv = ["--target", "python-tarfile", "--version", "3.12.16"]
    argv += ["--extraction-filter", "fully_trusted", "--extraction-filter", "data"]
    assert rt.main([*argv, "--out", str(tmp_path)]) == 1

    trusted = load_target_result(
        tmp_path / "python-tarfile-py3.12.16-fully_trusted" / "result.json"
    )
    data = load_target_result(tmp_path / "python-tarfile-py3.12.16-data" / "result.json")
    assert trusted.target == "python-tarfile"
    assert trusted.verdict is Verdict.FAIL and data.verdict is Verdict.PASS
    # Filter and runtime are separate fields; the package-version field does not apply.
    assert (trusted.axes.target_version, trusted.axes.runtime_version) == (None, "3.12.16")
    assert (trusted.axes.extraction_filter, data.axes.extraction_filter) == (
        "fully_trusted",
        "data",
    )
    assert trusted.provenance.image_ref == "python:3.12.16-slim"
    fixture = rc.build_fixtures()[0]
    saved = tmp_path / "python-tarfile-py3.12.16-data" / "inputs" / f"{fixture.name}.tar"
    assert saved.read_bytes() == fixture.tar
    out = capsys.readouterr().out
    assert "TARGET-RUN FAIL target=python-tarfile runtime=3.12.16,filter=fully_trusted" in out


def test_python_tarfile_runtime_axis_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--target", "python-tarfile", "--version", "3.12.3", "--version", "3.12.16"]
    assert rt.main([*argv, "--extraction-filter", "data", "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert sorted(plan["cells"]) == [
        "python-tarfile-py3.12.16-data",
        "python-tarfile-py3.12.3-data",
    ]
    assert plan["cells"]["python-tarfile-py3.12.3-data"]["image"] == "python:3.12.3-slim"


# ---- setup checks: one line with the cause and the fix, exit 3, nothing run or written ----


def _setup_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    monkeypatch.setattr(rt, "preflight", REAL_PREFLIGHT)

    def forbidden(*_: object) -> dict[str, Any]:
        raise AssertionError("no case may run when setup fails")

    monkeypatch.setattr(rt.cri, "run_one", forbidden)
    argv = ["--target", "node-tar", "--version", "7.5.2", "--version", "7.5.3"]
    code = rt.main([*argv, "--out", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()
    return code, capsys.readouterr().err


def _fake_docker(*, info_rc: int, present: set[str]):
    def run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["docker", "info"]:
            return subprocess.CompletedProcess(cmd, info_rc, "27.0.0\n", "")
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0 if cmd[3] in present else 1, "", "")
        raise AssertionError(f"unexpected command {cmd}")

    return run


def test_setup_docker_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt.shutil, "which", lambda _: None)
    code, err = _setup_main(tmp_path, monkeypatch, capsys)
    assert code == rt.SETUP_ERROR == 3
    assert err.count("\n") == 1 and err.startswith("TARGET-RUN SETUP: docker not found on PATH")


def test_setup_docker_daemon_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(rt.subprocess, "run", _fake_docker(info_rc=1, present=set()))
    code, err = _setup_main(tmp_path, monkeypatch, capsys)
    assert code == 3 and "docker daemon not reachable" in err and "start Docker" in err


def test_setup_missing_image_names_it_and_the_install_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt.shutil, "which", lambda _: "/usr/bin/docker")
    present = {"inodefence-node-tar-effect:7.5.2"}
    monkeypatch.setattr(rt.subprocess, "run", _fake_docker(info_rc=0, present=present))
    code, err = _setup_main(tmp_path, monkeypatch, capsys)
    assert code == 3 and err.count("\n") == 1
    assert "missing image(s) inodefence-node-tar-effect:7.5.3;" in err
    assert "7.5.2;" not in err
    assert "make target-images TARGET=node-tar 'TARGET_VERSIONS=7.5.2 7.5.3'" in err


def test_build_images_skips_present_and_runs_committed_recipe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt.shutil, "which", lambda _: "/usr/bin/docker")
    built: list[list[str]] = []
    inspect = _fake_docker(info_rc=0, present={"inodefence-node-tar-effect:7.5.2"})

    def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["docker", "build"]:
            built.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)
        return inspect(cmd, **kwargs)

    monkeypatch.setattr(rt.subprocess, "run", run)
    argv = ["--target", "node-tar", "--version", "7.5.2", "--version", "7.5.3", "--build-images"]
    assert rt.main(argv) == 0
    assert built == [
        [
            "docker", "build", "-f", "tools/node-tar/effect/Dockerfile",
            "--build-arg", "TAR_VERSION=7.5.3", "-t", "inodefence-node-tar-effect:7.5.3", ".",
        ]
    ]  # fmt: skip
    assert "present inodefence-node-tar-effect:7.5.2 (skip)" in capsys.readouterr().out


def test_build_images_without_recipe_is_setup_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(rt.subprocess, "run", _fake_docker(info_rc=0, present=set()))
    assert rt.main(["--target", "node-tar", "--version", "9.9.9", "--build-images"]) == 3
    assert "no build recipe for inodefence-node-tar-effect:9.9.9" in capsys.readouterr().err


def test_build_images_docker_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt.shutil, "which", lambda _: None)
    assert rt.main(["--target", "node-tar", "--version", "7.5.2", "--build-images"]) == 3
    assert capsys.readouterr().err.startswith("TARGET-IMAGES SETUP: docker not found")


def test_every_registered_target_has_an_image_recipe() -> None:
    examples = {
        "node-tar": (["7.5.2"], []),
        "python-tarfile": (["3.12.16"], ["data"]),
        "oras-go": (["2.6.1"], []),
        "decompress": (["decompress@4.2.1"], []),
    }
    assert set(examples) == set(rt.TARGETS)
    for target, (versions, filters) in examples.items():
        adapter = rt.load_adapter(target)
        (cell,) = adapter.cells(versions, filters)
        assert adapter.image_build is not None and adapter.image_build(cell), target


def test_env_check_names_missing_runtime_root_and_fix(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-runtime"
    problems = check_dev_env.setup_problems(missing)
    (root_problem,) = [p for p in problems if "runtime root" in p]
    assert f"runtime root {missing} does not exist" in root_problem
    assert f"sudo mkdir -p {missing}" in root_problem
    assert not [p for p in check_dev_env.setup_problems(tmp_path) if "runtime root" in p]

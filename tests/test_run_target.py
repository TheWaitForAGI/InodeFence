"""run_target: adapters -> inodefence-target-result-v1 files, image reuse/prepare (no docker)."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.regression_check as rc
import scripts.run_node_tar_target as nt
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
    def run_one(release: str, tar_b64: str, image: str | None = None) -> dict[str, Any]:
        assert image == f"inodefence-node-tar-effect:{release}"  # the cell's image reaches the run
        return raw_by_version[release]

    return run_one


REAL_DOCKER_PROBLEM = rt.docker_problem
REAL_PREPARE_IMAGE = rt.prepare_image


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    # No docker in the test environment: docker "works" and every image is "present".
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(rt, "image_id", lambda ref: f"sha256:{ref}")
    monkeypatch.setattr(
        rt, "engine_provenance", lambda image: Provenance("b" * 40, False, image, "sha256:abc")
    )


def test_pair_writes_common_results_with_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(nt.cri, "run_one", _fake_run_one({"7.5.2": SHARED, "7.5.3": DECLINED}))
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
    # 7.5.8 has a committed lock (a version without one needs --allow-registry-prepare).
    monkeypatch.setattr(nt.cri, "run_one", _fake_run_one({"7.5.8": broken}))
    assert rt.main(["--target", "node-tar", "--version", "7.5.8", "--out", str(tmp_path)]) == 2
    result = load_target_result(tmp_path / "node-tar-7.5.8" / "result.json")
    assert result.verdict is Verdict.ERROR
    assert {(c.outcome, c.c1, c.c2) for c in result.cases} == {(RUN_ERROR, None, None)}


def test_missing_reference_state_is_error() -> None:
    raw = {"declined": None, "shared_identity": [], "reference_before": None}
    case = rt.fixture_case(rc.build_fixtures()[0], raw)
    assert case.verdict.outcome == RUN_ERROR and case.verdict.c2 is None


def test_refuses_to_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nt.cri, "run_one", _fake_run_one({"7.5.3": DECLINED}))
    args = ["--target", "node-tar", "--version", "7.5.3", "--out", str(tmp_path)]
    assert rt.main(args) == 0
    with pytest.raises(SystemExit):
        rt.main(args)


def test_dry_run_runs_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*_: object, **__: object) -> dict[str, Any]:
        raise AssertionError("dry-run must not run a container")

    monkeypatch.setattr(nt.cri, "run_one", forbidden)
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


# ---- image layer: reuse / prepare / mismatch / tag override (fake adapter, no docker) ----


def _fake_adapter(prepare_supported: bool = True, shared_image: bool = False) -> rt.TargetAdapter:
    fixture = rc.build_fixtures()[0]

    def cells(versions: list[str], filters: list[str]) -> list[rt.RunCell]:
        return [
            rt.RunCell(
                f"fake-{v}",
                rt.TargetAxes(target_version=v),
                "fake-image:shared" if shared_image else f"fake-image:{v}",
            )
            for v in versions
        ]

    def run(cell: rt.RunCell) -> list[rt.CaseRun]:
        ran.append(cell.image_ref)
        return [rt.fixture_case(fixture, SHARED)]

    def prepare(cell: rt.RunCell) -> rt.PrepareStep:
        assert cell.image_ref is not None
        if not prepare_supported:
            return rt.prepare_unsupported(cell)
        return rt.PrepareStep(cell.image_ref, (("docker", "build", "-t", cell.image_ref),), "b")

    ran: list[str | None] = []
    adapter = rt.TargetAdapter(
        mode=rt.ResultMode.FIXTURE_REGRESSION,
        observed_contracts=("C1", "C2"),
        cells=cells,
        plan=lambda cell: [],
        run=run,
        prepare=prepare,
    )
    _fake_adapter.ran = ran  # type: ignore[attr-defined]
    return adapter


def _use(monkeypatch: pytest.MonkeyPatch, adapter: rt.TargetAdapter, present: dict[str, str]):
    monkeypatch.setitem(rt.TARGETS, "fake", "unused:ADAPTER")
    monkeypatch.setattr(rt, "load_adapter", lambda target: adapter)
    monkeypatch.setattr(rt, "image_id", lambda ref: present.get(ref))
    prepared: list[str] = []

    def prepare_image(step: rt.PrepareStep) -> str:
        if step.commands is None:
            raise rt.PrepareError(f"cannot prepare {step.image_ref}: {step.reason}")
        prepared.append(step.image_ref)
        present[step.image_ref] = f"sha256:new-{step.image_ref}"
        return present[step.image_ref]

    monkeypatch.setattr(rt, "prepare_image", prepare_image)
    return prepared


def _argv(tmp_path: Path, *versions: str) -> list[str]:
    out = ["--target", "fake"]
    for v in versions:
        out += ["--version", v]
    return [*out, "--out", str(tmp_path)]


def test_present_image_is_reused_without_preparing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    present = {"fake-image:1.0.0": "sha256:old"}
    prepared = _use(monkeypatch, _fake_adapter(), present)
    assert rt.main([*_argv(tmp_path, "1.0.0"), "--auto-prepare"]) == 1
    assert prepared == []
    result = load_target_result(tmp_path / "fake-1.0.0" / "result.json")
    assert result.provenance.image_id == "sha256:old"


def test_missing_image_without_auto_prepare_stops_before_any_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared = _use(monkeypatch, _fake_adapter(), {"fake-image:1.0.0": "sha256:old"})
    assert rt.main(_argv(tmp_path, "1.0.0", "2.0.0")) == rt.SETUP_ERROR == 3
    err = capsys.readouterr().err
    assert err == (
        "TARGET-RUN SETUP: missing image fake-image:2.0.0; "
        "rerun with AUTO_PREPARE=1 (--auto-prepare) to prepare it\n"
    )
    assert prepared == [] and _fake_adapter.ran == [] and list(tmp_path.iterdir()) == []


def test_missing_unsupported_image_prints_the_adapter_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _use(monkeypatch, _fake_adapter(prepare_supported=False), {})
    assert rt.main(_argv(tmp_path, "1.0.0")) == 3
    assert "automatic image preparation is not implemented for this target yet" in (
        capsys.readouterr().err
    )
    assert list(tmp_path.iterdir()) == []


def test_auto_prepare_prepares_each_image_once_and_records_its_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _use(monkeypatch, _fake_adapter(shared_image=True), {})
    assert rt.main([*_argv(tmp_path, "1.0.0", "2.0.0"), "--auto-prepare"]) == 1
    assert prepared == ["fake-image:shared"]  # two cells, one image, one preparation
    for v in ("1.0.0", "2.0.0"):
        result = load_target_result(tmp_path / f"fake-{v}" / "result.json")
        assert result.provenance.image_id == "sha256:new-fake-image:shared"


def test_failed_preparation_gives_no_verdict_for_that_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _use(monkeypatch, _fake_adapter(prepare_supported=False), {"fake-image:1.0.0": "sha256:a"})
    assert rt.main([*_argv(tmp_path, "1.0.0", "2.0.0"), "--auto-prepare"]) == 3
    assert (tmp_path / "fake-1.0.0" / "result.json").exists()
    assert not (tmp_path / "fake-2.0.0").exists()
    assert "TARGET-RUN PREPARE-ERROR fake-2.0.0: cannot prepare fake-image:2.0.0" in (
        capsys.readouterr().err
    )


def test_image_changed_during_run_gives_no_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    present = {"fake-image:1.0.0": "sha256:before"}
    adapter = _fake_adapter()
    _use(monkeypatch, adapter, present)
    inner = adapter.run

    def run_then_swap(cell: rt.RunCell) -> list[rt.CaseRun]:
        present["fake-image:1.0.0"] = "sha256:swapped"
        return inner(cell)

    monkeypatch.setattr(
        rt, "load_adapter", lambda t: rt.dataclasses.replace(adapter, run=run_then_swap)
    )
    assert rt.main(_argv(tmp_path, "1.0.0")) == 3
    assert not (tmp_path / "fake-1.0.0" / "result.json").exists()
    assert "IMAGE-MISMATCH fake-1.0.0" in capsys.readouterr().err


def test_tag_suffix_reaches_the_run_and_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    present = {"fake-image:1.0.0": "sha256:canonical"}
    prepared = _use(monkeypatch, _fake_adapter(), present)
    argv = [*_argv(tmp_path, "1.0.0"), "--auto-prepare", "--image-tag-suffix=-ifdev"]
    assert rt.main(argv) == 1
    assert prepared == ["fake-image:1.0.0-ifdev"]  # the canonical tag is neither reused nor touched
    assert _fake_adapter.ran == ["fake-image:1.0.0-ifdev"]
    assert present["fake-image:1.0.0"] == "sha256:canonical"
    result = load_target_result(tmp_path / "fake-1.0.0" / "result.json")
    assert result.provenance.image_ref == "fake-image:1.0.0-ifdev"
    assert "image=fake-image:1.0.0-ifdev" in capsys.readouterr().out


@pytest.mark.parametrize("suffix", ["has space", "/x", ":x", "a" * 41])
def test_bad_tag_suffix_is_refused(suffix: str) -> None:
    with pytest.raises(SystemExit):
        rt.main(["--target", "node-tar", "--version", "7.5.2", f"--image-tag-suffix={suffix}"])


def test_dry_run_shows_reuse_and_prepare_and_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared = _use(monkeypatch, _fake_adapter(), {"fake-image:1.0.0": "sha256:old"})
    assert (
        rt.main(["--target", "fake", "--version", "1.0.0", "--version", "2.0.0", "--dry-run"]) == 0
    )
    cells = json.loads(capsys.readouterr().out)["cells"]
    assert cells["fake-1.0.0"]["image_plan"] == {"action": "reuse", "image_id": "sha256:old"}
    assert cells["fake-2.0.0"]["image_plan"]["commands"] == ["docker build -t fake-image:2.0.0"]
    assert prepared == [] and _fake_adapter.ran == []


def test_docker_missing_is_one_line_and_exit_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt, "docker_problem", REAL_DOCKER_PROBLEM)
    monkeypatch.setattr(rt.shutil, "which", lambda _: None)
    assert rt.main(["--target", "node-tar", "--version", "7.5.2", "--out", str(tmp_path)]) == 3
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and err.startswith("TARGET-RUN SETUP: docker not found on PATH")
    assert list(tmp_path.iterdir()) == []


def test_docker_daemon_down_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(
        rt.subprocess, "run", lambda cmd, **_: subprocess.CompletedProcess(cmd, 1, "", "")
    )
    problem = REAL_DOCKER_PROBLEM()
    assert problem is not None and problem.startswith("docker daemon not reachable")


def test_prepare_image_runs_commands_and_returns_the_new_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0 if cmd[0] != "fail" else 1)

    monkeypatch.setattr(rt.subprocess, "run", run)
    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:made")
    step = rt.PrepareStep("x:1", (("docker", "pull", "x:1"),), "pull")
    assert REAL_PREPARE_IMAGE(step) == "sha256:made" and calls == [["docker", "pull", "x:1"]]
    with pytest.raises(rt.PrepareError, match="failed"):
        REAL_PREPARE_IMAGE(rt.PrepareStep("x:1", (("fail",),), "f"))
    with pytest.raises(rt.PrepareError, match="not implemented"):
        REAL_PREPARE_IMAGE(rt.prepare_unsupported(rt.RunCell("c", rt.TargetAxes(), "x:1")))
    monkeypatch.setattr(rt, "image_id", lambda ref: None)
    with pytest.raises(rt.PrepareError, match="not present"):
        REAL_PREPARE_IMAGE(step)


def test_every_registered_target_defaults_to_unsupported_prepare_or_has_one() -> None:
    for target in rt.TARGETS:
        adapter = rt.load_adapter(target)
        assert callable(adapter.prepare), target


def test_env_check_names_missing_runtime_root_and_fix(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-runtime"
    (root_problem,) = [p for p in check_dev_env.setup_problems(missing) if "runtime root" in p]
    assert f"runtime root {missing} does not exist" in root_problem
    assert f"sudo mkdir -p {missing}" in root_problem
    assert not [p for p in check_dev_env.setup_problems(tmp_path) if "runtime root" in p]


# ---- integration checks that need no docker (the rest ran on a real host; see the PR) ----


@pytest.mark.parametrize(
    "argv",
    [
        ["--target", "node-tar", "--version", "latest", "--dry-run"],  # refused version
        ["--target", "python-tarfile", "--version", "3.12", "--extraction-filter", "data"],
        ["--target", "decompress", "--version", "decompress@4.2.0", "--dry-run"],  # not pinned
    ],
)
def test_refusals_exit_3_not_the_error_verdict_code(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        rt.main(argv)
    assert raised.value.code == rt.SETUP_ERROR == 3


def test_rerun_into_existing_results_exits_3_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(nt.cri, "run_one", _fake_run_one({"7.5.3": DECLINED}))
    args = ["--target", "node-tar", "--version", "7.5.3", "--out", str(tmp_path)]
    assert rt.main(args) == 0
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(SystemExit) as raised:
        rt.main(args)
    assert raised.value.code == 3
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_result_inputs_and_summary_agree_and_failed_cells_get_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    from inodefence.target_result_summary import SUMMARY_NAME, summarize_file

    _use(monkeypatch, _fake_adapter(prepare_supported=False), {"fake-image:1.0.0": "sha256:a"})
    assert rt.main([*_argv(tmp_path, "1.0.0", "2.0.0"), "--auto-prepare"]) == 3
    good = tmp_path / "fake-1.0.0"
    result = load_target_result(good / "result.json")
    for item in result.repro_inputs:
        assert hashlib.sha256((good / item.tar_path).read_bytes()).hexdigest() == item.tar_sha256
    # The page is a pure function of result.json: re-rendering from that file alone matches.
    assert (good / SUMMARY_NAME).read_text(encoding="utf-8") == summarize_file(good / "result.json")
    assert not (tmp_path / "fake-2.0.0").exists()  # no result.json, no summary.md, no verdict

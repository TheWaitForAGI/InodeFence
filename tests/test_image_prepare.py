"""Image auto-prepare: generic step builder + offline check + each target's recipe (no docker)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.decompress_image as dci
import scripts.image_prepare as ip
import scripts.node_tar_image as nti
import scripts.run_oras_go_target as rog
import scripts.run_python_tarfile_target as rpt
import scripts.run_target as rt

from inodefence.target_result import TargetAxes

ADAPTERS = {
    "node-tar": "scripts.run_node_tar_target:ADAPTER",
    "python-tarfile": "scripts.run_python_tarfile_target:ADAPTER",
    "oras-go": "scripts.run_oras_go_target:ADAPTER",
    "decompress": "scripts.run_decompress_target:ADAPTER",
}


def _cell(target: str, version: str, image_ref: str, flt: str | None = None) -> rt.RunCell:
    axes = (
        TargetAxes(runtime_version=version, extraction_filter=flt)
        if target == "python-tarfile"
        else TargetAxes(target_version=version)
    )
    return rt.RunCell(dirname="x", axes=axes, image_ref=image_ref)


def _step(target: str, version: str, image_ref: str = "inodefence-dev/x:1") -> rt.PrepareStep:
    return rt.load_adapter(target).prepare(_cell(target, version, image_ref, "data"))


# ---- every target is wired, and every supported step ends in a verified tag ----


def test_all_four_targets_registered_with_their_prepare() -> None:
    for target, entry in ADAPTERS.items():
        assert rt.TARGETS[target] == entry
        assert rt.load_adapter(target).prepare is not rt.prepare_unsupported


@pytest.mark.parametrize(
    ("target", "version", "expect"),
    [
        ("node-tar", "7.4.4", "7.4.4"),
        ("oras-go", "2.6.1", "v2.6.1"),
        ("decompress", "@xhmikosr/decompress@11.1.4", "@xhmikosr/decompress 11.1.4"),
    ],
)
def test_build_step_builds_unverified_then_checks_then_tags(
    target: str, version: str, expect: str
) -> None:
    ref = "inodefence-dev/t:1"
    step = _step(target, version, ref)
    assert step.image_ref == ref and step.commands is not None
    build, check, tag, untag = step.commands
    assert build[:3] == ("docker", "build", "-q") and build[-3:] == ("-t", f"{ref}-unverified", ".")
    assert check[1:4] == ("-m", "scripts.image_prepare", "check")
    assert check[check.index("--expect") + 1] == expect
    assert f"{ref}-unverified" in check and ref not in check
    assert tag == ("docker", "tag", f"{ref}-unverified", ref)
    assert untag == ("docker", "rmi", "--no-prune", f"{ref}-unverified")
    # nothing in the step touches a tag other than image_ref and its own staging tag
    for command in step.commands:
        refs = [a for a in command if a.startswith("inodefence")]
        assert set(refs) <= {ref, f"{ref}-unverified"}


def test_python_step_pulls_official_only_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    recipe = rpt.image_recipe("3.12.10")
    absent = ip.prepare_step(recipe, "inodefence-dev/py:1", present=lambda ref: None)
    assert absent.commands is not None
    assert absent.commands[0] == ("docker", "pull", "-q", "python:3.12.10-slim")
    assert absent.commands[1] == (
        "docker",
        "tag",
        "python:3.12.10-slim",
        "inodefence-dev/py:1-unverified",
    )

    present = ip.prepare_step(recipe, "inodefence-dev/py:1", present=lambda ref: "sha256:x")
    assert present.commands is not None
    assert all(c[1] != "pull" for c in present.commands)  # a local official tag is never moved


def test_python_filter_axis_does_not_change_the_image_step() -> None:
    adapter = rt.load_adapter("python-tarfile")
    data = adapter.prepare(_cell("python-tarfile", "3.12.16", "r:1", "data"))
    trusted = adapter.prepare(_cell("python-tarfile", "3.12.16", "r:1", "fully_trusted"))
    assert data.commands == trusted.commands


def test_python_pull_is_only_the_official_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rpt.pti, "IMAGE", "evil.example/python:{runtime}-slim")
    with pytest.raises(ip.UnsupportedVersionError, match="not the official runtime tag"):
        rpt.image_recipe("3.12.16")


# ---- refusals: malformed or without a committed recipe -> commands None + reason ----


@pytest.mark.parametrize(
    ("target", "version", "reason"),
    [
        ("node-tar", "7.5.4", "no committed lock"),
        ("node-tar", "7.5.2; rm -rf /", "exact X.Y.Z"),
        ("python-tarfile", "3.12", "exact X.Y.Z"),
        ("oras-go", "2.6.3", "buildable: 2.6.1, 2.6.2"),
        ("oras-go", "v2.6.1", "exact X.Y.Z"),
        ("decompress", "decompress@11.1.4", "different packages"),
        ("decompress", "@xhmikosr/decompress@4.2.1", "not pinned"),
        ("decompress", "decompress@4.2.1 --build-arg X=1", "<package>@X.Y.Z"),
    ],
)
def test_unsupported_version_has_no_commands_and_a_reason(
    target: str, version: str, reason: str
) -> None:
    step = _step(target, version)
    assert step.commands is None
    assert reason in step.reason


def test_supported_recipes_come_from_committed_files() -> None:
    assert nti.recipe("7.4.4").build == (
        "-f",
        "tools/node-tar/effect/Dockerfile",
        "--build-arg",
        "TAR_VERSION=7.4.4",
    )
    assert rog.image_recipe("2.6.1").build[-1] == "ROLE=affected"  # type: ignore[index]
    assert rog.image_recipe("2.6.2").json_key == "oras_go_version"
    assert dci.recipe("@xhmikosr/decompress@11.1.4").build[-1] == "ROLE=fixed"  # type: ignore[index]
    assert dci.recipe("decompress@4.2.1").expected == "decompress 4.2.1"
    assert set(dci.pinned_specs()) == {"decompress@4.2.1", "@xhmikosr/decompress@11.1.4"}


def test_node_tar_lock_must_pin_the_requested_version(tmp_path: Path) -> None:
    version_dir = tmp_path / "9.9.9"
    version_dir.mkdir()
    (version_dir / "package.json").write_text(json.dumps({"dependencies": {"tar": "9.9.8"}}))
    (version_dir / "package-lock.json").write_text("{}")
    with pytest.raises(ip.UnsupportedVersionError, match="9.9.8"):
        nti.recipe("9.9.9", versions_dir=tmp_path)


# ---- the offline check command ----


def _runner(code: int, out: str, err: str = ""):
    calls: list[list[str]] = []

    def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, code, out, err)

    return run, calls


def test_check_passes_on_exact_version_and_runs_offline() -> None:
    run, calls = _runner(0, "7.4.4\n")
    assert ip.check(["--expect", "7.4.4", "--", "img", "-e", "x"], run) == 0
    assert calls[0][:5] == ["docker", "run", "--rm", "--network", "none"]


@pytest.mark.parametrize(
    ("code", "out", "args"),
    [
        (0, "7.4.3\n", ["--expect", "7.4.4"]),  # version mismatch inside the image
        (1, "", ["--expect", "7.4.4"]),  # check program failed
        (
            0,
            '{"oras_go_version":"v2.6.2"}',
            ["--expect", "v2.6.1", "--json-key", "oras_go_version"],
        ),
        (0, "not json", ["--expect", "v2.6.1", "--json-key", "k"]),
    ],
)
def test_check_fails_closed(code: int, out: str, args: list[str]) -> None:
    run, _ = _runner(code, out)
    assert ip.check([*args, "--", "img"], run) == 1


def test_check_reads_json_version() -> None:
    run, _ = _runner(0, 'noise\n{"oras_go_version":"v2.6.1","go_version":"go1"}\n')
    assert ip.check(["--expect", "v2.6.1", "--json-key", "oras_go_version", "--", "img"], run) == 0


def test_check_docker_unavailable_fails() -> None:
    def missing(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("docker")

    assert ip.check(["--expect", "1.0.0", "--", "img"], missing) == 1


# ---- the common runner never builds an image that is present ----


def test_present_image_is_reused_without_prepare(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = rt.load_adapter("oras-go")
    cells = adapter.cells(["2.6.1"], [])
    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:present")
    monkeypatch.setattr(rt, "prepare_image", lambda step: pytest.fail("must not prepare"))
    ready, errors = rt.resolve_images(adapter, cells, auto_prepare=True)
    assert ready == {"inodefence-oras-go:2.6.1": "sha256:present"} and errors == {}


def test_generic_helper_names_no_target() -> None:
    text = Path(ip.__file__).read_text(encoding="utf-8")
    for name in ("node-tar", "node_tar", "python-tarfile", "oras", "decompress", "tarfile"):
        assert name not in text


# ---- verify an already-present image before reusing it ----


def _recipe(expected: str = "7.4.4") -> ip.Recipe:
    return ip.Recipe(
        description="d", expected=expected, check=(ip.IMAGE_SLOT, "-e", "x"), build=("-f", "D")
    )


def test_check_existing_runs_the_recipe_check_against_the_image_and_passes() -> None:
    run, calls = _runner(0, "7.4.4\n")
    assert ip.check_existing(_recipe(), "img:ref", run) is None
    # it runs the existing image offline, never builds/pulls/retags
    assert calls[0][:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "img:ref" in calls[0] and all(c[0] != "docker" or c[1] != "build" for c in calls)


@pytest.mark.parametrize(
    ("code", "out"),
    [(0, "7.4.3\n"), (1, ""), (0, "")],  # wrong version, check failed, empty output
)
def test_check_existing_returns_a_reason_when_the_image_is_wrong(code: int, out: str) -> None:
    run, _ = _runner(code, out)
    reason = ip.check_existing(_recipe("7.4.4"), "img:ref", run)
    assert reason is not None and "7.4.4" in reason


def test_recipe_verify_existing_passes_through_a_matching_image() -> None:
    run, _ = _runner(0, "2.6.1\n")
    verify = ip.recipe_verify_existing(lambda cell: _recipe("2.6.1"), run)
    assert verify(_cell("oras-go", "2.6.1", "img:ref"), "sha256:present") is None


def test_recipe_verify_existing_reports_an_unsupported_version() -> None:
    def make(cell: rt.RunCell) -> ip.Recipe:
        raise ip.UnsupportedVersionError("9.9.9 not pinned")

    verify = ip.recipe_verify_existing(make)
    assert verify(_cell("oras-go", "9.9.9", "img:ref"), "sha256:present") == "9.9.9 not pinned"


def test_recipe_verify_existing_skips_a_cell_with_no_image() -> None:
    verify = ip.recipe_verify_existing(lambda cell: pytest.fail("no image -> no check"))
    cell = rt.RunCell(dirname="x", axes=TargetAxes(target_version="1"), image_ref=None)
    assert verify(cell, "") is None


def test_present_image_refused_when_verify_existing_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    base = rt.load_adapter("oras-go")
    adapter = dataclasses.replace(base, verify_existing=lambda cell, img: "reports 2.6.0")
    cells = adapter.cells(["2.6.1"], [])
    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:present")
    monkeypatch.setattr(rt, "prepare_image", lambda step: pytest.fail("must not prepare over it"))
    ready, errors = rt.resolve_images(adapter, cells, auto_prepare=True)
    assert ready == {} and "inodefence-oras-go:2.6.1" in errors
    assert "reports 2.6.0" in errors["inodefence-oras-go:2.6.1"]


def test_present_image_reused_when_verify_existing_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    base = rt.load_adapter("oras-go")
    seen: list[str] = []
    adapter = dataclasses.replace(base, verify_existing=lambda cell, img: seen.append(img) or None)
    cells = adapter.cells(["2.6.1"], [])
    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:present")
    ready, errors = rt.resolve_images(adapter, cells, auto_prepare=True)
    assert ready == {"inodefence-oras-go:2.6.1": "sha256:present"} and errors == {}
    assert seen == ["sha256:present"]  # the hook saw the resolved id

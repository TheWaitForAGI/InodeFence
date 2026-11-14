"""oras-go through the common target command (no docker: ``run_probe`` is replaced)."""

from __future__ import annotations

import io
import json
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import pytest
import scripts.regression_check as rc
import scripts.run_oras_go_target as rog
import scripts.run_target as rt

from inodefence.target_result import load_target_result


def _members(tar_bytes: bytes) -> list[tarfile.TarInfo]:
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        return archive.getmembers()


def test_registered_in_common_command() -> None:
    assert rt.TARGETS["oras-go"] == "scripts.run_oras_go_target:ADAPTER"
    assert rt.load_adapter("oras-go") is rog.ADAPTER


def test_relocate_keeps_types_order_and_contents_under_artifact_dir() -> None:
    by_name = {f.name: f for f in rc.build_fixtures()}
    original = _members(by_name["dir_symlink_write"].tar)
    moved = _members(rog.relocate(by_name["dir_symlink_write"].tar))
    assert [m.type for m in moved] == [m.type for m in original]
    assert [m.name for m in moved] == ["d/d", "d/d/sentinel.txt"]
    assert moved[0].linkname == "../../outside"
    assert moved[1].size == original[1].size

    hard = _members(rog.relocate(by_name["toplevel_hardlink"].tar))
    assert [(m.name, m.linkname) for m in hard] == [("d/link", "../outside/sentinel.txt")]


def test_fixture_set_is_regression_set_plus_repro_fixture() -> None:
    names = [f.name for f in rog.build_fixtures()]
    assert names == [f.name for f in rc.build_fixtures()] + ["cwd_relative_hardlink"]
    for fixture in rog.build_fixtures():
        assert all(m.name.startswith("d/") for m in _members(fixture.tar))


@pytest.mark.parametrize(
    ("versions", "filters", "message"),
    [
        (["2.6.1"], ["data"], "no extraction-filter axis"),
        (["v2.6.1"], [], "dotted numeric"),
    ],
)
def test_cells_reject_bad_axes(versions: list[str], filters: list[str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        rog.ADAPTER.cells(versions, filters)


def _fake_probe(shared_on: set[str]):
    def probe(tag: str, tar_b64: str, sentinel_b64: str) -> dict[str, Any]:
        import base64

        names = [m.name for m in _members(base64.b64decode(tar_b64))]
        hit = tag == "2.6.1" and names == ["d/evil"] and "cwd_relative_hardlink" in shared_on
        before = {"dev": "1", "ino": "9", "nlink": 1, "size": 30, "type": "reg"}
        after = {**before, "nlink": 2} if hit else before
        return {
            "declined": None if hit else {"message": "outside"},
            "reference_before": before,
            "reference_after": after,
            "shared_identity": ["extract/d/evil"] if hit else [],
        }

    return probe


def test_version_pair_writes_common_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rog.ogh, "run_probe", _fake_probe({"cwd_relative_hardlink"}))
    monkeypatch.setattr(rt, "engine_provenance", lambda image: rt.Provenance(None, True, image))
    monkeypatch.setattr(rt, "preflight", lambda *_: [])  # no docker here; the runner is faked
    argv = ["--target", "oras-go", "--version", "2.6.1", "--version", "2.6.2", "--out"]
    assert rt.main([*argv, str(tmp_path)]) == 1

    affected = load_target_result(tmp_path / "oras-go-2.6.1" / "result.json")
    fixed = load_target_result(tmp_path / "oras-go-2.6.2" / "result.json")
    data = json.loads((tmp_path / "oras-go-2.6.1" / "result.json").read_text(encoding="utf-8"))
    assert data["axes"] == {
        "target_version": "2.6.1",
        "runtime_version": None,
        "extraction_filter": None,
    }
    assert data["observed_contracts"] == ["C1", "C2"]
    assert all(case["c0"] is None for case in data["cases"])
    assert affected.violating_cases == ("cwd_relative_hardlink",)
    assert fixed.violating_cases == ()
    assert affected.executed == fixed.executed == len(rog.build_fixtures())
    assert data["provenance"]["image_ref"] == "inodefence-oras-go:2.6.1"
    assert "TARGET-RUN FAIL target=oras-go version=2.6.1" in capsys.readouterr().out


def test_probe_failure_is_run_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: Any) -> dict[str, Any]:
        raise subprocess.TimeoutExpired("docker", 600)

    monkeypatch.setattr(rog.ogh, "run_probe", timeout)
    runs = rog.ADAPTER.run(rog.ADAPTER.cells(["2.6.1"], [])[0])
    assert all(run.verdict.is_run_error for run in runs)
    assert all(run.verdict.c1 is None and run.verdict.c2 is None for run in runs)


def test_dry_run_through_common_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert rt.main(["--target", "oras-go", "--version", "2.6.1", "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["cells"]["oras-go-2.6.1"]["image"] == "inodefence-oras-go:2.6.1"
    assert len(plan["cells"]["oras-go-2.6.1"]["would_run"]) == len(rog.build_fixtures())
    assert not list(tmp_path.iterdir())


def test_image_recipe_is_the_committed_go_mod_pin() -> None:
    cells = rog.ADAPTER.cells(["2.6.1", "2.6.2"], [])
    assert rog.ADAPTER.image_build is not None
    for cell in cells:
        cmd = rog.ADAPTER.image_build(cell)
        assert cmd is not None and cmd[:4] == ["docker", "build", "-f", "tools/oras-go/Dockerfile"]
        assert cmd[-3:] == ["-t", cell.image_ref, "."]
    assert rog.pinned_recipe("2.6.1") != rog.pinned_recipe("2.6.2")
    assert rog.ADAPTER.image_build(rog.ADAPTER.cells(["9.9.9"], [])[0]) is None

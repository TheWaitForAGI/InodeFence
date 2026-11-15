"""python-tarfile symbolic runtimes (``latest``, ``X.Y``): resolve, record, refuse (no docker).

``docker`` is replaced by a fake that answers ``pull`` / ``run`` / ``image inspect`` for a small
table of official tags, so every path below runs without a daemon or network.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.run_python_tarfile_target as rpt
import scripts.run_target as rt

from inodefence.target_result import Verdict, load_target_result

DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
SHARED = {
    "runtime": "",
    "shared_identity": ["extract/link"],
    "declined": None,
    "reference_before": {"dev": "1", "ino": "2", "nlink": 1, "size": 9},
    "reference_after": {"dev": "1", "ino": "2", "nlink": 2, "size": 9},
    "nlink_before": 1,
    "nlink_after": 2,
    "extract_tree": {},
}


class FakeDocker:
    """``pull`` / ``run`` / ``image inspect`` over ``tags`` (tag -> python version reported)."""

    def __init__(self, tags: dict[str, str], *, pull_error: str | None = None) -> None:
        self.tags = tags
        self.pull_error = pull_error
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        if cmd[:2] == ["docker", "pull"]:
            if self.pull_error is not None:
                return subprocess.CompletedProcess(cmd, 1, "", self.pull_error)
            if cmd[2] not in self.tags:
                err = f"Error response from daemon: manifest for {cmd[2]} not found"
                return subprocess.CompletedProcess(cmd, 1, "", err)
            return subprocess.CompletedProcess(cmd, 0, f"Digest: {DIGEST}\nStatus: ok\n", "")
        if cmd[:2] == ["docker", "run"]:
            image = cmd[cmd.index("--entrypoint") + 2]
            return subprocess.CompletedProcess(cmd, 0, self.tags[image] + "\n", "")
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps([f"python@{OTHER}"]), "")
        raise AssertionError(f"unexpected docker call {cmd}")


@pytest.fixture(autouse=True)
def _clean_resolutions() -> Any:
    rpt._RESOLVED.clear()
    yield
    rpt._RESOLVED.clear()


def test_latest_resolves_through_the_official_slim_tag_and_is_recorded() -> None:
    docker = FakeDocker({"python:slim": "3.14.2"})
    assert rpt._resolve(["latest"], docker) == ["3.14.2"]
    assert docker.calls[0] == ["docker", "pull", "python:slim"]
    run = docker.calls[1]
    assert run[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "-v" not in run and "--mount" not in run
    spec, resolved_at, alias, alias_digest = rpt._RESOLVED["3.14.2"]
    assert (spec, alias, alias_digest) == ("latest", "python:slim", f"python@{DIGEST}")
    assert resolved_at.endswith("Z")


def test_minor_series_resolves_to_its_newest_patch() -> None:
    docker = FakeDocker({"python:3.13-slim": "3.13.9", "python:3.14-slim": "3.14.2"})
    assert rpt._resolve(["3.13", "3.14"], docker) == ["3.13.9", "3.14.2"]
    assert rpt._RESOLVED["3.13.9"][:1] == ("3.13",)


def test_exact_versions_pass_through_without_docker() -> None:
    docker = FakeDocker({})
    assert rpt._resolve(["3.12.16", "3.12.3"], docker) == ["3.12.16", "3.12.3"]
    assert docker.calls == []
    assert rpt._RESOLVED == {}


@pytest.mark.parametrize("reported", ["3.15.0rc1", "3.15.0b2", "3.15.0a7", "garbage", ""])
def test_pre_releases_and_unreadable_versions_are_never_resolved(reported: str) -> None:
    with pytest.raises(ValueError, match="not a stable exact"):
        rpt._resolve(["latest"], FakeDocker({"python:slim": reported}))
    assert rpt._RESOLVED == {}


def test_series_tag_reporting_another_series_is_refused() -> None:
    with pytest.raises(ValueError, match="outside 3.13"):
        rpt._resolve(["3.13"], FakeDocker({"python:3.13-slim": "3.14.2"}))


def test_missing_series_and_unreachable_registry_are_distinct_failures() -> None:
    with pytest.raises(ValueError, match="no such official image"):
        rpt._resolve(["3.99"], FakeDocker({}))
    unreachable = FakeDocker({}, pull_error="dial tcp: lookup registry-1.docker.io: no such host")
    with pytest.raises(ValueError, match="registry unreachable"):
        rpt._resolve(["latest"], unreachable)


@pytest.mark.parametrize(
    "bad",
    [
        "3",
        "3.12-rc",
        "3.12.16-slim",
        "3.12.x",
        "python:3.12",
        "docker.io/library/python:3.12",
        "python@" + DIGEST,
        DIGEST,
        "3.12;id",
        "3.12/../x",
        "$(id)",
        "~3.12",
        ">=3.12",
        "3.12 || 3.13",
        "slim",
        "Latest",
        "",
    ],
)
def test_other_forms_are_refused_before_any_docker_call(bad: str) -> None:
    docker = FakeDocker({"python:slim": "3.14.2"})
    with pytest.raises(ValueError):
        rpt._resolve(["latest", bad], docker)  # the bad value is refused before `latest` resolves
    assert docker.calls == []
    with pytest.raises(ValueError):
        rpt._adapter_cells([bad], ["data"])


def test_describe_records_official_image_and_rechecks_version(tmp_path: Path) -> None:
    rpt._resolve(["latest"], FakeDocker({"python:slim": "3.14.2"}))
    (cell,) = rpt._adapter_cells(["3.14.2"], ["data"])
    assert cell.dirname == "python-tarfile-py3.14.2-data"
    assert cell.image_ref == "python:3.14.2-slim"
    prep = rpt._describe(cell, tmp_path, FakeDocker({"python:3.14.2-slim": "3.14.2"}))
    assert prep is not None
    assert prep.method == "official-image"
    assert prep.requested_spec == "latest"
    assert prep.requested_version == prep.installed_version == "3.14.2"
    assert f"python@{OTHER}" in prep.recipe and f"python@{DIGEST}" in prep.recipe
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="runs python '3.14.1'"):
        rpt._describe(cell, tmp_path, FakeDocker({"python:3.14.2-slim": "3.14.1"}))


def test_exact_request_has_no_preparation(tmp_path: Path) -> None:
    (cell,) = rpt._adapter_cells(["3.12.16"], ["data"])
    docker = FakeDocker({})
    assert rpt._describe(cell, tmp_path, docker) is None
    assert docker.calls == []


def _common_command(monkeypatch: pytest.MonkeyPatch, docker: FakeDocker) -> None:
    def run_one(runtime: str, flt: str, tar_b64: str, **_: Any) -> dict[str, Any]:
        return {**SHARED, "runtime": runtime, "extraction_filter": flt}

    monkeypatch.setattr(rpt.pti, "run_one", run_one)
    monkeypatch.setattr(rpt.ip, "check", lambda argv, runner=None: 0)  # present images pass
    monkeypatch.setattr(rpt.subprocess, "run", docker)
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(rt, "image_id", lambda ref: f"sha256:{ref}")
    monkeypatch.setattr(rt, "engine_provenance", lambda ref: rt.Provenance(None, True, ref, None))


def test_latest_through_common_command_writes_exact_names_and_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    docker = FakeDocker({"python:slim": "3.14.2", "python:3.14.2-slim": "3.14.2"})
    _common_command(monkeypatch, docker)
    argv = ["--target", "python-tarfile", "--version", "latest", "--extraction-filter", "data"]
    assert rt.main([*argv, "--out", str(tmp_path)]) == 1
    path = tmp_path / "python-tarfile-py3.14.2-data" / "result.json"
    result = load_target_result(path)
    assert result.verdict is Verdict.FAIL
    assert result.axes.runtime_version == "3.14.2"
    assert result.provenance.image_ref == "python:3.14.2-slim"
    assert result.label == "demo run"
    assert result.preparation is not None and result.preparation.requested_spec == "latest"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["python-tarfile-py3.14.2-data"]
    assert "latest" not in json.dumps(json.loads(path.read_text())["axes"])
    out = capsys.readouterr().out
    assert "TARGET-RUN RESOLVE python-tarfile latest -> 3.14.2" in out


def test_exact_through_common_command_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _common_command(monkeypatch, FakeDocker({}))
    argv = ["--target", "python-tarfile", "--version", "3.12.16", "--extraction-filter", "data"]
    assert rt.main([*argv, "--out", str(tmp_path)]) == 1
    data = json.loads((tmp_path / "python-tarfile-py3.12.16-data" / "result.json").read_text())
    assert "preparation" not in data
    assert data["label"] == "demo run"


def test_version_mismatch_after_run_gives_no_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker = FakeDocker({"python:slim": "3.14.2", "python:3.14.2-slim": "3.14.1"})
    _common_command(monkeypatch, docker)
    argv = ["--target", "python-tarfile", "--version", "latest", "--extraction-filter", "data"]
    assert rt.main([*argv, "--out", str(tmp_path)]) == rt.SETUP_ERROR
    assert not list(tmp_path.rglob("result.json"))


def test_resolution_failure_exits_3_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _common_command(monkeypatch, FakeDocker({}))
    argv = ["--target", "python-tarfile", "--version", "3.99", "--extraction-filter", "data"]
    with pytest.raises(SystemExit) as raised:
        rt.main([*argv, "--out", str(tmp_path)])
    assert raised.value.code == rt.SETUP_ERROR
    assert not list(tmp_path.iterdir())


def test_dry_run_does_not_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    docker = FakeDocker({})
    _common_command(monkeypatch, docker)
    argv = ["--target", "python-tarfile", "--version", "latest", "--version", "3.13"]
    assert rt.main([*argv, "--extraction-filter", "data", "--dry-run"]) == 0
    assert docker.calls == []
    plan = json.loads(capsys.readouterr().out)
    assert sorted(plan["cells"]) == [
        "python-tarfile-py3.13-data (resolved at run time)",
        "python-tarfile-pylatest-data (resolved at run time)",
    ]
    cell = plan["cells"]["python-tarfile-pylatest-data (resolved at run time)"]
    assert cell["image"] is None
    assert "resolved at run time" in cell["would_run"][0]["note"]
    assert not list(tmp_path.iterdir())


def test_symbolic_runtime_with_both_axes_varied_is_refused() -> None:
    argv = ["--target", "python-tarfile", "--version", "latest", "--version", "3.13"]
    argv += ["--extraction-filter", "fully_trusted", "--extraction-filter", "data", "--dry-run"]
    with pytest.raises(SystemExit) as raised:
        rt.main(argv)
    assert raised.value.code == rt.SETUP_ERROR


def test_resolved_image_is_still_pulled_only_from_the_official_repository() -> None:
    recipe = rpt.image_recipe("3.14.2")
    assert recipe.pull == "python:3.14.2-slim"
    with pytest.raises(rpt.ip.UnsupportedVersionError):
        rpt.image_recipe("latest")


# ---- reuse of a present runtime image is re-checked (common verify_existing hook) ----


def test_present_runtime_image_must_still_report_its_version_before_reuse() -> None:
    assert rpt.ADAPTER.verify_existing is not None
    (cell,) = rpt._adapter_cells(["3.14.10"], ["data"])
    calls: list[list[str]] = []

    def reports(version: str):
        def runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, version + "\n", "")

        return runner

    verify = rpt.ip.recipe_verify_existing(rpt._existing_recipe, reports("3.14.10"))
    assert verify(cell, "sha256:" + "a" * 64) is None
    assert calls[0][:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "python:3.14.10-slim" in calls[0]
    wrong = rpt.ip.recipe_verify_existing(rpt._existing_recipe, reports("3.14.9"))
    reason = wrong(cell, "sha256:" + "a" * 64)
    assert reason is not None and "3.14.10" in reason
    (symbolic,) = rpt._adapter_cells(["latest"], ["data"])  # dry-run cell: no image, skipped
    assert verify(symbolic, "") is None

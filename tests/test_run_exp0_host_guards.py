"""run_exp0 --jobs with the shared host guards (#336): preflight, postflight, records, cleanup."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0

from test_run_exp0 import (
    BEFORE,
    DIGEST,
    DIGEST_B,
    TARGET_IMAGES,
    _deadline_setup,
    _fake_runner,
    _result_lines,
)
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine

CONTROLLER_ID = "sha256:" + "c" * 64
HELPER_ID = "sha256:" + "d" * 64


class FakeDocker:
    """The docker CLI as the guards call it; ``ids`` can change between calls."""

    def __init__(self) -> None:
        self.ids = {
            "inodefence-node-tar-effect:7.5.2": DIGEST,
            "inodefence-node-tar-effect:7.9.9": DIGEST_B,
            "inodefence-controller:local": CONTROLLER_ID,
            "inodefence-helper:local": HELPER_ID,
        }
        self.server = "29.8.0"
        self.leftover = ""
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str, timeout: float = 60.0) -> str:
        self.calls.append(args)
        if args[:1] == ("version",):
            return self.server
        if args[:2] == ("image", "inspect"):
            return self.ids[args[2]]
        if args[:1] == ("ps",):
            return self.leftover if "-a" in args else ""
        if args[:2] == ("volume", "ls"):
            return ""
        raise AssertionError(args)


#: Captured at import, before any fixture replaces them.
REAL_PREFLIGHT = run_exp0.host_preflight
REAL_POSTFLIGHT = run_exp0.host_postflight


@pytest.fixture
def real_guards(clean_engine: None, monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    """clean_engine stubs the guards; put the real ones back, on a fake docker CLI."""
    docker = FakeDocker()
    monkeypatch.setattr(run_exp0, "host_preflight", REAL_PREFLIGHT)
    monkeypatch.setattr(run_exp0, "host_postflight", REAL_POSTFLIGHT)
    monkeypatch.setattr(run_exp0, "guard_docker", lambda context: docker)
    monkeypatch.setattr(run_exp0, "start_host_recording", lambda *a, **k: lambda: [])
    return docker


def _host_dir(out: Path) -> Path:
    return out / run_exp0.HOST_RECORD_DIR


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_preflight_and_postflight_records_name_every_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    run_exp0.main(args)
    [pre] = sorted(_host_dir(out).glob("preflight-*.json"))
    [post] = sorted(_host_dir(out).glob("postflight-*.json"))
    before, after = json.loads(pre.read_text()), json.loads(post.read_text())
    for record in (before, after):
        assert record["image_ids"]["inodefence-controller:local"] == CONTROLLER_ID
        assert record["image_ids"]["inodefence-helper:local"] == HELPER_ID
        assert record["image_ids"]["inodefence-node-tar-effect:7.5.2"] == DIGEST
        assert record["docker_server"] == "29.8.0" and record["problems"] == []
        assert record["shared_path_sha256"]  # every shared execution file hashed
    assert before["recording"]["host_sampler"]["stop_policy"] is None
    assert before["recording"]["ping_socket"] is None
    guards_record = json.loads((out / "matrix.json").read_text())["host_guards"]
    assert guards_record["preflight"] == pre.name and guards_record["postflight"] == post.name
    assert guards_record["postflight_problems"] == []


@pytest.mark.usefixtures("admit_fixture_holdout")
@pytest.mark.parametrize("problem", ["engine", "image", "leftover"])
def test_a_preflight_problem_starts_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    real_guards: FakeDocker,
    problem: str,
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    if problem == "engine":
        monkeypatch.setattr(run_exp0, "docker_engine_version", lambda context: "28.0.0")
    elif problem == "image":
        real_guards.ids["inodefence-node-tar-effect:7.5.2"] = "sha256:" + "e" * 64
    else:
        real_guards.leftover = "inodefence-local-controller-old"
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert run_exp0.main(args) == 2
    assert runner.calls == []
    assert "refusing to run (host preflight)" in capsys.readouterr().err
    [pre] = _host_dir(out).glob("preflight-*.json")
    assert json.loads(pre.read_text())["problems"]
    assert not (out / "matrix.json").exists() or "cells" not in json.loads(
        (out / "matrix.json").read_text()
    )
    assert _result_lines(out) == [] if (out / "cell-results.jsonl").exists() else True


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_a_change_during_the_run_is_recorded_by_the_postflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    inner = _fake_runner(TARGET_IMAGES)

    def runner(cell: Any, output: Path, env: Any, bash: str, **limits: Any) -> Any:
        real_guards.ids["inodefence-helper:local"] = "sha256:" + "f" * 64  # rebuilt mid-run
        return inner(cell, output, env, bash, **limits)

    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main(args)
    problems = json.loads((out / "matrix.json").read_text())["host_guards"]["postflight_problems"]
    assert "image_ids changed during the run" in problems


def test_a_runner_failure_after_the_start_terminates_the_child(tmp_path: Path) -> None:
    """Same refusal as before #336 (the error escapes to run_target_cell); the child is ended."""

    class Child:
        pid = 4242
        returncode = None

        def __init__(self) -> None:
            self.terminated = False

        def poll(self) -> Any:
            return None if not self.terminated else -15

        def wait(self, timeout: float | None = None) -> int:
            if not self.terminated:
                raise OSError("wait failed")
            self.returncode = -15
            return -15

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.terminated = True

    child = Child()
    cell = run_exp0.TargetCell(
        "demo-historical",
        "7.5.2",
        run_exp0.Arm("R", "unretained-seed-restart-v1", "uniform-mutation-v1"),
        1,
        2,
        target_id="node-tar-7.5.2",
        subdir="node-tar-7.5.2",
    )
    (tmp_path / "node-tar-7.5.2").mkdir()
    with pytest.raises(OSError, match="wait failed") as raised:
        run_exp0.run_cell_with_watchdog(
            cell, tmp_path, {}, "/bin/bash", limit_seconds=5, popen=lambda *a, **k: child
        )
    assert child.terminated
    assert any("exited with -15" in note for note in raised.value.__notes__)
    log = next(tmp_path.rglob("*.log")).read_text()
    assert "[runner] OSError: wait failed" in log


def test_record_only_settings_are_the_same_on_every_host() -> None:
    from scripts import launcher_guards as guards

    settings = run_exp0.recording_settings(guards.Recorders())
    assert settings == run_exp0.recording_settings(guards.Recorders())
    assert settings["host_sampler"] == {
        "enabled": True,
        "stop_policy": None,
        "seconds": guards.PROC_SAMPLE_SECONDS,
        "probe_seconds": guards.DOCKER_PROBE_SECONDS,
    }
    assert settings["docker_events"]["enabled"] is True


def test_guard_images_cover_targets_and_local_images(tmp_path: Path) -> None:
    from test_run_exp0 import _ledger, _plan, _targets_file

    _, sha = _ledger(tmp_path)
    images = run_exp0.guard_images(_plan(_targets_file(tmp_path, ledger_sha=sha)))
    assert images == {
        "inodefence-node-tar-effect:7.5.2": DIGEST,
        "inodefence-node-tar-effect:7.9.9": DIGEST_B,
        "inodefence-controller:local": None,
        "inodefence-helper:local": None,
    }
    assert subprocess  # imported for the Child double's interface

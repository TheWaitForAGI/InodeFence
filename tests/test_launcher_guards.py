"""Shared launcher guards: the pieces run_exp0 --jobs imports from the benchmark path."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from scripts import launcher_guards as guards


def fake_docker(responses: dict[tuple[str, ...], str], failing: tuple[str, ...] = ()) -> Any:
    calls: list[tuple[str, ...]] = []

    def docker(*args: str) -> str:
        calls.append(args)
        if args[: len(failing)] == failing and failing:
            raise RuntimeError(f"docker {' '.join(args)}: daemon-unreachable")
        return responses.get(args, "")

    docker.calls = calls  # type: ignore[attr-defined]
    return docker


IMAGES = {"target:1": "sha256:t", "local:1": None}
OK = {
    ("version", "--format", "{{.Server.Version}}"): "29.8.0",
    ("image", "inspect", "target:1", "--format", "{{.Id}}"): "sha256:t",
    ("image", "inspect", "local:1", "--format", "{{.Id}}"): "sha256:l",
}


def test_docker_preflight_accepts_a_quiet_matching_host() -> None:
    facts, problems = guards.docker_preflight(
        engine="29.8.0", images=IMAGES, docker=fake_docker(OK), residual=list
    )
    assert problems == []
    assert facts == {
        "docker_server": "29.8.0",
        "image_ids": {"target:1": "sha256:t", "local:1": "sha256:l"},
    }


def test_docker_preflight_reports_every_refusal() -> None:
    responses = {
        **OK,
        ("version", "--format", "{{.Server.Version}}"): "28.0.0",
        ("image", "inspect", "target:1", "--format", "{{.Id}}"): "sha256:other",
        ("ps", "--format", "{{.Names}}"): "someone-else",
    }
    _facts, problems = guards.docker_preflight(
        engine="29.8.0",
        images=IMAGES,
        docker=fake_docker(responses),
        residual=lambda: ["inodefence-local-runtime-x"],
    )
    assert problems == [
        "docker engine 28.0.0 != 29.8.0",
        "target:1 is sha256:other, not sha256:t",
        "other containers are running: ['someone-else']",
        "residual benchmark resources exist: ['inodefence-local-runtime-x']",
    ]


def test_docker_preflight_failure_is_one_refusal_without_facts() -> None:
    facts, problems = guards.docker_preflight(
        engine="29.8.0", images=IMAGES, docker=fake_docker(OK, failing=("version",))
    )
    assert facts == {}
    assert problems == ["docker: docker version --format {{.Server.Version}}: daemon-unreachable"]


def test_residual_resources_lists_containers_and_volumes() -> None:
    docker = fake_docker(
        {
            ("ps", "-a", "--filter", "name=inodefence-", "--format", "{{.Names}}"): "c1\nc2",
            (
                "volume",
                "ls",
                "--filter",
                "name=inodefence-local-",
                "--format",
                "{{.Name}}",
            ): "v1",
        }
    )
    assert guards.residual_resources(docker) == ["c1", "c2", "v1"]


def test_residual_status_never_raises() -> None:
    assert guards.residual_status(lambda: ["x"]) == {"status": "observed", "resources": ["x"]}

    def broken() -> list[str]:
        raise RuntimeError("daemon-unreachable")

    assert guards.residual_status(broken) == {
        "status": "unknown",
        "error": "RuntimeError: daemon-unreachable",
    }


def test_terminate_started_reaps_a_running_child() -> None:
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE
    )
    note = guards.terminate_started(child)
    assert child.poll() is not None
    assert note.startswith(f"started process {child.pid} exited with ")
    assert "still requires verification" in note
    assert child.stdin is not None
    child.stdin.close()


def test_terminate_started_reports_its_own_failure() -> None:
    class Broken:
        pid = 1

        def poll(self) -> None:
            raise OSError("no such process table")

    note = guards.terminate_started(Broken())
    assert note.startswith("started process cleanup failed: OSError: no such process table")


def test_publish_json_once_never_replaces(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    guards.publish_json_once(path, {"first": 1})
    with pytest.raises(FileExistsError):
        guards.publish_json_once(path, {"second": 2})
    assert json.loads(path.read_text()) == {"first": 1}
    assert sorted(item.name for item in tmp_path.iterdir()) == ["evidence.json"]


def test_sample_host_record_only_writes_one_sample_and_stops(tmp_path: Path) -> None:
    stop = threading.Event()
    stop.set()  # one sample, then stop.wait returns at once
    path = tmp_path / "samples.jsonl"
    guards.sample_host(
        path,
        stop,
        disk_fraction=lambda: 0.25,
        counters=lambda: {"memory": {"MemTotal": 1}},
        docker=fake_docker({("ps", "--format", "{{.Names}}"): "a b"}),
    )
    (line,) = path.read_text().splitlines()
    sample = json.loads(line)
    assert sample["disk_fraction"] == 0.25
    assert sample["containers"] == ["a", "b"]
    assert sample["memory"] == {"MemTotal": 1}
    assert {"realtime", "monotonic", "monotonic_raw", "docker_ps_seconds"} <= sample.keys()


def test_sample_host_passes_samples_to_the_injected_policy(tmp_path: Path) -> None:
    stop = threading.Event()
    stop.set()
    seen: list[dict[str, Any]] = []
    guards.sample_host(
        tmp_path / "s.jsonl",
        stop,
        disk_fraction=lambda: 0.5,
        on_sample=seen.append,
        counters=dict,
        docker=fake_docker({}, failing=("ps",)),
    )
    assert len(seen) == 1
    assert "daemon-unreachable" in seen[0]["docker_ps_error"]


def test_sample_host_failure_goes_to_the_failure_hook_or_raises(tmp_path: Path) -> None:
    def broken() -> float:
        raise OSError("statvfs failed")

    failures: list[Exception] = []
    guards.sample_host(
        tmp_path / "s.jsonl",
        threading.Event(),
        disk_fraction=broken,
        on_failure=failures.append,
        counters=dict,
    )
    assert [str(error) for error in failures] == ["statvfs failed"]
    with pytest.raises(OSError, match="statvfs failed"):
        guards.sample_host(
            tmp_path / "t.jsonl", threading.Event(), disk_fraction=broken, counters=dict
        )

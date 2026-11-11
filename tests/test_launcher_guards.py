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


def _serve_once(path: Path, reply: bytes) -> threading.Thread:
    import socket

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)

    def handle() -> None:
        with server:
            connection, _ = server.accept()
            with connection:
                connection.recv(4096)
                connection.sendall(reply)

    thread = threading.Thread(target=handle)
    thread.start()
    return thread


def test_ping_daemon_reports_ok_and_latency(tmp_path: Path) -> None:
    sock = tmp_path / "d.sock"
    server = _serve_once(sock, b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nOK")
    record = guards.ping_daemon(sock)
    server.join(30)
    assert record["ok"] is True
    assert record["status"] == "HTTP/1.0 200 OK"
    assert record["seconds"] >= 0 and "realtime" in record


def test_ping_daemon_never_raises(tmp_path: Path) -> None:
    record = guards.ping_daemon(tmp_path / "absent.sock")
    assert record["ok"] is False
    assert record["error"].startswith(("FileNotFoundError", "ConnectionRefusedError"))


def test_ping_loop_records_until_stopped(tmp_path: Path) -> None:
    stop = threading.Event()
    stop.set()
    path = tmp_path / "ping.jsonl"
    guards.ping_loop(path, stop, tmp_path / "s", ping=lambda _p: {"ok": True})
    assert [json.loads(line) for line in path.read_text().splitlines()] == [{"ok": True}]


class ScriptedStop:
    """``wait`` runs the next step between iterations; the last step ends the loop."""

    def __init__(self, *steps: Any) -> None:
        self.steps = list(steps)

    def wait(self, _seconds: float) -> bool:
        self.steps.pop(0)()
        return not self.steps


def test_tail_log_copies_appends_and_survives_rotation(tmp_path: Path) -> None:
    source, copy = tmp_path / "desktop.log", tmp_path / "copy.log"
    source.write_bytes(b"one\n")

    def append() -> None:
        with source.open("ab") as stream:
            stream.write(b"two\n")

    def rotate() -> None:
        source.unlink()
        source.write_bytes(b"three\n")

    def vanish() -> None:
        source.unlink()

    def reappear() -> None:
        source.write_bytes(b"four\n")

    stop = ScriptedStop(append, rotate, vanish, reappear, lambda: None)
    guards.tail_log(source, copy, stop)  # type: ignore[arg-type]
    assert copy.read_bytes() == (
        b"one\ntwo\n\n[inodefence-log-tail: source rotated or truncated]\nthree\nfour\n"
    )
    assert source.read_bytes() == b"four\n"  # read-only on the source


def test_recorders_are_off_by_default_and_record_when_enabled(tmp_path: Path) -> None:
    stop = threading.Event()
    assert guards.start_recorders(tmp_path, guards.Recorders(), stop) == []
    log = tmp_path / "source.log"
    log.write_bytes(b"line\n")
    stop.set()  # each recorder makes one pass, then returns
    threads = guards.start_recorders(
        tmp_path,
        guards.Recorders(ping_socket=tmp_path / "absent.sock", desktop_log=log),
        stop,
    )
    for thread in threads:
        thread.join(30)
    assert len(threads) == 2
    (ping,) = [json.loads(line) for line in (tmp_path / "ping.jsonl").read_text().splitlines()]
    assert ping["ok"] is False
    assert (tmp_path / "desktop.log").read_bytes() == b"line\n"

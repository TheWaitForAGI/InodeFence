"""effect-replay-case: host validates and sends one stdin line; controller re-validates and runs it.

No Docker: the host test stops at the first Docker use, the controller test replaces the broker
client, backend and replay body with recorders.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import container_controller, container_host
from scripts.effect_replay import CASE_REPLAY_MODE

from inodefence.builder import build_tar
from inodefence.case_replay import CaseReplayError, load_replay_request, replay_input_line
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.live_exploration import LiveRecorder, LiveRunMeta, LiveStep

IMAGE = "sha256:" + "c" * 64
SETTINGS = {
    "sentinel_count": None,
    "sentinel_seed": None,
    "observer_integrity_policy": "stop",
    "profile": "full",
}


def _line(tmp_path: Path) -> str:
    meta = LiveRunMeta("node-tar", "7.5.1", 1, 10, image_id=IMAGE, run_settings=SETTINGS)
    case = minimal_seed_corpus()[1]
    rec = LiveRecorder(tmp_path / "live", meta)
    rec.on_step(
        LiveStep(
            index=0, case_id=case.case_id, status="success", c1=True, tar_bytes=build_tar(case)
        )
    )
    return replay_input_line(load_replay_request(tmp_path / "live/violations/run-000001"))


def _host_argv(*extra: str, mode: str = CASE_REPLAY_MODE) -> list[str]:
    return [
        "container_host",
        "--context",
        "default",
        "--controller",
        "inodefence-controller:test",
        "--volume",
        "inodefence-runtime",
        "--image",
        IMAGE,
        "--evidence",
        "/tmp/inodefence-replay.json",
        *extra,
        mode,
    ]


class _StopHere(Exception):
    pass


def _stop_at_docker(monkeypatch) -> None:
    def refuse(*args, **kwargs):
        raise _StopHere

    monkeypatch.setattr(container_host, "DockerCLI", refuse)
    monkeypatch.setattr(container_host.shutil, "which", lambda name: "/usr/bin/docker")


@pytest.mark.parametrize(
    ("content", "extra_mode", "message"),
    [
        (None, None, "required for effect-replay-case"),  # replay mode without an input
        ("x", "effect-demo-explore", "accepted nowhere else"),  # input on another mode
        ('{"schema": "nope"}\n', None, "replay input refused"),
        ("line one\nline two\n", None, "exactly one line"),
    ],
)
def test_host_refuses_bad_replay_input_before_any_container(
    tmp_path: Path, monkeypatch, capsys, content, extra_mode, message
) -> None:
    _stop_at_docker(monkeypatch)
    extra: list[str] = []
    if content is not None:
        path = tmp_path / "input.jsonl"
        path.write_text(content)
        extra = ["--replay-input", str(path)]
    argv = _host_argv(*extra, mode=extra_mode or CASE_REPLAY_MODE)
    if extra_mode == "effect-demo-explore":
        argv[-1:-1] = ["--tar-version", "7.5.1"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exit_info:
        container_host.main()
    assert exit_info.value.code == 2
    assert message in capsys.readouterr().err


def test_host_accepts_a_valid_line_and_goes_on_to_docker(tmp_path: Path, monkeypatch) -> None:
    _stop_at_docker(monkeypatch)
    path = tmp_path / "input.jsonl"
    path.write_text(_line(tmp_path))
    monkeypatch.setattr(sys, "argv", _host_argv("--replay-input", str(path)))
    with pytest.raises(_StopHere):  # validation passed; the next step is the Docker CLI
        container_host.main()


def _controller_argv(evidence: Path) -> list[str]:
    return [
        "container_controller",
        "--controller",
        "ctrl",
        "--volume",
        "vol",
        "--owner",
        "owner",
        "--image",
        IMAGE,
        "--evidence",
        str(evidence),
        CASE_REPLAY_MODE,
    ]


def test_controller_reads_revalidates_and_dispatches_the_replay(
    tmp_path: Path, monkeypatch
) -> None:
    line = _line(tmp_path)
    calls: list = []
    monkeypatch.setattr(sys, "argv", _controller_argv(tmp_path / "out.json"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(line + '{"broker": "stream"}\n'))
    monkeypatch.setattr(container_controller, "StdioDockerClient", lambda r, w: SimpleNamespace())
    monkeypatch.setattr(container_controller, "ObservedDockerClient", lambda c: c)
    monkeypatch.setattr(container_controller, "ContainerExecutionBackend", lambda *a: "backend")
    monkeypatch.setattr(container_controller, "StallRecovery", lambda o, owner: "recovery")
    monkeypatch.setattr(
        container_controller,
        "run_case_replay",
        lambda backend, image, evidence, replay_input, recovery: (
            calls.append((backend, image, evidence, replay_input, recovery)) or 0
        ),
    )
    assert container_controller.main() == 0
    ((backend, image, evidence, replay_input, recovery),) = calls
    assert (backend, image, recovery) == ("backend", IMAGE, "recovery")
    assert replay_input.case == minimal_seed_corpus()[1] and replay_input.rounds == 3
    # the broker stream after the input line is left for the Docker client
    assert sys.stdin.readline() == '{"broker": "stream"}\n'


def test_controller_refuses_a_tampered_line_before_brokering(tmp_path: Path, monkeypatch) -> None:
    data = json.loads(_line(tmp_path))
    data["tar_sha256"] = "0" * 64
    monkeypatch.setattr(sys, "argv", _controller_argv(tmp_path / "out.json"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(data) + "\n"))
    created: list = []
    monkeypatch.setattr(container_controller, "StdioDockerClient", lambda r, w: created.append(1))
    with pytest.raises(CaseReplayError, match="host's"):
        container_controller.main()
    assert not created  # no broker client was ever created

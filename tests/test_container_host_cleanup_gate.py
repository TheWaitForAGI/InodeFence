"""The broker's final target cleanup reports unknown resources to the start gate.

Before this, a failed target cleanup raised without a marker or a verdict, and
the smoke trap (which checks only the controller and volume) could commit S
while a target container remained.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from scripts import container_host

from inodefence.execution import start_gate
from inodefence.execution.docker_client import BackendError

GATE_SCRIPT = Path(start_gate.__file__).resolve()


class Events:
    """Records stderr writes and gate records in one order."""

    def __init__(self) -> None:
        self.order: list[str] = []

    def write(self, text: str) -> int:
        if text.strip():
            self.order.append("stderr:" + text.strip())
        return len(text)

    def flush(self) -> None:
        pass


@pytest.fixture
def live_cell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """A real child registered as cell 'a'; the broker runs with its gate env."""
    gate = start_gate.StartGate(tmp_path / "gate")
    child = gate.popen("a")(
        [sys.executable, "-I", "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE
    )
    monkeypatch.setenv(start_gate.GATE_DIR_ENV, str(gate.directory))
    monkeypatch.setenv(start_gate.GATE_CELL_ENV, "a")
    yield gate
    assert child.stdin is not None
    child.stdin.close()
    child.wait(timeout=30)


def failing_remove(*_args: Any) -> None:
    raise BackendError("container removal could not be verified")


def test_failed_target_cleanup_commits_unknown_before_marker(
    live_cell: start_gate.StartGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = Events()
    real_record = start_gate.record_verdict

    def observed_record(*args: Any, **kwargs: Any) -> None:
        real_record(*args, **kwargs)
        events.order.append("record:U")

    monkeypatch.setattr(container_host.start_gate, "record_verdict", observed_record)
    monkeypatch.setattr(container_host, "remove_owned", failing_remove)
    monkeypatch.setattr(sys, "stderr", events)
    with pytest.raises(ExceptionGroup, match="host target cleanup failed"):
        container_host.cleanup_targets(object(), {"inodefence-" + "0" * 32}, "owner")
    assert events.order[0] == "record:U"
    assert events.order[1].startswith("stderr:INODEFENCE_CLEANUP_UNKNOWN: host target cleanup")
    verdict = live_cell.verdict("a")
    assert verdict is not None and verdict[0] == "U"
    assert "BackendError: container removal could not be verified" in verdict[1]
    with pytest.raises(start_gate.StartDenied, match="a cleanup resource state unknown: host"):
        live_cell.popen("b")(["true"])


def test_trap_cannot_turn_the_broker_unknown_into_clean(
    live_cell: start_gate.StartGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(container_host, "remove_owned", failing_remove)
    with pytest.raises(ExceptionGroup):
        container_host.cleanup_targets(object(), {"inodefence-" + "0" * 32}, "owner")
    # The smoke trap later verifies controller and volume and tries S.
    trap = subprocess.run(
        [sys.executable, "-I", str(GATE_SCRIPT), "record", "S"],
        env=dict(os.environ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert trap.returncode == 1
    assert "UNKNOWN verdict is final" in trap.stderr
    verdict = live_cell.verdict("a")
    assert verdict is not None and verdict[0] == "U"


def test_interrupted_target_cleanup_commits_unknown(
    live_cell: start_gate.StartGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(*_args: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(container_host, "remove_owned", interrupted)
    with pytest.raises(KeyboardInterrupt):
        container_host.cleanup_targets(object(), {"inodefence-" + "0" * 32}, "owner")
    verdict = live_cell.verdict("a")
    assert verdict is not None and verdict[0] == "U"
    assert verdict[1].startswith("host target cleanup interrupted: KeyboardInterrupt")


def test_clean_target_cleanup_records_nothing(
    live_cell: start_gate.StartGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    removed: list[str] = []
    monkeypatch.setattr(container_host, "remove_owned", lambda _c, name, _o: removed.append(name))
    container_host.cleanup_targets(object(), {"inodefence-" + "1" * 32}, "owner")
    assert removed == ["inodefence-" + "1" * 32]
    assert live_cell.verdict("a") is None


def test_without_gate_environment_behavior_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(start_gate.GATE_DIR_ENV, raising=False)
    monkeypatch.delenv(start_gate.GATE_CELL_ENV, raising=False)
    monkeypatch.setattr(container_host, "remove_owned", failing_remove)
    with pytest.raises(ExceptionGroup, match="host target cleanup failed"):
        container_host.cleanup_targets(object(), {"inodefence-" + "0" * 32}, "owner")
    assert capsys.readouterr().err == ""
    assert list(tmp_path.iterdir()) == []


def test_unknown_record_failure_still_prints_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(start_gate.GATE_DIR_ENV, str(tmp_path / "missing-gate"))
    monkeypatch.setenv(start_gate.GATE_CELL_ENV, "a")
    monkeypatch.setattr(container_host, "remove_owned", failing_remove)
    with pytest.raises(ExceptionGroup):
        container_host.cleanup_targets(object(), {"inodefence-" + "0" * 32}, "owner")
    err = capsys.readouterr().err
    assert "start gate: U not recorded" in err
    assert "INODEFENCE_CLEANUP_UNKNOWN: host target cleanup failed" in err
    assert not (tmp_path / "missing-gate").exists()

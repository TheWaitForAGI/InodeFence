"""The shipped launch diagnostics (HealthObserver) through W1's session; Docker is always faked."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from inodefence.drivers.runtime import diagnostics, health
from inodefence.drivers.runtime.hooks import LaunchArtifacts, LaunchBlocked
from inodefence.drivers.runtime.session import RuntimeSession

SCRIPT = Path("/repo/scripts/local_python_tarfile_explore.sh")
ENV = {"RUN_ID": "py3.12.16-data-123-20"}
DAEMON_OK = health.DaemonStatus(health.DaemonState.OK, "server 29.9.3", "29.9.3")


class Runner:
    def __init__(self, returncode: int = 0, write=None, raises: BaseException | None = None):
        self.returncode, self.write, self.raises = returncode, write, raises
        self.calls = 0

    def __call__(self, argv, **kwargs):
        self.calls += 1
        if self.write:
            self.write()
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode)


@pytest.fixture
def shipped(monkeypatch):
    """The shipped observer, with every Docker question answered by fakes."""
    asked: list[str] = []
    monkeypatch.setattr(diagnostics, "OBSERVERS", diagnostics.DEFAULT_OBSERVERS)

    def exists(controller, volume, **kw):
        asked.append(f"exists {controller} {volume}")
        return None

    def leftovers(controller, volume, **kw):
        asked.append(f"leftovers {controller} {volume}")
        return []

    def probe(**kw):
        asked.append("probe")
        return DAEMON_OK

    monkeypatch.setattr(health, "run_resources_exist", exists)
    monkeypatch.setattr(health, "run_leftovers", leftovers)
    monkeypatch.setattr(health, "probe_daemon", probe)
    return asked


def _session_run(tmp_path: Path, runner: Runner, *, result_written=False) -> RuntimeSession:
    session = RuntimeSession(target="python-tarfile")
    report = tmp_path / "target-explore" / "inodefence-python-tarfile-explore-r.json"
    try:
        session.launch(
            SCRIPT, [], runner=runner, env=dict(ENV), artifacts=LaunchArtifacts(report=report)
        )
    finally:
        session.finish(result_written=result_written)
    return session


def _write_abort(tmp_path: Path):
    def write():
        folder = tmp_path / "target-explore"
        folder.mkdir(parents=True, exist_ok=True)
        stub = {
            "aborted": {
                "category": "cleanup_inspect",
                "reason": "container runtime cleanup inspect failed: ",
            }
        }
        (folder / "inodefence-python-tarfile-explore-r.json").write_text(json.dumps(stub))
        (folder / "inodefence-python-tarfile-explore-r.steps.jsonl").write_text("{}\n")

    return write


def test_the_host4_smoke_shape_prints_one_diagnosis_line_and_changes_nothing(
    tmp_path, shipped, capsys
) -> None:
    runner = Runner(returncode=1, write=_write_abort(tmp_path))
    session = _session_run(tmp_path, runner)
    record = session.launches[0]
    assert record.returncode == 1 and record.classification == "failed"  # unchanged
    err = capsys.readouterr().err
    (line,) = [x for x in err.splitlines() if "DIAGNOSIS" in x]
    assert line.startswith(
        "TARGET-EXPLORE DIAGNOSIS: stage=loop category=cleanup_inspect result=not-written "
    )
    assert "inodefence-python-tarfile-explore-r.steps.jsonl" in line
    assert "runtime record: <out>/runtime/py3.12.16-data-123-20-<UTC>.json" in line
    (finding,) = [f for f in record.findings if f.code == "stop-diagnosis"]
    assert finding.severity == "info"
    assert finding.message == (
        "stage=loop category=cleanup_inspect result_written=False evidence="
        "inodefence-python-tarfile-explore-r.json,inodefence-python-tarfile-explore-r.steps.jsonl"
    )
    assert str(tmp_path) not in json.dumps(session.to_json())  # no host paths in the record
    controller = "inodefence-python-tarfile-controller-py3.12.16-data-123-20"
    assert shipped[0].startswith(f"exists {controller} ")
    assert "probe" in shipped and any(a.startswith("leftovers") for a in shipped)


def test_a_clean_launch_prints_nothing_but_still_checks_its_names(
    tmp_path, shipped, capsys
) -> None:
    def write():
        folder = tmp_path / "target-explore"
        folder.mkdir(parents=True)
        (folder / "inodefence-python-tarfile-explore-r.json").write_text('{"case_records": []}')

    session = _session_run(tmp_path, Runner(0, write=write), result_written=True)
    assert session.launches[0].findings == []
    assert capsys.readouterr().err == ""
    assert "probe" not in shipped  # no daemon question after a clean exit
    assert any(a.startswith("leftovers") for a in shipped)


def test_leftover_names_after_a_launch_are_a_warning(tmp_path, shipped, monkeypatch, capsys):
    monkeypatch.setattr(health, "run_leftovers", lambda c, v, **kw: [f"this run's volume {v} x"])
    session = _session_run(tmp_path, Runner(0), result_written=True)
    (finding,) = session.launches[0].findings
    assert (finding.severity, finding.code) == ("warn", "leftover-resources")
    assert (
        "RUNTIME DIAGNOSTIC WARN leftover-resources: this run's volume" in capsys.readouterr().err
    )


def test_a_taken_run_name_blocks_before_the_launcher_runs(tmp_path, shipped, monkeypatch):
    monkeypatch.setattr(
        health, "run_resources_exist", lambda c, v, **kw: f"container {c} already exists"
    )
    runner = Runner(0)
    with pytest.raises(LaunchBlocked, match="run-resources-exist: container .* already exists"):
        _session_run(tmp_path, runner)
    assert runner.calls == 0


def test_an_interrupted_launcher_is_named_and_re_raised(tmp_path, shipped, monkeypatch, capsys):
    stalled = health.DaemonStatus(health.DaemonState.TIMEOUT, "no answer")
    monkeypatch.setattr(health, "probe_daemon", lambda **kw: stalled)
    with pytest.raises(KeyboardInterrupt):
        _session_run(tmp_path, Runner(raises=KeyboardInterrupt()))
    err = capsys.readouterr().err
    assert "DIAGNOSIS: stage=controller-setup category=daemon-timeout" in err
    assert "did not return an exit code (KeyboardInterrupt)" in err


def test_complete_report_but_failed_launcher_is_cleanup_unknown(tmp_path, shipped, capsys):
    def write():
        folder = tmp_path / "target-explore"
        folder.mkdir(parents=True)
        (folder / "inodefence-python-tarfile-explore-r.json").write_text('{"case_records": [1]}')

    _session_run(tmp_path, Runner(125, write=write))
    err = capsys.readouterr().err
    assert "DIAGNOSIS: stage=cleanup category=UNKNOWN result=not-written" in err
    assert "not treated as success" in err

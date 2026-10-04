"""Controlled controller failures, no claimed target/container qualification."""

import sys

import pytest
from scripts import evaluation_gnu_container as runner
from tests.container_integration import evaluation_gnu_checks as checks

from inodefence.campaign_export import export_campaign
from inodefence.evaluation.failure import CleanupStatus, read_failure
from inodefence.replay.execution import replay_benign
from inodefence.targets.python_tarfile import PythonTarfileTarget


def invoke(monkeypatch, destination):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--inside-controller",
            "--controller",
            "a" * 64,
            "--volume",
            "unit-volume",
            "--image",
            "sha256:" + "b" * 64,
            "--owner",
            "c" * 32,
            "--evidence",
            str(destination),
        ],
    )
    monkeypatch.setattr(runner, "ContainerExecutionBackend", lambda *args: object())


def test_outer_failure_preserves_prior_bytes_and_invalid_ledger(tmp_path, monkeypatch):
    destination = tmp_path / "new"
    invoke(monkeypatch, destination)

    def fail(backend, image, evidence):
        evidence.mkdir()
        (evidence / "prior").write_bytes(b"available diagnostics")
        raise OSError("injected controller publication failure")

    monkeypatch.setattr(checks, "run_checks", fail)
    with pytest.raises(OSError, match="injected"):
        runner.main()
    assert (destination / "prior").read_bytes() == b"available diagnostics"
    failure = read_failure(destination / "runner-failure.json")
    assert failure.classification == "infrastructure_invalid"
    assert failure.context.target is None and failure.context.last_fully_completed_step is None
    assert failure.context.cleanup_status == CleanupStatus.UNKNOWN
    assert not (destination / "checks.json").exists()


def test_existing_destination_is_never_modified(tmp_path, monkeypatch):
    destination = tmp_path / "prior"
    destination.mkdir()
    (destination / "raw").write_bytes(b"original evidence")
    invoke(monkeypatch, destination)
    with pytest.raises(FileExistsError):
        runner.main()
    assert {path.name for path in destination.iterdir()} == {"raw"}
    assert (destination / "raw").read_bytes() == b"original evidence"


def test_outer_failure_binds_available_verified_replay_prefix(tmp_path, monkeypatch, campaign):
    destination = tmp_path / "new"
    invoke(monkeypatch, destination)

    def fail(backend, image, evidence):
        evidence.mkdir()
        export_campaign(campaign, evidence / "original")
        replay_benign(evidence / "original", evidence / "replay", PythonTarfileTarget())
        raise OSError("injected after verified replay")

    monkeypatch.setattr(checks, "run_checks", fail)
    with pytest.raises(OSError, match="injected"):
        runner.main()
    failure = read_failure(destination / "runner-failure.json")
    assert failure.context.target == campaign.provenance.target
    assert failure.context.last_fully_completed_step == len(campaign.steps) - 1
    assert failure.context.artifacts[0].name == "original/manifest.json"
    assert failure.context.before is None and failure.context.after is None

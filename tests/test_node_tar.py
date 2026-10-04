"""Only ordinary controlled fixtures; never generated security campaigns."""

import json
from pathlib import Path

import pytest

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ExecutionStatus
from inodefence.model.provenance import ExecutionSafety
from inodefence.pipeline import run_case
from inodefence.runtime import RuntimeSandbox
from inodefence.targets.node_tar import NodeTarTarget

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "tools" / "node-tar"


def test_exact_discovered_versions_and_fixed_safety_requirement() -> None:
    target = NodeTarTarget(PACKAGE_ROOT, timeout_seconds=3.5)
    assert target.tar_version == "7.5.22"
    assert target.node_version.startswith("22.")
    assert (
        target.provenance.target_version == f"node={target.node_version};tar={target.tar_version}"
    )
    assert target.provenance.timeout_seconds == 3.5
    assert target.provenance.execution_safety == ExecutionSafety.ISOLATION_REQUIRED
    with pytest.raises(ValueError, match="requires execution isolation"):
        run_campaign(minimal_seed_corpus(), target, CampaignConfig(1, 4))


@pytest.mark.parametrize("index", range(4))
def test_benign_baseline_extraction_has_no_harness_bookkeeping(index: int) -> None:
    target = NodeTarTarget(PACKAGE_ROOT)
    result = run_case(minimal_seed_corpus()[index], target)
    assert result.execution.status == ExecutionStatus.SUCCESS
    assert result.execution.target_version == target.provenance.target_version
    assert result.execution.timeout_seconds == target.timeout_seconds
    assert result.execution.duration_seconds >= 0
    assert result.execution.stdout == result.execution.stderr == ""
    assert not any(verdict.violated for verdict in result.violations)
    assert all(change.path.startswith("extract") for change in result.changes)
    if index == 2:
        first, second = result.after.get("extract/a.txt"), result.after.get("extract/b.txt")
        assert first is not None and second is not None
        assert first.identity == second.identity
    if index == 3:
        link = result.after.get("extract/b.txt")
        assert link is not None and link.symlink_target == "a.txt"
    assert not Path(result.after.sandbox_root).exists()


def test_nonarchive_input_returns_error_diagnostics(sandbox: RuntimeSandbox) -> None:
    sandbox.archive_path.write_bytes(b"ordinary invalid format")
    result = NodeTarTarget(PACKAGE_ROOT).run(sandbox.archive_path, sandbox.extraction_root)
    assert result.status == ExecutionStatus.REJECTED
    diagnostic = json.loads(result.stderr)
    assert diagnostic["code"] == "TAR_BAD_ARCHIVE"
    assert result.stdout == ""


def test_version_discovery_is_mockable_and_invalid_identity_rejected(monkeypatch) -> None:
    monkeypatch.setattr("inodefence.targets.node_tar._identify", lambda *args: ("22.0.0", "1.2.3"))
    assert NodeTarTarget(PACKAGE_ROOT).tar_version == "1.2.3"
    monkeypatch.setattr(
        "inodefence.targets.node_tar._identify", lambda *args: ("latest", "installed")
    )
    with pytest.raises(ValueError, match="version"):
        NodeTarTarget(PACKAGE_ROOT)


def test_invalid_timeout_and_missing_node_rejected(monkeypatch) -> None:
    with pytest.raises(ValueError):
        NodeTarTarget(PACKAGE_ROOT, timeout_seconds=True)
    monkeypatch.setattr("shutil.which", lambda *args: None)
    with pytest.raises(ValueError, match="executable"):
        NodeTarTarget(PACKAGE_ROOT)


def test_timeout_status_and_streams_preserved(sandbox: RuntimeSandbox, monkeypatch) -> None:
    from inodefence.targets._process import ProcessOutcome

    target = NodeTarTarget(PACKAGE_ROOT)
    monkeypatch.setattr(
        "inodefence.targets.node_tar.run_process",
        lambda *args, **kwargs: ProcessOutcome(None, b"output\xff", b"error", 0.5),
    )
    result = target.run(sandbox.archive_path, sandbox.extraction_root)
    assert result.status == ExecutionStatus.TIMED_OUT
    assert result.stdout == "output\udcff" and result.stderr == "error"
    assert result.duration_seconds == 0.5


def test_unexpected_worker_error_is_failed(sandbox: RuntimeSandbox, monkeypatch) -> None:
    from inodefence.targets._process import ProcessOutcome

    target = NodeTarTarget(PACKAGE_ROOT)
    monkeypatch.setattr(
        "inodefence.targets.node_tar.run_process",
        lambda *args, **kwargs: ProcessOutcome(1, b"", b"controlled worker error", 0.5),
    )
    assert (
        target.run(sandbox.archive_path, sandbox.extraction_root).status == ExecutionStatus.FAILED
    )


def test_real_timeout_of_ordinary_fixture_preserves_after_state_and_cleanup() -> None:
    result = run_case(minimal_seed_corpus()[0], NodeTarTarget(PACKAGE_ROOT, timeout_seconds=1e-9))
    assert result.execution.status == ExecutionStatus.TIMED_OUT
    assert result.execution.duration_seconds > 0
    assert not Path(result.after.sandbox_root).exists()


def test_layout_rejection_precedes_worker_invocation(sandbox: RuntimeSandbox, monkeypatch) -> None:
    target = NodeTarTarget(PACKAGE_ROOT)

    def forbidden(*args, **kwargs):
        raise AssertionError("bad harness paths must never execute")

    monkeypatch.setattr("inodefence.targets.node_tar.run_process", forbidden)
    with pytest.raises(ValueError, match="layout"):
        target.run(sandbox.archive_path, sandbox.root)


def test_worker_identity_guard_precedes_extraction(sandbox: RuntimeSandbox, monkeypatch) -> None:
    monkeypatch.setattr("inodefence.targets.node_tar._identify", lambda *args: ("99.0.0", "7.5.22"))
    target = NodeTarTarget(PACKAGE_ROOT)
    with pytest.raises(RuntimeError, match="identity changed"):
        target.run(sandbox.archive_path, sandbox.extraction_root)
    assert tuple(sandbox.extraction_root.iterdir()) == ()

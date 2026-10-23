"""Engineering probes only: no target, Docker, live approval, or real attempt."""

from dataclasses import replace
from pathlib import PurePosixPath

import pytest
from tests.evaluation import test_n05_preflight as support

from inodefence.evaluation.failure import ArtifactReference
from inodefence.evaluation.n05_preflight import N05ControllerMount
from inodefence.evaluation.track_a_host_ledger import (
    TrackACampaignObservationStatus,
    TrackAHostAttemptStatus,
    TrackAHostAttemptTerminal,
    TrackAHostCleanupStatus,
)


def test_extra_absolute_host_evidence_mount_is_rejected(tmp_path, monkeypatch):
    # _inputs constructs controlled packaging/context metadata, never runs a target.
    _, _, _, broker = support._inputs(tmp_path, monkeypatch)
    extra = N05ControllerMount("bind", str(tmp_path), "/Users/evidence", False)
    mounts = tuple(sorted((*broker.controller_mounts, extra), key=lambda item: item.destination))
    with pytest.raises(ValueError, match="source/runtime boundary"):
        replace(broker, controller_mounts=mounts)


def test_allowed_mount_model_has_no_absolute_host_ledger_view(tmp_path, monkeypatch):
    _, _, _, broker = support._inputs(tmp_path, monkeypatch)
    host_ledger = PurePosixPath(support.preflight.HOST_LEDGER_ROOT)
    # This is a declared-mount model, not a live Docker namespace reproduction.
    destinations = [PurePosixPath(item.destination) for item in broker.controller_mounts]
    assert all(not host_ledger.is_relative_to(destination) for destination in destinations)
    source_mount = next(item for item in broker.controller_mounts if item.mount_type == "bind")
    assert source_mount.source == support.preflight.HOST_SOURCE_WORKTREE
    assert source_mount.destination == "/workspaces/InodeFence"
    assert source_mount.read_write is False


def _unknown_observation_terminal():
    digest = "a" * 64
    return TrackAHostAttemptTerminal(
        attempt_id="synthetic-no-execution",
        run_index=0,
        run_id="synthetic-cell",
        execution_sha256=digest,
        plan_sha256=digest,
        host_admission=ArtifactReference("admission/verified-admission.json", digest),
        started=ArtifactReference("started.json", digest),
        controller_stderr=ArtifactReference("controller-stderr.bin", digest),
        controller_stderr_size=0,
        controller_stderr_truncated=False,
        controller_stderr_capture_complete=False,
        controller_launched=False,
        controller_returncode=None,
        controller_terminal=None,
        deadline_expired=False,
        cleanup_status=TrackAHostCleanupStatus.NOT_NEEDED,
        cleanup_errors=(),
        campaign_observation_status=TrackACampaignObservationStatus.FAILED,
        campaign_observation_error="synthetic reread unavailable",
        campaign_state=None,
        campaign_claim=None,
        campaign_terminal=None,
        target_executions=None,
        exception="synthetic launch unavailable",
        started_at="2026-10-23T00:00:00+00:00",
        ended_at="2026-10-23T00:00:01+00:00",
        status=TrackAHostAttemptStatus.FAILED,
    )


def test_failed_observation_preserves_unknown_execution_count():
    terminal = _unknown_observation_terminal()
    assert terminal.target_executions is None
    assert terminal.campaign_state is None
    with pytest.raises(ValueError, match="failed campaign observation"):
        replace(terminal, target_executions=0)


def test_unknown_observation_cannot_be_promoted_to_complete():
    with pytest.raises(ValueError, match="complete host attempt"):
        replace(_unknown_observation_terminal(), status=TrackAHostAttemptStatus.COMPLETE)

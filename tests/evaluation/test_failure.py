from dataclasses import replace
from datetime import UTC, datetime

import pytest

from inodefence.evaluation.failure import (
    ArtifactReference,
    CleanupStatus,
    FailureContext,
    FailurePhase,
    failure_record,
    read_failure,
    write_failure,
)
from inodefence.model.provenance import SourceProvenance


def test_actual_exception_and_available_evidence_round_trip(campaign, tmp_path):
    result = campaign.steps[0].result
    context = FailureContext(
        "attempt-1",
        "test-experiment",
        campaign.provenance.source,
        campaign.provenance.target,
        1,
        FailurePhase.PUBLICATION,
        last_fully_completed_step=0,
        diagnostics=("controlled storage failure",),
        stdout=result.execution.stdout,
        stderr=result.execution.stderr,
        before=result.before,
        after=result.after,
        cleanup_status=CleanupStatus.SUCCEEDED,
        artifacts=(ArtifactReference("archive", result.archive_sha256),),
    )
    now = datetime.now(UTC)
    record = failure_record(OSError("controlled disk failure"), context)
    assert now <= datetime.fromisoformat(record.recorded_at) <= datetime.now(UTC)
    path = tmp_path / "failure.json"
    digest = write_failure(path, record)
    assert read_failure(path, expected_sha256=digest) == record
    assert record.classification == "infrastructure_invalid"
    assert record.exception_type == "builtins.OSError"
    assert record.exception_message == "controlled disk failure"
    assert record.context.after == result.after


def test_missing_evidence_stays_explicitly_unavailable(tmp_path):
    context = FailureContext(
        "attempt", "experiment", SourceProvenance(), None, None, FailurePhase.SETUP
    )
    record = failure_record(ValueError("setup unavailable"), context)
    path = tmp_path / "failure.json"
    write_failure(path, record)
    actual = read_failure(path)
    assert actual.context.stdout is actual.context.stderr is None
    assert actual.context.before is actual.context.after is None
    assert actual.context.last_fully_completed_step is None
    assert actual.context.cleanup_status == CleanupStatus.UNKNOWN
    with pytest.raises(ValueError):
        replace(actual, classification="success")
    with pytest.raises(ValueError):
        replace(actual, recorded_at="2026-10-05T00:00:00")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"step_index": True},
        {"step_index": -1},
        {"last_fully_completed_step": 3},
        {"cleanup_status": "succeeded"},
        {"config_id": "unknown"},
        {"diagnostics": ["mutable"]},
    ],
)
def test_invalid_failure_context_is_rejected(campaign, kwargs):
    context = FailureContext(
        "attempt",
        "experiment",
        campaign.provenance.source,
        campaign.provenance.target,
        1,
        FailurePhase.AFTER,
    )
    with pytest.raises(ValueError):
        replace(context, **kwargs)


def test_wrong_snapshot_phase_and_overwriting_failure_are_rejected(campaign, tmp_path):
    context = FailureContext(
        "attempt",
        "experiment",
        campaign.provenance.source,
        campaign.provenance.target,
        0,
        FailurePhase.BEFORE,
    )
    with pytest.raises(ValueError, match="phase"):
        replace(context, after=campaign.steps[0].result.before)
    path = tmp_path / "failure.json"
    first = failure_record(OSError("first"), context)
    write_failure(path, first)
    with pytest.raises(FileExistsError):
        write_failure(path, failure_record(OSError("second"), context))
    assert read_failure(path) == first

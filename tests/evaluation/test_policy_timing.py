"""Full-step timing is separate from process duration and policy semantics."""

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.campaign import SearchCampaignConfig
from inodefence.evaluation.encoding import json_bytes, read_json
from inodefence.evaluation.policy_binding import PolicyEvaluationConfig
from inodefence.evaluation.policy_timing import (
    PolicyCampaignTiming,
    PolicyStepTiming,
    TimedPolicyCampaign,
    export_timed_policy_result,
    run_timed_search_campaign,
    verify_timed_policy_evidence,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import SearchPolicy
from inodefence.mutator import MutationPolicy
from inodefence.replay.benign import benign_replay_cases
from inodefence.targets.python_tarfile import PythonTarfileTarget


def _timed(monkeypatch) -> TimedPolicyCampaign:
    ticks = iter((1_000, 1_100, 1_400, 2_000, 2_700, 3_000))
    utc = iter(
        (
            datetime(2026, 10, 14, 18, 0, tzinfo=UTC),
            datetime(2026, 10, 14, 18, 1, tzinfo=UTC),
        )
    )
    monkeypatch.setattr("inodefence.evaluation.policy_timing.monotonic_ns", lambda: next(ticks))
    monkeypatch.setattr("inodefence.evaluation.policy_timing._utc_now", lambda: next(utc))
    cases = benign_replay_cases()
    return run_timed_search_campaign(
        cases,
        PythonTarfileTarget(),
        SearchCampaignConfig(9, len(cases), SearchPolicy.B3, MutationPolicy.M1),
    )


def _config(timed: TimedPolicyCampaign) -> PolicyEvaluationConfig:
    result = timed.result
    return PolicyEvaluationConfig(
        result.config,
        result.initial_case_ids,
        result.provenance,
        "controlled-seed-v1",
        "unit-linux-v1",
        "default-sentinel-v1",
        "policy-timing-test-v1",
    )


def test_timed_runner_records_full_sequential_offsets_not_target_durations(monkeypatch):
    timed = _timed(monkeypatch)
    assert tuple(
        (item.index, item.started_offset_ns, item.completed_offset_ns)
        for item in timed.timing.steps
    ) == ((0, 0, 100), (1, 100, 400), (2, 400, 1_000), (3, 1_000, 1_700))
    assert timed.timing.campaign_completed_offset_ns == 2_000
    assert timed.timing.elapsed_seconds == pytest.approx(0.000002)
    assert timed.timing.started_at_utc == "2026-10-14T18:00:00+00:00"
    assert timed.timing.completed_at_utc == "2026-10-14T18:01:00+00:00"
    assert all(step.result.execution.duration_seconds >= 0 for step in timed.result.steps)
    assert all(not Path(step.result.after.sandbox_root).exists() for step in timed.result.steps)
    assert [item.duration_seconds for item in timed.timing.steps] == pytest.approx(
        [0.0000001, 0.0000003, 0.0000006, 0.0000007]
    )


def test_timed_policy_export_and_independent_reader_roundtrip(monkeypatch, tmp_path):
    timed = _timed(monkeypatch)
    config = _config(timed)
    directory = tmp_path / "timed"
    digest = export_timed_policy_result(timed, config, directory)
    verified = verify_timed_policy_evidence(directory, expected_manifest_sha256=digest)
    assert verified.campaign.campaign.result == timed.result
    assert verified.campaign.config == config
    assert verified.timing == timed.timing
    assert verified.manifest_sha256 == digest
    assert verified.manifest.evaluation_config_id == config.config_id


def test_semantically_invalid_rehashed_timing_fails_closed(monkeypatch, tmp_path):
    timed = _timed(monkeypatch)
    directory = tmp_path / "timed"
    export_timed_policy_result(timed, _config(timed), directory)
    timing_path = directory / "timing.json"
    timing = read_json(timing_path.read_bytes())
    assert isinstance(timing, dict) and isinstance(timing["payload"], dict)
    payload = timing["payload"]
    assert isinstance(payload["value"], dict) and isinstance(payload["value"]["steps"], list)
    payload["value"]["steps"][1]["started_offset_ns"] = 99
    timing["payload_sha256"] = sha256(json_bytes(payload)).hexdigest()
    timing_path.write_bytes(json_bytes(timing) + b"\n")
    timing_digest = sha256(timing_path.read_bytes()).hexdigest()
    manifest_path = directory / "manifest.json"
    manifest = read_json(manifest_path.read_bytes())
    assert isinstance(manifest, dict) and isinstance(manifest["payload"], dict)
    manifest_payload = manifest["payload"]
    assert isinstance(manifest_payload["value"], dict)
    manifest_payload["value"]["timing"]["sha256"] = timing_digest
    manifest["payload_sha256"] = sha256(json_bytes(manifest_payload)).hexdigest()
    manifest_path.write_bytes(json_bytes(manifest) + b"\n")
    with pytest.raises(VerificationError, match="contiguous campaign timeline"):
        verify_timed_policy_evidence(directory)


@pytest.mark.parametrize(
    "timing",
    (
        lambda valid: replace(valid, campaign_completed_offset_ns=0),
        lambda valid: replace(
            valid,
            steps=(
                valid.steps[0],
                replace(valid.steps[1], index=4),
                *valid.steps[2:],
            ),
        ),
    ),
)
def test_timing_model_rejects_incomplete_or_unordered_records(monkeypatch, timing):
    valid = _timed(monkeypatch).timing
    with pytest.raises(ValueError):
        timing(valid)


def test_timed_pair_rejects_missing_step_timing(monkeypatch):
    timed = _timed(monkeypatch)
    shorter = replace(timed.timing, steps=timed.timing.steps[:-1])
    with pytest.raises(ValueError, match="timing count"):
        TimedPolicyCampaign(timed.result, shorter)


def test_timed_export_refuses_overwrite_and_torn_marker_is_not_verified(monkeypatch, tmp_path):
    timed = _timed(monkeypatch)
    config = _config(timed)
    directory = tmp_path / "timed"
    digest = export_timed_policy_result(timed, config, directory)
    with pytest.raises(FileExistsError):
        export_timed_policy_result(timed, config, directory)
    assert verify_timed_policy_evidence(directory, expected_manifest_sha256=digest)
    (directory / "manifest.json").unlink()
    with pytest.raises(VerificationError):
        verify_timed_policy_evidence(directory)


def test_invalid_timed_binding_does_not_create_export_root(monkeypatch, tmp_path):
    timed = _timed(monkeypatch)
    config = replace(_config(timed), initial_case_ids=("0" * 64,))
    directory = tmp_path / "invalid"
    with pytest.raises(ValueError, match="declaration differs"):
        export_timed_policy_result(timed, config, directory)
    assert not directory.exists()


def test_timing_scalars_reject_bool_negative_and_naive_time():
    with pytest.raises(ValueError):
        PolicyStepTiming(True, 0, 1)
    with pytest.raises(ValueError):
        PolicyStepTiming(0, -1, 1)
    with pytest.raises(ValueError):
        PolicyCampaignTiming(
            "2026-10-14T18:00:00",
            "2026-10-14T18:01:00+00:00",
            (PolicyStepTiming(0, 0, 1),),
            1,
        )

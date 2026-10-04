from dataclasses import replace

import pytest

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.evaluation.failure import CleanupStatus, read_failure, write_failure
from inodefence.evaluation.storage import read_record, write_record
from inodefence.evaluation.verify import VerificationError, verify_campaign
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.replay import execution
from inodefence.targets.python_tarfile import PythonTarfileTarget


def forbid_execution(*args, **kwargs):
    raise AssertionError("unverified or unsupported input must not execute")


def test_benign_replay_keeps_original_and_full_fresh_evidence(original, tmp_path):
    old = verify_campaign(original)
    original_bytes = {path.name: path.read_bytes() for path in original.iterdir()}
    destination = tmp_path / "replay"
    result = execution.replay_benign(original, destination, PythonTarfileTarget())
    assert result.complete and result.failure is None
    assert len(result.steps) == len(old.result.steps)
    assert execution.verify_replay(original, destination) == result
    assert {path.name: path.read_bytes() for path in original.iterdir()} == original_bytes
    roots = {step.result.before.sandbox_root for step in old.result.steps}
    for replay, source in zip(result.steps, old.result.steps, strict=True):
        assert replay.original_step_index == source.index
        assert replay.original_case_id == source.result.case.case_id
        assert replay.original_archive_sha256 == source.result.archive_sha256
        assert replay.result.case == source.result.case
        assert replay.result.before.sandbox_root not in roots
        roots.add(replay.result.before.sandbox_root)
        assert replay.result.after.sandbox_root == replay.result.before.sandbox_root
    with pytest.raises(FileExistsError):
        execution.replay_benign(original, destination, PythonTarfileTarget())


def test_selection_preserves_original_indices(original, tmp_path):
    result = execution.replay_benign(
        original, tmp_path / "selected", PythonTarfileTarget(), step_indices=(3, 1)
    )
    assert [step.original_step_index for step in result.steps] == [3, 1]


@pytest.mark.parametrize("indices", [(), (True,), (-1,), (4,), (0, 0)])
def test_invalid_selection_has_no_target_execution(original, tmp_path, monkeypatch, indices):
    monkeypatch.setattr(execution, "run_case", forbid_execution)
    destination = tmp_path / "invalid"
    with pytest.raises(ValueError):
        execution.replay_benign(original, destination, PythonTarfileTarget(), step_indices=indices)
    assert not destination.exists()


def test_bad_original_and_overlapping_destination_fail_before_execution(
    original, tmp_path, monkeypatch
):
    monkeypatch.setattr(execution, "run_case", forbid_execution)
    with pytest.raises(ValueError, match="independent"):
        execution.replay_benign(original, original / "replay", PythonTarfileTarget())
    path = original / "steps.jsonl"
    path.write_bytes(path.read_bytes()[:-10])
    with pytest.raises(VerificationError):
        execution.replay_benign(original, tmp_path / "invalid", PythonTarfileTarget())


def test_other_ordinary_case_is_outside_bounded_profile(tmp_path, monkeypatch):
    case = ArchiveCase((ArchiveEntry("ordinary.txt", EntryType.REGULAR, content=b"ordinary"),))
    source = run_campaign((case,), PythonTarfileTarget(), CampaignConfig(23, 1))
    original = tmp_path / "ordinary"
    export_campaign(source, original)
    monkeypatch.setattr(execution, "run_case", forbid_execution)
    with pytest.raises(ValueError, match="fixed benign"):
        execution.replay_benign(original, tmp_path / "replay", PythonTarfileTarget())


def test_later_infrastructure_failure_preserves_completed_prefix(original, tmp_path, monkeypatch):
    real = execution.run_case
    count = 0

    def fail_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("injected unavailable infrastructure")
        return real(*args, **kwargs)

    monkeypatch.setattr(execution, "run_case", fail_second)
    destination = tmp_path / "failed"
    with pytest.raises(OSError, match="injected"):
        execution.replay_benign(original, destination, PythonTarfileTarget())
    prefix = execution.verify_replay(original, destination)
    assert not prefix.complete and len(prefix.steps) == 1
    assert prefix.failure is not None
    context = prefix.failure.context
    assert prefix.failure.classification == "infrastructure_invalid"
    assert context.step_index == 1 and context.last_fully_completed_step == 0
    assert context.before is None and context.after is None
    assert context.cleanup_status == CleanupStatus.UNKNOWN
    failure_path = destination / "failure.json"
    record = read_failure(failure_path)
    failure_path.unlink()
    write_failure(failure_path, replace(record, context=replace(context, experiment_id="other")))
    with pytest.raises(VerificationError, match="ledger differs"):
        execution.verify_replay(original, destination)


def test_completion_marker_and_all_record_checksums_are_required(original, tmp_path):
    destination = tmp_path / "replay"
    execution.replay_benign(original, destination, PythonTarfileTarget())
    marker = destination / "completion.json"
    data = marker.read_bytes()
    marker.unlink()
    assert not execution.verify_replay(original, destination).complete
    marker.write_bytes(data)
    step = destination / "step-00000000.json"
    step.write_bytes(step.read_bytes()[:-3])
    with pytest.raises(VerificationError):
        execution.verify_replay(original, destination)


def test_record_with_original_runtime_is_rejected(original, tmp_path):
    destination = tmp_path / "replay"
    execution.replay_benign(original, destination, PythonTarfileTarget())
    path = destination / "step-00000000.json"
    record = read_record(path, execution.ReplayStep)
    old = verify_campaign(original).result.steps[0].result
    path.unlink()
    write_record(path, replace(record, result=old))
    with pytest.raises(VerificationError, match="runtime was reused"):
        execution.verify_replay(original, destination)

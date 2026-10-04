from dataclasses import replace

import pytest

from inodefence.campaign import run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.evaluation.failure import FailureContext, FailurePhase, failure_record, write_failure
from inodefence.evaluation.repeated import (
    RepetitionController,
    RepetitionPlan,
    RunState,
    read_repetitions,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.experiment_config import (
    FEEDBACK_POLICY,
    MUTATION_POLICY,
    SEED_PROFILE,
    ExperimentConfig,
)
from inodefence.generator import minimal_seed_corpus
from inodefence.runtime import SentinelSpec
from inodefence.targets.python_tarfile import PythonTarfileTarget


@pytest.fixture
def plan(campaign):
    config = ExperimentConfig(
        campaign.provenance.target,
        SEED_PROFILE,
        campaign.initial_case_ids,
        campaign.config,
        MUTATION_POLICY,
        FEEDBACK_POLICY,
        (SentinelSpec(),),
        "unit-repetition-v1",
    )
    return RepetitionPlan(config.to_json(), (17, 23), campaign.provenance)


def export_slot(controller, index):
    snapshot = controller.snapshot()
    config = snapshot.plan.config_for(index)
    result = run_campaign(
        minimal_seed_corpus(),
        PythonTarfileTarget(),
        config.campaign,
        sentinels=config.sentinels,
        experiment_config_id=config.config_id,
    )
    export_campaign(
        result,
        controller.root / snapshot.slots[index].result_directory / "evidence",
        experiment_config_json=config.to_json(),
    )


def ledger(controller, index):
    snapshot = controller.snapshot()
    claim = snapshot.slots[index].claim
    assert claim is not None
    context = FailureContext(
        claim.attempt_id,
        snapshot.plan_sha256,
        snapshot.plan.provenance.source,
        snapshot.plan.provenance.target,
        None,
        FailurePhase.UNKNOWN,
        config_id=claim.config_id,
    )
    return failure_record(OSError("controlled unavailable infrastructure"), context)


def test_independent_seed_slots_complete_and_resume(tmp_path, plan):
    controller = RepetitionController.create(tmp_path / "runs", plan)
    assert [slot.state for slot in controller.snapshot().slots] == [RunState.PENDING] * 2
    for index in (1, 0):
        directory = controller.claim(index, attempt_id=f"unit-{index}")
        assert directory.name == f"run-{index:08d}"
        export_slot(controller, index)
        controller.complete(index)
    snapshot = controller.snapshot()
    assert [slot.random_seed for slot in snapshot.slots] == [17, 23]
    assert len({slot.config_id for slot in snapshot.slots}) == 2
    assert all(slot.state == RunState.COMPLETED for slot in snapshot.slots)
    assert RepetitionController(controller.root).snapshot() == snapshot
    assert read_repetitions(controller.root, expected_plan_sha256=snapshot.plan_sha256) == snapshot
    with pytest.raises(ValueError, match="duplicate"):
        controller.claim(0, attempt_id="another")


def test_export_without_terminal_remains_started(tmp_path, plan):
    controller = RepetitionController.create(tmp_path / "runs", plan)
    controller.claim(0, attempt_id="unit")
    export_slot(controller, 0)
    assert controller.snapshot().slots[0].state == RunState.STARTED
    assert controller.snapshot().slots[1].state == RunState.PENDING
    with pytest.raises(ValueError, match="already reserved"):
        controller.claim(1, attempt_id="unit")


@pytest.mark.parametrize("state", [RunState.FAILED, RunState.INVALID])
def test_failure_ledgers_bound_and_never_complete(tmp_path, plan, state):
    controller = RepetitionController.create(tmp_path / "runs", plan)
    controller.claim(0, attempt_id="unit")
    failure = ledger(controller, 0)
    with pytest.raises(ValueError, match="claim/plan"):
        controller.record_failure(
            0, replace(failure, context=replace(failure.context, config_id="0" * 64))
        )
    controller.record_failure(0, failure, state=state)
    assert controller.snapshot().slots[0].state == state
    with pytest.raises(ValueError, match="nonterminal"):
        controller.complete(0)


def test_wrong_seed_cannot_be_acknowledged(tmp_path, plan):
    controller = RepetitionController.create(tmp_path / "runs", plan)
    directory = controller.claim(0, attempt_id="unit")
    config = plan.config_for(1)
    result = run_campaign(
        minimal_seed_corpus(),
        PythonTarfileTarget(),
        config.campaign,
        experiment_config_id=config.config_id,
    )
    export_campaign(result, directory / "evidence", experiment_config_json=config.to_json())
    with pytest.raises(ValueError, match="explicit repetition plan"):
        controller.complete(0)
    assert controller.snapshot().slots[0].state == RunState.STARTED


def test_unacknowledged_infrastructure_failure_prevents_completion(tmp_path, plan):
    controller = RepetitionController.create(tmp_path / "runs", plan)
    directory = controller.claim(0, attempt_id="unit")
    export_slot(controller, 0)
    write_failure(directory / "failure.json", ledger(controller, 0))
    with pytest.raises(ValueError, match="failure artifact"):
        controller.complete(0)
    assert controller.snapshot().slots[0].state == RunState.STARTED


def test_torn_claim_and_changed_raw_never_become_completed(tmp_path, plan):
    controller = RepetitionController.create(tmp_path / "runs", plan)
    directory = controller.claim(0, attempt_id="unit")
    export_slot(controller, 0)
    controller.complete(0)
    manifest = directory / "evidence" / "manifest.json"
    manifest.write_bytes(manifest.read_bytes()[:-2])
    with pytest.raises(VerificationError):
        RepetitionController(controller.root)
    second = RepetitionController.create(tmp_path / "other", plan)
    (second.root / "run-00000000").mkdir()
    assert second.snapshot().slots[0].state == RunState.INVALID
    with pytest.raises(ValueError, match="duplicate"):
        second.claim(0, attempt_id="never-retry")


@pytest.mark.parametrize("seeds", [(), (17, 17), (True,), (23, 17), (17, -1)])
def test_invalid_seed_plan_rejected(plan, seeds):
    with pytest.raises(ValueError):
        replace(plan, seeds=seeds)

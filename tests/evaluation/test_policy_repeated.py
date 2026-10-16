"""Repeated policy schedules retain every terminal and interrupted attempt."""

import json
import sys
from dataclasses import replace

import pytest

import inodefence.campaign as campaign_module
import inodefence.evaluation.policy_repeated as policy_repeated_module
from inodefence.campaign import SearchCampaignConfig
from inodefence.evaluation.controller_memory import (
    ControllerMemoryObservation,
    ControllerMemoryObservationStart,
    LinuxProcessMemorySample,
)
from inodefence.evaluation.policy_binding import PolicyEvaluationConfig
from inodefence.evaluation.policy_repeated import (
    PolicyControllerMemory,
    PolicyRepetitionController,
    PolicyRepetitionPlan,
    PolicyScheduledRun,
    main,
    read_policy_repetitions,
)
from inodefence.evaluation.repeated import RunState
from inodefence.evaluation.storage import read_record, write_record
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import SearchPolicy
from inodefence.mutator import MutationPolicy
from inodefence.provenance import freeze_provenance
from inodefence.replay.benign import benign_replay_cases
from inodefence.runtime import SentinelSpec
from inodefence.targets.python_tarfile import PythonTarfileTarget

_BOOT_ID = "12345678-1234-5678-9234-567812345678"


def _patch_memory_observer(monkeypatch, *, process_id=123, process_start_ticks=42):
    started_sample = LinuxProcessMemorySample(
        process_id, _BOOT_ID, process_start_ticks, 100, 10_240, 20_480
    )
    completed_sample = LinuxProcessMemorySample(
        process_id, _BOOT_ID, process_start_ticks, 100, 12_288, 24_576
    )
    started = ControllerMemoryObservationStart("2026-10-16T00:00:00+00:00", 100, started_sample)
    observation = ControllerMemoryObservation(
        started.started_at_utc,
        "2026-10-16T00:00:01+00:00",
        1,
        started_sample,
        completed_sample,
    )
    monkeypatch.setattr(
        policy_repeated_module,
        "start_controller_memory_observation",
        lambda: started,
    )
    monkeypatch.setattr(
        policy_repeated_module,
        "finish_controller_memory_observation",
        lambda value: observation if value == started else None,
    )
    return observation


def _config(target, cases, policy, seed):
    return PolicyEvaluationConfig(
        SearchCampaignConfig(
            seed,
            len(cases) + 2,
            policy,
            MutationPolicy.M1_PROTECTED_COMPONENTS,
        ),
        tuple(case.case_id for case in cases),
        freeze_provenance(target.provenance, (SentinelSpec(),)),
        "minimal-benign-v1",
        "unit-linux-v1",
        "default-sentinel-v1",
        "policy-repeated-test-v1",
    )


@pytest.fixture
def scheduled():
    cases = benign_replay_cases()
    target = PythonTarfileTarget()
    runs = tuple(
        PolicyScheduledRun(
            f"{policy.name.lower()}-{seed}",
            policy.name,
            _config(target, cases, policy, seed),
        )
        for policy, seed in ((SearchPolicy.B0, 9001), (SearchPolicy.B3, 9001))
    )
    return (
        cases,
        target,
        PolicyRepetitionPlan("policy-repeated-test", "policy-repeated-test-v1", runs),
    )


def test_schedule_executes_independent_slots_and_reopens(scheduled, tmp_path):
    cases, target, plan = scheduled
    controller = PolicyRepetitionController.create(tmp_path / "runs", plan)
    assert [slot.state for slot in controller.snapshot().slots] == [RunState.PENDING] * 2
    for index in (1, 0):
        completed = controller.execute(
            index,
            cases,
            target,
            attempt_id=f"attempt-{index}",
        )
        assert completed.campaign.config == plan.runs[index].evaluation_config
    snapshot = controller.snapshot()
    assert [slot.state for slot in snapshot.slots] == [RunState.COMPLETED] * 2
    assert all(slot.completed_steps == len(cases) + 2 for slot in snapshot.slots)
    assert [slot.random_seed for slot in snapshot.slots] == [9001, 9001]
    assert [slot.arm_id for slot in snapshot.slots] == ["B0", "B3"]
    assert PolicyRepetitionController(controller.root).snapshot() == snapshot
    assert (
        read_policy_repetitions(controller.root, expected_plan_sha256=snapshot.plan_sha256)
        == snapshot
    )
    with pytest.raises(VerificationError, match="lacks required controller memory"):
        read_policy_repetitions(controller.root, require_controller_memory=True)
    with pytest.raises(ValueError, match="duplicate execution"):
        controller.claim(0, attempt_id="another")


def test_measured_run_binds_peak_and_prohibits_process_reuse(scheduled, monkeypatch, tmp_path):
    cases, target, plan = scheduled
    observation = _patch_memory_observer(monkeypatch)
    controller = PolicyRepetitionController.create(tmp_path / "runs", plan)

    controller.execute_measured(0, cases, target, attempt_id="measured")
    slot = controller.snapshot().slots[0]

    assert slot.state == RunState.COMPLETED
    assert slot.controller_memory is not None
    assert slot.controller_memory.observation == observation
    assert slot.controller_memory.observation.lifetime_peak_resident_bytes == 24_576
    assert slot.controller_memory_sha256 is not None
    assert (
        read_policy_repetitions(
            controller.root,
            require_controller_memory=True,
        )
        .slots[0]
        .controller_memory
        == slot.controller_memory
    )
    with pytest.raises(ValueError, match="already published a measured policy run"):
        controller.execute_measured(1, cases, target, attempt_id="same-process")
    assert controller.snapshot().slots[1].state == RunState.PENDING


def test_controller_memory_tamper_fails_closed(scheduled, monkeypatch, tmp_path):
    cases, target, plan = scheduled
    _patch_memory_observer(monkeypatch)
    controller = PolicyRepetitionController.create(tmp_path / "runs", plan)
    controller.execute_measured(0, cases, target, attempt_id="measured")
    memory = controller.root / "run-00000000" / "controller-memory.json"
    memory.write_bytes(memory.read_bytes()[:-4])

    with pytest.raises(VerificationError):
        read_policy_repetitions(controller.root)


def test_reader_rejects_reused_process_identity_across_measured_slots(
    scheduled, monkeypatch, tmp_path
):
    cases, target, plan = scheduled
    first_observation = _patch_memory_observer(monkeypatch)
    controller = PolicyRepetitionController.create(tmp_path / "runs", plan)
    controller.execute_measured(0, cases, target, attempt_id="first-process")
    _patch_memory_observer(monkeypatch, process_id=124, process_start_ticks=43)
    controller.execute_measured(1, cases, target, attempt_id="second-process")

    memory = controller.root / "run-00000001" / "controller-memory.json"
    second = read_record(memory, PolicyControllerMemory)
    memory.unlink()
    write_record(memory, replace(second, observation=first_observation))

    with pytest.raises(VerificationError, match="process identity reused"):
        read_policy_repetitions(controller.root)


def test_ordinary_exception_is_terminal_failed_not_a_no_hit(scheduled, monkeypatch, tmp_path):
    cases, target, plan = scheduled
    controller = PolicyRepetitionController.create(tmp_path / "runs", plan)
    original = campaign_module.run_case
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("controlled infrastructure failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(campaign_module, "run_case", fail_second)
    with pytest.raises(RuntimeError, match="controlled infrastructure failure"):
        controller.execute(0, cases, target, attempt_id="failed-attempt")
    slot = controller.snapshot().slots[0]
    assert slot.state == RunState.FAILED
    assert slot.completed_steps == 1
    assert slot.terminal is not None
    assert slot.terminal.artifact.name == "evidence/failure.json"
    assert controller.snapshot().slots[1].state == RunState.PENDING


def test_measured_ordinary_failure_retains_peak_with_failure_terminal(
    scheduled, monkeypatch, tmp_path
):
    cases, target, plan = scheduled
    _patch_memory_observer(monkeypatch)
    controller = PolicyRepetitionController.create(tmp_path / "runs", plan)

    def fail(*args, **kwargs):
        raise RuntimeError("controlled measured failure")

    monkeypatch.setattr(campaign_module, "run_case", fail)
    with pytest.raises(RuntimeError, match="controlled measured failure"):
        controller.execute_measured(0, cases, target, attempt_id="failed-measured")

    slot = controller.snapshot().slots[0]
    assert slot.state == RunState.FAILED
    assert slot.controller_memory is not None
    assert slot.controller_memory.evidence_terminal.name == "evidence/failure.json"


def test_hard_interruption_remains_started_with_verified_prefix(scheduled, monkeypatch, tmp_path):
    cases, target, plan = scheduled
    controller = PolicyRepetitionController.create(tmp_path / "runs", plan)
    original = campaign_module.run_case
    calls = 0

    def hard_stop(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return original(*args, **kwargs)

    monkeypatch.setattr(campaign_module, "run_case", hard_stop)
    with pytest.raises(KeyboardInterrupt):
        controller.execute(0, cases, target, attempt_id="hard-stop")
    slot = controller.snapshot().slots[0]
    assert slot.state == RunState.STARTED
    assert slot.completed_steps == 1
    assert slot.terminal is None
    assert slot.diagnostics == ("interrupted journal prefix; no automatic retry",)
    with pytest.raises(ValueError, match="duplicate execution"):
        controller.claim(0, attempt_id="forbidden-retry")


def test_unacknowledged_complete_journal_stays_started(scheduled, tmp_path):
    cases, target, plan = scheduled
    controller = PolicyRepetitionController.create(tmp_path / "runs", plan)
    directory = controller.claim(0, attempt_id="manual")
    scheduled_run = plan.runs[0]
    from inodefence.evaluation.policy_journal import run_journaled_timed_search_campaign

    run_journaled_timed_search_campaign(
        cases,
        target,
        scheduled_run.evaluation_config,
        directory / "evidence",
        attempt_id="manual",
        experiment_id=controller.snapshot().plan_sha256,
    )
    slot = controller.snapshot().slots[0]
    assert slot.state == RunState.STARTED
    assert slot.diagnostics == ("complete journal lacks terminal acknowledgement",)
    controller.complete(0)
    assert controller.snapshot().slots[0].state == RunState.COMPLETED


def test_plan_and_terminal_tamper_fail_closed(scheduled, tmp_path):
    cases, target, plan = scheduled
    controller = PolicyRepetitionController.create(tmp_path / "runs", plan)
    controller.execute(0, cases, target, attempt_id="complete")
    terminal = controller.root / "run-00000000" / "terminal.json"
    terminal.write_bytes(terminal.read_bytes()[:-4])
    with pytest.raises(VerificationError):
        read_policy_repetitions(controller.root)


def test_schedule_rejects_duplicate_or_protocol_drift(scheduled):
    _, _, plan = scheduled
    with pytest.raises(ValueError, match="unique run"):
        replace(plan, runs=(plan.runs[0], plan.runs[0]))
    drift = replace(
        plan.runs[1],
        evaluation_config=replace(plan.runs[1].evaluation_config, protocol_version="different-v1"),
    )
    with pytest.raises(ValueError, match="protocol version"):
        replace(plan, runs=(plan.runs[0], drift))


def test_cli_reports_all_pending_slots(scheduled, monkeypatch, capsys, tmp_path):
    _, _, plan = scheduled
    controller = PolicyRepetitionController.create(tmp_path / "runs", plan)
    digest = controller.snapshot().plan_sha256
    monkeypatch.setattr(
        sys,
        "argv",
        ["policy-repeated", str(controller.root), "--plan-sha256", digest],
    )
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["plan_sha256"] == digest
    assert report["states"]["pending"] == 2
    assert [slot["state"] for slot in report["slots"]] == ["pending", "pending"]

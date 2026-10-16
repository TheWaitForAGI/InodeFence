"""Repeated policy schedules retain every terminal and interrupted attempt."""

import json
import sys
from dataclasses import replace

import pytest

import inodefence.campaign as campaign_module
from inodefence.campaign import SearchCampaignConfig
from inodefence.evaluation.policy_binding import PolicyEvaluationConfig
from inodefence.evaluation.policy_repeated import (
    PolicyRepetitionController,
    PolicyRepetitionPlan,
    PolicyScheduledRun,
    main,
    read_policy_repetitions,
)
from inodefence.evaluation.repeated import RunState
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import SearchPolicy
from inodefence.mutator import MutationPolicy
from inodefence.provenance import freeze_provenance
from inodefence.replay.benign import benign_replay_cases
from inodefence.runtime import SentinelSpec
from inodefence.targets.python_tarfile import PythonTarfileTarget


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
    with pytest.raises(ValueError, match="duplicate execution"):
        controller.claim(0, attempt_id="another")


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

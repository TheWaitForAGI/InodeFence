"""Policy journals preserve exact prefixes and replay RNG/mutation provenance."""

from dataclasses import replace
from hashlib import sha256

import pytest

import inodefence.campaign as campaign_module
from inodefence.campaign import (
    SearchCampaignCompletedStep,
    SearchCampaignConfig,
    run_search_campaign,
)
from inodefence.evaluation.encoding import json_bytes, read_json
from inodefence.evaluation.policy_binding import PolicyEvaluationConfig
from inodefence.evaluation.policy_journal import (
    PolicyEvidenceJournal,
    PolicyJournalHeader,
    read_policy_journal,
    run_journaled_timed_search_campaign,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import SearchPolicy
from inodefence.mutator import MutationPolicy
from inodefence.provenance import freeze_provenance
from inodefence.replay.benign import benign_replay_cases
from inodefence.runtime import SentinelSpec
from inodefence.targets.python_tarfile import PythonTarfileTarget


def _configuration(target, cases, budget):
    campaign = SearchCampaignConfig(
        9051,
        budget,
        SearchPolicy.B3,
        MutationPolicy.M1_PROTECTED_COMPONENTS,
    )
    return PolicyEvaluationConfig(
        campaign,
        tuple(case.case_id for case in cases),
        freeze_provenance(target.provenance, (SentinelSpec(),)),
        "minimal-benign-v1",
        "unit-linux-v1",
        "default-sentinel-v1",
        "policy-journal-test-v1",
    )


def test_journaled_timed_campaign_roundtrip_replays_operator_trace(tmp_path):
    cases = benign_replay_cases()
    target = PythonTarfileTarget()
    config = _configuration(target, cases, len(cases) + 3)
    directory = tmp_path / "journal"
    completed = run_journaled_timed_search_campaign(
        cases,
        target,
        config,
        directory,
        attempt_id="attempt-success",
        experiment_id="policy-journal-test",
    )
    snapshot = read_policy_journal(directory)
    assert snapshot.complete and not snapshot.infrastructure_invalid
    assert snapshot.completed_campaign == completed
    assert len(snapshot.records) == config.campaign.execution_budget
    assert all(record.mutation_attempt is None for record in snapshot.records[: len(cases)])
    assert all(record.mutation_attempt is not None for record in snapshot.records[len(cases) :])
    assert completed.campaign.campaign.result.steps == tuple(
        record.step for record in snapshot.records
    )
    assert len(completed.timing.steps) == len(snapshot.records)
    assert snapshot.completion_sha256 is not None
    assert (
        read_policy_journal(
            directory, expected_completion_sha256=snapshot.completion_sha256
        ).completed_campaign
        == completed
    )
    with pytest.raises(VerificationError, match="completion checksum mismatch"):
        read_policy_journal(directory, expected_completion_sha256="0" * 64)


def test_execution_exception_is_terminal_infrastructure_evidence_not_no_hit(monkeypatch, tmp_path):
    cases = benign_replay_cases()
    target = PythonTarfileTarget()
    config = _configuration(target, cases, len(cases) + 1)
    original = campaign_module.run_case
    calls = 0

    def interrupted(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("controlled campaign interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(campaign_module, "run_case", interrupted)
    directory = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="controlled campaign interruption"):
        run_journaled_timed_search_campaign(
            cases,
            target,
            config,
            directory,
            attempt_id="attempt-failed",
            experiment_id="policy-journal-test",
        )
    snapshot = read_policy_journal(directory)
    assert not snapshot.complete and snapshot.infrastructure_invalid
    assert len(snapshot.records) == 1
    assert snapshot.failure is not None
    assert snapshot.failure.classification == "infrastructure_invalid"
    assert snapshot.failure.context.step_index == 1
    assert snapshot.failure.context.last_fully_completed_step == 0
    assert snapshot.failure_sha256 is not None
    assert not (directory / "completion.json").exists()


def test_failure_ledger_error_does_not_mask_campaign_exception(monkeypatch, tmp_path):
    cases = benign_replay_cases()
    target = PythonTarfileTarget()
    config = _configuration(target, cases, len(cases))

    def campaign_failure(*args, **kwargs):
        raise RuntimeError("primary campaign failure")

    def ledger_failure(*args, **kwargs):
        raise OSError("secondary ledger failure")

    monkeypatch.setattr(campaign_module, "run_case", campaign_failure)
    monkeypatch.setattr(PolicyEvidenceJournal, "fail", ledger_failure)
    with pytest.raises(RuntimeError, match="primary campaign failure") as raised:
        run_journaled_timed_search_campaign(
            cases,
            target,
            config,
            tmp_path / "ledger-failed",
            attempt_id="attempt-ledger-failed",
            experiment_id="policy-journal-test",
        )
    assert any("secondary ledger failure" in note for note in raised.value.__notes__)


def test_hard_interruption_leaves_readable_nonterminal_prefix(monkeypatch, tmp_path):
    cases = benign_replay_cases()
    target = PythonTarfileTarget()
    config = _configuration(target, cases, len(cases) + 1)
    directory = tmp_path / "interrupted"
    writer = PolicyEvidenceJournal.create(
        directory,
        PolicyJournalHeader(
            "attempt-hard-stop",
            "policy-journal-test",
            config,
            "2026-10-16T00:00:00+00:00",
        ),
    )

    def stop(record):
        writer.append(record)
        if record.step.index == 0:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_search_campaign(
            cases,
            target,
            config.campaign,
            provenance=config.provenance,
            completed_record=stop,
        )
    snapshot = read_policy_journal(directory)
    assert len(snapshot.records) == 1
    assert not snapshot.complete and not snapshot.infrastructure_invalid


def test_rehashed_mutation_trace_tamper_fails_deterministic_replay(tmp_path):
    cases = benign_replay_cases()
    target = PythonTarfileTarget()
    config = _configuration(target, cases, len(cases) + 1)
    directory = tmp_path / "tampered"
    writer = PolicyEvidenceJournal.create(
        directory,
        PolicyJournalHeader(
            "attempt-tamper",
            "policy-journal-test",
            config,
            "2026-10-16T00:00:00+00:00",
        ),
    )

    def append(record: SearchCampaignCompletedStep) -> None:
        writer.append(record)

    run_search_campaign(
        cases,
        target,
        config.campaign,
        provenance=config.provenance,
        completed_record=append,
    )
    step_path = directory / f"step-{len(cases):08d}.json"
    record = read_json(step_path.read_bytes())
    assert isinstance(record, dict)
    payload = record["payload"]
    assert isinstance(payload, dict)
    value = payload["value"]
    assert isinstance(value, dict)
    attempt = value["mutation_attempt"]
    assert isinstance(attempt, dict)
    replacement = "add_entry" if attempt["operator_id"] != "add_entry" else "remove_entry"
    attempt["operator_id"] = replacement
    record["payload_sha256"] = sha256(json_bytes(payload)).hexdigest()
    step_path.write_bytes(json_bytes(record) + b"\n")
    with pytest.raises(VerificationError, match="mutation replay mismatch"):
        read_policy_journal(directory)


def test_terminal_and_config_guards_prevent_reuse_or_drift(tmp_path):
    cases = benign_replay_cases()
    target = PythonTarfileTarget()
    config = _configuration(target, cases, len(cases))
    directory = tmp_path / "terminal"
    run_journaled_timed_search_campaign(
        cases,
        target,
        config,
        directory,
        attempt_id="attempt-terminal",
        experiment_id="policy-journal-test",
    )
    with pytest.raises(FileExistsError):
        run_journaled_timed_search_campaign(
            cases,
            target,
            config,
            directory,
            attempt_id="attempt-reuse",
            experiment_id="policy-journal-test",
        )
    wrong = replace(config, initial_case_ids=tuple(reversed(config.initial_case_ids)))
    with pytest.raises(ValueError, match="initial cases differ"):
        run_journaled_timed_search_campaign(
            cases,
            target,
            wrong,
            tmp_path / "wrong",
            attempt_id="attempt-wrong",
            experiment_id="policy-journal-test",
        )
    assert not (tmp_path / "wrong").exists()

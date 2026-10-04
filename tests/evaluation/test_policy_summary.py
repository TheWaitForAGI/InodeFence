"""Policy accounting stays separate from full raw observation counts."""

from dataclasses import replace

import pytest

from inodefence.campaign import SearchCampaignConfig, run_search_campaign
from inodefence.evaluation.policy_binding import PolicyEvaluationConfig, export_bound_policy_result
from inodefence.evaluation.policy_summary import policy_summary_markdown, summarize_policy_campaign
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import SearchPolicy, SearchState, state_signature
from inodefence.model import ExecutionStatus
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.replay.benign import benign_replay_cases
from inodefence.targets.python_tarfile import PythonTarfileTarget


@pytest.fixture(scope="module", params=list(SearchPolicy))
def raw(request):
    cases = benign_replay_cases()
    return run_search_campaign(
        cases, PythonTarfileTarget(), SearchCampaignConfig(17, len(cases), request.param)
    )


def export(tmp_path, result):
    config = PolicyEvaluationConfig(
        result.config,
        result.initial_case_ids,
        result.provenance,
        "unit-fixed-benign-v1",
        "unit-linux-v1",
        "unit-sentinel-v1",
        "unit-protocol-v1",
    )
    directory = tmp_path / "bound"
    return directory, export_bound_policy_result(result, config, directory)


def test_verified_policy_counts_and_raw_digests_are_preserved(raw, tmp_path):
    directory, digest = export(tmp_path, raw)
    summary = summarize_policy_campaign(directory, expected_binding_sha256=digest)
    assert summary["total_executions"] == 4
    assert sum(summary["status_counts"].values()) == 4
    assert summary["unique_state_signature_count"] == raw.final_corpus_stats.unique_states
    assert summary["unique_feedback_key_count"] == raw.unique_feedback_keys
    assert summary["retained_case_count"] == len(raw.retained_case_ids)
    assert summary["active_case_id"] == raw.active_case_id
    assert summary["binding_sha256"] == digest
    assert summary["search_policy"] == raw.config.search_policy.value
    assert "wall_clock" not in summary and "rediscovery" not in summary
    assert "experiment_config_id" not in summary
    text = policy_summary_markdown(summary)
    assert digest in text and raw.config.search_policy.value in text


def test_all_statuses_and_first_hit_arithmetic_on_explicit_synthetic_evidence(raw, tmp_path):
    """Synthetic model-only changes test arithmetic; no security trial is executed."""
    state = SearchState(benign_replay_cases(), raw.config.search_policy)
    steps = []
    for step, status in zip(raw.steps, ExecutionStatus, strict=True):
        result = step.result
        execution = replace(
            result.execution,
            status=status,
            exit_code=0
            if status == ExecutionStatus.SUCCESS
            else None
            if status == ExecutionStatus.TIMED_OUT
            else 1,
        )
        after = result.after
        if step.index == 1:
            after = replace(
                after,
                objects=tuple(
                    replace(obj, mode=0o640) if obj.path == "outside/sentinel.txt" else obj
                    for obj in after.objects
                ),
            )
        result = replace(
            result,
            execution=execution,
            after=after,
            changes=compare_states(result.before, after),
            signature=state_signature(result.before, after),
            violations=evaluate_contracts(result.before, after),
        )
        steps.append(replace(step, result=result, feedback=state.consider(result)))
    synthetic = replace(
        raw,
        steps=tuple(steps),
        final_corpus_stats=state.stats,
        retained_case_ids=tuple(entry.case.case_id for entry in state.entries),
        unique_feedback_keys=state.unique_feedback_keys,
    )
    directory, digest = export(tmp_path, synthetic)
    summary = summarize_policy_campaign(directory, expected_binding_sha256=digest)
    assert summary["status_counts"] == {status.value: 1 for status in ExecutionStatus}
    assert summary["first_observed_contract_violation"] == {"step_index": 1, "execution_count": 2}
    assert summary["contract_observed_counts"] == {"C0": 0, "C1": 0, "C2": 1}
    assert summary["any_contract_observed_count"] == 1
    assert "step 1 (zero-based), execution 2 (one-based)" in policy_summary_markdown(summary)


def test_corruption_or_incomplete_evidence_never_produces_summary(raw, tmp_path):
    directory, digest = export(tmp_path, raw)
    (directory / "campaign" / "result.json").write_bytes(b"partial")
    with pytest.raises(VerificationError):
        summarize_policy_campaign(directory, expected_binding_sha256=digest)


def test_cli_json_markdown_and_anchor_error(raw, tmp_path, monkeypatch, capsys):
    from inodefence.evaluation.policy_summary import main

    directory, digest = export(tmp_path, raw)
    monkeypatch.setattr("sys.argv", ["policy-summary", str(directory), "--binding-sha256", digest])
    assert main() == 0
    assert digest in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["policy-summary", str(directory), "--format", "markdown"])
    assert main() == 0
    assert "Unique projected feedback keys" in capsys.readouterr().out
    monkeypatch.setattr(
        "sys.argv", ["policy-summary", str(directory), "--binding-sha256", "0" * 64]
    )
    assert main() == 1
    assert "checksum" in capsys.readouterr().err

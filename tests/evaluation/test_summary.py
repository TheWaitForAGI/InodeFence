"""Aggregation arithmetic on verified benign and explicitly synthetic unit evidence."""

from dataclasses import replace

import pytest

from inodefence.campaign_export import export_campaign
from inodefence.evaluation.summary import summarize_campaign, summary_markdown
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import Corpus, state_signature
from inodefence.model import ExecutionStatus
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts


def test_benign_verified_counts_and_no_hit_are_not_estimated(bundle, campaign):
    summary = summarize_campaign(bundle)
    assert summary["total_executions"] == 4
    assert summary["status_counts"] == {"success": 4, "rejected": 0, "failed": 0, "timed_out": 0}
    assert summary["contract_observed_counts"] == {"C0": 0, "C1": 0, "C2": 0}
    assert summary["any_contract_observed_count"] == 0
    assert summary["first_observed_contract_violation"] is None
    assert summary["unique_case_count"] == 4
    assert summary["retained_case_count"] == campaign.final_corpus_stats.retained_cases
    assert summary["unique_state_signature_count"] == campaign.final_corpus_stats.unique_states
    assert summary["unique_violation_fingerprint_count"] == 0
    assert "time" not in summary and "wall_clock" not in summary
    assert "First observation: none within" in summary_markdown(summary)


def test_all_statuses_and_first_hit_use_recorded_step_order(tmp_path, campaign):
    corpus, steps = Corpus(), []
    for step, status in zip(campaign.steps, ExecutionStatus, strict=True):
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
        steps.append(replace(step, result=result, feedback=corpus.consider(result)))
    synthetic = replace(
        campaign,
        steps=tuple(steps),
        final_corpus_stats=corpus.stats,
        retained_case_ids=tuple(entry.case.case_id for entry in corpus.entries),
    )
    destination = tmp_path / "synthetic-aggregation-unit-input"
    export_campaign(synthetic, destination)
    summary = summarize_campaign(destination)
    assert summary["status_counts"] == {status.value: 1 for status in ExecutionStatus}
    assert summary["contract_observed_counts"] == {"C0": 0, "C1": 0, "C2": 1}
    assert summary["any_contract_observed_count"] == 1
    assert summary["first_observed_contract_violation"] == {"step_index": 1, "execution_count": 2}
    assert summary["unique_violation_fingerprint_count"] == 1
    assert "step 1 (zero-based), execution 2 (one-based)" in summary_markdown(summary)


def test_corrupted_or_partial_evidence_is_never_summarized(bundle):
    (bundle / "steps.jsonl").write_bytes(b"partial")
    with pytest.raises(VerificationError):
        summarize_campaign(bundle)

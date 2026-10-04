"""Actual benign runs plus explicitly synthetic unit arithmetic, not paper evidence."""

from dataclasses import replace

import pytest

from inodefence.campaign import SearchCampaignConfig, run_search_campaign
from inodefence.evaluation.policy_binding import PolicyEvaluationConfig, export_bound_policy_result
from inodefence.evaluation.policy_dataset import PolicyDatasetMember
from inodefence.evaluation.policy_statistics import summarize_policy_statistics
from inodefence.evaluation.statistics import statistics_markdown
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import SearchPolicy, SearchState, state_signature
from inodefence.model import ExecutionStatus
from inodefence.model.provenance import SourceProvenance
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.replay.benign import benign_replay_cases
from inodefence.targets.python_tarfile import PythonTarfileTarget


def member(path, *, seed=17, policy=SearchPolicy.B0, synthetic_hit=False):
    cases = benign_replay_cases()
    raw = run_search_campaign(
        cases, PythonTarfileTarget(), SearchCampaignConfig(seed, len(cases), policy)
    )
    # This placeholder checks metadata compatibility; never genuine source attribution.
    raw = replace(raw, provenance=replace(raw.provenance, source=SourceProvenance("a" * 40, False)))
    if synthetic_hit:
        state, steps = SearchState(cases, policy), []
        for step in raw.steps:
            result, after = step.result, step.result.after
            execution = result.execution
            if step.index == 0:
                execution = replace(execution, status=ExecutionStatus.TIMED_OUT, exit_code=None)
            if step.index == 2:
                after = replace(
                    after,
                    objects=tuple(
                        replace(obj, mode=0o640) if obj.path == "outside/sentinel.txt" else obj
                        for obj in after.objects
                    ),
                )
            result = replace(
                result,
                after=after,
                execution=execution,
                changes=compare_states(result.before, after),
                signature=state_signature(result.before, after),
                violations=evaluate_contracts(result.before, after),
            )
            steps.append(replace(step, result=result, feedback=state.consider(result)))
        raw = replace(
            raw,
            steps=tuple(steps),
            final_corpus_stats=state.stats,
            retained_case_ids=tuple(entry.case.case_id for entry in state.entries),
            unique_feedback_keys=state.unique_feedback_keys,
        )
    config = PolicyEvaluationConfig(
        raw.config,
        raw.initial_case_ids,
        raw.provenance,
        "unit-fixed-benign-v1",
        "unit-linux-v1",
        "unit-sentinel-v1",
        "unit-statistics-v1",
    )
    digest = export_bound_policy_result(raw, config, path)
    return PolicyDatasetMember(path, digest)


def test_empty_template_never_invents_measurements():
    result = summarize_policy_statistics(())
    assert result["classification"] == "empty-template"
    assert result["number_valid_runs"] == 0
    assert result["number_invalid_runs"] is None
    assert result["any_contract_observation_proportion"]["value"] is None
    assert result["first_hit_execution_count"]["median"] is None
    assert result["evaluation_config_ids"] == ()


def test_explicit_synthetic_first_hit_and_no_hit_denominators(tmp_path):
    a = member(tmp_path / "benign-no-hit", seed=17)
    b = member(tmp_path / "synthetic-arithmetic-only", seed=-23, synthetic_hit=True)
    result = summarize_policy_statistics((a, b), allow_seed_variation=True)
    assert result["number_valid_runs"] == 2 and result["number_invalid_runs"] is None
    assert result["any_contract_observation_proportion"] == {
        "numerator": 1,
        "denominator": 2,
        "value": 0.5,
    }
    assert result["process_success_proportion"] == {
        "numerator": 7,
        "denominator": 8,
        "value": 7 / 8,
    }
    assert result["number_no_hit_runs"] == 1
    assert result["censored_runs"][0]["execution_budget"] == 4
    first = result["first_hit_execution_count"]
    assert first["population"] == "runs_with_observation_only"
    assert (first["median"], first["iqr"], first["min"], first["max"]) == (3, 0, 3, 3)
    assert result["binding_sha256"] == (a.expected_binding_sha256, b.expected_binding_sha256)
    assert "not_available" in result["rediscovery_classification"]
    assert "right-censored" in statistics_markdown(result)


def test_seed_policy_strata_duplicates_and_corrupt_inputs_are_not_pooled(tmp_path):
    a = member(tmp_path / "a")
    b = member(tmp_path / "different-seed", seed=23)
    other = member(tmp_path / "different-policy", policy=SearchPolicy.B1)
    for selected, allow in (((a, b), False), ((a, other), True), ((a, a), True)):
        with pytest.raises(VerificationError, match="cannot be pooled"):
            summarize_policy_statistics(selected, allow_seed_variation=allow)
    (b.directory / "binding.json").write_bytes(b"torn")
    with pytest.raises(VerificationError):
        summarize_policy_statistics((a, b), allow_seed_variation=True)


def test_cli_empty_json_and_markdown_invalid_input(tmp_path, monkeypatch, capsys):
    from inodefence.evaluation.policy_statistics import main

    monkeypatch.setattr("sys.argv", ["policy-statistics"])
    assert main() == 0
    assert '"empty-template"' in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["policy-statistics", "--format", "markdown"])
    assert main() == 0
    assert "Invalid runs: None" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["policy-statistics", str(tmp_path / "missing")])
    assert main() == 1
    assert "cannot be pooled" in capsys.readouterr().err

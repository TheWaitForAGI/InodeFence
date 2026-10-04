"""Benign raw runs plus explicitly synthetic source metadata for comparison tests."""

from dataclasses import replace

import pytest

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.evaluation.dataset import DatasetMember
from inodefence.evaluation.failure import FailureContext, FailurePhase, failure_record
from inodefence.evaluation.repeated import RepetitionController, RepetitionPlan
from inodefence.evaluation.statistics import (
    _distribution,
    statistics_markdown,
    summarize_repetition_statistics,
    summarize_statistics,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.experiment_config import (
    FEEDBACK_POLICY,
    MUTATION_POLICY,
    SEED_PROFILE,
    ExperimentConfig,
)
from inodefence.generator import minimal_seed_corpus
from inodefence.model.provenance import SourceProvenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.python_tarfile import PythonTarfileTarget


def member(path, *, seed=17, profile="unit-statistics-v1"):
    target = PythonTarfileTarget()
    cases = minimal_seed_corpus()
    result = run_campaign(cases, target, CampaignConfig(seed, len(cases)))
    result = replace(
        result, provenance=replace(result.provenance, source=SourceProvenance("a" * 40, False))
    )
    config = ExperimentConfig(
        target.provenance,
        SEED_PROFILE,
        result.initial_case_ids,
        result.config,
        MUTATION_POLICY,
        FEEDBACK_POLICY,
        (SentinelSpec(),),
        profile,
    )
    result = replace(result, experiment_config_id=config.config_id)
    export_campaign(result, path, experiment_config_json=config.to_json())
    return DatasetMember(path, "unit-statistics-protocol-v1"), result, config


def test_empty_template_and_defined_quantile_math():
    template = summarize_statistics(())
    assert template["classification"] == "empty-template"
    assert template["number_valid_runs"] == 0
    assert template["number_invalid_runs"] is None
    assert template["any_contract_observation_proportion"]["value"] is None
    assert template["first_hit_execution_count"]["median"] is None
    observed = _distribution((7, 1, 5, 3))
    assert (observed["q1"], observed["median"], observed["q3"], observed["iqr"]) == (
        2.5,
        4.0,
        5.5,
        3.0,
    )
    assert (observed["min"], observed["max"]) == (1, 7)
    assert _distribution((4,))["iqr"] == 0
    with pytest.raises(ValueError):
        _distribution((True,))


def test_compatible_benign_runs_keep_no_hit_censoring_explicit(tmp_path):
    a, _, _ = member(tmp_path / "a", seed=17)
    b, _, _ = member(tmp_path / "b", seed=23)
    result = summarize_statistics((a, b), allow_seed_variation=True)
    assert result["number_valid_runs"] == 2
    assert result["number_invalid_runs"] is None
    assert result["any_contract_observation_proportion"] == {
        "numerator": 0,
        "denominator": 2,
        "value": 0.0,
    }
    assert result["number_no_hit_runs"] == 2
    assert [item["execution_budget"] for item in result["censored_runs"]] == [4, 4]
    assert result["first_hit_execution_count"]["median"] is None
    assert result["process_success_proportion"]["denominator"] == 8
    assert "right-censored" in statistics_markdown(result)


def test_incompatible_duplicate_or_corrupt_runs_are_not_silently_pooled(tmp_path):
    a, _, _ = member(tmp_path / "a", seed=17)
    b, _, _ = member(tmp_path / "b", seed=23)
    for selected in ((a, b), (a, a)):
        with pytest.raises(VerificationError, match="cannot be pooled"):
            summarize_statistics(selected)
    different, _, _ = member(tmp_path / "profile", profile="unit-different")
    with pytest.raises(VerificationError, match="cannot be pooled"):
        summarize_statistics((a, different), allow_seed_variation=True)
    (a.directory / "steps.jsonl").write_bytes(b"torn")
    with pytest.raises(VerificationError):
        summarize_statistics((a,))


def test_resolved_plan_counts_invalid_slots_outside_observation_denominator(tmp_path):
    source_member, raw, config = member(tmp_path / "source")
    protocol = source_member.protocol_version
    assert protocol is not None
    plan = RepetitionPlan(config.to_json(), (17, 23), raw.provenance)
    controller = RepetitionController.create(tmp_path / "runs", plan)
    slot = controller.claim(0, attempt_id="completed")
    export_campaign(raw, slot / "evidence", experiment_config_json=config.to_json())
    controller.complete(0)
    with pytest.raises(VerificationError, match="unresolved"):
        summarize_repetition_statistics(controller.root, protocol_version=protocol)
    controller.claim(1, attempt_id="failed")
    snapshot = controller.snapshot()
    context = FailureContext(
        "failed",
        snapshot.plan_sha256,
        plan.provenance.source,
        plan.provenance.target,
        None,
        FailurePhase.UNKNOWN,
        config_id=plan.config_for(1).config_id,
    )
    controller.record_failure(1, failure_record(OSError("injected failure"), context))
    result = summarize_repetition_statistics(controller.root, protocol_version=protocol)
    assert result["number_planned_runs"] == 2
    assert result["number_invalid_runs"] == 1 and result["number_valid_runs"] == 1
    assert result["any_contract_observation_proportion"]["denominator"] == 1
    assert result["number_no_hit_runs"] == 1
    failure = controller.root / "run-00000001" / "failure.json"
    failure.write_bytes(failure.read_bytes()[:-2])
    with pytest.raises(VerificationError):
        summarize_repetition_statistics(controller.root, protocol_version=protocol)


def test_failure_only_plan_has_no_invented_observation_proportions(tmp_path):
    _, raw, config = member(tmp_path / "source")
    plan = RepetitionPlan(config.to_json(), (17,), raw.provenance)
    controller = RepetitionController.create(tmp_path / "runs", plan)
    controller.claim(0, attempt_id="failed")
    context = FailureContext(
        "failed",
        controller.snapshot().plan_sha256,
        plan.provenance.source,
        plan.provenance.target,
        None,
        FailurePhase.UNKNOWN,
        config_id=config.config_id,
    )
    controller.record_failure(0, failure_record(OSError("injected"), context))
    result = summarize_repetition_statistics(controller.root, protocol_version="unit-statistics-v1")
    assert result["classification"] == "no-valid-completed-runs"
    assert result["number_valid_runs"] == 0 and result["number_invalid_runs"] == 1
    assert result["any_contract_observation_proportion"]["value"] is None
    assert result["first_hit_execution_count"]["median"] is None
    assert result["run_states"][0]["terminal"]["artifact"]["name"] == "failure.json"

"""Condition comparison with explicitly synthetic metadata, never paper results."""

from dataclasses import replace

import pytest

from inodefence.campaign import SearchCampaignConfig, run_search_campaign
from inodefence.evaluation.dataset import Compatibility
from inodefence.evaluation.policy_binding import PolicyEvaluationConfig, export_bound_policy_result
from inodefence.evaluation.policy_dataset import PolicyDatasetMember, validate_policy_dataset
from inodefence.feedback import FeedbackProjection, SearchPolicy, SearchState
from inodefence.model.provenance import SourceProvenance
from inodefence.mutator import MutationPolicy
from inodefence.replay.benign import benign_replay_cases
from inodefence.targets.python_tarfile import PythonTarfileTarget


@pytest.fixture(scope="module")
def raw():
    """Fresh distinct benign executions; config/source labels below are synthetic."""
    cases = benign_replay_cases()
    return tuple(
        run_search_campaign(
            cases, PythonTarfileTarget(), SearchCampaignConfig(17, len(cases), SearchPolicy.B0)
        )
        for _ in range(2)
    )


def export_member(tmp_path, name, raw, *, config_change=None, provenance_change=None, **profiles):
    config = raw.config if config_change is None else config_change(raw.config)
    provenance = replace(raw.provenance, source=SourceProvenance("a" * 40, False))
    if provenance_change is not None:
        provenance = provenance_change(provenance)
    state = SearchState(
        benign_replay_cases(), config.search_policy, projection=config.feedback_projection
    )
    steps = tuple(replace(step, feedback=state.consider(step.result)) for step in raw.steps)
    result = replace(
        raw,
        config=config,
        provenance=provenance,
        steps=steps,
        final_corpus_stats=state.stats,
        retained_case_ids=tuple(entry.case.case_id for entry in state.entries),
        unique_feedback_keys=state.unique_feedback_keys,
    )
    declaration = PolicyEvaluationConfig(
        config,
        result.initial_case_ids,
        provenance,
        "unit-fixed-benign-v1",
        "unit-linux-v1",
        "unit-sentinel-v1",
        "unit-protocol-v1",
    )
    declaration = replace(declaration, **profiles)
    directory = tmp_path / name
    digest = export_bound_policy_result(result, declaration, directory)
    return PolicyDatasetMember(directory, digest)


def test_distinct_runs_same_conditions_compatible(raw, tmp_path):
    a = export_member(tmp_path, "a", raw[0])
    b = export_member(tmp_path, "b", raw[1])
    report = validate_policy_dataset((a, b))
    assert report.compatibility == Compatibility.COMPATIBLE
    assert report.strata == ((0, 1),)
    assert report.binding_sha256 == (a.expected_binding_sha256, b.expected_binding_sha256)
    assert len(set(report.campaign_manifest_sha256)) == 2


@pytest.mark.parametrize(
    "dimension,change",
    [
        ("search_policy", lambda config: replace(config, search_policy=SearchPolicy.B1)),
        ("mutation_policy", lambda config: replace(config, mutation_policy=MutationPolicy.M1)),
        (
            "feedback_projection",
            lambda config: replace(config, feedback_projection=FeedbackProjection.A1),
        ),
        ("random_seed", lambda config: replace(config, random_seed=-23)),
    ],
)
def test_declared_policy_and_seed_differences_require_explicit_strata(
    raw, tmp_path, dimension, change
):
    a = export_member(tmp_path, "a", raw[0])
    b = export_member(tmp_path, "b", raw[1], config_change=change)
    report = validate_policy_dataset((a, b))
    assert report.compatibility == Compatibility.REQUIRES_STRATIFICATION
    assert report.strata == ((0,), (1,))
    assert {item.dimension for item in report.differences} == {dimension}
    allowed = validate_policy_dataset((a, b), allow_seed_variation=True)
    assert allowed.compatibility == (
        Compatibility.COMPATIBLE
        if dimension == "random_seed"
        else Compatibility.REQUIRES_STRATIFICATION
    )


@pytest.mark.parametrize("dimension", ["seed_profile", "sentinel_profile", "protocol_version"])
def test_hard_profile_differences_cannot_be_pooled(raw, tmp_path, dimension):
    a = export_member(tmp_path, "a", raw[0])
    b = export_member(tmp_path, "b", raw[1], **{dimension: "different-v1"})
    report = validate_policy_dataset((a, b))
    assert report.compatibility == Compatibility.INCOMPATIBLE
    assert report.strata == ()
    assert dimension in {item.dimension for item in report.differences}


def test_runtime_and_environment_profile_differences_require_strata(raw, tmp_path):
    a = export_member(tmp_path, "a", raw[0])
    b = export_member(
        tmp_path,
        "b",
        raw[1],
        environment_profile="other-linux-v1",
        provenance_change=lambda value: replace(
            value, environment=replace(value.environment, release="unit-other-kernel")
        ),
    )
    report = validate_policy_dataset((a, b))
    assert report.compatibility == Compatibility.REQUIRES_STRATIFICATION
    assert {item.dimension for item in report.differences} == {
        "environment_profile",
        "harness_runtime",
    }


@pytest.mark.parametrize("source", [SourceProvenance(), SourceProvenance("a" * 40, True)])
def test_unknown_or_dirty_source_never_becomes_comparable(raw, tmp_path, source):
    a = export_member(
        tmp_path, "a", raw[0], provenance_change=lambda value: replace(value, source=source)
    )
    report = validate_policy_dataset((a,))
    assert report.compatibility == Compatibility.INCOMPATIBLE
    assert report.binding_sha256 == (None,)
    assert "clean pinned source" in report.differences[0].detail


def test_unknown_runtime_and_source_revision_drift_fail_closed(raw, tmp_path):
    unknown = export_member(
        tmp_path,
        "unknown",
        raw[0],
        provenance_change=lambda value: replace(
            value, environment=replace(value.environment, python_version="")
        ),
    )
    assert validate_policy_dataset((unknown,)).compatibility == Compatibility.INCOMPATIBLE
    a = export_member(tmp_path, "a", raw[0])
    b = export_member(
        tmp_path,
        "b",
        raw[1],
        provenance_change=lambda value: replace(value, source=SourceProvenance("b" * 40, False)),
    )
    report = validate_policy_dataset((a, b))
    assert report.compatibility == Compatibility.INCOMPATIBLE
    assert report.strata == ()


def test_changed_actual_budget_seed_order_and_timeout_are_hard_differences(raw, tmp_path):
    a = export_member(tmp_path, "a", raw[0])
    cases = benign_replay_cases()[:3]
    shorter = run_search_campaign(
        cases, PythonTarfileTarget(5.0), SearchCampaignConfig(17, len(cases), SearchPolicy.B0)
    )
    b = export_member(tmp_path, "shorter", shorter)
    report = validate_policy_dataset((a, b))
    assert report.compatibility == Compatibility.INCOMPATIBLE
    assert report.strata == ()
    dimensions = {item.dimension for item in report.differences}
    assert {"execution_budget", "initial_case_ids", "timeout_seconds"} <= dimensions


def test_copied_raw_execution_relabelled_config_is_never_an_independent_run(raw, tmp_path):
    a = export_member(tmp_path, "a", raw[0])
    copied = export_member(
        tmp_path,
        "copied",
        raw[0],
        environment_profile="relabeled-v1",
        config_change=lambda config: replace(config, random_seed=99),
    )
    report = validate_policy_dataset((a, copied), allow_seed_variation=True)
    assert report.compatibility == Compatibility.INCOMPATIBLE
    assert report.strata == ()
    assert any("duplicate_execution" in item.dimension for item in report.differences)


def test_missing_corrupt_or_legacy_input_is_not_silently_excluded(raw, tmp_path, bundle):
    a = export_member(tmp_path, "a", raw[0])
    corrupt = export_member(tmp_path, "corrupt", raw[1])
    (corrupt.directory / "binding.json").write_bytes(b"{}")
    report = validate_policy_dataset((a, corrupt))
    assert report.compatibility == Compatibility.INCOMPATIBLE
    assert report.binding_sha256 == (a.expected_binding_sha256, None)
    assert report.strata == ()
    assert (
        validate_policy_dataset((PolicyDatasetMember(bundle),)).compatibility
        == Compatibility.INCOMPATIBLE
    )
    assert validate_policy_dataset(()).compatibility == Compatibility.INCOMPATIBLE


def test_cli_distinguishes_compatible_and_stratified(raw, tmp_path, monkeypatch, capsys):
    from inodefence.evaluation.policy_dataset import main

    a = export_member(tmp_path, "a", raw[0])
    b = export_member(
        tmp_path, "b", raw[1], config_change=lambda config: replace(config, random_seed=23)
    )
    monkeypatch.setattr("sys.argv", ["policy-dataset", str(a.directory), str(b.directory)])
    assert main() == 1
    assert '"requires_stratification"' in capsys.readouterr().out
    monkeypatch.setattr(
        "sys.argv", ["policy-dataset", str(a.directory), str(b.directory), "--allow-seed-variation"]
    )
    assert main() == 0
    assert '"compatible"' in capsys.readouterr().out

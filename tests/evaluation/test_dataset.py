"""Comparison rules with explicit synthetic metadata and fresh benign executions."""

from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.evaluation.dataset import Compatibility, DatasetMember, validate_dataset
from inodefence.evaluation.verify import verify_campaign
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


def export_member(tmp_path, name, *, seed=17, source=None, profile="unit-linux-v1", timeout=10.0):
    target = PythonTarfileTarget(timeout)
    seeds = minimal_seed_corpus()
    result = run_campaign(seeds, target, CampaignConfig(seed, len(seeds)))
    # Deliberately synthetic source metadata tests comparison, not authorship.
    result = replace(
        result,
        provenance=replace(
            result.provenance,
            source=source if source is not None else SourceProvenance("a" * 40, False),
        ),
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
    directory = tmp_path / name
    export_campaign(result, directory, experiment_config_json=config.to_json())
    digest = sha256((directory / "manifest.json").read_bytes()).hexdigest()
    return DatasetMember(directory, "unit-protocol-v1", digest)


def test_identical_recorded_conditions_compatible_with_distinct_raw_runs(tmp_path):
    a, b = export_member(tmp_path, "a"), export_member(tmp_path, "b")
    report = validate_dataset((a, b))
    assert report.compatibility == Compatibility.COMPATIBLE
    assert report.strata == ((0, 1),)
    assert len(report.manifest_sha256) == 2 and report.differences == ()
    assert (
        verify_campaign(a.directory).experiment_config_bytes
        == (a.directory / "experiment.json").read_bytes()
    )


def test_random_seed_variation_requires_explicit_repetition_policy(tmp_path):
    a, b = export_member(tmp_path, "a", seed=17), export_member(tmp_path, "b", seed=23)
    report = validate_dataset((a, b))
    assert report.compatibility == Compatibility.REQUIRES_STRATIFICATION
    assert {item.dimension for item in report.differences} == {"random_seed"}
    assert report.strata == ((0,), (1,))
    assert (
        validate_dataset((a, b), allow_seed_variation=True).compatibility
        == Compatibility.COMPATIBLE
    )


def test_environment_profiles_require_stratification(tmp_path):
    a = export_member(tmp_path, "a", profile="unit-linux-a")
    b = export_member(tmp_path, "b", profile="unit-linux-b")
    report = validate_dataset((a, b))
    assert report.compatibility == Compatibility.REQUIRES_STRATIFICATION
    assert report.strata == ((0,), (1,))
    assert {item.dimension for item in report.differences} == {"environment_profile"}


@pytest.mark.parametrize("change", ["source", "timeout", "protocol"])
def test_hard_differences_are_incompatible(tmp_path, change):
    a = export_member(tmp_path, "a")
    b = export_member(
        tmp_path,
        "b",
        source=SourceProvenance("b" * 40, False) if change == "source" else None,
        timeout=5.0 if change == "timeout" else 10.0,
    )
    if change == "protocol":
        b = replace(b, protocol_version="different-protocol-v2")
    report = validate_dataset((a, b))
    assert report.compatibility == Compatibility.INCOMPATIBLE
    assert report.strata == ()


def test_missing_config_protocol_unknown_source_and_duplicates_are_not_pooled(tmp_path, bundle):
    assert (
        validate_dataset((DatasetMember(bundle, "unit-protocol-v1"),)).compatibility
        == Compatibility.INCOMPATIBLE
    )
    a = export_member(tmp_path, "a")
    assert (
        validate_dataset((replace(a, protocol_version=None),)).compatibility
        == Compatibility.INCOMPATIBLE
    )
    assert validate_dataset((a, a)).compatibility == Compatibility.INCOMPATIBLE
    unknown = export_member(tmp_path, "unknown", source=SourceProvenance())
    assert validate_dataset((unknown,)).compatibility == Compatibility.INCOMPATIBLE
    dirty = export_member(tmp_path, "dirty", source=SourceProvenance("a" * 40, True))
    assert validate_dataset((dirty,)).compatibility == Compatibility.INCOMPATIBLE
    assert validate_dataset(()).compatibility == Compatibility.INCOMPATIBLE


def test_bound_config_cannot_lie_about_execution_settings(tmp_path):
    from inodefence.evaluation.encoding import json_bytes, read_json

    member = export_member(tmp_path, "a")
    config_path = member.directory / "experiment.json"
    config = read_json(config_path.read_bytes())
    assert isinstance(config, dict)
    config["campaign"]["random_seed"] = 99
    config_bytes = json_bytes(config)
    config_path.write_bytes(config_bytes + b"\n")
    manifest_path = member.directory / "manifest.json"
    manifest = read_json(manifest_path.read_bytes())
    assert isinstance(manifest, dict)
    manifest["experiment_config_id"] = sha256(config_bytes).hexdigest()
    manifest["experiment_config_sha256"] = sha256(config_path.read_bytes()).hexdigest()
    manifest_path.write_bytes(json_bytes(manifest) + b"\n")
    report = validate_dataset((replace(member, expected_manifest_sha256=None),))
    assert report.compatibility == Compatibility.INCOMPATIBLE
    assert "execution binding" in report.differences[0].detail

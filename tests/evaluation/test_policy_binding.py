"""Explicit evaluation binding on actual fixed benign seed-only observations."""

from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.campaign import SearchCampaignConfig, run_search_campaign
from inodefence.evaluation.encoding import json_bytes, read_json
from inodefence.evaluation.policy_binding import (
    PolicyEvaluationConfig,
    export_bound_policy_result,
    verify_bound_policy_evidence,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import SearchPolicy
from inodefence.mutator import MutationPolicy
from inodefence.replay.benign import benign_replay_cases
from inodefence.targets.python_tarfile import PythonTarfileTarget


@pytest.fixture(scope="module")
def declared():
    cases = benign_replay_cases()
    result = run_search_campaign(
        cases, PythonTarfileTarget(), SearchCampaignConfig(17, len(cases), SearchPolicy.B0)
    )
    config = PolicyEvaluationConfig(
        result.config,
        result.initial_case_ids,
        result.provenance,
        "fixed-benign-fixtures-v1",
        "unit-linux-reference-v1",
        "default-sentinel-v1",
        "unit-format-check-v1",
    )
    return result, config


def test_declaration_and_every_raw_field_roundtrip(declared, tmp_path):
    result, config = declared
    directory = tmp_path / "bound"
    digest = export_bound_policy_result(result, config, directory)
    verified = verify_bound_policy_evidence(directory, expected_binding_sha256=digest)
    assert verified.config == config
    assert verified.campaign.result == result
    assert verified.binding_sha256 == digest
    assert verified.config.config_id == config.config_id
    assert verified.config.campaign.search_policy == SearchPolicy.B0


def test_protected_component_policy_id_roundtrips_in_bound_evidence(tmp_path):
    cases = benign_replay_cases()
    result = run_search_campaign(
        cases,
        PythonTarfileTarget(),
        SearchCampaignConfig(
            17,
            len(cases),
            SearchPolicy.B0,
            MutationPolicy.M1_PROTECTED_COMPONENTS,
        ),
    )
    config = PolicyEvaluationConfig(
        result.config,
        result.initial_case_ids,
        result.provenance,
        "fixed-benign-fixtures-v1",
        "unit-linux-reference-v1",
        "default-sentinel-v1",
        "protected-components-binding-v1",
    )

    digest = export_bound_policy_result(result, config, tmp_path / "bound")
    verified = verify_bound_policy_evidence(tmp_path / "bound", expected_binding_sha256=digest)

    assert verified.config.campaign.mutation_policy == MutationPolicy.M1_PROTECTED_COMPONENTS
    assert verified.campaign.result.config == result.config


@pytest.mark.parametrize(
    "change",
    [
        lambda config: replace(config, campaign=replace(config.campaign, random_seed=-17)),
        lambda config: replace(config, campaign=replace(config.campaign, execution_budget=5)),
        lambda config: replace(
            config, campaign=replace(config.campaign, search_policy=SearchPolicy.B1)
        ),
        lambda config: replace(config, initial_case_ids=config.initial_case_ids[::-1]),
        lambda config: replace(
            config,
            provenance=replace(
                config.provenance,
                target=replace(config.provenance.target, timeout_seconds=123.0),
            ),
        ),
    ],
)
def test_declared_execution_mismatch_rejected_before_publication(declared, tmp_path, change):
    result, config = declared
    directory = tmp_path / "invalid"
    with pytest.raises(ValueError, match="declaration differs"):
        export_bound_policy_result(result, change(config), directory)
    assert not directory.exists()


@pytest.mark.parametrize("label", ["", "profile with spaces", "../profile", "profile\0"])
def test_missing_or_unstable_profile_is_not_inferred(declared, label):
    _, config = declared
    with pytest.raises(ValueError, match="stable version"):
        replace(config, environment_profile=label)


def modify(path, change):
    record = read_json(path.read_bytes())
    assert isinstance(record, dict)
    change(record["payload"]["value"])
    record["payload_sha256"] = sha256(json_bytes(record["payload"])).hexdigest()
    path.write_bytes(json_bytes(record) + b"\n")
    return sha256(path.read_bytes()).hexdigest()


def test_coherent_config_rehash_cannot_hide_execution_mismatch(declared, tmp_path):
    result, config = declared
    directory = tmp_path / "bound"
    export_bound_policy_result(result, config, directory)
    config_path = directory / "evaluation-config.json"
    digest = modify(config_path, lambda value: value["campaign"].update(random_seed=99))
    changed = replace(config, campaign=replace(config.campaign, random_seed=99))

    def rebind(value):
        value["config"]["sha256"] = digest
        value["config_id"] = changed.config_id

    modify(directory / "binding.json", rebind)
    with pytest.raises(VerificationError, match="declaration differs"):
        verify_bound_policy_evidence(directory)


@pytest.mark.parametrize(
    "artifact", ["binding.json", "evaluation-config.json", "campaign/manifest.json"]
)
def test_corrupt_or_missing_bound_artifacts_fail_closed(declared, tmp_path, artifact):
    result, config = declared
    directory = tmp_path / "bound"
    digest = export_bound_policy_result(result, config, directory)
    path = directory / artifact
    content = path.read_bytes()
    path.write_bytes(content[:-12])
    with pytest.raises(VerificationError):
        verify_bound_policy_evidence(directory, expected_binding_sha256=digest)
    path.unlink()
    with pytest.raises(VerificationError):
        verify_bound_policy_evidence(directory)


def test_symlink_and_forged_anchor_rejected_existing_output_preserved(declared, tmp_path):
    result, config = declared
    directory = tmp_path / "bound"
    digest = export_bound_policy_result(result, config, directory)
    with pytest.raises(VerificationError, match="checksum"):
        verify_bound_policy_evidence(directory, expected_binding_sha256="0" * 64)
    with pytest.raises(FileExistsError):
        export_bound_policy_result(result, config, directory)
    assert verify_bound_policy_evidence(directory).binding_sha256 == digest
    linked = tmp_path / "linked"
    linked.symlink_to(directory, target_is_directory=True)
    with pytest.raises(VerificationError):
        verify_bound_policy_evidence(linked)


def test_failed_binding_marker_preserves_raw_but_never_completes(declared, tmp_path, monkeypatch):
    from inodefence.evaluation import policy_binding

    result, config = declared
    original = policy_binding.write_record

    def fail_marker(path, value):
        if path.name == "binding.json":
            raise OSError("controlled binding publication failure")
        return original(path, value)

    monkeypatch.setattr(policy_binding, "write_record", fail_marker)
    directory = tmp_path / "incomplete"
    with pytest.raises(OSError, match="controlled binding"):
        export_bound_policy_result(result, config, directory)
    assert (directory / "campaign" / "result.json").is_file()
    with pytest.raises(VerificationError):
        verify_bound_policy_evidence(directory)

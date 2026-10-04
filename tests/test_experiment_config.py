"""Explicit configuration identity and pre-execution binding."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from inodefence.campaign import CampaignConfig
from inodefence.campaign_export import export_campaign
from inodefence.experiment_config import (
    FEEDBACK_POLICY,
    MUTATION_POLICY,
    SEED_PROFILE,
    ExperimentConfig,
    run_configured_campaign,
)
from inodefence.generator import minimal_seed_corpus
from inodefence.runtime import SentinelSpec
from inodefence.targets import PythonTarfileTarget


def _config() -> ExperimentConfig:
    return ExperimentConfig(
        PythonTarfileTarget(5.0).provenance,
        SEED_PROFILE,
        tuple(case.case_id for case in minimal_seed_corpus()),
        CampaignConfig(11, 4),
        MUTATION_POLICY,
        FEEDBACK_POLICY,
        (SentinelSpec(),),
        "linux-development-v1",
    )


def test_json_roundtrip_and_field_order_do_not_change_identity() -> None:
    config = _config()
    assert ExperimentConfig.from_json(config.to_json()) == config
    value = json.loads(config.to_json())
    reversed_fields = dict(reversed(tuple(value.items())))
    other = ExperimentConfig.from_json(json.dumps(reversed_fields))
    assert config.config_id == other.config_id
    assert len(config.config_id) == 64


@pytest.mark.parametrize("field", tuple(json.loads(_config().to_json())))
def test_missing_research_critical_fields_rejected(field: str) -> None:
    value = json.loads(_config().to_json())
    del value[field]
    with pytest.raises(ValueError):
        ExperimentConfig.from_json(json.dumps(value))


@pytest.mark.parametrize(
    "changes",
    (
        {"campaign": CampaignConfig(12, 4)},
        {"campaign": CampaignConfig(11, 5)},
        {"target": replace(PythonTarfileTarget(5).provenance, target_version="3.12.99")},
        {"sentinels": (SentinelSpec(content=b"different"),)},
    ),
)
def test_research_conditions_change_identity(changes) -> None:
    config = _config()
    assert replace(config, **changes).config_id != config.config_id


def test_sentinel_order_and_equivalent_timeout_numbers_have_same_identity() -> None:
    config = replace(_config(), sentinels=(SentinelSpec("z"), SentinelSpec("a")))
    other = replace(
        config,
        sentinels=tuple(reversed(config.sentinels)),
        target=replace(config.target, timeout_seconds=5),
    )
    assert config.config_id == other.config_id
    assert ExperimentConfig.from_json(config.to_json()) == config


@pytest.mark.parametrize(
    "changes",
    (
        {"seed_profile": ""},
        {"mutation_policy": "unsupported"},
        {"feedback_policy": "unsupported"},
        {"environment_profile": ""},
        {"initial_case_ids": []},
        {"sentinels": ()},
        {"sentinels": (SentinelSpec(), SentinelSpec())},
    ),
)
def test_invalid_typed_configuration_rejected(changes) -> None:
    with pytest.raises(ValueError):
        replace(_config(), **changes)


@pytest.mark.parametrize("value", ('{"schema_version":1,"schema_version":1}', "NaN", "[]"))
def test_ambiguous_or_nonobject_json_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        ExperimentConfig.from_json(value)


def test_result_or_volatile_fields_cannot_enter_config_identity() -> None:
    value = json.loads(_config().to_json())
    for field in ("results", "st_ino", "duration_seconds", "source_revision"):
        with pytest.raises(ValueError):
            ExperimentConfig.from_json(json.dumps({**value, field: 123}))


def test_runtime_binding_rejected_before_run_campaign(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("configuration mismatch must precede execution")

    monkeypatch.setattr("inodefence.experiment_config.run_campaign", forbidden)
    config = _config()
    with pytest.raises(ValueError, match="target"):
        run_configured_campaign(config, minimal_seed_corpus(), PythonTarfileTarget(2.0))
    with pytest.raises(ValueError, match="seed"):
        run_configured_campaign(
            config, tuple(reversed(minimal_seed_corpus())), PythonTarfileTarget(5.0)
        )


def test_configured_reference_campaign_records_preexecution_config_id(tmp_path: Path) -> None:
    config = _config()
    result = run_configured_campaign(config, minimal_seed_corpus(), PythonTarfileTarget(5.0))
    assert result.config is config.campaign
    assert result.experiment_config_id == config.config_id
    manifest, _ = export_campaign(result, tmp_path / "export")
    assert json.loads(manifest.read_bytes())["experiment_config_id"] == config.config_id
    assert len(result.steps) == 4


def test_invalid_nested_json_and_nonfinite_values_rejected() -> None:
    original = json.loads(_config().to_json())
    for nested, field, value in (
        ("target", "timeout_seconds", True),
        ("campaign", "random_seed", True),
        ("target", "target_version", "latest"),
        ("target", "execution_safety", "sandboxed"),
    ):
        raw = json.loads(json.dumps(original))
        raw[nested][field] = value
        with pytest.raises(ValueError):
            ExperimentConfig.from_json(json.dumps(raw))
    original["sentinels"][0]["content_base64"] = "invalid!"
    with pytest.raises(ValueError):
        ExperimentConfig.from_json(json.dumps(original))


def test_configured_runner_preserves_isolation_requirement() -> None:
    from inodefence.model.provenance import ExecutionSafety

    class Target:
        provenance = replace(_config().target, execution_safety=ExecutionSafety.ISOLATION_REQUIRED)

        def run(self, archive_path, extraction_root):
            raise AssertionError("isolation-required target must not execute")

    config = replace(_config(), target=Target.provenance)
    with pytest.raises(ValueError, match="requires execution isolation"):
        run_configured_campaign(config, minimal_seed_corpus(), Target())


def test_cli_preserves_the_config_it_read_before_execution(tmp_path: Path, monkeypatch) -> None:
    from scripts import run_configured_reference

    config = _config()
    input_path, output = tmp_path / "input.json", tmp_path / "export"
    input_path.write_text(config.to_json())
    monkeypatch.setattr("sys.argv", ["reference", str(input_path), "--output", str(output)])
    run_configured_reference.main()
    preserved = ExperimentConfig.from_json((output / "experiment.json").read_text())
    assert preserved == config
    assert (
        json.loads((output / "manifest.json").read_text())["experiment_config_id"]
        == config.config_id
    )
    with pytest.raises(FileExistsError):
        run_configured_reference.main()

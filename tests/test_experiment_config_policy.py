"""Bound policy identifiers are explicit; core-only IDs cannot silently run legacy."""

import json
from dataclasses import replace

import pytest

from inodefence.experiment_config import FEEDBACK_POLICY, MUTATION_POLICY, ExperimentConfig
from inodefence.feedback import SearchPolicy
from inodefence.mutator import MutationPolicy
from test_experiment_config import _config


def test_legacy_bound_ids_and_frozen_config_identity_are_unchanged():
    config = _config()
    config = replace(config, target=replace(config.target, target_version="3.12.99"))
    assert FEEDBACK_POLICY == SearchPolicy.B3.value
    assert MUTATION_POLICY == MutationPolicy.LEGACY.value
    # Recorded from the pre-change schema-v1 config with a fixed target version.
    assert config.config_id == "7ae4bca4da37a3ddda0f9a38032f46369b423b455457b2704381c1cfebee73b5"
    assert ExperimentConfig.from_json(config.to_json()) == config


@pytest.mark.parametrize(
    "field,identifier",
    (
        ("feedback_policy", SearchPolicy.B0.value),
        ("feedback_policy", SearchPolicy.B1.value),
        ("feedback_policy", "unknown-policy-v1"),
        ("mutation_policy", MutationPolicy.M1.value),
        ("mutation_policy", MutationPolicy.LEGACY_NO_REORDER.value),
        ("mutation_policy", MutationPolicy.M1_NO_REORDER.value),
        ("mutation_policy", "unknown-mutation-v1"),
    ),
)
def test_unknown_or_unbound_policy_is_rejected_before_runner(field, identifier, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unsupported binding must fail before campaign execution")

    monkeypatch.setattr("inodefence.experiment_config.run_campaign", forbidden)
    with pytest.raises(ValueError, match="unsupported"):
        replace(_config(), **{field: identifier})
    raw = json.loads(_config().to_json())
    raw[field] = identifier
    with pytest.raises(ValueError, match="unsupported"):
        ExperimentConfig.from_json(json.dumps(raw))

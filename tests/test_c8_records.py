"""v2 U3/C8: input_structure and chain keys in step records; registered bytes unchanged.

* Registered R/D/S-u x FIXED_BASELINE cells: the canonical JSON of every EffectCampaignStep is the
  one the code at bed077a produced (digests minted there), so neither the classifier record nor
  ChainedMutationAttempt touches the step model of a registered configuration.
* Their effect_demo step records equal the pre-C8 records once the new schema-5 optional key
  ``input_structure`` is removed (digests minted from the pre-C8 tree, research/b-engine-u3r
  after merging 1deb0b1).
* Every record carries ``input_structure`` (build-invalid: the child that could not be built);
  chain R records carry ``chain_length``/``operator_chain`` also through the streaming on_step path.
Seeds 5, 777, 4242 are outside every registered, reserved and ledger range.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any

import pytest

from inodefence.effect_campaign import (
    BuildInvalidStep,
    EffectCampaignConfig,
    EffectCampaignStep,
    run_effect_campaign,
)
from inodefence.effect_demo import EffectStepReporter, effect_campaign_report
from inodefence.effect_scheduler import EffectUniformMutationScheduler
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.rds import RdsArm, RdsCellConfig, RVariant, VocabularyMode, run_rds_cell
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model.serialization import canonical_json
from inodefence.mutator import MutationAttempt, MutationPolicy, apply_operator, operator_ids
from inodefence.mutator.chain import ChainedMutationAttempt
from inodefence.structure_class import CLASSIFIER_ID, class_record

ARMS = {
    "R": (RdsArm.R, RVariant.SEED_RESTART),
    "D": (RdsArm.D, RVariant.WALK),
    "S-u": (RdsArm.S_U, RVariant.WALK),
}
FIXED = MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE
CHAIN_M4 = EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M4

#: "<arm>:<seed>:16" -> (canonical step chain digest minted at bed077a,
#:                      record digest minted from the pre-C8 tree)
GOLDEN: dict[str, tuple[str, str]] = {
    "D:4242:16": (
        "3fba85d1340e5b51969d6494dbfeb340d3be00663f55fc5e152fc5a4750f9de6",
        "0b30903066a7e98f5d140a321867eb5d8ef41d5b9d7d75f56915bd7d3d124c41",
    ),
    "D:5:16": (
        "8f0410497a74fcc7c65f8614cd639201594eb2084b0d1c7056b8afd2dcc1892a",
        "f9e8877d53c3eb047d744902ab4a768531cc9b1ecafc6c8dbe3e77b9a80131da",
    ),
    "D:777:16": (
        "f6e31c8fa8509ad0fe61e14ac50f7a0f9d90a2212d79c42ed2459a906958f5ce",
        "5f8010bcded321ddc8e6719a8a87a01696481ad4bfbb1b3b3960bee951798721",
    ),
    "R:4242:16": (
        "4c3bd495eadab5cdc20bf93f8f7c0f06af947596b541128abf0e07e0b6d5a123",
        "0be492ff7167b3bc3b61ce4f4dbd13c223976736973719c3e5468081f18403a1",
    ),
    "R:5:16": (
        "86086b841ad6034b9dec23053adcfd682f2f28cbe8b816ae12f7428dcd3753bf",
        "a1f9b9d48be6f697ded62780ba2c0b330bdd031a0103cf3d18a18bcbb8312c74",
    ),
    "R:777:16": (
        "c4150b0a85c3d5461483f57f5ce681e3545c93254dd10c574796b7b5d0a67300",
        "525aa0560784393c0b406b585c487199ce8c587a2d2eaca15a212114f5723740",
    ),
    "S-u:4242:16": (
        "61e21a576d1c72afe7856e4593aec3336588f666881cdd6402c8a9751160b457",
        "20fec59b68a7a9eb5b92ccea5622b513940ae36e80e6c55ad969e35aa0d1301d",
    ),
    "S-u:5:16": (
        "1880845659149645ecca164f781bff4752dee41f26a0d1c1a028468083766dca",
        "333a99ec7bbef86e3ebb58cc655c93262762adb71f04111723296fa729e5e832",
    ),
    "S-u:777:16": (
        "a9977449ea79590852e4d20a18bf10032a809f109d87ebd9164cf99033fbceb6",
        "e510bd4f5657435af2cfbc472b9f998d121985e598d6506d5fd357447cf650a3",
    ),
}


def _registered(key: str) -> Any:
    arm, seed, budget = key.split(":")
    rds_arm, variant = ARMS[arm]
    config = RdsCellConfig(rds_arm, int(seed), int(budget), VocabularyMode.OBSERVED_NAMES, variant)
    return run_rds_cell(minimal_seed_corpus(), synthetic_effect_result, config).campaign


@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_registered_step_canonical_json_unchanged(key: str) -> None:
    digest = hashlib.sha256()
    for step in _registered(key).steps:
        digest.update(hashlib.sha256(canonical_json(step).encode("ascii")).digest())
    assert digest.hexdigest() == GOLDEN[key][0]


@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_registered_records_only_gain_the_optional_structure_key(key: str) -> None:
    campaign = _registered(key)
    records: list[dict[str, Any]] = effect_campaign_report(campaign, "synthetic")["steps"]  # type: ignore[assignment]
    digest = hashlib.sha256()
    for record, step in zip(records, campaign.steps, strict=True):
        structure = record.pop("input_structure")
        assert structure == class_record(step.result.base_result.case)
        assert structure["classifier"] == CLASSIFIER_ID
        assert "chain_length" not in (record["mutation_attempt"] or {})
        digest.update((json.dumps(record, sort_keys=True) + "\x1e").encode())
    assert digest.hexdigest() == GOLDEN[key][1]


def test_build_invalid_record_classifies_the_child_that_could_not_be_built() -> None:
    rng = random.Random(9)
    parent = minimal_seed_corpus()[0]
    scheduler = EffectUniformMutationScheduler()
    selection = scheduler.choose_operator(operator_ids(FIXED), rng)
    attempt = apply_operator(parent, rng, FIXED, selection.operator_id)
    evidence = scheduler.observe_outcome(selection, attempt, (), ())
    invalid = BuildInvalidStep(0, parent.case_id, attempt, evidence, "synthetic build failure")
    record = EffectStepReporter().add(invalid)
    assert record["input_structure"] == class_record(attempt.child_case)


def _chain_records(stream: bool) -> tuple[Any, list[dict[str, Any]]]:
    config = EffectCampaignConfig(55, 40, CHAIN_M4, FIXED)
    if not stream:
        result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
        steps: list[dict[str, Any]] = effect_campaign_report(result, "synthetic")["steps"]  # type: ignore[assignment]
        return result, steps
    reporter = EffectStepReporter()
    records: list[dict[str, Any]] = []
    result = run_effect_campaign(
        minimal_seed_corpus(),
        synthetic_effect_result,
        config,
        on_step=lambda step: records.append(reporter.add(step)),
    )
    return result, records


@pytest.mark.parametrize("stream", [False, True])
def test_chain_records_carry_the_chain(stream: bool) -> None:
    result, records = _chain_records(stream)
    seeds = len(minimal_seed_corpus())
    for record in records[:seeds]:
        assert record["mutation_attempt"] is None
    for record, chain in zip(records[seeds:], result.mutation_chains, strict=True):
        mutation = record["mutation_attempt"]
        assert mutation["chain_length"] == chain.chain_length
        assert mutation["operator_chain"] == [
            {
                "operator_id": link.operator_id.value,
                "applied": link.applied,
                "selected_weight": link.selected_weight,
            }
            for link in chain.links
        ]
        assert mutation["operator_id"] == chain.links[-1].operator_id.value
        assert record["input_structure"] == class_record(chain.child_case)


def test_chained_attempt_is_a_mutation_attempt_with_its_links_in_canonical_json() -> None:
    result, _ = _chain_records(stream=False)
    seeds = len(minimal_seed_corpus())
    for step in result.steps[seeds:]:
        assert isinstance(step, EffectCampaignStep)
        assert isinstance(step.mutation_attempt, ChainedMutationAttempt)
        assert isinstance(step.mutation_attempt, MutationAttempt)
        assert '"links"' in canonical_json(step)
    registered = _registered("R:5:16")
    for step in registered.steps:
        assert type(step.mutation_attempt) in (MutationAttempt, type(None))
        assert '"links"' not in canonical_json(step)

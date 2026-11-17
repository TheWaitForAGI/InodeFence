"""R chain variants in ``rds`` (D062): the existing variants and registered plans are unchanged,
and a v2 plan naming the chain policy passes the existing (no-modify) parser and run gate.

The preregistration documents are only read, never written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from inodefence.evaluation.rds import (
    RdsArm,
    RdsCellConfig,
    RVariant,
    VocabularyMode,
    arm_for_policy,
    arm_search_policy,
)
from inodefence.evaluation.rds_preregistration import (
    CellRequest,
    load_preregistration,
    parse_preregistration,
    preregistration_mismatches,
    require_preregistered_cell,
)
from inodefence.feedback import EffectSearchPolicy

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "experiments" / "preregistration"

R_WALK = "unretained-walk-v1-uniform-mutation-v1"
R_RESTART = "unretained-seed-restart-v1-uniform-mutation-v1"
D = "structure-coverage-v1-uniform-mutation-v1"
S_U = "effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1"
S_A = "effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1"

#: What these registered plans parsed to before the chain variants existed (recorded at
#: research/b-engine 77e58b9 with the code of that tree).
REGISTERED = {
    "exp0-pilot-v2.1.md": ("walk", {"R": R_WALK, "D": D, "S-u": S_U, "S-a": S_A}),
    "exp2-v1.md": ("seed-restart", {"R": R_RESTART, "D": D, "S-u": S_U}),
    "exp3-v1.md": ("seed-restart", {"R": R_RESTART, "D": D, "S-u": S_U}),
}


def test_existing_r_variants_keep_their_values_order_and_default() -> None:
    assert list(RVariant)[:2] == [RVariant.WALK, RVariant.SEED_RESTART]
    assert arm_search_policy(RdsArm.R).value == R_WALK  # default variant: walk
    assert arm_search_policy(RdsArm.R, RVariant.WALK).value == R_WALK
    assert arm_search_policy(RdsArm.R, RVariant.SEED_RESTART).value == R_RESTART
    assert arm_for_policy(EffectSearchPolicy(R_WALK)) == (RdsArm.R, RVariant.WALK)
    assert arm_for_policy(EffectSearchPolicy(R_RESTART)) == (RdsArm.R, RVariant.SEED_RESTART)
    assert RdsCellConfig(RdsArm.R, 1, 8).r_variant == RVariant.WALK


@pytest.mark.parametrize(
    ("variant", "policy"),
    [
        (RVariant.CHAIN_M4, EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M4),
        (RVariant.CHAIN_M6, EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M6),
    ],
)
def test_chain_variants_map_both_ways(variant: RVariant, policy: EffectSearchPolicy) -> None:
    assert arm_search_policy(RdsArm.R, variant) == policy
    assert arm_for_policy(policy) == (RdsArm.R, variant)


@pytest.mark.parametrize("name", sorted(REGISTERED))
def test_registered_plans_parse_as_before(name: str) -> None:
    plan = load_preregistration(PREREG / name)
    variant, arms = REGISTERED[name]
    assert plan.r_variant.value == variant
    assert {arm.value: policy.value for arm, policy in plan.arm_policies.items()} == arms
    assert plan.vocabulary_mode == VocabularyMode.OBSERVED_NAMES


_V2_PLAN = """```preregistration
experiment_id = v2-synthetic
engine_sha = 0123456789abcdef0123456789abcdef01234567
seeds = 5, 777
budget = 64
vocabulary = observed-names-b-grammar-v2-freeze-3
arm.R = {chain}
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
image_digest = sha256:{digest}
hit_definition = c1-or-c2-and-contract-violated
c0_counts_as_hit = false
denominator = all-cells-including-abort
abort_reporting = right-censored
rule_of_three_unit = campaign
primary_endpoint = t_first
```
"""


@pytest.mark.parametrize(
    ("chain", "variant"),
    [
        (EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M4, RVariant.CHAIN_M4),
        (EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M6, RVariant.CHAIN_M6),
    ],
)
def test_v2_plan_with_chain_r_passes_parser_and_gate(
    chain: EffectSearchPolicy, variant: RVariant
) -> None:
    """Synthetic plan (not a registration): seeds 5/777, a made-up SHA and digest."""
    digest = "a" * 64
    plan = parse_preregistration(_V2_PLAN.format(chain=chain.value, digest=digest))
    assert plan.r_variant == variant
    assert plan.vocabulary_mode == VocabularyMode.OBSERVED_NAMES_V2_FREEZE3
    sha = "0123456789abcdef0123456789abcdef01234567"
    for arm in (RdsArm.R, RdsArm.D, RdsArm.S_U):
        request = CellRequest(arm, 5, 64, sha, False, "sha256:" + digest)
        assert preregistration_mismatches(plan, request) == ()
        cell = require_preregistered_cell(plan, request)
        assert cell.vocabulary_mode == VocabularyMode.OBSERVED_NAMES_V2_FREEZE3
        if arm == RdsArm.R:
            assert cell.search_policy == chain
    # the gate still refuses what it refused before
    bad = CellRequest(RdsArm.R, 6, 64, sha, False, "sha256:" + digest)
    assert preregistration_mismatches(plan, bad)

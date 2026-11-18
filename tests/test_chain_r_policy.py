"""v2 random-chain R search policies and their D062 safeguards (#510, v2 U3/C9).

D062 (W4 2026-11-18): src/inodefence/feedback/effect_search.py is on the lane B no-touch union
by path; the only allowed change is the two added enum members below. Safeguard 1 is pinned here.
"""

import functools
import hashlib
import random
import subprocess
from pathlib import Path

import pytest

from inodefence.decompress_effect_campaign import DecompressEffectCampaignConfig
from inodefence.effect_campaign import (
    CHAIN_MAX_ATTEMPTS,
    CHAIN_SEARCH_STATE_POLICY,
    BuildInvalidPolicy,
    EffectCampaignConfig,
    _choose_recorded,
    _observed_name_segments,
    run_effect_campaign,
)
from inodefence.effect_scheduler import EffectUniformMutationScheduler
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.feedback import EffectSearchPolicy, EffectSearchState
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.mutator import MutationPolicy, operator_ids
from inodefence.mutator.chain import apply_chain

ROOT = Path(__file__).resolve().parents[1]
EFFECT_SEARCH = ROOT / "src" / "inodefence" / "feedback" / "effect_search.py"
ADDED_LINES = (
    '    R_UNRETAINED_SEED_CHAIN_M4 = "unretained-seed-chain-m4-v1-uniform-mutation-v1"\n',
    '    R_UNRETAINED_SEED_CHAIN_M6 = "unretained-seed-chain-m6-v1-uniform-mutation-v1"\n',
)
# sha256 of `git show bed077a:src/inodefence/feedback/effect_search.py` (the registered run SHA).
BED077A_EFFECT_SEARCH_SHA256 = "c0dd07fe96307c0f1e34b2eead18486f5d90e10c2cd7a1fc488894a2fab36b9b"
CHAIN_M4 = EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M4
CHAIN_M6 = EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M6
FIXED = MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE


def test_d062_effect_search_differs_from_bed077a_only_by_the_two_members() -> None:
    current = EFFECT_SEARCH.read_text(encoding="utf-8").splitlines(keepends=True)
    assert [line for line in current if line in ADDED_LINES] == list(ADDED_LINES)
    stripped = "".join(line for line in current if line not in ADDED_LINES)
    assert hashlib.sha256(stripped.encode("utf-8")).hexdigest() == BED077A_EFFECT_SEARCH_SHA256


def test_d062_effect_search_line_diff_against_the_bed077a_blob() -> None:
    done = subprocess.run(
        ["git", "-C", str(ROOT), "show", "bed077a:src/inodefence/feedback/effect_search.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:  # no history in this checkout: the sha256 test above still binds
        pytest.skip("bed077a is not in this checkout's history")
    old = done.stdout.splitlines(keepends=True)
    new = EFFECT_SEARCH.read_text(encoding="utf-8").splitlines(keepends=True)
    position = new.index(ADDED_LINES[0])
    assert new[:position] + new[position + 2 :] == old
    assert new[position : position + 2] == list(ADDED_LINES)


def test_chain_members_and_their_maximum_attempts() -> None:
    assert CHAIN_M4.value == "unretained-seed-chain-m4-v1-uniform-mutation-v1"
    assert CHAIN_M6.value == "unretained-seed-chain-m6-v1-uniform-mutation-v1"
    assert CHAIN_MAX_ATTEMPTS == {CHAIN_M4: 4, CHAIN_M6: 6}
    assert CHAIN_SEARCH_STATE_POLICY == EffectSearchPolicy.R_UNRETAINED_SEED_RESTART


def _chain_run(policy=CHAIN_M4, seed=55, budget=40, build_invalid=BuildInvalidPolicy.ABORT):
    config = EffectCampaignConfig(seed, budget, policy, FIXED, build_invalid)
    return run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)


@pytest.mark.parametrize(("policy", "maximum"), [(CHAIN_M4, 4), (CHAIN_M6, 6)])
def test_one_execution_per_chain_and_one_budget_unit(policy, maximum) -> None:
    result = _chain_run(policy, budget=60)
    seeds = len(minimal_seed_corpus())
    assert len(result.steps) == 60  # executions = budget, however many attempts the chains made
    assert len(result.mutation_chains) == 60 - seeds
    assert [c.index for c in result.mutation_chains] == list(range(seeds, 60))
    lengths = [c.chain_length for c in result.mutation_chains]
    assert min(lengths) >= 1 and max(lengths) <= maximum and sum(lengths) > len(lengths)
    assert all(c.applied_length <= c.chain_length for c in result.mutation_chains)
    assert result.config.search_policy == policy  # the record keeps the chain ID


def test_chain_starts_from_a_seed_every_execution_and_retains_nothing() -> None:
    result = _chain_run(budget=60)
    seed_ids = {case.case_id for case in minimal_seed_corpus()}
    for step, chain in zip(result.steps[len(seed_ids) :], result.mutation_chains, strict=True):
        assert step.parent_case_id in seed_ids
        assert chain.parent_case_id == step.parent_case_id
        assert chain.child_case.case_id == step.result.base_result.case.case_id
    restart = run_effect_campaign(
        minimal_seed_corpus(),
        synthetic_effect_result,
        EffectCampaignConfig(55, 60, EffectSearchPolicy.R_UNRETAINED_SEED_RESTART, FIXED),
    )
    assert set(result.retained_case_ids) == set(restart.retained_case_ids) <= seed_ids


def test_chain_search_state_is_the_seed_restart_state() -> None:
    # Same results fed to a seed-restart state give the same decisions, so admission and the
    # R/D/S-u diagnostic channel (boundary-attempt keys) are the seed-restart R's.
    result = _chain_run(budget=60)
    state = EffectSearchState(minimal_seed_corpus(), EffectSearchPolicy.R_UNRETAINED_SEED_RESTART)
    for step in result.steps:
        assert state.consider(step.result) == step.feedback


def test_loop_chains_equal_the_documented_rng_procedure() -> None:
    # The cross-implementation annex (engine vs W3 grammar_mc_v2) used this exact procedure.
    seed, budget = 55, 50
    result = _chain_run(seed=seed, budget=budget)
    extra = tuple(sorted(_observed_name_segments(result.steps[0].result, before_only=True)))
    rng = random.Random(seed)
    seeds = minimal_seed_corpus()
    scheduler = EffectUniformMutationScheduler()
    for chain in result.mutation_chains:
        parent = rng.choice(seeds)
        m = rng.randint(1, 4)
        links, attempt = apply_chain(
            parent,
            rng,
            FIXED,
            m,
            functools.partial(_choose_recorded, scheduler, operator_ids(FIXED), []),
            extra_components=extra,
        )
        assert tuple(links) == chain.links
        assert attempt.child_case == chain.child_case
        assert parent.case_id == chain.parent_case_id


def test_record_policy_still_gives_every_mutation_execution_a_chain() -> None:
    result = _chain_run(budget=80, build_invalid=BuildInvalidPolicy.RECORD)
    seeds = len(minimal_seed_corpus())
    indexes = sorted(
        [s.index for s in result.steps[seeds:]] + [s.index for s in result.build_invalid_steps]
    )
    assert [c.index for c in result.mutation_chains] == indexes == list(range(seeds, 80))


def test_non_chain_policies_record_no_chains() -> None:
    result = run_effect_campaign(
        minimal_seed_corpus(),
        synthetic_effect_result,
        EffectCampaignConfig(55, 30, EffectSearchPolicy.R_UNRETAINED_SEED_RESTART, FIXED),
    )
    assert result.mutation_chains == ()


@pytest.mark.parametrize("policy", [CHAIN_M4, CHAIN_M6])
def test_decompress_loop_refuses_chain_policies(policy) -> None:
    with pytest.raises(ValueError, match="not supported by the decompress campaign loop"):
        DecompressEffectCampaignConfig(random_seed=1, execution_budget=10, search_policy=policy)

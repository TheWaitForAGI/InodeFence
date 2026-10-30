"""The M4.5 decompress self-discovery roll-up maps evidence JSONs to an honest arm view."""

import json

import pytest
from scripts.analyze_m4_5_selfdiscover import (
    _combined_denominator,
    load_campaign,
    roll_up,
)

A3P = "uniform-generic-m1-state-aware-escape-hardlink-v1"
A1P = "uniform-generic-v1"


def _evidence(
    *,
    seed: int,
    budget: int,
    policy: str,
    eligible: int | None = None,
    hit_index: int | None = None,
    terminations: tuple[str, ...] | None = None,
) -> dict:
    """A minimal valid decompress_campaign_schema-1 evidence dict.

    ``hit_index`` is a 0-based step index whose ``contract_violated`` is true (its oracle
    C1 fires). ``eligible`` defaults to a complete campaign (== budget).
    """
    eligible = budget if eligible is None else eligible
    terms = terminations or (("success",) * budget)
    steps = []
    for index in range(budget):
        violated = hit_index is not None and index == hit_index
        steps.append(
            {
                "index": index,
                "termination": terms[index] if index < len(terms) else "success",
                "contract_violated": violated,
                "oracle": {"C0": False, "C1": violated, "C2": False},
            }
        )
    return {
        "decompress_campaign_schema": 1,
        "producer": "native-decompress[decompress=decompress@4.2.1;node=22.23.4]",
        "label": "demo run",
        "config": {
            "random_seed": seed,
            "execution_budget": budget,
            "mutation_policy": policy,
            "adaptive_scheduler": True,
        },
        "initial_case_ids": ["seed-0"],
        "discovered_violation": hit_index is not None,
        "final_stats": {
            "observations": budget,
            "eligible_observations": eligible,
            "retained_cases": 3,
            "unique_attempt_keys": 5,
            "unique_violation_fingerprints": 1 if hit_index is not None else 0,
            "unique_full_states": 4,
        },
        "steps": steps,
        "retained_case_ids": ["seed-0"],
    }


def _write(tmp_path, name: str, payload: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return str(path)


def test_load_campaign_parses_schema_and_arm(tmp_path):
    path = _write(tmp_path, "a3.json", _evidence(seed=500, budget=10, policy=A3P))
    campaign = load_campaign(path)
    assert campaign.seed == 500
    assert campaign.budget == 10
    assert campaign.arm == "A3-state-aware"
    assert campaign.complete is True
    assert campaign.discovered_violation is False


def test_random_policy_maps_to_a1_floor(tmp_path):
    path = _write(tmp_path, "a1.json", _evidence(seed=500, budget=10, policy=A1P))
    assert load_campaign(path).arm == "A1-random"


def test_incomplete_campaign_is_excluded_not_a_no_hit(tmp_path):
    # eligible < budget => infrastructure-incomplete.
    path = _write(tmp_path, "inc.json", _evidence(seed=501, budget=10, policy=A1P, eligible=7))
    campaign = load_campaign(path)
    assert campaign.complete is False
    outcome = campaign.seed_outcome()
    assert outcome.complete is False and outcome.hit is False
    report = roll_up([campaign])
    rc = report["arms"]["A1-random"]["right_censored"]
    assert rc["number_complete_campaigns"] == 0
    assert rc["number_incomplete_excluded"] == 1
    assert rc["incomplete_seeds"] == [501]


def test_hit_is_discovered_violation_with_one_based_first_hit(tmp_path):
    path = _write(tmp_path, "hit.json", _evidence(seed=502, budget=10, policy=A1P, hit_index=3))
    campaign = load_campaign(path)
    assert campaign.discovered_violation is True
    assert campaign.first_hit_index_one_based == 4  # 0-based index 3 -> 1-based 4
    outcome = campaign.seed_outcome()
    assert outcome.hit is True and outcome.first_hit_executions == 4


def test_roll_up_groups_by_arm_with_wilson(tmp_path):
    campaigns = [
        load_campaign(_write(tmp_path, "a3-500.json", _evidence(seed=500, budget=10, policy=A3P))),
        load_campaign(_write(tmp_path, "a3-501.json", _evidence(seed=501, budget=10, policy=A3P))),
        load_campaign(_write(tmp_path, "a1-500.json", _evidence(seed=500, budget=10, policy=A1P))),
    ]
    report = roll_up(campaigns)
    assert set(report["arms"]) == {"A3-state-aware", "A1-random"}
    a3 = report["arms"]["A3-state-aware"]
    assert a3["is_state_aware_not_blind"] is True
    assert a3["right_censored"]["number_complete_campaigns"] == 2
    assert a3["right_censored"]["number_observed_target"] == 0
    assert report["architecture"] == "x86_64"
    assert report["windows_host_seeds"] == [500, 501]


def test_combined_denominator_flags_overlap(tmp_path):
    disjoint = _combined_denominator([500, 501], {"mac": [11, 85]})
    assert disjoint["disjoint"] is True
    assert disjoint["combined_seed_count"] == 4
    overlapping = _combined_denominator([500, 11], {"mac": [11, 85]})
    assert overlapping["disjoint"] is False
    assert overlapping["overlap_with_external"]["mac"] == [11]
    assert overlapping["combined_seed_count"] is None


def test_wrong_schema_raises(tmp_path):
    bad = {"decompress_campaign_schema": 99}
    path = _write(tmp_path, "bad.json", bad)
    with pytest.raises(ValueError, match="decompress_campaign_schema"):
        load_campaign(path)

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
    hit_contract: str = "C1",
    terminations: tuple[str, ...] | None = None,
) -> dict:
    """A minimal valid decompress_campaign_schema-1 evidence dict.

    ``hit_index`` is a 0-based step index whose ``contract_violated`` is true; ``hit_contract``
    (C0/C1/C2) is the oracle flag that fires there. ``eligible`` defaults to complete (== budget).
    """
    eligible = budget if eligible is None else eligible
    terms = terminations or (("success",) * budget)
    steps = []
    for index in range(budget):
        violated = hit_index is not None and index == hit_index
        oracle = {"C0": False, "C1": False, "C2": False}
        if violated:
            oracle[hit_contract] = True
        steps.append(
            {
                "index": index,
                "termination": terms[index] if index < len(terms) else "success",
                "contract_violated": violated,
                "oracle": oracle,
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


_ABORT_STUB = {
    "aborted": {"reason": "container runtime cleanup inspect failed"},
    "decompress_campaign_schema": 1,
    "label": "demo run",
    "producer": "native-decompress[decompress=decompress@4.2.1;node=22.23.4]",
}


def test_abort_stub_is_incomplete_seed_and_arm_from_filename(tmp_path):
    # The backend writes this stub on a fail-closed abort; it has no config/steps, so seed
    # and arm must come from the -m45-<arm>-s<seed> filename.
    path = _write(
        tmp_path,
        "inodefence-decompress-selfdiscover-m45-sa-s500.json",
        _ABORT_STUB,
    )
    campaign = load_campaign(path)
    assert campaign.aborted is True
    assert campaign.complete is False
    assert campaign.seed == 500
    assert campaign.arm == "A3-state-aware"
    assert campaign.abort_reason == "container runtime cleanup inspect failed"
    assert campaign.seed_outcome().hit is False


def test_roll_up_counts_aborts_separately_from_denominator(tmp_path):
    complete = load_campaign(
        _write(
            tmp_path,
            "inodefence-decompress-selfdiscover-m45-a1-s500.json",
            _evidence(seed=500, budget=10, policy=A1P),
        )
    )
    aborted = load_campaign(
        _write(
            tmp_path,
            "inodefence-decompress-selfdiscover-m45-a1-s501.json",
            _ABORT_STUB,
        )
    )
    report = roll_up([complete, aborted])
    arm = report["arms"]["A1-random"]
    # The abort leaves the hit denominator (complete only) and is reported separately.
    assert arm["right_censored"]["number_complete_campaigns"] == 1
    assert arm["right_censored"]["number_incomplete_excluded"] == 1
    assert arm["fail_closed_aborts"]["count"] == 1
    assert arm["fail_closed_aborts"]["seeds"] == [501]


def test_by_contract_splits_c0_from_c1_c2(tmp_path):
    # A C0-only path-boundary hit must NOT count as a C1/C2 identity/effect discovery.
    c0 = load_campaign(
        _write(
            tmp_path,
            "inodefence-decompress-selfdiscover-m45-a1-s500.json",
            _evidence(seed=500, budget=10, policy=A1P, hit_index=2, hit_contract="C0"),
        )
    )
    assert c0.contract_counts == {"C0": 1, "C1": 0, "C2": 0}
    assert c0.contract_first_hit["C0"] == 3
    assert c0.contract_outcome("C0").hit is True
    assert c0.contract_outcome("C1").hit is False
    report = roll_up([c0])
    arm = report["arms"]["A1-random"]
    assert arm["right_censored_any_contract"]["number_observed_target"] == 1
    assert arm["by_contract"]["C0"]["number_observed_target"] == 1
    assert arm["by_contract"]["C1"]["number_observed_target"] == 0
    assert arm["by_contract"]["C2"]["number_observed_target"] == 0


def test_filename_seed_mismatch_raises(tmp_path):
    # A complete evidence whose filename seed disagrees with its config seed is an integrity error.
    path = _write(
        tmp_path,
        "inodefence-decompress-selfdiscover-m45-a1-s999.json",
        _evidence(seed=500, budget=10, policy=A1P),
    )
    with pytest.raises(ValueError, match="filename seed"):
        load_campaign(path)

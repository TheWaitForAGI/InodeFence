"""The unified M4.5 roll-up pools mac + windows seeds through the shared Wilson engine.

These cover the logic that is NEW in ``analyze_m4_5_unified`` (the base per-campaign loader
is covered by ``test_analyze_m4_5_selfdiscover``): the mac ``-m4p-`` abort-stub handling, the
reconstruction of windows per-seed outcomes from the published roll-up (with its self-check),
and the disjoint union arithmetic.
"""

import json

import pytest
from scripts.analyze_m4_5_selfdiscover import Campaign
from scripts.analyze_m4_5_unified import (
    assert_matches_windows,
    load_campaign_any,
    reconstruct_windows_outcomes,
    unify,
)

from inodefence.evaluation.right_censored import SeedOutcome, right_censored_summary

B = 1500

_ABORT_STUB = {
    "aborted": {"reason": "container runtime cleanup inspect failed"},
    "decompress_campaign_schema": 1,
    "label": "demo run",
    "producer": "native-decompress[decompress=decompress@4.2.1;node=22.23.4]",
}


def _mac(
    arm: str, seed: int, *, aborted: bool = False, c0: int = 0, c1: int = 0, c2: int = 0
) -> Campaign:
    if aborted:
        return Campaign(
            path="x",
            seed=seed,
            budget=B,
            policy="",
            arm=arm,
            producer="p",
            observations=0,
            eligible_observations=0,
            retained_cases=0,
            unique_attempt_keys=0,
            unique_violation_fingerprints=0,
            unique_full_states=0,
            terminations={},
            discovered_violation=False,
            first_hit_index_one_based=None,
            aborted=True,
            abort_reason="r",
        )
    counts = {"C0": c0, "C1": c1, "C2": c2}
    first = {k: (1 if v else None) for k, v in counts.items()}
    disc = any(counts.values())
    return Campaign(
        path="x",
        seed=seed,
        budget=B,
        policy="pol",
        arm=arm,
        producer="p",
        observations=B,
        eligible_observations=B,
        retained_cases=1,
        unique_attempt_keys=1,
        unique_violation_fingerprints=1 if disc else 0,
        unique_full_states=1,
        terminations={},
        discovered_violation=disc,
        first_hit_index_one_based=1 if disc else None,
        contract_counts=counts,
        contract_first_hit=first,
    )


def _win_rollup() -> dict:
    """A minimal published-windows roll-up: seeds 500-503, with 503 a fail-closed abort.

    Each by_contract block is built by the real engine over the same outcomes the real
    roll_up would pass (aborts included as complete=False), so it is internally consistent.
    """
    seeds = [500, 501, 502, 503]

    def arm_block(c0_hit_seeds: set[int]) -> dict:
        abort = [SeedOutcome(503, B, False, False, None)]
        complete = [500, 501, 502]
        c0 = [
            SeedOutcome(s, B, True, s in c0_hit_seeds, 10 if s in c0_hit_seeds else None)
            for s in complete
        ] + abort
        all_censored = [SeedOutcome(s, B, True, False, None) for s in complete] + abort
        return {
            "fail_closed_aborts": {"seeds": [503]},
            "by_contract": {
                "C0": right_censored_summary(c0),
                "C1": right_censored_summary(all_censored),
                "C2": right_censored_summary(all_censored),
            },
        }

    return {
        "windows_host_seeds": seeds,
        "arms": {"A1-random": arm_block({500, 501}), "A3-state-aware": arm_block({500})},
    }


def test_load_campaign_any_handles_mac_m4p_abort_stub(tmp_path):
    path = tmp_path / "inodefence-decompress-selfdiscover-m4p-sa-s85.json"
    path.write_text(json.dumps(_ABORT_STUB))
    campaign = load_campaign_any(str(path))
    assert campaign.aborted is True
    assert campaign.complete is False
    assert campaign.seed == 85
    assert campaign.arm == "A3-state-aware"


def test_load_campaign_any_delegates_non_stub(tmp_path):
    payload = {
        "decompress_campaign_schema": 1,
        "producer": "native-decompress",
        "config": {
            "random_seed": 11,
            "execution_budget": 4,
            "mutation_policy": "uniform-generic-v1",
        },
        "discovered_violation": False,
        "final_stats": {
            "observations": 4,
            "eligible_observations": 4,
            "retained_cases": 1,
            "unique_attempt_keys": 1,
            "unique_violation_fingerprints": 0,
            "unique_full_states": 1,
        },
        "steps": [
            {"index": i, "termination": "success", "contract_violated": False} for i in range(4)
        ],
    }
    path = tmp_path / "inodefence-decompress-selfdiscover-m4p-a1-s11.json"
    path.write_text(json.dumps(payload))
    campaign = load_campaign_any(str(path))
    assert campaign.aborted is False
    assert campaign.seed == 11
    assert campaign.arm == "A1-random"
    assert campaign.complete is True


def test_reconstruct_windows_outcomes_roundtrips_and_self_checks():
    win = _win_rollup()
    rebuilt = reconstruct_windows_outcomes(win, "A1-random", "C0")
    # 2 hits (500,501), 1 censored (502), 1 abort (503).
    assert_matches_windows(win, "A1-random", "C0", rebuilt)
    summary = right_censored_summary(rebuilt)
    assert summary["number_complete_campaigns"] == 3
    assert summary["number_observed_target"] == 2
    assert summary["number_incomplete_excluded"] == 1


def test_assert_matches_windows_rejects_a_corrupted_block():
    win = _win_rollup()
    win["arms"]["A1-random"]["by_contract"]["C0"]["number_observed_target"] = 3  # lie
    with pytest.raises(ValueError, match="number_observed_target"):
        assert_matches_windows(
            win, "A1-random", "C0", reconstruct_windows_outcomes(win, "A1-random", "C0")
        )


def test_unify_pools_disjoint_seeds_per_contract():
    win = _win_rollup()
    mac = [
        _mac("A1-random", 11, c0=1),
        _mac("A1-random", 85, c0=0),
        _mac("A1-random", 307, aborted=True),
        _mac("A3-state-aware", 11, c0=1),
        _mac("A3-state-aware", 85, c1=2),  # a C1 hit on the mac side (synthetic)
    ]
    report = unify(mac, win, mac_raw_pointer="glob")
    assert report["combined_denominator"]["disjoint"] is True
    # {11,85,307} U {500,501,502,503}
    assert report["combined_denominator"]["combined_seed_count"] == 7

    # A1 C0: mac 1/2 (s11 hit, s85 censored; s307 abort excluded) + win 2/3 = 3/5, 2 excluded.
    a1c0 = report["unified_by_arm"]["A1-random"]["by_contract"]["C0"]
    assert a1c0["number_observed_target"] == 3
    assert a1c0["number_complete_campaigns"] == 5
    assert a1c0["number_incomplete_excluded"] == 2  # mac s307 + win s503

    # A1 C1: mac 0/2 + win 0/3 = 0/5, right-censored negative.
    a1c1 = report["unified_by_arm"]["A1-random"]["by_contract"]["C1"]
    assert a1c1["number_observed_target"] == 0
    assert a1c1["number_complete_campaigns"] == 5

    # A3 aborts combine mac + windows (no mac A3 abort here, win has s503).
    a3_aborts = report["unified_by_arm"]["A3-state-aware"]["fail_closed_aborts"]
    assert a3_aborts["mac_seeds"] == []
    assert a3_aborts["windows_seeds"] == [503]
    assert a3_aborts["combined_count"] == 1

    # Novelty overall pools BOTH arms AND both hosts: A1(2+3 complete) + A3(2+3 complete) = 10,
    # with exactly the one synthetic mac A3 s85 C1 hit.
    overall_c1 = report["unified_novelty_overall"]["C1"]
    assert overall_c1["number_observed_target"] == 1
    assert overall_c1["number_complete_campaigns"] == 10


def test_unify_flags_overlapping_seeds_as_not_disjoint():
    win = _win_rollup()  # windows seeds 500-503
    # A mac campaign reusing a real windows seed makes the union non-disjoint.
    report = unify([_mac("A1-random", 500, c0=1)], win, mac_raw_pointer="glob")
    assert report["combined_denominator"]["disjoint"] is False
    assert report["combined_denominator"]["overlap"] == [500]
    assert report["combined_denominator"]["combined_seed_count"] is None

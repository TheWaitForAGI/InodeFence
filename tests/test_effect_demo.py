import argparse

import pytest
from scripts.compare_effect_policies import synthetic_policy_comparison
from scripts.run_effect_demo import (
    MAX_NATIVE_BUDGET,
    add_demo_arguments,
    check_demo_arguments,
    native_demo_report,
    pinned_node_tar_version,
    synthetic_demo_json,
    synthetic_demo_report,
)

from inodefence.effect_demo import compare_effect_campaign_reports, render_effect_campaign_report
from inodefence.feedback import EffectSearchPolicy
from inodefence.mutator import MutationPolicy


def test_synthetic_demo_json_is_byte_identical_for_same_seed() -> None:
    first = synthetic_demo_json(123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1)
    second = synthetic_demo_json(123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1)

    assert first == second


@pytest.mark.parametrize("budget", (0, MAX_NATIVE_BUDGET + 1, -1))
def test_native_demo_budget_cap_is_enforced_before_any_target_binding(budget) -> None:
    with pytest.raises(ValueError, match="budget"):
        native_demo_report(object(), "sha256:" + "0" * 64, budget=budget)  # type: ignore[arg-type]


def _demo_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    add_demo_arguments(parser)
    parser.add_argument("mode")
    return parser


def test_demo_arguments_are_restricted_to_effect_demo() -> None:
    parser = _demo_parser()
    args = parser.parse_args(["--seed", "7", "benign-node-smoke"])
    with pytest.raises(SystemExit):
        check_demo_arguments(parser, args)
    check_demo_arguments(parser, parser.parse_args(["--seed", "7", "effect-demo"]))
    check_demo_arguments(parser, parser.parse_args(["benign-node-smoke"]))


@pytest.mark.parametrize("budget", ("0", str(MAX_NATIVE_BUDGET + 1)))
def test_demo_argument_budget_cap(budget) -> None:
    parser = _demo_parser()
    with pytest.raises(SystemExit):
        check_demo_arguments(parser, parser.parse_args(["--budget", budget, "effect-demo"]))


def test_pinned_node_tar_version_reads_the_repository_pin() -> None:
    assert pinned_node_tar_version() == "7.5.22"


@pytest.mark.parametrize(
    "left", (EffectSearchPolicy.P1_EFFECT_RETENTION, EffectSearchPolicy.P0_FINAL_STATE)
)
def test_policy_comparison_is_byte_identical_for_same_input(left) -> None:
    def render() -> str:
        return render_effect_campaign_report(
            synthetic_policy_comparison(
                123, 20, MutationPolicy.M1, left, EffectSearchPolicy.P2_EFFECT_ADAPTIVE
            )
        )

    assert render() == render()


@pytest.mark.parametrize("seed", range(8))
def test_p1_p2_divergence_is_never_attributed_to_corpus_admission(seed) -> None:
    comparison = synthetic_policy_comparison(
        seed,
        40,
        MutationPolicy.M1,
        EffectSearchPolicy.P1_EFFECT_RETENTION,
        EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
    )

    divergence = comparison["first_divergence"]
    if divergence is not None:
        assert isinstance(divergence, dict)
        assert divergence["source"] == "weights_feedback"
        assert divergence["first_corpus_difference_step"] is None


@pytest.mark.parametrize(
    "right_args",
    (
        (124, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1),
        (123, 21, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1),
        (123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.LEGACY),
    ),
)
def test_policy_comparison_rejects_differences_beyond_search_policy(right_args) -> None:
    left = synthetic_demo_report(123, 20, EffectSearchPolicy.P1_EFFECT_RETENTION, MutationPolicy.M1)

    with pytest.raises(ValueError, match="differ"):
        compare_effect_campaign_reports(left, synthetic_demo_report(*right_args))


def test_policy_comparison_rejects_a_different_producer() -> None:
    left = synthetic_demo_report(123, 20, EffectSearchPolicy.P1_EFFECT_RETENTION, MutationPolicy.M1)
    right = dict(left, producer="native")

    with pytest.raises(ValueError, match="producer"):
        compare_effect_campaign_reports(left, right)


_EVEN = {"a": 1, "b": 1}
_A_REWARDED = {"a": 2, "b": 1}


def _fixture_report(policy: str, mutations: list[tuple]) -> dict:
    """One retained seed `s0`, then (parent, operator, child, weights_before, retained, reward)."""
    steps: list[dict] = [
        {
            "index": 0,
            "case_id": "s0",
            "parent_case_id": None,
            "feedback": {"retained": True, "new_effect_keys": []},
            "scheduler_evidence": None,
        }
    ]
    for parent, operator, child, weights, retained, reward in mutations:
        after = dict(weights)
        after[operator] += reward
        steps.append(
            {
                "index": len(steps),
                "case_id": child,
                "parent_case_id": parent,
                "feedback": {"retained": retained, "new_effect_keys": [{"key": child}] * reward},
                "scheduler_evidence": {
                    "selected_operator_id": operator,
                    "weights_before": weights,
                    "selected_weight": weights[operator],
                    "reward": reward,
                    "weights_after": after,
                },
            }
        )
    return {
        "demo_report_schema": 1,
        "producer": "fixture",
        "initial_case_ids": ["s0"],
        "config": {
            "random_seed": 1,
            "execution_budget": len(steps),
            "search_policy": policy,
            "mutation_policy": "m",
        },
        "steps": steps,
    }


def test_identical_selections_do_not_diverge() -> None:
    mutations = [("s0", "a", "c1", _EVEN, False, 0), ("s0", "b", "c2", _EVEN, False, 0)]

    comparison = compare_effect_campaign_reports(
        _fixture_report("left", mutations), _fixture_report("right", mutations)
    )

    assert comparison["first_divergence"] is None
    assert comparison["operator_match_ratio"] == 1.0
    assert comparison["selection_match_ratio"] == 1.0


def test_divergence_after_reward_is_attributed_to_weights_feedback() -> None:
    left = _fixture_report(
        "uniform", [("s0", "a", "c1", _EVEN, True, 0), ("s0", "b", "c2", _EVEN, False, 0)]
    )
    right = _fixture_report(
        "adaptive", [("s0", "a", "c1", _EVEN, True, 1), ("s0", "a", "c3", _A_REWARDED, False, 0)]
    )

    comparison = compare_effect_campaign_reports(left, right)

    divergence = comparison["first_divergence"]
    assert isinstance(divergence, dict)
    assert divergence["step"] == 2
    assert divergence["immediate_difference"] == "weights"
    assert divergence["source"] == "weights_feedback"
    assert comparison["operator_match_ratio"] == 0.5
    assert comparison["feedback_events"] == {
        "left": [],
        "right": [
            {
                "index": 1,
                "selected_operator_id": "a",
                "new_effect_key_count": 1,
                "reward": 1,
                "selected_weight_before": 1,
                "selected_weight_after": 2,
            }
        ],
    }


@pytest.mark.parametrize(
    ("right_second", "immediate"),
    (
        (("c1", "b", "c3", _EVEN, False, 0), "parent"),
        (("s0", "a", "c3", _EVEN, False, 0), "rng_desync"),
    ),
)
def test_divergence_after_admission_difference_is_attributed_to_corpus(
    right_second, immediate
) -> None:
    left = _fixture_report(
        "final-state", [("s0", "a", "c1", _EVEN, False, 0), ("s0", "b", "c2", _EVEN, False, 0)]
    )
    right = _fixture_report("effect", [("s0", "a", "c1", _EVEN, True, 0), right_second])

    divergence = compare_effect_campaign_reports(left, right)["first_divergence"]

    assert isinstance(divergence, dict)
    assert divergence["step"] == 2
    assert divergence["immediate_difference"] == immediate
    assert divergence["source"] == "corpus_admission"
    assert divergence["first_corpus_difference_step"] == 2

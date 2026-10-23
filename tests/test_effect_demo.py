import argparse

import pytest
from scripts.run_effect_demo import (
    MAX_NATIVE_BUDGET,
    add_demo_arguments,
    check_demo_arguments,
    native_demo_report,
    pinned_node_tar_version,
    synthetic_demo_json,
)

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

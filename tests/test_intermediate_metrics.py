"""Intermediate-state gradient metrics: dense, non-right-censored arm differentials.

The generic core is tested on abstract key sets (no extractor, no target); the
adapters are tested against real effect signals already on main via synthetic traces
(no docker), including the boundary-attempt directed-gradient milestone.
"""

import pytest

from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.arm_comparison import Arm
from inodefence.evaluation.intermediate_metrics import (
    AbcdIntermediateComparison,
    abcd_intermediate_comparison,
    boundary_attempt_trace_keys,
    effect_trace_keys,
    intermediate_state_metrics,
    is_boundary_attempt_key,
    is_external_resolve_key,
)
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, OperationOutcome
from test_m3_boundary_attempt_gradient import _external_link_attempt_result


def test_core_dense_metrics_and_trajectory():
    steps = [frozenset({"a"}), frozenset({"b", "c"}), frozenset({"a"}), frozenset({"d"})]
    metrics = intermediate_state_metrics(steps)
    assert metrics.total_steps == 4
    assert metrics.unique_keys == 4
    assert metrics.novel_key_steps == 3  # steps 1, 2, 4 add new; step 3 repeats "a"
    assert metrics.novelty_rate == 3 / 4
    # gradient trajectory: cumulative unique keys at 25/50/75/100% of the run
    assert metrics.cumulative_unique_keys == ((0.25, 1), (0.5, 3), (0.75, 3), (1.0, 4))
    assert metrics.milestone_executions is None and metrics.milestone_censored is False


def test_milestone_hit_vs_censored():
    hit = intermediate_state_metrics(
        [frozenset({"x"}), frozenset({"M", "y"}), frozenset({"z"})], milestone=lambda k: k == "M"
    )
    assert hit.milestone_executions == 2 and hit.milestone_censored is False
    assert hit.milestone_key_count == 1
    miss = intermediate_state_metrics(
        [frozenset({"x"}), frozenset({"y"})], milestone=lambda k: k == "M"
    )
    assert miss.milestone_executions is None and miss.milestone_censored is True
    assert miss.milestone_key_count == 0


def test_arm_differential_is_measurable_without_terminal_hit():
    # Random arm repeats one state and never reaches the milestone; an exploring arm
    # accumulates unique states and reaches it early -> a measurable, non-censored diff
    # on the dense intermediate signal even with no terminal violation anywhere.
    random_arm = [frozenset({"s"})] * 6
    exploring = [frozenset({f"s{index}"}) | ({"M"} if index == 1 else set()) for index in range(6)]
    comparison = abcd_intermediate_comparison(
        {Arm.A: random_arm, Arm.C: exploring}, milestone=lambda k: k == "M"
    )
    assert isinstance(comparison, AbcdIntermediateComparison)
    a_metrics, c_metrics = comparison.metrics[Arm.A], comparison.metrics[Arm.C]
    assert a_metrics.unique_keys == 1 and a_metrics.milestone_censored is True
    assert c_metrics.unique_keys > a_metrics.unique_keys
    assert c_metrics.novelty_rate > a_metrics.novelty_rate
    assert c_metrics.milestone_executions == 2 and c_metrics.milestone_censored is False
    assert "EN-008" in comparison.note and "not a confirmed" in comparison.milestone_note


def test_validation_errors():
    with pytest.raises(ValueError):
        intermediate_state_metrics([frozenset()], checkpoints=())
    with pytest.raises(ValueError):
        intermediate_state_metrics([frozenset()], checkpoints=(1.5,))
    with pytest.raises(ValueError):
        intermediate_state_metrics([frozenset()], milestone=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        abcd_intermediate_comparison({})
    with pytest.raises(ValueError):
        abcd_intermediate_comparison({"A": [frozenset()]})  # type: ignore[arg-type]


def test_effect_adapter_on_benign_trace():
    result = synthetic_effect_result(
        ArchiveCase((ArchiveEntry("f.txt", EntryType.REGULAR, content=b"x"),))
    )
    keys = effect_trace_keys(result.trace)
    assert keys and all(hasattr(key, "kind") for key in keys)
    assert not any(is_boundary_attempt_key(key) for key in keys)
    assert boundary_attempt_trace_keys(result.trace) == frozenset()


def test_boundary_attempt_adapter_and_milestone_on_real_signal():
    result = _external_link_attempt_result(
        link_target="../outside/sentinel", outcome=OperationOutcome.NOT_FOUND
    )
    boundary = boundary_attempt_trace_keys(result.trace)
    assert boundary
    assert all(is_boundary_attempt_key(key) for key in boundary)
    assert not any(is_external_resolve_key(key) for key in boundary)
    # The directed-gradient milestone fires on the execution carrying these keys.
    metrics = intermediate_state_metrics([boundary], milestone=is_boundary_attempt_key)
    assert metrics.milestone_executions == 1 and metrics.milestone_censored is False

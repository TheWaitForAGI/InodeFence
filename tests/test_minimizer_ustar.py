"""Representation-aware reduction keeps unsupported candidates out of execution."""

from dataclasses import replace

import pytest

from inodefence.builder import build_tar
from inodefence.minimizer import (
    MINIMIZATION_POLICY,
    MinimizationTermination,
    ReductionPolicy,
    minimize_case,
    minimize_violation,
    reduction_candidates,
)
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, canonical_json
from test_feedback_corpus import _creation, _result
from test_minimizer_evidence import _evaluate


def _long_case(tail="a" * 100):
    return ArchiveCase((ArchiveEntry(".//" + tail, EntryType.REGULAR, content=b"x", mode=0),))


def _supported(case):
    try:
        build_tar(case)
    except ValueError:
        return False
    return True


@pytest.mark.parametrize("tail", ("a" * 99, "a" * 100, "é" * 50, "🙂" * 25))
def test_ustar_candidates_keep_raw_order_and_filter_only_unrepresentable_cases(tail):
    case = _long_case(tail)
    assert _supported(case)
    raw = tuple(reduction_candidates(case))
    compatible = tuple(reduction_candidates(case, policy=ReductionPolicy.USTAR))
    assert compatible == tuple(item for item in raw if _supported(item[1]))
    assert canonical_json(case) == canonical_json(_long_case(tail))
    assert len({candidate.case_id for _, candidate in compatible}) == len(compatible)
    if len(tail.encode("utf-8")) == 100:
        assert any(not _supported(candidate) for _, candidate in raw)
        assert len(compatible) == len(raw) - 1
    else:
        assert compatible == raw


def test_filtered_candidates_never_execute_or_consume_budget_and_v1_is_reproducible():
    case = _long_case()
    calls = []

    def evaluate(candidate):
        calls.append(candidate)
        return _evaluate(candidate)

    def preserves(result):
        return result.case == case

    result = minimize_case(
        case, evaluate, preserves, execution_budget=7, policy=ReductionPolicy.USTAR
    )
    assert result.policy_id == "greedy-ustar-archive-reduction-v1"
    assert result.termination == MinimizationTermination.FIXED_POINT
    assert result.final_case == case
    assert len(calls) == len(result.steps) == 6
    assert tuple(step.index for step in result.steps) == tuple(range(6))
    assert calls == [
        case,
        *(candidate for _, candidate in reduction_candidates(case, policy=ReductionPolicy.USTAR)),
    ]
    assert all(_supported(step.result.case) for step in result.steps)
    assert result == minimize_case(
        case, _evaluate, preserves, execution_budget=7, policy=ReductionPolicy.USTAR
    )
    # The raw v1 candidate sequence and exception semantics remain available.
    calls.clear()
    with pytest.raises(ValueError, match="USTAR"):
        minimize_case(case, evaluate, preserves, execution_budget=7)
    assert len(calls) == 6  # evaluator receives the unsupported candidate in legacy mode
    legacy = minimize_case(case, _result, lambda run: bool(run.case.entries), execution_budget=2)
    assert legacy.policy_id == MINIMIZATION_POLICY


def test_bound_violation_minimizer_defaults_to_recorded_ustar_policy_with_raw_opt_in():
    case = _long_case()

    def evaluate(candidate):
        result = _evaluate(candidate)
        return replace(result, violations=(_creation(),) if candidate == case else ())

    result = minimize_violation(case, evaluate, execution_budget=7)
    assert result.reduction.policy_id == ReductionPolicy.USTAR.value
    assert result.reduction.termination == MinimizationTermination.FIXED_POINT
    assert result.final_result.case == case
    assert all(
        result.condition.matches(step.result) == step.accepted for step in result.reduction.steps
    )
    with pytest.raises(ValueError, match="USTAR"):
        minimize_violation(
            case, evaluate, execution_budget=7, reduction_policy=ReductionPolicy.GENERIC
        )


@pytest.mark.parametrize("policy", ("unknown", "greedy-ustar-archive-reduction-v1", None))
def test_invalid_policy_is_rejected_before_any_evaluation(policy):
    calls = []

    def evaluate(case):
        calls.append(case)
        return _result(case)

    with pytest.raises(ValueError, match="ReductionPolicy"):
        minimize_case(_long_case(), evaluate, lambda run: True, execution_budget=2, policy=policy)
    with pytest.raises(ValueError, match="ReductionPolicy"):
        tuple(reduction_candidates(_long_case(), policy=policy))
    assert calls == []


def test_unsupported_baseline_fails_before_evaluation_without_fabricating_run_result():
    case = ArchiveCase((ArchiveEntry("/" + "a" * 100, EntryType.REGULAR, content=b"x"),))
    calls = []

    def evaluate(candidate):
        calls.append(candidate)
        return _result(candidate)

    with pytest.raises(ValueError, match="USTAR"):
        minimize_case(
            case, evaluate, lambda run: True, execution_budget=2, policy=ReductionPolicy.USTAR
        )
    with pytest.raises(ValueError, match="USTAR"):
        tuple(reduction_candidates(case, policy=ReductionPolicy.USTAR))
    assert calls == []


def test_evaluator_value_error_is_not_treated_as_an_unsupported_candidate():
    calls = []

    def evaluate(case):
        calls.append(case)
        if len(calls) > 1:
            raise ValueError("controller failure")
        return _result(case)

    with pytest.raises(ValueError, match="controller failure"):
        minimize_case(
            _long_case(),
            evaluate,
            lambda run: True,
            execution_budget=2,
            policy=ReductionPolicy.USTAR,
        )
    assert len(calls) == 2

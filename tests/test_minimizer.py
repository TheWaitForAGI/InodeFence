"""Generic deterministic reduction, full trial evidence and bounded execution."""

from dataclasses import replace

import pytest

from inodefence.builder import build_tar
from inodefence.feedback import violation_fingerprints
from inodefence.minimizer import (
    MINIMIZATION_POLICY,
    MinimizationTermination,
    ReductionKind,
    minimize_case,
    reduction_candidates,
)
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, ExecutionStatus, canonical_json
from test_feedback_corpus import _case, _creation, _result


def _input():
    return ArchiveCase(
        (
            ArchiveEntry("dir//marker", EntryType.REGULAR, content=b"xpadding", mode=0o4640),
            ArchiveEntry("unused", EntryType.DIRECTORY, mode=0o755),
            ArchiveEntry("reference", EntryType.SYMLINK, link_target="dir//marker"),
        )
    )


def _evaluate(case):
    # Synthetic evidence condition on generic content; no target/CVE recipe.
    evidence = (
        (_creation(),)
        if any(entry.content and entry.content.startswith(b"x") for entry in case.entries)
        else ()
    )
    return replace(_result(case), violations=evidence)


def _preserves(result):
    return violation_fingerprints(result.violations) == violation_fingerprints((_creation(),))


def test_reduction_preserves_evidence_condition_and_all_rejected_trial_evidence():
    case = _input()
    raw = canonical_json(case)
    first = minimize_case(case, _evaluate, _preserves, execution_budget=200)
    second = minimize_case(case, _evaluate, _preserves, execution_budget=200)
    assert first == second
    assert first.policy_id == MINIMIZATION_POLICY
    assert first.termination == MinimizationTermination.FIXED_POINT
    assert first.final_case == ArchiveCase(
        (ArchiveEntry("a", EntryType.REGULAR, content=b"x", mode=0),)
    )
    assert canonical_json(case) == raw
    assert first.steps[0].transformation == ReductionKind.INITIAL
    assert tuple(step.index for step in first.steps) == tuple(range(len(first.steps)))
    assert any(not step.accepted for step in first.steps)
    assert all(_preserves(step.result) for step in first.steps if step.accepted)
    assert all(step.result.case.case_id for step in first.steps)
    assert not any(
        _preserves(_evaluate(candidate)) for _, candidate in reduction_candidates(first.final_case)
    )


@pytest.mark.parametrize("budget", (1, 2, 4, 9))
def test_budget_includes_baseline_and_rejected_trials_and_keeps_last_accepted_case(budget):
    case = _input()
    calls = []

    def evaluate(candidate):
        calls.append(candidate.case_id)
        return _evaluate(candidate)

    result = minimize_case(case, evaluate, _preserves, execution_budget=budget)  # type: ignore[arg-type]
    assert len(calls) == len(result.steps) == budget
    assert result.termination == MinimizationTermination.BUDGET
    assert (
        result.final_case == tuple(step.result.case for step in result.steps if step.accepted)[-1]
    )
    assert _preserves(_evaluate(result.final_case))


def test_candidate_transforms_preserve_entry_order_duplicates_and_builder_representation():
    case = ArchiveCase((*_input().entries, _input().entries[0]))
    trials = tuple(reduction_candidates(case))
    assert {kind for kind, _ in trials} == set(ReductionKind) - {ReductionKind.INITIAL}
    assert len({candidate.case_id for _, candidate in trials}) == len(trials)
    assert trials[0] == (ReductionKind.ENTRY, ArchiveCase(case.entries[1:]))
    for kind, candidate in trials:
        build_tar(candidate)
        if kind == ReductionKind.ENTRY:
            assert len(candidate.entries) == len(case.entries) - 1
        else:
            assert len(candidate.entries) == len(case.entries)
    assert tuple(reduction_candidates(ArchiveCase(()))) == ()
    result = minimize_case(ArchiveCase(()), _result, lambda run: True, execution_budget=1)
    assert result.termination == MinimizationTermination.FIXED_POINT


@pytest.mark.parametrize("status", tuple(ExecutionStatus))
def test_execution_status_is_not_a_preservation_condition(status):
    def evaluate(case):
        result = _evaluate(case)
        exit_code = (
            None
            if status == ExecutionStatus.TIMED_OUT
            else (0 if status == ExecutionStatus.SUCCESS else 1)
        )
        return replace(
            result, execution=replace(result.execution, status=status, exit_code=exit_code)
        )

    result = minimize_case(_input(), evaluate, _preserves, execution_budget=100)
    assert _preserves(_evaluate(result.final_case))
    assert all(step.result.execution.status == status for step in result.steps)


def test_invalid_budget_baseline_and_evaluator_drift_raise_without_fabricating_completion():
    calls = []

    def evaluate(case):
        calls.append(case)
        return _result(case)

    for budget in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match="positive integer"):
            minimize_case(_input(), evaluate, _preserves, execution_budget=budget)  # type: ignore[arg-type]
    assert calls == []
    with pytest.raises(ValueError, match="initial case"):
        minimize_case(_input(), evaluate, _preserves, execution_budget=5)
    with pytest.raises(ValueError, match="requested case"):
        minimize_case(
            _input(), lambda case: _result(_case("other")), lambda run: True, execution_budget=5
        )
    with pytest.raises(ValueError, match="bool"):
        minimize_case(_input(), _evaluate, lambda run: 1, execution_budget=5)  # type: ignore[arg-type]


def test_evaluator_and_predicate_failures_propagate():
    def fail(value):
        raise RuntimeError("controller failure")

    with pytest.raises(RuntimeError, match="controller failure"):
        minimize_case(_input(), fail, _preserves, execution_budget=2)
    with pytest.raises(RuntimeError, match="controller failure"):
        minimize_case(_input(), _evaluate, fail, execution_budget=2)

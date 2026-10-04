"""Exact archive binding and explicit generic violation-preservation evidence."""

import json
from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.minimizer import ViolationCondition, minimize_violation
from inodefence.model import ContractId, ExecutionStatus, canonical_json
from test_feedback_corpus import _case, _creation, _identity, _result
from test_minimizer import _input


def _evaluate(case):
    result = _result(case)
    violations = (
        (_creation(),)
        if any(entry.content and entry.content.startswith(b"x") for entry in case.entries)
        else ()
    )
    return replace(
        result,
        archive_format=BUILDER_FORMAT,
        archive_sha256=sha256(build_tar(case)).hexdigest(),
        violations=violations,
    )


def test_violation_reduction_keeps_exact_condition_and_replayable_archive_binding():
    result = minimize_violation(_input(), _evaluate, execution_budget=100)
    assert result.condition.policy_id == "exact-violation-fingerprints-v1"
    assert result.final_result.case == result.reduction.final_case
    assert result.final_result in tuple(
        step.result for step in result.reduction.steps if step.accepted
    )
    for step in result.reduction.steps:
        assert step.result.archive_sha256 == sha256(build_tar(step.result.case)).hexdigest()
        assert step.result.archive_format == BUILDER_FORMAT
        assert result.condition.matches(step.result) == step.accepted
    assert any(not step.accepted for step in result.reduction.steps)
    assert result == minimize_violation(_input(), _evaluate, execution_budget=100)
    encoded = json.loads(canonical_json(result))
    assert encoded["model"] == "ViolationMinimizationResult" and encoded["schema_version"] == 1
    assert encoded["value"]["condition"]["policy_id"] == "exact-violation-fingerprints-v1"
    assert result.final_result.case.case_id == result.reduction.final_case.case_id


def test_condition_uses_full_semantic_evidence_and_ignores_raw_inode_values():
    first = replace(_result(_case("a")), violations=(_identity(inode=10),))
    condition = ViolationCondition.from_result(first)
    same = replace(first, violations=(_identity(inode=9910),))
    assert condition.matches(same)
    assert not condition.matches(replace(first, violations=()))
    assert not condition.matches(replace(first, violations=(_identity("extract/b"),)))
    assert not condition.matches(replace(first, violations=(_identity(), _creation())))
    assert not condition.matches(
        replace(first, violations=(replace(_creation(), contract_id=ContractId.C2),))
    )
    with pytest.raises(ValueError, match="violation"):
        ViolationCondition.from_result(_result(_case("safe")))
    with pytest.raises(ValueError):
        replace(condition, policy_id="unknown")
    with pytest.raises(ValueError):
        replace(condition, fingerprints=())


@pytest.mark.parametrize("drift", ("hash", "format", "case"))
def test_unbound_run_is_rejected_before_preservation_decision(drift):
    calls = []

    def evaluate(case):
        calls.append(case)
        result = _evaluate(case)
        if drift == "hash":
            return replace(result, archive_sha256="0" * 64)
        if drift == "format":
            return replace(result, archive_format="other-encoding")
        return replace(result, case=_case("other"))

    with pytest.raises(ValueError, match="case|archive"):
        minimize_violation(_input(), evaluate, execution_budget=3)
    assert len(calls) == 1


@pytest.mark.parametrize("status", tuple(ExecutionStatus))
def test_status_does_not_substitute_for_preserved_violation_evidence(status):
    calls = []

    def evaluate(case):
        calls.append(case)
        result = _evaluate(case)
        exit_code = (
            None
            if status == ExecutionStatus.TIMED_OUT
            else (0 if status == ExecutionStatus.SUCCESS else 1)
        )
        return replace(
            result, execution=replace(result.execution, status=status, exit_code=exit_code)
        )

    result = minimize_violation(_input(), evaluate, execution_budget=3)
    assert len(calls) == len(result.reduction.steps) == 3
    assert all(step.result.execution.status == status for step in result.reduction.steps)
    assert result.condition.matches(result.final_result)


def test_invalid_budget_never_invokes_evaluator_and_safe_baseline_is_not_minimized():
    calls = []

    def evaluate(case):
        calls.append(case)
        return replace(
            _result(case),
            archive_format=BUILDER_FORMAT,
            archive_sha256=sha256(build_tar(case)).hexdigest(),
        )

    with pytest.raises(ValueError, match="positive integer"):
        minimize_violation(_input(), evaluate, execution_budget=0)
    assert calls == []
    with pytest.raises(ValueError, match="violation"):
        minimize_violation(_input(), evaluate, execution_budget=2)
    assert len(calls) == 1

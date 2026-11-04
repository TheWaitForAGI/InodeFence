"""Step-level observer-integrity policy: mark invalid, continue, keep the verdict.

The native demo historically aborted the whole campaign when a target run
succeeded but its effect trace was not integrity-valid (e.g. a
``malformed_identity`` failure from a duplicate-path/different-type archive).
This input-shape-correlated STOP censored the campaign denominator, so the
reproduction loop now offers a step-level policy: keep the step as an
observer-integrity invalid observation and continue. These tests pin the policy
behaviour, the per-step ``validity`` marker, and the summary counts (including
the ``hit_with_invalid_trace`` sensitivity field), none of which need docker.
"""

from dataclasses import replace
from typing import Any, cast

import pytest
import scripts.run_effect_demo as run_effect_demo
from scripts.run_effect_demo import NativeDemoAborted, minimal_seed_corpus, native_demo_report

from inodefence.effect_demo import (
    DEMO_REPORT_SCHEMA,
    OBSERVER_INTEGRITY_REASON,
    _step_is_prereg_hit,
    observer_integrity_summary,
    observer_integrity_validity,
)
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.model import (
    ContractId,
    EffectStreamCompleteness,
    ObservationFailure,
    ObservationFailureKind,
)


def _non_integrity_success(case):
    """A SUCCESS run whose effect trace carries a malformed_identity failure.

    Derived from a synthetic (valid) result by flipping its trace to INVALID with
    one MALFORMED_IDENTITY failure; the execution status stays SUCCESS, which is
    exactly the observer-integrity STOP condition.
    """
    result = synthetic_effect_result(case)
    trace = result.trace
    failure = ObservationFailure(
        ObservationFailureKind.MALFORMED_IDENTITY,
        "entry identity differs from ArchiveCase",
        trace.provenance.sources[0].source_id,
        0,
    )
    bad_trace = replace(
        trace,
        completeness=EffectStreamCompleteness.INVALID,
        observation_failures=(failure,),
    )
    return replace(result, trace=bad_trace)


def test_schema_is_bumped_for_the_additive_validity_field() -> None:
    assert DEMO_REPORT_SCHEMA == 3


def test_validity_marks_success_with_untrustworthy_trace_invalid() -> None:
    case = minimal_seed_corpus()[0]
    valid = synthetic_effect_result(case)
    invalid = _non_integrity_success(case)

    assert observer_integrity_validity(valid) == {
        "validity": "valid",
        "invalid_reason": None,
        "observation_failure_kinds": [],
    }
    assert observer_integrity_validity(invalid) == {
        "validity": "invalid",
        "invalid_reason": OBSERVER_INTEGRITY_REASON,
        "observation_failure_kinds": ["malformed_identity"],
    }


def _record(validity: str, *, c1: bool = False, c2: bool = False, violated: bool = False) -> dict:
    return {
        "validity": validity,
        "invalid_reason": OBSERVER_INTEGRITY_REASON if validity == "invalid" else None,
        "oracle": {ContractId.C0.value: False, ContractId.C1.value: c1, ContractId.C2.value: c2},
        "feedback": {"contract_violated": violated},
    }


def test_prereg_hit_reads_only_snapshot_verdict_not_trace_validity() -> None:
    # A hit is a contract-violated step whose post-state oracle flags C1 or C2,
    # independent of whether the effect trace was observer-integrity valid.
    assert _step_is_prereg_hit(_record("invalid", c1=True, violated=True))
    assert _step_is_prereg_hit(_record("valid", c2=True, violated=True))
    # C1/C2 flagged but not contract_violated is not a hit.
    assert not _step_is_prereg_hit(_record("invalid", c1=True, violated=False))
    # contract_violated but only C0 is not a hit (C0 is not in the hit definition).
    assert not _step_is_prereg_hit(_record("valid", violated=True))


def test_summary_counts_invalid_steps_and_the_a1_sensitivity_count() -> None:
    steps = [
        _record("valid", c1=True, violated=True),  # valid hit
        _record("invalid"),  # invalid, not a hit
        _record("invalid", c1=True, violated=True),  # invalid hit (C1)
        _record("invalid", c2=True, violated=True),  # invalid hit (C2)
    ]

    summary = observer_integrity_summary(steps)

    assert summary["invalid_steps"] == 3
    assert summary["invalid_by_reason"] == {OBSERVER_INTEGRITY_REASON: 3}
    # a2 (primary) keeps all hits; a1 (sensitivity) would exclude these two.
    assert summary["hit_with_invalid_trace"] == 2


class _FakeTarget:
    tar_version = run_effect_demo.pinned_node_tar_version()
    node_version = "22.22.0"


class _FakeRun:
    def __init__(self, result) -> None:
        self.result = result
        self.controller_flush_verified = True
        self.transport_error = None
        self.raw_stream = b""


def _bind_fake_producer(monkeypatch, invalid_index: int):
    """Producer whose case at ``invalid_index`` returns a non-integrity SUCCESS run."""
    monkeypatch.setattr(run_effect_demo.NodeTarEffectTarget, "bind", lambda *a, **k: _FakeTarget())
    calls = 0

    def fake_run(case, target):
        nonlocal calls
        result = (
            _non_integrity_success(case)
            if calls == invalid_index
            else synthetic_effect_result(case)
        )
        calls += 1
        return _FakeRun(result)

    monkeypatch.setattr(run_effect_demo, "run_node_tar_effect_case", fake_run)


def test_stop_policy_aborts_on_untrustworthy_trace_after_success(monkeypatch) -> None:
    _bind_fake_producer(monkeypatch, invalid_index=1)
    records: list[dict] = []

    with pytest.raises(NativeDemoAborted) as aborted:
        native_demo_report(object(), "sha256:" + "0" * 64, budget=6, step_sink=records.append)  # type: ignore[arg-type]

    assert aborted.value.step_index == 1
    assert "evidence integrity failed" in aborted.value.reason
    # Only the clean step before the abort was delivered.
    assert [record["index"] for record in records] == [0]
    assert records[0]["validity"] == "valid"


def test_continue_policy_keeps_the_invalid_step_and_finishes_the_budget(monkeypatch) -> None:
    _bind_fake_producer(monkeypatch, invalid_index=1)
    records: list[dict] = []

    report = native_demo_report(
        object(),  # type: ignore[arg-type]
        "sha256:" + "0" * 64,
        budget=6,
        step_sink=records.append,
        observer_integrity_continue=True,
    )

    # The campaign ran the full budget instead of aborting at step 1; the sink
    # records are identical to the report's steps array.
    assert [record["index"] for record in records] == list(range(6))
    steps = cast(list[dict[str, Any]], report["steps"])
    assert records == steps
    invalid_step = steps[1]
    assert invalid_step["validity"] == "invalid"
    assert invalid_step["invalid_reason"] == OBSERVER_INTEGRITY_REASON
    assert invalid_step["observation_failure_kinds"] == ["malformed_identity"]
    # The invalid step is feedback-ineligible and never enters the retained corpus.
    assert invalid_step["feedback"]["feedback_eligible"] is False
    assert invalid_step["feedback"]["retained"] is False
    assert invalid_step["case_id"] not in cast(list[str], report["retained_case_ids"])
    # Summary reports exactly one observer-integrity invalid step.
    summary = cast(dict[str, Any], report["observer_integrity_summary"])
    assert summary["invalid_steps"] == 1
    assert summary["invalid_by_reason"] == {OBSERVER_INTEGRITY_REASON: 1}

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
    assert DEMO_REPORT_SCHEMA >= 3  # integration: 4 after oracle_fingerprints (lane 5)


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

    def fake_run(case, target, **_sentinel_kwargs):
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


class _FakeHistoricalTarget:
    tar_version = "7.5.2"
    node_version = "22.22.0"


def _bind_fake_historical_producer(monkeypatch, invalid_index: int):
    """Historical producer with an observer-integrity invalid run at ``invalid_index``.

    The catalog guards are stubbed so the test exercises the step policy, not the
    frozen-image allowlist (covered elsewhere).
    """
    monkeypatch.setattr(run_effect_demo, "historical_target_versions", lambda: {"7.5.2": "lock"})
    monkeypatch.setattr(
        run_effect_demo.NodeTarEffectTarget, "bind", lambda *a, **k: _FakeHistoricalTarget()
    )
    calls = 0

    def fake_run(case, target, **_sentinel_kwargs):
        nonlocal calls
        result = (
            _non_integrity_success(case)
            if calls == invalid_index
            else synthetic_effect_result(case)
        )
        calls += 1
        return _FakeRun(result)

    monkeypatch.setattr(run_effect_demo, "run_node_tar_effect_case", fake_run)


def test_historical_stop_policy_aborts_like_the_powered_campaign(monkeypatch) -> None:
    _bind_fake_historical_producer(monkeypatch, invalid_index=1)

    with pytest.raises(NativeDemoAborted) as aborted:
        run_effect_demo.historical_demo_report(object(), "sha256:" + "0" * 64, "7.5.2", budget=6)  # type: ignore[arg-type]

    assert aborted.value.step_index == 1
    assert "evidence integrity failed" in aborted.value.reason


def test_historical_continue_policy_keeps_the_invalid_step(monkeypatch) -> None:
    _bind_fake_historical_producer(monkeypatch, invalid_index=1)

    report = run_effect_demo.historical_demo_report(
        object(),  # type: ignore[arg-type]
        "sha256:" + "0" * 64,
        "7.5.2",
        budget=6,
        observer_integrity_continue=True,
    )

    steps = cast(list[dict[str, Any]], report["steps"])
    assert len(steps) == 6
    assert steps[1]["validity"] == "invalid"
    assert steps[1]["invalid_reason"] == OBSERVER_INTEGRITY_REASON
    summary = cast(dict[str, Any], report["observer_integrity_summary"])
    assert summary["invalid_steps"] == 1


def _demo_namespace(mode: str, policy: str | None):
    import argparse

    return argparse.Namespace(
        mode=mode,
        seed=None,
        budget=None,
        policy=None,
        mutation_policy=None,
        tar_version="7.5.2" if mode == run_effect_demo.HISTORICAL_DEMO_MODE else None,
        observer_integrity_policy=policy,
    )


@pytest.mark.parametrize("mode", ["effect-demo", run_effect_demo.HISTORICAL_DEMO_MODE])
def test_policy_flag_is_accepted_and_mapped_for_both_demos(mode) -> None:
    parser = run_effect_demo.argparse.ArgumentParser()
    args = _demo_namespace(mode, "invalid-continue")

    run_effect_demo.check_demo_arguments(parser, args)  # does not raise

    assert run_effect_demo.demo_options(args)["observer_integrity_continue"] is True
    assert "observer_integrity_policy" in run_effect_demo.DEMO_FORWARDED_ARGUMENTS


def test_policy_flag_defaults_to_stop_and_is_rejected_outside_the_demos() -> None:
    parser = run_effect_demo.argparse.ArgumentParser()
    # Default (no flag) leaves the frozen behavior: no continue option in the forwarded opts.
    assert "observer_integrity_continue" not in run_effect_demo.demo_options(
        _demo_namespace("effect-demo", None)
    )
    # 'stop' is explicit frozen behavior, still no continue flag.
    assert "observer_integrity_continue" not in run_effect_demo.demo_options(
        _demo_namespace("effect-demo", "stop")
    )
    # Restricted to the effect demos.
    with pytest.raises(SystemExit):
        run_effect_demo.check_demo_arguments(
            parser, _demo_namespace("benign-node-smoke", "invalid-continue")
        )


class _TransportBrokenRun:
    """A SUCCESS run whose trace is integrity-valid but whose transport is not trusted.

    Constructed directly (not reachable from a real capture, where the signals are
    coupled) to prove the continue policy never releases a host/transport trust
    failure: that abort is the runtime lane's to classify, not observer_integrity.
    """

    def __init__(self, result) -> None:
        self.result = result
        self.controller_flush_verified = False
        self.transport_error = "controller did not acknowledge terminal frame"
        self.raw_stream = b""


def test_continue_policy_still_aborts_on_host_transport_trust_failure(monkeypatch) -> None:
    monkeypatch.setattr(run_effect_demo.NodeTarEffectTarget, "bind", lambda *a, **k: _FakeTarget())
    calls = 0

    def fake_run(case, target, **_sentinel_kwargs):
        nonlocal calls
        # A fully valid (integrity_valid=True) result, but the controller could not
        # verify the terminal frame: a transport trust failure, not observer-integrity.
        run = (
            _TransportBrokenRun(synthetic_effect_result(case))
            if calls == 1
            else _FakeRun(synthetic_effect_result(case))
        )
        calls += 1
        return run

    monkeypatch.setattr(run_effect_demo, "run_node_tar_effect_case", fake_run)

    # Even with the continue policy on, a transport trust failure aborts: it is not
    # a pure observer-integrity failure, so it is never kept or mislabeled.
    with pytest.raises(NativeDemoAborted) as aborted:
        native_demo_report(
            object(),  # type: ignore[arg-type]
            "sha256:" + "0" * 64,
            budget=6,
            observer_integrity_continue=True,
        )
    assert aborted.value.step_index == 1
    assert "evidence integrity failed" in aborted.value.reason


def test_stop_and_continue_share_the_case_id_sequence_up_to_the_invalid_step(monkeypatch) -> None:
    invalid_index = 2

    def run_once(continue_policy: bool, records: list[dict]):
        return native_demo_report(
            object(),  # type: ignore[arg-type]
            "sha256:" + "0" * 64,
            budget=6,
            step_sink=records.append,
            observer_integrity_continue=continue_policy,
        )

    _bind_fake_producer(monkeypatch, invalid_index=invalid_index)
    stop_records: list[dict] = []
    with pytest.raises(NativeDemoAborted):
        run_once(False, stop_records)

    _bind_fake_producer(monkeypatch, invalid_index=invalid_index)
    continue_records: list[dict] = []
    report = run_once(True, continue_records)
    continue_steps = cast(list[dict[str, Any]], report["steps"])

    # stop aborts exactly at the invalid step, so it delivered only the steps before it.
    assert [record["index"] for record in stop_records] == list(range(invalid_index))
    # Both policies drive an identical case_id sequence up to the invalid step; only
    # at the invalid step do they diverge (stop aborts, continue keeps and continues).
    stop_case_ids = [record["case_id"] for record in stop_records]
    continue_case_ids = [step["case_id"] for step in continue_steps[:invalid_index]]
    assert stop_case_ids == continue_case_ids
    assert continue_steps[invalid_index]["validity"] == "invalid"

"""Actual contained node-tar v2 producer fixtures; no campaign integration."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from scripts.qualify_node_causal_effects import REJECTION_CASE, qualification_cases

from inodefence.effect_pipeline import run_node_tar_effect_case
from inodefence.evaluation.native_effect_evidence import export_native_effect_run
from inodefence.model import (
    EffectClass,
    EffectStreamCompleteness,
    EffectTargetTermination,
    ExecutionStatus,
)
from inodefence.model.effect import effect_is_realized
from inodefence.targets.node_tar_effect import NodeTarEffectTarget, archive_references


@pytest.mark.parametrize(("name", "case"), tuple(qualification_cases().items()))
def test_actual_effect_producer_preserves_target_and_typed_evidence(
    name, case, container_backend, container_image
) -> None:
    target = NodeTarEffectTarget.bind(container_backend, container_image)
    run = run_node_tar_effect_case(case, target)
    trace = run.result.trace
    if not trace.integrity_valid:
        destination = Path(trace.before.sandbox_root).parent / f"gate3-invalid-{name}-{uuid4().hex}"
        digest = export_native_effect_run(run, destination)
        print(json.dumps({"invalid_evidence": str(destination), "manifest_sha256": digest}))
    expected_status = (
        ExecutionStatus.REJECTED if name == REJECTION_CASE else ExecutionStatus.SUCCESS
    )
    expected_termination = (
        EffectTargetTermination.REJECTED
        if name == REJECTION_CASE
        else EffectTargetTermination.SUCCESS
    )

    assert run.result.base_result.execution.status == expected_status
    assert trace.termination == expected_termination
    assert trace.archive_entries == archive_references(case)
    assert trace.integrity_valid
    assert trace.completeness == EffectStreamCompleteness.COMPLETE
    assert run.controller_flush_verified and run.transport_error is None
    raw = json.loads(run.raw_stream)
    assert all("archive/input.tar" not in record.get("paths", []) for record in raw["records"])
    assert trace.provenance.raw_stream_sha256
    assert [point.sequence for point in trace.observed_event_points()] == list(
        range(trace.last_produced_sequence + 1)
    )
    assert all(
        event.effect_class == EffectClass.OPERATION_OBSERVED or effect_is_realized(event)
        for event in trace.effect_events
    )
    if name == "hardlink-identity":
        assert any(
            event.effect_class == EffectClass.HARDLINK_IDENTITY_RELATION_CREATION
            for event in trace.effect_events
        )
    if name == "symlink":
        assert any(
            event.effect_class == EffectClass.SYMLINK_CREATION for event in trace.effect_events
        )
    assert not Path(trace.after.sandbox_root).exists()


def test_actual_overflow_is_explicit_and_never_integrity_valid(
    container_backend, container_image
) -> None:
    case = qualification_cases()["regular-file"]
    target = NodeTarEffectTarget.bind(container_backend, container_image, event_bound=3)
    trace = run_node_tar_effect_case(case, target).result.trace
    assert trace.completeness == EffectStreamCompleteness.INVALID
    assert not trace.integrity_valid
    assert any(failure.kind.value == "buffer_overflow" for failure in trace.observation_failures)


def test_actual_timeout_is_distinct_from_observer_failure(
    container_backend, container_image
) -> None:
    case = qualification_cases()["regular-file"]
    target = NodeTarEffectTarget.bind(container_backend, container_image, timeout_seconds=1e-9)
    trace = run_node_tar_effect_case(case, target).result.trace
    assert trace.termination == EffectTargetTermination.TIMED_OUT
    assert trace.completeness == EffectStreamCompleteness.INCOMPLETE
    assert not trace.integrity_valid

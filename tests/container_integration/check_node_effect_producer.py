"""Actual contained node-tar v2 producer fixtures; no campaign integration."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from scripts.qualify_node_causal_effects import REJECTION_CASE, qualification_cases

from inodefence.effect_pipeline import run_node_tar_effect_case
from inodefence.evaluation.native_effect_evidence import export_native_effect_run
from inodefence.feedback.boundary_attempt_frame import (
    FRAME_FORMAT,
    boundary_attempt_frame_from_effect_trace,
    frame_boundary_attempt_keys,
)
from inodefence.feedback.effect import boundary_attempt_keys, external_resolve_keys
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    BoundaryAttemptSignature,
    EffectClass,
    EffectFeedbackKey,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EntryType,
    ExecutionStatus,
    ExternalResolveSignature,
    ObservedOperationType,
    OperationOutcome,
)
from inodefence.model.effect import EffectEventTrace, effect_is_realized
from inodefence.targets.node_tar_effect import NodeTarEffectTarget, archive_references

_LINK_OPS = (ObservedOperationType.LINK, ObservedOperationType.SYMLINK)


def _outcome_blind(keys: set[EffectFeedbackKey]) -> set[tuple]:
    """Identify each feedback key ignoring the operation outcome.

    The v1 frame's coarse outcome collapses the rarer non-SUCCEEDED OperationOutcome values
    (NOT_FOUND -> INVALID), so the projection and the direct M3.1 derivation can differ only in a
    key's outcome; every other dimension (kind, trigger entry type, region, escape shape) matches.
    """
    blind: set[tuple] = set()
    for key in keys:
        signature = key.signature
        if isinstance(signature, BoundaryAttemptSignature):
            blind.add(
                (
                    key.kind,
                    signature.trigger_entry_type,
                    signature.target_region,
                    signature.escape_shape,
                )
            )
        elif isinstance(signature, ExternalResolveSignature):
            blind.add((key.kind, signature.operation, signature.resolved_region))
    return blind


def _assert_projection_matches_direct_derivation(trace: EffectEventTrace) -> None:
    """The real trace drives the v1-frame projection -> normalizer identically to the M3.1 keys.

    Projecting an EffectEventTrace to the inodefence-boundary-attempt-v1 frame and normalizing it
    must yield the same feedback keys node-tar's direct M3.1 trace derivation produces, up to the
    frame's documented outcome coarsening. For SUCCEEDED link ops the match is exact.
    """
    frame = boundary_attempt_frame_from_effect_trace(trace)
    assert frame["format"] == FRAME_FORMAT
    assert isinstance(frame["attempts"], list)
    framed = set(frame_boundary_attempt_keys(frame))
    direct = set(boundary_attempt_keys(trace)) | set(external_resolve_keys(trace))
    assert _outcome_blind(framed) == _outcome_blind(direct)
    link_outcomes = {event.outcome for event in trace.effect_events if event.operation in _LINK_OPS}
    if link_outcomes <= {OperationOutcome.SUCCEEDED}:
        assert framed == direct


@pytest.mark.parametrize(("name", "case"), tuple(qualification_cases().items()))
def test_actual_effect_producer_preserves_target_and_typed_evidence(
    name, case, container_backend, container_image
) -> None:
    target = NodeTarEffectTarget.bind(container_backend, container_image)
    if name == "regular-file":
        frozen = target.capture_isolation()
        assert frozen.artifacts == target.artifacts
        assert frozen.artifact_origin == "image-identification-v1"
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
    # M4 generality: the SAME real producer trace drives the v1-frame projection and normalizer.
    _assert_projection_matches_direct_derivation(trace)
    assert not Path(trace.after.sandbox_root).exists()


def test_escaping_hardlink_real_trace_projects_to_boundary_attempt_frame(
    container_backend, container_image
) -> None:
    """A real node-tar run of an escaping hardlink emits the v1 frame -> M3.1 boundary keys.

    End-to-end on a real extractor: producer -> inodefence-boundary-attempt-v1 frame -> normalizer
    -> M3.1 feedback keys. The pinned producer image is a fixed node-tar release, so the escaping
    hardlink is rejected; this exercises the non-right-censored boundary-ATTEMPT signal (an attempt
    the extractor declined still surfaces a key). The projection and the direct M3.1 derivation are
    asserted to agree on every key up to the frame's documented outcome coarsening; the observed
    link operations and resulting frame are printed as evidence.
    """
    case = ArchiveCase(
        (
            ArchiveEntry("source", EntryType.REGULAR, content=b"shared"),
            ArchiveEntry("hard", EntryType.HARDLINK, link_target="../outside/sentinel.txt"),
        )
    )
    target = NodeTarEffectTarget.bind(container_backend, container_image)
    trace = run_node_tar_effect_case(case, target).result.trace

    _assert_projection_matches_direct_derivation(trace)
    frame = boundary_attempt_frame_from_effect_trace(trace)
    framed = set(frame_boundary_attempt_keys(frame))
    print(
        json.dumps(
            {
                "escaping_hardlink_real_trace": {
                    "termination": trace.termination.value,
                    "integrity_valid": trace.integrity_valid,
                    "link_operations": [
                        {
                            "operation": event.operation.value,
                            "outcome": event.outcome.value,
                            "effect_class": event.effect_class.value,
                            "affected_paths": list(event.affected_paths),
                            "link_target": event.entry.link_target,
                        }
                        for event in trace.effect_events
                        if event.operation in _LINK_OPS
                    ],
                    "frame_attempts": frame["attempts"],
                    "boundary_feedback_keys": sorted(str(key) for key in framed),
                }
            },
            sort_keys=True,
        )
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

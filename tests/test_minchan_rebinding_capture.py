"""Synthetic callback schedules only; never imports or executes node-tar."""

from dataclasses import replace
from hashlib import sha256

import pytest
from scripts.minchan_rebinding_capture import SyntheticRebindingCapture

from inodefence.evaluation.rebinding_evidence import reconstruct_rebinding_evidence
from inodefence.model import ArchiveEntryReference, EntryType, OperationOutcome
from test_rebinding_v3 import V3_SOURCE, _trace


def test_explicit_continuation_exports_existing_v3_reader_compatible_bytes():
    trace = _trace()
    removal, creation = trace.effect_events
    capture = SyntheticRebindingCapture()
    capture.begin(removal.correlation_id, removal.entry, removal.start_sequence)
    capture.complete(removal)
    capture.begin(
        creation.correlation_id,
        creation.entry,
        creation.start_sequence,
        predecessor=removal.correlation_id,
        token="synthetic-callback-continuation",
    )
    capture.complete(creation)
    assert capture.finish(target_succeeded=True).complete
    raw = capture.envelope(trace, V3_SOURCE)
    verified = reconstruct_rebinding_evidence(raw, sha256(raw).hexdigest(), trace, V3_SOURCE)
    assert len(verified.sequences) == 1


@pytest.mark.parametrize("completion_order", [("outer", "inner"), ("inner", "outer")])
@pytest.mark.parametrize("same_entry", [False, True])
def test_overlapping_operations_keep_identity_with_either_completion_order(
    completion_order, same_entry
):
    template = _trace().effect_events[0]
    capture = SyntheticRebindingCapture()
    entries = {
        "outer": template.entry,
        "inner": (
            template.entry if same_entry else ArchiveEntryReference(1, "q", EntryType.REGULAR, None)
        ),
    }
    for sequence, name in enumerate(entries):
        capture.begin(name, entries[name], sequence)
    for sequence, name in enumerate(completion_order, start=2):
        capture.complete(
            replace(
                template,
                correlation_id=name,
                entry=entries[name],
                start_sequence=list(entries).index(name),
                completion_sequence=sequence,
            )
        )
    assert capture.finish(target_succeeded=True).complete


def test_failed_callback_preserves_error_and_refuses_success_export():
    event = replace(_trace().effect_events[0], outcome=OperationOutcome.ACCESS_DENIED)
    capture = SyntheticRebindingCapture()
    capture.begin(event.correlation_id, event.entry, event.start_sequence)
    capture.complete(event, error_code="EACCES")
    terminal = capture.finish(target_succeeded=False)
    assert terminal.failures == ((event.correlation_id, "EACCES"),)
    assert not terminal.complete
    with pytest.raises(ValueError, match="complete successful"):
        capture.envelope(_trace(), V3_SOURCE)


@pytest.mark.parametrize(
    "defect", ["duplicate_start", "duplicate_completion", "unmatched", "entry"]
)
def test_missing_duplicate_or_mismatched_events_poison_capture(defect):
    event = _trace().effect_events[0]
    capture = SyntheticRebindingCapture()
    capture.begin(event.correlation_id, event.entry, event.start_sequence)
    with pytest.raises(ValueError):
        if defect == "duplicate_start":
            capture.begin(event.correlation_id, event.entry, event.start_sequence + 1)
        elif defect == "duplicate_completion":
            capture.complete(event)
            capture.complete(replace(event, completion_sequence=event.completion_sequence + 1))
        elif defect == "unmatched":
            capture.complete(replace(event, correlation_id="missing"))
        else:
            capture.complete(
                replace(event, entry=ArchiveEntryReference(1, "q", EntryType.REGULAR, None))
            )
    assert capture.finish(target_succeeded=True).invalid


def test_exit_keeps_pending_operations_and_rejects_late_callbacks():
    event = _trace().effect_events[0]
    capture = SyntheticRebindingCapture()
    capture.begin(event.correlation_id, event.entry, event.start_sequence)
    terminal = capture.finish(target_succeeded=False)
    assert terminal.pending == (event.correlation_id,)
    assert not terminal.complete
    with pytest.raises(ValueError, match="closed"):
        capture.complete(event)


def test_overflow_is_invalid_and_bound_is_not_silently_extended():
    event = _trace().effect_events[0]
    capture = SyntheticRebindingCapture(max_operations=1)
    capture.begin(event.correlation_id, event.entry, 0)
    with pytest.raises(ValueError, match="bound exceeded"):
        capture.begin("second", event.entry, 1)
    assert capture.finish(target_succeeded=True).invalid


def test_no_token_means_no_dependency_even_with_same_entry_path_and_order():
    trace = _trace()
    capture = SyntheticRebindingCapture()
    for event in trace.effect_events:
        capture.begin(event.correlation_id, event.entry, event.start_sequence)
        capture.complete(event)
    capture.finish(target_succeeded=True)
    raw = capture.envelope(trace, V3_SOURCE)
    verified = reconstruct_rebinding_evidence(raw, sha256(raw).hexdigest(), trace, V3_SOURCE)
    assert verified.sequences == ()


def test_continuation_cannot_start_before_predecessor_completes():
    removal, creation = _trace().effect_events
    capture = SyntheticRebindingCapture()
    capture.begin(removal.correlation_id, removal.entry, removal.start_sequence)
    with pytest.raises(ValueError, match="successful same-entry"):
        capture.begin("creation", creation.entry, 2, predecessor=removal.correlation_id, token="t")


def test_failed_callback_without_error_is_invalid():
    event = replace(_trace().effect_events[0], outcome=OperationOutcome.ACCESS_DENIED)
    capture = SyntheticRebindingCapture()
    capture.begin(event.correlation_id, event.entry, event.start_sequence)
    with pytest.raises(ValueError, match="requires error"):
        capture.complete(event)
    assert capture.finish(target_succeeded=False).invalid


def test_sequence_gap_is_not_misrepresented_as_full_transport_validation():
    event = _trace().effect_events[0]
    capture = SyntheticRebindingCapture()
    capture.begin(event.correlation_id, event.entry, event.start_sequence)
    capture.complete(replace(event, completion_sequence=event.completion_sequence + 10))
    # The operation-only prototype cannot tell omitted lifecycle records from
    # omitted operations. Native completeness must come from the v2 channel.
    assert capture.finish(target_succeeded=True).complete


def test_export_rejects_endpoint_drift_from_validated_v2_trace():
    trace = _trace()
    capture = SyntheticRebindingCapture()
    for event in trace.effect_events:
        capture.begin(event.correlation_id, event.entry, event.start_sequence)
        capture.complete(replace(event, correlation_id=event.correlation_id))
    capture.finish(target_succeeded=True)
    other = _trace(created_ino=23)
    with pytest.raises(ValueError, match="differs from v2 trace"):
        capture.envelope(other, V3_SOURCE)


def test_close_is_one_shot_and_target_failure_cannot_export():
    trace = _trace()
    capture = SyntheticRebindingCapture()
    for event in trace.effect_events:
        capture.begin(event.correlation_id, event.entry, event.start_sequence)
        capture.complete(event)
    assert not capture.finish(target_succeeded=False).complete
    with pytest.raises(ValueError, match="closed"):
        capture.finish(target_succeeded=True)
    with pytest.raises(ValueError, match="complete successful"):
        capture.envelope(trace, V3_SOURCE)


@pytest.mark.parametrize("record_removal", [False, True])
def test_export_rejects_whole_operation_pairs_missing_from_capture(record_removal):
    trace = _trace()
    capture = SyntheticRebindingCapture()
    if record_removal:
        event = trace.effect_events[0]
        capture.begin(event.correlation_id, event.entry, event.start_sequence)
        capture.complete(event)
    assert capture.finish(target_succeeded=True).complete
    # Local settlement cannot replace a complete-v2-trace coverage cross-check.
    with pytest.raises(ValueError, match="captured operation set differs"):
        capture.envelope(trace, V3_SOURCE)


@pytest.mark.parametrize("reuse", ["predecessor", "token"])
def test_continuation_is_consumed_once_per_predecessor_and_token(reuse):
    removal, creation = _trace().effect_events
    capture = SyntheticRebindingCapture()
    capture.begin(removal.correlation_id, removal.entry, removal.start_sequence)
    capture.complete(removal)
    capture.begin(
        creation.correlation_id,
        creation.entry,
        creation.start_sequence,
        predecessor=removal.correlation_id,
        token="branch-token",
    )
    predecessor = removal.correlation_id
    sequence = creation.start_sequence + 1
    token = "new-token"
    if reuse == "token":
        other = replace(
            removal,
            correlation_id="other-removal",
            start_sequence=sequence,
            completion_sequence=sequence + 1,
        )
        capture.begin(other.correlation_id, other.entry, other.start_sequence)
        capture.complete(other)
        predecessor, sequence, token = other.correlation_id, sequence + 2, "branch-token"
    with pytest.raises(ValueError, match="continuation already consumed"):
        capture.begin(
            "second-creation", creation.entry, sequence, predecessor=predecessor, token=token
        )
    assert capture.finish(target_succeeded=False).invalid

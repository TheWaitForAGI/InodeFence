import json
from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.evaluation.rebinding_evidence import (
    PROTOCOL_ID,
    PROTOCOL_VERSION,
    reconstruct_rebinding_evidence,
)
from inodefence.feedback import (
    derive_namespace_rebinding_sequences,
    effect_feedback_keys,
    effect_feedback_projection_v3,
)
from inodefence.model import (
    ArchiveEntryReference,
    AssociationKind,
    CausalRelation,
    CausalRelationKind,
    EffectClass,
    EffectEventTrace,
    EffectEvidenceStrength,
    EffectObjectObservation,
    EffectObservationStatus,
    EffectPathEvidence,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EffectTraceProvenance,
    EntryLifecycleEvent,
    EntryLifecycleKind,
    EntryType,
    EvidenceSourceIdentity,
    FilesystemEffectEvent,
    LifecycleStatus,
    MonotonicInterval,
    ObjectSnapshot,
    ObjectType,
    ObservationFailure,
    ObservationFailureKind,
    ObservedOperationType,
    OperationOutcome,
    RawEvidenceReference,
    RebindingCreationKind,
    RebindingDependencyKind,
    SnapshotPhase,
    StateSnapshot,
    canonical_json,
)

V2_SOURCE_ID = "synthetic-v2-source"
V2_RAW_SHA256 = "a" * 64
V3_SOURCE = EvidenceSourceIdentity(
    "synthetic-v3-source",
    "synthetic-branch-continuation-fixture",
    PROTOCOL_VERSION,
    "b" * 64,
)


def _object(path: str, ino: int, *, kind: ObjectType = ObjectType.REGULAR) -> ObjectSnapshot:
    return ObjectSnapshot(
        path,
        kind,
        7,
        ino,
        1,
        0o777 if kind == ObjectType.SYMLINK else 0o644,
        0 if kind != ObjectType.REGULAR else 4,
        1000,
        1000,
        ino * 10,
        ino * 10,
        "source" if kind == ObjectType.SYMLINK else None,
        "c" * 64 if kind == ObjectType.REGULAR else None,
    )


def _observation(obj: ObjectSnapshot | None) -> EffectObjectObservation:
    return EffectObjectObservation(
        EffectObservationStatus.ABSENT if obj is None else EffectObservationStatus.PRESENT,
        obj,
    )


def _event(
    start: int,
    completion: int,
    entry: ArchiveEntryReference,
    effect_class: EffectClass,
    operation: ObservedOperationType,
    paths: tuple[str, ...],
    evidence: tuple[EffectPathEvidence, ...],
    correlation: str,
    *,
    outcome: OperationOutcome = OperationOutcome.SUCCEEDED,
    strength: EffectEvidenceStrength = EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
) -> FilesystemEffectEvent:
    return FilesystemEffectEvent(
        start,
        completion,
        entry,
        AssociationKind.ASYNC_CONTEXT,
        effect_class,
        strength,
        paths,
        operation,
        MonotonicInterval(start * 10, start * 10 + 1),
        MonotonicInterval(completion * 10, completion * 10 + 1),
        outcome,
        evidence,
        V2_SOURCE_ID,
        correlation,
        RawEvidenceReference(V2_SOURCE_ID, f"{correlation}-completion"),
    )


def _edge(
    predecessor: int,
    successor: int,
    kind: CausalRelationKind,
    token: str,
) -> CausalRelation:
    return CausalRelation(
        predecessor,
        successor,
        kind,
        V2_SOURCE_ID,
        token,
        RawEvidenceReference(V2_SOURCE_ID, f"edge-{predecessor}-{successor}-{kind.value}"),
    )


def _trace(
    *,
    creation_path: str = "extract/p",
    same_entry: bool = True,
    with_v2_dependency: bool = True,
    removal_outcome: OperationOutcome = OperationOutcome.SUCCEEDED,
    creation_outcome: OperationOutcome = OperationOutcome.SUCCEEDED,
    creation_before_absent: bool = True,
    created_ino: int = 22,
    intervening_binding: bool = False,
    termination: EffectTargetTermination = EffectTargetTermination.SUCCESS,
) -> EffectEventTrace:
    removal_entry = ArchiveEntryReference(0, "p", EntryType.REGULAR, None)
    creation_entry = (
        removal_entry if same_entry else ArchiveEntryReference(1, "q", EntryType.REGULAR, None)
    )
    entries = (removal_entry,) if same_entry else (removal_entry, creation_entry)
    lifecycle = tuple(
        EntryLifecycleEvent(
            index,
            entry,
            EntryLifecycleKind.READ,
            MonotonicInterval(index * 10, index * 10 + 1),
            LifecycleStatus.SUCCEEDED,
            None,
            V2_SOURCE_ID,
            RawEvidenceReference(V2_SOURCE_ID, f"entry-{index}-read"),
        )
        for index, entry in enumerate(entries)
    )
    removal_start = len(lifecycle)
    removal_completion = removal_start + 1
    creation_start = removal_start + (4 if intervening_binding else 2)
    creation_completion = creation_start + 1
    destination = "extract/p"
    old = _object(destination, 11)
    removal = _event(
        removal_start,
        removal_completion,
        removal_entry,
        EffectClass.NAMESPACE_REMOVAL,
        ObservedOperationType.UNLINK,
        (destination,),
        (EffectPathEvidence(destination, _observation(old), _observation(None)),),
        "remove-p",
        outcome=removal_outcome,
    )
    created = _object(creation_path, created_ino)
    creation_before = None if creation_before_absent else _object(creation_path, 19)
    creation = _event(
        creation_start,
        creation_completion,
        creation_entry,
        EffectClass.NAMESPACE_CREATION,
        ObservedOperationType.OPEN,
        (creation_path,),
        (
            EffectPathEvidence(
                creation_path,
                _observation(creation_before),
                _observation(created),
            ),
        ),
        "create-p",
        outcome=creation_outcome,
    )
    effects = [removal]
    edges = [
        _edge(
            removal.start_sequence,
            removal.completion_sequence,
            CausalRelationKind.OPERATION_INTERVAL,
            removal.correlation_id,
        )
    ]
    if intervening_binding:
        inter_start, inter_completion = removal_completion + 1, removal_completion + 2
        intermediate = _event(
            inter_start,
            inter_completion,
            removal_entry,
            EffectClass.NAMESPACE_CREATION,
            ObservedOperationType.OPEN,
            (destination,),
            (
                EffectPathEvidence(
                    destination,
                    _observation(None),
                    _observation(_object(destination, 17)),
                ),
            ),
            "intervening-bind",
        )
        effects.append(intermediate)
        edges.append(
            _edge(
                intermediate.start_sequence,
                intermediate.completion_sequence,
                CausalRelationKind.OPERATION_INTERVAL,
                intermediate.correlation_id,
            )
        )
    effects.append(creation)
    edges.append(
        _edge(
            creation.start_sequence,
            creation.completion_sequence,
            CausalRelationKind.OPERATION_INTERVAL,
            creation.correlation_id,
        )
    )
    if with_v2_dependency:
        edges.append(
            _edge(
                removal.completion_sequence,
                creation.start_sequence,
                CausalRelationKind.EXPLICIT_OPERATION_DEPENDENCY,
                "v2-explicit-dependency",
            )
        )
    sentinel = _object("outside/sentinel", 99)
    before = StateSnapshot(
        "/var/lib/inodefence/rebinding-v3",
        SnapshotPhase.BEFORE,
        (sentinel,),
        ("outside/sentinel",),
    )
    after = replace(before, phase=SnapshotPhase.AFTER)
    source = EvidenceSourceIdentity(V2_SOURCE_ID, "synthetic-v2", "2.0.0", "d" * 64)
    last = creation.completion_sequence
    return EffectEventTrace(
        before,
        entries,
        lifecycle,
        tuple(effects),
        tuple(edges),
        (),
        after,
        EffectStreamCompleteness.COMPLETE,
        termination,
        EffectTraceProvenance(
            "entry-effect-trace-v2",
            "2.0.0",
            "synthetic-rebinding-v3",
            (source,),
            64,
            (EntryLifecycleKind.READ,),
            V2_RAW_SHA256,
        ),
        last,
        last,
        last,
        (),
    )


def _object_record(obj: ObjectSnapshot | None) -> dict[str, object]:
    if obj is None:
        return {"status": "absent", "object": None}
    return {
        "status": "present",
        "object": {
            "path": obj.path,
            "object_type": obj.object_type.value,
            "st_dev": obj.st_dev,
            "st_ino": obj.st_ino,
            "st_nlink": obj.st_nlink,
            "mode": obj.mode,
            "size": obj.size,
            "uid": obj.uid,
            "gid": obj.gid,
            "mtime_ns": obj.mtime_ns,
            "ctime_ns": obj.ctime_ns,
            "symlink_target": obj.symlink_target,
            "content_digest": obj.content_digest,
        },
    }


def _entry_record(entry: ArchiveEntryReference) -> dict[str, object]:
    return {
        "ordinal": entry.entry_index,
        "path": entry.path,
        "type": entry.entry_type.value,
        "link_target": entry.link_target,
    }


def _endpoint_record(
    event: FilesystemEffectEvent, role: str, dependency_id: str
) -> dict[str, object]:
    return {
        "record_type": "operation_endpoint",
        "record_id": f"v3-{role}",
        "dependency_id": dependency_id,
        "role": role,
        "entry": _entry_record(event.entry),
        "association": event.association.value,
        "effect_class": event.effect_class.value,
        "evidence_strength": event.evidence_strength.value,
        "affected_paths": list(event.affected_paths),
        "operation": event.operation.value,
        "start_sequence": event.start_sequence,
        "completion_sequence": event.completion_sequence,
        "start_observation": {
            "started_ns": event.start_observation.started_ns,
            "finished_ns": event.start_observation.finished_ns,
        },
        "completion_observation": {
            "started_ns": event.completion_observation.started_ns,
            "finished_ns": event.completion_observation.finished_ns,
        },
        "outcome": event.outcome.value,
        "object_evidence": [
            {
                "path": item.path,
                "before": _object_record(item.before.object),
                "after": _object_record(item.after.object),
            }
            for item in event.object_evidence
        ],
        "v2_source_id": event.source_id,
        "v2_raw_record_id": event.raw_evidence.record_id,
        "correlation_id": event.correlation_id,
    }


def _raw_evidence(trace: EffectEventTrace) -> bytes:
    removal = next(event for event in trace.effect_events if event.correlation_id == "remove-p")
    creation = next(event for event in trace.effect_events if event.correlation_id == "create-p")
    dependency_id = "dependency-0"
    records = [
        _endpoint_record(removal, "removal", dependency_id),
        _endpoint_record(creation, "creation", dependency_id),
        {
            "record_type": "operation_dependency",
            "record_id": "v3-dependency",
            "dependency_id": dependency_id,
            "predecessor_correlation_id": removal.correlation_id,
            "successor_correlation_id": creation.correlation_id,
            "predecessor_completion_sequence": removal.completion_sequence,
            "successor_start_sequence": creation.start_sequence,
            "kind": RebindingDependencyKind.PRODUCER_BRANCH_CONTINUATION.value,
            "evidence_token": "synthetic-branch-0",
        },
    ]
    records_bytes = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    envelope = {
        "format": PROTOCOL_ID,
        "schema_version": 3,
        "protocol_version": PROTOCOL_VERSION,
        "source": {
            "source_id": V3_SOURCE.source_id,
            "mechanism": V3_SOURCE.mechanism,
            "version": V3_SOURCE.version,
            "source_sha256": V3_SOURCE.source_sha256,
        },
        "v2_raw_stream_sha256": trace.provenance.raw_stream_sha256,
        "records": records,
        "terminal": {
            "record_count": len(records),
            "records_sha256": sha256(records_bytes).hexdigest(),
            "complete": True,
        },
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _verified(trace: EffectEventTrace):
    raw = _raw_evidence(trace)
    return reconstruct_rebinding_evidence(raw, sha256(raw).hexdigest(), trace, V3_SOURCE)


def test_positive_raw_fixture_reconstructs_additive_sequence_and_key() -> None:
    trace = _trace()
    verified = _verified(trace)
    projection = effect_feedback_projection_v3(trace, verified.dependencies)

    assert len(verified.dependencies) == len(verified.sequences) == 1
    sequence = verified.sequences[0]
    assert sequence.destination_path == "extract/p"
    assert sequence.removal.effect_class == EffectClass.NAMESPACE_REMOVAL
    assert sequence.creation.effect_class == EffectClass.NAMESPACE_CREATION
    assert sequence.removal_destination_evidence.after.status == EffectObservationStatus.ABSENT
    assert sequence.creation_destination_evidence.before.status == EffectObservationStatus.ABSENT
    assert projection.v2_keys == effect_feedback_keys(trace)
    assert len(projection.rebinding_keys) == 1
    encoded = canonical_json(projection.rebinding_keys[0])
    for raw_value in ("extract/p", "remove-p", "create-p", "synthetic-branch-0", "st_ino"):
        assert raw_value not in encoded


def test_v3_distinguishes_equal_v2_feedback_without_adding_paths_to_key() -> None:
    same_path = _trace()
    different_path = _trace(creation_path="extract/q")
    same_verified = _verified(same_path)
    different_verified = _verified(different_path)
    same_projection = effect_feedback_projection_v3(same_path, same_verified.dependencies)
    different_projection = effect_feedback_projection_v3(
        different_path, different_verified.dependencies
    )

    assert same_projection.v2_keys == different_projection.v2_keys
    assert len(same_projection.rebinding_keys) == 1
    assert different_projection.rebinding_keys == ()


def test_symlink_and_hardlink_destination_roles_are_explicit() -> None:
    base = _trace()
    original = next(event for event in base.effect_events if event.correlation_id == "create-p")
    symlink_object = _object("extract/p", 31, kind=ObjectType.SYMLINK)
    symlink = replace(
        original,
        effect_class=EffectClass.SYMLINK_CREATION,
        operation=ObservedOperationType.SYMLINK,
        object_evidence=(
            EffectPathEvidence("extract/p", _observation(None), _observation(symlink_object)),
        ),
    )
    symlink_trace = replace(
        base,
        effect_events=tuple(
            symlink if event.correlation_id == original.correlation_id else event
            for event in base.effect_events
        ),
    )
    assert _verified(symlink_trace).sequences[0].creation_kind == RebindingCreationKind.SYMLINK

    source_before = _object("extract/source", 41)
    source_after = replace(source_before, st_nlink=2)
    destination_after = replace(source_after, path="extract/p")
    hardlink = replace(
        original,
        effect_class=EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
        evidence_strength=EffectEvidenceStrength.IDENTITY_VERIFIED,
        affected_paths=("extract/source", "extract/p"),
        operation=ObservedOperationType.LINK,
        object_evidence=(
            EffectPathEvidence(
                "extract/source", _observation(source_before), _observation(source_after)
            ),
            EffectPathEvidence("extract/p", _observation(None), _observation(destination_after)),
        ),
    )
    hardlink_trace = replace(
        base,
        effect_events=tuple(
            hardlink if event.correlation_id == original.correlation_id else event
            for event in base.effect_events
        ),
    )
    hardlink_sequence = _verified(hardlink_trace).sequences[0]
    assert hardlink_sequence.creation_kind == RebindingCreationKind.HARDLINK_RELATION
    assert hardlink_sequence.hardlink_source_path == "extract/source"


@pytest.mark.parametrize(
    ("trace", "expected"),
    (
        (_trace(with_v2_dependency=False), 1),
        (_trace(same_entry=False), 0),
        (_trace(creation_path="extract/q"), 0),
        (_trace(removal_outcome=OperationOutcome.OTHER_ERROR), 0),
        (_trace(creation_outcome=OperationOutcome.OTHER_ERROR), 0),
        (_trace(creation_before_absent=False), 0),
        (_trace(intervening_binding=True), 0),
        (_trace(created_ino=11), 1),
        (_trace(created_ino=222), 1),
    ),
)
def test_composite_requires_all_semantic_predicates(trace: EffectEventTrace, expected: int) -> None:
    verified = _verified(trace)
    assert len(verified.sequences) == expected


def test_incomplete_trace_and_same_inode_truncation_do_not_form_rebinding() -> None:
    valid = _trace()
    incomplete = replace(
        valid,
        completeness=EffectStreamCompleteness.INCOMPLETE,
        observation_failures=(
            ObservationFailure(
                ObservationFailureKind.EVENT_LOSS,
                "synthetic missing record",
                V2_SOURCE_ID,
                3,
            ),
        ),
    )
    dependencies = _verified(valid).dependencies
    rejected = replace(valid, termination=EffectTargetTermination.REJECTED)
    timed_out = replace(valid, termination=EffectTargetTermination.TIMED_OUT)
    invalid = replace(incomplete, completeness=EffectStreamCompleteness.INVALID)
    assert derive_namespace_rebinding_sequences(incomplete, dependencies) == ()
    assert derive_namespace_rebinding_sequences(invalid, dependencies) == ()
    assert derive_namespace_rebinding_sequences(rejected, dependencies) == ()
    assert derive_namespace_rebinding_sequences(timed_out, dependencies) == ()
    assert derive_namespace_rebinding_sequences(valid, ()) == ()
    for trace in (incomplete, invalid, rejected, timed_out):
        raw = _raw_evidence(trace)
        with pytest.raises(ValueError, match="complete valid successful v2 trace"):
            reconstruct_rebinding_evidence(raw, sha256(raw).hexdigest(), trace, V3_SOURCE)

    removal = valid.effect_events[0]
    removal_only = replace(
        valid,
        effect_events=(removal,),
        causal_relations=(valid.causal_relations[0],),
        last_produced_sequence=removal.completion_sequence,
        last_flushed_sequence=removal.completion_sequence,
        flush_acknowledged_sequence=removal.completion_sequence,
    )
    assert removal_only.integrity_valid
    assert derive_namespace_rebinding_sequences(removal_only, ()) == ()
    with pytest.raises(ValueError, match="unknown operation"):
        derive_namespace_rebinding_sequences(removal_only, dependencies)

    entry = valid.archive_entries[0]
    before = _object("extract/p", 11)
    after = replace(before, size=0, content_digest="e" * 64)
    truncation = _event(
        1,
        2,
        entry,
        EffectClass.TRUNCATION,
        ObservedOperationType.OPEN,
        ("extract/p",),
        (EffectPathEvidence("extract/p", _observation(before), _observation(after)),),
        "truncate-p",
    )
    truncation_trace = replace(
        valid,
        effect_events=(truncation,),
        causal_relations=(
            _edge(1, 2, CausalRelationKind.OPERATION_INTERVAL, truncation.correlation_id),
        ),
        last_produced_sequence=2,
        last_flushed_sequence=2,
        flush_acknowledged_sequence=2,
    )
    assert derive_namespace_rebinding_sequences(truncation_trace, ()) == ()


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda value: value.__setitem__("v2_raw_stream_sha256", "f" * 64),
            "different v2 stream",
        ),
        (
            lambda value: value["records"][0].__setitem__("correlation_id", "tampered"),
            "differs from the validated v2 event",
        ),
        (
            lambda value: value["records"][1]["object_evidence"][0]["before"].__setitem__(
                "status", "not_observed"
            ),
            "differs from the validated v2 event",
        ),
        (
            lambda value: value["source"].__setitem__("source_sha256", "f" * 64),
            "differs from the pinned expected source",
        ),
        (
            lambda value: value["records"][1].__setitem__("completion_sequence", 5),
            "differs from the validated v2 event",
        ),
    ),
)
def test_reader_rejects_tampered_raw_provenance_and_endpoint_evidence(mutate, message) -> None:
    trace = _trace()
    value = json.loads(_raw_evidence(trace))
    mutate(value)
    records_bytes = json.dumps(
        value["records"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    value["terminal"]["records_sha256"] = sha256(records_bytes).hexdigest()
    raw = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()

    with pytest.raises(ValueError, match=message):
        reconstruct_rebinding_evidence(raw, sha256(raw).hexdigest(), trace, V3_SOURCE)


def test_reader_rejects_rehashed_dependency_forgery_against_trusted_manifest() -> None:
    trace = _trace()
    original = _raw_evidence(trace)
    value = json.loads(original)
    value["records"][2]["evidence_token"] = "forged-branch-token"
    records_bytes = json.dumps(
        value["records"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    value["terminal"]["records_sha256"] = sha256(records_bytes).hexdigest()
    forged = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()

    with pytest.raises(ValueError, match="differs from the trusted manifest"):
        reconstruct_rebinding_evidence(forged, sha256(original).hexdigest(), trace, V3_SOURCE)


def test_reader_rejects_record_digest_tampering_before_derivation() -> None:
    trace = _trace()
    value = json.loads(_raw_evidence(trace))
    value["records"][2]["evidence_token"] = "tampered-without-terminal-update"
    raw = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()

    with pytest.raises(ValueError, match="count/digest/completeness"):
        reconstruct_rebinding_evidence(raw, sha256(raw).hexdigest(), trace, V3_SOURCE)


def test_reader_rejects_noninteger_terminal_count() -> None:
    trace = _trace()
    value = json.loads(_raw_evidence(trace))
    value["terminal"]["record_count"] = 3.0
    raw = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()

    with pytest.raises(ValueError, match="terminal record count must be an integer"):
        reconstruct_rebinding_evidence(raw, sha256(raw).hexdigest(), trace, V3_SOURCE)


def test_composite_constructor_rejects_creation_kind_drift() -> None:
    sequence = _verified(_trace()).sequences[0]
    with pytest.raises(ValueError, match="creation kind must match"):
        replace(sequence, creation_kind=RebindingCreationKind.SYMLINK)

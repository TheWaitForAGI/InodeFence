"""Strict independent reader for additive namespace-rebinding v3 evidence."""

import json
from dataclasses import dataclass
from hashlib import sha256

from inodefence.feedback import derive_namespace_rebinding_sequences
from inodefence.model import (
    ArchiveEntryReference,
    AssociationKind,
    EffectClass,
    EffectEventTrace,
    EffectEvidenceStrength,
    EffectObjectObservation,
    EffectObservationStatus,
    EffectPathEvidence,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EntryType,
    EvidenceSourceIdentity,
    FilesystemEffectEvent,
    MonotonicInterval,
    NamespaceRebindingSequence,
    ObjectSnapshot,
    ObjectType,
    ObservedOperationType,
    OperationOutcome,
    RawEvidenceReference,
    RebindingDependencyKind,
    RebindingOperationDependency,
)
from inodefence.model._validation import validate_sha256

PROTOCOL_ID = "inodefence-namespace-rebinding-sequence"
PROTOCOL_VERSION = "3.0.0"
MAX_RAW_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class VerifiedRebindingEvidence:
    raw_sha256: str
    source: EvidenceSourceIdentity
    dependencies: tuple[RebindingOperationDependency, ...]
    sequences: tuple[NamespaceRebindingSequence, ...]


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("v3 raw evidence contains a duplicate JSON key")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _strict_json(raw: bytes) -> object:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_RAW_BYTES:
        raise ValueError("v3 raw evidence must be nonempty bounded bytes")
    if not raw.endswith(b"\n") or b"\n" in raw[:-1]:
        raise ValueError("v3 raw evidence must be one LF-terminated frame")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_no_duplicate_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("v3 raw evidence is not strict JSON") from error


def _integer(value: object, field: str, *, nonnegative: bool = True) -> int:
    if type(value) is not int or (nonnegative and value < 0):
        raise ValueError(f"v3 raw {field} must be an integer")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"v3 raw {field} must be nonempty text")
    return value


def _entry(value: object) -> ArchiveEntryReference:
    fields = {"ordinal", "path", "type", "link_target"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("v3 raw entry fields differ from schema")
    return ArchiveEntryReference(
        _integer(value["ordinal"], "entry ordinal"),
        _text(value["path"], "entry path"),
        EntryType(value["type"]),
        value["link_target"],
    )


def _interval(value: object) -> MonotonicInterval:
    if not isinstance(value, dict) or set(value) != {"started_ns", "finished_ns"}:
        raise ValueError("v3 raw observation interval fields differ from schema")
    return MonotonicInterval(
        _integer(value["started_ns"], "started_ns"),
        _integer(value["finished_ns"], "finished_ns"),
    )


def _object(value: object, path: str) -> ObjectSnapshot:
    fields = {
        "path",
        "object_type",
        "st_dev",
        "st_ino",
        "st_nlink",
        "mode",
        "size",
        "uid",
        "gid",
        "mtime_ns",
        "ctime_ns",
        "symlink_target",
        "content_digest",
    }
    if not isinstance(value, dict) or set(value) != fields or value["path"] != path:
        raise ValueError("v3 raw object fields or path differ from schema")
    return ObjectSnapshot(
        path,
        ObjectType(value["object_type"]),
        _integer(value["st_dev"], "st_dev"),
        _integer(value["st_ino"], "st_ino"),
        _integer(value["st_nlink"], "st_nlink"),
        _integer(value["mode"], "mode"),
        _integer(value["size"], "size"),
        _integer(value["uid"], "uid"),
        _integer(value["gid"], "gid"),
        _integer(value["mtime_ns"], "mtime_ns", nonnegative=False),
        _integer(value["ctime_ns"], "ctime_ns", nonnegative=False),
        value["symlink_target"],
        value["content_digest"],
    )


def _observation(value: object, path: str) -> EffectObjectObservation:
    if not isinstance(value, dict) or set(value) != {"status", "object"}:
        raise ValueError("v3 raw object observation fields differ from schema")
    status = EffectObservationStatus(value["status"])
    if status == EffectObservationStatus.PRESENT:
        return EffectObjectObservation(status, _object(value["object"], path))
    if value["object"] is not None:
        raise ValueError("v3 raw non-present observation carries an object")
    return EffectObjectObservation(status, None)


def _path_evidence(value: object) -> EffectPathEvidence:
    if not isinstance(value, dict) or set(value) != {"path", "before", "after"}:
        raise ValueError("v3 raw path evidence fields differ from schema")
    path = _text(value["path"], "evidence path")
    return EffectPathEvidence(
        path,
        _observation(value["before"], path),
        _observation(value["after"], path),
    )


_ENDPOINT_FIELDS = {
    "record_type",
    "record_id",
    "dependency_id",
    "role",
    "entry",
    "association",
    "effect_class",
    "evidence_strength",
    "affected_paths",
    "operation",
    "start_sequence",
    "completion_sequence",
    "start_observation",
    "completion_observation",
    "outcome",
    "object_evidence",
    "v2_source_id",
    "v2_raw_record_id",
    "correlation_id",
}


def _endpoint(value: object) -> tuple[str, str, FilesystemEffectEvent]:
    if not isinstance(value, dict) or set(value) != _ENDPOINT_FIELDS:
        raise ValueError("v3 raw operation endpoint fields differ from schema")
    if value["record_type"] != "operation_endpoint" or value["role"] not in (
        "removal",
        "creation",
    ):
        raise ValueError("v3 raw operation endpoint type or role is invalid")
    affected = value["affected_paths"]
    evidence = value["object_evidence"]
    if not isinstance(affected, list) or not isinstance(evidence, list):
        raise ValueError("v3 raw endpoint paths/evidence must be arrays")
    event = FilesystemEffectEvent(
        _integer(value["start_sequence"], "start sequence"),
        _integer(value["completion_sequence"], "completion sequence"),
        _entry(value["entry"]),
        AssociationKind(value["association"]),
        EffectClass(value["effect_class"]),
        EffectEvidenceStrength(value["evidence_strength"]),
        tuple(_text(path, "affected path") for path in affected),
        ObservedOperationType(value["operation"]),
        _interval(value["start_observation"]),
        _interval(value["completion_observation"]),
        OperationOutcome(value["outcome"]),
        tuple(_path_evidence(item) for item in evidence),
        _text(value["v2_source_id"], "v2 source ID"),
        _text(value["correlation_id"], "correlation ID"),
        RawEvidenceReference(
            _text(value["v2_source_id"], "v2 source ID"),
            _text(value["v2_raw_record_id"], "v2 raw record ID"),
        ),
    )
    return (
        _text(value["dependency_id"], "dependency ID"),
        value["role"],
        event,
    )


_DEPENDENCY_FIELDS = {
    "record_type",
    "record_id",
    "dependency_id",
    "predecessor_correlation_id",
    "successor_correlation_id",
    "predecessor_completion_sequence",
    "successor_start_sequence",
    "kind",
    "evidence_token",
}


def reconstruct_rebinding_evidence(
    raw: bytes,
    expected_raw_sha256: str,
    trace: EffectEventTrace,
    expected_source: EvidenceSourceIdentity,
) -> VerifiedRebindingEvidence:
    """Cross-check raw v3 endpoints and derive composites without trusting labels."""
    if not isinstance(trace, EffectEventTrace) or not isinstance(
        expected_source, EvidenceSourceIdentity
    ):
        raise ValueError("v3 reconstruction requires a v2 trace and expected source")
    if (
        not trace.integrity_valid
        or trace.completeness != EffectStreamCompleteness.COMPLETE
        or trace.termination != EffectTargetTermination.SUCCESS
    ):
        raise ValueError("v3 reconstruction requires a complete valid successful v2 trace")
    if not isinstance(raw, bytes):
        raise ValueError("v3 raw evidence must be bytes")
    validate_sha256(expected_raw_sha256)
    raw_digest = sha256(raw).hexdigest()
    if raw_digest != expected_raw_sha256:
        raise ValueError("v3 raw evidence digest differs from the trusted manifest")
    envelope = _strict_json(raw)
    fields = {
        "format",
        "schema_version",
        "protocol_version",
        "source",
        "v2_raw_stream_sha256",
        "records",
        "terminal",
    }
    if not isinstance(envelope, dict) or set(envelope) != fields:
        raise ValueError("v3 raw envelope fields differ from schema")
    if (
        envelope["format"] != PROTOCOL_ID
        or envelope["schema_version"] != 3
        or envelope["protocol_version"] != PROTOCOL_VERSION
    ):
        raise ValueError("v3 raw protocol identity differs from the reader")
    source = envelope["source"]
    expected_source_record = {
        "source_id": expected_source.source_id,
        "mechanism": expected_source.mechanism,
        "version": expected_source.version,
        "source_sha256": expected_source.source_sha256,
    }
    if source != expected_source_record or expected_source.version != PROTOCOL_VERSION:
        raise ValueError("v3 raw source differs from the pinned expected source")
    v2_digest = envelope["v2_raw_stream_sha256"]
    validate_sha256(v2_digest)
    if v2_digest != trace.provenance.raw_stream_sha256:
        raise ValueError("v3 raw evidence is bound to a different v2 stream")

    records, terminal = envelope["records"], envelope["terminal"]
    if (
        not isinstance(records, list)
        or not isinstance(terminal, dict)
        or set(terminal)
        != {
            "record_count",
            "records_sha256",
            "complete",
        }
    ):
        raise ValueError("v3 raw records or terminal fields differ from schema")
    if len(records) > trace.provenance.event_bound * 3:
        raise ValueError("v3 raw record count exceeds the trace-derived bound")
    canonical_records = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if (
        _integer(terminal["record_count"], "terminal record count") != len(records)
        or terminal["records_sha256"] != sha256(canonical_records).hexdigest()
        or terminal["complete"] is not True
    ):
        raise ValueError("v3 raw count/digest/completeness verification failed")

    endpoints: dict[str, dict[str, FilesystemEffectEvent]] = {}
    dependency_records: dict[str, dict[str, object]] = {}
    record_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("v3 raw record must be an object")
        record_id = _text(record.get("record_id"), "record ID")
        if record_id in record_ids:
            raise ValueError("v3 raw record IDs must be unique")
        record_ids.add(record_id)
        if record.get("record_type") == "operation_endpoint":
            dependency_id, role, event = _endpoint(record)
            roles = endpoints.setdefault(dependency_id, {})
            if role in roles:
                raise ValueError("v3 raw dependency repeats an endpoint role")
            roles[role] = event
        elif record.get("record_type") == "operation_dependency":
            if set(record) != _DEPENDENCY_FIELDS:
                raise ValueError("v3 raw dependency fields differ from schema")
            dependency_id = _text(record["dependency_id"], "dependency ID")
            if dependency_id in dependency_records:
                raise ValueError("v3 raw dependency ID is duplicated")
            dependency_records[dependency_id] = record
        else:
            raise ValueError("v3 raw record type is unsupported")
    if set(endpoints) != set(dependency_records):
        raise ValueError("v3 raw endpoints and dependency records do not join exactly")

    trace_events = {event.correlation_id: event for event in trace.effect_events}
    if len(trace_events) != len(trace.effect_events):
        raise ValueError("validated v2 events must have unique correlation IDs")
    dependencies: list[RebindingOperationDependency] = []
    for dependency_id in sorted(dependency_records):
        roles = endpoints[dependency_id]
        if set(roles) != {"removal", "creation"}:
            raise ValueError("v3 raw dependency requires removal and creation endpoints")
        removal, creation = roles["removal"], roles["creation"]
        if removal.effect_class != EffectClass.NAMESPACE_REMOVAL or creation.effect_class not in {
            EffectClass.NAMESPACE_CREATION,
            EffectClass.SYMLINK_CREATION,
            EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
        }:
            raise ValueError("v3 raw endpoint role differs from its effect class")
        if (
            trace_events.get(removal.correlation_id) != removal
            or trace_events.get(creation.correlation_id) != creation
        ):
            raise ValueError("v3 raw endpoint differs from the validated v2 event")
        record = dependency_records[dependency_id]
        dependency = RebindingOperationDependency(
            dependency_id,
            _text(record["predecessor_correlation_id"], "predecessor correlation ID"),
            _text(record["successor_correlation_id"], "successor correlation ID"),
            _integer(record["predecessor_completion_sequence"], "predecessor completion sequence"),
            _integer(record["successor_start_sequence"], "successor start sequence"),
            RebindingDependencyKind(record["kind"]),
            _text(record["evidence_token"], "dependency evidence token"),
            expected_source.source_id,
            v2_digest,
            raw_digest,
            RawEvidenceReference(
                expected_source.source_id,
                _text(record["record_id"], "record ID"),
            ),
        )
        if (
            dependency.predecessor_correlation_id != removal.correlation_id
            or dependency.successor_correlation_id != creation.correlation_id
            or dependency.predecessor_completion_sequence != removal.completion_sequence
            or dependency.successor_start_sequence != creation.start_sequence
        ):
            raise ValueError("v3 raw dependency differs from its endpoint records")
        dependencies.append(dependency)

    dependency_tuple = tuple(dependencies)
    return VerifiedRebindingEvidence(
        raw_digest,
        expected_source,
        dependency_tuple,
        derive_namespace_rebinding_sequences(trace, dependency_tuple),
    )

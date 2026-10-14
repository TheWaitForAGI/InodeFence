"""Raw export and independent verification for native v2 effect observations."""

import json
import re
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from hashlib import sha256
from pathlib import Path
from typing import ClassVar

from inodefence.effect_pipeline import NativeEffectRun
from inodefence.feedback import effect_feedback_keys
from inodefence.model import (
    ArchiveEntryReference,
    AssociationKind,
    CausalRelation,
    CausalRelationKind,
    EffectClass,
    EffectEventTrace,
    EffectEvidenceStrength,
    EffectFeedbackKey,
    EffectObjectObservation,
    EffectObservationStatus,
    EffectPathEvidence,
    EffectRunResult,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EffectTraceProvenance,
    EntryLifecycleEvent,
    EntryLifecycleKind,
    EntryType,
    EvidenceSourceIdentity,
    ExecutionStatus,
    FilesystemEffectEvent,
    LifecycleStatus,
    MonotonicInterval,
    ObjectSnapshot,
    ObjectType,
    ObservedOperationType,
    OperationOutcome,
    RawEvidenceReference,
)
from inodefence.model.effect import effect_is_realized

from .encoding import read_json
from .failure import ArtifactReference
from .storage import publish_bytes, read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file, verify_run


@dataclass(frozen=True, slots=True)
class NativeEffectEvidenceManifest:
    """Completion marker for immutable raw producer and typed result bytes."""

    serialization_schema: ClassVar[int] = 1

    raw_stream: ArtifactReference
    result: ArtifactReference
    case_id: str
    raw_stream_sha256: str
    producer_source_sha256: str
    trace_schema: int = 2
    result_schema: int = EffectRunResult.serialization_schema
    classification: str = "raw-native-effect-observation-v2"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.raw_stream, ArtifactReference)
            or self.raw_stream.name != "raw-stream.json"
            or not isinstance(self.result, ArtifactReference)
            or self.result.name != "result.json"
        ):
            raise ValueError("native effect manifest artifact names are fixed")
        for value in (self.case_id, self.raw_stream_sha256, self.producer_source_sha256):
            _digest(value)
        if self.trace_schema != 2 or self.result_schema != EffectRunResult.serialization_schema:
            raise ValueError("unsupported native effect evidence schema")
        if self.classification != "raw-native-effect-observation-v2":
            raise ValueError("unsupported native effect evidence classification")


def export_native_effect_run(run: NativeEffectRun, directory: Path) -> str:
    """Publish exact raw bytes and derived typed evidence, then the manifest."""
    if not isinstance(run, NativeEffectRun):
        raise ValueError("native effect export requires a NativeEffectRun")
    raw_digest = sha256(run.raw_stream).hexdigest()
    trace = run.result.trace
    if trace.provenance.raw_stream_sha256 != raw_digest:
        raise ValueError("typed trace raw-stream binding differs from producer bytes")
    if run.archive_sha256 != run.result.base_result.archive_sha256:
        raise ValueError("raw archive identity differs from RunResult")
    sources = trace.provenance.sources
    if len(sources) != 1:
        raise ValueError("native node-tar trace requires one producer source")
    directory.mkdir()
    sync_directory(directory.parent)
    raw_file_digest = publish_bytes(directory / "raw-stream.json", run.raw_stream)
    result_digest = write_record(directory / "result.json", run.result)
    manifest = NativeEffectEvidenceManifest(
        ArtifactReference("raw-stream.json", raw_file_digest),
        ArtifactReference("result.json", result_digest),
        run.result.base_result.case.case_id,
        raw_digest,
        sources[0].source_sha256,
    )
    return write_record(directory / "manifest.json", manifest)


@dataclass(frozen=True, slots=True)
class VerifiedNativeEffectEvidence:
    """Evidence returned only after raw reconstruction matches the stored trace."""

    result: EffectRunResult
    manifest: NativeEffectEvidenceManifest
    manifest_sha256: str
    raw_stream: bytes
    feedback_keys: tuple[EffectFeedbackKey, ...]


_PROTOCOL_ID = "inodefence-node-tar-effect-stream"
_PROTOCOL_VERSION = "2.0.0"
_SOURCE_ID = "node-tar-effect-worker-v2"
_NODE = "/usr/local/bin/node"
_WORKER = "/target/effect-producer.cjs"
_MODULE = "/target/node_modules/tar"
_LOCK = "/target/package-lock.json"
_NODE_TYPES = {
    "File": EntryType.REGULAR,
    "Directory": EntryType.DIRECTORY,
    "Link": EntryType.HARDLINK,
    "SymbolicLink": EntryType.SYMLINK,
}
_OPERATIONS = {
    "open": ObservedOperationType.OPEN,
    "write": ObservedOperationType.WRITE,
    "writev": ObservedOperationType.WRITEV,
    "close": ObservedOperationType.CLOSE,
    "mkdir": ObservedOperationType.MKDIR,
    "chmod": ObservedOperationType.CHMOD,
    "chown": ObservedOperationType.CHOWN,
    "utimes": ObservedOperationType.UTIMES,
    "futimes": ObservedOperationType.FUTIMES,
    "fchown": ObservedOperationType.FCHOWN,
    "unlink": ObservedOperationType.UNLINK,
    "rmdir": ObservedOperationType.RMDIR,
    "link": ObservedOperationType.LINK,
    "symlink": ObservedOperationType.SYMLINK,
    "rename": ObservedOperationType.RENAME,
    "rm": ObservedOperationType.REMOVE,
}
_LIFECYCLE = {
    "read": EntryLifecycleKind.READ,
    "effect_work_started": EntryLifecycleKind.EFFECT_WORK_STARTED,
    "effect_work_settled": EntryLifecycleKind.EFFECT_WORK_SETTLED,
}
_EFFECT_COVERAGE = {
    "namespace_creation": "supported_when_one correlated operation proves absent-to-present",
    "namespace_removal": "supported_when_one correlated operation proves present-to-absent",
    "namespace_replacement": "supported_when one correlated operation changes identity or type",
    "regular_file_content_modification": "supported by stable before/after content digests",
    "truncation": "supported by stable before/after regular-file sizes",
    "metadata_modification": "supported by stable before/after metadata fields",
    "symlink_creation": "supported by absent-to-symlink evidence and raw link text",
    "hardlink_identity_relation_creation": (
        "supported by source/destination lstat identity evidence"
    ),
    "identity_relation_removal": ("unsupported: no counterpart provenance for single-path removal"),
}


def _raw_interval(value: object) -> MonotonicInterval:
    if not isinstance(value, dict) or set(value) != {"started_ns", "finished_ns"}:
        raise ValueError("invalid raw observation interval")
    return MonotonicInterval(int(value["started_ns"]), int(value["finished_ns"]))


def _expected_entries(result: EffectRunResult) -> tuple[ArchiveEntryReference, ...]:
    return tuple(
        ArchiveEntryReference(index, entry.path, entry.entry_type, entry.link_target)
        for index, entry in enumerate(result.base_result.case.entries)
    )


def _raw_entry(value: object, expected: tuple[ArchiveEntryReference, ...]) -> ArchiveEntryReference:
    if not isinstance(value, dict) or set(value) != {
        "ordinal",
        "path",
        "type",
        "link_target",
    }:
        raise ValueError("invalid raw entry identity fields")
    ordinal = value["ordinal"]
    if type(ordinal) is not int or not 0 <= ordinal < len(expected):
        raise ValueError("raw entry ordinal is outside ArchiveCase")
    if not isinstance(value["type"], str) or value["type"] not in _NODE_TYPES:
        raise ValueError("unsupported raw entry type")
    entry = ArchiveEntryReference(
        ordinal,
        value["path"],
        _NODE_TYPES[value["type"]],
        value["link_target"],
    )
    if entry != expected[ordinal]:
        raise ValueError("raw entry identity differs from ArchiveCase")
    return entry


def _raw_object(value: object, path: str) -> ObjectSnapshot:
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
        raise ValueError("invalid raw object evidence")
    return ObjectSnapshot(
        path,
        ObjectType(value["object_type"]),
        int(value["st_dev"]),
        int(value["st_ino"]),
        int(value["st_nlink"]),
        value["mode"],
        int(value["size"]),
        int(value["uid"]),
        int(value["gid"]),
        int(value["mtime_ns"]),
        int(value["ctime_ns"]),
        value["symlink_target"],
        value["content_digest"],
    )


def _raw_observation(value: object, path: str) -> EffectObjectObservation:
    if not isinstance(value, dict) or set(value) != {"status", "object", "error"}:
        raise ValueError("invalid raw object-observation fields")
    status = EffectObservationStatus(value["status"])
    if status == EffectObservationStatus.PRESENT:
        return EffectObjectObservation(status, _raw_object(value["object"], path))
    if value["object"] is not None:
        raise ValueError("non-present raw observation carries an object")
    if value["error"] is not None and not isinstance(value["error"], dict):
        raise ValueError("raw observation error must be an object or null")
    return EffectObjectObservation(status, None)


def _raw_path_observations(
    value: object, paths: tuple[str, ...]
) -> tuple[EffectObjectObservation, ...]:
    if not isinstance(value, list) or len(value) != len(paths):
        raise ValueError("raw path-observation arity mismatch")
    observations = []
    for item, path in zip(value, paths, strict=True):
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "observation"}
            or item["path"] != path
        ):
            raise ValueError("raw path-observation order mismatch")
        observations.append(_raw_observation(item["observation"], path))
    return tuple(observations)


def _raw_outcome(success: object, error_code: object) -> OperationOutcome:
    if type(success) is not bool:
        raise ValueError("raw operation success must be boolean")
    if success:
        return OperationOutcome.SUCCEEDED
    code = error_code if isinstance(error_code, str) else ""
    return {
        "EEXIST": OperationOutcome.ALREADY_EXISTS,
        "ENOENT": OperationOutcome.NOT_FOUND,
        "EACCES": OperationOutcome.ACCESS_DENIED,
        "EPERM": OperationOutcome.ACCESS_DENIED,
        "EINVAL": OperationOutcome.INVALID,
    }.get(code, OperationOutcome.OTHER_ERROR)


def _independent_effect_candidate(
    operation: ObservedOperationType,
    paths: tuple[str, ...],
    evidence: tuple[EffectPathEvidence, ...],
) -> tuple[EffectClass, EffectEvidenceStrength, tuple[str, ...], tuple[EffectPathEvidence, ...]]:
    if operation == ObservedOperationType.LINK and len(paths) == 2:
        return (
            EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
            EffectEvidenceStrength.IDENTITY_VERIFIED,
            paths,
            evidence,
        )
    if operation == ObservedOperationType.SYMLINK and len(paths) == 1:
        return (
            EffectClass.SYMLINK_CREATION,
            EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
            paths,
            evidence,
        )
    selected_paths, selected_evidence = paths, evidence
    if operation == ObservedOperationType.RENAME and len(paths) == 2:
        selected_paths, selected_evidence = (paths[1],), (evidence[1],)
    if len(selected_paths) != 1:
        return (
            EffectClass.OPERATION_OBSERVED,
            EffectEvidenceStrength.OPERATION_RESULT,
            paths,
            evidence,
        )
    before = selected_evidence[0].before.object
    after = selected_evidence[0].after.object
    if before is None and after is not None:
        effect_class = EffectClass.NAMESPACE_CREATION
    elif before is not None and after is None:
        effect_class = EffectClass.NAMESPACE_REMOVAL
    elif (
        before is not None
        and after is not None
        and (before.identity != after.identity or before.object_type != after.object_type)
    ):
        effect_class = EffectClass.NAMESPACE_REPLACEMENT
    elif operation in (ObservedOperationType.WRITE, ObservedOperationType.WRITEV):
        effect_class = EffectClass.REGULAR_FILE_CONTENT_MODIFICATION
    elif operation == ObservedOperationType.OPEN:
        effect_class = EffectClass.TRUNCATION
    elif operation in (
        ObservedOperationType.CHMOD,
        ObservedOperationType.CHOWN,
        ObservedOperationType.UTIMES,
        ObservedOperationType.FUTIMES,
        ObservedOperationType.FCHOWN,
    ):
        effect_class = EffectClass.METADATA_MODIFICATION
    else:
        return (
            EffectClass.OPERATION_OBSERVED,
            EffectEvidenceStrength.OPERATION_RESULT,
            paths,
            evidence,
        )
    return (
        effect_class,
        EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
        selected_paths,
        selected_evidence,
    )


def _reconstruct_effect(
    start: dict, completion: dict, expected: tuple[ArchiveEntryReference, ...]
) -> FilesystemEffectEvent:
    start_fields = {
        "sequence",
        "source_id",
        "record_type",
        "record_id",
        "correlation_id",
        "operation",
        "entry",
        "association",
        "association_conflict",
        "context_start_sequence",
        "handle_origin_completion_sequence",
        "paths",
        "observation",
        "object_observations",
        "detail",
    }
    completion_fields = {
        "sequence",
        "source_id",
        "record_type",
        "record_id",
        "correlation_id",
        "operation",
        "entry",
        "association",
        "association_conflict",
        "start_sequence",
        "paths",
        "observation",
        "object_observations",
        "success",
        "error_code",
        "error_message",
    }
    if set(start) != start_fields or set(completion) != completion_fields:
        raise ValueError("raw operation record fields differ from schema")
    if (
        start["source_id"] != _SOURCE_ID
        or completion["source_id"] != _SOURCE_ID
        or start["record_type"] != "operation_start"
        or completion["record_type"] != "operation_completion"
        or start["correlation_id"] != completion["correlation_id"]
        or completion["start_sequence"] != start["sequence"]
        or start["operation"] != completion["operation"]
        or start["association"] != completion["association"]
        or start["paths"] != completion["paths"]
        or start["association_conflict"] is not False
        or completion["association_conflict"] is not False
    ):
        raise ValueError("raw operation start/completion correlation conflict")
    entry = _raw_entry(start["entry"], expected)
    if _raw_entry(completion["entry"], expected) != entry:
        raise ValueError("raw operation entry association conflict")
    operation = _OPERATIONS[start["operation"]]
    detail = start["detail"]
    if not isinstance(detail, dict) or set(detail) != {"symlink_target", "open_flags"}:
        raise ValueError("raw operation detail fields differ from schema")
    if operation == ObservedOperationType.SYMLINK:
        if detail["symlink_target"] != entry.link_target or detail["open_flags"] is not None:
            raise ValueError("raw symlink text differs from ArchiveCase")
    elif detail["symlink_target"] is not None:
        raise ValueError("non-symlink operation carries symlink text")
    if detail["open_flags"] is not None and not isinstance(detail["open_flags"], str):
        raise ValueError("raw open flags must be text or null")
    if operation != ObservedOperationType.OPEN and detail["open_flags"] is not None:
        raise ValueError("non-open operation carries open flags")
    success = completion["success"]
    error_code = completion["error_code"]
    error_message = completion["error_message"]
    if type(success) is not bool or (
        success
        and (error_code is not None or error_message is not None)
        or not success
        and (
            not isinstance(error_code, str)
            or not error_code
            or not isinstance(error_message, str)
            or not error_message
        )
    ):
        raise ValueError("raw operation outcome/error fields are inconsistent")
    paths = tuple(start["paths"])
    before = _raw_path_observations(start["object_observations"], paths)
    after = _raw_path_observations(completion["object_observations"], paths)
    evidence = tuple(
        EffectPathEvidence(path, first, second)
        for path, first, second in zip(paths, before, after, strict=True)
    )
    effect_class, strength, affected, selected = _independent_effect_candidate(
        operation, paths, evidence
    )
    event = FilesystemEffectEvent(
        start["sequence"],
        completion["sequence"],
        entry,
        AssociationKind(start["association"]),
        effect_class,
        strength,
        affected,
        operation,
        _raw_interval(start["observation"]),
        _raw_interval(completion["observation"]),
        _raw_outcome(success, error_code),
        selected,
        _SOURCE_ID,
        start["correlation_id"],
        RawEvidenceReference(_SOURCE_ID, completion["record_id"]),
    )
    if event.effect_class != EffectClass.OPERATION_OBSERVED and not effect_is_realized(event):
        event = dataclass_replace(
            event,
            effect_class=EffectClass.OPERATION_OBSERVED,
            evidence_strength=EffectEvidenceStrength.OPERATION_RESULT,
            affected_paths=paths,
            object_evidence=evidence,
        )
    return event


def _command_binding(result: EffectRunResult) -> tuple[str, int, dict[str, str]]:
    command = result.base_result.execution.command
    if len(command) != 14 or command[:4] != (_NODE, _WORKER, _MODULE, _LOCK):
        raise ValueError("execution command differs from native effect worker schema")
    root = Path(result.base_result.before.sandbox_root)
    if command[4:6] != (str(root / "archive/input.tar"), str(root / "extract")):
        raise ValueError("execution command paths differ from observed sandbox")
    profile = command[6]
    if profile not in ("minimal", "full"):
        raise ValueError("execution command has unsupported profile")
    bound = int(command[7])
    if not 1 <= bound <= 256:
        raise ValueError("execution command event bound is invalid")
    if (
        result.base_result.execution.target_id != "node-tar-strict-effect-v2"
        or result.base_result.execution.target_version
        != f"node={command[8]};tar={command[9]};profile={profile}"
        or any(
            re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", value) is None
            for value in command[8:10]
        )
    ):
        raise ValueError("execution target/version differs from source binding")
    for digest in command[10:14]:
        _digest(digest)
    return (
        profile,
        bound,
        {
            "node_version": command[8],
            "tar_version": command[9],
            "producer_sha256": command[10],
            "package_lock_sha256": command[11],
            "package_entrypoint_sha256": command[12],
            "unpack_sha256": command[13],
        },
    )


def _configuration_id(profile: str, bound: int, source: dict, coverage: object) -> str:
    identity = {
        "event_bound": bound,
        "profile": profile,
        "source": {
            "node": source["node_version"],
            "tar": source["tar_version"],
            "producer": source["producer_sha256"],
            "lock": source["package_lock_sha256"],
            "entrypoint": source["package_entrypoint_sha256"],
            "unpack": source["unpack_sha256"],
        },
        "coverage": coverage,
    }
    encoded = json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return sha256(encoded).hexdigest()


def _reconstruct_trace(raw: bytes, result: EffectRunResult) -> EffectEventTrace:
    if not raw.endswith(b"\n") or b"\n" in raw[:-1]:
        raise ValueError("raw stream is not one LF-terminated frame")
    envelope = read_json(raw)
    fields = {
        "format",
        "schema_version",
        "profile",
        "event_bound",
        "source",
        "input",
        "coverage",
        "target",
        "records",
        "terminal",
    }
    if not isinstance(envelope, dict) or set(envelope) != fields:
        raise ValueError("raw stream envelope fields differ from schema")
    profile, bound, command_source = _command_binding(result)
    if (
        envelope["format"] != _PROTOCOL_ID
        or envelope["schema_version"] != 1
        or envelope["profile"] != profile
        or envelope["event_bound"] != bound
        or envelope["input"] != {"archive_sha256": result.base_result.archive_sha256}
    ):
        raise ValueError("raw stream protocol/config/archive binding mismatch")
    source = envelope["source"]
    expected_source = {
        "source_id": _SOURCE_ID,
        "protocol_id": _PROTOCOL_ID,
        "protocol_version": _PROTOCOL_VERSION,
        **command_source,
        "package_entrypoint": "/target/node_modules/tar/dist/commonjs/index.min.js",
    }
    if source != expected_source:
        raise ValueError("raw stream source differs from execution command")
    coverage = envelope["coverage"]
    expected_coverage = {
        "lifecycle_kinds": ["read", "effect_work_started", "effect_work_settled"],
        "operation_callbacks": list(_OPERATIONS) if profile == "full" else [],
        "effect_classes": _EFFECT_COVERAGE,
        "path_scope": "sandbox-relative callback paths and proven descriptor-owner paths",
        "observation_perturbation": (
            "synchronous lstat/content probes at callback request and completion boundaries"
            if profile == "full"
            else "entry lifecycle and async-context propagation only"
        ),
    }
    if coverage != expected_coverage:
        raise ValueError("raw stream coverage declaration differs from reader contract")

    records, terminal = envelope["records"], envelope["terminal"]
    if (
        not isinstance(records, list)
        or not isinstance(terminal, dict)
        or set(terminal)
        != {
            "record_count",
            "last_produced_sequence",
            "last_attempted_sequence",
            "records_sha256",
            "overflow",
            "dropped_records",
            "producer_failures",
            "flush",
        }
    ):
        raise ValueError("raw records/terminal fields differ from schema")
    canonical = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    sequences = [record.get("sequence") if isinstance(record, dict) else None for record in records]
    if (
        terminal["records_sha256"] != sha256(canonical).hexdigest()
        or terminal["record_count"] != len(records)
        or terminal["last_produced_sequence"] != (len(records) - 1)
        or terminal["last_attempted_sequence"] != terminal["last_produced_sequence"]
        or terminal["overflow"] is not False
        or terminal["dropped_records"] != 0
        or terminal["producer_failures"] != []
        or terminal["flush"] != "synchronous_stdout_write"
        or sequences != list(range(len(records)))
        or len(records) > bound
    ):
        raise ValueError("raw sequence/count/digest/flush integrity failed")

    target = envelope["target"]
    expected_outcome = {
        ExecutionStatus.SUCCESS: "success",
        ExecutionStatus.REJECTED: "rejected",
        ExecutionStatus.FAILED: "failed",
        ExecutionStatus.TIMED_OUT: "timed_out",
    }[result.base_result.execution.status]
    if (
        not isinstance(target, dict)
        or set(target) != {"outcome", "error", "duration_ns"}
        or target["outcome"] != expected_outcome
        or not isinstance(target["duration_ns"], str)
        or not target["duration_ns"].isdigit()
    ):
        raise ValueError("raw target outcome/duration differs from execution")
    target_error = target["error"]
    if expected_outcome == "success":
        if target_error is not None:
            raise ValueError("successful raw target carries an error")
    elif (
        not isinstance(target_error, dict)
        or set(target_error) != {"name", "code", "message"}
        or not all(isinstance(target_error[field], str) for field in target_error)
    ):
        raise ValueError("unsuccessful raw target lacks structured error evidence")
    if result.base_result.execution.stdout.encode("utf-8", "surrogateescape") != raw:
        raise ValueError("raw stream differs from captured target stdout")

    expected_entries = _expected_entries(result)
    lifecycle: list[EntryLifecycleEvent] = []
    starts: dict[str, dict] = {}
    completions: dict[str, dict] = {}
    lifecycle_fields = {
        "sequence",
        "source_id",
        "record_type",
        "record_id",
        "entry",
        "kind",
        "observation",
        "success",
        "error",
    }
    record_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or record.get("source_id") != _SOURCE_ID:
            raise ValueError("raw record is malformed or has an unknown source")
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id or record_id in record_ids:
            raise ValueError("raw record ID is missing or duplicated")
        record_ids.add(record_id)
        record_type = record.get("record_type")
        if record_type == "lifecycle":
            if set(record) != lifecycle_fields:
                raise ValueError("raw lifecycle fields differ from schema")
            success = record["success"]
            if type(success) is not bool:
                raise ValueError("raw lifecycle success is not boolean")
            error = record["error"]
            normalized_error = None
            if not success:
                if isinstance(error, dict):
                    normalized_error = str(error.get("code") or "entry_error")
                elif isinstance(error, str) and error:
                    normalized_error = error
                else:
                    normalized_error = "entry_error"
            lifecycle.append(
                EntryLifecycleEvent(
                    record["sequence"],
                    _raw_entry(record["entry"], expected_entries),
                    _LIFECYCLE[record["kind"]],
                    _raw_interval(record["observation"]),
                    LifecycleStatus.SUCCEEDED if success else LifecycleStatus.ERRORED,
                    normalized_error,
                    _SOURCE_ID,
                    RawEvidenceReference(_SOURCE_ID, record["record_id"]),
                )
            )
        elif record_type in ("operation_start", "operation_completion"):
            correlation = record.get("correlation_id")
            if not isinstance(correlation, str) or not correlation:
                raise ValueError("raw operation lacks correlation ID")
            collection = starts if record_type == "operation_start" else completions
            if correlation in collection:
                raise ValueError("raw operation correlation is duplicated")
            collection[correlation] = record
        else:
            raise ValueError("raw record type is unsupported")
    if set(starts) != set(completions):
        raise ValueError("raw operation starts/completions do not correlate exactly")
    effects = tuple(
        sorted(
            (
                _reconstruct_effect(starts[item], completions[item], expected_entries)
                for item in starts
            ),
            key=lambda event: event.start_sequence,
        )
    )
    lifecycle.sort(key=lambda event: event.sequence)
    lifecycle_by_sequence = {event.sequence: event for event in lifecycle}
    effect_by_completion = {event.completion_sequence: event for event in effects}
    causal: list[CausalRelation] = []
    for event in effects:
        start, completion = starts[event.correlation_id], completions[event.correlation_id]
        causal.append(
            CausalRelation(
                event.start_sequence,
                event.completion_sequence,
                CausalRelationKind.OPERATION_INTERVAL,
                _SOURCE_ID,
                event.correlation_id,
                RawEvidenceReference(_SOURCE_ID, completion["record_id"]),
            )
        )
        context_sequence = start["context_start_sequence"]
        if event.association == AssociationKind.ASYNC_CONTEXT:
            context = lifecycle_by_sequence.get(context_sequence)
            if (
                type(context_sequence) is not int
                or context is None
                or context.kind != EntryLifecycleKind.EFFECT_WORK_STARTED
                or context.entry != event.entry
                or context_sequence >= event.start_sequence
            ):
                raise ValueError("raw async-context edge is unsupported")
            causal.append(
                CausalRelation(
                    context_sequence,
                    event.start_sequence,
                    CausalRelationKind.ENTRY_CONTEXT_PROPAGATION,
                    _SOURCE_ID,
                    f"context-{context_sequence}",
                    RawEvidenceReference(_SOURCE_ID, start["record_id"]),
                )
            )
        handle_sequence = start["handle_origin_completion_sequence"]
        if handle_sequence is not None:
            cause = effect_by_completion.get(handle_sequence)
            if (
                type(handle_sequence) is not int
                or cause is None
                or cause.entry != event.entry
                or handle_sequence >= event.start_sequence
            ):
                raise ValueError("raw handle-provenance edge is unsupported")
            causal.append(
                CausalRelation(
                    handle_sequence,
                    event.start_sequence,
                    CausalRelationKind.HANDLE_PROVENANCE,
                    _SOURCE_ID,
                    f"handle-{handle_sequence}",
                    RawEvidenceReference(_SOURCE_ID, start["record_id"]),
                )
            )
    causal.sort(
        key=lambda edge: (edge.predecessor_sequence, edge.successor_sequence, edge.kind.value)
    )
    trace_source = EvidenceSourceIdentity(
        _SOURCE_ID,
        "node-tar-private-checkfs2-async-context-fs-callbacks",
        _PROTOCOL_VERSION,
        command_source["producer_sha256"],
    )
    provenance = EffectTraceProvenance(
        _PROTOCOL_ID,
        _PROTOCOL_VERSION,
        _configuration_id(profile, bound, source, coverage),
        (trace_source,),
        bound,
        tuple(EntryLifecycleKind),
        sha256(raw).hexdigest(),
    )
    termination = {
        ExecutionStatus.SUCCESS: EffectTargetTermination.SUCCESS,
        ExecutionStatus.REJECTED: EffectTargetTermination.REJECTED,
        ExecutionStatus.FAILED: EffectTargetTermination.FAILED,
        ExecutionStatus.TIMED_OUT: EffectTargetTermination.TIMED_OUT,
    }[result.base_result.execution.status]
    return EffectEventTrace(
        result.base_result.before,
        expected_entries,
        tuple(lifecycle),
        effects,
        tuple(causal),
        (),
        result.base_result.after,
        EffectStreamCompleteness.COMPLETE,
        termination,
        provenance,
        terminal["last_produced_sequence"],
        terminal["last_produced_sequence"],
        terminal["last_produced_sequence"],
        (),
    )


def reconstruct_native_effect_trace(raw: bytes, result: EffectRunResult) -> EffectEventTrace:
    """Public independent raw reconstruction used by qualification injections."""
    try:
        if not isinstance(raw, bytes) or not isinstance(result, EffectRunResult):
            raise ValueError("raw reconstruction requires bytes and EffectRunResult")
        return _reconstruct_trace(raw, result)
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        RecursionError,
    ) as error:
        raise VerificationError(f"invalid native effect raw stream: {error}") from error


def verify_native_effect_evidence(
    directory: Path, *, expected_manifest_sha256: str | None = None
) -> VerifiedNativeEffectEvidence:
    """Independently rebuild the trace and normalized keys from immutable raw bytes."""
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("expected a completed native effect evidence directory")
        if {path.name for path in directory.iterdir()} != {
            "manifest.json",
            "raw-stream.json",
            "result.json",
        }:
            raise ValueError("native effect evidence files are incomplete or unexpected")
        manifest_bytes = _read_file(directory / "manifest.json")
        manifest_digest = sha256(manifest_bytes).hexdigest()
        if expected_manifest_sha256 is not None and manifest_digest != _digest(
            expected_manifest_sha256
        ):
            raise ValueError("native effect manifest checksum mismatch")
        manifest = read_record(
            directory / "manifest.json",
            NativeEffectEvidenceManifest,
            expected_sha256=manifest_digest,
        )
        result = read_record(
            directory / manifest.result.name,
            EffectRunResult,
            expected_sha256=manifest.result.sha256,
        )
        raw = _read_file(directory / manifest.raw_stream.name)
        raw_digest = sha256(raw).hexdigest()
        if (
            raw_digest != manifest.raw_stream.sha256
            or raw_digest != manifest.raw_stream_sha256
            or raw_digest != result.trace.provenance.raw_stream_sha256
            or manifest.case_id != result.base_result.case.case_id
            or manifest.producer_source_sha256 != result.trace.provenance.sources[0].source_sha256
        ):
            raise ValueError("native effect manifest/result/raw binding mismatch")
        verify_run(result.base_result)
        reconstructed = reconstruct_native_effect_trace(raw, result)
        if reconstructed != result.trace:
            raise ValueError("producer trace differs from independent raw reconstruction")
        keys = effect_feedback_keys(reconstructed)
        if keys != effect_feedback_keys(result.trace):
            raise ValueError("normalized effect key derivation is inconsistent")
        return VerifiedNativeEffectEvidence(result, manifest, manifest_digest, raw, keys)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        RecursionError,
    ) as error:
        raise VerificationError(f"invalid native effect evidence: {error}") from error

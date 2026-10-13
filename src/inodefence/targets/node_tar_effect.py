"""Contained node-tar v2 effect producer and target-specific raw conversion."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from inodefence.execution.base import ContainerOutcome, ContainerRequest, ExecutionBackend
from inodefence.model import (
    ArchiveCase,
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
    ExecutionResult,
    ExecutionStatus,
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
    StateSnapshot,
)
from inodefence.model.effect import effect_is_realized
from inodefence.model.isolation import ArtifactDigest, IsolationProvenance
from inodefence.model.provenance import TargetProvenance

from ._paths import validate_run_paths
from .isolated import identify_image

NODE = "/usr/local/bin/node"
WORKER = "/target/effect-producer.cjs"
MODULE = "/target/node_modules/tar"
LOCK = "/target/package-lock.json"
PROTOCOL_ID = "inodefence-node-tar-effect-stream"
PROTOCOL_VERSION = "2.0.0"
SOURCE_ID = "node-tar-effect-worker-v2"
MAX_EVENT_BOUND = 256


class NativeEffectProfile(StrEnum):
    MINIMAL = "minimal"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class NativeEffectCapture:
    """Stopped-target execution plus the bounded raw stdout frame."""

    execution: ExecutionResult
    raw_stream: bytes
    transport_truncated: bool
    controller_flush_verified: bool
    transport_error: str | None
    expected_archive_sha256: str


@dataclass(frozen=True, slots=True)
class NodeTarEffectTarget:
    """Pinned contained invocation for the v2 node-tar effect worker."""

    backend: ExecutionBackend
    image_id: str
    node_version: str
    tar_version: str
    producer_sha256: str
    package_lock_sha256: str
    package_entrypoint_sha256: str
    unpack_sha256: str
    profile: NativeEffectProfile = NativeEffectProfile.FULL
    event_bound: int = MAX_EVENT_BOUND
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.backend, ExecutionBackend):
            raise ValueError("effect target requires a trusted ExecutionBackend")
        if (
            not isinstance(self.image_id, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id) is None
        ):
            raise ValueError("effect target requires an immutable image ID")
        if not all(
            isinstance(value, str) and re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", value)
            for value in (self.node_version, self.tar_version)
        ):
            raise ValueError("effect target versions must be exact semantic versions")
        for value in (
            self.producer_sha256,
            self.package_lock_sha256,
            self.package_entrypoint_sha256,
            self.unpack_sha256,
        ):
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ValueError("effect target source identities require SHA-256")
        if not isinstance(self.profile, NativeEffectProfile):
            raise ValueError("effect target requires an explicit instrumentation profile")
        if type(self.event_bound) is not int or not 1 <= self.event_bound <= MAX_EVENT_BOUND:
            raise ValueError(f"effect event bound must be in 1..{MAX_EVENT_BOUND}")
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 120
        ):
            raise ValueError("effect timeout must be finite, positive and at most 120 seconds")
        self.backend.validate_image(self.image_id)

    @classmethod
    def bind(
        cls,
        backend: ExecutionBackend,
        image_id: str,
        *,
        profile: NativeEffectProfile = NativeEffectProfile.FULL,
        event_bound: int = MAX_EVENT_BOUND,
        timeout_seconds: float = 10.0,
    ) -> NodeTarEffectTarget:
        if not isinstance(backend, ExecutionBackend):
            raise ValueError("effect target requires a trusted ExecutionBackend")
        # Constructor-shaped validation must precede image execution.
        placeholder = "0" * 64
        cls(
            backend,
            image_id,
            "0.0.0",
            "0.0.0",
            placeholder,
            placeholder,
            placeholder,
            placeholder,
            profile,
            event_bound,
            timeout_seconds,
        )
        value = _identify(backend, image_id)
        try:
            return cls(
                backend,
                image_id,
                value["node_version"],
                value["tar_version"],
                value["producer_sha256"],
                value["package_lock_sha256"],
                value["package_entrypoint_sha256"],
                value["unpack_sha256"],
                profile,
                event_bound,
                timeout_seconds,
            )
        except (KeyError, TypeError) as error:
            raise ValueError("effect target identity response is incomplete") from error

    @property
    def provenance(self) -> TargetProvenance:
        return TargetProvenance(
            "node-tar-strict-effect-v2",
            f"node={self.node_version};tar={self.tar_version};profile={self.profile.value}",
            self.timeout_seconds,
        )

    @property
    def artifacts(self) -> tuple[ArtifactDigest, ...]:
        return (
            ArtifactDigest("node-tar-effect-producer", self.producer_sha256),
            ArtifactDigest("node-tar-package-lock", self.package_lock_sha256),
            ArtifactDigest("node-tar-package-entrypoint", self.package_entrypoint_sha256),
            ArtifactDigest("node-tar-unpack-source", self.unpack_sha256),
        )

    def _verify_identity(self) -> None:
        value = _identify(self.backend, self.image_id)
        observed = NodeTarEffectTarget(
            self.backend,
            self.image_id,
            value["node_version"],
            value["tar_version"],
            value["producer_sha256"],
            value["package_lock_sha256"],
            value["package_entrypoint_sha256"],
            value["unpack_sha256"],
            self.profile,
            self.event_bound,
            self.timeout_seconds,
        )
        if observed != self:
            raise RuntimeError("node-tar effect identity changed after setup")

    def capture_isolation(self) -> IsolationProvenance:
        captured = self.backend.capture_isolation(self.image_id)
        self._verify_identity()
        return replace(
            captured,
            artifacts=self.artifacts,
            artifact_origin="image-identification-effect-v2",
        )

    def command(self, archive_path: Path, extraction_root: Path) -> tuple[str, ...]:
        return (
            NODE,
            WORKER,
            MODULE,
            LOCK,
            str(archive_path),
            str(extraction_root),
            self.profile.value,
            str(self.event_bound),
            self.node_version,
            self.tar_version,
            self.producer_sha256,
            self.package_lock_sha256,
            self.package_entrypoint_sha256,
            self.unpack_sha256,
        )

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult:
        if outcome.exit_code == 3:
            raise RuntimeError("node-tar effect identity changed after setup")
        status = (
            ExecutionStatus.TIMED_OUT
            if outcome.exit_code is None
            else ExecutionStatus.SUCCESS
            if outcome.exit_code == 0
            else ExecutionStatus.REJECTED
            if outcome.exit_code == 2
            else ExecutionStatus.FAILED
        )
        declared = self.provenance
        return ExecutionResult(
            declared.target_id,
            declared.target_version,
            command,
            status,
            outcome.exit_code,
            outcome.stdout.decode("utf-8", "surrogateescape"),
            outcome.stderr.decode("utf-8", "surrogateescape"),
            outcome.duration_seconds,
            self.timeout_seconds,
        )

    @contextmanager
    def prepare(
        self, archive_path: Path, extraction_root: Path
    ) -> Iterator[Callable[[], NativeEffectCapture]]:
        validate_run_paths(archive_path, extraction_root)
        self._verify_identity()
        expected_archive_sha256 = sha256(archive_path.read_bytes()).hexdigest()
        command = self.command(archive_path, extraction_root)
        request = ContainerRequest(
            self.image_id, command, extraction_root.parent, self.timeout_seconds
        )
        with self.backend.prepare(request) as prepared:
            executed = False

            def execute() -> NativeEffectCapture:
                nonlocal executed
                if executed:
                    raise RuntimeError("one prepared effect target executes exactly once")
                executed = True
                outcome = prepared.execute()
                execution = self.classify(outcome, command)
                flush_verified, transport_error = _verify_transport_frame(
                    outcome.stdout,
                    outcome.output_truncated,
                    self,
                    expected_archive_sha256,
                )
                return NativeEffectCapture(
                    execution,
                    outcome.stdout,
                    outcome.output_truncated,
                    flush_verified,
                    transport_error,
                    expected_archive_sha256,
                )

            yield execute


def _identify(backend: ExecutionBackend, image_id: str) -> dict[str, Any]:
    stdout = identify_image(backend, image_id, (NODE, WORKER, "--identify", MODULE, LOCK))
    try:
        value = json.loads(stdout)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("effect target returned invalid identity metadata") from error
    if not isinstance(value, dict):
        raise ValueError("effect target identity metadata must be an object")
    return value


def _verify_transport_frame(
    raw_stream: bytes,
    truncated: bool,
    target: NodeTarEffectTarget,
    expected_archive_sha256: str,
) -> tuple[bool, str | None]:
    """Verify terminal delivery before the caller is allowed to capture AFTER."""
    if truncated:
        return False, "backend output bound exceeded"
    try:
        if not raw_stream.endswith(b"\n") or b"\n" in raw_stream[:-1]:
            raise ValueError("transport is not one LF-terminated frame")
        value = json.loads(raw_stream)
        if not isinstance(value, dict):
            raise ValueError("transport frame is not an object")
        if (
            value.get("format") != PROTOCOL_ID
            or value.get("schema_version") != 1
            or value.get("profile") != target.profile.value
            or value.get("event_bound") != target.event_bound
        ):
            raise ValueError("transport protocol/configuration mismatch")
        source = value.get("source")
        input_record = value.get("input")
        terminal = value.get("terminal")
        records = value.get("records")
        if (
            not isinstance(source, dict)
            or not isinstance(terminal, dict)
            or not isinstance(records, list)
        ):
            raise ValueError("transport source/records/terminal are malformed")
        if input_record != {"archive_sha256": expected_archive_sha256}:
            raise ValueError("transport archive identity mismatch")
        expected = {
            "source_id": SOURCE_ID,
            "protocol_id": PROTOCOL_ID,
            "protocol_version": PROTOCOL_VERSION,
            "node_version": target.node_version,
            "tar_version": target.tar_version,
            "producer_sha256": target.producer_sha256,
            "package_lock_sha256": target.package_lock_sha256,
            "package_entrypoint_sha256": target.package_entrypoint_sha256,
            "unpack_sha256": target.unpack_sha256,
        }
        if any(source.get(key) != item for key, item in expected.items()):
            raise ValueError("transport source binding mismatch")
        canonical = json.dumps(
            records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        if terminal.get("records_sha256") != sha256(canonical).hexdigest():
            raise ValueError("transport record digest mismatch")
        if terminal.get("record_count") != len(records):
            raise ValueError("transport record count mismatch")
        if terminal.get("flush") != "synchronous_stdout_write":
            raise ValueError("transport terminal flush marker mismatch")
        last = records[-1].get("sequence") if records else -1
        if terminal.get("last_produced_sequence") != last:
            raise ValueError("transport terminal sequence mismatch")
        return True, None
    except (UnicodeDecodeError, ValueError, TypeError, KeyError, OverflowError) as error:
        return False, str(error)


def archive_references(case: ArchiveCase) -> tuple[ArchiveEntryReference, ...]:
    return tuple(
        ArchiveEntryReference(index, entry.path, entry.entry_type, entry.link_target)
        for index, entry in enumerate(case.entries)
    )


_NODE_ENTRY_TYPES = {
    "File": EntryType.REGULAR,
    "Directory": EntryType.DIRECTORY,
    "Link": EntryType.HARDLINK,
    "SymbolicLink": EntryType.SYMLINK,
}
_OPERATION_TYPES = {
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
_LIFECYCLE_KINDS = {
    "read": EntryLifecycleKind.READ,
    "effect_work_started": EntryLifecycleKind.EFFECT_WORK_STARTED,
    "effect_work_settled": EntryLifecycleKind.EFFECT_WORK_SETTLED,
}


def _termination(status: ExecutionStatus) -> EffectTargetTermination:
    return {
        ExecutionStatus.SUCCESS: EffectTargetTermination.SUCCESS,
        ExecutionStatus.REJECTED: EffectTargetTermination.REJECTED,
        ExecutionStatus.FAILED: EffectTargetTermination.FAILED,
        ExecutionStatus.TIMED_OUT: EffectTargetTermination.TIMED_OUT,
    }[status]


def _source(target: NodeTarEffectTarget) -> EvidenceSourceIdentity:
    return EvidenceSourceIdentity(
        SOURCE_ID,
        "node-tar-private-checkfs2-async-context-fs-callbacks",
        PROTOCOL_VERSION,
        target.producer_sha256,
    )


def _configuration_id(target: NodeTarEffectTarget, coverage: object) -> str:
    value = {
        "event_bound": target.event_bound,
        "profile": target.profile.value,
        "source": {
            "node": target.node_version,
            "tar": target.tar_version,
            "producer": target.producer_sha256,
            "lock": target.package_lock_sha256,
            "entrypoint": target.package_entrypoint_sha256,
            "unpack": target.unpack_sha256,
        },
        "coverage": coverage,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return sha256(encoded).hexdigest()


def _failure(
    kind: ObservationFailureKind, message: str, sequence: int | None = None
) -> ObservationFailure:
    return ObservationFailure(kind, message, SOURCE_ID, sequence)


def _fallback_trace(
    capture: NativeEffectCapture,
    target: NodeTarEffectTarget,
    case: ArchiveCase,
    before: StateSnapshot,
    after: StateSnapshot,
    failures: Sequence[ObservationFailure],
    *,
    completeness: EffectStreamCompleteness = EffectStreamCompleteness.INVALID,
) -> EffectEventTrace:
    if not failures and completeness != EffectStreamCompleteness.COMPLETE:
        raise ValueError("incomplete fallback traces require a failure")
    provenance = EffectTraceProvenance(
        PROTOCOL_ID,
        PROTOCOL_VERSION,
        _configuration_id(target, {"unavailable": True}),
        (_source(target),),
        target.event_bound,
        tuple(EntryLifecycleKind),
        sha256(capture.raw_stream).hexdigest(),
    )
    return EffectEventTrace(
        before,
        archive_references(case),
        (),
        (),
        (),
        (),
        after,
        completeness,
        _termination(capture.execution.status),
        provenance,
        -1,
        None,
        None,
        tuple(failures),
    )


def _interval(value: object) -> MonotonicInterval:
    if not isinstance(value, dict) or set(value) != {"started_ns", "finished_ns"}:
        raise ValueError("observation interval has invalid fields")
    return MonotonicInterval(int(value["started_ns"]), int(value["finished_ns"]))


def _entry(value: object, expected: tuple[ArchiveEntryReference, ...]) -> ArchiveEntryReference:
    if not isinstance(value, dict) or set(value) != {
        "ordinal",
        "path",
        "type",
        "link_target",
    }:
        raise ValueError("entry identity has invalid fields")
    ordinal = value["ordinal"]
    if type(ordinal) is not int or not 0 <= ordinal < len(expected):
        raise ValueError("entry ordinal is outside ArchiveCase")
    try:
        entry_type = _NODE_ENTRY_TYPES[value["type"]]
    except (KeyError, TypeError) as error:
        raise ValueError("entry type is not supported") from error
    reference = ArchiveEntryReference(ordinal, value["path"], entry_type, value["link_target"])
    if reference != expected[ordinal]:
        raise ValueError("entry identity differs from ArchiveCase")
    return reference


def _object(value: object, expected_path: str) -> ObjectSnapshot:
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
    if not isinstance(value, dict) or set(value) != fields or value["path"] != expected_path:
        raise ValueError("object evidence has invalid fields or path")
    return ObjectSnapshot(
        value["path"],
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


def _observation(value: object, expected_path: str) -> EffectObjectObservation:
    if not isinstance(value, dict) or set(value) != {"status", "object", "error"}:
        raise ValueError("object observation has invalid fields")
    status = EffectObservationStatus(value["status"])
    if status == EffectObservationStatus.PRESENT:
        return EffectObjectObservation(status, _object(value["object"], expected_path))
    if value["object"] is not None:
        raise ValueError("non-present observations cannot carry an object")
    return EffectObjectObservation(status, None)


def _path_observations(
    value: object, paths: tuple[str, ...]
) -> tuple[EffectObjectObservation, ...]:
    if not isinstance(value, list) or len(value) != len(paths):
        raise ValueError("path observation arity differs from affected paths")
    observations: list[EffectObjectObservation] = []
    for item, expected_path in zip(value, paths, strict=True):
        if not isinstance(item, dict) or set(item) != {"path", "observation"}:
            raise ValueError("path observation has invalid fields")
        if item["path"] != expected_path:
            raise ValueError("path observation order differs from affected paths")
        observations.append(_observation(item["observation"], expected_path))
    return tuple(observations)


def _outcome(success: bool, error_code: object) -> OperationOutcome:
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


def _candidate_effect(
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
    selected_paths = paths
    selected_evidence = evidence
    if operation == ObservedOperationType.RENAME and len(paths) == 2:
        selected_paths = (paths[1],)
        selected_evidence = (evidence[1],)
    if len(selected_paths) != 1:
        return (
            EffectClass.OPERATION_OBSERVED,
            EffectEvidenceStrength.OPERATION_RESULT,
            paths,
            evidence,
        )
    item = selected_evidence[0]
    before, after = item.before.object, item.after.object
    if before is None and after is not None:
        return (
            EffectClass.NAMESPACE_CREATION,
            EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
            selected_paths,
            selected_evidence,
        )
    if before is not None and after is None:
        return (
            EffectClass.NAMESPACE_REMOVAL,
            EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
            selected_paths,
            selected_evidence,
        )
    if (
        before is not None
        and after is not None
        and (before.identity != after.identity or before.object_type != after.object_type)
    ):
        return (
            EffectClass.NAMESPACE_REPLACEMENT,
            EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
            selected_paths,
            selected_evidence,
        )
    if operation in (ObservedOperationType.WRITE, ObservedOperationType.WRITEV):
        return (
            EffectClass.REGULAR_FILE_CONTENT_MODIFICATION,
            EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
            selected_paths,
            selected_evidence,
        )
    if operation == ObservedOperationType.OPEN:
        return (
            EffectClass.TRUNCATION,
            EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
            selected_paths,
            selected_evidence,
        )
    if operation in (
        ObservedOperationType.CHMOD,
        ObservedOperationType.CHOWN,
        ObservedOperationType.UTIMES,
        ObservedOperationType.FUTIMES,
        ObservedOperationType.FCHOWN,
    ):
        return (
            EffectClass.METADATA_MODIFICATION,
            EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
            selected_paths,
            selected_evidence,
        )
    return (
        EffectClass.OPERATION_OBSERVED,
        EffectEvidenceStrength.OPERATION_RESULT,
        paths,
        evidence,
    )


def _effect_event(
    start: Mapping[str, Any],
    completion: Mapping[str, Any],
    expected: tuple[ArchiveEntryReference, ...],
) -> FilesystemEffectEvent:
    start_entry = _entry(start["entry"], expected)
    completion_entry = _entry(completion["entry"], expected)
    if start_entry != completion_entry:
        raise ValueError("operation start/completion entry identities differ")
    if start["operation"] != completion["operation"]:
        raise ValueError("operation start/completion names differ")
    operation = _OPERATION_TYPES[start["operation"]]
    paths = tuple(start["paths"])
    if tuple(completion["paths"]) != paths:
        raise ValueError("operation start/completion paths differ")
    before = _path_observations(start["object_observations"], paths)
    after = _path_observations(completion["object_observations"], paths)
    evidence = tuple(
        EffectPathEvidence(effect_path, before_item, after_item)
        for effect_path, before_item, after_item in zip(paths, before, after, strict=True)
    )
    success = completion["success"]
    if type(success) is not bool:
        raise ValueError("operation completion success must be boolean")
    outcome = _outcome(success, completion["error_code"])
    effect_class, strength, affected, selected_evidence = _candidate_effect(
        operation, paths, evidence
    )
    association = AssociationKind(start["association"])
    event = FilesystemEffectEvent(
        start["sequence"],
        completion["sequence"],
        start_entry,
        association,
        effect_class,
        strength,
        affected,
        operation,
        _interval(start["observation"]),
        _interval(completion["observation"]),
        outcome,
        selected_evidence,
        SOURCE_ID,
        start["correlation_id"],
        RawEvidenceReference(SOURCE_ID, completion["record_id"]),
    )
    if effect_class != EffectClass.OPERATION_OBSERVED and not effect_is_realized(event):
        event = replace(
            event,
            effect_class=EffectClass.OPERATION_OBSERVED,
            evidence_strength=EffectEvidenceStrength.OPERATION_RESULT,
            affected_paths=paths,
            object_evidence=evidence,
        )
    return event


def effect_trace_from_capture(
    capture: NativeEffectCapture,
    target: NodeTarEffectTarget,
    case: ArchiveCase,
    before: StateSnapshot,
    after: StateSnapshot,
) -> EffectEventTrace:
    """Validate producer framing and convert only supported raw evidence."""
    if capture.execution.status == ExecutionStatus.TIMED_OUT:
        return _fallback_trace(
            capture,
            target,
            case,
            before,
            after,
            (_failure(ObservationFailureKind.INCOMPLETE_FLUSH, "target timed out before flush"),),
            completeness=EffectStreamCompleteness.INCOMPLETE,
        )
    if capture.transport_truncated:
        return _fallback_trace(
            capture,
            target,
            case,
            before,
            after,
            (
                _failure(ObservationFailureKind.BUFFER_OVERFLOW, "backend output bound exceeded"),
                _failure(ObservationFailureKind.INCOMPLETE_FLUSH, "transport frame was truncated"),
            ),
        )
    try:
        if not capture.raw_stream.endswith(b"\n") or b"\n" in capture.raw_stream[:-1]:
            raise ValueError("raw transport must contain exactly one LF-terminated frame")
        envelope = json.loads(capture.raw_stream)
        if not isinstance(envelope, dict) or set(envelope) != {
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
        }:
            raise ValueError("raw transport envelope fields differ from schema")
        if (
            envelope["format"] != PROTOCOL_ID
            or envelope["schema_version"] != 1
            or envelope["profile"] != target.profile.value
            or envelope["event_bound"] != target.event_bound
        ):
            raise ValueError("raw transport protocol/configuration mismatch")
        if envelope["input"] != {"archive_sha256": capture.expected_archive_sha256}:
            raise ValueError("raw transport archive identity mismatch")
        source = envelope["source"]
        expected_source = {
            "source_id": SOURCE_ID,
            "protocol_id": PROTOCOL_ID,
            "protocol_version": PROTOCOL_VERSION,
            "node_version": target.node_version,
            "tar_version": target.tar_version,
            "producer_sha256": target.producer_sha256,
            "package_lock_sha256": target.package_lock_sha256,
            "package_entrypoint_sha256": target.package_entrypoint_sha256,
            "unpack_sha256": target.unpack_sha256,
        }
        if not isinstance(source, dict) or any(
            source.get(key) != value for key, value in expected_source.items()
        ):
            raise ValueError("raw transport source identity mismatch")
        if set(source) != set(expected_source) | {"package_entrypoint"} or not isinstance(
            source["package_entrypoint"], str
        ):
            raise ValueError("raw transport source identity fields differ from schema")
        records = envelope["records"]
        terminal = envelope["terminal"]
        if not isinstance(records, list) or not isinstance(terminal, dict):
            raise ValueError("raw records and terminal must be structured")
        canonical_records = json.dumps(
            records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        if terminal.get("records_sha256") != sha256(canonical_records).hexdigest():
            raise ValueError("raw record digest mismatch")
    except (UnicodeDecodeError, ValueError, TypeError, KeyError, OverflowError) as error:
        return _fallback_trace(
            capture,
            target,
            case,
            before,
            after,
            (
                _failure(
                    ObservationFailureKind.SOURCE_READER_DISAGREEMENT,
                    f"malformed producer frame: {error}",
                ),
                _failure(ObservationFailureKind.INCOMPLETE_FLUSH, "frame could not be verified"),
            ),
        )

    expected = archive_references(case)
    failures: list[ObservationFailure] = []
    lifecycle: list[EntryLifecycleEvent] = []
    starts: dict[str, Mapping[str, Any]] = {}
    completions: dict[str, Mapping[str, Any]] = {}
    sequences: list[int] = []
    for raw in records:
        sequence: int | None = None
        try:
            if not isinstance(raw, dict):
                raise ValueError("record is not an object")
            sequence = raw.get("sequence")
            if type(sequence) is not int or not 0 <= sequence < target.event_bound:
                raise ValueError("record sequence is outside declared bound")
            sequences.append(sequence)
            if raw.get("source_id") != SOURCE_ID:
                raise ValueError("record source differs from declared source")
            record_type = raw.get("record_type")
            if record_type == "lifecycle":
                reference = _entry(raw.get("entry"), expected)
                kind = _LIFECYCLE_KINDS[raw["kind"]]
                success = raw["success"]
                if type(success) is not bool:
                    raise ValueError("lifecycle success must be boolean")
                error = raw["error"]
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
                        sequence,
                        reference,
                        kind,
                        _interval(raw["observation"]),
                        LifecycleStatus.SUCCEEDED if success else LifecycleStatus.ERRORED,
                        normalized_error,
                        SOURCE_ID,
                        RawEvidenceReference(SOURCE_ID, raw["record_id"]),
                    )
                )
            elif record_type == "operation_start":
                correlation = raw["correlation_id"]
                if not isinstance(correlation, str) or not correlation or correlation in starts:
                    raise ValueError("duplicate or invalid operation start correlation")
                starts[correlation] = raw
            elif record_type == "operation_completion":
                correlation = raw["correlation_id"]
                if (
                    not isinstance(correlation, str)
                    or not correlation
                    or correlation in completions
                ):
                    raise ValueError("duplicate or invalid operation completion correlation")
                completions[correlation] = raw
            else:
                raise ValueError("record type is not supported")
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            kind = (
                ObservationFailureKind.MALFORMED_IDENTITY
                if "entry" in str(error) or "identity" in str(error)
                else ObservationFailureKind.SOURCE_READER_DISAGREEMENT
            )
            failures.append(_failure(kind, f"malformed raw record: {error}", sequence))

    if len(set(sequences)) != len(sequences):
        failures.append(
            _failure(ObservationFailureKind.DUPLICATE_SEQUENCE, "duplicate source sequence")
        )
    terminal_last = terminal.get("last_produced_sequence")
    expected_sequences = list(range(terminal_last + 1)) if type(terminal_last) is int else []
    if sorted(set(sequences)) != expected_sequences:
        failures.append(_failure(ObservationFailureKind.EVENT_LOSS, "source sequence gap"))
    if terminal.get("record_count") != len(records):
        failures.append(
            _failure(ObservationFailureKind.EVENT_LOSS, "terminal record count mismatch")
        )
    if terminal.get("overflow") is not False or terminal.get("dropped_records") != 0:
        failures.append(
            _failure(ObservationFailureKind.BUFFER_OVERFLOW, "producer event bound overflowed")
        )
    if terminal.get("producer_failures") != []:
        failures.append(
            _failure(
                ObservationFailureKind.SOURCE_READER_DISAGREEMENT,
                "producer reported internal observation failures",
            )
        )
    if terminal.get("flush") != "synchronous_stdout_write":
        failures.append(_failure(ObservationFailureKind.INCOMPLETE_FLUSH, "flush marker mismatch"))
    if not capture.controller_flush_verified:
        failures.append(
            _failure(
                ObservationFailureKind.INCOMPLETE_FLUSH,
                f"controller did not acknowledge terminal frame: {capture.transport_error}",
            )
        )

    expected_outcome = {
        ExecutionStatus.SUCCESS: "success",
        ExecutionStatus.REJECTED: "rejected",
        ExecutionStatus.FAILED: "failed",
    }[capture.execution.status]
    target_record = envelope["target"]
    if not isinstance(target_record, dict) or target_record.get("outcome") != expected_outcome:
        failures.append(
            _failure(
                ObservationFailureKind.SOURCE_READER_DISAGREEMENT,
                "producer target outcome differs from execution status",
            )
        )

    effects: list[FilesystemEffectEvent] = []
    causal: list[CausalRelation] = []
    lifecycle_by_sequence = {event.sequence: event for event in lifecycle}
    completion_sequences: set[int] = set()

    def correlation_order(correlation: str) -> tuple[int, str]:
        sequence = (starts.get(correlation) or completions.get(correlation) or {}).get("sequence")
        return (sequence if type(sequence) is int else target.event_bound, correlation)

    correlations = sorted(set(starts) | set(completions), key=correlation_order)
    for correlation in correlations:
        start, completion = starts.get(correlation), completions.get(correlation)
        if start is None or completion is None:
            sequence = (start or completion or {}).get("sequence")
            failures.append(
                _failure(
                    ObservationFailureKind.OPERATION_CORRELATION_CONFLICT,
                    f"unmatched operation correlation {correlation}",
                    sequence if type(sequence) is int else None,
                )
            )
            continue
        try:
            if completion.get("start_sequence") != start.get("sequence"):
                raise ValueError("completion does not name its start sequence")
            if (
                start.get("association_conflict") is not False
                or completion.get("association_conflict") is not False
            ):
                raise ValueError("conflicting async-context and handle provenance")
            event = _effect_event(start, completion, expected)
            effects.append(event)
            completion_sequences.add(event.completion_sequence)
            causal.append(
                CausalRelation(
                    event.start_sequence,
                    event.completion_sequence,
                    CausalRelationKind.OPERATION_INTERVAL,
                    SOURCE_ID,
                    correlation,
                    RawEvidenceReference(SOURCE_ID, completion["record_id"]),
                )
            )
            context_sequence = start.get("context_start_sequence")
            if event.association == AssociationKind.ASYNC_CONTEXT:
                if type(context_sequence) is not int:
                    raise ValueError("async-context provenance lacks a work-start sequence")
                context_event = lifecycle_by_sequence.get(context_sequence)
                if (
                    context_event is None
                    or context_event.kind != EntryLifecycleKind.EFFECT_WORK_STARTED
                    or context_event.entry != event.entry
                    or context_sequence >= event.start_sequence
                ):
                    raise ValueError("async-context provenance does not name matching work start")
                causal.append(
                    CausalRelation(
                        context_sequence,
                        event.start_sequence,
                        CausalRelationKind.ENTRY_CONTEXT_PROPAGATION,
                        SOURCE_ID,
                        f"context-{context_sequence}",
                        RawEvidenceReference(SOURCE_ID, start["record_id"]),
                    )
                )
            handle_sequence = start.get("handle_origin_completion_sequence")
            if handle_sequence is not None:
                if (
                    type(handle_sequence) is not int
                    or handle_sequence not in completion_sequences
                    or handle_sequence >= event.start_sequence
                ):
                    raise ValueError("handle provenance does not name an earlier completion")
                causal.append(
                    CausalRelation(
                        handle_sequence,
                        event.start_sequence,
                        CausalRelationKind.HANDLE_PROVENANCE,
                        SOURCE_ID,
                        f"handle-{handle_sequence}",
                        RawEvidenceReference(SOURCE_ID, start["record_id"]),
                    )
                )
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            failures.append(
                _failure(
                    ObservationFailureKind.OPERATION_CORRELATION_CONFLICT
                    if "provenance" not in str(error)
                    else ObservationFailureKind.ASSOCIATION_CONFLICT,
                    f"invalid correlated operation {correlation}: {error}",
                    start.get("sequence") if type(start.get("sequence")) is int else None,
                )
            )
            effects = [item for item in effects if item.correlation_id != correlation]
            causal = [
                edge
                for edge in causal
                if edge.evidence_token != correlation
                and edge.raw_evidence.record_id != start.get("record_id")
            ]

    lifecycle.sort(key=lambda event: event.sequence)
    effects.sort(key=lambda event: event.start_sequence)
    causal.sort(
        key=lambda edge: (edge.predecessor_sequence, edge.successor_sequence, edge.kind.value)
    )
    frame_verified = capture.controller_flush_verified and not any(
        failure.kind == ObservationFailureKind.INCOMPLETE_FLUSH for failure in failures
    )
    completeness = (
        EffectStreamCompleteness.COMPLETE if not failures else EffectStreamCompleteness.INVALID
    )
    provenance = EffectTraceProvenance(
        PROTOCOL_ID,
        PROTOCOL_VERSION,
        _configuration_id(target, envelope["coverage"]),
        (_source(target),),
        target.event_bound,
        tuple(EntryLifecycleKind),
        sha256(capture.raw_stream).hexdigest(),
    )
    last_produced = terminal_last if type(terminal_last) is int else -1
    try:
        return EffectEventTrace(
            before,
            expected,
            tuple(lifecycle),
            tuple(effects),
            tuple(causal),
            (),
            after,
            completeness,
            _termination(capture.execution.status),
            provenance,
            last_produced,
            last_produced if frame_verified else None,
            last_produced if frame_verified else None,
            tuple(failures),
        )
    except ValueError as error:
        return _fallback_trace(
            capture,
            target,
            case,
            before,
            after,
            (
                *failures,
                _failure(
                    ObservationFailureKind.SOURCE_READER_DISAGREEMENT,
                    f"typed trace rejected producer evidence: {error}",
                ),
                _failure(ObservationFailureKind.INCOMPLETE_FLUSH, "typed trace not acknowledged"),
            ),
        )

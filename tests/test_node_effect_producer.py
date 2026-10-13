"""Contract tests for bounded native effect framing and conversion."""

import json
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

import inodefence.effect_pipeline as effect_pipeline_module
from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.effect_pipeline import NativeEffectRun, run_node_tar_effect_case
from inodefence.evaluation.native_effect_evidence import (
    export_native_effect_run,
    reconstruct_native_effect_trace,
    verify_native_effect_evidence,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.execution.base import BackendError, ContainerOutcome, ExecutionBackend
from inodefence.feedback import state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EffectClass,
    EffectRunResult,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    ObjectSnapshot,
    ObjectType,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
)
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance
from inodefence.observer import ObservationError, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.targets.node_tar_effect import (
    PROTOCOL_ID,
    PROTOCOL_VERSION,
    SOURCE_ID,
    NativeEffectCapture,
    NativeEffectProfile,
    NodeTarEffectTarget,
    _verify_transport_frame,
    effect_trace_from_capture,
)

IMAGE = "sha256:" + "a" * 64
DIGESTS = {
    "producer_sha256": "b" * 64,
    "package_lock_sha256": "c" * 64,
    "package_entrypoint_sha256": "d" * 64,
    "unpack_sha256": "e" * 64,
}


class ControlledBackend(ExecutionBackend):
    def validate_image(self, image_id):
        assert image_id == IMAGE

    def policy(self, image_id):  # pragma: no cover - unused protocol member
        raise AssertionError("not used")

    def capture_isolation(self, image_id):  # pragma: no cover - unused protocol member
        raise AssertionError("not used")

    @contextmanager
    def prepare(self, request):  # pragma: no cover - binding tests provide a subclass
        raise AssertionError("not used")
        yield


def _target(
    profile: NativeEffectProfile = NativeEffectProfile.FULL, event_bound: int = 64
) -> NodeTarEffectTarget:
    return NodeTarEffectTarget(
        ControlledBackend(),
        IMAGE,
        "22.22.0",
        "7.5.22",
        DIGESTS["producer_sha256"],
        DIGESTS["package_lock_sha256"],
        DIGESTS["package_entrypoint_sha256"],
        DIGESTS["unpack_sha256"],
        profile,
        event_bound,
    )


def _object(
    path: str,
    *,
    inode: int,
    kind: str = "regular",
    digest: str | None = None,
    mode: int = 0o644,
    size: int = 1,
    link_target: str | None = None,
) -> dict:
    return {
        "path": path,
        "object_type": kind,
        "st_dev": "1",
        "st_ino": str(inode),
        "st_nlink": "2" if inode == 20 else "1",
        "mode": mode,
        "size": str(size),
        "uid": "1000",
        "gid": "1000",
        "mtime_ns": "1",
        "ctime_ns": "1",
        "symlink_target": link_target,
        "content_digest": digest if kind == "regular" else None,
    }


def _observed(path: str, obj: dict | None) -> dict:
    return {
        "path": path,
        "observation": {
            "status": "present" if obj is not None else "absent",
            "object": obj,
            "error": None,
        },
    }


def _identity(index: int, path: str, kind: str = "File", link: str | None = None) -> dict:
    return {"ordinal": index, "path": path, "type": kind, "link_target": link}


def _lifecycle(sequence: int, identity: dict, kind: str) -> dict:
    return {
        "sequence": sequence,
        "source_id": SOURCE_ID,
        "record_type": "lifecycle",
        "record_id": f"entry-{identity['ordinal']}-{kind}",
        "entry": identity,
        "kind": kind,
        "observation": {"started_ns": str(sequence), "finished_ns": str(sequence)},
        "success": True,
        "error": None,
    }


def _operation(
    start_sequence: int,
    completion_sequence: int,
    identity: dict,
    operation: str,
    paths: list[str],
    before: list[dict],
    after: list[dict],
    *,
    association: str = "async_context",
    work_sequence: int = 1,
    handle_sequence: int | None = None,
    success: bool = True,
) -> list[dict]:
    correlation = f"operation-{start_sequence}"
    return [
        {
            "sequence": start_sequence,
            "source_id": SOURCE_ID,
            "record_type": "operation_start",
            "record_id": f"{correlation}-start",
            "correlation_id": correlation,
            "operation": operation,
            "entry": identity,
            "association": association,
            "association_conflict": False,
            "context_start_sequence": work_sequence if association == "async_context" else None,
            "handle_origin_completion_sequence": handle_sequence,
            "paths": paths,
            "observation": {
                "started_ns": str(start_sequence),
                "finished_ns": str(start_sequence),
            },
            "object_observations": before,
            "detail": {
                "symlink_target": identity["link_target"] if operation == "symlink" else None,
                "open_flags": None,
            },
        },
        {
            "sequence": completion_sequence,
            "source_id": SOURCE_ID,
            "record_type": "operation_completion",
            "record_id": f"{correlation}-completion",
            "correlation_id": correlation,
            "operation": operation,
            "entry": identity,
            "association": association,
            "association_conflict": False,
            "start_sequence": start_sequence,
            "paths": paths,
            "observation": {
                "started_ns": str(completion_sequence),
                "finished_ns": str(completion_sequence),
            },
            "object_observations": after,
            "success": success,
            "error_code": None if success else "ENOENT",
            "error_message": None if success else "missing",
        },
    ]


def _frame(
    target: NodeTarEffectTarget,
    records: list[dict],
    *,
    outcome: str = "success",
    overflow: bool = False,
    dropped: int = 0,
    archive_sha256: str | None = None,
) -> bytes:
    record_bytes = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    envelope = {
        "format": PROTOCOL_ID,
        "schema_version": 1,
        "profile": target.profile.value,
        "event_bound": target.event_bound,
        "source": {
            "source_id": SOURCE_ID,
            "protocol_id": PROTOCOL_ID,
            "protocol_version": PROTOCOL_VERSION,
            "node_version": target.node_version,
            "tar_version": target.tar_version,
            "producer_sha256": target.producer_sha256,
            "package_lock_sha256": target.package_lock_sha256,
            "package_entrypoint": "/target/node_modules/tar/dist/commonjs/index.min.js",
            "package_entrypoint_sha256": target.package_entrypoint_sha256,
            "unpack_sha256": target.unpack_sha256,
        },
        "input": {"archive_sha256": archive_sha256 or sha256(b"fixture-archive").hexdigest()},
        "coverage": {
            "lifecycle_kinds": ["read", "effect_work_started", "effect_work_settled"],
            "operation_callbacks": []
            if target.profile == NativeEffectProfile.MINIMAL
            else [
                "open",
                "write",
                "writev",
                "close",
                "mkdir",
                "chmod",
                "chown",
                "utimes",
                "futimes",
                "fchown",
                "unlink",
                "rmdir",
                "link",
                "symlink",
                "rename",
                "rm",
            ],
            "effect_classes": {
                "namespace_creation": (
                    "supported_when_one correlated operation proves absent-to-present"
                ),
                "namespace_removal": (
                    "supported_when_one correlated operation proves present-to-absent"
                ),
                "namespace_replacement": (
                    "supported_when one correlated operation changes identity or type"
                ),
                "regular_file_content_modification": (
                    "supported by stable before/after content digests"
                ),
                "truncation": "supported by stable before/after regular-file sizes",
                "metadata_modification": ("supported by stable before/after metadata fields"),
                "symlink_creation": ("supported by absent-to-symlink evidence and raw link text"),
                "hardlink_identity_relation_creation": (
                    "supported by source/destination lstat identity evidence"
                ),
                "identity_relation_removal": (
                    "unsupported: no counterpart provenance for single-path removal"
                ),
            },
            "path_scope": ("sandbox-relative callback paths and proven descriptor-owner paths"),
            "observation_perturbation": (
                "synchronous lstat/content probes at callback request and completion boundaries"
                if target.profile == NativeEffectProfile.FULL
                else "entry lifecycle and async-context propagation only"
            ),
        },
        "target": {
            "outcome": outcome,
            "error": None
            if outcome == "success"
            else {"name": "Error", "code": "TAR_BAD_ARCHIVE", "message": "rejected"},
            "duration_ns": "10",
        },
        "records": records,
        "terminal": {
            "record_count": len(records),
            "last_produced_sequence": records[-1]["sequence"] if records else -1,
            "last_attempted_sequence": records[-1]["sequence"] if records else -1,
            "records_sha256": sha256(record_bytes).hexdigest(),
            "overflow": overflow,
            "dropped_records": dropped,
            "producer_failures": [],
            "flush": "synchronous_stdout_write",
        },
    }
    return (json.dumps(envelope, separators=(",", ":")) + "\n").encode()


def _snapshots(
    archive_sha256: str = sha256(b"fixture-archive").hexdigest(),
) -> tuple[StateSnapshot, StateSnapshot]:
    root = ObjectSnapshot(".", ObjectType.DIRECTORY, 1, 1, 1, 0o755, 0, 1000, 1000, 1, 1)
    sentinel = ObjectSnapshot(
        "outside/sentinel.txt",
        ObjectType.REGULAR,
        1,
        2,
        1,
        0o600,
        8,
        1000,
        1000,
        1,
        1,
        content_digest=sha256(b"sentinel").hexdigest(),
    )
    archive = ObjectSnapshot(
        "archive/input.tar",
        ObjectType.REGULAR,
        1,
        3,
        1,
        0o600,
        len(b"fixture-archive"),
        1000,
        1000,
        1,
        1,
        content_digest=archive_sha256,
    )
    return (
        StateSnapshot(
            "/var/lib/inodefence/core-run-test",
            SnapshotPhase.BEFORE,
            (root, archive, sentinel),
            ("outside/sentinel.txt",),
        ),
        StateSnapshot(
            "/var/lib/inodefence/core-run-test",
            SnapshotPhase.AFTER,
            (root, archive, sentinel),
            ("outside/sentinel.txt",),
        ),
    )


def _capture(
    target: NodeTarEffectTarget,
    raw: bytes,
    *,
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
    truncated: bool = False,
) -> NativeEffectCapture:
    try:
        archive_sha256 = json.loads(raw)["input"]["archive_sha256"]
    except (KeyError, TypeError, ValueError):
        archive_sha256 = sha256(b"fixture-archive").hexdigest()
    verified, error = _verify_transport_frame(raw, truncated, target, archive_sha256)
    exit_code = (
        None
        if status == ExecutionStatus.TIMED_OUT
        else 0
        if status == ExecutionStatus.SUCCESS
        else 2
    )
    execution = ExecutionResult(
        "node-tar-strict-effect-v2",
        target.provenance.target_version,
        target.command(
            Path("/var/lib/inodefence/core-run-test/archive/input.tar"),
            Path("/var/lib/inodefence/core-run-test/extract"),
        ),
        status,
        exit_code,
        raw.decode("utf-8", "surrogateescape"),
        "",
        0.1,
        10,
    )
    return NativeEffectCapture(execution, raw, truncated, verified, error, archive_sha256)


def test_regular_content_effect_has_exact_entry_correlation_and_causality() -> None:
    target = _target()
    identity = _identity(0, "file")
    empty = sha256(b"").hexdigest()
    content = sha256(b"content").hexdigest()
    records = [
        _lifecycle(0, identity, "read"),
        _lifecycle(1, identity, "effect_work_started"),
        *_operation(
            2,
            3,
            identity,
            "write",
            ["extract/file"],
            [_observed("extract/file", _object("extract/file", inode=10, digest=empty, size=0))],
            [_observed("extract/file", _object("extract/file", inode=10, digest=content, size=7))],
        ),
        _lifecycle(4, identity, "effect_work_settled"),
    ]
    case = ArchiveCase((ArchiveEntry("file", EntryType.REGULAR, b"content"),))
    before, after = _snapshots()
    trace = effect_trace_from_capture(
        _capture(target, _frame(target, records)), target, case, before, after
    )

    assert trace.integrity_valid
    assert trace.effect_events[0].effect_class == EffectClass.REGULAR_FILE_CONTENT_MODIFICATION
    assert [point.sequence for point in trace.observed_event_points()] == list(range(5))
    assert trace.causally_precedes(1, 3)


@pytest.mark.parametrize(
    ("case", "identity", "operation", "paths", "before_objects", "after_objects", "effect"),
    (
        (
            ArchiveCase(
                (
                    ArchiveEntry("source", EntryType.REGULAR, b"x"),
                    ArchiveEntry("hard", EntryType.HARDLINK, link_target="source"),
                )
            ),
            _identity(1, "hard", "Link", "source"),
            "link",
            ["extract/source", "extract/hard"],
            [_object("extract/source", inode=20, digest=sha256(b"x").hexdigest()), None],
            [
                _object("extract/source", inode=20, digest=sha256(b"x").hexdigest()),
                _object("extract/hard", inode=20, digest=sha256(b"x").hexdigest()),
            ],
            EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
        ),
        (
            ArchiveCase((ArchiveEntry("sym", EntryType.SYMLINK, link_target="source"),)),
            _identity(0, "sym", "SymbolicLink", "source"),
            "symlink",
            ["extract/sym"],
            [None],
            [
                _object(
                    "extract/sym",
                    inode=30,
                    kind="symlink",
                    size=6,
                    mode=0o777,
                    link_target="source",
                )
            ],
            EffectClass.SYMLINK_CREATION,
        ),
        (
            ArchiveCase((ArchiveEntry("directory", EntryType.DIRECTORY, mode=0o750),)),
            _identity(0, "directory", "Directory"),
            "chmod",
            ["extract/directory"],
            [_object("extract/directory", inode=40, kind="directory", mode=0o700)],
            [_object("extract/directory", inode=40, kind="directory", mode=0o750)],
            EffectClass.METADATA_MODIFICATION,
        ),
    ),
)
def test_class_specific_evidence_is_realized(
    case, identity, operation, paths, before_objects, after_objects, effect
) -> None:
    target = _target()
    work_sequence = 1
    records = [
        _lifecycle(0, identity, "read"),
        _lifecycle(work_sequence, identity, "effect_work_started"),
        *_operation(
            2,
            3,
            identity,
            operation,
            paths,
            [_observed(path, obj) for path, obj in zip(paths, before_objects, strict=True)],
            [_observed(path, obj) for path, obj in zip(paths, after_objects, strict=True)],
            work_sequence=work_sequence,
        ),
        _lifecycle(4, identity, "effect_work_settled"),
    ]
    # A complete success requires lifecycle coverage for every ArchiveCase member.
    if len(case.entries) == 2:
        first = _identity(0, "source")
        records = [
            _lifecycle(0, first, "read"),
            _lifecycle(1, first, "effect_work_started"),
            _lifecycle(2, first, "effect_work_settled"),
            _lifecycle(3, identity, "read"),
            _lifecycle(4, identity, "effect_work_started"),
            *_operation(
                5,
                6,
                identity,
                operation,
                paths,
                [_observed(path, obj) for path, obj in zip(paths, before_objects, strict=True)],
                [_observed(path, obj) for path, obj in zip(paths, after_objects, strict=True)],
                work_sequence=4,
            ),
            _lifecycle(7, identity, "effect_work_settled"),
        ]
    before, after = _snapshots()
    trace = effect_trace_from_capture(
        _capture(target, _frame(target, records)), target, case, before, after
    )
    assert trace.integrity_valid
    assert trace.effect_events[0].effect_class == effect


def test_out_of_order_completions_remain_observed_without_invented_dependency() -> None:
    target = _target()
    first = _identity(0, "a")
    second = _identity(1, "b")
    digest = sha256(b"").hexdigest()
    records = [
        _lifecycle(0, first, "read"),
        _lifecycle(1, first, "effect_work_started"),
        _lifecycle(2, second, "read"),
        _lifecycle(3, second, "effect_work_started"),
        *_operation(
            4,
            7,
            first,
            "close",
            ["extract/a"],
            [_observed("extract/a", _object("extract/a", inode=50, digest=digest))],
            [_observed("extract/a", _object("extract/a", inode=50, digest=digest))],
            work_sequence=1,
        ),
        *_operation(
            5,
            6,
            second,
            "close",
            ["extract/b"],
            [_observed("extract/b", _object("extract/b", inode=51, digest=digest))],
            [_observed("extract/b", _object("extract/b", inode=51, digest=digest))],
            work_sequence=3,
        ),
        _lifecycle(8, second, "effect_work_settled"),
        _lifecycle(9, first, "effect_work_settled"),
    ]
    records.sort(key=lambda record: record["sequence"])
    case = ArchiveCase(
        (
            ArchiveEntry("a", EntryType.REGULAR, b""),
            ArchiveEntry("b", EntryType.REGULAR, b""),
        )
    )
    before, after = _snapshots()
    trace = effect_trace_from_capture(
        _capture(target, _frame(target, records)), target, case, before, after
    )
    assert trace.integrity_valid
    assert [point.sequence for point in trace.observed_event_points()] == list(range(10))
    assert not trace.causally_precedes(6, 7)


def test_complete_rejected_prefix_is_retained_with_distinct_termination() -> None:
    target = _target()
    identity = _identity(0, "kept")
    records = [
        _lifecycle(0, identity, "read"),
        _lifecycle(1, identity, "effect_work_started"),
        _lifecycle(2, identity, "effect_work_settled"),
    ]
    case = ArchiveCase(
        (
            ArchiveEntry("kept", EntryType.REGULAR, b"x"),
            ArchiveEntry("bad", EntryType.HARDLINK, link_target="missing"),
        )
    )
    before, after = _snapshots()
    trace = effect_trace_from_capture(
        _capture(
            target,
            _frame(target, records, outcome="rejected"),
            status=ExecutionStatus.REJECTED,
        ),
        target,
        case,
        before,
        after,
    )
    assert trace.integrity_valid
    assert trace.completeness == EffectStreamCompleteness.COMPLETE
    assert trace.termination == EffectTargetTermination.REJECTED


@pytest.mark.parametrize("failure", ("gap", "duplicate", "overflow", "unmatched", "identity"))
def test_transport_and_association_failures_never_promote_a_trace(failure: str) -> None:
    target = _target()
    identity = _identity(0, "file")
    records = [
        _lifecycle(0, identity, "read"),
        _lifecycle(1, identity, "effect_work_started"),
        _lifecycle(2, identity, "effect_work_settled"),
    ]
    overflow = False
    dropped = 0
    if failure == "gap":
        records[2]["sequence"] = 3
    elif failure == "duplicate":
        records[2]["sequence"] = 1
    elif failure == "overflow":
        overflow, dropped = True, 1
    elif failure == "unmatched":
        records.insert(
            2,
            _operation(
                2,
                3,
                identity,
                "close",
                ["extract/file"],
                [_observed("extract/file", None)],
                [_observed("extract/file", None)],
            )[0],
        )
        records[-1]["sequence"] = 3
    else:
        records[0]["entry"] = _identity(0, "different")
    case = ArchiveCase((ArchiveEntry("file", EntryType.REGULAR, b"x"),))
    before, after = _snapshots()
    raw = _frame(target, records, overflow=overflow, dropped=dropped)
    trace = effect_trace_from_capture(_capture(target, raw), target, case, before, after)
    assert not trace.integrity_valid
    assert trace.completeness == EffectStreamCompleteness.INVALID
    assert trace.observation_failures


def test_timeout_and_truncated_transport_preserve_distinct_fail_closed_results() -> None:
    target = _target()
    case = ArchiveCase((ArchiveEntry("file", EntryType.REGULAR, b"x"),))
    before, after = _snapshots()
    timeout = effect_trace_from_capture(
        _capture(target, b"", status=ExecutionStatus.TIMED_OUT),
        target,
        case,
        before,
        after,
    )
    truncated = effect_trace_from_capture(
        _capture(target, b'{"prefix":', truncated=True), target, case, before, after
    )
    assert timeout.completeness == EffectStreamCompleteness.INCOMPLETE
    assert timeout.termination == EffectTargetTermination.TIMED_OUT
    assert truncated.completeness == EffectStreamCompleteness.INVALID
    assert truncated.termination == EffectTargetTermination.SUCCESS


def test_bind_and_command_pin_worker_lock_entrypoint_and_unpack_hashes() -> None:
    metadata = {
        "node_version": "22.22.0",
        "tar_version": "7.5.22",
        "package_entrypoint": "/target/node_modules/tar/dist/commonjs/index.min.js",
        **DIGESTS,
    }

    class BindingBackend(ControlledBackend):
        @contextmanager
        def prepare(self, request):
            class Prepared:
                def execute(self):
                    return ContainerOutcome(0, json.dumps(metadata).encode(), b"", 0, False)

            yield Prepared()

    target = NodeTarEffectTarget.bind(
        BindingBackend(), IMAGE, profile=NativeEffectProfile.MINIMAL, event_bound=32
    )
    command = target.command(
        Path("/var/lib/inodefence/core-run-test/archive/input.tar"),
        Path("/var/lib/inodefence/core-run-test/extract"),
    )
    assert command[-4:] == tuple(DIGESTS.values())
    assert target.profile == NativeEffectProfile.MINIMAL and target.event_bound == 32
    with pytest.raises(ValueError, match="event bound"):
        replace(target, event_bound=257)


def test_effect_image_provenance_conforms_to_shared_isolation_contract() -> None:
    metadata = {
        "node_version": "22.22.0",
        "tar_version": "7.5.22",
        "package_entrypoint": "/target/node_modules/tar/dist/commonjs/index.min.js",
        **DIGESTS,
    }

    class ProvenanceBackend(ControlledBackend):
        def capture_isolation(self, image_id):
            return IsolationProvenance(
                IsolationPolicy(image_id, 1000, 1000),
                "test-double",
                "test",
                "test",
                "linux",
                "amd64",
                "amd64",
            )

        @contextmanager
        def prepare(self, request):
            class Prepared:
                def execute(self):
                    return ContainerOutcome(0, json.dumps(metadata).encode(), b"", 0, False)

            yield Prepared()

    target = NodeTarEffectTarget.bind(ProvenanceBackend(), IMAGE)
    frozen = target.capture_isolation()
    assert frozen.policy.image_id == IMAGE
    assert frozen.artifact_origin == "image-identification-v1"
    assert {item.sha256 for item in frozen.artifacts} == set(DIGESTS.values())
    assert tuple(item.name for item in frozen.artifacts) == tuple(
        sorted(item.name for item in frozen.artifacts)
    )


def test_backend_failure_propagates_without_target_or_trace_classification() -> None:
    metadata = {
        "node_version": "22.22.0",
        "tar_version": "7.5.22",
        "package_entrypoint": "/target/node_modules/tar/dist/commonjs/index.min.js",
        **DIGESTS,
    }

    class FailingBackend(ControlledBackend):
        @contextmanager
        def prepare(self, request):
            class Prepared:
                def execute(self):
                    if "--identify" in request.command:
                        return ContainerOutcome(0, json.dumps(metadata).encode(), b"", 0, False)
                    raise BackendError("injected backend failure")

            yield Prepared()

    target = NodeTarEffectTarget.bind(FailingBackend(), IMAGE)
    case = ArchiveCase((ArchiveEntry("file", EntryType.REGULAR, b"x"),))
    with pytest.raises(BackendError, match="injected backend failure"):
        run_node_tar_effect_case(case, target)


def test_observer_failure_propagates_without_executing_or_inventing_a_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = {
        "node_version": "22.22.0",
        "tar_version": "7.5.22",
        "package_entrypoint": "/target/node_modules/tar/dist/commonjs/index.min.js",
        **DIGESTS,
    }
    target_executions: list[bool] = []

    class Prepared:
        def __init__(self, identify: bool) -> None:
            self.identify = identify

        def execute(self):
            if self.identify:
                return ContainerOutcome(0, json.dumps(metadata).encode(), b"", 0, False)
            target_executions.append(True)
            raise AssertionError("target must not execute after BEFORE observation failure")

    class BindingBackend(ControlledBackend):
        @contextmanager
        def prepare(self, request):
            yield Prepared("--identify" in request.command)

    def fail_observation(*_args, **_kwargs):
        raise ObservationError("injected observer failure")

    target = NodeTarEffectTarget.bind(BindingBackend(), IMAGE)
    case = ArchiveCase((ArchiveEntry("file", EntryType.REGULAR, b"x"),))
    monkeypatch.setattr(effect_pipeline_module, "capture_state", fail_observation)
    with pytest.raises(ObservationError, match="injected observer failure"):
        run_node_tar_effect_case(case, target)
    assert not target_executions


def test_raw_export_binds_exact_stream_and_refuses_overwrite(tmp_path) -> None:
    target = _target(NativeEffectProfile.MINIMAL)
    identity = _identity(0, "file")
    records = [
        _lifecycle(0, identity, "read"),
        _lifecycle(1, identity, "effect_work_started"),
        _lifecycle(2, identity, "effect_work_settled"),
    ]
    case = ArchiveCase((ArchiveEntry("file", EntryType.REGULAR, b"x"),))
    archive_sha256 = sha256(build_tar(case)).hexdigest()
    raw = _frame(target, records, archive_sha256=archive_sha256)
    capture = _capture(target, raw)
    before, after = _snapshots(archive_sha256)
    trace = effect_trace_from_capture(capture, target, case, before, after)
    base = RunResult(
        case,
        archive_sha256,
        BUILDER_FORMAT,
        capture.execution,
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )
    run = NativeEffectRun(EffectRunResult(base, trace), raw, archive_sha256, True, None)
    destination = tmp_path / "native-effect"

    manifest_sha256 = export_native_effect_run(run, destination)

    assert set(path.name for path in destination.iterdir()) == {
        "manifest.json",
        "raw-stream.json",
        "result.json",
    }
    assert (destination / "raw-stream.json").read_bytes() == raw
    assert manifest_sha256 == sha256((destination / "manifest.json").read_bytes()).hexdigest()
    verified = verify_native_effect_evidence(destination, expected_manifest_sha256=manifest_sha256)
    assert verified.result == run.result and verified.feedback_keys == ()
    with pytest.raises(FileExistsError):
        export_native_effect_run(run, destination)


def test_independent_reader_rejects_producer_trace_self_declaration(tmp_path) -> None:
    target = _target(NativeEffectProfile.MINIMAL)
    identity = _identity(0, "file")
    case = ArchiveCase((ArchiveEntry("file", EntryType.REGULAR, b"x"),))
    archive_sha256 = sha256(build_tar(case)).hexdigest()
    raw = _frame(
        target,
        [
            _lifecycle(0, identity, "read"),
            _lifecycle(1, identity, "effect_work_started"),
            _lifecycle(2, identity, "effect_work_settled"),
        ],
        archive_sha256=archive_sha256,
    )
    capture = _capture(target, raw)
    before, after = _snapshots(archive_sha256)
    trace = effect_trace_from_capture(capture, target, case, before, after)
    trace = replace(trace, provenance=replace(trace.provenance, configuration_id="0" * 64))
    base = RunResult(
        case,
        archive_sha256,
        BUILDER_FORMAT,
        capture.execution,
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )
    run = NativeEffectRun(EffectRunResult(base, trace), raw, archive_sha256, True, None)
    destination = tmp_path / "self-declared"
    export_native_effect_run(run, destination)
    with pytest.raises(VerificationError, match="independent raw reconstruction"):
        verify_native_effect_evidence(destination)


@pytest.mark.parametrize(
    "injection",
    (
        "missing_sequence",
        "duplicate_sequence",
        "overflow",
        "malformed_identity",
        "association_conflict",
        "unmatched_operation",
        "flush_mismatch",
        "source_disagreement",
    ),
)
def test_independent_reader_detects_failure_injections(injection: str) -> None:
    target = _target(NativeEffectProfile.MINIMAL)
    identity = _identity(0, "file")
    case = ArchiveCase((ArchiveEntry("file", EntryType.REGULAR, b"x"),))
    archive_sha256 = sha256(build_tar(case)).hexdigest()
    raw = _frame(
        target,
        [
            _lifecycle(0, identity, "read"),
            _lifecycle(1, identity, "effect_work_started"),
            _lifecycle(2, identity, "effect_work_settled"),
        ],
        archive_sha256=archive_sha256,
    )
    capture = _capture(target, raw)
    before, after = _snapshots(archive_sha256)
    trace = effect_trace_from_capture(capture, target, case, before, after)
    base = RunResult(
        case,
        archive_sha256,
        BUILDER_FORMAT,
        capture.execution,
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )
    result = EffectRunResult(base, trace)
    envelope = deepcopy(json.loads(raw))
    records = envelope["records"]
    if injection == "missing_sequence":
        records[2]["sequence"] = 3
    elif injection == "duplicate_sequence":
        records[2]["sequence"] = 1
    elif injection == "overflow":
        envelope["terminal"]["overflow"] = True
        envelope["terminal"]["dropped_records"] = 1
    elif injection == "malformed_identity":
        records[0]["entry"]["ordinal"] = "0"
    elif injection == "association_conflict":
        records[0]["entry"]["path"] = "other"
    elif injection == "unmatched_operation":
        records.append(
            _operation(
                3,
                4,
                identity,
                "close",
                ["extract/file"],
                [_observed("extract/file", None)],
                [_observed("extract/file", None)],
            )[0]
        )
    elif injection == "flush_mismatch":
        envelope["terminal"]["flush"] = "interrupted"
    else:
        envelope["source"]["producer_sha256"] = "f" * 64
    envelope["terminal"]["record_count"] = len(records)
    envelope["terminal"]["last_produced_sequence"] = records[-1]["sequence"]
    envelope["terminal"]["last_attempted_sequence"] = records[-1]["sequence"]
    record_bytes = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    envelope["terminal"]["records_sha256"] = sha256(record_bytes).hexdigest()
    injected = (json.dumps(envelope, separators=(",", ":")) + "\n").encode()

    with pytest.raises(VerificationError):
        reconstruct_native_effect_trace(injected, result)


def test_independent_reader_rejects_invalid_handle_causal_edge() -> None:
    target = _target(NativeEffectProfile.FULL)
    identity = _identity(0, "file")
    case = ArchiveCase((ArchiveEntry("file", EntryType.REGULAR, b""),))
    archive_sha256 = sha256(build_tar(case)).hexdigest()
    digest = sha256(b"").hexdigest()
    records = [
        _lifecycle(0, identity, "read"),
        _lifecycle(1, identity, "effect_work_started"),
        *_operation(
            2,
            3,
            identity,
            "close",
            ["extract/file"],
            [_observed("extract/file", _object("extract/file", inode=70, digest=digest))],
            [_observed("extract/file", _object("extract/file", inode=70, digest=digest))],
            handle_sequence=3,
        ),
        _lifecycle(4, identity, "effect_work_settled"),
    ]
    raw = _frame(target, records, archive_sha256=archive_sha256)
    capture = _capture(target, raw)
    before, after = _snapshots(archive_sha256)
    producer_trace = effect_trace_from_capture(capture, target, case, before, after)
    base = RunResult(
        case,
        archive_sha256,
        BUILDER_FORMAT,
        capture.execution,
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )
    result = EffectRunResult(base, producer_trace)
    with pytest.raises(VerificationError, match="handle-provenance"):
        reconstruct_native_effect_trace(raw, result)

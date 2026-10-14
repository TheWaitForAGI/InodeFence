"""Independent engine controls; constructed frames never qualify a native producer."""

import os
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.effect_pipeline import NativeEffectRun
from inodefence.evaluation.native_effect_evidence import (
    export_native_effect_run,
    reconstruct_native_effect_trace,
    verify_native_effect_evidence,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import effect_feedback_keys, state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EffectClass,
    EffectRunResult,
    EntryType,
    RunResult,
    SnapshotPhase,
    effect_is_realized,
)
from inodefence.observer import capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.targets.node_tar_effect import effect_trace_from_capture
from test_node_effect_producer import (
    _capture,
    _frame,
    _identity,
    _lifecycle,
    _object,
    _observed,
    _operation,
    _snapshots,
    _target,
)

CASE = ArchiveCase((ArchiveEntry("file", EntryType.REGULAR, b"later"),))
STAT_TEXT_FIELDS = ("st_dev", "st_ino", "st_nlink", "size", "uid", "gid", "mtime_ns", "ctime_ns")


def _records(operation, paths, before, after):
    identity = _identity(0, "file")
    return [
        _lifecycle(0, identity, "read"),
        _lifecycle(1, identity, "effect_work_started"),
        *_operation(2, 3, identity, operation, paths, before, after),
        _lifecycle(4, identity, "effect_work_settled"),
    ]


def _run(records, snapshots=None):
    target = _target()
    digest = sha256(build_tar(CASE)).hexdigest()
    raw = _frame(target, records, archive_sha256=digest)
    capture = _capture(target, raw)
    before, after = snapshots or _snapshots(digest)
    root = Path(before.sandbox_root)
    capture = replace(
        capture,
        execution=replace(
            capture.execution, command=target.command(root / "archive/input.tar", root / "extract")
        ),
    )
    trace = effect_trace_from_capture(capture, target, CASE, before, after)
    base = RunResult(
        CASE,
        digest,
        BUILDER_FORMAT,
        capture.execution,
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )
    return NativeEffectRun(EffectRunResult(base, trace), raw, digest, True, None)


def _snapshot_observation(snapshot, path):
    obj = next((item for item in snapshot.objects if item.path == path), None)
    raw = asdict(obj) if obj is not None else None
    if raw is not None:
        for field in STAT_TEXT_FIELDS:
            raw[field] = str(raw[field])
    return _observed(path, raw)


@pytest.mark.parametrize(
    ("action", "operation", "expected"),
    (
        ("content", "write", EffectClass.REGULAR_FILE_CONTENT_MODIFICATION),
        ("truncate", "open", EffectClass.TRUNCATION),
        ("replace", "rename", EffectClass.NAMESPACE_REPLACEMENT),
        ("type", "rename", EffectClass.NAMESPACE_REPLACEMENT),
    ),
)
def test_controlled_filesystem_effect_round_trips_through_reader(
    sandbox, tmp_path, action, operation, expected
):
    """Use real lstat evidence with synthetic transport/association, outside native gates."""
    sandbox.archive_path.write_bytes(build_tar(CASE))
    destination = sandbox.extraction_root / "file"
    destination.write_bytes(b"first")
    source = sandbox.extraction_root / "replacement"
    if action == "replace":
        source.write_bytes(b"later")
    elif action == "type":
        source.symlink_to("contained-target")
    before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
    if action == "content":
        with destination.open("r+b") as stream:
            stream.write(b"later")
    elif action == "truncate":
        with destination.open("r+b") as stream:
            stream.truncate(0)
    else:
        os.replace(source, destination)
    after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    paths = ["extract/replacement", "extract/file"] if operation == "rename" else ["extract/file"]
    run = _run(
        _records(
            operation,
            paths,
            [_snapshot_observation(before, path) for path in paths],
            [_snapshot_observation(after, path) for path in paths],
        ),
        (before, after),
    )
    event = run.result.trace.effect_events[0]
    assert event.effect_class == expected and effect_is_realized(event)
    evidence = event.object_evidence[0]
    assert evidence.before.object is not None and evidence.after.object is not None
    if action in ("content", "truncate"):
        assert evidence.before.object.identity == evidence.after.object.identity
    else:
        assert evidence.before.object.identity != evidence.after.object.identity
    if action == "type":
        assert evidence.before.object.object_type != evidence.after.object.object_type
    directory = tmp_path / "controlled-engine-evidence"
    manifest = export_native_effect_run(run, directory)
    verified = verify_native_effect_evidence(directory, expected_manifest_sha256=manifest)
    assert verified.result.trace == run.result.trace and verified.feedback_keys


def _positive_records():
    path = "extract/file"
    digest = sha256(b"x").hexdigest()
    return _records(
        "open",
        [path],
        [_observed(path, _object(path, inode=10, digest=digest))],
        [_observed(path, _object(path, inode=11, digest=digest))],
    )


def test_exact_bigint_identity_and_signed_timestamp_text_remain_supported():
    records = _positive_records()
    for index in (2, 3):
        obj = records[index]["object_observations"][0]["observation"]["object"]
        obj.update(st_dev=str(2**60 + 1), st_ino=str(2**60 + index), mtime_ns="-1")
    run = _run(records)
    reconstructed = reconstruct_native_effect_trace(run.raw_stream, run.result)
    assert reconstructed == run.result.trace and reconstructed.integrity_valid
    event = reconstructed.effect_events[0]
    assert event.effect_class == EffectClass.NAMESPACE_REPLACEMENT
    before, after = event.object_evidence[0].before.object, event.object_evidence[0].after.object
    assert before is not None and after is not None
    assert before.identity == (2**60 + 1, 2**60 + 2)
    assert after.identity == (2**60 + 1, 2**60 + 3)
    assert before.mtime_ns == after.mtime_ns == -1


@pytest.mark.parametrize("side", ("before", "after", "both"))
def test_success_without_observed_effect_evidence_never_creates_keys(side):
    records = _positive_records()
    for index in (2, 3) if side == "both" else (2,) if side == "before" else (3,):
        observation = records[index]["object_observations"][0]["observation"]
        observation.update(
            status="not_observed",
            object=None,
            error={"code": "EIO", "message": "control: missing evidence"},
        )
    run = _run(records)
    assert run.result.trace.integrity_valid
    reconstructed = reconstruct_native_effect_trace(run.raw_stream, run.result)
    assert reconstructed == run.result.trace
    assert reconstructed.effect_events[0].outcome.value == "succeeded"
    assert reconstructed.effect_events[0].effect_class == EffectClass.OPERATION_OBSERVED
    assert not effect_is_realized(reconstructed.effect_events[0])
    assert effect_feedback_keys(reconstructed) == ()


@pytest.mark.parametrize(
    "failure", ("missing_inode", "entry", "correlation", "association", "association_kind")
)
def test_invalid_identity_or_association_fails_closed_in_both_readers(failure):
    records = _positive_records()
    valid = _run(records)
    records = deepcopy(records)
    if failure == "missing_inode":
        del records[3]["object_observations"][0]["observation"]["object"]["st_ino"]
    elif failure == "entry":
        records[3]["entry"] = _identity(0, "wrong")
    elif failure == "correlation":
        records[3]["start_sequence"] = 1
    elif failure == "association":
        records[3]["association_conflict"] = True
    else:
        records[3]["association"] = "handle_provenance"
    invalid = _run(records)
    assert not invalid.result.trace.integrity_valid
    assert effect_feedback_keys(invalid.result.trace) == ()
    # Bind mutated stdout so the rejection exercises record validation, not stdout equality.
    reader_input = replace(valid.result, base_result=invalid.result.base_result)
    with pytest.raises(VerificationError):
        reconstruct_native_effect_trace(invalid.raw_stream, reader_input)


@pytest.mark.parametrize("field", STAT_TEXT_FIELDS)
@pytest.mark.parametrize("invalid_value", (True, 10.75))
@pytest.mark.parametrize("reader", ("adapter", "independent"))
def test_raw_stat_numbers_cannot_be_coerced_into_identity_or_effect_evidence(
    field, invalid_value, reader
):
    records = _positive_records()
    valid = _run(records)
    records[3]["object_observations"][0]["observation"]["object"][field] = invalid_value
    invalid = _run(records)
    if reader == "adapter":
        assert not invalid.result.trace.integrity_valid
        assert effect_feedback_keys(invalid.result.trace) == ()
    else:
        reader_input = replace(valid.result, base_result=invalid.result.base_result)
        with pytest.raises(VerificationError):
            reconstruct_native_effect_trace(invalid.raw_stream, reader_input)

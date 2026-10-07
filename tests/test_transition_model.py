import json
import os
from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.feedback import state_signature, transition_sequence_key, transition_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ArchiveEntryReference,
    ChangeField,
    EntryCheckpoint,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    ObjectSnapshot,
    ObjectType,
    ObservationCompleteness,
    ObservationKind,
    ObservationPoint,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
    TraceCompleteness,
    TraceTermination,
    TransitionRunResult,
    TransitionTrace,
    canonical_json,
    derive_transition,
)
from inodefence.observer import capture_checkpoint, capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.runtime import RuntimeSandbox


def _digest(value: bytes = b"x") -> str:
    return sha256(value).hexdigest()


def _object(
    path: str,
    *,
    kind: ObjectType = ObjectType.REGULAR,
    dev: int = 1,
    ino: int = 1,
    nlink: int = 1,
    mode: int = 0o644,
    size: int = 1,
    mtime: int = 1,
    ctime: int = 1,
    target: str | None = None,
    content: bytes = b"x",
) -> ObjectSnapshot:
    return ObjectSnapshot(
        path,
        kind,
        dev,
        ino,
        nlink,
        mode,
        size,
        1000,
        1000,
        mtime,
        ctime,
        target,
        _digest(content) if kind == ObjectType.REGULAR else None,
    )


def _checkpoint(
    index: int,
    objects: tuple[ObjectSnapshot, ...],
    entry: ArchiveEntryReference | None = None,
    *,
    root: str = "/var/lib/inodefence/core-run-transition",
    protected: tuple[str, ...] = ("outside/sentinel",),
    started: int = 10,
) -> EntryCheckpoint:
    point = ObservationPoint(
        ObservationKind.BEFORE if entry is None else ObservationKind.ENTRY_BOUNDARY,
        entry,
    )
    return EntryCheckpoint(
        index,
        point,
        root,
        tuple(sorted(objects, key=lambda obj: obj.path)),
        protected,
        started,
        started + 5,
    )


def _after(checkpoint: EntryCheckpoint) -> StateSnapshot:
    return StateSnapshot(
        checkpoint.sandbox_root,
        SnapshotPhase.AFTER,
        checkpoint.objects,
        checkpoint.protected_paths,
    )


def test_entry_reference_uses_ordinal_for_duplicate_paths() -> None:
    first = ArchiveEntryReference(0, "same", EntryType.REGULAR, None)
    second = ArchiveEntryReference(1, "same", EntryType.REGULAR, None)

    assert first != second
    with pytest.raises(ValueError, match="nonnegative"):
        replace(first, entry_index=-1)
    with pytest.raises(ValueError, match="link target"):
        ArchiveEntryReference(0, "same", EntryType.HARDLINK, None)


def test_checkpoint_validation_rejects_partial_transition_input() -> None:
    before = replace(_checkpoint(0, ()), completeness=ObservationCompleteness.INCOMPLETE)
    current = _checkpoint(1, (), ArchiveEntryReference(0, "a", EntryType.REGULAR, None))

    with pytest.raises(ValueError, match="incomplete observations"):
        derive_transition(before, current, 0)
    with pytest.raises(ValueError, match="timestamps"):
        replace(current, observation_finished_ns=current.observation_started_ns - 1)


def test_transition_records_hardlink_identity_relation_without_raw_identity_key() -> None:
    sentinel = _object("outside/sentinel", dev=7, ino=90)
    before = _checkpoint(0, (sentinel, _object("extract/a", dev=7, ino=10)))
    current = _checkpoint(
        1,
        (
            sentinel,
            _object("extract/a", dev=7, ino=10, nlink=2),
            _object("extract/b", dev=7, ino=10, nlink=2),
        ),
        ArchiveEntryReference(0, "b", EntryType.HARDLINK, "a"),
    )

    transition = derive_transition(before, current, 0)

    assert transition.identity_groups_created == (("extract/a", "extract/b"),)
    assert {change.path: change.fields for change in transition.changes} == {
        "extract/a": (ChangeField.NLINK,),
        "extract/b": (ChangeField.EXISTENCE,),
    }
    encoded = canonical_json(transition_signature(transition))
    assert '"st_dev"' not in encoded and '"st_ino"' not in encoded
    assert '"identity_relation_effects"' in encoded


def test_symlink_target_and_object_replacement_are_exact_raw_transition_evidence() -> None:
    before = _checkpoint(
        0,
        (
            _object(
                "extract/link",
                kind=ObjectType.SYMLINK,
                ino=20,
                mode=0o777,
                size=1,
                target="a",
            ),
            _object("extract/item", ino=30),
        ),
    )
    current = _checkpoint(
        1,
        (
            _object(
                "extract/link",
                kind=ObjectType.SYMLINK,
                ino=20,
                mode=0o777,
                size=1,
                target="b",
            ),
            _object("extract/item", kind=ObjectType.DIRECTORY, ino=31, mode=0o755),
        ),
        ArchiveEntryReference(0, "item", EntryType.DIRECTORY, None),
    )

    changes = {
        change.path: change.fields for change in derive_transition(before, current, 0).changes
    }

    assert changes["extract/link"] == (ChangeField.SYMLINK_TARGET,)
    assert changes["extract/item"] == (
        ChangeField.OBJECT_TYPE,
        ChangeField.IDENTITY,
        ChangeField.MODE,
        ChangeField.CONTENT,
    )


def test_transition_signature_normalizes_external_effect_values_and_timing() -> None:
    trigger = ArchiveEntryReference(0, "a", EntryType.REGULAR, None)

    def observed(dev: int, ino: int, timestamp: int, path: str) -> tuple[EntryCheckpoint, ...]:
        old = _object(path, dev=dev, ino=ino, content=b"old", mtime=timestamp, ctime=timestamp)
        new = _object(
            path,
            dev=dev + 1,
            ino=ino + 1,
            content=b"new",
            mtime=timestamp + 8,
            ctime=timestamp + 9,
        )
        return (
            _checkpoint(0, (old,), protected=(path,), started=timestamp),
            _checkpoint(1, (new,), trigger, protected=(path,), started=timestamp + 100),
        )

    first_pair = observed(1, 10, 1000, "outside/sentinel")
    second_pair = observed(9, 99, 9000, "outside/other")
    first = derive_transition(first_pair[0], first_pair[1], 0)
    second = derive_transition(second_pair[0], second_pair[1], 0)

    assert transition_signature(first) == transition_signature(second)
    signature_json = canonical_json(transition_signature(first))
    for excluded in ("st_dev", "st_ino", "observation_started_ns", "9000", "9100"):
        assert excluded not in signature_json
    assert transition_signature(first).protected_external_effect


def test_trace_enforces_order_transition_correspondence_and_reconciliation() -> None:
    initial = _checkpoint(0, ())
    first = _checkpoint(1, (), ArchiveEntryReference(0, "same", EntryType.REGULAR, None))
    second = _checkpoint(2, (), ArchiveEntryReference(1, "same", EntryType.REGULAR, None))
    transitions = (derive_transition(initial, first, 0), derive_transition(first, second, 1))

    trace = TransitionTrace(
        2,
        (initial, first, second),
        transitions,
        _after(second),
        TraceCompleteness.COMPLETE,
        TraceTermination.SUCCESS,
    )

    assert trace.reconciled
    assert transition_sequence_key(trace).keys == tuple(transition_sequence_key(trace).keys)
    with pytest.raises(ValueError, match="strictly monotonic"):
        replace(
            trace,
            checkpoints=(initial, first, replace(second, point=first.point)),
        )
    with pytest.raises(ValueError, match="labeled incomplete"):
        replace(trace, completeness=TraceCompleteness.INCOMPLETE)


def test_synthetic_target_sequence_captures_file_link_and_replacement(
    sandbox: RuntimeSandbox,
) -> None:
    entries = (
        ArchiveEntry("a", EntryType.REGULAR, content=b"one"),
        ArchiveEntry("b", EntryType.HARDLINK, link_target="a"),
        ArchiveEntry("a", EntryType.DIRECTORY),
    )
    checkpoints = [
        capture_checkpoint(
            sandbox.root,
            0,
            ObservationPoint(ObservationKind.BEFORE),
            sandbox.protected_paths,
        )
    ]
    (sandbox.extraction_root / "a").write_bytes(b"one")
    checkpoints.append(
        capture_checkpoint(
            sandbox.root,
            1,
            ObservationPoint(
                ObservationKind.ENTRY_BOUNDARY,
                ArchiveEntryReference(0, "a", EntryType.REGULAR, None),
            ),
            sandbox.protected_paths,
        )
    )
    os.link(sandbox.extraction_root / "a", sandbox.extraction_root / "b")
    checkpoints.append(
        capture_checkpoint(
            sandbox.root,
            2,
            ObservationPoint(
                ObservationKind.ENTRY_BOUNDARY,
                ArchiveEntryReference(1, "b", EntryType.HARDLINK, "a"),
            ),
            sandbox.protected_paths,
        )
    )
    (sandbox.extraction_root / "a").unlink()
    (sandbox.extraction_root / "a").mkdir()
    checkpoints.append(
        capture_checkpoint(
            sandbox.root,
            3,
            ObservationPoint(
                ObservationKind.ENTRY_BOUNDARY,
                ArchiveEntryReference(2, "a", EntryType.DIRECTORY, None),
            ),
            sandbox.protected_paths,
        )
    )
    after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    transitions = tuple(
        derive_transition(checkpoints[index], checkpoints[index + 1], index) for index in range(3)
    )
    trace = TransitionTrace(
        len(entries),
        tuple(checkpoints),
        transitions,
        after,
        TraceCompleteness.COMPLETE,
        TraceTermination.SUCCESS,
    )

    assert trace.checkpoints[2].identity_groups() == (("extract/a", "extract/b"),)
    replacement = {change.path: change for change in trace.transitions[2].changes}["extract/a"]
    assert ChangeField.OBJECT_TYPE in replacement.fields
    assert json.loads(canonical_json(trace))["schema_version"] == 1


def test_transition_run_result_composes_without_changing_run_result_shape(
    sandbox: RuntimeSandbox,
) -> None:
    case = ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, content=b"x"),))
    before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
    initial = EntryCheckpoint(
        0,
        ObservationPoint(ObservationKind.BEFORE),
        before.sandbox_root,
        before.objects,
        before.protected_paths,
        1,
        2,
    )
    (sandbox.extraction_root / "a").write_bytes(b"x")
    checkpoint = capture_checkpoint(
        sandbox.root,
        1,
        ObservationPoint(
            ObservationKind.ENTRY_BOUNDARY,
            ArchiveEntryReference(0, "a", EntryType.REGULAR, None),
        ),
        sandbox.protected_paths,
    )
    after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    trace = TransitionTrace(
        1,
        (initial, checkpoint),
        (derive_transition(initial, checkpoint, 0),),
        after,
        TraceCompleteness.COMPLETE,
        TraceTermination.SUCCESS,
    )
    run = RunResult(
        case,
        "0" * 64,
        "synthetic-v1",
        ExecutionResult("synthetic", "1", (), ExecutionStatus.SUCCESS, 0, "", "", 0.0),
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )

    composed = TransitionRunResult(run, trace)

    assert composed.base_result is run
    assert set(json.loads(canonical_json(run))["value"]) == {
        "case",
        "archive_sha256",
        "archive_format",
        "execution",
        "before",
        "after",
        "changes",
        "signature",
        "violations",
    }

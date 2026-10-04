"""Public evidence constructors reject mutable or falsely typed records."""

import json
from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.feedback import (
    ChangeFingerprint,
    Corpus,
    CorpusEntry,
    FeedbackDecision,
    IdentityFingerprint,
    ViolationFingerprint,
    state_signature,
    violation_fingerprints,
)
from inodefence.model import (
    ArchiveCase,
    ChangeField,
    ContractId,
    ExecutionResult,
    ExecutionStatus,
    ObjectSnapshot,
    ObjectType,
    RunResult,
    SnapshotPhase,
    StateChange,
    StateSnapshot,
    canonical_json,
)
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts


def regular() -> ObjectSnapshot:
    return ObjectSnapshot(
        "outside/sentinel.txt",
        ObjectType.REGULAR,
        1,
        10,
        1,
        0o600,
        4,
        1000,
        1000,
        10,
        10,
        content_digest=sha256(b"same").hexdigest(),
    )


def result() -> RunResult:
    sentinel = regular()
    before = StateSnapshot(
        "/var/lib/inodefence/synthetic", SnapshotPhase.BEFORE, (sentinel,), (sentinel.path,)
    )
    after = replace(before, phase=SnapshotPhase.AFTER)
    return RunResult(
        ArchiveCase(()),
        "a" * 64,
        "synthetic-test",
        ExecutionResult("controlled", "test", (), ExecutionStatus.SUCCESS, 0, "", "", 0.0),
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )


@pytest.mark.parametrize("value", (["a"] * 64, tuple("a" * 64), b"a" * 64, 7))
def test_observed_digest_requires_text(value: object) -> None:
    with pytest.raises(ValueError):
        replace(regular(), content_digest=value)


@pytest.mark.parametrize("value", (["target"], ("target",), b"target", 7))
def test_observed_symlink_target_requires_text(value: object) -> None:
    with pytest.raises(ValueError):
        replace(
            regular(), object_type=ObjectType.SYMLINK, content_digest=None, symlink_target=value
        )


@pytest.mark.parametrize("field", ("duration_seconds", "timeout_seconds"))
@pytest.mark.parametrize("value", (True, False, "1", [1]))
def test_execution_seconds_require_real_numeric_scalars(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        replace(result().execution, **{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("objects", []),
        ("objects", ("object",)),
        ("external_effects", []),
        ("external_effects", ("effect",)),
        ("identity_groups", []),
        ("identity_groups", (["extract/a", "extract/b"],)),
        ("identity_groups", (("extract/a", 1),)),
        ("protected_paths", []),
        ("protected_paths", (1,)),
        ("schema_version", True),
        ("schema_version", "3"),
        ("schema_version", 2),
        ("schema_version", 99),
    ],
)
def test_signature_requires_supported_schema_and_typed_tuples(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        replace(result().signature, **{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_digest", ["a"] * 64),
        ("object_type", "regular"),
        ("mode", True),
        ("st_nlink", True),
        ("size", []),
        ("path", ["outside/a"]),
    ],
)
def test_signature_object_validates_scalar_evidence(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        replace(result().signature.objects[0], **{field: value})


@pytest.mark.parametrize(
    "target",
    (
        ["literal:target"],
        ("literal:target",),
        b"literal:target",
        "target",
        "run:relative",
        "literal:",
        "run:/a\0b",
    ),
)
def test_signature_symlink_requires_valid_tagged_text(target: object) -> None:
    node = replace(
        result().signature.objects[0],
        object_type=ObjectType.SYMLINK,
        st_nlink=None,
        size=None,
        content_digest=None,
        symlink_target="run:",
    )
    with pytest.raises(ValueError):
        replace(node, symlink_target=target)


@pytest.mark.parametrize("value", ([ChangeField.MODE], ("mode",), ()))
def test_effect_and_change_fingerprint_require_typed_field_tuples(value: object) -> None:
    sentinel = regular()
    modified = replace(sentinel, mode=0o640)
    run = result()
    effect = state_signature(run.before, replace(run.after, objects=(modified,))).external_effects[
        0
    ]
    fingerprint = ChangeFingerprint(sentinel.path, (ChangeField.MODE,))
    for record in (effect, fingerprint):
        with pytest.raises(ValueError):
            replace(record, fields=value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case", []),
        ("archive_sha256", ["a"] * 64),
        ("archive_format", []),
        ("execution", []),
        ("before", []),
        ("after", []),
        ("signature", []),
        ("changes", []),
        ("changes", ("change",)),
        ("violations", []),
        ("violations", ("verdict",)),
    ],
)
def test_run_result_requires_immutable_typed_evidence(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        replace(result(), **{field: value})


def test_public_feedback_records_reject_mutable_nested_collections() -> None:
    run = result()
    change = ChangeFingerprint("outside/a", (ChangeField.EXISTENCE,))
    fingerprint = ViolationFingerprint(ContractId.C0, (change,))
    decision = FeedbackDecision(run.case.case_id, True, (fingerprint,), False)
    entry = CorpusEntry(run.case, run.signature, (fingerprint,))
    for record, field, value in (
        (fingerprint, "evidence", [change]),
        (fingerprint, "evidence", ("change",)),
        (fingerprint, "contract_id", "C0"),
        (decision, "new_violation_fingerprints", [fingerprint]),
        (decision, "new_violation_fingerprints", ("fingerprint",)),
        (decision, "state_novel", 1),
        (decision, "already_retained", []),
        (entry, "admission_violation_fingerprints", [fingerprint]),
        (entry, "admission_violation_fingerprints", ("fingerprint",)),
        (entry, "admission_signature", []),
        (entry, "case", []),
        (IdentityFingerprint("extract/a", "outside/a"), "internal_path", []),
    ):
        with pytest.raises(ValueError):
            replace(record, **{field: value})


def test_valid_produced_records_remain_hashable_and_serializable() -> None:
    run = result()
    corpus = Corpus()
    decision = corpus.consider(run)
    for record in (run, run.before, run.signature, decision, corpus.entries[0], corpus.stats):
        assert record == replace(record)
        assert hash(record) == hash(replace(record))
        assert canonical_json(record) == canonical_json(replace(record))
    assert json.loads(canonical_json(run.before))["value"]["objects"][0]["content_digest"] == (
        sha256(b"same").hexdigest()
    )
    assert violation_fingerprints(run.violations) == ()


@pytest.mark.parametrize(
    "fields", ((ChangeField.MODE,), (ChangeField.MODE, ChangeField.CONTENT), (ChangeField.CONTENT,))
)
def test_change_labels_must_match_all_actual_differences(fields: tuple[ChangeField, ...]) -> None:
    before = regular()
    after = replace(before, size=5, content_digest=sha256(b"other").hexdigest())
    with pytest.raises(ValueError, match="observations"):
        StateChange(before.path, before, after, fields)


def test_compare_states_produces_exact_change_and_existence_evidence() -> None:
    run = result()
    before = regular()
    after = replace(before, size=5, content_digest=sha256(b"other").hexdigest())
    exact = StateChange(before.path, before, after, (ChangeField.SIZE, ChangeField.CONTENT))
    assert compare_states(run.before, replace(run.after, objects=(after,))) == (exact,)
    for previous, current in ((None, before), (before, None)):
        change = StateChange(before.path, previous, current, (ChangeField.EXISTENCE,))
        old = replace(run.before, objects=() if previous is None else (previous,))
        new = replace(run.after, objects=() if current is None else (current,))
        assert compare_states(old, new) == (change,)
        with pytest.raises(ValueError):
            replace(change, fields=(ChangeField.EXISTENCE, ChangeField.CONTENT))
    assert compare_states(run.before, run.after) == ()
    with pytest.raises(ValueError):
        StateChange(before.path, before, after, (ChangeField.EXISTENCE,))

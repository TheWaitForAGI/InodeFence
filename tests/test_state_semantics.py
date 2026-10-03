import hashlib
from dataclasses import replace

import pytest

from inodefence.feedback import state_signature
from inodefence.model import (
    ChangeField,
    ContractId,
    IdentityEvidence,
    ObjectSnapshot,
    ObjectType,
    SnapshotPhase,
    StateChange,
    StateSnapshot,
    ViolationResult,
    canonical_json,
)
from inodefence.oracle import evaluate_contracts


def regular(path: str, inode: int, content: bytes = b"same", **changes: int) -> ObjectSnapshot:
    return ObjectSnapshot(
        path,
        ObjectType.REGULAR,
        changes.get("st_dev", 1),
        inode,
        changes.get("st_nlink", 1),
        changes.get("mode", 0o600),
        len(content),
        1000,
        1000,
        10,
        10,
        content_digest=hashlib.sha256(content).hexdigest(),
    )


def state(
    phase: SnapshotPhase, *objects: ObjectSnapshot, root: str = "/var/lib/inodefence/synthetic"
) -> StateSnapshot:
    return StateSnapshot(
        root, phase, tuple(sorted(objects, key=lambda obj: obj.path)), ("outside/sentinel.txt",)
    )


def test_safe_internal_hardlink_relation_is_not_a_violation() -> None:
    sentinel = regular("outside/sentinel.txt", 10)
    before = state(SnapshotPhase.BEFORE, sentinel)
    after = state(
        SnapshotPhase.AFTER,
        sentinel,
        regular("extract/a", 20, st_nlink=2),
        regular("extract/b", 20, st_nlink=2),
    )
    results = evaluate_contracts(before, after)
    assert tuple(r.contract_id for r in results) == (ContractId.C0, ContractId.C1, ContractId.C2)
    assert all(not r.violated and r.evidence == () and r.limitations for r in results)
    assert after.identity_groups() == (("extract/a", "extract/b"),)


def test_c1_requires_device_and_inode_equality_and_records_paths() -> None:
    sentinel = regular("outside/sentinel.txt", 10)
    before = state(SnapshotPhase.BEFORE, sentinel)
    internal = regular("extract/alias", 10)
    c1 = evaluate_contracts(before, state(SnapshotPhase.AFTER, sentinel, internal))[1]
    assert c1.violated
    assert c1.evidence == (IdentityEvidence("extract/alias", "outside/sentinel.txt", 1, 10),)
    different_device = replace(internal, st_dev=2)
    assert not evaluate_contracts(before, state(SnapshotPhase.AFTER, sentinel, different_device))[
        1
    ].violated
    symlink = ObjectSnapshot(
        "extract/sym",
        ObjectType.SYMLINK,
        1,
        30,
        1,
        0o777,
        23,
        1000,
        1000,
        10,
        10,
        "../outside/sentinel.txt",
    )
    assert not evaluate_contracts(before, state(SnapshotPhase.AFTER, sentinel, symlink))[1].violated


@pytest.mark.parametrize(
    "field",
    [
        ChangeField.MODE,
        ChangeField.SIZE,
        ChangeField.CONTENT,
        ChangeField.IDENTITY,
        ChangeField.NLINK,
        ChangeField.UID,
        ChangeField.GID,
        ChangeField.MTIME,
        ChangeField.CTIME,
    ],
)
def test_c2_each_selected_effect_is_evidence(field: ChangeField) -> None:
    sentinel = regular("outside/sentinel.txt", 10)
    before = state(SnapshotPhase.BEFORE, sentinel)
    if field == ChangeField.CONTENT:
        modified = regular(sentinel.path, 10, content=b"diff")
    elif field == ChangeField.IDENTITY:
        modified = replace(sentinel, st_ino=11)
    else:
        modified = replace(sentinel, **{field.value: getattr(sentinel, field.value) + 1})
    c2 = evaluate_contracts(before, state(SnapshotPhase.AFTER, modified))[2]
    assert c2.violated and len(c2.evidence) == 1
    evidence = c2.evidence[0]
    assert isinstance(evidence, StateChange)
    assert evidence.before == sentinel and evidence.after == modified and field in evidence.fields
    if field != ChangeField.IDENTITY:
        assert not evaluate_contracts(before, state(SnapshotPhase.AFTER, modified))[0].violated


def test_c0_namespace_and_c2_existence_and_replacement() -> None:
    sentinel = regular("outside/sentinel.txt", 10)
    before = state(SnapshotPhase.BEFORE, sentinel)
    results = evaluate_contracts(before, state(SnapshotPhase.AFTER))
    assert results[0].violated and results[2].violated
    replacement = regular(sentinel.path, 11)
    results = evaluate_contracts(before, state(SnapshotPhase.AFTER, replacement))
    assert results[0].violated and results[2].violated
    created = regular("outside/new", 40)
    results = evaluate_contracts(before, state(SnapshotPhase.AFTER, sentinel, created))
    assert results[0].violated and not results[2].violated


def test_oracle_requires_protected_baseline_and_matching_context() -> None:
    with pytest.raises(ValueError, match="initially existing"):
        evaluate_contracts(state(SnapshotPhase.BEFORE), state(SnapshotPhase.AFTER))
    sentinel = regular("outside/sentinel.txt", 10)
    before = state(SnapshotPhase.BEFORE, sentinel)
    with pytest.raises(ValueError, match="same run"):
        evaluate_contracts(before, state(SnapshotPhase.AFTER, sentinel, root="/different/run"))


def test_signature_is_stable_under_identity_relabeling_times_and_run_paths() -> None:
    sentinel = regular("outside/sentinel.txt", 10)
    before = state(SnapshotPhase.BEFORE, sentinel)
    after = state(
        SnapshotPhase.AFTER,
        replace(sentinel, st_nlink=2, ctime_ns=11),
        regular("extract/alias", 10, st_nlink=2),
        regular("extract/other", 20),
    )
    signature = state_signature(before, after)

    def relabel(snapshot: StateSnapshot) -> StateSnapshot:
        return replace(
            snapshot,
            sandbox_root="/var/lib/inodefence/another-run",
            objects=tuple(
                replace(
                    obj,
                    st_dev=91,
                    st_ino=1000 - obj.st_ino,
                    uid=500,
                    gid=500,
                    mtime_ns=obj.mtime_ns + 5000,
                    ctime_ns=obj.ctime_ns + 5000,
                )
                for obj in snapshot.objects
            ),
        )

    equivalent = state_signature(relabel(before), relabel(after))
    assert signature == equivalent
    assert canonical_json(signature) == canonical_json(equivalent)
    assert signature.identity_groups == (("extract/alias", "outside/sentinel.txt"),)
    assert signature.external_effects[0].fields == (ChangeField.NLINK, ChangeField.CTIME)
    text = canonical_json(signature)
    assert '"st_ino"' not in text and '"st_dev"' not in text
    assert '"mtime_ns":' not in text and '"ctime_ns":' not in text


def test_signature_distinguishes_relations_and_external_effects() -> None:
    sentinel = regular("outside/sentinel.txt", 10)
    before = state(SnapshotPhase.BEFORE, sentinel)
    alias = regular("extract/alias", 10)
    same = state(SnapshotPhase.AFTER, sentinel, alias)
    separate = state(SnapshotPhase.AFTER, sentinel, replace(alias, st_ino=20))
    assert state_signature(before, same) != state_signature(before, separate)
    changed = state(SnapshotPhase.AFTER, replace(sentinel, mode=0o644), alias)
    assert state_signature(before, same) != state_signature(before, changed)


def test_absolute_run_link_text_normalized_without_claiming_resolution() -> None:
    sentinel = regular("outside/sentinel.txt", 10)
    first_root, second_root = "/var/lib/inodefence/one", "/var/lib/inodefence/two"
    link = ObjectSnapshot(
        "extract/sym",
        ObjectType.SYMLINK,
        1,
        30,
        1,
        0o777,
        50,
        1000,
        1000,
        10,
        10,
        first_root + "/outside/../outside/sentinel.txt",
    )
    first = state_signature(
        state(SnapshotPhase.BEFORE, sentinel, root=first_root),
        state(SnapshotPhase.AFTER, sentinel, link, root=first_root),
    )
    second_link = replace(
        link, st_ino=31, size=51, symlink_target=second_root + "/outside/../outside/sentinel.txt"
    )
    second = state_signature(
        state(SnapshotPhase.BEFORE, sentinel, root=second_root),
        state(SnapshotPhase.AFTER, sentinel, second_link, root=second_root),
    )
    assert first == second
    assert first.objects[0].symlink_target == "$RUN/outside/../outside/sentinel.txt"


def test_evidence_boundary_rejects_contradictory_proof() -> None:
    sentinel = regular("outside/sentinel.txt", 10)
    with pytest.raises(ValueError, match="different observations"):
        StateChange(sentinel.path, sentinel, sentinel, (ChangeField.CONTENT,))
    with pytest.raises(ValueError, match="absent side"):
        StateChange(sentinel.path, None, sentinel, (ChangeField.CONTENT,))
    with pytest.raises(ValueError, match="match the changed path"):
        StateChange("outside/other", None, sentinel, (ChangeField.EXISTENCE,))
    with pytest.raises(ValueError, match="requires evidence"):
        ViolationResult(ContractId.C0, True, (), "missing proof", ())
    identity = IdentityEvidence("extract/a", sentinel.path, 1, 10)
    with pytest.raises(ValueError, match="evidence type"):
        ViolationResult(ContractId.C2, True, (identity,), "wrong evidence", ())
    with pytest.raises(ValueError, match="internal and external"):
        IdentityEvidence("outside/a", sentinel.path, 1, 10)

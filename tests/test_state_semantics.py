import hashlib
from dataclasses import replace

import pytest

from inodefence.feedback import state_signature
from inodefence.model import (
    ArchiveEntry,
    ChangeField,
    ContractId,
    EntryType,
    IdentityEvidence,
    ObjectSnapshot,
    ObjectType,
    Region,
    SnapshotPhase,
    StateChange,
    StateSnapshot,
    ViolationResult,
    canonical_json,
)
from inodefence.model.filesystem import is_extraction_path, path_region
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


@pytest.mark.parametrize(
    ("path", "region"),
    [
        ("extract", Region.EXTRACTION),
        ("extract/dir/a", Region.EXTRACTION),
        (".", Region.HARNESS),
        ("archive", Region.HARNESS),
        ("archive/input.tar", Region.HARNESS),
        ("archive/nested/evidence", Region.HARNESS),
        ("outside", Region.EXTERNAL),
        ("outside/nested/sentinel", Region.EXTERNAL),
        ("escape.txt", Region.EXTERNAL),
        ("escaped/dir/a", Region.EXTERNAL),
        ("archive-other/input.tar", Region.EXTERNAL),
        ("extract-other/a", Region.EXTERNAL),
    ],
)
def test_region_ownership_includes_unreserved_external_paths(path: str, region: Region) -> None:
    assert path_region(path) == regular(path, 10).region == region
    assert is_extraction_path(path) == (region == Region.EXTRACTION)


@pytest.mark.parametrize("path", [".", "archive", "archive/input.tar", "extract", "extract/a"])
def test_harness_and_extraction_paths_cannot_be_protected_sentinels(path: str) -> None:
    with pytest.raises(ValueError, match="external sandbox paths"):
        replace(state(SnapshotPhase.BEFORE), protected_paths=(path,))
    with pytest.raises(ValueError, match="internal and external"):
        IdentityEvidence("extract/a", path, 1, 10)


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


def test_signature_projects_raw_identity_groups_and_drops_singletons() -> None:
    sentinel = regular("outside/sentinel.txt", 10, st_nlink=3)
    before = state(SnapshotPhase.BEFORE, sentinel)
    after = state(
        SnapshotPhase.AFTER,
        sentinel,
        regular("archive/input.tar", 10, st_nlink=3),
        regular("extract/alias", 10, st_nlink=3),
        regular("archive/other", 20, st_nlink=2),
        regular("extract/single", 20, st_nlink=2),
        regular("archive/harness-a", 30, st_nlink=2),
        regular("archive/harness-b", 30, st_nlink=2),
    )
    assert len(after.identity_groups()) == 3  # Raw evidence retains all aliases.
    signature = state_signature(before, after)
    assert signature.schema_version == 3
    assert signature.identity_groups == (("extract/alias", "outside/sentinel.txt"),)
    paths = {obj.path for obj in signature.objects}
    assert paths == {"extract/alias", "extract/single", "outside/sentinel.txt"}
    assert all(path in paths for group in signature.identity_groups for path in group)


@pytest.mark.parametrize("path", ["extract/dir", "outside/dir"])
def test_signature_normalizes_directory_nlink_but_keeps_regular_hardlink_count(path: str) -> None:
    sentinel = regular("outside/sentinel.txt", 10)
    directory = replace(regular(path, 20), object_type=ObjectType.DIRECTORY, content_digest=None)
    before = state(SnapshotPhase.BEFORE, sentinel, directory)
    after = state(SnapshotPhase.AFTER, sentinel, directory)
    other_directory = replace(directory, st_nlink=7, size=4096)
    equivalent_before = state(SnapshotPhase.BEFORE, sentinel, other_directory)
    equivalent_after = state(SnapshotPhase.AFTER, sentinel, other_directory)
    assert directory.st_nlink != other_directory.st_nlink  # Raw counts are still available.
    signature = state_signature(before, after)
    equivalent = state_signature(equivalent_before, equivalent_after)
    assert signature == equivalent and canonical_json(signature) == canonical_json(equivalent)
    node = next(obj for obj in signature.objects if obj.path == path)
    assert node.st_nlink is None and node.size is None
    # Regular-file counts remain meaningful even if the second alias is unobserved.
    extra_link = state(SnapshotPhase.AFTER, replace(sentinel, st_nlink=2), directory)
    assert state_signature(before, extra_link) != signature


def test_directory_nlink_change_remains_raw_external_effect_and_c2_evidence() -> None:
    directory = replace(
        regular("outside/dir", 10), object_type=ObjectType.DIRECTORY, content_digest=None
    )
    before = replace(state(SnapshotPhase.BEFORE, directory), protected_paths=(directory.path,))
    after = replace(before, phase=SnapshotPhase.AFTER, objects=(replace(directory, st_nlink=2),))
    c0, c1, c2 = evaluate_contracts(before, after)
    assert not c0.violated and not c1.violated and c2.violated
    assert isinstance(c2.evidence[0], StateChange)
    assert c2.evidence[0].fields == (ChangeField.NLINK,)
    signature = state_signature(before, after)
    assert signature.objects[0].st_nlink is None
    assert signature.external_effects[0].fields == (ChangeField.NLINK,)


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
    assert first.objects[0].symlink_target == "run:/outside/../outside/sentinel.txt"


@pytest.mark.parametrize("suffix", ("", "/outside/sentinel.txt", "//outside/../sentinel.txt"))
def test_signature_distinguishes_run_anchor_from_literal_target(suffix: str) -> None:
    root = "/var/lib/inodefence/synthetic"
    sentinel = regular("outside/sentinel.txt", 10)
    before = state(SnapshotPhase.BEFORE, sentinel, root=root)
    link = ObjectSnapshot(
        "extract/sym",
        ObjectType.SYMLINK,
        1,
        30,
        1,
        0o777,
        0,
        1000,
        1000,
        10,
        10,
        symlink_target=root + suffix,
    )
    absolute = state(SnapshotPhase.AFTER, sentinel, link, root=root)
    signature = state_signature(before, absolute)
    assert signature.schema_version == 3
    assert signature.objects[0].symlink_target == "run:" + suffix
    for raw in ("$RUN" + suffix, "run:" + suffix, "literal:" + suffix, root + "-other" + suffix):
        literal = state(SnapshotPhase.AFTER, sentinel, replace(link, symlink_target=raw), root=root)
        other = state_signature(before, literal)
        assert signature != other
        assert canonical_json(signature) != canonical_json(other)
        assert other.objects[0].symlink_target == "literal:" + raw
        assert literal.get(link.path) == replace(link, symlink_target=raw)
    assert absolute.get(link.path) == link
    # Normalize only the allocation prefix; redundant separators/dot components stay raw.
    new_root = root + "-new"
    renamed = state_signature(
        replace(before, sandbox_root=new_root),
        replace(
            absolute,
            sandbox_root=new_root,
            objects=(replace(link, symlink_target=new_root + suffix), sentinel),
        ),
    )
    assert renamed == signature


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


@pytest.mark.parametrize("path", ["../outside", "/foo/bar", "a/../../b", "a//b", "./a"])
def test_archive_input_path_and_observed_path_are_different_domains(path: str) -> None:
    entry = ArchiveEntry(path, EntryType.SYMLINK, link_target=path)
    assert entry.path == entry.link_target == path
    observed = regular("extract/a", 20)
    with pytest.raises(ValueError, match="observed paths"):
        replace(observed, path=path)


@pytest.mark.parametrize("field", ["st_dev", "st_ino", "st_nlink", "size", "uid", "gid"])
@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_observed_stat_facts_require_nonnegative_integers(field: str, value: object) -> None:
    with pytest.raises(ValueError, match="nonnegative integers"):
        replace(regular("extract/a", 20), **{field: value})


@pytest.mark.parametrize("mode", [-1, 0o100644, True])
def test_observed_mode_is_permission_and_special_bits_only(mode: int) -> None:
    with pytest.raises(ValueError, match="permission mask"):
        replace(regular("extract/a", 20), mode=mode)


@pytest.mark.parametrize(
    "digest", [None, "", "arbitrary hash", "A" * 64, "x" * 64, "0" * 63, "0" * 65]
)
def test_regular_content_digest_requires_lowercase_sha256(digest: str | None) -> None:
    with pytest.raises(ValueError, match="content digest|SHA-256"):
        replace(regular("extract/a", 20), content_digest=digest)


@pytest.mark.parametrize("kind", [ObjectType.DIRECTORY, ObjectType.SYMLINK, ObjectType.OTHER])
def test_observed_type_requires_matching_link_and_digest_evidence(kind: ObjectType) -> None:
    observed = regular("extract/a", 20)
    with pytest.raises(ValueError):
        replace(observed, object_type=kind)
    with pytest.raises(ValueError, match="symlink target"):
        replace(observed, symlink_target="../outside/sentinel.txt")

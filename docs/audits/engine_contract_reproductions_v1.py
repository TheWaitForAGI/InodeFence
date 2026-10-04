"""Benign audit observations at fae2954, not intended post-fix regression assertions.

Run explicitly with pytest. No extractor, container or vulnerable target executes.
TARs exist only in memory and contain inert entries; filesystem work uses only
disposable runtime sentinels. Some assertions document defects as observed; the
audit specifies the opposite acceptance criteria for subsequent fix contracts.
"""

import io
import os
import tarfile
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from typing import cast

import pytest

from inodefence.builder import build_tar
from inodefence.execution.base import ExecutionBackend
from inodefence.feedback import state_signature, violation_fingerprints
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ChangeField,
    ContractId,
    EntryType,
    ObjectSnapshot,
    ObjectType,
    SnapshotPhase,
    StateChange,
    StateSignature,
    StateSnapshot,
    ViolationResult,
)
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance
from inodefence.observer import capture_state
from inodefence.oracle import evaluate_contracts
from inodefence.provenance import freeze_provenance
from inodefence.runtime import SentinelSpec, disposable_sandbox
from inodefence.targets.isolated import IsolatedTarget
from inodefence.targets.node_tar import NodeTarTarget


def _regular(path: str = "outside/sentinel.txt", inode: int = 10) -> ObjectSnapshot:
    return ObjectSnapshot(
        path,
        ObjectType.REGULAR,
        1,
        inode,
        1,
        0o600,
        4,
        1000,
        1000,
        10,
        10,
        content_digest=sha256(b"same").hexdigest(),
    )


@pytest.mark.parametrize("kind", tuple(EntryType))
@pytest.mark.parametrize(
    "path", ("/" + "a" * 100, "//" + "a" * 99, "/dir/" + "a" * 96, "/" + "é" * 50)
)
def test_en001_long_absolute_member_loses_one_leading_slash(kind: EntryType, path: str) -> None:
    entry = ArchiveEntry(
        path,
        kind,
        content=b"benign" if kind == EntryType.REGULAR else None,
        link_target="benign" if kind in (EntryType.HARDLINK, EntryType.SYMLINK) else None,
    )
    encoded = build_tar(ArchiveCase((entry,)))
    assert len(path.encode("utf-8")) == 101
    assert encoded[345:500].split(b"\0", 1)[0] == b""
    assert encoded[:100].split(b"\0", 1)[0] == path[1:].encode("utf-8")
    with tarfile.open(fileobj=io.BytesIO(encoded), mode="r:") as archive:
        assert archive.getmembers()[0].name == path[1:]
    # Logical input identity changes while the emitted archive stays identical.
    shortened = replace(entry, path=path[1:])
    assert ArchiveCase((entry,)).case_id != ArchiveCase((shortened,)).case_id
    assert encoded == build_tar(ArchiveCase((shortened,)))


@pytest.mark.parametrize("path", ("/" + "a" * 99, "a/" + "b" * 100, "x" * 155 + "/" + "y" * 100))
def test_en001_adjacent_supported_member_paths_preserve_spelling(path: str) -> None:
    encoded = build_tar(ArchiveCase((ArchiveEntry(path, EntryType.REGULAR, content=b""),)))
    with tarfile.open(fileobj=io.BytesIO(encoded), mode="r:") as archive:
        assert archive.getmembers()[0].name == path


@pytest.mark.parametrize("kind", (EntryType.HARDLINK, EntryType.SYMLINK))
def test_en001_adjacent_linkname_limit_rejects_instead_of_normalizing(kind: EntryType) -> None:
    with pytest.raises(ValueError, match="USTAR"):
        build_tar(ArchiveCase((ArchiveEntry("benign", kind, link_target="/" + "a" * 100),)))


def test_en002_mutable_digest_and_derived_signature_are_accepted() -> None:
    digest = ["a"] * 64
    observed = replace(_regular(), content_digest=cast(str, digest))
    digest[0] = "b"
    assert observed.content_digest is digest and observed.content_digest[0] == "b"
    objects: list = []
    signature = StateSignature(2, cast(tuple, objects), (), (), ())
    objects.append("not-a-signature-object")
    assert signature.objects is objects and len(signature.objects) == 1
    with pytest.raises(TypeError):
        hash(signature)


def test_en003_changed_field_labels_need_not_match_the_raw_values() -> None:
    before = _regular()
    after = replace(before, content_digest=sha256(b"diff").hexdigest())
    change = StateChange(before.path, before, after, (ChangeField.MODE,))
    assert change.fields == (ChangeField.MODE,)
    assert before.mode == after.mode and before.content_digest != after.content_digest


def test_en004_literal_relative_placeholder_collides_with_absolute_run_target() -> None:
    root = "/var/lib/inodefence/synthetic"
    sentinel = _regular()
    before = StateSnapshot(root, SnapshotPhase.BEFORE, (sentinel,), (sentinel.path,))
    link = ObjectSnapshot(
        "extract/link",
        ObjectType.SYMLINK,
        1,
        20,
        1,
        0o777,
        0,
        1000,
        1000,
        10,
        10,
        root + "/outside/sentinel.txt",
    )
    absolute = replace(before, phase=SnapshotPhase.AFTER, objects=(link, sentinel))
    relative = replace(
        absolute, objects=(replace(link, symlink_target="$RUN/outside/sentinel.txt"), sentinel)
    )
    assert absolute != relative
    assert state_signature(before, absolute) == state_signature(before, relative)
    other = replace(
        absolute,
        objects=(replace(link, symlink_target="$RUN-other/outside/sentinel.txt"), sentinel),
    )
    assert state_signature(before, absolute) != state_signature(before, other)


def test_en008_content_digest_changes_key_without_changing_relations() -> None:
    sentinel = _regular()
    before = StateSnapshot(
        "/var/lib/inodefence/synthetic", SnapshotPhase.BEFORE, (sentinel,), (sentinel.path,)
    )
    file = _regular("extract/benign", inode=20)
    first = replace(before, phase=SnapshotPhase.AFTER, objects=(file, sentinel))
    second = replace(
        first, objects=(replace(file, content_digest=sha256(b"diff").hexdigest()), sentinel)
    )
    assert first.identity_groups() == second.identity_groups() == ()
    assert state_signature(before, first) != state_signature(before, second)
    assert all(not verdict.violated for verdict in evaluate_contracts(before, second))


def test_en009_creation_and_deletion_share_a_whole_contract_fingerprint() -> None:
    object = _regular("archive/benign")
    creation = StateChange(object.path, None, object, (ChangeField.EXISTENCE,))
    deletion = StateChange(object.path, object, None, (ChangeField.EXISTENCE,))
    created = ViolationResult(ContractId.C0, True, (creation,), "created", ())
    deleted = replace(created, evidence=(deletion,), explanation="deleted")
    assert creation != deletion
    assert violation_fingerprints((created,)) == violation_fingerprints((deleted,))


def test_c1_and_metadata_only_c2_use_real_benign_hardlink_evidence() -> None:
    with disposable_sandbox() as sandbox:
        sentinel = sandbox.root / sandbox.protected_paths[0]
        before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
        os.link(sentinel, sandbox.extraction_root / "benign-alias")
        after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
        c0, c1, c2 = evaluate_contracts(before, after)
        assert not c0.violated and c1.violated and c2.violated
        changed = c2.evidence[0]
        assert isinstance(changed, StateChange)
        assert ChangeField.NLINK in changed.fields and ChangeField.CONTENT not in changed.fields
        assert changed.before is not None and changed.after is not None
        assert changed.before.content_digest == changed.after.content_digest


class _MetadataOnlyBackend(ExecutionBackend):
    """No execution capability: this double permits only metadata capture."""

    def validate_image(self, image_id):
        assert image_id.startswith("sha256:")

    def policy(self, image_id):
        return IsolationPolicy(image_id, 1000, 1000)

    def capture_isolation(self, image_id):
        return IsolationProvenance(
            self.policy(image_id), "audit-double", "test", "test", "linux", "test", "test"
        )

    @contextmanager
    def prepare(self, request):
        raise AssertionError("this audit double must never execute")
        yield  # pragma: no cover


@pytest.mark.parametrize(
    "changed",
    (
        {"worker_sha256": "d" * 64},
        {"package_lock_sha256": "d" * 64},
        {"image_id": "sha256:" + "e" * 64},
    ),
)
def test_cr001_pre_freeze_descriptor_replacement_is_not_reidentified(changed, monkeypatch):
    metadata = {
        "node_version": "22.22.0",
        "tar_version": "7.5.22",
        "worker_sha256": "b" * 64,
        "package_lock_sha256": "c" * 64,
    }
    calls = []

    def identify(backend, image_id):
        calls.append(image_id)
        return metadata

    monkeypatch.setattr("inodefence.targets.node_tar._identify", identify)
    backend = _MetadataOnlyBackend()
    bound = NodeTarTarget.bind(backend, "sha256:" + "a" * 64)
    assert isinstance(bound.invocation, NodeTarTarget)
    replacement = IsolatedTarget(replace(bound.invocation, **changed), backend)
    captured = replacement.capture_isolation()
    frozen = freeze_provenance(replacement.provenance, (SentinelSpec(),), isolation=captured)
    assert frozen.isolation is captured
    assert captured.artifacts == replacement.invocation.artifacts
    assert captured.policy.image_id == replacement.invocation.image_id
    assert calls == ["sha256:" + "a" * 64]  # New declarations/image were not reidentified.

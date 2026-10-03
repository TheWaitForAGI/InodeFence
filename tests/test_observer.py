import hashlib
import os
from dataclasses import replace

import pytest

from inodefence.feedback import state_signature
from inodefence.model import ChangeField, ObjectType, SnapshotPhase, StateChange
from inodefence.observer import ObservationError, capture_state, compare_states
from inodefence.observer import snapshot as snapshot_module
from inodefence.oracle import evaluate_contracts
from inodefence.runtime import RuntimeSandbox, disposable_sandbox


def test_real_files_directories_hardlinks_and_digest(sandbox: RuntimeSandbox) -> None:
    root = sandbox.extraction_root
    (root / "dir").mkdir()
    file = root / "dir" / "a"
    file.write_bytes(b"\0\xffreal bytes")
    file.chmod(0o640)
    os.link(file, root / "b")
    state = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    a, b, directory = state.get("extract/dir/a"), state.get("extract/b"), state.get("extract/dir")
    assert a is not None and b is not None and directory is not None
    assert a.object_type == b.object_type == ObjectType.REGULAR
    assert directory.object_type == ObjectType.DIRECTORY
    assert a.identity == b.identity == (file.lstat().st_dev, file.lstat().st_ino)
    assert a.st_nlink == b.st_nlink == 2
    assert a.mode == 0o640 and a.size == len(b"\0\xffreal bytes")
    assert a.content_digest == b.content_digest == hashlib.sha256(b"\0\xffreal bytes").hexdigest()
    assert ("extract/b", "extract/dir/a") in state.identity_groups()
    assert directory.content_digest is None


def test_symlink_lstat_no_referent_read_or_directory_traversal(sandbox: RuntimeSandbox) -> None:
    with disposable_sandbox() as neighbor:
        target = neighbor.root / "outside"
        os.symlink(str(target), sandbox.extraction_root / "external-directory")
        os.symlink(str(target / "sentinel.txt"), sandbox.extraction_root / "external-file")
        os.symlink("missing", sandbox.extraction_root / "dangling")
        state = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
        for name in ("external-directory", "external-file", "dangling"):
            relative = f"extract/{name}"
            obj = state.get(relative)
            assert obj is not None
            link = sandbox.extraction_root / name
            assert obj.object_type == ObjectType.SYMLINK
            assert obj.identity == (link.lstat().st_dev, link.lstat().st_ino)
            assert obj.symlink_target == os.readlink(link)
            assert obj.content_digest is None
            assert not any(entry.path.startswith(relative + "/") for entry in state.objects)
        neighbor_sentinel = (target / "sentinel.txt").lstat()
        link_obj = state.get("extract/external-file")
        assert link_obj is not None
        assert link_obj.identity != (neighbor_sentinel.st_dev, neighbor_sentinel.st_ino)


def test_special_files_observed_without_opening(sandbox: RuntimeSandbox) -> None:
    os.mkfifo(sandbox.extraction_root / "fifo")
    state = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    fifo = state.get("extract/fifo")
    assert fifo is not None and fifo.object_type == ObjectType.OTHER
    assert fifo.content_digest is None


def test_before_after_creation_deletion_content_mode_and_identity(sandbox: RuntimeSandbox) -> None:
    root = sandbox.extraction_root
    (root / "deleted").write_bytes(b"old")
    (root / "changed").write_bytes(b"old")
    (root / "replaced").write_bytes(b"same")
    before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
    (root / "deleted").unlink()
    (root / "created").write_bytes(b"new")
    (root / "changed").write_bytes(b"new content")
    (root / "changed").chmod(0o600)
    # Retain the old inode under another internal name, avoiding inode reuse.
    (root / "replaced").rename(root / "retained")
    (root / "replaced").write_bytes(b"same")
    after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    changes = {change.path: change for change in compare_states(before, after)}
    assert changes["extract/deleted"].after is None
    assert changes["extract/created"].before is None
    assert changes["extract/created"].fields == (ChangeField.EXISTENCE,)
    assert {ChangeField.CONTENT, ChangeField.SIZE, ChangeField.MODE}.issubset(
        changes["extract/changed"].fields
    )
    assert ChangeField.IDENTITY in changes["extract/replaced"].fields
    assert ChangeField.CONTENT not in changes["extract/replaced"].fields
    assert not any(result.violated for result in evaluate_contracts(before, after))
    with pytest.raises(ValueError, match="same run"):
        compare_states(before, replace(after, sandbox_root="/another/run"))
    with pytest.raises(ValueError):
        compare_states(after, before)


def test_controlled_external_identity_and_effect_have_real_evidence(
    sandbox: RuntimeSandbox,
) -> None:
    sentinel = sandbox.root / sandbox.protected_paths[0]
    before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
    alias = sandbox.extraction_root / "alias"
    os.link(sentinel, alias)
    alias.write_bytes(b"controlled changed bytes")
    os.link(sentinel, sandbox.archive_path)
    after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    c0, c1, c2 = evaluate_contracts(before, after)
    assert not c0.violated  # Content effects do not prove an external namespace operation.
    assert c1.violated and c2.violated
    assert sentinel.read_bytes() == b"controlled changed bytes"
    internal, external = after.get("extract/alias"), after.get(sandbox.protected_paths[0])
    assert internal is not None and external is not None
    assert internal.identity == external.identity
    assert c1.evidence and c2.evidence
    assert after.identity_groups() == (
        ("archive/input.tar", "extract/alias", "outside/sentinel.txt"),
    )
    signature = state_signature(before, after)
    assert signature.identity_groups == (("extract/alias", "outside/sentinel.txt"),)
    assert signature.protected_paths == after.protected_paths
    assert any(effect.path == "outside/sentinel.txt" for effect in signature.external_effects)


def test_harness_artifact_changes_remain_raw_evidence_without_state_novelty(
    sandbox: RuntimeSandbox,
) -> None:
    sandbox.archive_path.write_bytes(b"first input artifact")
    before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
    baseline = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    sandbox.archive_path.write_bytes(b"different input artifact bytes")
    sandbox.archive_path.chmod(0o640)
    sandbox.archive_path.parent.chmod(0o710)
    sandbox.root.chmod(0o750)
    extra = sandbox.archive_path.parent / "nested"
    extra.mkdir()
    (extra / "evidence.txt").write_bytes(b"harness bookkeeping")
    after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    changes = {change.path: change for change in compare_states(before, after)}
    assert {".", "archive", "archive/input.tar", "archive/nested/evidence.txt"} <= changes.keys()
    assert ChangeField.CONTENT in changes["archive/input.tar"].fields
    assert ChangeField.MODE in changes["."].fields
    assert before != after and baseline != after
    assert all(not verdict.violated for verdict in evaluate_contracts(before, after))
    assert state_signature(before, baseline) == state_signature(before, after)


@pytest.mark.parametrize("operation", ["create", "delete", "replace"])
def test_root_level_external_namespace_escape_is_c0_evidence(
    sandbox: RuntimeSandbox, operation: str
) -> None:
    escape = sandbox.root / "escape.txt"
    if operation != "create":
        escape.write_bytes(b"controlled previous object")
    before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
    if operation == "delete":
        escape.unlink()
    else:
        if operation == "replace":
            # Keep the old inode alive so replacement cannot be hidden by reuse.
            escape.rename(sandbox.archive_path.parent / "retained-escape")
        escape.write_bytes(b"controlled external object")
    after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    c0, c1, c2 = evaluate_contracts(before, after)
    assert c0.violated and not c1.violated and not c2.violated
    assert len(c0.evidence) == 1
    evidence = c0.evidence[0]
    assert isinstance(evidence, StateChange) and evidence.path == "escape.txt"
    assert (ChangeField.IDENTITY if operation == "replace" else ChangeField.EXISTENCE) in (
        evidence.fields
    )
    signature = state_signature(before, after)
    assert any(effect.path == "escape.txt" for effect in signature.external_effects)
    assert ("escape.txt" in {obj.path for obj in signature.objects}) == (operation != "delete")


def test_missing_sentinel_and_external_creation(sandbox: RuntimeSandbox) -> None:
    before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
    (sandbox.root / sandbox.protected_paths[0]).unlink()
    (sandbox.root / "outside" / "new-file").write_bytes(b"controlled")
    after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
    assert after.get(sandbox.protected_paths[0]) is None
    assert after.protected_paths == before.protected_paths
    c0, c1, c2 = evaluate_contracts(before, after)
    assert c0.violated and not c1.violated and c2.violated
    assert {e.path for e in c0.evidence if isinstance(e, StateChange)} == {
        "outside/new-file",
        "outside/sentinel.txt",
    }
    signature = state_signature(before, after)
    assert signature.protected_paths == before.protected_paths
    assert any(effect.path == "outside/sentinel.txt" for effect in signature.external_effects)


def test_io_failure_is_not_missing_state(
    sandbox: RuntimeSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny_read(directory_fd: int, name: str, metadata: os.stat_result) -> str:
        raise PermissionError("controlled unreadable file")

    monkeypatch.setattr(snapshot_module, "_digest", deny_read)
    with pytest.raises(ObservationError, match="cannot observe"):
        capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)


def test_snapshot_rejects_symlink_root_and_ancestor(sandbox: RuntimeSandbox) -> None:
    alias = sandbox.root / "alias"
    alias.symlink_to(sandbox.extraction_root, target_is_directory=True)
    with pytest.raises(ObservationError):
        capture_state(alias, SnapshotPhase.AFTER, sandbox.protected_paths)
    (sandbox.extraction_root / "child").mkdir()
    with pytest.raises(ObservationError):
        capture_state(alias / "child", SnapshotPhase.AFTER, sandbox.protected_paths)


def test_model_rejects_unsorted_observation(sandbox: RuntimeSandbox) -> None:
    state = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
    with pytest.raises(ValueError, match="unique sorted"):
        replace(state, objects=tuple(reversed(state.objects)))
    with pytest.raises(ValueError):
        replace(state, objects=state.objects + (state.objects[-1],))
    with pytest.raises(ValueError):
        replace(state.objects[-1], path="../escape")
    with pytest.raises(ValueError):
        replace(state.objects[-1], content_digest="bad-digest")

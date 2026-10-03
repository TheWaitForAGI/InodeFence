"""Check supplied filesystem facts without accessing the filesystem."""

from dataclasses import FrozenInstanceError

import pytest

from inodefence.model import FilesystemObjectType, ObjectSnapshot


def test_regular_file_snapshot() -> None:
    snapshot = ObjectSnapshot(
        relative_path="a.txt",
        object_type=FilesystemObjectType.REGULAR,
        st_dev=10,
        st_ino=555,
        st_nlink=2,
        mode=0o100640,
        size=123,
    )

    assert snapshot.relative_path == "a.txt"
    assert snapshot.object_type is FilesystemObjectType.REGULAR
    assert snapshot.st_dev == 10
    assert snapshot.st_ino == 555
    assert snapshot.st_nlink == 2
    assert snapshot.mode == 0o100640
    assert snapshot.size == 123
    assert snapshot.symlink_target is None
    assert snapshot.content_hash is None


@pytest.mark.parametrize(
    ("object_type", "mode"),
    [(FilesystemObjectType.DIRECTORY, 0o40755), (FilesystemObjectType.OTHER, 0o10600)],
)
def test_directory_and_other_snapshot(object_type: FilesystemObjectType, mode: int) -> None:
    snapshot = ObjectSnapshot(
        relative_path="object",
        object_type=object_type,
        st_dev=10,
        st_ino=556,
        st_nlink=1,
        mode=mode,
        size=0,
    )

    assert snapshot.object_type is object_type
    assert snapshot.mode == mode
    assert snapshot.size == 0
    assert snapshot.symlink_target is None


@pytest.mark.parametrize("target", ["../outside/file", "/outside/file", "dir/../file"])
def test_symlink_target_is_preserved(target: str) -> None:
    snapshot = ObjectSnapshot(
        relative_path="link",
        object_type=FilesystemObjectType.SYMLINK,
        st_dev=10,
        st_ino=557,
        st_nlink=1,
        mode=0o120777,
        size=len(target),
        symlink_target=target,
    )

    assert snapshot.object_type is FilesystemObjectType.SYMLINK
    assert snapshot.symlink_target == target


@pytest.mark.parametrize("content_hash", [None, "", "  arbitrary hash\r\n\x00  "])
def test_content_hash_is_preserved(content_hash: str | None) -> None:
    snapshot = ObjectSnapshot(
        relative_path="a.txt",
        object_type=FilesystemObjectType.REGULAR,
        st_dev=10,
        st_ino=555,
        st_nlink=1,
        mode=0o100644,
        size=0,
        content_hash=content_hash,
    )

    assert snapshot.content_hash == content_hash


@pytest.mark.parametrize("relative_path", ["../outside/file", "/file", "dir/../file"])
def test_relative_path_is_preserved(relative_path: str) -> None:
    snapshot = ObjectSnapshot(
        relative_path=relative_path,
        object_type=FilesystemObjectType.REGULAR,
        st_dev=10,
        st_ino=555,
        st_nlink=1,
        mode=0o100644,
        size=0,
    )

    assert snapshot.relative_path == relative_path


@pytest.mark.parametrize("value", [0, -1])
@pytest.mark.parametrize(
    ("object_type", "symlink_target"),
    [(FilesystemObjectType.SYMLINK, None), (FilesystemObjectType.REGULAR, "../target")],
)
def test_numeric_ranges_and_field_combinations_are_not_validated(
    value: int, object_type: FilesystemObjectType, symlink_target: str | None
) -> None:
    snapshot = ObjectSnapshot(
        relative_path="object",
        object_type=object_type,
        st_dev=value,
        st_ino=value,
        st_nlink=value,
        mode=value,
        size=value,
        symlink_target=symlink_target,
    )

    assert snapshot.st_dev == value
    assert snapshot.st_ino == value
    assert snapshot.st_nlink == value
    assert snapshot.mode == value
    assert snapshot.size == value
    assert snapshot.object_type is object_type
    assert snapshot.symlink_target == symlink_target


def test_different_paths_can_share_identity() -> None:
    snapshots = tuple(
        ObjectSnapshot(
            relative_path=path,
            object_type=FilesystemObjectType.REGULAR,
            st_dev=10,
            st_ino=555,
            st_nlink=2,
            mode=0o100644,
            size=123,
        )
        for path in ("a.txt", "b.txt")
    )

    first, second = snapshots
    assert first.relative_path != second.relative_path
    assert (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)
    assert first.st_nlink == second.st_nlink == 2


def test_snapshot_is_frozen() -> None:
    snapshot = ObjectSnapshot(
        relative_path="a.txt",
        object_type=FilesystemObjectType.REGULAR,
        st_dev=10,
        st_ino=555,
        st_nlink=1,
        mode=0o100644,
        size=0,
    )

    with pytest.raises(FrozenInstanceError):
        setattr(snapshot, "relative_path", "b.txt")  # noqa: B010

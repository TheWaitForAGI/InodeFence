"""Check logical archive structure without creating or extracting TAR files."""

from dataclasses import FrozenInstanceError

import pytest

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType


def test_regular_file_baseline() -> None:
    entry = ArchiveEntry(
        path="a.txt",
        entry_type=EntryType.REGULAR,
        content=b"hello inodefence",
    )
    case = ArchiveCase(entries=(entry,))

    assert case.entries == (entry,)
    assert entry.path == "a.txt"
    assert entry.entry_type is EntryType.REGULAR
    assert entry.content == b"hello inodefence"
    assert entry.link_target is None


def test_directory_baseline() -> None:
    directory = ArchiveEntry(path="dir/", entry_type=EntryType.DIRECTORY)
    regular = ArchiveEntry(
        path="dir/a.txt",
        entry_type=EntryType.REGULAR,
        content=b"hello inodefence",
    )
    case = ArchiveCase(entries=(directory, regular))

    assert case.entries == (directory, regular)
    assert [entry.path for entry in case.entries] == ["dir/", "dir/a.txt"]
    assert case.entries[0].entry_type is EntryType.DIRECTORY
    assert case.entries[0].content == b""
    assert case.entries[0].link_target is None
    assert case.entries[1].entry_type is EntryType.REGULAR
    assert case.entries[1].content == b"hello inodefence"


@pytest.mark.parametrize("entry_type", [EntryType.HARDLINK, EntryType.SYMLINK])
def test_link_baseline(entry_type: EntryType) -> None:
    regular = ArchiveEntry(
        path="a.txt",
        entry_type=EntryType.REGULAR,
        content=b"hello inodefence",
    )
    link = ArchiveEntry(path="b.txt", entry_type=entry_type, link_target="a.txt")
    case = ArchiveCase(entries=(regular, link))

    assert case.entries == (regular, link)
    assert case.entries[0].path == "a.txt"
    assert case.entries[0].content == b"hello inodefence"
    assert case.entries[1].path == "b.txt"
    assert case.entries[1].entry_type is entry_type
    assert case.entries[1].content == b""
    assert case.entries[1].link_target == "a.txt"


def test_case_preserves_order_and_duplicate_paths() -> None:
    link = ArchiveEntry(path="b.txt", entry_type=EntryType.HARDLINK, link_target="a.txt")
    first = ArchiveEntry(path="a.txt", entry_type=EntryType.REGULAR, content=b"first")
    second = ArchiveEntry(path="a.txt", entry_type=EntryType.REGULAR, content=b"second")
    case = ArchiveCase(entries=(link, first, second))

    assert case.entries == (link, first, second)
    assert [entry.path for entry in case.entries] == ["b.txt", "a.txt", "a.txt"]
    assert case.entries[0].link_target == "a.txt"
    assert case.entries[1].content == b"first"
    assert case.entries[2].content == b"second"


def test_empty_case() -> None:
    assert ArchiveCase(entries=()).entries == ()


@pytest.mark.parametrize("content", [b"", b"\x00\xff\x80\n\r\x00"])
def test_content_bytes_are_preserved(content: bytes) -> None:
    entry = ArchiveEntry(path="a.txt", entry_type=EntryType.REGULAR, content=content)

    assert isinstance(entry.content, bytes)
    assert entry.content == content


@pytest.mark.parametrize("path", ["../a", "/a", "dir/../a"])
@pytest.mark.parametrize("entry_type", list(EntryType))
def test_path_is_not_normalized(path: str, entry_type: EntryType) -> None:
    entry = ArchiveEntry(path=path, entry_type=entry_type)
    case = ArchiveCase(entries=(entry,))

    assert case.entries[0].path == path


@pytest.mark.parametrize("link_target", ["../a", "/a", "dir/../a"])
@pytest.mark.parametrize("entry_type", [EntryType.HARDLINK, EntryType.SYMLINK])
def test_link_target_is_not_normalized(link_target: str, entry_type: EntryType) -> None:
    entry = ArchiveEntry(path="b.txt", entry_type=entry_type, link_target=link_target)

    assert entry.link_target == link_target


def test_entry_is_frozen() -> None:
    entry = ArchiveEntry(path="a.txt", entry_type=EntryType.REGULAR)

    with pytest.raises(FrozenInstanceError):
        entry.path = "b.txt"


def test_case_is_frozen() -> None:
    case = ArchiveCase(entries=())

    with pytest.raises(FrozenInstanceError):
        case.entries = (ArchiveEntry(path="a.txt", entry_type=EntryType.REGULAR),)

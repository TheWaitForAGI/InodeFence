import base64
import json
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    canonical_json,
)


@pytest.mark.parametrize("kind", [EntryType.HARDLINK, EntryType.SYMLINK])
def test_link_requires_target_and_forbids_even_empty_content(kind: EntryType) -> None:
    with pytest.raises(ValueError, match="require a link target"):
        ArchiveEntry("b", kind)
    with pytest.raises(ValueError, match="only regular"):
        ArchiveEntry("b", kind, content=b"", link_target="a")
    assert ArchiveEntry("b", kind, link_target="../raw/target").link_target == "../raw/target"


def test_regular_and_directory_invariants() -> None:
    with pytest.raises(ValueError, match="require bytes"):
        ArchiveEntry("a", EntryType.REGULAR)
    with pytest.raises(ValueError):
        ArchiveEntry("a", EntryType.REGULAR, content=b"x", link_target="b")
    with pytest.raises(ValueError):
        ArchiveEntry("dir", EntryType.DIRECTORY, content=b"")
    with pytest.raises(ValueError):
        ArchiveEntry("dir", EntryType.DIRECTORY, link_target="a")
    assert ArchiveEntry("a", EntryType.REGULAR, content=b"").content == b""
    assert ArchiveEntry("dir/", EntryType.DIRECTORY).content is None


@pytest.mark.parametrize("path", ["", "a\0b", "\ud800"])
def test_unrepresentable_text_rejected_at_boundary(path: str) -> None:
    with pytest.raises(ValueError):
        ArchiveEntry(path, EntryType.REGULAR, content=b"")
    with pytest.raises(ValueError):
        ArchiveEntry("link", EntryType.SYMLINK, link_target=path)


@pytest.mark.parametrize("mode", [-1, 0o10000, True, 1.5])
def test_invalid_modes(mode: int) -> None:
    with pytest.raises(ValueError, match="mode"):
        ArchiveEntry("a", EntryType.REGULAR, content=b"", mode=mode)


def test_incorrect_runtime_types_rejected() -> None:
    with pytest.raises(ValueError):
        ArchiveEntry("a", cast(EntryType, "regular"), content=b"")
    with pytest.raises(ValueError):
        ArchiveEntry("a", EntryType.REGULAR, content=cast(bytes, bytearray(b"x")))
    with pytest.raises(ValueError):
        ArchiveCase(cast(tuple[ArchiveEntry, ...], []))
    with pytest.raises(ValueError):
        ArchiveCase((cast(ArchiveEntry, "a"),))


@pytest.mark.parametrize("path", ["../outside", "/foo/bar", "a/../../b", "a//b", "./a"])
def test_raw_archive_text_is_preserved(path: str) -> None:
    entry = ArchiveEntry(path, EntryType.SYMLINK, link_target=path)
    assert entry.path == entry.link_target == path
    value = json.loads(canonical_json(ArchiveCase((entry,))))
    assert value["value"]["entries"][0]["path"] == path


def test_case_order_duplicates_immutability_and_content_address() -> None:
    first = ArchiveEntry("a", EntryType.REGULAR, content=b"\0\xfffirst")
    second = ArchiveEntry("a", EntryType.REGULAR, content=b"second")
    case = ArchiveCase((first, second, first))
    assert case.entries == (first, second, first)
    assert len(case.case_id) == 64
    assert canonical_json(case) == canonical_json(ArchiveCase((first, second, first)))
    assert case.case_id != ArchiveCase((second, first, first)).case_id
    for instance, field, value in ((case, "entries", ()), (first, "path", "changed")):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, field, value)
    encoded = json.loads(canonical_json(case))["value"]["entries"][0]["content"]
    assert base64.b64decode(encoded["data"]) == first.content
    assert ArchiveCase(()).entries == ()


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [
        (ExecutionStatus.SUCCESS, 2),
        (ExecutionStatus.REJECTED, 0),
        (ExecutionStatus.TIMED_OUT, 1),
        (ExecutionStatus.FAILED, None),
    ],
)
def test_execution_result_rejects_contradictory_status(
    status: ExecutionStatus, exit_code: int | None
) -> None:
    with pytest.raises(ValueError):
        ExecutionResult("target", "version", (), status, exit_code, "", "", duration_seconds=0.0)

import io
import tarfile

import pytest

from inodefence.builder import build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType


def test_tar_member_semantics_order_and_fixed_metadata() -> None:
    case = ArchiveCase(
        (
            ArchiveEntry("dir/", EntryType.DIRECTORY, mode=0o750),
            ArchiveEntry("dir/file", EntryType.REGULAR, content=b"\0\xffpayload", mode=0o640),
            ArchiveEntry("hard", EntryType.HARDLINK, link_target="dir/file", mode=0o600),
            ArchiveEntry("sym", EntryType.SYMLINK, link_target="dir/file", mode=0o777),
            ArchiveEntry("dir/file", EntryType.REGULAR, content=b"replacement", mode=0o644),
        )
    )
    data = build_tar(case)
    assert data == build_tar(case)
    assert data[257:263] == b"ustar\0"
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        members = tar.getmembers()
        assert [m.name for m in members] == ["dir", "dir/file", "hard", "sym", "dir/file"]
        assert [m.type for m in members] == [
            tarfile.DIRTYPE,
            tarfile.REGTYPE,
            tarfile.LNKTYPE,
            tarfile.SYMTYPE,
            tarfile.REGTYPE,
        ]
        assert [m.mode for m in members] == [entry.mode for entry in case.entries]
        assert members[2].linkname == members[3].linkname == "dir/file"
        for index in (1, 4):
            stream = tar.extractfile(members[index])
            assert stream is not None
            assert stream.read() == case.entries[index].content
        for member in members:
            assert (member.uid, member.gid, member.mtime) == (0, 0, 0)
            assert (member.uname, member.gname) == ("", "")
            assert member.pax_headers == {}


@pytest.mark.parametrize("path", ["../outside", "/foo/bar", "a/../../b", "a//b", "dir//"])
def test_raw_paths_and_links_survive_encoding(path: str) -> None:
    for kind in (EntryType.SYMLINK, EntryType.DIRECTORY):
        entry = ArchiveEntry(path, kind, link_target=path if kind == EntryType.SYMLINK else None)
        data = build_tar(ArchiveCase((entry,)))
        assert data[:100].split(b"\0", 1)[0] == path.encode()
        if kind == EntryType.SYMLINK:
            assert data[157:257].split(b"\0", 1)[0] == path.encode()


def test_utf8_ustar_prefix_and_empty_archive() -> None:
    path = "한" * 40 + "/file"
    data = build_tar(ArchiveCase((ArchiveEntry(path, EntryType.REGULAR, content=b""),)))
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        assert tar.getnames() == [path]
    with tarfile.open(fileobj=io.BytesIO(build_tar(ArchiveCase(()))), mode="r:") as tar:
        assert tar.getmembers() == []


@pytest.mark.parametrize(
    "entry",
    [
        ArchiveEntry("x" * 101, EntryType.REGULAR, content=b""),
        ArchiveEntry("link", EntryType.SYMLINK, link_target="x" * 101),
    ],
)
def test_unrepresentable_ustar_input_rejected_without_truncation(entry: ArchiveEntry) -> None:
    with pytest.raises(ValueError, match="entry 0 cannot be represented in USTAR"):
        build_tar(ArchiveCase((entry,)))

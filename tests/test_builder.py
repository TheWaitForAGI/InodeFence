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


@pytest.mark.parametrize("kind", tuple(EntryType))
@pytest.mark.parametrize(
    ("path", "accepted"),
    [
        ("/" + "a" * 99, True),
        ("/" + "a" * 100, False),
        ("//" + "a" * 99, False),
        ("/dir/" + "a" * 96, False),
        ("/" + "é" * 50, False),
        ("///" + "a" * 98, False),
        ("//" + "a" * 100, True),
        ("a//" + "b" * 99, True),
        ("a/" + "b" * 100, True),
        ("a/" + "b" * 101, False),
        ("x" * 154 + "/" + "y" * 100, True),
        ("x" * 155 + "/" + "y" * 100, True),
        ("x" * 156 + "/" + "y" * 100, False),
        ("é" * 77 + "x/" + "é" * 50, True),
        ("é" * 78 + "/" + "é" * 50, False),
        ("é" * 77 + "/" + "é" * 51, False),
        ("dir//", True),
        ("x" * 155 + "/" + "y" * 99 + "/", True),
    ],
)
def test_ustar_emits_exact_raw_path_or_rejects(kind: EntryType, path: str, accepted: bool) -> None:
    entry = ArchiveEntry(
        path,
        kind,
        content=b"inert" if kind == EntryType.REGULAR else None,
        link_target="benign" if kind in (EntryType.HARDLINK, EntryType.SYMLINK) else None,
    )
    case = ArchiveCase((entry,))
    if not accepted:
        with pytest.raises(ValueError, match="entry 0 cannot be represented in USTAR"):
            build_tar(case)
        # Each frozen slash-loss witness has a different, representable relative case.
        if path.startswith("/"):
            relative = ArchiveCase(
                (ArchiveEntry(path[1:], kind, entry.content, entry.link_target, entry.mode),)
            )
            assert relative.case_id != case.case_id
            assert build_tar(relative)
    else:
        data = build_tar(case)
        prefix = data[345:500].split(b"\0", 1)[0]
        name = data[:100].split(b"\0", 1)[0]
        reconstructed = prefix + b"/" + name if prefix else name
        assert reconstructed == path.encode("utf-8")
        assert data == build_tar(case)
    assert entry.path == path


@pytest.mark.parametrize("kind", (EntryType.HARDLINK, EntryType.SYMLINK))
@pytest.mark.parametrize("target", ("/" + "a" * 99, "é" * 50, "a//b"))
def test_link_target_byte_boundary_preserves_raw_text(kind: EntryType, target: str) -> None:
    data = build_tar(ArchiveCase((ArchiveEntry("link", kind, link_target=target),)))
    assert data[157:257].split(b"\0", 1)[0] == target.encode("utf-8")


@pytest.mark.parametrize("kind", (EntryType.HARDLINK, EntryType.SYMLINK))
@pytest.mark.parametrize("target", ("/" + "a" * 100, "é" * 50 + "x"))
def test_link_target_over_byte_boundary_fails(kind: EntryType, target: str) -> None:
    with pytest.raises(ValueError, match="entry 0 cannot be represented in USTAR"):
        build_tar(ArchiveCase((ArchiveEntry("link", kind, link_target=target),)))

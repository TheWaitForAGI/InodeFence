"""Caller-level composition evidence; the mutator itself never imports the builder."""

import io
import random
import tarfile
from collections.abc import Callable
from dataclasses import replace

import pytest

from inodefence.builder import build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, canonical_json
from inodefence.mutator import (
    add_entry,
    add_hardlink,
    add_symlink,
    duplicate_entry,
    mutate,
    mutate_link_target,
    mutate_path,
    remove_entry,
    reorder_entries,
)


@pytest.mark.parametrize(
    "operator",
    (
        mutate,
        add_entry,
        remove_entry,
        duplicate_entry,
        reorder_entries,
        mutate_path,
        add_hardlink,
        add_symlink,
        mutate_link_target,
    ),
)
def test_mutated_cases_compose_with_canonical_constructor_and_builder(
    operator: Callable[[ArchiveCase, random.Random], ArchiveCase],
) -> None:
    regular = ArchiveEntry("./a", EntryType.REGULAR, content=b"\0\xfffirst", mode=0o4640)
    cases = (
        ArchiveCase(()),
        ArchiveCase((regular,)),
        ArchiveCase(
            (
                ArchiveEntry("dir//", EntryType.DIRECTORY, mode=0o2750),
                regular,
                ArchiveEntry("a//b", EntryType.HARDLINK, link_target="./a"),
                ArchiveEntry("/raw-link", EntryType.SYMLINK, link_target="../raw//target"),
                replace(regular, content=b"replacement"),
            )
        ),
    )
    for case in cases:
        original = canonical_json(case)
        for seed in (0, 7, 1234, 1607):
            first_rng, second_rng = random.Random(seed), random.Random(999)
            first_rng.random()  # Exercise an advanced RNG state, not just a fresh seed.
            second_rng.setstate(first_rng.getstate())
            first, second = operator(case, first_rng), operator(case, second_rng)
            assert first == second and first_rng.getstate() == second_rng.getstate()
            assert canonical_json(case) == original
            rebuilt = ArchiveCase(tuple(replace(entry) for entry in first.entries))
            assert rebuilt == first and rebuilt.case_id == first.case_id
            data = build_tar(first)
            assert data == build_tar(second) == build_tar(rebuilt)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
                members = archive.getmembers()
                assert len(members) == len(first.entries)
                for entry, member in zip(first.entries, members, strict=True):
                    header = data[member.offset : member.offset + 512]
                    # TarInfo's read API strips directory trailing slashes; raw headers do not.
                    assert header[:100].split(b"\0", 1)[0] == entry.path.encode("utf-8")
                    assert header[157:257].split(b"\0", 1)[0] == (entry.link_target or "").encode(
                        "utf-8"
                    )
                    assert member.mode == entry.mode
                    assert (
                        member.type
                        == {
                            EntryType.REGULAR: tarfile.REGTYPE,
                            EntryType.DIRECTORY: tarfile.DIRTYPE,
                            EntryType.HARDLINK: tarfile.LNKTYPE,
                            EntryType.SYMLINK: tarfile.SYMTYPE,
                        }[entry.entry_type]
                    )
                    if entry.entry_type == EntryType.REGULAR:
                        stream = archive.extractfile(member)
                        assert stream is not None and stream.read() == entry.content


@pytest.mark.parametrize("kind", (EntryType.HARDLINK, EntryType.SYMLINK))
def test_mutation_keeps_ustar_length_limits_at_builder_boundary(kind: EntryType) -> None:
    case = ArchiveCase((ArchiveEntry("link", kind, link_target="x" * 100),))
    build_tar(case)  # The starting target fits the current encoding.
    for seed in (0, 7, 1234, 1607):
        mutated = mutate_link_target(case, random.Random(seed))
        target = mutated.entries[0].link_target
        assert target is not None and len(target.encode("utf-8")) > 100
        assert ArchiveCase(tuple(replace(entry) for entry in mutated.entries)) == mutated
        assert case.entries[0].link_target == "x" * 100
        with pytest.raises(ValueError, match="cannot be represented in USTAR"):
            build_tar(mutated)

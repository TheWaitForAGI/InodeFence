"""Fixed benign fixture whitelist; independent of evolving search seed policy."""

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType


def benign_replay_cases() -> tuple[ArchiveCase, ...]:
    regular = ArchiveEntry("a.txt", EntryType.REGULAR, content=b"hello inodefence")
    return (
        ArchiveCase((regular,)),
        ArchiveCase(
            (
                ArchiveEntry("dir/", EntryType.DIRECTORY, mode=0o755),
                ArchiveEntry("dir/a.txt", EntryType.REGULAR, content=b"hello inodefence"),
            )
        ),
        ArchiveCase((regular, ArchiveEntry("b.txt", EntryType.HARDLINK, link_target="a.txt"))),
        ArchiveCase(
            (regular, ArchiveEntry("b.txt", EntryType.SYMLINK, link_target="a.txt", mode=0o777))
        ),
    )

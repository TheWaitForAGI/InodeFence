"""Small normal starting cases, with no target, IO, feedback or TAR encoding."""

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType


def minimal_seed_corpus() -> tuple[ArchiveCase, ...]:
    """Return regular, directory, hardlink and symlink seeds in that order.

    These are the existing generic development baselines. Link targets follow
    their regular file entry and stay inside the archive namespace. Fixed paths,
    content and modes make case IDs reproducible. All values are immutable;
    callers explicitly choose whether to pass these seeds to a campaign.
    """
    content = b"hello inodefence"
    regular = ArchiveEntry("a.txt", EntryType.REGULAR, content=content)
    return (
        ArchiveCase((regular,)),
        ArchiveCase(
            (
                ArchiveEntry("dir/", EntryType.DIRECTORY, mode=0o755),
                ArchiveEntry("dir/a.txt", EntryType.REGULAR, content=content),
            )
        ),
        ArchiveCase((regular, ArchiveEntry("b.txt", EntryType.HARDLINK, link_target="a.txt"))),
        ArchiveCase(
            (regular, ArchiveEntry("b.txt", EntryType.SYMLINK, link_target="a.txt", mode=0o777))
        ),
    )

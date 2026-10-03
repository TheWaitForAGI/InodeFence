"""Pure logical mutations; entry order, duplicates and raw spelling are meaningful."""

import random
from collections.abc import Callable
from dataclasses import replace

from inodefence.model.archive import ArchiveCase, ArchiveEntry, EntryType

_PATH_PREFIXES = ("", "./", "../", "/")
_PATH_STEMS = ("a", "b", "file", "dir/item")
_TEXT_AFFIXES = (("../", ""), ("./", ""), ("/", ""), ("", "/.."), ("", "x"))
_MAX_CONTENT_BYTES = 16


def _new_raw_path(rng: random.Random) -> str:
    """Generate short logical text, allowing collisions with existing paths."""
    return rng.choice(_PATH_PREFIXES) + rng.choice(_PATH_STEMS)


def _mutate_raw_text(value: str, rng: random.Random) -> str:
    """Preserve every existing character and add at most three ASCII characters."""
    prefix, suffix = rng.choice(_TEXT_AFFIXES)
    return prefix + value + suffix


def add_entry(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Append a regular file with short raw text and a small bytes payload."""
    entry = ArchiveEntry(
        path=_new_raw_path(rng),
        entry_type=EntryType.REGULAR,
        content=rng.randbytes(rng.randrange(_MAX_CONTENT_BYTES + 1)),
        mode=0o644,
    )
    return ArchiveCase((*case.entries, entry))


def remove_entry(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Remove one entry while preserving relative order; empty cases are unchanged."""
    if not case.entries:
        return case
    index = rng.randrange(len(case.entries))
    return ArchiveCase(case.entries[:index] + case.entries[index + 1 :])


def duplicate_entry(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Insert one exact duplicate at a random position; empty cases are unchanged."""
    if not case.entries:
        return case
    entry = rng.choice(case.entries)
    index = rng.randrange(len(case.entries) + 1)
    return ArchiveCase(case.entries[:index] + (entry,) + case.entries[index:])


def reorder_entries(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Swap two unequal entry values; fewer than two distinct values is a no-op."""
    if len(case.entries) < 2:
        return case
    first = rng.randrange(len(case.entries))
    different_indices = [
        index for index, entry in enumerate(case.entries) if entry != case.entries[first]
    ]
    if not different_indices:
        return case
    second = rng.choice(different_indices)
    entries = list(case.entries)
    entries[first], entries[second] = entries[second], entries[first]
    return ArchiveCase(tuple(entries))


def mutate_path(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Change only one entry's raw path; empty cases are unchanged."""
    if not case.entries:
        return case
    index = rng.randrange(len(case.entries))
    entry = case.entries[index]
    changed = replace(entry, path=_mutate_raw_text(entry.path, rng))
    return ArchiveCase(case.entries[:index] + (changed,) + case.entries[index + 1 :])


def add_hardlink(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Append a hardlink to an existing raw path; empty cases are unchanged."""
    if not case.entries:
        return case
    target = rng.choice(case.entries).path
    entry = ArchiveEntry(
        path=_new_raw_path(rng),
        entry_type=EntryType.HARDLINK,
        link_target=target,
        mode=0o644,
    )
    return ArchiveCase((*case.entries, entry))


def add_symlink(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Append a symlink to an existing raw path or a short generic raw target."""
    if case.entries and rng.choice((False, True)):
        target = rng.choice(case.entries).path
    else:
        target = _new_raw_path(rng)
    entry = ArchiveEntry(
        path=_new_raw_path(rng),
        entry_type=EntryType.SYMLINK,
        link_target=target,
        mode=0o777,
    )
    return ArchiveCase((*case.entries, entry))


def mutate_link_target(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Change only one link's raw target; cases without links are unchanged."""
    indices = [
        index
        for index, entry in enumerate(case.entries)
        if entry.entry_type in (EntryType.HARDLINK, EntryType.SYMLINK)
    ]
    if not indices:
        return case
    index = rng.choice(indices)
    entry = case.entries[index]
    # The canonical ArchiveEntry invariant guarantees a nonempty target for links.
    assert entry.link_target is not None
    changed = replace(entry, link_target=_mutate_raw_text(entry.link_target, rng))
    return ArchiveCase(case.entries[:index] + (changed,) + case.entries[index + 1 :])


_OPERATORS: tuple[Callable[[ArchiveCase, random.Random], ArchiveCase], ...] = (
    add_entry,
    remove_entry,
    duplicate_entry,
    reorder_entries,
    mutate_path,
    add_hardlink,
    add_symlink,
    mutate_link_target,
)


def mutate(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Select and apply one of eight operators using only the supplied RNG.

    Selection is uniform, including inapplicable operators; their no-op behavior
    is retained rather than retrying or consulting another layer.
    """
    return rng.choice(_OPERATORS)(case, rng)

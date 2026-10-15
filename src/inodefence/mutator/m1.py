"""Bounded generic grammar for repeated paths, replacement and link composition."""

import random
from dataclasses import replace

from inodefence.model.archive import ArchiveCase, ArchiveEntry, EntryType

from .operators import duplicate_entry, remove_entry, reorder_entries

# Conservative single-field UTF-8 bound supported by the current USTAR builder.
MAX_TEXT_BYTES = 100
COMPONENTS = ("a", "b", "dir", "file", "item", ".", "..")
_PREFIXES = ("", "./", "../", "/")
_SEPARATORS = ("/", "//")
_AFFIXES = (("../", ""), ("./", ""), ("/", ""), ("", "/.."), ("", "/"))


def _raw_path(
    case: ArchiveCase, rng: random.Random, *, components: tuple[str, ...] = COMPONENTS
) -> str:
    """Half the nonempty-case draws reuse a representable existing raw name.

    Reuse samples entry occurrences, including links and repeated names. The
    other branch draws prefix, depth (1..4), separator and each component in that
    order. No normalization or dependency repair occurs.
    """
    paths = tuple(
        entry.path for entry in case.entries if len(entry.path.encode("utf-8")) <= MAX_TEXT_BYTES
    )
    if paths and rng.choice((False, True)):
        return rng.choice(paths)
    prefix = rng.choice(_PREFIXES)
    depth = rng.randrange(1, 5)
    separator = rng.choice(_SEPARATORS)
    return prefix + separator.join(rng.choice(components) for _ in range(depth))


def _insert(case: ArchiveCase, entry: ArchiveEntry, rng: random.Random) -> ArchiveCase:
    index = rng.randrange(len(case.entries) + 1)
    return ArchiveCase(case.entries[:index] + (entry,) + case.entries[index:])


def add_entry(
    case: ArchiveCase, rng: random.Random, *, components: tuple[str, ...] = COMPONENTS
) -> ArchiveCase:
    """Insert regular/directory entries, allowing same-name type replacement."""
    path = _raw_path(case, rng, components=components)
    kind = rng.choice((EntryType.REGULAR, EntryType.DIRECTORY))
    content = rng.randbytes(rng.randrange(17)) if kind == EntryType.REGULAR else None
    return _insert(case, ArchiveEntry(path, kind, content=content), rng)


def mutate_path(
    case: ArchiveCase, rng: random.Random, *, components: tuple[str, ...] = COMPONENTS
) -> ArchiveCase:
    if not case.entries:
        return case
    index = rng.randrange(len(case.entries))
    changed = replace(case.entries[index], path=_raw_path(case, rng, components=components))
    return ArchiveCase(case.entries[:index] + (changed,) + case.entries[index + 1 :])


def add_hardlink(
    case: ArchiveCase, rng: random.Random, *, components: tuple[str, ...] = COMPONENTS
) -> ArchiveCase:
    """Target any representable entry path, including existing link entries."""
    paths = tuple(
        entry.path for entry in case.entries if len(entry.path.encode("utf-8")) <= MAX_TEXT_BYTES
    )
    if not paths:
        return case
    target = rng.choice(paths)
    path = _raw_path(case, rng, components=components)
    return _insert(case, ArchiveEntry(path, EntryType.HARDLINK, link_target=target), rng)


def add_symlink(
    case: ArchiveCase, rng: random.Random, *, components: tuple[str, ...] = COMPONENTS
) -> ArchiveCase:
    target = _raw_path(case, rng, components=components)
    path = _raw_path(case, rng, components=components)
    return _insert(case, ArchiveEntry(path, EntryType.SYMLINK, link_target=target, mode=0o777), rng)


def mutate_link_target(
    case: ArchiveCase, rng: random.Random, *, components: tuple[str, ...] = COMPONENTS
) -> ArchiveCase:
    indices = tuple(
        index for index, entry in enumerate(case.entries) if entry.link_target is not None
    )
    if not indices:
        return case
    index = rng.choice(indices)
    entry = case.entries[index]
    assert entry.link_target is not None
    if rng.choice((False, True)):
        prefix, suffix = rng.choice(_AFFIXES)
        target = prefix + entry.link_target + suffix
    else:
        target = _raw_path(case, rng, components=components)
    # A bounded miss is one no-op, with no retry or replacement RNG draw.
    if len(target.encode("utf-8")) > MAX_TEXT_BYTES:
        return case
    changed = replace(entry, link_target=target)
    return ArchiveCase(case.entries[:index] + (changed,) + case.entries[index + 1 :])


OPERATORS = (
    add_entry,
    remove_entry,
    duplicate_entry,
    reorder_entries,
    mutate_path,
    add_hardlink,
    add_symlink,
    mutate_link_target,
)

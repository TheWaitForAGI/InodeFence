"""M1 operator slots with a versioned controlled protected-path vocabulary."""

import random

from inodefence.model.archive import ArchiveCase

from . import m1

# This finite tuple extends M1 only with the existing default controlled setup
# components. It contains no target, version, CVE, PoC, or runtime-generated path.
COMPONENTS = (*m1.COMPONENTS, "outside", "sentinel.txt")


def add_entry(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    return m1.add_entry(case, rng, components=COMPONENTS)


def mutate_path(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    return m1.mutate_path(case, rng, components=COMPONENTS)


def add_hardlink(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    return m1.add_hardlink(case, rng, components=COMPONENTS)


def add_symlink(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    return m1.add_symlink(case, rng, components=COMPONENTS)


def mutate_link_target(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    return m1.mutate_link_target(case, rng, components=COMPONENTS)


OPERATORS = (
    add_entry,
    m1.remove_entry,
    m1.duplicate_entry,
    m1.reorder_entries,
    mutate_path,
    add_hardlink,
    add_symlink,
    mutate_link_target,
)


def mutate(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Apply one uniformly selected versioned slot with caller-owned RNG."""
    return rng.choice(OPERATORS)(case, rng)

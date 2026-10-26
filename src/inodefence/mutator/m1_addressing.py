"""M1 operator slots with a versioned controlled protected-path vocabulary."""

import functools
import random
from collections.abc import Callable

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


def add_escaping_hardlink(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    return m1.add_escaping_hardlink(case, rng, components=COMPONENTS)


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

# Identical to OPERATORS except the ADD_HARDLINK slot (index 5) generates an
# extraction-root-escaping target instead of reusing an in-archive entry path.
# The slot order, every other slot, and the uniform draw are unchanged, so seed
# reproducibility and the operator distribution are preserved; only the target
# addressing of the hardlink slot differs.
ESCAPE_OPERATORS = (
    add_entry,
    m1.remove_entry,
    m1.duplicate_entry,
    m1.reorder_entries,
    mutate_path,
    add_escaping_hardlink,
    add_symlink,
    mutate_link_target,
)

# Token-clean escaping-hardlink set: identical slot order to m1.OPERATORS but slot 5
# (ADD_HARDLINK) is the extraction-root-escaping variant, and every vocabulary-taking
# slot draws from the GENERIC m1 vocabulary only (no `outside`/`sentinel.txt` or any
# other target-specific token). A generated escaping target therefore cannot spell a
# name the generic alphabet does not contain — the reachability floor arm.
GENERIC_ESCAPE_OPERATORS = (
    m1.add_entry,
    m1.remove_entry,
    m1.duplicate_entry,
    m1.reorder_entries,
    m1.mutate_path,
    m1.add_escaping_hardlink,
    m1.add_symlink,
    m1.mutate_link_target,
)


def state_aware_escape_operators(
    observed_components: tuple[str, ...],
) -> tuple[Callable[[ArchiveCase, random.Random], ArchiveCase], ...]:
    """GENERIC_ESCAPE_OPERATORS whose vocabulary-taking slots also draw observed names.

    `observed_components` are segment names the run has observed in the general
    filesystem tree (`ObjectSnapshot` paths), supplied by the caller — never the
    protected-path list. They are appended to the generic M1 vocabulary so a
    generated path can compose an observed name (e.g. reach an external object by a
    name the run saw), with no target-specific token hardcoded (target-agnostic). The
    slot order and each slot's RNG draw sequence are unchanged; only the component
    pool differs. An empty pool reproduces GENERIC_ESCAPE_OPERATORS exactly.
    """
    pool = m1.COMPONENTS + tuple(observed_components)
    return (
        functools.partial(m1.add_entry, components=pool),
        m1.remove_entry,
        m1.duplicate_entry,
        m1.reorder_entries,
        functools.partial(m1.mutate_path, components=pool),
        functools.partial(m1.add_escaping_hardlink, components=pool),
        functools.partial(m1.add_symlink, components=pool),
        functools.partial(m1.mutate_link_target, components=pool),
    )


def mutate(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
    """Apply one uniformly selected versioned slot with caller-owned RNG."""
    return rng.choice(OPERATORS)(case, rng)

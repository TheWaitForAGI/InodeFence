"""v2 mutation grammar `b-grammar-v2-freeze-3` (#512): ten slots over one generic pool.

Implements the families the freeze marks for the v2 engine
(docs/research/design/mutation-vocabulary-inventory-v1.md, D061):

* L1 link-target base: slot ``add_hardlink`` inserts a hardlink whose target is
  ``"../" * depth`` + 1..3 tokens with **depth in 0..3** (0 = no parent step, so the
  target is resolved by whatever base the extractor uses). INSERT = 1 primitive.
* L2 symlink chains and same-path type replacement: no new slot. ``add_symlink`` and
  ``add_entry`` draw their path and target with :func:`raw_path`, which can reuse an
  existing entry path (a symlink's path as a new symlink's target makes a chain link;
  an existing path as a new entry's path replaces its type). INSERT = 1 each.
* O1 order dependence: :func:`raw_path` has a third branch, an existing path +
  separator + 1..3 tokens, so a later entry can pass through an object an earlier
  entry created. The path is a parameter of the one INSERT/SET that uses it.
* H1 field changes kept in v2: ``set_mode`` (SET mode = 1, any entry, one of the five
  pinned modes) and ``set_content`` (SET content = 1, a regular entry, one of the three
  pinned contents).

Not implemented here (freeze-3 "v2 engine not implemented"): H1 owner, size/link
content mismatch, PAX/GNU headers, P1 variant tokens. The USTAR text bound and its four
check sites are those of M1 (``m1.MAX_TEXT_BYTES``); a path made longer by the O1
branch is not repaired -- the builder decides, and the campaign records a refusal as a
build-invalid step (D060).

Every parameter draw comes from :class:`GrammarParameters`, bound to the policy id
(``dispatch.V2_PARAMETERS``). :data:`FINAL_UNIFORM` is the axis list W3/W4 fixed before
p_R (W4 ruling 2026-11-18 on the rng-draw table): every draw is ``rng.choice`` over a
finite tuple (or ``randrange`` over a position range), i.e. uniform over that domain.
The axes, their domains and the code sites are in docs/research/design/v2-grammar-axes.md.
Changing any domain means a new policy id. No target, CVE, path or sentinel name appears:
the only tokens are ``m1.COMPONENTS`` plus the caller's observed names.
"""

from __future__ import annotations

import functools
import random
from collections.abc import Callable
from dataclasses import dataclass, replace

from inodefence.model.archive import ArchiveCase, ArchiveEntry, EntryType

from . import m1
from .operators import duplicate_entry, remove_entry, reorder_entries

GRAMMAR_ID = "b-grammar-v2-freeze-3"

_PATH_REUSE = "reuse"
_PATH_EXTEND = "extend"
_PATH_NEW = "new"


@dataclass(frozen=True, slots=True)
class GrammarParameters:
    """Parameter domains of one v2 policy; every draw is uniform over its tuple.

    A different domain is a new policy id.
    """

    path_branches: tuple[str, ...] = (_PATH_REUSE, _PATH_EXTEND, _PATH_NEW)
    new_path_prefixes: tuple[str, ...] = m1._PREFIXES
    new_path_depths: tuple[int, ...] = (1, 2, 3, 4)
    separators: tuple[str, ...] = m1._SEPARATORS
    extend_token_counts: tuple[int, ...] = (1, 2, 3)
    hardlink_depths: tuple[int, ...] = (0, 1, 2, 3)
    hardlink_token_counts: tuple[int, ...] = (1, 2, 3)
    link_target_ways: tuple[bool, ...] = (False, True)
    link_target_affixes: tuple[tuple[str, str], ...] = m1._AFFIXES
    entry_kinds: tuple[EntryType, ...] = (EntryType.REGULAR, EntryType.DIRECTORY)
    # W3 axis list (pinned before p_R): five modes, three regular-file contents.
    modes: tuple[int, ...] = (0o644, 0o755, 0o4755, 0o2755, 0o1777)
    contents: tuple[bytes, ...] = (b"", b"x" * 8, b"x" * 16)


FINAL_UNIFORM = GrammarParameters()

Operator = Callable[[ArchiveCase, random.Random], ArchiveCase]


def _bounded_paths(case: ArchiveCase) -> tuple[str, ...]:
    return tuple(
        entry.path for entry in case.entries if len(entry.path.encode("utf-8")) <= m1.MAX_TEXT_BYTES
    )


def raw_path(
    case: ArchiveCase,
    rng: random.Random,
    *,
    components: tuple[str, ...],
    parameters: GrammarParameters,
) -> str:
    """Reuse an existing path, extend one (O1), or draw a new one, each branch uniform.

    With no representable existing path only the new-path branch is possible and no
    branch is drawn. The new branch draws prefix, depth, separator and each component
    in that order (as M1). The extend branch draws a path, a separator and 1..3 tokens.
    """
    paths = _bounded_paths(case)
    branch = rng.choice(parameters.path_branches) if paths else _PATH_NEW
    if branch == _PATH_REUSE:
        return rng.choice(paths)
    if branch == _PATH_EXTEND:
        base = rng.choice(paths)
        separator = rng.choice(parameters.separators)
        count = rng.choice(parameters.extend_token_counts)
        return base + separator + separator.join(rng.choice(components) for _ in range(count))
    prefix = rng.choice(parameters.new_path_prefixes)
    depth = rng.choice(parameters.new_path_depths)
    separator = rng.choice(parameters.separators)
    return prefix + separator.join(rng.choice(components) for _ in range(depth))


def add_entry(
    case: ArchiveCase,
    rng: random.Random,
    *,
    components: tuple[str, ...],
    parameters: GrammarParameters,
) -> ArchiveCase:
    path = raw_path(case, rng, components=components, parameters=parameters)
    kind = rng.choice(parameters.entry_kinds)
    content = rng.choice(parameters.contents) if kind == EntryType.REGULAR else None
    return m1._insert(case, ArchiveEntry(path, kind, content=content), rng)


def mutate_path(
    case: ArchiveCase,
    rng: random.Random,
    *,
    components: tuple[str, ...],
    parameters: GrammarParameters,
) -> ArchiveCase:
    if not case.entries:
        return case
    index = rng.randrange(len(case.entries))
    path = raw_path(case, rng, components=components, parameters=parameters)
    changed = replace(case.entries[index], path=path)
    return ArchiveCase(case.entries[:index] + (changed,) + case.entries[index + 1 :])


def add_hardlink(
    case: ArchiveCase,
    rng: random.Random,
    *,
    components: tuple[str, ...],
    parameters: GrammarParameters,
) -> ArchiveCase:
    """L1: a hardlink whose target is ``"../" * depth`` + tokens, depth in 0..3.

    A target over the USTAR text bound is one no-op (the entry is dropped), as in M1.
    """
    depth = rng.choice(parameters.hardlink_depths)
    count = rng.choice(parameters.hardlink_token_counts)
    tail = tuple(rng.choice(components) for _ in range(count))
    target = "/".join(("..",) * depth + tail)
    path = raw_path(case, rng, components=components, parameters=parameters)
    if len(target.encode("utf-8")) > m1.MAX_TEXT_BYTES:
        return case
    return m1._insert(case, ArchiveEntry(path, EntryType.HARDLINK, link_target=target), rng)


def add_symlink(
    case: ArchiveCase,
    rng: random.Random,
    *,
    components: tuple[str, ...],
    parameters: GrammarParameters,
) -> ArchiveCase:
    target = raw_path(case, rng, components=components, parameters=parameters)
    path = raw_path(case, rng, components=components, parameters=parameters)
    entry = ArchiveEntry(path, EntryType.SYMLINK, link_target=target, mode=0o777)
    return m1._insert(case, entry, rng)


def mutate_link_target(
    case: ArchiveCase,
    rng: random.Random,
    *,
    components: tuple[str, ...],
    parameters: GrammarParameters,
) -> ArchiveCase:
    indices = tuple(
        index for index, entry in enumerate(case.entries) if entry.link_target is not None
    )
    if not indices:
        return case
    index = rng.choice(indices)
    entry = case.entries[index]
    assert entry.link_target is not None
    if rng.choice(parameters.link_target_ways):
        prefix, suffix = rng.choice(parameters.link_target_affixes)
        target = prefix + entry.link_target + suffix
    else:
        target = raw_path(case, rng, components=components, parameters=parameters)
    if len(target.encode("utf-8")) > m1.MAX_TEXT_BYTES:
        return case
    changed = replace(entry, link_target=target)
    return ArchiveCase(case.entries[:index] + (changed,) + case.entries[index + 1 :])


def set_mode(
    case: ArchiveCase,
    rng: random.Random,
    *,
    components: tuple[str, ...],
    parameters: GrammarParameters,
) -> ArchiveCase:
    """H1: SET(mode) on one entry, uniform over the pinned modes."""
    if not case.entries:
        return case
    index = rng.randrange(len(case.entries))
    changed = replace(case.entries[index], mode=rng.choice(parameters.modes))
    return ArchiveCase(case.entries[:index] + (changed,) + case.entries[index + 1 :])


def set_content(
    case: ArchiveCase,
    rng: random.Random,
    *,
    components: tuple[str, ...],
    parameters: GrammarParameters,
) -> ArchiveCase:
    """H1: SET(content) on one regular entry, uniform over the pinned contents."""
    indices = tuple(
        index for index, entry in enumerate(case.entries) if entry.entry_type == EntryType.REGULAR
    )
    if not indices:
        return case
    index = rng.choice(indices)
    changed = replace(case.entries[index], content=rng.choice(parameters.contents))
    return ArchiveCase(case.entries[:index] + (changed,) + case.entries[index + 1 :])


def _structural(
    operator: Callable[[ArchiveCase, random.Random], ArchiveCase],
) -> Callable[..., ArchiveCase]:
    def apply(
        case: ArchiveCase,
        rng: random.Random,
        *,
        components: tuple[str, ...],
        parameters: GrammarParameters,
    ) -> ArchiveCase:
        return operator(case, rng)

    return apply


# Slot functions in the order of dispatch.OPERATOR_ORDER_V2.
SLOTS: tuple[Callable[..., ArchiveCase], ...] = (
    add_entry,
    _structural(remove_entry),
    _structural(duplicate_entry),
    _structural(reorder_entries),
    mutate_path,
    add_hardlink,
    add_symlink,
    mutate_link_target,
    set_mode,
    set_content,
)


def operators(
    observed_components: tuple[str, ...], parameters: GrammarParameters
) -> tuple[Operator, ...]:
    """The ten slots over ``m1.COMPONENTS`` + the caller's observed names.

    An observed name equal to a ``COMPONENTS`` token is not added again (W3 axis list: one
    uniform draw over the distinct pool), and repeated observed names count once.
    """
    extra = tuple(dict.fromkeys(n for n in observed_components if n not in m1.COMPONENTS))
    pool = m1.COMPONENTS + extra
    return tuple(functools.partial(slot, components=pool, parameters=parameters) for slot in SLOTS)

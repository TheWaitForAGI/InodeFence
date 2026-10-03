import random
from collections import Counter
from collections.abc import Callable
from dataclasses import replace

import pytest

from inodefence.model.archive import ArchiveCase, ArchiveEntry, EntryType
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
_MUTATIONS = (mutate, *_OPERATORS)
_SEEDS = range(32)
_RAW_TEXT = ("../outside", "./a", "a//b", "/absolute-looking", "한글/файл")


@pytest.fixture
def mixed_case() -> ArchiveCase:
    """All entry types, special mode bits, duplicate paths and distinct values."""
    return ArchiveCase(
        (
            ArchiveEntry("./a", EntryType.REGULAR, content=b"\0\xfffirst", mode=0o4640),
            ArchiveEntry("a//b", EntryType.DIRECTORY, mode=0o2750),
            ArchiveEntry("../outside", EntryType.HARDLINK, link_target="./a", mode=0o600),
            ArchiveEntry("/absolute-looking", EntryType.SYMLINK, link_target="a//b", mode=0o777),
            ArchiveEntry("./a", EntryType.REGULAR, content=b"replacement", mode=0o640),
        )
    )


def test_add_entry(mixed_case: ArchiveCase) -> None:
    for case in (ArchiveCase(()), mixed_case):
        for seed in _SEEDS:
            result = add_entry(case, random.Random(seed))
            assert len(result.entries) == len(case.entries) + 1
            assert result.entries[:-1] == case.entries
            added = result.entries[-1]
            assert added.entry_type == EntryType.REGULAR
            assert isinstance(added.content, bytes)
            assert added.link_target is None
            assert 0 <= added.mode <= 0o7777
            assert added.path and "\0" not in added.path


def test_remove_entry_preserves_relative_order(mixed_case: ArchiveCase) -> None:
    for seed in _SEEDS:
        result = remove_entry(mixed_case, random.Random(seed))
        assert len(result.entries) == len(mixed_case.entries) - 1
        assert any(
            result.entries == mixed_case.entries[:index] + mixed_case.entries[index + 1 :]
            for index in range(len(mixed_case.entries))
        )
    single = ArchiveCase((mixed_case.entries[0],))
    assert remove_entry(single, random.Random(0)) == ArchiveCase(())


def test_duplicate_entry_is_exact_and_preserves_existing_order(mixed_case: ArchiveCase) -> None:
    for seed in _SEEDS:
        result = duplicate_entry(mixed_case, random.Random(seed))
        assert len(result.entries) == len(mixed_case.entries) + 1
        extra = Counter(result.entries) - Counter(mixed_case.entries)
        assert sum(extra.values()) == 1
        assert all(entry in mixed_case.entries for entry in extra)
        assert any(
            result.entries[:index] + result.entries[index + 1 :] == mixed_case.entries
            for index in range(len(result.entries))
        )


@pytest.mark.parametrize("size", [2, 5])
def test_reorder_entries_changes_order_and_preserves_values(
    mixed_case: ArchiveCase, size: int
) -> None:
    case = ArchiveCase(mixed_case.entries[:size])
    for seed in _SEEDS:
        result = reorder_entries(case, random.Random(seed))
        assert result.entries != case.entries
        assert Counter(result.entries) == Counter(case.entries)


@pytest.mark.parametrize("order", [(0, 0, 1), (0, 1, 0), (1, 0, 0)])
def test_reorder_entries_changes_order_with_exact_duplicates(order: tuple[int, ...]) -> None:
    first = ArchiveEntry("./a", EntryType.REGULAR, content=b"first")
    second = replace(first, content=b"second")
    entries = tuple(replace((first, second)[index]) for index in order)
    case = ArchiveCase(entries)
    for seed in _SEEDS:
        result = reorder_entries(case, random.Random(seed))
        assert result != case
        assert Counter(result.entries) == Counter(case.entries)
        assert (
            sum(before != after for before, after in zip(case.entries, result.entries, strict=True))
            == 2
        )
        assert result == reorder_entries(case, random.Random(seed))
        assert case.entries == entries


@pytest.mark.parametrize("size", [2, 3])
def test_reorder_entries_all_exact_duplicates_no_op(size: int) -> None:
    entry = ArchiveEntry("./a", EntryType.REGULAR, content=b"first")
    case = ArchiveCase(tuple(replace(entry) for _ in range(size)))
    for seed in _SEEDS:
        assert reorder_entries(case, random.Random(seed)) == case


@pytest.mark.parametrize("kind", list(EntryType))
def test_mutate_path_changes_only_path(kind: EntryType) -> None:
    original = ArchiveEntry(
        "a//b",
        kind,
        content=b"\0\xffpayload" if kind == EntryType.REGULAR else None,
        link_target="../raw//target" if kind in (EntryType.HARDLINK, EntryType.SYMLINK) else None,
        mode=0o6754,
    )
    case = ArchiveCase((original,))
    for seed in _SEEDS:
        result = mutate_path(case, random.Random(seed))
        assert len(result.entries) == 1
        changed = result.entries[0]
        assert changed.path != original.path
        assert replace(changed, path=original.path) == original


def test_mutate_path_changes_exactly_one_entry(mixed_case: ArchiveCase) -> None:
    for seed in _SEEDS:
        result = mutate_path(mixed_case, random.Random(seed))
        assert len(result.entries) == len(mixed_case.entries)
        changed = [
            (before, after)
            for before, after in zip(mixed_case.entries, result.entries, strict=True)
            if before != after
        ]
        assert len(changed) == 1
        before, after = changed[0]
        assert after.path != before.path
        assert replace(after, path=before.path) == before


def test_add_hardlink(mixed_case: ArchiveCase) -> None:
    for seed in _SEEDS:
        result = add_hardlink(mixed_case, random.Random(seed))
        assert len(result.entries) == len(mixed_case.entries) + 1
        assert result.entries[:-1] == mixed_case.entries
        added = result.entries[-1]
        assert added.entry_type == EntryType.HARDLINK
        assert added.content is None
        assert added.link_target
        assert added.link_target in {entry.path for entry in mixed_case.entries}


def test_add_symlink(mixed_case: ArchiveCase) -> None:
    for case in (ArchiveCase(()), mixed_case):
        for seed in _SEEDS:
            result = add_symlink(case, random.Random(seed))
            assert len(result.entries) == len(case.entries) + 1
            assert result.entries[:-1] == case.entries
            added = result.entries[-1]
            assert added.entry_type == EntryType.SYMLINK
            assert added.content is None
            assert added.link_target


@pytest.mark.parametrize("kind", [EntryType.HARDLINK, EntryType.SYMLINK])
def test_mutate_link_target_changes_only_target(kind: EntryType) -> None:
    original = ArchiveEntry("./link//name", kind, link_target="../raw//target", mode=0o4751)
    case = ArchiveCase((original,))
    for seed in _SEEDS:
        result = mutate_link_target(case, random.Random(seed))
        assert len(result.entries) == 1
        changed = result.entries[0]
        assert changed.link_target != original.link_target
        assert replace(changed, link_target=original.link_target) == original


def test_mutate_link_target_changes_exactly_one_link(mixed_case: ArchiveCase) -> None:
    for seed in _SEEDS:
        result = mutate_link_target(mixed_case, random.Random(seed))
        assert len(result.entries) == len(mixed_case.entries)
        changed = [
            (before, after)
            for before, after in zip(mixed_case.entries, result.entries, strict=True)
            if before != after
        ]
        assert len(changed) == 1
        before, after = changed[0]
        assert before.entry_type in (EntryType.HARDLINK, EntryType.SYMLINK)
        assert after.link_target != before.link_target
        assert replace(after, link_target=before.link_target) == before


@pytest.mark.parametrize(
    "operator",
    (remove_entry, duplicate_entry, reorder_entries, mutate_path, add_hardlink, mutate_link_target),
)
def test_empty_case_no_op(operator: Callable[[ArchiveCase, random.Random], ArchiveCase]) -> None:
    case = ArchiveCase(())
    for seed in _SEEDS:
        assert operator(case, random.Random(seed)) == case


def test_inapplicable_operators_no_op(mixed_case: ArchiveCase) -> None:
    single = ArchiveCase((mixed_case.entries[0],))
    no_links = ArchiveCase((mixed_case.entries[0], mixed_case.entries[1]))
    for seed in _SEEDS:
        assert reorder_entries(single, random.Random(seed)) == single
        assert mutate_link_target(no_links, random.Random(seed)) == no_links


@pytest.mark.parametrize("operator", _MUTATIONS)
def test_original_case_unchanged(
    mixed_case: ArchiveCase, operator: Callable[[ArchiveCase, random.Random], ArchiveCase]
) -> None:
    original_entries = mixed_case.entries
    before = ArchiveCase(tuple(replace(entry) for entry in original_entries))
    for seed in _SEEDS:
        operator(mixed_case, random.Random(seed))
        assert mixed_case == before
        assert mixed_case.entries is original_entries


@pytest.mark.parametrize("operator", _MUTATIONS)
def test_deterministic_rng(
    mixed_case: ArchiveCase, operator: Callable[[ArchiveCase, random.Random], ArchiveCase]
) -> None:
    for case in (ArchiveCase(()), mixed_case):
        for seed in (*_SEEDS, 1234):
            first = operator(case, random.Random(seed))
            second = operator(case, random.Random(seed))
            assert first == second


def test_only_caller_rng_is_used(mixed_case: ArchiveCase, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_global_random(*args: object, **kwargs: object) -> None:
        raise AssertionError("mutation must use the caller's RNG")

    before = random.getstate()
    for name in (
        "choice",
        "choices",
        "randrange",
        "randint",
        "sample",
        "shuffle",
        "randbytes",
        "random",
    ):
        monkeypatch.setattr(random, name, fail_global_random)
    for operator in _MUTATIONS:
        for case in (ArchiveCase(()), mixed_case):
            operator(case, random.Random(1234))
    assert random.getstate() == before


@pytest.mark.parametrize("operator", _MUTATIONS)
def test_constructor_invariants(
    mixed_case: ArchiveCase, operator: Callable[[ArchiveCase, random.Random], ArchiveCase]
) -> None:
    for case in (ArchiveCase(()), ArchiveCase((mixed_case.entries[0],)), mixed_case):
        for seed in _SEEDS:
            result = operator(case, random.Random(seed))
            assert isinstance(result, ArchiveCase)
            assert isinstance(result.entries, tuple)
            assert all(isinstance(entry, ArchiveEntry) for entry in result.entries)
            rebuilt = ArchiveCase(
                tuple(
                    ArchiveEntry(
                        entry.path, entry.entry_type, entry.content, entry.link_target, entry.mode
                    )
                    for entry in result.entries
                )
            )
            assert rebuilt == result


@pytest.mark.parametrize("raw", _RAW_TEXT)
def test_raw_spelling_survives_path_and_link_mutations(raw: str) -> None:
    entry = ArchiveEntry(raw, EntryType.REGULAR, content=b"raw")
    case = ArchiveCase((entry,))
    symlink_targets: set[str] = set()
    for seed in _SEEDS:
        changed_path = mutate_path(case, random.Random(seed)).entries[0].path
        assert raw in changed_path
        assert 0 < len(changed_path) - len(raw) <= 3
        assert duplicate_entry(case, random.Random(seed)).entries == (entry, entry)
        hardlink = add_hardlink(case, random.Random(seed)).entries[-1]
        assert hardlink.link_target == raw
        symlink_target = add_symlink(case, random.Random(seed)).entries[-1].link_target
        assert symlink_target is not None
        symlink_targets.add(symlink_target)
    assert raw in symlink_targets
    assert any(target != raw for target in symlink_targets)


@pytest.mark.parametrize("raw", _RAW_TEXT)
@pytest.mark.parametrize("kind", [EntryType.HARDLINK, EntryType.SYMLINK])
def test_raw_link_target_spelling_is_preserved(raw: str, kind: EntryType) -> None:
    entry = ArchiveEntry("./link//name", kind, link_target=raw)
    case = ArchiveCase((entry,))
    for seed in _SEEDS:
        changed = mutate_link_target(case, random.Random(seed)).entries[0]
        assert changed.link_target is not None
        assert raw in changed.link_target
        assert 0 < len(changed.link_target) - len(raw) <= 3
        assert replace(changed, link_target=raw) == entry


@pytest.mark.parametrize("operator", (add_entry, add_hardlink, add_symlink))
def test_added_path_collisions_are_preserved(
    operator: Callable[[ArchiveCase, random.Random], ArchiveCase],
) -> None:
    # Reuse a generated path with the same case shape/RNG state, without relying
    # on a particular seed's spelling or internal random-call sequence.
    probe = ArchiveCase((ArchiveEntry("placeholder", EntryType.REGULAR, content=b""),))
    path = operator(probe, random.Random(1234)).entries[-1].path
    original = ArchiveEntry(path, EntryType.REGULAR, content=b"original")
    result = operator(ArchiveCase((original,)), random.Random(1234))
    assert len(result.entries) == 2
    assert result.entries[0] == original
    assert result.entries[0].path == result.entries[1].path == path

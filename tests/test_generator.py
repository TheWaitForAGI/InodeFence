"""Explicit minimal seeds: deterministic logical cases, independent of IO/target."""

import builtins
import random
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from inodefence.generator import minimal_seed_corpus
from inodefence.model import EntryType, canonical_json


def test_minimal_seeds_have_declared_order_and_normal_dependencies() -> None:
    regular, directory, hardlink, symlink = minimal_seed_corpus()
    assert [(entry.path, entry.entry_type) for entry in regular.entries] == [
        ("a.txt", EntryType.REGULAR)
    ]
    assert [(entry.path, entry.entry_type) for entry in directory.entries] == [
        ("dir/", EntryType.DIRECTORY),
        ("dir/a.txt", EntryType.REGULAR),
    ]
    for case, kind in ((hardlink, EntryType.HARDLINK), (symlink, EntryType.SYMLINK)):
        first, link = case.entries
        assert first == regular.entries[0]
        assert link.path == "b.txt" and link.entry_type == kind
        assert link.link_target == first.path == "a.txt"
        assert link.content is None
        assert link.mode == (0o644 if kind == EntryType.HARDLINK else 0o777)
    assert directory.entries[0].mode == 0o755
    for case in minimal_seed_corpus():
        for entry in case.entries:
            if entry.entry_type == EntryType.REGULAR:
                assert entry.content == b"hello inodefence" and entry.mode == 0o644


def test_repeat_calls_have_same_cases_ids_and_canonical_order() -> None:
    first, second = minimal_seed_corpus(), minimal_seed_corpus()
    assert first == second
    assert tuple(case.case_id for case in first) == tuple(case.case_id for case in second)
    assert tuple(canonical_json(case) for case in first) == tuple(
        canonical_json(case) for case in second
    )
    assert len(first) == len({case.case_id for case in first}) == 4


def test_seed_collection_and_cases_are_immutable() -> None:
    seeds = minimal_seed_corpus()
    assert isinstance(seeds, tuple)
    for case in seeds:
        assert isinstance(case.entries, tuple)
        for record, name, replacement in (
            (case, "entries", ()),
            (case.entries[0], "path", "changed"),
        ):
            with pytest.raises(FrozenInstanceError):
                setattr(record, name, replacement)
    assert seeds == minimal_seed_corpus()


def test_generation_has_no_filesystem_io_or_randomness(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("seed generation must not access filesystem or randomness")

    before = random.getstate()
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(random, "Random", forbidden)
    assert len(minimal_seed_corpus()) == 4
    assert random.getstate() == before

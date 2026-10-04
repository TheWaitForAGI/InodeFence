"""M1 representation, deterministic growth and USTAR composition contracts."""

import io
import random
import tarfile
from dataclasses import replace

import pytest

from inodefence.builder import build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, canonical_json
from inodefence.mutator import MutationPolicy, m1, mutate, mutate_with_policy


class ScriptedRandom(random.Random):
    """Assert every declared random choice and range; no implicit retries."""

    def __init__(self, choices=(), ranges=()):
        super().__init__(0)
        self._scripted_choices = iter(choices)
        self._scripted_ranges = iter(ranges)

    def choice(self, seq):
        value = next(self._scripted_choices)
        assert value in seq
        return value

    def randrange(self, start, stop=None, step=1):
        value = next(self._scripted_ranges)
        assert value in range(0, start) if stop is None else value in range(start, stop, step)
        return value


def _case():
    return ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, content=b"input"),))


@pytest.mark.parametrize("operator", m1.OPERATORS)
def test_each_operator_is_deterministic_immutable_and_buildable(operator):
    case = ArchiveCase(
        (
            *_case().entries,
            ArchiveEntry("dir//", EntryType.DIRECTORY),
            ArchiveEntry("link", EntryType.HARDLINK, link_target="a"),
            ArchiveEntry("sym", EntryType.SYMLINK, link_target="./link"),
        )
    )
    original = canonical_json(case)
    for seed in range(32):
        rng, restored = random.Random(seed), random.Random(0)
        rng.random()
        restored.setstate(rng.getstate())
        first, second = operator(case, rng), operator(case, restored)
        assert first == second and rng.getstate() == restored.getstate()
        rebuilt = ArchiveCase(tuple(replace(entry) for entry in first.entries))
        assert first.case_id == second.case_id == rebuilt.case_id
        assert build_tar(first) == build_tar(second)
        assert canonical_json(case) == original


def test_fresh_nested_raw_spelling_and_insertion_position():
    # Reuse=False, prefix, separator, three components, directory type.
    rng = ScriptedRandom((False, "../", "//", "dir", ".", "item", EntryType.DIRECTORY), (3, 0))
    child = m1.add_entry(_case(), rng)
    assert child.entries[0].path == "../dir//.//item"
    assert child.entries[0].entry_type == EntryType.DIRECTORY
    assert child.entries[1:] == _case().entries
    with tarfile.open(fileobj=io.BytesIO(build_tar(child)), mode="r:") as archive:
        assert archive.getmembers()[0].name == "../dir//.//item"


def test_controlled_name_reuse_can_change_type_without_repair_or_dedup():
    rng = ScriptedRandom((True, "a", EntryType.DIRECTORY), (1,))
    child = m1.add_entry(_case(), rng)
    assert tuple(entry.path for entry in child.entries) == ("a", "a")
    assert tuple(entry.entry_type for entry in child.entries) == (
        EntryType.REGULAR,
        EntryType.DIRECTORY,
    )
    build_tar(child)


@pytest.mark.parametrize("kind", (EntryType.HARDLINK, EntryType.SYMLINK))
def test_link_composition_targets_an_existing_link_with_independent_name(kind):
    case = ArchiveCase((*_case().entries, ArchiveEntry("first", kind, link_target="a")))
    if kind == EntryType.HARDLINK:
        choices = ("first", False, "", "/", "b")
    else:
        choices = (True, "first", False, "", "/", "b")
    rng = ScriptedRandom(choices, (1, 0))
    operator = m1.add_hardlink if kind == EntryType.HARDLINK else m1.add_symlink
    child = operator(case, rng)
    assert child.entries[0].path == "b" and child.entries[0].link_target == "first"
    assert child.entries[1:] == case.entries
    build_tar(child)


def test_link_target_raw_affix_over_bound_is_noop_without_retry():
    case = ArchiveCase((ArchiveEntry("link", EntryType.SYMLINK, link_target="é" * 50),))
    rng = ScriptedRandom((0, True, ("", "/")))
    assert m1.mutate_link_target(case, rng) is case
    build_tar(case)


@pytest.mark.parametrize(
    "operator",
    (
        m1.remove_entry,
        m1.duplicate_entry,
        m1.reorder_entries,
        m1.mutate_path,
        m1.add_hardlink,
        m1.mutate_link_target,
    ),
)
def test_inapplicable_operators_are_noops_without_random_draws(operator):
    case, rng = ArchiveCase(()), random.Random(11)
    before = rng.getstate()
    assert operator(case, rng) is case and rng.getstate() == before


def test_multistep_policy_growth_preserves_buildability_and_logical_lineage():
    for seed in range(12):
        first = second = ArchiveCase(())
        rng, restored = random.Random(seed), random.Random(seed)
        for _ in range(80):
            first = mutate_with_policy(first, rng, MutationPolicy.M1)
            second = mutate_with_policy(second, restored, MutationPolicy.M1)
            assert first.case_id == second.case_id
            assert rng.getstate() == restored.getstate()
            build_tar(first)


def test_legacy_policy_keeps_original_draws_and_unknown_ids_fail_before_draws():
    rng, old = random.Random(3), random.Random(3)
    first = second = _case()
    for _ in range(40):
        first = mutate_with_policy(first, rng, MutationPolicy.LEGACY)
        second = mutate(second, old)
        assert first == second and rng.getstate() == old.getstate()
    before = rng.getstate()
    with pytest.raises(ValueError):
        mutate_with_policy(first, rng, "unknown")  # type: ignore[arg-type]
    assert rng.getstate() == before
    with pytest.raises(ValueError):
        MutationPolicy("unknown")

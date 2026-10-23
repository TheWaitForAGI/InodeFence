"""A3 reserves the original reorder probability slot and its random draws."""

import random

import pytest

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.mutator import MutationPolicy, m1, m1_addressing, mutate_with_policy, operators


@pytest.mark.parametrize(
    "full,ablated,table",
    (
        (MutationPolicy.LEGACY, MutationPolicy.LEGACY_NO_REORDER, operators._OPERATORS),
        (MutationPolicy.M1, MutationPolicy.M1_NO_REORDER, m1.OPERATORS),
        (
            MutationPolicy.M1_PROTECTED_COMPONENTS,
            MutationPolicy.M1_PROTECTED_COMPONENTS_NO_REORDER,
            m1_addressing.OPERATORS,
        ),
    ),
)
def test_all_slots_keep_weights_and_rng_draws_and_only_reorder_output_is_removed(
    full, ablated, table
):
    case = ArchiveCase(
        (
            ArchiveEntry("a", EntryType.REGULAR, content=b"a"),
            ArchiveEntry("b", EntryType.SYMLINK, link_target="./a"),
            ArchiveEntry("dir", EntryType.DIRECTORY),
        )
    )
    selected = set()
    for seed in range(128):
        probe, rng, ablated_rng = random.Random(seed), random.Random(seed), random.Random(seed)
        slot = probe.choice(table)
        selected.add(slot)
        ordinary = mutate_with_policy(case, rng, full)
        reduced = mutate_with_policy(case, ablated_rng, ablated)
        assert rng.getstate() == ablated_rng.getstate()
        if slot is operators.reorder_entries:
            assert ordinary != case
            assert reduced is case
        else:
            assert reduced == ordinary
    assert selected == set(table)


@pytest.mark.parametrize(
    "policy",
    (
        MutationPolicy.LEGACY_NO_REORDER,
        MutationPolicy.M1_NO_REORDER,
        MutationPolicy.M1_PROTECTED_COMPONENTS_NO_REORDER,
    ),
)
def test_reorder_slot_is_noop_for_inapplicable_case_without_resampling(policy):
    empty = ArchiveCase(())
    table = {
        MutationPolicy.LEGACY_NO_REORDER: operators._OPERATORS,
        MutationPolicy.M1_NO_REORDER: m1.OPERATORS,
        MutationPolicy.M1_PROTECTED_COMPONENTS_NO_REORDER: m1_addressing.OPERATORS,
    }[policy]

    class ReorderOnly(random.Random):
        def choice(self, seq):
            assert seq == table  # Any attempt to resample or draw an entry fails.
            return operators.reorder_entries

    rng = ReorderOnly(3)
    assert mutate_with_policy(empty, rng, policy) is empty


def test_ablations_have_distinct_versioned_ids_and_do_not_change_legacy_default():
    assert len({policy.value for policy in MutationPolicy}) == 7
    assert MutationPolicy.LEGACY.value == "uniform-generic-v1"
    assert MutationPolicy.M1.value == "uniform-generic-m1-v1"
    assert (
        MutationPolicy.M1_PROTECTED_COMPONENTS.value == "uniform-generic-m1-protected-components-v1"
    )
    assert MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK.value == (
        "uniform-generic-m1-protected-components-escape-hardlink-v1"
    )


def test_escape_hardlink_policy_differs_only_in_the_hardlink_slot():
    """The escape policy reuses every protected-components slot but the hardlink.

    Only the ADD_HARDLINK slot (index 5) is replaced; the table is otherwise the
    same object sequence, preserving slot order, distribution and seed draws.
    """
    assert len(m1_addressing.ESCAPE_OPERATORS) == len(m1_addressing.OPERATORS) == 6 + 2
    for index, (escape_slot, base_slot) in enumerate(
        zip(m1_addressing.ESCAPE_OPERATORS, m1_addressing.OPERATORS, strict=True)
    ):
        if index == 5:
            assert escape_slot is m1_addressing.add_escaping_hardlink
            assert escape_slot is not base_slot
        else:
            assert escape_slot is base_slot


def test_escape_hardlink_policy_is_bounded_deterministic_and_builder_compatible():
    from inodefence.builder import build_tar
    from inodefence.generator import minimal_seed_corpus

    policy = MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK
    for seed in range(32):
        first_rng = random.Random(seed)
        second_rng = random.Random(seed)
        first = minimal_seed_corpus()[seed % 4]
        second = first
        for _ in range(32):
            first = mutate_with_policy(first, first_rng, policy)
            second = mutate_with_policy(second, second_rng, policy)
            assert first == second
            assert first_rng.getstate() == second_rng.getstate()
            build_tar(first)

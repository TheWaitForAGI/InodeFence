"""A3 reserves the original reorder probability slot and its random draws."""

import random

import pytest

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.mutator import MutationPolicy, m1, mutate_with_policy, operators


@pytest.mark.parametrize(
    "full,ablated,table",
    (
        (MutationPolicy.LEGACY, MutationPolicy.LEGACY_NO_REORDER, operators._OPERATORS),
        (MutationPolicy.M1, MutationPolicy.M1_NO_REORDER, m1.OPERATORS),
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


@pytest.mark.parametrize("policy", (MutationPolicy.LEGACY_NO_REORDER, MutationPolicy.M1_NO_REORDER))
def test_reorder_slot_is_noop_for_inapplicable_case_without_resampling(policy):
    empty = ArchiveCase(())
    table = operators._OPERATORS if policy == MutationPolicy.LEGACY_NO_REORDER else m1.OPERATORS

    class ReorderOnly(random.Random):
        def choice(self, seq):
            assert seq == table  # Any attempt to resample or draw an entry fails.
            return operators.reorder_entries

    rng = ReorderOnly(3)
    assert mutate_with_policy(empty, rng, policy) is empty


def test_ablations_have_distinct_versioned_ids_and_do_not_change_legacy_default():
    assert len({policy.value for policy in MutationPolicy}) == 4
    assert MutationPolicy.LEGACY.value == "uniform-generic-v1"
    assert MutationPolicy.M1.value == "uniform-generic-m1-v1"

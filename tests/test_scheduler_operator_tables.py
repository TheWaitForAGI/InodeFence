"""Schedulers draw from and record weights over an explicit operator table (v2 U1/C1).

Every existing policy uses the eight-slot V1 table; the default must keep today's draws
and weight records exactly (``tests/test_registered_arms_golden.py`` pins the campaigns,
this file pins the table contract itself).
"""

import random

import pytest

from inodefence.effect_scheduler import (
    EffectAdaptiveMutationScheduler,
    EffectUniformMutationScheduler,
)
from inodefence.mutation_scheduler import (
    MutationSelection,
    TransitionAdaptiveScheduler,
    UniformMutationScheduler,
)
from inodefence.mutator import (
    OPERATOR_ORDER_V1,
    OPERATOR_ORDER_V2,
    OPERATOR_TABLES,
    MutationOperatorId,
    MutationPolicy,
    operator_ids,
)

V1_VALUES = [
    "add_entry",
    "remove_entry",
    "duplicate_entry",
    "reorder_entries",
    "mutate_path",
    "add_hardlink",
    "add_symlink",
    "mutate_link_target",
]
SCHEDULERS = (
    EffectUniformMutationScheduler,
    EffectAdaptiveMutationScheduler,
    UniformMutationScheduler,
    TransitionAdaptiveScheduler,
)


def test_v1_table_is_the_eight_existing_slots_in_order() -> None:
    assert [operator.value for operator in OPERATOR_ORDER_V1] == V1_VALUES
    # V2 (`b-grammar-v2-freeze-3`, #512 U3) is appended; V1 stays first and unchanged.
    assert OPERATOR_TABLES == (OPERATOR_ORDER_V1, OPERATOR_ORDER_V2)


@pytest.mark.parametrize(
    "policy", [p for p in MutationPolicy if p != MutationPolicy.V2_FREEZE3_FIXED_BASELINE]
)
def test_every_existing_policy_draws_from_v1(policy: MutationPolicy) -> None:
    assert operator_ids(policy) == OPERATOR_ORDER_V1


@pytest.mark.parametrize("scheduler_type", SCHEDULERS)
def test_default_table_records_v1_weights(scheduler_type: type) -> None:
    scheduler = scheduler_type()
    assert [(operator.value, weight) for operator, weight in scheduler.weights] == [
        (value, 1) for value in V1_VALUES
    ]
    explicit = scheduler_type(operators=OPERATOR_ORDER_V1)
    assert explicit.weights == scheduler.weights


@pytest.mark.parametrize("scheduler_type", SCHEDULERS)
def test_default_and_explicit_v1_draw_identically(scheduler_type: type) -> None:
    default, explicit = scheduler_type(), scheduler_type(operators=OPERATOR_ORDER_V1)
    first, second = random.Random(7), random.Random(7)
    for _ in range(50):
        assert default.choose_operator(OPERATOR_ORDER_V1, first) == explicit.choose_operator(
            OPERATOR_ORDER_V1, second
        )
    assert first.getstate() == second.getstate()


@pytest.mark.parametrize("scheduler_type", SCHEDULERS)
def test_unknown_table_is_refused(scheduler_type: type) -> None:
    reordered = tuple(reversed(OPERATOR_ORDER_V1))
    with pytest.raises(ValueError, match="known operator table"):
        scheduler_type(operators=reordered)
    with pytest.raises(ValueError, match="stable complete operator table"):
        scheduler_type().choose_operator(reordered, random.Random(0))


def test_weight_snapshot_over_an_unknown_table_is_refused() -> None:
    partial = tuple((operator, 1) for operator in OPERATOR_ORDER_V1[:-1])
    with pytest.raises(ValueError, match="every operator in stable order"):
        MutationSelection(MutationOperatorId.ADD_ENTRY, partial, 1)

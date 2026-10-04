"""Explicit versioned mutation dispatch; legacy draws and behavior stay stable."""

import random
from enum import StrEnum

from inodefence.model.archive import ArchiveCase

from . import m1, operators


class MutationPolicy(StrEnum):
    LEGACY = "uniform-generic-v1"
    M1 = "uniform-generic-m1-v1"
    LEGACY_NO_REORDER = "uniform-generic-no-reorder-v1"
    M1_NO_REORDER = "uniform-generic-m1-no-reorder-v1"


def mutate_with_policy(
    case: ArchiveCase, rng: random.Random, policy: MutationPolicy
) -> ArchiveCase:
    """Draw one uniform slot; A3 discards reorder output but keeps its RNG draws.

    No slot is removed, retried or reweighted. For a given input and RNG state,
    ablated and full policies select the same slot and consume identical draws.
    Campaign streams may subsequently differ because their parent cases differ.
    """
    if not isinstance(policy, MutationPolicy):
        raise ValueError("policy must be a supported MutationPolicy")
    if policy == MutationPolicy.LEGACY:
        return operators.mutate(case, rng)
    table = operators._OPERATORS if policy == MutationPolicy.LEGACY_NO_REORDER else m1.OPERATORS
    operator = rng.choice(table)
    child = operator(case, rng)
    if policy in (MutationPolicy.LEGACY_NO_REORDER, MutationPolicy.M1_NO_REORDER) and (
        operator is operators.reorder_entries
    ):
        return case
    return child

"""Explicit versioned mutation dispatch; legacy draws and behavior stay stable."""

import random
from enum import StrEnum

from inodefence.model.archive import ArchiveCase

from . import m1
from .operators import mutate


class MutationPolicy(StrEnum):
    LEGACY = "uniform-generic-v1"
    M1 = "uniform-generic-m1-v1"


def mutate_with_policy(
    case: ArchiveCase, rng: random.Random, policy: MutationPolicy
) -> ArchiveCase:
    """Draw one uniform operator slot, retaining inapplicable/no-op outcomes."""
    if not isinstance(policy, MutationPolicy):
        raise ValueError("policy must be a supported MutationPolicy")
    if policy == MutationPolicy.LEGACY:
        return mutate(case, rng)
    return rng.choice(m1.OPERATORS)(case, rng)

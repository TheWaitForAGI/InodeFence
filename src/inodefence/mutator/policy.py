"""Explicit versioned mutation dispatch; legacy draws and behavior stay stable."""

import random
from enum import StrEnum

from inodefence.model.archive import ArchiveCase


class MutationPolicy(StrEnum):
    LEGACY = "uniform-generic-v1"
    M1 = "uniform-generic-m1-v1"
    M1_PROTECTED_COMPONENTS = "uniform-generic-m1-protected-components-v1"
    LEGACY_NO_REORDER = "uniform-generic-no-reorder-v1"
    M1_NO_REORDER = "uniform-generic-m1-no-reorder-v1"
    M1_PROTECTED_COMPONENTS_NO_REORDER = "uniform-generic-m1-protected-components-no-reorder-v1"
    # Additive: same slots/draws as M1_PROTECTED_COMPONENTS, but the hardlink slot
    # addresses an extraction-root-escaping target instead of an in-archive path.
    M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK = (
        "uniform-generic-m1-protected-components-escape-hardlink-v1"
    )


def mutate_with_policy(
    case: ArchiveCase, rng: random.Random, policy: MutationPolicy
) -> ArchiveCase:
    """Draw one uniform slot; A3 discards reorder output but keeps its RNG draws.

    No slot is removed, retried or reweighted. For a given input and RNG state,
    ablated and full policies select the same slot and consume identical draws.
    Campaign streams may subsequently differ because their parent cases differ.
    """
    # Local import keeps the enum definition independent from dispatch tables.
    from .dispatch import mutate_attempt_with_policy

    return mutate_attempt_with_policy(case, rng, policy).child_case

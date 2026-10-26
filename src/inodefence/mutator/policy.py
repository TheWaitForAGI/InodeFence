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
    # Additive, token-clean: the escaping-hardlink slot over the *generic* M1
    # vocabulary only (a,b,dir,file,item,.,..). It carries no target-specific
    # components, so an escaping target can never spell a name the generic
    # alphabet does not contain. Used as the reachability floor arm.
    M1_GENERIC_ESCAPE_HARDLINK = "uniform-generic-m1-escape-hardlink-v1"
    # Additive, state-aware: the generic escaping-hardlink slot whose link-target
    # segment pool is the generic vocabulary PLUS the names of objects the run has
    # actually observed (ObjectSnapshot paths from the general filesystem tree, not
    # the protected-path list). The caller (campaign) supplies the observed names;
    # with none supplied it behaves exactly like M1_GENERIC_ESCAPE_HARDLINK. This
    # lets a run reach an external reference target by observing its name, without
    # any target-specific token being hardcoded (target-agnostic).
    M1_STATE_AWARE_ESCAPE_HARDLINK = "uniform-generic-m1-state-aware-escape-hardlink-v1"
    # Additive blind control for M1_STATE_AWARE_ESCAPE_HARDLINK: identical slots,
    # draws and observed-name mechanism, except the observed-name pool DROPS any
    # segment whose object lies in the EXTERNAL region (kept: EXTRACTION/HARNESS
    # names the extraction itself produced). The filter is by common Region, not by
    # any specific name, so it stays target-agnostic. This removes the run's ability
    # to observe the identity (name) of a pre-existing external object, isolating
    # object-identity observation as the causal input: with it (full) a run can
    # compose a reference to an external object, without it (this arm) it cannot.
    M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND = "uniform-generic-m1-state-aware-escape-hardlink-blind-v1"


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

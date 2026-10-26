"""Inspectable operator identity and explicit application; no search feedback."""

import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from inodefence.model import ArchiveCase

from . import m1, m1_addressing, operators
from .policy import MutationPolicy


class MutationOperatorId(StrEnum):
    ADD_ENTRY = "add_entry"
    REMOVE_ENTRY = "remove_entry"
    DUPLICATE_ENTRY = "duplicate_entry"
    REORDER_ENTRIES = "reorder_entries"
    MUTATE_PATH = "mutate_path"
    ADD_HARDLINK = "add_hardlink"
    ADD_SYMLINK = "add_symlink"
    MUTATE_LINK_TARGET = "mutate_link_target"


OPERATOR_ORDER = tuple(MutationOperatorId)


@dataclass(frozen=True, slots=True)
class MutationAttempt:
    serialization_schema: ClassVar[int] = 1

    operator_id: MutationOperatorId
    mutation_policy: MutationPolicy
    parent_case_id: str
    child_case: ArchiveCase
    applied: bool

    def __post_init__(self) -> None:
        if not isinstance(self.operator_id, MutationOperatorId) or not isinstance(
            self.mutation_policy, MutationPolicy
        ):
            raise ValueError("mutation attempt requires stable operator and policy IDs")
        if not isinstance(self.parent_case_id, str) or not self.parent_case_id:
            raise ValueError("mutation attempt requires a parent case ID")
        if not isinstance(self.child_case, ArchiveCase) or type(self.applied) is not bool:
            raise ValueError("mutation attempt requires an ArchiveCase and applied flag")


def operator_ids(policy: MutationPolicy) -> tuple[MutationOperatorId, ...]:
    if not isinstance(policy, MutationPolicy):
        raise ValueError("policy must be a supported MutationPolicy")
    return OPERATOR_ORDER


def _operator_table(
    policy: MutationPolicy,
) -> tuple[Callable[[ArchiveCase, random.Random], ArchiveCase], ...]:
    if policy in (MutationPolicy.LEGACY, MutationPolicy.LEGACY_NO_REORDER):
        return operators._OPERATORS
    if policy in (MutationPolicy.M1, MutationPolicy.M1_NO_REORDER):
        return m1.OPERATORS
    if policy in (
        MutationPolicy.M1_PROTECTED_COMPONENTS,
        MutationPolicy.M1_PROTECTED_COMPONENTS_NO_REORDER,
    ):
        return m1_addressing.OPERATORS
    if policy == MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK:
        return m1_addressing.ESCAPE_OPERATORS
    if policy in (
        MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK,
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK,
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND,
    ):
        # Static default pool; the state-aware policies' observed-name pool is applied
        # per-call in apply_operator when the caller provides extra_components. The
        # blind control differs only in which observed names the caller accumulates.
        return m1_addressing.GENERIC_ESCAPE_OPERATORS
    raise AssertionError(f"unhandled mutation policy: {policy}")


_NO_REORDER_POLICIES = (
    MutationPolicy.LEGACY_NO_REORDER,
    MutationPolicy.M1_NO_REORDER,
    MutationPolicy.M1_PROTECTED_COMPONENTS_NO_REORDER,
)

# The state-aware escape policies accept a caller-supplied observed-name pool
# (full and its blind control); every other policy ignores extra_components.
_STATE_AWARE_POLICIES = (
    MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK,
    MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND,
)


def apply_operator(
    case: ArchiveCase,
    rng: random.Random,
    policy: MutationPolicy,
    operator_id: MutationOperatorId,
    *,
    extra_components: tuple[str, ...] = (),
) -> MutationAttempt:
    """Apply one selected slot; A3 still executes then discards reorder output.

    `extra_components` are observed object names the caller may supply only for the
    state-aware escaping-hardlink policies (full and its blind control); they extend
    those policies' generic vocabulary (never the protected-path list). Other
    policies ignore them, so the existing arms are byte-for-byte unchanged.
    """
    if not isinstance(case, ArchiveCase) or not isinstance(policy, MutationPolicy):
        raise ValueError("operator application requires ArchiveCase and MutationPolicy")
    if not isinstance(operator_id, MutationOperatorId):
        raise ValueError("operator_id must be a MutationOperatorId")
    if extra_components and policy not in _STATE_AWARE_POLICIES:
        raise ValueError("extra_components apply only to the state-aware escape policies")
    index = OPERATOR_ORDER.index(operator_id)
    if policy in _STATE_AWARE_POLICIES and extra_components:
        table = m1_addressing.state_aware_escape_operators(tuple(extra_components))
    else:
        table = _operator_table(policy)
    child = table[index](case, rng)
    if policy in _NO_REORDER_POLICIES and operator_id == MutationOperatorId.REORDER_ENTRIES:
        child = case
    return MutationAttempt(operator_id, policy, case.case_id, child, child != case)


def mutate_attempt_with_policy(
    case: ArchiveCase, rng: random.Random, policy: MutationPolicy
) -> MutationAttempt:
    """Uniform inspectable dispatch with the exact legacy choice argument.

    Selecting from the function table preserves custom Random test doubles as
    well as stdlib random.Random draws. The stable ID is derived afterward.
    """
    if not isinstance(policy, MutationPolicy):
        raise ValueError("policy must be a supported MutationPolicy")
    table = _operator_table(policy)
    operator = rng.choice(table)
    operator_id = OPERATOR_ORDER[table.index(operator)]
    child = operator(case, rng)
    if policy in _NO_REORDER_POLICIES and operator_id == MutationOperatorId.REORDER_ENTRIES:
        child = case
    return MutationAttempt(operator_id, policy, case.case_id, child, child != case)

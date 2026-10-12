"""Inspectable operator identity and explicit application; no search feedback."""

import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from inodefence.model import ArchiveCase

from . import m1, operators
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
    return m1.OPERATORS


def apply_operator(
    case: ArchiveCase,
    rng: random.Random,
    policy: MutationPolicy,
    operator_id: MutationOperatorId,
) -> MutationAttempt:
    """Apply one selected slot; A3 still executes then discards reorder output."""
    if not isinstance(case, ArchiveCase) or not isinstance(policy, MutationPolicy):
        raise ValueError("operator application requires ArchiveCase and MutationPolicy")
    if not isinstance(operator_id, MutationOperatorId):
        raise ValueError("operator_id must be a MutationOperatorId")
    index = OPERATOR_ORDER.index(operator_id)
    child = _operator_table(policy)[index](case, rng)
    if policy in (MutationPolicy.LEGACY_NO_REORDER, MutationPolicy.M1_NO_REORDER) and (
        operator_id == MutationOperatorId.REORDER_ENTRIES
    ):
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
    if policy in (MutationPolicy.LEGACY_NO_REORDER, MutationPolicy.M1_NO_REORDER) and (
        operator_id == MutationOperatorId.REORDER_ENTRIES
    ):
        child = case
    return MutationAttempt(operator_id, policy, case.case_id, child, child != case)

"""v2 random-chain R: one execution = a chain of m operator attempts from one seed (#510, D062).

The chain R (search policies ``R_UNRETAINED_SEED_CHAIN_M4``/``_M6``) is the v2 confirmatory R:
every execution draws a seed uniformly, draws ``m`` uniformly in ``1..m_max``, applies ``m``
operator **attempts** in sequence and executes only the final child; nothing is retained.

Convention ("ATTEMPTS", W3/W4 2026-11-18, same as W3's grammar_mc_v2 ``r_mode="depth"``):
* ``m`` counts operator attempts. An attempt whose result equals its input (``applied`` False:
  not applicable, over a bound, same value) still counts toward ``m`` and is recorded with
  ``applied`` False; it adds nothing to the lineage depth. The applied chain length is <= m.
* One execution = one chain = one budget unit, like an execution of any other arm, regardless of
  how many attempts the chain made.
* RNG order (one ``random.Random`` per campaign): parent seed draw (``select_case``), then
  ``m = rng.randint(1, m_max)``, then for each attempt the operator draw (the uniform scheduler's
  ``rng.choice``) followed by that operator's own draws.

Every arm uses the same MutationPolicy; only R's search policy differs, so the vocabulary and the
slot weights stay equal across arms. This module only composes ``apply_operator`` calls.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from inodefence.model import ArchiveCase

from .dispatch import MutationAttempt, MutationOperatorId, apply_operator
from .policy import MutationPolicy


@dataclass(frozen=True, slots=True)
class ChainLink:
    """One attempt of a chain: the operator drawn, whether it changed the case, its weight."""

    operator_id: MutationOperatorId
    applied: bool
    selected_weight: int

    def __post_init__(self) -> None:
        if not isinstance(self.operator_id, MutationOperatorId) or type(self.applied) is not bool:
            raise ValueError("chain link requires an operator ID and applied flag")
        if type(self.selected_weight) is not int or self.selected_weight <= 0:
            raise ValueError("chain link requires a positive integer selected weight")


@dataclass(frozen=True, slots=True)
class MutationChainAttempt:
    """A whole chain: the step it produced, its seed parent, final child and every attempt.

    A separate type from :class:`MutationAttempt` so that type's serialized form is unchanged.
    """

    serialization_schema: ClassVar[int] = 1

    index: int
    parent_case_id: str
    child_case: ArchiveCase
    links: tuple[ChainLink, ...]

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("chain index must be a nonnegative integer")
        if not isinstance(self.parent_case_id, str) or not self.parent_case_id:
            raise ValueError("chain requires a parent case ID")
        if not isinstance(self.child_case, ArchiveCase):
            raise ValueError("chain requires an ArchiveCase child")
        if (
            not isinstance(self.links, tuple)
            or not self.links
            or not all(isinstance(link, ChainLink) for link in self.links)
        ):
            raise ValueError("chain requires at least one typed link")

    @property
    def chain_length(self) -> int:
        """m: the number of attempts (no-op attempts included)."""
        return len(self.links)

    @property
    def applied_length(self) -> int:
        """The number of attempts that changed the case (the lineage depth this chain adds)."""
        return sum(link.applied for link in self.links)


def apply_chain(
    parent: ArchiveCase,
    rng: random.Random,
    policy: MutationPolicy,
    m: int,
    choose: Callable[[random.Random], tuple[MutationOperatorId, int]],
    *,
    extra_components: tuple[str, ...] = (),
) -> tuple[list[ChainLink], MutationAttempt]:
    """Apply ``m`` attempts; return the links and the composite attempt seed -> final child.

    ``choose(rng)`` draws one operator and returns it with its scheduler weight (the uniform
    scheduler: ``rng.choice`` over the policy's table, weight 1). The composite attempt carries the
    last operator ID, the seed as parent and the final child; ``applied`` is final child != seed.
    """
    if type(m) is not int or m < 1:
        raise ValueError("a chain needs at least one attempt")
    current = parent
    links: list[ChainLink] = []
    operator_id = None
    for _ in range(m):
        operator_id, weight = choose(rng)
        attempt = apply_operator(
            current, rng, policy, operator_id, extra_components=extra_components
        )
        links.append(ChainLink(operator_id, attempt.applied, weight))
        current = attempt.child_case
    assert operator_id is not None
    composite = MutationAttempt(operator_id, policy, parent.case_id, current, current != parent)
    return links, composite

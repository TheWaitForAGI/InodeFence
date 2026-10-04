"""Versioned search-policy core; execution and legacy campaign encoding stay separate."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from inodefence.model import ArchiveCase, RunResult

from ._novelty import NoveltyIndex
from .corpus import CorpusEntry, CorpusStats, FeedbackDecision
from .fingerprint import ViolationFingerprint
from .projection import FeedbackKey, FeedbackProjection, feedback_key


class SearchPolicy(StrEnum):
    B0 = "unretained-walk-v1"
    B1 = "state-v3-uniform-parent-v1"
    B3 = "state-v2-or-violation-v1-uniform-parent-v1"


@dataclass(frozen=True, slots=True)
class SearchDecision:
    """Full diagnostic novelty and explicit admission, independently inspectable.

    Interesting always means full state OR violation novelty. Admission uses the
    declared policy and never suppresses raw oracle evidence.
    """

    serialization_schema: ClassVar[int] = 2

    case_id: str
    state_novel: bool
    new_violation_fingerprints: tuple[ViolationFingerprint, ...]
    already_retained: bool
    admission_eligible: bool
    feedback_key_novel: bool

    def __post_init__(self) -> None:
        FeedbackDecision(
            self.case_id, self.state_novel, self.new_violation_fingerprints, self.already_retained
        )
        if type(self.admission_eligible) is not bool or type(self.feedback_key_novel) is not bool:
            raise ValueError("admission_eligible and feedback_key_novel must be bool")

    @property
    def interesting(self) -> bool:
        return self.state_novel or bool(self.new_violation_fingerprints)

    @property
    def retained(self) -> bool:
        return self.admission_eligible and not self.already_retained


class SearchState:
    """Caller-driven seed phase, full diagnostics, admission and parent selection.

    This is a policy core, not a second campaign engine. Observe initial cases in
    their declared order before selection. B0 holds the immutable seed bank and
    one active child; its diagnostic indexes grow but it retains no parents.
    Every post-seed observation advances its walk, regardless of target status,
    duplicate case identity or novelty. No execution, mutation or IO occurs here.
    """

    def __init__(
        self,
        initial_cases: Sequence[ArchiveCase],
        policy: SearchPolicy,
        *,
        projection: FeedbackProjection = FeedbackProjection.FULL,
    ) -> None:
        if not isinstance(policy, SearchPolicy):
            raise ValueError("policy must be a supported SearchPolicy")
        if not isinstance(projection, FeedbackProjection):
            raise ValueError("projection must be a supported FeedbackProjection")
        cases = tuple(initial_cases)
        if not cases or not all(isinstance(case, ArchiveCase) for case in cases):
            raise ValueError("initial cases must be nonempty ArchiveCase records")
        if len({case.case_id for case in cases}) != len(cases):
            raise ValueError("initial cases contain duplicate case IDs")
        self._policy = policy
        self._projection = projection
        self._keys: set[FeedbackKey] = set()
        self._seeds = cases
        self._novelty = NoveltyIndex()
        self._entries: list[CorpusEntry] = []
        self._retained_ids: set[str] = set()
        self._active: ArchiveCase | None = None

    @property
    def policy(self) -> SearchPolicy:
        return self._policy

    @property
    def projection(self) -> FeedbackProjection:
        return self._projection

    @property
    def unique_feedback_keys(self) -> int:
        """Projected-key count; stats.unique_states always counts full states."""
        return len(self._keys)

    def consider(self, result: RunResult) -> SearchDecision:
        index = self._novelty.observations
        is_seed = index < len(self._seeds)
        if is_seed and result.case != self._seeds[index]:
            raise ValueError("seed observations must match declared cases/order")
        key = feedback_key(result.signature, self.projection)
        key_novel = key not in self._keys
        state_novel, new, fingerprints = self._novelty.observe(result)
        self._keys.add(key)
        diagnostic = FeedbackDecision(
            result.case.case_id, state_novel, new, result.case.case_id in self._retained_ids
        )
        eligible = (
            False
            if self.policy == SearchPolicy.B0
            else key_novel
            if self.policy == SearchPolicy.B1
            else key_novel or bool(new)
        )
        decision = SearchDecision(
            diagnostic.case_id, state_novel, new, diagnostic.already_retained, eligible, key_novel
        )
        if decision.retained:
            self._entries.append(CorpusEntry(result.case, result.signature, fingerprints))
            self._retained_ids.add(result.case.case_id)
        if self.policy == SearchPolicy.B0 and not is_seed:
            self._active = result.case
        return decision

    def select_case(self, rng: random.Random) -> ArchiveCase:
        """B0 draws once from seeds; B1/B3 draw uniformly from retained parents."""
        if self._novelty.observations < len(self._seeds):
            raise ValueError("parent selection requires a completed seed phase")
        if self.policy == SearchPolicy.B0:
            if self._active is None:
                self._active = rng.choice(self._seeds)
            return self._active
        if not self._entries:
            raise ValueError("cannot select a case from an empty corpus")
        return rng.choice(self._entries).case

    @property
    def entries(self) -> tuple[CorpusEntry, ...]:
        return tuple(self._entries)

    @property
    def active_case(self) -> ArchiveCase | None:
        """B0 working parent, separate from retained-case accounting."""
        return self._active

    @property
    def stats(self) -> CorpusStats:
        return CorpusStats(
            self._novelty.observations,
            self._novelty.interesting_observations,
            len(self._entries),
            len(self._novelty.states),
            len(self._novelty.violations),
        )

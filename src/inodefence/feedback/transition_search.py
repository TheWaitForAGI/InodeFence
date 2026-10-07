"""Causally separated final-state and transition-retention policy core."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from inodefence.model import (
    ArchiveCase,
    StateSignature,
    TraceCompleteness,
    TraceTermination,
    TransitionFeedbackKey,
    TransitionRunResult,
)

from ._novelty import NoveltyIndex
from .fingerprint import ViolationFingerprint
from .transition_novelty import TransitionNoveltyIndex


class TransitionSearchPolicy(StrEnum):
    P0_FINAL_ONLY = "final-state-v3-or-violation-v1-uniform-mutation-v1"
    P1_TRANSITION_RETENTION = "transition-v1-or-violation-v1-uniform-mutation-v1"
    P2_TRANSITION_ADAPTIVE = "transition-v1-or-violation-v1-adaptive-mutation-v1"


@dataclass(frozen=True, slots=True)
class TransitionSearchDecision:
    """Independent full-state, violation and transition novelty diagnostics."""

    serialization_schema: ClassVar[int] = 1

    case_id: str
    full_state_novel: bool
    new_violation_fingerprints: tuple[ViolationFingerprint, ...]
    new_transition_keys: tuple[TransitionFeedbackKey, ...]
    transition_novel: bool
    already_retained: bool
    admission_eligible: bool
    trace_completeness: TraceCompleteness
    trace_termination: TraceTermination

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("transition decision requires a case ID")
        if not isinstance(self.new_violation_fingerprints, tuple) or not all(
            isinstance(item, ViolationFingerprint) for item in self.new_violation_fingerprints
        ):
            raise ValueError("decision violation novelty must be semantic fingerprints")
        if not isinstance(self.new_transition_keys, tuple) or not all(
            isinstance(item, TransitionFeedbackKey) for item in self.new_transition_keys
        ):
            raise ValueError("decision transition novelty must be feedback keys")
        if any(
            type(value) is not bool
            for value in (
                self.full_state_novel,
                self.transition_novel,
                self.already_retained,
                self.admission_eligible,
            )
        ):
            raise ValueError("decision flags must be bool")
        if self.transition_novel != bool(self.new_transition_keys):
            raise ValueError("transition_novel must exactly reflect new transition keys")
        if not isinstance(self.trace_completeness, TraceCompleteness) or not isinstance(
            self.trace_termination, TraceTermination
        ):
            raise ValueError("decision must preserve trace status")

    @property
    def interesting(self) -> bool:
        return (
            self.full_state_novel or self.transition_novel or bool(self.new_violation_fingerprints)
        )

    @property
    def retained(self) -> bool:
        return self.admission_eligible and not self.already_retained


@dataclass(frozen=True, slots=True)
class TransitionCorpusEntry:
    case: ArchiveCase
    admission_signature: StateSignature
    admission_transition_keys: tuple[TransitionFeedbackKey, ...]
    admission_violation_fingerprints: tuple[ViolationFingerprint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case, ArchiveCase) or not isinstance(
            self.admission_signature, StateSignature
        ):
            raise ValueError("transition corpus entry requires case and final signature")
        if not isinstance(self.admission_transition_keys, tuple) or not all(
            isinstance(item, TransitionFeedbackKey) for item in self.admission_transition_keys
        ):
            raise ValueError("transition corpus entry requires transition keys")
        if not isinstance(self.admission_violation_fingerprints, tuple) or not all(
            isinstance(item, ViolationFingerprint) for item in self.admission_violation_fingerprints
        ):
            raise ValueError("transition corpus entry requires violation fingerprints")


@dataclass(frozen=True, slots=True)
class TransitionSearchStats:
    observations: int
    interesting_observations: int
    retained_cases: int
    unique_full_states: int
    unique_transition_keys: int
    unique_violation_fingerprints: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (
                self.observations,
                self.interesting_observations,
                self.retained_cases,
                self.unique_full_states,
                self.unique_transition_keys,
                self.unique_violation_fingerprints,
            )
        ):
            raise ValueError("transition search stats must be nonnegative integers")


class TransitionSearchState:
    """In-memory parent admission with uniform caller-RNG selection.

    P0 mirrors legacy B3 full-state-or-violation admission. P1 replaces the
    final-state admission channel with transition-key novelty while retaining
    the same violation channel and uniform parent selection. Every trace status
    remains visible and incomplete traces are never converted to empty success.
    """

    def __init__(
        self, initial_cases: Sequence[ArchiveCase], policy: TransitionSearchPolicy
    ) -> None:
        if not isinstance(policy, TransitionSearchPolicy):
            raise ValueError("policy must be a supported TransitionSearchPolicy")
        cases = tuple(initial_cases)
        if not cases or not all(isinstance(case, ArchiveCase) for case in cases):
            raise ValueError("initial cases must be nonempty ArchiveCase records")
        if len({case.case_id for case in cases}) != len(cases):
            raise ValueError("initial cases contain duplicate case IDs")
        self._initial_cases = cases
        self._policy = policy
        self._final_novelty = NoveltyIndex()
        self._transition_novelty = TransitionNoveltyIndex()
        self._entries: list[TransitionCorpusEntry] = []
        self._retained_ids: set[str] = set()
        self._interesting_observations = 0

    @property
    def policy(self) -> TransitionSearchPolicy:
        return self._policy

    def consider(self, result: TransitionRunResult) -> TransitionSearchDecision:
        if not isinstance(result, TransitionRunResult):
            raise ValueError("transition search requires TransitionRunResult")
        index = self._final_novelty.observations
        if (
            index < len(self._initial_cases)
            and result.base_result.case != self._initial_cases[index]
        ):
            raise ValueError("seed observations must match declared cases/order")
        state_novel, new_violations, all_violations = self._final_novelty.observe(
            result.base_result
        )
        transition = self._transition_novelty.observe(result.trace)
        already_retained = result.base_result.case.case_id in self._retained_ids
        eligible = (
            state_novel or bool(new_violations)
            if self.policy == TransitionSearchPolicy.P0_FINAL_ONLY
            else transition.transition_novel or bool(new_violations)
        )
        decision = TransitionSearchDecision(
            result.base_result.case.case_id,
            state_novel,
            new_violations,
            transition.new_transition_keys,
            transition.transition_novel,
            already_retained,
            eligible,
            result.trace.completeness,
            result.trace.termination,
        )
        if decision.interesting:
            self._interesting_observations += 1
        if decision.retained:
            self._entries.append(
                TransitionCorpusEntry(
                    result.base_result.case,
                    result.base_result.signature,
                    transition.new_transition_keys,
                    all_violations,
                )
            )
            self._retained_ids.add(result.base_result.case.case_id)
        return decision

    def select_case(self, rng: random.Random) -> ArchiveCase:
        if self._final_novelty.observations < len(self._initial_cases):
            raise ValueError("parent selection requires a completed seed phase")
        if not self._entries:
            raise ValueError("cannot select a case from an empty transition corpus")
        return rng.choice(self._entries).case

    @property
    def entries(self) -> tuple[TransitionCorpusEntry, ...]:
        return tuple(self._entries)

    @property
    def stats(self) -> TransitionSearchStats:
        return TransitionSearchStats(
            self._final_novelty.observations,
            self._interesting_observations,
            len(self._entries),
            len(self._final_novelty.states),
            len(self._transition_novelty.keys),
            len(self._final_novelty.violations),
        )

"""P0-v2/P1-v2/P2-v2 corpus retention over qualified effect traces."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from inodefence.model import (
    ArchiveCase,
    EffectFeedbackKey,
    EffectRunResult,
    EffectStreamCompleteness,
    EffectTargetTermination,
    StateSignature,
)

from .effect_novelty import EffectNoveltyIndex
from .fingerprint import ViolationFingerprint, violation_fingerprints


class EffectSearchPolicy(StrEnum):
    P0_FINAL_STATE = "final-state-v3-or-violation-v1-effect-observation-v2-uniform-mutation-v1"
    P1_EFFECT_RETENTION = "effect-feedback-v2-or-violation-v1-uniform-mutation-v1"
    P2_EFFECT_ADAPTIVE = "effect-feedback-v2-or-violation-v1-adaptive-mutation-v1"
    # M3 (opt-in): P2 plus the boundary-approach *attempt* key channel. Same
    # admission rule as P2 (effect novelty OR new violation); the key set is a
    # superset, and only this arm relaxes the fail-closed gate to also admit a
    # cleanly recorded rejected trace's boundary-attempt keys. P0/P1/P2 and every
    # existing SUCCESS-only effect key are unchanged.
    P3_BOUNDARY_ATTEMPT_GRADIENT = (
        "effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1"
    )
    # M3 refinement: P3 plus the observed external-resolve rung (the full ladder —
    # lexical escape attempt + observed external resolution). Same admission rule and
    # the same opt-in relaxed gate; the key set is a further superset.
    P3_EXTERNAL_RESOLVE_GRADIENT = (
        "effect-feedback-v2-or-violation-v1-external-resolve-v1-adaptive-mutation-v1"
    )


@dataclass(frozen=True, slots=True)
class EffectSearchDecision:
    serialization_schema: ClassVar[int] = 2

    case_id: str
    full_state_novel: bool
    new_violation_fingerprints: tuple[ViolationFingerprint, ...]
    new_effect_keys: tuple[EffectFeedbackKey, ...]
    effect_novel: bool
    contract_violated: bool
    observation_failure: bool
    feedback_eligible: bool
    already_retained: bool
    admission_eligible: bool
    trace_completeness: EffectStreamCompleteness
    trace_termination: EffectTargetTermination

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("effect search decision requires a case ID")
        if not isinstance(self.new_violation_fingerprints, tuple) or not all(
            isinstance(item, ViolationFingerprint) for item in self.new_violation_fingerprints
        ):
            raise ValueError("effect decision requires violation fingerprints")
        if not isinstance(self.new_effect_keys, tuple) or not all(
            isinstance(item, EffectFeedbackKey) for item in self.new_effect_keys
        ):
            raise ValueError("effect decision requires feedback keys")
        if self.effect_novel != bool(self.new_effect_keys):
            raise ValueError("effect_novel must exactly reflect new effect keys")
        for value in (
            self.full_state_novel,
            self.effect_novel,
            self.contract_violated,
            self.observation_failure,
            self.feedback_eligible,
            self.already_retained,
            self.admission_eligible,
        ):
            if type(value) is not bool:
                raise ValueError("effect decision flags must be bool")
        if not self.feedback_eligible and (
            self.full_state_novel
            or self.new_violation_fingerprints
            or self.new_effect_keys
            or self.admission_eligible
        ):
            raise ValueError("ineligible effect observations must fail closed")
        if not isinstance(self.trace_completeness, EffectStreamCompleteness) or not isinstance(
            self.trace_termination, EffectTargetTermination
        ):
            raise ValueError("effect decision must preserve trace status")

    @property
    def interesting(self) -> bool:
        return self.feedback_eligible and (
            self.full_state_novel or self.effect_novel or bool(self.new_violation_fingerprints)
        )

    @property
    def retained(self) -> bool:
        return self.admission_eligible and not self.already_retained


@dataclass(frozen=True, slots=True)
class EffectCorpusEntry:
    case: ArchiveCase
    admission_signature: StateSignature
    admission_effect_keys: tuple[EffectFeedbackKey, ...]
    admission_violation_fingerprints: tuple[ViolationFingerprint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case, ArchiveCase) or not isinstance(
            self.admission_signature, StateSignature
        ):
            raise ValueError("effect corpus entry requires case and final signature")
        if not isinstance(self.admission_effect_keys, tuple) or not all(
            isinstance(item, EffectFeedbackKey) for item in self.admission_effect_keys
        ):
            raise ValueError("effect corpus entry requires feedback keys")
        if not isinstance(self.admission_violation_fingerprints, tuple) or not all(
            isinstance(item, ViolationFingerprint) for item in self.admission_violation_fingerprints
        ):
            raise ValueError("effect corpus entry requires violation fingerprints")


@dataclass(frozen=True, slots=True)
class EffectSearchStats:
    observations: int
    feedback_eligible_observations: int
    observation_failures: int
    interesting_observations: int
    retained_cases: int
    unique_full_states: int
    unique_effect_keys: int
    unique_violation_fingerprints: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (
                self.observations,
                self.feedback_eligible_observations,
                self.observation_failures,
                self.interesting_observations,
                self.retained_cases,
                self.unique_full_states,
                self.unique_effect_keys,
                self.unique_violation_fingerprints,
            )
        ):
            raise ValueError("effect search stats must be nonnegative integers")


class EffectSearchState:
    """Independent novelty channels with shared fail-closed observation eligibility."""

    def __init__(self, initial_cases: Sequence[ArchiveCase], policy: EffectSearchPolicy) -> None:
        if not isinstance(policy, EffectSearchPolicy):
            raise ValueError("policy must be a supported EffectSearchPolicy")
        cases = tuple(initial_cases)
        if not cases or not all(isinstance(case, ArchiveCase) for case in cases):
            raise ValueError("initial cases must be nonempty ArchiveCase records")
        if len({case.case_id for case in cases}) != len(cases):
            raise ValueError("initial cases contain duplicate case IDs")
        self._initial_cases = cases
        self._policy = policy
        self._effect_novelty = EffectNoveltyIndex(
            include_boundary_attempt=policy
            in (
                EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT,
                EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT,
            ),
            include_external_resolve=(policy == EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT),
        )
        self._states: set[StateSignature] = set()
        self._violations: set[ViolationFingerprint] = set()
        self._entries: list[EffectCorpusEntry] = []
        self._retained_ids: set[str] = set()
        self._observation_failures = 0
        self._interesting_observations = 0

    @property
    def policy(self) -> EffectSearchPolicy:
        return self._policy

    def consider(self, result: EffectRunResult) -> EffectSearchDecision:
        if not isinstance(result, EffectRunResult):
            raise ValueError("effect search requires EffectRunResult")
        index = self._effect_novelty.observations
        if (
            index < len(self._initial_cases)
            and result.base_result.case != self._initial_cases[index]
        ):
            raise ValueError("seed observations must match declared cases/order")

        novelty = self._effect_novelty.observe(result.trace)
        all_violations = violation_fingerprints(result.base_result.violations)
        observation_failure = bool(result.trace.observation_failures) or not (
            result.trace.integrity_valid
        )
        if novelty.feedback_eligible:
            state_novel = result.base_result.signature not in self._states
            new_violations = tuple(item for item in all_violations if item not in self._violations)
            self._states.add(result.base_result.signature)
            self._violations.update(all_violations)
        else:
            state_novel = False
            new_violations = ()
        already_retained = result.base_result.case.case_id in self._retained_ids
        if self.policy == EffectSearchPolicy.P0_FINAL_STATE:
            policy_novel = state_novel or bool(new_violations)
        else:
            policy_novel = novelty.effect_novel or bool(new_violations)
        admission_eligible = novelty.feedback_eligible and policy_novel
        decision = EffectSearchDecision(
            result.base_result.case.case_id,
            state_novel,
            new_violations,
            novelty.new_effect_keys,
            novelty.effect_novel,
            bool(all_violations),
            observation_failure,
            novelty.feedback_eligible,
            already_retained,
            admission_eligible,
            result.trace.completeness,
            result.trace.termination,
        )
        if observation_failure:
            self._observation_failures += 1
        if decision.interesting:
            self._interesting_observations += 1
        if decision.retained:
            self._entries.append(
                EffectCorpusEntry(
                    result.base_result.case,
                    result.base_result.signature,
                    novelty.new_effect_keys,
                    all_violations,
                )
            )
            self._retained_ids.add(result.base_result.case.case_id)
        return decision

    def select_case(self, rng: random.Random) -> ArchiveCase:
        if self._effect_novelty.observations < len(self._initial_cases):
            raise ValueError("parent selection requires a completed seed phase")
        if not self._entries:
            raise ValueError("cannot select a case from an empty effect corpus")
        return rng.choice(self._entries).case

    @property
    def entries(self) -> tuple[EffectCorpusEntry, ...]:
        return tuple(self._entries)

    @property
    def stats(self) -> EffectSearchStats:
        return EffectSearchStats(
            self._effect_novelty.observations,
            self._effect_novelty.eligible_observations,
            self._observation_failures,
            self._interesting_observations,
            len(self._entries),
            len(self._states),
            len(self._effect_novelty.keys),
            len(self._violations),
        )

"""P0-v2/P1-v2/P2-v2 corpus retention over qualified effect traces.

Also hosts the R/D/S-u equal-vocabulary arms (research-questions v2 H-A): same
diagnostic channel and uniform operator scheduling, differing only in admission.
"""

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

from .coverage import StructureCoverageFeature, structure_coverage_features
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
    # ---- R/D/S-u equal-vocabulary comparison (research-questions v2 H-A; EXP-0 v2.1) ----
    # The four IDs below share ONE diagnostic channel — the P3 boundary-attempt key
    # set under the P3 clean-trace gate (integrity-valid, complete, SUCCESS or
    # REJECTED) — so `new_effect_keys`, `unique_effect_keys` and the dense signals
    # (boundary-attempt key count, rejected ratio) are measured identically in every
    # arm. They differ ONLY in admission (which observation becomes a mutation
    # parent). All four use the uniform operator scheduler (every slot weight 1).
    #
    # R (random floor), walk variant: retention none. The first parent is drawn once
    # from the seeds; afterwards every observed child becomes the next parent
    # regardless of outcome (the `SearchPolicy.B0` "unretained walk" convention).
    # `r_variant = walk`.
    R_UNRETAINED_WALK = "unretained-walk-v1-uniform-mutation-v1"
    # R, seed-restart variant: retention none; EVERY parent is drawn uniformly from
    # the seed corpus, so each mutation is one step away from a seed. A different
    # random floor from the walk (no lineage depth); recorded as `r_variant =
    # seed-restart`. Not the EXP-0 default.
    R_UNRETAINED_SEED_RESTART = "unretained-seed-restart-v1-uniform-mutation-v1"
    # D (coverage control): admit a mutation when its post-state structure signature
    # exercises a target-agnostic structure-coverage feature (`coverage.py`) not yet
    # seen; seeds are the base corpus. Never reads identity groups, external effects
    # or any effect key — the same separation as `SearchPolicy.D` on the final-state
    # path, now on the effect-campaign path.
    D_STRUCTURE_COVERAGE = "structure-coverage-v1-uniform-mutation-v1"
    # S-u (InodeFence retention, main comparison): the P3_BOUNDARY_ATTEMPT_GRADIENT
    # admission rule (effect-feedback novelty OR new violation fingerprint OR new
    # boundary-attempt key) with the UNIFORM scheduler instead of the adaptive one,
    # so S-u vs D isolates the retention type and S-a (= P3_BOUNDARY_ATTEMPT_GRADIENT
    # itself, the optional ablation) minus S-u isolates the scheduler effect.
    S_U_STATE_RETENTION_UNIFORM = (
        "effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1"
    )


# The equal-vocabulary arms (uniform scheduler, shared diagnostic channel).
RDS_POLICIES = (
    EffectSearchPolicy.R_UNRETAINED_WALK,
    EffectSearchPolicy.R_UNRETAINED_SEED_RESTART,
    EffectSearchPolicy.D_STRUCTURE_COVERAGE,
    EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM,
)
_R_POLICIES = (
    EffectSearchPolicy.R_UNRETAINED_WALK,
    EffectSearchPolicy.R_UNRETAINED_SEED_RESTART,
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
                *RDS_POLICIES,
            ),
            include_external_resolve=(policy == EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT),
        )
        self._states: set[StateSignature] = set()
        self._violations: set[ViolationFingerprint] = set()
        self._entries: list[EffectCorpusEntry] = []
        self._retained_ids: set[str] = set()
        # D only: structure-coverage features seen so far (eligible observations).
        self._coverage: set[StructureCoverageFeature] = set()
        # R walk only: the working parent (last observed child), never a retained entry.
        self._active: ArchiveCase | None = None
        self._observation_failures = 0
        self._interesting_observations = 0

    @property
    def policy(self) -> EffectSearchPolicy:
        return self._policy

    def consider(self, result: EffectRunResult) -> EffectSearchDecision:
        if not isinstance(result, EffectRunResult):
            raise ValueError("effect search requires EffectRunResult")
        index = self._effect_novelty.observations
        is_seed = index < len(self._initial_cases)
        if is_seed and result.base_result.case != self._initial_cases[index]:
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
        elif self.policy in _R_POLICIES:
            policy_novel = False
        elif self.policy == EffectSearchPolicy.D_STRUCTURE_COVERAGE:
            features = structure_coverage_features(result.base_result.signature)
            # Seeds are the base corpus; a mutation is admitted only when it exercises
            # a structure feature not yet covered by an eligible observation.
            policy_novel = is_seed or not features <= self._coverage
            if novelty.feedback_eligible:
                self._coverage |= features
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
        if self.policy == EffectSearchPolicy.R_UNRETAINED_WALK and not is_seed:
            self._active = result.base_result.case
        return decision

    def select_case(self, rng: random.Random) -> ArchiveCase:
        """R walk: one seed draw then the last child; R seed-restart: a seed each time.

        Every retaining policy draws uniformly from its retained parents.
        """
        if self._effect_novelty.observations < len(self._initial_cases):
            raise ValueError("parent selection requires a completed seed phase")
        if self.policy == EffectSearchPolicy.R_UNRETAINED_WALK:
            if self._active is None:
                self._active = rng.choice(self._initial_cases)
            return self._active
        if self.policy == EffectSearchPolicy.R_UNRETAINED_SEED_RESTART:
            return rng.choice(self._initial_cases)
        if not self._entries:
            raise ValueError("cannot select a case from an empty effect corpus")
        return rng.choice(self._entries).case

    @property
    def active_case(self) -> ArchiveCase | None:
        """R-walk working parent, separate from retained-case accounting."""
        return self._active

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

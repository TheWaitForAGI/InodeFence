"""Fail-closed novelty index for normalized effect feedback v2."""

from dataclasses import dataclass

from inodefence.model import (
    EffectEventTrace,
    EffectFeedbackKey,
    EffectStreamCompleteness,
    EffectTargetTermination,
)

from .effect import (
    boundary_attempt_keys,
    effect_feedback_eligible,
    effect_feedback_keys,
    external_resolve_keys,
)


@dataclass(frozen=True, slots=True)
class EffectNoveltyDecision:
    new_effect_keys: tuple[EffectFeedbackKey, ...]
    effect_novel: bool
    feedback_eligible: bool

    def __post_init__(self) -> None:
        if not isinstance(self.new_effect_keys, tuple) or not all(
            isinstance(key, EffectFeedbackKey) for key in self.new_effect_keys
        ):
            raise ValueError("effect novelty requires EffectFeedbackKey records")
        if len(set(self.new_effect_keys)) != len(self.new_effect_keys):
            raise ValueError("new effect keys must be unique")
        if type(self.effect_novel) is not bool or self.effect_novel != bool(self.new_effect_keys):
            raise ValueError("effect_novel must exactly reflect new effect keys")
        if type(self.feedback_eligible) is not bool:
            raise ValueError("effect feedback eligibility must be bool")
        if not self.feedback_eligible and self.new_effect_keys:
            raise ValueError("ineligible observations cannot consume effect novelty")


class EffectNoveltyIndex:
    def __init__(
        self,
        *,
        include_boundary_attempt: bool = False,
        include_external_resolve: bool = False,
    ) -> None:
        # Opt-in M3 relaxation: when either flag is set, also derive the extra key(s)
        # and admit them from a cleanly recorded *rejected* trace (not only a
        # successful one). Off by default, so P0/P1/P2 keep the exact SUCCESS-only
        # fail-closed gate and their key sets are unchanged. These flags are the one
        # research-honesty judgment point of the boundary arms.
        #  - include_boundary_attempt: lexical escaping-link attempt keys.
        #  - include_external_resolve: the refinement rung — a link operation whose
        #    observed resolved path is EXTERNAL (region-based, outcome-independent).
        self._include_boundary_attempt = bool(include_boundary_attempt)
        self._include_external_resolve = bool(include_external_resolve)
        self._keys: set[EffectFeedbackKey] = set()
        self._observations = 0
        self._eligible_observations = 0
        self._novel_observations = 0

    @property
    def keys(self) -> frozenset[EffectFeedbackKey]:
        return frozenset(self._keys)

    @property
    def observations(self) -> int:
        return self._observations

    @property
    def eligible_observations(self) -> int:
        return self._eligible_observations

    @property
    def novel_observations(self) -> int:
        return self._novel_observations

    def observe(self, trace: EffectEventTrace) -> EffectNoveltyDecision:
        if not isinstance(trace, EffectEventTrace):
            raise ValueError("effect novelty requires an EffectEventTrace")
        self._observations += 1
        success_eligible = effect_feedback_eligible(trace)
        # The boundary rungs may also come from a clean, valid, complete trace that
        # the target *rejected* (a refused escaping link is still cleanly recorded).
        # Everything else about the gate is unchanged: an invalid, incomplete, failed
        # or timed-out stream never contributes.
        relaxed_eligible = (self._include_boundary_attempt or self._include_external_resolve) and (
            trace.integrity_valid
            and trace.completeness == EffectStreamCompleteness.COMPLETE
            and trace.termination
            in (EffectTargetTermination.SUCCESS, EffectTargetTermination.REJECTED)
        )
        if not success_eligible and not relaxed_eligible:
            return EffectNoveltyDecision((), False, False)
        self._eligible_observations += 1
        keys: tuple[EffectFeedbackKey, ...] = (
            effect_feedback_keys(trace) if success_eligible else ()
        )
        if relaxed_eligible:
            if self._include_boundary_attempt:
                keys = tuple(dict.fromkeys(keys + boundary_attempt_keys(trace)))
            if self._include_external_resolve:
                keys = tuple(dict.fromkeys(keys + external_resolve_keys(trace)))
        new = tuple(key for key in keys if key not in self._keys)
        self._keys.update(keys)
        if new:
            self._novel_observations += 1
        return EffectNoveltyDecision(new, bool(new), True)

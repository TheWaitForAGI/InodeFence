"""Fail-closed novelty index for normalized effect feedback v2."""

from dataclasses import dataclass

from inodefence.model import EffectEventTrace, EffectFeedbackKey

from .effect import (
    effect_feedback_eligible,
    effect_feedback_keys,
    observed_boundary_escape_keys,
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
    def __init__(self, *, include_boundary_escape: bool = False) -> None:
        # include_boundary_escape adds the M3 observed boundary-approach keys to the
        # same eligibility-gated channel. Off by default so P0/P1/P2 are unchanged.
        self._include_boundary_escape = bool(include_boundary_escape)
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
        eligible = effect_feedback_eligible(trace)
        if not eligible:
            return EffectNoveltyDecision((), False, False)
        self._eligible_observations += 1
        keys: tuple[EffectFeedbackKey, ...] = effect_feedback_keys(trace)
        if self._include_boundary_escape:
            keys = tuple(dict.fromkeys(keys + observed_boundary_escape_keys(trace)))
        new = tuple(key for key in keys if key not in self._keys)
        self._keys.update(keys)
        if new:
            self._novel_observations += 1
        return EffectNoveltyDecision(new, bool(new), True)

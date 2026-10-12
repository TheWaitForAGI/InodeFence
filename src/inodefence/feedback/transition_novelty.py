"""Independent novelty index for normalized entry-transition keys."""

from dataclasses import dataclass

from inodefence.model import TransitionFeedbackKey, TransitionTrace

from .transition import transition_keys


@dataclass(frozen=True, slots=True)
class TransitionNoveltyDecision:
    new_transition_keys: tuple[TransitionFeedbackKey, ...]
    transition_novel: bool

    def __post_init__(self) -> None:
        if not isinstance(self.new_transition_keys, tuple) or not all(
            isinstance(key, TransitionFeedbackKey) for key in self.new_transition_keys
        ):
            raise ValueError("new transition keys must be TransitionFeedbackKey records")
        if len(set(self.new_transition_keys)) != len(self.new_transition_keys):
            raise ValueError("new transition keys must be unique")
        if type(self.transition_novel) is not bool or self.transition_novel != bool(
            self.new_transition_keys
        ):
            raise ValueError("transition_novel must exactly reflect new keys")


class TransitionNoveltyIndex:
    """Seen-key channel independent of final state and violation novelty."""

    def __init__(self) -> None:
        self._keys: set[TransitionFeedbackKey] = set()
        self._observations = 0
        self._novel_observations = 0

    @property
    def keys(self) -> frozenset[TransitionFeedbackKey]:
        return frozenset(self._keys)

    @property
    def observations(self) -> int:
        return self._observations

    @property
    def novel_observations(self) -> int:
        return self._novel_observations

    def observe(self, trace: TransitionTrace) -> TransitionNoveltyDecision:
        if not isinstance(trace, TransitionTrace):
            raise ValueError("transition novelty requires a TransitionTrace")
        new = []
        keys = transition_keys(trace)
        for key in keys:
            if key not in self._keys and key not in new:
                new.append(key)
        self._keys.update(keys)
        self._observations += 1
        if new:
            self._novel_observations += 1
        return TransitionNoveltyDecision(tuple(new), bool(new))

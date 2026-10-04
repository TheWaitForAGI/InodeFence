"""Shared full-evidence novelty indexes, independent of parent admission."""

from inodefence.model import RunResult, StateSignature

from .fingerprint import ViolationFingerprint, violation_fingerprints


class NoveltyIndex:
    def __init__(self) -> None:
        self.states: set[StateSignature] = set()
        self.violations: set[ViolationFingerprint] = set()
        self.observations = 0
        self.interesting_observations = 0

    def observe(
        self, result: RunResult
    ) -> tuple[bool, tuple[ViolationFingerprint, ...], tuple[ViolationFingerprint, ...]]:
        fingerprints = violation_fingerprints(result.violations)
        state_novel = result.signature not in self.states
        new = tuple(item for item in fingerprints if item not in self.violations)
        self.states.add(result.signature)
        self.violations.update(fingerprints)
        self.observations += 1
        if state_novel or new:
            self.interesting_observations += 1
        return state_novel, new, fingerprints

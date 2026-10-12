"""Reproducible mutation operator selection, separate from mutation functions."""

import random
from dataclasses import dataclass
from typing import ClassVar, Protocol

from inodefence.feedback import ViolationFingerprint
from inodefence.model import TransitionFeedbackKey
from inodefence.mutator import MutationAttempt, MutationOperatorId

WeightSnapshot = tuple[tuple[MutationOperatorId, int], ...]


def _validate_weights(weights: WeightSnapshot) -> None:
    if (
        not isinstance(weights, tuple)
        or not weights
        or tuple(operator for operator, _ in weights) != tuple(MutationOperatorId)
        or any(type(weight) is not int or weight <= 0 for _, weight in weights)
    ):
        raise ValueError("weights must cover every operator in stable order")


@dataclass(frozen=True, slots=True)
class MutationSelection:
    operator_id: MutationOperatorId
    weights_before: WeightSnapshot
    selected_weight: int

    def __post_init__(self) -> None:
        if not isinstance(self.operator_id, MutationOperatorId):
            raise ValueError("selection requires a MutationOperatorId")
        _validate_weights(self.weights_before)
        weights = dict(self.weights_before)
        if (
            type(self.selected_weight) is not int
            or self.selected_weight != weights[self.operator_id]
        ):
            raise ValueError("selected weight must match the selected operator")


@dataclass(frozen=True, slots=True)
class MutationSchedulerEvidence:
    serialization_schema: ClassVar[int] = 1

    selected_operator_id: MutationOperatorId
    weights_before: WeightSnapshot
    selected_weight: int
    new_transition_keys: tuple[TransitionFeedbackKey, ...]
    new_violation_fingerprints: tuple[ViolationFingerprint, ...]
    reward: int
    weights_after: WeightSnapshot
    parent_case_id: str
    child_case_id: str

    def __post_init__(self) -> None:
        MutationSelection(self.selected_operator_id, self.weights_before, self.selected_weight)
        _validate_weights(self.weights_after)
        if not isinstance(self.new_transition_keys, tuple) or not all(
            isinstance(item, TransitionFeedbackKey) for item in self.new_transition_keys
        ):
            raise ValueError("scheduler evidence requires transition feedback keys")
        if not isinstance(self.new_violation_fingerprints, tuple) or not all(
            isinstance(item, ViolationFingerprint) for item in self.new_violation_fingerprints
        ):
            raise ValueError("scheduler evidence requires violation fingerprints")
        if type(self.reward) is not int or self.reward not in (0, 1):
            raise ValueError("scheduler reward must be integer zero or one")
        if not all(
            isinstance(value, str) and value for value in (self.parent_case_id, self.child_case_id)
        ):
            raise ValueError("scheduler evidence requires parent and child case IDs")


class MutationScheduler(Protocol):
    def choose_operator(
        self, operators: tuple[MutationOperatorId, ...], rng: random.Random
    ) -> MutationSelection: ...

    def observe_outcome(
        self,
        selection: MutationSelection,
        attempt: MutationAttempt,
        new_transition_keys: tuple[TransitionFeedbackKey, ...],
        new_violation_fingerprints: tuple[ViolationFingerprint, ...],
    ) -> MutationSchedulerEvidence: ...


class UniformMutationScheduler:
    """Stateless legacy uniform choice; outcomes never change weights."""

    @property
    def weights(self) -> WeightSnapshot:
        return tuple((operator, 1) for operator in MutationOperatorId)

    def choose_operator(
        self, operators: tuple[MutationOperatorId, ...], rng: random.Random
    ) -> MutationSelection:
        if operators != tuple(MutationOperatorId):
            raise ValueError("uniform scheduler requires the stable complete operator table")
        selected = rng.choice(operators)
        return MutationSelection(selected, self.weights, 1)

    def observe_outcome(
        self,
        selection: MutationSelection,
        attempt: MutationAttempt,
        new_transition_keys: tuple[TransitionFeedbackKey, ...],
        new_violation_fingerprints: tuple[ViolationFingerprint, ...],
    ) -> MutationSchedulerEvidence:
        _validate_outcome(selection, attempt)
        return MutationSchedulerEvidence(
            selection.operator_id,
            selection.weights_before,
            selection.selected_weight,
            new_transition_keys,
            new_violation_fingerprints,
            0,
            self.weights,
            attempt.parent_case_id,
            attempt.child_case.case_id,
        )


class TransitionAdaptiveScheduler:
    """Bounded integer reward for operators yielding any new transition key."""

    def __init__(self, *, maximum_weight: int = 8) -> None:
        if type(maximum_weight) is not int or maximum_weight < 1:
            raise ValueError("maximum_weight must be a positive integer")
        self._maximum_weight = maximum_weight
        self._weights = {operator: 1 for operator in MutationOperatorId}

    @property
    def maximum_weight(self) -> int:
        return self._maximum_weight

    @property
    def weights(self) -> WeightSnapshot:
        return tuple((operator, self._weights[operator]) for operator in MutationOperatorId)

    def choose_operator(
        self, operators: tuple[MutationOperatorId, ...], rng: random.Random
    ) -> MutationSelection:
        if operators != tuple(MutationOperatorId):
            raise ValueError("adaptive scheduler requires the stable complete operator table")
        before = self.weights
        total = sum(weight for _, weight in before)
        draw = rng.randrange(total)
        cumulative = 0
        for operator, weight in before:
            cumulative += weight
            if draw < cumulative:
                return MutationSelection(operator, before, weight)
        raise AssertionError("bounded integer selection failed")

    def observe_outcome(
        self,
        selection: MutationSelection,
        attempt: MutationAttempt,
        new_transition_keys: tuple[TransitionFeedbackKey, ...],
        new_violation_fingerprints: tuple[ViolationFingerprint, ...],
    ) -> MutationSchedulerEvidence:
        _validate_outcome(selection, attempt)
        if self.weights != selection.weights_before:
            raise ValueError("scheduler weights changed between selection and outcome")
        reward = int(bool(new_transition_keys))
        if reward:
            current = self._weights[selection.operator_id]
            self._weights[selection.operator_id] = min(current + 1, self.maximum_weight)
        return MutationSchedulerEvidence(
            selection.operator_id,
            selection.weights_before,
            selection.selected_weight,
            new_transition_keys,
            new_violation_fingerprints,
            reward,
            self.weights,
            attempt.parent_case_id,
            attempt.child_case.case_id,
        )


def _validate_outcome(selection: MutationSelection, attempt: MutationAttempt) -> None:
    if not isinstance(selection, MutationSelection) or not isinstance(attempt, MutationAttempt):
        raise ValueError("scheduler outcome requires selection and mutation attempt")
    if selection.operator_id != attempt.operator_id:
        raise ValueError("scheduler selection differs from applied operator")

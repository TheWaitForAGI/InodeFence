"""V2 scheduler evidence; v1 transition scheduler schemas remain unchanged."""

import random
from dataclasses import dataclass
from typing import ClassVar, Protocol

from inodefence.feedback import ViolationFingerprint
from inodefence.feedback.pre_violation import PreViolationSignal
from inodefence.model import EffectFeedbackKey
from inodefence.mutation_scheduler import MutationSelection, WeightSnapshot, operator_table
from inodefence.mutator import (
    OPERATOR_ORDER_V1,
    OPERATOR_TABLES,
    MutationAttempt,
    MutationOperatorId,
)


def _validate_weights(weights: WeightSnapshot) -> None:
    if (
        not isinstance(weights, tuple)
        or not weights
        or tuple(operator for operator, _ in weights) not in OPERATOR_TABLES
        or any(type(weight) is not int or weight <= 0 for _, weight in weights)
    ):
        raise ValueError("weights must cover every operator in stable order")


@dataclass(frozen=True, slots=True)
class EffectMutationSchedulerEvidence:
    serialization_schema: ClassVar[int] = 2

    selected_operator_id: MutationOperatorId
    weights_before: WeightSnapshot
    selected_weight: int
    new_effect_keys: tuple[EffectFeedbackKey, ...]
    new_violation_fingerprints: tuple[ViolationFingerprint, ...]
    reward: int
    weights_after: WeightSnapshot
    parent_case_id: str
    child_case_id: str

    def __post_init__(self) -> None:
        MutationSelection(self.selected_operator_id, self.weights_before, self.selected_weight)
        _validate_weights(self.weights_after)
        if not isinstance(self.new_effect_keys, tuple) or not all(
            isinstance(item, EffectFeedbackKey) for item in self.new_effect_keys
        ):
            raise ValueError("scheduler evidence requires effect feedback keys")
        if not isinstance(self.new_violation_fingerprints, tuple) or not all(
            isinstance(item, ViolationFingerprint) for item in self.new_violation_fingerprints
        ):
            raise ValueError("scheduler evidence requires violation fingerprints")
        if type(self.reward) is not int or self.reward not in (0, 1):
            raise ValueError("effect scheduler reward must be integer zero or one")
        if not all(
            isinstance(value, str) and value for value in (self.parent_case_id, self.child_case_id)
        ):
            raise ValueError("scheduler evidence requires parent and child case IDs")


class EffectMutationScheduler(Protocol):
    def choose_operator(
        self, operators: tuple[MutationOperatorId, ...], rng: random.Random
    ) -> MutationSelection: ...

    def observe_outcome(
        self,
        selection: MutationSelection,
        attempt: MutationAttempt,
        new_effect_keys: tuple[EffectFeedbackKey, ...],
        new_violation_fingerprints: tuple[ViolationFingerprint, ...],
    ) -> EffectMutationSchedulerEvidence: ...


class EffectUniformMutationScheduler:
    """Uniform choice over ``operators`` (default: the eight-slot V1 table every
    existing policy uses); outcomes never change weights and the reward is 0."""

    def __init__(self, operators: tuple[MutationOperatorId, ...] = OPERATOR_ORDER_V1) -> None:
        self._operators = operator_table(operators)

    @property
    def weights(self) -> WeightSnapshot:
        return tuple((operator, 1) for operator in self._operators)

    def choose_operator(
        self, operators: tuple[MutationOperatorId, ...], rng: random.Random
    ) -> MutationSelection:
        if operators != self._operators:
            raise ValueError("uniform scheduler requires the stable complete operator table")
        selected = rng.choice(operators)
        return MutationSelection(selected, self.weights, 1)

    def observe_outcome(
        self,
        selection: MutationSelection,
        attempt: MutationAttempt,
        new_effect_keys: tuple[EffectFeedbackKey, ...],
        new_violation_fingerprints: tuple[ViolationFingerprint, ...],
    ) -> EffectMutationSchedulerEvidence:
        _validate_outcome(selection, attempt)
        return EffectMutationSchedulerEvidence(
            selection.operator_id,
            selection.weights_before,
            selection.selected_weight,
            new_effect_keys,
            new_violation_fingerprints,
            0,
            self.weights,
            attempt.parent_case_id,
            attempt.child_case.case_id,
        )


class EffectAdaptiveMutationScheduler:
    """Bounded 1..8 mechanism; binary reward on new effect key OR new violation.

    The reward channel matches corpus admission (`effect_novel or new_violations`):
    a new boundary-violation fingerprint is the strongest security-state signal,
    so the operator that produced it gains weight too, not only effect novelty.
    Benign runs (no violations) are unaffected, so a 0-violation campaign keeps the
    exact same operator-weight trajectory as before. ``operators`` is the table it
    draws from and records weights over (default: the eight-slot V1 table).
    """

    def __init__(
        self,
        *,
        maximum_weight: int = 8,
        operators: tuple[MutationOperatorId, ...] = OPERATOR_ORDER_V1,
    ) -> None:
        if type(maximum_weight) is not int or maximum_weight < 1:
            raise ValueError("maximum_weight must be a positive integer")
        self._maximum_weight = maximum_weight
        self._operators = operator_table(operators)
        self._weights = {operator: 1 for operator in self._operators}

    @property
    def maximum_weight(self) -> int:
        return self._maximum_weight

    @property
    def weights(self) -> WeightSnapshot:
        return tuple((operator, self._weights[operator]) for operator in self._operators)

    def choose_operator(
        self, operators: tuple[MutationOperatorId, ...], rng: random.Random
    ) -> MutationSelection:
        if operators != self._operators:
            raise ValueError("adaptive scheduler requires the stable complete operator table")
        before = self.weights
        draw = rng.randrange(sum(weight for _, weight in before))
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
        new_effect_keys: tuple[EffectFeedbackKey, ...],
        new_violation_fingerprints: tuple[ViolationFingerprint, ...],
    ) -> EffectMutationSchedulerEvidence:
        _validate_outcome(selection, attempt)
        if self.weights != selection.weights_before:
            raise ValueError("scheduler weights changed between selection and outcome")
        reward = int(bool(new_effect_keys) or bool(new_violation_fingerprints))
        if reward:
            current = self._weights[selection.operator_id]
            self._weights[selection.operator_id] = min(current + 1, self.maximum_weight)
        return EffectMutationSchedulerEvidence(
            selection.operator_id,
            selection.weights_before,
            selection.selected_weight,
            new_effect_keys,
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


#: Fixed-point unit of :class:`PreViolationNoveltyScheduler` weights: weight 1 is 60, so a reward
#: split evenly over k applied operators is exact for every k up to 6 (the largest chain).
WEIGHT_UNIT = 60


@dataclass(frozen=True, slots=True)
class PreViolationSchedulerEvidence(EffectMutationSchedulerEvidence):
    """Scheduler evidence of an exploration policy (#511): the base fields plus the signal channel.

    ``reward`` is 1 exactly when ``new_signals`` is nonempty. ``new_effect_keys`` and
    ``new_violation_fingerprints`` are the recorded diagnostic channel only and never reward.
    ``credited_operators`` received ``weight_unit // len(credited_operators)`` each (an operator
    applied twice is listed twice). Weights are in units of ``weight_unit``.
    """

    new_signals: tuple[PreViolationSignal, ...] = ()
    credited_operators: tuple[MutationOperatorId, ...] = ()
    signal_retained: bool = False
    weight_unit: int = WEIGHT_UNIT

    def __post_init__(self) -> None:
        EffectMutationSchedulerEvidence.__post_init__(self)
        if not isinstance(self.new_signals, tuple) or not all(
            isinstance(item, PreViolationSignal) for item in self.new_signals
        ):
            raise ValueError("exploration evidence requires pre-violation signals")
        if self.reward != int(bool(self.new_signals)):
            raise ValueError("exploration reward must be 1 exactly on a new signal")
        if self.credited_operators and not self.reward:
            raise ValueError("operators are credited only on a reward")
        if type(self.signal_retained) is not bool or self.weight_unit != WEIGHT_UNIT:
            raise ValueError("exploration evidence requires signal_retained and the weight unit")


class PreViolationNoveltyScheduler:
    """Binary reward on a new pre-violation signal; credit split over the applied operators.

    W4 2026-11-18 (rulings 4 and 5): the reward is 1 when the execution showed a pre-violation
    signal not seen before in the campaign, else 0; violations and effect keys never reward. The
    reward is split evenly over the operators **applied** in that execution (a no-op attempt gets
    nothing; with none applied nobody is credited). Weights start at one unit each, grow by the
    share, and are capped at ``maximum_weight`` units; there is no decay. Selection draws in
    proportion to the integer weights, as the adaptive scheduler does.
    """

    def __init__(
        self,
        *,
        maximum_weight: int = 8,
        operators: tuple[MutationOperatorId, ...] = OPERATOR_ORDER_V1,
    ) -> None:
        if type(maximum_weight) is not int or maximum_weight < 1:
            raise ValueError("maximum_weight must be a positive integer")
        self._cap = maximum_weight * WEIGHT_UNIT
        self._operators = operator_table(operators)
        self._weights = {operator: WEIGHT_UNIT for operator in self._operators}

    @property
    def weights(self) -> WeightSnapshot:
        return tuple((operator, self._weights[operator]) for operator in self._operators)

    def choose_operator(
        self, operators: tuple[MutationOperatorId, ...], rng: random.Random
    ) -> MutationSelection:
        if operators != self._operators:
            raise ValueError("exploration scheduler requires the stable complete operator table")
        before = self.weights
        draw = rng.randrange(sum(weight for _, weight in before))
        cumulative = 0
        for operator, weight in before:
            cumulative += weight
            if draw < cumulative:
                return MutationSelection(operator, before, weight)
        raise AssertionError("bounded integer selection failed")

    def observe_signals(
        self,
        selection: MutationSelection,
        attempt: MutationAttempt,
        applied_operators: tuple[MutationOperatorId, ...],
        new_signals: tuple[PreViolationSignal, ...],
        signal_retained: bool,
        new_effect_keys: tuple[EffectFeedbackKey, ...] = (),
        new_violation_fingerprints: tuple[ViolationFingerprint, ...] = (),
    ) -> PreViolationSchedulerEvidence:
        _validate_outcome(selection, attempt)
        if self.weights != selection.weights_before:
            raise ValueError("scheduler weights changed between selection and outcome")
        if any(operator not in self._weights for operator in applied_operators):
            raise ValueError("applied operators must come from the scheduler's table")
        reward = int(bool(new_signals))
        credited: tuple[MutationOperatorId, ...] = ()
        if reward and applied_operators:
            if WEIGHT_UNIT % len(applied_operators):
                raise ValueError("an even split needs at most 6 applied operators")
            share = WEIGHT_UNIT // len(applied_operators)
            for operator in applied_operators:
                self._weights[operator] = min(self._weights[operator] + share, self._cap)
            credited = applied_operators
        return PreViolationSchedulerEvidence(
            selection.operator_id,
            selection.weights_before,
            selection.selected_weight,
            new_effect_keys,
            new_violation_fingerprints,
            reward,
            self.weights,
            attempt.parent_case_id,
            attempt.child_case.case_id,
            new_signals,
            credited,
            signal_retained,
        )

    def observe_outcome(
        self,
        selection: MutationSelection,
        attempt: MutationAttempt,
        new_effect_keys: tuple[EffectFeedbackKey, ...],
        new_violation_fingerprints: tuple[ViolationFingerprint, ...],
    ) -> PreViolationSchedulerEvidence:
        """An execution with no observation (a build-invalid child): no signal, no reward."""
        return self.observe_signals(
            selection, attempt, (), (), False, new_effect_keys, new_violation_fingerprints
        )


def applied_operators(attempt: MutationAttempt) -> tuple[MutationOperatorId, ...]:
    """The operators applied in one execution: chain links with ``applied``, else the one."""
    links = getattr(attempt, "links", None)
    if links:
        return tuple(link.operator_id for link in links if link.applied)
    return (attempt.operator_id,) if attempt.applied else ()

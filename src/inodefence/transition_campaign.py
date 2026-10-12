"""In-memory transition-policy composition over a caller-owned result producer."""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar

from inodefence.campaign import CampaignOrigin
from inodefence.feedback import (
    TransitionSearchDecision,
    TransitionSearchPolicy,
    TransitionSearchState,
    TransitionSearchStats,
)
from inodefence.model import ArchiveCase, TransitionRunResult
from inodefence.mutation_scheduler import (
    MutationSchedulerEvidence,
    MutationSelection,
    TransitionAdaptiveScheduler,
    UniformMutationScheduler,
)
from inodefence.mutator import (
    MutationAttempt,
    MutationPolicy,
    apply_operator,
    operator_ids,
)


@dataclass(frozen=True, slots=True)
class TransitionCampaignConfig:
    random_seed: int
    execution_budget: int
    search_policy: TransitionSearchPolicy
    mutation_policy: MutationPolicy = MutationPolicy.LEGACY

    def __post_init__(self) -> None:
        if type(self.random_seed) is not int:
            raise ValueError("random_seed must be an integer")
        if type(self.execution_budget) is not int or self.execution_budget <= 0:
            raise ValueError("execution_budget must be a positive integer")
        if not isinstance(self.search_policy, TransitionSearchPolicy):
            raise ValueError("search_policy must be a supported TransitionSearchPolicy")
        if not isinstance(self.mutation_policy, MutationPolicy):
            raise ValueError("mutation_policy must be a supported MutationPolicy")


@dataclass(frozen=True, slots=True)
class TransitionCampaignStep:
    serialization_schema: ClassVar[int] = 2

    index: int
    origin: CampaignOrigin
    parent_case_id: str | None
    result: TransitionRunResult
    feedback: TransitionSearchDecision
    mutation_attempt: MutationAttempt | None
    scheduler_evidence: MutationSchedulerEvidence | None

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("transition campaign step index must be nonnegative")
        if not isinstance(self.origin, CampaignOrigin) or not isinstance(
            self.result, TransitionRunResult
        ):
            raise ValueError("transition campaign step requires typed origin and result")
        if not isinstance(self.feedback, TransitionSearchDecision):
            raise ValueError("transition campaign step requires typed feedback")
        if self.parent_case_id is not None and (
            not isinstance(self.parent_case_id, str) or not self.parent_case_id
        ):
            raise ValueError("transition campaign parent ID must be nonempty or None")
        if (self.origin == CampaignOrigin.SEED) != (self.parent_case_id is None):
            raise ValueError("only mutation steps require a parent case ID")
        if self.feedback.case_id != self.result.base_result.case.case_id:
            raise ValueError("transition feedback differs from step result")
        if (self.origin == CampaignOrigin.SEED) != (self.mutation_attempt is None):
            raise ValueError("only mutation steps require a mutation attempt")
        if (self.origin == CampaignOrigin.SEED) != (self.scheduler_evidence is None):
            raise ValueError("only mutation steps require scheduler evidence")
        if self.mutation_attempt is not None and (
            self.mutation_attempt.child_case != self.result.base_result.case
            or self.mutation_attempt.parent_case_id != self.parent_case_id
        ):
            raise ValueError("mutation attempt differs from step lineage/result")
        if self.scheduler_evidence is not None and (
            self.scheduler_evidence.parent_case_id != self.parent_case_id
            or self.scheduler_evidence.child_case_id != self.result.base_result.case.case_id
        ):
            raise ValueError("scheduler evidence differs from step lineage/result")


@dataclass(frozen=True, slots=True)
class TransitionCampaignResult:
    serialization_schema: ClassVar[int] = 2

    config: TransitionCampaignConfig
    initial_case_ids: tuple[str, ...]
    steps: tuple[TransitionCampaignStep, ...]
    final_search_stats: TransitionSearchStats
    retained_case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.config, TransitionCampaignConfig):
            raise ValueError("transition campaign result requires typed config")
        if (
            not isinstance(self.initial_case_ids, tuple)
            or not self.initial_case_ids
            or len(set(self.initial_case_ids)) != len(self.initial_case_ids)
        ):
            raise ValueError("transition campaign result requires unique initial IDs")
        if not isinstance(self.steps, tuple) or not all(
            isinstance(step, TransitionCampaignStep) for step in self.steps
        ):
            raise ValueError("transition campaign result requires typed steps")
        if len(self.steps) != self.config.execution_budget or len(self.initial_case_ids) > len(
            self.steps
        ):
            raise ValueError("transition campaign steps must fill the execution budget")
        if tuple(step.index for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("transition campaign step indexes must be contiguous")
        if not isinstance(self.final_search_stats, TransitionSearchStats):
            raise ValueError("transition campaign result requires final search stats")
        if not isinstance(self.retained_case_ids, tuple) or not all(
            isinstance(case_id, str) and case_id for case_id in self.retained_case_ids
        ):
            raise ValueError("transition campaign result requires retained case IDs")


TransitionResultProducer = Callable[[ArchiveCase], TransitionRunResult]


def run_transition_campaign(
    initial_cases: Sequence[ArchiveCase],
    produce_result: TransitionResultProducer,
    config: TransitionCampaignConfig,
) -> TransitionCampaignResult:
    """Compose policy and uniform mutation over already authorized observations.

    The result producer is caller-owned because no native target adapter is
    currently qualified. This core API does not weaken campaign isolation gates
    or claim a configured/formal experiment runner.
    """
    if not callable(produce_result) or not isinstance(config, TransitionCampaignConfig):
        raise ValueError("transition campaign requires a producer and typed config")
    cases = tuple(initial_cases)
    if not cases or not all(isinstance(case, ArchiveCase) for case in cases):
        raise ValueError("initial cases must be nonempty ArchiveCase records")
    if config.execution_budget < len(cases):
        raise ValueError("execution_budget must cover all initial cases")
    initial_ids = tuple(case.case_id for case in cases)
    if len(set(initial_ids)) != len(initial_ids):
        raise ValueError("initial cases contain duplicate case IDs")

    state = TransitionSearchState(cases, config.search_policy)
    steps: list[TransitionCampaignStep] = []

    scheduler = (
        TransitionAdaptiveScheduler()
        if config.search_policy == TransitionSearchPolicy.P2_TRANSITION_ADAPTIVE
        else UniformMutationScheduler()
    )

    def observe(
        case: ArchiveCase,
        origin: CampaignOrigin,
        parent: str | None,
        attempt: MutationAttempt | None = None,
        selection: MutationSelection | None = None,
    ) -> None:
        result = produce_result(case)
        if not isinstance(result, TransitionRunResult) or result.base_result.case != case:
            raise ValueError("producer must return TransitionRunResult for the requested case")
        decision = state.consider(result)
        if (attempt is None) != (selection is None):
            raise ValueError("mutation attempt and scheduler selection must appear together")
        scheduler_evidence = None
        if attempt is not None and selection is not None:
            scheduler_evidence = scheduler.observe_outcome(
                selection,
                attempt,
                decision.new_transition_keys,
                decision.new_violation_fingerprints,
            )
        steps.append(
            TransitionCampaignStep(
                len(steps),
                origin,
                parent,
                result,
                decision,
                attempt,
                scheduler_evidence,
            )
        )

    for case in cases:
        observe(case, CampaignOrigin.SEED, None)

    rng = random.Random(config.random_seed)
    while len(steps) < config.execution_budget:
        parent = state.select_case(rng)
        selection = scheduler.choose_operator(operator_ids(config.mutation_policy), rng)
        attempt = apply_operator(parent, rng, config.mutation_policy, selection.operator_id)
        observe(
            attempt.child_case,
            CampaignOrigin.MUTATION,
            parent.case_id,
            attempt,
            selection,
        )

    return TransitionCampaignResult(
        config,
        initial_ids,
        tuple(steps),
        state.stats,
        tuple(entry.case.case_id for entry in state.entries),
    )

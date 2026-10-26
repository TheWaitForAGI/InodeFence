"""Synthetic v2 closed loop over a caller-owned EffectRunResult producer."""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar

from inodefence.campaign import CampaignOrigin
from inodefence.effect_scheduler import (
    EffectAdaptiveMutationScheduler,
    EffectMutationSchedulerEvidence,
    EffectUniformMutationScheduler,
)
from inodefence.feedback import (
    EffectSearchDecision,
    EffectSearchPolicy,
    EffectSearchState,
    EffectSearchStats,
)
from inodefence.model import ArchiveCase, EffectRunResult
from inodefence.model.filesystem import Region, path_region
from inodefence.mutation_scheduler import MutationSelection
from inodefence.mutator import MutationAttempt, MutationPolicy, apply_operator, operator_ids


@dataclass(frozen=True, slots=True)
class EffectCampaignConfig:
    random_seed: int
    execution_budget: int
    search_policy: EffectSearchPolicy
    mutation_policy: MutationPolicy = MutationPolicy.LEGACY

    def __post_init__(self) -> None:
        if type(self.random_seed) is not int:
            raise ValueError("random_seed must be an integer")
        if type(self.execution_budget) is not int or self.execution_budget <= 0:
            raise ValueError("execution_budget must be a positive integer")
        if not isinstance(self.search_policy, EffectSearchPolicy):
            raise ValueError("search_policy must be a supported EffectSearchPolicy")
        if not isinstance(self.mutation_policy, MutationPolicy):
            raise ValueError("mutation_policy must be a supported MutationPolicy")


@dataclass(frozen=True, slots=True)
class EffectCampaignStep:
    serialization_schema: ClassVar[int] = 2

    index: int
    origin: CampaignOrigin
    parent_case_id: str | None
    result: EffectRunResult
    feedback: EffectSearchDecision
    mutation_attempt: MutationAttempt | None
    scheduler_evidence: EffectMutationSchedulerEvidence | None

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("effect campaign step index must be nonnegative")
        if not isinstance(self.origin, CampaignOrigin) or not isinstance(
            self.result, EffectRunResult
        ):
            raise ValueError("effect campaign step requires typed origin and result")
        if not isinstance(self.feedback, EffectSearchDecision):
            raise ValueError("effect campaign step requires typed feedback")
        if self.parent_case_id is not None and (
            not isinstance(self.parent_case_id, str) or not self.parent_case_id
        ):
            raise ValueError("effect campaign parent ID must be nonempty or None")
        if (self.origin == CampaignOrigin.SEED) != (self.parent_case_id is None):
            raise ValueError("only mutation steps require a parent case ID")
        if self.feedback.case_id != self.result.base_result.case.case_id:
            raise ValueError("effect feedback differs from step result")
        if (self.origin == CampaignOrigin.SEED) != (self.mutation_attempt is None):
            raise ValueError("only mutation steps require a mutation attempt")
        if (self.origin == CampaignOrigin.SEED) != (self.scheduler_evidence is None):
            raise ValueError("only mutation steps require scheduler evidence")
        if self.mutation_attempt is not None and (
            self.mutation_attempt.child_case != self.result.base_result.case
            or self.mutation_attempt.parent_case_id != self.parent_case_id
        ):
            raise ValueError("mutation attempt differs from effect step lineage/result")
        if self.scheduler_evidence is not None and (
            self.scheduler_evidence.parent_case_id != self.parent_case_id
            or self.scheduler_evidence.child_case_id != self.result.base_result.case.case_id
            or self.scheduler_evidence.new_effect_keys != self.feedback.new_effect_keys
            or self.scheduler_evidence.new_violation_fingerprints
            != self.feedback.new_violation_fingerprints
        ):
            raise ValueError("scheduler evidence differs from effect feedback/lineage")


@dataclass(frozen=True, slots=True)
class EffectCampaignResult:
    serialization_schema: ClassVar[int] = 2

    config: EffectCampaignConfig
    initial_case_ids: tuple[str, ...]
    steps: tuple[EffectCampaignStep, ...]
    final_search_stats: EffectSearchStats
    retained_case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.config, EffectCampaignConfig):
            raise ValueError("effect campaign result requires typed config")
        if (
            not isinstance(self.initial_case_ids, tuple)
            or not self.initial_case_ids
            or len(set(self.initial_case_ids)) != len(self.initial_case_ids)
        ):
            raise ValueError("effect campaign result requires unique initial IDs")
        if not isinstance(self.steps, tuple) or not all(
            isinstance(step, EffectCampaignStep) for step in self.steps
        ):
            raise ValueError("effect campaign result requires typed steps")
        if len(self.steps) != self.config.execution_budget or len(self.initial_case_ids) > len(
            self.steps
        ):
            raise ValueError("effect campaign steps must fill the execution budget")
        if tuple(step.index for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("effect campaign step indexes must be contiguous")
        if not isinstance(self.final_search_stats, EffectSearchStats):
            raise ValueError("effect campaign result requires final search stats")
        if not isinstance(self.retained_case_ids, tuple) or not all(
            isinstance(case_id, str) and case_id for case_id in self.retained_case_ids
        ):
            raise ValueError("effect campaign result requires retained case IDs")


EffectResultProducer = Callable[[ArchiveCase], EffectRunResult]
EffectStepObserver = Callable[[EffectCampaignStep], None]


def _observed_name_segments(result: EffectRunResult, *, exclude_external: bool = False) -> set[str]:
    """Segment names of objects observed in the general filesystem tree.

    Sourced from `ObjectSnapshot` paths in the run's before/after snapshots — the
    general observed tree, never `protected_paths` (reading the protected list would
    be reading the answer). This is the only input the state-aware escape policies add
    to their generic vocabulary, and it is target-agnostic (the same mechanism yields
    whatever names the run happens to observe).

    With `exclude_external` set (the blind control arm), any object whose path lies in
    the EXTERNAL region is skipped, so a name that exists only outside the extraction
    boundary — the identity of a pre-existing external object — never enters the pool.
    EXTRACTION/HARNESS names the run itself produced are still kept. The filter is by
    common Region, not by any specific name, so it stays target-agnostic.
    """
    names: set[str] = set()
    for snapshot in (result.trace.before, result.trace.after):
        for obj in snapshot.objects:
            if exclude_external and path_region(obj.path) == Region.EXTERNAL:
                continue
            for segment in obj.path.split("/"):
                if segment and segment not in (".", ".."):
                    names.add(segment)
    return names


def run_effect_campaign(
    initial_cases: Sequence[ArchiveCase],
    produce_result: EffectResultProducer,
    config: EffectCampaignConfig,
    on_step: EffectStepObserver | None = None,
) -> EffectCampaignResult:
    """Exercise v2 policy causality without claiming a qualified native producer.

    `on_step` receives each completed step right after feedback and scheduler
    bookkeeping, so a caller can persist the loop record incrementally; an
    aborting producer then leaves every finished step behind. It cannot change
    the loop: the step is already appended and the result is unaffected.
    """
    if not callable(produce_result) or not isinstance(config, EffectCampaignConfig):
        raise ValueError("effect campaign requires a producer and typed config")
    if on_step is not None and not callable(on_step):
        raise ValueError("on_step must be callable when given")
    cases = tuple(initial_cases)
    if not cases or not all(isinstance(case, ArchiveCase) for case in cases):
        raise ValueError("initial cases must be nonempty ArchiveCase records")
    if config.execution_budget < len(cases):
        raise ValueError("execution_budget must cover all initial cases")
    initial_ids = tuple(case.case_id for case in cases)
    if len(set(initial_ids)) != len(initial_ids):
        raise ValueError("initial cases contain duplicate case IDs")

    state = EffectSearchState(cases, config.search_policy)
    steps: list[EffectCampaignStep] = []
    # The state-aware escape policy composes link targets from names the run has
    # observed in the general filesystem tree (not the protected list). We
    # accumulate them here and feed them to the mutator; every other policy leaves
    # this empty and is unaffected.
    state_aware = config.mutation_policy in (
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK,
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND,
    )
    # The blind control observes the same tree but drops EXTERNAL-region names, so it
    # cannot learn the identity (name) of a pre-existing external object.
    blind_observation = (
        config.mutation_policy == MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND
    )
    observed_names: set[str] = set()
    scheduler = (
        EffectAdaptiveMutationScheduler()
        if config.search_policy
        in (
            EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
            EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT,
            EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT,
        )
        else EffectUniformMutationScheduler()
    )

    def observe(
        case: ArchiveCase,
        origin: CampaignOrigin,
        parent: str | None,
        attempt: MutationAttempt | None = None,
        selection: MutationSelection | None = None,
    ) -> None:
        result = produce_result(case)
        if not isinstance(result, EffectRunResult) or result.base_result.case != case:
            raise ValueError("producer must return EffectRunResult for the requested case")
        if state_aware:
            observed_names.update(
                _observed_name_segments(result, exclude_external=blind_observation)
            )
        decision = state.consider(result)
        if (attempt is None) != (selection is None):
            raise ValueError("mutation attempt and scheduler selection must appear together")
        scheduler_evidence = None
        if attempt is not None and selection is not None:
            scheduler_evidence = scheduler.observe_outcome(
                selection,
                attempt,
                decision.new_effect_keys,
                decision.new_violation_fingerprints,
            )
        step = EffectCampaignStep(
            len(steps),
            origin,
            parent,
            result,
            decision,
            attempt,
            scheduler_evidence,
        )
        steps.append(step)
        if on_step is not None:
            on_step(step)

    for case in cases:
        observe(case, CampaignOrigin.SEED, None)

    rng = random.Random(config.random_seed)
    while len(steps) < config.execution_budget:
        parent = state.select_case(rng)
        selection = scheduler.choose_operator(operator_ids(config.mutation_policy), rng)
        attempt = apply_operator(
            parent,
            rng,
            config.mutation_policy,
            selection.operator_id,
            extra_components=tuple(sorted(observed_names)) if state_aware else (),
        )
        observe(
            attempt.child_case,
            CampaignOrigin.MUTATION,
            parent.case_id,
            attempt,
            selection,
        )

    return EffectCampaignResult(
        config,
        initial_ids,
        tuple(steps),
        state.stats,
        tuple(entry.case.case_id for entry in state.entries),
    )

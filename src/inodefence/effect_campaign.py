"""Synthetic v2 closed loop over a caller-owned EffectRunResult producer."""

import functools
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, overload

from inodefence.builder import build_tar
from inodefence.campaign import CampaignOrigin
from inodefence.campaign_hooks import (
    CampaignHooks,
    LightCampaignResult,
    ensure_no_unwired_hooks,
    resolve_on_step,
)
from inodefence.effect_scheduler import (
    EffectAdaptiveMutationScheduler,
    EffectMutationScheduler,
    EffectMutationSchedulerEvidence,
    EffectUniformMutationScheduler,
    PreViolationNoveltyScheduler,
    applied_operators,
)
from inodefence.feedback import (
    EffectSearchDecision,
    EffectSearchPolicy,
    EffectSearchState,
    EffectSearchStats,
)
from inodefence.feedback.exploration_search import (
    EXPLORATION_BASE_SEARCH_POLICY,
    ExplorationPolicyId,
    ExplorationSearchState,
)
from inodefence.generator import SeedCorpusId, minimal_seed_corpus, seed_corpus
from inodefence.model import ArchiveCase, EffectRunResult
from inodefence.model.filesystem import Region, path_region
from inodefence.mutation_scheduler import MutationSelection
from inodefence.mutator import (
    MutationAttempt,
    MutationOperatorId,
    MutationPolicy,
    apply_operator,
    operator_ids,
)
from inodefence.mutator.chain import MutationChainAttempt, apply_chain
from inodefence.mutator.policy import RECORDS_BUILD_INVALID, SEED_CORPUS

# v2 random-chain R (D062, ATTEMPTS convention, see inodefence.mutator.chain): attempts per
# execution are drawn uniformly in 1..m_max, m_max fixed by the search policy ID.
CHAIN_MAX_ATTEMPTS: dict[EffectSearchPolicy, int] = {
    EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M4: 4,
    EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M6: 6,
}
# The chain's search state (parent selection, admission, diagnostic channel) is exactly the
# seed-restart R: a seed every execution, nothing retained, the R/D/S-u boundary-attempt channel.
# effect_search.py only gained the two enum members (D062), so the loop builds the state with this
# policy and records the chain ID as the configuration's search policy.
CHAIN_SEARCH_STATE_POLICY = EffectSearchPolicy.R_UNRETAINED_SEED_RESTART


class BuildInvalidPolicy(StrEnum):
    """What the loop does with a mutation child the TAR builder cannot represent.

    ``ABORT`` (default, every existing and registered configuration): nothing changes --
    the producer's own ``build_tar`` raises and the campaign stops as before.
    ``RECORD`` (v2 only): the loop tries ``build_tar`` before the producer; on
    ``ValueError`` the step is recorded as a :class:`BuildInvalidStep`, spends one budget
    unit, gives the scheduler no reward and joins no corpus. It never reaches the
    producer, oracle or feedback. A configuration sets one value for all three arms.
    """

    ABORT = "abort"
    RECORD = "record"


@dataclass(frozen=True, slots=True)
class EffectCampaignConfig:
    random_seed: int
    execution_budget: int
    search_policy: EffectSearchPolicy
    mutation_policy: MutationPolicy = MutationPolicy.LEGACY
    # None: the mutation policy's profile decides (RECORDS_BUILD_INVALID -> record, else
    # abort). Read it through ``build_invalid_policy``.
    build_invalid: BuildInvalidPolicy | None = None
    # Exploratory policy outside EffectSearchPolicy (#511, W4 2026-11-18). None: unchanged.
    # When set, ``search_policy`` must be its declared base (the recorded diagnostic channel).
    exploration_policy: ExplorationPolicyId | None = None

    def __post_init__(self) -> None:
        if type(self.random_seed) is not int:
            raise ValueError("random_seed must be an integer")
        if type(self.execution_budget) is not int or self.execution_budget <= 0:
            raise ValueError("execution_budget must be a positive integer")
        if not isinstance(self.search_policy, EffectSearchPolicy):
            raise ValueError("search_policy must be a supported EffectSearchPolicy")
        if not isinstance(self.mutation_policy, MutationPolicy):
            raise ValueError("mutation_policy must be a supported MutationPolicy")
        if self.build_invalid is not None and not isinstance(
            self.build_invalid, BuildInvalidPolicy
        ):
            raise ValueError("build_invalid must be a BuildInvalidPolicy or None")
        if self.exploration_policy is not None:
            if not isinstance(self.exploration_policy, ExplorationPolicyId):
                raise ValueError("exploration_policy must be an ExplorationPolicyId or None")
            base = EXPLORATION_BASE_SEARCH_POLICY[self.exploration_policy]
            if self.search_policy != base:
                raise ValueError(
                    f"exploration policy {self.exploration_policy.value} requires "
                    f"search_policy {base.value}"
                )

    @property
    def build_invalid_policy(self) -> BuildInvalidPolicy:
        """The effective policy: the explicit value, else the mutation policy's profile."""
        if self.build_invalid is not None:
            return self.build_invalid
        if self.mutation_policy in RECORDS_BUILD_INVALID:
            return BuildInvalidPolicy.RECORD
        return BuildInvalidPolicy.ABORT


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
class BuildInvalidStep:
    """A mutation step whose child the TAR builder could not represent (``RECORD`` only).

    A separate type, not a variant of :class:`EffectCampaignStep`, so that type's
    serialized form (and every digest over it) is unchanged. There is no result, oracle
    verdict or feedback: the archive never existed. ``reason`` is the builder's message.
    """

    serialization_schema: ClassVar[int] = 1

    index: int
    parent_case_id: str
    mutation_attempt: MutationAttempt
    scheduler_evidence: EffectMutationSchedulerEvidence
    reason: str

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("build-invalid step index must be nonnegative")
        if not isinstance(self.parent_case_id, str) or not self.parent_case_id:
            raise ValueError("build-invalid step requires a parent case ID")
        if not isinstance(self.mutation_attempt, MutationAttempt) or not isinstance(
            self.scheduler_evidence, EffectMutationSchedulerEvidence
        ):
            raise ValueError("build-invalid step requires a mutation attempt and evidence")
        if self.mutation_attempt.parent_case_id != self.parent_case_id or (
            self.scheduler_evidence.parent_case_id != self.parent_case_id
            or self.scheduler_evidence.child_case_id != self.mutation_attempt.child_case.case_id
        ):
            raise ValueError("build-invalid step lineage differs from its attempt/evidence")
        if self.scheduler_evidence.new_effect_keys or (
            self.scheduler_evidence.new_violation_fingerprints
        ):
            raise ValueError("a build-invalid step observed nothing")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("build-invalid step requires the builder's reason")

    @property
    def origin(self) -> CampaignOrigin:
        return CampaignOrigin.MUTATION

    @property
    def case_id(self) -> str:
        return self.mutation_attempt.child_case.case_id


@dataclass(frozen=True, slots=True)
class EffectCampaignResult:
    serialization_schema: ClassVar[int] = 2

    config: EffectCampaignConfig
    initial_case_ids: tuple[str, ...]
    steps: tuple[EffectCampaignStep, ...]
    final_search_stats: EffectSearchStats
    retained_case_ids: tuple[str, ...]
    # RECORD only; empty under ABORT. ``steps`` + these fill the budget, indexes interleave.
    build_invalid_steps: tuple[BuildInvalidStep, ...] = ()
    # Chain R only: one per mutation execution (executed or build-invalid), by step index.
    mutation_chains: tuple[MutationChainAttempt, ...] = ()

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
        if not isinstance(self.build_invalid_steps, tuple) or not all(
            isinstance(step, BuildInvalidStep) for step in self.build_invalid_steps
        ):
            raise ValueError("effect campaign result requires typed build-invalid steps")
        if self.build_invalid_steps and (
            self.config.build_invalid_policy != BuildInvalidPolicy.RECORD
        ):
            raise ValueError("build-invalid steps require the RECORD policy")
        total = len(self.steps) + len(self.build_invalid_steps)
        if total != self.config.execution_budget or len(self.initial_case_ids) > len(self.steps):
            raise ValueError("effect campaign steps must fill the execution budget")
        executed = [step.index for step in self.steps]
        invalid = [step.index for step in self.build_invalid_steps]
        if executed != sorted(executed) or sorted(executed + invalid) != list(range(total)):
            raise ValueError("effect campaign step indexes must be contiguous")
        if not isinstance(self.mutation_chains, tuple) or not all(
            isinstance(chain, MutationChainAttempt) for chain in self.mutation_chains
        ):
            raise ValueError("effect campaign result requires typed mutation chains")
        if self.config.search_policy in CHAIN_MAX_ATTEMPTS:
            seeds = len(self.initial_case_ids)
            if [chain.index for chain in self.mutation_chains] != list(range(seeds, total)):
                raise ValueError("a chain policy records one chain per mutation execution")
            maximum = CHAIN_MAX_ATTEMPTS[self.config.search_policy]
            if any(chain.chain_length > maximum for chain in self.mutation_chains):
                raise ValueError("a chain exceeds its policy's maximum attempts")
        elif self.mutation_chains:
            raise ValueError("mutation chains require a chain search policy")
        if not isinstance(self.final_search_stats, EffectSearchStats):
            raise ValueError("effect campaign result requires final search stats")
        if not isinstance(self.retained_case_ids, tuple) or not all(
            isinstance(case_id, str) and case_id for case_id in self.retained_case_ids
        ):
            raise ValueError("effect campaign result requires retained case IDs")


EffectResultProducer = Callable[[ArchiveCase], EffectRunResult]
EffectStepObserver = Callable[[EffectCampaignStep], None]
BuildInvalidObserver = Callable[[BuildInvalidStep], None]
MutationChainObserver = Callable[[MutationChainAttempt], None]


def _choose_recorded(
    scheduler: EffectMutationScheduler,
    operators: tuple[MutationOperatorId, ...],
    drawn: list[MutationSelection],
    rng: random.Random,
) -> tuple[MutationOperatorId, int]:
    """One chain attempt's operator draw (the scheduler's own draw); keeps the selection."""
    chosen = scheduler.choose_operator(operators, rng)
    drawn.append(chosen)
    return chosen.operator_id, chosen.selected_weight


def _observed_name_segments(
    result: EffectRunResult, *, exclude_external: bool = False, before_only: bool = False
) -> set[str]:
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

    With `before_only` set (the fixed-baseline variant), only the BEFORE snapshot is
    read: the tree as the harness laid it out before extraction, independent of what
    this run's extraction then produced.
    """
    names: set[str] = set()
    snapshots = (result.trace.before,) if before_only else (result.trace.before, result.trace.after)
    for snapshot in snapshots:
        for obj in snapshot.objects:
            if exclude_external and path_region(obj.path) == Region.EXTERNAL:
                continue
            for segment in obj.path.split("/"):
                if segment and segment not in (".", ".."):
                    names.add(segment)
    return names


def bound_seed_cases(
    cases: tuple[ArchiveCase, ...], mutation_policy: MutationPolicy
) -> tuple[ArchiveCase, ...]:
    """The seeds a campaign runs: the caller's, or the corpus the policy binds (v2.1).

    A policy whose profile binds a non-registered corpus (``SEED_CORPUS``) runs that corpus
    when the caller passes the registered seeds (what the shared launchers always pass) or
    that corpus itself; any other caller corpus is refused rather than silently replaced.
    Every other policy, the registered ones included, runs exactly the caller's cases.
    """
    if not cases or not all(isinstance(case, ArchiveCase) for case in cases):
        raise ValueError("initial cases must be nonempty ArchiveCase records")
    corpus = SEED_CORPUS.get(mutation_policy, SeedCorpusId.REGISTERED)
    if corpus == SeedCorpusId.REGISTERED:
        return cases
    bound = seed_corpus(corpus)
    if cases not in (minimal_seed_corpus(), bound):
        raise ValueError(
            f"{mutation_policy.value} binds seed corpus {corpus.value}; "
            "pass the registered seeds or that corpus"
        )
    return bound


@overload
def run_effect_campaign(
    initial_cases: Sequence[ArchiveCase],
    produce_result: EffectResultProducer,
    config: EffectCampaignConfig,
    on_step: EffectStepObserver | None = None,
    hooks: None = None,
    *,
    on_build_invalid: BuildInvalidObserver | None = None,
    on_mutation_chain: MutationChainObserver | None = None,
) -> EffectCampaignResult: ...
@overload
def run_effect_campaign(
    initial_cases: Sequence[ArchiveCase],
    produce_result: EffectResultProducer,
    config: EffectCampaignConfig,
    on_step: EffectStepObserver | None = None,
    *,
    hooks: CampaignHooks,
    on_build_invalid: BuildInvalidObserver | None = None,
    on_mutation_chain: MutationChainObserver | None = None,
) -> EffectCampaignResult | LightCampaignResult: ...
def run_effect_campaign(
    initial_cases: Sequence[ArchiveCase],
    produce_result: EffectResultProducer,
    config: EffectCampaignConfig,
    on_step: EffectStepObserver | None = None,
    hooks: CampaignHooks | None = None,
    *,
    on_build_invalid: BuildInvalidObserver | None = None,
    on_mutation_chain: MutationChainObserver | None = None,
) -> EffectCampaignResult | LightCampaignResult:
    """Exercise v2 policy causality without claiming a qualified native producer.

    `on_step` receives each completed step right after feedback and scheduler
    bookkeeping, so a caller can persist the loop record incrementally; an
    aborting producer then leaves every finished step behind. It cannot change
    the loop: the step is already appended and the result is unaffected.

    `hooks` (``CampaignHooks``) optionally streams steps instead of retaining them
    (``retain_steps=False`` -> a ``LightCampaignResult``), stops early (``should_stop``)
    and checkpoints; with ``hooks`` ``None`` the result and order are byte-identical to before.

    ``config.build_invalid_policy`` = ``RECORD`` turns an unrepresentable mutation child into a
    :class:`BuildInvalidStep` (one budget unit, reward 0, no corpus) passed to
    ``on_build_invalid``; ``ABORT`` (default) leaves the loop exactly as before and never
    calls the builder itself. Seeds are never recorded as build-invalid. Without
    ``on_build_invalid`` the step goes to the step callback (``on_step`` or the hook's) in
    index order, so a caller that only streams steps sees every budget unit (W4, D060);
    such a callback must accept both step types when ``RECORD`` can apply.

    A chain search policy (``CHAIN_MAX_ATTEMPTS``, v2 R, D062) runs each execution as a chain:
    a seed, ``m = rng.randint(1, m_max)`` operator attempts (no-op attempts count), one execution
    of the final child, one budget unit. Its search state is the seed-restart R
    (``CHAIN_SEARCH_STATE_POLICY``); every chain is passed to ``on_mutation_chain`` and kept in
    ``EffectCampaignResult.mutation_chains``. Every other policy takes exactly the path above.
    """
    if not callable(produce_result) or not isinstance(config, EffectCampaignConfig):
        raise ValueError("effect campaign requires a producer and typed config")
    if on_step is not None and not callable(on_step):
        raise ValueError("on_step must be callable when given")
    if on_build_invalid is not None and not callable(on_build_invalid):
        raise ValueError("on_build_invalid must be callable when given")
    if on_mutation_chain is not None and not callable(on_mutation_chain):
        raise ValueError("on_mutation_chain must be callable when given")
    cases = bound_seed_cases(tuple(initial_cases), config.mutation_policy)
    if config.execution_budget < len(cases):
        raise ValueError("execution_budget must cover all initial cases")
    initial_ids = tuple(case.case_id for case in cases)
    if len(set(initial_ids)) != len(initial_ids):
        raise ValueError("initial cases contain duplicate case IDs")
    ensure_no_unwired_hooks(hooks)
    effective_on_step = resolve_on_step(hooks, on_step)
    should_stop = hooks.should_stop if hooks is not None else None
    retain = hooks is None or hooks.retain_steps
    executed = 0
    stop_reason: str | None = None

    chain_max = CHAIN_MAX_ATTEMPTS.get(config.search_policy)
    exploration = config.exploration_policy
    state: EffectSearchState | ExplorationSearchState = (
        ExplorationSearchState(cases, exploration)
        if exploration is not None
        else EffectSearchState(
            cases, CHAIN_SEARCH_STATE_POLICY if chain_max is not None else config.search_policy
        )
    )
    steps: list[EffectCampaignStep] = []
    build_invalid_steps: list[BuildInvalidStep] = []
    mutation_chains: list[MutationChainAttempt] = []
    record_build_invalid = config.build_invalid_policy == BuildInvalidPolicy.RECORD
    # The state-aware escape policy composes link targets from names the run has
    # observed in the general filesystem tree (not the protected list). We
    # accumulate them here and feed them to the mutator; every other policy leaves
    # this empty and is unaffected.
    state_aware = config.mutation_policy in (
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK,
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND,
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE,
        MutationPolicy.V2_FREEZE3_FIXED_BASELINE,
        MutationPolicy.V2_FREEZE3_FIXED_BASELINE_MINIMAL_EMPTY_REG,
    )
    # The blind control observes the same tree but drops EXTERNAL-region names, so it
    # cannot learn the identity (name) of a pre-existing external object.
    blind_observation = (
        config.mutation_policy == MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND
    )
    # The fixed-baseline variant reads the pool exactly once, from the first seed
    # run's BEFORE snapshot, and never updates it: the vocabulary is then a property
    # of the harness layout shared by every arm, not of the arm's own search history.
    fixed_baseline = config.mutation_policy in (
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE,
        MutationPolicy.V2_FREEZE3_FIXED_BASELINE,
        MutationPolicy.V2_FREEZE3_FIXED_BASELINE_MINIMAL_EMPTY_REG,
    )
    observed_names: set[str] = set()
    table = operator_ids(config.mutation_policy)
    scheduler: EffectMutationScheduler | PreViolationNoveltyScheduler = (
        PreViolationNoveltyScheduler(operators=table)
        if exploration is not None
        else EffectAdaptiveMutationScheduler(operators=table)
        if config.search_policy
        in (
            EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
            EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT,
            EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT,
        )
        else EffectUniformMutationScheduler(table)
    )

    def observe(
        case: ArchiveCase,
        origin: CampaignOrigin,
        parent: str | None,
        attempt: MutationAttempt | None = None,
        selection: MutationSelection | None = None,
    ) -> None:
        nonlocal executed
        result = produce_result(case)
        if not isinstance(result, EffectRunResult) or result.base_result.case != case:
            raise ValueError("producer must return EffectRunResult for the requested case")
        if fixed_baseline:
            if executed == 0:
                observed_names.update(_observed_name_segments(result, before_only=True))
        elif state_aware:
            observed_names.update(
                _observed_name_segments(result, exclude_external=blind_observation)
            )
        decision = state.consider(result)
        if (attempt is None) != (selection is None):
            raise ValueError("mutation attempt and scheduler selection must appear together")
        scheduler_evidence = None
        if attempt is not None and selection is not None:
            if isinstance(scheduler, PreViolationNoveltyScheduler):
                assert isinstance(state, ExplorationSearchState)
                scheduler_evidence = scheduler.observe_signals(
                    selection,
                    attempt,
                    applied_operators(attempt),
                    state.last.new_signals,
                    state.last.signal_retained,
                    decision.new_effect_keys,
                    decision.new_violation_fingerprints,
                )
            else:
                scheduler_evidence = scheduler.observe_outcome(
                    selection,
                    attempt,
                    decision.new_effect_keys,
                    decision.new_violation_fingerprints,
                )
        step = EffectCampaignStep(
            executed,
            origin,
            parent,
            result,
            decision,
            attempt,
            scheduler_evidence,
        )
        if retain:
            steps.append(step)
        executed += 1
        if effective_on_step is not None:
            effective_on_step(step)

    for case in cases:
        observe(case, CampaignOrigin.SEED, None)

    rng = random.Random(config.random_seed)
    while executed < config.execution_budget:
        if should_stop is not None:
            reason = should_stop(executed)
            if reason is not None:
                stop_reason = reason
                break
        parent = state.select_case(rng)
        if chain_max is None:
            selection = scheduler.choose_operator(operator_ids(config.mutation_policy), rng)
            attempt = apply_operator(
                parent,
                rng,
                config.mutation_policy,
                selection.operator_id,
                extra_components=tuple(sorted(observed_names)) if state_aware else (),
            )
        else:
            attempts = rng.randint(1, chain_max)
            drawn: list[MutationSelection] = []
            links, attempt = apply_chain(
                parent,
                rng,
                config.mutation_policy,
                attempts,
                functools.partial(
                    _choose_recorded, scheduler, operator_ids(config.mutation_policy), drawn
                ),
                extra_components=tuple(sorted(observed_names)) if state_aware else (),
            )
            selection = drawn[-1]
            chain = MutationChainAttempt(executed, parent.case_id, attempt.child_case, tuple(links))
            if retain:
                mutation_chains.append(chain)
            if on_mutation_chain is not None:
                on_mutation_chain(chain)
        if record_build_invalid:
            try:
                build_tar(attempt.child_case)
            except ValueError as error:
                evidence = scheduler.observe_outcome(selection, attempt, (), ())
                reason = str(error) or type(error).__name__
                invalid = BuildInvalidStep(executed, parent.case_id, attempt, evidence, reason)
                if retain:
                    build_invalid_steps.append(invalid)
                executed += 1
                if on_build_invalid is not None:
                    on_build_invalid(invalid)
                elif effective_on_step is not None:
                    effective_on_step(invalid)
                continue
        observe(
            attempt.child_case,
            CampaignOrigin.MUTATION,
            parent.case_id,
            attempt,
            selection,
        )

    retained = (
        state.retained_case_ids
        if isinstance(state, ExplorationSearchState)
        else tuple(entry.case.case_id for entry in state.entries)
    )
    # The full result type requires a complete run (len(steps) == budget), so a non-retaining
    # run OR an early stop returns the lightweight aggregate instead.
    if not retain or stop_reason is not None:
        return LightCampaignResult(executed, config.execution_budget, stop_reason, retained)
    return EffectCampaignResult(
        config,
        initial_ids,
        tuple(steps),
        state.stats,
        retained,
        tuple(build_invalid_steps),
        tuple(mutation_chains),
    )

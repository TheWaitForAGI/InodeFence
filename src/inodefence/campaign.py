"""Execution-count-bounded caller of mutation, one-case runs and feedback."""

import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from inodefence.feedback import (
    Corpus,
    CorpusStats,
    FeedbackDecision,
    FeedbackProjection,
    SearchDecision,
    SearchPolicy,
    SearchState,
)
from inodefence.model import ArchiveCase, RunResult
from inodefence.model.provenance import ExecutionProvenance, ExecutionSafety, TargetProvenance
from inodefence.mutator import MutationPolicy, mutate, mutate_with_policy
from inodefence.pipeline import run_case
from inodefence.provenance import freeze_provenance, sentinel_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.base import CampaignTarget
from inodefence.targets.isolated import IsolatedTarget


@dataclass(frozen=True, slots=True)
class CampaignConfig:
    """Explicit search seed and total executions, including initial cases."""

    random_seed: int
    execution_budget: int

    def __post_init__(self) -> None:
        if type(self.random_seed) is not int:
            raise ValueError("random_seed must be an integer")
        if type(self.execution_budget) is not int or self.execution_budget <= 0:
            raise ValueError("execution_budget must be a positive integer")


class CampaignOrigin(StrEnum):
    SEED = "seed"
    MUTATION = "mutation"


@dataclass(frozen=True, slots=True)
class CampaignStep:
    """Trusted runner-produced index, lineage, raw evidence and feedback.

    Direct construction is an internal assembly path, not validated evidence ingest.
    """

    index: int
    origin: CampaignOrigin
    parent_case_id: str | None
    result: RunResult
    feedback: FeedbackDecision


@dataclass(frozen=True, slots=True)
class CampaignResult:
    """Completed bounded campaign; full RunResults use O(execution_budget) memory.

    Evidence size per run also depends on case/output size. Retained IDs preserve
    Corpus admission order. These records are engineering evidence, not findings
    or validated analysis. There is no persistence, checkpointing or resume.
    Construction is trusted runner assembly, not validated imported evidence;
    use run_campaign for the enforced configuration and completion path.
    """

    serialization_schema: ClassVar[int] = 2

    config: CampaignConfig
    initial_case_ids: tuple[str, ...]
    steps: tuple[CampaignStep, ...]
    final_corpus_stats: CorpusStats
    retained_case_ids: tuple[str, ...]
    provenance: ExecutionProvenance
    experiment_config_id: str | None = None


@dataclass(frozen=True, slots=True)
class SearchCampaignConfig:
    """Explicit caller configuration for policy-aware, in-memory campaigns.

    This is not an ExperimentConfig or a legacy evidence-export configuration.
    Policy identifiers are enum values; unknown/untyped values fail immediately.
    """

    random_seed: int
    execution_budget: int
    search_policy: SearchPolicy
    mutation_policy: MutationPolicy = MutationPolicy.LEGACY
    feedback_projection: FeedbackProjection = FeedbackProjection.FULL

    def __post_init__(self) -> None:
        CampaignConfig(self.random_seed, self.execution_budget)
        for name, expected in (
            ("search_policy", SearchPolicy),
            ("mutation_policy", MutationPolicy),
            ("feedback_projection", FeedbackProjection),
        ):
            if not isinstance(getattr(self, name), expected):
                raise ValueError(f"{name} must be a supported {expected.__name__}")


@dataclass(frozen=True, slots=True)
class SearchCampaignStep:
    """Full raw evidence, logical lineage and explicit policy admission."""

    index: int
    origin: CampaignOrigin
    parent_case_id: str | None
    result: RunResult
    feedback: SearchDecision


@dataclass(frozen=True, slots=True)
class SearchCampaignResult:
    """Trusted bounded assembly with separately identified policy configuration.

    Canonical model envelope v1 is distinct from legacy CampaignResult v2.
    B0's seed bank/active case is separate from retained corpus accounting.
    No manifest/journal reader, checkpointing or validated comparison is implied.
    """

    config: SearchCampaignConfig
    initial_case_ids: tuple[str, ...]
    steps: tuple[SearchCampaignStep, ...]
    final_corpus_stats: CorpusStats
    retained_case_ids: tuple[str, ...]
    unique_feedback_keys: int
    active_case_id: str | None
    provenance: ExecutionProvenance


@dataclass(frozen=True, slots=True)
class _CampaignExecution:
    cases: tuple[ArchiveCase, ...]
    initial_case_ids: tuple[str, ...]
    provenance: ExecutionProvenance
    execute: Callable[[ArchiveCase], RunResult]


def _prepare_campaign(
    initial_cases: Sequence[ArchiveCase],
    target: CampaignTarget,
    config: CampaignConfig,
    *,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    provenance: ExecutionProvenance | None = None,
    experiment_config_id: str | None = None,
) -> _CampaignExecution:
    """Shared seed validation, fail-closed execution gate and frozen provenance."""
    if experiment_config_id is not None and (
        not isinstance(experiment_config_id, str)
        or re.fullmatch(r"[0-9a-f]{64}", experiment_config_id) is None
    ):
        raise ValueError("experiment_config_id must be lowercase SHA-256 or None")
    cases = tuple(initial_cases)
    if not cases:
        raise ValueError("initial cases must be non-empty")
    if config.execution_budget < len(cases):
        raise ValueError("execution_budget must cover all initial cases")
    initial_ids = tuple(case.case_id for case in cases)
    if len(set(initial_ids)) != len(initial_ids):
        raise ValueError("initial cases contain duplicate case IDs")

    declared_target = getattr(target, "provenance", None)
    if not isinstance(declared_target, TargetProvenance):
        raise ValueError("campaign target must declare TargetProvenance before execution")
    if isinstance(target, IsolatedTarget) and (
        type(target) is not IsolatedTarget
        or declared_target.execution_safety != ExecutionSafety.ISOLATION_REQUIRED
    ):
        raise ValueError("target requires execution isolation through the enforced target wrapper")
    isolation = None
    if declared_target.execution_safety == ExecutionSafety.ISOLATION_REQUIRED:
        # Exact composition owns execution; subclass/attribute declarations cannot bypass it.
        if type(target) is not IsolatedTarget:
            raise ValueError(
                "target requires execution isolation through the enforced target wrapper"
            )
        isolation = target.capture_isolation()
    frozen = (
        freeze_provenance(declared_target, sentinels, isolation=isolation)
        if provenance is None
        else provenance
    )
    if not isinstance(frozen, ExecutionProvenance):
        raise ValueError("provenance must be ExecutionProvenance")
    if (
        frozen.target != declared_target
        or frozen.sentinels != sentinel_provenance(sentinels)
        or frozen.isolation != isolation
    ):
        raise ValueError("provenance must match target, sentinel and isolation configuration")

    def execute(case: ArchiveCase) -> RunResult:
        if type(target) is IsolatedTarget:
            assert frozen.isolation is not None  # validated against captured isolation above
            if (
                target.isolation_policy != frozen.isolation.policy
                or target.invocation.artifacts != frozen.isolation.artifacts
            ):
                raise ValueError("isolation configuration changed during campaign")
        if target.provenance != frozen.target:
            raise ValueError("target configuration changed during campaign")
        result = run_case(case, target, sentinels=sentinels)
        if not isinstance(result, RunResult) or result.case != case:
            raise ValueError("execution must return RunResult for the requested case")
        execution = result.execution
        if (
            TargetProvenance(
                execution.target_id,
                execution.target_version,
                execution.timeout_seconds,
                frozen.target.execution_safety,
            )
            != frozen.target
        ):
            raise ValueError("execution result differs from frozen target provenance")
        return result

    return _CampaignExecution(cases, initial_ids, frozen, execute)


def run_campaign(
    initial_cases: Sequence[ArchiveCase],
    target: CampaignTarget,
    config: CampaignConfig,
    *,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    provenance: ExecutionProvenance | None = None,
    experiment_config_id: str | None = None,
) -> CampaignResult:
    """Run explicit seeds in order, then select → mutate → execute → consider.

    Initial cases must be nonempty, fit the budget and have unique case IDs.
    Snapshot the collection before execution; never mutate the caller's cases.
    One campaign-owned RNG serves both uniform parent selection and mutation.
    Seeds consume no search RNG. A no-op child is executed once, without retry.
    Freeze target/sentinel/source/environment provenance before run_case. Supplied
    immutable provenance is preserved by identity after configuration validation;
    callers own its source/environment accuracy. Result configuration drift is
    a harness error, never a reason to rewrite the frozen configuration.
    Trusted references or the enforced IsolatedTarget composition can run campaigns.
    Boundary availability/attestation is checked before capture/runtime/execution;
    there is no bypass flag, subclass override or ordinary subprocess fallback.
    Every returned target status counts. Infrastructure exceptions propagate;
    an aborted campaign does not return an invented completed result.

    Deterministic lineage requires the same semantic feedback outcomes as well
    as the same initial cases, config and RNG implementation. Raw filesystem
    allocation, timestamps and process durations need not repeat.
    """
    prepared = _prepare_campaign(
        initial_cases,
        target,
        config,
        sentinels=sentinels,
        provenance=provenance,
        experiment_config_id=experiment_config_id,
    )
    corpus = Corpus()
    steps: list[CampaignStep] = []
    for case in prepared.cases:
        result = prepared.execute(case)
        steps.append(
            CampaignStep(len(steps), CampaignOrigin.SEED, None, result, corpus.consider(result))
        )

    rng = random.Random(config.random_seed)
    while len(steps) < config.execution_budget:
        parent = corpus.select_case(rng)
        child = mutate(parent, rng)
        result = prepared.execute(child)
        steps.append(
            CampaignStep(
                len(steps), CampaignOrigin.MUTATION, parent.case_id, result, corpus.consider(result)
            )
        )

    return CampaignResult(
        config,
        prepared.initial_case_ids,
        tuple(steps),
        corpus.stats,
        tuple(entry.case.case_id for entry in corpus.entries),
        prepared.provenance,
        experiment_config_id,
    )


def run_search_campaign(
    initial_cases: Sequence[ArchiveCase],
    target: CampaignTarget,
    config: SearchCampaignConfig,
    *,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    provenance: ExecutionProvenance | None = None,
    completed_step: Callable[[SearchCampaignStep], None] | None = None,
) -> SearchCampaignResult:
    """Run declared search/mutation/projection policies under the campaign gate.

    Seeds execute in order without search RNG draws. One owned RNG then serves
    policy selection and versioned mutation; every child, including no-ops and
    all returned statuses, executes once. Every policy receives full raw
    observations/oracle results. B0 advances to the previous child with no
    novelty admission; B1/B3 uniformly select retained cases. No adaptive
    scheduling, exporter or ExperimentConfig binding is implemented here.
    Determinism requires the same semantic outcomes, config and RNG version.

    An optional completed_step sink receives each immutable step after run_case
    has returned (including sandbox cleanup) and policy feedback is complete,
    before the next step begins. Sink exceptions propagate and no subsequent
    execution starts. The core still returns no partial result on failure; sinks
    own any incremental evidence they preserve.
    """
    if not isinstance(config, SearchCampaignConfig):
        raise ValueError("config must be a SearchCampaignConfig")
    if completed_step is not None and not callable(completed_step):
        raise ValueError("completed_step must be callable or None")
    prepared = _prepare_campaign(
        initial_cases,
        target,
        CampaignConfig(config.random_seed, config.execution_budget),
        sentinels=sentinels,
        provenance=provenance,
    )
    state = SearchState(prepared.cases, config.search_policy, projection=config.feedback_projection)
    steps: list[SearchCampaignStep] = []
    for case in prepared.cases:
        result = prepared.execute(case)
        step = SearchCampaignStep(
            len(steps), CampaignOrigin.SEED, None, result, state.consider(result)
        )
        steps.append(step)
        if completed_step is not None:
            completed_step(step)
    rng = random.Random(config.random_seed)
    while len(steps) < config.execution_budget:
        parent = state.select_case(rng)
        child = mutate_with_policy(parent, rng, config.mutation_policy)
        result = prepared.execute(child)
        step = SearchCampaignStep(
            len(steps),
            CampaignOrigin.MUTATION,
            parent.case_id,
            result,
            state.consider(result),
        )
        steps.append(step)
        if completed_step is not None:
            completed_step(step)
    return SearchCampaignResult(
        config,
        prepared.initial_case_ids,
        tuple(steps),
        state.stats,
        tuple(entry.case.case_id for entry in state.entries),
        state.unique_feedback_keys,
        state.active_case.case_id if state.active_case else None,
        prepared.provenance,
    )

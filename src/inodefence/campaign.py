"""Execution-count-bounded caller of mutation, one-case runs and feedback."""

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from inodefence.feedback import Corpus, CorpusStats, FeedbackDecision
from inodefence.model import ArchiveCase, RunResult
from inodefence.model.provenance import ExecutionProvenance, ExecutionSafety, TargetProvenance
from inodefence.mutator import mutate
from inodefence.pipeline import run_case
from inodefence.provenance import freeze_provenance, sentinel_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.base import CampaignTarget


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
    """Zero-based execution index, parent lineage, raw evidence and feedback."""

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
    """

    config: CampaignConfig
    initial_case_ids: tuple[str, ...]
    steps: tuple[CampaignStep, ...]
    final_corpus_stats: CorpusStats
    retained_case_ids: tuple[str, ...]
    provenance: ExecutionProvenance
    experiment_config_id: str | None = None


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
    Only explicitly trusted reference adapters can run campaigns today. Isolation
    requirements fail before capture/runtime/execution; there is no bypass flag.
    Every returned target status counts. Infrastructure exceptions propagate;
    an aborted campaign does not return an invented completed result.

    Deterministic lineage requires the same semantic feedback outcomes as well
    as the same initial cases, config and RNG implementation. Raw filesystem
    allocation, timestamps and process durations need not repeat.
    """
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
    if declared_target.execution_safety != ExecutionSafety.TRUSTED_REFERENCE:
        raise ValueError("target requires execution isolation; no validated boundary is available")
    frozen = freeze_provenance(declared_target, sentinels) if provenance is None else provenance
    if not isinstance(frozen, ExecutionProvenance):
        raise ValueError("provenance must be ExecutionProvenance")
    if frozen.target != declared_target or frozen.sentinels != sentinel_provenance(sentinels):
        raise ValueError("provenance must match target and sentinel configuration")

    def execute(case: ArchiveCase) -> RunResult:
        if target.provenance != frozen.target:
            raise ValueError("target configuration changed during campaign")
        result = run_case(case, target, sentinels=sentinels)
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

    corpus = Corpus()
    steps: list[CampaignStep] = []
    for case in cases:
        result = execute(case)
        steps.append(
            CampaignStep(len(steps), CampaignOrigin.SEED, None, result, corpus.consider(result))
        )

    rng = random.Random(config.random_seed)
    while len(steps) < config.execution_budget:
        parent = corpus.select_case(rng)
        child = mutate(parent, rng)
        result = execute(child)
        steps.append(
            CampaignStep(
                len(steps), CampaignOrigin.MUTATION, parent.case_id, result, corpus.consider(result)
            )
        )

    return CampaignResult(
        config,
        initial_ids,
        tuple(steps),
        corpus.stats,
        tuple(entry.case.case_id for entry in corpus.entries),
        frozen,
        experiment_config_id,
    )

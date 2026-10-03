"""Execution-count-bounded caller of mutation, one-case runs and feedback."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from inodefence.feedback import Corpus, CorpusStats, FeedbackDecision
from inodefence.model import ArchiveCase, RunResult
from inodefence.mutator import mutate
from inodefence.pipeline import run_case
from inodefence.runtime import SentinelSpec
from inodefence.targets import TargetAdapter


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


def run_campaign(
    initial_cases: Sequence[ArchiveCase],
    target: TargetAdapter,
    config: CampaignConfig,
    *,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
) -> CampaignResult:
    """Run explicit seeds in order, then select → mutate → execute → consider.

    Initial cases must be nonempty, fit the budget and have unique case IDs.
    Snapshot the collection before execution; never mutate the caller's cases.
    One campaign-owned RNG serves both uniform parent selection and mutation.
    Seeds consume no search RNG. A no-op child is executed once, without retry.
    Every returned target status counts. Infrastructure exceptions propagate;
    an aborted campaign does not return an invented completed result.

    Deterministic lineage requires the same semantic feedback outcomes as well
    as the same initial cases, config and RNG implementation. Raw filesystem
    allocation, timestamps and process durations need not repeat.
    """
    cases = tuple(initial_cases)
    if not cases:
        raise ValueError("initial cases must be non-empty")
    if config.execution_budget < len(cases):
        raise ValueError("execution_budget must cover all initial cases")
    initial_ids = tuple(case.case_id for case in cases)
    if len(set(initial_ids)) != len(initial_ids):
        raise ValueError("initial cases contain duplicate case IDs")

    corpus = Corpus()
    steps: list[CampaignStep] = []
    for case in cases:
        result = run_case(case, target, sentinels=sentinels)
        steps.append(
            CampaignStep(len(steps), CampaignOrigin.SEED, None, result, corpus.consider(result))
        )

    rng = random.Random(config.random_seed)
    while len(steps) < config.execution_budget:
        parent = corpus.select_case(rng)
        child = mutate(parent, rng)
        result = run_case(child, target, sentinels=sentinels)
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
    )

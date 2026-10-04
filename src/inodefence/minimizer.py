"""Deterministic archive reduction with a caller-owned evidence predicate."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from enum import StrEnum

from inodefence.model import ArchiveCase, EntryType, RunResult

MINIMIZATION_POLICY = "greedy-archive-reduction-v1"


class ReductionKind(StrEnum):
    INITIAL = "initial"
    ENTRY = "entry-deletion"
    CONTENT = "content-reduction"
    PATH = "path-simplification"
    MODE = "mode-simplification"
    LINK_TARGET = "link-target-simplification"


class MinimizationTermination(StrEnum):
    FIXED_POINT = "local-fixed-point"
    BUDGET = "execution-budget-exhausted"


@dataclass(frozen=True, slots=True)
class MinimizationStep:
    """Full evaluated evidence and predicate outcome; rejected trials stay visible."""

    index: int
    transformation: ReductionKind
    result: RunResult
    accepted: bool


@dataclass(frozen=True, slots=True)
class MinimizationResult:
    """Trusted assembly result, with no claim of globally smallest input."""

    policy_id: str
    execution_budget: int
    initial_case: ArchiveCase
    final_case: ArchiveCase
    steps: tuple[MinimizationStep, ...]
    termination: MinimizationTermination


def _text_reductions(value: str) -> tuple[str, ...]:
    candidates = (
        "a",
        value.rsplit("/", 1)[-1],
        value.removeprefix("./"),
        value.removeprefix("../"),
        value.replace("//", "/", 1),
    )
    return tuple(
        dict.fromkeys(
            candidate
            for candidate in candidates
            if candidate and len(candidate.encode("utf-8")) < len(value.encode("utf-8"))
        )
    )


def reduction_candidates(case: ArchiveCase) -> Iterator[tuple[ReductionKind, ArchiveCase]]:
    """Fixed transformation/entry order; every yielded case is strictly smaller.

    No dependency repair or normalization is performed. Text changes are raw
    candidate operations whose semantic acceptability belongs to the predicate.
    Candidate duplicates/no-ops are omitted within this round, without execution.
    """
    seen = {case.case_id}

    def unique(kind: ReductionKind, candidate: ArchiveCase):
        if candidate.case_id not in seen:
            seen.add(candidate.case_id)
            yield kind, candidate

    for index in range(len(case.entries)):
        yield from unique(
            ReductionKind.ENTRY, ArchiveCase(case.entries[:index] + case.entries[index + 1 :])
        )
    for kind in (
        ReductionKind.CONTENT,
        ReductionKind.PATH,
        ReductionKind.MODE,
        ReductionKind.LINK_TARGET,
    ):
        for index, entry in enumerate(case.entries):
            changes = []
            if kind == ReductionKind.CONTENT and entry.entry_type == EntryType.REGULAR:
                assert entry.content is not None
                changes = [
                    replace(entry, content=entry.content[:size])
                    for size in dict.fromkeys((0, len(entry.content) // 2, len(entry.content) - 1))
                    if 0 <= size < len(entry.content)
                ]
            elif kind == ReductionKind.PATH:
                changes = [replace(entry, path=text) for text in _text_reductions(entry.path)]
            elif kind == ReductionKind.MODE and entry.mode:
                changes = [
                    replace(entry, mode=mode)
                    for mode in dict.fromkeys(
                        (0, entry.mode & 0o777, entry.mode & (entry.mode - 1))
                    )
                    if mode != entry.mode
                ]
            elif kind == ReductionKind.LINK_TARGET and entry.link_target is not None:
                changes = [
                    replace(entry, link_target=text) for text in _text_reductions(entry.link_target)
                ]
            for changed in changes:
                candidate = ArchiveCase(
                    case.entries[:index] + (changed,) + case.entries[index + 1 :]
                )
                yield from unique(kind, candidate)


def minimize_case(
    case: ArchiveCase,
    evaluate: Callable[[ArchiveCase], RunResult],
    preserves: Callable[[RunResult], bool],
    *,
    execution_budget: int,
) -> MinimizationResult:
    """Evaluate baseline then greedily accept smaller cases preserving the predicate.

    Budget includes baseline and rejected trials. On acceptance restart the fixed
    candidate order. No RNG, target-specific rule, execution-status filtering,
    evidence caching or replay infrastructure is used. Caller owns execution
    isolation, target/configuration binding and the research evidence condition.
    Evaluator/predicate exceptions propagate; an aborted run is not completed
    evidence. Reproducibility requires repeatable evaluator/predicate outcomes.
    """
    if not isinstance(case, ArchiveCase):
        raise ValueError("case must be an ArchiveCase")
    if type(execution_budget) is not int or execution_budget <= 0:
        raise ValueError("execution_budget must be a positive integer")
    steps: list[MinimizationStep] = []

    def trial(candidate: ArchiveCase, kind: ReductionKind) -> bool:
        result = evaluate(candidate)
        if not isinstance(result, RunResult) or result.case != candidate:
            raise ValueError("evaluator must return RunResult for the requested case")
        accepted = preserves(result)
        if type(accepted) is not bool:
            raise ValueError("preservation predicate must return bool")
        steps.append(MinimizationStep(len(steps), kind, result, accepted))
        return accepted

    if not trial(case, ReductionKind.INITIAL):
        raise ValueError("initial case does not satisfy the preservation condition")
    current = case

    def finish(termination: MinimizationTermination) -> MinimizationResult:
        return MinimizationResult(
            MINIMIZATION_POLICY, execution_budget, case, current, tuple(steps), termination
        )

    while True:
        for kind, candidate in reduction_candidates(current):
            if len(steps) == execution_budget:
                return finish(MinimizationTermination.BUDGET)
            if trial(candidate, kind):
                current = candidate
                break
        else:
            return finish(MinimizationTermination.FIXED_POINT)

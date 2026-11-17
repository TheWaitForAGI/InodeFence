"""Entry-level minimization of one violating case, re-run check and a cause signature (#519).

Post-processing outside the exploration loop: the caller hands in a violating ``ArchiveCase``
(for example a saved violation step read from an exploration result folder with
:func:`inodefence.case_replay.load_request`) and an evaluator that runs one case and returns its
verdict. This module never runs anything itself and imports no product driver; the caller owns
execution isolation, the target binding (image, version, options) and where evidence is kept.

**The minimized input and its signature are never used as a seed or corpus entry of any
exploration, benchmark or comparison arm.** They are analysis output for people. Feeding them back
would plant a found violation into a search and contaminate any later measurement.

What it does:

1. :func:`minimize_entries` — delta debugging (ddmin) over the entry list. A candidate keeps a
   subset of the entries in their original order; nothing inside an entry is changed (paths,
   targets, modes and contents stay as recorded; the finer text/mode reductions live in
   :mod:`inodefence.minimizer`). A candidate is **kept** only when the evaluator judged it and its
   set of violated contracts (C0/C1/C2) is exactly the original's — an extra or a missing
   contract is a different verdict. Un-judged runs (infrastructure failure, incomplete
   observation) are never kept. Candidates the deterministic USTAR builder cannot encode are
   skipped without running. Within one minimization a case already evaluated is not run again;
   the earlier verdict is reused and the trial is marked ``reused``.
2. :func:`verify` — re-runs the original and the minimum ``rounds`` times each and reports whether
   every round reproduced the same contract set. A run that does not reproduce means the verdict is
   not deterministic for this input; the caller must not publish the minimum as a result then.
3. :func:`cause_signature` — a first draft: the violated contracts plus, per remaining entry in
   order, its type and the *shape* of its link target (absolute, parent depth, plain relative,
   or pointing at another entry of the case). Paths, link target text, file names and any sentinel
   or protected-path name are not part of it.

Limits: the minimum is 1-minimal with respect to removing entry subsets ddmin tries, not the
globally smallest input. Contract-set preservation keeps the declared verdict class, not a proven
root cause. Nothing here is evidence about search performance.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Any

from inodefence.builder import build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType

CONTRACTS = ("C0", "C1", "C2")
TRIAGE_POLICY = "entry-ddmin-contract-set-v1"
SIGNATURE_SCHEMA = "inodefence-violation-signature-v1"
RECORD_SCHEMA = "inodefence-violation-triage-v1"


@dataclass(frozen=True, slots=True)
class TrialVerdict:
    """What the evaluator saw for one case: judged or not, and which contracts were violated.

    ``detail`` is free-form evidence the caller wants kept (e.g. termination, raw round record);
    it is recorded, never interpreted here.
    """

    judged: bool
    violated: frozenset[str]
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.judged) is not bool:
            raise ValueError("judged must be a bool")
        if not isinstance(self.violated, frozenset) or not self.violated <= set(CONTRACTS):
            raise ValueError(f"violated must be a frozenset of {CONTRACTS}")
        if not self.judged and self.violated:
            raise ValueError("an un-judged run has no violated contracts")


Evaluate = Callable[[ArchiveCase], TrialVerdict]


class Termination(StrEnum):
    FIXED_POINT = "ddmin-1-minimal"
    BUDGET = "execution-budget-exhausted"
    SINGLE_ENTRY = "single-entry"


@dataclass(frozen=True, slots=True)
class Trial:
    index: int
    case_id: str
    entry_count: int
    verdict: TrialVerdict
    kept: bool
    reused: bool


@dataclass(frozen=True, slots=True)
class MinimizationRun:
    policy_id: str
    execution_budget: int
    original: ArchiveCase
    minimal: ArchiveCase
    contracts: frozenset[str]
    trials: tuple[Trial, ...]
    termination: Termination

    @property
    def executions(self) -> int:
        """Evaluator calls actually made (reused verdicts are not executions)."""
        return sum(1 for trial in self.trials if not trial.reused)


def _preserves(verdict: TrialVerdict, contracts: frozenset[str]) -> bool:
    return verdict.judged and verdict.violated == contracts


def _encodable(case: ArchiveCase) -> bool:
    try:
        build_tar(case)
    except ValueError:
        return False
    return True


def _split(items: Sequence[int], parts: int) -> list[tuple[int, ...]]:
    size, extra = divmod(len(items), parts)
    chunks, start = [], 0
    for index in range(parts):
        end = start + size + (1 if index < extra else 0)
        chunks.append(tuple(items[start:end]))
        start = end
    return [chunk for chunk in chunks if chunk]


def minimize_entries(
    case: ArchiveCase, evaluate: Evaluate, *, execution_budget: int
) -> MinimizationRun:
    """ddmin over entries, keeping only candidates with exactly the original contract set.

    The original is evaluated first (one execution) and must be a judged violation. The budget
    counts executions (the baseline included, reused verdicts excluded). On exhaustion the
    smallest kept case so far is returned with ``Termination.BUDGET``.
    """
    if not isinstance(case, ArchiveCase) or not case.entries:
        raise ValueError("case must be a nonempty ArchiveCase")
    if type(execution_budget) is not int or execution_budget <= 0:
        raise ValueError("execution_budget must be a positive integer")
    build_tar(case)  # the original itself must be encodable
    trials: list[Trial] = []
    seen: dict[str, TrialVerdict] = {}

    def executions() -> int:
        return sum(1 for trial in trials if not trial.reused)

    def run(candidate: ArchiveCase, contracts: frozenset[str] | None) -> TrialVerdict:
        reused = candidate.case_id in seen
        if reused:
            verdict = seen[candidate.case_id]
        else:
            verdict = evaluate(candidate)
            if not isinstance(verdict, TrialVerdict):
                raise ValueError("evaluator must return a TrialVerdict")
            seen[candidate.case_id] = verdict
        kept = contracts is None or _preserves(verdict, contracts)
        trials.append(
            Trial(len(trials), candidate.case_id, len(candidate.entries), verdict, kept, reused)
        )
        return verdict

    baseline = run(case, None)
    if not baseline.judged or not baseline.violated:
        raise ValueError("the original case is not a judged violation under this evaluator")
    contracts = baseline.violated
    indices: tuple[int, ...] = tuple(range(len(case.entries)))

    def subset(kept_indices: Sequence[int]) -> ArchiveCase:
        return ArchiveCase(tuple(case.entries[index] for index in kept_indices))

    def finish(current: tuple[int, ...], termination: Termination) -> MinimizationRun:
        return MinimizationRun(
            TRIAGE_POLICY,
            execution_budget,
            case,
            subset(current),
            contracts,
            tuple(trials),
            termination,
        )

    def test(candidate_indices: tuple[int, ...]) -> bool | None:
        """True/False = kept or not; None = budget exhausted before it could run."""
        candidate = subset(candidate_indices)
        if not _encodable(candidate):
            return False
        if candidate.case_id not in seen and executions() >= execution_budget:
            return None
        return _preserves(run(candidate, contracts), contracts)

    current = indices
    parts = 2
    while len(current) >= 2:
        chunks = _split(current, min(parts, len(current)))
        reduced = False
        # Try each chunk alone, then each complement (ddmin order).
        for candidate in [*chunks, *(tuple(i for i in current if i not in c) for c in chunks)]:
            if not candidate or candidate == current:
                continue
            outcome = test(candidate)
            if outcome is None:
                return finish(current, Termination.BUDGET)
            if outcome:
                was_chunk = candidate in chunks
                current = candidate
                parts = 2 if was_chunk else max(parts - 1, 2)
                reduced = True
                break
        if not reduced:
            if parts >= len(current):
                break
            parts = min(parts * 2, len(current))
    termination = Termination.SINGLE_ENTRY if len(current) == 1 else Termination.FIXED_POINT
    return finish(current, termination)


@dataclass(frozen=True, slots=True)
class Verification:
    rounds: int
    contracts: frozenset[str]
    original: tuple[TrialVerdict, ...]
    minimal: tuple[TrialVerdict, ...]

    @property
    def consistent(self) -> bool:
        """Every round of both cases was judged with exactly the expected contract set."""
        return all(
            _preserves(verdict, self.contracts) for verdict in (*self.original, *self.minimal)
        )


def verify(run: MinimizationRun, evaluate: Evaluate, *, rounds: int) -> Verification:
    """Re-run the original and the minimum ``rounds`` times each (fresh evaluations, no reuse)."""
    if type(rounds) is not int or rounds <= 0:
        raise ValueError("rounds must be a positive integer")
    original = tuple(evaluate(run.original) for _ in range(rounds))
    minimal = tuple(evaluate(run.minimal) for _ in range(rounds))
    for verdict in (*original, *minimal):
        if not isinstance(verdict, TrialVerdict):
            raise ValueError("evaluator must return a TrialVerdict")
    return Verification(rounds, run.contracts, original, minimal)


def _target_shape(entry: ArchiveEntry, case: ArchiveCase) -> str | None:
    """Shape of a link target without its text: absolute / parent-N / relative / entry."""
    target = entry.link_target
    if target is None:
        return None
    if any(other is not entry and other.path == target for other in case.entries):
        return "entry"
    if target.startswith("/"):
        return "absolute"
    parents = 0
    for part in target.split("/"):
        if part in ("", "."):
            continue
        if part != "..":
            break
        parents += 1
    return f"parent-{parents}" if parents else "relative"


def cause_signature(case: ArchiveCase, contracts: frozenset[str]) -> dict[str, Any]:
    """First-draft cause signature: contracts + ordered entry kinds and link-target shapes.

    No path, link target text, file name, sentinel or protected-path name is included, so two
    cases with the same structure but different names share a signature.
    """
    entries = [
        {"type": entry.entry_type.value, "target": _target_shape(entry, case)}
        for entry in case.entries
    ]
    body = {
        "schema": SIGNATURE_SCHEMA,
        "contracts": sorted(contracts),
        "entries": entries,
    }
    digest = sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**body, "id": digest[:16]}


def _verdict_record(verdict: TrialVerdict) -> dict[str, Any]:
    return {
        "judged": verdict.judged,
        "violated": sorted(verdict.violated),
        "detail": dict(verdict.detail),
    }


def _entry_count_by_type(case: ArchiveCase) -> dict[str, int]:
    counts = {kind.value: 0 for kind in EntryType}
    for entry in case.entries:
        counts[entry.entry_type.value] += 1
    return {kind: count for kind, count in counts.items() if count}


def triage_record(
    run: MinimizationRun, verification: Verification | None, *, label: str
) -> dict[str, Any]:
    """JSON-serializable record of one triage (no TAR bytes; case ids and sizes only)."""
    return {
        "schema": RECORD_SCHEMA,
        "label": label,
        "policy_id": run.policy_id,
        "use_restriction": (
            "analysis output only; never a seed or corpus entry of any exploration, benchmark "
            "or comparison arm"
        ),
        "contracts": sorted(run.contracts),
        "execution_budget": run.execution_budget,
        "executions": run.executions,
        "termination": run.termination.value,
        "original": {
            "case_id": run.original.case_id,
            "entries": len(run.original.entries),
            "by_type": _entry_count_by_type(run.original),
        },
        "minimal": {
            "case_id": run.minimal.case_id,
            "entries": len(run.minimal.entries),
            "by_type": _entry_count_by_type(run.minimal),
        },
        "signature": cause_signature(run.minimal, run.contracts),
        "trials": [
            {
                "index": trial.index,
                "case_id": trial.case_id,
                "entries": trial.entry_count,
                "kept": trial.kept,
                "reused": trial.reused,
                **_verdict_record(trial.verdict),
            }
            for trial in run.trials
        ],
        "verification": None
        if verification is None
        else {
            "rounds": verification.rounds,
            "consistent": verification.consistent,
            "original": [_verdict_record(item) for item in verification.original],
            "minimal": [_verdict_record(item) for item in verification.minimal],
        },
    }

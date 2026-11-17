"""Entry-level minimization of one violating case, re-run check and a cause signature (#519).

Post-processing outside the exploration loop: the caller hands in a violating ``ArchiveCase``
(for example a saved violation step read from an exploration result folder with
:func:`inodefence.case_replay.load_request`) and an evaluator that runs one case and returns its
verdict. This module never runs anything itself and imports no product driver; the caller owns
execution isolation, the target binding (image, version, options) and where evidence is kept.

**The minimized input and its signature are never used as a seed or corpus entry of any
exploration, benchmark or comparison arm.** They are analysis output for people. Feeding them back
would plant a found violation into a search and contaminate any later measurement.

What it does (:func:`triage` runs the whole procedure; the parts are usable on their own):

1. **Measure the original** :attr:`TriagePolicy.baseline_runs` times (default n = 10). The target
   contract set is the most frequent non-empty set of violated contracts (C0/C1/C2) among the
   judged runs; the original's *rate* is the share of runs that showed exactly that set.
   Rate 1.0 → **deterministic** case. 0 < rate < 1 → **nondeterministic** case (W4 ruling
   2026-11-18). Rate 0 → nothing to minimize.
2. :func:`minimize_entries` — delta debugging (ddmin) over the entry list. A candidate keeps a
   subset of the entries in their original order; nothing inside an entry is changed (paths,
   targets, modes and contents stay as recorded; the finer text/mode reductions live in
   :mod:`inodefence.minimizer`). A run *hits* when the evaluator judged it and its violated
   contract set is exactly the target set (an extra or a missing contract is a different verdict;
   un-judged runs never hit). A candidate is **kept** when it gets at least
   ``keep_min_hits`` hits in ``runs_per_candidate`` runs:
   deterministic cases use 1-of-1 (the original rule); nondeterministic cases use
   :attr:`TriagePolicy.nondeterministic_keep` (default k = 1 of n = 5). Every run's verdict and each
   candidate's hit rate are recorded. Candidates the deterministic USTAR builder cannot encode are
   skipped without running. Within one minimization a case already evaluated is not run again;
   the earlier verdicts are reused and the trial is marked ``reused``.
3. **Check the minimum.** Deterministic cases: :func:`verify` re-runs the original and the
   minimum :attr:`TriagePolicy.verify_rounds` times each; every round must show the target set.
   Nondeterministic cases: the minimum is re-measured :attr:`TriagePolicy.final_runs` times
   (default n = 20) and its rate is reported beside the original's rate. 1-of-5 is a loose rule,
   so the minimum's rate can be far below the original's; the reader must see both. The result is
   labelled "nondeterministic target; minimization is for reference only".
4. :func:`cause_signature` — a first draft: the violated contracts plus, per remaining entry in
   order, its type and the *shape* of its link target (absolute, parent depth, plain relative,
   or pointing at another entry of the case). Paths, link target text, file names and any sentinel
   or protected-path name are not part of it.

All counts (n, k) are fixed in :class:`TriagePolicy` before any run and recorded in the result.

Limits: the minimum is 1-minimal with respect to removing entry subsets ddmin tries, not the
globally smallest input. Contract-set preservation keeps the declared verdict class, not a proven
root cause. A nondeterministic minimum only shows that the kept entries still *can* produce the
verdict. Nothing here is evidence about search performance.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Any

from inodefence.builder import build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType

CONTRACTS = ("C0", "C1", "C2")
TRIAGE_POLICY = "entry-ddmin-contract-set-v2"
SIGNATURE_SCHEMA = "inodefence-violation-signature-v1"
RECORD_SCHEMA = "inodefence-violation-triage-v2"
NONDETERMINISTIC_LABEL = "nondeterministic target; minimization is for reference only"


@dataclass(frozen=True, slots=True)
class TrialVerdict:
    """What the evaluator saw for one run: judged or not, and which contracts were violated.

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


@dataclass(frozen=True, slots=True)
class KeepRule:
    """Keep a candidate when at least ``min_hits`` of ``runs`` runs show the target set."""

    runs: int
    min_hits: int

    def __post_init__(self) -> None:
        if type(self.runs) is not int or self.runs <= 0:
            raise ValueError("runs must be a positive integer")
        if type(self.min_hits) is not int or not 1 <= self.min_hits <= self.runs:
            raise ValueError("min_hits must be in 1..runs")


DETERMINISTIC_KEEP = KeepRule(1, 1)


@dataclass(frozen=True, slots=True)
class TriagePolicy:
    """Counts fixed before any run (W4 ruling 2026-11-18 for the nondeterministic rule)."""

    baseline_runs: int = 10
    nondeterministic_keep: KeepRule = KeepRule(5, 1)
    final_runs: int = 20
    verify_rounds: int = 3
    execution_budget: int = 200

    def __post_init__(self) -> None:
        for name in ("baseline_runs", "final_runs", "verify_rounds", "execution_budget"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.nondeterministic_keep, KeepRule):
            raise ValueError("nondeterministic_keep must be a KeepRule")


class Termination(StrEnum):
    FIXED_POINT = "ddmin-1-minimal"
    BUDGET = "execution-budget-exhausted"
    SINGLE_ENTRY = "single-entry"


class Determinism(StrEnum):
    DETERMINISTIC = "deterministic"
    NONDETERMINISTIC = "nondeterministic"
    NOT_REPRODUCED = "not-reproduced"  # the original never showed a violation in the baseline


@dataclass(frozen=True, slots=True)
class Trial:
    index: int
    case_id: str
    entry_count: int
    verdicts: tuple[TrialVerdict, ...]
    hits: int
    kept: bool
    reused: bool

    @property
    def verdict(self) -> TrialVerdict:
        """The first run's verdict (1-of-1 trials have exactly one)."""
        return self.verdicts[0]


@dataclass(frozen=True, slots=True)
class MinimizationRun:
    policy_id: str
    execution_budget: int
    original: ArchiveCase
    minimal: ArchiveCase
    contracts: frozenset[str]
    keep: KeepRule
    trials: tuple[Trial, ...]
    termination: Termination

    @property
    def executions(self) -> int:
        """Evaluator calls actually made (reused verdicts are not executions)."""
        return sum(len(trial.verdicts) for trial in self.trials if not trial.reused)


def _hit(verdict: TrialVerdict, contracts: frozenset[str]) -> bool:
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


def _checked(verdict: object) -> TrialVerdict:
    if not isinstance(verdict, TrialVerdict):
        raise ValueError("evaluator must return a TrialVerdict")
    return verdict


def minimize_entries(
    case: ArchiveCase,
    evaluate: Evaluate,
    *,
    execution_budget: int,
    contracts: frozenset[str] | None = None,
    keep: KeepRule = DETERMINISTIC_KEEP,
) -> MinimizationRun:
    """ddmin over entries, keeping candidates that meet ``keep`` for the target contract set.

    With ``contracts`` ``None`` (the deterministic original rule) the original is run once first,
    must be a judged violation, and its contract set becomes the target. With ``contracts`` given
    (the caller already measured the original) the original is not run again. The budget counts
    executions (each run of each candidate; reused verdicts excluded). On exhaustion the smallest
    kept case so far is returned with ``Termination.BUDGET``.
    """
    if not isinstance(case, ArchiveCase) or not case.entries:
        raise ValueError("case must be a nonempty ArchiveCase")
    if type(execution_budget) is not int or execution_budget <= 0:
        raise ValueError("execution_budget must be a positive integer")
    if not isinstance(keep, KeepRule):
        raise ValueError("keep must be a KeepRule")
    if contracts is not None and (
        not isinstance(contracts, frozenset) or not contracts or not contracts <= set(CONTRACTS)
    ):
        raise ValueError(f"contracts must be a nonempty frozenset of {CONTRACTS}")
    build_tar(case)  # the original itself must be encodable
    trials: list[Trial] = []
    seen: dict[str, tuple[TrialVerdict, ...]] = {}

    def executions() -> int:
        return sum(len(trial.verdicts) for trial in trials if not trial.reused)

    if contracts is None:
        baseline = _checked(evaluate(case))
        if not baseline.judged or not baseline.violated:
            raise ValueError("the original case is not a judged violation under this evaluator")
        contracts = baseline.violated
        seen[case.case_id] = (baseline,)
        trials.append(Trial(0, case.case_id, len(case.entries), (baseline,), 1, True, False))
    target: frozenset[str] = contracts
    indices: tuple[int, ...] = tuple(range(len(case.entries)))

    def subset(kept_indices: Sequence[int]) -> ArchiveCase:
        return ArchiveCase(tuple(case.entries[index] for index in kept_indices))

    def finish(current: tuple[int, ...], termination: Termination) -> MinimizationRun:
        return MinimizationRun(
            TRIAGE_POLICY,
            execution_budget,
            case,
            subset(current),
            target,
            keep,
            tuple(trials),
            termination,
        )

    def test(candidate_indices: tuple[int, ...]) -> bool | None:
        """True/False = kept or not; None = budget would be exceeded before it could finish."""
        candidate = subset(candidate_indices)
        if not _encodable(candidate):
            return False
        reused = candidate.case_id in seen
        if not reused and executions() + keep.runs > execution_budget:
            return None
        if reused:
            verdicts = seen[candidate.case_id]
        else:
            verdicts = tuple(_checked(evaluate(candidate)) for _ in range(keep.runs))
            seen[candidate.case_id] = verdicts
        hits = sum(1 for verdict in verdicts if _hit(verdict, target))
        kept = hits >= keep.min_hits
        trials.append(
            Trial(
                len(trials),
                candidate.case_id,
                len(candidate.entries),
                verdicts,
                hits,
                kept,
                reused,
            )
        )
        return kept

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
class Measurement:
    """``runs`` fresh evaluations of one case against a target contract set."""

    case_id: str
    contracts: frozenset[str]
    verdicts: tuple[TrialVerdict, ...]

    @property
    def runs(self) -> int:
        return len(self.verdicts)

    @property
    def hits(self) -> int:
        """Runs showing exactly the target set; an empty target (no violation seen) has none."""
        if not self.contracts:
            return 0
        return sum(1 for verdict in self.verdicts if _hit(verdict, self.contracts))

    @property
    def rate(self) -> float:
        return self.hits / self.runs if self.runs else 0.0


def measure(
    case: ArchiveCase,
    evaluate: Evaluate,
    *,
    runs: int,
    contracts: frozenset[str] | None = None,
) -> Measurement:
    """Run ``case`` ``runs`` times. Without ``contracts`` the target is the most frequent
    non-empty violated set among judged runs (ties broken by sorted order; empty if none)."""
    if type(runs) is not int or runs <= 0:
        raise ValueError("runs must be a positive integer")
    verdicts = tuple(_checked(evaluate(case)) for _ in range(runs))
    if contracts is None:
        sets = Counter(v.violated for v in verdicts if v.judged and v.violated)
        if sets:
            best = max(sets.values())
            contracts = min(
                (s for s, count in sets.items() if count == best), key=lambda s: sorted(s)
            )
        else:
            contracts = frozenset()
    return Measurement(case.case_id, contracts, verdicts)


@dataclass(frozen=True, slots=True)
class Verification:
    rounds: int
    contracts: frozenset[str]
    original: tuple[TrialVerdict, ...]
    minimal: tuple[TrialVerdict, ...]

    @property
    def consistent(self) -> bool:
        """Every round of both cases was judged with exactly the expected contract set."""
        return all(_hit(verdict, self.contracts) for verdict in (*self.original, *self.minimal))


def verify(run: MinimizationRun, evaluate: Evaluate, *, rounds: int) -> Verification:
    """Re-run the original and the minimum ``rounds`` times each (fresh evaluations, no reuse)."""
    if type(rounds) is not int or rounds <= 0:
        raise ValueError("rounds must be a positive integer")
    original = tuple(_checked(evaluate(run.original)) for _ in range(rounds))
    minimal = tuple(_checked(evaluate(run.minimal)) for _ in range(rounds))
    return Verification(rounds, run.contracts, original, minimal)


@dataclass(frozen=True, slots=True)
class TriageOutcome:
    """The whole procedure's result; exactly one of ``verification`` / ``final`` is set when a
    minimization ran (deterministic → verification, nondeterministic → final measurement)."""

    policy: TriagePolicy
    determinism: Determinism
    baseline: Measurement
    run: MinimizationRun | None
    verification: Verification | None
    final: Measurement | None

    @property
    def consistent(self) -> bool | None:
        """Deterministic: re-run check result. Otherwise ``None`` (not a pass/fail notion)."""
        if self.determinism is Determinism.DETERMINISTIC and self.verification is not None:
            return self.verification.consistent
        return None


def triage(case: ArchiveCase, evaluate: Evaluate, policy: TriagePolicy) -> TriageOutcome:
    """Measure → classify → minimize under the class's keep rule → check the minimum."""
    if not isinstance(policy, TriagePolicy):
        raise ValueError("policy must be a TriagePolicy")
    baseline = measure(case, evaluate, runs=policy.baseline_runs)
    if baseline.hits == 0:
        return TriageOutcome(policy, Determinism.NOT_REPRODUCED, baseline, None, None, None)
    if baseline.hits == baseline.runs:
        run = minimize_entries(
            case,
            evaluate,
            execution_budget=policy.execution_budget,
            contracts=baseline.contracts,
            keep=DETERMINISTIC_KEEP,
        )
        verification = verify(run, evaluate, rounds=policy.verify_rounds)
        return TriageOutcome(policy, Determinism.DETERMINISTIC, baseline, run, verification, None)
    run = minimize_entries(
        case,
        evaluate,
        execution_budget=policy.execution_budget,
        contracts=baseline.contracts,
        keep=policy.nondeterministic_keep,
    )
    final = measure(run.minimal, evaluate, runs=policy.final_runs, contracts=baseline.contracts)
    return TriageOutcome(policy, Determinism.NONDETERMINISTIC, baseline, run, None, final)


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


def _measurement_record(item: Measurement) -> dict[str, Any]:
    return {
        "case_id": item.case_id,
        "contracts": sorted(item.contracts),
        "runs": item.runs,
        "hits": item.hits,
        "rate": item.rate,
        "verdicts": [_verdict_record(verdict) for verdict in item.verdicts],
    }


def triage_record(outcome: TriageOutcome, *, label: str) -> dict[str, Any]:
    """JSON-serializable record of one triage (no TAR bytes; case ids, sizes and rates only)."""
    policy = outcome.policy
    record: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "label": label,
        "policy_id": TRIAGE_POLICY,
        "use_restriction": (
            "analysis output only; never a seed or corpus entry of any exploration, benchmark "
            "or comparison arm"
        ),
        "counts": {
            "baseline_runs": policy.baseline_runs,
            "nondeterministic_keep": {
                "runs": policy.nondeterministic_keep.runs,
                "min_hits": policy.nondeterministic_keep.min_hits,
            },
            "final_runs": policy.final_runs,
            "verify_rounds": policy.verify_rounds,
            "execution_budget": policy.execution_budget,
        },
        "determinism": outcome.determinism.value,
        "reference_only": outcome.determinism is Determinism.NONDETERMINISTIC,
        "note": NONDETERMINISTIC_LABEL
        if outcome.determinism is Determinism.NONDETERMINISTIC
        else None,
        "baseline": _measurement_record(outcome.baseline),
        "minimization": None,
        "verification": None,
        "final": None,
    }
    run = outcome.run
    if run is not None:
        record["minimization"] = {
            "contracts": sorted(run.contracts),
            "keep": {"runs": run.keep.runs, "min_hits": run.keep.min_hits},
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
                    "runs": len(trial.verdicts),
                    "hits": trial.hits,
                    "rate": trial.hits / len(trial.verdicts),
                    "kept": trial.kept,
                    "reused": trial.reused,
                    "verdicts": [_verdict_record(verdict) for verdict in trial.verdicts],
                }
                for trial in run.trials
            ],
        }
    if outcome.verification is not None:
        verification = outcome.verification
        record["verification"] = {
            "rounds": verification.rounds,
            "consistent": verification.consistent,
            "original": [_verdict_record(item) for item in verification.original],
            "minimal": [_verdict_record(item) for item in verification.minimal],
        }
    if outcome.final is not None:
        record["final"] = _measurement_record(outcome.final)
    return record

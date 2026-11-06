"""Side-by-side throughput + parity of two execution methods (EXP-0 measurement 4).

Pure analysis: given the per-campaign timings and per-cell parity subjects that two
execution methods produced for the *same* matrix -- the per-case fresh-container
path and the persistent worker pool -- this builds the comparison the surgery plan's
EXP-0 asks for (throughput of both methods, read next to each other) and folds in the
G1 parity verdict per cell. It never runs a target, never touches Docker, and never
times anything itself; the methods measure their own wall-clock and hand the numbers
here. The script ``scripts/measure_worker_pool_throughput.py`` drives the methods and
feeds their output into these functions.
"""

from dataclasses import dataclass

from inodefence.evaluation.execution_parity import ParityReport, ParitySubject, compare_subjects


@dataclass(frozen=True, slots=True)
class CampaignTiming:
    """One campaign cell's measured cost under one execution method."""

    run_id: str
    seed: int
    arm: str
    version: str | None
    wall_seconds: float
    cases: int
    aborts: int
    retries: int

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("campaign timing requires a run id")
        if type(self.seed) is not int:
            raise ValueError("campaign timing seed must be an integer")
        if not isinstance(self.arm, str) or not self.arm:
            raise ValueError("campaign timing requires an arm label")
        if self.version is not None and (not isinstance(self.version, str) or not self.version):
            raise ValueError("campaign timing version is a nonempty string or None")
        if type(self.wall_seconds) not in (int, float) or self.wall_seconds < 0:
            raise ValueError("campaign wall seconds must be nonnegative")
        for name in ("cases", "aborts", "retries"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class MethodMeasurement:
    """One execution method's measured run of the whole matrix.

    ``wall_seconds_total`` is the end-to-end wall clock of running every campaign
    with this method (campaigns may run concurrently, so it is measured, not summed).
    ``startup_seconds`` is the one-time cost the method pays before cases run -- image
    build for the per-case path, worker pre-start for the pool -- and is included in
    ``wall_seconds_total``. It is reported on its own so the pool's amortized pre-start
    can be read against the per-case path's per-run image reuse.
    """

    method: str
    startup_seconds: float
    wall_seconds_total: float
    campaigns: tuple[CampaignTiming, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.method, str) or not self.method:
            raise ValueError("method measurement requires a method label")
        for name in ("startup_seconds", "wall_seconds_total"):
            value = getattr(self, name)
            if type(value) not in (int, float) or value < 0:
                raise ValueError(f"{name} must be nonnegative")
        if not isinstance(self.campaigns, tuple) or not all(
            isinstance(item, CampaignTiming) for item in self.campaigns
        ):
            raise ValueError("method measurement requires CampaignTiming records")

    @property
    def total_cases(self) -> int:
        return sum(campaign.cases for campaign in self.campaigns)

    @property
    def total_aborts(self) -> int:
        return sum(campaign.aborts for campaign in self.campaigns)

    @property
    def total_retries(self) -> int:
        return sum(campaign.retries for campaign in self.campaigns)

    @property
    def campaign_wall_sum(self) -> float:
        """Summed per-campaign wall; over ``wall_seconds_total`` this shows concurrency."""
        return sum(campaign.wall_seconds for campaign in self.campaigns)

    @property
    def cases_per_second(self) -> float:
        """End-to-end throughput, the headline number EXP-0 compares between methods."""
        if self.wall_seconds_total <= 0:
            return 0.0
        return self.total_cases / self.wall_seconds_total


@dataclass(frozen=True, slots=True)
class CellParity:
    """One cell's G1 parity verdict between the two methods' evidence for that cell."""

    run_id: str
    report: ParityReport

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("cell parity requires a run id")
        if not isinstance(self.report, ParityReport):
            raise ValueError("cell parity requires a ParityReport")


@dataclass(frozen=True, slots=True)
class ThroughputComparison:
    """Both methods read next to each other, plus the per-cell parity verdicts."""

    per_case: MethodMeasurement
    worker_pool: MethodMeasurement
    cells: tuple[CellParity, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.per_case, MethodMeasurement) or not isinstance(
            self.worker_pool, MethodMeasurement
        ):
            raise ValueError("comparison requires two MethodMeasurement records")
        if not isinstance(self.cells, tuple) or not all(
            isinstance(item, CellParity) for item in self.cells
        ):
            raise ValueError("comparison requires CellParity records")

    @property
    def speedup(self) -> float:
        """How many times faster the worker pool finished the matrix (>1 is faster)."""
        if self.worker_pool.wall_seconds_total <= 0:
            return 0.0
        return self.per_case.wall_seconds_total / self.worker_pool.wall_seconds_total

    @property
    def parity_passed(self) -> bool:
        """Every cell agreed on all four dimensions (retried steps stayed transparent)."""
        return bool(self.cells) and all(cell.report.passed for cell in self.cells)


def build_comparison(
    per_case: MethodMeasurement,
    worker_pool: MethodMeasurement,
    baseline_subjects: dict[str, ParitySubject],
    worker_pool_subjects: dict[str, ParitySubject],
) -> ThroughputComparison:
    """Pair the two methods' per-cell subjects by run id and compare each.

    Only cells both methods produced a subject for are compared; a run id present
    in one method only is left out of the parity table (the timing side still
    reports it). Comparison direction is baseline (per-case) vs candidate (pool).
    """
    shared = sorted(set(baseline_subjects) & set(worker_pool_subjects))
    cells = tuple(
        CellParity(
            run_id, compare_subjects(baseline_subjects[run_id], worker_pool_subjects[run_id])
        )
        for run_id in shared
    )
    return ThroughputComparison(per_case, worker_pool, cells)


def _method_report(measurement: MethodMeasurement) -> dict[str, object]:
    return {
        "method": measurement.method,
        "startup_seconds": round(measurement.startup_seconds, 3),
        "wall_seconds_total": round(measurement.wall_seconds_total, 3),
        "campaign_wall_sum": round(measurement.campaign_wall_sum, 3),
        "total_cases": measurement.total_cases,
        "total_aborts": measurement.total_aborts,
        "total_retries": measurement.total_retries,
        "cases_per_second": round(measurement.cases_per_second, 4),
        "campaigns": [
            {
                "run_id": campaign.run_id,
                "seed": campaign.seed,
                "arm": campaign.arm,
                "version": campaign.version,
                "wall_seconds": round(campaign.wall_seconds, 3),
                "cases": campaign.cases,
                "aborts": campaign.aborts,
                "retries": campaign.retries,
            }
            for campaign in measurement.campaigns
        ],
    }


def render_report(comparison: ThroughputComparison) -> dict[str, object]:
    """A JSON-able side-by-side report: both methods, the speedup, the parity table."""
    return {
        "schema": "worker-pool-throughput-parity-v1",
        "summary": {
            "speedup": round(comparison.speedup, 3),
            "parity_passed": comparison.parity_passed,
            "cells_compared": len(comparison.cells),
        },
        "per_case": _method_report(comparison.per_case),
        "worker_pool": _method_report(comparison.worker_pool),
        "parity": [
            {
                "run_id": cell.run_id,
                "passed": cell.report.passed,
                "both_retry_free": cell.report.both_retry_free,
                "failing_dimensions": [
                    dimension.name for dimension in cell.report.dimensions if not dimension.agree
                ],
                "retried_steps": [
                    {
                        "index": verdict.index,
                        "candidate_retries": verdict.candidate_retries,
                        "matches_retry_free": verdict.matches_retry_free,
                    }
                    for verdict in cell.report.retried_steps
                ],
            }
            for cell in comparison.cells
        ],
    }

"""Analysis of the exploratory hazard pilot (``exp3-hazard-pilot-v1``), fixed before it runs.

Exploratory, not a test: it states per-arm event counts with binomial intervals and applies the
design's decision rules mechanically. It never claims confirmatory power, never reads an upper
bound as "hazard = 0", and never selects an R variant by its event count (the higher of the two
is used, the conservative choice for S-u).

Two scales, kept apart. The reported event share and two-sided interval count every planned cell
(an aborted or unrecorded campaign is never replaced or dropped). The decision rules use the
exposure actually run, so a cell that ran less bounds the hazard less tightly, and an abort
enters the planning once, in the required-n projection, and not again through the estimate.

The power model matches the planning model the review used: constant per-execution hazard,
seed blocks, block-winner exact sign test, both Holm contrasts rejected at family alpha .05 with
S-u faster. It approximates the registered permutation log-rank; it is a planning input.

    python -m scripts.analyze_hazard_pilot --design <file> --raw <dir> --out <dir>
    python -m scripts.analyze_hazard_pilot --sensitivity-only     # the design's a-priori table
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.run_g1_smoke import cell_paths
from scripts.run_hazard_pilot import PilotDesign, has_record, load_design, planned_cells
from scripts.run_parallel_native import Cell

from inodefence.evaluation.rds import RdsCellConfig
from inodefence.evaluation.rds_report import (
    LoadedCell,
    ReportFormatError,
    check_report_config,
    load_cell_files,
    summarize_report_records,
    timing_record,
)

BUDGET = 2000
FAMILY_ALPHA = 0.05
TARGET_POWER = 0.8
ABORTED_EXPOSURE = 0.5
SIMS = 4000
N_MAX = 1000
SIM_SEED = 20261106
#: Host-days of one host from the freeze to G2 (11/18~11/26) and the shorter planned windows.
WINDOWS_HOST_DAYS = (2, 5, 8)
DECISION_WINDOW_HOST_DAYS = 8
CONFIRMATORY_ARMS = 3
R_ARMS = ("R-walk", "R-restart")
ZERO_RULE_ARMS = ("R-walk", "R-restart", "D")
SENSITIVITY_P_S = (0.059, 0.117, 0.145, 0.259, 0.418)
SENSITIVITY_P_FLOOR = (0.0, 0.02, 0.05, 0.10)
NOT_A_CLAIM = (
    "exploratory planning input: not a confirmatory result, no claim of confirmatory power, "
    "not pooled with EXP-0/EXP-2/EXP-3, zero events never mean hazard = 0"
)
VERDICT_LABELS = {
    "possible": "가능",
    "reduced": "축소안",
    "undetermined": "미결(증거 부족)",
    "impossible": "불가",
}
UPPER_N_NOTE = (
    "required_n_s_upper95 is the best-case lower bound, never a planned EXP-2 n; "
    "power at that n is not assured"
)
#: What a malformed record can raise while it is read or summarized.
UNREADABLE_ERRORS = (ValueError, KeyError, TypeError, AttributeError, OSError)


# ---- binomial intervals ---------------------------------------------------------------------


def _binomial_tail_at_least(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    return sum(math.comb(n, x) * p**x * (1 - p) ** (n - x) for x in range(k, n + 1))


def _solve_increasing(function: Any, target: float, upper_limit: float = 1.0) -> float:
    low, high = 0.0, upper_limit
    for _ in range(80):
        middle = (low + high) / 2
        if function(middle) < target:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Exact two-sided interval for a binomial proportion."""
    tail = (1 - confidence) / 2
    lower = 0.0 if k == 0 else _solve_increasing(lambda p: _binomial_tail_at_least(k, n, p), tail)
    upper = (
        1.0
        if k == n
        else _solve_increasing(lambda p: _binomial_tail_at_least(k + 1, n, p), 1 - tail)
    )
    return lower, upper


def one_sided_upper(k: int, n: int, confidence: float = 0.95) -> float:
    """Exact one-sided upper bound; with k = 0 this is 1 - (1 - confidence) ** (1 / n)."""
    if k >= n:
        return 1.0
    return _solve_increasing(lambda p: _binomial_tail_at_least(k + 1, n, p), confidence)


# ---- estimates on the exposure actually run ------------------------------------------------


def _poisson_upper_mean(events: int, confidence: float) -> float:
    """Exact one-sided upper bound on a Poisson mean, given the observed count."""

    def at_least_one_more(mean: float) -> float:
        below = sum(mean**x / math.factorial(x) for x in range(events + 1))
        return 1 - math.exp(-mean) * below

    limit = float(events + 4)
    while at_least_one_more(limit) < confidence:
        limit *= 2
    return _solve_increasing(at_least_one_more, confidence, limit)


def exposure_point(events: int, at_risk: int, budget: int) -> float | None:
    """Per-campaign event probability on exposure: 1 - exp(-budget * events / at_risk).

    Constant per-execution hazard, as the power model assumes: a right-censored cell counts only
    the executions it ran. None when nothing ran.
    """
    if at_risk <= 0:
        return None
    return -math.expm1(-budget * events / at_risk) if events else 0.0


def exposure_upper(events: int, at_risk: int, budget: int, confidence: float = 0.95) -> float:
    """One-sided upper bound of that probability; 1.0 when nothing ran.

    With no events this is 1 - (1 - confidence) ** (budget / at_risk), the exact binomial bound
    for at_risk / budget campaigns: ten full campaigns give .259, seven give .348.
    """
    if at_risk <= 0:
        return 1.0
    return -math.expm1(-_poisson_upper_mean(events, confidence) * budget / at_risk)


# ---- power model ----------------------------------------------------------------------------


_SIGN_P: dict[tuple[int, int], float] = {}


def sign_p(wins: int, total: int) -> float:
    """Exact two-sided sign-test p value."""
    high = max(wins, total - wins)
    key = (high, total)
    if key not in _SIGN_P:
        tail = sum(math.comb(total, x) for x in range(high, total + 1)) / 2.0**total
        _SIGN_P[key] = min(1.0, 2 * tail)
    return _SIGN_P[key]


def _rate(p: float) -> float:
    if p <= 0:
        return 0.0
    if p >= 1:
        return math.inf
    return -math.log(1 - p) / BUDGET


def _event_time(rng: random.Random, rate: float, abort: float) -> float:
    if rate <= 0:
        return math.inf
    exposure = BUDGET * ABORTED_EXPOSURE if abort > 0 and rng.random() < abort else BUDGET
    time = rng.expovariate(rate)
    return time if time <= exposure else math.inf


def scenario_power(
    n: int,
    p_s: float,
    p_r: float,
    p_d: float,
    *,
    abort: float = 0.0,
    sims: int = SIMS,
    seed: int = SIM_SEED,
) -> float:
    """P(both Holm contrasts reject with S-u faster) at family alpha .05."""
    rng = random.Random(seed)
    rate_s, rate_r, rate_d = _rate(p_s), _rate(p_r), _rate(p_d)
    joint = 0
    for _ in range(sims):
        s_vs_r = r_vs_s = s_vs_d = d_vs_s = 0
        for _block in range(n):
            time_s = _event_time(rng, rate_s, abort)
            time_r = _event_time(rng, rate_r, abort)
            time_d = _event_time(rng, rate_d, abort)
            if time_s < time_r:
                s_vs_r += 1
            elif time_r < time_s:
                r_vs_s += 1
            if time_s < time_d:
                s_vs_d += 1
            elif time_d < time_s:
                d_vs_s += 1
        if s_vs_r <= r_vs_s or s_vs_d <= d_vs_s:
            continue
        low, high = sorted((sign_p(s_vs_r, s_vs_r + r_vs_s), sign_p(s_vs_d, s_vs_d + d_vs_s)))
        if 2 * low <= FAMILY_ALPHA and high <= FAMILY_ALPHA:
            joint += 1
    return joint / sims


def required_n(
    p_s: float,
    p_r: float,
    p_d: float,
    *,
    abort: float = 0.0,
    sims: int = SIMS,
    n_max: int = N_MAX,
) -> int | None:
    """Smallest n/arm reaching the target power, or None when above ``n_max``/untestable."""
    if p_s <= max(p_r, p_d):
        return None

    def power(n: int) -> float:
        return scenario_power(n, p_s, p_r, p_d, abort=abort, sims=sims)

    high = 8
    while power(high) < TARGET_POWER:
        if high >= n_max:
            return None
        high = min(high * 2, n_max)
    low = high // 2
    while high - low > max(1, high // 50):
        middle = (low + high) // 2
        if power(middle) >= TARGET_POWER:
            high = middle
        else:
            low = middle
    return high


def sensitivity_rows(*, sims: int = SIMS) -> list[dict[str, Any]]:
    """Required n/arm over assumed S-u and R = D hazards; the same table for any outcome."""
    rows = []
    for p_s in SENSITIVITY_P_S:
        for floor in SENSITIVITY_P_FLOOR:
            if floor < p_s:
                rows.append(
                    {
                        "p_s": p_s,
                        "p_r_eq_p_d": floor,
                        "required_n_per_arm": required_n(p_s, floor, floor, sims=sims),
                    }
                )
    return rows


# ---- cell outcomes --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CellOutcome:
    run_id: str
    arm: str
    seed: int
    state: str  # complete | abort | no-record | unreadable | invalid
    reason: str | None
    executions: int
    event: bool
    t_first: int
    first_c0: int | None
    first_c1: int | None
    first_c2: int | None
    hit_steps: int
    rejected: int
    mutations: int
    mutation_successes: int
    seed_parent_mutations: int
    mean_entries: float | None
    invalid_trace_steps: int
    boundary_attempt_keys: int
    retained_cases: int
    unique_effect_keys: int
    u_viol: int
    vocabulary: tuple[str, ...]
    p50_seconds: float | None
    p95_seconds: float | None


def _no_outcome(cell: Cell, state: str, reason: str | None) -> CellOutcome:
    return CellOutcome(
        cell.run_id,
        cell.arm.label,
        cell.seed,
        state,
        reason,
        0,
        False,
        0,
        None,
        None,
        None,
        0,
        0,
        0,
        0,
        0,
        None,
        0,
        0,
        0,
        0,
        0,
        (),
        None,
        None,
    )


def _conformance_problem(report: Mapping[str, Any], design: PilotDesign) -> str | None:
    if report.get("image_id") != design.image_digest:
        return f"report image_id {report.get('image_id')!r} != {design.image_digest}"
    recorded = report.get("sentinel_set")
    if not isinstance(recorded, Mapping):
        return "report records no sentinel_set"
    expected = (
        ("generator_id", design.sentinel_generator_id),
        ("generator_seed", design.sentinel_generator_seed),
        ("count", design.sentinel_count),
    )
    for key, value in expected:
        if recorded.get(key) != value:
            return f"report sentinel_set.{key} {recorded.get(key)!r} != {value!r}"
    return None


def _step_metrics(
    records: Sequence[Mapping[str, Any]], initial: frozenset[str]
) -> tuple[int, int, int, float | None, int]:
    mutations = successes = seed_parents = invalid = 0
    entries: list[int] = []
    for record in records:
        feedback = record.get("feedback")
        feedback = feedback if isinstance(feedback, Mapping) else {}
        trace = record.get("trace")
        trace = trace if isinstance(trace, Mapping) else {}
        recorded_entries = trace.get("entries")
        if isinstance(recorded_entries, list):
            entries.append(len(recorded_entries))
        if trace.get("observation_failures") or feedback.get("trace_completeness") == "invalid":
            invalid += 1
        if record.get("origin") == "mutation":
            mutations += 1
            successes += feedback.get("trace_termination") == "success"
            seed_parents += record.get("parent_case_id") in initial
    return (
        mutations,
        successes,
        seed_parents,
        statistics.mean(entries) if entries else None,
        invalid,
    )


def load_outcome(cell: Cell, raw: Path, design: PilotDesign) -> CellOutcome:
    """One cell's outcome, keeping apart the states the design treats differently.

    invalid: the report states a config, image or sentinel set other than the design's; the cell
    was not the planned one and leaves the denominator. unreadable: the record exists but cannot
    be parsed; the planned cell stays in the denominator with zero exposure and its own reason.
    """
    paths = cell_paths(cell, raw)
    if not has_record(cell, raw):
        return _no_outcome(cell, "no-record", "no report and no nonempty steps file")
    config = design.cell_config(cell)
    try:
        loaded = load_cell_files(paths["report"], paths["steps_jsonl"])
    except UNREADABLE_ERRORS as error:
        return _no_outcome(cell, "unreadable", f"{type(error).__name__}: {error}")
    if loaded.report is not None and "aborted" not in loaded.report:
        try:
            check_report_config(loaded.report, config)
        except ReportFormatError as error:
            return _no_outcome(cell, "invalid", str(error))
        problem = _conformance_problem(loaded.report, design)
        if problem is not None:
            return _no_outcome(cell, "invalid", problem)
    try:
        return _outcome_from_records(cell, loaded, config, design)
    except UNREADABLE_ERRORS as error:
        return _no_outcome(cell, "unreadable", f"{type(error).__name__}: {error}")


def _outcome_from_records(
    cell: Cell, loaded: LoadedCell, config: RdsCellConfig, design: PilotDesign
) -> CellOutcome:
    aborted_at, reason = loaded.aborted_at_step, loaded.abort_reason
    if aborted_at is None and len(loaded.records) < config.execution_budget:
        aborted_at = len(loaded.records)
        reason = "report has fewer steps than the budget and no abort record"
    summary = summarize_report_records(
        loaded.records, config, aborted_at_step=aborted_at, abort_reason=reason
    ).summary
    report = loaded.report or {}
    initial = report.get("initial_case_ids")
    initial_ids = frozenset(initial) if isinstance(initial, list) else frozenset()
    mutations, successes, seed_parents, mean_entries, invalid = _step_metrics(
        loaded.records, initial_ids
    )
    timing = timing_record(loaded.report, design.execution_mode)
    return CellOutcome(
        cell.run_id,
        cell.arm.label,
        cell.seed,
        "complete" if summary.complete else "abort",
        summary.abort_reason,
        summary.executions_completed,
        bool(summary.hit),
        summary.t_first,
        summary.first_c0,
        summary.first_c1,
        summary.first_c2,
        summary.hit_steps,
        summary.rejected_executions,
        mutations,
        successes,
        seed_parents,
        mean_entries,
        invalid,
        summary.boundary_attempt_keys,
        summary.retained_cases,
        summary.unique_effect_keys,
        summary.u_viol,
        tuple(summary.vocabulary_pool_final),
        timing["full_step_seconds_p50"],
        timing["full_step_seconds_p95"],
    )


# ---- arm summaries and the design's decision rules ------------------------------------------


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _reasons(cells: Sequence[CellOutcome], *states: str) -> list[str]:
    return sorted(
        {str(cell.reason)[:160] for cell in cells if cell.state in states and cell.reason}
    )


def summarize_arm(
    arm: str, cells: Sequence[CellOutcome], *, budget: int = BUDGET
) -> dict[str, Any]:
    """Report events over all planned, non-invalid cells; decide on the exposure they ran.

    ``p_hat``, ``ci95_two_sided`` and ``upper95_one_sided`` count every such cell as a campaign.
    ``p_hat_exposure`` and ``upper95_exposure`` are what the decision rules read.
    """
    denominator = [cell for cell in cells if cell.state != "invalid"]
    n = len(denominator)
    events = [cell for cell in denominator if cell.event]
    at_risk = sum(cell.t_first if cell.event else cell.executions for cell in denominator)
    low, high = clopper_pearson(len(events), n) if n else (0.0, 1.0)
    executions = sum(cell.executions for cell in denominator)
    return {
        "arm": arm,
        "campaigns": len(cells),
        "denominator": n,
        "complete": sum(cell.state == "complete" for cell in cells),
        "abort": sum(cell.state == "abort" for cell in cells),
        "no_record": sum(cell.state == "no-record" for cell in cells),
        "unreadable": sum(cell.state == "unreadable" for cell in cells),
        "invalid": sum(cell.state == "invalid" for cell in cells),
        "abort_reasons": _reasons(cells, "abort", "no-record"),
        "unreadable_reasons": _reasons(cells, "unreadable"),
        "invalid_reasons": _reasons(cells, "invalid"),
        "events_first_c1_or_c2": len(events),
        "campaigns_with_c1": sum(cell.first_c1 is not None for cell in denominator),
        "campaigns_with_c2": sum(cell.first_c2 is not None for cell in denominator),
        "campaigns_with_c0": sum(cell.first_c0 is not None for cell in denominator),
        "hit_steps": sum(cell.hit_steps for cell in denominator),
        "t_first_observed": sorted(cell.t_first for cell in events),
        "p_hat": len(events) / n if n else None,
        "ci95_two_sided": [low, high],
        "upper95_one_sided": one_sided_upper(len(events), n) if n else 1.0,
        "at_risk_executions": at_risk,
        "exposure_campaigns": at_risk / budget,
        "p_hat_exposure": exposure_point(len(events), at_risk, budget),
        "upper95_exposure": exposure_upper(len(events), at_risk, budget),
        "events_per_execution_at_risk": _ratio(len(events), at_risk),
        "u_viol_total": sum(cell.u_viol for cell in denominator),
        "non_event_metrics": {
            "rejected_ratio": _ratio(sum(cell.rejected for cell in denominator), executions),
            "mutation_success_rate": _ratio(
                sum(cell.mutation_successes for cell in denominator),
                sum(cell.mutations for cell in denominator),
            ),
            "seed_parent_ratio": _ratio(
                sum(cell.seed_parent_mutations for cell in denominator),
                sum(cell.mutations for cell in denominator),
            ),
            "mean_entries": (
                statistics.mean(
                    cell.mean_entries for cell in denominator if cell.mean_entries is not None
                )
                if any(cell.mean_entries is not None for cell in denominator)
                else None
            ),
            "boundary_attempt_keys_cell_sum": sum(
                cell.boundary_attempt_keys for cell in denominator
            ),
            "retained_cases_cell_sum": sum(cell.retained_cases for cell in denominator),
            "invalid_trace_steps": sum(cell.invalid_trace_steps for cell in denominator),
        },
    }


def rule_condition_4(arms: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Any R or D first event discards the R = D = 0 assumption; zero events never confirm it."""
    counts = {arm: arms[arm]["events_first_c1_or_c2"] for arm in ZERO_RULE_ARMS}
    triggered = any(count >= 1 for count in counts.values())
    return {
        "events": counts,
        "unreadable_cells": {arm: arms[arm]["unreadable"] for arm in ZERO_RULE_ARMS},
        "r_d_zero_assumption": "discarded" if triggered else "not discarded (not confirmed)",
        "recalculate_power": triggered,
    }


def rule_condition_5(arms: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Zero-event arms get the bound on the exposure they ran, wider when cells ran less."""
    zero = {
        arm: summary["upper95_exposure"]
        for arm, summary in arms.items()
        if summary["events_first_c1_or_c2"] == 0
    }
    return {
        "arms_with_zero_events": zero,
        "statement": "zero events bound the hazard from above; they do not show hazard = 0",
    }


def planning_inputs(arms: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    """Exposure-based estimates and the S-u upper bound; R is the higher of the two variants."""
    return {
        "p_s_point": arms["S-u"]["p_hat_exposure"] or 0.0,
        "p_s_upper95": arms["S-u"]["upper95_exposure"],
        "p_r_point_higher_variant": max(arms[arm]["p_hat_exposure"] or 0.0 for arm in R_ARMS),
        "p_d_point": arms["D"]["p_hat_exposure"] or 0.0,
        "events_s": arms["S-u"]["events_first_c1_or_c2"],
        "events_r_d_max": max(arms[arm]["events_first_c1_or_c2"] for arm in ZERO_RULE_ARMS),
    }


def s_u_leads(inputs: Mapping[str, float]) -> bool:
    """More S-u events than any R variant or D, and a higher estimate on exposure.

    The count comes first: with equal counts the estimates differ only by when the events fell,
    and a single event's timing must not decide the label.
    """
    return inputs["events_s"] > inputs["events_r_d_max"] and inputs["p_s_point"] > max(
        inputs["p_r_point_higher_variant"], inputs["p_d_point"]
    )


def n_capacity(campaigns_per_host_day: float, host_days: int) -> int:
    return math.floor(campaigns_per_host_day * host_days / CONFIRMATORY_ARMS)


def feasibility(
    inputs: Mapping[str, float], *, abort: float, campaigns_per_host_day: float, sims: int = SIMS
) -> dict[str, Any]:
    """Condition 6 label, by the design's fixed rule, on the decision window.

    possible: S-u leads (``s_u_leads``) and the point-estimate n fits. reduced: S-u leads, its
    point-estimate n does not fit, but the n at its upper bound does (power not assured).
    undetermined: S-u does not lead, which includes zero S-u events and tied event counts, but the
    upper bound still fits, so this sample cannot tell. impossible: even the upper bound does not
    fit, or does not separate.

    ``abort`` enters here once, in the projection; the inputs are already on exposure.
    """
    point_n = required_n(
        inputs["p_s_point"],
        inputs["p_r_point_higher_variant"],
        inputs["p_d_point"],
        abort=abort,
        sims=sims,
    )
    optimistic_n = required_n(
        inputs["p_s_upper95"],
        inputs["p_r_point_higher_variant"],
        inputs["p_d_point"],
        abort=abort,
        sims=sims,
    )
    capacity = {str(days): n_capacity(campaigns_per_host_day, days) for days in WINDOWS_HOST_DAYS}
    decision_capacity = capacity[str(DECISION_WINDOW_HOST_DAYS)]
    s_leads = s_u_leads(inputs)
    if s_leads and point_n is not None and point_n <= decision_capacity:
        verdict = "possible"
    elif optimistic_n is None or optimistic_n > decision_capacity:
        verdict = "impossible"
    elif s_leads:
        verdict = "reduced"
    else:
        verdict = "undetermined"
    return {
        "verdict": verdict,
        "verdict_label": VERDICT_LABELS[verdict],
        "s_u_leads": s_leads,
        "required_n_point": point_n,
        "required_n_s_upper95": optimistic_n,
        "required_n_s_upper95_note": UPPER_N_NOTE,
        "abort_fraction_used": abort,
        "campaigns_per_host_day": campaigns_per_host_day,
        "n_capacity_by_host_days": capacity,
        "decision_window_host_days": DECISION_WINDOW_HOST_DAYS,
        "assumption": "holdout hazard equals train 7.5.2 hazard (unverified; holdout not touched)",
        "note": NOT_A_CLAIM,
    }


def vocabulary_equal(cells: Sequence[CellOutcome]) -> bool:
    """Per seed, every arm's final token pool is the same nonempty set."""
    by_seed: dict[int, set[tuple[str, ...]]] = {}
    for cell in cells:
        if cell.state == "complete":
            by_seed.setdefault(cell.seed, set()).add(tuple(sorted(cell.vocabulary)))
    return bool(by_seed) and all(
        len(pools) == 1 and bool(next(iter(pools))) for pools in by_seed.values()
    )


def clock_summary(raw: Path, executions: int, budget: int) -> dict[str, Any]:
    """Real-time throughput from the driver's stamps; ``executions`` counts aborted cells' steps."""
    path = raw / "clocks.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    finished = [record for record in records if record["record_present"]]
    real = [r["ended"]["realtime"] - r["started"]["realtime"] for r in finished]
    mono = [r["ended"]["monotonic"] - r["started"]["monotonic"] for r in finished]
    rawc = [r["ended"]["monotonic_raw"] - r["started"]["monotonic_raw"] for r in finished]
    elapsed = max(r["ended"]["realtime"] for r in records) - min(
        r["started"]["realtime"] for r in records
    )
    exec_per_hour = executions / elapsed * 3600
    factors = [m / r for m, r in zip(mono, real, strict=True)]
    return {
        "elapsed_real_seconds": elapsed,
        "exec_per_hour_real": exec_per_hour,
        "campaigns_per_host_day_real": exec_per_hour * 24 / budget,
        "monotonic_over_real_pooled": sum(mono) / sum(real),
        "monotonic_over_real_min": min(factors),
        "monotonic_over_real_max": max(factors),
        "real_over_raw_pooled": sum(real) / sum(rawc),
        "mean_campaign_real_seconds": statistics.mean(real),
    }


def incomplete_attempts(raw: Path, cells: Sequence[CellOutcome]) -> dict[str, list[dict[str, Any]]]:
    """Exit code and wall time of each attempt of an unfinished cell; a watchdog kill shows here."""
    path = raw / "clocks.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    incomplete = {cell.run_id for cell in cells if cell.state != "complete"}
    attempts: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record["run_id"] in incomplete:
            attempts.setdefault(record["run_id"], []).append(
                {
                    "attempt": record["attempt"],
                    "returncode": record["returncode"],
                    "launcher_wall_seconds": record["launcher_wall_seconds"],
                    "record_present": record["record_present"],
                }
            )
    return attempts


def analyze(raw: Path, design: PilotDesign, *, sims: int = SIMS) -> dict[str, Any]:
    outcomes = [load_outcome(cell, raw, design) for cell in planned_cells(design)]
    arms = {
        arm.label: summarize_arm(
            arm.label, [cell for cell in outcomes if cell.arm == arm.label], budget=design.budget
        )
        for arm in design.arms
    }
    clocks = clock_summary(raw, sum(cell.executions for cell in outcomes), design.budget)
    usable = [cell for cell in outcomes if cell.state != "invalid"]
    abort_fraction = sum(cell.state != "complete" for cell in usable) / len(usable)
    inputs = planning_inputs(arms)
    return {
        "design_id": design.design_id,
        "design_sha256": design.sha256,
        "classification": NOT_A_CLAIM,
        "k": design.sentinel_count,
        "arms": arms,
        "vocabulary_equal_across_arms": vocabulary_equal(outcomes),
        "condition_4": rule_condition_4(arms),
        "condition_5": rule_condition_5(arms),
        "planning_inputs": inputs,
        "condition_6": feasibility(
            inputs,
            abort=abort_fraction,
            campaigns_per_host_day=clocks["campaigns_per_host_day_real"],
            sims=sims,
        ),
        "sensitivity": sensitivity_rows(sims=sims),
        "clocks": clocks,
        "incomplete_cell_attempts": incomplete_attempts(raw, outcomes),
        "cells": [asdict(cell) for cell in outcomes],
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# 위험도 파일럿 결과 ({report['design_id']}, k={report['k']})",
        "",
        f"_{report['classification']}_",
        "",
        "| arm | 캠페인 | 완주 | abort | 기록 없음 | 읽기 불가 | 무효 | 첫 C1∨C2 사건 | "
        "95% CI (양측, 계획 분모) | 노출 (캠페인분) | p̂ (노출) | 95% 상한 (단측, 노출, 규칙 B) | "
        "T_first 관측 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for arm in report["arms"].values():
        low, high = arm["ci95_two_sided"]
        point = arm["p_hat_exposure"]
        lines.append(
            f"| {arm['arm']} | {arm['campaigns']} | {arm['complete']} | {arm['abort']} | "
            f"{arm['no_record']} | {arm['unreadable']} | {arm['invalid']} | "
            f"{arm['events_first_c1_or_c2']} | {low:.3f}–{high:.3f} | "
            f"{arm['exposure_campaigns']:.2f} | "
            f"{'-' if point is None else format(point, '.3f')} | "
            f"{arm['upper95_exposure']:.3f} | {arm['t_first_observed']} |"
        )
    condition_4, condition_6 = report["condition_4"], report["condition_6"]
    clocks = report["clocks"]
    lines += [
        "",
        f"- 조건 4: `R=D=0` 가정 = **{condition_4['r_d_zero_assumption']}** "
        f"(사건 {condition_4['events']}, 사건 여부를 알 수 없는 읽기 불가 셀 "
        f"{condition_4['unreadable_cells']})",
        f"- 조건 5: {report['condition_5']['statement']}",
        f"- 조건 6: **{condition_6['verdict_label']}** "
        f"(점추정 n/arm {condition_6['required_n_point']}, "
        f"S-u 상한 n/arm {condition_6['required_n_s_upper95']} (계획 n이 아니라 최선 가정의 하한), "
        f"미완주 비율 {condition_6['abort_fraction_used']:.3f}, "
        f"용량 {condition_6['n_capacity_by_host_days']}, 가정: {condition_6['assumption']})",
        f"- 미완주 셀 시도 기록(종료 코드·실경과): {report['incomplete_cell_attempts']}",
        f"- arm 간 어휘 동일: {report['vocabulary_equal_across_arms']}",
        f"- 실경과 {clocks['elapsed_real_seconds'] / 3600:.2f} h, "
        f"{clocks['exec_per_hour_real']:.0f} exec/h (실시간), "
        f"monotonic/실시간 {clocks['monotonic_over_real_pooled']:.4f}",
        "",
        "## 비-사건 지표 (R 변형 선택 입력)",
        "",
        "| arm | 거부 비율 | 변이 성공률 | 시드 직속 부모 | 평균 entry | invalid trace |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for arm in report["arms"].values():
        metrics = arm["non_event_metrics"]
        lines.append(
            f"| {arm['arm']} | {metrics['rejected_ratio']} | {metrics['mutation_success_rate']} | "
            f"{metrics['seed_parent_ratio']} | {metrics['mean_entries']} | "
            f"{metrics['invalid_trace_steps']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--sims", type=int, default=SIMS)
    parser.add_argument("--sensitivity-only", action="store_true")
    args = parser.parse_args(argv)
    if args.sensitivity_only:
        print(json.dumps(sensitivity_rows(sims=args.sims), indent=1))
        return 0
    if not (args.design and args.raw and args.out):
        parser.error("--design, --raw and --out are required")
    if re.search(r"(^|/)raw(/|$)", args.out.as_posix()):
        parser.error("--out must be outside the raw directory")
    report = analyze(args.raw, load_design(args.design), sims=args.sims)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "pilot-report.json").write_text(
        json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.out / "pilot-report.md").write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

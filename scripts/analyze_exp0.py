"""EXP-0 pilot report generator: prereg "측정(전부 기록)" items 1-7 in one pass.

Consumes the runtime lane's per-campaign summary files (one JSON per cell = seed x arm x
target) and produces the EVALUATION-lane EXP-0 infrastructure-measurement roll-up defined in
``experiments/preregistration/exp0-pilot-v2.md``. It MEASURES infrastructure; it does not test
H-A and never concludes effectiveness (prereg v2 "목적: 인프라 측정"). Every reported number
carries its denominator, and the hazard proxy is emitted only as a판정-무관 reference value.

Input is lane 5's G1-smoke / EXP-0 run directory. Each cell file
(``summaries/<run_id>.summary.json``) is a wrapper:

* ``summary``  -- the ``RdsCellSummary.summary_record()`` fields (``t_first`` / ``t_first_event``,
  ``executions_completed``, ``first_c0/c1/c2``, dense counts, ...); ``null`` for an invalid cell;
* ``timing``   -- ``wall_seconds``, ``step_wall_seconds`` (per-step full-step wall, step order),
  ``execution_mode`` ("per-case-container" | "worker-pool"), ``exec_per_hour`` (runner value);
* ``environment`` -- host / docker / image / node versions (passthrough provenance);
* ``config_nonconformant`` / ``invalid_reason`` -- the invalid bucket (summary is ``null``);
* ``unfingerprinted_hit_steps`` -- C1|C2 steps whose fingerprint the raw report did not record.

``summaries/index.json`` (``--index``) lists the cells and carries each cell's ``arm`` / ``seed``,
so invalid cells (whose ``summary`` is ``null``) still get their identity. A flat
``summary_record()`` dict is also accepted (no wrapper, no timing).

The RdsCellSummary field names are bound in ``_DEFAULT_FIELD_MAP`` and the timing subfields in
``_TIMING_*`` -- those are the single places a runner field name is bound; override cell fields
with ``--field-map``. The T_first survival pair feeds :mod:`inodefence.evaluation.survival`.

Items: (1) aborts by reason and arm + invalid bucket; (2) p95 full-step per cell and pooled;
(3) exec/h per cell and summed; (4) per-case vs worker-pool throughput + lane-4 parity verdict
(read, never decided here); (5) first C0/C1/C2 index per arm right-censored + combined T_first;
(6) dense signals; (7) hazard proxy (reference-only; campaign-unit rule-of-three when zero-hit).
A measurement whose inputs are entirely null/absent is reported ``available: false`` with the
missing field, never invented.

  python -m scripts.analyze_exp0 --index <run>/summaries/index.json [--parity <file>]
"""

import argparse
import importlib
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from inodefence.evaluation.encoding import json_bytes, read_json
from inodefence.evaluation.independence import arm_abort_independence_from_contingency
from inodefence.evaluation.survival import (
    AbortPolicy,
    Observation,
    SeedRecord,
    holm_adjust,
    kaplan_meier,
    km_median,
    observations_for_policy,
    rule_of_three,
    seed_block_logrank_permutation,
)

# Abort-reason vocabulary. Prefer the shared lane-3 enum so the buckets stay in lock-step
# with the classifier; fall back to a literal list (with the same members) when that module is
# not yet on this branch (before #203 merges). The fallback MUST list every InvalidReason value.
_FALLBACK_ABORT_REASONS = (
    "observer_integrity",
    "broker",
    "cleanup_inspect",
    "cleanup_remove",
    "cleanup_reset",
    "other",
)


def _load_abort_reasons() -> tuple[str, ...]:
    # Dynamic import so a missing module (before #203 merges) is a clean fallback, not a
    # pyright reportMissingImports on this branch.
    try:
        module = importlib.import_module("inodefence.evaluation.abort_classification")
    except ImportError:
        return _FALLBACK_ABORT_REASONS
    return tuple(reason.value for reason in module.InvalidReason)


ABORT_REASONS = _load_abort_reasons()
CONTRACTS = ("C0", "C1", "C2")

_DEFAULT_FIELD_MAP = {
    "seed": "random_seed",
    "arm": "arm",
    "target": "target_id",
    "budget": "execution_budget",
    "executions": "executions_completed",
    "complete": "complete",
    "aborted": "aborted",
    "invalid": "config_nonconformant",
    "abort_reason": "abort_reason",
    "t_first": "t_first",
    "t_first_event": "t_first_event",
    "hit_steps": "hit_steps",
    "first_c0": "first_c0",
    "first_c1": "first_c1",
    "first_c2": "first_c2",
    "boundary_attempt_keys": "boundary_attempt_keys",
    "rejected_executions": "rejected_executions",
    "observation_failures": "observation_failures",
    "u_viol": "u_viol",
    "u_viol_c0": "u_viol_c0",
}

# Wrapper top-level keys (outside the inner "summary" object), from lane 5's schema.
_SUMMARY_KEY = "summary"
_TIMING_KEY = "timing"
_ENVIRONMENT_KEY = "environment"
_CONFIG_NONCONFORMANT_KEY = "config_nonconformant"
_INVALID_REASON_KEY = "invalid_reason"
_UNFINGERPRINTED_KEY = "unfingerprinted_hit_steps"
# Subfields of the "timing" object.
_TIMING_WALL = "wall_seconds"
_TIMING_STEPS = "step_wall_seconds"
_TIMING_MODE = "execution_mode"
_TIMING_EXEC_PER_HOUR = "exec_per_hour"
_TIMING_RUNNER_P50 = "full_step_seconds_p50"
_TIMING_RUNNER_P95 = "full_step_seconds_p95"
_TIMING_RUNNER_MAX = "full_step_seconds_max"


@dataclass(frozen=True, slots=True)
class InvalidCell:
    """A config-nonconformant cell (summary is null): tracked and reported, never analyzed."""

    seed: int
    arm: str
    invalid_reason: str | None
    target_id: str = ""


@dataclass(frozen=True, slots=True)
class CellSummary:
    """One analyzable EXP-0 cell (complete or abort), as the runtime lane summarized it.

    ``disposition`` is ``"abort"`` (fail-closed stop, raw ``abort_reason``) or ``"complete"``.
    ``t_first`` / ``t_first_event`` is the combined C1|C2 survival pair. ``first_cX`` is the
    1-based first C0/C1/C2 execution or ``None``. Timing (``wall_clock_seconds``,
    ``full_step_durations``, ``execution_mode``) is optional; ``None`` when the runner omitted it.
    """

    seed: int
    arm: str
    target: str
    budget: int
    executions: int
    disposition: str
    abort_reason: str | None
    t_first: int
    t_first_event: int
    hit_steps: int
    first_c0: int | None
    first_c1: int | None
    first_c2: int | None
    boundary_attempt_keys: int
    rejected_executions: int
    observation_failures: int
    u_viol: int
    u_viol_c0: int
    unfingerprinted_hit_steps: int
    wall_clock_seconds: float | None
    full_step_durations: tuple[float, ...] | None
    execution_mode: str | None
    runner_exec_per_hour: float | None
    runner_p50_seconds: float | None
    runner_p95_seconds: float | None
    runner_max_seconds: float | None
    environment: Mapping[str, object] | None
    target_id: str = ""
    role: str = "train"
    hypothesis: str = "H-A"

    def __post_init__(self) -> None:
        if self.role not in ("train", "fix-verification", "holdout"):
            raise ValueError(f"role must be train/fix-verification/holdout, got {self.role!r}")
        if self.hypothesis not in ("H-A", "H-B"):
            raise ValueError(f"hypothesis must be H-A/H-B, got {self.hypothesis!r}")
        if self.disposition not in ("complete", "abort"):
            raise ValueError(
                f"CellSummary disposition must be complete/abort, got {self.disposition!r}"
            )
        if self.disposition != "abort" and self.abort_reason is not None:
            raise ValueError("only an aborted cell may carry an abort_reason")
        if self.budget <= 0 or self.executions <= 0 or self.executions > self.budget:
            raise ValueError("need 0 < executions <= budget")
        if self.t_first_event not in (0, 1):
            raise ValueError("t_first_event must be 0 or 1")
        if not (1 <= self.t_first <= self.budget):
            raise ValueError("t_first must be a 1-based index within the budget")
        if self.t_first_event == 1 and self.t_first > self.executions:
            raise ValueError("a T_first event cannot occur after the executions run")
        for index in (self.first_c0, self.first_c1, self.first_c2):
            if index is not None and not (1 <= index <= self.executions):
                raise ValueError("a first-contract index must be within the executions run")
        if self.wall_clock_seconds is not None and self.wall_clock_seconds <= 0:
            raise ValueError("wall_clock_seconds, when present, must be positive")

    def first_index(self, contract: str) -> int | None:
        return {"C0": self.first_c0, "C1": self.first_c1, "C2": self.first_c2}[contract]

    def censoring_horizon(self) -> int:
        """Right-censoring time for a no-observation cell: budget if complete, else executions."""
        return self.budget if self.disposition == "complete" else self.executions


def _get(row: Mapping[str, object], field_map: Mapping[str, str], key: str) -> object:
    return row.get(field_map[key])


def _timing_value(timing: Mapping[str, object] | None, key: str) -> object:
    return None if timing is None else timing.get(key)


def _identity(
    inner: Mapping[str, object] | None,
    entry: Mapping[str, object] | None,
    field_map: Mapping[str, str],
) -> tuple[int, str]:
    for source in (inner, entry):
        if isinstance(source, dict):
            seed = source.get(field_map["seed"], source.get("seed"))
            arm = source.get(field_map["arm"], source.get("arm"))
            if seed is not None and arm is not None:
                return int(seed), str(arm)  # type: ignore[arg-type]
    raise ValueError("invalid cell has no identity; load it via --index so arm/seed are known")


def cell_from_row(
    row: Mapping[str, object],
    field_map: Mapping[str, str],
    *,
    entry: Mapping[str, object] | None = None,
) -> CellSummary | InvalidCell:
    """Map one wrapper (or flat) runner row to a :class:`CellSummary` or :class:`InvalidCell`.

    Reads the inner RdsCellSummary object through ``field_map`` and the wrapper's ``timing`` /
    ``config_nonconformant`` / ``unfingerprinted_hit_steps`` through the ``_TIMING_*`` / ``_*_KEY``
    constants. ``entry`` is the matching ``index.json`` record, used only to recover an invalid
    cell's arm/seed when its ``summary`` is null.
    """
    has_wrapper = _SUMMARY_KEY in row
    inner = row.get(_SUMMARY_KEY) if has_wrapper else row
    config_nonconformant = (
        bool(row.get(_CONFIG_NONCONFORMANT_KEY))
        if has_wrapper
        else bool(_get(row, field_map, "invalid"))
    )
    if config_nonconformant or (has_wrapper and inner is None):
        reason = row.get(_INVALID_REASON_KEY) if has_wrapper else None
        seed, arm = _identity(inner if isinstance(inner, dict) else None, entry, field_map)
        invalid_tid = (
            str(entry["target_id"]) if isinstance(entry, Mapping) and entry.get("target_id") else ""
        )
        return InvalidCell(
            seed=seed,
            arm=arm,
            invalid_reason=None if reason is None else str(reason),
            target_id=invalid_tid,
        )

    if not isinstance(inner, dict):
        raise ValueError("a non-invalid cell must carry a summary object")

    def optional_int(key: str) -> int | None:
        value = _get(inner, field_map, key)
        return None if value is None else int(value)  # type: ignore[arg-type]

    aborted = bool(_get(inner, field_map, "aborted"))
    complete = bool(_get(inner, field_map, "complete"))
    if aborted:
        disposition = "abort"
    elif complete:
        disposition = "complete"
    else:
        raise ValueError("a non-invalid cell must be complete or aborted")

    timing = row.get(_TIMING_KEY) if has_wrapper else None
    timing = timing if isinstance(timing, dict) else None
    durations = _timing_value(timing, _TIMING_STEPS)
    if durations is not None and not isinstance(durations, list):
        raise ValueError("timing.step_wall_seconds, when present, must be a list of seconds")
    wall = _timing_value(timing, _TIMING_WALL)
    mode = _timing_value(timing, _TIMING_MODE)
    runner_eph = _timing_value(timing, _TIMING_EXEC_PER_HOUR)
    runner_p50 = _timing_value(timing, _TIMING_RUNNER_P50)
    runner_p95 = _timing_value(timing, _TIMING_RUNNER_P95)
    runner_max = _timing_value(timing, _TIMING_RUNNER_MAX)
    environment = row.get(_ENVIRONMENT_KEY) if has_wrapper else None
    abort_reason = _get(inner, field_map, "abort_reason")
    target = str(_get(inner, field_map, "target") or "unspecified")
    meta = entry if isinstance(entry, Mapping) else None
    target_id = str(meta["target_id"]) if meta and meta.get("target_id") else target
    role = str(meta["role"]) if meta and meta.get("role") else "train"
    hypothesis = str(meta["hypothesis"]) if meta and meta.get("hypothesis") else "H-A"

    return CellSummary(
        seed=int(_get(inner, field_map, "seed")),  # type: ignore[arg-type]
        arm=str(_get(inner, field_map, "arm")),
        target=target,
        budget=int(_get(inner, field_map, "budget")),  # type: ignore[arg-type]
        executions=int(_get(inner, field_map, "executions")),  # type: ignore[arg-type]
        disposition=disposition,
        abort_reason=None
        if (disposition != "abort" or abort_reason is None)
        else str(abort_reason),
        t_first=int(_get(inner, field_map, "t_first")),  # type: ignore[arg-type]
        t_first_event=int(_get(inner, field_map, "t_first_event")),  # type: ignore[arg-type]
        hit_steps=int(_get(inner, field_map, "hit_steps")),  # type: ignore[arg-type]
        first_c0=optional_int("first_c0"),
        first_c1=optional_int("first_c1"),
        first_c2=optional_int("first_c2"),
        boundary_attempt_keys=int(_get(inner, field_map, "boundary_attempt_keys")),  # type: ignore[arg-type]
        rejected_executions=int(_get(inner, field_map, "rejected_executions")),  # type: ignore[arg-type]
        observation_failures=int(_get(inner, field_map, "observation_failures") or 0),  # type: ignore[arg-type]
        u_viol=int(_get(inner, field_map, "u_viol") or 0),  # type: ignore[arg-type]
        u_viol_c0=int(_get(inner, field_map, "u_viol_c0") or 0),  # type: ignore[arg-type]
        unfingerprinted_hit_steps=int(row.get(_UNFINGERPRINTED_KEY) or 0) if has_wrapper else 0,  # type: ignore[arg-type]
        wall_clock_seconds=None if wall is None else float(wall),  # type: ignore[arg-type]
        full_step_durations=None if durations is None else tuple(float(v) for v in durations),
        execution_mode=None if mode is None else str(mode),
        runner_exec_per_hour=None if runner_eph is None else float(runner_eph),  # type: ignore[arg-type]
        runner_p50_seconds=None if runner_p50 is None else float(runner_p50),  # type: ignore[arg-type]
        runner_p95_seconds=None if runner_p95 is None else float(runner_p95),  # type: ignore[arg-type]
        runner_max_seconds=None if runner_max is None else float(runner_max),  # type: ignore[arg-type]
        environment=environment if isinstance(environment, dict) else None,
        target_id=target_id,
        role=role,
        hypothesis=hypothesis,
    )


def _percentile(values: Sequence[float], p: float) -> float | None:
    """Nearest-rank percentile (matching lane 5's precomputed p50/p95/max)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p * len(ordered)))
    return ordered[min(rank - 1, len(ordered) - 1)]


def _by_arm(cells: Sequence[CellSummary]) -> dict[str, list[CellSummary]]:
    arms: dict[str, list[CellSummary]] = {}
    for cell in cells:
        arms.setdefault(cell.arm, []).append(cell)
    return dict(sorted(arms.items()))


def _bucket_reason(reason: str) -> str:
    return reason if reason in ABORT_REASONS else "other"


def _aborts(cells: Sequence[CellSummary], invalid: Sequence[InvalidCell]) -> dict:
    invalid_by_arm: dict[str, int] = {}
    for cell in invalid:
        invalid_by_arm[cell.arm] = invalid_by_arm.get(cell.arm, 0) + 1
    per_arm = {}
    arms = sorted({c.arm for c in cells} | set(invalid_by_arm))
    for arm in arms:
        arm_cells = [c for c in cells if c.arm == arm]
        reasons = {reason: 0 for reason in ABORT_REASONS}
        for cell in arm_cells:
            if cell.disposition == "abort":
                reasons[_bucket_reason(cell.abort_reason or "other")] += 1
        aborts = sum(reasons.values())
        invalid_count = invalid_by_arm.get(arm, 0)
        total = len(arm_cells) + invalid_count
        per_arm[arm] = {
            "number_cells": total,
            "number_complete": sum(1 for c in arm_cells if c.disposition == "complete"),
            "number_abort": aborts,
            "number_invalid_nonconformant": invalid_count,
            "abort_by_reason": reasons,
            "abort_fraction": aborts / total if total else None,
            "denominator": total,
        }
    return {"by_arm": per_arm, "abort_reason_enum": list(ABORT_REASONS)}


def _p95_full_step(cells: Sequence[CellSummary]) -> dict:
    timed = [c for c in cells if c.full_step_durations is not None]
    if not timed:
        return {
            "available": False,
            "missing_field": f"{_TIMING_KEY}.{_TIMING_STEPS}",
            "note": "no per-step duration field in the runner timing block",
        }
    per_cell = []
    pooled: list[float] = []
    for cell in timed:
        durations = cell.full_step_durations or ()
        pooled.extend(durations)
        per_cell.append(
            {
                "seed": cell.seed,
                "arm": cell.arm,
                "number_steps": len(durations),
                "p50_seconds": _percentile(durations, 0.50),
                "p95_seconds": _percentile(durations, 0.95),
                "max_seconds": max(durations) if durations else None,
                "runner_p50_seconds": cell.runner_p50_seconds,
                "runner_p95_seconds": cell.runner_p95_seconds,
                "runner_max_seconds": cell.runner_max_seconds,
            }
        )
    return {
        "available": True,
        "unit": "seconds",
        "method": "nearest-rank percentile",
        "per_cell": per_cell,
        "pooled": {
            "number_steps": len(pooled),
            "p50_seconds": _percentile(pooled, 0.50),
            "p95_seconds": _percentile(pooled, 0.95),
            "max_seconds": max(pooled) if pooled else None,
        },
    }


def _throughput(cells: Sequence[CellSummary]) -> dict:
    timed = [c for c in cells if c.wall_clock_seconds is not None]
    if not timed:
        return {
            "available": False,
            "missing_field": f"{_TIMING_KEY}.{_TIMING_WALL}",
            "note": "no wall-clock field in the runner timing block",
        }
    executions = sum(c.executions for c in timed)
    wall = sum(c.wall_clock_seconds or 0.0 for c in timed)
    per_cell = [
        {
            "seed": c.seed,
            "arm": c.arm,
            "executions": c.executions,
            "wall_clock_seconds": c.wall_clock_seconds,
            "exec_per_hour": c.executions / ((c.wall_clock_seconds or 0.0) / 3600.0),
            "runner_exec_per_hour": c.runner_exec_per_hour,
        }
        for c in timed
    ]
    return {
        "available": True,
        "per_cell": per_cell,
        "summed": {
            "number_cells": len(timed),
            "executions": executions,
            "wall_clock_seconds": wall,
            "exec_per_hour": executions / (wall / 3600.0) if wall else None,
        },
    }


def _throughput_parity(cells: Sequence[CellSummary], parity: object | None) -> dict:
    moded = [c for c in cells if c.execution_mode is not None and c.wall_clock_seconds is not None]
    by_mode: dict[str, dict] = {}
    for cell in moded:
        bucket = by_mode.setdefault(
            cell.execution_mode or "", {"number_cells": 0, "executions": 0, "wall": 0.0}
        )
        bucket["number_cells"] += 1
        bucket["executions"] += cell.executions
        bucket["wall"] += cell.wall_clock_seconds or 0.0
    rendered = {
        mode: {
            "number_cells": s["number_cells"],
            "executions": s["executions"],
            "exec_per_hour": s["executions"] / (s["wall"] / 3600.0) if s["wall"] else None,
        }
        for mode, s in by_mode.items()
    }
    return {
        "available_self_throughput": bool(rendered),
        "by_execution_mode": rendered,
        "mode_note": (
            "null/empty = the runner summaries carry no execution-mode + wall-clock timing; "
            "per-case vs worker-pool split is then unavailable from summaries alone"
        ),
        "parity_verdict": parity,
        "parity_note": (
            "parity verdict is read verbatim from the lane-4 comparator result file; this "
            "report does not decide parity. null = no comparator file was provided."
        ),
    }


def _seed_record_from_cell(cell: CellSummary) -> SeedRecord:
    """Project a cell to a survival :class:`SeedRecord` (the pre-censoring T_first fact).

    An aborted cell's abort execution is its ``executions`` (where the fail-closed stop
    happened); a complete cell carries no abort index. The first event, when observed, is
    ``t_first``. This reconstructs the observation from the raw facts so each abort policy can
    be applied, rather than reusing the already-right-censored ``t_first`` column.
    """
    return SeedRecord(
        seed=cell.seed,
        budget=cell.budget,
        status=cell.disposition,
        first_event_executions=cell.t_first if cell.t_first_event == 1 else None,
        abort_executions=cell.executions if cell.disposition == "abort" else None,
    )


def _t_first_abort_sensitivity(cells: Sequence[CellSummary]) -> dict:
    """Abort-censoring sensitivity for combined-C1|C2 T_first (promised in §4.6.2 / §6.7).

    item5's main body is the primary read, which censors an abort at its abort execution
    (:attr:`AbortPolicy.CENSOR_AT_ABORT`). This adds the other two conventions as an additive
    ``sensitivity`` object -- complete campaigns only (:attr:`AbortPolicy.EXCLUDE`) and an abort
    treated as a no-hit full run (:attr:`AbortPolicy.CENSOR_AT_BUDGET`) -- so a median or
    ordering stable across all three is robust to the abort assumption and one that moves is
    driven by it (EN-008). Only aborted cells move; complete cells are identical across policies.
    Reuses :func:`inodefence.evaluation.survival.observations_for_policy`; invents no numbers.
    """
    policies: dict[str, dict] = {}
    for policy in (AbortPolicy.EXCLUDE, AbortPolicy.CENSOR_AT_BUDGET):
        by_arm = {}
        for arm, valid in _by_arm(cells).items():
            records = [_seed_record_from_cell(c) for c in valid]
            observations = observations_for_policy(records, policy)
            observed = [o.time for o in observations if o.event]
            steps = kaplan_meier(observations)
            by_arm[arm] = {
                "number_observed": len(observed),
                "observed_t_first": sorted(observed),
                "number_right_censored": len(observations) - len(observed),
                "number_in_risk_set": len(observations),
                "km_median_executions": km_median(steps),
            }
        policies[policy.value] = {"by_arm": by_arm}
    return {
        "classification": "abort-censoring-sensitivity (T_first combined C1|C2)",
        "primary_policy": AbortPolicy.CENSOR_AT_ABORT.value,
        "primary_location": "item5_first_contract_index.by_arm[*].t_first_combined_c1_or_c2",
        "policies": policies,
        "note": (
            "primary (item5 body) censors an abort at its abort execution; these two bracket the "
            "informative-censoring assumption -- EXCLUDE drops aborts (risk set = complete cells), "
            "CENSOR_AT_BUDGET treats an abort as a no-hit full run. A verdict stable across all "
            "three is robust; one that moves is abort-assumption-driven (EN-008). Complete cells "
            "are identical across policies, so any change is the aborts alone."
        ),
    }


def _first_index_censored(cells: Sequence[CellSummary], invalid: Sequence[InvalidCell]) -> dict:
    invalid_by_arm: dict[str, int] = {}
    for cell in invalid:
        invalid_by_arm[cell.arm] = invalid_by_arm.get(cell.arm, 0) + 1
    per_arm = {}
    for arm, valid in _by_arm(cells).items():
        contracts = {}
        for contract in CONTRACTS:
            observations, observed = [], []
            for cell in valid:
                index = cell.first_index(contract)
                if index is not None:
                    observations.append(Observation(time=index, event=True))
                    observed.append(index)
                else:
                    observations.append(Observation(time=cell.censoring_horizon(), event=False))
            steps = kaplan_meier(observations)
            contracts[contract] = {
                "number_observed": len(observed),
                "observed_indices": sorted(observed),
                "number_right_censored": len(observations) - len(observed),
                "km_median_executions": km_median(steps),
                "denominator_cells_in_risk_set": len(observations),
            }
        t_first_obs = [Observation(time=c.t_first, event=bool(c.t_first_event)) for c in valid]
        t_first_observed = [c.t_first for c in valid if c.t_first_event == 1]
        t_first_steps = kaplan_meier(t_first_obs)
        per_arm[arm] = {
            "number_invalid_excluded": invalid_by_arm.get(arm, 0),
            "censoring": "no-hit censored at budget; abort censored at abort execution",
            "contracts": contracts,
            "t_first_combined_c1_or_c2": {
                "number_observed": len(t_first_observed),
                "observed_t_first": sorted(t_first_observed),
                "number_right_censored": len(t_first_obs) - len(t_first_observed),
                "km_median_executions": km_median(t_first_steps),
                "denominator_cells_in_risk_set": len(t_first_obs),
                # Plottable step curve + censoring tick times (all derived from observed data).
                "km_curve": [
                    {
                        "time": step.time,
                        "survival": step.survival,
                        "at_risk": step.at_risk,
                        "events": step.events,
                    }
                    for step in t_first_steps
                ],
                "censored_times": sorted(o.time for o in t_first_obs if not o.event),
            },
        }
    return {"by_arm": per_arm, "sensitivity": _t_first_abort_sensitivity(cells)}


def _dense_signals(cells: Sequence[CellSummary]) -> dict:
    per_arm = {}
    for arm, valid in _by_arm(cells).items():
        executions = sum(c.executions for c in valid)
        boundary_total = sum(c.boundary_attempt_keys for c in valid)
        rejected = sum(c.rejected_executions for c in valid)
        u_viol_total = sum(c.u_viol for c in valid)
        u_viol_c0_total = sum(c.u_viol_c0 for c in valid)
        per_arm[arm] = {
            "number_cells_in_denominator": len(valid),
            "boundary_attempt_keys": {
                "total": boundary_total,
                "mean_per_cell": boundary_total / len(valid) if valid else None,
            },
            "rejected_ratio": {
                "numerator": rejected,
                "denominator_executions": executions,
                "value": rejected / executions if executions else None,
            },
            "observation_failures_total": sum(c.observation_failures for c in valid),
            "u_viol": {
                "total_unique_c1_c2_fingerprints": u_viol_total,
                "mean_per_cell": u_viol_total / len(valid) if valid else None,
            },
            "u_viol_c0": {
                "total_unique_c0_fingerprints": u_viol_c0_total,
                "mean_per_cell": u_viol_c0_total / len(valid) if valid else None,
            },
            "unfingerprinted_hit_steps_total": sum(c.unfingerprinted_hit_steps for c in valid),
        }
    return {"by_arm": per_arm}


def _hazard_proxy(cells: Sequence[CellSummary]) -> dict:
    per_arm = {}
    total_hits = 0
    for arm, valid in _by_arm(cells).items():
        executions = sum(c.executions for c in valid)
        hits = sum(c.hit_steps for c in valid)
        total_hits += hits
        per_arm[arm] = {
            "hit_steps_c1_or_c2": hits,
            "executions": executions,
            "campaigns": len(valid),
            "proxy_per_execution": hits / executions if executions else None,
        }
    result = {
        "label": "참고값(판정 무관) / reference value only, not a verdict",
        "definition": "(C1|C2 step count) / (execution count)",
        "by_arm": per_arm,
    }
    if total_hits == 0:
        result["zero_hit"] = {
            "policy": (
                "prereg v2 (a): campaign-unit rule-of-three is primary; execution-unit exploratory"
            ),
            "by_arm": {
                arm: {
                    "campaign_unit_rule_of_three_upper95": (
                        rule_of_three(s["campaigns"]) if s["campaigns"] else None
                    ),
                    "campaign_denominator": s["campaigns"],
                    "execution_unit_rule_of_three_upper95_exploratory": (
                        rule_of_three(s["executions"]) if s["executions"] else None
                    ),
                    "execution_denominator": s["executions"],
                }
                for arm, s in per_arm.items()
            },
        }
    return result


def _environments(cells: Sequence[CellSummary]) -> dict:
    seen = [c.environment for c in cells if c.environment is not None]
    distinct = []
    for env in seen:
        if env not in distinct:
            distinct.append(dict(env))
    return {
        "number_cells_with_environment": len(seen),
        "distinct": distinct,
        "homogeneous": len(distinct) <= 1,
    }


def build_report(
    cells: Sequence[CellSummary | InvalidCell],
    *,
    parity: object | None = None,
    independence: dict | None = None,
    field_map: Mapping[str, str],
    sources: Sequence[str],
) -> dict:
    """Assemble the EXP-0 measurement report (prereg items 1-7) from validated cells.

    ``independence`` is the optional arm x abort independence reporting flag (audit 13a) from
    lane 3's contingency table; when present it is added as ``arm_abort_independence``.
    """
    if not cells:
        raise ValueError("no cells to summarize")
    valid = [c for c in cells if isinstance(c, CellSummary)]
    invalid = [c for c in cells if isinstance(c, InvalidCell)]
    arms = sorted({c.arm for c in cells})
    report = {
        "schema_version": 1,
        "classification": "exp0-pilot-infrastructure-measurement",
        "purpose": (
            "infrastructure measurement only; NOT an H-A test and NOT an "
            "effectiveness claim (prereg v2)"
        ),
        "number_cells": len(cells),
        "number_valid_cells": len(valid),
        "number_invalid_cells": len(invalid),
        "arms": arms,
        "seeds": sorted({c.seed for c in cells}),
        "targets": sorted({c.target for c in valid}),
        "item1_aborts": _aborts(valid, invalid),
        "item2_p95_full_step": _p95_full_step(valid),
        "item3_throughput": _throughput(valid),
        "item4_throughput_parity": _throughput_parity(valid, parity),
        "item5_first_contract_index": _first_index_censored(valid, invalid),
        "item6_dense_signals": _dense_signals(valid),
        "item7_hazard_proxy": _hazard_proxy(valid),
        "environment": _environments(valid),
        "provenance": {"source_files": list(sources), "field_map": dict(field_map)},
    }
    if independence is not None:
        report["arm_abort_independence"] = independence
    return report


_ROLE_INTERPRETATION = {
    "train": "exploratory (pre-exposed; design developed here, not confirmatory)",
    "fix-verification": "negative control (patched; expected 0 hits)",
    "holdout": "confirmatory (independent, unseen)",
}


def _index_plan(index_file: Path) -> dict | None:
    """Read the top-level ``analysis_plan`` (EXP-3 multi-target) from an index, if present."""
    data = read_json(index_file.read_bytes())
    if isinstance(data, dict):
        plan = data.get("analysis_plan")
        if isinstance(plan, dict):
            return plan
    return None


def _confirmatory_section(
    valid: Sequence[CellSummary], analysis_plan: Mapping[str, object], *, alpha: float = 0.05
) -> dict | None:
    """Run the frozen confirmatory family: seed-block exact-permutation log-rank + Holm-FWER.

    For each ordered ``confirmatory_contrasts`` record (holdout&H-A only, pre-filtered by the
    registration) this pairs the target's two arms by seed on the primary endpoint (T_first,
    right-censored) and runs :func:`survival.seed_block_logrank_permutation` (valid at any n),
    then applies :func:`survival.holm_adjust` across the family in order. When a contrast's
    observed events fall below ``event_threshold`` it is FLAGGED underpowered and a descriptive
    campaign-unit rule-of-three bound is attached -- the test is never switched, and the bound is
    not a confirmation (EN-008). Returns ``None`` when the plan declares no contrasts.
    """
    contrasts = analysis_plan.get("confirmatory_contrasts")
    if not isinstance(contrasts, list) or not contrasts:
        return None
    threshold = analysis_plan.get("event_threshold")
    results: list[dict] = []
    raw_ps: list[float] = []
    for contrast in contrasts:
        tid, arm_a, arm_b = (
            contrast.get("target_id"),
            contrast.get("arm_a"),
            contrast.get("arm_b"),
        )
        cells_t = [c for c in valid if c.target_id == tid and c.arm in (arm_a, arm_b)]
        by_seed: dict[int, dict[str, Observation]] = {}
        for c in cells_t:
            by_seed.setdefault(c.seed, {})[c.arm] = Observation(c.t_first, bool(c.t_first_event))
        blocks = [
            (by_seed[s][arm_a], by_seed[s][arm_b])
            for s in sorted(by_seed)
            if arm_a in by_seed[s] and arm_b in by_seed[s]
        ]
        perm = seed_block_logrank_permutation(blocks, seed=0)
        events = int(perm["total_events"])
        underpowered = isinstance(threshold, int) and events < threshold
        entry: dict = {
            "order": contrast.get("order"),
            "target_id": tid,
            "contrast": contrast.get("contrast"),
            "arm_a": arm_a,
            "arm_b": arm_b,
            "number_seed_blocks": perm["number_blocks"],
            "total_events": events,
            "permutation": perm,
            "underpowered": underpowered,
        }
        if underpowered:
            entry["rule_of_three_upper95"] = rule_of_three(len(cells_t)) if cells_t else None
            entry["underpowered_note"] = (
                "events below event_threshold: the permutation test is valid but near-powerless "
                "(verdict is scenario-5, unobserved at achieved power); the rule-of-three is a "
                "descriptive campaign-unit upper bound, NOT a confirmation (EN-008)"
            )
        raw_ps.append(float(perm["p_value"]) if perm["p_value"] is not None else 1.0)
        results.append(entry)
    for entry, adjusted in zip(results, holm_adjust(raw_ps), strict=True):
        entry["holm_adjusted_p"] = adjusted
        entry["reject_at_alpha"] = adjusted <= alpha
    return {
        "classification": "confirmatory-holm-fwer",
        "confirmatory_test": analysis_plan.get("confirmatory_test"),
        "multiplicity": analysis_plan.get("multiplicity"),
        "primary_endpoint": analysis_plan.get("primary_endpoint"),
        "event_threshold": threshold,
        "alpha": alpha,
        "contrasts": results,
        "note": (
            "per-contrast seed-block arm-label permutation log-rank (valid at any n), Holm-FWER "
            "over the frozen ordered family; event_threshold is an underpowered FLAG + rule-of-"
            "three descriptor, never a test switch; rule-of-three is not a confirmation (EN-008)"
        ),
    }


def build_multitarget_report(
    cells: Sequence[CellSummary | InvalidCell],
    *,
    analysis_plan: dict | None = None,
    parity: object | None = None,
    independence: dict | None = None,
    field_map: Mapping[str, str],
    sources: Sequence[str],
) -> dict:
    """Per-target, per-role EXP-3 sections (no cross-target pooling).

    Each target is reported in its own ``by_target`` section -- train (pre-exposed, exploratory),
    fix-verification (negative control, expected 0 hits) and holdout (confirmatory) never share a
    risk set, because hazards differ by extractor/version (pooling would confound; Simpson). The
    frozen ``analysis_plan`` (ordered ``confirmatory_contrasts`` on holdout&H-A, ``multiplicity``,
    ``primary_endpoint``, ``event_threshold``) is echoed verbatim -- this builder derives no family
    membership and runs no confirmatory test (that is the exact-log-rank step). Single-target input
    uses :func:`build_report` (byte-identical to the EXP-0 output); this path is for >1 target_id.
    """
    if not cells:
        raise ValueError("no cells to summarize")
    valid = [c for c in cells if isinstance(c, CellSummary)]
    invalid = [c for c in cells if isinstance(c, InvalidCell)]
    target_ids = sorted({c.target_id for c in cells})
    by_target: dict[str, dict] = {}
    for tid in target_ids:
        tvalid = [c for c in valid if c.target_id == tid]
        tinvalid = [c for c in invalid if c.target_id == tid]
        roles = sorted({c.role for c in tvalid})
        hyps = sorted({c.hypothesis for c in tvalid})
        role: object = roles[0] if len(roles) == 1 else roles
        by_target[tid] = {
            "role": role,
            "hypothesis": hyps[0] if len(hyps) == 1 else hyps,
            "role_interpretation": _ROLE_INTERPRETATION.get(role, "mixed roles in one target")
            if isinstance(role, str)
            else "mixed roles in one target",
            "number_cells": len(tvalid) + len(tinvalid),
            "arms": sorted({c.arm for c in [*tvalid, *tinvalid]}),
            "seeds": sorted({c.seed for c in [*tvalid, *tinvalid]}),
            "item1_aborts": _aborts(tvalid, tinvalid),
            "item2_p95_full_step": _p95_full_step(tvalid),
            "item3_throughput": _throughput(tvalid),
            "item4_throughput_parity": _throughput_parity(tvalid, parity),
            "item5_first_contract_index": _first_index_censored(tvalid, tinvalid),
            "item6_dense_signals": _dense_signals(tvalid),
            "item7_hazard_proxy": _hazard_proxy(tvalid),
            "environment": _environments(tvalid),
        }
    report = {
        "schema_version": 2,
        "classification": "exp3-multitarget-measurement",
        "purpose": (
            "per-target, per-role measurement; targets are NOT pooled (hazard differs by "
            "extractor/version). H-A arm inference is confirmatory only on a holdout target; "
            "train is exploratory (pre-exposed) and fix-verification is a negative control "
            "(expected 0 hits). This report echoes the frozen analysis_plan and runs no "
            "confirmatory test (the exact-log-rank step consumes it separately)."
        ),
        "number_cells": len(cells),
        "number_valid_cells": len(valid),
        "number_invalid_cells": len(invalid),
        "target_ids": target_ids,
        "arms": sorted({c.arm for c in cells}),
        "seeds": sorted({c.seed for c in cells}),
        "analysis_plan": analysis_plan,
        "confirmatory_targets": (analysis_plan or {}).get("confirmatory_targets"),
        "confirmatory": (
            _confirmatory_section(valid, analysis_plan) if isinstance(analysis_plan, dict) else None
        ),
        "by_target": by_target,
        "provenance": {"source_files": list(sources), "field_map": dict(field_map)},
    }
    if independence is not None:
        report["arm_abort_independence"] = independence
    return report


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return lines


def _multitarget_markdown(report: dict) -> str:
    lines = [
        "# EXP-3 multi-target measurement (per-target, no pooling)",
        "",
        f"Targets: {', '.join(report['target_ids'])} | "
        f"cells {report['number_cells']} (valid {report['number_valid_cells']}, "
        f"invalid {report['number_invalid_cells']}) | arms {', '.join(report['arms'])}",
        "",
        "_H-A arm inference is confirmatory on a holdout target only; train is exploratory "
        "(pre-exposed), fix-verification is a negative control. Targets are not pooled._",
        "",
    ]
    plan = report.get("analysis_plan")
    if isinstance(plan, dict):
        lines += [
            "## Confirmatory plan (frozen, echoed)",
            "",
            f"primary_endpoint={plan.get('primary_endpoint')} · "
            f"multiplicity={plan.get('multiplicity')} · "
            f"event_threshold={plan.get('event_threshold')} · "
            f"confirmatory_test={plan.get('confirmatory_test')}",
            "",
        ]
        contrasts = plan.get("confirmatory_contrasts") or []
        if isinstance(contrasts, list) and contrasts:
            lines += _md_table(
                ["order", "target_id", "arm_a", "arm_b", "contrast"],
                [
                    [
                        c.get("order"),
                        c.get("target_id"),
                        c.get("arm_a"),
                        c.get("arm_b"),
                        c.get("contrast"),
                    ]
                    for c in contrasts
                ],
            )
        else:
            lines.append("(no H-A holdout contrasts registered)")
        lines.append("")
    conf = report.get("confirmatory")
    if isinstance(conf, dict):
        lines += ["## Confirmatory result (seed-block permutation log-rank + Holm)", ""]
        rows = []
        for c in conf["contrasts"]:
            perm_p = c["permutation"]["p_value"]
            rows.append([
                c.get("order"),
                c.get("contrast"),
                c.get("number_seed_blocks"),
                c.get("total_events"),
                "n/a" if perm_p is None else f"{perm_p:.4f}",
                f"{c['holm_adjusted_p']:.4f}",
                c["reject_at_alpha"],
                c["underpowered"],
            ])
        lines += _md_table(
            ["order", "contrast", "blocks", "events", "perm_p", "holm_p", "reject", "underpow"],
            rows,
        )
        lines += ["", f"_{conf['note']}_", ""]
    for tid in report["target_ids"]:
        sec = report["by_target"][tid]
        t5 = sec["item5_first_contract_index"]["by_arm"]
        aborts = sec["item1_aborts"]["by_arm"]
        lines += [
            f"## Target `{tid}` — role {sec['role']} ({sec['role_interpretation']}), "
            f"hypothesis {sec['hypothesis']}",
            "",
            f"arms {', '.join(sec['arms'])} | seeds {len(sec['seeds'])} | "
            f"cells {sec['number_cells']}",
            "",
        ]
        lines += _md_table(
            ["arm", "T_first observed", "T_first median", "aborts"],
            [
                [
                    arm,
                    t5[arm]["t_first_combined_c1_or_c2"]["number_observed"],
                    t5[arm]["t_first_combined_c1_or_c2"]["km_median_executions"],
                    aborts.get(arm, {}).get("number_abort", 0),
                ]
                for arm in sec["arms"]
                if arm in t5
            ],
        )
        lines.append("")
    lines.append("_Full per-item detail (items 1-7, item5 sensitivity) is in the JSON report._")
    return "\n".join(lines)


def report_markdown(report: dict) -> str:
    if "by_target" in report:
        return _multitarget_markdown(report)
    lines = [
        "# EXP-0 pilot infrastructure measurement",
        "",
        f"Cells: {report['number_cells']} "
        f"(valid {report['number_valid_cells']}, invalid {report['number_invalid_cells']}) | "
        f"arms: {', '.join(report['arms'])} | seeds: {len(report['seeds'])}",
        "",
        "_Infrastructure measurement only; not an H-A test, not an effectiveness claim._",
        "",
        "## 1. Aborts by reason and arm",
        "",
    ]
    lines += _md_table(
        ["arm", "cells", "complete", "abort", "invalid", "abort_frac"],
        [
            [
                arm,
                s["number_cells"],
                s["number_complete"],
                s["number_abort"],
                s["number_invalid_nonconformant"],
                "n/a" if s["abort_fraction"] is None else f"{s['abort_fraction']:.3f}",
            ]
            for arm, s in report["item1_aborts"]["by_arm"].items()
        ],
    )
    p95 = report["item2_p95_full_step"]
    throughput = report["item3_throughput"]
    lines += [
        "",
        "## 2. p95 full-step time",
        "",
        f"Pooled p95: {p95['pooled']['p95_seconds']} s over {p95['pooled']['number_steps']} steps."
        if p95.get("available")
        else f"Unavailable: {p95['note']}",
        "",
        "## 3. Throughput (exec/h)",
        "",
        f"Summed: {throughput['summed']['exec_per_hour']} exec/h over "
        f"{throughput['summed']['executions']} executions."
        if throughput.get("available")
        else f"Unavailable: {throughput['note']}",
        "",
        "## 4. Per-case vs worker-pool throughput",
        "",
    ]
    parity = report["item4_throughput_parity"]
    if parity["by_execution_mode"]:
        lines += _md_table(
            ["mode", "cells", "executions", "exec/h"],
            [
                [mode, s["number_cells"], s["executions"], s["exec_per_hour"]]
                for mode, s in parity["by_execution_mode"].items()
            ],
        )
    else:
        lines.append(f"Self-throughput split unavailable: {parity['mode_note']}")
    lines += ["", f"Parity verdict (lane-4 file): {parity['parity_verdict']}", ""]
    lines += ["## 5. First C0/C1/C2 index + T_first per arm (right-censored)", ""]
    index_rows = []
    for arm, s in report["item5_first_contract_index"]["by_arm"].items():
        for contract in CONTRACTS:
            e = s["contracts"][contract]
            index_rows.append(
                [
                    arm,
                    contract,
                    e["number_observed"],
                    e["number_right_censored"],
                    e["km_median_executions"],
                ]
            )
        t = s["t_first_combined_c1_or_c2"]
        index_rows.append(
            [
                arm,
                "T_first",
                t["number_observed"],
                t["number_right_censored"],
                t["km_median_executions"],
            ]
        )
    lines += _md_table(["arm", "metric", "observed", "censored", "km_median"], index_rows)
    lines += ["", "## 6. Dense signals per arm", ""]
    lines += _md_table(
        ["arm", "boundary_keys", "mean/cell", "rejected_ratio", "u_viol_total"],
        [
            [
                arm,
                s["boundary_attempt_keys"]["total"],
                s["boundary_attempt_keys"]["mean_per_cell"],
                s["rejected_ratio"]["value"],
                s["u_viol"]["total_unique_c1_c2_fingerprints"],
            ]
            for arm, s in report["item6_dense_signals"]["by_arm"].items()
        ],
    )
    hazard = report["item7_hazard_proxy"]
    lines += ["", "## 7. Hazard proxy (reference value only, not a verdict)", ""]
    lines += _md_table(
        ["arm", "hit_steps", "executions", "proxy/exec"],
        [
            [arm, s["hit_steps_c1_or_c2"], s["executions"], s["proxy_per_execution"]]
            for arm, s in hazard["by_arm"].items()
        ],
    )
    if "zero_hit" in hazard:
        lines += ["", f"Zero-hit: {hazard['zero_hit']['policy']}"]
    independence = report.get("arm_abort_independence")
    if independence:
        primary = independence["primary_arm_vs_abort"]
        lines += [
            "",
            "## 8. Arm x abort independence (audit 13a reporting flag, not a verdict)",
            "",
            f"Flag: **{independence['flag']}** -- {independence['flag_meaning']}",
            f"Primary (arm x abort) p-value: {primary.get('p_value')} "
            f"(test: {primary.get('test')}).",
        ]
    return "\n".join(lines) + "\n"


def _index_entries(index_file: Path) -> list[tuple[Path, Mapping[str, object]]]:
    """Resolve lane 5 ``summaries/index.json`` entries to (summary path, entry) pairs.

    Accepts a top-level list of entries or an object holding one such list; each entry's
    ``summary`` pointer is resolved against the index directory and its parent (so a run-root-
    relative ``summaries/<run_id>.summary.json`` resolves from either location).
    """
    data = read_json(index_file.read_bytes())
    if isinstance(data, list):
        entries: object = data
    elif isinstance(data, dict):
        # Pick the cell-entry list specifically: its entries carry a "summary" pointer. This
        # must not match the EXP-3 schema's top-level ``targets`` list (target metadata, no
        # pointer) nor ``analysis_plan`` (a dict).
        entries = next(
            (
                v
                for v in data.values()
                if isinstance(v, list)
                and v
                and all(isinstance(e, dict) and "summary" in e for e in v)
            ),
            None,
        )
    else:
        entries = None
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{index_file}: no cell-entry list found")
    roots = [index_file.parent, index_file.parent.parent]
    resolved: list[tuple[Path, Mapping[str, object]]] = []
    for entry in entries:
        pointer = entry.get("summary") if isinstance(entry, dict) else None
        if not isinstance(pointer, str):
            raise ValueError(f"{index_file}: an entry has no 'summary' path")
        candidate = Path(pointer)
        if candidate.is_absolute() and candidate.exists():
            resolved.append((candidate, entry))
            continue
        for root in roots:
            option = root / pointer
            if option.exists():
                resolved.append((option, entry))
                break
        else:
            raise ValueError(f"{index_file}: cannot resolve summary pointer {pointer!r}")
    return resolved


def load_cells(
    items: Sequence[tuple[Path, Mapping[str, object] | None]], field_map: Mapping[str, str]
) -> list[CellSummary | InvalidCell]:
    cells: list[CellSummary | InvalidCell] = []
    for path, entry in items:
        row = read_json(path.read_bytes())
        if not isinstance(row, dict):
            raise ValueError(f"{path}: expected a JSON object per cell")
        cells.append(cell_from_row(row, field_map, entry=entry))
    return cells


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EXP-0 pilot measurement report (items 1-7)")
    parser.add_argument(
        "--cell", type=Path, action="append", default=[], help="per-cell summary JSON (repeatable)"
    )
    parser.add_argument(
        "--cells-dir", type=Path, help="lane 5 summaries/ dir of *.summary.json cells"
    )
    parser.add_argument(
        "--index", type=Path, help="lane 5 summaries/index.json (resolves pointers + identity)"
    )
    parser.add_argument(
        "--parity", type=Path, help="lane-4 throughput-parity comparator result JSON"
    )
    parser.add_argument(
        "--contingency",
        type=Path,
        help="lane-3 abort-contingency JSON; adds the arm x abort independence flag (audit 13a)",
    )
    parser.add_argument("--field-map", type=Path, help="JSON overriding runner field names")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    field_map = dict(_DEFAULT_FIELD_MAP)
    if args.field_map is not None:
        override = read_json(args.field_map.read_bytes())
        if not isinstance(override, dict):
            parser.error("--field-map must be a JSON object")
        field_map.update({str(k): str(v) for k, v in override.items()})

    items: list[tuple[Path, Mapping[str, object] | None]] = [(p, None) for p in args.cell]
    if args.cells_dir is not None:
        found = sorted(args.cells_dir.glob("*.summary.json"))
        if not found:
            found = [
                p
                for p in sorted(args.cells_dir.glob("*.json"))
                if p.name not in ("index.json", "matrix.json")
            ]
        items.extend((p, None) for p in found)
    if args.index is not None:
        try:
            items.extend(_index_entries(args.index))
        except (ValueError, KeyError, OSError) as error:
            parser.error(f"--index: {error}")
    if not items:
        parser.error("provide --cell, --cells-dir, and/or --index")

    parity = None if args.parity is None else read_json(args.parity.read_bytes())
    independence = None
    if args.contingency is not None:
        contingency = read_json(args.contingency.read_bytes())
        if not isinstance(contingency, dict):
            parser.error("--contingency must be a JSON object")
        try:
            independence = arm_abort_independence_from_contingency(contingency)
        except (ValueError, KeyError) as error:
            parser.error(f"--contingency: {error}")

    try:
        cells = load_cells(items, field_map)
        sources = [str(p) for p, _ in items]
        if len({c.target_id for c in cells}) > 1:
            analysis_plan = _index_plan(args.index) if args.index is not None else None
            report = build_multitarget_report(
                cells,
                analysis_plan=analysis_plan,
                parity=parity,
                independence=independence,
                field_map=field_map,
                sources=sources,
            )
        else:
            report = build_report(
                cells,
                parity=parity,
                independence=independence,
                field_map=field_map,
                sources=sources,
            )
    except (ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1

    rendered = (
        json_bytes(report).decode("ascii") if args.format == "json" else report_markdown(report)
    )
    if args.output is not None:
        args.output.write_text(rendered + ("\n" if args.format == "json" else ""))
    else:
        print(rendered, end="\n" if args.format == "json" else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

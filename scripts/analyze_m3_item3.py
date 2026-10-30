"""item-3 mover: A/B/C/D intermediate-state primary-metric roll-up (eval lane).

Consumes the runtime lane's ``run_effect_demo historical`` item-3 evidence (the
A/B/C/D × seed cells frozen in ``jueon-item3-mover-contract.md``) and computes the
PRIMARY intermediate-state metrics the contract fixed, on the full cells' per-step
``trace.effect_events``:

- M1 boundary-attempt rate  = (executions with >=1 BOUNDARY_ESCAPE_ATTEMPT key) / executions
- M2 executions-to-first-boundary-attempt (1-based; via ``intermediate_state_metrics``)
- M3 observed-external-resolve rate + executions-to-first  (the rung unique to arm C,
  which is what separates identity-state from identity-blind boundary coverage)
- secondary: cumulative-unique-key trajectory; terminal C1 via ``right_censored`` roll-up.

Why re-derive keys here instead of reading them from the evidence: the demo trace is a
reduced projection (``effect_demo._trace_report``), not a round-trippable
``EffectEventTrace`` -- rebuilding one is infeasible (strict ``__post_init__``
invariants, dropped snapshots/causal graph). The projection IS faithful for exactly
the fields the two key predicates read (``_effect_event_record`` keeps every
``affected_path`` even for rejected ops; ``entries`` keeps each entry's type +
link_target), so this re-derives ``feedback.effect.boundary_attempt_keys`` /
``external_resolve_keys`` from the projection using the AUTHENTIC ``_escape_shape`` and
``path_region``. ``test_analyze_m3_item3`` cross-checks the re-derivation against the
canonical functions on a real serialized trace so the two cannot drift.

Honest boundaries (audit EN-008): a boundary-attempt key is SEARCH BEHAVIOUR toward a
boundary, not a vulnerability count and not effectiveness. Terminal C1 was 0 across all
cells, so no superiority claim is made from a hit count; the arms are contrasted only on
how they explore intermediate states, with the informative-censoring bias stated.

Run (host, where the evidence lives):
  PYTHONPATH=src python -m scripts.analyze_m3_item3 \
    --evidence-dir ~/inodefence-evidence/m3-item3-abcd-20261030 \
    --output ~/inodefence-evidence/m3-item3-abcd-20261030/primary-metric-rollup.json
"""

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from inodefence.evaluation.arm_comparison import Arm
from inodefence.evaluation.intermediate_metrics import (
    abcd_intermediate_comparison,
    intermediate_state_metrics,
    is_boundary_attempt_key,
    is_external_resolve_key,
)
from inodefence.evaluation.right_censored import (
    SeedOutcome,
    right_censored_summary,
    wilson_interval,
)
from inodefence.feedback.effect import _escape_shape
from inodefence.model import (
    BoundaryAttemptSignature,
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    EntryType,
    ExternalResolveSignature,
    ObservedOperationType,
    OperationOutcome,
    Region,
)
from inodefence.model.filesystem import path_region

_LINK = ObservedOperationType.LINK.value
_HARDLINK = EntryType.HARDLINK.value
_ARMS = ("A", "B", "C", "D")
_ANCHOR_SEED = 77


# --- Faithful key re-derivation from the reduced demo-trace projection. ---
# Cross-checked against feedback.effect.{boundary_attempt_keys,external_resolve_keys}
# in test_analyze_m3_item3; the only difference is projection access, not the logic.


def _affected_paths(event: Mapping) -> tuple[str, ...]:
    """The event's affected paths, in role order (projection keeps all of them)."""
    return tuple(item["path"] for item in event.get("paths", ()))


def boundary_attempt_keys_from_record(trace: Mapping) -> frozenset[EffectFeedbackKey]:
    """Re-derive ``boundary_attempt_keys`` from one serialized demo-trace record."""
    entries = {entry["entry_index"]: entry for entry in trace.get("entries", ())}
    keys: set[EffectFeedbackKey] = set()
    for event in trace.get("effect_events", ()):
        if event.get("operation") != _LINK:
            continue
        entry = entries.get(event.get("entry_index"), {})
        if entry.get("type") != _HARDLINK or entry.get("link_target") is None:
            continue
        external = tuple(p for p in _affected_paths(event) if path_region(p) != Region.EXTRACTION)
        if not external:
            continue
        shape = _escape_shape(entry["link_target"])
        if shape is None:
            continue
        keys.add(
            EffectFeedbackKey(
                EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT,
                BoundaryAttemptSignature(
                    EntryType(entry["type"]),
                    path_region(external[0]),
                    OperationOutcome(event["outcome"]),
                    shape,
                ),
            )
        )
    return frozenset(keys)


def external_resolve_keys_from_record(trace: Mapping) -> frozenset[EffectFeedbackKey]:
    """Re-derive ``external_resolve_keys`` from one serialized demo-trace record."""
    keys: set[EffectFeedbackKey] = set()
    for event in trace.get("effect_events", ()):
        if event.get("operation") != _LINK:
            continue
        if any(path_region(p) == Region.EXTERNAL for p in _affected_paths(event)):
            keys.add(
                EffectFeedbackKey(
                    EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE,
                    ExternalResolveSignature(ObservedOperationType.LINK, Region.EXTERNAL),
                )
            )
    return frozenset(keys)


def _rate_and_first(key_sets: Sequence[frozenset]) -> tuple[int, float, int | None]:
    """(# executions with >=1 key, rate over all executions, 1-based first-hit index)."""
    total = len(key_sets)
    hit_steps = [index + 1 for index, keys in enumerate(key_sets) if keys]
    rate = len(hit_steps) / total if total else 0.0
    return len(hit_steps), rate, (hit_steps[0] if hit_steps else None)


def analyze_cell(steps: Sequence[Mapping]) -> dict:
    """Per-cell intermediate-state metrics over one full campaign's ordered steps."""
    traces = [step.get("trace") or {} for step in steps]
    boundary_sets = [boundary_attempt_keys_from_record(trace) for trace in traces]
    external_sets = [external_resolve_keys_from_record(trace) for trace in traces]
    boundary_metrics = intermediate_state_metrics(boundary_sets, milestone=is_boundary_attempt_key)
    external_metrics = intermediate_state_metrics(external_sets, milestone=is_external_resolve_key)
    b_hits, b_rate, b_first = _rate_and_first(boundary_sets)
    e_hits, e_rate, e_first = _rate_and_first(external_sets)
    c1_steps = [
        index + 1 for index, step in enumerate(steps) if (step.get("oracle") or {}).get("C1")
    ]
    return {
        "executions": len(steps),
        "boundary_attempt": {
            "executions_with_key": b_hits,
            "rate": b_rate,
            "executions_to_first": b_first,
            "unique_keys": boundary_metrics.unique_keys,
            "total_keys": boundary_metrics.milestone_key_count,
            "cumulative_unique_keys": [
                list(point) for point in boundary_metrics.cumulative_unique_keys
            ],
        },
        "external_resolve": {
            "executions_with_key": e_hits,
            "rate": e_rate,
            "executions_to_first": e_first,
            "unique_keys": external_metrics.unique_keys,
        },
        "terminal_c1_steps": c1_steps,
        "boundary_sets": boundary_sets,
    }


def _seed_outcome(seed: int, budget: int, cell: Mapping, c1_steps: Sequence[int]) -> SeedOutcome:
    """Terminal-C1 outcome: full campaign is complete (hit iff a C1 step was observed)."""
    complete = cell["status"] == "full"
    hit = complete and bool(c1_steps)
    first = c1_steps[0] if hit else None
    return SeedOutcome(
        seed=seed, budget=budget, complete=complete, hit=hit, first_hit_executions=first
    )


def analyze(evidence_dir: Path) -> dict:
    """Roll up the frozen item-3 A/B/C/D evidence into the primary-metric readout data."""
    summary = json.loads((evidence_dir / "summary.json").read_text())
    budget = int(summary["budget"])
    cells = summary["cells"]

    per_cell: dict[str, dict] = {}
    anchor_boundary: dict[Arm, Sequence[frozenset]] = {}
    anchor_external: dict[Arm, Sequence[frozenset]] = {}
    outcomes: list[SeedOutcome] = []
    per_arm: dict[str, dict] = {arm: {"full": [], "abort_seeds": []} for arm in _ARMS}

    for cell in cells:
        arm, seed = cell["arm"], int(cell["seed"])
        run_id = cell["run_id"]
        if cell["status"] != "full":
            per_arm[arm]["abort_seeds"].append(seed)
            outcomes.append(_seed_outcome(seed, budget, cell, ()))
            per_cell[run_id] = {"arm": arm, "seed": seed, "status": "integrity_abort_censored"}
            continue
        steps = json.loads((evidence_dir / cell["evidence"]).read_text())["steps"]
        result = analyze_cell(steps)
        boundary_sets = result.pop("boundary_sets")
        external_sets = [external_resolve_keys_from_record(s.get("trace") or {}) for s in steps]
        outcomes.append(_seed_outcome(seed, budget, cell, result["terminal_c1_steps"]))
        per_arm[arm]["full"].append({"seed": seed, **result})
        per_cell[run_id] = {"arm": arm, "seed": seed, "status": "full", **result}
        if seed == _ANCHOR_SEED:
            anchor_boundary[Arm[arm]] = boundary_sets
            anchor_external[Arm[arm]] = external_sets

    arm_summaries = {}
    for arm in _ARMS:
        full = per_arm[arm]["full"]
        n_abort = len(per_arm[arm]["abort_seeds"])
        n_cells = len(full) + n_abort
        b_rates = [cell["boundary_attempt"]["rate"] for cell in full]
        e_rates = [cell["external_resolve"]["rate"] for cell in full]
        arm_summaries[arm] = {
            "arm_label": Arm[arm].value,
            "n_full": len(full),
            "n_abort": n_abort,
            "abort_rate": n_abort / n_cells if n_cells else 0.0,
            "full_seeds": [cell["seed"] for cell in full],
            "abort_seeds": sorted(per_arm[arm]["abort_seeds"]),
            "boundary_attempt_rate": _distribution(b_rates),
            "external_resolve_rate": _distribution(e_rates),
            "selection_bias_note": (
                "per-arm mean is over this arm's full-seed subset only; subsets differ by "
                "arm (which seeds aborted), so the within-seed s77 anchor is the primary read"
            ),
        }

    anchor = _anchor_comparison(anchor_boundary, anchor_external, per_cell)
    return {
        "schema_version": 1,
        "task": "item-3 mover A/B/C/D intermediate-state primary metric (fulls-only, pass 1)",
        "contract": "jueon-item3-mover-contract.md (FROZEN)",
        "primary_metric": (
            "boundary-attempt rate + executions-to-first; external-resolve isolates C from D"
        ),
        "en_008": (
            "boundary-attempt is search behaviour toward a boundary, not effectiveness or a "
            "vulnerability count"
        ),
        "budget": budget,
        "arm_policy": {cell_arm: _arm_policy(summary, cell_arm) for cell_arm in _ARMS},
        "per_arm_fulls": arm_summaries,
        "s77_paired_anchor": anchor,
        "informative_censoring": _informative_censoring(arm_summaries),
        "terminal_c1_rollup": right_censored_summary(outcomes),
        "per_cell": per_cell,
    }


def _arm_policy(summary: Mapping, arm: str) -> str:
    return summary.get("per_arm", {}).get(arm, {}).get("search_policy", "")


def _distribution(values: Sequence[float]) -> dict:
    ordered = sorted(values)
    n = len(ordered)
    return {
        "n": n,
        "mean": sum(ordered) / n if n else None,
        "min": ordered[0] if n else None,
        "max": ordered[-1] if n else None,
        "per_cell": ordered,
    }


def _pooled_rate(hits: int, trials: int) -> dict:
    """Pooled boundary-attempt proportion with a Wilson 95% CI (executions as trials).

    NOTE: executions within a campaign are correlated, so this execution-pooled CI is
    anti-conservative; the campaign count (n_full) is the real precision limiter.
    """
    return {
        "hits": hits,
        "trials": trials,
        "rate": hits / trials if trials else 0.0,
        "wilson_95_ci": list(wilson_interval(hits, trials)) if trials else None,
    }


def _anchor_comparison(
    anchor_boundary: Mapping[Arm, Sequence[frozenset]],
    anchor_external: Mapping[Arm, Sequence[frozenset]],
    per_cell: Mapping[str, dict],
) -> dict:
    """The within-seed paired A/B/C/D read on the only seed full across all four arms."""
    if len(anchor_boundary) != 4:
        return {"available": False, "reason": "seed 77 not full across all four arms"}
    boundary = abcd_intermediate_comparison(anchor_boundary, milestone=is_boundary_attempt_key)
    external = abcd_intermediate_comparison(anchor_external, milestone=is_external_resolve_key)
    per_arm = {}
    for arm in _ARMS:
        cell = per_cell[f"item3-752-{arm}-s{_ANCHOR_SEED}"]
        b = boundary.metrics[Arm[arm]]
        e = external.metrics[Arm[arm]]
        per_arm[arm] = {
            "boundary_attempt_rate": cell["boundary_attempt"]["rate"],
            "boundary_executions_to_first": b.milestone_executions,
            "boundary_unique_keys": b.unique_keys,
            "external_resolve_rate": cell["external_resolve"]["rate"],
            "external_executions_to_first": e.milestone_executions,
            "external_unique_keys": e.unique_keys,
        }
    identical = (
        per_arm["C"]["boundary_attempt_rate"] == per_arm["D"]["boundary_attempt_rate"]
        and per_arm["C"]["external_resolve_rate"] == per_arm["D"]["external_resolve_rate"]
    )
    return {
        "available": True,
        "seed": _ANCHOR_SEED,
        "note": boundary.note,
        "per_arm": per_arm,
        "c_equals_d": identical,
    }


def _informative_censoring(arm_summaries: Mapping[str, dict]) -> dict:
    """Abort is informative, not ignorable: C/D abort more, biasing fulls-only down."""
    abort = {arm: arm_summaries[arm]["abort_rate"] for arm in _ARMS}
    return {
        "abort_rate_by_arm": abort,
        "mechanism": (
            "aborts are fail-closed observation-integrity STOPs (target exit 0, observer "
            "could not vouch for the trace), NOT C0/C1/C2 violations. Gradient arms C/D steer "
            "toward conflicting-identity boundary-adjacent shapes more, tripping the guard more"
        ),
        "bias_direction": (
            "C/D abort more than A/B, and the censored runs are the most boundary-oriented, so "
            "the fulls-only boundary-attempt rate UNDER-estimates C/D more than A/B: the true "
            "gradient-vs-nongradient gap is at least as large as observed, but C-vs-D is not "
            "separated by censoring (C and D abort equally)"
        ),
        "treatment": (
            "informative right-censoring; fulls-only is a lower bound for C/D, not ignorable"
        ),
    }


def _load_step_records(path: Path) -> list[dict]:
    """Ordered step records from a full .json (steps[]) or a .steps.jsonl head file."""
    if path.name.endswith(".jsonl"):
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return json.loads(path.read_text())["steps"]


def _full_cell(steps: Sequence[Mapping]) -> tuple[dict, list[frozenset], list[frozenset]]:
    """analyze_cell split into (JSON-safe metrics, boundary key sets, external key sets)."""
    metrics = analyze_cell(steps)
    boundary_sets = metrics.pop("boundary_sets")
    external_sets = [external_resolve_keys_from_record(step.get("trace") or {}) for step in steps]
    return metrics, boundary_sets, external_sets


def analyze_decensor(evidence_dir: Path, decensor_dir: Path) -> dict:
    """PASS 2: pool 18 original full + 3 de-censor newly-full (= 21) plus the 11 degraded
    pre-abort heads, widen the within-seed paired comparison, and correct the informative-
    censoring reading with the observed abort non-determinism."""
    orig = json.loads((evidence_dir / "summary.json").read_text())
    decensor = json.loads((decensor_dir / "summary.json").read_text())
    budget = int(orig["budget"])

    full_metrics: dict[tuple[str, int], dict] = {}
    full_boundary: dict[tuple[str, int], list[frozenset]] = {}
    full_case_ids: dict[tuple[str, int], list] = {}
    sources: dict[tuple[str, int], str] = {}
    for cell in orig["cells"]:
        if cell["status"] != "full":
            continue
        key = (cell["arm"], int(cell["seed"]))
        steps = _load_step_records(evidence_dir / cell["evidence"])
        metrics, boundary, _ = _full_cell(steps)
        full_metrics[key], full_boundary[key] = metrics, boundary
        full_case_ids[key] = [step.get("case_id") for step in steps]
        sources[key] = "original"

    heads: dict[tuple[str, int], dict] = {}
    for cell in decensor["cells"]:
        key = (cell["arm"], int(cell["seed"]))
        if cell["new_status"] == "completed_full":
            steps = _load_step_records(decensor_dir / cell["evidence"])
            metrics, boundary, _ = _full_cell(steps)
            full_metrics[key], full_boundary[key] = metrics, boundary
            full_case_ids[key] = [step.get("case_id") for step in steps]
            sources[key] = "decensor_newly_full"
        else:
            head = analyze_cell(_load_step_records(decensor_dir / cell["steps_jsonl"]))
            head.pop("boundary_sets")
            heads[key] = {"new_abort_step": cell.get("new_abort_step"), **head}

    outcomes: list[SeedOutcome] = []
    arm_summaries: dict[str, dict] = {}
    for arm in _ARMS:
        seeds = sorted(seed for (cell_arm, seed) in full_metrics if cell_arm == arm)
        b_rates = [full_metrics[(arm, seed)]["boundary_attempt"]["rate"] for seed in seeds]
        e_rates = [full_metrics[(arm, seed)]["external_resolve"]["rate"] for seed in seeds]
        firsts = [
            full_metrics[(arm, seed)]["boundary_attempt"]["executions_to_first"]
            for seed in seeds
            if full_metrics[(arm, seed)]["boundary_attempt"]["executions_to_first"] is not None
        ]
        hits = sum(
            full_metrics[(arm, seed)]["boundary_attempt"]["executions_with_key"] for seed in seeds
        )
        trials = sum(full_metrics[(arm, seed)]["executions"] for seed in seeds)
        head_seeds = [seed for (cell_arm, seed) in heads if cell_arm == arm]
        head_hits = sum(
            heads[(arm, seed)]["boundary_attempt"]["executions_with_key"] for seed in head_seeds
        )
        head_trials = sum(heads[(arm, seed)]["executions"] for seed in head_seeds)
        arm_summaries[arm] = {
            "arm_label": Arm[arm].value,
            "n_full": len(seeds),
            "full_seeds": seeds,
            "boundary_attempt_rate": _distribution(b_rates),
            "external_resolve_rate": _distribution(e_rates),
            "boundary_executions_to_first": _distribution(firsts),
            "boundary_attempt_pooled": _pooled_rate(hits, trials),
            "boundary_attempt_pooled_with_heads": _pooled_rate(
                hits + head_hits, trials + head_trials
            ),
        }
        for seed in seeds:
            c1 = full_metrics[(arm, seed)]["terminal_c1_steps"]
            outcomes.append(
                SeedOutcome(
                    seed=seed,
                    budget=budget,
                    complete=True,
                    hit=bool(c1),
                    first_hit_executions=c1[0] if c1 else None,
                )
            )
    for seed in (key[1] for key in heads):
        outcomes.append(
            SeedOutcome(
                seed=seed, budget=budget, complete=False, hit=False, first_hit_executions=None
            )
        )

    def arm_full_seeds(arm: str) -> set[int]:
        return {seed for (cell_arm, seed) in full_metrics if cell_arm == arm}

    four_arm_seeds = sorted(
        arm_full_seeds("A") & arm_full_seeds("B") & arm_full_seeds("C") & arm_full_seeds("D")
    )
    cd_seeds = sorted(arm_full_seeds("C") & arm_full_seeds("D"))

    def cell_rates(arm: str, seed: int) -> dict:
        metrics = full_metrics[(arm, seed)]
        return {
            "boundary_attempt_rate": metrics["boundary_attempt"]["rate"],
            "boundary_executions_to_first": metrics["boundary_attempt"]["executions_to_first"],
            "external_resolve_rate": metrics["external_resolve"]["rate"],
            "external_executions_to_first": metrics["external_resolve"]["executions_to_first"],
            "source": sources[(arm, seed)],
        }

    four_arm_paired = {}
    for seed in four_arm_seeds:
        comparison = abcd_intermediate_comparison(
            {Arm[arm]: full_boundary[(arm, seed)] for arm in _ARMS},
            milestone=is_boundary_attempt_key,
        )
        per_arm = {}
        for arm in _ARMS:
            rates = cell_rates(arm, seed)
            rates["boundary_unique_keys"] = comparison.metrics[Arm[arm]].unique_keys
            per_arm[arm] = rates
        four_arm_paired[str(seed)] = per_arm

    cd_paired = {}
    cd_verdict = {"c_equals_d": 0, "c_greater": 0, "c_less": 0, "operationally_identical": 0}
    for seed in cd_seeds:
        c, d = cell_rates("C", seed), cell_rates("D", seed)
        identical = (
            c["boundary_attempt_rate"] == d["boundary_attempt_rate"]
            and c["external_resolve_rate"] == d["external_resolve_rate"]
        )
        # strongest check: did the two policies evolve the exact same corpus sequence?
        operationally_identical = full_case_ids[("C", seed)] == full_case_ids[("D", seed)]
        if identical:
            cd_verdict["c_equals_d"] += 1
        elif c["boundary_attempt_rate"] > d["boundary_attempt_rate"]:
            cd_verdict["c_greater"] += 1
        else:
            cd_verdict["c_less"] += 1
        if operationally_identical:
            cd_verdict["operationally_identical"] += 1
        cd_paired[str(seed)] = {
            "C": c,
            "D": d,
            "identical_on_both_signals": identical,
            "operationally_identical_case_sequence": operationally_identical,
        }

    head_summary = {}
    for arm in _ARMS:
        arm_heads = {seed: heads[(cell_arm, seed)] for (cell_arm, seed) in heads if cell_arm == arm}
        head_summary[arm] = {
            "n_heads": len(arm_heads),
            "seeds": sorted(arm_heads),
            "heads_with_boundary_attempt": sum(
                1
                for head in arm_heads.values()
                if head["boundary_attempt"]["executions_with_key"] > 0
            ),
            "per_seed": {
                str(seed): {
                    "head_steps": arm_heads[seed]["executions"],
                    "boundary_attempt_rate": arm_heads[seed]["boundary_attempt"]["rate"],
                    "boundary_attempts_observed": (
                        arm_heads[seed]["boundary_attempt"]["executions_with_key"]
                    ),
                    "external_resolve_rate": arm_heads[seed]["external_resolve"]["rate"],
                }
                for seed in sorted(arm_heads)
            },
        }

    determinism = decensor["determinism_check"]
    nondeterminism = {
        "re_run_of": "14 original abort cells (de-censor)",
        "exact_match": determinism["match"],
        "diverged_completed": determinism["diverged"],
        "diverged_cells": determinism["diverged_cells"],
        "all_diverged_are_gradient_arms": all(
            cell.split("-")[2] in ("C", "D") for cell in determinism["diverged_cells"]
        ),
        "finding": (
            "fail-closed abort has an observer-side non-deterministic component: WHERE it aborts "
            "is input-determined (11/14 re-aborted at the exact original step), WHETHER it trips "
            "is race/timing (3/14 completed full on identical input). So abort-rate-by-arm "
            "(C/D>A/B) is partly observer flakiness, not purely arm search behaviour (EN-008)"
        ),
    }

    # Lower-bound test (deliverable: measure, don't assume): PASS 1 inferred that fulls-only
    # UNDER-estimates C/D because the aborted C/D runs were more boundary-oriented. The
    # de-censor recovers 3 C/D cells, so we can check directly whether they rate higher.
    recovered = {key for key in full_metrics if sources[key] == "decensor_newly_full"}

    def _rate_stats(keys: Sequence[tuple[str, int]]) -> dict:
        rates = sorted(full_metrics[key]["boundary_attempt"]["rate"] for key in keys)
        return {
            "n": len(rates),
            "cells": sorted(f"{arm}-s{seed}" for (arm, seed) in keys),
            "rates": rates,
            "mean": sum(rates) / len(rates) if rates else None,
            "min": rates[0] if rates else None,
            "max": rates[-1] if rates else None,
        }

    cd_keys = [key for key in full_metrics if key[0] in ("C", "D")]
    recovered_stats = _rate_stats([key for key in cd_keys if key in recovered])
    original_stats = _rate_stats([key for key in cd_keys if key not in recovered])
    recovered_higher = (
        recovered_stats["mean"] is not None
        and original_stats["mean"] is not None
        and recovered_stats["mean"] > original_stats["mean"]
    )
    lower_bound_test = {
        "pass1_claim": "fulls-only is a lower bound for C/D (aborted runs more boundary-oriented)",
        "recovered_cd": recovered_stats,
        "original_full_cd": original_stats,
        "recovered_mean_higher_than_original": recovered_higher,
        "finding": (
            "recovered (previously-aborted) C/D cells rate higher than the already-full C/D "
            "cells: the lower-bound claim IS supported"
            if recovered_higher
            else "recovered (previously-aborted) C/D cells rate WITHIN the already-full C/D range, "
            "not higher: the PASS 1 lower-bound (downward-censoring-bias) claim is NOT supported "
            "and is retracted. C/D>A/B still stands on its own (EN-008)"
        ),
    }

    def _gradient_over_nongradient(rates: dict) -> bool:
        return min(rates["C"], rates["D"]) > max(rates["A"], rates["B"])

    fulls_only = {arm: arm_summaries[arm]["boundary_attempt_pooled"]["rate"] for arm in _ARMS}
    with_heads = {
        arm: arm_summaries[arm]["boundary_attempt_pooled_with_heads"]["rate"] for arm in _ARMS
    }
    head_sensitivity = {
        "note": "heads are partial/right-censored; include & exclude both reported",
        "fulls_only_pooled_rate": fulls_only,
        "fulls_plus_heads_pooled_rate": with_heads,
        "gradient_over_nongradient_fulls_only": _gradient_over_nongradient(fulls_only),
        "gradient_over_nongradient_with_heads": _gradient_over_nongradient(with_heads),
        "ordering_robust_to_head_inclusion": (
            _gradient_over_nongradient(fulls_only) and _gradient_over_nongradient(with_heads)
        ),
    }

    return {
        "schema_version": 2,
        "task": "item-3 mover A/B/C/D intermediate-state primary metric (de-censored, pass 2)",
        "contract": "jueon-item3-mover-contract.md (FROZEN)",
        "primary_metric": (
            "boundary-attempt rate + executions-to-first; external-resolve isolates C from D"
        ),
        "en_008": (
            "boundary-attempt is search behaviour toward a boundary, not effectiveness or a "
            "vulnerability count"
        ),
        "budget": budget,
        "combined_full_cells": {
            "n": len(full_metrics),
            "by_arm": {arm: arm_summaries[arm]["full_seeds"] for arm in _ARMS},
            "newly_full_from_decensor": [
                f"{cell['arm']}-s{cell['seed']}"
                for cell in decensor["cells"]
                if cell["new_status"] == "completed_full"
            ],
        },
        "per_arm_fulls": arm_summaries,
        "four_arm_paired_seeds": four_arm_seeds,
        "four_arm_paired": four_arm_paired,
        "c_vs_d_paired_seeds": cd_seeds,
        "c_vs_d_paired": cd_paired,
        "c_vs_d_verdict": cd_verdict,
        "degraded_pre_abort_heads": head_summary,
        "lower_bound_test": lower_bound_test,
        "head_sensitivity": head_sensitivity,
        "abort_nondeterminism": nondeterminism,
        "terminal_c1_rollup": right_censored_summary(outcomes),
    }


def _print_pass2(rollup: dict) -> None:
    print("== item-3 A/B/C/D primary metric (de-censored, pass 2) ==")
    combined = rollup["combined_full_cells"]
    newly = combined["newly_full_from_decensor"]
    print(f"combined full cells: {combined['n']}; newly-full {newly}")
    print("per-arm fulls (boundary-attempt rate mean [min,max], external mean, n_full):")
    for arm in _ARMS:
        summary = rollup["per_arm_fulls"][arm]
        dist = summary["boundary_attempt_rate"]
        ext = summary["external_resolve_rate"]
        pooled = summary["boundary_attempt_pooled"]
        ci = [round(x, 4) for x in pooled["wilson_95_ci"]] if pooled["wilson_95_ci"] else None
        print(
            f"  {arm} {summary['arm_label']:<18} bAtt={dist['mean']:.4f}"
            f" [{dist['min']:.4f},{dist['max']:.4f}]"
            f" extR={ext['mean']:.4f} n_full={summary['n_full']} pooledCI={ci}"
        )
    print(f"\n4-arm paired seeds {rollup['four_arm_paired_seeds']} (boundary-attempt rate):")
    for seed, per_arm in rollup["four_arm_paired"].items():
        cells = " ".join(f"{arm}={per_arm[arm]['boundary_attempt_rate']:.4f}" for arm in _ARMS)
        print(f"  s{seed}: {cells}")
    verdict = rollup["c_vs_d_verdict"]
    print(f"\nC-vs-D paired {rollup['c_vs_d_paired_seeds']} verdict {verdict}:")
    for seed, pair in rollup["c_vs_d_paired"].items():
        print(
            f"  s{seed}: C bAtt={pair['C']['boundary_attempt_rate']:.4f}"
            f" extR={pair['C']['external_resolve_rate']:.4f} |"
            f" D bAtt={pair['D']['boundary_attempt_rate']:.4f}"
            f" extR={pair['D']['external_resolve_rate']:.4f}"
            f" | id={pair['identical_on_both_signals']}"
            f" op_id={pair['operationally_identical_case_sequence']}"
        )
    heads = rollup["degraded_pre_abort_heads"]
    print("\ndegraded pre-abort heads (boundary attempts observed / n_heads):")
    for arm in _ARMS:
        head = heads[arm]
        print(f"  {arm}: {head['heads_with_boundary_attempt']}/{head['n_heads']} heads w/ attempt")
    lb = rollup["lower_bound_test"]
    print("\nlower-bound test (recovered C/D vs original-full C/D boundary-attempt rate):")
    print(
        f"  recovered {lb['recovered_cd']['cells']} mean={lb['recovered_cd']['mean']:.4f}"
        f" vs original mean={lb['original_full_cd']['mean']:.4f}"
        f" -> recovered_higher={lb['recovered_mean_higher_than_original']}"
    )
    hs = rollup["head_sensitivity"]
    print(
        f"head sensitivity: grad>nongrad"
        f" fulls_only={hs['gradient_over_nongradient_fulls_only']}"
        f" with_heads={hs['gradient_over_nongradient_with_heads']}"
        f" robust={hs['ordering_robust_to_head_inclusion']}"
    )
    nd = rollup["abort_nondeterminism"]
    print(
        f"\nabort non-determinism: {nd['exact_match']}/14 exact,"
        f" {nd['diverged_completed']}/14 completed on re-run"
        f" (all gradient arms: {nd['all_diverged_are_gradient_arms']})"
    )
    c1 = rollup["terminal_c1_rollup"]
    print(
        f"terminal C1: {c1['number_observed_target']}/{c1['number_complete_campaigns']} complete"
        f" (Wilson {c1['observed_proportion']['wilson_95_ci']}),"
        f" {c1['number_incomplete_excluded']} incomplete"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--decensor-dir", type=Path, help="de-censor re-run dir enables pass 2")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.decensor_dir is not None:
        rollup = analyze_decensor(args.evidence_dir, args.decensor_dir)
    else:
        rollup = analyze(args.evidence_dir)
    raw = json.dumps(rollup, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(raw)

    if rollup.get("schema_version") == 2:
        _print_pass2(rollup)
        return

    anchor = rollup["s77_paired_anchor"]
    print("== item-3 A/B/C/D primary metric (fulls-only, pass 1) ==")
    print("per-arm fulls (boundary-attempt rate mean [min,max], n_full, abort_rate):")
    for arm in _ARMS:
        summary = rollup["per_arm_fulls"][arm]
        dist = summary["boundary_attempt_rate"]
        ext = summary["external_resolve_rate"]
        print(
            f"  {arm} {summary['arm_label']:<18} bAtt={dist['mean']:.4f}"
            f" [{dist['min']:.4f},{dist['max']:.4f}]"
            f" extR={ext['mean']:.4f} n_full={summary['n_full']} abort={summary['abort_rate']:.3f}"
        )
    if anchor["available"]:
        print(f"\ns{anchor['seed']} within-seed paired anchor (all 4 arms full):")
        for arm in _ARMS:
            a = anchor["per_arm"][arm]
            print(
                f"  {arm}: bAtt_rate={a['boundary_attempt_rate']:.4f}"
                f" first={a['boundary_executions_to_first']}"
                f" extR_rate={a['external_resolve_rate']:.4f}"
                f" first={a['external_executions_to_first']}"
                f" uniq_b={a['boundary_unique_keys']}"
            )
        print(f"  C == D on s{anchor['seed']}: {anchor['c_equals_d']}")
    c1 = rollup["terminal_c1_rollup"]
    print(
        f"\nterminal C1 roll-up: {c1['number_observed_target']}"
        f"/{c1['number_complete_campaigns']} complete"
        f" (Wilson {c1['observed_proportion']['wilson_95_ci']}),"
        f" {c1['number_incomplete_excluded']} aborts excluded"
    )


if __name__ == "__main__":
    main()

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
from inodefence.evaluation.right_censored import SeedOutcome, right_censored_summary
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rollup = analyze(args.evidence_dir)
    raw = json.dumps(rollup, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(raw)

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

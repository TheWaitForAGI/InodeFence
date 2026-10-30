"""M3.3 A1 random-control right-censored roll-up from the runtime lane's summary.

Consumes the runtime lane's per-seed determination (its ``summary.json``: which seeds
completed the full budget, which fail-closed-aborted, and which observed a clean exact
C1) and produces the EVALUATION-lane statistical roll-up via
``evaluation.right_censored``. It does not re-derive the clean-C1 determination from
raw traces -- that is the runtime lane's call; this is the stats layer over its facts.

This is a SINGLE-ARM control, so it makes no rate or effectiveness claim (audit
EN-008): a few complete campaigns with 0 hits over a wide small-sample Wilson interval
is not a rate, and the research argument is the causal CONTRAST with the
identity-feedback arm (the effect-path, recorded in STATUS M3), not this arm's rate. It
is incremental: pass several ``--summary`` files to pool consecutive batches as they
seal (``merge_summaries``); a partial/growing set is reported as such, never concluded
as if complete.

Terminology: the runtime summary labels its fail-closed aborts
``right_censored_abort_seeds`` (survival-sense censoring at the abort step). This
roll-up instead classifies them as infrastructure-incomplete and excludes them from the
complete-campaign rate denominator, per ``evaluation-protocol-v1`` (an infrastructure
abort is not ordinary within-budget no-hit censoring); each is reported separately and
observed 0 before its abort. The complete no-hit campaigns are the ones this roll-up
reports as right-censored at the budget horizon N.

  uv run python -m scripts.analyze_m3_3_control --summary <dir>/summary.json [...] [--output <file>]
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from inodefence.evaluation.right_censored import (
    SeedOutcome,
    right_censored_summary,
    wilson_interval,
)

_FRAMING = (
    "single-arm random control: 0 clean exact C1 observed. The Wilson interval on "
    "complete campaigns is wide at this sample size, so this is NOT a rate or "
    "effectiveness claim (audit EN-008); the argument is the causal contrast with the "
    "identity-feedback arm (effect-path, STATUS M3), not this arm's rate. Fail-closed "
    "aborts are infrastructure-incomplete (observation-integrity STOP), excluded from "
    "the complete-campaign denominator per evaluation-protocol-v1 and reported "
    "separately, each having observed 0 before its abort. Batch coverage is "
    "incremental; a partial set is not a conclusion."
)
_RUNTIME_KEYS = (
    "task",
    "arm",
    "budget",
    "version",
    "seeds",
    "observed_executions",
    "clean_exact_c1_total",
    "seeds_with_clean_exact_c1",
    "completed_full_budget",
    "right_censored_abort_seeds",
    "config_nonconformant_seeds",
    "hit_criterion",
    "note",
    "pooled_batches",
)
_POOL_INVARIANT_KEYS = ("budget", "version", "arm", "hit_criterion")


def merge_summaries(summaries: Sequence[dict]) -> dict:
    """Pool consecutive, DISJOINT per-batch runtime summaries into one summary dict.

    The batches are consecutive-seed slices of one control arm, so they must share the
    arm/target/budget and cover non-overlapping seeds. Overlapping seeds would
    double-count and a differing arm/budget would pool unlike runs, so either raises
    rather than silently combining. The result has the same shape build_outcomes/analyze
    consume -- concatenated seed-indexed fields, summed totals -- plus a pooled_batches
    provenance list recording each batch's seeds, execution count, and timestamp.
    """
    if not summaries:
        raise ValueError("merge_summaries needs at least one summary")
    base = summaries[0]
    for other in summaries[1:]:
        for key in _POOL_INVARIANT_KEYS:
            if other.get(key) != base.get(key):
                raise ValueError(f"cannot pool batches that differ in {key!r}")
    seeds: list[int] = []
    seen: set[int] = set()
    for summary in summaries:
        for raw_seed in summary["seeds"]:
            seed = int(raw_seed)
            if seed in seen:
                raise ValueError(f"cannot pool batches with overlapping seed {seed}")
            seen.add(seed)
            seeds.append(seed)

    def _concat(key: str) -> list:
        pooled: list = []
        for summary in summaries:
            pooled.extend(summary.get(key, []))
        return pooled

    merged = dict(base)
    merged["seeds"] = seeds
    merged["completed_full_budget"] = _concat("completed_full_budget")
    merged["right_censored_abort_seeds"] = _concat("right_censored_abort_seeds")
    merged["seeds_with_clean_exact_c1"] = _concat("seeds_with_clean_exact_c1")
    merged["config_nonconformant_seeds"] = _concat("config_nonconformant_seeds")
    merged["cells"] = _concat("cells")
    merged["observed_executions"] = sum(
        int(summary.get("observed_executions", 0)) for summary in summaries
    )
    merged["clean_exact_c1_total"] = sum(
        int(summary.get("clean_exact_c1_total", 0)) for summary in summaries
    )
    merged["pooled_batches"] = [
        {
            "created_at": summary.get("created_at"),
            "seeds": [int(raw_seed) for raw_seed in summary["seeds"]],
            "observed_executions": int(summary.get("observed_executions", 0)),
        }
        for summary in summaries
    ]
    return merged


def build_outcomes(summary: dict) -> list[SeedOutcome]:
    """Map the runtime lane's per-seed determination to abstract SeedOutcome facts.

    A completed seed is a complete campaign; a fail-closed-abort seed is incomplete.
    A seed the runtime lane marks as a clean-exact-C1 hit needs a 1-based first-hit
    index from its cell; if one is marked without a resolvable index this raises,
    rather than inventing one.
    """
    budget = int(summary["budget"])
    completed = set(summary["completed_full_budget"])
    hit_seeds = set(summary["seeds_with_clean_exact_c1"])
    cells = {cell["seed"]: cell for cell in summary.get("cells", []) if "seed" in cell}
    outcomes = []
    for raw_seed in summary["seeds"]:
        seed = int(raw_seed)
        complete = seed in completed
        hit = seed in hit_seeds
        first_hit = None
        if hit:
            cell = cells.get(seed, {})
            first_hit = cell.get("clean_exact_c1_first_step") or cell.get("censor_step")
            if type(first_hit) is not int:
                raise ValueError(f"hit seed {seed} lacks a resolvable first-hit index")
        outcomes.append(
            SeedOutcome(
                seed=seed,
                budget=budget,
                complete=complete,
                hit=hit,
                first_hit_executions=first_hit,
            )
        )
    return outcomes


def analyze(summary: dict) -> dict:
    """Produce the eval-lane roll-up plus the runtime determination it was built on."""
    rollup = right_censored_summary(build_outcomes(summary))
    return {
        "classification": "m3.3-a1-random-control-rollup",
        "runtime_determination": {key: summary.get(key) for key in _RUNTIME_KEYS},
        "rollup": rollup,
        "framing": _FRAMING,
    }


_CONTRAST_FRAMING = (
    "matched two-arm causal contrast on shared seeds at one budget -- the comparison the "
    "single-arm roll-up explicitly defers to (audit EN-008). Each arm's rate is the committed "
    "right-censored complete-campaign roll-up (right_censored_summary, same engine as the "
    "single-arm path); a rate-superiority claim needs the two arms' Wilson intervals to "
    "SEPARATE, which 'complete_hit_wilson_intervals_separate' reports -- a difference in point "
    "counts alone is not one. A clean exact C1 observed before a fail-closed infrastructure "
    "abort is reported as an 'observed trigger', kept separate from the complete-campaign hit "
    "rate because a hit requires a complete campaign (the right_censored contract); it is an "
    "observed mechanism fact, not a rate."
)
_CONTRAST_INVARIANT_KEYS = ("budget", "version", "hit_criterion")


def _seed_cells(summary: dict) -> dict[int, dict]:
    """Index a summary's per-seed cells by seed (skips cells without a seed)."""
    return {int(cell["seed"]): cell for cell in summary.get("cells", []) if "seed" in cell}


def _arm_shared_aggregate(
    cells: dict[int, dict], complete: set[int], hit: set[int], shared: Sequence[int]
) -> dict:
    """One arm's complete-campaign rate and observed-trigger tally over the shared seeds.

    ``complete``/``hit`` are the summary's completed_full_budget / seeds_with_clean_exact_c1
    sets (a hit is already complete-only there, matching build_outcomes). The observed-trigger
    tally counts seeds whose cell recorded any clean exact C1, INCLUDING ones that later
    fail-closed-aborted -- those are observed mechanism facts, not complete-campaign hits.
    """
    complete_seeds = [seed for seed in shared if seed in complete]
    complete_hits = [seed for seed in shared if seed in hit]
    observed_trigger_seeds = [
        seed for seed in shared if int(cells.get(seed, {}).get("clean_exact_c1", 0)) > 0
    ]
    total_observed = sum(int(cells.get(seed, {}).get("clean_exact_c1", 0)) for seed in shared)
    if complete_seeds:
        low, high = wilson_interval(len(complete_hits), len(complete_seeds))
    else:
        low, high = None, None
    return {
        "shared_seeds": len(shared),
        "complete_campaigns": len(complete_seeds),
        "complete_campaign_hits": len(complete_hits),
        "complete_campaign_hit_seeds": complete_hits,
        "complete_hit_rate": len(complete_hits) / len(complete_seeds) if complete_seeds else None,
        "complete_hit_wilson_95_ci": [low, high],
        "observed_trigger_seeds": observed_trigger_seeds,
        "number_observed_trigger_seeds": len(observed_trigger_seeds),
        "total_observed_clean_exact_c1": total_observed,
    }


def matched_contrast(summary_a: dict, summary_b: dict) -> dict:
    """Contrast two arms' right-censored roll-ups on their shared seeds (the EN-008 contrast).

    Each arm is rolled up with the same committed ``right_censored`` engine the single-arm path
    uses. The per-seed matched table pairs the arms on the seeds both ran, separating a complete-
    campaign hit (which enters the rate) from a clean exact C1 observed before a fail-closed abort
    (an observed trigger, reported but not a complete hit). Raises if the arms differ in
    budget/version/hit-criterion (unlike runs, not a matched contrast) or carry the same arm label
    (not two arms).
    """
    for key in _CONTRAST_INVARIANT_KEYS:
        if summary_a.get(key) != summary_b.get(key):
            raise ValueError(f"cannot contrast arms that differ in {key!r}")
    label_a = (summary_a.get("arm") or {}).get("label")
    label_b = (summary_b.get("arm") or {}).get("label")
    if label_a is not None and label_a == label_b:
        raise ValueError("matched contrast needs two different arms, got the same label twice")

    cells_a, cells_b = _seed_cells(summary_a), _seed_cells(summary_b)
    complete_a = {int(seed) for seed in summary_a.get("completed_full_budget", [])}
    complete_b = {int(seed) for seed in summary_b.get("completed_full_budget", [])}
    hit_a = {int(seed) for seed in summary_a.get("seeds_with_clean_exact_c1", [])}
    hit_b = {int(seed) for seed in summary_b.get("seeds_with_clean_exact_c1", [])}
    shared = sorted(set(cells_a) & set(cells_b))

    def _row(seed: int, cells: dict[int, dict], complete: set[int], hit: set[int]) -> dict:
        cell = cells.get(seed, {})
        return {
            "complete": seed in complete,
            "complete_hit": seed in hit,
            "observed_clean_exact_c1": int(cell.get("clean_exact_c1", 0)),
            "status": cell.get("status"),
        }

    per_seed = [
        {
            "seed": seed,
            "arm_a": _row(seed, cells_a, complete_a, hit_a),
            "arm_b": _row(seed, cells_b, complete_b, hit_b),
        }
        for seed in shared
    ]
    agg_a = _arm_shared_aggregate(cells_a, complete_a, hit_a, shared)
    agg_b = _arm_shared_aggregate(cells_b, complete_b, hit_b, shared)
    ci_a = agg_a["complete_hit_wilson_95_ci"]
    ci_b = agg_b["complete_hit_wilson_95_ci"]
    separated = None not in ci_a and None not in ci_b and (ci_a[1] < ci_b[0] or ci_b[1] < ci_a[0])
    a_set = set(agg_a["observed_trigger_seeds"])
    b_set = set(agg_b["observed_trigger_seeds"])
    return {
        "classification": "m3.3-matched-two-arm-contrast",
        "arms": {"arm_a": label_a, "arm_b": label_b},
        "budget": summary_a.get("budget"),
        "version": summary_a.get("version"),
        "hit_criterion": summary_a.get("hit_criterion"),
        "arm_a_rollup": right_censored_summary(build_outcomes(summary_a)),
        "arm_b_rollup": right_censored_summary(build_outcomes(summary_b)),
        "shared_seeds": shared,
        "number_shared_seeds": len(shared),
        "per_seed": per_seed,
        "arm_a_shared": agg_a,
        "arm_b_shared": agg_b,
        "matched_discordant": {
            "arm_b_only_observed_trigger_seeds": sorted(b_set - a_set),
            "arm_a_only_observed_trigger_seeds": sorted(a_set - b_set),
            "both_observed_trigger_seeds": sorted(a_set & b_set),
        },
        "complete_hit_wilson_intervals_separate": separated,
        "framing": _CONTRAST_FRAMING,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        nargs="+",
        type=Path,
        help="single-arm roll-up: one or more disjoint batch summaries of ONE arm (pooled)",
    )
    parser.add_argument(
        "--contrast",
        nargs=2,
        type=Path,
        metavar=("ARM_A_SUMMARY", "ARM_B_SUMMARY"),
        help="matched two-arm causal contrast between two per-arm summaries",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if bool(args.summary) == bool(args.contrast):
        parser.error("pass exactly one of --summary (single-arm) or --contrast (two-arm)")
    if args.contrast is not None:
        summary_a = json.loads(args.contrast[0].read_text())
        summary_b = json.loads(args.contrast[1].read_text())
        result = matched_contrast(summary_a, summary_b)
    else:
        summaries = [json.loads(path.read_text()) for path in args.summary]
        summary = summaries[0] if len(summaries) == 1 else merge_summaries(summaries)
        result = analyze(summary)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()

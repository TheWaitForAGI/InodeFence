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

from inodefence.evaluation.right_censored import SeedOutcome, right_censored_summary

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    summaries = [json.loads(path.read_text()) for path in args.summary]
    summary = summaries[0] if len(summaries) == 1 else merge_summaries(summaries)
    result = analyze(summary)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()

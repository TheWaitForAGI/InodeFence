"""Generate a per-arm ``summary.json`` from raw M3 matched-run campaign JSONs.

This is the MISSING producer step upstream of ``scripts.analyze_m3_3_control``: that
analyzer consumes a per-arm ``summary.json`` (the runtime lane's per-seed
determination) but there was no committed script that DERIVES one from the raw
campaign JSONs -- prior summaries were hand-built by ad-hoc launchers. This script
scans one arm's campaign JSONs in an evidence directory and emits exactly the summary
dict that ``analyze_m3_3_control`` (both ``--summary`` and ``--contrast``) consumes.

What it determines, per seed, from the raw evidence (read-only; never modifies it):

* completed vs aborted -- a COMPLETED campaign JSON has a top-level ``steps`` list
  whose length equals the budget; an ABORTED one carries only an ``aborted`` stub
  (``aborted``/``label``/``mode``/``producer``/``requested_tar_version``) and no steps.
  Aborted campaigns are right-censored infrastructure-incomplete runs, excluded from
  the complete-campaign denominator (per evaluation-protocol-v1 / EN-008), reported
  separately as ``right_censored_abort_seeds``.

* per-seed ``clean_exact_c1`` -- the COUNT of steps whose rendered verdict is a clean
  exact C1, i.e. ``oracle.C1 is True AND contract_violated is True``. In this producer
  the per-step ``contract_violated`` flag is carried under ``step["feedback"]``
  (there is no top-level ``contract_violated`` field), so it is read from there, with
  a top-level fallback if a future producer moves it. This is the real step-level
  determination -- never inferred. ``c2`` is reported likewise as ``clean_exact_c2``.

A seed enters ``seeds_with_clean_exact_c1`` (the complete-campaign HIT set that drives
the rate) only if it BOTH completed the full budget AND observed a clean exact C1 --
matching the right_censored contract that a hit requires a complete campaign. A clean
exact C1 observed in an aborted campaign's partial stream is kept as an "observed
trigger" (its cell's ``clean_exact_c1`` > 0) but is NOT a complete-campaign hit.

Scoring source: completed seeds are scored from the campaign JSON's own ``steps``.
Aborted campaign JSONs carry no steps; when a ``<name>.steps.jsonl`` sidecar is present
its partial per-step stream (the steps observed before the abort) is scored so an
observed-trigger-before-abort is not silently dropped; otherwise the aborted seed
scores 0 with ``source="aborted-stub-no-steps"``. Pass ``--no-jsonl-for-aborted`` to
force aborted seeds to 0 and read campaign JSONs only. Every cell records its scoring
``source`` for transparency.

Usage::

    python3 -m scripts.rollup_m3_matched \
        --evidence-dir ~/inodefence-evidence/m3-powered-matched-20261030 \
        --arm A1 --output /tmp/out/A1_summary.json

    # then the matched contrast (the final H1 rate judgment):
    PYTHONPATH=src python3 -m scripts.analyze_m3_3_control \
        --contrast /tmp/out/A1_summary.json /tmp/out/A3full_summary.json
"""

import argparse
import json
import re
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path

# Fixed, identical across arms so analyze_m3_3_control's --contrast invariant check
# (budget/version/hit_criterion must match) passes; it mirrors the committed example
# summary's hit_criterion string.
HIT_CRITERION = "step rendered 'C1 VIOLATED' == oracle.C1 && contract_violated"
_FILENAME_STEM = "inodefence-effect-demo-historical"
_SEED_RE = re.compile(r"-s(\d+)\.json$")


def _resolve_contract_violated(step: dict) -> bool:
    """A step's contract-violation flag.

    This producer carries it under ``step["feedback"]["contract_violated"]`` and has no
    top-level field; a top-level value, if a future producer adds one, takes precedence.
    """
    top = step.get("contract_violated")
    if top is not None:
        return bool(top)
    feedback = step.get("feedback")
    if isinstance(feedback, dict) and feedback.get("contract_violated") is not None:
        return bool(feedback["contract_violated"])
    return False


def _score_steps(steps: Iterable[dict]) -> dict:
    """Tally oracle verdicts over a per-step stream.

    ``clean_exact_c1`` / ``clean_exact_c2`` are the clean-exact counts
    (``oracle.Cx AND contract_violated``); ``cN_steps`` are the raw ``oracle.CN`` flag
    counts. ``clean_exact_c1_first_step`` is the 1-based execution index of the first
    clean exact C1 (from the step's own 0-based ``index`` when present, else position).
    """
    c0 = c1 = c2 = clean_c1 = clean_c2 = 0
    first_clean_c1: int | None = None
    observed = 0
    for position, step in enumerate(steps):
        observed += 1
        oracle = step.get("oracle")
        if not isinstance(oracle, dict):
            continue
        cv = _resolve_contract_violated(step)
        is_c0 = bool(oracle.get("C0"))
        is_c1 = bool(oracle.get("C1"))
        is_c2 = bool(oracle.get("C2"))
        c0 += is_c0
        c1 += is_c1
        c2 += is_c2
        if is_c1 and cv:
            clean_c1 += 1
            if first_clean_c1 is None:
                raw_index = step.get("index")
                base = raw_index if isinstance(raw_index, int) else position
                first_clean_c1 = base + 1  # 1-based execution count
        if is_c2 and cv:
            clean_c2 += 1
    return {
        "observed_steps": observed,
        "c0_steps": c0,
        "c1_steps": c1,
        "c2_steps": c2,
        "clean_exact_c1": clean_c1,
        "clean_exact_c2": clean_c2,
        "clean_exact_c1_first_step": first_clean_c1,
    }


def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _classify_abort(reason: object) -> str:
    text = reason if isinstance(reason, str) else ""
    if "evidence integrity failed" in text:
        return "aborted_fail_closed_obs_integrity (right-censored)"
    if "BackendError" in text or "broker" in text:
        return "aborted_backend_error (right-censored)"
    return "aborted_other (right-censored)"


def _campaign_json_paths(evidence_dir: Path, arm: str, label_prefix: str) -> list[Path]:
    """Campaign JSONs for one arm, newest-name-sorted by seed; excludes .steps.jsonl."""
    pattern = f"{_FILENAME_STEM}-{label_prefix}-{arm}-s*.json"
    paths = [p for p in evidence_dir.glob(pattern) if not p.name.endswith(".steps.jsonl")]

    def seed_of(path: Path) -> int:
        match = _SEED_RE.search(path.name)
        return int(match.group(1)) if match else -1

    return sorted(paths, key=seed_of)


def _seed_of(path: Path) -> int:
    match = _SEED_RE.search(path.name)
    if match is None:
        raise ValueError(f"cannot parse seed from {path.name!r}")
    return int(match.group(1))


def build_arm_summary(
    evidence_dir: Path,
    arm: str,
    *,
    label_prefix: str = "m3p-752",
    budget: int | None = None,
    score_aborted_from_jsonl: bool = True,
    task: str | None = None,
) -> dict:
    """Scan one arm's campaign JSONs and build the analyze_m3_3_control summary dict."""
    paths = _campaign_json_paths(evidence_dir, arm, label_prefix)
    if not paths:
        raise FileNotFoundError(
            f"no campaign JSONs matched arm {arm!r} with prefix {label_prefix!r} in {evidence_dir}"
        )

    raw: list[dict] = []  # per-seed intermediate records
    search_policy = mutation_policy = version = image_id = None
    for path in paths:
        seed = _seed_of(path)
        with path.open() as handle:
            document = json.load(handle)
        version = version or document.get("requested_tar_version") or document.get("node_tar_version")
        steps = document.get("steps")
        if isinstance(steps, list):
            config = document.get("config") or {}
            search_policy = search_policy or config.get("search_policy")
            mutation_policy = mutation_policy or config.get("mutation_policy")
            image_id = image_id or document.get("image_id")
            seed_budget = config.get("execution_budget")
            ode = document.get("oracle_detected_events")
            raw.append(
                {
                    "seed": seed,
                    "path": path,
                    "kind": "completed",  # conformance (len==budget) decided once budget is known
                    "config_budget": seed_budget if isinstance(seed_budget, int) else None,
                    "config_seed": config.get("random_seed"),
                    "n_steps": len(steps),
                    "scored": _score_steps(steps),
                    "source": "json-steps",
                    "oracle_detected_events": len(ode) if isinstance(ode, list) else 0,
                    "status": "completed",
                }
            )
            del document, steps
        else:
            aborted = document.get("aborted")
            aborted = aborted if isinstance(aborted, dict) else {}
            step_index = aborted.get("step_index")
            censor = step_index if isinstance(step_index, int) else None
            status = _classify_abort(aborted.get("reason"))
            sidecar = path.with_name(path.name[: -len(".json")] + ".steps.jsonl")
            if score_aborted_from_jsonl and sidecar.exists():
                scored = _score_steps(_iter_jsonl(sidecar))
                source = "steps-jsonl"
            else:
                scored = _score_steps([])
                source = "aborted-stub-no-steps"
            raw.append(
                {
                    "seed": seed,
                    "path": path,
                    "kind": "aborted",
                    "config_budget": None,
                    "config_seed": None,
                    "n_steps": None,
                    "scored": scored,
                    "source": source,
                    "oracle_detected_events": 0,
                    "status": status,
                    "censor_step": censor,
                }
            )

    # Budget: prefer the explicit arg, else the first completed seed's config budget.
    completed_budgets = [r["config_budget"] for r in raw if r["kind"] == "completed" and r["config_budget"]]
    if budget is None:
        if not completed_budgets:
            raise ValueError(
                "cannot infer budget: no completed campaign carries config.execution_budget; pass --budget"
            )
        budget = completed_budgets[0]

    # Finalize completed vs nonconformant now that the budget is known: a campaign with a
    # steps list whose length != budget, or a config seed that disagrees, is nonconformant
    # and excluded from completed_full_budget (reported honestly, not silently completed).
    cells: list[dict] = []
    completed_full_budget: list[int] = []
    right_censored_abort_seeds: list[int] = []
    config_nonconformant_seeds: list[int] = []
    seeds_with_clean_exact_c1: list[int] = []
    observed_executions = 0
    clean_exact_c1_total = 0

    for record in raw:
        seed = record["seed"]
        scored = record["scored"]
        observed_steps = scored["observed_steps"]
        clean_c1 = scored["clean_exact_c1"]
        is_completed = False
        status = record["status"]
        censor_step = record.get("censor_step")

        if record["kind"] == "completed":
            conformant = record["n_steps"] == budget and (
                record["config_seed"] is None or record["config_seed"] == seed
            )
            observed_steps = record["n_steps"]
            if conformant:
                is_completed = True
                completed_full_budget.append(seed)
                # A completed campaign that hit is not censored; a completed no-hit is
                # right-censored at the budget horizon (> N), so censor_step = budget.
                censor_step = None if clean_c1 > 0 else budget
            else:
                config_nonconformant_seeds.append(seed)
                status = "config_nonconformant (excluded)"
                censor_step = record["n_steps"]  # provenance; excluded from denominator
        else:
            right_censored_abort_seeds.append(seed)
            if censor_step is None:
                censor_step = observed_steps  # best-effort: jsonl line count

        observed_executions += observed_steps if isinstance(observed_steps, int) else 0
        clean_exact_c1_total += clean_c1
        if is_completed and clean_c1 > 0:
            seeds_with_clean_exact_c1.append(seed)

        cell = {
            "seed": seed,
            "run_id": f"{label_prefix}-{arm}-s{seed}",
            "evidence": record["path"].name,
            "source": record["source"],
            "status": status,
            "observed_steps": observed_steps,
            "censor_step": censor_step,
            "c0_steps": scored["c0_steps"],
            "c1_steps": scored["c1_steps"],
            "c2_steps": scored["c2_steps"],
            "clean_exact_c1": clean_c1,
            "clean_exact_c2": scored["clean_exact_c2"],
            "oracle_detected_events": record["oracle_detected_events"],
            "conformant": record["kind"] == "completed" and seed not in config_nonconformant_seeds,
        }
        first_step = scored["clean_exact_c1_first_step"]
        if first_step is not None:
            cell["clean_exact_c1_first_step"] = first_step
        cells.append(cell)

    seeds = sorted(record["seed"] for record in raw)
    image_prefix = None
    if isinstance(image_id, str):
        image_prefix = image_id[:19]  # e.g. "sha256:21d8a0e3a5c5"
    created_at = datetime.now(timezone.utc).isoformat()
    # One roll-up == one batch; merge_summaries overwrites this when it pools several.
    pooled_batches = [
        {"created_at": created_at, "seeds": seeds, "observed_executions": observed_executions}
    ]

    note = (
        "completed campaigns scored from the campaign JSON's own top-level steps "
        "(clean exact C1 = oracle.C1 && contract_violated); contract_violated read from "
        "step.feedback.contract_violated (this producer has no top-level field). "
        "aborted campaigns are right-censored infrastructure-incomplete (fail-closed "
        "obs-integrity STOP or Docker BackendError), excluded from the complete-campaign "
        "denominator; their partial pre-abort stream is scored from the .steps.jsonl "
        "sidecar when present (observed-trigger, not a complete hit), else 0. "
        "seeds_with_clean_exact_c1 is complete-campaign hits only."
    )

    return {
        "created_at": created_at,
        "task": task
        or f"M3 powered matched run, arm {arm} per-seed roll-up (producer for analyze_m3_3_control)",
        "arm": {"label": arm, "search": search_policy, "mutation": mutation_policy},
        "budget": budget,
        "version": version,
        "image_prefix": image_prefix,
        "seeds": seeds,
        "observed_executions": observed_executions,
        "clean_exact_c1_total": clean_exact_c1_total,
        "seeds_with_clean_exact_c1": sorted(seeds_with_clean_exact_c1),
        "completed_full_budget": sorted(completed_full_budget),
        "right_censored_abort_seeds": sorted(right_censored_abort_seeds),
        "config_nonconformant_seeds": sorted(config_nonconformant_seeds),
        "hit_criterion": HIT_CRITERION,
        "note": note,
        "pooled_batches": pooled_batches,
        "cells": sorted(cells, key=lambda cell: cell["seed"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--arm", required=True, help="arm token in the filenames, e.g. A1 or A3full")
    parser.add_argument("--label-prefix", default="m3p-752", help="filename label between the stem and the arm")
    parser.add_argument("--budget", type=int, default=None, help="override; default inferred from config.execution_budget")
    parser.add_argument(
        "--no-jsonl-for-aborted",
        action="store_true",
        help="do not score aborted seeds' partial stream from the .steps.jsonl sidecar (score 0)",
    )
    parser.add_argument("--output", type=Path, help="write summary.json here (also printed to stdout)")
    args = parser.parse_args()

    summary = build_arm_summary(
        args.evidence_dir,
        args.arm,
        label_prefix=args.label_prefix,
        budget=args.budget,
        score_aborted_from_jsonl=not args.no_jsonl_for_aborted,
    )
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()

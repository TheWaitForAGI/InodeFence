"""Runtime-lane clean-C1 determination for the M3.3 powered matched run (A1 vs A3full).

The M3.3 powered matched run (pre-registered 2026-10-30, LOG) ran two arms at budget
2000 over disjoint seeds 100-119 against the frozen node-tar 7.5.2 overlay:

* ``A1``     -- uniform effect-retention search + uniform escape-hardlink mutation
               (random floor).
* ``A3full`` -- boundary-attempt gradient (adaptive) search + state-aware escape-hardlink
               mutation (identity-feedback arm; blind-aware, no hardcoded answer path).

Each campaign cell left a demo-historical report stub (``.json``) and a preserved
per-step log (``.steps.jsonl``, retained for this run by the PR #180 copy-out fix). This
module is the RUNTIME-lane determination: per cell it reads whether the campaign
fail-closed-aborted (an ``"aborted"`` stub) and counts the clean-exact-C1 steps in the
per-step log, where a clean exact C1 is ``oracle.C1 and feedback.contract_violated`` --
the same predicate the demo renders as ``C1 VIOLATED``. It emits the per-arm
``summary.json`` that :mod:`scripts.analyze_m3_3_control` consumes.

The statistical roll-up (Wilson intervals, matched contrast, CI separation) is the
EVALUATION layer and lives in :mod:`scripts.analyze_m3_3_control` /
:mod:`inodefence.evaluation.right_censored`. This module makes no rate or effectiveness
claim: it only turns raw cells into the per-seed facts those tools score (audit EN-008).

A clean exact C1 observed before a fail-closed abort is recorded on the cell as
``clean_exact_c1`` (so the eval layer can tally it as an observed trigger) but the seed
is NOT listed in ``seeds_with_clean_exact_c1`` -- a complete-campaign hit requires a
complete campaign (the ``SeedOutcome`` contract). The 1-based first-hit position is the
ordinal of the first hitting record in the ordered per-step stream, which is independent
of the record ``index`` field's base.

  uv run python -m scripts.determine_m3_powered_cells \
      --evidence-dir ~/inodefence-evidence/m3-powered-matched-20261030 \
      --arm A1 --output <dir>/A1-summary.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

HIT_CRITERION = "step rendered 'C1 VIOLATED' == oracle.C1 && contract_violated"

# Arm definitions, byte-identical to the pre-registration (LOG 2026-10-30 12:34) and to
# the m3-scale-full / m3-ablation / m3-3-control arm labels.
ARM_META: dict[str, dict[str, str]] = {
    "A1": {
        "label": "A1",
        "search": "effect-feedback-v2-or-violation-v1-uniform-mutation-v1",
        "mutation": "uniform-generic-m1-escape-hardlink-v1",
    },
    "A3full": {
        "label": "A3full",
        "search": "effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1",
        "mutation": "uniform-generic-m1-state-aware-escape-hardlink-v1",
    },
}

_RUN_PREFIX = "inodefence-effect-demo-historical-m3p-752"
_IMAGE_PREFIX = "sha256:21d8a0e3a5c5"
_VERSION = "7.5.2"
_BUDGET = 2000
_TASK = (
    "M3.3 powered matched run per-arm determination (A1 random floor vs A3full "
    "identity-feedback), node-tar 7.5.2, budget 2000, disjoint seeds 100-119 -- "
    "runtime-lane clean-C1 facts for the eval-lane matched contrast (NOT a rate claim, "
    "audit EN-008)"
)
_NOTE = (
    "clean exact C1 = oracle.C1 && feedback.contract_violated, scored from the preserved "
    ".steps.jsonl (retained by the PR #180 demo-historical copy-out). abort cells = "
    "fail-closed native observation-integrity STOP (incomplete campaign), excluded from "
    "the complete-campaign denominator; a clean exact C1 seen before an abort is recorded "
    "as the cell's clean_exact_c1 (observed trigger) but the seed is not a complete hit."
)


def _is_clean_exact_c1(record: dict) -> bool:
    """A step is a clean exact C1 iff the oracle flags C1 and feedback flags a violation."""
    oracle = record.get("oracle") or {}
    feedback = record.get("feedback") or {}
    return bool(oracle.get("C1")) and bool(feedback.get("contract_violated"))


def classify_cell(
    seed: int,
    run_id: str,
    evidence_name: str,
    aborted: bool,
    steps: Iterable[dict],
) -> dict:
    """Turn one cell's stub flag and ordered per-step records into a summary cell dict.

    ``steps`` is iterated once, in stream order. ``aborted`` is whether the report stub
    carried an ``"aborted"`` payload (a fail-closed observation-integrity STOP). The
    returned dict matches the per-cell shape ``analyze_m3_3_control`` reads: ``status``,
    ``observed_steps``, ``censor_step`` (abort only), per-contract step tallies,
    ``clean_exact_c1`` and a 1-based ``clean_exact_c1_first_step`` when any.
    """
    observed = 0
    c0 = c1 = c2 = 0
    clean = 0
    first_step: int | None = None
    for record in steps:
        observed += 1
        oracle = record.get("oracle") or {}
        if oracle.get("C0"):
            c0 += 1
        if oracle.get("C1"):
            c1 += 1
        if oracle.get("C2"):
            c2 += 1
        if _is_clean_exact_c1(record):
            clean += 1
            if first_step is None:
                first_step = observed  # 1-based ordinal in the ordered stream
    status = (
        "aborted_fail_closed_obs_integrity (right-censored)"
        if aborted
        else "completed (full budget)"
    )
    cell = {
        "seed": seed,
        "run_id": run_id,
        "evidence": evidence_name,
        "source": "steps.jsonl",
        "status": status,
        "observed_steps": observed,
        "censor_step": observed if aborted else None,
        "c0_steps": c0,
        "c1_steps": c1,
        "c2_steps": c2,
        "clean_exact_c1": clean,
        "clean_exact_c1_first_step": first_step,
        "conformant": True,
    }
    return cell


def build_arm_summary(arm: str, seeds: Sequence[int], cells: Sequence[dict]) -> dict:
    """Assemble the per-arm summary dict that ``analyze_m3_3_control`` consumes.

    ``seeds_with_clean_exact_c1`` is complete-only (a hit needs a complete campaign); a
    pre-abort clean C1 stays as the cell's ``clean_exact_c1`` observed-trigger tally.
    """
    if arm not in ARM_META:
        raise ValueError(f"unknown arm {arm!r}; expected one of {sorted(ARM_META)}")
    by_seed = {cell["seed"]: cell for cell in cells}
    completed = [s for s in seeds if not _is_abort(by_seed[s])]
    aborted = [s for s in seeds if _is_abort(by_seed[s])]
    complete_hits = [s for s in completed if by_seed[s]["clean_exact_c1"] > 0]
    total_clean = sum(by_seed[s]["clean_exact_c1"] for s in seeds)
    observed_exec = sum(by_seed[s]["observed_steps"] for s in seeds)
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "task": _TASK,
        "arm": ARM_META[arm],
        "budget": _BUDGET,
        "version": _VERSION,
        "image_prefix": _IMAGE_PREFIX,
        "seeds": list(seeds),
        "observed_executions": observed_exec,
        "clean_exact_c1_total": total_clean,
        "seeds_with_clean_exact_c1": complete_hits,
        "completed_full_budget": completed,
        "right_censored_abort_seeds": aborted,
        "config_nonconformant_seeds": [],
        "hit_criterion": HIT_CRITERION,
        "note": _NOTE,
        "cells": [by_seed[s] for s in seeds],
    }


def _is_abort(cell: dict) -> bool:
    return cell["status"].startswith("aborted")


def _iter_steps(path: Path) -> Iterator[dict]:
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def scan_arm(evidence_dir: Path, arm: str, seeds: Sequence[int]) -> dict:
    """Read every cell's stub + per-step log under ``evidence_dir`` and build the summary."""
    cells = []
    for seed in seeds:
        run_id = f"m3p-752-{arm}-s{seed}"
        base = f"{_RUN_PREFIX}-{arm}-s{seed}"
        stub_path = evidence_dir / f"{base}.json"
        steps_path = evidence_dir / f"{base}.steps.jsonl"
        if not stub_path.exists():
            raise FileNotFoundError(f"missing report stub for {run_id}: {stub_path}")
        if not steps_path.exists():
            raise FileNotFoundError(f"missing per-step log for {run_id}: {steps_path}")
        stub = json.loads(stub_path.read_text())
        aborted = "aborted" in stub
        cells.append(classify_cell(seed, run_id, stub_path.name, aborted, _iter_steps(steps_path)))
    return build_arm_summary(arm, seeds, cells)


def _parse_seeds(spec: str) -> list[int]:
    """Parse ``100-119`` or ``100,101,...`` into a sorted seed list."""
    if "-" in spec and "," not in spec:
        low, high = spec.split("-", 1)
        return list(range(int(low), int(high) + 1))
    return [int(part) for part in spec.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--arm", choices=sorted(ARM_META), required=True)
    parser.add_argument("--seeds", default="100-119", help="e.g. 100-119 or 100,101,102")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    summary = scan_arm(args.evidence_dir.expanduser(), args.arm, _parse_seeds(args.seeds))
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.output:
        args.output.expanduser().write_text(text + "\n")
        print(f"wrote {args.output} (arm {args.arm}, {len(summary['seeds'])} seeds)")
    else:
        print(text)


if __name__ == "__main__":
    main()

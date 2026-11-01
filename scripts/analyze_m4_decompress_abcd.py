"""M4 decompress A/C/D search-arm roll-up: does the identity-state rung separate from coverage?

Consumes the native ``decompress-effect-campaign`` reports of an A/C/D matrix (one JSON per
arm x seed cell, written by ``scripts.container_controller``) and computes, per the node-tar
item-3 method (``scripts/analyze_m3_item3.py``), the PRIMARY intermediate-state metrics on each
campaign's per-step frame observation:

- boundary-attempt rate + executions-to-first-boundary-attempt  (the coverage rung, arm D)
- observed-external-resolve rate + executions-to-first          (the identity-state rung, arm C)
- the DECISIVE C-vs-D contrast on shared seeds: is C's evolved corpus (case-id sequence)
  operationally identical to D's, or does C's external-resolve rung admit a shapeless external
  reach -- the decompress escape resolved against the sandbox-root CWD -- that the coverage rung
  is structurally blind to, separating the two arms?
- secondary: terminal C0/C1/C2 self-discovery via the ``right_censored`` roll-up.

The decisive extractor-specific fact this exploits: for decompress the escape is a SHAPELESS
relative hardlink (``_escape_shape`` is None), so it fires only the external-resolve rung, not the
lexical boundary-attempt rung -- the opposite of node-tar, whose escapes are ``..``-shaped and make
the two rungs coincide (item-3 PASS 2, C == D operationally). ``decoupled_external_steps`` counts
the frame-observed decoupling, and ``external_only_novel_keys`` counts the steps where C admitted a
novelty D could never earn.

Honest boundaries (audit EN-008): a rung rate is SEARCH BEHAVIOUR toward a boundary, not a
vulnerability count and not effectiveness. The arms are contrasted only on how they explore
intermediate states; any terminal self-discovery is reported as a right-censored outcome, never a
superiority claim.

Run (host, where the evidence lives):
  PYTHONPATH=src python -m scripts.analyze_m4_decompress_abcd \\
    --evidence-dir ~/inodefence-evidence \\
    --glob 'inodefence-decompress-selfdiscover-m4abcd-*.json' \\
    --output ~/inodefence-evidence/m4-decompress-abcd-<stamp>/primary-metric-rollup.json
"""

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from inodefence.evaluation.right_censored import (
    SeedOutcome,
    right_censored_summary,
    wilson_interval,
)
from inodefence.feedback import EffectSearchPolicy

_ARMS = ("A", "C", "D")
_ARM_BY_POLICY = {
    EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT.value: "C",
    EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT.value: "D",
}
_ARM_POLICY = {
    "A": "random floor (P1): neither gradient rung",
    "C": "identity-state (P3_EXTERNAL_RESOLVE): boundary-attempt + external-resolve rungs",
    "D": "coverage (P3_BOUNDARY_ATTEMPT): boundary-attempt rung only",
}


def arm_label(search_policy: str) -> str:
    """A/C/D for the campaign's search policy; any non-P3 policy is the A floor."""
    return _ARM_BY_POLICY.get(search_policy, "A")


def _rate_and_first(flags: Sequence[bool]) -> dict:
    """(# executions exhibiting the rung, rate over all executions, 1-based first-hit index)."""
    total = len(flags)
    hits = [index + 1 for index, flag in enumerate(flags) if flag]
    return {
        "executions_with_rung": len(hits),
        "rate": len(hits) / total if total else 0.0,
        "executions_to_first": hits[0] if hits else None,
    }


def cell_metrics(report: Mapping) -> dict:
    """Per-cell intermediate-state metrics from one decompress campaign report."""
    steps = report["steps"]
    boundary = [bool(step.get("boundary_attempt_present")) for step in steps]
    external = [bool(step.get("external_resolve_present")) for step in steps]
    new_keys = [int(step.get("new_attempt_keys") or 0) for step in steps]
    config = report["config"]
    return {
        "arm": arm_label(config["search_policy"]),
        "seed": config["random_seed"],
        "search_policy": config["search_policy"],
        "mutation_policy": config.get("mutation_policy"),
        "executions": len(steps),
        "boundary_attempt": _rate_and_first(boundary),
        "external_resolve": _rate_and_first(external),
        # Frame-observed: the shapeless decompress escape (external present, boundary absent). This
        # is the structural precondition for C to separate from D; it is arm-independent.
        "decoupled_external_steps": sum(
            1 for b, e in zip(boundary, external, strict=True) if e and not b
        ),
        # Decisive per-arm: a decoupled step on which THIS arm admitted a novel key -- a novelty
        # only the external-resolve rung (C) can earn; the coverage rung (D) is always 0 here.
        "external_only_novel_keys": sum(
            1 for b, e, k in zip(boundary, external, new_keys, strict=True) if e and not b and k > 0
        ),
        "retained": sum(1 for step in steps if step.get("retained")),
        "terminal_c1_steps": [
            index + 1 for index, step in enumerate(steps) if (step.get("oracle") or {}).get("C1")
        ],
        "case_ids": [step["case_id"] for step in steps],
        "discovered_violation": bool(report.get("discovered_violation")),
    }


def cd_contrast(c: Mapping, d: Mapping) -> dict:
    """Contrast the C and D cells on one shared seed: did the identity rung change the search?"""
    identical_rates = (
        c["boundary_attempt"]["rate"] == d["boundary_attempt"]["rate"]
        and c["external_resolve"]["rate"] == d["external_resolve"]["rate"]
    )
    # Strongest check (item-3 method): did the two policies evolve the exact same corpus sequence?
    operationally_identical = c["case_ids"] == d["case_ids"]
    return {
        "seed": c["seed"],
        "identical_on_both_rungs": identical_rates,
        "operationally_identical_case_sequence": operationally_identical,
        "c_boundary_attempt_rate": c["boundary_attempt"]["rate"],
        "d_boundary_attempt_rate": d["boundary_attempt"]["rate"],
        "c_external_resolve_rate": c["external_resolve"]["rate"],
        "d_external_resolve_rate": d["external_resolve"]["rate"],
        "c_decoupled_external_steps": c["decoupled_external_steps"],
        "c_external_only_novel_keys": c["external_only_novel_keys"],
        "d_external_only_novel_keys": d["external_only_novel_keys"],
    }


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
    """Pooled rung proportion with a Wilson 95% CI (executions as trials).

    NOTE: executions within a campaign are correlated, so this execution-pooled CI is
    anti-conservative; the campaign count (n cells) is the real precision limiter.
    """
    return {
        "hits": hits,
        "trials": trials,
        "rate": hits / trials if trials else 0.0,
        "wilson_95_ci": list(wilson_interval(hits, trials)) if trials else None,
    }


def _seed_outcome(cell: Mapping) -> SeedOutcome:
    c1 = cell["terminal_c1_steps"]
    return SeedOutcome(
        seed=int(cell["seed"]),
        budget=int(cell["executions"]),
        complete=True,
        hit=bool(c1),
        first_hit_executions=c1[0] if c1 else None,
    )


def rollup(reports: Sequence[Mapping]) -> dict:
    """Reduce an A/C/D matrix of decompress reports to the identity-vs-coverage verdict data."""
    cells = [cell_metrics(report) for report in reports]
    by_arm: dict[str, list[dict]] = {arm: [] for arm in _ARMS}
    for cell in cells:
        by_arm[cell["arm"]].append(cell)

    per_arm: dict[str, dict] = {}
    for arm in _ARMS:
        arm_cells = sorted(by_arm[arm], key=lambda cell: cell["seed"])
        b_hits = sum(cell["boundary_attempt"]["executions_with_rung"] for cell in arm_cells)
        e_hits = sum(cell["external_resolve"]["executions_with_rung"] for cell in arm_cells)
        trials = sum(cell["executions"] for cell in arm_cells)
        per_arm[arm] = {
            "policy": _ARM_POLICY[arm],
            "n_cells": len(arm_cells),
            "seeds": [cell["seed"] for cell in arm_cells],
            "boundary_attempt_rate": _distribution(
                [cell["boundary_attempt"]["rate"] for cell in arm_cells]
            ),
            "external_resolve_rate": _distribution(
                [cell["external_resolve"]["rate"] for cell in arm_cells]
            ),
            "boundary_attempt_pooled": _pooled_rate(b_hits, trials),
            "external_resolve_pooled": _pooled_rate(e_hits, trials),
            "decoupled_external_steps_total": sum(
                cell["decoupled_external_steps"] for cell in arm_cells
            ),
            "external_only_novel_keys_total": sum(
                cell["external_only_novel_keys"] for cell in arm_cells
            ),
        }

    c_by_seed = {cell["seed"]: cell for cell in by_arm["C"]}
    d_by_seed = {cell["seed"]: cell for cell in by_arm["D"]}
    shared = sorted(set(c_by_seed) & set(d_by_seed))
    contrasts = [cd_contrast(c_by_seed[seed], d_by_seed[seed]) for seed in shared]
    separated = [
        row["seed"] for row in contrasts if not row["operationally_identical_case_sequence"]
    ]
    identical = [row["seed"] for row in contrasts if row["operationally_identical_case_sequence"]]

    outcomes = [_seed_outcome(cell) for cell in cells]
    return {
        "schema_version": 1,
        "task": "M4 decompress A/C/D intermediate-state primary metric (identity vs coverage)",
        "primary_metric": (
            "boundary-attempt (coverage, D) vs external-resolve (identity, C) rate + "
            "executions-to-first; the C-vs-D corpus contrast on shared seeds is decisive"
        ),
        "en_008": (
            "a rung rate is search behaviour toward a boundary, not effectiveness or a "
            "vulnerability count"
        ),
        "per_arm": per_arm,
        "c_vs_d_shared_seeds": shared,
        "c_vs_d_contrast": contrasts,
        "c_vs_d_verdict": {
            "shared_seed_count": len(shared),
            "operationally_identical_seeds": identical,
            "separated_seeds": separated,
            "separation_detected": bool(separated),
            "c_decoupled_external_steps_total": per_arm["C"]["decoupled_external_steps_total"],
            "c_external_only_novel_keys_total": per_arm["C"]["external_only_novel_keys_total"],
        },
        "terminal_cx_rollup": right_censored_summary(outcomes),
    }


def _load_reports(evidence_dir: Path, pattern: str) -> list[dict]:
    reports: list[dict] = []
    for path in sorted(evidence_dir.glob(pattern)):
        report = json.loads(path.read_text())
        if "steps" not in report:  # an aborted stub carries no loop record; skip it, note it
            print(f"skipping aborted/stub report (no steps): {path.name}")
            continue
        reports.append(report)
    return reports


def _print_readout(data: Mapping) -> None:
    print("== M4 decompress A/C/D primary metric (identity vs coverage) ==")
    print("per-arm (boundary-attempt rate mean, external-resolve rate mean, n_cells):")
    for arm in _ARMS:
        summary = data["per_arm"][arm]
        if not summary["n_cells"]:
            continue
        b = summary["boundary_attempt_rate"]
        e = summary["external_resolve_rate"]
        print(
            f"  {arm}: bAtt={b['mean']:.4f} extR={e['mean']:.4f} n={summary['n_cells']}"
            f" decoupled_ext_steps={summary['decoupled_external_steps_total']}"
            f" ext_only_novel={summary['external_only_novel_keys_total']}"
        )
    verdict = data["c_vs_d_verdict"]
    print(f"\nC-vs-D shared seeds {data['c_vs_d_shared_seeds']}:")
    for row in data["c_vs_d_contrast"]:
        print(
            f"  s{row['seed']}: C bAtt={row['c_boundary_attempt_rate']:.4f}"
            f" extR={row['c_external_resolve_rate']:.4f}"
            f" | D bAtt={row['d_boundary_attempt_rate']:.4f}"
            f" extR={row['d_external_resolve_rate']:.4f}"
            f" | op_identical={row['operationally_identical_case_sequence']}"
            f" c_decoupled={row['c_decoupled_external_steps']}"
            f" c_ext_novel={row['c_external_only_novel_keys']}"
        )
    print(
        f"\nverdict: separation_detected={verdict['separation_detected']}"
        f" (separated seeds {verdict['separated_seeds']},"
        f" operationally-identical {verdict['operationally_identical_seeds']});"
        f" C decoupled_external_steps_total={verdict['c_decoupled_external_steps_total']},"
        f" C external_only_novel_keys_total={verdict['c_external_only_novel_keys_total']}"
    )
    c1 = data["terminal_cx_rollup"]
    print(
        f"terminal C1: {c1['number_observed_target']}/{c1['number_complete_campaigns']} complete"
        f" (Wilson {c1['observed_proportion']['wilson_95_ci']}),"
        f" {c1['number_incomplete_excluded']} incomplete"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument(
        "--glob",
        default="inodefence-decompress-selfdiscover-m4abcd-*.json",
        help="filename glob of the A/C/D cell reports under --evidence-dir",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    reports = _load_reports(args.evidence_dir, args.glob)
    if not reports:
        raise SystemExit(f"no campaign reports matched {args.glob!r} in {args.evidence_dir}")
    data = rollup(reports)
    raw = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw)
    _print_readout(data)


if __name__ == "__main__":
    main()

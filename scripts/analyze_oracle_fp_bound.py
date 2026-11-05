"""Oracle false-positive upper bound from raw campaign reports (audit Report 7 #5).

The generic C0/C1/C2 oracle emits verdicts without a quantified false-positive
rate. This script computes, over a population of executions ASSUMED to contain no
genuine boundary violation (ground-truth negative), a one-sided 95% Clopper-Pearson
UPPER confidence bound on the oracle's false-positive probability.

Denominator = every scored execution in the assumed-negative population -- "all
non-violating executions" in a campaign that discovered nothing. Numerator =
executions the oracle flagged (candidate false positives). When the oracle flagged
zero (the usual calibration case) the bound reduces to the rule-of-three value
~3/n. The assumed-negative claim is an INPUT, not a result: this script never
asserts ground truth. It reports what the bound WOULD be under that assumption and
prints which files were pooled, so the assumption itself can be audited separately.

It is generic over the oracle output fields (``contract_violated`` and the
``oracle`` C0/C1/C2 dict per step). No CVE string, target path or sentinel name is
referenced; the bound is a property of the oracle, not of any one target.

Run:
    PYTHONPATH=src python -m scripts.analyze_oracle_fp_bound ~/inodefence-evidence/*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from math import exp, lgamma, log
from pathlib import Path
from typing import Any

CONTRACTS = ("C0", "C1", "C2")
DEFAULT_CONFIDENCE = 0.95


def _binomial_lower_tail(flagged: int, scored: int, probability: float) -> float:
    """P(X <= flagged) for X ~ Binomial(scored, probability), via log-gamma pmf.

    Log-space terms keep the sum stable for large ``scored``. Endpoints are exact:
    probability 0 gives 1.0 (all mass at 0); probability 1 gives 1.0 only when
    flagged == scored, else 0.0.
    """
    if probability <= 0.0:
        return 1.0
    if probability >= 1.0:
        return 1.0 if flagged >= scored else 0.0
    log_p = log(probability)
    log_q = log1p_neg(probability)
    total = 0.0
    for k in range(flagged + 1):
        log_coeff = lgamma(scored + 1) - lgamma(k + 1) - lgamma(scored - k + 1)
        total += exp(log_coeff + k * log_p + (scored - k) * log_q)
    return total


def log1p_neg(probability: float) -> float:
    """log(1 - probability), guarding the domain for the binomial tail."""
    return log(1.0 - probability)


def clopper_pearson_upper(
    flagged: int, scored: int, confidence: float = DEFAULT_CONFIDENCE
) -> float:
    """One-sided upper Clopper-Pearson bound on a binomial proportion.

    ``flagged`` successes in ``scored`` trials. Returns the largest proportion p
    whose binomial lower tail ``P(X <= flagged)`` equals ``1 - confidence``, found
    by bisection (the tail is monotone decreasing in p). ``flagged == scored``
    returns 1.0. With ``flagged == 0`` the value equals the rule-of-three style
    ``1 - (1 - confidence) ** (1 / scored)``.
    """
    if type(flagged) is not int or type(scored) is not int:
        raise ValueError("flagged and scored must be ints")
    if scored <= 0 or not 0 <= flagged <= scored:
        raise ValueError("require 0 <= flagged <= scored and scored > 0")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if flagged == scored:
        return 1.0
    alpha = 1.0 - confidence
    low, high = 0.0, 1.0
    for _ in range(200):
        mid = (low + high) / 2.0
        if _binomial_lower_tail(flagged, scored, mid) > alpha:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


@dataclass(frozen=True, slots=True)
class ReportCounts:
    """Scored executions and oracle-flagged counts for one raw report."""

    label: str
    producer: str
    seed: Any
    discovered_violation: bool
    scored: int
    flagged_any: int
    flagged: dict[str, int]  # per contract C0/C1/C2


def count_report(report: dict[str, Any]) -> ReportCounts:
    """Count scored executions and oracle firings from one parsed report.

    A step is *scored* when it carries a real observation (``frame_observed``);
    steps without one cannot be an assumed-negative trial and are excluded from
    the denominator. ``flagged_any`` counts steps whose ``contract_violated`` is
    true; per-contract counts read the ``oracle`` C0/C1/C2 booleans.
    """
    steps = report.get("steps")
    if not isinstance(steps, list):
        raise ValueError("report has no 'steps' list")
    scored = 0
    flagged_any = 0
    flagged = {contract: 0 for contract in CONTRACTS}
    for step in steps:
        if not isinstance(step, dict) or not step.get("frame_observed"):
            continue
        scored += 1
        if step.get("contract_violated"):
            flagged_any += 1
        oracle = step.get("oracle") or {}
        for contract in CONTRACTS:
            if oracle.get(contract):
                flagged[contract] += 1
    config = report.get("config") or {}
    return ReportCounts(
        label=str(report.get("label", "")),
        producer=str(report.get("producer", "")),
        seed=config.get("random_seed"),
        discovered_violation=bool(report.get("discovered_violation")),
        scored=scored,
        flagged_any=flagged_any,
        flagged=flagged,
    )


def pool(counts: list[ReportCounts]) -> ReportCounts:
    """Pool several reports into one assumed-negative population."""
    if not counts:
        raise ValueError("cannot pool zero reports")
    merged = {contract: sum(c.flagged[contract] for c in counts) for contract in CONTRACTS}
    return ReportCounts(
        label=f"POOLED ({len(counts)} files)",
        producer="|".join(sorted({c.producer for c in counts})),
        seed=None,
        discovered_violation=any(c.discovered_violation for c in counts),
        scored=sum(c.scored for c in counts),
        flagged_any=sum(c.flagged_any for c in counts),
        flagged=merged,
    )


def _bound_fields(flagged: int, scored: int, confidence: float) -> str:
    if scored == 0:
        return f"x={flagged} n=0 rate=n/a upper95=n/a"
    upper = clopper_pearson_upper(flagged, scored, confidence)
    return f"x={flagged} n={scored} rate={flagged / scored:.4f} upper95={upper:.4f}"


def render(counts: ReportCounts, confidence: float) -> str:
    any_fields = _bound_fields(counts.flagged_any, counts.scored, confidence)
    lines = [
        f"[{counts.label}] producer={counts.producer or '?'} "
        f"seed={counts.seed} discovered_violation={counts.discovered_violation}",
        f"  any-contract false-positive bound: {any_fields}",
    ]
    for contract in CONTRACTS:
        lines.append(
            f"  {contract}: {_bound_fields(counts.flagged[contract], counts.scored, confidence)}"
        )
    return "\n".join(lines)


_ASSUMPTION = (
    "ASSUMPTION: the pooled executions are treated as ground-truth NEGATIVE (no genuine\n"
    "boundary violation). The upper bound is the oracle false-positive rate ONLY if that\n"
    "holds; it must be justified separately (e.g. benign/calibration corpus). 'upper95' is\n"
    "the one-sided 95% Clopper-Pearson upper bound; with x=0 it is the rule-of-three ~3/n."
)


def load_reports(
    paths: list[Path],
) -> tuple[list[tuple[Path, ReportCounts]], list[tuple[Path, str]]]:
    parsed: list[tuple[Path, ReportCounts]] = []
    skipped: list[tuple[Path, str]] = []
    for path in paths:
        try:
            report = json.loads(path.read_text())
            parsed.append((path, count_report(report)))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            skipped.append((path, str(error)))
    return parsed, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="raw campaign report JSON file(s)")
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    parser.add_argument(
        "--no-per-file", action="store_true", help="print only the pooled population bound"
    )
    args = parser.parse_args(argv)

    parsed, skipped = load_reports(args.paths)
    print(_ASSUMPTION)
    print()
    if not args.no_per_file:
        for path, counts in parsed:
            print(f"# {path.name}")
            print(render(counts, args.confidence))
            print()
    if parsed:
        print(render(pool([counts for _, counts in parsed]), args.confidence))
    else:
        print("no parseable campaign reports found")
    for path, reason in skipped:
        print(f"  skipped {path.name}: {reason}", file=sys.stderr)
    return 0 if parsed else 1


if __name__ == "__main__":
    raise SystemExit(main())

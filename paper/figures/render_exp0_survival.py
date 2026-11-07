"""Render the EXP-0 pilot survival figure and summary table from analyze_exp0 output.

Data source (observed, measurement only): the JSON produced by ``scripts/analyze_exp0.py``
over lane 5's per-cell summaries. This script plots only what that report already contains --
the per-arm combined T_first (C1|C2) Kaplan-Meier step curve and its censoring ticks -- and
tabulates the abort, first-contract, and dense-signal counts with their denominators. It
invents no numbers. Per prereg v2 EXP-0 is INFRASTRUCTURE MEASUREMENT, not an H-A test; an
unregistered G1-smoke run is tool verification and is NOT a paper claim.

Follows the ``render_m2_cross_release.py`` convention: matplotlib is used for the PNG in an
ephemeral environment and is NOT part of ``make check``. matplotlib is imported lazily (via
importlib, inside the figure function) so the module stays importable -- and the summary table
stays renderable -- without matplotlib, which the project venv does not install.

Run (host, ephemeral env, no project .venv):
    MPLBACKEND=Agg uv run --no-project --with matplotlib \\
        python paper/figures/render_exp0_survival.py --report <analyze_exp0.json>

With no report, or an empty one, it writes the ``TBD -- EXP-0 미실행`` placeholder table.
"""

import argparse
import importlib
import json
from pathlib import Path
from typing import Any

# Okabe-Ito palette (colour-blind safe), matching render_m2_cross_release.py.
_ARM_COLORS = {
    "R": "#999999",  # grey: random floor
    "D": "#0072B2",  # blue: coverage control
    "S-u": "#D55E00",  # vermillion: InodeFence identity feedback (primary)
    "S-a": "#009E73",  # green: adaptive ablation
}
_FALLBACK_COLORS = ["#CC79A7", "#E69F00", "#56B4E9", "#F0E442"]
_PLACEHOLDER = "TBD — EXP-0 미실행"
_DISCLAIMER = (
    "Infrastructure measurement only (prereg v2); observed counts, not an H-A test or an "
    "effectiveness claim. An unregistered G1-smoke run is tool verification, not a paper claim."
)
# How to read two table values. The numbers stay as analyze_exp0 emits them; the official EXP-0
# report's deviations hold the converted and de-duplicated values.
_OFFICIAL_REPORT = "experiments/summaries/exp0-20261105-report.md"
_BOUNDARY_KEYS_NOTE = (
    "boundary_keys is a per-cell sum, not a count of unique keys "
    f"(deviation 4 of {_OFFICIAL_REPORT})."
)
_TIMING_CLOCK_NOTE = (
    "p50, p95 and max are monotonic-clock recorded values; real-time conversions of p50 and p95 "
    f"are in deviation 1 of {_OFFICIAL_REPORT}."
)


def has_results(report: dict | None) -> bool:
    """True when the report carries at least one analyzable cell."""
    return bool(report) and int(report.get("number_cells", 0)) > 0


def _md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out.extend("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return out


def render_summary_table(report: dict | None) -> str:
    """Markdown summary table (abort / first-contract / dense), each number with a denominator.

    Returns the ``TBD -- EXP-0 미실행`` placeholder when there are no results yet.
    """
    lines = ["# EXP-0 pilot summary", "", f"_{_DISCLAIMER}_", ""]
    if not has_results(report):
        lines += [
            _PLACEHOLDER,
            "",
            "No EXP-0 cells were provided; run analyze_exp0 on the pilot output.",
        ]
        return "\n".join(lines) + "\n"
    assert report is not None

    lines += [
        f"Cells: {report['number_cells']} (valid {report['number_valid_cells']}, "
        f"invalid {report['number_invalid_cells']}); arms: {', '.join(report['arms'])}.",
        "",
        "## Aborts by reason and arm (denominator = cells in arm)",
        "",
    ]
    abort = report["item1_aborts"]["by_arm"]
    reason_cols = report["item1_aborts"]["abort_reason_enum"]
    lines += _md_table(
        ["arm", "cells", "complete", "abort", "invalid", *reason_cols, "abort_frac"],
        [
            [
                arm,
                s["number_cells"],
                s["number_complete"],
                s["number_abort"],
                s["number_invalid_nonconformant"],
                *[s["abort_by_reason"][r] for r in reason_cols],
                "n/a" if s["abort_fraction"] is None else f"{s['abort_fraction']:.3f}",
            ]
            for arm, s in abort.items()
        ],
    )

    lines += ["", "## First C0/C1/C2 index and combined T_first (right-censored)", ""]
    index_rows = []
    for arm, s in report["item5_first_contract_index"]["by_arm"].items():
        for contract in ("C0", "C1", "C2"):
            e = s["contracts"][contract]
            index_rows.append(
                [
                    arm,
                    contract,
                    e["number_observed"],
                    e["number_right_censored"],
                    e["km_median_executions"],
                    e["denominator_cells_in_risk_set"],
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
                t["denominator_cells_in_risk_set"],
            ]
        )
    lines += _md_table(
        ["arm", "metric", "observed", "censored", "km_median", "risk_set_n"], index_rows
    )

    lines += ["", "## Dense signals per arm (denominator = valid cells / executions)", ""]
    lines += _md_table(
        [
            "arm",
            "boundary_keys",
            "mean/cell",
            "rejected",
            "executions",
            "rejected_ratio",
            "u_viol",
            "u_viol_c0",
            "obs_fail",
        ],
        [
            [
                arm,
                s["boundary_attempt_keys"]["total"],
                s["boundary_attempt_keys"]["mean_per_cell"],
                s["rejected_ratio"]["numerator"],
                s["rejected_ratio"]["denominator_executions"],
                s["rejected_ratio"]["value"],
                s["u_viol"]["total_unique_c1_c2_fingerprints"],
                s["u_viol_c0"]["total_unique_c0_fingerprints"],
                s["observation_failures_total"],
            ]
            for arm, s in report["item6_dense_signals"]["by_arm"].items()
        ],
    )
    lines += ["", f"_{_BOUNDARY_KEYS_NOTE}_"]

    p95 = report["item2_p95_full_step"]
    if p95.get("available"):
        pooled = p95["pooled"]
        lines += [
            "",
            "## Full-step time distribution (pooled, seconds; nearest-rank)",
            "",
            f"p50 {pooled['p50_seconds']} | p95 {pooled['p95_seconds']} | "
            f"max {pooled['max_seconds']} over {pooled['number_steps']} steps.",
            "",
            f"_{_TIMING_CLOCK_NOTE}_",
        ]

    hazard = report["item7_hazard_proxy"]
    lines += ["", "## Hazard proxy (reference value only, not a verdict)", ""]
    lines += _md_table(
        ["arm", "hit_steps", "executions", "proxy/exec"],
        [
            [arm, s["hit_steps_c1_or_c2"], s["executions"], s["proxy_per_execution"]]
            for arm, s in hazard["by_arm"].items()
        ],
    )
    if "zero_hit" in hazard:
        lines += ["", f"Zero-hit: {hazard['zero_hit']['policy']}"]
        lines += _md_table(
            ["arm", "campaign_n", "rule_of_three_upper95", "exec_n", "exec_upper95 (exploratory)"],
            [
                [
                    arm,
                    s["campaign_denominator"],
                    s["campaign_unit_rule_of_three_upper95"],
                    s["execution_denominator"],
                    s["execution_unit_rule_of_three_upper95_exploratory"],
                ]
                for arm, s in hazard["zero_hit"]["by_arm"].items()
            ],
        )

    env = report.get("environment", {})
    if env.get("distinct"):
        first = env["distinct"][0]
        lines += [
            "",
            "## Environment (provenance)",
            "",
            f"homogeneous: {env['homogeneous']}; "
            + ", ".join(f"{k}={v}" for k, v in sorted(first.items())),
        ]
    return "\n".join(lines) + "\n"


def _arm_color(arm: str, index: int) -> str:
    return _ARM_COLORS.get(arm, _FALLBACK_COLORS[index % len(_FALLBACK_COLORS)])


def _step_xy(km_curve: list[dict], horizon: float) -> tuple[list[float], list[float]]:
    """Step-function (time, survival) points starting at (0, 1.0), flattened to ``horizon``."""
    xs: list[float] = [0.0]
    ys: list[float] = [1.0]
    for step in km_curve:
        xs.append(float(step["time"]))
        ys.append(float(step["survival"]))
    if xs[-1] < horizon:
        xs.append(float(horizon))
        ys.append(ys[-1])
    return xs, ys


def _survival_at(km_curve: list[dict], time: float) -> float:
    survival = 1.0
    for step in km_curve:
        if step["time"] <= time:
            survival = float(step["survival"])
        else:
            break
    return survival


def render_km_figure(report: dict | None, out_path: Path) -> bool:
    """Draw per-arm combined-T_first KM step curves with censoring ticks; write a PNG.

    Returns ``True`` when a figure was written, ``False`` when there are no results (the caller
    emits the placeholder instead). matplotlib is imported here, lazily, via importlib.
    """
    if not has_results(report):
        return False
    assert report is not None
    matplotlib = importlib.import_module("matplotlib")
    matplotlib.use("Agg")
    plt = importlib.import_module("matplotlib.pyplot")

    by_arm = report["item5_first_contract_index"]["by_arm"]
    horizon = 1.0
    for s in by_arm.values():
        curve = s["t_first_combined_c1_or_c2"]
        horizon = max(
            horizon,
            *(float(step["time"]) for step in curve["km_curve"]),
            *(float(t) for t in curve["censored_times"]),
        )

    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    for index, (arm, s) in enumerate(sorted(by_arm.items())):
        curve = s["t_first_combined_c1_or_c2"]
        color = _arm_color(arm, index)
        xs, ys = _step_xy(curve["km_curve"], horizon)
        ax.step(
            xs,
            ys,
            where="post",
            color=color,
            linewidth=2,
            label=f"{arm} (n={curve['denominator_cells_in_risk_set']})",
        )
        for censored_time in curve["censored_times"]:
            ax.plot(
                float(censored_time),
                _survival_at(curve["km_curve"], float(censored_time)),
                marker="|",
                color=color,
                markersize=9,
                markeredgewidth=1.5,
            )

    ax.set_xlabel("execution (1-based)")
    ax.set_ylabel("S(t) = P(no C1|C2 observed yet)")
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlim(0, horizon * 1.02)
    ax.set_title("EXP-0 combined T_first (C1|C2) survival by arm (observed)", fontsize=11)
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(True, color="#EEEEEE", linewidth=1)
    caption = (
        "Step curves are the Kaplan-Meier estimate of T_first (first C1|C2 execution); "
        "vertical ticks are right-censored campaigns (no-hit at budget, abort at abort step). "
        + _DISCLAIMER
    )
    fig.text(0.5, 0.01, caption, ha="center", va="bottom", fontsize=7, wrap=True)
    fig.subplots_adjust(left=0.1, right=0.97, top=0.92, bottom=0.22)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return True


def _load_report(path: Path | None) -> dict | None:
    if path is None:
        return None
    report = json.loads(path.read_text())
    return report if isinstance(report, dict) else None


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    tables = here.parent / "tables"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="analyze_exp0 JSON output")
    parser.add_argument("--figure", type=Path, default=here / "exp0-survival.png")
    parser.add_argument("--table", type=Path, default=tables / "exp0-summary.md")
    parser.add_argument("--no-figure", action="store_true", help="write the table only")
    args = parser.parse_args(argv)

    report = _load_report(args.report)
    args.table.write_text(render_summary_table(report))
    print(f"wrote {args.table}")

    if args.no_figure:
        return 0
    if not has_results(report):
        print(f"{_PLACEHOLDER}: no results, figure skipped")
        return 0
    try:
        if render_km_figure(report, args.figure):
            print(f"wrote {args.figure}")
    except ModuleNotFoundError:
        print("matplotlib not installed; figure skipped (run in an ephemeral env with matplotlib)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

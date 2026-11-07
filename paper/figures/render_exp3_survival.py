"""Render the EXP-3 train or EXP-2 holdout T_first survival figure from an ``analyze_exp0`` report.

One report, one target, per arm: train and holdout are never drawn together. The train title says
it is exploratory. Like the other figures, matplotlib runs in an ephemeral environment and is not
part of ``make check``; it is imported lazily so the data helpers stay testable without it. Text is
English because the default matplotlib font has no Korean glyphs.

    MPLBACKEND=Agg uv run --no-project --with matplotlib \\
        python paper/figures/render_exp3_survival.py --role train \\
        --report experiments/summaries/exp3-train-report.json \\
        --out paper/figures/exp3-train-survival.png
"""

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

_base = importlib.import_module("paper.figures.render_exp0_survival")
TITLES = {
    "train": "EXP-3 train T_first (C1|C2) by arm (exploratory, pre-exposed, not confirmatory)",
    "holdout": "EXP-2 holdout T_first (C1|C2) by arm (not pooled with train)",
}
REPORTS = {
    "train": REPO / "experiments/summaries/exp3-train-report.json",
    "holdout": REPO / "experiments/summaries/exp2-holdout-report.json",
}
OUTPUTS = {
    "train": REPO / "paper/figures/exp3-train-survival.png",
    "holdout": REPO / "paper/figures/exp2-holdout-survival.png",
}
CAPTION = (
    "Step curves are the Kaplan-Meier estimate of T_first (first C1|C2 execution); vertical ticks "
    "are right-censored campaigns (no-hit at budget, abort at abort step). Executions, not time."
)


def arm_curves(report: dict[str, Any], role: str) -> dict[str, dict[str, Any]]:
    """Per-arm curve data of the report's one target. Anything else raises rather than pools."""
    targets = report["registered"]["targets"]
    if len(targets) != 1 or targets[0]["role"] != role:
        raise ValueError(f"expected exactly one registered target, with role {role}")
    section = report["by_target"][targets[0]["target_id"]]
    return {
        arm: values["t_first_combined_c1_or_c2"]
        for arm, values in sorted(section["item5_first_contract_index"]["by_arm"].items())
    }


def render(report: dict[str, Any], role: str, out_path: Path) -> None:
    curves = arm_curves(report, role)
    matplotlib = importlib.import_module("matplotlib")
    matplotlib.use("Agg")
    plt = importlib.import_module("matplotlib.pyplot")
    horizon = 1.0
    for curve in curves.values():
        horizon = max(
            horizon,
            *(float(step["time"]) for step in curve["km_curve"]),
            *(float(time) for time in curve["censored_times"]),
        )
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    for index, (arm, curve) in enumerate(curves.items()):
        color = _base._arm_color(arm, index)
        xs, ys = _base._step_xy(curve["km_curve"], horizon)
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
                _base._survival_at(curve["km_curve"], float(censored_time)),
                marker="|",
                color=color,
                markersize=9,
                markeredgewidth=1.5,
            )
    ax.set_xlabel("execution (1-based)")
    ax.set_ylabel("S(t) = P(no C1|C2 observed yet)")
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlim(0, horizon * 1.02)
    ax.set_title(TITLES[role], fontsize=10)
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(True, color="#EEEEEE", linewidth=1)
    fig.text(0.5, 0.01, CAPTION, ha="center", va="bottom", fontsize=7, wrap=True)
    fig.subplots_adjust(left=0.1, right=0.97, top=0.92, bottom=0.2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=sorted(TITLES))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    path = args.report or REPORTS[args.role]
    render(json.loads(path.read_text(encoding="utf-8")), args.role, args.out or OUTPUTS[args.role])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

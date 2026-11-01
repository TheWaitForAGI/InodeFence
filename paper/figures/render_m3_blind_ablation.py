"""Render the M3 blind-ablation figure (observed data only).

Data source (observed): ``paper/tables/m3-blind-ablation.md``, re-counted from the raw
step logs (hit = a step with ``oracle.C1`` AND ``feedback.contract_violated``). node-tar
7.5.2, budget 1500. See the M3 results subsection (``paper/sections/06-results.md``
section 5.3).

This script hardcodes only the observed counts; it invents no numbers. It is rendered with
matplotlib in an ephemeral environment and is NOT part of ``make check``.

Run (host, ephemeral env, no project .venv):
    MPLBACKEND=Agg uv run --no-project --with matplotlib \\
        python paper/figures/render_m3_blind_ablation.py
"""

from pathlib import Path

import matplotlib.pyplot as plt

ARMS = [
    "A3full s11\n(identity obs ON)",
    "A3blind s11\n(identity obs OFF)",
    "A1 random floor\n(seeds 1-35)",
]
HITS = [21, 0, 0]
STEP_NOTES = ["416 steps (pre-abort)", "1475 steps", "33,005 steps"]
BAR_COLORS = ["#D55E00", "#999999", "#999999"]  # vermillion = discovery; grey = floor


def main() -> None:
    out_path = Path(__file__).resolve().parent / "m3-blind-ablation.png"
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    xs = list(range(len(ARMS)))
    ax.bar(xs, HITS, color=BAR_COLORS, width=0.6, edgecolor="black", linewidth=0.6)

    ax.set_xticks(xs)
    ax.set_xticklabels(ARMS)
    ax.set_ylabel("autonomous C1 hits  (C1 and contract_violated)")
    ax.set_ylim(0, 26)
    ax.set_title(
        "M3: object-identity observation enables autonomous discovery (observed)",
        fontsize=11,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for x, hits, note in zip(xs, HITS, STEP_NOTES, strict=True):
        ax.text(
            x, hits + 0.6, f"{hits} hits", ha="center", va="bottom", fontsize=12, fontweight="bold"
        )
        ax.text(x, hits + 2.4, note, ha="center", va="bottom", fontsize=8, color="#333333")

    caption = (
        "Causal contrast: feedback (identity observation) enables discovery; absent -> "
        "unreachable. This is NOT a rate claim. The trigger is seed-rare (1 of 65 seeds). It "
        "is not blind discovery (the fuzzer obtains the external name by observation; no "
        "hardcoded target path / answer seed / proximity reward). node-tar 7.5.2, budget 1500."
    )
    fig.text(0.5, 0.015, caption, ha="center", va="bottom", fontsize=7, wrap=True)
    fig.subplots_adjust(left=0.1, right=0.97, top=0.9, bottom=0.26)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

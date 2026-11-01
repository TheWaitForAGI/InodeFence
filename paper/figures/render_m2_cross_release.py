"""Render the M2 cross-release hardlink identity figure (observed data only).

Data source (observed): ``paper/tables/m2-cross-release-evidence.md``, re-derived from
``experiments/repro/evidence/summary.json``. The verdict is "extraction object shares
``(st_dev, st_ino)`` with the external reference file" -- i.e. the generic C1 oracle
observation -- with no release id or answer path in the decision. See the M2 results
subsection (``paper/sections/06-results.md`` section 5.2).

This script hardcodes only the observed verdicts; it invents no numbers. It is rendered
with matplotlib in an ephemeral environment and is NOT part of ``make check``.

Run (host, ephemeral env, no project .venv):
    MPLBACKEND=Agg uv run --no-project --with matplotlib \\
        python paper/figures/render_m2_cross_release.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Rectangle

RELEASES = ["7.5.2", "7.5.3", "7.5.6", "7.5.7", "7.5.8"]
FIXTURES = ["top-level hardlink", "nested hardlink"]

# True = shared (resolved, nlink 1->2); False = rejected. (observed; see module docstring)
SHARED = {
    "top-level hardlink": [True, False, False, False, False],
    "nested hardlink": [True, False, True, False, False],
}

SHARED_COLOR = "#D55E00"  # vermillion (Okabe-Ito): identity shared = boundary violation
REJECT_COLOR = "#E6E6E6"  # light grey: rejected


def main() -> None:
    out_path = Path(__file__).resolve().parent / "m2-cross-release-evidence.png"
    grid = [[1 if SHARED[fx][i] else 0 for i in range(len(RELEASES))] for fx in FIXTURES]

    fig, ax = plt.subplots(figsize=(8.4, 3.4))
    ax.imshow(
        grid, cmap=ListedColormap([REJECT_COLOR, SHARED_COLOR]), vmin=0, vmax=1, aspect="auto"
    )

    ax.set_xticks(range(len(RELEASES)))
    ax.set_xticklabels([f"node-tar\n{r}" for r in RELEASES])
    ax.set_yticks(range(len(FIXTURES)))
    ax.set_yticklabels(FIXTURES)
    ax.set_xticks([x - 0.5 for x in range(1, len(RELEASES))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(FIXTURES))], minor=True)
    ax.grid(which="minor", color="white", linewidth=3)
    ax.tick_params(which="minor", length=0)
    ax.set_ylim(1.95, -1.15)

    for r, fx in enumerate(FIXTURES):
        for c in range(len(RELEASES)):
            shared = SHARED[fx][c]
            label = "shared\nnlink 1->2" if shared else "rejected"
            ax.text(
                c,
                r,
                label,
                ha="center",
                va="center",
                fontsize=9,
                color="white" if shared else "#444444",
            )

    # Fixed pairs: top-level 7.5.2->7.5.3 = R1; nested 7.5.6->7.5.7 = R2.
    ax.add_patch(Rectangle((-0.5, -0.5), 2, 1, fill=False, edgecolor="black", linewidth=2))
    ax.add_patch(Rectangle((1.5, 0.5), 2, 1, fill=False, edgecolor="black", linewidth=2))
    ax.text(
        0.5, -0.78, "R1  CVE-2026-23745", ha="center", va="center", fontsize=8, fontweight="bold"
    )
    ax.text(
        2.5, 1.78, "R2  CVE-2026-24842", ha="center", va="center", fontsize=8, fontweight="bold"
    )

    ax.set_title("node-tar cross-release hardlink identity verdict (observed)", fontsize=11)

    caption = (
        "Orange = shared (identity, C1 violation); grey = rejected.  "
        "verdict = extraction object shares (st_dev, st_ino) with the external reference file "
        "(generic C1 oracle). One oracle, no release-id/answer-path hardcoding. The nested row "
        "is non-monotone (7.5.2 shared, 7.5.3 rejected, 7.5.6 shared, 7.5.7/7.5.8 rejected): the "
        "7.5.6 regression was introduced by the R1 fix. Observed."
    )
    fig.text(0.5, 0.02, caption, ha="center", va="bottom", fontsize=7, wrap=True)
    fig.subplots_adjust(left=0.16, right=0.98, top=0.9, bottom=0.24)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

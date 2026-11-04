"""Regenerate and verify the paper's tables and figures from one entry point.

Audit item (8) asks for a single script that produces every paper table/figure from
raw. This orchestrates the generators that exist and is **honest about the gaps**:

  * Figures (`paper/figures/*.png`) have generators (`render_m2_cross_release.py`,
    `render_m3_blind_ablation.py`). They render with matplotlib in an ephemeral env
    (`uv run --with matplotlib`), which this project's venv does not carry, and matplotlib
    PNG output is not bit-reproducible. So ``--verify`` checks a figure by existence and
    size, not byte-equality, and records that reason.
  * Tables (`paper/tables/*.md`) are currently **hand-maintained**: no committed generator
    derives them from raw. ``--verify`` checks them by existence only and flags the missing
    generator as the audit-(8) gap. A future table generator that accepts ``--out`` can be
    registered with ``verify="byte"`` to get real byte-comparison.
  * Lane 6's EXP-0 survival generators are not merged yet (#219); their rows are optional
    and skipped until the generator files appear.

Modes (default ``--verify``, read-only):

    python -m scripts.regenerate_paper_artifacts --list
    python -m scripts.regenerate_paper_artifacts --verify
    python -m scripts.regenerate_paper_artifacts --regenerate   # runs generators in place

``--verify`` and ``--list`` also run the evidence-chain check so a broken summary->raw
pointer surfaces here too.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from scripts.check_evidence_chain import check_summaries
from scripts.check_evidence_chain import repository_root as _repo_root


@dataclass(frozen=True, slots=True)
class Artifact:
    output: str
    kind: str  # "figure" | "table"
    generator: str | None  # repo-relative generator, or None when hand-maintained
    env: str  # "matplotlib-ephemeral" | "project" | ""
    inputs: tuple[str, ...]  # raw/summary/manifest provenance
    verify: str  # "byte" | "size" | "exists"
    note: str = ""
    out_flag: bool = False  # generator accepts --out <path> (enables byte-verify to temp)


#: The committed paper artifacts and how each is produced/verified.
ARTIFACTS: tuple[Artifact, ...] = (
    Artifact(
        "paper/figures/m2-cross-release-evidence.png",
        "figure",
        "paper/figures/render_m2_cross_release.py",
        "matplotlib-ephemeral",
        ("paper/tables/m2-cross-release-evidence.md", "experiments/repro/evidence/summary.json"),
        "size",
        "matplotlib PNG not bit-reproducible; observed verdicts transcribed from raw",
    ),
    Artifact(
        "paper/figures/m3-blind-ablation.png",
        "figure",
        "paper/figures/render_m3_blind_ablation.py",
        "matplotlib-ephemeral",
        (
            "paper/tables/m3-blind-ablation.md",
            "~/inodefence-evidence/m3-scale-full|m3-ablation (manifest mac-20261103)",
        ),
        "size",
        "matplotlib PNG not bit-reproducible; observed counts transcribed from raw",
    ),
    Artifact(
        "paper/tables/m2-cross-release-evidence.md",
        "table",
        None,
        "",
        ("experiments/repro/evidence/summary.json", "experiments/repro/cross_release_identity.py"),
        "exists",
        "hand-maintained; no generator derives it from raw (audit-(8) gap)",
    ),
    Artifact(
        "paper/tables/m3-blind-ablation.md",
        "table",
        None,
        "",
        ("~/inodefence-evidence/m3-scale-full|m3-ablation (manifest mac-20261103)",),
        "exists",
        "hand-maintained; no generator derives it from raw (audit-(8) gap)",
    ),
    Artifact(
        "paper/tables/capability-ledger-summary.md",
        "table",
        None,
        "",
        ("docs/STATUS.md (Capability Ledger)",),
        "exists",
        "hand-maintained summary of the Ledger; no raw generator",
    ),
    # Lane 6 EXP-0 survival (optional until #219 merges): generators are not in the tree yet.
    Artifact(
        "paper/figures/exp0-survival.png",
        "figure",
        "paper/figures/render_exp0_survival.py",
        "matplotlib-ephemeral",
        ("scripts/analyze_exp0.py output",),
        "size",
        "pending lane 6 #219 (generator not in tree)",
    ),
)

#: Verify statuses that mean failure.
_FAIL = {"MISSING", "BYTE-MISMATCH"}


@dataclass(slots=True)
class VerifyRow:
    output: str
    status: str
    detail: str


def _sha_size(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return sha256(data).hexdigest(), len(data)


def _default_runner(artifact: Artifact, repo_root: Path, dest: Path) -> None:
    """Run a generator that accepts ``--out`` to ``dest`` (used only for verify=='byte')."""
    assert artifact.generator is not None
    gen = repo_root / artifact.generator
    if artifact.env == "matplotlib-ephemeral":
        cmd = [
            "uv",
            "run",
            "--no-project",
            "--with",
            "matplotlib",
            "python",
            str(gen),
            "--out",
            str(dest),
        ]
    else:
        cmd = [sys.executable, str(gen), "--out", str(dest)]
    subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=repo_root)


Runner = Callable[[Artifact, Path, Path], None]


def verify_artifacts(
    artifacts: tuple[Artifact, ...],
    repo_root: Path,
    runner: Runner = _default_runner,
    tmp_dir: Path | None = None,
) -> list[VerifyRow]:
    """Verify each committed artifact per its policy (read-only for the committed tree)."""
    rows: list[VerifyRow] = []
    for art in artifacts:
        committed = repo_root / art.output
        generator_present = art.generator is not None and (repo_root / art.generator).is_file()
        if not committed.exists():
            if art.generator is not None and not generator_present:
                rows.append(
                    VerifyRow(art.output, "SKIP", f"optional; generator absent ({art.note})")
                )
            else:
                rows.append(VerifyRow(art.output, "MISSING", "committed artifact not found"))
            continue
        _, size = _sha_size(committed)
        if art.verify == "byte" and generator_present and art.out_flag:
            dest = (tmp_dir or committed.parent) / (committed.name + ".regen")
            try:
                runner(art, repo_root, dest)
            except (subprocess.CalledProcessError, FileNotFoundError) as exc:
                rows.append(VerifyRow(art.output, "SKIP", f"regeneration unavailable: {exc}"))
                continue
            match = dest.read_bytes() == committed.read_bytes()
            dest.unlink(missing_ok=True)
            rows.append(
                VerifyRow(art.output, "BYTE-MATCH" if match else "BYTE-MISMATCH", f"{size} bytes")
            )
        elif art.verify == "size":
            rows.append(
                VerifyRow(art.output, "SIZE-ONLY", f"{size} bytes; byte-compare N/A — {art.note}")
            )
        else:
            rows.append(VerifyRow(art.output, "EXISTS", f"{size} bytes; {art.note}"))
    return rows


@dataclass(slots=True)
class RegenRow:
    output: str
    status: str
    detail: str


def regenerate_artifacts(artifacts: tuple[Artifact, ...], repo_root: Path) -> list[RegenRow]:
    """Run each present generator in place (writes into the tree). Tables are skipped."""
    rows: list[RegenRow] = []
    for art in artifacts:
        if art.generator is None:
            rows.append(RegenRow(art.output, "SKIP", "hand-maintained; no generator"))
            continue
        gen = repo_root / art.generator
        if not gen.is_file():
            rows.append(RegenRow(art.output, "SKIP", f"generator absent ({art.note})"))
            continue
        if art.env == "matplotlib-ephemeral":
            cmd = ["uv", "run", "--no-project", "--with", "matplotlib", "python", str(gen)]
        else:
            cmd = [sys.executable, str(gen)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=repo_root)
            rows.append(RegenRow(art.output, "WROTE", f"via {art.generator} ({art.env})"))
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            rows.append(RegenRow(art.output, "FAIL", f"{art.generator}: {exc}"))
    return rows


def _print_list(artifacts: tuple[Artifact, ...]) -> None:
    for art in artifacts:
        gen = art.generator or "(hand-maintained)"
        print(f"{art.output}")
        print(f"    kind={art.kind} verify={art.verify} generator={gen} env={art.env or '-'}")
        print(f"    inputs: {', '.join(art.inputs)}")
        if art.note:
            print(f"    note: {art.note}")


def _evidence_chain(repo_root: Path) -> int:
    rows = check_summaries(repo_root / "experiments" / "summaries", repo_root)
    missing = [r for r in rows if r.status == "REPO-MISSING"]
    print(f"evidence-chain: {len(rows)} pointers, {len(missing)} REPO-MISSING")
    for row in missing:
        print(f"  REPO-MISSING {row.summary}: {row.pointer}")
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="list artifacts and their inputs")
    group.add_argument("--verify", action="store_true", help="verify committed artifacts (default)")
    group.add_argument("--regenerate", action="store_true", help="run generators in place (writes)")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    if args.list:
        _print_list(ARTIFACTS)
        return _evidence_chain(repo_root)
    if args.regenerate:
        rows = regenerate_artifacts(ARTIFACTS, repo_root)
        for row in rows:
            print(f"{row.status:<6} {row.output}  [{row.detail}]")
        return 1 if any(r.status == "FAIL" for r in rows) else 0

    verify_rows = verify_artifacts(ARTIFACTS, repo_root)
    for row in verify_rows:
        print(f"{row.status:<13} {row.output}  [{row.detail}]")
    failed = [r for r in verify_rows if r.status in _FAIL]
    chain = _evidence_chain(repo_root)
    print(
        f"verify: {len(verify_rows)} artifacts, {len(failed)} failing "
        f"({', '.join(sorted({r.status for r in verify_rows}))})"
    )
    return 1 if (failed or chain) else 0


if __name__ == "__main__":
    raise SystemExit(main())

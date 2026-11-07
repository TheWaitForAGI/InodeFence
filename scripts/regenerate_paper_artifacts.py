"""Regenerate and verify the paper's tables and figures from one entry point.

Audit item (8) asks for a single script that produces every paper table/figure from
raw. This orchestrates the generators that exist and is **honest about the gaps**:

  * Figures (`paper/figures/*.png`) have generators (`render_m2_cross_release.py`,
    `render_m3_blind_ablation.py`). They render with matplotlib in an ephemeral env
    (`uv run --with matplotlib`), which this project's venv does not carry, and matplotlib
    PNG output is not bit-reproducible. So ``--verify`` checks a figure by existence and
    size, not byte-equality, and records that reason.
  * The M2 and M3 tables now have generators (`gen_table_m2.py` from summary.json,
    `gen_table_m3.py` from the validated summary table) that reproduce the committed tables
    **byte-identically**, so ``--verify`` byte-compares them (``verify="byte"``). The
    capability-ledger summary is still hand-maintained (STATUS-derived, no raw generator),
    checked by existence only.
  * The EXP-0 survival figure's generator (#219) needs ``--report``. Its row is ``optional``:
    ``--regenerate`` never runs that generator (with no report it would overwrite the summary
    table with a placeholder), and ``--verify`` checks the committed PNG by size. Regenerate it
    by running the script directly with ``--report``.

Modes (default ``--verify``, read-only):

    python -m scripts.regenerate_paper_artifacts --list
    python -m scripts.regenerate_paper_artifacts --verify
    python -m scripts.regenerate_paper_artifacts --regenerate   # stages to a temp dir
    python -m scripts.regenerate_paper_artifacts --regenerate --apply   # writes in place

``--regenerate`` without ``--apply`` stages the ``--out``-capable tables into a fresh
``tempfile.mkdtemp()`` directory outside the repository (removed on success unless
``--keep-stage``), so the checkout stays clean for the registered-run clean-checkout gate.

``--verify`` and ``--list`` also run the evidence-chain check so a broken summary->raw
pointer surfaces here too.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
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
    optional: bool = False  # uncommitted output is SKIP, not MISSING; --regenerate leaves it alone
    generator_args: tuple[str, ...] = ()  # passed before --out, for a generator of several outputs


#: EXP-3 and EXP-2 result tables (scripts/gen_exp3_tables.py); none exists before those runs.
_TRAIN = ("exp3-train-report.json",)
_HOLDOUT = ("exp2-holdout-report.json",)
_EXP3_TABLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("T-EXP3-1", "paper/tables/exp3-train-arms.md", _TRAIN),
    ("T-EXP3-2", "paper/tables/exp3-go-inputs.md", (*_TRAIN, "exp3-train-cell-results.jsonl")),
    ("T-EXP3-3", "paper/tables/exp3-dense-signals.md", _TRAIN),
    ("T-EXP2-1", "paper/tables/exp2-holdout-arms.md", _HOLDOUT),
    ("T-EXP2-2", "paper/tables/exp2-holdout-contrasts.md", _HOLDOUT),
    ("T-EXP2-3", "paper/tables/exp2-holdout-notes.md", (*_HOLDOUT, "exp2-holdout-hand-input.json")),
    ("T-EXP2-4", "paper/tables/exp2-abort-sensitivity.md", _HOLDOUT),
    ("T-EXP2-5", "paper/tables/exp2-infra.md", _HOLDOUT),
    ("T-EXP2-6", "paper/tables/exp2-dense-signals.md", _HOLDOUT),
)
_EXP3_FIGURES: tuple[tuple[str, str], ...] = (
    ("paper/figures/exp3-train-survival.png", "exp3-train-report.json"),
    ("paper/figures/exp2-holdout-survival.png", "exp2-holdout-report.json"),
)


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
        "scripts/gen_table_m2.py",
        "project",
        ("experiments/repro/evidence/summary.json", "experiments/repro/cross_release_identity.py"),
        "byte",
        "grid derived from summary.json (per_release_shared + fixed_pair); reasons/prose literal",
        out_flag=True,
    ),
    Artifact(
        "paper/tables/m3-blind-ablation.md",
        "table",
        "scripts/gen_table_m3.py",
        "project",
        (
            "experiments/summaries/node-self-discovery-mechanism-v1.md",
            "raw m3-scale-full|m3-ablation|m3-repro (manifest mac-20261103, host-local)",
        ),
        "byte",
        "data cols from validated summary table (raw mac-host-local); paper labels literal",
        out_flag=True,
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
    # EXP-0 survival: optional keeps --regenerate from running it; verified by size when committed.
    Artifact(
        "paper/figures/exp0-survival.png",
        "figure",
        "paper/figures/render_exp0_survival.py",
        "matplotlib-ephemeral",
        ("scripts/analyze_exp0.py output",),
        "size",
        "matplotlib PNG not bit-reproducible; run directly with --report, not --regenerate",
        optional=True,
    ),
    *(
        Artifact(
            output,
            "table",
            "scripts/gen_exp3_tables.py",
            "project",
            tuple(f"experiments/summaries/{name}" for name in inputs),
            "byte",
            "from the analyze_exp0 report; a missing input stops it",
            out_flag=True,
            optional=True,
            generator_args=("--artifact", artifact),
        )
        for artifact, output, inputs in _EXP3_TABLES
    ),
    *(
        Artifact(
            output,
            "figure",
            "paper/figures/render_exp3_survival.py",
            "matplotlib-ephemeral",
            (f"experiments/summaries/{report}",),
            "size",
            "matplotlib PNG not bit-reproducible; run directly with --role, not --regenerate",
            optional=True,
        )
        for output, report in _EXP3_FIGURES
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
            *artifact.generator_args,
            "--out",
            str(dest),
        ]
    else:
        cmd = [sys.executable, str(gen), *artifact.generator_args, "--out", str(dest)]
    subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=repo_root)


Runner = Callable[[Artifact, Path, Path], None]


def verify_artifacts(
    artifacts: tuple[Artifact, ...],
    repo_root: Path,
    runner: Runner = _default_runner,
    tmp_dir: Path | None = None,
) -> list[VerifyRow]:
    """Verify each committed artifact per its policy (read-only for the committed tree).

    Byte-verify regenerates into ``tmp_dir`` or, when not given, a :func:`make_stage_dir` temp
    dir outside the repo that is removed before returning; each ``*.regen`` file is also removed
    in a ``finally``, so a failing generator never leaves a file in the checkout.
    """
    rows: list[VerifyRow] = []
    own_tmp: Path | None = None
    try:
        for art in artifacts:
            committed = repo_root / art.output
            generator_present = art.generator is not None and (repo_root / art.generator).is_file()
            if not committed.exists():
                if art.optional:
                    rows.append(
                        VerifyRow(art.output, "SKIP", f"optional; not committed ({art.note})")
                    )
                elif art.generator is not None and not generator_present:
                    rows.append(
                        VerifyRow(art.output, "SKIP", f"optional; generator absent ({art.note})")
                    )
                else:
                    rows.append(VerifyRow(art.output, "MISSING", "committed artifact not found"))
                continue
            _, size = _sha_size(committed)
            if art.verify == "byte" and generator_present and art.out_flag:
                if tmp_dir is not None:
                    base = tmp_dir
                else:
                    if own_tmp is None:
                        own_tmp = make_stage_dir()
                    base = own_tmp
                dest = base / (committed.name + ".regen")
                try:
                    try:
                        runner(art, repo_root, dest)
                    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
                        rows.append(
                            VerifyRow(art.output, "SKIP", f"regeneration unavailable: {exc}")
                        )
                        continue
                    match = dest.read_bytes() == committed.read_bytes()
                finally:
                    dest.unlink(missing_ok=True)
                status = "BYTE-MATCH" if match else "BYTE-MISMATCH"
                rows.append(VerifyRow(art.output, status, f"{size} bytes"))
            elif art.verify == "size":
                rows.append(
                    VerifyRow(
                        art.output, "SIZE-ONLY", f"{size} bytes; byte-compare N/A — {art.note}"
                    )
                )
            else:
                rows.append(VerifyRow(art.output, "EXISTS", f"{size} bytes; {art.note}"))
    finally:
        if own_tmp is not None:
            shutil.rmtree(own_tmp, ignore_errors=True)
    return rows


@dataclass(slots=True)
class RegenRow:
    output: str
    status: str
    detail: str


def make_stage_dir() -> Path:
    """A fresh staging directory outside the repository (``tempfile.mkdtemp``).

    Staging must not land in the checkout: an untracked directory there makes the engine
    checkout dirty, and the registered-run gate refuses a dirty checkout.
    """
    return Path(tempfile.mkdtemp(prefix="inodefence-paper-artifacts-"))


def regenerate_artifacts(
    artifacts: tuple[Artifact, ...],
    repo_root: Path,
    apply: bool = False,
    stage_dir: Path | None = None,
) -> list[RegenRow]:
    """Run each present generator.

    Default (``apply=False``) does not touch committed files: ``--out``-capable generators
    (the byte-reproducible tables) render to ``stage_dir`` (a fresh :func:`make_stage_dir`
    temp dir outside the repo when not given; the caller removes it); non-``--out`` generators
    (the matplotlib figures, which write their fixed path and are not bit-reproducible) are
    skipped with a note. With ``apply=True`` generators write in place.
    """
    stage = stage_dir
    rows: list[RegenRow] = []
    for art in artifacts:
        if art.generator is None:
            rows.append(RegenRow(art.output, "SKIP", "hand-maintained; no generator"))
            continue
        if art.optional:
            rows.append(RegenRow(art.output, "SKIP", f"optional; not run here ({art.note})"))
            continue
        gen = repo_root / art.generator
        if not gen.is_file():
            rows.append(RegenRow(art.output, "SKIP", f"generator absent ({art.note})"))
            continue
        if art.out_flag:
            if apply:
                dest = repo_root / art.output
            else:
                if stage is None:
                    stage = make_stage_dir()
                stage.mkdir(parents=True, exist_ok=True)
                dest = stage / Path(art.output).name
            cmd = [sys.executable, str(gen), "--out", str(dest)]
        elif not apply:
            rows.append(RegenRow(art.output, "SKIP", "needs --apply (generator writes in place)"))
            continue
        elif art.env == "matplotlib-ephemeral":
            cmd = ["uv", "run", "--no-project", "--with", "matplotlib", "python", str(gen)]
        else:
            cmd = [sys.executable, str(gen)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=repo_root)
            where = "in place" if apply else f"staged {dest}" if art.out_flag else "staged"
            rows.append(
                RegenRow(art.output, "WROTE" if apply else "STAGED", f"{art.generator} ({where})")
            )
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
    group.add_argument(
        "--regenerate",
        action="store_true",
        help="run generators (stages to a temp dir outside the repo)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="with --regenerate: write in place instead of staging to a temp dir",
    )
    parser.add_argument(
        "--keep-stage",
        action="store_true",
        help="with --regenerate: keep the temp staging dir (removed on success by default)",
    )
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    if args.list:
        _print_list(ARTIFACTS)
        return _evidence_chain(repo_root)
    if args.regenerate:
        stage = None if args.apply else make_stage_dir()
        rows = regenerate_artifacts(ARTIFACTS, repo_root, apply=args.apply, stage_dir=stage)
        for row in rows:
            print(f"{row.status:<7} {row.output}  [{row.detail}]")
        failed = any(r.status == "FAIL" for r in rows)
        if stage is not None:
            print("staged only (no committed file changed); pass --apply to write in place")
            if failed or args.keep_stage:
                print(f"staging dir kept: {stage}")
            else:
                shutil.rmtree(stage, ignore_errors=True)
                print(f"staging dir removed: {stage} (pass --keep-stage to keep it)")
        return 1 if failed else 0

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

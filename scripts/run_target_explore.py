"""make target-explore: point the fuzzer at a node-tar version and run the existing loop on it.

This CONNECTS an arbitrary node-tar version (``latest`` or an exact version) to the existing
state-aware mutation/feedback loop, so a distributor can try their version before releasing it.
It does not run an experiment or a campaign -- the person using the tool does that.

Flow (one command): prepare the image host-side (network, via ``ensure_image`` -- resolve
``latest``, reuse or build, verify installed version / harness / effect producer offline) -> run
the loop inside the isolated controller (``effect-demo-explore`` through
``local_node_tar_smoke.sh``; the controller's disposable sandbox, sentinel and strict isolation
are unchanged) -> read the loop's report -> write a small exploration summary. Output goes OUTSIDE
the repository (default ``~/inodefence-evidence/target-explore/``).

Mutation vocabulary and the loop are exactly the existing effect demo's; nothing new is added.

FOUND A BOUNDARY VIOLATION ON A MAINTAINED VERSION? Handle it responsibly, in order:
  1. keep the result, the inputs and the logs in the OFF-repository output folder only -- never in
     any branch, commit, PR body, PR comment, issue or log (this repository is public);
  2. re-run the same version twice more to see whether it reproduces;
  3. report the version, the violation count and the off-repo folder path to the maintainers of the
     extractor first -- disclosure to anyone else comes after they have had a chance to fix it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.run_node_tar_target import PreparedNodeTar, ensure_image

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE = REPO_ROOT / "scripts" / "local_node_tar_smoke.sh"
DEFAULT_OUT = Path.home() / "inodefence-evidence" / "target-explore"
TARGETS = ("node-tar",)


def controller_report_path(out: Path, run_id: str) -> Path:
    """Where ``local_node_tar_smoke.sh explore`` writes the loop's report for this run."""
    return out / f"inodefence-effect-explore-{run_id}.json"


def run_controller(
    prepared: PreparedNodeTar,
    *,
    out: Path,
    run_id: str,
    budget: int,
    seed: int,
    python: str,
    runner=subprocess.run,
) -> Path:
    """Run the loop in the controller via the smoke script; return the report path it wrote.

    The image is already prepared host-side; the script only builds the controller/helper images,
    creates the disposable controller, and drives ``effect-demo-explore``. Network stays off the
    extraction containers (the controller's isolation, unchanged).
    """
    env = {
        **os.environ,
        "EXPLORE_IMAGE": prepared.image_ref,
        "TAR_VERSION": prepared.version,
        "DEMO_BUDGET": str(budget),
        "DEMO_SEED": str(seed),
        "INODEFENCE_EVIDENCE_DIR": str(out),
        "RUN_ID": run_id,
        "PYTHON": python,
    }
    done = runner(["bash", str(SMOKE), "explore"], env=env, cwd=str(REPO_ROOT))
    if done.returncode != 0:
        raise RuntimeError(f"controller run failed (exit {done.returncode}); see output above")
    report = controller_report_path(out, run_id)
    if not report.is_file():
        raise RuntimeError(f"controller run produced no report at {report}")
    return report


def summarize(
    report: dict, prepared: PreparedNodeTar, *, seed: int, budget: int, report_path: Path
) -> dict:
    """The small, user-facing summary: only what someone trying their version needs.

    No research framing -- just the version, the run settings, how many cases ran, how many
    violations the oracle flagged, the image id, and where the reproduction material is.
    """
    aborted = report.get("aborted")
    runs = len(report.get("native_checks", [])) if aborted is None else int(aborted["step_index"])
    violations = len(report.get("oracle_detected_events", []))
    steps_path = report_path.with_name(report_path.stem + ".steps.jsonl")
    return {
        "target": "node-tar",
        "requested": prepared.requested,
        "version": prepared.version,
        "registry_prepared": prepared.exploratory,
        "seed": seed,
        "budget": budget,
        "runs": runs,
        "violations": violations,
        "aborted": None if aborted is None else aborted.get("reason"),
        "image_id": prepared.image_id,
        "result_file": str(report_path),
        "reproduction": {"result_file": str(report_path), "steps": str(steps_path)},
    }


def _print_summary(summary: dict) -> None:
    line = (
        f"TARGET-EXPLORE node-tar version={summary['version']} "
        f"(requested {summary['requested']}) seed={summary['seed']} budget={summary['budget']} "
        f"runs={summary['runs']} violations={summary['violations']} "
        f"image={summary['image_id']} (exploration run)"
    )
    if summary["aborted"]:
        line += f" ABORTED: {summary['aborted']}"
    print(line)
    print(f"result: {summary['result_file']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="prepare a node-tar version and run the existing effect loop on it (exploration)",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", default="node-tar", choices=TARGETS)
    parser.add_argument("--version", required=True, help="latest or an exact node-tar version")
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output dir (outside the repo)")
    parser.add_argument("--image-tag-suffix", default="")
    parser.add_argument(
        "--auto-prepare",
        action="store_true",
        help="prepare (resolve/build/verify) the image; required for a real run",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan; prepare/run nothing")
    args = parser.parse_args(argv)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "target": args.target,
                    "version": args.version,
                    "seed": args.seed,
                    "budget": args.budget,
                    "out": str(args.out),
                    "note": "dry-run: nothing resolved, prepared, run or written",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.auto_prepare:
        parser.error("pass AUTO_PREPARE=1 (--auto-prepare) to prepare the image and run")

    try:
        prepared = ensure_image(args.version, image_tag_suffix=args.image_tag_suffix)
    except ValueError as error:
        print(f"TARGET-EXPLORE SETUP: {error}", file=sys.stderr)
        return 3

    args.out.mkdir(parents=True, exist_ok=True)
    run_id = f"{prepared.version}-{args.seed}-{args.budget}{args.image_tag_suffix}"
    python = os.environ.get("PYTHON", sys.executable)
    report_path = run_controller(
        prepared, out=args.out, run_id=run_id, budget=args.budget, seed=args.seed, python=python
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = summarize(report, prepared, seed=args.seed, budget=args.budget, report_path=report_path)
    summary_path = report_path.with_name(report_path.stem + ".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print_summary(summary)
    print(f"summary: {summary_path}")
    return 1 if summary["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

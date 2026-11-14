"""make target-explore: point the fuzzer at a node-tar version and run the existing loop on it.

This CONNECTS an arbitrary node-tar version (``latest`` or an exact version) to the existing
state-aware mutation/feedback loop, so a distributor can try their version before releasing it.
It does not run an experiment or a campaign -- the person using the tool does that.

Flow (one command): prepare the image host-side (network, via ``ensure_image`` -- resolve
``latest``, reuse or build, verify installed version / harness / effect producer offline) -> run
the loop inside the isolated controller (``effect-demo-explore`` through
``local_node_tar_smoke.sh``; the controller's disposable sandbox, sentinel and strict isolation
are unchanged) -> convert the loop's report into the common ``inodefence-target-result-v1`` result
(``mode=campaign``). Output goes OUTSIDE the repository and outside ``~/inodefence-evidence``
(default ``~/inodefence-explore``).

Only the inputs of cases the oracle flagged as violations are saved (a large budget makes keeping
every case's TAR wasteful). ``cases[]`` still lists every run with its verdict, because the common
format ties ``runs_to_first_violation`` and ``budget`` to the run count.

FOUND A BOUNDARY VIOLATION ON A MAINTAINED VERSION? Handle it responsibly, in order:
  1. keep the result, the inputs and the logs in the OFF-repository output folder only -- never in
     any branch, commit, PR body, PR comment, issue or log (this repository is public);
  2. re-run the same version twice more to see whether it reproduces;
  3. report the version, the violation count and the off-repo folder path to the maintainers of the
     extractor first -- disclosure to anyone else comes after they have had a chance to fix it.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from scripts.run_node_tar_target import PreparedNodeTar, ensure_image
from scripts.run_target import engine_provenance

from inodefence.target_result import (
    CampaignInfo,
    CaseVerdict,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE = REPO_ROOT / "scripts" / "local_node_tar_smoke.sh"
# Outside the repo AND outside ~/inodefence-evidence (confirmatory evidence lives there).
DEFAULT_OUT = Path.home() / "inodefence-explore"
TARGETS = ("node-tar",)
OBSERVED_CONTRACTS = ("C0", "C1", "C2")  # the effect path takes a full before/after snapshot


def controller_report_path(out: Path, run_id: str) -> Path:
    """Where ``local_node_tar_smoke.sh explore`` writes the loop's report for this run."""
    return out / "target-explore" / f"inodefence-effect-explore-{run_id}.json"


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
    creates the disposable controller, and drives ``effect-demo-explore``. The target containers'
    isolation is the controller's, unchanged.
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


def build_campaign_result(
    report: dict, prepared: PreparedNodeTar, *, seed: int, budget: int
) -> tuple[TargetResult, dict[str, bytes]]:
    """Convert the loop report into the common campaign result, plus the violating TARs to save.

    ``cases[]`` lists every run with its C0/C1/C2 verdict (the schema ties
    ``runs_to_first_violation`` and ``budget`` to the run count). Only violating cases get a saved
    input; ``repro_inputs`` is that subset. A small converter rather than a reuse of
    ``build_explore_result``, which would save every case's TAR.
    """
    records = report.get("case_records", [])
    cases = tuple(
        CaseVerdict(f"step-{r['run_index']}", r["outcome"], r["c0"], r["c1"], r["c2"])
        for r in records
    )
    repro = []
    tar_files: dict[str, bytes] = {}
    first_violation: int | None = None
    for item in report.get("violation_inputs", []):
        run_index = item["run_index"]
        tar = base64.b64decode(item["tar_b64"])
        if sha256(tar).hexdigest() != item["tar_sha256"]:
            raise ValueError(f"violation input step-{run_index} failed its SHA-256 check")
        tar_path = f"inputs/step-{run_index}.tar"
        tar_files[tar_path] = tar
        repro.append(repro_input(f"step-{run_index}", tar_path, tar))
        rank = int(run_index) + 1
        first_violation = rank if first_violation is None else min(first_violation, rank)
    base_prov = engine_provenance(prepared.image_ref)
    provenance = type(base_prov)(
        engine_sha=base_prov.engine_sha,
        engine_dirty=base_prov.engine_dirty,
        image_ref=prepared.image_ref,
        image_id=prepared.image_id,
    )
    result = TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version=prepared.version),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=OBSERVED_CONTRACTS,
        cases=cases,
        repro_inputs=tuple(repro),
        provenance=provenance,
        campaign=CampaignInfo(seed=seed, budget=budget, runs_to_first_violation=first_violation),
    )
    return result, tar_files


def write_result(out_dir: Path, result: TargetResult, tar_files: dict[str, bytes]) -> Path:
    """Write result.json and the violating TARs under ``out_dir``; refuse to overwrite."""
    result_path = out_dir / "result.json"
    if result_path.exists():
        raise FileExistsError(f"refusing to overwrite {result_path}")
    (out_dir / "inputs").mkdir(parents=True, exist_ok=True)
    for tar_path, data in tar_files.items():
        (out_dir / tar_path).write_bytes(data)
    result_path.write_text(result.dumps(), encoding="utf-8")
    return result_path


def _print_summary(result: TargetResult, prepared: PreparedNodeTar, report_path: Path) -> None:
    print(
        f"TARGET-EXPLORE {result.verdict.value} node-tar version={prepared.version} "
        f"(requested {prepared.requested}) runs={result.executed} "
        f"violations={len(result.violating_cases)} image={prepared.image_id} (exploration run)"
    )
    print(f"loop report: {report_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="prepare a node-tar version and run the existing effect loop on it",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", default="node-tar", choices=TARGETS)
    parser.add_argument("--version", required=True, help="latest or an exact node-tar version")
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="output dir (outside the repo)"
    )
    parser.add_argument("--image-tag-suffix", default="")
    parser.add_argument(
        "--auto-prepare",
        action="store_true",
        help="prepare (resolve/build/verify) the image; required for a real run",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan; prepare/run nothing"
    )
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
    result, tar_files = build_campaign_result(report, prepared, seed=args.seed, budget=args.budget)
    out_dir = report_path.parent / f"{run_id}-result"
    result_path = write_result(out_dir, result, tar_files)
    _print_summary(result, prepared, report_path)
    print(f"result: {result_path}")
    return 1 if result.violating_cases else 0


if __name__ == "__main__":
    raise SystemExit(main())

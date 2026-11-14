"""oras-go's exploration hook: open the existing oras-go campaign on a prepared oras-go image.

This is the oras-go implementation of ``TargetAdapter.explore`` (``scripts.run_target``). The
common driver (``scripts.run_target_explore``) prepares the image (``latest`` or an exact version,
through the same prepare layer as ``make target-run``: a committed go.mod/go.sum or the Go module
proxy with its offline checks, including the campaign's ``frame`` worker) and passes a
``PreparedTargetImage`` plus target-agnostic ``ExploreOptions``.

Everything oras-go specific stays here: the host script (``local_oras_go_selfdiscover.sh`` with
``EXPLORE_IMAGE``), its controller mode (``oras-go-effect-campaign``: the oras-go mutation/feedback
loop over the ``frame`` worker inside the controller's disposable sandbox and isolated target
containers, unchanged), and the check that the run used exactly the prepared image. The report's
``case_records`` / ``violation_inputs`` have the shape node-tar's exploration report uses, so the
common campaign converter turns them into ``inodefence-target-result-v1`` (``mode=campaign``) and
saves only the violating inputs. Before the campaign, the (possibly reused) image's ``frame``
worker is checked offline (``verify_existing``); after it, a report with fewer run records than
the budget is refused, and any run the program did not judge makes the verdict ERROR, never PASS
(its count and ratio are printed). The mutation policy is the campaign's default (unchanged); its
name is printed with the result.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.run_target import ExploreOptions, ExploreOutcome, PreparedTargetImage

from inodefence.generator import minimal_seed_corpus
from inodefence.target_result import RUN_ERROR, TargetResult
from inodefence.target_result_summary import write_cell_summaries

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "local_oras_go_selfdiscover.sh"
TARGET = "oras-go"
# One campaign must cover all initial seed cases, so a budget below the seed count is refused.
MIN_BUDGET = len(minimal_seed_corpus())


def controller_report_path(out: Path, run_id: str) -> Path:
    """Where ``local_oras_go_selfdiscover.sh`` copies the campaign report for this run."""
    return out / "target-explore" / f"inodefence-oras-go-selfdiscover-{run_id}.json"


def run_controller(
    prepared: PreparedTargetImage,
    *,
    out: Path,
    run_id: str,
    budget: int,
    seed: int,
    python: str,
    runner=subprocess.run,
) -> Path:
    """Run the oras-go campaign in the controller on the prepared image; return the report path.

    The image is already prepared host-side; the script builds only the controller/helper images,
    never the oras-go image (``EXPLORE_IMAGE``), creates the disposable controller and drives the
    existing ``oras-go-effect-campaign`` mode. Target isolation is the controller's, unchanged.
    """
    env = {
        **os.environ,
        "EXPLORE_IMAGE": prepared.image_ref,
        "DEMO_BUDGET": str(budget),
        "DEMO_SEED": str(seed),
        "INODEFENCE_EVIDENCE_DIR": str(out / "target-explore"),
        "RUN_ID": run_id,
        "PYTHON": python,
    }
    done = runner(["bash", str(SCRIPT)], env=env, cwd=str(REPO_ROOT))
    report = controller_report_path(out, run_id)
    if done.returncode != 0:
        raise RuntimeError(f"controller run failed (exit {done.returncode}); see output above")
    if not report.is_file():
        raise RuntimeError(f"controller run produced no report at {report}")
    return report


def verify_existing(prepared: PreparedTargetImage, runner=None) -> str:
    """Offline, before the campaign: the image's ``frame`` worker (what the campaign runs) works.

    A reused image skipped preparation's checks, and an older build may lack the ``frame``
    subcommand; this runs it (``--network none``, nothing mounted) on a benign archive, checks the
    reported oras-go version and that the identity binds as the campaign target. Raises
    ``RuntimeError`` with the reason; returns the check's description.
    """
    from scripts import oras_go_registry_prepare as proxy

    try:
        check = proxy.frame_check(runner or subprocess.run, prepared.image_ref, prepared.version)
    except proxy.RegistryPrepareError as error:
        raise RuntimeError(
            f"{prepared.image_ref}: campaign worker check failed: {error}"
        ) from error
    if not check["ok"]:
        raise RuntimeError(f"{prepared.image_ref}: campaign worker unusable: {check['reason']}")
    return str(check["reason"])


def unjudged(report: dict) -> tuple[int, int]:
    """(runs with no verdict because the run program did not start cleanly, all runs)."""
    records = report.get("case_records", [])
    return sum(1 for r in records if r.get("outcome") == RUN_ERROR), len(records)


def check_report(report: dict, prepared: PreparedTargetImage, budget: int | None = None) -> None:
    """Fail unless the report is a finished run on exactly the prepared image, with records.

    A report with fewer (or more) run records than the budget is refused, so a shortened
    campaign is never read as a clean one.
    """
    if "aborted" in report:
        raise RuntimeError(f"campaign aborted: {report['aborted'].get('reason')}")
    if report.get("image_id") != prepared.image_id:
        raise RuntimeError(
            f"campaign ran image {report.get('image_id')!r}, prepared {prepared.image_id!r}"
        )
    if "case_records" not in report or "violation_inputs" not in report:
        raise RuntimeError("campaign report has no case_records / violation_inputs")
    runs = len(report["case_records"])
    if budget is not None and runs != budget:
        raise RuntimeError(f"campaign report has {runs} run records, budget was {budget}")


def build_result(
    report: dict, prepared: PreparedTargetImage, *, seed: int, budget: int
) -> tuple[TargetResult, dict[str, bytes]]:
    """The common campaign result for oras-go, from the shared exploration-report converter."""
    from scripts.node_tar_explore import build_campaign_result

    result, tar_files = build_campaign_result(report, prepared, seed=seed, budget=budget)
    return dataclasses.replace(result, target=TARGET), tar_files


def explore(prepared: PreparedTargetImage, options: ExploreOptions) -> ExploreOutcome:
    """``TargetAdapter.explore`` for oras-go: run the campaign in the controller, write a result."""
    from scripts.node_tar_explore import write_result

    if options.budget < MIN_BUDGET:
        raise ValueError(f"budget must be >= {MIN_BUDGET} (the loop's seed count)")
    options.out.mkdir(parents=True, exist_ok=True)
    run_id = f"oras-go-{prepared.version}-{options.seed}-{options.budget}{options.image_tag_suffix}"
    python = os.environ.get("PYTHON", sys.executable)
    print(f"TARGET-EXPLORE CHECK {verify_existing(prepared)}")
    report_path = run_controller(
        prepared,
        out=options.out,
        run_id=run_id,
        budget=options.budget,
        seed=options.seed,
        python=python,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    check_report(report, prepared, options.budget)
    result, tar_files = build_result(report, prepared, seed=options.seed, budget=options.budget)
    result_path = write_result(report_path.parent / f"{run_id}-result", result, tar_files)
    try:  # the result is written; a summary failure must not lose it
        write_cell_summaries([result_path])
    except Exception as error:  # noqa: BLE001
        print(f"TARGET-EXPLORE SUMMARY: summary.md not written ({error})", file=sys.stderr)
    policy = (report.get("config") or {}).get("mutation_policy")
    missing, runs = unjudged(report)
    # Any unjudged run makes the common verdict ERROR (never PASS); all unjudged is ERROR too.
    print(
        f"loop report: {report_path} (mutation policy {policy}; unjudged runs {missing}/{runs}"
        f" = {missing / max(runs, 1):.0%})"
    )
    return ExploreOutcome(
        result_path=result_path,
        verdict=result.verdict.value,
        runs=result.executed,
        violations=len(result.violating_cases),
    )

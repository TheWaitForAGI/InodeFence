"""node-tar's exploration hook: open the state-aware effect loop on a prepared node-tar image.

This is the node-tar implementation of ``TargetAdapter.explore`` (``scripts.run_target``). The
common driver (``scripts.run_target_explore``) prepares the image and passes a
``PreparedTargetImage`` plus target-agnostic ``ExploreOptions``; everything here is node-tar
specific -- the controller mode (``effect-demo-explore``), the run program, and the node-tar
observation -- and it emits the common ``inodefence-target-result-v1`` campaign result.

Other extractors register their own ``explore`` hook the same way; a target with no hook reports
"exploration not supported". The result format, options, output and (later) stop conditions and
sinks are reused unchanged across targets.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.explore_result import build_campaign_result, write_result
from scripts.run_target import (
    ExploreOptions,
    ExploreOutcome,
    PreparedTargetImage,
    engine_provenance,
)

from inodefence.evaluation.rds_preregistration import parse_preregistration
from inodefence.generator import minimal_seed_corpus
from inodefence.live_exploration import LivePuller
from inodefence.target_result_summary import write_cell_summaries

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE = REPO_ROOT / "scripts" / "local_node_tar_smoke.sh"
# Writable tmpfs path inside the controller (root is read-only); the host pulls it with docker cp.
CONTROLLER_LIVE_DIR = "/tmp/inodefence-live"
OBSERVED_CONTRACTS = ("C0", "C1", "C2")  # the effect path takes a full before/after snapshot
# One campaign must cover all initial seed cases, so a budget below the seed count is refused.
MIN_BUDGET = len(minimal_seed_corpus())
# Exploration matches the registered S-u sandbox: the same generated sentinel set and observer
# policy the confirmatory EXP-2 holdout uses, so the observed-names vocabulary pool and the
# invalid-trace handling are the experiment's, not a demo default. The values are READ from the
# frozen preregistration (never copied here), so the two cannot drift; the operator can still
# override them, and the run records what it actually used.
REGISTERED_PREREG = REPO_ROOT / "experiments" / "preregistration" / "exp2-v1.md"


def registered_sandbox_defaults() -> tuple[str, str, str]:
    """``(sentinel_seed, sentinel_count, observer_integrity_policy)`` of the registered S-u arm."""
    prereg = parse_preregistration(REGISTERED_PREREG.read_text(encoding="utf-8"))
    return (
        str(prereg.sentinel_generator_seed),
        str(prereg.sentinel_count),
        prereg.observer_integrity_policy or "invalid-continue",
    )


def controller_report_path(out: Path, run_id: str) -> Path:
    """Where ``local_node_tar_smoke.sh explore`` writes the loop's report for this run."""
    return out / "target-explore" / f"inodefence-effect-explore-{run_id}.json"


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
    """Run the loop in the controller via the smoke script; return the report path it wrote.

    The image is already prepared host-side; the script only builds the controller/helper images,
    creates the disposable controller, and drives ``effect-demo-explore``. The target containers'
    isolation is the controller's, unchanged.
    """
    sentinel_seed, sentinel_count, observer_policy = registered_sandbox_defaults()
    # The engine revision is read host-side (the controller's read-only repo mount cannot run git)
    # and recorded in the live meta so a saved violation's replay can tell if the engine has moved.
    engine = engine_provenance(None)
    engine_commit = f"{engine.engine_sha or 'unknown'}{'-dirty' if engine.engine_dirty else ''}"
    env = {
        **os.environ,
        "EXPLORE_IMAGE": prepared.image_ref,
        "TAR_VERSION": prepared.version,
        "DEMO_BUDGET": str(budget),
        "DEMO_SEED": str(seed),
        "DEMO_ENGINE_COMMIT": engine_commit,
        # Registered S-u sandbox defaults (overridable by the operator's own DEMO_* env).
        "DEMO_SENTINEL_SEED": os.environ.get("DEMO_SENTINEL_SEED", sentinel_seed),
        "DEMO_SENTINEL_COUNT": os.environ.get("DEMO_SENTINEL_COUNT", sentinel_count),
        "DEMO_OBSERVER_INTEGRITY_POLICY": os.environ.get(
            "DEMO_OBSERVER_INTEGRITY_POLICY", observer_policy
        ),
        "INODEFENCE_EVIDENCE_DIR": str(out),
        "RUN_ID": run_id,
        "PYTHON": python,
        # The controller writes live snapshots to this tmpfs path; the host pulls it below.
        "DEMO_LIVE_DIR": CONTROLLER_LIVE_DIR,
    }
    # Pull the controller's live folder to the host on a timer while the loop runs, so progress and
    # violation cases appear during the run (and survive a forced stop). The controller name matches
    # the smoke script's ``inodefence-local-controller[-RUN_ID]``; a pull before it exists or after
    # it is gone fails quietly (recorded in fetch.json) and never stops the campaign.
    controller_name = f"inodefence-local-controller{f'-{run_id}' if run_id else ''}"
    # ``<out>/target-explore/<run_id>/live`` so ``inodefence status <out>/target-explore`` finds it
    # (find_live_dirs matches ``*/live``) and parallel runs never share a live folder.
    host_live_dir = out / "target-explore" / run_id / "live"
    puller = LivePuller(controller_name, CONTROLLER_LIVE_DIR, host_live_dir).start()
    try:
        done = runner(["bash", str(SMOKE), "explore"], env=env, cwd=str(REPO_ROOT))
    finally:
        puller.stop()  # one last pull so the final snapshot reaches the host
    if done.returncode != 0:
        raise RuntimeError(f"controller run failed (exit {done.returncode}); see output above")
    report = controller_report_path(out, run_id)
    if not report.is_file():
        raise RuntimeError(f"controller run produced no report at {report}")
    return report


def explore(prepared: PreparedTargetImage, options: ExploreOptions) -> ExploreOutcome:
    """``TargetAdapter.explore`` for node-tar: run the loop in the controller, write the result."""
    if options.budget < MIN_BUDGET:
        raise ValueError(f"budget must be >= {MIN_BUDGET} (the loop's seed count)")
    options.out.mkdir(parents=True, exist_ok=True)
    run_id = f"{prepared.version}-{options.seed}-{options.budget}{options.image_tag_suffix}"
    python = os.environ.get("PYTHON", sys.executable)
    report_path = run_controller(
        prepared,
        out=options.out,
        run_id=run_id,
        budget=options.budget,
        seed=options.seed,
        python=python,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    result, tar_files = build_campaign_result(
        report, prepared, seed=options.seed, budget=options.budget
    )
    result_path = write_result(report_path.parent / f"{run_id}-result", result, tar_files)
    try:  # the result is written; a summary failure must not lose it
        write_cell_summaries([result_path])
    except Exception as error:  # noqa: BLE001
        print(f"TARGET-EXPLORE SUMMARY: summary.md not written ({error})", file=sys.stderr)
    print(f"loop report: {report_path}")
    return ExploreOutcome(
        result_path=result_path,
        verdict=result.verdict.value,
        runs=result.executed,
        violations=len(result.violating_cases),
    )

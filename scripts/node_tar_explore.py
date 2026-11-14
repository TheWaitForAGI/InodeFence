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

import base64
import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from scripts.run_target import (
    ExploreOptions,
    ExploreOutcome,
    PreparedTargetImage,
    engine_provenance,
)

from inodefence.generator import minimal_seed_corpus
from inodefence.target_result import (
    CampaignInfo,
    CaseVerdict,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)
from inodefence.target_result_summary import write_cell_summaries

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE = REPO_ROOT / "scripts" / "local_node_tar_smoke.sh"
OBSERVED_CONTRACTS = ("C0", "C1", "C2")  # the effect path takes a full before/after snapshot
# One campaign must cover all initial seed cases, so a budget below the seed count is refused.
MIN_BUDGET = len(minimal_seed_corpus())


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
    report: dict, prepared: PreparedTargetImage, *, seed: int, budget: int
) -> tuple[TargetResult, dict[str, bytes]]:
    """Convert the loop report into the common campaign result, plus the violating TARs to save.

    ``cases[]`` lists every run with its C0/C1/C2 verdict (the schema ties
    ``runs_to_first_violation`` and ``budget`` to the run count). Only violating cases get a saved
    input; ``repro_inputs`` is that subset.
    """
    cases = tuple(
        CaseVerdict(f"step-{r['run_index']}", r["outcome"], r["c0"], r["c1"], r["c2"])
        for r in report.get("case_records", [])
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
    base = engine_provenance(prepared.image_ref)
    provenance = type(base)(
        base.engine_sha, base.engine_dirty, prepared.image_ref, prepared.image_id
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

"""python-tarfile's exploration hook: the shared effect loop on one prepared runtime + one filter.

This is the python-tarfile implementation of ``TargetAdapter.explore`` (``scripts.run_target``).
The common driver (``scripts.run_target_explore``) resolves ``latest`` / ``X.Y`` / ``X.Y.Z`` and
prepares the official ``python:X.Y.Z-slim`` image (``scripts.run_python_tarfile_target``); this
hook then

1. builds or reuses the producer image on top of it (``scripts.python_tarfile_producer``: only the
   worker file is added; checked offline before it is named and again before every reuse);
2. runs the ``python-tarfile-effect-campaign`` controller mode through
   ``scripts/local_python_tarfile_explore.sh`` -- the target runs only inside the disposable
   controller via the common container backend;
3. converts the loop report into the common ``inodefence-target-result-v1`` campaign result
   (``axes.runtime_version`` + ``axes.extraction_filter``; one of each per campaign).

Silent negatives: any step without a verdict makes the result ERROR (the common verdict rule), and
a report whose every step is undetermined or that aborted is an error, never a PASS.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Any

from scripts import python_tarfile_producer as producer
from scripts import run_python_tarfile_target as rpt
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
    Preparation,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)
from inodefence.target_result_summary import write_cell_summaries

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "scripts" / "local_python_tarfile_explore.sh"
OBSERVED_CONTRACTS = ("C0", "C1", "C2")  # the effect path takes a full before/after snapshot
MIN_BUDGET = len(minimal_seed_corpus())
#: Filters exploration accepts now; ``fully_trusted`` is held until that use is approved.
EXPLORE_FILTERS = ("data",)

Runner = Callable[..., subprocess.CompletedProcess[Any]]


def report_path(out: Path, run_id: str) -> Path:
    return out / "target-explore" / f"inodefence-python-tarfile-explore-{run_id}.json"


def run_controller(
    producer_ref: str,
    version: str,
    extraction_filter: str,
    *,
    out: Path,
    run_id: str,
    budget: int,
    seed: int,
    runner: Runner = subprocess.run,
) -> Path:
    """Run the controller mode via the launcher script; return the report path it wrote."""
    env = {
        **os.environ,
        "EXPLORE_IMAGE": producer_ref,
        "RUNTIME_VERSION": version,
        "EXTRACTION_FILTER": extraction_filter,
        "DEMO_BUDGET": str(budget),
        "DEMO_SEED": str(seed),
        "INODEFENCE_EVIDENCE_DIR": str(out),
        "RUN_ID": run_id,
        "PYTHON": os.environ.get("PYTHON", sys.executable),
    }
    done = runner(["bash", str(LAUNCHER)], env=env, cwd=str(REPO_ROOT))
    report = report_path(out, run_id)
    if done.returncode != 0 and not report.is_file():
        raise ValueError(f"controller run failed (exit {done.returncode}); see output above")
    if not report.is_file():
        raise ValueError(f"controller run produced no report at {report}")
    return report


def _preparation(prepared: PreparedTargetImage, made: producer.ProducerImage) -> Preparation:
    resolved = rpt._RESOLVED.get(prepared.version)
    spec, resolved_at = (resolved[0], resolved[1]) if resolved is not None else (None, None)
    return Preparation(
        method="official-image",
        requested_version=prepared.version,
        installed_version=made.python_version,
        lock_sha256=None,
        worker_sha256=None,
        recipe=(
            f"official {prepared.image_ref} ({prepared.image_id}) + "
            f"tools/python-tarfile/effect/worker.py -> {made.image_ref} ({made.image_id})"
        ),
        requested_spec=spec,
        resolved_at=resolved_at,
        producer_sha256=made.worker_sha256,
        producer_check=made.check,
    )


def build_campaign_result(
    report: dict[str, Any],
    prepared: PreparedTargetImage,
    made: producer.ProducerImage,
    extraction_filter: str,
    *,
    seed: int,
    budget: int,
) -> tuple[TargetResult, dict[str, bytes]]:
    """Loop report -> common campaign result plus the violating TARs (only those are saved)."""
    if "aborted" in report:
        raise ValueError(f"exploration aborted: {report['aborted'].get('reason')}")
    if report.get("all_undetermined"):
        raise ValueError("every step was undetermined (no verdict); refusing to report a result")
    if (report.get("runtime_version"), report.get("extraction_filter")) != (
        prepared.version,
        extraction_filter,
    ):
        raise ValueError("loop report is for a different runtime or filter")
    cases = tuple(
        CaseVerdict(
            f"step-{r['run_index']}",
            "run_error" if r["outcome"] == "run_error" else r["outcome"],
            r["c0"],
            r["c1"],
            r["c2"],
        )
        for r in report.get("case_records", [])
    )
    repro = []
    tar_files: dict[str, bytes] = {}
    first: int | None = None
    for item in report.get("violation_inputs", []):
        run_index = int(item["run_index"])
        tar = base64.b64decode(item["tar_b64"])
        if sha256(tar).hexdigest() != item["tar_sha256"]:
            raise ValueError(f"violation input step-{run_index} failed its SHA-256 check")
        tar_path = f"inputs/step-{run_index}.tar"
        tar_files[tar_path] = tar
        repro.append(repro_input(f"step-{run_index}", tar_path, tar))
        first = run_index + 1 if first is None else min(first, run_index + 1)
    base = engine_provenance(made.image_ref)
    provenance = type(base)(base.engine_sha, base.engine_dirty, made.image_ref, made.image_id)
    result = TargetResult(
        target=rpt.TARGET,
        axes=TargetAxes(runtime_version=prepared.version, extraction_filter=extraction_filter),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=OBSERVED_CONTRACTS,
        cases=cases,
        repro_inputs=tuple(repro),
        provenance=provenance,
        preparation=_preparation(prepared, made),
        campaign=CampaignInfo(seed=seed, budget=budget, runs_to_first_violation=first),
    )
    return result, tar_files


def write_result(out_dir: Path, result: TargetResult, tar_files: dict[str, bytes]) -> Path:
    result_path = out_dir / "result.json"
    if result_path.exists():
        raise FileExistsError(f"refusing to overwrite {result_path}")
    (out_dir / "inputs").mkdir(parents=True, exist_ok=True)
    for tar_path, data in tar_files.items():
        (out_dir / tar_path).write_bytes(data)
    result_path.write_text(result.dumps(), encoding="utf-8")
    return result_path


def explore(
    prepared: PreparedTargetImage,
    options: ExploreOptions,
    *,
    runner: Runner | None = None,
    ensure: Callable[..., producer.ProducerImage] | None = None,
) -> ExploreOutcome:
    """``TargetAdapter.explore`` for python-tarfile (one runtime image, one filter)."""
    extraction_filter = options.extraction_filter
    if extraction_filter is None:
        raise ValueError("python-tarfile exploration needs one --extraction-filter (data)")
    if extraction_filter not in EXPLORE_FILTERS:
        raise ValueError(
            f"extraction filter {extraction_filter!r} is not explored yet "
            f"(allowed: {', '.join(EXPLORE_FILTERS)}; fully_trusted is held until approved)"
        )
    if options.budget < MIN_BUDGET:
        raise ValueError(f"budget must be >= {MIN_BUDGET} (the loop's seed count)")
    ensure = ensure or producer.ensure_producer_image
    made = ensure(prepared.image_ref, prepared.version, suffix=options.image_tag_suffix)
    options.out.mkdir(parents=True, exist_ok=True)
    run_id = (
        f"py{prepared.version}-{extraction_filter}-{options.seed}-{options.budget}"
        f"{options.image_tag_suffix}"
    )
    path = run_controller(
        made.image_ref,
        prepared.version,
        extraction_filter,
        out=options.out,
        run_id=run_id,
        budget=options.budget,
        seed=options.seed,
        runner=runner or subprocess.run,
    )
    report = json.loads(path.read_text(encoding="utf-8"))
    result, tar_files = build_campaign_result(
        report, prepared, made, extraction_filter, seed=options.seed, budget=options.budget
    )
    result_path = write_result(path.parent / f"{run_id}-result", result, tar_files)
    try:  # the result is written; a summary failure must not lose it
        write_cell_summaries([result_path])
    except Exception as error:  # noqa: BLE001
        print(f"TARGET-EXPLORE SUMMARY: summary.md not written ({error})", file=sys.stderr)
    print(f"loop report: {path}")
    return ExploreOutcome(
        result_path=result_path,
        verdict=result.verdict.value,
        runs=result.executed,
        violations=len(result.violating_cases),
    )

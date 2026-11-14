"""python-tarfile's exploration hook: the shared effect loop on one prepared runtime + one filter.

This is the python-tarfile implementation of ``TargetAdapter.explore`` (``scripts.run_target``).
The common driver (``scripts.run_target_explore``) resolves ``latest`` / ``X.Y`` / ``X.Y.Z``,
validates the declared ``--extraction-filter`` option (``run_python_tarfile_target``), prepares
the official ``python:X.Y.Z-slim`` image, and passes the option in
``ExploreOptions.target_options``. This hook then

1. refuses a filter exploration does not take yet (``EXPLORE_FILTERS``; ``fully_trusted`` is held,
   the reason is in the message);
2. builds or reuses the producer image on top of the runtime image
   (``scripts.python_tarfile_producer``: only the worker file is added; checked offline before it
   is named and again before every reuse);
3. runs the ``python-tarfile-effect-campaign`` controller mode through
   ``scripts/local_python_tarfile_explore.sh`` -- the target runs only inside the disposable
   controller via the common container backend;
4. converts the loop report with the common converter (``scripts.explore_result``) and only then
   sets what is python-specific: the two axes (``runtime_version`` + ``extraction_filter``, one of
   each), the producer image as the run image, and the ``preparation`` record.

Silent negatives: any step without a verdict makes the result ERROR (the common verdict rule), and
a report whose every step is undetermined, that aborted, or that is for another runtime or filter
gives no result at all.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts import explore_result
from scripts import python_tarfile_producer as producer
from scripts import run_python_tarfile_target as rpt
from scripts.run_target import ExploreOptions, ExploreOutcome, PreparedTargetImage

from inodefence.generator import minimal_seed_corpus
from inodefence.target_result import Preparation, TargetAxes, TargetResult
from inodefence.target_result_summary import write_cell_summaries

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "scripts" / "local_python_tarfile_explore.sh"
MIN_BUDGET = len(minimal_seed_corpus())

Runner = Callable[..., subprocess.CompletedProcess[Any]]


def explore_filter(options: ExploreOptions) -> str:
    """The ONE extraction filter of this exploration, from the declared target option."""
    declared = rpt.EXTRACTION_FILTER_OPTION
    value = options.target_options.get(declared.name)
    if not value:
        raise ValueError(
            f"python-tarfile exploration needs --{declared.name} "
            f"(one of {', '.join(rpt.EXPLORE_FILTERS)})"
        )
    if declared.choices is not None and value not in declared.choices:
        raise ValueError(f"--{declared.name} must be one of {declared.choices}, got {value!r}")
    if value not in rpt.EXPLORE_FILTERS:
        raise ValueError(f"--{declared.name} {value} is not explored: {rpt.EXPLORE_HELD_REASON}")
    return value


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
    """Common conversion, then the python-specific axes, run image and preparation record."""
    if "aborted" in report:
        raise ValueError(f"exploration aborted: {report['aborted'].get('reason')}")
    if report.get("all_undetermined"):
        raise ValueError("every step was undetermined (no verdict); refusing to report a result")
    if (report.get("runtime_version"), report.get("extraction_filter")) != (
        prepared.version,
        extraction_filter,
    ):
        raise ValueError("loop report is for a different runtime or filter")
    common, tar_files = explore_result.build_campaign_result(
        report, prepared, seed=seed, budget=budget
    )
    result = dataclasses.replace(
        common,
        axes=TargetAxes(runtime_version=prepared.version, extraction_filter=extraction_filter),
        provenance=dataclasses.replace(
            common.provenance, image_ref=made.image_ref, image_id=made.image_id
        ),
        preparation=_preparation(prepared, made),
    )
    return result, tar_files


def explore(
    prepared: PreparedTargetImage,
    options: ExploreOptions,
    *,
    runner: Runner | None = None,
    ensure: Callable[..., producer.ProducerImage] | None = None,
) -> ExploreOutcome:
    """``TargetAdapter.explore`` for python-tarfile (one runtime image, one filter)."""
    extraction_filter = explore_filter(options)
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
    result_path = explore_result.write_result(path.parent / f"{run_id}-result", result, tar_files)
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

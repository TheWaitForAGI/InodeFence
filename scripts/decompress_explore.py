"""decompress exploration: latest (or any) version prepared, then the existing mutation loop.

    python -m scripts.decompress_explore --version @xhmikosr/decompress@latest \
        --budget 20 --seed 123 --out ~/inodefence-explore/decompress-run

Flow, host side (the shape of the node-tar exploration driver):

1. ``run_decompress_target.ensure_image``: resolve ``<package>@latest`` per package, reuse or
   prepare the image (committed recipe, else the registry path of #416), and refuse it unless the
   exploration worker passes its offline identify+frame check. That check also runs on images that
   already exist: an image built before the worker had ``frame`` would bind and then fail every
   step, which would otherwise read as a clean negative.
2. ``scripts/local_decompress_selfdiscover.sh`` with ``EXPLORE_IMAGE``: the existing controller mode
   ``decompress-effect-campaign`` (generic mutator -> decompress ``frame`` worker in the
   controller's disposable sandbox with its unchanged isolation -> generic C0/C1/C2 oracle ->
   boundary-attempt feedback). The controller is not modified.
3. Conversion into the common format: ``result.json`` (``mode=campaign``; every step is a case;
   only violating steps keep their input TAR, re-hashed) and ``exploration.json`` (label
   ``exploratory demo run``, ``qualification: false``, requested and resolved spec, policies,
   and the judged/unjudged tally).

Unjudged steps: a step whose worker did not finish (``failed`` / ``timed_out``) has no reliable
post-state, so its contracts are recorded as not observed. The share of such steps is reported.
If it exceeds ``--max-unjudged-ratio``, or no step produced a frame at all, those steps become run
errors and the result is ``ERROR``, never a ``PASS``. The original ``decompress`` and the fork
``@xhmikosr/decompress`` are different targets; the default mutation vocabulary is unchanged and
its policy name is recorded.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts import run_decompress_target as dt
from scripts.run_target import (
    ExploreOptions,
    ExploreOutcome,
    PreparedTargetImage,
    RunCell,
)

from inodefence.target_result import (
    RUN_ERROR,
    Preparation,
    Provenance,
    TargetAxes,
    TargetResult,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "local_decompress_selfdiscover.sh"
RESULT_NAME = "result.json"
EXPLORATION_NAME = "exploration.json"
JUDGED = ("success", "rejected")
DEFAULT_MAX_UNJUDGED_RATIO = 0.1


@dataclass(frozen=True, slots=True)
class Tally:
    steps: int
    unjudged: int
    frame_errors: int

    @property
    def unjudged_ratio(self) -> float:
        return self.unjudged / self.steps if self.steps else 1.0


def tally(report: dict[str, Any]) -> Tally:
    steps = report.get("steps") or []
    unjudged = sum(1 for s in steps if not s.get("judged", s.get("termination") in JUDGED))
    frame_errors = sum(1 for s in steps if s.get("frame_error"))
    return Tally(len(steps), unjudged, frame_errors)


def gate(counts: Tally, max_unjudged_ratio: float) -> str | None:
    """Why the campaign cannot be read as PASS/FAIL, or ``None``."""
    if counts.steps == 0:
        return "no step ran"
    if counts.frame_errors == counts.steps:
        return f"no step produced a worker frame ({counts.frame_errors}/{counts.steps})"
    if counts.unjudged_ratio > max_unjudged_ratio:
        return (
            f"{counts.unjudged}/{counts.steps} steps unjudged "
            f"(ratio {counts.unjudged_ratio:.3f} > {max_unjudged_ratio})"
        )
    return None


def build_campaign_result(
    report: dict[str, Any],
    *,
    spec: str,
    image_ref: str,
    image_id: str,
    preparation: Preparation | None,
    max_unjudged_ratio: float,
    seed: int,
    budget: int,
    engine: Any = None,
) -> tuple[TargetResult, dict[str, bytes], dict[str, Any]]:
    """Report -> (common result, saved input TARs by relative path, exploration summary).

    The decompress loop report (``steps`` / ``violation_inputs`` keyed by ``index``) is reshaped
    into the target-agnostic loop shape (``case_records`` / ``violation_inputs`` keyed by
    ``run_index``) and converted by the shared ``scripts.explore_result.build_campaign_result``.
    Decompress-specific: unjudged steps carry no contract values (run errors when the gate trips),
    and the image ``preparation`` is attached to the common record.
    """
    from scripts import explore_result

    counts = tally(report)
    stop = gate(counts, max_unjudged_ratio)
    records = []
    for step in report.get("steps") or []:
        oracle = step.get("oracle") or {}
        judged = bool(step.get("judged", step.get("termination") in JUDGED))
        outcome = str(step.get("termination"))
        if not judged and stop is not None:
            outcome = RUN_ERROR
        records.append(
            {
                "run_index": step["index"],
                "outcome": outcome,
                "c0": oracle.get("C0") if judged else None,
                "c1": oracle.get("C1") if judged else None,
                "c2": oracle.get("C2") if judged else None,
            }
        )
    inputs = [
        {"run_index": item["index"], "tar_b64": item["tar_b64"], "tar_sha256": item["tar_sha256"]}
        for item in report.get("violation_inputs") or []
    ]
    prepared = PreparedTargetImage(
        target="decompress",
        requested=spec,
        version=spec,
        image_ref=image_ref,
        image_id=image_id,
        exploratory=preparation is not None,
    )
    shared, tars = explore_result.build_campaign_result(
        {"case_records": records, "violation_inputs": inputs}, prepared, seed=seed, budget=budget
    )
    prov = engine if engine is not None else shared.provenance
    result = dataclasses.replace(
        shared,
        provenance=Provenance(prov.engine_sha, prov.engine_dirty, image_ref, image_id),
        preparation=preparation,
    )
    repro = result.repro_inputs
    config = report.get("config") or {}
    summary = {
        "label": "exploratory demo run",
        "mode": "exploration",
        "qualification": False,
        "spec": spec,
        "image_ref": image_ref,
        "image_id": image_id,
        "mutation_policy": config.get("mutation_policy"),
        "search_policy": config.get("search_policy"),
        "random_seed": config.get("random_seed"),
        "execution_budget": config.get("execution_budget"),
        "steps": counts.steps,
        "unjudged_steps": counts.unjudged,
        "unjudged_ratio": round(counts.unjudged_ratio, 6),
        "frame_error_steps": counts.frame_errors,
        "max_unjudged_ratio": max_unjudged_ratio,
        "not_readable_as_pass": stop,
        "violation_inputs": len(repro),
        "controller_report_label": report.get("label"),
    }
    return result, tars, summary


def write_outputs(
    out_dir: Path, result: TargetResult, tars: dict[str, bytes], summary: dict[str, Any]
) -> Path:
    from scripts import explore_result

    if (out_dir / RESULT_NAME).exists():
        raise FileExistsError(f"refusing to overwrite {out_dir / RESULT_NAME}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / EXPLORATION_NAME).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # The shared writer saves the violating inputs and writes result.json last.
    return explore_result.write_result(out_dir, result, tars)


def controller_report_path(evidence_dir: Path, run_id: str) -> Path:
    return evidence_dir / f"inodefence-decompress-selfdiscover-{run_id}.json"


def run_controller(
    image_id: str,
    evidence_dir: Path,
    run_id: str,
    *,
    seed: int,
    budget: int,
    mutation_policy: str | None,
    search_policy: str | None,
    runner: Any = subprocess.run,
) -> Path:
    env = {
        **os.environ,
        "EXPLORE_IMAGE": image_id,
        "RUN_ID": run_id,
        "INODEFENCE_EVIDENCE_DIR": str(evidence_dir),
        "DEMO_SEED": str(seed),
        "DEMO_BUDGET": str(budget),
    }
    if mutation_policy:
        env["DEMO_MUTATION_POLICY"] = mutation_policy
    if search_policy:
        env["DEMO_POLICY"] = search_policy
    done = runner(["bash", str(SCRIPT)], env=env, check=False)
    path = controller_report_path(evidence_dir, run_id)
    if done.returncode != 0 or not path.is_file():
        raise RuntimeError(f"controller run failed (exit {done.returncode}); report {path}")
    return path


def explore(prepared: PreparedTargetImage, options: ExploreOptions) -> ExploreOutcome:
    """``TargetAdapter.explore`` for decompress: worker check, controller campaign, common result.

    The worker check runs here on every image (also one the common layer reused unchecked), so an
    image whose worker cannot run ``frame`` is refused before any budget is spent.
    """
    package, version = dt.parse_spec(prepared.version)
    check = dt.registry.worker_check(
        dt.registry.subprocess.run, prepared.image_ref, package, version
    )
    if not check["ok"]:
        raise ValueError(
            f"worker incompatible (decompress worker) in {prepared.image_ref}: "
            f"{check['reason']}; rebuild it"
        )
    ratio = getattr(options, "max_unjudged_ratio", DEFAULT_MAX_UNJUDGED_RATIO)
    run_id = f"{dt._slug(package)}-{version}-{options.seed}-{options.budget}"
    run_id += options.image_tag_suffix
    options.out.mkdir(parents=True, exist_ok=True)
    report_path = run_controller(
        prepared.image_id,
        options.out / "controller",
        run_id,
        seed=options.seed,
        budget=options.budget,
        mutation_policy=getattr(options, "mutation_policy", None),
        search_policy=getattr(options, "search_policy", None),
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if "aborted" in report:
        raise RuntimeError(f"controller aborted: {report['aborted']}")
    out_dir = options.out / f"{run_id}-result"
    axes = TargetAxes(target_version=prepared.version)
    cell = RunCell(out_dir.name, axes, prepared.image_ref, prepared.exploratory)
    preparation = dt.ADAPTER.describe(cell, out_dir) if dt.ADAPTER.describe else None
    result, tars, summary = build_campaign_result(
        report,
        spec=prepared.version,
        image_ref=prepared.image_ref,
        image_id=prepared.image_id,
        preparation=preparation,
        max_unjudged_ratio=ratio,
        seed=options.seed,
        budget=options.budget,
    )
    summary.update(
        requested=prepared.requested,
        worker_check=check["reason"],
        controller_report=str(report_path),
    )
    path = write_outputs(out_dir, result, tars, summary)
    try:  # the result is written; a summary failure must not lose it
        from inodefence.target_result_summary import write_cell_summaries

        write_cell_summaries([path])
    except Exception as error:  # noqa: BLE001
        print(f"TARGET-EXPLORE SUMMARY: summary.md not written ({error})", file=sys.stderr)
    stop = summary["not_readable_as_pass"]
    if stop:
        print(f"TARGET-EXPLORE NOT-PASS {prepared.version}: {stop}", file=sys.stderr)
    return ExploreOutcome(
        result_path=path,
        verdict=result.verdict.value,
        runs=result.executed,
        violations=len(result.violating_cases),
    )


def main(argv: list[str] | None = None) -> int:
    """Stand-alone use; ``make target-explore`` calls ``explore`` through the adapter."""
    parser = argparse.ArgumentParser(description="decompress exploration (exploratory demo run)")
    parser.add_argument("--version", required=True, help="<package>@<X.Y.Z|latest>")
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--image-tag-suffix", default="")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; no network/docker")
    args = parser.parse_args(argv)
    if args.budget < 1:
        parser.error("--budget must be positive")
    if args.dry_run:
        plan = {
            "version": args.version,
            "steps": ["ensure_image (+ offline worker check)", "controller campaign", "convert"],
            "budget": args.budget,
            "seed": args.seed,
            "max_unjudged_ratio": DEFAULT_MAX_UNJUDGED_RATIO,
            "note": "dry-run: nothing resolved, prepared, run or written",
        }
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    try:
        ready = dt.ensure_image(args.version, image_tag_suffix=args.image_tag_suffix)
        prepared = PreparedTargetImage(
            target="decompress",
            requested=ready.requested,
            version=ready.spec,
            image_ref=ready.image_ref,
            image_id=ready.image_id,
            exploratory=ready.exploratory,
        )
        outcome = explore(
            prepared, ExploreOptions(args.budget, args.seed, args.out, args.image_tag_suffix)
        )
    except ValueError as error:
        print(f"TARGET-EXPLORE SETUP: {error}", file=sys.stderr)
        return 3
    print(
        f"TARGET-EXPLORE {outcome.verdict} {prepared.version} runs={outcome.runs} "
        f"violations={outcome.violations} (exploratory demo run) -> {outcome.result_path}"
    )
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[outcome.verdict]


if __name__ == "__main__":
    raise SystemExit(main())

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
import base64
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from scripts import run_decompress_target as dt
from scripts.run_target import RunCell, engine_provenance

from inodefence.target_result import (
    RUN_ERROR,
    CaseVerdict,
    Preparation,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
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
    unjudged = sum(1 for s in steps if s.get("termination") not in JUDGED)
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
    engine: Any = None,
) -> tuple[TargetResult, dict[str, bytes], dict[str, Any]]:
    """Report -> (common result, saved input TARs by relative path, exploration summary)."""
    counts = tally(report)
    stop = gate(counts, max_unjudged_ratio)
    cases = []
    for step in report.get("steps") or []:
        oracle = step.get("oracle") or {}
        judged = step.get("termination") in JUDGED
        outcome = str(step.get("termination"))
        if not judged and stop is not None:
            outcome = RUN_ERROR
        cases.append(
            CaseVerdict(
                f"step-{step['index']}",
                outcome,
                oracle.get("C0") if judged else None,
                oracle.get("C1") if judged else None,
                oracle.get("C2") if judged else None,
            )
        )
    tars: dict[str, bytes] = {}
    repro = []
    for item in report.get("violation_inputs") or []:
        archive = base64.b64decode(item["tar_b64"])
        if sha256(archive).hexdigest() != item["tar_sha256"]:
            raise ValueError(f"violation input for step {item['index']} fails its SHA-256")
        path = f"inputs/step-{item['index']}.tar"
        tars[path] = archive
        repro.append(repro_input(f"step-{item['index']}", path, archive))
    prov = engine if engine is not None else engine_provenance(image_ref)
    result = TargetResult(
        target="decompress",
        axes=TargetAxes(target_version=spec),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cases=tuple(cases),
        repro_inputs=tuple(repro),
        provenance=Provenance(prov.engine_sha, prov.engine_dirty, image_ref, image_id),
        preparation=preparation,
    )
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
    result_path = out_dir / RESULT_NAME
    if result_path.exists():
        raise FileExistsError(f"refusing to overwrite {result_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for relative, archive in tars.items():
        target = out_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive)
    (out_dir / EXPLORATION_NAME).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result_path.write_text(result.dumps(), encoding="utf-8")
    return result_path


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="decompress exploration (exploratory demo run)")
    parser.add_argument("--version", required=True, help="<package>@<X.Y.Z|latest>")
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--image-tag-suffix", default="")
    parser.add_argument("--max-unjudged-ratio", type=float, default=DEFAULT_MAX_UNJUDGED_RATIO)
    parser.add_argument("--mutation-policy")
    parser.add_argument("--policy", help="search policy (EffectSearchPolicy value)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; no network/docker")
    args = parser.parse_args(argv)
    if not 0.0 <= args.max_unjudged_ratio <= 1.0:
        parser.error("--max-unjudged-ratio must be within 0..1")
    if args.budget < 1:
        parser.error("--budget must be positive")
    if args.dry_run:
        plan = {
            "version": args.version,
            "steps": ["ensure_image (+ offline worker check)", "controller campaign", "convert"],
            "budget": args.budget,
            "seed": args.seed,
            "max_unjudged_ratio": args.max_unjudged_ratio,
            "note": "dry-run: nothing resolved, prepared, run or written",
        }
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    try:
        prepared = dt.ensure_image(args.version, image_tag_suffix=args.image_tag_suffix)
    except ValueError as error:
        print(f"TARGET-EXPLORE SETUP: {error}", file=sys.stderr)
        return 3
    print(f"TARGET-EXPLORE ready {prepared.spec} {prepared.image_ref} ({prepared.worker_check})")
    out_dir = args.out / dt.dirname(*dt.parse_spec(prepared.spec))
    token = f"{prepared.image_id}{args.seed}{args.budget}".encode()
    run_id = f"explore-{sha256(token).hexdigest()[:12]}"
    report_path = run_controller(
        prepared.image_id,
        args.out / "controller",
        run_id,
        seed=args.seed,
        budget=args.budget,
        mutation_policy=args.mutation_policy,
        search_policy=args.policy,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if "aborted" in report:
        print(f"TARGET-EXPLORE ERROR: controller aborted: {report['aborted']}", file=sys.stderr)
        return 2
    axes = TargetAxes(target_version=prepared.spec)
    cell = RunCell(out_dir.name, axes, prepared.image_ref, prepared.exploratory)
    preparation = dt.ADAPTER.describe(cell, out_dir) if dt.ADAPTER.describe else None
    result, tars, summary = build_campaign_result(
        report,
        spec=prepared.spec,
        image_ref=prepared.image_ref,
        image_id=prepared.image_id,
        preparation=preparation,
        max_unjudged_ratio=args.max_unjudged_ratio,
    )
    summary["requested"] = prepared.requested
    summary["worker_check"] = prepared.worker_check
    summary["controller_report"] = str(report_path)
    path = write_outputs(out_dir, result, tars, summary)
    stop = summary["not_readable_as_pass"]
    print(
        f"TARGET-EXPLORE {result.verdict.value} {prepared.spec} steps={summary['steps']} "
        f"violating={len(result.violating_cases)} unjudged={summary['unjudged_steps']}"
        + (f" NOT-PASS: {stop}" if stop else "")
        + f" (exploratory demo run) -> {path}"
    )
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[result.verdict.value]


if __name__ == "__main__":
    raise SystemExit(main())

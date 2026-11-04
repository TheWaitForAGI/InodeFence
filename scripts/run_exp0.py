"""EXP-0 launcher: run the preregistered R/D/S-u pilot through the controller path.

Input is ONE committed preregistration file (``experiments/preregistration/*.md``
with the fenced ``preregistration`` block, e.g. EXP-0 v2.1). Nothing runs unless the
gate passes for every planned cell: engine HEAD SHA (clean checkout), image digest,
seeds, budget, arm policy IDs, ``observer_integrity_policy``, ``sentinel_*`` and the
five rule keys are all compared (``inodefence.evaluation.rds_preregistration``).

Cells = preregistered seeds × R/D/S-u (+ S-a with ``--include-s-a`` when the file
declares it) × preregistered budget, each run as a ``local_node_tar_smoke.sh
demo-historical`` campaign with a unique ``RUN_ID`` — the same path and summaries
as ``scripts/run_g1_smoke.py``. Outputs are labelled ``registered run`` with the
preregistration file name, its SHA-256 and the engine SHA, and go to::

    <output>/registration.json                  what this directory was launched under
    <output>/matrix.json                        last invocation's cell results
    <output>/inodefence-effect-demo-historical-<run_id>.json / .steps.jsonl / <run_id>.log
    <output>/attempts/<run_id>.attempt<N>.*     files of a rerun cell's earlier attempt
    <output>/summaries/<run_id>.summary.json + index.json   analyze_exp0 input
    <manifest>                                  raw SHA-256 manifest (make_raw_manifest)

Idempotent: a rerun skips cells whose report is complete and conformant (budget
reached, no abort, planned config, preregistered image id and sentinel set) and
re-runs only the rest, moving their earlier files to ``attempts/``. ``--dry-run``
prints the gate verdict and every cell's command/env/paths without Docker;
``--summarize-only`` rebuilds the summaries and manifest from existing files.

Post-run conformance (per cell, third bucket ``config_nonconformant`` when it
fails): the report's ``image_id`` must equal the preregistered digest and, when the
file declares a sentinel generator, the report's ``sentinel_set`` must match it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from scripts.run_g1_smoke import (
    DEFAULT_EXECUTION_MODE,
    EXECUTION_MODES,
    SENTINEL_GENERATOR_ID,
    cell_paths,
    summarize_output,
)
from scripts.run_parallel_native import (
    SCRIPT,
    Arm,
    Cell,
    CellResult,
    _run_cell,
    _warmup,
    build_cells,
    cell_env,
)

from inodefence.evaluation.rds import VOCABULARY_MUTATION_POLICY, RdsArm, RdsCellConfig
from inodefence.evaluation.rds_preregistration import (
    CellRequest,
    Preregistration,
    PreregistrationFormatError,
    load_preregistration,
    preregistration_mismatches,
)
from inodefence.evaluation.rds_report import ReportFormatError, load_cell_files
from inodefence.provenance import capture_source

PLAN = "exp0"
REGISTERED_LABEL = "registered run"
DEFAULT_VERSION = "7.5.2"
DEFAULT_JOBS = 2
DEFAULT_MANIFEST_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_raw_manifest.py"
REGISTRATION_FILE = "registration.json"
# Env names the smoke script must consume for the declared options to reach the
# controller; probed in the script text so a declared-but-unwired option never
# silently runs with the default.
SENTINEL_ENV = ("DEMO_SENTINEL_SEED", "DEMO_SENTINEL_COUNT")
OBSERVER_ENV = "DEMO_OBSERVER_INTEGRITY_POLICY"


def _script_has(variable: str) -> bool:
    """Whether the smoke script references an env variable (wiring probe)."""
    return SCRIPT.is_file() and variable in SCRIPT.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class Exp0Plan:
    """The preregistered cells; every parameter comes from the file, none from flags."""

    preregistration: Preregistration
    preregistration_path: Path
    preregistration_sha256: str
    version: str
    include_s_a: bool
    execution_mode: str = DEFAULT_EXECUTION_MODE

    @property
    def plan(self) -> str:
        return PLAN

    def arm_list(self) -> tuple[RdsArm, ...]:
        arms = [RdsArm.R, RdsArm.D, RdsArm.S_U]
        if self.include_s_a:
            arms.append(RdsArm.S_A)
        return tuple(arms)

    def arms(self) -> tuple[Arm, ...]:
        prereg = self.preregistration
        mutation = VOCABULARY_MUTATION_POLICY[prereg.vocabulary_mode].value
        return tuple(
            Arm(arm.value, prereg.arm_policies[arm].value, mutation) for arm in self.arm_list()
        )

    def cells(self) -> list[Cell]:
        prereg = self.preregistration
        return build_cells(
            "demo-historical", [self.version], self.arms(), prereg.seeds, prereg.budget
        )

    def cell_config(self, cell: Cell) -> RdsCellConfig:
        prereg = self.preregistration
        return RdsCellConfig(
            RdsArm(cell.arm.label),
            cell.seed,
            cell.budget,
            prereg.vocabulary_mode,
            prereg.r_variant,
        )

    def sentinel_request(self) -> dict[str, object] | None:
        prereg = self.preregistration
        if prereg.sentinel_generator_seed is None:
            return None
        return {
            "generator_id": prereg.sentinel_generator_id or SENTINEL_GENERATOR_ID,
            "generator_seed": prereg.sentinel_generator_seed,
            "count": prereg.sentinel_count,
        }

    def labels(self, engine_sha: str | None) -> list[str]:
        return [
            REGISTERED_LABEL,
            f"preregistration={self.preregistration_path.name}",
            f"preregistration_sha256={self.preregistration_sha256}",
            f"engine_sha={engine_sha}",
        ]

    def gate_text(self) -> str:
        return (
            f"preregistration gate on: {self.preregistration_path.name} "
            f"(sha256 {self.preregistration_sha256[:12]}…)"
        )


def gate_mismatches(
    plan: Exp0Plan,
    *,
    engine_sha: str | None,
    engine_dirty: bool | None,
    image_digest: str | None,
    observer_integrity_policy: str | None,
) -> tuple[str, ...]:
    """Union of every cell's mismatches (cells differ only in arm/seed)."""
    problems: list[str] = []
    for cell in plan.cells():
        request = CellRequest(
            RdsArm(cell.arm.label),
            cell.seed,
            cell.budget,
            engine_sha,
            engine_dirty,
            image_digest,
            plan.sentinel_request(),
            observer_integrity_policy,
        )
        for item in preregistration_mismatches(plan.preregistration, request):
            if item not in problems:
                problems.append(item)
    return tuple(problems)


def post_check(plan: Exp0Plan) -> Any:
    """Report-level conformance to the registration (image id, sentinel set)."""
    prereg = plan.preregistration

    def check(report: Mapping[str, Any] | None, cell: Cell) -> str | None:
        if report is None or "aborted" in report:
            return None
        image = report.get("image_id")
        if image != prereg.image_digest:
            return f"report image_id {image!r} != preregistered {prereg.image_digest}"
        if prereg.sentinel_generator_seed is not None:
            recorded = report.get("sentinel_set")
            if not isinstance(recorded, Mapping):
                return "preregistered sentinel set but the report records no sentinel_set"
            expected = plan.sentinel_request() or {}
            for key in ("generator_id", "generator_seed", "count"):
                if expected.get(key) is not None and recorded.get(key) != expected[key]:
                    return f"report sentinel_set.{key} {recorded.get(key)!r} != {expected[key]!r}"
        return None

    return check


def exp0_status(plan: str, cells: Any, vocabulary_equal: bool) -> dict[str, Any]:
    complete = sum(1 for cell in cells if cell["complete"])
    invalid = sum(1 for cell in cells if cell.get("invalid"))
    aborts = sum(1 for cell in cells if not cell["complete"] and not cell.get("invalid"))
    return {
        "plan": plan,
        "rule": "all preregistered cells complete and conformant; vocabulary equal across arms",
        "cells": len(cells),
        "complete": complete,
        "aborts": aborts,
        "invalid": invalid,
        "vocabulary_equal_across_arms": vocabulary_equal,
        "pass": bool(cells) and complete == len(cells) and vocabulary_equal,
    }


def cell_is_complete(plan: Exp0Plan, cell: Cell, output: Path) -> bool:
    """A cell counts as done only when its report is complete AND conformant."""
    paths = cell_paths(cell, output)
    if not paths["report"].is_file():
        return False
    try:
        loaded = load_cell_files(paths["report"], paths["steps_jsonl"])
    except (ReportFormatError, ValueError, json.JSONDecodeError):
        return False
    if loaded.report is None or loaded.aborted_at_step is not None:
        return False
    if len(loaded.records) != cell.budget or loaded.steps_from != "report":
        return False
    config = plan.cell_config(cell)
    recorded = loaded.report.get("config")
    if not isinstance(recorded, Mapping) or (
        recorded.get("random_seed") != config.random_seed
        or recorded.get("execution_budget") != config.execution_budget
        or recorded.get("search_policy") != config.search_policy.value
        or recorded.get("mutation_policy") != config.mutation_policy.value
    ):
        return False
    return post_check(plan)(loaded.report, cell) is None


def archive_attempt(cell: Cell, output: Path) -> int | None:
    """Move an incomplete cell's files to ``attempts/``; returns the attempt number."""
    paths = cell_paths(cell, output)
    existing = [key for key in ("report", "steps_jsonl", "log") if paths[key].exists()]
    if not existing:
        return None
    attempts = output / "attempts"
    attempts.mkdir(exist_ok=True)
    number = 1
    while any(attempts.glob(f"{cell.run_id}.attempt{number}.*")):
        number += 1
    for key in existing:
        suffix = {"report": "json", "steps_jsonl": "steps.jsonl", "log": "log"}[key]
        paths[key].rename(attempts / f"{cell.run_id}.attempt{number}.{suffix}")
    return number


def exp0_cell_env(
    plan: Exp0Plan, cell: Cell, output: Path, base_env: dict[str, str]
) -> dict[str, str]:
    env = cell_env(cell, output, base_env)
    prereg = plan.preregistration
    if prereg.sentinel_generator_seed is not None:
        env["DEMO_SENTINEL_SEED"] = str(prereg.sentinel_generator_seed)
        env["DEMO_SENTINEL_COUNT"] = str(prereg.sentinel_count)
    if prereg.observer_integrity_policy is not None:
        env[OBSERVER_ENV] = prereg.observer_integrity_policy
    return env


def wiring_problems(plan: Exp0Plan) -> tuple[str, ...]:
    prereg = plan.preregistration
    problems: list[str] = []
    if prereg.sentinel_generator_seed is not None and not all(_script_has(v) for v in SENTINEL_ENV):
        problems.append(
            f"preregistration declares a sentinel set but {SCRIPT.name} does not consume "
            f"{'/'.join(SENTINEL_ENV)} (lane 7 wiring pending)"
        )
    if prereg.observer_integrity_policy is not None and not _script_has(OBSERVER_ENV):
        problems.append(
            f"preregistration declares observer_integrity_policy but {SCRIPT.name} does not "
            f"consume {OBSERVER_ENV} (controller wiring pending; #207 also restricts the "
            "option to effect-demo, not demo-historical)"
        )
    return tuple(problems)


def write_registration(
    plan: Exp0Plan, output: Path, *, engine_sha: str | None, image_digest: str | None
) -> dict[str, Any]:
    """Create or re-validate the directory's registration record."""
    path = output / REGISTRATION_FILE
    record = {
        "label": plan.labels(engine_sha),
        "preregistration_file": plan.preregistration_path.name,
        "preregistration_sha256": plan.preregistration_sha256,
        "engine_sha": engine_sha,
        "image_digest": image_digest,
        "version": plan.version,
        "include_s_a": plan.include_s_a,
        "execution_mode": plan.execution_mode,
        "cells": [cell.run_id for cell in plan.cells()],
    }
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        for key in ("preregistration_sha256", "engine_sha", "image_digest"):
            if existing.get(key) != record[key]:
                raise SystemExit(
                    f"{output} was registered under a different {key} "
                    f"({existing.get(key)!r} != {record[key]!r}); use a new directory"
                )
        record["created_at"] = existing.get("created_at")
        record["invocations"] = int(existing.get("invocations", 0)) + 1
    else:
        record["created_at"] = datetime.now(UTC).isoformat()
        record["invocations"] = 1
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def write_raw_manifest(
    output: Path, *, script: Path, python: str, host: str, date: str, out: Path | None
) -> dict[str, Any]:
    """Run make_raw_manifest over the output tree (completion condition 8)."""
    if not script.is_file():
        return {"generated": False, "reason": f"manifest script missing: {script}", "path": None}
    manifest = (
        out
        if out is not None
        else Path("experiments/summaries") / f"raw-manifest-{host}-{date}.sha256"
    )
    command = [
        python,
        str(script),
        "--root",
        str(output),
        "--host",
        host,
        "--date",
        date,
        "--out",
        str(manifest),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "generated": completed.returncode == 0 and manifest.is_file(),
        "path": str(manifest),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip()[-500:],
        "stderr": completed.stderr.strip()[-500:],
    }


def _print_dry_run(
    plan: Exp0Plan, output: Path, base_env: dict[str, str], pending: list[Cell]
) -> None:
    cells = plan.cells()
    prereg = plan.preregistration
    print(
        f"plan={PLAN} cells={len(cells)} pending={len(pending)} seeds={list(prereg.seeds)} "
        f"budget={prereg.budget} arms={[a.label for a in plan.arms()]} "
        f"vocabulary={prereg.vocabulary_mode.value} execution_mode={plan.execution_mode}"
    )
    print(f"warmup: BUILD_ONLY=1 bash {SCRIPT} demo-historical")
    pending_ids = {cell.run_id for cell in pending}
    for cell in cells:
        env = exp0_cell_env(plan, cell, output, base_env)
        shown = {
            key: env[key]
            for key in (
                "RUN_ID",
                "SKIP_BUILD",
                "TAR_VERSION",
                "DEMO_SEED",
                "DEMO_BUDGET",
                "DEMO_POLICY",
                "DEMO_MUTATION_POLICY",
                "DEMO_SENTINEL_SEED",
                "DEMO_SENTINEL_COUNT",
                OBSERVER_ENV,
                "INODEFENCE_EVIDENCE_DIR",
            )
            if key in env
        }
        state = "pending" if cell.run_id in pending_ids else "complete (skip)"
        paths = cell_paths(cell, output)
        print(f"  {cell.run_id} [{state}]: bash {SCRIPT} demo-historical")
        print(f"    env: {json.dumps(shown, sort_keys=True)}")
        print(f"    report={paths['report']} summary={paths['summary']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-digest", help="sha256:<64 hex> of the image the cells will run")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--include-s-a", action="store_true", help="also run the declared S-a ablation"
    )
    parser.add_argument("--observer-integrity-policy", choices=("stop", "invalid-continue"))
    parser.add_argument("--execution-mode", choices=EXECUTION_MODES, default=DEFAULT_EXECUTION_MODE)
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--python", default=None)
    parser.add_argument("--context", default=None)
    parser.add_argument(
        "--manifest-host", default=None, help="host label for the raw manifest name"
    )
    parser.add_argument("--manifest-out", type=Path, default=None)
    parser.add_argument("--manifest-script", type=Path, default=DEFAULT_MANIFEST_SCRIPT)
    parser.add_argument("--no-manifest", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be >= 1")

    try:
        prereg = load_preregistration(args.preregistration)
    except (PreregistrationFormatError, OSError) as error:
        print(f"preregistration unusable: {error}", file=sys.stderr)
        return 2
    if args.include_s_a and RdsArm.S_A not in prereg.arm_policies:
        parser.error("--include-s-a requested but the preregistration declares no arm.S-a")
    file_sha = sha256(args.preregistration.read_bytes()).hexdigest()
    plan = Exp0Plan(
        prereg, args.preregistration, file_sha, args.version, args.include_s_a, args.execution_mode
    )
    source = capture_source()
    mismatches = gate_mismatches(
        plan,
        engine_sha=source.revision,
        engine_dirty=source.dirty,
        image_digest=args.image_digest,
        observer_integrity_policy=args.observer_integrity_policy,
    )
    if prereg.unknown_keys:
        print(
            "warning: unknown preregistration keys (not compared): "
            + ", ".join(prereg.unknown_keys),
            file=sys.stderr,
        )
    output: Path = args.output
    base_env = dict(os.environ)
    if args.python:
        base_env["PYTHON"] = args.python
    if args.context:
        base_env["INODEFENCE_DOCKER_CONTEXT"] = args.context

    if args.dry_run:
        if mismatches:
            print("gate: FAIL (a live run would be refused)")
            for item in mismatches:
                print(f"  - {item}")
        else:
            print(f"gate: PASS ({plan.gate_text()})")
        for item in wiring_problems(plan):
            print(f"wiring: {item}")
        pending = [cell for cell in plan.cells() if not cell_is_complete(plan, cell, output)]
        _print_dry_run(plan, output, base_env, pending)
        return 0 if not mismatches else 2
    if mismatches:
        print("refusing to run (preregistration gate):", file=sys.stderr)
        for item in mismatches:
            print(f"  - {item}", file=sys.stderr)
        return 2

    def finish(results: list[CellResult] | None) -> int:
        document = summarize_output(
            plan,
            output,
            labels=plan.labels(source.revision),
            gate=plan.gate_text(),
            verdict_fn=exp0_status,
            post_check=post_check(plan),
            extra={
                "preregistration": {
                    "file": plan.preregistration_path.name,
                    "sha256": plan.preregistration_sha256,
                    "engine_sha": source.revision,
                    "image_digest": args.image_digest,
                }
            },
        )
        status = document["g1_verdict"]
        manifest: dict[str, Any] = {"generated": False, "reason": "--no-manifest", "path": None}
        if not args.no_manifest:
            host = args.manifest_host or os.uname().nodename.split(".")[0]
            manifest = write_raw_manifest(
                output,
                script=args.manifest_script,
                python=args.python or sys.executable,
                host=host,
                date=datetime.now(UTC).strftime("%Y%m%d"),
                out=args.manifest_out,
            )
        registration = json.loads((output / REGISTRATION_FILE).read_text(encoding="utf-8"))
        registration["raw_manifest"] = manifest
        registration["last_status"] = status
        (output / REGISTRATION_FILE).write_text(
            json.dumps(registration, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({"status": status, "raw_manifest": manifest}, sort_keys=True))
        if not manifest["generated"] and not args.no_manifest:
            print("raw manifest NOT generated (completion condition 8 unmet)", file=sys.stderr)
        return 0 if status["pass"] and (manifest["generated"] or args.no_manifest) else 1

    output.mkdir(parents=True, exist_ok=True)
    write_registration(plan, output, engine_sha=source.revision, image_digest=args.image_digest)
    if args.summarize_only:
        return finish(None)

    problems = wiring_problems(plan)
    if problems:
        print("refusing to run (controller wiring):", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        return 2
    bash = shutil.which("bash")
    if bash is None:
        raise SystemExit("bash not found: the native launcher runs only on the host terminal")
    pending = [cell for cell in plan.cells() if not cell_is_complete(plan, cell, output)]
    skipped = [cell.run_id for cell in plan.cells() if cell not in pending]
    archived = {cell.run_id: archive_attempt(cell, output) for cell in pending}
    if pending and not args.skip_build:
        code = _warmup("demo-historical", output, base_env, bash)
        if code != 0:
            print(
                f"image warmup failed (exit {code}); see {output / 'warmup.log'}", file=sys.stderr
            )
            return code
    results: list[CellResult] = []
    if pending:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(
                pool.map(
                    lambda cell: _run_cell(
                        cell, output, exp0_cell_env(plan, cell, output, base_env), bash
                    ),
                    pending,
                )
            )
    (output / "matrix.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now(UTC).isoformat(),
                "label": plan.labels(source.revision),
                "plan": PLAN,
                "mode": "demo-historical",
                "execution_mode": plan.execution_mode,
                "host": {
                    "machine": os.uname().machine,
                    "system": os.uname().sysname,
                    "release": os.uname().release,
                },
                "skipped_complete": skipped,
                "archived_attempts": {k: v for k, v in archived.items() if v is not None},
                "cells": [
                    {
                        "run_id": r.cell.run_id,
                        "arm": r.cell.arm.label,
                        "seed": r.cell.seed,
                        "budget": r.cell.budget,
                        "returncode": r.returncode,
                        "wall_seconds": round(r.wall_seconds, 3),
                        "evidence": r.evidence.name,
                        "evidence_exists": r.evidence_exists,
                        "log": r.log.name,
                    }
                    for r in results
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return finish(results)


if __name__ == "__main__":
    raise SystemExit(main())

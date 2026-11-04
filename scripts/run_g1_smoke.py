"""G1 smoke driver: R/D/S-u cells through the existing controller path, summarized.

Plans the G1 gate cells of ``docs/BACKLOG.md`` (phase 3, 구현 수리) and runs each
one as a ``scripts/local_node_tar_smoke.sh demo-historical`` campaign with a
unique ``RUN_ID`` — exactly the path ``scripts/run_parallel_native.py`` uses — then
converts every cell's demo report into the R/D/S-u per-cell summary
(``inodefence.evaluation.rds_report``) under ``<output>/summaries/``.

Plans:

* ``completion``: R, D, S-u × one seed × budget 50 — three cells that must finish.
* ``smoke``: R, D, S-u × the given seeds (default four) × budget 50 — at least ten
  campaigns; the G1 verdict is PASS when at most one cell aborts.

Every cell uses the same vocabulary (one ``VocabularyMode`` → one mutation policy
for all arms), seed set and budget; only the arm's retention policy differs. No
controller code changes: the policy IDs are selected with the existing
``--policy``/``--mutation-policy`` demo arguments (``DEMO_POLICY`` /
``DEMO_MUTATION_POLICY`` env of the smoke script).

This is an UNREGISTERED run: the preregistration gate is off and every output is
labelled ``demo run`` + ``unregistered G1 smoke``; it is never EXP-0 evidence.
``--dry-run`` prints the per-cell command, env, RUN_ID and output paths and exits
without Docker. ``--summarize-only`` rebuilds ``summaries/`` from an existing
output directory. Real runs belong to the runtime lane on a Docker host.

Sentinel set (lane 7 ``inodefence.sentinel_set``): ``--sentinel-seed/--sentinel-count``
are accepted and recorded, but the controller path has no wiring to pass them yet
(see ``SENTINEL_WIRING``); a live run with them is refused until that lands.

Output layout (agreed with the statistics lane; ``analyze_exp0`` reads it):

    <output>/matrix.json                       manifest (plan, label, cells, verdict)
    <output>/inodefence-effect-demo-historical-<run_id>.json / .steps.jsonl / <run_id>.log
    <output>/summaries/<run_id>.summary.json   per-cell summary record
    <output>/summaries/index.json              cell index + abort count + G1 verdict
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from scripts.run_parallel_native import (
    SCRIPT,
    Arm,
    Cell,
    CellResult,
    _prepare_output_dir,
    _run_cell,
    _warmup,
    build_cells,
    cell_env,
)

from inodefence.evaluation.rds import RdsArm, RdsCellConfig, RVariant, VocabularyMode
from inodefence.evaluation.rds_report import (
    ReportFormatError,
    check_report_config,
    environment_record,
    load_cell_files,
    summarize_report_records,
    timing_record,
)

LABELS = ("demo run", "unregistered G1 smoke")
GATE = "none (unregistered G1 smoke; preregistration gate off)"
PLANS = ("completion", "smoke")
DEFAULT_BUDGET = 50
DEFAULT_VERSION = "7.5.2"
DEFAULT_SEEDS = {"completion": (9001,), "smoke": (9001, 9002, 9003, 9004)}
MAIN_ARMS = (RdsArm.R, RdsArm.D, RdsArm.S_U)
SMOKE_MIN_CELLS = 10
SMOKE_MAX_ABORTS = 1
SENTINEL_GENERATOR_ID = "sentinel-names/seed-random-v1"
EXECUTION_MODES = ("per-case-container", "worker-pool")
# The controller demo path runs one disposable target container per case.
DEFAULT_EXECUTION_MODE = "per-case-container"
_ENGINE_LINE = re.compile(r"engine=(\S+)")
# Where a sentinel-set option must be threaded through the controller path before
# this driver can pass one (reported to lane 7; nothing here changes those files):
SENTINEL_WIRING = (
    "scripts/run_effect_demo.py: add_demo_arguments/DEMO_ARGUMENTS/demo_options "
    "(--sentinel-seed/--sentinel-count) and historical_demo_report/native_demo_report "
    "(sentinels= to run_node_tar_effect_case; report.update(sentinel_set=describe()))",
    "scripts/container_host.py: DEMO_FORWARDED_ARGUMENTS forwards the new arguments",
    "scripts/local_node_tar_smoke.sh: DEMO_SENTINEL_SEED/DEMO_SENTINEL_COUNT env -> DEMO_ARGS",
    "scripts/run_parallel_native.py cell_env: export the env for a cell",
)


@dataclass(frozen=True, slots=True)
class G1Plan:
    plan: str
    version: str
    seeds: tuple[int, ...]
    budget: int
    vocabulary_mode: VocabularyMode
    r_variant: RVariant
    sentinel_seed: int | None
    sentinel_count: int | None
    execution_mode: str = DEFAULT_EXECUTION_MODE

    def arms(self) -> tuple[Arm, ...]:
        return tuple(
            Arm(
                arm.value,
                RdsCellConfig(
                    arm, 0, self.budget, self.vocabulary_mode, self.r_variant
                ).search_policy.value,
                RdsCellConfig(
                    arm, 0, self.budget, self.vocabulary_mode, self.r_variant
                ).mutation_policy.value,
            )
            for arm in MAIN_ARMS
        )

    def cells(self) -> list[Cell]:
        return build_cells("demo-historical", [self.version], self.arms(), self.seeds, self.budget)

    def cell_config(self, cell: Cell) -> RdsCellConfig:
        return RdsCellConfig(
            RdsArm(cell.arm.label), cell.seed, cell.budget, self.vocabulary_mode, self.r_variant
        )

    def sentinel_request(self) -> dict[str, object] | None:
        if self.sentinel_seed is None:
            return None
        return {
            "generator_id": SENTINEL_GENERATOR_ID,
            "generator_seed": self.sentinel_seed,
            "count": self.sentinel_count,
            "status": "requested; not wired through the controller path yet",
        }


class CellPlan(Protocol):
    """What a summarizable plan exposes (G1 smoke and the EXP-0 launcher share it)."""

    @property
    def plan(self) -> str: ...

    @property
    def execution_mode(self) -> str: ...

    def cells(self) -> list[Cell]: ...

    def cell_config(self, cell: Cell) -> RdsCellConfig: ...

    def sentinel_request(self) -> dict[str, object] | None: ...


# A post-load check on a cell's report: returns an invalid reason or None.
PostCheck = Callable[[Mapping[str, Any] | None, Cell], str | None]
VerdictFn = Callable[[str, Sequence[Mapping[str, Any]], bool], dict[str, Any]]


def cell_paths(cell: Cell, output: Path) -> dict[str, Path]:
    # Not Path.with_suffix: the version token ("7.5.2") contains dots.
    return {
        "report": output / f"{cell.evidence_basename}.json",
        "steps_jsonl": output / f"{cell.evidence_basename}.steps.jsonl",
        "log": output / f"{cell.run_id}.log",
        "summary": output / "summaries" / f"{cell.run_id}.summary.json",
    }


def vocabulary_equality(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per seed, the three arms' final token pools must be the same nonempty set.

    This is the native evidence for the G1 "vocabulary equality" test: the pools
    are reconstructed from each cell's recorded step name segments, so when the
    producer was native the equality was observed on node-tar, not assumed.
    """
    per_seed: dict[str, dict[str, Any]] = {}
    by_seed: dict[int, dict[str, frozenset[str]]] = {}
    for cell in cells:
        by_seed.setdefault(int(cell["seed"]), {})[str(cell["arm"])] = frozenset(
            cell.get("vocabulary_pool_final", ())
        )
    for seed, pools in sorted(by_seed.items()):
        arms = sorted(pools)
        distinct = set(pools.values())
        equal = (
            set(arms) >= {arm.value for arm in MAIN_ARMS}
            and len(distinct) == 1
            and bool(next(iter(distinct)))
        )
        per_seed[str(seed)] = {
            "equal": equal,
            "arms": arms,
            "pool_sizes": {arm: len(pools[arm]) for arm in arms},
        }
    return {
        "equal": bool(per_seed) and all(item["equal"] for item in per_seed.values()),
        "per_seed": per_seed,
        "basis": "vocabulary_pool_final reconstructed from each cell's recorded step "
        "name_segments (fixed at step 0 BEFORE for observed-names); empty pools fail",
    }


def g1_verdict(
    plan: str, cells: Sequence[Mapping[str, Any]], vocabulary_equal: bool
) -> dict[str, Any]:
    invalid = sum(1 for cell in cells if cell.get("invalid"))
    aborts = sum(1 for cell in cells if not cell["complete"] and not cell.get("invalid"))
    if plan == "completion":
        passed = bool(cells) and aborts == 0
        rule = "every cell complete"
    else:
        passed = len(cells) >= SMOKE_MIN_CELLS and aborts <= SMOKE_MAX_ABORTS
        rule = f">= {SMOKE_MIN_CELLS} cells and aborts <= {SMOKE_MAX_ABORTS}"
    rule += "; no config-nonconformant cell; vocabulary pools equal across arms per seed"
    return {
        "plan": plan,
        "rule": rule,
        "cells": len(cells),
        "aborts": aborts,
        "invalid": invalid,
        "vocabulary_equal_across_arms": vocabulary_equal,
        "pass": passed and invalid == 0 and vocabulary_equal,
    }


def _docker_version_from_log(log: Path) -> str | None:
    if not log.is_file():
        return None
    match = _ENGINE_LINE.search(log.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else None


def _host_record() -> dict[str, Any]:
    return {
        "machine": platform.machine(),
        "system": platform.system(),
        "release": platform.release(),
    }


def _manifest_host(output: Path) -> dict[str, Any] | None:
    manifest = output / "matrix.json"
    if not manifest.is_file():
        return None
    loaded = json.loads(manifest.read_text(encoding="utf-8"))
    host = loaded.get("host") if isinstance(loaded, dict) else None
    return dict(host) if isinstance(host, dict) else None


def summarize_output(
    plan: CellPlan,
    output: Path,
    *,
    labels: Sequence[str] = LABELS,
    gate: str = GATE,
    verdict_fn: VerdictFn | None = None,
    post_check: PostCheck | None = None,
    extra: Mapping[str, Any] | None = None,
    redact_outcomes: bool = False,
) -> dict[str, Any]:
    """(Re)build ``summaries/`` from the cell files in ``output``; returns the index.

    A cell whose report records a different config than planned (or fails
    ``post_check``) is not folded into complete/abort: it is the third bucket,
    ``config_nonconformant`` (invalid), with no summary and its reason recorded; it
    fails the verdict. ``extra`` is merged into the index document (e.g. the
    registration a launcher ran under). With ``redact_outcomes`` (a registered
    experiment that forbids interim analysis, while cells are still pending) the
    index carries completion state only — no hit/T_first fields, no summary files —
    so nothing outcome-bearing exists to look at before the run is complete.
    """
    verdict_fn = g1_verdict if verdict_fn is None else verdict_fn
    summaries_dir = output / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    manifest_host = _manifest_host(output)
    index: list[dict[str, Any]] = []
    for cell in plan.cells():
        paths = cell_paths(cell, output)
        config = plan.cell_config(cell)
        host = dict(manifest_host or {})
        host["docker_server_version"] = _docker_version_from_log(paths["log"])
        record: dict[str, Any] = {
            "schema_version": 1,
            "label": list(labels),
            "producer": "native",
            "gate": gate,
            "run_id": cell.run_id,
            "source": {
                "report": paths["report"].name,
                "steps_jsonl": paths["steps_jsonl"].name,
                "log": paths["log"].name,
            },
            "sentinel_set_requested": plan.sentinel_request(),
            "config_nonconformant": False,
            "invalid_reason": None,
        }
        entry: dict[str, Any] = {
            "run_id": cell.run_id,
            "arm": cell.arm.label,
            "seed": cell.seed,
            "budget": cell.budget,
            "summary": f"summaries/{paths['summary'].name}",
        }
        try:
            loaded = load_cell_files(paths["report"], paths["steps_jsonl"])
            if loaded.report is not None:
                check_report_config(loaded.report, config)
            if post_check is not None:
                problem = post_check(loaded.report, cell)
                if problem is not None:
                    raise ReportFormatError(problem)
            aborted_at, reason = loaded.aborted_at_step, loaded.abort_reason
            if aborted_at is None and len(loaded.records) < config.execution_budget:
                aborted_at = len(loaded.records)
                reason = "report has fewer steps than the budget and no abort record"
            report_summary = summarize_report_records(
                loaded.records, config, aborted_at_step=aborted_at, abort_reason=reason
            )
        except (ReportFormatError, ValueError, json.JSONDecodeError) as error:
            record.update(
                config_nonconformant=True,
                invalid_reason=f"{type(error).__name__}: {error}",
                summary=None,
            )
            entry.update(
                complete=False,
                aborted=False,
                invalid=True,
                hit=None,
                t_first=None,
                t_first_event=None,
                vocabulary_pool_final=[],
            )
        else:
            record["source"].update(
                report_present=loaded.report_present, steps_from=loaded.steps_from
            )
            record.update(report_summary.record())
            record["timing"] = timing_record(loaded.report, plan.execution_mode)
            record["environment"] = environment_record(loaded.report, host)
            summary = report_summary.summary
            entry.update(
                complete=summary.complete,
                aborted=summary.aborted,
                invalid=False,
                hit=summary.hit,
                t_first=summary.t_first,
                t_first_event=summary.t_first_event,
                vocabulary_pool_final=list(summary.vocabulary_pool_final),
            )
        if redact_outcomes:
            for key in ("hit", "t_first", "t_first_event"):
                entry.pop(key, None)
            entry["summary"] = None
            entry["outcomes_redacted"] = True
        else:
            paths["summary"].write_text(
                json.dumps(record, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                encoding="ascii",
            )
        index.append(entry)
    equality = vocabulary_equality(index)
    verdict = verdict_fn(plan.plan, index, equality["equal"])
    document = {
        "schema_version": 1,
        "label": list(labels),
        "gate": gate,
        **dict(extra or {}),
        "plan": plan.plan,
        "execution_mode": plan.execution_mode,
        "cells": index,
        "abort_count": verdict["aborts"],
        "invalid_count": verdict["invalid"],
        "outcomes_redacted": redact_outcomes,
        "vocabulary_equal_across_arms": equality["equal"],
        "vocabulary_equality": equality,
        "g1_verdict": verdict,
    }
    (summaries_dir / "index.json").write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    return document


def _manifest(plan: G1Plan, output: Path, results: Sequence[CellResult] | None) -> None:
    manifest: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "label": list(LABELS),
        "gate": GATE,
        "plan": plan.plan,
        "mode": "demo-historical",
        "execution_mode": plan.execution_mode,
        "host": _host_record(),
        "version": plan.version,
        "budget": plan.budget,
        "seeds": list(plan.seeds),
        "vocabulary_mode": plan.vocabulary_mode.value,
        "r_variant": plan.r_variant.value,
        "arms": [
            {"label": a.label, "search": a.search, "mutation": a.mutation} for a in plan.arms()
        ],
        "sentinel_set_requested": plan.sentinel_request(),
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
            for r in (results or ())
        ],
    }
    (output / "matrix.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _dry_run(plan: G1Plan, output: Path, base_env: dict[str, str]) -> None:
    cells = plan.cells()
    print(
        f"plan={plan.plan} mode=demo-historical version={plan.version} budget={plan.budget} "
        f"cells={len(cells)} vocabulary={plan.vocabulary_mode.value} "
        f"execution_mode={plan.execution_mode} labels={list(LABELS)}"
    )
    print(f"warmup: BUILD_ONLY=1 bash {SCRIPT} demo-historical")
    for cell in cells:
        env = cell_env(cell, output, base_env)
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
                "INODEFENCE_EVIDENCE_DIR",
            )
            if key in env
        }
        if plan.sentinel_seed is not None:
            shown["DEMO_SENTINEL_SEED"] = str(plan.sentinel_seed)
            shown["DEMO_SENTINEL_COUNT"] = str(plan.sentinel_count)
        paths = cell_paths(cell, output)
        print(f"  {cell.run_id}: bash {SCRIPT} demo-historical")
        print(f"    env: {json.dumps(shown, sort_keys=True)}")
        print(
            f"    report={paths['report']} steps={paths['steps_jsonl']} "
            f"log={paths['log']} summary={paths['summary']}"
        )
    print(f"index: {output / 'summaries' / 'index.json'}  manifest: {output / 'matrix.json'}")


def _comma_ints(value: str) -> list[int]:
    try:
        return [int(item) for item in value.split(",") if item.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integers") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--plan", choices=PLANS, required=True)
    parser.add_argument("--output", type=Path, required=True, help="evidence directory")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="frozen historical node-tar")
    parser.add_argument("--seeds", type=_comma_ints, default=None, help="comma list; plan default")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument(
        "--vocabulary",
        choices=tuple(mode.value for mode in VocabularyMode),
        default=VocabularyMode.OBSERVED_NAMES.value,
    )
    parser.add_argument(
        "--r-variant", choices=tuple(v.value for v in RVariant), default=RVariant.WALK.value
    )
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument(
        "--execution-mode",
        choices=EXECUTION_MODES,
        default=DEFAULT_EXECUTION_MODE,
        help="declared target execution path recorded in every summary (timing.execution_mode)",
    )
    parser.add_argument("--sentinel-seed", type=int, default=None)
    parser.add_argument("--sentinel-count", type=int, default=3)
    parser.add_argument("--skip-build", action="store_true", help="reuse prebuilt images")
    parser.add_argument("--python", default=None, help="host Python for the inner script")
    parser.add_argument("--context", default=None, help="Docker context")
    parser.add_argument("--dry-run", action="store_true", help="print plan/commands; no Docker")
    parser.add_argument(
        "--summarize-only", action="store_true", help="rebuild summaries/ from --output; no Docker"
    )
    args = parser.parse_args(argv)

    if args.budget < 1:
        parser.error("--budget must be >= 1")
    if args.jobs < 1:
        parser.error("--jobs must be >= 1")
    if args.sentinel_seed is not None and args.sentinel_count < 1:
        parser.error("--sentinel-count must be >= 1")
    seeds = tuple(args.seeds) if args.seeds else DEFAULT_SEEDS[args.plan]
    if len(set(seeds)) != len(seeds):
        parser.error("--seeds must be unique")
    plan = G1Plan(
        args.plan,
        args.version,
        seeds,
        args.budget,
        VocabularyMode(args.vocabulary),
        RVariant(args.r_variant),
        args.sentinel_seed,
        args.sentinel_count if args.sentinel_seed is not None else None,
        args.execution_mode,
    )
    try:
        cells = plan.cells()
    except ValueError as error:
        parser.error(str(error))
    if args.plan == "smoke" and len(cells) < SMOKE_MIN_CELLS:
        parser.error(f"smoke plan needs >= {SMOKE_MIN_CELLS} cells; give more --seeds")

    output: Path = args.output
    base_env = dict(os.environ)
    if args.python:
        base_env["PYTHON"] = args.python
    if args.context:
        base_env["INODEFENCE_DOCKER_CONTEXT"] = args.context

    if args.dry_run:
        _dry_run(plan, output, base_env)
        return 0
    if args.summarize_only:
        document = summarize_output(plan, output)
        print(json.dumps(document["g1_verdict"], sort_keys=True))
        return 0 if document["g1_verdict"]["pass"] else 1

    if plan.sentinel_seed is not None:
        print("refusing to run: sentinel set is not wired through the controller path yet:")
        for item in SENTINEL_WIRING:
            print(f"  - {item}")
        return 2
    bash = shutil.which("bash")
    if bash is None:
        raise SystemExit("bash not found: the native smoke runs only on the host terminal")
    _prepare_output_dir(output)
    if not args.skip_build:
        code = _warmup("demo-historical", output, base_env, bash)
        if code != 0:
            print(
                f"image warmup failed (exit {code}); see {output / 'warmup.log'}", file=sys.stderr
            )
            return code
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda cell: _run_cell(cell, output, base_env, bash), cells))
    _manifest(plan, output, results)
    document = summarize_output(plan, output)
    verdict = document["g1_verdict"]
    print(json.dumps(verdict, sort_keys=True))
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

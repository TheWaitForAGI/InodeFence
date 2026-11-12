"""Merge the two hosts' run directories of one two-host registration into one analysable index.

Each host runs ``run_exp0 --seed-assignment FILE --host-id HOSTn`` into its own directory. This tool
checks that the two directories are halves of the same registered run, then writes one index that
``analyze_exp0 --index`` reads like a one-host index:

    python -m scripts.merge_host_indexes --preregistration exp2-v1.md \\
        --seed-assignment exp2-v1.assignment.json \\
        --host HOST1=<run dir> --host HOST2=<run dir> --output <merged dir>

Refused (exit 2, nothing written): an assignment file that is not what the registered
``seed_assignment_rule`` gives (``--go-decision`` for ``rh-proportional-v1``), a different
preregistration sha256 or assignment sha256 in a
directory, a directory recorded under another host id, a seed in both directories or outside its
host's assignment, a run id in both, an exit-record line without this host's id and assignment
sha256, or launcher records that differ where the registration fixes them.

Incomplete (exit 1, written with ``merge.complete = false`` and ``g1_verdict.pass = false``): a host
directory not given yet, or the hosts' seeds not covering the assignment. Seeds are never moved
from one host to the other here.

Pooled records follow the one-host definitions over the union of cells: cell completeness counts
are sums and the failure rate is recomputed from the sums; a registered deadline excludes the union
of the hosts' excluded seed blocks. Each host's own records stay under ``hosts.<id>``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any

from inodefence.evaluation.cell_completeness import CELL_RESULTS_FILE
from inodefence.evaluation.rds_preregistration import (
    PreregistrationFormatError,
    load_preregistration,
)
from inodefence.evaluation.seed_assignment import (
    HOST_IDS,
    SeedAssignment,
    SeedAssignmentError,
    load_seed_assignment,
    rule_problems,
)

REGISTRATION_FILE = "registration.json"
INDEX_PATH = Path("summaries") / "index.json"
# Launcher records that must be byte-equal across the hosts (they come from the registration).
SHARED_KEYS = ("preregistration", "targets", "analysis_plan", "registered", "plan")
COUNT_KEYS = (
    "cells",
    "complete",
    "aborts",
    "watchdog",
    "no_record",
    "record_inconsistent",
    "unattempted",
    "aborts_plus_inconsistent",
    "unknown_outcome_steps",
    "recorded_steps",
)


class MergeRefused(ValueError):
    """The directories are not two halves of one registered two-host run."""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MergeRefused(f"{path}: {error}") from error


def _check_lines(run_dir: Path, host_id: str, assignment: SeedAssignment) -> None:
    """Every exit-record line names this host and the assignment it ran under."""
    path = run_dir / CELL_RESULTS_FILE
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            if number == len(lines):
                continue  # The launcher forgives only a cut last line; so does this check.
            raise MergeRefused(f"{path}:{number}: unreadable line") from None
        if row.get("host_id") != host_id or row.get("seed_assignment_sha256") != (
            assignment.sha256
        ):
            raise MergeRefused(
                f"{path}:{number}: line is not from {host_id} under assignment "
                f"{assignment.sha256[:12]}…"
            )


def load_host(
    run_dir: Path, host_id: str, prereg_sha: str, assignment: SeedAssignment
) -> dict[str, Any]:
    """One host's index, after checking it belongs to this registration, host and assignment."""
    registration = _read_json(run_dir / REGISTRATION_FILE)
    index = _read_json(run_dir / INDEX_PATH)
    for name, record in (("registration", registration), ("index", index)):
        recorded = record.get("seed_assignment") if isinstance(record, dict) else None
        if not isinstance(recorded, dict):
            raise MergeRefused(f"{run_dir}: {name} has no seed_assignment record")
        if recorded.get("sha256") != assignment.sha256:
            raise MergeRefused(f"{run_dir}: {name} ran under another seed assignment")
        if recorded.get("host_id") != host_id:
            raise MergeRefused(
                f"{run_dir}: {name} is from host {recorded.get('host_id')!r}, not {host_id}"
            )
    if registration.get("preregistration_sha256") != prereg_sha:
        raise MergeRefused(f"{run_dir}: registered under another preregistration sha256")
    if index.get("preregistration", {}).get("sha256") != prereg_sha:
        raise MergeRefused(f"{run_dir}: index is from another preregistration sha256")
    assigned = set(assignment.seeds_for(host_id))
    cells = index.get("cells")
    if not isinstance(cells, list):
        raise MergeRefused(f"{run_dir}: index has no cell list")
    seeds = {cell.get("seed") for cell in cells}
    if not seeds <= assigned:
        stray = sorted(seeds - assigned, key=str)
        raise MergeRefused(f"{run_dir}: seeds {stray} are not assigned to {host_id}")
    _check_lines(run_dir, host_id, assignment)
    return index


def _absolute(entry: Mapping[str, Any], run_dir: Path) -> dict[str, Any]:
    pointer = entry.get("summary")
    merged = dict(entry)
    if isinstance(pointer, str):
        merged["summary"] = str((run_dir / pointer).resolve())
    return merged


def _merge_completeness(parts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        key: sum(int(p.get(key) or 0) for p in parts.values()) for key in COUNT_KEYS
    }
    merged["infrastructure_failure_rate"] = (
        merged["aborts_plus_inconsistent"] / merged["cells"] if merged["cells"] else None
    )
    merged["infrastructure_stopped"] = any(p.get("infrastructure_stopped") for p in parts.values())
    for key in ("infrastructure_stops", "infrastructure_resumes"):
        merged[key] = [
            {**event, "host_id": host} for host, p in parts.items() for event in p.get(key) or ()
        ]
    merged["inconsistent_checks"] = {
        run_id: problems
        for p in parts.values()
        for run_id, problems in (p.get("inconsistent_checks") or {}).items()
    }
    return merged


def _merge_deadline(parts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    instants = {p.get("execution_deadline") for p in parts.values()}
    if len(instants) != 1:
        raise MergeRefused(
            f"hosts recorded different execution deadlines {sorted(map(str, instants))}"
        )
    excluded: dict[str, set[int]] = {}
    causes: dict[str, str] = {}
    for p in parts.values():
        for target, seeds in (p.get("excluded_seeds") or {}).items():
            excluded.setdefault(target, set()).update(seeds)
        causes.update(p.get("causes") or {})
    return {
        "execution_deadline": instants.pop(),
        "passed": all(p.get("passed") for p in parts.values()),
        "excluded_seeds": {target: sorted(seeds) for target, seeds in sorted(excluded.items())},
        "causes": dict(sorted(causes.items())),
    }


#: The cause recorded for a seed block left unfinished by an unresumed stop (D047 section 9.1).
PARTIAL_GO_CAUSE = "unresumed-stop-partial-go"


def exclude_unfinished_blocks(document: dict[str, Any], go_decision: Mapping[str, Any]) -> None:
    """D047 section 9.1 (b): an excluded host's unfinished train seed blocks leave the analysis.

    They join the index ``deadline`` record's ``excluded_seeds`` (the D041 rule the analysis
    already applies), with the cause keyed ``<host>/<target>/s<seed>``. The seeds come from the
    GO decision file that ``partial_go_check --record-in-go-decision`` wrote, never from outcomes.
    """
    excluded = go_decision.get("excluded_hosts") or []
    completion = go_decision.get("partial_completion")
    if not isinstance(completion, Mapping) or any(h not in completion for h in excluded):
        raise MergeRefused("the GO file excludes hosts without their partial_completion")
    empty: dict[str, Any] = {"execution_deadline": None, "passed": None}
    deadline: dict[str, Any] = dict(document.get("deadline") or empty)
    seeds = {t: set(v) for t, v in (deadline.get("excluded_seeds") or {}).items()}
    causes = dict(deadline.get("causes") or {})
    for host in excluded:
        for target, blocks in completion[host].items():
            for seed in blocks.get("unfinished_seeds") or []:
                seeds.setdefault(target, set()).add(int(seed))
                causes[f"{host}/{target}/s{seed}"] = PARTIAL_GO_CAUSE
    deadline["excluded_seeds"] = {t: sorted(v) for t, v in sorted(seeds.items())}
    deadline["causes"] = dict(sorted(causes.items()))
    deadline["partial_go_excluded_hosts"] = sorted(excluded)
    document["deadline"] = deadline


def merge(
    indexes: Mapping[str, Mapping[str, Any]],
    run_dirs: Mapping[str, Path],
    assignment: SeedAssignment,
) -> dict[str, Any]:
    """The merged index document. ``indexes`` holds the hosts given so far (one or both)."""
    first = next(iter(indexes.values()))
    for key in SHARED_KEYS:
        values = {json.dumps(index.get(key), sort_keys=True) for index in indexes.values()}
        if len(values) != 1:
            raise MergeRefused(f"hosts differ in the registered record {key!r}")
    cells: list[dict[str, Any]] = []
    owner: dict[str, str] = {}
    seed_host: dict[int, str] = {}
    for host, index in indexes.items():
        for entry in index["cells"]:
            run_id, seed = entry.get("run_id"), entry.get("seed")
            if run_id in owner:
                raise MergeRefused(f"run id {run_id} is in {owner[run_id]} and {host}")
            if seed_host.setdefault(seed, host) != host:
                raise MergeRefused(f"seed {seed} has cells on {seed_host[seed]} and {host}")
            owner[run_id] = host
            cells.append(_absolute(entry, run_dirs[host]))
    missing_hosts = [host for host in assignment.participants if host not in indexes]
    missing_seeds = sorted(set(assignment.all_seeds()) - set(seed_host))
    reasons = [f"host {host} not merged yet" for host in missing_hosts]
    if missing_seeds and not missing_hosts:
        reasons.append(f"assigned seeds without cells: {missing_seeds}")
    complete = not reasons
    host_verdicts = {host: index.get("g1_verdict") or {} for host, index in indexes.items()}
    verdict = {
        "plan": first.get("plan"),
        "cells": sum(int(v.get("cells") or 0) for v in host_verdicts.values()),
        "complete": sum(int(v.get("complete") or 0) for v in host_verdicts.values()),
        "aborts": sum(int(v.get("aborts") or 0) for v in host_verdicts.values()),
        "invalid": sum(int(v.get("invalid") or 0) for v in host_verdicts.values()),
        "vocabulary_equal_across_arms": all(
            v.get("vocabulary_equal_across_arms") for v in host_verdicts.values()
        ),
        "pass": complete and all(v.get("pass") is True for v in host_verdicts.values()),
        "rule": "both hosts merged, every assigned seed present, each host's own verdict passes",
    }
    document: dict[str, Any] = {
        "schema_version": 1,
        "label": first.get("label"),
        **{key: first.get(key) for key in SHARED_KEYS if key in first},
        "execution_mode": first.get("execution_mode"),
        "seed_assignment": {**assignment.record(), "host_of_seed_checked": True},
        "merge": {
            "complete": complete,
            "reasons": reasons,
            "hosts": sorted(indexes),
            "run_dirs": {host: str(path.resolve()) for host, path in run_dirs.items()},
        },
        "hosts": {
            host: {
                key: index.get(key)
                for key in ("g1_verdict", "deadline", "cell_completeness", "interim")
                if key in index
            }
            for host, index in indexes.items()
        },
        "cells": cells,
        "outcomes_redacted": any(index.get("outcomes_redacted") for index in indexes.values()),
        "g1_verdict": verdict,
    }
    completeness = {
        host: index["cell_completeness"]
        for host, index in indexes.items()
        if isinstance(index.get("cell_completeness"), dict)
    }
    if completeness:
        document["cell_completeness"] = _merge_completeness(completeness)
    deadlines = {
        host: index["deadline"]
        for host, index in indexes.items()
        if isinstance(index.get("deadline"), dict)
    }
    if deadlines:
        document["deadline"] = _merge_deadline(deadlines)
    return document


def steps_paths(
    preregistration: Path, assignment: SeedAssignment, run_dirs: Mapping[str, Path]
) -> dict[str, dict[str, Path]]:
    """Per host, run id -> steps file, named exactly as the launcher names it (``cell_paths``).

    No summary or report is opened to find a file.
    """
    from scripts.run_exp0 import DEFAULT_VERSION, Exp0Plan
    from scripts.run_g1_smoke import cell_paths

    prereg = load_preregistration(preregistration)
    digest = sha256(preregistration.read_bytes()).hexdigest()
    found: dict[str, dict[str, Path]] = {}
    for host, run_dir in run_dirs.items():
        plan = Exp0Plan(
            prereg,
            preregistration,
            digest,
            DEFAULT_VERSION,
            False,  # as run_exp0 without --include-s-a: S-a never runs in EXP-3, EXP-2 or D047
            assignment=assignment,
            host_id=host,
        )
        found[host] = {
            cell.run_id: cell_paths(cell, run_dir)["steps_jsonl"] for cell in plan.cells()
        }
    return found


def compare_replicates(
    indexes: Mapping[str, Mapping[str, Any]],
    run_dirs: Mapping[str, Path],
    steps: Mapping[str, Mapping[str, Path]],
) -> dict[str, Any]:
    """``replicate-v1``: the same cell on each host, path against path. Never pooled.

    The pairs go through ``compare_cell_paths.compare_pairs`` (the same comparison a host's
    original-versus-re-run check uses): per run id whether the two ``case_id`` sequences are
    equal, their common prefix and lengths, and each side's infrastructure re-executions; then
    ``m_x``, ``incomparable`` and ``identical``. Report only.
    """
    from scripts.compare_cell_paths import compare_pairs

    hosts = sorted(indexes)
    if len(hosts) != 2:
        raise MergeRefused("--compare needs both hosts' directories")
    by_host = {host: {entry["run_id"]: entry for entry in indexes[host]["cells"]} for host in hosts}
    shared = sorted(set(by_host[hosts[0]]) & set(by_host[hosts[1]]))
    only = sorted(set(by_host[hosts[0]]) ^ set(by_host[hosts[1]]))
    missing = [run_id for run_id in shared if any(run_id not in steps[h] for h in hosts)]
    if missing:
        raise MergeRefused(f"cells not in the plan: {missing}")
    # Both indexes carry the same preregistration sha (load_host), so the budget is equal by the
    # registration; a per-cell budget that differs still means the indexes are not comparable.
    unequal = [
        run_id
        for run_id in shared
        if by_host[hosts[0]][run_id].get("budget") != by_host[hosts[1]][run_id].get("budget")
    ]
    if unequal:
        raise MergeRefused(f"replicate cells with different budgets: {unequal}")
    compared = compare_pairs(
        {run_id: (steps[hosts[0]][run_id], steps[hosts[1]][run_id]) for run_id in shared},
        (hosts[0], hosts[1]),
    )
    return {
        "classification": "replicate-v1 cross-host path comparison: report only, never pooled",
        "hosts": hosts,
        "run_ids_on_one_host_only": only,
        **compared,
        "all_identical": bool(compared["cells"])
        and not only
        and compared["summary"]["m_x"] == 0
        and compared["summary"]["incomparable"] == 0,
    }


def _host_arg(text: str) -> tuple[str, Path]:
    host, sep, path = text.partition("=")
    if not sep or host not in HOST_IDS or not path:
        raise argparse.ArgumentTypeError(f"expected HOST1=<dir> or HOST2=<dir>, got {text!r}")
    return host, Path(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--seed-assignment", type=Path, required=True)
    parser.add_argument("--go-decision", type=Path, help="holdout: the GO decision file (r_h)")
    parser.add_argument("--host", type=_host_arg, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True, help="directory for summaries/")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="replicate-v1 only: compare the hosts' paths (written as compare.json), never pool",
    )
    args = parser.parse_args(argv)
    run_dirs = dict(args.host)
    if len(run_dirs) != len(args.host):
        parser.error("each host may be given once")
    try:
        prereg = load_preregistration(args.preregistration)
        prereg_sha = sha256(args.preregistration.read_bytes()).hexdigest()
        assignment = load_seed_assignment(args.seed_assignment, prereg.seeds)
        go_decision = (
            None
            if args.go_decision is None
            else json.loads(args.go_decision.read_text(encoding="utf-8"))
        )
        problems = rule_problems(
            assignment.data,
            rule=prereg.seed_assignment_rule or "",
            registered_seeds=prereg.seeds,
            registered_sha256=prereg.seed_assignment_sha256,
            go_decision=go_decision if isinstance(go_decision, dict) else None,
        )
        if problems:
            raise MergeRefused("; ".join(problems))
        strangers = sorted(set(run_dirs) - set(assignment.participants))
        if strangers:
            raise MergeRefused(f"hosts {strangers} take no part in this assignment")
        if assignment.replicated != args.compare:
            raise MergeRefused(
                "replicate-v1 runs are compared, never pooled: use --compare"
                if assignment.replicated
                else "--compare is only for replicate-v1 assignments"
            )
        indexes = {
            host: load_host(run_dirs[host], host, prereg_sha, assignment)
            for host in HOST_IDS
            if host in run_dirs
        }
        if args.compare:
            comparison = compare_replicates(
                indexes, run_dirs, steps_paths(args.preregistration, assignment, run_dirs)
            )
            args.output.mkdir(parents=True, exist_ok=True)
            out = args.output / "compare.json"
            out.write_text(
                json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(json.dumps({"compare": str(out), "all_identical": comparison["all_identical"]}))
            return 0 if comparison["all_identical"] else 1
        document = merge(indexes, run_dirs, assignment)
        if isinstance(go_decision, dict) and go_decision.get("excluded_hosts"):
            exclude_unfinished_blocks(document, go_decision)
    except (
        MergeRefused,
        SeedAssignmentError,
        PreregistrationFormatError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        print(f"merge refused: {error}", file=sys.stderr)
        return 2
    target = args.output / INDEX_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="ascii"
    )
    print(json.dumps({"index": str(target), **document["merge"]}, sort_keys=True))
    return 0 if document["merge"]["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

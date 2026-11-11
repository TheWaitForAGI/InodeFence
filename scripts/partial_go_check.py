"""Partial GO inputs (D047 section 9.1): unresumed-stop participants, seed blocks, hold conditions.

At GO time a participant whose last infrastructure event is an unresumed ``infrastructure-stop``
leaves ``r`` and the holdout assignment; its finished train cells stay in E, abort and e. This
tool finds those hosts, lists every participant's finished and unfinished train seed blocks (the
D041 rule: a seed with an unattempted cell is unfinished), and checks the hold conditions for each
excluded host. Any hold condition means no GO: the decision goes to the person (지웅).

* (i) the stop cause is unconfirmed (D047 Q8 on the cells that ended the run) or is not an
  infrastructure cause;
* (ii) the host's aborts look input dependent: the same (arm, seed, step, case id) in two
  attempts, or the host's arm x abort table flags at p <= .10 (``arm_abort_independence``);
* (iii) the host's records are incomplete (a start without its end line, a start-gate cell not
  verified clean) or its evidence manifest does not verify;
* (iv) no recorded statement that the stop was not a decision made after reading oracle values.

Inputs are the exit record, cell states, abort stubs (reason, category, error chain, step index,
case id) and file hashes. No oracle field is read; the output holds counts, seeds and reasons.

    python -m scripts.partial_go_check --preregistration exp3-v1-filled.md \\
        --seed-assignment A.json --host HOST1=<out-1> --host HOST2=<out-2> \\
        --go-decision exp3-train-go-decision.json --raw-manifest HOST2=<manifest.sha256> \\
        --stop-statement HOST2=<approval ref> [--record-in-go-decision] --out check.json

``--record-in-go-decision`` writes ``excluded_hosts``, ``exclusions`` and
``partial_completion`` into the GO decision file (refused when it already holds other values).
``gen_exp3_tables`` (T-EXP3-2, ``--go-rates-out``), ``make_seed_assignment`` and
``merge_host_indexes`` read them from there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.qualify_host import Reader, abort_category, gate_state, unconfirmed_abort
from scripts.run_exp0 import DEFAULT_VERSION, Exp0Plan, TargetCell
from scripts.run_g1_smoke import cell_paths

from inodefence.evaluation.abort_classification import INFRASTRUCTURE_REASONS, InvalidReason
from inodefence.evaluation.cell_completeness import (
    ABORT_FINAL,
    CELL_RESULTS_FILE,
    COMPLETE,
    INFRASTRUCTURE_STOP_EVENT,
    UNATTEMPTED,
    Attempt,
    counted_attempts,
    read_cell_results,
    read_infrastructure_events,
)
from inodefence.evaluation.independence import arm_abort_independence
from inodefence.evaluation.rds_preregistration import load_preregistration
from inodefence.evaluation.seed_assignment import load_seed_assignment

#: Stop causes counted as infrastructure: the retryable classes plus a failed docker call.
INFRASTRUCTURE_CATEGORIES = frozenset(
    {reason.value for reason in INFRASTRUCTURE_REASONS} | {InvalidReason.RUNTIME_CALL.value}
)
#: A start-gate stop: cleanup state, an infrastructure cause by construction.
GATE_STOP_MARKERS = ("start gate", "cleanup unknown")
#: The guard stops after this many consecutive cells without a record.
TRIGGER_CELLS = 3
INDEPENDENCE_FLAG = "report_sensitivity"
NOT_ASSESSABLE = "not_assessable"
RECORD_KEYS = ("excluded_hosts", "exclusions", "partial_completion")


class PartialGoInputError(ValueError):
    """The inputs cannot give a partial GO check."""


def _realtime(row: Mapping[str, Any] | None) -> float | None:
    value = (row or {}).get("clocks", {}).get("realtime")
    return float(value) if isinstance(value, int | float) else None


def table_shape_problem(by_arm: Mapping[str, Sequence[int]]) -> str | None:
    """Why the arm x abort table cannot be tested, from its shape alone; ``None`` when it can.

    Each row is ``[complete, abort-final, invalid]`` cells of one arm. The test needs at least
    two arms, at least one abort-final cell and at least one complete cell. No cell-count floor
    is registered (D047), so none is added here.
    """
    if not by_arm:
        return "no complete or abort-final cell"
    if len(by_arm) < 2:
        return "fewer than two arms"
    if sum(row[1] for row in by_arm.values()) == 0:
        return "no abort-final cell"
    if sum(row[0] for row in by_arm.values()) == 0:
        return "no complete cell"
    return None


def attempt_stub(
    output: Path, cell: TargetCell, tried: Sequence[Attempt], position: int, reader: Reader
) -> Mapping[str, Any] | None:
    """The abort stub of one counted attempt: the cell's report for the last, the archive before.

    ``archive_attempt`` numbers a cell's moved files 1, 2, ... in order, so the n-th counted
    attempt that was retried is ``attempts/<run_id>.attempt<n>.json``.
    """
    if position == len(tried) - 1:
        path = cell_paths(cell, output)["report"]
    else:
        path = output / "attempts" / f"{cell.run_id}.attempt{position + 1}.json"
    stub, _ = reader.report_fields(path)
    return stub


def verify_manifest(output: Path, manifest: Path | None) -> list[str]:
    """``sha256  path`` lines (paths relative to the run directory or absolute) must all verify."""
    if manifest is None:
        return ["no evidence manifest given"]
    if not manifest.is_file():
        return [f"evidence manifest not found: {manifest}"]
    problems: list[str] = []
    covered: set[Path] = set()
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        if not name:
            problems.append(f"manifest line {number} is not '<sha256>  <path>'")
            continue
        path = Path(name) if Path(name).is_absolute() else output / name
        covered.add(path.resolve())
        if not path.is_file():
            problems.append(f"manifest file missing: {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"manifest hash differs: {name}")
    if (output / CELL_RESULTS_FILE).resolve() not in covered:
        problems.append(f"manifest does not cover {CELL_RESULTS_FILE}")
    return problems


def host_check(
    plan: Exp0Plan,
    output: Path,
    decided_at: float,
    *,
    manifest: Path | None,
    statement: str | None,
    reader: Reader,
) -> dict[str, Any]:
    """One participant: its stop state and seed blocks; for an excluded host, the hold checks."""
    from scripts.run_exp0 import target_cell_check

    results = output / CELL_RESULTS_FILE
    if not results.is_file():
        raise PartialGoInputError(f"{results}: no exit record")
    reader.files.append(str(results))
    attempts = read_cell_results(results)
    events = [e for e in read_infrastructure_events(results) if _realtime(e) is not None]
    events = [e for e in events if (_realtime(e) or 0.0) <= decided_at]
    last = events[-1] if events else None
    unresumed = last is not None and last.get("event") == INFRASTRUCTURE_STOP_EVENT
    states: dict[str, str] = {}
    unfinished: dict[str, set[int]] = {}
    causes: dict[str, str] = {}
    seeds: dict[str, set[int]] = {}
    for cell in plan.cells():
        assert isinstance(cell, TargetCell)
        state = target_cell_check(plan, cell, output, attempts).state
        states[cell.run_id] = state
        seeds.setdefault(cell.target_id, set()).add(cell.seed)
        tried = counted_attempts(attempts.get(cell.run_id, ()))
        if state == UNATTEMPTED or any(attempt.ended is None for attempt in tried):
            unfinished.setdefault(cell.target_id, set()).add(cell.seed)
            causes[cell.run_id] = UNATTEMPTED if state == UNATTEMPTED else "started-without-end"
    completion = {
        target: {
            "finished_seeds": sorted(all_seeds - unfinished.get(target, set())),
            "unfinished_seeds": sorted(unfinished.get(target, set())),
        }
        for target, all_seeds in sorted(seeds.items())
    }
    document: dict[str, Any] = {
        "unresumed_stop": unresumed,
        "seed_blocks": completion,
        "unfinished_causes": dict(sorted(causes.items())),
        "cell_states": dict(sorted(Counter(states.values()).items())),
    }
    if not unresumed:
        return document
    assert last is not None
    hold: list[str] = []
    checks: dict[str, Any] = {}
    stop_reason = str(last.get("reason") or "")
    stop_at = _realtime(last) or 0.0

    # (i) The stop cause.
    cell_of = {cell.run_id: cell for cell in plan.cells() if isinstance(cell, TargetCell)}
    if any(marker in stop_reason for marker in GATE_STOP_MARKERS):
        checks["i_stop_cause"] = {"kind": "start gate", "trigger_cells": []}
    else:
        ended = sorted(
            (
                (_realtime(attempt.ended) or 0.0, run_id, position)
                for run_id, tried_all in attempts.items()
                for position, attempt in enumerate(counted_attempts(tried_all))
                if attempt.ended is not None and (_realtime(attempt.ended) or 0.0) <= stop_at
            ),
            reverse=True,
        )
        triggers = []
        for _, run_id, position in ended:
            if run_id not in cell_of or states.get(run_id) == COMPLETE:
                break
            tried = counted_attempts(attempts[run_id])
            stub = attempt_stub(output, cell_of[run_id], tried, position, reader)
            triggers.append(
                {
                    "run_id": run_id,
                    "attempt": position + 1,
                    "unconfirmed": unconfirmed_abort(stub),
                    "category": None if stub is None else abort_category(stub),
                }
            )
            if len(triggers) == TRIGGER_CELLS:
                break
        checks["i_stop_cause"] = {"kind": "cells without record", "trigger_cells": triggers}
        if not triggers:
            hold.append("(i) the cells that ended the run are not found")
        for trigger in triggers:
            if trigger["unconfirmed"]:
                hold.append(f"(i) unconfirmed abort cause: {trigger['run_id']}")
            elif trigger["category"] not in INFRASTRUCTURE_CATEGORIES:
                hold.append(
                    f"(i) not an infrastructure cause: {trigger['run_id']} {trigger['category']}"
                )

    # (ii) Input dependence: a repeated abort key, or the arm x abort flag.
    # Per cell (run id = target, arm, seed): two targets share arm labels and seeds.
    keys: Counter[tuple[str, int, str]] = Counter()
    by_arm: dict[str, list[int]] = {}
    for run_id, cell in cell_of.items():
        tried = counted_attempts(attempts.get(run_id, ()))
        for position in range(len(tried)):
            stub = attempt_stub(output, cell, tried, position, reader)
            if stub is not None and isinstance(stub.get("step_index"), int):
                keys[(run_id, stub["step_index"], str(stub.get("case_id")))] += 1
        if tried and states[run_id] in (COMPLETE, ABORT_FINAL):
            row = by_arm.setdefault(cell.arm.label, [0, 0, 0])
            row[0 if states[run_id] == COMPLETE else 1] += 1
    repeated = [
        {"run_id": run_id, "step_index": step, "attempts": count}
        for (run_id, step, _), count in sorted(keys.items())
        if count >= 2
    ]
    arms = sorted(by_arm)
    # The table's shape decides, before any test, whether the independence test can run
    # (table_shape_problem). Not assessable is not a hold reason: section 9.1 (ii) holds when an
    # input-dependence pattern is seen, and no data is not evidence of one; (i), (iii) and (iv)
    # still apply, the repeated-key check above always runs, and the reason stays visible in the
    # GO file and the T-EXP3-2 table. An error the test raises on a well-shaped table is not
    # caught: the tool refuses.
    shape = table_shape_problem(by_arm)
    notes: list[str] = []
    if shape is None:
        independence = arm_abort_independence([by_arm[arm] for arm in arms], arms)
        flag, p_value = independence["flag"], independence["primary_arm_vs_abort"].get("p_value")
    else:
        flag, p_value = NOT_ASSESSABLE, None
        notes.append(f"(ii) 검정 불가: {shape}")
    checks["ii_input_dependence"] = {
        "repeated_abort_keys": repeated,
        "arm_abort_table": {arm: by_arm[arm][:2] for arm in arms},
        "independence_flag": flag,
        "independence_p": p_value,
        "not_assessable_reason": shape,
    }
    if repeated:
        hold.append(f"(ii) the same abort input in {len(repeated)} cells")
    if flag == INDEPENDENCE_FLAG:
        hold.append("(ii) arm x abort independence flagged (p <= .10)")

    # (iii) Record completeness and evidence hashes.
    open_attempts = sorted(
        f"{run_id}#{position + 1}"
        for run_id, tried_all in attempts.items()
        for position, attempt in enumerate(counted_attempts(tried_all))
        if attempt.ended is None
    )
    gate = gate_state(output)
    manifest_problems = verify_manifest(output, manifest)
    checks["iii_records"] = {
        "starts_without_end": open_attempts,
        "gate": gate,
        "manifest": str(manifest) if manifest else None,
        "manifest_problems": manifest_problems,
    }
    if open_attempts:
        hold.append(f"(iii) starts without an end line: {len(open_attempts)}")
    if gate["not_clean"]:
        hold.append(f"(iii) start-gate cells not verified clean: {gate['not_clean']}")
    hold += [f"(iii) {problem}" for problem in manifest_problems]

    # (iv) A recorded statement that no oracle value was read before the stop decision.
    checks["iv_statement"] = statement
    if not statement:
        hold.append("(iv) no recorded statement that the stop preceded any oracle reading")

    document["exclusion"] = {
        "stop_reason": stop_reason,
        "stopped_at_realtime": stop_at,
        "checks": checks,
        "hold_reasons": hold,
        "notes": notes,
    }
    return document


def check(
    plans: Mapping[str, Exp0Plan],
    outputs: Mapping[str, Path],
    decided_at: float,
    *,
    manifests: Mapping[str, Path],
    statements: Mapping[str, str],
) -> dict[str, Any]:
    reader = Reader()
    hosts = {
        host: host_check(
            plans[host],
            outputs[host],
            decided_at,
            manifest=manifests.get(host),
            statement=statements.get(host),
            reader=reader,
        )
        for host in sorted(plans)
    }
    excluded = [host for host, doc in hosts.items() if doc["unresumed_stop"]]
    exclusions = {host: hosts[host]["exclusion"] for host in excluded}
    held = {host: e["hold_reasons"] for host, e in exclusions.items() if e["hold_reasons"]}
    if excluded and len(excluded) == len(hosts):
        status = "not computed: every participant stopped unresumed"
    elif held:
        status = "held: GO goes to the person (D047 section 9.1 item 3)"
    elif excluded:
        status = "partial: GO computable from the running participants"
    else:
        status = "full: no participant stopped unresumed"
    return {
        "classification": "partial GO check (D047 9.1): infrastructure and records, no oracle",
        "status": status,
        "participants": sorted(hosts),
        "hosts": hosts,
        "excluded_hosts": excluded,
        "exclusions": exclusions,
        "partial_completion": {host: doc["seed_blocks"] for host, doc in hosts.items()},
        "files_read": sorted(set(reader.files)),
    }


def record_in_go_decision(path: Path, document: Mapping[str, Any]) -> None:
    go = json.loads(path.read_text(encoding="utf-8"))
    for key in RECORD_KEYS:
        if key in go and go[key] != document[key]:
            raise PartialGoInputError(f"the GO decision file already holds another {key}")
        go[key] = document[key]
    path.write_text(json.dumps(go, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _pairs(values: Sequence[str], flag: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for item in values:
        host, sep, value = item.partition("=")
        if not sep or not host or not value or host in found:
            raise PartialGoInputError(f"{flag} expects HOST=VALUE once per host: {item}")
        found[host] = value
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--seed-assignment", type=Path, required=True)
    parser.add_argument("--host", action="append", default=[], metavar="HOST=OUTPUT")
    parser.add_argument("--go-decision", type=Path, required=True)
    parser.add_argument("--raw-manifest", action="append", default=[], metavar="HOST=PATH")
    parser.add_argument("--stop-statement", action="append", default=[], metavar="HOST=REF")
    parser.add_argument("--record-in-go-decision", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        outputs = {h: Path(p) for h, p in _pairs(args.host, "--host").items()}
        manifests = {h: Path(p) for h, p in _pairs(args.raw_manifest, "--raw-manifest").items()}
        statements = _pairs(args.stop_statement, "--stop-statement")
        prereg = load_preregistration(args.preregistration)
        assignment = load_seed_assignment(args.seed_assignment, prereg.seeds)
        if sorted(outputs) != sorted(assignment.participants):
            raise PartialGoInputError(
                f"--host must name every participant {list(assignment.participants)}"
            )
        decided = json.loads(args.go_decision.read_text(encoding="utf-8")).get("decided_at")
        decided_at = datetime.fromisoformat(str(decided))
        if decided_at.tzinfo is None:
            raise PartialGoInputError("decided_at needs a UTC offset")
        digest = hashlib.sha256(args.preregistration.read_bytes()).hexdigest()
        plans = {
            host: Exp0Plan(
                prereg,
                args.preregistration,
                digest,
                DEFAULT_VERSION,
                False,
                assignment=assignment,
                host_id=host,
            )
            for host in outputs
        }
        document = check(
            plans, outputs, decided_at.timestamp(), manifests=manifests, statements=statements
        )
        if args.record_in_go_decision:
            record_in_go_decision(args.go_decision, document)
    except (PartialGoInputError, OSError, ValueError, KeyError) as error:
        print(f"partial GO check refused: {error}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": document["status"], "excluded_hosts": document["excluded_hosts"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

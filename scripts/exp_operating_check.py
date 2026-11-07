"""The operating-stop check W2 runs during EXP-3 and EXP-2. It shows counts and never stops a run.

D041: over the last 24 hours, with at least 20 ended cells, the infrastructure failure rate
(aborts + inconsistent records, over ended cells) reaches .60. The decision stays with people: this
tool prints, and stopping or resuming follows the registered rule and W3.

The run is still sealed, so the output is pooled counts and clock values. No run id, arm, seed, step
or case id goes to the output, and the rule looks at no arm. Files it reads:

* ``cell-results.jsonl``, for every cell;
* for a cell ended in the window, the ``index`` of each step line;
* for a cell with a nonzero exit, its report, for the abort stub.

A cell that exited 0 has only its step lines checked, so no complete report is read. The launcher
checks it fully at ``finish``. Oracle values are never kept.

``--after-stop`` is for after a stop has really been called, and its use goes in ``docs/LOG.md``. It
adds reason category totals and end times, still without a cell's name.

    python -m scripts.exp_operating_check --preregistration <file> --output <run dir>

It lowers its own priority to nice 19, because it runs on the measured host.
"""

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from scripts.run_concurrency_benchmark import output_problem
from scripts.run_exp0 import DEFAULT_VERSION, Exp0Plan
from scripts.run_g1_smoke import cell_paths

from inodefence.evaluation.abort_classification import classify_abort_reason
from inodefence.evaluation.cell_completeness import (
    ABORT_FINAL,
    CELL_RESULTS_FILE,
    COMPLETE,
    NO_RECORD,
    RECORD_INCONSISTENT,
    UNATTEMPTED,
    Attempt,
    classify_cell,
    infrastructure_stopped,
    read_cell_results,
    read_infrastructure_events,
    scan_steps,
)
from inodefence.evaluation.rds import RdsArm
from inodefence.evaluation.rds_preregistration import (
    PreregistrationFormatError,
    load_preregistration,
)

WINDOW = timedelta(hours=24)
MIN_ENDED_CELLS = 20
STOP_RATE = 0.60
WATCHDOG_CATEGORY = "watchdog"


@dataclass(frozen=True, slots=True)
class CellFiles:
    report: Path
    steps: Path
    budget: int


@dataclass(frozen=True, slots=True)
class WindowCell:
    """What the check keeps of a cell. Cached values never hold an outcome."""

    state: str
    watchdog: bool
    category: str | None


def _stat(path: Path) -> list[float] | None:
    if not path.is_file():
        return None
    status = path.stat()
    return [status.st_size, status.st_mtime]


def _abort_category(report: Path) -> str | None:
    """The stub's reason as a fixed category: its text can name a case, the category cannot."""
    if not report.is_file():
        return None
    try:
        aborted = json.loads(report.read_text(encoding="utf-8")).get("aborted")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return None
    reason = aborted.get("reason") if isinstance(aborted, Mapping) else None
    return classify_abort_reason(reason).value if isinstance(reason, str) else None


def _classify(files: CellFiles, attempts: Sequence[Attempt]) -> WindowCell:
    ended = attempts[-1].ended or {}
    returncode, watchdog = ended.get("returncode"), ended.get("watchdog_fired") is True
    if returncode == 0 and not watchdog:
        scan = scan_steps(files.steps)
        whole = scan.indexes == tuple(range(files.budget))
        whole = whole and not scan.torn_last_line and not scan.torn_inner_line
        return WindowCell(COMPLETE if whole else RECORD_INCONSISTENT, False, None)
    check = classify_cell(
        report_path=files.report,
        steps_path=files.steps,
        budget=files.budget,
        attempts=attempts,
        complete_and_conformant=False,
    )
    category = None
    if check.state == ABORT_FINAL:
        category = WATCHDOG_CATEGORY if check.watchdog else _abort_category(files.report)
    return WindowCell(check.state, check.watchdog, category)


def _cached_classify(
    run_id: str,
    files: CellFiles,
    attempts: Sequence[Attempt],
    cache: dict[str, Any],
) -> WindowCell:
    """Reuse a verdict while the cell's files and its attempt count are unchanged."""
    key = [len(attempts), _stat(files.report), _stat(files.steps)]
    entry = cache.get(run_id)
    if isinstance(entry, Mapping) and entry.get("key") == key:
        return WindowCell(**entry["cell"])
    cell = _classify(files, attempts)
    cache[run_id] = {"key": key, "cell": asdict(cell)}
    return cell


def _iso(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, UTC).isoformat()


def check_window(
    output: Path,
    cells: Mapping[str, CellFiles],
    now: datetime,
    *,
    after_stop: bool = False,
    cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pooled counts over the window. See the module docstring for what must stay out of them."""
    results = output / CELL_RESULTS_FILE
    attempts_by_cell = read_cell_results(results)
    if set(attempts_by_cell) - set(cells):
        raise ValueError(f"{CELL_RESULTS_FILE} names cells the registration does not plan")
    window_start = now - WINDOW
    cache = {} if cache is None else cache
    states: Counter[str] = Counter()
    categories: dict[str, list[float]] = {}
    watchdog = running = 0
    for run_id, attempts in attempts_by_cell.items():
        ended = attempts[-1].ended
        if ended is None:
            running += 1
            continue
        clocks = ended.get("clocks")
        stamp = clocks.get("realtime") if isinstance(clocks, Mapping) else None
        if not isinstance(stamp, int | float):
            raise ValueError(f"an end line in {CELL_RESULTS_FILE} has no realtime clock")
        if not window_start.timestamp() <= stamp <= now.timestamp():
            continue
        cell = _cached_classify(run_id, cells[run_id], attempts, cache)
        states[cell.state] += 1
        watchdog += cell.watchdog and cell.state == ABORT_FINAL
        if cell.state == ABORT_FINAL:
            categories.setdefault(cell.category or "unknown", []).append(stamp)
        elif cell.state in (NO_RECORD, RECORD_INCONSISTENT):
            categories.setdefault(cell.state, []).append(stamp)
    awaiting_retry = states[UNATTEMPTED]
    abort = states[ABORT_FINAL] + states[NO_RECORD]
    ended_cells = states[COMPLETE] + abort + states[RECORD_INCONSISTENT]
    failed = abort + states[RECORD_INCONSISTENT]
    rate = failed / ended_cells if ended_cells else None
    enough = ended_cells >= MIN_ENDED_CELLS
    report: dict[str, Any] = {
        "classification": "operating check: counts only, no automatic stop",
        "now": now.astimezone(UTC).isoformat(),
        "window_start": window_start.astimezone(UTC).isoformat(),
        "ended_cells": ended_cells,
        "complete": states[COMPLETE],
        "abort": abort,
        "abort_watchdog": watchdog,
        "no_record": states[NO_RECORD],
        "record_inconsistent": states[RECORD_INCONSISTENT],
        "infrastructure_failure_rate": rate,
        "min_ended_cells_met": enough,
        "stop_rate_reached": enough and rate is not None and rate >= STOP_RATE,
        "running_cells": running,
        "awaiting_retry": awaiting_retry,
        "infrastructure_stopped": infrastructure_stopped(read_infrastructure_events(results)),
    }
    if after_stop:
        report["after_stop"] = {
            category: {"total": len(stamps), "end_times": [_iso(s) for s in sorted(stamps)]}
            for category, stamps in sorted(categories.items())
        }
    return report


def _plan_cells(preregistration: Path, output: Path) -> dict[str, CellFiles]:
    prereg = load_preregistration(preregistration)
    if not prereg.targets:
        raise ValueError("this check reads the exit record of a targets.<id> registration")
    plan = Exp0Plan(
        prereg,
        preregistration,
        sha256(preregistration.read_bytes()).hexdigest(),
        DEFAULT_VERSION,  # unused by a targets registration, which names its versions
        RdsArm.S_A in prereg.arm_policies,
    )
    cells = {}
    for cell in plan.cells():
        paths = cell_paths(cell, output)
        cells[cell.run_id] = CellFiles(paths["report"], paths["steps_jsonl"], cell.budget)
    return cells


def _write_problem(path: Path, run_dir: Path) -> str | None:
    """A file this tool writes stays out of the evidence, the repository and the run directory."""
    repo_root = Path(__file__).resolve().parents[1]
    problem = output_problem(path, repo_root, Path.home())
    resolved, run = path.expanduser().resolve(), run_dir.expanduser().resolve()
    if problem is None and (resolved == run or run in resolved.parents):
        problem = f"must be outside the run directory ({run})"
    return problem


def _load_cache(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="the run's output directory")
    parser.add_argument("--after-stop", action="store_true", help="only after a stop was called")
    parser.add_argument("--out", type=Path, help="also write the result here")
    parser.add_argument("--cache", type=Path, help="verdicts by file size and time, for reruns")
    args = parser.parse_args(argv)
    for path in (args.out, args.cache):
        problem = None if path is None else _write_problem(path, args.output)
        if problem is not None:
            print(f"{path}: {problem}", file=sys.stderr)
            return 2
    os.nice(19)  # this runs on the measured host
    cache = _load_cache(args.cache)
    try:
        cells = _plan_cells(args.preregistration, args.output)
        report = check_window(
            args.output, cells, datetime.now(UTC), after_stop=args.after_stop, cache=cache
        )
    except (PreregistrationFormatError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    sys.stdout.write(text)
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
    if args.cache is not None:
        args.cache.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

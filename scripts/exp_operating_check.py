"""The operating-stop check W2 runs during EXP-3 and EXP-2. It shows counts and never stops a run.

D041: over the last 24 hours, with at least 20 ended cells, the infrastructure failure rate
(aborts + inconsistent records, over ended cells) reaches .60. The decision stays with people: this
tool prints, and stopping or resuming follows the registered rule and W3.

The run is still sealed, so the output is pooled counts and clock values. No run id, arm, seed, step
or case id goes to the output, and the rule looks at no arm. Files it reads:

* ``cell-results.jsonl``, for every cell;
* for a cell ended in the window, the ``index`` of each step line and whether its report exists;
* for a cell with a nonzero exit, its report, for the abort stub.

A cell that exited 0 needs a report file to exist, but its contents are never read. The launcher
checks the report fully at ``finish``. Oracle values are never kept.

``--after-stop`` is for after a stop has really been called, and its use goes in ``docs/LOG.md``. It
adds reason category totals and the first/last end time, still without a cell's name.

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
CACHE_KEY_PREFIX = "sha256:"


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
        whole = files.report.is_file() and scan.indexes == tuple(range(files.budget))
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
    """Reuse a verdict without storing a reversible cell identifier in the cache."""
    key = [len(attempts), _stat(files.report), _stat(files.steps)]
    cache_key = (
        CACHE_KEY_PREFIX
        + sha256(b"inodefence-operating-check-v2\0" + run_id.encode("utf-8")).hexdigest()
    )
    entry = cache.get(cache_key)
    if isinstance(entry, Mapping) and entry.get("key") == key:
        return WindowCell(**entry["cell"])
    cell = _classify(files, attempts)
    cache[cache_key] = {"key": key, "cell": asdict(cell)}
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
            category: {
                "total": len(stamps),
                "first_end_time": _iso(min(stamps)),
                "last_end_time": _iso(max(stamps)),
            }
            for category, stamps in sorted(categories.items())
        }
    return report


POOLED_COUNTS = (
    "ended_cells",
    "complete",
    "abort",
    "abort_watchdog",
    "no_record",
    "record_inconsistent",
    "running_cells",
    "awaiting_retry",
)


def _last_realtime(output: Path) -> float | None:
    """The last whole line's realtime stamp in a host's exit record (clock reference only)."""
    path = output / CELL_RESULTS_FILE
    if not path.is_file():
        return None
    last = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            clocks = json.loads(line).get("clocks")
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(clocks, Mapping) and isinstance(clocks.get("realtime"), int | float):
            last = float(clocks["realtime"])
    return last


def _excluded_hosts(go_decision: Path | None) -> tuple[str, ...]:
    if go_decision is None:
        return ()
    listed = json.loads(go_decision.read_text(encoding="utf-8")).get("excluded_hosts") or []
    return tuple(str(host) for host in listed)


def pool_hosts(
    reports: Mapping[str, Mapping[str, Any]],
    outputs: Mapping[str, Path],
    now: datetime,
    excluded: Sequence[str] = (),
) -> dict[str, Any]:
    """Two hosts as one run (the D041 rule), plus a per-host alarm line; nothing stops a run.

    The pooled counts are sums and the rate is recomputed from them. A host whose own counts meet
    the same condition gets an alarm line, because the pool can hide one host failing outright.
    Each host's last stamp against this checker's clock is shown as a reference, never used.
    A host the partial GO excluded (``excluded``, D047 section 9.1) stays in the pooled counts,
    since its attempted cells stay in the abort denominator; it is marked, and it gets no alarm
    line because it runs no further cell.
    """
    pooled: dict[str, Any] = {
        key: sum(int(r[key]) for r in reports.values()) for key in POOLED_COUNTS
    }
    failed = pooled["abort"] + pooled["record_inconsistent"]
    rate = failed / pooled["ended_cells"] if pooled["ended_cells"] else None
    enough = pooled["ended_cells"] >= MIN_ENDED_CELLS
    first = next(iter(reports.values()))
    report: dict[str, Any] = {
        "classification": first["classification"],
        "now": first["now"],
        "window_start": first["window_start"],
        **pooled,
        "infrastructure_failure_rate": rate,
        "min_ended_cells_met": enough,
        "stop_rate_reached": enough and rate is not None and rate >= STOP_RATE,
        "infrastructure_stopped": any(r["infrastructure_stopped"] for r in reports.values()),
        "hosts": {
            host: {
                "ended_cells": r["ended_cells"],
                "infrastructure_failure_rate": r["infrastructure_failure_rate"],
                "condition_met": bool(r["stop_rate_reached"]),
                "infrastructure_stopped": r["infrastructure_stopped"],
                **({"excluded_by_partial_go": True} if host in excluded else {}),
            }
            for host, r in sorted(reports.items())
        },
        "host_alarms": [
            f"경보: {host} 단독으로 종료 셀 {r['ended_cells']} ≥ {MIN_ENDED_CELLS}, "
            f"실패율 {r['infrastructure_failure_rate']:.2f} ≥ {STOP_RATE:.2f} "
            "(자동 정지 아님, 지웅 결정)"
            for host, r in sorted(reports.items())
            if r["stop_rate_reached"] and host not in excluded
        ],
        "clock_reference": {
            host: {
                "last_realtime": None
                if (last := _last_realtime(outputs[host])) is None
                else _iso(last),
                "checker_now_minus_last_seconds": None
                if last is None
                else round(now.timestamp() - last, 3),
            }
            for host in sorted(reports)
        },
    }
    if all("after_stop" in r for r in reports.values()):
        categories: dict[str, dict[str, Any]] = {}
        for r in reports.values():
            for category, value in r["after_stop"].items():
                merged = categories.setdefault(category, {"total": 0})
                merged["total"] += value["total"]
                for key, pick in (("first_end_time", min), ("last_end_time", max)):
                    merged[key] = pick(filter(None, (merged.get(key), value[key])))
        report["after_stop"] = dict(sorted(categories.items()))
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
    if not isinstance(data, dict):
        return {}
    # Drop legacy plaintext run_id keys when rewriting a pre-fix cache file.
    return {
        key: value
        for key, value in data.items()
        if isinstance(key, str)
        and key.startswith(CACHE_KEY_PREFIX)
        and len(key) == len(CACHE_KEY_PREFIX) + 64
        and all(digit in "0123456789abcdef" for digit in key[len(CACHE_KEY_PREFIX) :])
        and isinstance(value, dict)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="the run's output directory")
    parser.add_argument(
        "--host-output",
        action="append",
        default=[],
        metavar="HOST=DIR",
        help="two-host run: each host's output directory (replaces --output)",
    )
    parser.add_argument("--after-stop", action="store_true", help="only after a stop was called")
    parser.add_argument(
        "--go-decision",
        type=Path,
        help="two-host run after GO: mark the hosts the partial GO excluded (D047 section 9.1)",
    )
    parser.add_argument("--out", type=Path, help="also write the result here")
    parser.add_argument("--cache", type=Path, help="verdicts by file size and time, for reruns")
    args = parser.parse_args(argv)
    outputs: dict[str, Path] = {}
    for item in args.host_output:
        host, sep, path = item.partition("=")
        if not sep or not host or not path or host in outputs:
            parser.error(f"--host-output expects HOST=DIR once per host, got {item!r}")
        outputs[host] = Path(path)
    if (args.output is None) == (not outputs):
        parser.error("give --output, or --host-output for each host, not both")
    run_dirs = [args.output] if args.output is not None else list(outputs.values())
    for path in (args.out, args.cache):
        for run_dir in run_dirs:
            problem = None if path is None else _write_problem(path, run_dir)
            if problem is not None:
                print(f"{path}: {problem}", file=sys.stderr)
                return 2
    os.nice(19)  # this runs on the measured host
    cache = _load_cache(args.cache)
    try:
        now = datetime.now(UTC)
        if args.output is not None:
            cells = _plan_cells(args.preregistration, args.output)
            report = check_window(args.output, cells, now, after_stop=args.after_stop, cache=cache)
        else:
            report = pool_hosts(
                {
                    host: check_window(
                        output,
                        _plan_cells(args.preregistration, output),
                        now,
                        after_stop=args.after_stop,
                        cache=cache,
                    )
                    for host, output in outputs.items()
                },
                outputs,
                now,
                _excluded_hosts(args.go_decision),
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

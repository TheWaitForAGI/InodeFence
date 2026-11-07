"""Whether a cell's record is whole, for registrations in the ``targets.<id>`` form.

A record found on disk is final: it is never re-run, because a record can be read and replacing it
would let the results choose which runs count. So an abort record must not be taken at face value,
and this module separates the records that hold together from those that do not.

Reads the launcher's exit record (``cell-results.jsonl``), the report's structure and each step's
``index``. It never reads an oracle value, so the classification cannot follow the outcomes. Nothing
on the cell execution path imports this module.

States:

* ``complete``: every planned step, no abort, exit code 0, the planned configuration.
* ``abort-final``: an abort record that holds together. Either the report's ``aborted`` stub agrees
  with the steps and a nonzero exit, or the launcher's watchdog ended the cell (see below).
* ``record-inconsistent``: a record exists but fails a check. It is not re-run and leaves the
  analysis per contrast, like an invalid cell.
* ``unattempted``: no record, attempts left.
* ``no-record``: no record, attempts used up. It counts as an abort.

The watchdog is known only from ``watchdog_fired`` in the exit record. Exit code -15 is the same as
an outside SIGTERM and log lines are not conditions. A watchdog cell usually has no report, and its
last line may be cut: only that one unparsable last line is forgiven, as a step of unknown outcome.
A cut line alone, with no whole line, is no record for a watchdog cell and inconsistent otherwise.
With a report, a watchdog cell takes the ordinary checks and keeps its watchdog mark.
"""

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

CELL_RESULTS_FILE = "cell-results.jsonl"
COMPLETE = "complete"
ABORT_FINAL = "abort-final"
RECORD_INCONSISTENT = "record-inconsistent"
UNATTEMPTED = "unattempted"
NO_RECORD = "no-record"
CELL_STATES = (COMPLETE, ABORT_FINAL, RECORD_INCONSISTENT, UNATTEMPTED, NO_RECORD)
# One first attempt and one retry. A start with no record counts, so a launcher that keeps dying
# cannot retry for ever.
MAX_ATTEMPTS = 2
# Consecutive cells ending with no record point at the infrastructure, not at the cells: without a
# stop, a dead Docker would use up every waiting cell's attempts within minutes (same as the pilot).
STOP_AFTER_NO_RECORD = 3
INFRASTRUCTURE_STOP_EVENT = "infrastructure-stop"
INFRASTRUCTURE_RESUME_EVENT = "infrastructure-resume"
WATCHDOG_ABORT_REASON = "campaign watchdog terminated the cell"


@dataclass(frozen=True, slots=True)
class Attempt:
    """One launcher attempt at a cell: its ``start`` line and its ``end`` line, if it wrote one."""

    number: int
    started: Mapping[str, Any]
    ended: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class StepScan:
    """What a steps file holds, by step index only."""

    indexes: tuple[object, ...] = ()
    torn_last_line: bool = False
    torn_inner_line: bool = False


@dataclass(frozen=True, slots=True)
class CellCheck:
    state: str
    problems: tuple[str, ...] = ()
    watchdog: bool = False
    unknown_outcome_steps: int = 0
    step_count: int = 0


def read_cell_results(path: Path) -> dict[str, tuple[Attempt, ...]]:
    """Attempts per run id. A line that does not parse is skipped: its cell then misses a record."""
    if not path.is_file():
        return {}
    starts: dict[str, dict[int, Mapping[str, Any]]] = {}
    ends: dict[tuple[str, int], Mapping[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, Mapping):
            continue
        run_id, attempt = record.get("run_id"), record.get("attempt")
        if not isinstance(run_id, str) or not isinstance(attempt, int):
            continue
        if record.get("event") == "start":
            starts.setdefault(run_id, {})[attempt] = record
        elif record.get("event") == "end":
            ends[(run_id, attempt)] = record
    return {
        run_id: tuple(
            Attempt(number, by_number[number], ends.get((run_id, number)))
            for number in sorted(by_number)
        )
        for run_id, by_number in starts.items()
    }


def scan_steps(path: Path) -> StepScan:
    """Step indexes of a steps file, line by line. Only the ``index`` of each record is kept."""
    if not path.is_file():
        return StepScan()
    indexes: list[object] = []
    torn_positions: list[int] = []
    count = 0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                torn_positions.append(count)
            else:
                indexes.append(record.get("index") if isinstance(record, Mapping) else None)
            count += 1
    torn_last = bool(torn_positions) and torn_positions[-1] == count - 1
    return StepScan(tuple(indexes), torn_last, len(torn_positions) > int(torn_last))


def _report_problems(
    report: Mapping[str, Any],
    scan: StepScan,
    returncode: object,
    budget: int,
    complete_and_conformant: bool,
) -> list[str]:
    problems: list[str] = []
    steps = report.get("steps")
    if isinstance(steps, list):
        expected = [step.get("index") if isinstance(step, Mapping) else None for step in steps]
        if list(scan.indexes) != expected[: len(scan.indexes)]:
            problems.append("steps-not-a-prefix-of-the-report")
    aborted = report.get("aborted")
    if isinstance(aborted, Mapping):
        if aborted.get("step_index") != len(scan.indexes):
            problems.append("abort-step-index-differs-from-the-record-count")
        if returncode == 0:
            problems.append("abort-with-exit-code-zero")
        if not aborted.get("reason"):
            problems.append("abort-without-a-reason")
        return problems
    if not complete_and_conformant:
        problems.append("report-incomplete-without-an-abort-record")
    if returncode is not None and returncode != 0:  # None: already reported as a missing record
        problems.append("complete-report-with-a-nonzero-exit")
    if len(scan.indexes) != budget:
        problems.append("steps-file-does-not-reach-the-budget")
    return problems


def classify_cell(
    *,
    report_path: Path,
    steps_path: Path,
    budget: int,
    attempts: Sequence[Attempt],
    complete_and_conformant: bool,
) -> CellCheck:
    """Classify one cell from its files and its exit record. See the module docstring."""
    scan = scan_steps(steps_path)
    count = len(scan.indexes)
    has_report = report_path.is_file()
    ended = attempts[-1].ended if attempts else None
    watchdog = ended is not None and ended.get("watchdog_fired") is True
    # No whole line is no record, unless a cut line shows a run the watchdog does not explain.
    only_a_watchdog_cut = scan.torn_last_line and not scan.torn_inner_line and watchdog
    if not has_report and not count and (not scan.torn_last_line or only_a_watchdog_cut):
        return CellCheck(UNATTEMPTED if len(attempts) < MAX_ATTEMPTS else NO_RECORD)
    problems: list[str] = []
    if ended is None:
        problems.append("no-exit-record")
    elif not isinstance(ended.get("returncode"), int):
        problems.append("exit-record-without-an-exit-code")
    if scan.indexes != tuple(range(count)):
        problems.append("step-indexes-not-contiguous")
    if scan.torn_inner_line:
        problems.append("unparsable-line-inside-the-steps-file")
    if watchdog and not has_report:
        unknown = int(scan.torn_last_line)
        if problems:
            return CellCheck(RECORD_INCONSISTENT, tuple(problems), True, unknown, count)
        return CellCheck(ABORT_FINAL, (), True, unknown, count)
    if scan.torn_last_line:
        problems.append("unparsable-last-line-without-the-watchdog")
    if not has_report:
        problems.append("no-report-and-no-watchdog")
    else:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            problems.append("report-unreadable")
        else:
            if isinstance(report, Mapping):
                problems += _report_problems(
                    report,
                    scan,
                    ended.get("returncode") if ended is not None else None,
                    budget,
                    complete_and_conformant,
                )
            else:
                problems.append("report-is-not-an-object")
    if problems:
        return CellCheck(RECORD_INCONSISTENT, tuple(problems), watchdog, 0, count)
    state = COMPLETE if complete_and_conformant else ABORT_FINAL
    return CellCheck(state, (), watchdog, 0, count)


class InfrastructureGuard:
    """Stops new cells after ``STOP_AFTER_NO_RECORD`` consecutive cells with no record.

    It reads no outcome, only whether a cell left a record. The rules are fixed here:

    * **What counts:** a cell, once, when it ends with no record after its last attempt. A failed
      attempt that is retried does not count.
    * **Order:** the order in which cells end, as the launcher notes them under this lock. Not the
      order they started and not the planned order, so with several jobs the count follows the
      infrastructure's state over time.
    * **Reset:** any cell that leaves a record sets the count to 0, whatever the record says
      (complete, abort or inconsistent). A cell not started changes nothing.
    * **Scope:** one launcher call, starting at 0. A resume is a new call and starts at 0.
    * **After the stop:** no new attempt starts, retries included. Running cells finish and keep
      their records; nothing is deleted or overwritten. A cell ending after the stop does not undo
      it. A later call refuses to start cells until an operator resumes with an approval reference
      (``--resume-after-stop``). Nothing resumes by itself.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._streak = 0
        self.stopped = False

    def note_cell_end(self, *, recorded: bool) -> str | None:
        """Note one ended cell. Returns the stop reason once, when this end triggers the stop."""
        with self._lock:
            self._streak = 0 if recorded else self._streak + 1
            if self.stopped or self._streak < STOP_AFTER_NO_RECORD:
                return None
            self.stopped = True
        return (
            f"{STOP_AFTER_NO_RECORD} consecutive cells left no record; "
            "infrastructure suspected, no new cell started"
        )


def read_infrastructure_events(path: Path) -> list[dict[str, Any]]:
    """The launcher's stop and resume lines, in file order."""
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("event") in (
            INFRASTRUCTURE_STOP_EVENT,
            INFRASTRUCTURE_RESUME_EVENT,
        ):
            events.append(record)
    return events


def infrastructure_stopped(events: Sequence[Mapping[str, Any]]) -> bool:
    """Whether the last stop has not been resumed."""
    return bool(events) and events[-1].get("event") == INFRASTRUCTURE_STOP_EVENT


def infrastructure_summary(
    checks: Mapping[str, CellCheck], events: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """Counts and the infrastructure failure rate: (aborts + inconsistent records) / all cells.

    A no-record cell counts as an abort and is also shown alone. Both the abort count and the sum
    are given, because the D040-D11 GO input and the operating stop use the sum.
    """
    states = Counter(check.state for check in checks.values())
    aborts = states[ABORT_FINAL] + states[NO_RECORD]
    failures = aborts + states[RECORD_INCONSISTENT]
    return {
        "cells": len(checks),
        "complete": states[COMPLETE],
        "aborts": aborts,
        "watchdog": sum(check.watchdog and check.state == ABORT_FINAL for check in checks.values()),
        "no_record": states[NO_RECORD],
        "record_inconsistent": states[RECORD_INCONSISTENT],
        "unattempted": states[UNATTEMPTED],
        "aborts_plus_inconsistent": failures,
        "infrastructure_failure_rate": failures / len(checks) if checks else None,
        "unknown_outcome_steps": sum(check.unknown_outcome_steps for check in checks.values()),
        # Every attempted cell's whole step lines, invalid cells too (the GO step ratio).
        "recorded_steps": sum(check.step_count for check in checks.values()),
        "infrastructure_stopped": infrastructure_stopped(events),
        "infrastructure_stops": [
            {"reason": event.get("reason"), "clocks": event.get("clocks")}
            for event in events
            if event.get("event") == INFRASTRUCTURE_STOP_EVENT
        ],
        "infrastructure_resumes": [
            {"approval_ref": event.get("approval_ref"), "clocks": event.get("clocks")}
            for event in events
            if event.get("event") == INFRASTRUCTURE_RESUME_EVENT
        ],
        "inconsistent_checks": {
            run_id: list(check.problems)
            for run_id, check in sorted(checks.items())
            if check.state == RECORD_INCONSISTENT
        },
    }

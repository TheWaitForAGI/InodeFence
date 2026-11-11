"""Analysis and decision of the concurrency scaling benchmark (``concurrency-scaling-v1``).

Reads a benchmark output tree and writes ``concurrency-report.json`` and ``.md``. The report ends
in a mechanical decision (design file, section 6): a selected concurrency level, a stage whose
measurement an external stop voided, or a stop condition H1, H2, H3, H3-unmeasured or H5, plus the
H4 count.

Sealed raw: no oracle value leaves this script. To compare paths between blocks, each step's
oracle verdict and fed-back keys are reduced to an in-memory hash. The one thing the decision takes
from that hash is whether it differs, which counts toward a block's path differences (m). A pure
verdict difference is otherwise reported only as a total per concurrency level, with no arm or seed.

Terms:

* normal campaign: return code 0, a report without an abort record, every planned step present,
  the planned config and image, a steps file that matches the report (design file, section 4);
* throughput uses CLOCK_REALTIME, because this host's monotonic clock is not real time. Per-step
  seconds come from the report and stay labelled monotonic;
* X is a block's real-time execution rate while every slot is busy; N is a level's normal fraction
  over all its blocks. A cell whose path first differs at a step that is ``timed_out`` or ``failed``
  on only one side does not count as normal.

Design v3 (``concurrency-scaling-v3``, two hosts): ``--host-output HOST=DIR`` per host. Each host is
decided from its own tree by the same procedure, with V10' (both clocks) and V7' (timed-out steps
plus infrastructure re-executions) in place of V10 and V7; then X1 (cross-host path agreement, not
a jobs exclusion), H2' (H2 on one host halts all) and the engine and host identity checks are
added, and a combined summary is written. A v2 design's output is unchanged byte for byte.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.check_native_determinism import subject_from_report
from scripts.run_concurrency_benchmark import (
    BLOCK_FILE,
    INCOMPLETE_BLOCK_FILE,
    REPORT_JSON,
    SMOKE_STAGE,
    STOP_EXTERNAL,
    Design,
    load_design,
    measured_stages,
    planned_cells,
    planned_stop,
)

from inodefence.evaluation.abort_classification import InvalidReason, classify_abort_reason
from inodefence.evaluation.independence import arm_abort_independence
from inodefence.evaluation.rds_report import LoadedCell, ReportFormatError, load_cell_files

LABEL = "demo run; concurrency benchmark (unregistered, not pooled, oracle sealed)"
REPORT_MD = "concurrency-report.md"
CLEANUP_CATEGORIES = frozenset({InvalidReason.CLEANUP_INSPECT, InvalidReason.CLEANUP_REMOVE})
_FAILED_STEP = re.compile(r"FAILED at step: (.+?) \(exit")
#: Target outcomes that can be congestion rather than the input (first-difference check).
CONGESTION_TERMINATIONS = frozenset({"timed_out", "failed"})
REASON_LIMIT = 500
ABNORMAL_DISPOSITIONS = (
    "no-record",
    "incomplete",
    "unreadable",
    "nonconformant",
    "integrity-failure",
)

# The decision thresholds below are the design file's section 6, set by W3 before any run. They
# are judgement values, not measurements.
V2_OTHER_ABNORMAL = 2
V3_ABORT_FRACTION = 0.30
ALPHA = 0.05
V5_ARM_P = 0.10
V6_TARGET_P999_SECONDS = 5.0
V7_TIMED_OUT_PER_1000 = 1.0
V8_RATE_RATIO = 1.25
V8_PER_1000 = 20.0
V9_EXCESS_OVER_FLOOR = 2
V9_ONE_SIDED_CELLS = 2
#: Cells of one block without a path on either side. Fewer differences could only mean less was
#: compared, so this many cannot pass V9 or measure F; one is reported.
UNCOMPARABLE_CELLS = 2
V10_CELL_MONOTONIC_SECONDS = 7200.0
RHO_MIN = 1.15
DRIFT_MAX = 0.15
H3_FLOOR = 3
COINCIDENCE_SECONDS = 60.0


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _rate(count: float, seconds: float) -> float | None:
    return count / seconds * 3600.0 if seconds > 0 else None


def exact_upper_p(events: int, other_events: int, share: float = 0.5) -> float:
    """One-sided exact conditional test: P(X >= events) for X ~ Bin(events + other, share)."""
    total = events + other_events
    return sum(
        math.comb(total, k) * share**k * (1 - share) ** (total - k)
        for k in range(events, total + 1)
    )


def significantly_more(events: int, ref_events: int, share: float = 0.5) -> bool:
    return events > ref_events and exact_upper_p(events, ref_events, share) <= ALPHA


@dataclass(slots=True)
class CellPath:
    """A cell's path. Verdicts are opaque hashes so that no oracle value can leak from here."""

    case_ids: tuple[str, ...]
    terminations: tuple[str, ...]
    verdicts: tuple[int, ...]
    operators: tuple[str | None, ...]


@dataclass(slots=True)
class PathDifference:
    case_sequence_same: bool
    verdicts_same: bool
    first_step: int | None
    terminations: tuple[str, str] | None

    @property
    def differs(self) -> bool:
        return not self.case_sequence_same or not self.verdicts_same or self.first_step is not None

    @property
    def one_sided_congestion(self) -> bool:
        if self.terminations is None:
            return False
        left, right = self.terminations
        return (left in CONGESTION_TERMINATIONS) != (right in CONGESTION_TERMINATIONS)


def cell_path(records: Sequence[Mapping[str, Any]]) -> CellPath | None:
    if not records:
        return None
    try:
        subject = subject_from_report({"steps": [dict(step) for step in records]}, label="cell")
    except (KeyError, TypeError, ValueError):
        return None
    return CellPath(
        tuple(step.case_id for step in subject.steps),
        tuple(str((step.get("feedback") or {}).get("trace_termination")) for step in records),
        tuple(hash((step.oracle, step.feedback_keys)) for step in subject.steps),
        tuple((step.get("mutation_attempt") or {}).get("operator_id") for step in records),
    )


def compare_paths(reference: CellPath, candidate: CellPath) -> PathDifference:
    """Compare the common prefix, so an aborted cell is compared up to its abort."""
    common = min(len(reference.case_ids), len(candidate.case_ids))
    first_step: int | None = None
    terminations: tuple[str, str] | None = None
    for index in range(common):
        same_case = reference.case_ids[index] == candidate.case_ids[index]
        same_end = reference.terminations[index] == candidate.terminations[index]
        if not same_case or not same_end:
            first_step = index
            terminations = (reference.terminations[index], candidate.terminations[index])
            break
    return PathDifference(
        reference.case_ids[:common] == candidate.case_ids[:common],
        reference.verdicts[:common] == candidate.verdicts[:common],
        first_step,
        terminations,
    )


def _harness_step(log: Path) -> str | None:
    """The harness step a nonzero cell failed in, from the smoke script's own log line."""
    if not log.is_file():
        return None
    found = _FAILED_STEP.findall(log.read_text(encoding="utf-8", errors="replace"))
    return found[-1] if found else None


def _steps_match_report(loaded: LoadedCell, steps_path: Path) -> bool:
    """The steps file is a prefix of the report's steps, by index and case id."""
    if loaded.steps_from != "report":
        return True
    if not steps_path.is_file():
        return False
    lines = [line for line in steps_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) > len(loaded.records):
        return False
    for line, record in zip(lines, loaded.records, strict=False):
        step = json.loads(line)
        if step.get("index") != record.get("index") or step.get("case_id") != record.get("case_id"):
            return False
    return True


def _nonconformance(report: Mapping[str, Any], cell: Mapping[str, Any], design: Design) -> str:
    config = report.get("config")
    if isinstance(config, Mapping) and (
        config.get("random_seed") != cell["seed"]
        or config.get("execution_budget") != cell["budget"]
    ):
        return "report config differs from the planned cell"
    if report.get("image_id") != design.image_digest:
        return f"report image_id is {report.get('image_id')}"
    sentinels = report.get("sentinel_set")
    if not isinstance(sentinels, Mapping) or sentinels.get("count") != design.sentinel_count:
        count = sentinels.get("count") if isinstance(sentinels, Mapping) else None
        return f"report sentinel count is {count}"
    return ""


def first_error(aborted: Mapping[str, Any] | None) -> dict[str, Any]:
    """Whether an abort's first error is known (H4).

    Unconfirmed only when a failure could still be hiding: no abort record, a truncated chain, or
    a cleanup reason with no chain. A whole chain is confirmed even if it ends in a cleanup error:
    a replaced error would be further along it, so that cleanup error really came first. A null
    chain with a non-cleanup reason comes from a raise that replaces nothing (evidence integrity,
    image version), so it is confirmed too.
    """
    if aborted is None:
        return {"status": "unconfirmed", "type": None, "message": None, "frames": None}
    chain = aborted.get("error_chain")
    reason = str(aborted.get("reason") or "")
    if isinstance(chain, list) and chain:
        last = chain[-1]
        if not isinstance(last, Mapping) or last.get("truncated"):
            return {"status": "unconfirmed", "type": None, "message": None, "frames": None}
        return {
            "status": "confirmed",
            "type": last.get("type"),
            "message": str(last.get("message") or "")[:REASON_LIMIT],
            # For a person to read which call site this was; no rule uses it.
            "frames": last.get("frames"),
        }
    cleanup = classify_abort_reason(reason) in CLEANUP_CATEGORIES
    return {
        "status": "unconfirmed" if cleanup else "confirmed",
        "type": None,
        "message": reason[:REASON_LIMIT],
        "frames": None,
    }


@dataclass(slots=True)
class CellData:
    summary: dict[str, Any]
    path: CellPath | None = None
    target_seconds: list[float] = field(default_factory=list)


#: The clocks of a ``clock_stamp`` record that the v3 dual-clock rule V10' reads.
V10_CLOCKS = ("monotonic", "realtime")


def _stamp(record: Mapping[str, Any], side: str, clock: str) -> float | None:
    """One clock reading of a cell or block record (v3); None when absent or not a number."""
    stamps = record.get(side)
    value = stamps.get(clock) if isinstance(stamps, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def _span(record: Mapping[str, Any], clock: str) -> float | None:
    started, ended = _stamp(record, "started", clock), _stamp(record, "ended", clock)
    return ended - started if started is not None and ended is not None else None


def infra_reexecution_count(report: Mapping[str, Any] | None) -> int | None:
    """Infrastructure re-executions (discarded attempts) of one cell, design v3.

    A report column, and part of V7''s numerator. An abort stub's ``infra_reexecution_count``
    first; otherwise the length of the report's ``infra_reexecutions`` list, whose absence means
    no stall (0). None when there is no report or the value is malformed. Only the count leaves
    this function, never an event.
    """
    if report is None:
        return None
    aborted = report.get("aborted")
    if isinstance(aborted, Mapping) and "infra_reexecution_count" in aborted:
        value = aborted["infra_reexecution_count"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value
    events = report.get("infra_reexecutions")
    if events is None:
        return 0
    if not isinstance(events, list):
        return None
    return len(events)


def _abort_record(
    aborted: Mapping[str, Any] | None, records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    reason = str(aborted.get("reason")) if aborted is not None else "no report written"
    shape = aborted.get("case_shape") if aborted is not None else None
    step_entries = [
        step["trace"]["entries"]
        for step in records
        if isinstance((step.get("trace") or {}).get("entries"), list)
    ]
    abort_entries = shape.get("entries") if isinstance(shape, Mapping) else None
    abort_types = shape.get("entry_types") if isinstance(shape, Mapping) else None

    def rank(count: object, counts: Sequence[int]) -> float | None:
        if not counts or not isinstance(count, int):
            return None
        return sum(1 for value in counts if value <= count) / len(counts)

    return {
        "step_index": aborted.get("step_index") if aborted is not None else len(records),
        "case_id": aborted.get("case_id") if aborted is not None else None,
        "category": classify_abort_reason(reason).value,
        "first_error": first_error(aborted),
        "reason": reason[:REASON_LIMIT],
        # Bytes are the recorded value only: completed steps do not record content size.
        "case_shape": shape,
        # Case comparison against the same cell's completed steps: entry count and entry types.
        "entries_rank_in_cell": rank(abort_entries, [len(entries) for entries in step_entries]),
        "entry_type_ranks_in_cell": (
            {
                kind: rank(
                    count,
                    [
                        sum(1 for entry in entries if entry.get("type") == kind)
                        for entries in step_entries
                    ],
                )
                for kind, count in abort_types.items()
            }
            if isinstance(abort_types, Mapping)
            else None
        ),
        "operator_from_other_block": None,
    }


def summarize_cell(cell: Mapping[str, Any], raw: Path, design: Design) -> CellData:
    """One cell's facts and path. No oracle field is copied into the summary.

    Design v3 reads the clock stamps leniently: a missing one leaves that clock's seconds None (not
    measurable), which V10' then counts against the arm. A v2 design reads them exactly as before.
    """
    budget = cell["budget"]
    if design.is_v3:
        clocks: dict[str, Any] = {
            "started_real": _stamp(cell, "started", "realtime"),
            "ended_real": _stamp(cell, "ended", "realtime"),
            "real_seconds": _span(cell, "realtime"),
            "monotonic_seconds": _span(cell, "monotonic"),
        }
    else:
        clocks = {
            "started_real": cell["started"]["realtime"],
            "ended_real": cell["ended"]["realtime"],
            "real_seconds": cell["ended"]["realtime"] - cell["started"]["realtime"],
            "monotonic_seconds": cell["ended"]["monotonic"] - cell["started"]["monotonic"],
        }
    summary: dict[str, Any] = {
        "run_id": cell["run_id"],
        "arm": cell["arm"],
        "seed": cell["seed"],
        "returncode": cell["returncode"],
        "watchdog_killed": cell["watchdog_killed"],
        **clocks,
        "harness_failed_step": _harness_step(raw / cell["log"]),
        "executions": 0,
        "exposure": 0.0,
        "abort": None,
        "terminations": {},
        "ineligible_steps": 0,
        "failure_kinds": {},
        "integrity_problem": None,
    }
    if design.is_v3:
        summary["clock_unmeasured"] = [
            clock
            for clock, key in zip(V10_CLOCKS, ("monotonic_seconds", "real_seconds"), strict=True)
            if summary[key] is None
        ]
        summary["infra_reexecutions"] = None
        summary["infra_reexecutions_malformed"] = False
    data = CellData(summary)
    report_path, steps_path = raw / cell["report"], raw / cell["steps"]
    if not report_path.is_file() and not steps_path.is_file():
        summary["disposition"] = "no-record"
        return data
    try:
        loaded = load_cell_files(report_path, steps_path)
    except (ReportFormatError, ValueError, OSError) as error:
        summary["disposition"] = "unreadable"
        summary["integrity_problem"] = str(error)[:REASON_LIMIT]
        return data
    if design.is_v3:
        summary["infra_reexecutions"] = infra_reexecution_count(loaded.report)
        # A report whose count cannot be read: V7' cannot be measured for this cell.
        summary["infra_reexecutions_malformed"] = (
            loaded.report is not None and summary["infra_reexecutions"] is None
        )
    records = loaded.records
    data.path = cell_path(records)
    summary["executions"] = len(records)
    summary["exposure"] = len(records) / budget if budget else 0.0
    summary["terminations"] = dict(
        Counter(str((step.get("feedback") or {}).get("trace_termination")) for step in records)
    )
    summary["ineligible_steps"] = sum(
        1 for step in records if (step.get("feedback") or {}).get("feedback_eligible") is False
    )
    kinds: Counter[str] = Counter()
    for step in records:
        for failure in (step.get("trace") or {}).get("observation_failures") or ():
            kinds[str(failure.get("kind") if isinstance(failure, Mapping) else failure)] += 1
    summary["failure_kinds"] = dict(kinds)
    report = loaded.report
    timing = report.get("timing") if report else None
    per_case = timing.get("per_case") if isinstance(timing, Mapping) else None
    if isinstance(per_case, list):
        data.target_seconds = [float(item["target_seconds"]) for item in per_case]
    if loaded.aborted_at_step is not None:
        aborted = report.get("aborted") if report else None
        summary["disposition"] = "abort"
        summary["abort"] = _abort_record(aborted if isinstance(aborted, Mapping) else None, records)
        return data
    assert report is not None
    problem = _nonconformance(report, cell, design)
    if problem:
        summary["disposition"] = "nonconformant"
        summary["integrity_problem"] = problem
        return data
    if not _steps_match_report(loaded, steps_path):
        summary["disposition"] = "integrity-failure"
        summary["integrity_problem"] = "steps file is not a prefix of the report steps"
        return data
    summary["disposition"] = (
        "normal" if cell["returncode"] == 0 and len(records) == budget else "incomplete"
    )
    return data


def saturated_exec_per_hour(cells: Sequence[Mapping[str, Any]], jobs: int) -> float | None:
    """Real-time execution rate while every slot is busy.

    The window ends when the first slot has nothing left to start: the (N - jobs + 1)th cell end.
    Each cell's executions are spread evenly over its real duration. Without this, a batch that
    does not divide by ``jobs`` would count its tail, where fewer cells share the host and run
    faster.
    """
    if not cells:
        return None
    # Design v3 only: a cell without real-time stamps leaves X unmeasured, so no gain is shown.
    if any(cell["started_real"] is None or cell["ended_real"] is None for cell in cells):
        return None
    start = min(cell["started_real"] for cell in cells)
    ends = sorted(cell["ended_real"] for cell in cells)
    end = ends[max(0, len(ends) - jobs)]
    if end <= start:
        return None
    executions = 0.0
    for cell in cells:
        duration = cell["ended_real"] - cell["started_real"]
        overlap = min(cell["ended_real"], end) - max(cell["started_real"], start)
        if duration > 0 and overlap > 0:
            executions += cell["executions"] * overlap / duration
    return _rate(executions, end - start)


def lifecycle_seconds(lines: Iterable[str]) -> dict[str, dict[str, float | int | None]]:
    """create->start, start->die, die->destroy seconds per container class, on the daemon clock."""
    moments: dict[str, dict[str, int]] = defaultdict(dict)
    names: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        identity = event.get("id") or event.get("ID")
        action = event.get("Action") or event.get("status")
        stamp = event.get("timeNano")
        if not identity or not action or stamp is None:
            continue
        moments[identity].setdefault(action, int(stamp))
        attributes = (event.get("Actor") or {}).get("Attributes") or {}
        if "name" in attributes:
            names[identity] = attributes["name"]
    spans: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for identity, seen in moments.items():
        kind = "controller" if "controller" in names.get(identity, "") else "target"
        for span, first, second in (
            ("create_to_start", "create", "start"),
            ("start_to_die", "start", "die"),
            ("die_to_destroy", "die", "destroy"),
        ):
            if first in seen and second in seen:
                spans[kind][span].append((seen[second] - seen[first]) / 1e9)
    return {
        f"{kind}.{span}": {
            "count": len(values),
            "p50": _percentile(values, 0.5),
            "p95": _percentile(values, 0.95),
            "max": max(values),
        }
        for kind, by_span in sorted(spans.items())
        for span, values in sorted(by_span.items())
    }


def host_summary(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Peaks and means from the host samples; CPU busy share from the kernel counters."""
    if not samples:
        return {"samples": 0}
    available = [s["memory"]["MemAvailable"] for s in samples if "MemAvailable" in s["memory"]]
    swap = [s["memory"]["SwapTotal"] - s["memory"]["SwapFree"] for s in samples]
    probes = [s["docker_ps_seconds"] for s in samples if "docker_ps_seconds" in s]
    first, last = samples[0]["cpu_jiffies"], samples[-1]["cpu_jiffies"]
    deltas = [after - before for before, after in zip(first, last, strict=False)]
    total = sum(deltas)
    # /proc/stat order: user nice system idle iowait irq softirq steal ...
    return {
        "samples": len(samples),
        "load1_max": max(s["loadavg"][0] for s in samples),
        "cpu_busy_fraction": 1 - (deltas[3] + deltas[4]) / total if total else None,
        "cpu_iowait_fraction": deltas[4] / total if total else None,
        "cpu_system_fraction": deltas[2] / total if total else None,
        "memory_available_min_bytes": min(available) if available else None,
        "swap_used_max_bytes": max(swap),
        "disk_fraction_max": max(s["disk_fraction"] for s in samples),
        "docker_ps_seconds_p50": _percentile(probes, 0.5),
        "docker_ps_seconds_max": max(probes) if probes else None,
        "docker_ps_errors": sum(1 for s in samples if "docker_ps_error" in s),
    }


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def _coincidence(
    cell: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]],
    samples: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """What else happened within the window of this cell's end (input-independent signal)."""
    moment = cell["ended_real"]
    if moment is None:
        # Design v3 only: no real-time end stamp, so nothing can be placed near it.
        return {"other_aborts": None, "docker_ps_errors": None, "docker_ps_seconds_max": None}

    def near(when: float | None) -> bool:
        return when is not None and abs(when - moment) <= COINCIDENCE_SECONDS

    nearby = [s for s in samples if near(s["realtime"])]
    probes = [s["docker_ps_seconds"] for s in nearby if "docker_ps_seconds" in s]
    return {
        "other_aborts": sum(
            1
            for other in cells
            if other is not cell and other["disposition"] == "abort" and near(other["ended_real"])
        ),
        "docker_ps_errors": sum(1 for s in nearby if "docker_ps_error" in s),
        "docker_ps_seconds_max": max(probes) if probes else None,
    }


def summarize_block(
    directory: Path, record: Mapping[str, Any], design: Design
) -> tuple[dict[str, Any], dict[str, CellPath], dict[str, list[float]]]:
    """One block's metrics, cell paths by run id, and target seconds by arm."""
    raw = directory / "raw"
    cells: list[dict[str, Any]] = []
    paths: dict[str, CellPath] = {}
    target_by_arm: dict[str, list[float]] = defaultdict(list)
    not_run = 0
    for cell in record["cells"]:
        if cell["state"] != "ran":
            not_run += 1
            continue
        data = summarize_cell(cell, raw, design)
        cells.append(data.summary)
        target_by_arm[cell["arm"]].extend(data.target_seconds)
        if data.path is not None:
            paths[cell["run_id"]] = data.path
    samples = [json.loads(line) for line in _read_lines(directory / "host" / "samples.jsonl")]
    for cell in cells:
        if cell["abort"] is not None:
            cell["abort"]["coincidence"] = _coincidence(cell, cells, samples)
    real = record["ended"]["realtime"] - record["started"]["realtime"]
    monotonic = record["ended"]["monotonic"] - record["started"]["monotonic"]
    executions = sum(cell["executions"] for cell in cells)
    normal = sum(1 for cell in cells if cell["disposition"] == "normal")
    block = {
        "stage": record["stage"],
        "index": record["index"],
        "jobs": record["jobs"],
        "real_seconds": real,
        "monotonic_over_real": monotonic / real if real > 0 else None,
        "stopped_reason": record.get("stopped_reason"),
        "stop_kind": record.get("stop_kind"),
        "residual_after_block": record.get("residual_after_block"),
        "cells_planned": len(record["cells"]),
        "cells_not_run": not_run,
        "dispositions": dict(Counter(cell["disposition"] for cell in cells)),
        "normal_campaigns": normal,
        "normal_campaigns_per_real_hour": _rate(normal, real),
        "executions": executions,
        "executions_per_real_hour": _rate(executions, real),
        "exposure_per_real_hour": _rate(sum(cell["exposure"] for cell in cells), real),
        "saturated_exec_per_real_hour": saturated_exec_per_hour(cells, record["jobs"]),
        "aborts": [{"run_id": cell["run_id"], **cell["abort"]} for cell in cells if cell["abort"]],
        "watchdog_kills": sum(1 for cell in cells if cell["watchdog_killed"]),
        "harness_failed_steps": dict(
            Counter(cell["harness_failed_step"] for cell in cells if cell["harness_failed_step"])
        ),
        "integrity_problems": {
            cell["run_id"]: cell["integrity_problem"] for cell in cells if cell["integrity_problem"]
        },
        "host": host_summary(samples),
        "lifecycle_seconds": lifecycle_seconds(_read_lines(directory / "host" / "events.jsonl")),
        "cells": cells,
    }
    return block, paths, dict(target_by_arm)


def block_determinism(
    block: Mapping[str, Any],
    paths: Mapping[str, CellPath],
    reference: Mapping[str, CellPath],
    reexecuted: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Differences against the stage's first block. Verdict-only differences carry no identity.

    A cell that cannot be compared is counted, not passed. The two sides are told apart so that a
    loss in the first block does not read as this block's fault.

    ``reexecuted`` (design v3) names the run ids whose cell had an infrastructure re-execution on
    either side; the differences among them are reported as a count and judge nothing.
    """
    arm_by_run = {cell["run_id"]: cell for cell in block["cells"]}
    differing = 0
    verdict_only = 0
    uncomparable = 0
    reference_missing = 0
    block_missing = 0
    by_arm: Counter[str] = Counter()
    first_differences: list[dict[str, Any]] = []
    one_sided: list[str] = []
    differing_reexecuted = 0
    for run_id, cell in arm_by_run.items():
        path = paths.get(run_id)
        base = reference.get(run_id)
        if path is None or base is None:
            uncomparable += 1
            reference_missing += base is None
            block_missing += path is None
            continue
        difference = compare_paths(base, path)
        if not difference.differs:
            continue
        differing += 1
        differing_reexecuted += reexecuted is not None and run_id in reexecuted
        if difference.first_step is None and difference.case_sequence_same:
            verdict_only += 1
            continue
        if not difference.case_sequence_same:
            by_arm[cell["arm"]] += 1
        first_differences.append(
            {
                "run_id": run_id,
                "first_step": difference.first_step,
                "terminations": difference.terminations,
            }
        )
        if difference.one_sided_congestion:
            one_sided.append(run_id)
    result = {
        "m": differing,
        "uncomparable": uncomparable,
        "uncomparable_reference_missing": reference_missing,
        "uncomparable_block_missing": block_missing,
        "case_sequence_by_arm": dict(by_arm),
        "first_differences": first_differences,
        "one_sided_congestion_cells": one_sided,
        "verdict_only_cells": verdict_only,
    }
    if reexecuted is not None:
        result["differing_cells_with_reexecution"] = differing_reexecuted
    return result


def fill_abort_operators(
    blocks: Sequence[Mapping[str, Any]], paths_by_block: Sequence[Mapping[str, CellPath]]
) -> None:
    """Use the blocks that passed an aborted case: its operator, and how often it passed.

    The aborted step left no record, but another block that completed the same step did. The
    number of such passes is the denominator of "no recurrence".
    """
    for block in blocks:
        for cell in block["cells"]:
            abort = cell["abort"]
            if abort is None:
                continue
            abort["passes_elsewhere"] = 0
            if not isinstance(abort["step_index"], int) or abort["case_id"] is None:
                continue
            step = abort["step_index"]
            for paths in paths_by_block:
                path = paths.get(cell["run_id"])
                if (
                    path is not None
                    and step < len(path.case_ids)
                    and path.case_ids[step] == abort["case_id"]
                ):
                    abort["passes_elsewhere"] += 1
                    abort["operator_from_other_block"] = path.operators[step]
    for block in blocks:
        for item in block["aborts"]:
            match = next(cell for cell in block["cells"] if cell["run_id"] == item["run_id"])
            item["operator_from_other_block"] = match["abort"]["operator_from_other_block"]
            item["passes_elsewhere"] = match["abort"]["passes_elsewhere"]


def _counted_normal(block: Mapping[str, Any]) -> int:
    """Normal cells, without those whose path changed at a one-sided timed_out or failed step."""
    determinism = block.get("determinism") or {}
    excluded = determinism.get("one_sided_congestion_cells") or ()
    return sum(
        1
        for cell in block["cells"]
        if cell["disposition"] == "normal" and cell["run_id"] not in excluded
    )


def normal_fraction(blocks: Sequence[Mapping[str, Any]]) -> float | None:
    """N(j): the normal fraction over all of a level's blocks, the selection rule's only use."""
    ran = sum(block["cells_planned"] - block["cells_not_run"] for block in blocks)
    return sum(_counted_normal(block) for block in blocks) / ran if ran else None


def block_g(block: Mapping[str, Any], design_budget: int) -> float | None:
    """G: saturated exec/h per budget times the block's normal fraction. A report column only.

    The selection rule does not use it: in a 12-cell block the abort noise would dominate.
    """
    rate = block["saturated_exec_per_real_hour"]
    fraction = normal_fraction([block])
    if rate is None or fraction is None:
        return None
    return rate / design_budget * fraction


def _v3_arm_inputs(group: Sequence[Mapping[str, Any]], timed_out: int) -> dict[str, Any]:
    """Design v3 additions for one arm: V10' clock coverage and V7''s numerator, as counts."""
    reexecutions = sum(cell["infra_reexecutions"] or 0 for cell in group)
    return {
        "cell_clock_unmeasured": {
            clock: sum(1 for cell in group if clock in cell["clock_unmeasured"])
            for clock in V10_CLOCKS
        },
        "infra_reexecutions": reexecutions,
        "infra_reexecutions_unmeasured": sum(
            1 for cell in group if cell["infra_reexecutions_malformed"]
        ),
        "cells_with_reexecution": sum(1 for cell in group if (cell["infra_reexecutions"] or 0) > 0),
        "v7_numerator": timed_out + reexecutions,
    }


def summarize_level(
    jobs: int,
    blocks: Sequence[Mapping[str, Any]],
    targets: Mapping[str, Sequence[float]],
    *,
    v3: bool = False,
) -> dict[str, Any]:
    """Everything the decision reads for one concurrency level of one stage.

    ``v3`` adds V10''s clock coverage and V7''s numerator (timed-out steps plus infrastructure
    re-executions) per arm and for the level. Without it the summary is exactly the v2 one.
    """
    cells = [cell for block in blocks for cell in block["cells"]]
    arms: dict[str, dict[str, Any]] = {}
    for arm in sorted({cell["arm"] for cell in cells}):
        group = [cell for cell in cells if cell["arm"] == arm]
        steps = sum(cell["executions"] for cell in group)
        timed_out = sum(cell["terminations"].get("timed_out", 0) for cell in group)
        ineligible = sum(cell["ineligible_steps"] for cell in group)
        kinds: Counter[str] = Counter()
        for cell in group:
            kinds.update(cell["failure_kinds"])
        seconds = list(targets.get(arm, ()))
        arms[arm] = {
            "campaigns": len(group),
            "aborts": sum(1 for cell in group if cell["disposition"] == "abort"),
            "abort_steps": [c["abort"]["step_index"] for c in group if c["abort"]],
            "exposure": sum(cell["exposure"] for cell in group),
            "steps": steps,
            "timed_out": timed_out,
            "ineligible_steps": ineligible,
            "failure_kinds": dict(kinds),
            "target_seconds_p50": _percentile(seconds, 0.5),
            "target_seconds_p99": _percentile(seconds, 0.99),
            "target_seconds_p999": _percentile(seconds, 0.999),
            "target_seconds_max": max(seconds) if seconds else None,
            # A None (design v3, stamp missing) is left out here and counted by V10'.
            "cell_monotonic_max": max(
                (c["monotonic_seconds"] for c in group if c["monotonic_seconds"] is not None),
                default=None,
            ),
            "cell_real_max": max(
                (c["real_seconds"] for c in group if c["real_seconds"] is not None), default=None
            ),
            "real_seconds_per_step": (
                statistics.fmean(
                    c["real_seconds"] / c["executions"]
                    for c in group
                    if c["disposition"] == "normal"
                    and c["executions"]
                    and c["real_seconds"] is not None
                )
                if any(
                    c["disposition"] == "normal"
                    and c["executions"]
                    and c["real_seconds"] is not None
                    for c in group
                )
                else None
            ),
        }
        if v3:
            arms[arm].update(_v3_arm_inputs(group, timed_out))
    rates = [b["normal_campaigns_per_real_hour"] or 0.0 for b in blocks]
    extra: dict[str, Any] = {}
    if v3:
        reexecutions = sum(arm["infra_reexecutions"] for arm in arms.values())
        extra = {
            "infra_reexecutions": reexecutions,
            "v7_numerator": sum(arm["timed_out"] for arm in arms.values()) + reexecutions,
            "differing_cells_with_reexecution": sum(
                (b.get("determinism") or {}).get("differing_cells_with_reexecution", 0)
                for b in blocks
            ),
        }
    return {
        **extra,
        "jobs": jobs,
        "blocks": len(blocks),
        "campaigns": len(cells),
        "aborts": sum(1 for cell in cells if cell["disposition"] == "abort"),
        "watchdog_kills": sum(1 for cell in cells if cell["watchdog_killed"]),
        "stopped": [b["stopped_reason"] for b in blocks if b["stopped_reason"]],
        "other_abnormal": sum(1 for cell in cells if cell["disposition"] in ABNORMAL_DISPOSITIONS),
        "steps": sum(cell["executions"] for cell in cells),
        "timed_out": sum(arm["timed_out"] for arm in arms.values()),
        "first_error_unconfirmed": sum(
            1
            for cell in cells
            if cell["abort"] and cell["abort"]["first_error"]["status"] == "unconfirmed"
        ),
        "verdict_only_cells": sum(
            (b.get("determinism") or {}).get("verdict_only_cells", 0) for b in blocks
        ),
        "normal_campaigns_per_real_hour_mean": statistics.fmean(rates) if rates else None,
        "executions_per_real_hour_mean": (
            statistics.fmean(b["executions_per_real_hour"] or 0.0 for b in blocks)
            if blocks
            else None
        ),
        "arms": arms,
    }


def abort_arm_p_value(level: Mapping[str, Any]) -> float | None:
    """V5 input: the existing arm x abort test on the level's per-campaign table."""
    arms = level["arms"]
    if len(arms) < 2 or not level["aborts"]:
        return None
    matrix = [[arm["campaigns"] - arm["aborts"], arm["aborts"], 0] for arm in arms.values()]
    result = arm_abort_independence(matrix, list(arms))
    return result["primary_arm_vs_abort"]["p_value"]


def _ineligible_over_limit(arm: Mapping[str, Any]) -> bool:
    steps = arm["steps"]
    return bool(steps) and arm["ineligible_steps"] / steps * 1000 > V8_PER_1000


@dataclass(frozen=True, slots=True)
class V3Rules:
    """Design v3's strengthened rules (v3 section 6.2), applied per host.

    V10' replaces V10: an arm is excluded if a cell's duration exceeds ``monotonic_seconds`` on
    CLOCK_MONOTONIC or ``realtime_seconds`` on CLOCK_REALTIME, and a cell whose stamp for a clock
    is missing counts as over that clock's limit (not measurable is not a pass). V7' replaces V7:
    its numerator is timed-out steps plus infrastructure re-executions, with V7's thresholds and
    table; a cell whose re-execution count cannot be read counts against the arm the same way.
    """

    monotonic_seconds: float
    realtime_seconds: float

    @classmethod
    def of(cls, design: Design) -> V3Rules | None:
        if not design.is_v3:
            return None
        if design.v10_monotonic_seconds is None or design.v10_realtime_seconds is None:
            raise ValueError("a v3 design needs v10_monotonic_seconds and v10_realtime_seconds")
        return cls(design.v10_monotonic_seconds, design.v10_realtime_seconds)


def _v3_arm_violations(name: str, arm: Mapping[str, Any], rules: V3Rules, add: Any) -> None:
    steps = arm["steps"]
    if steps and arm["v7_numerator"] / steps * 1000 > V7_TIMED_OUT_PER_1000:
        add(
            "V7'",
            {
                "arm": name,
                "timed_out": arm["timed_out"],
                "infra_reexecutions": arm["infra_reexecutions"],
                "steps": steps,
            },
        )
    if arm["infra_reexecutions_unmeasured"]:
        add("V7'", {"arm": name, "unmeasurable_cells": arm["infra_reexecutions_unmeasured"]})
    for clock, key, limit in (
        ("monotonic", "cell_monotonic_max", rules.monotonic_seconds),
        ("realtime", "cell_real_max", rules.realtime_seconds),
    ):
        value = arm[key]
        if value is not None and value > limit:
            add("V10'", {"arm": name, "clock": clock, "cell_seconds_max": value, "limit": limit})
        unmeasured = arm["cell_clock_unmeasured"][clock]
        if unmeasured:
            add("V10'", {"arm": name, "clock": clock, "unmeasurable_cells": unmeasured})


def absolute_violations(
    level: Mapping[str, Any],
    earlier: Mapping[str, Any] | None = None,
    *,
    v3: V3Rules | None = None,
) -> list[dict[str, Any]]:
    """The rules that need no reference level: V1, V2, V3, V6, V7 per arm, V8 limit, V10.

    A stage's reference level is re-judged by these alone. It passed its own comparison earlier,
    so only an outright failure in its new blocks can take that back. ``earlier`` is the same level
    in the stage where it was the higher one. V3 pools it, since a(j) is over all the level's blocks
    and abort noise alone would otherwise cancel a sound level; the other rules read new blocks.
    With ``v3`` (design v3), V7' and V10' take the place of V7 per arm and V10.
    """
    found: list[dict[str, Any]] = []

    def add(rule: str, detail: object) -> None:
        found.append({"rule": rule, "detail": detail})

    if level["watchdog_kills"] >= 1:
        add("V1", level["watchdog_kills"])
    if level["other_abnormal"] >= V2_OTHER_ABNORMAL:
        add("V2", level["other_abnormal"])
    aborts = level["aborts"] + (earlier["aborts"] if earlier else 0)
    campaigns = level["campaigns"] + (earlier["campaigns"] if earlier else 0)
    fraction = aborts / campaigns if campaigns else 0.0
    if fraction > V3_ABORT_FRACTION:
        add("V3", fraction)
    for name, arm in level["arms"].items():
        p999 = arm["target_seconds_p999"]
        if p999 is not None and p999 > V6_TARGET_P999_SECONDS:
            add("V6", {"arm": name, "p999": p999})
        steps = arm["steps"]
        if v3 is None and steps and arm["timed_out"] / steps * 1000 > V7_TIMED_OUT_PER_1000:
            add("V7", {"arm": name, "timed_out": arm["timed_out"], "steps": steps})
        if _ineligible_over_limit(arm):
            add("V8", {"arm": name, "ineligible": arm["ineligible_steps"], "steps": steps})
        if v3 is not None:
            _v3_arm_violations(name, arm, v3, add)
            continue
        monotonic = arm["cell_monotonic_max"]
        if monotonic is not None and monotonic > V10_CELL_MONOTONIC_SECONDS:
            add("V10", {"arm": name, "cell_monotonic_max": monotonic})
    return found


def level_violations(
    level: Mapping[str, Any],
    ref: Mapping[str, Any],
    *,
    floor: int,
    block_m: Sequence[int],
    one_sided_cells: int,
    block_uncomparable: Sequence[int] = (),
    v3: V3Rules | None = None,
) -> list[dict[str, Any]]:
    """Exclusion rules V1 to V10 for a level against its stage's reference level.

    With ``v3``, the relative V7 test becomes V7': the same table on timed-out steps plus
    infrastructure re-executions.
    """
    found = absolute_violations(level, v3=v3)

    def add(rule: str, detail: object) -> None:
        found.append({"rule": rule, "detail": detail})

    if level["stopped"]:
        add("stopped", level["stopped"])
    if significantly_more(level["aborts"], ref["aborts"]):
        add("V4", {"aborts": level["aborts"], "ref_aborts": ref["aborts"]})
    if level["aborts"] > ref["aborts"]:
        p_value = abort_arm_p_value(level)
        if p_value is not None and p_value <= V5_ARM_P:
            add("V5", p_value)
    for name, arm in level["arms"].items():
        steps = arm["steps"]
        ref_arm = ref["arms"].get(name)
        if not _ineligible_over_limit(arm) and steps and ref_arm and ref_arm["steps"]:
            rate = arm["ineligible_steps"] / steps
            ref_rate = ref_arm["ineligible_steps"] / ref_arm["steps"]
            share = steps / (steps + ref_arm["steps"])
            if (
                rate > V8_RATE_RATIO * ref_rate
                and exact_upper_p(arm["ineligible_steps"], ref_arm["ineligible_steps"], share)
                <= ALPHA
            ):
                add("V8", {"arm": name, "rate": rate, "ref_rate": ref_rate})
    if v3 is not None:
        if significantly_more(level["v7_numerator"], ref["v7_numerator"]):
            add(
                "V7'",
                {
                    "timed_out": level["timed_out"],
                    "infra_reexecutions": level["infra_reexecutions"],
                    "ref_timed_out": ref["timed_out"],
                    "ref_infra_reexecutions": ref["infra_reexecutions"],
                },
            )
    elif significantly_more(level["timed_out"], ref["timed_out"]):
        add("V7", {"timed_out": level["timed_out"], "ref_timed_out": ref["timed_out"]})
    if block_m and max(block_m) - floor >= V9_EXCESS_OVER_FLOOR:
        add("V9", {"block_m": list(block_m), "floor": floor})
    if one_sided_cells >= V9_ONE_SIDED_CELLS:
        add("V9", {"one_sided_congestion_cells": one_sided_cells})
    if block_uncomparable and max(block_uncomparable) >= UNCOMPARABLE_CELLS:
        add("V9", {"uncomparable_cells": list(block_uncomparable)})
    return found


def selection_ratios(
    throughput: Sequence[float | None], normal_ref: float | None, normal_high: float | None
) -> dict[str, Any]:
    """The selection rule from the four crossed blocks' X, in run order (ref, high, high, ref).

    rho and drift use the saturated execution rate X, which aborts barely move. The normal
    fraction enters once, as the level totals N(high)/N(ref).
    """
    empty = {"rho": None, "drift": None, "valid": False, "adjusted_gain": None, "gain": False}
    if len(throughput) != 4 or any(value is None or value <= 0 for value in throughput):
        return empty
    first, second, third, fourth = (float(value) for value in throughput)  # type: ignore[arg-type]
    rho = (second / first, third / fourth)
    # Later block over earlier block of the same level.
    drift = max(abs(fourth / first - 1), abs(third / second - 1))
    adjusted = (
        min(rho) * normal_high / normal_ref if normal_ref and normal_high is not None else None
    )
    gain = (
        min(rho) >= RHO_MIN and drift <= DRIFT_MAX and adjusted is not None and adjusted >= RHO_MIN
    )
    return {
        "rho": list(rho),
        "drift": drift,
        "valid": drift <= DRIFT_MAX,
        "adjusted_gain": adjusted,
        "gain": gain,
    }


def recurrences(blocks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Whether aborts repeat on the same input, and how often that input was tried again.

    The same (arm, seed, step, case id) in two or more blocks is input dependence (H2). "None" is
    only as strong as its denominator: how often an aborted case passed in another block. A case
    id alone repeating at another arm, seed or step is reported but does not count, since a common
    case can coincide by chance.
    """
    seen: dict[tuple[str, int, Any, Any], list[str]] = defaultdict(list)
    by_case: dict[Any, set[tuple[str, int, Any]]] = defaultdict(set)
    passes = 0
    for block in blocks:
        for cell in block["cells"]:
            abort = cell["abort"]
            if abort is None:
                continue
            passes += abort.get("passes_elsewhere") or 0
            if abort["case_id"] is None:
                continue
            key = (cell["arm"], cell["seed"], abort["step_index"], abort["case_id"])
            seen[key].append(f"{block['stage']}/{block['index']}")
            by_case[abort["case_id"]].add(key[:3])
    return {
        "same_input": [
            {"arm": key[0], "seed": key[1], "step": key[2], "blocks": where}
            for key, where in seen.items()
            if len(where) >= 2
        ],
        "same_case_elsewhere": sum(1 for places in by_case.values() if len(places) >= 2),
        "passes_elsewhere": passes,
        "recurrence_upper95": 1 - 0.05 ** (1 / passes) if passes else None,
    }


def decide(design: Design, stages: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The mechanical result: a selected level or a stop, and what the next stage may do.

    A v3 design is decided for one host's blocks, with V7' and V10' (``V3Rules``).
    """
    v3 = V3Rules.of(design)
    all_blocks = [block for stage in stages.values() for block in stage["blocks"]]
    recurrence = recurrences(all_blocks)
    repeated = recurrence["same_input"]
    unconfirmed = sum(
        level["first_error_unconfirmed"]
        for stage in stages.values()
        for level in stage["levels"].values()
    )
    selected: int | None = None
    halts: list[dict[str, Any]] = []
    verdicts: dict[str, Any] = {}
    status = "pending"
    invalid_stage: str | None = None
    if repeated:
        halts.append({"rule": "H2", "detail": repeated})
    measured = measured_stages(design)
    for position, name in enumerate(measured):
        order = design.stages[name]
        ref_jobs, high_jobs = order[0], order[1]
        first_stage = position == 0
        if selected is None:
            selected = ref_jobs
        stage = stages.get(name)
        if stage is None:
            break
        blocks = stage["blocks"]
        stopped_blocks = [block for block in blocks if block["stopped_reason"]]
        if len(blocks) < len(order) and not stopped_blocks:
            break
        external = any(block["stop_kind"] == STOP_EXTERNAL for block in stopped_blocks)
        ref_stopped = any(block["jobs"] == ref_jobs for block in stopped_blocks)
        # The first reference did not finish: not "failed to pass" but "could not measure".
        if first_stage and ref_stopped:
            halts.append({"rule": "H5", "detail": [b["stopped_reason"] for b in stopped_blocks]})
        # An external stop voids the stage's measurements, so no rule reads them.
        invalid = external and not (first_stage and ref_stopped)
        ref = stage["levels"][str(ref_jobs)]
        high = stage["levels"].get(str(high_jobs))
        floor = next(
            (b["determinism"]["m"] for b in blocks if b["index"] == len(order)),
            0,
        )
        fraction = ref["aborts"] / ref["campaigns"] if ref["campaigns"] else 0.0
        if first_stage and not external and fraction > V3_ABORT_FRACTION:
            halts.append({"rule": "H1", "detail": fraction})
        if not external and floor >= H3_FLOOR:
            halts.append({"rule": "H3", "stage": name, "floor": floor})
        # F cannot be measured: not a pass and not H3, whose fallback needs a measured jobs=2.
        ref_uncomparable = [
            b["determinism"]["uncomparable"] for b in blocks if b["jobs"] == ref_jobs
        ]
        if not external and max(ref_uncomparable, default=0) >= UNCOMPARABLE_CELLS:
            halts.append(
                {"rule": "H3-unmeasured", "stage": name, "uncomparable_cells": ref_uncomparable}
            )
        high_blocks = [b for b in blocks if b["jobs"] == high_jobs]
        violations: list[dict[str, Any]] = []
        ref_violations: list[dict[str, Any]] = []
        if not external:
            violations = (
                level_violations(
                    high,
                    ref,
                    floor=floor,
                    block_m=[b["determinism"]["m"] for b in high_blocks],
                    one_sided_cells=sum(
                        len(b["determinism"]["one_sided_congestion_cells"]) for b in high_blocks
                    ),
                    block_uncomparable=[b["determinism"]["uncomparable"] for b in high_blocks],
                    v3=v3,
                )
                if high is not None
                else [{"rule": "stopped", "detail": "the higher level did not run"}]
            )
            earlier = (
                None if first_stage else stages[measured[position - 1]]["levels"].get(str(ref_jobs))
            )
            ref_violations = absolute_violations(ref, earlier, v3=v3)
            if ref["stopped"]:
                ref_violations.append({"rule": "stopped", "detail": ref["stopped"]})
        # The first reference has nowhere lower to go, so its violations are only shown.
        ref_cancelled = bool(ref_violations) and not first_stage
        ratios = selection_ratios(
            [block["saturated_exec_per_real_hour"] for block in blocks],
            normal_fraction([b for b in blocks if b["jobs"] == ref_jobs]),
            normal_fraction(high_blocks),
        )
        passed = not invalid and not ref_cancelled and not violations and bool(ratios["gain"])
        verdicts[name] = {
            "ref_jobs": ref_jobs,
            "high_jobs": high_jobs,
            "floor": floor,
            "stage_invalid": invalid,
            "violations": violations,
            "ref_violations": ref_violations,
            "ref_cancelled": ref_cancelled,
            "g_blocks": [block_g(block, design.budget) for block in blocks],
            **ratios,
            "throughput_judgement_invalid": ratios["drift"] is not None and not ratios["valid"],
            "passed": passed and not halts,
        }
        if halts:
            break
        if invalid:
            invalid_stage = name
            status = "provisional"
            if first_stage:
                selected = None
            break
        if ref_cancelled:
            selected = design.stages[measured[position - 1]][0]
            status = "selected"
            break
        if not passed:
            status = "selected"
            break
        selected = high_jobs
        status = "provisional"
    # H3 alone: nothing was selected by comparison, but EXP-3 needs a value, the measured safe one.
    fallback: int | None = None
    if halts:
        status = "halted"
        selected = None
        if all(item["rule"] == "H3" for item in halts):
            fallback = design.stages[measured_stages(design)[0]][0]
    elif status == "pending":
        selected = None
    elif status == "provisional" and all(
        name in verdicts and verdicts[name]["passed"] for name in measured
    ):
        status = "selected"
    return {
        "status": status,
        "selected_jobs": selected,
        "fallback_jobs": fallback,
        "stage_invalid": invalid_stage,
        "halts": halts,
        "h4_first_error_unconfirmed": unconfirmed,
        "stages": verdicts,
        "recurrences": recurrence,
    }


#: Paths of one output tree's measured blocks by (stage, block index), kept in memory only.
BlockPaths = dict[tuple[str, int], dict[str, CellPath]]


def _block_stamps_present(record: Mapping[str, Any]) -> bool:
    return all(
        _stamp(record, side, clock) is not None
        for side in ("started", "ended")
        for clock in V10_CLOCKS
    )


def _reexecuted(block: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(
        cell["run_id"] for cell in block["cells"] if (cell.get("infra_reexecutions") or 0) > 0
    )


def analyze(output: Path, design: Design) -> dict[str, Any]:
    return _analyze(output, design)[0]


def _analyze(output: Path, design: Design) -> tuple[dict[str, Any], BlockPaths]:
    """One output tree (v2: the run; v3: one host). Paths are returned for X1, never written."""
    stages: dict[str, Any] = {}
    every_block: list[dict[str, Any]] = []
    every_path: list[dict[str, CellPath]] = []
    block_paths: BlockPaths = {}
    incomplete: list[str] = []
    for stage in design.stages:
        if not (output / stage).is_dir():
            continue
        if stage == SMOKE_STAGE:
            for index, jobs in enumerate(design.stages[stage], start=1):
                directory = output / stage / f"block-{index}-j{jobs}"
                record_path = directory / BLOCK_FILE
                if directory.exists() and (
                    (directory / INCOMPLETE_BLOCK_FILE).exists() or not record_path.is_file()
                ):
                    incomplete.append(f"{stage}/{directory.name}")
                elif record_path.is_file():
                    record = json.loads(record_path.read_text(encoding="utf-8"))
                    if record.get("finished") is not True and not planned_stop(record):
                        incomplete.append(f"{stage}/{directory.name}")
            continue
        blocks: list[dict[str, Any]] = []
        targets_by_jobs: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        reference: dict[str, CellPath] = {}
        reference_reexecuted: frozenset[str] = frozenset()
        for index, jobs in enumerate(design.stages[stage], start=1):
            directory = output / stage / f"block-{index}-j{jobs}"
            record_path = directory / BLOCK_FILE
            if (directory / INCOMPLETE_BLOCK_FILE).exists():
                incomplete.append(f"{stage}/{directory.name}")
                continue
            if directory.exists() and not record_path.is_file():
                incomplete.append(f"{stage}/{directory.name}")
                continue
            if not record_path.is_file():
                continue
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("finished") is not True and not planned_stop(record):
                incomplete.append(f"{stage}/{directory.name}")
                continue
            # Design v3: a block record without its clock stamps cannot be measured at all.
            if design.is_v3 and not _block_stamps_present(record):
                incomplete.append(f"{stage}/{directory.name}")
                continue
            block, paths, targets = summarize_block(directory, record, design)
            reexecuted: frozenset[str] | None = None
            if design.is_v3:
                if index == 1:
                    reference_reexecuted = _reexecuted(block)
                reexecuted = _reexecuted(block) | reference_reexecuted
            if index == 1:
                reference = paths
            block["determinism"] = block_determinism(block, paths, reference, reexecuted)
            for arm, seconds in targets.items():
                targets_by_jobs[jobs][arm].extend(seconds)
            blocks.append(block)
            every_path.append(paths)
            block_paths[(stage, index)] = paths
        every_block.extend(blocks)
        by_jobs: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for block in blocks:
            by_jobs[block["jobs"]].append(block)
        levels = {
            str(jobs): summarize_level(jobs, group, targets_by_jobs[jobs], v3=design.is_v3)
            for jobs, group in sorted(by_jobs.items())
        }
        stages[stage] = {"levels": levels, "blocks": blocks}
    # Every stage repeats the same seeds, so a case can pass again in any of them.
    fill_abort_operators(every_block, every_path)
    decision = decide(design, stages)
    if incomplete:
        decision["status"] = "halted"
        decision["selected_jobs"] = None
        decision["fallback_jobs"] = None
        decision["halts"].append({"rule": "incomplete-block", "detail": incomplete})
    report = {
        "label": LABEL,
        "design_id": design.design_id,
        "design_sha256": design.sha256,
        "execution_mode": "per-case-container",
        "decision": decision,
        "stages": stages,
    }
    return report, block_paths


# ---- design v3: two hosts -----------------------------------------------------------------

REPORT_V3_JSON = "concurrency-report-v3.json"
REPORT_V3_MD = "concurrency-report-v3.md"
SCHEMA_V3 = "inodefence-h1-concurrency-v3-combined-v1"
PREFLIGHT_FILE = "preflight.json"
#: X1's second clause has no design key; v3 section 6.2 writes it as ">= 2", the V9 value.
X1_ONE_SIDED_CELLS = V9_ONE_SIDED_CELLS
#: The pre-registered consequence of X1 (v3 sections 6.2 and 10, D044). Not a jobs exclusion.
X1_CONSEQUENCE = (
    "X1은 jobs 배제 규칙이 아니다(v3 §6.2). 결과는 본실험 분석에만 영향을 준다. "
    "발동했으면 확증 분석(seed 블록 단위 순열 검정)의 구조는 그대로 두고 "
    "호스트별 민감도 표(호스트별 T_first·U_viol 요약과 abort)를 추가 보고한다. "
    "호스트 제외나 단일 호스트 전환은 지웅이 결정하며, 이 결정은 EXP-3 train 첫 셀 "
    "시작 전에 하고 그 시각과 근거를 docs/LOG.md에 기록한다. 그 뒤에는 X1을 근거로 "
    "호스트를 제외하거나 바꾸지 않는다. X1이 발동하지 않았어도 호스트는 기록 요인으로 "
    "남는다(v3 §10)."
)
V3_RULES_EVALUATED = (
    "v2 §6 (V1-V10, H1-H5, H3-unmeasured, selection) per host on that host's blocks only; "
    "no statistic is pooled across hosts",
    "V10' (v3 §6.2): monotonic or realtime cell duration over its limit; a missing stamp counts "
    "as over (fail closed); replaces V10",
    "V7' (methodology owner 2026-11-11, pending the v3 text correction): V7 with timed-out steps "
    "plus infrastructure re-executions as numerator; replaces V7; V3/V4 unchanged",
    "X1 (v3 §6.2, §6.3): first-stage block 1 across hosts, three clauses; not a jobs exclusion; "
    "block-4 pair reported only",
    "H2' (v3 §6.2): H2 on any host halts every host",
    "host identity and Docker engine per host against the design (halt on mismatch or missing)",
    "infrastructure re-executions per cell: report column and V7' numerator; differences in "
    "re-executed cells reported for V9 and X1, judging nothing",
    "not evaluated here: probe/probe.json (not a decision input, v3 §5), shared path hashes "
    "(v3 §11 table; no record field to read yet)",
)


def _halt(decision: dict[str, Any], rule: str, detail: object) -> None:
    """A stop added after the per-host decision; like an incomplete block it selects nothing."""
    decision["halts"].append({"rule": rule, "detail": detail})
    decision["status"] = "halted"
    decision["selected_jobs"] = None
    decision["fallback_jobs"] = None


def _block_directories(output: Path, design: Design) -> list[tuple[str, Path]]:
    found = []
    for stage, order in design.stages.items():
        for index, jobs in enumerate(order, start=1):
            directory = output / stage / f"block-{index}-j{jobs}"
            if directory.is_dir():
                found.append((f"{stage}/{directory.name}", directory))
    return found


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def host_identity_problems(output: Path, design: Design, host: str) -> list[str]:
    """Block records under ``output`` that do not name this host and its run prefix (fail closed).

    A record without ``host`` is a problem too: the v3 driver writes it, so its absence means the
    block cannot be attributed to this host.
    """
    prefix = design.hosts[host].run_prefix
    problems = []
    for name, directory in _block_directories(output, design):
        record = _read_json(directory / BLOCK_FILE)
        if not isinstance(record, Mapping):
            continue  # Missing or unreadable records are the incomplete-block halt already.
        listed = record.get("cells")
        cells: list[Any] = listed if isinstance(listed, list) else []
        if (
            record.get("host") != host
            or record.get("run_prefix") != prefix
            or any(not str(cell.get("run_id", "")).startswith(f"{prefix}-") for cell in cells)
        ):
            problems.append(name)
    return problems


def engine_check(output: Path, design: Design, host: str) -> dict[str, Any]:
    """The Docker server each block's preflight found, against ``host.<id>.docker_engine``.

    The v2 driver refuses to run on a different engine; here a mismatch halts the host. A block
    whose preflight (or its block record's own ``docker_engine``, if any) cannot be read is
    unverified, which halts too.
    """
    expected = design.engine_for(host)
    observed: dict[str, Any] = {}
    unverified: list[str] = []
    for name, directory in _block_directories(output, design):
        preflight = _read_json(directory / PREFLIGHT_FILE)
        facts = preflight.get("preflight") if isinstance(preflight, Mapping) else None
        server = facts.get("docker_server") if isinstance(facts, Mapping) else None
        record = _read_json(directory / BLOCK_FILE)
        recorded = record.get("docker_engine") if isinstance(record, Mapping) else None
        if not isinstance(server, str):
            unverified.append(name)
            continue
        observed[name] = server
        if recorded is not None and recorded != server:
            observed[f"{name} (block record)"] = recorded
    mismatched = sorted(name for name, value in observed.items() if value != expected)
    return {
        "expected": expected,
        "observed": observed,
        "mismatched": mismatched,
        "unverified": unverified,
    }


@dataclass(slots=True)
class HostAnalysis:
    report: dict[str, Any]
    paths: BlockPaths


def _block_summary(report: Mapping[str, Any], stage: str, index: int) -> Mapping[str, Any] | None:
    blocks = ((report.get("stages") or {}).get(stage) or {}).get("blocks") or ()
    return next((block for block in blocks if block["index"] == index), None)


def cross_host_paths(
    design: Design, stage: str, index: int, left: HostAnalysis, right: HostAnalysis
) -> dict[str, Any] | None:
    """Path agreement of the same block on two hosts, by (arm, seed); counts only.

    Uses V9's notion (``compare_paths``: case sequence, step terminations, verdict hashes in
    memory). Every planned cell is looked for, so a cell missing on either side is incomparable,
    not passed. None when either host has no usable record of this block.
    """
    left_block = _block_summary(left.report, stage, index)
    right_block = _block_summary(right.report, stage, index)
    if left_block is None or right_block is None:
        return None
    sides = []
    for block, analysis in ((left_block, left), (right_block, right)):
        paths = analysis.paths.get((stage, index), {})
        by_key = {(cell["arm"], cell["seed"]): cell for cell in block["cells"]}
        sides.append((by_key, paths))
    differing = one_sided = incomparable = with_reexecution = 0
    missing = [0, 0]
    for planned in planned_cells(design, stage):
        key = (planned.arm.label, planned.seed)
        found = []
        for position, (by_key, paths) in enumerate(sides):
            cell = by_key.get(key)
            path = paths.get(cell["run_id"]) if cell is not None else None
            if path is None:
                missing[position] += 1
            found.append((cell, path))
        (left_cell, left_path), (right_cell, right_path) = found
        if left_path is None or right_path is None:
            incomparable += 1
            continue
        difference = compare_paths(left_path, right_path)
        if not difference.differs:
            continue
        differing += 1
        one_sided += difference.one_sided_congestion
        with_reexecution += any(
            ((cell or {}).get("infra_reexecutions") or 0) > 0 for cell in (left_cell, right_cell)
        )
    return {
        "m_x": differing,
        "one_sided_congestion_cells": one_sided,
        "incomparable_cells": incomparable,
        "incomparable_missing_on": missing,
        "differing_cells_with_reexecution": with_reexecution,
        "planned_cells": len(planned_cells(design, stage)),
    }


def host_floor(design: Design, stage: str, report: Mapping[str, Any]) -> int | None:
    """F of one host's stage: ref block 4 against block 1. None when it was not measured.

    Not measured: the last reference block has no record, or a reference block has
    ``UNCOMPARABLE_CELLS`` incomparable cells (H3-unmeasured).
    """
    order = design.stages[stage]
    last = _block_summary(report, stage, len(order))
    if last is None:
        return None
    for index, jobs in enumerate(order, start=1):
        block = _block_summary(report, stage, index)
        if jobs == order[0] and (
            block is None or block["determinism"]["uncomparable"] >= UNCOMPARABLE_CELLS
        ):
            return None
    return last["determinism"]["m"]


def evaluate_x1(design: Design, analyses: Mapping[str, HostAnalysis]) -> dict[str, Any]:
    """X1, cross-host path agreement (v3 sections 6.2 and 6.3). Not a jobs exclusion.

    Fires on any clause: m_x - max(F) >= x1_margin; one-sided timed_out/failed first differences
    >= 2; incomparable cells >= x1_incomparable_cells. The first clause needs both floors; when one
    is not measured and no other clause fires, X1 is "not evaluated" (not "not fired").
    """
    hosts = list(design.hosts)
    stage = measured_stages(design)[0]
    order = design.stages[stage]
    result: dict[str, Any] = {
        "status": "not evaluated",
        "jobs_exclusion": False,
        "stage": stage,
        "compared_block": f"block-1-j{order[0]}",
        "thresholds": {
            "margin": design.x1_margin,
            "one_sided_congestion_cells": X1_ONE_SIDED_CELLS,
            "incomparable_cells": design.x1_incomparable_cells,
        },
        "hosts": hosts,
        "inputs": None,
        "clauses": None,
        "one_incomparable_reported": False,
        "report_only_last_block": None,
        "reasons_not_evaluated": [],
        "consequence": X1_CONSEQUENCE,
    }
    reasons = result["reasons_not_evaluated"]
    if len(hosts) != 2:
        reasons.append(f"X1 is defined for two hosts; the design has {len(hosts)}")
        return result
    absent = [host for host in hosts if host not in analyses]
    if absent:
        reasons.append(f"no output for {absent}")
        return result
    left, right = (analyses[host] for host in hosts)
    pair = cross_host_paths(design, stage, 1, left, right)
    result["report_only_last_block"] = cross_host_paths(design, stage, len(order), left, right)
    if pair is None:
        reasons.append(f"{result['compared_block']} has no usable record on every host")
        return result
    floors = {host: host_floor(design, stage, analyses[host].report) for host in hosts}
    measured = [value for value in floors.values() if value is not None]
    floor_max = max(measured) if len(measured) == len(hosts) else None
    assert design.x1_margin is not None and design.x1_incomparable_cells is not None
    clauses = {
        "excess_over_floor": (
            pair["m_x"] - floor_max >= design.x1_margin if floor_max is not None else None
        ),
        "one_sided_congestion": pair["one_sided_congestion_cells"] >= X1_ONE_SIDED_CELLS,
        "incomparable": pair["incomparable_cells"] >= design.x1_incomparable_cells,
    }
    result["inputs"] = {
        **pair,
        "floors": floors,
        "floor_max": floor_max,
        "excess": pair["m_x"] - floor_max if floor_max is not None else None,
    }
    result["clauses"] = clauses
    result["one_incomparable_reported"] = (
        0 < pair["incomparable_cells"] < (design.x1_incomparable_cells)
    )
    if any(value is True for value in clauses.values()):
        result["status"] = "fired"
    elif clauses["excess_over_floor"] is None:
        unmeasured = sorted(host for host, value in floors.items() if value is None)
        reasons.append(f"F not measured on {unmeasured}; the first clause cannot be judged")
    else:
        result["status"] = "not fired"
    return result


def _infra_column(report: Mapping[str, Any]) -> dict[str, Any]:
    """Per-cell infrastructure re-executions of one host (counts only)."""
    cells: dict[str, Any] = {}
    for stage, content in (report.get("stages") or {}).items():
        for block in content["blocks"]:
            for cell in block["cells"]:
                cells[f"{stage}/{block['index']}/{cell['run_id']}"] = cell.get("infra_reexecutions")
    known = [value for value in cells.values() if value is not None]
    return {
        "cells": cells,
        "total": sum(known),
        "cells_with_reexecution": sum(1 for value in known if value > 0),
        "cells_unknown": sum(1 for value in cells.values() if value is None),
    }


def _pending_host() -> dict[str, Any]:
    return {
        "status": "pending",
        "selected_jobs": None,
        "fallback_jobs": None,
        "stage_invalid": None,
        "halts": [],
        "missing": True,
    }


def analyze_v3(
    design: Design, outputs: Mapping[str, Path], *, partial: bool = False
) -> dict[str, Any]:
    """Design v3: decide each host from its own output tree, then add the cross-host rules.

    Returns ``{"combined": ..., "hosts": {host: per-host report}}``. A host named in the design
    without an output is refused unless ``partial``; then every host is pending (or halted) and
    X1 is not evaluated.
    """
    if not design.is_v3:
        raise ValueError("analyze_v3 needs a v3 design (with hosts)")
    unknown = sorted(set(outputs) - set(design.hosts))
    if unknown:
        raise ValueError(f"hosts {unknown} are not in the design ({sorted(design.hosts)})")
    missing = [host for host in design.hosts if host not in outputs]
    if missing and not partial:
        raise ValueError(f"no output for hosts {missing}; pass --partial to analyze without them")
    analyses: dict[str, HostAnalysis] = {}
    engines: dict[str, Any] = {}
    for host, output in outputs.items():
        report, paths = _analyze(output, design)
        report["host"] = host
        report["run_prefix"] = design.hosts[host].run_prefix
        decision = report["decision"]
        identity = host_identity_problems(output, design, host)
        if identity:
            _halt(decision, "host-mismatch", identity)
        engine = engine_check(output, design, host)
        engines[host] = engine
        if engine["mismatched"]:
            _halt(
                decision,
                "engine-mismatch",
                {"expected": engine["expected"], "blocks": engine["mismatched"]},
            )
        if engine["unverified"]:
            _halt(decision, "engine-unverified", engine["unverified"])
        analyses[host] = HostAnalysis(report, paths)
    decisions: dict[str, dict[str, Any]] = {
        host: analyses[host].report["decision"] if host in analyses else _pending_host()
        for host in design.hosts
    }
    h2_sources = sorted(
        host
        for host, decision in decisions.items()
        if any(item["rule"] == "H2" for item in decision["halts"])
    )
    for host, decision in decisions.items():
        if h2_sources and host not in h2_sources:
            _halt(decision, "H2'", {"source_hosts": h2_sources})
    # A missing host leaves X1 "not evaluated" (never "not fired").
    x1 = evaluate_x1(design, analyses)
    if partial:
        for decision in decisions.values():
            decision["partial_input"] = True
            if decision["status"] != "halted":
                decision["status"] = "pending"
                decision["selected_jobs"] = None
                decision["fallback_jobs"] = None
    selected = {host: decision["selected_jobs"] for host, decision in decisions.items()}
    chosen = [value for value in selected.values() if value is not None]
    combined = {
        "schema": SCHEMA_V3,
        "label": LABEL,
        "design_id": design.design_id,
        "design_sha256": design.sha256,
        "partial": partial,
        "missing_hosts": missing,
        "outputs": {host: str(outputs[host]) if host in outputs else None for host in design.hosts},
        "decisions": decisions,
        "selected_jobs": selected,
        # v3 section 6.1: if the main experiment needs one value, the smaller one.
        "common_jobs_if_needed": min(chosen) if len(chosen) == len(design.hosts) else None,
        "x1": x1,
        "h2_joint": {"fired": bool(h2_sources), "source_hosts": h2_sources},
        "engines": engines,
        "clocks": {
            host: {
                f"{stage}/{block['index']}": block["monotonic_over_real"]
                for stage, content in analysis.report["stages"].items()
                for block in content["blocks"]
            }
            for host, analysis in analyses.items()
        },
        "infra_reexecutions": {
            host: _infra_column(analysis.report) for host, analysis in analyses.items()
        },
        "rules_evaluated": list(V3_RULES_EVALUATED),
    }
    return {"combined": combined, "hosts": {host: a.report for host, a in analyses.items()}}


def render_markdown_v3(combined: Mapping[str, Any]) -> str:
    """The two-host summary (v3 section 11). Counts and decisions only."""
    x1 = combined["x1"]
    lines = [
        f"# 동시 실행 벤치마크 2호스트 요약: {combined['design_id']}",
        "",
        f"라벨: {combined['label']}.",
        "호스트별 판정이며 합산 통계로 선정하지 않는다. oracle 값은 내보내지 않는다.",
        f"부분 입력: {combined['partial']}, "
        f"출력 없는 호스트: {combined['missing_hosts'] or '없음'}",
        "",
        "## 호스트별 판정",
        "",
        "| 호스트 | 상태 | 선택 jobs | 대체값 | 중단 조건 | 재실행 합계 | 재실행 셀 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for host, decision in combined["decisions"].items():
        infra = combined["infra_reexecutions"].get(host) or {}
        lines.append(
            f"| {host} | {decision['status']} | {_fmt(decision['selected_jobs'])} | "
            f"{_fmt(decision['fallback_jobs'])} | "
            f"{[item['rule'] for item in decision['halts']] or '없음'} | "
            f"{_fmt(infra.get('total'))} | {_fmt(infra.get('cells_with_reexecution'))} |"
        )
    inputs = x1["inputs"] or {}
    lines += [
        "",
        f"- 공통 jobs가 필요할 때(작은 값): {_fmt(combined['common_jobs_if_needed'])}",
        f"- H2′(합동 정지): {combined['h2_joint']['fired']}, "
        f"출처 {combined['h2_joint']['source_hosts']}",
        "",
        "## X1 교차 호스트 경로 일치 (jobs 배제 아님)",
        "",
        f"- 상태: {x1['status']}",
        f"- m_x {_fmt(inputs.get('m_x'))}, F {inputs.get('floors')}, "
        f"m_x − max F {_fmt(inputs.get('excess'))}, "
        f"한쪽만 timed_out·failed {_fmt(inputs.get('one_sided_congestion_cells'))}, "
        f"비교 불가 {_fmt(inputs.get('incomparable_cells'))}, "
        f"재실행 셀의 불일치 {_fmt(inputs.get('differing_cells_with_reexecution'))}",
        f"- 미평가 사유: {x1['reasons_not_evaluated'] or '없음'}",
        f"- 귀결: {x1['consequence']}",
        "",
        "## 엔진",
        "",
    ]
    for host, engine in combined["engines"].items():
        lines.append(
            f"- {host}: 설계 {engine['expected']}, 불일치 {engine['mismatched'] or '없음'}, "
            f"미확인 {engine['unverified'] or '없음'}"
        )
    lines += ["", "## 평가한 규칙", ""]
    lines += [f"- {item}" for item in combined["rules_evaluated"]]
    return "\n".join(lines) + "\n"


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def render_markdown(report: Mapping[str, Any]) -> str:
    decision = report["decision"]
    lines = [
        f"# 동시 실행 벤치마크 결과: {report['design_id']}",
        "",
        f"라벨: {report['label']}.",
        "실험 결과가 아니며 EXP 데이터와 합치지 않는다.",
        "판정은 oracle 값을 쓰지 않는다(경로 비교에 판정값 동일 여부만 쓴다).",
        "처리량은 실시간 기준이다. 제한시간 비교 값은 monotonic이다.",
        "",
        "## 판정",
        "",
        f"- 상태: {decision['status']}",
        f"- 선택 수준: {_fmt(decision['selected_jobs'])}",
        f"- 대체값(H3, 비교로 고른 값 아님): {_fmt(decision['fallback_jobs'])}",
        f"- 측정 무효 단계(외부 탓 멈춤, 재실행은 별도 승인): {_fmt(decision['stage_invalid'])}",
        f"- 중단 조건: {[item['rule'] for item in decision['halts']] or '없음'}",
        f"- 첫 오류 미확인 abort(H4): {decision['h4_first_error_unconfirmed']}",
        f"- 재발 abort: {len(decision['recurrences']['same_input'])}, "
        f"다시 지나간 횟수 {decision['recurrences']['passes_elsewhere']}, "
        f"재발률 95% 상한 {_fmt(decision['recurrences']['recurrence_upper95'], 3)}",
        f"- 같은 case가 다른 위치에서 abort(H2 아님): "
        f"{decision['recurrences']['same_case_elsewhere']}",
    ]
    for name, verdict in decision["stages"].items():
        rules = sorted({item["rule"] for item in verdict["violations"]})
        ref_rules = sorted({item["rule"] for item in verdict["ref_violations"]})
        lines.append(
            f"- 단계 {name} ({verdict['ref_jobs']}→{verdict['high_jobs']}): "
            f"통과 {verdict['passed']}, 측정 무효 {verdict['stage_invalid']}, "
            f"배제 {rules or '없음'}, 기준 수준 위반 {ref_rules or '없음'}"
            f"{' (취소하고 내림)' if verdict['ref_cancelled'] else ''}, rho {verdict['rho']}, "
            f"정상 비율 반영 이득 {_fmt(verdict['adjusted_gain'])}, "
            f"드리프트 {_fmt(verdict['drift'])}, 바닥값 F {verdict['floor']}"
        )
    for stage, content in report["stages"].items():
        lines += [
            "",
            f"## 단계 {stage}",
            "",
            "| 블록 | jobs | 실시간 h | G | 포화 실행/h | 정상/h | 노출/h | abort | 불일치 m | "
            "비교 불가: 기준 블록 셀 없음 | 비교 불가: 이 블록 셀 없음 | "
            "CPU | iowait | 최소 가용 GiB | docker ps p50 s | 중단 사유 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | "
            "--- | --- |",
        ]
        verdict = decision["stages"].get(stage)
        for position, block in enumerate(content["blocks"]):
            host = block["host"]
            available = host.get("memory_available_min_bytes")
            g_blocks = verdict["g_blocks"] if verdict else ()
            lines.append(
                f"| {block['index']} | {block['jobs']} | {block['real_seconds'] / 3600:.2f} | "
                f"{_fmt(g_blocks[position] if position < len(g_blocks) else None)} | "
                f"{_fmt(block['saturated_exec_per_real_hour'], 0)} | "
                f"{_fmt(block['normal_campaigns_per_real_hour'])} | "
                f"{_fmt(block['exposure_per_real_hour'])} | {len(block['aborts'])} | "
                f"{block['determinism']['m']} | "
                f"{block['determinism']['uncomparable_reference_missing']} | "
                f"{block['determinism']['uncomparable_block_missing']} | "
                f"{_fmt(host.get('cpu_busy_fraction'))} | "
                f"{_fmt(host.get('cpu_iowait_fraction'))} | "
                f"{_fmt(available / 2**30 if available else None)} | "
                f"{_fmt(host.get('docker_ps_seconds_p50'))} | {block['stopped_reason'] or '—'} |"
            )
        lines += [
            "",
            "| jobs | arm | 캠페인 | abort | 노출 | timed_out | 부적격 step | "
            "target p50/p99/p99.9 s | 셀 monotonic 최대 s | 실시간 s/step |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for jobs, level in content["levels"].items():
            for arm_name, arm in level["arms"].items():
                lines.append(
                    f"| {jobs} | {arm_name} | {arm['campaigns']} | {arm['aborts']} | "
                    f"{_fmt(arm['exposure'])} | {arm['timed_out']} | {arm['ineligible_steps']} | "
                    f"{_fmt(arm['target_seconds_p50'])}/{_fmt(arm['target_seconds_p99'])}/"
                    f"{_fmt(arm['target_seconds_p999'])} | {_fmt(arm['cell_monotonic_max'], 0)} | "
                    f"{_fmt(arm['real_seconds_per_step'])} |"
                )
        lines += ["", "### abort", ""]
        aborts = [(block["index"], item) for block in content["blocks"] for item in block["aborts"]]
        if not aborts:
            lines.append("없음.")
        for index, item in aborts:
            first = item["first_error"]
            coincidence = item.get("coincidence") or {}
            lines.append(
                f"- 블록 {index} `{item['run_id']}` step {item['step_index']}: {item['category']}, "
                f"첫 오류 {first['status']}: {first['message'] or '—'}; "
                f"±{COINCIDENCE_SECONDS:.0f} s 다른 abort {coincidence.get('other_aborts')}, "
                f"입력 크기 순위 {_fmt(item['entries_rank_in_cell'])}"
            )
    return "\n".join(lines) + "\n"


def render_host_markdown_v3(report: Mapping[str, Any]) -> str:
    """One host's v2-format report plus V7''s numerator and V10''s clocks (design v3)."""
    lines = [
        render_markdown(report).rstrip("\n"),
        "",
        f"## v3 추가 (호스트 {report['host']}, 접두 {report['run_prefix']})",
        "",
        "| 단계 | jobs | arm | timed_out | 인프라 재실행 | V7′ 분자 | 재실행 셀 | "
        "재실행 미확인 셀 | 셀 monotonic 최대 s | 셀 실시간 최대 s | "
        "시계 미측정 셀 (mono/real) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for stage, content in report["stages"].items():
        for jobs, level in content["levels"].items():
            for name, arm in level["arms"].items():
                unmeasured = arm["cell_clock_unmeasured"]
                lines.append(
                    f"| {stage} | {jobs} | {name} | {arm['timed_out']} | "
                    f"{arm['infra_reexecutions']} | {arm['v7_numerator']} | "
                    f"{arm['cells_with_reexecution']} | {arm['infra_reexecutions_unmeasured']} | "
                    f"{_fmt(arm['cell_monotonic_max'], 0)} | {_fmt(arm['cell_real_max'], 0)} | "
                    f"{unmeasured['monotonic']}/{unmeasured['realtime']} |"
                )
            lines.append(
                f"| {stage} | {jobs} | 수준 합계 | {level['timed_out']} | "
                f"{level['infra_reexecutions']} | {level['v7_numerator']} | — | — | — | — | — |"
            )
    lines += [
        "",
        "| 단계 | 블록 | 불일치 m | 재실행 셀의 불일치 (보고 전용) |",
        "| --- | --- | --- | --- |",
    ]
    for stage, content in report["stages"].items():
        for block in content["blocks"]:
            determinism = block["determinism"]
            lines.append(
                f"| {stage} | {block['index']} | {determinism['m']} | "
                f"{determinism.get('differing_cells_with_reexecution', '—')} |"
            )
    return "\n".join(lines) + "\n"


def _write_report(directory: Path, name_json: str, name_md: str, value: Any, md: str) -> None:
    (directory / name_json).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (directory / name_md).write_text(md, encoding="utf-8")


def _host_outputs(parser: argparse.ArgumentParser, items: Sequence[str]) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    for item in items:
        host, separator, directory = item.partition("=")
        if not separator or not host or not directory:
            parser.error(f"--host-output takes HOST=DIR, not {item!r}")
        if host in outputs:
            parser.error(f"--host-output names {host} twice")
        outputs[host] = Path(directory)
    return outputs


def main_v3(args: argparse.Namespace, parser: argparse.ArgumentParser, design: Design) -> int:
    """Design v3: one output tree per host, a per-host report in each, a combined summary.

    With ``--partial`` only the combined summary is written: no per-host report, so the driver's
    stage gate (which reads that report) cannot pass a host on partial input.
    """
    if args.output is not None:
        parser.error("a v3 design takes --host-output HOST=DIR per host, not --output")
    if args.combined_output is None:
        parser.error("a v3 design needs --combined-output DIR for the two-host summary")
    outputs = _host_outputs(parser, args.host_output or ())
    try:
        result = analyze_v3(design, outputs, partial=args.partial)
    except ValueError as error:
        parser.error(str(error))
    combined = result["combined"]
    if not args.partial:
        for host, report in result["hosts"].items():
            _write_report(
                outputs[host], REPORT_JSON, REPORT_MD, report, render_host_markdown_v3(report)
            )
    args.combined_output.mkdir(parents=True, exist_ok=True)
    _write_report(
        args.combined_output, REPORT_V3_JSON, REPORT_V3_MD, combined, render_markdown_v3(combined)
    )
    for host, decision in combined["decisions"].items():
        print(
            f"{host}: status={decision['status']} selected_jobs={decision['selected_jobs']} "
            f"halts={[item['rule'] for item in decision['halts']]}"
        )
    print(f"X1={combined['x1']['status']}; wrote {args.combined_output / REPORT_V3_JSON}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="the benchmark output tree (design v2)")
    parser.add_argument(
        "--host-output",
        action="append",
        metavar="HOST=DIR",
        help="design v3: one host's output tree; repeat for every host of the design",
    )
    parser.add_argument(
        "--combined-output", type=Path, help="design v3: directory for the two-host summary"
    )
    parser.add_argument(
        "--partial",
        action="store_true",
        help="design v3: analyze without some hosts; every host stays pending, X1 not evaluated",
    )
    args = parser.parse_args(argv)
    design = load_design(args.design)
    if design.is_v3:
        return main_v3(args, parser, design)
    if args.host_output or args.combined_output is not None or args.partial:
        parser.error("--host-output, --combined-output and --partial are for a v3 design")
    if args.output is None:
        parser.error("the following arguments are required: --output")
    report = analyze(args.output, design)
    (args.output / REPORT_JSON).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output / REPORT_MD).write_text(render_markdown(report), encoding="utf-8")
    decision = report["decision"]
    print(
        f"status={decision['status']} selected_jobs={decision['selected_jobs']} "
        f"halts={[item['rule'] for item in decision['halts']]}; wrote {args.output / REPORT_JSON}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

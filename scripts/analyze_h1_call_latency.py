"""Oracle-blind comparison of abnormal Docker broker calls in all H1 campaigns.

The broker records only unusual calls (slow >=2 s, timeout, truncation, and
nonroutine nonzero). Every invocation is counted in its summary.calls. Thus
latency quantiles of logged calls are *not* quantiles of all Docker calls.
This is descriptive host-call timing, not a new concurrency selection criterion.
Only reads concurrency-report.json, each block.json, and raw/*.calls.jsonl.
Never opens campaign reports, *.steps.jsonl, or any oracle outcome.

Usage:
    PYTHONPATH=src python3.12 -m scripts.analyze_h1_call_latency \
        --root /home/linux/inodefence-benchmarks/concurrency-scaling-v2 \
        > /home/linux/inodefence-evidence/h1-latency.json
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scripts.diagnose_concurrency_h1 import _call_path, _read_json


def _percentile(values: list[float], fraction: float) -> float | None:
    """Linear interpolation of the empirical sample; purely descriptive."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(math.floor(position))
    high = int(math.ceil(position))
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 6)


def _valid_duration(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _read_broker(path: Path) -> tuple[str, list[dict[str, Any]], dict[str, int] | None]:
    """Reject incomplete logs rather than treating missing calls as healthy."""
    if not path.is_file():
        return "missing", [], None
    try:
        with path.open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    except (OSError, ValueError, UnicodeError):
        return "unreadable", [], None
    if not rows or any(not isinstance(row, dict) for row in rows):
        return "unreadable", [], None
    header, summary = rows[0], rows[-1]
    calls = [row for row in rows if row.get("kind") == "call"]
    totals = summary.get("calls")
    totals_valid = (
        isinstance(totals, dict)
        and all(
            isinstance(op, str)
            and bool(op)
            and type(count) is int
            and count >= 0
            for op, count in totals.items()
        )
        and all(
            sum(1 for call in calls if call.get("op") == op) <= count
            for op, count in totals.items()
        )
        and all(call.get("op") in totals for call in calls)
    )
    complete = (
        totals_valid
        and header.get("kind") == "header"
        and summary.get("kind") == "summary"
        and isinstance(summary.get("recorded"), int)
        and not isinstance(summary.get("recorded"), bool)
        and summary["recorded"] == len(calls)
        and summary.get("dropped") == 0
        and summary.get("write_failures") == 0
        and isinstance(summary.get("dropped"), int)
        and isinstance(summary.get("write_failures"), int)
        and all(
            isinstance(call.get("op"), str)
            and call["op"]
            and _valid_duration(call.get("seconds_monotonic"))
            and isinstance(call.get("timed_out"), bool)
            for call in calls
        )
        and all(row.get("kind") in {"header", "call", "summary"} for row in rows)
    )
    if not complete:
        return "partial", [], None
    # Permit only host metadata; strip potentially sensitive stdout/stderr.
    return (
        "complete",
        [
            {
                "op": call["op"],
                "seconds": float(call["seconds_monotonic"]),
                "timed_out": call["timed_out"],
            }
            for call in calls
        ],
        dict(totals),
    )


def _summarize(
    groups: dict[tuple[Any, ...], list[dict[str, Any]]],
    totals: Counter[tuple[Any, ...]],
    labels: tuple[str, ...],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for key in sorted(set(groups) | set(totals)):
        calls = groups.get(key, [])
        values = [call["seconds"] for call in calls]
        total = totals.get(key, 0)
        results.append({
            **dict(zip(labels, key, strict=True)),
            "all_invocations_from_summary": total,
            "logged_unusual_calls": len(calls),
            "logged_unusual_fraction": round(len(calls) / total, 8) if total else None,
            "timed_out": sum(call["timed_out"] for call in calls),
            "at_least_2s_logged": sum(value >= 2 for value in values),
            "at_least_5s_logged": sum(value >= 5 for value in values),
            "at_least_10s_logged": sum(value >= 10 for value in values),
            "p50_logged_seconds": _percentile(values, 0.50),
            "p95_logged_seconds": _percentile(values, 0.95),
            "p99_logged_seconds": _percentile(values, 0.99),
            "max_logged_seconds": round(max(values), 6) if values else None,
        })
    return results


def analyze(root: Path) -> dict[str, Any]:
    report = _read_json(root / "concurrency-report.json")
    if report.get("design_id") != "concurrency-scaling-v2":
        raise ValueError("not a concurrency-scaling-v2 report")
    stage_records = report.get("stages", {})
    if not isinstance(stage_records, dict):
        raise ValueError("invalid stages")
    by_outcome: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    by_block: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    totals_outcome: Counter[tuple[Any, ...]] = Counter()
    totals_block: Counter[tuple[Any, ...]] = Counter()
    coverage: Counter[str] = Counter()
    dispositions: Counter[str] = Counter()
    timeout_campaigns: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for stage, stage_record in sorted(stage_records.items()):
        for block in stage_record["blocks"]:
            index, jobs = int(block["index"]), int(block["jobs"])
            block_dir = root / stage / f"block-{index}-j{jobs}"
            original = _read_json(block_dir / "block.json")
            original_by_id = {cell["run_id"]: cell for cell in original["cells"]}
            for cell in block["cells"]:
                run_id = cell["run_id"]
                unique_key = (str(stage), index, run_id)
                if unique_key in seen:
                    raise ValueError(f"duplicate campaign in one block: {run_id}")
                seen.add(unique_key)
                disposition = str(cell["disposition"])
                dispositions[disposition] += 1
                broker_path = _call_path(block_dir / "raw", original_by_id[run_id]["report"])
                state, calls, totals = _read_broker(broker_path)
                coverage[state] += 1
                if state != "complete":
                    continue
                assert totals is not None
                for op, invocations in totals.items():
                    totals_outcome[(jobs, disposition, op)] += invocations
                    totals_block[(str(stage), index, jobs, op)] += invocations
                count = 0
                for call in calls:
                    by_outcome[(jobs, disposition, call["op"])].append(call)
                    by_block[(str(stage), index, jobs, call["op"])].append(call)
                    count += int(call["timed_out"])
                if count:
                    timeout_campaigns.append({
                        "stage": stage,
                        "block": index,
                        "jobs": jobs,
                        "run_id": run_id,
                        "disposition": disposition,
                        "timeout_calls": count,
                    })
    return {
        "scope": (
            "all recorded benchmark campaigns; only unusual Docker broker calls are timed; "
            "all-invocation denominators use summary.calls; "
            "oracle sealed; descriptive, not H1/D21 or experiment-selection evidence"
        ),
        "design_id": report["design_id"],
        "original_decision": report.get("decision"),
        "campaigns_by_disposition": dict(sorted(dispositions.items())),
        "broker_coverage": dict(sorted(coverage.items())),
        "incomplete_broker_logs_excluded_from_latency": sum(
            value for name, value in coverage.items() if name != "complete"
        ),
        "latency_by_jobs_disposition_operation": _summarize(
            by_outcome, totals_outcome, ("jobs", "disposition", "operation")
        ),
        "latency_by_stage_block_jobs_operation": _summarize(
            by_block, totals_block, ("stage", "block", "jobs", "operation")
        ),
        "timeout_campaigns": timeout_campaigns,
        "limitations": [
            "BrokerCallLog records only unusual calls: >=2s or anomalous status; "
            "normal container start calls are excluded even when slow. "
            "p50/p95/p99_logged_seconds are conditional on recording and are NOT "
            "whole-operation latency quantiles.",
            "The same 'container inspect' operation occurs in runtime and cleanup; "
            "broker op strings alone cannot reliably identify each call site.",
            "Host-call timing does not establish Docker daemon/WSL2 root cause.",
            "All non-complete broker logs are excluded, not imputed as zero.",
            "This output does not read or incorporate oracle outcomes, "
            "and cannot alter the registered benchmark decision.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.root), indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

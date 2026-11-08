"""Read-only H1 abort correlation from the sealed concurrency benchmark.

Only ``concurrency-report.json``, ``block.json``, broker ``*.calls.jsonl`` and host
``events.jsonl`` are opened.  Campaign ``*.json`` and ``*.steps.jsonl`` (which hold
oracle outcomes) are never opened.  This is descriptive evidence, not a second
selection rule or a replacement for the registered benchmark analyzer.

Usage::

    python -m scripts.diagnose_concurrency_h1 --root /path/to/concurrency-scaling-v2

The JSON report goes to stdout; neither the source tree nor the raw archive is
modified.  If a broker log is missing, incomplete or dropped records, its
absence is reported as unknown, not as evidence of a healthy Docker daemon.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# D041 and concurrency-scaling-v2 §2: chosen before the benchmark ran.
PILOT_ABORT_COMBINATIONS = frozenset(
    {
        ("R-restart", 8110),
        ("D", 8110),
        ("S-u", 8110),
        ("S-u", 8102),
        ("R-restart", 8103),
        ("D", 8106),
    }
)
NEAR_END_SECONDS = 60.0


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _broker_calls(path: Path, ended_real: float) -> dict[str, Any]:
    """Read host broker metadata only; never follow paths named inside this file."""
    if not path.is_file():
        return {"coverage": "missing", "call_count": None, "near_end": []}
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError("non-object row")
    except (OSError, ValueError, json.JSONDecodeError):
        return {"coverage": "unreadable", "call_count": None, "near_end": []}
    header = rows[0] if rows else {}
    summary = rows[-1] if rows else {}
    calls = [row for row in rows if row.get("kind") == "call"]
    valid_summary = (
        header.get("kind") == "header"
        and summary.get("kind") == "summary"
        and isinstance(summary.get("dropped"), int)
        and isinstance(summary.get("write_failures"), int)
    )
    complete = valid_summary and summary["dropped"] == 0 and summary["write_failures"] == 0
    flags = Counter()
    operations = Counter()
    near_end: list[dict[str, Any]] = []
    for call in calls:
        operations[str(call.get("op"))] += 1
        for flag in ("timed_out", "truncated"):
            if call.get(flag) is True:
                flags[flag] += 1
        if call.get("returncode") not in (0, None):
            flags["nonzero"] += 1
        when = call.get("started_real")
        if isinstance(when, (int, float)) and abs(when - ended_real) <= NEAR_END_SECONDS:
            near_end.append(
                {
                    "op": call.get("op"),
                    "started_real": when,
                    "seconds_monotonic": call.get("seconds_monotonic"),
                    "returncode": call.get("returncode"),
                    "timed_out": call.get("timed_out"),
                    "truncated": call.get("truncated"),
                    "stderr": call.get("stderr"),
                }
            )
    return {
        "coverage": "complete" if complete else "partial",
        "call_count": len(calls),
        "recorded": summary.get("recorded") if valid_summary else None,
        "dropped": summary.get("dropped") if valid_summary else None,
        "write_failures": summary.get("write_failures") if valid_summary else None,
        "operations": dict(sorted(operations.items())),
        "flags": dict(sorted(flags.items())),
        "near_end": near_end,
    }


def _docker_events(path: Path, ended_real: float) -> dict[str, Any]:
    if not path.is_file():
        return {"coverage": "missing", "near_end": None}
    counts: Counter[str] = Counter()
    bad_rows = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, Mapping):
                raise ValueError("not an object")
            stamp = float(event["timeNano"]) / 1e9
            if abs(stamp - ended_real) <= NEAR_END_SECONDS:
                counts[str(event.get("Action") or event.get("status"))] += 1
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            bad_rows += 1
    return {
        "coverage": "partial" if bad_rows else "present",
        "bad_rows": bad_rows,
        "near_end": dict(sorted(counts.items())),
    }


def _call_path(raw: Path, relative_report: str) -> Path:
    """Resolve a broker filename from block metadata, without opening its report."""
    if not relative_report.endswith(".json"):
        raise ValueError("invalid report path in block.json")
    path = (raw / (relative_report.removesuffix(".json") + ".calls.jsonl")).resolve()
    if not path.is_relative_to(raw.resolve()):
        raise ValueError("broker log escapes the raw directory")
    return path


def _fraction(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    aborts = sum(cell["disposition"] == "abort" for cell in cells)
    return {
        "campaigns": len(cells),
        "aborts": aborts,
        "abort_fraction": aborts / len(cells) if cells else None,
    }


def diagnose(root: Path) -> dict[str, Any]:
    """Correlate the designated analyzer's H1 summary with host-only metadata."""
    report = _read_json(root / "concurrency-report.json")
    if report.get("design_id") != "concurrency-scaling-v2":
        raise ValueError("not a concurrency-scaling-v2 report")
    decision = report["decision"]
    cells: list[dict[str, Any]] = []
    for stage, stage_record in sorted(report["stages"].items()):
        for block in stage_record["blocks"]:
            index, jobs = int(block["index"]), int(block["jobs"])
            block_dir = root / stage / f"block-{index}-j{jobs}"
            original = _read_json(block_dir / "block.json")
            by_run = {cell["run_id"]: cell for cell in original["cells"]}
            raw = block_dir / "raw"
            for cell in block["cells"]:
                run_id = cell["run_id"]
                original_cell = by_run[run_id]
                item: dict[str, Any] = {
                    "stage": stage,
                    "block": index,
                    "jobs": jobs,
                    "run_id": run_id,
                    "arm": cell["arm"],
                    "seed": cell["seed"],
                    "disposition": cell["disposition"],
                    "ended_real": cell["ended_real"],
                    "pilot_abort_history": (cell["arm"], cell["seed"]) in PILOT_ABORT_COMBINATIONS,
                    "broker": _broker_calls(
                        _call_path(raw, original_cell["report"]), float(cell["ended_real"])
                    ),
                }
                if cell["disposition"] == "abort":
                    item["abort"] = cell["abort"]
                    item["events"] = _docker_events(
                        block_dir / "host" / "events.jsonl", float(cell["ended_real"])
                    )
                cells.append(item)
    jobs2 = [cell for cell in cells if cell["jobs"] == 2]
    excluded = [cell for cell in jobs2 if not cell["pilot_abort_history"]]
    by_jobs = {
        str(jobs): _fraction([cell for cell in cells if cell["jobs"] == jobs])
        for jobs in sorted({cell["jobs"] for cell in cells})
    }
    return {
        "scope": "host metadata only; oracle sealed; non-EXP demo benchmark",
        "source_decision": {
            "status": decision.get("status"),
            "halts": decision.get("halts"),
            "selected_jobs": decision.get("selected_jobs"),
            "fallback_jobs": decision.get("fallback_jobs"),
        },
        "by_jobs": by_jobs,
        "jobs2_pilot_history_excluded": _fraction(excluded),
        "broker_coverage": dict(
            sorted(Counter(cell["broker"]["coverage"] for cell in cells).items())
        ),
        "aborts": [cell for cell in cells if cell["disposition"] == "abort"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, required=True, help="benchmark output root (read only)"
    )
    args = parser.parse_args()
    print(json.dumps(diagnose(args.root), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()

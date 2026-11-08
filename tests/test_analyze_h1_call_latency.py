"""Synthetic host-broker tests; never read a campaign report or oracle file."""

import json
from pathlib import Path

from scripts.analyze_h1_call_latency import _percentile, _read_broker, analyze


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _broker(path: Path, seconds: list[float], *, timeout_last: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"kind": "header"}]
    for i, duration in enumerate(seconds):
        rows.append({
            "kind": "call",
            "op": "container inspect",
            "seconds_monotonic": duration,
            "timed_out": timeout_last and i == len(seconds) - 1,
            "stderr": "not to be emitted",
        })
    rows.append({
        "kind": "summary", "recorded": len(seconds), "dropped": 0, "write_failures": 0
    })
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_compare_normal_and_abort_without_opening_oracle(tmp_path: Path) -> None:
    root = tmp_path / "bench"
    block = root / "A" / "block-1-j2"
    _write(root / "concurrency-report.json", {
        "design_id": "concurrency-scaling-v2",
        "decision": {"status": "halted", "selected_jobs": None},
        "stages": {"A": {"blocks": [{
            "index": 1, "jobs": 2, "cells": [
                {"run_id": "normal", "disposition": "normal"},
                {"run_id": "abort", "disposition": "abort"},
            ]
        }]}}
    })
    _write(block / "block.json", {"cells": [
        {"run_id": "normal", "report": "normal.json"},
        {"run_id": "abort", "report": "abort.json"},
    ]})
    _broker(block / "raw" / "normal.calls.jsonl", [0.1, 0.2])
    _broker(block / "raw" / "abort.calls.jsonl", [0.1, 10.0], timeout_last=True)
    # If an oracle file is accidentally opened, decoding would fail.
    (block / "raw" / "abort.json").write_bytes(b"\xff\x00PRIVATE ORACLE")
    (block / "raw" / "abort.steps.jsonl").write_bytes(b"\xff\x00PRIVATE STEPS")
    result = analyze(root)
    assert result["campaigns_by_disposition"] == {"abort": 1, "normal": 1}
    assert result["broker_coverage"] == {"complete": 2}
    rows = {
        (row["disposition"], row["operation"]): row
        for row in result["latency_by_jobs_disposition_operation"]
    }
    assert rows[("normal", "container inspect")]["calls"] == 2
    assert rows[("normal", "container inspect")]["timed_out"] == 0
    assert rows[("abort", "container inspect")]["timed_out"] == 1
    assert rows[("abort", "container inspect")]["p50_seconds"] == 5.05
    assert result["timeout_campaigns"][0]["run_id"] == "abort"
    assert result["original_decision"]["status"] == "halted"
    assert "PRIVATE" not in json.dumps(result)


def test_missing_and_partial_are_excluded_not_counted_as_zero(tmp_path: Path) -> None:
    absent = tmp_path / "absent.calls.jsonl"
    assert _read_broker(absent) == ("missing", [])
    bad = tmp_path / "bad.calls.jsonl"
    bad.write_text("BAD JSON")
    assert _read_broker(bad) == ("unreadable", [])
    _broker(bad, [0.1])
    assert _read_broker(bad)[0] == "complete"
    rows = [json.loads(line) for line in bad.read_text().splitlines()]
    rows[-1]["dropped"] = 1
    bad.write_text("\n".join(json.dumps(row) for row in rows))
    assert _read_broker(bad) == ("partial", [])
    rows[-1]["dropped"] = 0
    rows[1]["seconds_monotonic"] = None
    bad.write_text("\n".join(json.dumps(row) for row in rows))
    assert _read_broker(bad) == ("partial", [])


def test_percentiles_are_descriptive_and_nonempty() -> None:
    assert _percentile([], 0.95) is None
    assert _percentile([2.0], 0.99) == 2.0
    assert _percentile([0.1, 10.0], 0.5) == 5.05

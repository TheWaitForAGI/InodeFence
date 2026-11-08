"""Oracle-blind host metadata correlation for the stopped concurrency benchmark."""

import json
from pathlib import Path

import pytest
from scripts.diagnose_concurrency_h1 import (
    _broker_calls,
    _call_path,
    _docker_events,
    _host_samples,
    _timeout_clusters,
    diagnose,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_h1_correlates_host_calls_without_opening_oracle_raw(tmp_path: Path) -> None:
    root = tmp_path / "bench"
    block_dir = root / "A" / "block-1-j2"
    run_id = "7.5.2-D-s8110"
    # Deliberately unreadable oracle file: the diagnostic must never open it.
    (block_dir / "raw").mkdir(parents=True)
    (block_dir / "raw" / f"{run_id}.json").write_text("PRIVATE ORACLE", encoding="utf-8")
    _write_json(
        root / "concurrency-report.json",
        {
            "design_id": "concurrency-scaling-v2",
            "decision": {
                "status": "halted",
                "halts": [{"rule": "H1", "detail": 0.33333}],
                "selected_jobs": None,
                "fallback_jobs": None,
            },
            "stages": {
                "A": {
                    "blocks": [
                        {
                            "index": 1,
                            "jobs": 2,
                            "cells": [
                                {
                                    "run_id": run_id,
                                    "arm": "D",
                                    "seed": 8110,
                                    "disposition": "abort",
                                    "ended_real": 100.0,
                                    "abort": {"first_error": {"status": "confirmed"}},
                                },
                                {
                                    "run_id": "ok",
                                    "arm": "D",
                                    "seed": 8102,
                                    "disposition": "normal",
                                    "ended_real": 100.0,
                                },
                            ],
                        }
                    ]
                }
            },
        },
    )
    _write_json(
        block_dir / "block.json",
        {
            "cells": [
                {"run_id": run_id, "report": f"{run_id}.json"},
                {"run_id": "ok", "report": "ok.json"},
            ]
        },
    )
    calls = [
        {"kind": "header", "format": 1},
        {
            "kind": "call",
            "op": "container inspect",
            "started_real": 99.0,
            "seconds_monotonic": 10.0,
            "returncode": -9,
            "timed_out": True,
            "truncated": False,
            "stderr": "daemon stalled",
        },
        {"kind": "summary", "recorded": 1, "dropped": 0, "write_failures": 0},
    ]
    call_path = block_dir / "raw" / f"{run_id}.calls.jsonl"
    call_path.write_text("\n".join(json.dumps(row) for row in calls), encoding="utf-8")
    events = block_dir / "host" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text(
        json.dumps({"Action": "destroy", "timeNano": 99_000_000_000}), encoding="utf-8"
    )

    result = diagnose(root)

    assert result["source_decision"]["selected_jobs"] is None
    assert result["by_jobs"]["2"] == {"campaigns": 2, "aborts": 1, "abort_fraction": 0.5}
    assert result["jobs2_pilot_history_excluded"] == {
        "campaigns": 1,
        "aborts": 0,
        "abort_fraction": 0.0,
    }
    assert result["broker_coverage"] == {"complete": 1, "missing": 1}
    abort = result["aborts"][0]
    assert abort["broker"]["flags"] == {"nonzero": 1, "timed_out": 1}
    assert abort["broker"]["near_end"][0]["stderr"] == "daemon stalled"
    assert abort["events"]["near_end"] == {"destroy": 1}
    assert result["docker_timeouts"][0]["op"] == "container inspect"
    assert result["simultaneous_docker_timeout_clusters"] == []
    assert result["host_docker_probe"][0]["coverage"] == "missing"


def test_missing_truncated_and_dropped_logs_are_not_treated_as_success(tmp_path: Path) -> None:
    path = tmp_path / "missing.calls.jsonl"
    assert _broker_calls(path, 0)["coverage"] == "missing"
    path.write_text('{"kind":"header"}\n', encoding="utf-8")
    assert _broker_calls(path, 0)["coverage"] == "partial"
    path.write_text('{"kind":"header"}\n{"kind":"summary","dropped":1,"write_failures":0}')
    assert _broker_calls(path, 0)["coverage"] == "partial"
    path.write_text("BAD JSON")
    assert _broker_calls(path, 0)["coverage"] == "unreadable"


def test_call_path_rejects_escape_and_never_reads_report(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    assert _call_path(raw, "cell.json") == raw / "cell.calls.jsonl"
    with pytest.raises(ValueError, match="escapes"):
        _call_path(raw, "../../outside.json")
    with pytest.raises(ValueError, match="invalid"):
        _call_path(raw, "cell.steps.jsonl")


def test_missing_and_malformed_docker_events_are_visible(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    assert _docker_events(path, 100)["coverage"] == "missing"
    path.write_text('{"Action":"start","timeNano":100000000000}\ninvalid')
    assert _docker_events(path, 100) == {
        "coverage": "partial",
        "bad_rows": 1,
        "near_end": {"start": 1},
    }


def test_broker_keeps_all_timeouts_not_only_near_abort(tmp_path: Path) -> None:
    path = tmp_path / "old.calls.jsonl"
    rows = [
        {"kind": "header"},
        {
            "kind": "call",
            "op": "container start",
            "started_real": 10.0,
            "seconds_monotonic": 10.01,
            "timed_out": True,
            "returncode": -9,
        },
        {"kind": "summary", "recorded": 1, "dropped": 0, "write_failures": 0},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    result = _broker_calls(path, ended_real=1000.0)
    assert result["coverage"] == "complete"
    assert result["near_end"] == []
    assert result["timeout_calls"] == [
        {
            "op": "container start",
            "started_real": 10.0,
            "seconds_monotonic": 10.01,
            "returncode": -9,
            "truncated": None,
        }
    ]


def test_simultaneous_timeout_clusters_are_block_local_and_nontransitive() -> None:
    def call(run_id: str, when: float, *, block: int = 1, stage: str = "A") -> dict:
        return {
            "stage": stage,
            "block": block,
            "jobs": 2,
            "run_id": run_id,
            "op": "container inspect",
            "started_real": when,
        }

    clusters = _timeout_clusters(
        [
            call("a", 100.0),
            call("b", 100.1),
            call("c", 100.2),  # must not join the cluster anchored at 100.0
            call("d", 100.21, block=2),
            call("e", 100.22, block=2),
            call("one", 105.0),
            call("one", 105.01),  # one campaign is not simultaneous cross-campaign
            call("f", 100.11, stage="B"),
            call("g", 100.12, stage="B"),
            call("unknown", 10.0, stage="B", block=3) | {"started_real": None},
        ]
    )
    assert len(clusters) == 3
    assert clusters[0]["distinct_campaigns"] == 2
    assert [member["run_id"] for member in clusters[0]["calls"]] == ["a", "b"]
    assert {(cluster["stage"], cluster["block"]) for cluster in clusters} == {
        ("A", 1),
        ("A", 2),
        ("B", 1),
    }


def test_host_sampler_reports_slow_docker_ps_and_bad_rows(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    assert _host_samples(path)["coverage"] == "missing"
    rows = [
        {"realtime": 100.0, "docker_ps_seconds": 0.1},
        {"realtime": 105.0, "docker_ps_seconds": 23.03},
        {"realtime": 110.0, "docker_ps_error": "timeout"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\nBAD", encoding="utf-8")
    result = _host_samples(path)
    assert result == {
        "coverage": "partial",
        "bad_rows": 1,
        "slow_docker_ps": [{"started_real": 105.0, "seconds": 23.03}],
    }

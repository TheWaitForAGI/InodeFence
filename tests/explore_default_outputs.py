"""Exploration result outputs of default-policy (v1) runs, for the byte-identity check.

``default_outputs`` builds ``result.json`` and ``summary.md`` for a few fixed default-policy loop
reports, through the explore hooks' common path (``build_campaign_result`` -> ``write_result`` ->
``render_summary``), with the provenance fixed. It uses only APIs that existed before
``--mutation-policy`` (main e1098d6), so the same function run against that tree produced
``tests/fixtures/explore-default-v1/outputs.json``; ``test_explore_mutation_policy`` compares the
current code's outputs against that file byte for byte.
"""

from __future__ import annotations

import base64
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

TAR = b"default-policy violating input"
PROGRESS_SCHEMA = "inodefence-live-progress-v1"


def _record(index: int, *, c1: bool = False, termination: str = "success") -> dict[str, Any]:
    return {
        "run_index": index,
        "outcome": "judged",
        "c0": False,
        "c1": c1,
        "c2": False,
        "termination": termination,
        "observation_complete": True,
    }


def _violation_input(index: int) -> dict[str, Any]:
    return {
        "run_index": index,
        "tar_sha256": sha256(TAR).hexdigest(),
        "tar_b64": base64.b64encode(TAR).decode(),
    }


def scenarios() -> dict[str, dict[str, Any]]:
    """Name -> (loop report, live progress snapshot or None, seed, budget)."""
    per_case = {
        "demo_report_schema": 4,
        "case_records": [_record(0), _record(1, termination="rejected"), _record(2, c1=True)],
        "violation_inputs": [_violation_input(2)],
    }
    streaming = {
        "demo_report_schema": 5,
        "streaming": True,
        "vocabulary_mode": "observed-names",
        "aggregate": {
            "runs_executed": 30,
            "terminations": {"success": 20, "rejected": 8, "failed": 2},
            "unjudged_steps": 2,
            "errors": 1,
        },
        "violation_cases": [],
        "violation_inputs": [],
    }
    progress = {
        "schema": PROGRESS_SCHEMA,
        "state": "finished",
        "runs_executed": 30,
        "terminations": {"success": 20, "rejected": 8, "failed": 2, "timed_out": 0},
    }
    unjudged_heavy = json.loads(json.dumps(streaming))
    unjudged_heavy["aggregate"]["unjudged_steps"] = 9
    return {
        "per-case": {"report": per_case, "progress": None, "seed": 1, "budget": 3},
        "streaming-live": {"report": streaming, "progress": progress, "seed": 7, "budget": 30},
        "streaming-no-live": {"report": streaming, "progress": None, "seed": 7, "budget": 30},
        "streaming-error": {
            "report": unjudged_heavy,
            "progress": progress,
            "seed": 7,
            "budget": 30,
        },
    }


def default_outputs(tmp: Path) -> dict[str, dict[str, str]]:
    """Scenario name -> {"result.json", "summary.md"} texts as the default path writes them."""
    import inodefence.drivers.explore_result as er
    import inodefence.drivers.run_target as rt
    from inodefence.target_result import load_target_result
    from inodefence.target_result_summary import render_summary

    er.engine_provenance = lambda image: rt.Provenance("b" * 40, False, image, None)  # type: ignore[assignment]
    prepared = rt.PreparedTargetImage(
        "node-tar",
        "7.5.23",
        "7.5.23",
        "inodefence-node-tar-registry:7.5.23",
        "sha256:" + "a" * 64,
        True,
    )
    outputs: dict[str, dict[str, str]] = {}
    for name, item in scenarios().items():
        live_dir = None
        if item["progress"] is not None:
            live_dir = tmp / name / "live"
            live_dir.mkdir(parents=True)
            (live_dir / "progress.json").write_text(json.dumps(item["progress"]), encoding="utf-8")
        result, tar_files = er.build_campaign_result(
            item["report"], prepared, seed=item["seed"], budget=item["budget"], live_dir=live_dir
        )
        path = er.write_result(tmp / name / "result", result, tar_files)
        outputs[name] = {
            "result.json": path.read_text(encoding="utf-8"),
            "summary.md": render_summary(
                load_target_result(path), source_name="result.json", inputs_verified=True
            ),
        }
    return outputs

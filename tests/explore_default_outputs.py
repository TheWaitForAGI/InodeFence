"""Result outputs of default runs (no ``--mutation-policy``), for the byte-identity check.

``default_outputs`` builds ``result.json`` and ``summary.md`` with the provenance fixed for:
a few node-tar exploration loop reports (the explore hooks' common path), one python-tarfile
exploration (its own axes, run image and preparation) and one verify cell (the fixture-regression
writer). It uses only APIs that main fccdf35 already had, so the same function run against that
tree produced ``tests/fixtures/explore-default-v1/outputs.json``; ``test_explore_mutation_policy``
compares the current code's outputs with that file byte for byte.
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

    original = er.engine_provenance
    er.engine_provenance = lambda image: rt.Provenance("b" * 40, False, image, None)  # type: ignore[assignment]
    try:
        outputs = _node_tar_outputs(tmp, er, rt)
        outputs["python-tarfile-explore"] = _python_tarfile_output(tmp, rt)
        outputs["verify-cell"] = _verify_output(tmp, rt)
    finally:
        er.engine_provenance = original  # type: ignore[assignment]
    return outputs


def _texts(path: Path) -> dict[str, str]:
    from inodefence.target_result import load_target_result
    from inodefence.target_result_summary import render_summary

    return {
        "result.json": path.read_text(encoding="utf-8"),
        "summary.md": render_summary(
            load_target_result(path), source_name="result.json", inputs_verified=True
        ),
    }


def _python_tarfile_output(tmp: Path, rt: Any) -> dict[str, str]:
    """python-tarfile exploration: its own axes, run image and preparation record."""
    import inodefence.drivers.explore_result as er
    from inodefence.drivers.python_tarfile import explore as pte
    from inodefence.drivers.python_tarfile.producer import ProducerImage

    prepared = rt.PreparedTargetImage(
        "python-tarfile", "3.12.7", "3.12.7", "python:3.12.7-slim", "sha256:" + "c" * 64, False
    )
    made = ProducerImage(
        "inodefence-python-tarfile:3.12.7", "sha256:" + "d" * 64, "3.12.7", "e" * 64, "f" * 64,
        "reused, checked",
    )  # fmt: skip
    report = {
        "demo_report_schema": 4,
        "runtime_version": "3.12.7",
        "extraction_filter": "data",
        "case_records": [_record(0), _record(1, termination="failed"), _record(2, c1=True)],
        "violation_inputs": [_violation_input(2)],
    }
    result, tar_files = pte.build_campaign_result(report, prepared, made, "data", seed=3, budget=3)
    return _texts(er.write_result(tmp / "python-tarfile" / "result", result, tar_files))


def _verify_output(tmp: Path, rt: Any) -> dict[str, str]:
    """One fixture-regression (verify) cell, written by the verify driver's own writer."""
    from inodefence.target_result import CaseVerdict, TargetAxes

    adapter = rt.load_adapter("node-tar")
    cell = rt.RunCell("7.5.23", TargetAxes(target_version="7.5.23"), "img:7.5.23")
    runs = [
        rt.CaseRun(CaseVerdict("fixture-a", "judged", None, False, False), b"tar-a", {"a": 1}),
        rt.CaseRun(CaseVerdict("fixture-b", "judged", None, True, False), b"tar-b", {"b": 2}),
    ]
    provenance = rt.Provenance("b" * 40, False, "img:7.5.23", "sha256:" + "a" * 64)
    result = rt.build_result("node-tar", adapter, cell, runs, provenance)
    return _texts(rt.write_result(tmp / "verify" / "7.5.23", result, runs))


def _node_tar_outputs(tmp: Path, er: Any, rt: Any) -> dict[str, dict[str, str]]:
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
        outputs[name] = _texts(er.write_result(tmp / name / "result", result, tar_files))
    return outputs

"""The python-tarfile controller mode: argument rules, forwarding, journalled run (no docker).

The run function is driven with the same local fake backend as the target tests (the real worker
under this interpreter), so the mode is exercised end to end except for the container runtime.
"""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import pytest
import scripts.container_controller as controller
import scripts.run_effect_demo as demo
from tests.test_python_tarfile_contained import IMAGE, _LocalBackend

from inodefence.generator import minimal_seed_corpus

MODE = demo.PYTHON_TARFILE_CAMPAIGN_MODE
RUNTIME = platform.python_version()


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    demo.add_demo_arguments(parser)
    parser.add_argument("mode")
    args = parser.parse_args(argv)
    demo.check_demo_arguments(parser, args)
    return args


def test_mode_requires_one_runtime_and_one_filter() -> None:
    args = _parse(["--runtime-version", "3.14.10", "--extraction-filter", "data", MODE])
    assert (args.runtime_version, args.extraction_filter) == ("3.14.10", "data")
    for argv in (
        [MODE],
        ["--runtime-version", "3.14.10", MODE],
        ["--extraction-filter", "data", MODE],
        ["--runtime-version", "latest", "--extraction-filter", "data", MODE],
        ["--runtime-version", "3.14.10", "--extraction-filter", "tar", MODE],
        ["--runtime-version", "3.14.10", "--extraction-filter", "data", demo.EXPLORE_DEMO_MODE],
    ):
        with pytest.raises(SystemExit):
            _parse(argv)


def test_runtime_and_filter_are_forwarded_by_the_host_broker() -> None:
    assert {"runtime_version", "extraction_filter"} <= set(demo.DEMO_FORWARDED_ARGUMENTS)
    assert MODE in demo.DEMO_MODES


def _args(budget: int) -> argparse.Namespace:
    return _parse(
        ["--runtime-version", RUNTIME, "--extraction-filter", "data", "--budget", str(budget), MODE]
    )


def test_controller_run_writes_report_and_step_journal(tmp_path: Path) -> None:
    budget = len(minimal_seed_corpus()) + 1
    evidence = tmp_path / "report.json"
    code = controller.run_native_python_tarfile_campaign(
        _LocalBackend(),  # type: ignore[arg-type]
        IMAGE,
        evidence,
        _args(budget),
    )
    assert code == 0
    report = json.loads(evidence.read_text())
    assert report["runtime_version"] == RUNTIME and report["extraction_filter"] == "data"
    assert len(report["case_records"]) == budget
    steps = controller.demo_steps_path(evidence).read_text().splitlines()
    assert len(steps) == budget


def test_controller_abort_is_recorded_not_invented(tmp_path: Path) -> None:
    evidence = tmp_path / "report.json"
    args = _parse(["--runtime-version", "0.0.1", "--extraction-filter", "data", MODE])
    code = controller.run_native_python_tarfile_campaign(
        _LocalBackend(),  # type: ignore[arg-type]
        IMAGE,
        evidence,
        args,
    )
    assert code == 1
    report = json.loads(evidence.read_text())
    assert "expected 0.0.1" in report["aborted"]["reason"]
    assert "case_records" not in report

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


# ---- additive only: existing modes, their argument gates and forwarding are unchanged ----


def test_exactly_one_mode_and_two_forwarded_arguments_were_added() -> None:
    assert demo.DEMO_MODES == (
        "effect-demo",
        demo.HISTORICAL_DEMO_MODE,
        demo.EXPLORE_DEMO_MODE,
        demo.DECOMPRESS_CAMPAIGN_MODE,
        demo.ORAS_GO_CAMPAIGN_MODE,
        MODE,
    )
    assert demo.DEMO_FORWARDED_ARGUMENTS == (
        *demo.DEMO_ARGUMENTS,
        "tar_version",
        "observer_integrity_policy",
        "sentinel_count",
        "sentinel_seed",
        "runtime_version",
        "extraction_filter",
    )


@pytest.mark.parametrize(
    "mode", [demo.EXPLORE_DEMO_MODE, demo.HISTORICAL_DEMO_MODE, demo.DECOMPRESS_CAMPAIGN_MODE]
)
def test_existing_modes_refuse_the_new_arguments(mode: str) -> None:
    extra = ["--tar-version", "7.5.2"] if mode != demo.DECOMPRESS_CAMPAIGN_MODE else []
    _parse([*extra, mode])  # unchanged: still parses as before
    with pytest.raises(SystemExit):
        _parse([*extra, "--extraction-filter", "data", mode])


def test_existing_gates_still_hold() -> None:
    with pytest.raises(SystemExit):  # explore still requires the node-tar version
        _parse([demo.EXPLORE_DEMO_MODE])
    with pytest.raises(SystemExit):  # tar-version is still node-tar only
        _parse(
            ["--tar-version", "7.5.2", "--runtime-version", "3.14.10"]
            + ["--extraction-filter", "data", MODE]
        )

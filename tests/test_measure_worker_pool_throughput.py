"""Tests for the throughput measurement script: planning + orchestration, no Docker."""

from pathlib import Path

import pytest
from scripts.measure_worker_pool_throughput import (
    _build_runners,
    main,
    measure,
    plan_cells,
)
from scripts.run_parallel_native import Arm, Cell, build_cells

from inodefence.evaluation.execution_parity import (
    CanonicalSnapshot,
    ParityStep,
    ParitySubject,
    ResetVerification,
)
from inodefence.evaluation.throughput import CampaignTiming, MethodMeasurement

DEFAULT = Arm("default", None, None)


def _cells() -> list[Cell]:
    return plan_cells("demo", [None], [DEFAULT], [123, 456], 20)


def _subject(label: str) -> ParitySubject:
    obj = ("extract/a", "regular", 1, 0o644, 1, 1000, 1000, None, "0" * 64)
    snap = CanonicalSnapshot("after", ("outside/sentinel",), (obj,), ())
    step = ParityStep(0, "case-a", (("C0", False),), (), snap, snap, 0)
    return ParitySubject(
        label, (step,), (("image_id", "sha256:" + "a" * 64),), (ResetVerification(0, False, False),)
    )


def _runner(method: str, wall: float, run_ids: list[str]):
    def run(cells, output_dir: Path):
        timings = tuple(CampaignTiming(rid, 123, "default", None, wall, 1, 0, 0) for rid in run_ids)
        measurement = MethodMeasurement(method, 2.0, wall, timings)
        subjects = {rid: _subject(method) for rid in run_ids}
        return measurement, subjects

    return run


def test_plan_cells_matches_build_cells() -> None:
    cells = _cells()
    assert [cell.run_id for cell in cells] == [
        cell.run_id for cell in build_cells("demo", [None], [DEFAULT], [123, 456], 20)
    ]
    assert {cell.run_id for cell in cells} == {"native-default-s123", "native-default-s456"}


def test_main_plan_prints_matrix(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["--mode", "demo", "--seeds", "123,456", "--arm", "default", "--budget", "20", "--plan"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "cells=2" in out
    assert "native-default-s123" in out
    assert "native-default-s456" in out


def test_measure_with_fake_runners(tmp_path: Path) -> None:
    cells = _cells()
    run_ids = [cell.run_id for cell in cells]
    per_case = _runner("per-case", 40.0, run_ids)
    worker_pool = _runner("worker-pool", 20.0, run_ids)
    report = measure(cells, per_case, worker_pool, tmp_path)
    summary = report["summary"]
    assert isinstance(summary, dict)
    assert summary["speedup"] == pytest.approx(2.0)
    assert summary["parity_passed"] is True
    assert summary["cells_compared"] == 2


def test_demo_rejects_versions() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "demo", "--versions", "7.5.2", "--seeds", "123", "--plan"])


def test_demo_historical_requires_versions() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "demo-historical", "--seeds", "123", "--plan"])


def test_build_runners_unavailable_raises_system_exit() -> None:
    # The worker pool runners are unavailable until the integration base: the module is
    # absent here (ImportError), or present-but-unwired on the stack (NotImplementedError).
    # Either way the loader must refuse clearly rather than crash.
    with pytest.raises(SystemExit) as excinfo:
        _build_runners(3)
    assert "worker pool" in str(excinfo.value)

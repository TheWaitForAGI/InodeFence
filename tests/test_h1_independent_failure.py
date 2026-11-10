"""Independent fault injection for child lifecycle on a runner exception."""

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from scripts import run_concurrency_benchmark as bench
from scripts.run_parallel_native import CellResult


def test_runner_exception_does_not_leave_started_child_running(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    children: list[subprocess.Popen[Any]] = []

    def runner(_cell: Any, _raw: Any, _env: Any, launch: Any) -> Any:
        child = launch(
            lambda: subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        )
        children.append(child)
        raise OSError("injected wait failure")

    run = bench.BlockRun(design, block, tmp_path, runner)
    try:
        with pytest.raises(OSError, match="injected wait failure"):
            run.run_one(block.cells[0])
        assert children[0].poll() is not None
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


def test_result_recording_failure_stops_later_launches(tmp_path: Path, monkeypatch: Any) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    launched: list[str] = []

    def runner(cell: Any, raw: Path, _env: Any, launch: Any) -> CellResult:
        launch(lambda: launched.append(cell.run_id))
        return CellResult(cell, 0, 0.01, raw / "e.json", False, raw / "log")

    def fail_paths(*_args: Any) -> Any:
        raise OSError("injected record failure")

    monkeypatch.setattr(bench, "cell_paths", fail_paths)
    run = bench.BlockRun(design, block, tmp_path, runner)
    with pytest.raises(OSError, match="injected record failure"):
        run.run_one(block.cells[0])
    run.run_one(block.cells[1])
    assert launched == [block.cells[0].run_id]
    assert "injected record failure" in (run.stopped_reason or "")

"""H1 startup failures stop the block and remain visible without Docker."""

from pathlib import Path
from typing import Any

from scripts import run_concurrency_benchmark as bench


def test_failed_process_launch_stops_and_records_block(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    attempts: list[str] = []

    def run_cell(cell: Any, _raw: Any, _env: Any, launch: Any) -> Any:
        def fail() -> None:
            attempts.append(cell.run_id)
            raise OSError("process creation failed")

        launch(fail)

    record = bench.BlockRun(design, block, tmp_path, run_cell).execute()
    assert len(attempts) == 1
    assert record["stop_kind"] == bench.STOP_EXTERNAL
    assert "OSError" in record["stopped_reason"]
    failed = [cell for cell in record["cells"] if cell.get("start_error")]
    assert len(failed) == 1
    assert failed[0]["state"] == "not-run"
    assert all(cell["state"] == "not-run" for cell in record["cells"])


def test_environment_failure_stops_without_launch(tmp_path: Path, monkeypatch: Any) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    launched: list[str] = []

    def fail_env(*_args: Any) -> Any:
        raise ValueError("bad environment")

    def never_launch(*_args: Any) -> Any:
        launched.append("started")
        raise AssertionError("launch should not occur")

    monkeypatch.setattr(bench, "cell_env", fail_env)
    run = bench.BlockRun(design, block, tmp_path, never_launch)
    run.run_one(block.cells[0])
    assert launched == []
    assert run.stop_kind == bench.STOP_EXTERNAL
    assert "ValueError: bad environment" in run.records[0]["start_error"]

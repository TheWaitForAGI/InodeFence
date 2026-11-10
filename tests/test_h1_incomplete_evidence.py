"""Incomplete H1 runs must retain the stop decision without becoming clean blocks."""

import json
import threading
from pathlib import Path
from typing import Any

import pytest
from scripts import analyze_concurrency_benchmark as analysis
from scripts import run_concurrency_benchmark as bench
from scripts.run_parallel_native import CellResult


def test_runner_exception_publishes_incomplete_record(tmp_path: Path, monkeypatch: Any) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    directory = tmp_path / block.stage / block.name
    directory.mkdir(parents=True)

    class Events:
        def terminate(self) -> None:
            pass

        def wait(self, timeout: float) -> int:
            return 0

    def sample(_run: Any, _path: Path, stop: threading.Event) -> None:
        stop.wait(5)

    def fail(_cell: Any, _raw: Any, _env: Any, _bash: Any, **kwargs: Any) -> Any:
        kwargs["popen"]()
        raise OSError("injected runner failure")

    class Process:
        pid = 123
        returncode = 0

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(bench, "_start_events", lambda _path: Events())
    monkeypatch.setattr(bench, "_sample_host", sample)
    monkeypatch.setattr(bench, "run_cell_with_watchdog", fail)
    monkeypatch.setattr(bench.subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(bench, "residual_resources", list)
    with pytest.raises(OSError, match="injected runner failure"):
        bench.run_block(design, block, directory, "bash")
    record = json.loads((directory / "block.incomplete.json").read_text())
    assert record["finished"] is False
    assert "injected runner failure" in record["stopped_reason"]
    assert record["stop_order"] is not None
    assert record["started_cells"]
    assert not (directory / bench.BLOCK_FILE).exists()
    assert bench.stage_state(tmp_path, block) == "incomplete"


def test_atomic_publication_never_replaces_evidence(tmp_path: Path) -> None:
    path = tmp_path / "block.incomplete.json"
    bench._publish_json(path, {"first": 1})
    with pytest.raises(FileExistsError):
        bench._publish_json(path, {"second": 2})
    assert json.loads(path.read_text()) == {"first": 1}
    assert sorted(item.name for item in tmp_path.iterdir()) == [path.name]


def test_failed_publication_leaves_no_partial_file(tmp_path: Path, monkeypatch: Any) -> None:
    def fail_link(*_args: Any) -> None:
        raise OSError("injected link failure")

    monkeypatch.setattr(bench.os, "link", fail_link)
    with pytest.raises(OSError, match="injected link failure"):
        bench._publish_json(tmp_path / bench.INCOMPLETE_BLOCK_FILE, {"finished": False})
    assert list(tmp_path.iterdir()) == []


def test_unknown_cleanup_stops_waiting_cells(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    log = tmp_path / "log"
    log.write_text("INODEFENCE_CLEANUP_UNKNOWN: test\n")
    launched: list[str] = []

    def runner(cell: Any, raw: Path, _env: Any, launch: Any) -> CellResult:
        launch(lambda: launched.append(cell.run_id))
        return CellResult(cell, 37, 1, raw / "e.json", False, log)

    run = bench.BlockRun(design, block, tmp_path, runner)
    run.run_one(block.cells[0])
    run.run_one(block.cells[1])
    assert launched == [block.cells[0].run_id]
    assert run.stop_kind == bench.STOP_EXTERNAL
    assert "cleanup resource state unknown" in (run.stopped_reason or "")


def test_missing_cell_log_cannot_be_treated_as_clean(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]

    def runner(cell: Any, raw: Path, _env: Any, launch: Any) -> CellResult:
        launch(lambda: None)
        return CellResult(cell, 0, 1, raw / "e.json", False, raw / "missing-log")

    run = bench.BlockRun(design, block, tmp_path, runner)
    run.require_logs = True
    with pytest.raises(OSError, match="cell log"):
        run.run_one(block.cells[0])
    assert run.stop_kind == bench.STOP_EXTERNAL


def test_incomplete_directory_halts_analysis_even_without_evidence_file(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "A")[0]
    (tmp_path / block.stage / block.name).mkdir(parents=True)
    decision = analysis.analyze(tmp_path, design)["decision"]
    assert decision["status"] == "halted"
    assert decision["selected_jobs"] is None
    assert decision["fallback_jobs"] is None
    assert decision["halts"][0]["rule"] == "incomplete-block"


def test_keyboard_interrupt_commits_stop_before_waiting_for_workers(
    tmp_path: Path, monkeypatch: Any
) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]

    def never_run(*_args: Any) -> CellResult:
        raise AssertionError("worker must not run")

    run = bench.BlockRun(design, block, tmp_path, never_run)
    observed: list[str | None] = []

    class Pool:
        def __init__(self, max_workers: int) -> None:
            pass

        def __enter__(self) -> "Pool":
            return self

        def __exit__(self, *_args: Any) -> None:
            observed.append(run.stopped_reason)

        def map(self, *_args: Any) -> Any:
            raise KeyboardInterrupt

    monkeypatch.setattr(bench, "ThreadPoolExecutor", Pool)
    with pytest.raises(KeyboardInterrupt):
        run.execute()
    assert observed[0] is not None


def test_keyboard_interrupt_publishes_incomplete(tmp_path: Path, monkeypatch: Any) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]

    def interrupt(*_args: Any) -> Any:
        raise KeyboardInterrupt("operator")

    monkeypatch.setattr(bench, "_run_block", interrupt)
    monkeypatch.setattr(bench, "residual_resources", list)
    with pytest.raises(KeyboardInterrupt):
        bench.run_block(design, block, tmp_path, "bash")
    record = json.loads((tmp_path / bench.INCOMPLETE_BLOCK_FILE).read_text())
    assert record["finished"] is False
    assert "KeyboardInterrupt" in record["stopped_reason"]

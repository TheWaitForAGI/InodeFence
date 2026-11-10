"""Deterministic H1 stop/start ordering checks without Docker."""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from scripts import run_concurrency_benchmark as bench
from scripts.run_parallel_native import Cell, CellResult


def test_stop_during_start_preparation_refuses_launch(tmp_path: Path, monkeypatch: Any) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "A")[0]
    entered = threading.Event()
    resume = threading.Event()
    launched = []
    original = bench.cell_env

    def paused_env(*args: Any) -> dict[str, str]:
        entered.set()
        assert resume.wait(5)
        return original(*args)

    def run_cell(cell: Cell, raw: Path, _env: dict[str, str], *gate: Any) -> CellResult:
        if gate:
            gate[0](lambda: launched.append(cell.run_id))
        else:
            launched.append(cell.run_id)
        return CellResult(cell, 0, 0.01, raw / "e.json", False, raw / "log")

    monkeypatch.setattr(bench, "cell_env", paused_env)
    run = bench.BlockRun(design, block, tmp_path, run_cell)
    worker = threading.Thread(target=run.run_one, args=(block.cells[0],))
    worker.start()
    assert entered.wait(5)
    run.request_stop("sampler stopped", bench.STOP_EXTERNAL)
    resume.set()
    worker.join(5)
    assert not worker.is_alive()
    assert launched == []
    assert run.records[0]["state"] == "not-run"
    assert run.stop_order < run.records[0]["decision_order"]


@pytest.mark.parametrize("stop_source", ["watchdog", "threshold", "sampler"])
def test_stop_source_precedes_waiting_start(
    tmp_path: Path, monkeypatch: Any, stop_source: str
) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "A")[0]
    waiting, release = threading.Event(), threading.Event()
    launches: list[str] = []
    original = bench.cell_env
    waiting_cell = block.cells[7]

    def paused_env(cell: Cell, *args: Any) -> dict[str, str]:
        if cell == waiting_cell:
            waiting.set()
            assert release.wait(5)
        return original(cell, *args)

    def run_cell(cell: Cell, raw: Path, _env: dict[str, str], launch: Any) -> CellResult:
        launch(lambda: launches.append(cell.run_id))
        code = bench.WATCHDOG_RETURNCODE if stop_source == "watchdog" else 1
        return CellResult(cell, code, 0.01, raw / "e.json", False, raw / "log")

    monkeypatch.setattr(bench, "cell_env", paused_env)
    run = bench.BlockRun(design, block, tmp_path, run_cell)
    worker = threading.Thread(target=run.run_one, args=(waiting_cell,))
    worker.start()
    assert waiting.wait(5)
    if stop_source == "sampler":
        run.request_stop("host sampler failed", bench.STOP_EXTERNAL)
    else:
        count = 6 if stop_source == "threshold" else 1
        for cell in block.cells[:count]:
            run.run_one(cell)
    stop_order = run.stop_order
    release.set()
    worker.join(5)
    assert not worker.is_alive()
    assert waiting_cell.run_id not in launches
    denied = next(record for record in run.records if record["run_id"] == waiting_cell.run_id)
    assert denied["state"] == "not-run"
    assert stop_order is not None and stop_order < denied["decision_order"]
    assert all(r["start_order"] < stop_order for r in run.records if r["state"] == "ran")
    assert run.stop_kind == (bench.STOP_EXTERNAL if stop_source == "sampler" else bench.STOP_LEVEL)
    assert (
        "watchdog"
        if stop_source == "watchdog"
        else "6 cells"
        if stop_source == "threshold"
        else "sampler"
    ) in (run.stopped_reason or "")


def test_running_start_finishes_before_stop_without_blocking_completion(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "A")[0]
    creating, allow_create, running, finish, stopped = (threading.Event() for _ in range(5))

    def run_cell(cell: Cell, raw: Path, _env: dict[str, str], launch: Any) -> CellResult:
        def start() -> None:
            creating.set()
            assert allow_create.wait(5)

        launch(start)
        running.set()
        assert finish.wait(5)
        return CellResult(cell, 0, 0.01, raw / "e.json", False, raw / "log")

    run = bench.BlockRun(design, block, tmp_path, run_cell)
    worker = threading.Thread(target=run.run_one, args=(block.cells[0],))
    worker.start()
    assert creating.wait(5)

    def stop() -> None:
        run.request_stop("sampler", bench.STOP_EXTERNAL)
        stopped.set()

    stopper = threading.Thread(target=stop)
    stopper.start()
    allow_create.set()
    assert running.wait(5)
    assert stopped.wait(5)  # Running work never holds the lock.
    run.request_stop("later watchdog", bench.STOP_LEVEL)
    assert run.stopped_reason == "sampler"
    finish.set()
    worker.join(5)
    stopper.join(5)
    assert not worker.is_alive() and not stopper.is_alive()
    record = run.records[0]
    assert record["state"] == "ran"
    assert record["start_order"] < run.stop_order
    run.run_one(block.cells[1])
    assert run.records[1]["state"] == "not-run"
    assert run.stop_order < run.records[1]["decision_order"]


def test_simultaneous_nonzero_results_commit_single_threshold_stop(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "A")[0]
    all_started = threading.Barrier(6, timeout=5)

    def run_cell(cell: Cell, raw: Path, _env: dict[str, str], launch: Any) -> CellResult:
        launch(lambda: None)
        all_started.wait()
        return CellResult(cell, 1, 0.01, raw / "e.json", False, raw / "log")

    run = bench.BlockRun(design, block, tmp_path, run_cell)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(run.run_one, block.cells[:6]))
    assert run.nonzero_cells == 6
    assert run.stopped_reason == "6 cells exited nonzero"
    assert len(run.records) == 6
    assert all(record["start_order"] < run.stop_order for record in run.records)
    run.run_one(block.cells[6])
    assert run.records[-1]["state"] == "not-run"


@pytest.mark.parametrize("source", ["watchdog", "threshold"])
def test_stop_commit_blocks_competing_launch(tmp_path: Path, monkeypatch: Any, source: str) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "A")[0]
    committing, release, competing = (threading.Event() for _ in range(3))
    launches: list[str] = []
    next_cell = block.cells[7]
    original_env = bench.cell_env

    def cell_env(cell: Cell, *args: Any) -> dict[str, str]:
        if cell == next_cell:
            competing.set()
        return original_env(cell, *args)

    def run_cell(cell: Cell, raw: Path, _env: dict[str, str], launch: Any) -> CellResult:
        launch(lambda: launches.append(cell.run_id))
        code = bench.WATCHDOG_RETURNCODE if source == "watchdog" else 1
        return CellResult(cell, code, 0.01, raw / "e.json", False, raw / "log")

    monkeypatch.setattr(bench, "cell_env", cell_env)
    run = bench.BlockRun(design, block, tmp_path, run_cell)
    if source == "threshold":
        for cell in block.cells[:5]:
            run.run_one(cell)
    original_stop = run._stop_locked

    def paused_stop(reason: str, kind: str) -> None:
        committing.set()
        assert release.wait(5)
        original_stop(reason, kind)

    monkeypatch.setattr(run, "_stop_locked", paused_stop)
    finishing = threading.Thread(target=run.run_one, args=(block.cells[5],))
    finishing.start()
    assert committing.wait(5)
    contender = threading.Thread(target=run.run_one, args=(next_cell,))
    contender.start()
    assert competing.wait(5)
    release.set()
    finishing.join(5)
    contender.join(5)
    assert not finishing.is_alive() and not contender.is_alive()
    assert next_cell.run_id not in launches
    denied = next(r for r in run.records if r["run_id"] == next_cell.run_id)
    assert denied["state"] == "not-run"
    assert run.stop_order < denied["decision_order"]


def test_real_watchdog_launch_wiring_denies_popen_after_sampler_stop(
    tmp_path: Path, monkeypatch: Any
) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    stopped = threading.Event()
    launches: list[Any] = []
    original_env = bench.cell_env

    class Events:
        def terminate(self) -> None:
            pass

        def wait(self, timeout: float) -> int:
            return 0

    def sample(run: bench.BlockRun, _path: Path, done: threading.Event) -> None:
        run.request_stop("sampler", bench.STOP_EXTERNAL)
        stopped.set()
        assert done.wait(5)

    def cell_env(*args: Any) -> dict[str, str]:
        assert stopped.wait(5)
        return original_env(*args)

    monkeypatch.setattr(bench, "_start_events", lambda _path: Events())
    monkeypatch.setattr(bench, "_sample_host", sample)
    monkeypatch.setattr(bench, "residual_resources", list)
    monkeypatch.setattr(bench, "cell_env", cell_env)
    monkeypatch.setattr(bench.subprocess, "Popen", lambda *a, **k: launches.append((a, k)))
    record = bench.run_block(design, block, tmp_path, "bash")
    assert launches == []
    assert record["stopped_reason"] == "sampler"
    assert all(cell["state"] == "not-run" for cell in record["cells"])
    assert all(record["stop_order"] < cell["decision_order"] for cell in record["cells"])

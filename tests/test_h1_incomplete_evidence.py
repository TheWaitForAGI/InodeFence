"""Incomplete H1 runs must retain the stop decision without becoming clean blocks."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from scripts import analyze_concurrency_benchmark as analysis
from scripts import run_concurrency_benchmark as bench
from scripts.run_parallel_native import CellResult

from inodefence.execution import start_gate


def clean_fake_popen(*_args: Any, **kwargs: Any) -> object:
    """A fake cell child whose cleanup was verified: its S verdict is already on disk.

    It is called under the gate lock (as Popen is), so it writes the verdict
    file directly instead of taking the lock like a real child does later.
    """
    directory = Path(kwargs["env"][start_gate.GATE_DIR_ENV])
    (directory / f"{kwargs['env'][start_gate.GATE_CELL_ENV]}.verdict").write_text("S\n")
    return object()


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

    # The started "child" stays alive: it keeps the inherited lifetime lock, as a
    # real child does until the runner's exception path terminates it.
    held: list[int] = []

    def live_child(*_args: Any, **kwargs: Any) -> Process:
        held.append(os.dup(kwargs["pass_fds"][-1]))
        return Process()

    monkeypatch.setattr(bench, "_start_events", lambda _path: Events())
    monkeypatch.setattr(bench, "_sample_host", sample)
    monkeypatch.setattr(bench, "run_cell_with_watchdog", fail)
    monkeypatch.setattr(bench.subprocess, "Popen", live_child)
    monkeypatch.setattr(bench, "residual_resources", list)
    try:
        with pytest.raises(OSError, match="injected runner failure"):
            bench.run_block(design, block, directory, "bash")
    finally:
        for fd in held:
            os.close(fd)
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
    with pytest.raises(RuntimeError, match="cleanup resource state unknown"):
        run.run_one(block.cells[0])
    run.run_one(block.cells[1])
    assert launched == [block.cells[0].run_id]
    assert run.stop_kind == bench.STOP_EXTERNAL
    assert "cleanup resource state unknown" in (run.stopped_reason or "")


def test_cleanup_unknown_blocks_launch_before_runner_returns(tmp_path: Path) -> None:
    """The first cell's child commits U through the gate and keeps running.

    The child is a real process started through ``StartGate``; it records U the
    way local_node_tar_smoke.sh does (start_gate.py record U, then the marker),
    reports over a pipe and then blocks until released. The second cell is
    attempted while the first runner is still waiting for its child.
    """
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    gate_script = Path(start_gate.__file__).resolve()
    child = (
        "import subprocess, sys\n"
        "rc = subprocess.call([sys.executable, '-I', sys.argv[1], 'record', 'U', 'test'])\n"
        "print('INODEFENCE_CLEANUP_UNKNOWN: test', file=sys.stderr, flush=True)\n"
        "print('recorded', rc, flush=True)\n"
        "sys.stdin.read()\n"
    )
    recorded = threading.Event()
    launches: list[str] = []
    gate = start_gate.StartGate(tmp_path / "start-gate")

    def runner(cell: Any, raw: Path, _env: Any, launch: Any) -> CellResult:
        log = tmp_path / f"{cell.run_id}.log"
        with log.open("w") as stream:
            process = launch(
                lambda: gate.try_start(
                    cell.run_id,
                    subprocess.Popen,
                    ([sys.executable, "-I", "-c", child, str(gate_script)],),
                    {
                        "stdin": subprocess.PIPE,
                        "stdout": subprocess.PIPE,
                        "stderr": stream,
                        "text": True,
                    },
                )
            )
            launches.append(cell.run_id)
            assert process.stdout.readline() == "recorded 0\n"
            recorded.set()
            assert release.wait(30)
            process.stdin.close()
            process.wait(timeout=30)
        return CellResult(cell, process.returncode, 1, raw / "e.json", False, log)

    release = threading.Event()
    run = bench.BlockRun(design, block, tmp_path, runner)
    run.gate = gate
    errors: list[BaseException] = []

    def run_first() -> None:
        try:
            run.run_one(block.cells[0])
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=run_first)
    first.start()
    try:
        assert recorded.wait(30)
        run.run_one(block.cells[1])  # the first runner has not returned
    finally:
        release.set()
        first.join(30)
    assert launches == [block.cells[0].run_id]
    assert run.records[0] == {
        "run_id": block.cells[1].run_id,
        "state": "not-run",
        "decision_order": 3,
    }
    assert run.stop_kind == bench.STOP_EXTERNAL
    assert run.stop_order == 2
    assert "cleanup resource state unknown: test" in (run.stopped_reason or "")
    assert len(errors) == 1 and "cleanup resource state unknown" in str(errors[0])


def test_watchdog_gate_reason_keeps_level_stop(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    gate = start_gate.StartGate(tmp_path / "start-gate")

    def runner(cell: Any, raw: Path, _env: Any, launch: Any) -> CellResult:
        process = launch(lambda: gate.try_start(cell.run_id, subprocess.Popen, (["true"],), {}))
        process.wait(timeout=30)
        gate.mark_unknown(cell.run_id, bench.WATCHDOG_GATE_REASON)
        log = tmp_path / f"{cell.run_id}.log"
        log.write_text("")
        return CellResult(cell, bench.WATCHDOG_RETURNCODE, 1, raw / "e.json", False, log)

    run = bench.BlockRun(design, block, tmp_path, runner)
    run.gate = gate
    with pytest.raises(RuntimeError, match="watchdog terminated"):
        run.run_one(block.cells[0])
    assert run.stop_kind == bench.STOP_LEVEL
    run.run_one(block.cells[1])
    assert run.records[-1]["state"] == "not-run"


def test_cell_without_verdict_is_an_external_stop(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    gate = start_gate.StartGate(tmp_path / "start-gate")

    def runner(cell: Any, raw: Path, _env: Any, launch: Any) -> CellResult:
        process = launch(lambda: gate.try_start(cell.run_id, subprocess.Popen, (["true"],), {}))
        process.wait(timeout=30)
        log = tmp_path / f"{cell.run_id}.log"
        log.write_text("")
        return CellResult(cell, 0, 1, raw / "e.json", False, log)

    run = bench.BlockRun(design, block, tmp_path, runner)
    run.gate = gate
    with pytest.raises(RuntimeError, match="exited without a cleanup verdict"):
        run.run_one(block.cells[0])
    assert run.stop_kind == bench.STOP_EXTERNAL
    assert gate.verdict(block.cells[0].run_id) is not None
    assert gate.verdict(block.cells[0].run_id)[0] == "U"


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


def test_designed_stop_is_not_classified_as_incomplete(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "A")[0]
    directory = tmp_path / block.stage / block.name
    directory.mkdir(parents=True)
    (directory / bench.BLOCK_FILE).write_text(
        json.dumps(
            {
                "finished": False,
                "state": "stopped",
                "stop_kind": bench.STOP_LEVEL,
                "stopped_reason": "watchdog",
                "cells": [],
            }
        )
    )
    assert bench.stage_state(tmp_path, block) == "stopped"


def test_stale_pass_report_cannot_authorize_after_incomplete_block(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "A")[0]
    (tmp_path / block.stage / block.name).mkdir(parents=True)
    (tmp_path / bench.REPORT_JSON).write_text(
        json.dumps(
            {
                "design_sha256": design.sha256,
                "decision": {"halts": [], "stages": {"A": {"passed": True}}},
            }
        )
    )
    assert bench.stage_gate_problem(design, "B", tmp_path) is not None


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


def test_stuck_event_collector_is_killed_and_failure_retained() -> None:
    calls: list[str] = []

    class Events:
        def terminate(self) -> None:
            calls.append("terminate")

        def kill(self) -> None:
            calls.append("kill")

        def wait(self, timeout: float) -> int:
            calls.append("wait")
            if "kill" not in calls:
                raise subprocess.TimeoutExpired("docker events", timeout)
            return -9

    events: Any = Events()
    with pytest.raises(subprocess.TimeoutExpired):
        bench._stop_events(events)
    assert calls == ["terminate", "wait", "kill", "wait"]


def test_failed_block_publication_writes_incomplete_evidence(
    tmp_path: Path, monkeypatch: Any
) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]

    class Events:
        def terminate(self) -> None:
            pass

        def wait(self, timeout: float) -> int:
            return 0

    def cell_runner(cell: Any, raw: Path, _env: Any, _bash: Any, **kwargs: Any) -> CellResult:
        kwargs["popen"]()
        log = raw / f"{cell.run_id}.log"
        log.write_text("")
        return CellResult(cell, 0, 0.01, raw / "e.json", False, log)

    publish = bench._publish_json

    def fail_completed(path: Path, value: Any) -> None:
        if path.name == bench.BLOCK_FILE:
            raise OSError("injected completed record failure")
        publish(path, value)

    monkeypatch.setattr(bench, "_start_events", lambda _path: Events())
    monkeypatch.setattr(bench, "_sample_host", lambda *_args: None)
    monkeypatch.setattr(bench, "run_cell_with_watchdog", cell_runner)
    monkeypatch.setattr(bench.subprocess, "Popen", clean_fake_popen)
    monkeypatch.setattr(bench, "residual_resources", list)
    monkeypatch.setattr(bench, "_publish_json", fail_completed)
    with pytest.raises(OSError, match="injected completed record failure"):
        bench.run_block(design, block, tmp_path, "bash")
    record = json.loads((tmp_path / bench.INCOMPLETE_BLOCK_FILE).read_text())
    assert record["finished"] is False
    assert len(record["completed_cells"]) == len(block.cells)
    assert not (tmp_path / bench.BLOCK_FILE).exists()


def test_failed_incomplete_publication_preserves_first_exception(
    tmp_path: Path, monkeypatch: Any
) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "smoke")[0]
    directory = tmp_path / block.stage / block.name
    directory.mkdir(parents=True)

    def fail_run(_design: Any, _block: Any, _directory: Any, _bash: Any, run: Any) -> Any:
        run.request_stop("sampler first", bench.STOP_EXTERNAL)
        raise OSError("original failure")

    def fail_write(*_args: Any) -> Any:
        raise OSError("write failure")

    monkeypatch.setattr(bench, "_run_block", fail_run)
    monkeypatch.setattr(bench, "_publish_json", fail_write)
    monkeypatch.setattr(bench, "residual_resources", list)
    with pytest.raises(OSError, match="original failure") as error:
        bench.run_block(design, block, directory, "bash")
    notes = " ".join(error.value.__notes__)
    assert "write failure" in notes
    assert "sampler first" in notes
    assert bench.stage_state(tmp_path, block) == "incomplete"

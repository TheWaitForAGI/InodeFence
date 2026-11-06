"""Concurrency benchmark: the design pins everything but jobs; analysis stays oracle-blind."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from scripts import analyze_concurrency_benchmark as analysis
from scripts import run_concurrency_benchmark as bench
from scripts.run_parallel_native import Cell, CellResult

REPO = Path(__file__).resolve().parents[1]
DESIGN_PATH = REPO / "experiments" / "configs" / "concurrency-scaling-v1.md"


@pytest.fixture(scope="module")
def design() -> bench.Design:
    return bench.load_design(DESIGN_PATH)


def _replace_line(key: str, value: str) -> str:
    lines = DESIGN_PATH.read_text(encoding="utf-8").splitlines()
    matches = [i for i, line in enumerate(lines) if line.startswith(f"{key} =")]
    assert len(matches) == 1
    lines[matches[0]] = f"{key} = {value}"
    return "\n".join(lines) + "\n"


def test_committed_design_uses_the_pilot_conditions_and_rising_stages(design: bench.Design) -> None:
    assert design.stages["A"] == (2, 4, 4, 2)
    assert design.stages["B"] == (4, 6, 6, 4)
    assert design.stages["C"] == (6, 8, 8, 6)
    assert bench.measured_stages(design) == ("A", "B", "C")
    assert design.target_version == "7.5.2"
    assert design.budget == 2000
    assert design.sentinel_count == 5
    assert design.image_digest.startswith("sha256:22c8734f")


def test_only_jobs_differ_between_blocks(design: bench.Design) -> None:
    for stage in bench.measured_stages(design):
        blocks = bench.planned_blocks(design, stage)
        assert len({block.cells for block in blocks}) == 1
        assert {block.jobs for block in blocks} == set(design.stages[stage])
    cells_per_stage = {bench.planned_cells(design, s) for s in bench.measured_stages(design)}
    assert len(cells_per_stage) == 1


def test_arm_seed_matrix_is_balanced_and_rotated(design: bench.Design) -> None:
    cells = bench.planned_cells(design, "A")
    assert len(cells) == len(design.arms) * len(design.seeds) == 12
    assert len({cell.run_id for cell in cells}) == 12
    first_arm_per_seed = [cells[i * len(design.arms)].arm.label for i in range(len(design.seeds))]
    assert len(set(first_arm_per_seed)) == len(design.seeds)


def test_smoke_stage_is_separate_and_short(design: bench.Design) -> None:
    cells = bench.planned_cells(design, bench.SMOKE_STAGE)
    assert {cell.seed for cell in cells} == {design.smoke_seed}
    assert {cell.budget for cell in cells} == {design.smoke_budget}
    assert design.smoke_seed not in design.seeds


@pytest.mark.parametrize("seed", ["9001", "8101", "7001", "100", "9500", "8002"])
def test_seeds_inside_reserved_ranges_are_refused(seed: str) -> None:
    with pytest.raises(bench.DesignError, match="reserved"):
        bench.parse_design(_replace_line("seeds", f"6101, {seed}"))


def test_other_execution_modes_are_refused() -> None:
    with pytest.raises(bench.DesignError, match="varies concurrency only"):
        bench.parse_design(_replace_line("execution_mode", "worker-pool"))


def test_uncrossed_order_is_refused() -> None:
    with pytest.raises(bench.DesignError, match="crossed"):
        bench.parse_design(_replace_line("stage.A", "2,2,4,4"))


def test_output_must_stay_apart_from_evidence_and_repository(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    assert "evidence" in (
        bench.output_problem(home / "inodefence-evidence" / "x", repo, home) or ""
    )
    assert "repository" in (bench.output_problem(repo / "out", repo, home) or "")
    assert bench.output_problem(home / "inodefence-benchmarks" / "x", repo, home) is None


def _fake_result(cell: Cell, raw: Path, returncode: int) -> CellResult:
    raw.mkdir(parents=True, exist_ok=True)
    return CellResult(cell, returncode, 0.01, raw / "e.json", False, raw / f"{cell.run_id}.log")


def test_block_run_honors_jobs_and_records_no_outcome(design: bench.Design, tmp_path: Path) -> None:
    block = bench.planned_blocks(design, "A")[1]
    assert block.jobs == 4
    lock = threading.Lock()
    running = 0
    peak = 0

    def run_cell(cell: Cell, raw: Path, _env: dict[str, str]) -> CellResult:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.02)
        with lock:
            running -= 1
        return _fake_result(cell, raw, 0)

    record = bench.BlockRun(design, block, tmp_path, run_cell).execute()
    assert peak == 4
    assert record["jobs"] == 4
    assert [cell["run_id"] for cell in record["cells"]] == [c.run_id for c in block.cells]
    text = json.dumps(record)
    for field in ("oracle", "C1", "C2", "t_first", "hit"):
        assert f'"{field}"' not in text


def test_block_stops_starting_cells_after_repeated_failures(
    design: bench.Design, tmp_path: Path
) -> None:
    block = bench.planned_blocks(design, "A")[0]
    run = bench.BlockRun(design, block, tmp_path, lambda c, r, _e: _fake_result(c, r, 1))
    record = run.execute()
    states = [cell["state"] for cell in record["cells"]]
    assert "not-run" in states
    assert record["stopped_reason"] is not None
    ran = sum(1 for state in states if state == "ran")
    assert design.stop_nonzero_cells <= ran <= design.stop_nonzero_cells + block.jobs - 1


def test_watchdog_kill_stops_the_block(design: bench.Design, tmp_path: Path) -> None:
    block = bench.planned_blocks(design, "A")[0]
    run = bench.BlockRun(
        design,
        block,
        tmp_path,
        lambda c, r, _e: _fake_result(c, r, bench.WATCHDOG_RETURNCODE),
    )
    record = run.execute()
    assert "watchdog" in (record["stopped_reason"] or "")


def test_host_stop_reasons(design: bench.Design) -> None:
    quiet = {
        "memory": {"MemTotal": 100, "MemAvailable": 50},
        "disk_fraction": 0.1,
        "containers": ["inodefence-local-controller-7.5.2-D-s6101", "inodefence-" + "a" * 32],
    }
    assert bench.host_stop_reason(quiet, design) is None
    low_memory = {**quiet, "memory": {"MemTotal": 100, "MemAvailable": 5}}
    assert "memory" in (bench.host_stop_reason(low_memory, design) or "")
    assert "disk" in (bench.host_stop_reason({**quiet, "disk_fraction": 0.95}, design) or "")
    foreign = {**quiet, "containers": ["someone-else"]}
    assert "foreign" in (bench.host_stop_reason(foreign, design) or "")


def test_stage_gate_requires_the_previous_stage_clean(design: bench.Design, tmp_path: Path) -> None:
    assert bench.stage_gate_problem(design, bench.SMOKE_STAGE, tmp_path) is None
    assert "not clean" in (bench.stage_gate_problem(design, "A", tmp_path) or "")
    for block in bench.planned_blocks(design, bench.SMOKE_STAGE):
        path = tmp_path / block.stage / block.name
        path.mkdir(parents=True)
        (path / bench.BLOCK_FILE).write_text(json.dumps({"stopped_reason": None}), encoding="utf-8")
    assert bench.stage_gate_problem(design, "A", tmp_path) is None
    assert "stage A" in (bench.stage_gate_problem(design, "B", tmp_path) or "")


def _step(index: int, termination: str = "success") -> dict[str, Any]:
    return {
        "index": index,
        "case_id": f"case-{index}",
        "validity": "valid",
        "oracle": {"C0": False, "C1": False, "C2": False},
        "feedback": {"trace_termination": termination, "new_effect_keys": []},
        "trace": {"observation_failures": []},
    }


def _write_cell(
    raw: Path,
    design: bench.Design,
    run_id: str,
    seed: int,
    *,
    budget: int = 3,
    report_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw.mkdir(parents=True, exist_ok=True)
    steps = [_step(i) for i in range(budget)]
    report: dict[str, Any] = {
        "config": {"random_seed": seed, "execution_budget": budget},
        "image_id": design.image_digest,
        "sentinel_set": {"count": design.sentinel_count},
        "steps": steps,
        "timing": {
            "per_case": [{"wall_seconds": 1.5, "target_seconds": 0.3} for _ in range(budget)]
        },
    }
    report.update(report_extra or {})
    (raw / f"{run_id}.json").write_text(json.dumps(report), encoding="utf-8")
    (raw / f"{run_id}.steps.jsonl").write_text(
        "".join(json.dumps(step) + "\n" for step in steps), encoding="utf-8"
    )
    (raw / f"{run_id}.log").write_text("PASSED\n", encoding="utf-8")
    return {
        "run_id": run_id,
        "state": "ran",
        "arm": "D",
        "seed": seed,
        "budget": budget,
        "returncode": 0,
        "watchdog_killed": False,
        "started": {"realtime": 1000.0, "monotonic": 1000.0},
        "ended": {"realtime": 1360.0, "monotonic": 1392.0},
        "report": f"{run_id}.json",
        "steps": f"{run_id}.steps.jsonl",
        "log": f"{run_id}.log",
    }


def test_normal_cell_and_each_failure_disposition(design: bench.Design, tmp_path: Path) -> None:
    cell = _write_cell(tmp_path, design, "ok", 6101)
    summary, report = analysis.summarize_cell(cell, tmp_path, design)
    assert summary["disposition"] == "normal"
    assert report is not None
    assert summary["executions"] == 3
    assert summary["terminations"] == {"success": 3}

    wrong_image = _write_cell(tmp_path, design, "img", 6101, report_extra={"image_id": "other"})
    assert analysis.summarize_cell(wrong_image, tmp_path, design)[0]["disposition"] == (
        "nonconformant"
    )

    short = {**_write_cell(tmp_path, design, "short", 6101), "budget": 5}
    assert analysis.summarize_cell(short, tmp_path, design)[0]["disposition"] == "nonconformant"

    missing = {**cell, "run_id": "gone", "report": "gone.json", "steps": "gone.steps", "log": "x"}
    assert analysis.summarize_cell(missing, tmp_path, design)[0]["disposition"] == "no-record"

    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    unreadable = {**cell, "run_id": "bad", "report": "bad.json"}
    assert analysis.summarize_cell(unreadable, tmp_path, design)[0]["disposition"] == "unreadable"


def test_steps_file_disagreeing_with_report_is_an_integrity_failure(
    design: bench.Design, tmp_path: Path
) -> None:
    cell = _write_cell(tmp_path, design, "split", 6101)
    (tmp_path / "split.steps.jsonl").write_text(
        json.dumps({"index": 0, "case_id": "other"}) + "\n", encoding="utf-8"
    )
    summary, _ = analysis.summarize_cell(cell, tmp_path, design)
    assert summary["disposition"] == "integrity-failure"


def test_cleanup_abort_is_flagged_as_possibly_masking(design: bench.Design, tmp_path: Path) -> None:
    aborted = {
        "reason": "x.BackendError: container runtime cleanup inspect failed: timeout",
        "step_index": 7,
    }
    cell = {
        **_write_cell(tmp_path, design, "a", 6101, report_extra={"aborted": aborted}),
        "returncode": 1,
    }
    (tmp_path / "a.log").write_text(
        "FAILED at step: effect-demo-historical (exit 1)\n", encoding="utf-8"
    )
    summary, report = analysis.summarize_cell(cell, tmp_path, design)
    assert report is None
    assert summary["disposition"] == "abort"
    assert summary["abort"]["category"] == "cleanup_inspect"
    assert summary["abort"]["first_error_may_be_masked"] is True
    assert summary["abort"]["step_index"] == 7
    assert summary["harness_failed_step"] == "effect-demo-historical"


def test_lifecycle_seconds_from_docker_events() -> None:
    def event(identity: str, action: str, seconds: float, name: str) -> str:
        return json.dumps(
            {
                "id": identity,
                "Action": action,
                "timeNano": int(seconds * 1e9),
                "Actor": {"Attributes": {"name": name}},
            }
        )

    target = "inodefence-" + "a" * 32
    lines = [
        event("t1", "create", 1.0, target),
        event("t1", "start", 1.5, target),
        event("t1", "die", 2.5, target),
        event("t1", "destroy", 2.75, target),
        event("c1", "create", 0.0, "inodefence-local-controller-x"),
        event("c1", "start", 2.0, "inodefence-local-controller-x"),
        "not json",
    ]
    spans = analysis.lifecycle_seconds(lines)
    assert spans["target.create_to_start"]["p50"] == pytest.approx(0.5)
    assert spans["target.die_to_destroy"]["max"] == pytest.approx(0.25)
    assert spans["controller.create_to_start"]["count"] == 1


def _host_sample(busy: int, idle: int, available: int) -> str:
    return json.dumps(
        {
            "loadavg": [2.0, 1.0, 0.5],
            "memory": {
                "MemTotal": 100,
                "MemAvailable": available,
                "SwapTotal": 10,
                "SwapFree": 10,
            },
            "cpu_jiffies": [busy, 0, 0, idle, 0, 0, 0, 0],
            "disk_fraction": 0.2,
            "docker_ps_seconds": 0.1,
        }
    )


def test_host_summary() -> None:
    host = analysis.host_summary([_host_sample(0, 0, 60), _host_sample(30, 10, 40)])
    assert host["cpu_busy_fraction"] == pytest.approx(0.75)
    assert host["memory_available_min_bytes"] == 40
    assert analysis.host_summary([]) == {"samples": 0}


def _write_block(root: Path, design: bench.Design, stage: str, index: int, jobs: int) -> None:
    directory = root / stage / f"block-{index}-j{jobs}"
    raw = directory / "raw"
    cells = [_write_cell(raw, design, f"cell-{seed}", seed) for seed in (6101, 6102)]
    record = {
        "stage": stage,
        "index": index,
        "jobs": jobs,
        "started": {"realtime": 0.0, "monotonic": 0.0},
        "ended": {"realtime": 3600.0 / jobs, "monotonic": 3900.0 / jobs},
        "stopped_reason": None,
        "residual_after_block": [],
        "cells": cells,
    }
    (directory / bench.BLOCK_FILE).write_text(json.dumps(record), encoding="utf-8")


def test_analyze_reports_rates_on_real_time_without_oracle_fields(
    design: bench.Design, tmp_path: Path
) -> None:
    for index, jobs in enumerate(design.stages["A"], start=1):
        _write_block(tmp_path, design, "A", index, jobs)
    report = analysis.analyze(tmp_path, design)
    levels = report["stages"]["A"]["levels"]
    assert levels["2"]["normal_campaigns_per_real_hour_mean"] == pytest.approx(4.0)
    assert levels["4"]["normal_campaigns_per_real_hour_mean"] == pytest.approx(8.0)
    assert levels["2"]["drift_second_over_first"] == pytest.approx(1.0)
    assert levels["2"]["aborts"] == 0
    assert levels["2"]["determinism_cells_differing"] == 0
    block = report["stages"]["A"]["blocks"][0]
    assert block["monotonic_over_real"] == pytest.approx(3900 / 3600)
    assert block["abort_per_execution_rule_of_three"] == pytest.approx(0.5)
    last = report["stages"]["A"]["blocks"][-1]
    assert last["determinism"] == {
        "cells_compared": 2,
        "determinism_pass": 2,
        "observation_sequence_identical": 2,
        "differing_cells": [],
    }
    text = json.dumps(report)
    for field in ('"oracle"', '"C1"', '"C2"', "t_first", "u_viol", "contract_violated"):
        assert field not in text
    assert "단계 A" in analysis.render_markdown(report)


def test_changed_search_path_under_load_is_a_determinism_difference(
    design: bench.Design, tmp_path: Path
) -> None:
    """A target timeout caused by daemon latency changes the path; it must not pass silently."""
    first = {"steps": [_step(0), _step(1)]}
    changed = {"steps": [_step(0), {**_step(1), "case_id": "case-other"}]}
    reference: dict[str, Any] = {}
    assert analysis.determinism_against_reference({"x": first}, reference)["cells_compared"] == 0
    verdict = analysis.determinism_against_reference({"x": changed}, reference)
    assert verdict["differing_cells"] == ["x"]

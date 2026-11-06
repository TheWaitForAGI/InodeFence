"""Concurrency benchmark: only jobs vary, the decision is mechanical, oracle values stay sealed."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from scripts import analyze_concurrency_benchmark as analysis
from scripts import run_concurrency_benchmark as bench
from scripts.run_parallel_native import Cell, CellResult

REPO = Path(__file__).resolve().parents[1]
DESIGN_PATH = REPO / "experiments" / "configs" / "concurrency-scaling-v1.md"
ARMS = ("D", "R-restart", "R-walk", "S-u")


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
    assert design.stop_nonzero_cells == 6
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


def test_block_stops_starting_cells_after_half_fail(design: bench.Design, tmp_path: Path) -> None:
    block = bench.planned_blocks(design, "A")[0]
    run = bench.BlockRun(design, block, tmp_path, lambda c, r, _e: _fake_result(c, r, 1))
    record = run.execute()
    states = [cell["state"] for cell in record["cells"]]
    assert "not-run" in states
    assert record["stopped_reason"] is not None
    ran = sum(1 for state in states if state == "ran")
    assert 6 <= ran <= 6 + block.jobs - 1


def test_five_failures_do_not_stop_a_block(design: bench.Design, tmp_path: Path) -> None:
    block = bench.planned_blocks(design, "A")[0]
    failing = {cell.run_id for cell in block.cells[:5]}

    def run_cell(cell: Cell, raw: Path, _env: dict[str, str]) -> CellResult:
        return _fake_result(cell, raw, 1 if cell.run_id in failing else 0)

    record = bench.BlockRun(design, block, tmp_path, run_cell).execute()
    assert record["stopped_reason"] is None
    assert all(cell["state"] == "ran" for cell in record["cells"])


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


def test_a_failed_sampler_stops_the_block(
    design: bench.Design, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> dict[str, Any]:
        raise OSError("no /proc")

    monkeypatch.setattr(bench, "read_host_counters", broken)
    block = bench.planned_blocks(design, "A")[0]
    run = bench.BlockRun(design, block, tmp_path, lambda c, r, _e: _fake_result(c, r, 0))
    bench._sample_host(run, tmp_path / "samples.jsonl", threading.Event(), seconds=0.01)
    assert "sampler failed" in (run.stopped_reason or "")


def _write_report(path: Path, design: bench.Design, passed: bool, **extra: Any) -> None:
    decision = {"halts": [], "stages": {"A": {"passed": passed}}, **extra}
    path.write_text(
        json.dumps({"design_sha256": design.sha256, "decision": decision}), encoding="utf-8"
    )


def test_stage_gate_follows_the_decision(design: bench.Design, tmp_path: Path) -> None:
    assert bench.stage_gate_problem(design, bench.SMOKE_STAGE, tmp_path) is None
    assert "not clean" in (bench.stage_gate_problem(design, "A", tmp_path) or "")
    for block in bench.planned_blocks(design, bench.SMOKE_STAGE):
        path = tmp_path / block.stage / block.name
        path.mkdir(parents=True)
        (path / bench.BLOCK_FILE).write_text(json.dumps({"stopped_reason": None}), encoding="utf-8")
    assert bench.stage_gate_problem(design, "A", tmp_path) is None
    assert "no analysis report" in (bench.stage_gate_problem(design, "B", tmp_path) or "")
    report = tmp_path / bench.REPORT_JSON
    _write_report(report, design, passed=False)
    assert "did not pass" in (bench.stage_gate_problem(design, "B", tmp_path) or "")
    _write_report(report, design, passed=True)
    assert bench.stage_gate_problem(design, "B", tmp_path) is None
    _write_report(report, design, passed=True, halts=[{"rule": "H2"}])
    assert "H2" in (bench.stage_gate_problem(design, "B", tmp_path) or "")
    report.write_text(json.dumps({"design_sha256": "other"}), encoding="utf-8")
    assert "another design" in (bench.stage_gate_problem(design, "B", tmp_path) or "")


# ---- decision rules ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("events", "ref", "expected"),
    [(5, 0, True), (4, 0, False), (7, 1, True), (6, 1, False), (9, 2, True), (8, 2, False)],
)
def test_abort_relative_table(events: int, ref: int, expected: bool) -> None:
    assert analysis.significantly_more(events, ref) is expected


def _arm(**values: Any) -> dict[str, Any]:
    return {
        "campaigns": 6,
        "aborts": 0,
        "steps": 12000,
        "timed_out": 0,
        "ineligible_steps": 0,
        "target_seconds_p999": 1.0,
        "cell_monotonic_max": 1000.0,
        **values,
    }


def _level(arm_values: dict[str, dict[str, Any]] | None = None, **values: Any) -> dict[str, Any]:
    arms = {name: _arm(**(arm_values or {}).get(name, {})) for name in ARMS}
    return {
        "stopped": [],
        "watchdog_kills": 0,
        "other_abnormal": 0,
        "campaigns": 24,
        "aborts": sum(arm["aborts"] for arm in arms.values()),
        "timed_out": sum(arm["timed_out"] for arm in arms.values()),
        "first_error_unconfirmed": 0,
        "arms": arms,
        **values,
    }


def _rules(level: dict[str, Any], ref: dict[str, Any] | None = None, **kwargs: Any) -> set[str]:
    options = {"floor": 0, "block_m": [0, 0], "one_sided_cells": 0, **kwargs}
    found = analysis.level_violations(level, ref or _level(), **options)
    return {item["rule"] for item in found}


def test_clean_level_has_no_violations() -> None:
    assert _rules(_level()) == set()


def test_watchdog_and_other_abnormal_boundaries() -> None:
    assert _rules(_level(watchdog_kills=1)) == {"V1"}
    assert _rules(_level(other_abnormal=1)) == set()
    assert _rules(_level(other_abnormal=2)) == {"V2"}


def test_stopped_level_is_excluded() -> None:
    assert _rules(_level(stopped=["6 cells exited nonzero"])) == {"stopped"}


def test_abort_absolute_boundary_is_eight_of_twentyfour() -> None:
    even = {name: {"aborts": 2} for name in ARMS}
    seven = _level({**even, "S-u": {"aborts": 1}})
    eight = _level(even)
    assert seven["aborts"] == 7 and eight["aborts"] == 8
    assert "V3" not in _rules(seven, _level({"D": {"aborts": 7}}))
    assert "V3" in _rules(eight, _level({"D": {"aborts": 8}}))


@pytest.mark.parametrize(
    ("counts", "expected", "flagged"),
    [
        ((3, 0, 0, 0), 0.04, True),
        ((4, 1, 1, 0), 0.089, True),
        ((3, 1, 1, 0), 0.314, False),
        ((2, 0, 0, 0), 0.217, False),
    ],
)
def test_arm_abort_values_match_the_design(
    counts: tuple[int, ...], expected: float, flagged: bool
) -> None:
    level = _level({name: {"aborts": n} for name, n in zip(ARMS, counts, strict=True)})
    p_value = analysis.abort_arm_p_value(level)
    assert p_value == pytest.approx(expected, abs=0.002)
    assert ("V5" in _rules(level)) is flagged


def test_arm_skew_needs_more_aborts_than_reference() -> None:
    level = _level({"D": {"aborts": 3}})
    assert "V5" not in _rules(level, _level({"S-u": {"aborts": 3}}))


def test_target_time_boundary() -> None:
    assert _rules(_level({"D": {"target_seconds_p999": 5.0}})) == set()
    assert _rules(_level({"D": {"target_seconds_p999": 5.01}})) == {"V6"}


def test_timed_out_boundaries() -> None:
    # 12 in 12000 steps is exactly one per thousand. Equal totals isolate the arm rate.
    one_per_thousand = _level({"D": {"timed_out": 12}}, timed_out=4)
    assert "V7" not in _rules(one_per_thousand, _level(timed_out=4))
    assert "V7" in _rules(_level({"D": {"timed_out": 13}}, timed_out=4), _level(timed_out=4))


def test_timed_out_total_uses_the_relative_table() -> None:
    spread = {name: {"timed_out": 1} for name in ARMS}
    assert "V7" not in _rules(_level(spread), _level())
    with_five = _level({**spread, "D": {"timed_out": 2}})
    assert with_five["timed_out"] == 5
    assert "V7" in _rules(with_five, _level())


def test_observation_error_absolute_boundary() -> None:
    assert "V8" not in _rules(
        _level({"D": {"ineligible_steps": 240}}), _level({"D": {"ineligible_steps": 240}})
    )
    assert "V8" in _rules(
        _level({"D": {"ineligible_steps": 241}}), _level({"D": {"ineligible_steps": 241}})
    )


def test_observation_error_ratio_needs_size_and_significance() -> None:
    ref = _level({"D": {"ineligible_steps": 100}})
    assert "V8" in _rules(_level({"D": {"ineligible_steps": 170}}), ref)
    assert "V8" not in _rules(_level({"D": {"ineligible_steps": 125}}), ref)
    small_ref = _level({"D": {"ineligible_steps": 2}})
    assert "V8" not in _rules(_level({"D": {"ineligible_steps": 3}}), small_ref)


def test_path_difference_boundaries() -> None:
    assert "V9" not in _rules(_level(), block_m=[2, 1], floor=1)
    assert "V9" in _rules(_level(), block_m=[3, 1], floor=1)
    assert "V9" not in _rules(_level(), one_sided_cells=1)
    assert "V9" in _rules(_level(), one_sided_cells=2)


def test_watchdog_margin_boundary() -> None:
    assert _rules(_level({"R-walk": {"cell_monotonic_max": 7200.0}})) == set()
    assert _rules(_level({"R-walk": {"cell_monotonic_max": 7200.1}})) == {"V10"}


def test_selection_ratios_boundaries() -> None:
    def ratios(
        throughput: Sequence[float | None], ref: float | None = 1.0, high: float | None = 1.0
    ) -> dict[str, Any]:
        return analysis.selection_ratios(throughput, ref, high)

    passing = ratios([10.0, 12.0, 12.0, 10.0])
    assert passing["rho"] == pytest.approx([1.2, 1.2])
    assert passing["drift"] == pytest.approx(0.0)
    assert passing["gain"] is True
    assert ratios([10.0, 11.5, 11.5, 10.0])["gain"] is True
    assert ratios([10.0, 11.4, 11.4, 10.0])["gain"] is False
    # One crossed half below 1.15 is enough to refuse the level.
    assert ratios([10.0, 13.0, 11.0, 10.0])["gain"] is False
    within_drift = ratios([10.0, 12.0, 11.0, 9.5])
    assert within_drift["drift"] == pytest.approx(1 / 12)
    assert within_drift["gain"] is True
    too_much_drift = ratios([10.0, 20.0, 16.0, 8.0])
    assert too_much_drift["valid"] is False
    assert too_much_drift["gain"] is False
    assert ratios([10.0, None, 12.0, 10.0])["gain"] is False


def test_normal_fraction_enters_once_as_level_totals() -> None:
    double = [10.0, 20.0, 20.0, 10.0]
    # Twice the throughput survives losing 40% of campaigns, not 50%.
    kept = analysis.selection_ratios(double, 1.0, 0.6)
    assert kept["adjusted_gain"] == pytest.approx(1.2)
    assert kept["gain"] is True
    lost = analysis.selection_ratios(double, 1.0, 0.5)
    assert lost["adjusted_gain"] == pytest.approx(1.0)
    assert lost["gain"] is False
    # The reference losing campaigns too leaves the ratio, so the high level is not penalized.
    assert analysis.selection_ratios(double, 0.75, 0.75)["adjusted_gain"] == pytest.approx(2.0)
    assert analysis.selection_ratios(double, 0.0, 1.0)["gain"] is False
    assert analysis.selection_ratios(double, None, 1.0)["gain"] is False


# ---- first error, paths, saturation --------------------------------------------------


@pytest.mark.parametrize(
    ("aborted", "status"),
    [
        (None, "unconfirmed"),
        ({"reason": "evidence integrity failed after target success: {}"}, "confirmed"),
        ({"reason": "image node-tar 1 differs from repository pin 2"}, "confirmed"),
        ({"reason": "container runtime cleanup inspect failed: x"}, "unconfirmed"),
        (
            {
                "reason": "container runtime cleanup inspect failed: x",
                "error_chain": [
                    {"type": "BackendError", "message": "container runtime remove failed: y"}
                ],
            },
            # A whole chain ending in cleanup: nothing was replaced, cleanup really came first.
            "confirmed",
        ),
        (
            {
                "reason": "container runtime cleanup inspect failed: x",
                "error_chain": [
                    {"type": "BackendError", "message": "cleanup"},
                    {"type": "BackendError", "message": "container target could not start"},
                ],
            },
            "confirmed",
        ),
        (
            {"reason": "x", "error_chain": [{"type": "A", "message": "b"}, {"truncated": True}]},
            "unconfirmed",
        ),
    ],
)
def test_first_error_status(aborted: dict[str, Any] | None, status: str) -> None:
    assert analysis.first_error(aborted)["status"] == status


def _path(
    cases: Sequence[str],
    terminations: Sequence[str] | None = None,
    verdicts: Sequence[int] | None = None,
) -> analysis.CellPath:
    return analysis.CellPath(
        tuple(cases),
        tuple(terminations or ["success"] * len(cases)),
        tuple(verdicts or [0] * len(cases)),
        tuple([None] * len(cases)),
    )


def test_compare_paths_uses_the_common_prefix() -> None:
    full = _path(["a", "b", "c"])
    aborted = _path(["a", "b"])
    assert analysis.compare_paths(full, aborted).differs is False


def test_compare_paths_finds_the_first_difference_and_its_cause() -> None:
    base = _path(["a", "b", "c"])
    congested = _path(["a", "b", "x"], ["success", "timed_out", "success"])
    difference = analysis.compare_paths(base, congested)
    assert difference.first_step == 1
    assert difference.terminations == ("success", "timed_out")
    assert difference.one_sided_congestion is True
    both_failed = analysis.compare_paths(
        _path(["a", "b"], ["failed", "success"]), _path(["z", "b"], ["failed", "success"])
    )
    assert both_failed.one_sided_congestion is False


def test_verdict_only_difference_carries_no_identity() -> None:
    block = {"cells": [{"run_id": "cell", "arm": "S-u"}]}
    result = analysis.block_determinism(
        block,
        {"cell": _path(["a"], verdicts=[1])},
        {"cell": _path(["a"], verdicts=[2])},
    )
    assert result["m"] == 1
    assert result["verdict_only_cells"] == 1
    assert result["first_differences"] == []
    assert result["case_sequence_by_arm"] == {}


def test_saturated_rate_excludes_the_low_occupancy_tail() -> None:
    def cell(start: float, end: float) -> dict[str, float]:
        return {"started_real": start, "ended_real": end, "executions": 3600}

    # Two slots, three cells: the third runs alone and twice as fast after the second slot empties.
    cells = [cell(0, 3600), cell(0, 3600), cell(3600, 5400)]
    assert analysis.saturated_exec_per_hour(cells, 2) == pytest.approx(7200)
    overall = sum(c["executions"] for c in cells) / 5400 * 3600
    assert overall == pytest.approx(7200)
    tail_heavy = [cell(0, 3600), cell(0, 1800), cell(1800, 3600), cell(3600, 4500)]
    assert analysis.saturated_exec_per_hour(tail_heavy, 2) == pytest.approx(10800)


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


def test_host_summary() -> None:
    def sample(busy: int, idle: int, available: int) -> dict[str, Any]:
        return {
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

    host = analysis.host_summary([sample(0, 0, 60), sample(30, 10, 40)])
    assert host["cpu_busy_fraction"] == pytest.approx(0.75)
    assert host["memory_available_min_bytes"] == 40
    assert analysis.host_summary([]) == {"samples": 0}


# ---- report files ---------------------------------------------------------------------


def _step(index: int, *, termination: str = "success", case: str | None = None) -> dict[str, Any]:
    return {
        "index": index,
        "case_id": case or f"case-{index}",
        "validity": "valid",
        "oracle": {"C0": False, "C1": True, "C2": False},
        "oracle_fingerprints": ["SECRET-FINGERPRINT"],
        "feedback": {
            "trace_termination": termination,
            "new_effect_keys": [],
            "feedback_eligible": True,
            "contract_violated": True,
        },
        "trace": {
            "observation_failures": [],
            "entries": [{"type": "regular"}] * (index + 1),
        },
        "mutation_attempt": {"operator_id": f"op-{index}"},
    }


def _write_cell(
    raw: Path,
    design: bench.Design,
    run_id: str,
    seed: int,
    *,
    arm: str = "D",
    duration: float = 360.0,
    steps: Sequence[dict[str, Any]] | None = None,
    report_extra: dict[str, Any] | None = None,
    returncode: int = 0,
) -> dict[str, Any]:
    raw.mkdir(parents=True, exist_ok=True)
    records = list(steps if steps is not None else [_step(i) for i in range(3)])
    report: dict[str, Any] = {
        "config": {"random_seed": seed, "execution_budget": 3},
        "image_id": design.image_digest,
        "sentinel_set": {"count": design.sentinel_count},
        "steps": records,
        "timing": {
            "per_case": [{"wall_seconds": 1.5, "target_seconds": 0.3} for _ in records],
        },
    }
    report.update(report_extra or {})
    (raw / f"{run_id}.json").write_text(json.dumps(report), encoding="utf-8")
    (raw / f"{run_id}.steps.jsonl").write_text(
        "".join(json.dumps(step) + "\n" for step in records), encoding="utf-8"
    )
    (raw / f"{run_id}.log").write_text("PASSED\n", encoding="utf-8")
    return {
        "run_id": run_id,
        "state": "ran",
        "arm": arm,
        "seed": seed,
        "budget": 3,
        "returncode": returncode,
        "watchdog_killed": False,
        "started": {"realtime": 0.0, "monotonic": 0.0},
        "ended": {"realtime": duration, "monotonic": duration * 1.09},
        "report": f"{run_id}.json",
        "steps": f"{run_id}.steps.jsonl",
        "log": f"{run_id}.log",
    }


def test_normal_cell_and_each_failure_disposition(design: bench.Design, tmp_path: Path) -> None:
    cell = _write_cell(tmp_path, design, "ok", 6101)
    data = analysis.summarize_cell(cell, tmp_path, design)
    assert data.summary["disposition"] == "normal"
    assert data.path is not None
    assert data.summary["executions"] == 3
    assert data.summary["terminations"] == {"success": 3}

    def disposition(item: dict[str, Any]) -> str:
        return analysis.summarize_cell(item, tmp_path, design).summary["disposition"]

    wrong_image = _write_cell(tmp_path, design, "img", 6101, report_extra={"image_id": "other"})
    assert disposition(wrong_image) == "nonconformant"
    no_sentinels = _write_cell(tmp_path, design, "sen", 6101, report_extra={"sentinel_set": None})
    assert disposition(no_sentinels) == "nonconformant"
    short = {**_write_cell(tmp_path, design, "short", 6101), "budget": 5}
    assert disposition(short) == "nonconformant"
    nonzero = _write_cell(tmp_path, design, "rc", 6101, returncode=1)
    assert disposition(nonzero) == "incomplete"
    missing = {**cell, "run_id": "gone", "report": "gone.json", "steps": "gone.steps", "log": "x"}
    assert disposition(missing) == "no-record"
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert disposition({**cell, "run_id": "bad", "report": "bad.json"}) == "unreadable"


def test_steps_file_disagreeing_with_report_is_an_integrity_failure(
    design: bench.Design, tmp_path: Path
) -> None:
    cell = _write_cell(tmp_path, design, "split", 6101)
    (tmp_path / "split.steps.jsonl").write_text(
        json.dumps({"index": 0, "case_id": "other"}) + "\n", encoding="utf-8"
    )
    data = analysis.summarize_cell(cell, tmp_path, design)
    assert data.summary["disposition"] == "integrity-failure"


def _aborted(step: int, *, case: str = "case-x") -> dict[str, Any]:
    return {
        "step_index": step,
        "case_id": case,
        "reason": "x.BackendError: container runtime cleanup inspect failed: timeout",
        "error_chain": [
            {"type": "BackendError", "message": "container runtime cleanup inspect failed"},
            {"type": "BackendError", "message": "container target could not start"},
        ],
        "case_shape": {"entries": 2, "entry_types": {"regular": 2}, "content_bytes": 9},
    }


def _write_abort_cell(
    raw: Path, design: bench.Design, run_id: str, seed: int, *, step: int = 2, **kwargs: Any
) -> dict[str, Any]:
    records = [_step(i) for i in range(step)]
    extra = {"aborted": _aborted(step), "steps": None}
    return _write_cell(
        raw, design, run_id, seed, steps=records, report_extra=extra, returncode=1, **kwargs
    )


def test_abort_cell_reports_first_error_and_case_comparison(
    design: bench.Design, tmp_path: Path
) -> None:
    cell = _write_abort_cell(tmp_path, design, "a", 6101)
    (tmp_path / "a.log").write_text(
        "FAILED at step: effect-demo-historical (exit 1)\n", encoding="utf-8"
    )
    data = analysis.summarize_cell(cell, tmp_path, design)
    summary = data.summary
    assert summary["disposition"] == "abort"
    assert summary["executions"] == 2
    assert summary["exposure"] == pytest.approx(2 / 3)
    abort = summary["abort"]
    assert abort["category"] == "cleanup_inspect"
    assert abort["first_error"]["status"] == "confirmed"
    assert abort["first_error"]["message"] == "container target could not start"
    assert abort["step_index"] == 2
    assert abort["case_shape"]["content_bytes"] == 9
    # The two completed steps had 1 and 2 entries, so 2 entries is at the top of this cell.
    assert abort["entries_rank_in_cell"] == pytest.approx(1.0)
    assert abort["entry_type_ranks_in_cell"] == {"regular": pytest.approx(1.0)}
    assert summary["harness_failed_step"] == "effect-demo-historical"


def _write_stage(
    root: Path,
    design: bench.Design,
    stage: str,
    *,
    durations: dict[int, float] | None = None,
    abort_blocks: Sequence[int] = (),
    abort_step: int = 2,
    abort_duration: float = 360.0,
    last_block_case: str | None = None,
) -> None:
    order = design.stages[stage]
    for index, jobs in enumerate(order, start=1):
        directory = root / stage / f"block-{index}-j{jobs}"
        raw = directory / "raw"
        duration = (durations or {}).get(jobs, 720.0 / jobs)
        cells = []
        for position, seed in enumerate((6101, 6102)):
            arm = ARMS[position]
            run_id = f"cell-{seed}"
            if index in abort_blocks and position == 0:
                cells.append(
                    _write_abort_cell(
                        raw, design, run_id, seed, step=abort_step, arm=arm, duration=abort_duration
                    )
                )
                continue
            steps = None
            if last_block_case and index == len(order):
                steps = [_step(0), _step(1, case=last_block_case), _step(2)]
            cells.append(
                _write_cell(raw, design, run_id, seed, arm=arm, duration=duration, steps=steps)
            )
        record = {
            "stage": stage,
            "index": index,
            "jobs": jobs,
            "started": {"realtime": 0.0, "monotonic": 0.0},
            "ended": {"realtime": duration, "monotonic": duration * 1.09},
            "stopped_reason": None,
            "residual_after_block": [],
            "cells": cells,
        }
        (directory / bench.BLOCK_FILE).write_text(json.dumps(record), encoding="utf-8")


def test_analyze_selects_the_higher_level_and_stays_oracle_blind(
    design: bench.Design, tmp_path: Path
) -> None:
    _write_stage(tmp_path, design, "A")
    report = analysis.analyze(tmp_path, design)
    decision = report["decision"]
    assert decision["status"] == "provisional"
    assert decision["selected_jobs"] == 4
    verdict = decision["stages"]["A"]
    assert verdict["passed"] is True
    assert verdict["rho"] == pytest.approx([2.0, 2.0])
    assert verdict["floor"] == 0
    block = report["stages"]["A"]["blocks"][0]
    assert block["monotonic_over_real"] == pytest.approx(1.09)
    text = json.dumps(report)
    # The fixtures hold C1=True, fingerprints and contract_violated=True; none may come out.
    for field in ('"oracle"', '"C1"', '"C2"', "SECRET-FINGERPRINT", "contract_violated"):
        assert field not in text
    for field in ("t_first", "u_viol", "hit"):
        assert f'"{field}' not in text
    markdown = analysis.render_markdown(report)
    assert "단계 A" in markdown
    assert "SECRET-FINGERPRINT" not in markdown


def test_no_gain_keeps_jobs_two(design: bench.Design, tmp_path: Path) -> None:
    _write_stage(tmp_path, design, "A", durations={2: 360.0, 4: 340.0})
    decision = analysis.analyze(tmp_path, design)["decision"]
    assert decision["status"] == "selected"
    assert decision["selected_jobs"] == 2
    assert decision["stages"]["A"]["passed"] is False


def test_recurring_abort_halts_without_a_selection(design: bench.Design, tmp_path: Path) -> None:
    _write_stage(tmp_path, design, "A", abort_blocks=(1, 2))
    report = analysis.analyze(tmp_path, design)
    decision = report["decision"]
    assert decision["status"] == "halted"
    assert decision["selected_jobs"] is None
    assert [item["rule"] for item in decision["halts"]] == ["H2"]
    assert decision["recurrences"]["same_input"][0]["blocks"] == ["A/1", "A/2"]
    assert decision["fallback_jobs"] is None
    assert decision["stages"]["A"]["passed"] is False


def test_nothing_run_yet_selects_nothing(design: bench.Design, tmp_path: Path) -> None:
    decision = analysis.analyze(tmp_path, design)["decision"]
    assert decision["status"] == "pending"
    assert decision["selected_jobs"] is None
    assert decision["fallback_jobs"] is None
    assert decision["recurrences"]["recurrence_upper95"] is None


def test_recurrence_denominator_and_upper_bound() -> None:
    def cell(arm: str, seed: int, step: int, case: str, passes: int) -> dict[str, Any]:
        return {
            "arm": arm,
            "seed": seed,
            "abort": {"step_index": step, "case_id": case, "passes_elsewhere": passes},
        }

    first = {"stage": "A", "index": 1, "cells": [cell("D", 6101, 5, "c1", 10)]}
    # The same case at another arm, seed and step is only reported.
    second = {"stage": "A", "index": 2, "cells": [cell("S-u", 6102, 9, "c1", 8)]}
    result = analysis.recurrences([first, second])
    assert result["same_input"] == []
    assert result["same_case_elsewhere"] == 1
    assert result["passes_elsewhere"] == 18
    assert result["recurrence_upper95"] == pytest.approx(0.153, abs=0.001)
    third = {"stage": "A", "index": 3, "cells": [cell("D", 6101, 5, "c1", 0)]}
    assert len(analysis.recurrences([first, third])["same_input"]) == 1
    assert analysis.recurrences([])["recurrence_upper95"] is None


def test_single_abort_is_counted_not_halted_and_gets_the_operator(
    design: bench.Design, tmp_path: Path
) -> None:
    _write_stage(tmp_path, design, "A", abort_blocks=(2,))
    report = analysis.analyze(tmp_path, design)
    assert report["decision"]["halts"] == []
    assert report["decision"]["h4_first_error_unconfirmed"] == 0
    abort = report["stages"]["A"]["blocks"][1]["aborts"][0]
    # Other blocks passed step 2 with a different case id: no operator, and no real retry.
    assert abort["operator_from_other_block"] is None
    assert abort["passes_elsewhere"] == 0
    assert report["decision"]["recurrences"]["recurrence_upper95"] is None


def test_an_abort_does_not_sink_a_real_throughput_gain(
    design: bench.Design, tmp_path: Path
) -> None:
    """The earlier rule let one block's abort noise dominate; X and level totals do not."""
    # A late abort: the campaign's executions and time are as in the other blocks.
    _write_stage(tmp_path, design, "A", abort_blocks=(2,), abort_step=3, abort_duration=180.0)
    verdict = analysis.analyze(tmp_path, design)["decision"]["stages"]["A"]
    assert verdict["rho"] == pytest.approx([2.0, 2.0])
    assert verdict["adjusted_gain"] == pytest.approx(1.5)
    assert verdict["passed"] is True


def test_abort_operator_comes_from_a_block_that_passed_the_same_case(
    design: bench.Design, tmp_path: Path
) -> None:
    raw = tmp_path / "raw"
    cell = _write_abort_cell(raw, design, "cell", 6101)
    data = analysis.summarize_cell(cell, raw, design)
    block = {"cells": [data.summary], "aborts": [{"run_id": "cell", **data.summary["abort"]}]}
    other = analysis.cell_path(
        [_step(0), _step(1), {**_step(2, case="case-x"), "mutation_attempt": {"operator_id": "op"}}]
    )
    assert other is not None
    analysis.fill_abort_operators([block], [{"cell": other}, {"cell": other}])
    assert block["aborts"][0]["operator_from_other_block"] == "op"
    assert block["aborts"][0]["passes_elsewhere"] == 2


def test_floor_of_three_halts(design: bench.Design) -> None:
    def block(index: int, jobs: int, m: int) -> dict[str, Any]:
        return {
            "index": index,
            "jobs": jobs,
            "stopped_reason": None,
            "cells": [],
            "cells_planned": 12,
            "cells_not_run": 0,
            "saturated_exec_per_real_hour": 100.0,
            "determinism": {"m": m, "one_sided_congestion_cells": []},
        }

    blocks = [block(1, 2, 0), block(2, 4, 0), block(3, 4, 0), block(4, 2, 3)]
    levels = {"2": _level(), "4": _level()}
    decision = analysis.decide(design, {"A": {"blocks": blocks, "levels": levels}})
    assert [item["rule"] for item in decision["halts"]] == ["H3"]
    assert decision["status"] == "halted"
    # Nothing was selected by comparison, but EXP-3 has a value to use.
    assert decision["selected_jobs"] is None
    assert decision["fallback_jobs"] == 2


def test_jobs_two_over_the_abort_limit_halts(design: bench.Design) -> None:
    def block(index: int, jobs: int) -> dict[str, Any]:
        return {
            "index": index,
            "jobs": jobs,
            "stopped_reason": None,
            "cells": [],
            "cells_planned": 12,
            "cells_not_run": 0,
            "saturated_exec_per_real_hour": 100.0,
            "determinism": {"m": 0, "one_sided_congestion_cells": []},
        }

    blocks = [block(1, 2), block(2, 4), block(3, 4), block(4, 2)]
    ref = _level({name: {"aborts": 2} for name in ARMS})
    decision = analysis.decide(
        design, {"A": {"blocks": blocks, "levels": {"2": ref, "4": _level()}}}
    )
    assert [item["rule"] for item in decision["halts"]] == ["H1"]
    assert decision["selected_jobs"] is None
    assert decision["fallback_jobs"] is None


def test_one_sided_congestion_cell_is_not_normal_for_g(design: bench.Design) -> None:
    cells = [
        {"run_id": "x", "disposition": "normal"},
        {"run_id": "y", "disposition": "normal"},
    ]
    block = {
        "cells": cells,
        "cells_planned": 2,
        "cells_not_run": 0,
        "saturated_exec_per_real_hour": 4000.0,
        "determinism": {"one_sided_congestion_cells": ["x"]},
    }
    assert analysis.block_g(block, design.budget) == pytest.approx(1.0)

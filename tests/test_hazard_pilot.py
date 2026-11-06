"""Exploratory hazard pilot: design binding, schedule and the fixed decision rules (no Docker)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from scripts import run_hazard_pilot
from scripts.analyze_hazard_pilot import (
    CellOutcome,
    analyze,
    clopper_pearson,
    feasibility,
    load_outcome,
    n_capacity,
    one_sided_upper,
    planning_inputs,
    render_markdown,
    required_n,
    rule_condition_4,
    rule_condition_5,
    scenario_power,
    sign_p,
    summarize_arm,
    vocabulary_equal,
)
from scripts.run_effect_demo import synthetic_demo_report
from scripts.run_g1_smoke import cell_paths
from scripts.run_hazard_pilot import (
    MAX_ATTEMPTS,
    STOP_AFTER_NO_RECORD,
    DesignError,
    Schedule,
    attempts_used,
    has_record,
    load_design,
    parse_design,
    planned_cells,
)
from scripts.run_parallel_native import CellResult

from inodefence.feedback import EffectSearchPolicy
from inodefence.mutator import MutationPolicy

DESIGN = Path(__file__).resolve().parents[1] / "experiments/preregistration/exp3-hazard-pilot-v1.md"


def _outcome(arm: str, seed: int, **changes: object) -> CellOutcome:
    base = CellOutcome(
        run_id=f"7.5.2-{arm}-s{seed}",
        arm=arm,
        seed=seed,
        state="complete",
        reason=None,
        executions=2000,
        event=False,
        t_first=2000,
        first_c0=None,
        first_c1=None,
        first_c2=None,
        hit_steps=0,
        rejected=100,
        mutations=1996,
        mutation_successes=900,
        seed_parent_mutations=10,
        mean_entries=12.0,
        invalid_trace_steps=0,
        boundary_attempt_keys=2,
        retained_cases=5,
        unique_effect_keys=40,
        u_viol=0,
        vocabulary=("a", "b"),
        p50_seconds=1.4,
        p95_seconds=1.5,
    )
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


def _arms(**events: int) -> dict[str, dict[str, object]]:
    return {
        arm: summarize_arm(
            arm,
            [
                _outcome(arm, 8101 + index, event=index < events.get(arm, 0), t_first=500)
                for index in range(10)
            ],
        )
        for arm in ("R-walk", "R-restart", "D", "S-u")
    }


def test_committed_design_binds_the_approved_plan() -> None:
    design = load_design(DESIGN)
    cells = planned_cells(design)
    assert len(cells) == 40
    assert {arm.label for arm in design.arms} == {"R-walk", "R-restart", "D", "S-u"}
    assert design.target_version == "7.5.2"
    assert design.budget == 2000
    assert design.image_digest.startswith("sha256:22c8734f141d91b3")
    assert design.jobs == 2
    assert design.sentinel_count == 5  # 지웅 결정 D8, this pilot only
    assert {cell.run_id for cell in cells} == {
        f"7.5.2-{arm.label}-s{seed}" for arm in design.arms for seed in design.seeds
    }


def test_committed_seeds_are_disjoint_from_every_exposed_or_reserved_set() -> None:
    seeds = set(load_design(DESIGN).seeds)
    assert len(seeds) == 10
    reserved = (
        set(range(0, 1416))  # historical campaigns, including decompress 500-529
        | {7001, 7002}  # throughput measurement
        | {8001, 8002, 8003}  # budget-2000 rehearsal and pilot preflight
        | set(range(9001, 9006))  # EXP-0
        | set(range(9006, 9006 + 200))  # the EXP-3 proposed contiguous block
    )
    assert not seeds & reserved


def test_schedule_keeps_seed_blocks_together_and_rotates_the_arm_order() -> None:
    design = load_design(DESIGN)
    cells = planned_cells(design)
    blocks = [cells[i : i + 4] for i in range(0, 40, 4)]
    for block, seed in zip(blocks, design.seeds, strict=True):
        assert {cell.seed for cell in block} == {seed}
        assert len({cell.arm.label for cell in block}) == 4
    assert [block[0].arm.label for block in blocks[:4]] == [arm.label for arm in design.arms]


def test_design_parser_fails_closed() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    with pytest.raises(DesignError, match="no ```hazard-pilot"):
        parse_design("no block here")
    budget_line = next(line for line in text.splitlines() if line.startswith("budget = "))
    with pytest.raises(DesignError, match="duplicate"):
        parse_design(text.replace(budget_line, f"{budget_line}\n{budget_line}"))
    with pytest.raises(DesignError, match="differ"):
        parse_design(text.replace(budget_line, "extra_key = 1"))
    walk = "arm.R-walk = unretained-walk-v1-uniform-mutation-v1"
    assert walk in text
    with pytest.raises(DesignError, match="R-walk"):
        parse_design(
            text.replace(walk, "arm.R-walk = unretained-seed-restart-v1-uniform-mutation-v1")
        )


def test_only_a_cell_without_any_record_can_be_retried(tmp_path: Path) -> None:
    design = load_design(DESIGN)
    cell = planned_cells(design)[0]
    paths = cell_paths(cell, tmp_path)
    assert not has_record(cell, tmp_path)
    paths["steps_jsonl"].write_text("", encoding="utf-8")
    assert not has_record(cell, tmp_path)  # an empty steps file carries no outcome
    paths["steps_jsonl"].write_text('{"index": 0}\n', encoding="utf-8")
    assert has_record(cell, tmp_path)
    schedule = Schedule(design, tmp_path, "/bin/false")
    assert schedule.run_one(cell)["state"] == "final-from-earlier-invocation"


def test_attempt_cap_and_infrastructure_stop(tmp_path: Path) -> None:
    design = load_design(DESIGN)
    first, second = planned_cells(design)[:2]
    attempts = tmp_path / "attempts"
    attempts.mkdir()
    for number in range(1, MAX_ATTEMPTS + 1):
        (attempts / f"{first.run_id}.attempt{number}.log").write_text("x", encoding="utf-8")
    assert attempts_used(first, tmp_path) == MAX_ATTEMPTS
    schedule = Schedule(design, tmp_path, "/bin/false")
    assert schedule.run_one(first)["state"] == "no-record"
    for _ in range(STOP_AFTER_NO_RECORD):
        schedule._note_cell_end(recorded=False)
    assert schedule.stopped_reason is not None
    assert schedule.run_one(second)["state"] == "not-run"


def test_exact_intervals() -> None:
    assert one_sided_upper(0, 10) == pytest.approx(1 - 0.05**0.1, abs=1e-9)
    assert one_sided_upper(0, 10) == pytest.approx(0.2589, abs=1e-4)
    low, high = clopper_pearson(0, 10)
    assert low == 0.0
    assert high == pytest.approx(0.3085, abs=1e-4)
    low, high = clopper_pearson(1, 10)
    assert low == pytest.approx(0.0025, abs=1e-4)
    assert high == pytest.approx(0.4450, abs=1e-4)
    assert clopper_pearson(10, 10)[1] == 1.0


def test_sign_test_matches_the_registered_informative_block_floor() -> None:
    assert sign_p(7, 7) == pytest.approx(0.015625)
    assert sign_p(6, 6) == pytest.approx(0.03125)


def test_power_model_reproduces_the_reviewed_planning_grid() -> None:
    assert scenario_power(76, 0.117, 0.0, 0.0, sims=3000) == pytest.approx(0.80, abs=0.03)
    assert scenario_power(76, 0.117, 0.05, 0.05, sims=3000) == pytest.approx(0.088, abs=0.03)
    assert required_n(0.418, 0.0, 0.0, sims=2000) == pytest.approx(20, abs=2)
    assert required_n(0.05, 0.05, 0.05, sims=200) is None  # no separation to detect


def test_any_r_or_d_event_discards_the_zero_floor_and_zero_never_confirms_it() -> None:
    assert rule_condition_4(_arms())["r_d_zero_assumption"] == "not discarded (not confirmed)"
    for arm in ("R-walk", "R-restart", "D"):
        result = rule_condition_4(_arms(**{arm: 1}))
        assert result["r_d_zero_assumption"] == "discarded"
        assert result["recalculate_power"] is True
    assert rule_condition_4(_arms(**{"S-u": 3}))["recalculate_power"] is False


def test_zero_events_report_an_upper_bound_not_a_zero_hazard() -> None:
    result = rule_condition_5(_arms())
    assert result["arms_with_zero_events"]["S-u"] == pytest.approx(0.2589, abs=1e-4)
    assert "do not show hazard = 0" in result["statement"]


def test_recalculation_uses_the_higher_r_variant_never_the_lower() -> None:
    inputs = planning_inputs(_arms(**{"R-walk": 0, "R-restart": 2, "D": 1, "S-u": 4}))
    assert inputs["p_r_point_higher_variant"] == pytest.approx(0.2)
    inputs = planning_inputs(_arms(**{"R-walk": 2, "R-restart": 0, "D": 1, "S-u": 4}))
    assert inputs["p_r_point_higher_variant"] == pytest.approx(0.2)
    assert inputs["p_s_point"] == pytest.approx(0.4)
    assert inputs["p_d_point"] == pytest.approx(0.1)


def test_abort_and_no_record_stay_in_the_denominator_invalid_is_reported_apart() -> None:
    cells = [
        _outcome("D", 8101),
        _outcome("D", 8102, state="abort", executions=700, reason="broker"),
        _outcome("D", 8103, state="no-record", executions=0, reason="none"),
        _outcome("D", 8104, event=True, t_first=321, first_c1=321, hit_steps=2),
        _outcome("D", 8105, state="invalid", executions=0, reason="config"),
    ]
    summary = summarize_arm("D", cells)
    assert summary["denominator"] == 4
    assert summary["invalid"] == 1
    assert summary["events_first_c1_or_c2"] == 1
    assert summary["at_risk_executions"] == 2000 + 700 + 0 + 321
    assert summary["t_first_observed"] == [321]
    assert summary["p_hat"] == pytest.approx(0.25)


def test_condition_6_labels_follow_the_fixed_rule() -> None:
    capacity = 57.0
    assert n_capacity(capacity, 8) == 152
    common = {"p_r_point_higher_variant": 0.0, "p_d_point": 0.0}
    possible = feasibility(
        {"p_s_point": 0.3, "p_s_upper95": 0.6, **common},
        abort=0.0,
        campaigns_per_host_day=capacity,
        sims=500,
    )
    assert possible["verdict"] == "possible"
    reduced = feasibility(
        {"p_s_point": 0.0, "p_s_upper95": 0.259, **common},
        abort=0.0,
        campaigns_per_host_day=capacity,
        sims=500,
    )
    assert reduced["verdict"] == "reduced"
    assert reduced["required_n_point"] is None
    impossible = feasibility(
        {"p_s_point": 0.1, "p_s_upper95": 0.3, "p_r_point_higher_variant": 0.3, "p_d_point": 0.3},
        abort=0.0,
        campaigns_per_host_day=capacity,
        sims=200,
    )
    assert impossible["verdict"] == "impossible"
    assert "no claim of confirmatory power" in possible["note"]


def test_vocabulary_equality_is_per_seed_over_all_four_arms() -> None:
    arms = ("R-walk", "R-restart", "D", "S-u")
    assert vocabulary_equal([_outcome(arm, 8101) for arm in arms])
    unequal = [*[_outcome(arm, 8101) for arm in arms[:3]], _outcome("S-u", 8101, vocabulary=("c",))]
    assert not vocabulary_equal(unequal)
    assert not vocabulary_equal([_outcome(arm, 8101, vocabulary=()) for arm in arms])


def test_missing_cell_is_no_record_and_a_wrong_image_is_invalid(tmp_path: Path) -> None:
    design = load_design(DESIGN)
    cell = planned_cells(design)[0]
    assert load_outcome(cell, tmp_path, design).state == "no-record"
    config = design.cell_config(cell)
    report = {
        "image_id": "sha256:" + "0" * 64,
        "config": {
            "random_seed": cell.seed,
            "execution_budget": cell.budget,
            "search_policy": config.search_policy.value,
            "mutation_policy": config.mutation_policy.value,
        },
        "steps": [],
    }
    cell_paths(cell, tmp_path)["report"].write_text(json.dumps(report), encoding="utf-8")
    outcome = load_outcome(cell, tmp_path, design)
    assert outcome.state == "invalid"
    assert "image_id" in str(outcome.reason)


def test_schedule_and_analysis_end_to_end_on_synthetic_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = DESIGN.read_text(encoding="utf-8")
    budget_line = next(line for line in text.splitlines() if line.startswith("budget = "))
    design = parse_design(text.replace(budget_line, "budget = 6"))
    cells = planned_cells(design)
    aborted = cells[1].run_id
    seen_env: dict[str, dict[str, str]] = {}

    def fake_run(cell, output: Path, env: dict[str, str], bash: str, *, limit_seconds: float):
        assert limit_seconds == design.campaign_watchdog_seconds
        seen_env[cell.run_id] = env
        paths = cell_paths(cell, output)
        report: dict[str, object] = synthetic_demo_report(
            cell.seed,
            cell.budget,
            EffectSearchPolicy(env["DEMO_POLICY"]),
            MutationPolicy(env["DEMO_MUTATION_POLICY"]),
        )
        report["image_id"] = design.image_digest
        report["sentinel_set"] = {
            "generator_id": design.sentinel_generator_id,
            "generator_seed": int(env["DEMO_SENTINEL_SEED"]),
            "count": int(env["DEMO_SENTINEL_COUNT"]),
            "names": ["a", "b", "c"],
        }
        steps = report["steps"]
        assert isinstance(steps, list)
        if cell.run_id == aborted:
            report = {
                "label": "demo run",
                "producer": "native",
                "aborted": {"step_index": 2, "reason": "broker", "case_id": "c", "observed": None},
            }
            steps = steps[:2]
        paths["report"].write_text(json.dumps(report), encoding="utf-8")
        paths["steps_jsonl"].write_text(
            "".join(json.dumps(step) + "\n" for step in steps), encoding="utf-8"
        )
        paths["log"].write_text("engine=29.8.0\n", encoding="utf-8")
        return CellResult(cell, 0, 1.0, paths["report"], True, paths["log"])

    monkeypatch.setattr(run_hazard_pilot, "run_cell_with_watchdog", fake_run)
    monkeypatch.setattr(run_hazard_pilot, "wait_for_disk", lambda output, fraction: 0)
    schedule = Schedule(design, tmp_path, "/bin/false")
    states = [schedule.run_one(cell) for cell in cells]
    assert {state["state"] for state in states} == {"ran"}
    env = seen_env[cells[0].run_id]
    assert env["DEMO_SENTINEL_COUNT"] == str(design.sentinel_count)
    assert env["DEMO_OBSERVER_INTEGRITY_POLICY"] == "invalid-continue"
    assert env["SKIP_BUILD"] == "1"
    assert env["TAR_VERSION"] == "7.5.2"

    assert run_hazard_pilot.print_status(tmp_path, len(cells)) == 0
    assert "finished 40/40" in capsys.readouterr().out

    report = analyze(tmp_path, design, sims=50)
    arms = report["arms"]
    assert sum(arm["campaigns"] for arm in arms.values()) == 40
    assert sum(arm["complete"] for arm in arms.values()) == 39
    assert sum(arm["abort"] for arm in arms.values()) == 1
    assert all(arm["denominator"] == 10 for arm in arms.values())
    assert sum(arm["invalid"] for arm in arms.values()) == 0
    assert arms["R-walk"]["non_event_metrics"]["rejected_ratio"] is not None
    assert sum(cell["executions"] for cell in report["cells"]) == 39 * 6 + 2
    assert report["clocks"]["monotonic_over_real_pooled"] > 0
    rendered = render_markdown(report)
    assert "no claim of confirmatory power" in rendered
    assert "R-restart" in rendered

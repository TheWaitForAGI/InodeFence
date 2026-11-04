"""EXP-0 figure/table generator: table rows, placeholder, KM-curve data, PNG creation."""

import importlib

import pytest
from scripts.analyze_exp0 import build_report, cell_from_row

# paper/ is not on pyright's include path; import the renderer dynamically.
render = importlib.import_module("paper.figures.render_exp0_survival")


def _rec(**over):
    base = {
        "random_seed": 9001,
        "arm": "R",
        "execution_budget": 200,
        "executions_completed": 200,
        "complete": True,
        "aborted": False,
        "abort_reason": None,
        "t_first": 200,
        "t_first_event": 0,
        "hit_steps": 0,
        "first_c0": None,
        "first_c1": None,
        "first_c2": None,
        "boundary_attempt_keys": 0,
        "rejected_executions": 0,
        "observation_failures": 0,
        "u_viol": 0,
    }
    base.update(over)
    return base


def _report():
    from scripts.analyze_exp0 import _DEFAULT_FIELD_MAP

    rows = [
        _rec(arm="R", random_seed=9001, boundary_attempt_keys=8, rejected_executions=20),
        _rec(arm="R", random_seed=9002, boundary_attempt_keys=4, rejected_executions=10),
        _rec(
            arm="S-u",
            random_seed=9001,
            t_first=150,
            t_first_event=1,
            hit_steps=3,
            first_c1=150,
            boundary_attempt_keys=25,
            u_viol=2,
        ),
        _rec(arm="S-u", random_seed=9002, boundary_attempt_keys=30),
    ]
    cells = [cell_from_row(r, _DEFAULT_FIELD_MAP) for r in rows]
    return build_report(cells, field_map=_DEFAULT_FIELD_MAP, sources=["t"])


def test_km_curve_enrichment_in_report():
    # S-u: one event at 150 of 2 at risk -> S=0.5; the other campaign censored at budget 200
    s_u = _report()["item5_first_contract_index"]["by_arm"]["S-u"]["t_first_combined_c1_or_c2"]
    assert s_u["km_curve"] == [{"time": 150, "survival": 0.5, "at_risk": 2, "events": 1}]
    assert s_u["censored_times"] == [200]
    # R: no events -> empty curve, both campaigns censored at 200
    r = _report()["item5_first_contract_index"]["by_arm"]["R"]["t_first_combined_c1_or_c2"]
    assert r["km_curve"] == []
    assert r["censored_times"] == [200, 200]


def test_summary_table_has_rows_and_denominators():
    table = render.render_summary_table(_report())
    assert "# EXP-0 pilot summary" in table
    assert "measurement only" in table.lower() or "effectiveness claim" in table
    # abort table has a row per arm
    assert "| R |" in table and "| S-u |" in table
    # first-contract table includes a T_first row and a risk-set denominator column
    assert "T_first" in table and "risk_set_n" in table
    # dense table exposes the rejected ratio denominator
    assert "rejected_ratio" in table and "executions" in table


def test_placeholder_when_no_results():
    assert "TBD — EXP-0 미실행" in render.render_summary_table(None)
    empty = {"number_cells": 0}
    assert "TBD — EXP-0 미실행" in render.render_summary_table(empty)
    assert render.has_results(None) is False
    assert render.has_results(_report()) is True


def test_render_km_figure_returns_false_without_results(tmp_path):
    out = tmp_path / "none.png"
    assert render.render_km_figure(None, out) is False
    assert not out.exists()


def test_render_km_figure_writes_png(tmp_path):
    pytest.importorskip("matplotlib")
    out = tmp_path / "exp0-survival.png"
    assert render.render_km_figure(_report(), out) is True
    assert out.exists() and out.stat().st_size > 0


def test_step_xy_starts_at_one_and_flattens_to_horizon():
    xs, ys = render._step_xy([{"time": 150, "survival": 0.5}], horizon=200)
    assert xs == [0.0, 150.0, 200.0]
    assert ys == [1.0, 0.5, 0.5]
    assert render._survival_at([{"time": 150, "survival": 0.5}], 149) == 1.0
    assert render._survival_at([{"time": 150, "survival": 0.5}], 150) == 0.5


def test_dense_u_viol_c0_and_timing_distribution_in_table():
    from scripts.analyze_exp0 import _DEFAULT_FIELD_MAP, build_report, cell_from_row

    wrapper = {
        "summary": _rec(arm="S-u", random_seed=9001, u_viol=2, u_viol_c0=5),
        "config_nonconformant": False,
        "timing": {
            "wall_seconds": 100.0,
            "step_wall_seconds": [1.0, 2.0, 3.0, 4.0],
            "execution_mode": "per-case-container",
            "full_step_seconds_p50": 2.0,
            "full_step_seconds_max": 4.0,
        },
    }
    cell = cell_from_row(wrapper, _DEFAULT_FIELD_MAP)
    table = render.render_summary_table(
        build_report([cell], field_map=_DEFAULT_FIELD_MAP, sources=["t"])
    )
    assert "u_viol_c0" in table
    assert "Full-step time distribution" in table and "p50" in table and "max" in table

"""EXP-0 report generator over lane 5's RdsCellSummary schema (items 1-7, denominators)."""

import json

import pytest
from scripts.analyze_exp0 import (
    _DEFAULT_FIELD_MAP,
    CellSummary,
    InvalidCell,
    build_multitarget_report,
    build_report,
    cell_from_row,
    load_cells,
    main,
)

from inodefence.evaluation.encoding import json_bytes

DEFAULT_MAP = dict(_DEFAULT_FIELD_MAP)


def _wrap(
    rec=None,
    *,
    timing=None,
    environment=None,
    invalid=False,
    invalid_reason=None,
    unfingerprinted=0,
):
    """Build a lane 5 wrapper file dict: inner summary + top-level timing/env/invalid."""
    wrapper = {
        "schema_version": 1,
        "label": ["demo run", "unregistered G1 smoke"],
        "producer": "native",
        "summary": None if invalid else rec,
        "config_nonconformant": invalid,
        "invalid_reason": invalid_reason,
        "unfingerprinted_hit_steps": unfingerprinted,
    }
    if timing is not None:
        wrapper["timing"] = timing
    if environment is not None:
        wrapper["environment"] = environment
    return wrapper


def _rec(**over):
    """A lane 5 summary_record() dict with sensible defaults; override per test."""
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


def _cells(rows):
    return [cell_from_row(r, DEFAULT_MAP) for r in rows]


FIXTURE = [
    _rec(
        arm="R",
        random_seed=9001,
        complete=True,
        first_c0=50,
        boundary_attempt_keys=8,
        rejected_executions=20,
    ),
    _rec(
        arm="R",
        random_seed=9002,
        complete=False,
        aborted=True,
        abort_reason="broker",
        executions_completed=120,
        t_first=120,
        boundary_attempt_keys=3,
        rejected_executions=10,
        observation_failures=1,
    ),
    _rec(
        arm="S-u",
        random_seed=9001,
        t_first=150,
        t_first_event=1,
        hit_steps=4,
        first_c0=10,
        first_c1=150,
        boundary_attempt_keys=25,
        rejected_executions=5,
        u_viol=2,
    ),
    _rec(arm="S-u", random_seed=9002, first_c0=20, boundary_attempt_keys=30, rejected_executions=6),
]


def _report(rows=FIXTURE):
    return build_report(_cells(rows), field_map=DEFAULT_MAP, sources=["t"])


def test_item1_aborts_by_reason_and_arm():
    report = _report()
    r = report["item1_aborts"]["by_arm"]["R"]
    assert r["number_cells"] == 2 and r["number_complete"] == 1 and r["number_abort"] == 1
    assert r["abort_by_reason"]["broker"] == 1 and r["abort_fraction"] == pytest.approx(0.5)
    s = report["item1_aborts"]["by_arm"]["S-u"]
    assert s["number_abort"] == 0 and s["abort_fraction"] == 0.0


def test_items_2_3_4_unavailable_without_timing_fields():
    report = _report()
    assert report["item2_p95_full_step"]["available"] is False
    assert report["item3_throughput"]["available"] is False
    assert report["item4_throughput_parity"]["by_execution_mode"] == {}
    assert report["item4_throughput_parity"]["parity_verdict"] is None


def test_item5_first_index_and_combined_t_first():
    report = _report()["item5_first_contract_index"]["by_arm"]
    # R: C0 observed at 50 for s9001; s9002 (abort) censored at 120 -> 1 observed, 1 censored
    r_c0 = report["R"]["contracts"]["C0"]
    assert r_c0["number_observed"] == 1 and r_c0["observed_indices"] == [50]
    assert r_c0["number_right_censored"] == 1
    # R T_first: both censored -> no median
    assert report["R"]["t_first_combined_c1_or_c2"]["number_observed"] == 0
    assert report["R"]["t_first_combined_c1_or_c2"]["km_median_executions"] is None
    # S-u T_first: one event at 150 of 2 at risk -> S=0.5 at 150 -> median 150
    s_t = report["S-u"]["t_first_combined_c1_or_c2"]
    assert s_t["number_observed"] == 1 and s_t["observed_t_first"] == [150]
    assert s_t["km_median_executions"] == 150
    # S-u C0 observed at both seeds
    assert report["S-u"]["contracts"]["C0"]["number_observed"] == 2


def test_item6_dense_signals_with_denominators():
    report = _report()["item6_dense_signals"]["by_arm"]
    r = report["R"]
    assert r["boundary_attempt_keys"]["total"] == 11
    assert r["boundary_attempt_keys"]["mean_per_cell"] == pytest.approx(5.5)
    assert r["rejected_ratio"]["value"] == pytest.approx(30 / 320)
    assert r["observation_failures_total"] == 1
    assert report["S-u"]["u_viol"]["total_unique_c1_c2_fingerprints"] == 2


def test_item7_hazard_proxy_reference_only():
    report = _report()["item7_hazard_proxy"]
    assert "참고값" in report["label"] or "reference" in report["label"]
    assert report["by_arm"]["S-u"]["proxy_per_execution"] == pytest.approx(4 / 400)
    assert report["by_arm"]["R"]["proxy_per_execution"] == 0.0
    assert "zero_hit" not in report  # S-u has hits


def test_zero_hit_rule_of_three_is_campaign_unit():
    rows = [
        _rec(arm="R", random_seed=9001),
        _rec(arm="R", random_seed=9002),
        _rec(arm="S-u", random_seed=9001),
    ]
    hazard = build_report(_cells(rows), field_map=DEFAULT_MAP, sources=["t"])["item7_hazard_proxy"]
    assert "zero_hit" in hazard
    r = hazard["zero_hit"]["by_arm"]["R"]
    assert r["campaign_denominator"] == 2
    assert r["campaign_unit_rule_of_three_upper95"] == pytest.approx(1.5)
    assert r["execution_denominator"] == 400  # exploratory exec-unit still reported


def test_invalid_bucket_excluded_from_risk_set():
    rows = [
        _rec(arm="R", random_seed=9001, first_c1=50, t_first=50, t_first_event=1, hit_steps=1),
        {**_rec(arm="R", random_seed=9002), "config_nonconformant": True, "complete": False},
    ]
    report = build_report(_cells(rows), field_map=DEFAULT_MAP, sources=["t"])
    assert report["item1_aborts"]["by_arm"]["R"]["number_invalid_nonconformant"] == 1
    # invalid cell excluded: only 1 cell in the C1 risk set
    assert report["item5_first_contract_index"]["by_arm"]["R"]["number_invalid_excluded"] == 1
    assert (
        report["item5_first_contract_index"]["by_arm"]["R"]["contracts"]["C1"][
            "denominator_cells_in_risk_set"
        ]
        == 1
    )


def test_unknown_abort_reason_buckets_to_other():
    rows = [
        _rec(
            arm="R",
            complete=False,
            aborted=True,
            abort_reason="disk_full",
            executions_completed=10,
            t_first=10,
        )
    ]
    report = build_report(_cells(rows), field_map=DEFAULT_MAP, sources=["t"])
    assert report["item1_aborts"]["by_arm"]["R"]["abort_by_reason"]["other"] == 1


def test_field_map_override_and_flat_record():
    # a flat (unwrapped) record with two renamed keys; the rest keep default names
    flat = _rec()
    del flat["random_seed"]
    del flat["arm"]
    flat["theSeed"] = 7
    flat["theArm"] = "D"
    cell = cell_from_row(flat, {**DEFAULT_MAP, "seed": "theSeed", "arm": "theArm"})
    assert cell.seed == 7 and cell.arm == "D"


def test_main_reads_lane5_index_json(tmp_path, capsys):
    run = tmp_path / "run"
    summaries = run / "summaries"
    summaries.mkdir(parents=True)
    entries = []
    for rec in FIXTURE:
        run_id = f"7.5.2-{rec['arm']}-s{rec['random_seed']}"
        wrapped = {
            "schema_version": 1,
            "label": ["demo run", "unregistered G1 smoke"],
            "producer": "native",
            "source": {"report": f"{run_id}.json", "report_present": True, "steps_from": "report"},
            "summary": rec,
            "u_viol_note": "fingerprint on feedback_eligible steps only",
        }
        path = summaries / f"{run_id}.summary.json"
        path.write_text(json.dumps(wrapped))
        entries.append(
            {
                "run_id": run_id,
                "arm": rec["arm"],
                "seed": rec["random_seed"],
                "budget": rec["execution_budget"],
                "summary": f"summaries/{run_id}.summary.json",
                "complete": rec["complete"],
                "aborted": rec["aborted"],
                "hit": rec["t_first_event"] == 1,
            }
        )
    index = {"cells": entries, "abort_count": 1, "abort_le_1": True}
    (summaries / "index.json").write_text(json.dumps(index))

    exit_code = main(["--index", str(summaries / "index.json"), "--format", "json"])
    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["number_cells"] == 4
    assert report["item1_aborts"]["by_arm"]["R"]["number_abort"] == 1
    assert (
        report["item5_first_contract_index"]["by_arm"]["S-u"]["t_first_combined_c1_or_c2"][
            "km_median_executions"
        ]
        == 150
    )


# --- lane 5 wrapper: timing, invalid-via-index, environment ----------------------


def test_wrapper_timing_enables_items_2_3_4():
    cells = [
        cell_from_row(
            _wrap(
                _rec(arm="R", random_seed=9001),
                timing={
                    "wall_seconds": 3600.0,
                    "step_wall_seconds": [1.0, 2.0, 3.0, 4.0],
                    "execution_mode": "per-case-container",
                    "exec_per_hour": 200.0,
                    "full_step_seconds_p95": 4.0,
                },
            ),
            DEFAULT_MAP,
        ),
        cell_from_row(
            _wrap(
                _rec(arm="S-u", random_seed=9001),
                timing={
                    "wall_seconds": 1800.0,
                    "step_wall_seconds": [2.0, 2.0],
                    "execution_mode": "worker-pool",
                },
            ),
            DEFAULT_MAP,
        ),
    ]
    report = build_report(cells, field_map=DEFAULT_MAP, sources=["t"])
    p95 = report["item2_p95_full_step"]
    assert p95["available"] is True
    # nearest-rank p95 of [1,2,3,4] = 4.0; pooled over [1,2,3,4,2,2]
    assert p95["per_cell"][0]["p95_seconds"] == 4.0
    assert p95["pooled"]["number_steps"] == 6
    tput = report["item3_throughput"]
    assert tput["available"] is True
    assert tput["summed"]["exec_per_hour"] == pytest.approx(400 / (5400 / 3600))
    modes = report["item4_throughput_parity"]["by_execution_mode"]
    assert set(modes) == {"per-case-container", "worker-pool"}


def test_invalid_wrapper_null_summary_uses_index_identity():
    entry = {"run_id": "7.5.2-D-s9003", "arm": "D", "seed": 9003, "invalid": True}
    cell = cell_from_row(
        _wrap(invalid=True, invalid_reason="budget mismatch vs plan"),
        DEFAULT_MAP,
        entry=entry,
    )
    assert isinstance(cell, InvalidCell)
    assert cell.seed == 9003 and cell.arm == "D"
    assert cell.invalid_reason == "budget mismatch vs plan"


def test_invalid_wrapper_without_identity_raises():
    with pytest.raises(ValueError):
        cell_from_row(_wrap(invalid=True), DEFAULT_MAP)


def test_environment_and_unfingerprinted_passthrough():
    env = {"host_machine": "x86_64", "docker_server_version": "29.8.1", "node_tar_version": "7.5.2"}
    cells = [
        cell_from_row(
            _wrap(
                _rec(arm="R", random_seed=9001, hit_steps=2),
                environment=env,
                unfingerprinted=3,
            ),
            DEFAULT_MAP,
        )
    ]
    report = build_report(cells, field_map=DEFAULT_MAP, sources=["t"])
    assert report["environment"]["homogeneous"] is True
    assert report["environment"]["distinct"][0]["docker_server_version"] == "29.8.1"
    dense = report["item6_dense_signals"]["by_arm"]["R"]
    assert dense["unfingerprinted_hit_steps_total"] == 3


def test_build_report_counts_valid_and_invalid():
    cells = [
        cell_from_row(_wrap(_rec(arm="R", random_seed=9001)), DEFAULT_MAP),
        cell_from_row(
            _wrap(invalid=True, invalid_reason="parse failure"),
            DEFAULT_MAP,
            entry={"arm": "R", "seed": 9002},
        ),
    ]
    assert isinstance(cells[0], CellSummary) and isinstance(cells[1], InvalidCell)
    report = build_report(cells, field_map=DEFAULT_MAP, sources=["t"])
    assert report["number_valid_cells"] == 1 and report["number_invalid_cells"] == 1
    assert report["item1_aborts"]["by_arm"]["R"]["number_invalid_nonconformant"] == 1
    assert report["item1_aborts"]["by_arm"]["R"]["number_cells"] == 2


# --- lane 5 additive fields: u_viol_c0 + full_step p50/max ------------------------


def test_p50_max_and_runner_passthrough_in_item2():
    cell = cell_from_row(
        _wrap(
            _rec(arm="R", random_seed=9001),
            timing={
                "wall_seconds": 3600.0,
                "step_wall_seconds": [1.0, 2.0, 3.0, 4.0],
                "execution_mode": "per-case-container",
                "full_step_seconds_p50": 2.0,
                "full_step_seconds_p95": 4.0,
                "full_step_seconds_max": 4.0,
            },
        ),
        DEFAULT_MAP,
    )
    report = build_report([cell], field_map=DEFAULT_MAP, sources=["t"])
    pc = report["item2_p95_full_step"]["per_cell"][0]
    # nearest-rank p50 of [1,2,3,4] = ceil(0.5*4)=2 -> ordered[1] = 2.0
    assert pc["p50_seconds"] == 2.0 and pc["p95_seconds"] == 4.0 and pc["max_seconds"] == 4.0
    assert pc["runner_p50_seconds"] == 2.0 and pc["runner_max_seconds"] == 4.0
    pooled = report["item2_p95_full_step"]["pooled"]
    assert pooled["p50_seconds"] == 2.0 and pooled["max_seconds"] == 4.0


def test_u_viol_c0_in_dense_signals():
    rows = [
        _rec(arm="S-u", random_seed=9001, u_viol=2, u_viol_c0=5),
        _rec(arm="S-u", random_seed=9002, u_viol=0, u_viol_c0=3),
    ]
    cells = [cell_from_row(r, DEFAULT_MAP) for r in rows]
    dense = build_report(cells, field_map=DEFAULT_MAP, sources=["t"])["item6_dense_signals"][
        "by_arm"
    ]["S-u"]
    assert dense["u_viol_c0"]["total_unique_c0_fingerprints"] == 8
    assert dense["u_viol_c0"]["mean_per_cell"] == 4.0
    # the existing C1/C2 u_viol is unchanged
    assert dense["u_viol"]["total_unique_c1_c2_fingerprints"] == 2


# --- abort-reason vocabulary from the shared enum (cleanup_reset) -----------------


def test_abort_reasons_includes_cleanup_reset():
    from scripts.analyze_exp0 import ABORT_REASONS

    assert "cleanup_reset" in ABORT_REASONS
    assert set(ABORT_REASONS) >= {
        "observer_integrity",
        "broker",
        "cleanup_inspect",
        "cleanup_remove",
        "cleanup_reset",
        "other",
    }


def test_cleanup_reset_abort_bucketed_distinctly():
    rows = [
        _rec(
            arm="R",
            complete=False,
            aborted=True,
            abort_reason="cleanup_reset",
            executions_completed=10,
            t_first=10,
        )
    ]
    report = build_report(_cells(rows), field_map=DEFAULT_MAP, sources=["t"])
    by_reason = report["item1_aborts"]["by_arm"]["R"]["abort_by_reason"]
    assert by_reason["cleanup_reset"] == 1 and by_reason["other"] == 0


# --- lane 3 contingency -> arm x abort independence flag (item 8) -----------------


def test_build_report_with_independence_adds_item8():
    from inodefence.evaluation.independence import arm_abort_independence

    cells = [cell_from_row(_rec(arm="R", random_seed=9001), DEFAULT_MAP)]
    indep = arm_abort_independence([[4, 0, 0], [4, 0, 0], [4, 0, 0]], ["R", "D", "S-u"])
    report = build_report(cells, field_map=DEFAULT_MAP, sources=["t"], independence=indep)
    assert report["arm_abort_independence"]["flag"] == "not_assessable"


def test_main_contingency_option(tmp_path, capsys):
    cell = tmp_path / "7.5.2-R-s9001.summary.json"
    cell.write_text(json.dumps({"summary": _rec(arm="R", random_seed=9001)}))
    contingency = tmp_path / "contingency.json"
    contingency.write_text(
        json.dumps(
            {
                "arms": ["R", "D", "S-u"],
                "per_campaign": {
                    "columns": ["complete", "aborted", "invalid"],
                    "matrix": [[4, 0, 0], [4, 0, 0], [4, 0, 0]],
                },
            }
        )
    )
    exit_code = main(["--cell", str(cell), "--contingency", str(contingency), "--format", "json"])
    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["arm_abort_independence"]["flag"] == "not_assessable"
    assert report["arm_abort_independence"]["arms"] == ["R", "D", "S-u"]


def test_item5_abort_sensitivity_structure_and_risk_set():
    # item5 gains an additive abort-censoring sensitivity (EXCLUDE + CENSOR_AT_BUDGET);
    # the primary body stays right-censored (CENSOR_AT_ABORT).
    item5 = _report()["item5_first_contract_index"]
    sens = item5["sensitivity"]
    assert sens["primary_policy"] == "censor-at-abort"
    assert set(sens["policies"]) == {"exclude", "censor-at-budget"}
    # R has one abort (s9002): EXCLUDE drops it (risk set 1), CENSOR_AT_BUDGET keeps it (2).
    assert sens["policies"]["exclude"]["by_arm"]["R"]["number_in_risk_set"] == 1
    assert sens["policies"]["censor-at-budget"]["by_arm"]["R"]["number_in_risk_set"] == 2
    # S-u has no abort -> identical across policies (only aborts move).
    assert sens["policies"]["exclude"]["by_arm"]["S-u"]["number_in_risk_set"] == 2
    assert sens["policies"]["censor-at-budget"]["by_arm"]["S-u"]["number_in_risk_set"] == 2


def test_item5_abort_sensitivity_median_moves_with_policy():
    # Two events (50, 100) and one no-event abort at 60, budget 200. The abort policy moves the
    # T_first KM median: dropping the abort (EXCLUDE) makes 2 events -> S=0.5 at 50; censoring it
    # at abort (primary) or at budget keeps 3 at risk -> median 100.
    rows = [
        _rec(arm="R", random_seed=1, t_first=50, t_first_event=1, first_c1=50, hit_steps=1),
        _rec(arm="R", random_seed=2, t_first=100, t_first_event=1, first_c1=100, hit_steps=1),
        _rec(
            arm="R",
            random_seed=3,
            complete=False,
            aborted=True,
            abort_reason="broker",
            executions_completed=60,
            t_first=60,
            t_first_event=0,
        ),
    ]
    item5 = build_report(_cells(rows), field_map=DEFAULT_MAP, sources=["t"])[
        "item5_first_contract_index"
    ]
    primary = item5["by_arm"]["R"]["t_first_combined_c1_or_c2"]["km_median_executions"]
    excl = item5["sensitivity"]["policies"]["exclude"]["by_arm"]["R"]["km_median_executions"]
    budget = item5["sensitivity"]["policies"]["censor-at-budget"]["by_arm"]["R"][
        "km_median_executions"
    ]
    assert primary == 100  # abort censored at 60 (CENSOR_AT_ABORT)
    assert excl == 50  # abort dropped -> events at 50, 100 -> S=0.5 at 50
    assert budget == 100  # abort censored at budget 200


def _write_multitarget_index(tmp_path):
    """A lane-5 index.json spanning 2 targets (train + holdout), EXP-3 schema shape."""
    summaries = tmp_path / "summaries"
    summaries.mkdir(parents=True)
    targets_meta = [
        {
            "target_id": "nt-7.5.2",
            "extractor": "node-tar",
            "version": "7.5.2",
            "role": "train",
            "hypothesis": "H-A",
            "exposure": "pre-exposed",
        },
        {
            "target_id": "nt-holdout",
            "extractor": "node-tar",
            "version": "7.6.0",
            "role": "holdout",
            "hypothesis": "H-A",
            "exposure": "none",
        },
    ]
    cells = []
    su_over = {"t_first": 120, "t_first_event": 1, "first_c1": 120, "hit_steps": 1}
    for tid, role in (("nt-7.5.2", "train"), ("nt-holdout", "holdout")):
        for arm, over in (("R", {}), ("S-u", su_over)):
            rec = _rec(arm=arm, random_seed=1, **over)
            run_id = f"{tid}-{arm}-s1"
            (summaries / f"{run_id}.summary.json").write_text(
                json.dumps({"summary": rec, "schema_version": 1})
            )
            cells.append(
                {
                    "run_id": run_id,
                    "arm": arm,
                    "seed": 1,
                    "budget": rec["execution_budget"],
                    "summary": f"summaries/{run_id}.summary.json",
                    "target_id": tid,
                    "role": role,
                    "hypothesis": "H-A",
                }
            )
    analysis_plan = {
        "confirmatory_family": "holdout:S-u-vs-R,S-u-vs-D",
        "confirmatory_test": "exact-logrank-permutation-v1",
        "multiplicity": "holm-fwer-v1",
        "primary_endpoint": "t_first",
        "event_threshold": 5,
        "confirmatory_targets": ["nt-holdout"],
        "confirmatory_contrasts": [
            {
                "order": 1,
                "target_id": "nt-holdout",
                "role": "holdout",
                "hypothesis": "H-A",
                "arm_a": "S-u",
                "arm_b": "R",
                "contrast": "S-u-vs-R",
            },
            {
                "order": 2,
                "target_id": "nt-holdout",
                "role": "holdout",
                "hypothesis": "H-A",
                "arm_a": "S-u",
                "arm_b": "D",
                "contrast": "S-u-vs-D",
            },
        ],
    }
    index = {"targets": targets_meta, "analysis_plan": analysis_plan, "cells": cells}
    (summaries / "index.json").write_text(json.dumps(index))
    return summaries / "index.json"


def test_single_target_report_stays_flat_schema1():
    # FIXTURE has one (default) target_id -> legacy flat build_report, byte-shape unchanged.
    report = _report()
    assert report["schema_version"] == 1
    assert "by_target" not in report and "target_ids" not in report


def test_multitarget_sections_no_pooling(tmp_path, capsys):
    index = _write_multitarget_index(tmp_path)
    assert main(["--index", str(index), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == 2
    assert report["target_ids"] == ["nt-7.5.2", "nt-holdout"]
    train, hold = report["by_target"]["nt-7.5.2"], report["by_target"]["nt-holdout"]
    assert train["role"] == "train" and train["hypothesis"] == "H-A"
    assert hold["role"] == "holdout" and "confirmatory" in hold["role_interpretation"]
    # no pooling: each target sees only its own 2 cells
    assert train["number_cells"] == 2 and hold["number_cells"] == 2
    assert report["number_cells"] == 4
    assert "item5_first_contract_index" in train and "item1_aborts" in hold


def test_multitarget_echoes_frozen_analysis_plan(tmp_path, capsys):
    index = _write_multitarget_index(tmp_path)
    assert main(["--index", str(index), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    plan = report["analysis_plan"]
    assert plan["multiplicity"] == "holm-fwer-v1" and plan["primary_endpoint"] == "t_first"
    assert plan["event_threshold"] == 5
    assert [c["contrast"] for c in plan["confirmatory_contrasts"]] == ["S-u-vs-R", "S-u-vs-D"]
    assert report["confirmatory_targets"] == ["nt-holdout"]


def test_multitarget_markdown_renders(tmp_path, capsys):
    index = _write_multitarget_index(tmp_path)
    assert main(["--index", str(index), "--format", "markdown"]) == 0
    out = capsys.readouterr().out
    assert "EXP-3 multi-target" in out and "nt-holdout" in out and "S-u-vs-R" in out


def test_index_entries_skips_targets_metadata_list(tmp_path, capsys):
    # top-level targets[] (no 'summary' pointer) must not be mistaken for the cell list.
    index = _write_multitarget_index(tmp_path)
    assert main(["--index", str(index), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["number_cells"] == 4  # resolved the 4-cell list, not the 2-entry targets[]


_SU_HIT = {"t_first": 20, "t_first_event": 1, "first_c1": 20, "hit_steps": 1}


def _mt_cell(arm, seed, target_id, role, **over):
    """A CellSummary tagged with target_id/role via the index entry (as cell_from_row reads it)."""
    rec = _rec(arm=arm, random_seed=seed, **over)
    entry = {"target_id": target_id, "role": role, "hypothesis": "H-A", "summary": "x"}
    return cell_from_row({"summary": rec}, DEFAULT_MAP, entry=entry)


def test_confirmatory_permutation_and_holm():
    # holdout target h, R/D/S-u x 3 seeds, S-u hits@20 each; R/D censored. Perfect separation
    # at n=3 still gives permutation p=2/8=0.25 (underpowered), Holm on [.25,.25]=[.5,.5].
    cells = []
    for s in (1, 2, 3):
        cells += [
            _mt_cell("S-u", s, "h", "holdout", **_SU_HIT),
            _mt_cell("R", s, "h", "holdout"),
            _mt_cell("D", s, "h", "holdout"),
        ]
    plan = {
        "confirmatory_contrasts": [
            {"order": 1, "target_id": "h", "arm_a": "S-u", "arm_b": "R", "contrast": "S-u-vs-R"},
            {"order": 2, "target_id": "h", "arm_a": "S-u", "arm_b": "D", "contrast": "S-u-vs-D"},
        ],
        "event_threshold": 5,
        "multiplicity": "holm-fwer-v1",
        "primary_endpoint": "t_first",
        "confirmatory_test": "exact-logrank-permutation-v1",
        "confirmatory_targets": ["h"],
    }
    report = build_multitarget_report(
        cells, analysis_plan=plan, field_map=DEFAULT_MAP, sources=["t"]
    )
    conf = report["confirmatory"]
    assert conf["classification"] == "confirmatory-holm-fwer"
    cr = conf["contrasts"]
    assert [c["contrast"] for c in cr] == ["S-u-vs-R", "S-u-vs-D"]
    assert all(c["number_seed_blocks"] == 3 and c["total_events"] == 3 for c in cr)
    assert all(c["permutation"]["p_value"] == pytest.approx(0.25) for c in cr)
    assert all(c["holm_adjusted_p"] == pytest.approx(0.5) for c in cr)
    assert all(c["reject_at_alpha"] is False for c in cr)
    # events 3 < threshold 5 -> underpowered + descriptive rule-of-three (6 cells in the contrast)
    assert all(c["underpowered"] is True for c in cr)
    assert cr[0]["campaign_unit_rule_of_three_upper95"] == pytest.approx(0.5)  # 3 / 6


def test_build_multitarget_confirmatory_is_none_without_plan():
    cells = [
        _mt_cell("R", 1, "a", "train"),
        _mt_cell("S-u", 1, "a", "train"),
        _mt_cell("R", 1, "b", "holdout"),
        _mt_cell("S-u", 1, "b", "holdout"),
    ]
    report = build_multitarget_report(
        cells, analysis_plan=None, field_map=DEFAULT_MAP, sources=["t"]
    )
    assert report["confirmatory"] is None


def test_confirmatory_renders_in_markdown():
    cells = []
    for s in (1, 2, 3):
        cells += [
            _mt_cell("S-u", s, "h", "holdout", **_SU_HIT),
            _mt_cell("R", s, "h", "holdout"),
        ]
    plan = {
        "confirmatory_contrasts": [
            {"order": 1, "target_id": "h", "arm_a": "S-u", "arm_b": "R", "contrast": "S-u-vs-R"},
        ],
        "event_threshold": 5,
        "multiplicity": "holm-fwer-v1",
        "primary_endpoint": "t_first",
        "confirmatory_test": "exact-logrank-permutation-v1",
        "confirmatory_targets": ["h"],
    }
    report = build_multitarget_report(
        cells, analysis_plan=plan, field_map=DEFAULT_MAP, sources=["t"]
    )
    from scripts.analyze_exp0 import report_markdown

    md = report_markdown(report)
    assert "Confirmatory result" in md and "S-u-vs-R" in md


def test_cells_dir_reads_wrapper_target_object(tmp_path, capsys):
    # --cells-dir alone (no index): target_id/role come from the wrapper top-level `target`.
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    for tid, role in (("nt-a", "train"), ("nt-b", "holdout")):
        for arm in ("R", "S-u"):
            wrapped = {
                "summary": _rec(arm=arm, random_seed=1),
                "target": {"target_id": tid, "role": role, "hypothesis": "H-A"},
            }
            (summaries / f"{tid}-{arm}-s1.summary.json").write_text(json.dumps(wrapped))
    assert main(["--cells-dir", str(summaries), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == 2  # per-target from wrapper objects, not 'unspecified'
    assert set(report["by_target"]) == {"nt-a", "nt-b"}
    assert report["by_target"]["nt-b"]["role"] == "holdout"


def test_index_and_cells_dir_do_not_double_count(tmp_path, capsys):
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    entries = []
    for tid, role in (("nt-a", "train"), ("nt-b", "holdout")):
        for arm in ("R", "S-u"):
            run_id = f"{tid}-{arm}-s1"
            wrapped = {
                "summary": _rec(arm=arm, random_seed=1),
                "target": {"target_id": tid, "role": role, "hypothesis": "H-A"},
            }
            (summaries / f"{run_id}.summary.json").write_text(json.dumps(wrapped))
            entries.append(
                {
                    "run_id": run_id,
                    "arm": arm,
                    "seed": 1,
                    "budget": 200,
                    "summary": f"summaries/{run_id}.summary.json",
                    "target_id": tid,
                    "role": role,
                    "hypothesis": "H-A",
                }
            )
    (summaries / "index.json").write_text(json.dumps({"cells": entries}))
    exit_code = main(
        [
            "--index",
            str(summaries / "index.json"),
            "--cells-dir",
            str(summaries),
            "--format",
            "json",
        ]
    )
    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["number_cells"] == 4  # deduped by path, not 8
    assert set(report["by_target"]) == {"nt-a", "nt-b"}  # per-target, not 'unspecified'


def test_confirmatory_degenerate_contrast_rule_of_three_is_none():
    # contrast names arm R but the holdout has only S-u -> 0 paired blocks: R-o-3 must be None
    # (not 3/2 = 1.5, a nonsensical >1 probability bound).
    cells = [_mt_cell("S-u", s, "h", "holdout", **_SU_HIT) for s in (1, 2)]
    plan = {
        "confirmatory_contrasts": [
            {"order": 1, "target_id": "h", "arm_a": "S-u", "arm_b": "R", "contrast": "S-u-vs-R"},
        ],
        "event_threshold": 5,
        "multiplicity": "holm-fwer-v1",
        "primary_endpoint": "t_first",
        "confirmatory_test": "exact-logrank-permutation-v1",
        "confirmatory_targets": ["h"],
    }
    report = build_multitarget_report(
        cells, analysis_plan=plan, field_map=DEFAULT_MAP, sources=["t"]
    )
    c = report["confirmatory"]["contrasts"][0]
    assert c["number_seed_blocks"] == 0 and c["underpowered"] is True
    assert c["campaign_unit_rule_of_three_upper95"] is None


def test_confirmatory_supplementary_u_viol_a12():
    # S-u finds 2 unique violations per seed, R finds 0 -> A12 = 1.0 (>0.5 favors arm_a = S-u).
    cells = []
    for s in (1, 2, 3):
        cells += [
            _mt_cell("S-u", s, "h", "holdout", u_viol=2, **_SU_HIT),
            _mt_cell("R", s, "h", "holdout", u_viol=0),
        ]
    plan = {
        "confirmatory_contrasts": [
            {"order": 1, "target_id": "h", "arm_a": "S-u", "arm_b": "R", "contrast": "S-u-vs-R"},
        ],
        "event_threshold": 5,
        "multiplicity": "holm-fwer-v1",
        "primary_endpoint": "t_first",
        "confirmatory_test": "exact-logrank-permutation-v1",
        "confirmatory_targets": ["h"],
    }
    report = build_multitarget_report(
        cells, analysis_plan=plan, field_map=DEFAULT_MAP, sources=["t"]
    )
    conf = report["confirmatory"]
    sup = conf["contrasts"][0]["supplementary"]
    assert sup["u_viol_a12"] == pytest.approx(1.0)  # S-u(2) > R(0) every seed
    assert "NOT a confirmatory test" in sup["u_viol_a12_note"]
    # confirmatory-scope one-liner present, marks only reject_at_alpha as confirmatory
    assert "reject_at_alpha" in conf["confirmatory_scope"]
    # 7.5.6 is affected: the scope line must not re-state the role as a negative control.
    assert "negative control" not in conf["confirmatory_scope"]
    assert "no hit-count prediction" in conf["confirmatory_scope"]


def test_confirmatory_faster_arm_prevents_sign_flip():
    plan = {
        "confirmatory_contrasts": [
            {"order": 1, "target_id": "h", "arm_a": "S-u", "arm_b": "R", "contrast": "S-u-vs-R"},
        ],
        "event_threshold": 5,
        "multiplicity": "holm-fwer-v1",
        "primary_endpoint": "t_first",
        "confirmatory_test": "exact-logrank-permutation-v1",
        "confirmatory_targets": ["h"],
    }
    fast, slow = [], []
    for s in (1, 2, 3):
        fast += [_mt_cell("S-u", s, "h", "holdout", **_SU_HIT), _mt_cell("R", s, "h", "holdout")]
        slow += [_mt_cell("S-u", s, "h", "holdout"), _mt_cell("R", s, "h", "holdout", **_SU_HIT)]
    rf = build_multitarget_report(fast, analysis_plan=plan, field_map=DEFAULT_MAP, sources=["t"])
    rs = build_multitarget_report(slow, analysis_plan=plan, field_map=DEFAULT_MAP, sources=["t"])
    cf = rf["confirmatory"]["contrasts"][0]
    cs = rs["confirmatory"]["contrasts"][0]
    assert cf["faster_arm"] == "S-u"  # S-u faster -> acceleration (scenario 1)
    assert cs["faster_arm"] == "R"  # R faster -> reverse (scenario 8)
    # same two-sided p regardless of direction (sign is carried by faster_arm, not p)
    assert cf["permutation"]["p_value"] == cs["permutation"]["p_value"]


def test_invalid_bare_cell_without_target_keeps_single_target_schema(tmp_path, capsys):
    # One valid + one config-nonconformant bare --cell, neither naming a target id. #246 gave the
    # invalid cell target_id "" while the valid one defaulted to "unspecified", so the two
    # distinct ids flipped this single-target run into the schema-2 multi-target report.
    valid = tmp_path / "R-s9001.summary.json"
    valid.write_text(json.dumps(_wrap(_rec(arm="R", random_seed=9001))))
    flagged = _wrap(_rec(arm="R", random_seed=9002))
    flagged["config_nonconformant"] = True
    flagged["invalid_reason"] = "budget mismatch vs plan"
    invalid = tmp_path / "R-s9002.summary.json"
    invalid.write_text(json.dumps(flagged))

    assert main(["--cell", str(valid), "--cell", str(invalid), "--format", "json"]) == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["schema_version"] == 1
    assert "by_target" not in report and "target_ids" not in report
    assert report["number_valid_cells"] == 1 and report["number_invalid_cells"] == 1
    # Byte-identical to the single-target build_report path (unchanged since pre-#246).
    cells = [cell_from_row(json.loads(p.read_text()), DEFAULT_MAP) for p in (valid, invalid)]
    assert all(c.target_id == "unspecified" for c in cells)
    expected = build_report(cells, field_map=DEFAULT_MAP, sources=[str(valid), str(invalid)])
    assert out == json_bytes(expected).decode("ascii") + "\n"
    assert "role_interpretation" not in out and "fix-verification" not in out


def test_old_index_invalid_cell_inherits_single_target(tmp_path):
    # An index entry without target_id + a null summary: the invalid cell takes the run's one
    # target id (from the valid cell's wrapper target), never "".
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    valid = {
        "summary": _rec(arm="R", random_seed=9001),
        "target": {"target_id": "nt-7.5.2", "role": "train", "hypothesis": "H-A"},
    }
    (summaries / "R-s9001.summary.json").write_text(json.dumps(valid))
    (summaries / "R-s9002.summary.json").write_text(json.dumps(_wrap(invalid=True)))
    items = [
        (summaries / "R-s9001.summary.json", {"arm": "R", "seed": 9001}),
        (summaries / "R-s9002.summary.json", {"arm": "R", "seed": 9002}),
    ]
    cells = load_cells(items, DEFAULT_MAP)
    assert isinstance(cells[1], InvalidCell)
    assert [c.target_id for c in cells] == ["nt-7.5.2", "nt-7.5.2"]


def test_fix_verification_role_label_makes_no_hit_count_prediction():
    # 7.5.6 is affected (cross-release-identity-repro-v1.md:49): the fix-verification label
    # describes the registered role only -- no "negative control" / "expected 0 hits".
    cells = [_mt_cell(a, s, "nt-7.5.6", "fix-verification") for a in ("R", "S-u") for s in (1, 2)]
    cells += [_mt_cell(a, s, "h", "holdout") for a in ("R", "S-u") for s in (1, 2)]
    report = build_multitarget_report(cells, field_map=DEFAULT_MAP, sources=["t"])
    label = report["by_target"]["nt-7.5.6"]["role_interpretation"]
    assert label == "fix-verification (H-A, pre-exposed; no hit-count prediction)"
    from scripts.analyze_exp0 import report_markdown

    rendered = json_bytes(report).decode("ascii") + report_markdown(report)
    assert "negative control" not in rendered and "expected 0 hits" not in rendered
    assert "no hit-count prediction" in report["purpose"]

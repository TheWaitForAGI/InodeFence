"""EXP-0 report generator over lane 5's RdsCellSummary schema (items 1-7, denominators)."""

import json

import pytest
from scripts.analyze_exp0 import (
    _DEFAULT_FIELD_MAP,
    build_report,
    cell_from_row,
    main,
)

DEFAULT_MAP = dict(_DEFAULT_FIELD_MAP)


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

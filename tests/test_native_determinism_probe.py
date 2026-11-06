"""Tests for the native per-case determinism probe (scripts/check_native_determinism.py).

All docker-free: the report-pair path is exercised with synthetic demo reports
(perturbed copies), and the in-process self-test runs the synthetic campaign.
"""

from __future__ import annotations

import copy
from typing import Any

from scripts.check_native_determinism import (
    REPORT_BACKED_DIMENSIONS,
    compare_report_pair,
    native_run_plan,
    report_equality,
    selftest_inprocess,
    subject_from_report,
)
from scripts.run_effect_demo import synthetic_demo_report

from inodefence.feedback import EffectSearchPolicy
from inodefence.mutator import MutationPolicy


def _report() -> dict[str, Any]:
    return synthetic_demo_report(123, 12, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1)


def test_identical_reports_pass_every_report_backed_dimension() -> None:
    report = _report()
    result = compare_report_pair(copy.deepcopy(report), copy.deepcopy(report))

    assert result["determinism_pass"] is True
    assert result["observation_sequence_identical"] is True
    assert result["report_equality"]["equal"] is True
    assert result["report_equality"]["raw_identical"] is True
    assert set(result["report_backed_dimensions"]) == set(REPORT_BACKED_DIMENSIONS)
    agree = {dim["name"]: dim["agree"] for dim in result["dimensions"]}
    assert agree["case_sequence"] and agree["oracle_and_feedback"]


def _first_step_with_effect_event(report: dict[str, Any]) -> int:
    for step in report["steps"]:
        if step["trace"].get("effect_events"):
            return int(step["index"])
    raise AssertionError("no step with an effect event in the synthetic report")


def test_sequence_renumbering_passes_g1_but_flags_the_sequence_diagnostic() -> None:
    # Async fs-callback completion order renumbers effect-event sequences without
    # changing the effect set, oracle or feedback: G1 premise holds, but the
    # stricter observation-sequence diagnostic must flag it (this is EN-008).
    baseline = _report()
    candidate = copy.deepcopy(baseline)
    index = _first_step_with_effect_event(candidate)
    event = candidate["steps"][index]["trace"]["effect_events"][0]
    event["start_sequence"] = event["start_sequence"] + 100
    result = compare_report_pair(baseline, candidate)

    assert result["determinism_pass"] is True  # parity dimensions unaffected
    assert result["observation_sequence_identical"] is False
    agree = {dim["name"]: dim["agree"] for dim in result["dimensions"]}
    assert agree["case_sequence"] and agree["oracle_and_feedback"]


def test_raw_inode_renumbering_is_canonicalized_away() -> None:
    baseline = _report()
    candidate = copy.deepcopy(baseline)
    index = _first_step_with_effect_event(candidate)
    after = candidate["steps"][index]["trace"]["effect_events"][0]["paths"][0]["after"]
    after["st_ino"] = int(after["st_ino"]) + 1  # fresh inode number next run
    result = compare_report_pair(baseline, candidate)

    # Raw bytes differ, but the canonical determinism verdict is unaffected.
    assert result["report_equality"]["raw_identical"] is False
    assert result["observation_sequence_identical"] is True
    assert result["determinism_pass"] is True


def test_sandbox_run_token_is_normalized() -> None:
    baseline = _report()
    candidate = copy.deepcopy(baseline)
    baseline["steps"][0]["target_stderr"] = {
        "text": "link '/var/lib/inodefence/core-run-AAAA/extract/x'",
        "chars": 1,
        "truncated": False,
    }
    candidate["steps"][0]["target_stderr"] = {
        "text": "link '/var/lib/inodefence/core-run-ZZZZ/extract/x'",
        "chars": 1,
        "truncated": False,
    }
    result = compare_report_pair(baseline, candidate)

    assert result["report_equality"]["raw_identical"] is False
    assert result["observation_sequence_identical"] is True
    assert result["determinism_pass"] is True


def test_timing_difference_alone_still_passes() -> None:
    # Wall-clock timing legitimately differs between two runs of the same input;
    # it must not count as non-determinism.
    baseline = _report()
    candidate = copy.deepcopy(baseline)
    candidate["timing"] = {"total_seconds": 999.0, "per_case": []}
    result = compare_report_pair(baseline, candidate)

    assert result["determinism_pass"] is True
    assert result["report_equality"]["equal"] is True


def test_perturbed_case_id_fails_case_sequence() -> None:
    baseline = _report()
    candidate = copy.deepcopy(baseline)
    candidate["steps"][1]["case_id"] = "tampered-case-id"
    result = compare_report_pair(baseline, candidate)

    assert result["determinism_pass"] is False
    assert result["report_equality"]["equal"] is False
    agree = {dim["name"]: dim["agree"] for dim in result["dimensions"]}
    assert agree["case_sequence"] is False


def test_perturbed_oracle_fails_oracle_dimension() -> None:
    baseline = _report()
    candidate = copy.deepcopy(baseline)
    # Flip a C0 verdict on a step without changing its case id.
    candidate["steps"][0]["oracle"]["C0"] = not candidate["steps"][0]["oracle"]["C0"]
    result = compare_report_pair(baseline, candidate)

    assert result["determinism_pass"] is False
    agree = {dim["name"]: dim["agree"] for dim in result["dimensions"]}
    assert agree["case_sequence"] is True
    assert agree["oracle_and_feedback"] is False


def test_report_equality_locates_first_differing_step() -> None:
    baseline = _report()
    candidate = copy.deepcopy(baseline)
    candidate["steps"][2]["validity"] = "invalid"
    equality = report_equality(baseline, candidate)

    assert equality["equal"] is False
    assert "steps" in equality["differing_keys"]
    assert equality["first_step_difference"]["index"] == 2
    assert "validity" in equality["first_step_difference"]["fields"]


def test_report_equality_step_count_mismatch() -> None:
    baseline = _report()
    candidate = copy.deepcopy(baseline)
    candidate["steps"] = candidate["steps"][:-1]
    equality = report_equality(baseline, candidate)

    assert equality["equal"] is False
    assert equality["first_step_difference"]["kind"] == "step_count"


def test_subject_from_report_shapes_steps() -> None:
    report = _report()
    subject = subject_from_report(report, label="probe")

    assert subject.label == "probe"
    assert len(subject.steps) == len(report["steps"])
    assert [step.index for step in subject.steps] == list(range(len(report["steps"])))
    assert subject.isolation is None
    # Oracle is a sorted tuple of (contract-id, violated) pairs.
    assert subject.steps[0].oracle == tuple(
        sorted((cid, bool(v)) for cid, v in report["steps"][0]["oracle"].items())
    )


def test_selftest_inprocess_is_deterministic_on_the_synthetic_path() -> None:
    result = selftest_inprocess(
        seed=123,
        policy=EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
        mutation=MutationPolicy.M1,
        budget=12,
    )
    assert result["determinism_pass"] is True
    agree = {dim["name"]: dim["agree"] for dim in result["dimensions"]}
    # The three observer-output dimensions agree; snapshots is genuinely exercised
    # here (real synthetic StateSnapshots), unlike the report-pair path.
    assert agree["case_sequence"] and agree["oracle_and_feedback"] and agree["snapshots"]


def test_native_run_plan_is_six_runs_with_three_compare_pairs() -> None:
    plan = native_run_plan(seeds=(118, 124), budget=100)

    assert len(plan["runs"]) == 6
    stop = [run for run in plan["runs"] if run["policy"] == "stop"]
    cont = [run for run in plan["runs"] if run["policy"] == "invalid-continue"]
    assert len(stop) == 4 and len(cont) == 2
    # Each measured (seed, policy) cell has a genuine two-run determinism pair.
    assert {run["rerun"] for run in cont} == {1, 2}
    assert {run["seed"] for run in cont} == {118}
    assert len(plan["compare_pairs"]) == 3
    assert plan["jobs"] == 2
    assert all(run["budget"] == 100 for run in plan["runs"])

"""Report-record → RdsCellSummary conversion (no Docker; synthetic demo reports)."""

import json
from pathlib import Path

import pytest
from scripts.run_effect_demo import synthetic_demo_report
from test_rds import _c1_hit, _c2_hit, _ineligible, _Script  # shared synthetic cell helpers

from inodefence.effect_demo import effect_campaign_report
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.rds import (
    RdsArm,
    RdsCellConfig,
    RVariant,
    arm_for_policy,
    run_rds_cell,
)
from inodefence.evaluation.rds_report import (
    ReportFormatError,
    check_report_config,
    load_cell_files,
    summarize_cell_files,
    summarize_report_records,
)
from inodefence.generator import minimal_seed_corpus

CONFIG = RdsCellConfig(RdsArm.S_U, 9001, 12)


def _report() -> dict:
    return synthetic_demo_report(
        CONFIG.random_seed, CONFIG.execution_budget, CONFIG.search_policy, CONFIG.mutation_policy
    )


def _identity_fingerprint(internal: str, sentinel: str) -> dict:
    return {
        "model": "ViolationFingerprint",
        "schema_version": 1,
        "value": {
            "contract_id": "C1",
            "evidence": [{"internal_path": internal, "sentinel_path": sentinel}],
        },
    }


def _fingerprint(contract: str, path: str) -> dict:
    return {
        "model": "ViolationFingerprint",
        "schema_version": 1,
        "value": {
            "contract_id": contract,
            "evidence": [{"path": path, "fields": ["content_digest"]}],
        },
    }


def test_report_summary_matches_in_memory_summary_for_the_same_cell() -> None:
    report = _report()
    cell = run_rds_cell(minimal_seed_corpus(), synthetic_effect_result, CONFIG)
    from_report = summarize_report_records(report["steps"], CONFIG).summary
    memory = cell.summary
    for field in (
        "executions_completed",
        "complete",
        "hit",
        "t_first",
        "t_first_event",
        "t_first_censored",
        "u_viol",
        "u_viol_c0",
        "u_viol_source",
        "u_viol_feedback",
        "hit_steps",
        "retained_cases",
        "unique_effect_keys",
        "boundary_attempt_keys",
        "rejected_executions",
        "initial_cases",
        "search_policy",
        "mutation_policy",
    ):
        assert getattr(from_report, field) == getattr(memory, field), field
    assert from_report.vocabulary_pool_final == memory.vocabulary_pool_final
    assert from_report.vocabulary_pool_after_seed == memory.vocabulary_pool_after_seed
    assert from_report.observed_protected_paths == memory.observed_protected_paths
    assert "outside" in from_report.vocabulary_pool_final


def test_records_without_name_segments_report_empty_pools() -> None:
    report = _report()
    for step in report["steps"]:
        del step["name_segments"]
        del step["before_protected_paths"]
    summary = summarize_report_records(report["steps"], CONFIG).summary
    assert summary.vocabulary_pool_final == () and summary.observed_protected_paths == ()


def test_u_viol_reads_oracle_classes_regardless_of_eligibility() -> None:
    report = _report()
    steps = report["steps"]
    steps[7]["oracle"]["C2"] = True
    steps[7]["oracle_fingerprints"] = [_fingerprint("C2", "outside/s")]
    steps[7]["feedback"]["new_violation_fingerprints"] = [_fingerprint("C2", "outside/s")]
    steps[9]["oracle"]["C2"] = True  # same class again: counts once
    steps[9]["oracle_fingerprints"] = [_fingerprint("C2", "outside/s")]
    steps[10]["oracle"]["C1"] = True
    steps[10]["oracle_fingerprints"] = [_identity_fingerprint("extract/a", "outside/s")]
    steps[10]["feedback"]["feedback_eligible"] = False  # ineligible: oracle still counts
    steps[11]["oracle"]["C0"] = True
    steps[11]["oracle_fingerprints"] = [_fingerprint("C0", "outside/n")]
    result = summarize_report_records(steps, CONFIG)
    summary = result.summary
    assert summary.hit and summary.first_hit_step_index == 7
    assert (summary.t_first, summary.t_first_event, summary.t_first_censored) == (8, 1, False)
    assert summary.hit_steps == 3 and summary.u_viol == 2 and summary.u_viol_c0 == 1
    assert summary.u_viol_source == "oracle" and summary.u_viol_feedback == 1
    assert result.unfingerprinted_hit_steps == 1
    assert (summary.first_c2, summary.first_c1, summary.first_c0) == (8, 11, 12)
    record = result.record()
    assert record["summary"]["u_viol_source"] == "oracle" and "u_viol_feedback" in record["summary"]


def test_records_without_oracle_classes_fall_back_to_feedback_and_say_so() -> None:
    """Pre-schema-3 records (G1): u_viol counts what the loop fed back, and an ineligible
    hit is only visible as unfingerprinted_hit_steps — the pre-fix behaviour, labelled."""
    report = _report()
    steps = report["steps"]
    for step in steps:
        del step["oracle_fingerprints"]
    steps[7]["oracle"]["C2"] = True
    steps[7]["feedback"]["new_violation_fingerprints"] = [_fingerprint("C2", "outside/s")]
    steps[9]["oracle"]["C2"] = True  # same class again: no new fingerprint recorded
    steps[10]["oracle"]["C1"] = True
    steps[10]["feedback"]["feedback_eligible"] = False  # ineligible trace: no fingerprint
    steps[11]["oracle"]["C0"] = True
    steps[11]["feedback"]["new_violation_fingerprints"] = [_fingerprint("C0", "outside/n")]
    result = summarize_report_records(steps, CONFIG)
    summary = result.summary
    assert summary.hit and summary.first_hit_step_index == 7
    assert (summary.t_first, summary.t_first_event, summary.t_first_censored) == (8, 1, False)
    assert summary.hit_steps == 3 and summary.u_viol == 1 and summary.u_viol_c0 == 1
    assert summary.u_viol_source == "feedback-fallback" and summary.u_viol_feedback == 1
    assert result.unfingerprinted_hit_steps == 1
    assert (summary.first_c2, summary.first_c1, summary.first_c0) == (8, 11, 12)
    assert "unfingerprinted_hit_steps" in result.record()
    # A single record lacking the classes is enough to fall back (sources never mix).
    mixed = _report()["steps"]
    del mixed[3]["oracle_fingerprints"]
    assert summarize_report_records(mixed, CONFIG).summary.u_viol_source == "feedback-fallback"


def test_report_config_cross_check_refuses_a_different_cell() -> None:
    report = _report()
    check_report_config(report, CONFIG)
    with pytest.raises(ReportFormatError, match="differs"):
        check_report_config(report, RdsCellConfig(RdsArm.D, 9001, 12))
    with pytest.raises(ReportFormatError, match="differs"):
        check_report_config(report, RdsCellConfig(RdsArm.S_U, 9002, 12))


def _write_cell(tmp_path: Path, report: dict | None, steps: list[dict] | None) -> tuple[Path, Path]:
    report_path = tmp_path / "cell.json"
    steps_path = tmp_path / "cell.steps.jsonl"
    if report is not None:
        report_path.write_text(json.dumps(report), encoding="utf-8")
    if steps is not None:
        steps_path.write_text("".join(json.dumps(s) + "\n" for s in steps), encoding="utf-8")
    return report_path, steps_path


def test_complete_report_file_is_summarized_from_its_steps(tmp_path: Path) -> None:
    report = _report()
    summary, loaded = summarize_cell_files(*_write_cell(tmp_path, report, report["steps"]), CONFIG)
    assert loaded.steps_from == "report" and loaded.report_present
    assert summary.summary.complete and summary.summary.t_first == 12


def test_aborted_report_uses_steps_jsonl_and_censors_at_completed(tmp_path: Path) -> None:
    report = _report()
    partial = report["steps"][:5]
    aborted = {
        "label": "demo run",
        "producer": "native",
        "aborted": {"step_index": 5, "case_id": "x", "reason": "docker broker", "observed": None},
    }
    summary, loaded = summarize_cell_files(*_write_cell(tmp_path, aborted, partial), CONFIG)
    assert loaded.steps_from == "steps_jsonl"
    s = summary.summary
    assert s.aborted and s.abort_step_index == 5 and s.executions_completed == 5
    assert "docker broker" in str(s.abort_reason)
    assert (s.t_first, s.t_first_event, s.t_first_censored) == (5, 0, True)


def test_missing_report_is_an_abort_after_recorded_steps(tmp_path: Path) -> None:
    report = _report()
    report_path, steps_path = _write_cell(tmp_path, None, report["steps"][:3])
    loaded = load_cell_files(report_path, steps_path)
    assert not loaded.report_present and loaded.aborted_at_step == 3
    summary, _ = summarize_cell_files(report_path, steps_path, CONFIG)
    assert summary.summary.aborted and summary.summary.t_first == 3


def test_no_evidence_at_all_is_an_abort_at_zero(tmp_path: Path) -> None:
    summary, loaded = summarize_cell_files(tmp_path / "none.json", tmp_path / "none.jsonl", CONFIG)
    assert loaded.steps_from == "none" and summary.summary.executions_completed == 0
    assert summary.summary.aborted and summary.summary.t_first == 0


def test_short_report_without_abort_record_is_still_censored(tmp_path: Path) -> None:
    report = _report()
    report["steps"] = report["steps"][:4]
    summary, _ = summarize_cell_files(*_write_cell(tmp_path, report, None), CONFIG)
    assert summary.summary.aborted and summary.summary.t_first == 4
    assert "fewer steps" in str(summary.summary.abort_reason)


def test_malformed_records_fail_closed() -> None:
    report = _report()
    steps = report["steps"]
    del steps[3]["oracle"]
    with pytest.raises(ReportFormatError, match="oracle"):
        summarize_report_records(steps, CONFIG)
    with pytest.raises(ReportFormatError, match="contiguous"):
        summarize_report_records(report["steps"][1:], CONFIG)


# ---- cross-path parity on the same step sequence (memory == report) ----------------

PARITY_FIELDS = (
    "executions_completed",
    "complete",
    "hit",
    "t_first",
    "t_first_event",
    "t_first_censored",
    "first_hit_step_index",
    "hit_steps",
    "u_viol",
    "u_viol_c0",
    "u_viol_source",
    "u_viol_feedback",
    "first_c0",
    "first_c1",
    "first_c2",
    "c0_steps",
    "retained_cases",
)


def _scripted_cell(arm: RdsArm, special: dict, *, budget: int = 20):
    config = RdsCellConfig(arm, 9001, budget)
    cell = run_rds_cell(minimal_seed_corpus(), _Script(special), config)
    report = effect_campaign_report(cell.campaign, "synthetic")
    return config, cell.summary, report


@pytest.mark.parametrize("arm", [RdsArm.R, RdsArm.D, RdsArm.S_U, RdsArm.S_A])
def test_memory_and_report_paths_agree_on_eligible_and_ineligible_hits(arm: RdsArm) -> None:
    """One event definition, two paths, every arm: a C2 hit on an eligible step, the
    same C2 class again, a C1 hit on a FAILURE-terminated step and a C1 hit on an
    integrity-invalid step give identical hit/t_first/u_viol in memory and from the
    report records; only u_viol_feedback shows what the loop fed back."""
    special = {
        5: _c2_hit,
        8: _c2_hit,
        11: _ineligible(_c1_hit, how="failure"),
        14: _ineligible(_c1_hit, how="integrity"),
    }
    config, memory, report = _scripted_cell(arm, special)
    result = summarize_report_records(report["steps"], config)
    for field in PARITY_FIELDS:
        assert getattr(result.summary, field) == getattr(memory, field), field
    assert memory.hit and memory.t_first == 6 and memory.u_viol == 2
    assert memory.u_viol_source == "oracle" and memory.u_viol_feedback == 1
    assert result.unfingerprinted_hit_steps == 2
    for index in (11, 14):
        step = report["steps"][index]
        assert step["oracle"]["C1"] and not step["feedback"]["feedback_eligible"]
        assert step["oracle_fingerprints"] and not step["feedback"]["new_violation_fingerprints"]


def test_pre_fix_logic_differs_from_oracle_count_on_an_ineligible_hit() -> None:
    """Pins lane 10's finding: on an ineligible C1 hit the feedback-only count (the
    pre-fix report path, still reachable as the fallback) under-counts U_viol while hit
    and t_first already see the step; the oracle count does not."""
    config, memory, report = _scripted_cell(RdsArm.S_U, {6: _ineligible(_c1_hit, how="failure")})
    with_classes = summarize_report_records(report["steps"], config).summary
    for step in report["steps"]:
        del step["oracle_fingerprints"]
    pre_fix = summarize_report_records(report["steps"], config).summary
    assert with_classes.hit == pre_fix.hit is True and with_classes.t_first == pre_fix.t_first == 7
    assert with_classes.u_viol == memory.u_viol == 1 and with_classes.u_viol_source == "oracle"
    assert pre_fix.u_viol == 0 and pre_fix.u_viol_source == "feedback-fallback"
    assert pre_fix.u_viol_feedback == with_classes.u_viol_feedback == 0


# ---- G1 (2026-11-04) before/after regression: lane 10's "no impact" verdict ---------

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "g1-20261104"
G1_EVIDENCE = Path.home() / "inodefence-evidence" / "g1-20261104"


def _g1_config(report: dict) -> RdsCellConfig:
    from inodefence.feedback import EffectSearchPolicy

    config = report["config"]
    arm, variant = arm_for_policy(EffectSearchPolicy(config["search_policy"]))
    return RdsCellConfig(
        arm, config["random_seed"], config["execution_budget"], r_variant=variant or RVariant.WALK
    )


@pytest.mark.parametrize("run_id", ["7.5.2-D-s9002", "7.5.2-R-s9001"])
def test_g1_reduced_fixture_summarizes_to_the_frozen_pre_fix_values(run_id: str) -> None:
    """Reduced copies of two G1 raw reports (sha256 of the raw file recorded in the
    fixture) summarize to the values the pre-fix summaries froze; the records predate
    oracle_fingerprints so the fallback path is taken and labelled."""
    reduced = json.loads((FIXTURES / f"{run_id}.reduced.json").read_text())
    frozen = json.loads((FIXTURES / "g1-20261104-frozen.json").read_text())
    expected = frozen["reduced_reports"][run_id]
    assert len(reduced["source"]["sha256"]) == 64
    assert all("oracle_fingerprints" not in step for step in reduced["steps"])  # pre-fix records
    result = summarize_report_records(reduced["steps"], _g1_config(reduced))
    for field, value in expected["frozen"].items():
        assert getattr(result.summary, field) == value, field
    assert result.unfingerprinted_hit_steps == expected["unfingerprinted_hit_steps"]
    assert result.summary.u_viol_source == "feedback-fallback"
    assert result.summary.u_viol_feedback == result.summary.u_viol  # every G1 hit was eligible


@pytest.mark.skipif(not G1_EVIDENCE.is_dir(), reason="G1 raw evidence not on this host")
def test_g1_fifteen_cells_summarize_unchanged_from_their_pre_fix_summaries() -> None:
    frozen = json.loads((FIXTURES / "g1-20261104-frozen.json").read_text())
    checked = 0
    for key, expected in frozen["cells"].items():
        plan, run_id = key.split("/")
        report_path = G1_EVIDENCE / plan / f"inodefence-effect-demo-historical-{run_id}.json"
        if not report_path.is_file():
            continue
        report = json.loads(report_path.read_text())
        result = summarize_report_records(report["steps"], _g1_config(report))
        for field in ("hit", "t_first", "t_first_event", "u_viol", "u_viol_c0", "hit_steps"):
            assert getattr(result.summary, field) == expected[field], (key, field)
        assert result.unfingerprinted_hit_steps == expected["unfingerprinted_hit_steps"]
        assert result.summary.u_viol_source == "feedback-fallback"
        checked += 1
    assert checked == 15

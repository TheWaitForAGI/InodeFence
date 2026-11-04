"""Report-record → RdsCellSummary conversion (no Docker; synthetic demo reports)."""

import json
from pathlib import Path

import pytest
from scripts.run_effect_demo import synthetic_demo_report

from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.rds import RdsArm, RdsCellConfig, run_rds_cell
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


def test_hits_read_oracle_and_u_viol_reads_recorded_fingerprints() -> None:
    report = _report()
    steps = report["steps"]
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
    assert result.unfingerprinted_hit_steps == 1
    assert (summary.first_c2, summary.first_c1, summary.first_c0) == (8, 11, 12)
    assert "unfingerprinted_hit_steps" in result.record()


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

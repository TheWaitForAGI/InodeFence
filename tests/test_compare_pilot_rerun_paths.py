"""Pilot-versus-re-run path comparison: recurrence, untested cases and the sealed output."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from scripts import compare_pilot_rerun_paths as cmp
from scripts.compare_pilot_rerun_paths import (
    NOT_TESTED_DIVERGED,
    NOT_TESTED_NO_RECORD,
    NOT_TESTED_OTHER_CASE,
    NOT_TESTED_REPORT,
    NOT_TESTED_STOPPED,
    PASSED,
    RECURRED,
    AbortRecord,
    CellFiles,
    ComparisonError,
    RerunBlock,
    UnreadableSteps,
    classify_abort,
    common_prefix,
    compare,
    compare_paths,
    design_differences,
    read_abort,
    read_case_ids,
    render_markdown,
    summarize,
    verify_pilot_files,
)
from scripts.make_raw_manifest import hash_file
from scripts.run_concurrency_benchmark import load_design as load_benchmark
from scripts.run_hazard_pilot import load_design as load_pilot

ROOT = Path(__file__).resolve().parents[1]
PILOT_DESIGN = ROOT / "experiments/preregistration/exp3-hazard-pilot-v1.md"
BENCHMARK_DESIGN = ROOT / "experiments/configs/concurrency-scaling-v1.md"
ORACLE_SECRET = "ORACLE-VALUE-MUST-NOT-LEAK"
ABORT = AbortRecord(3, "c3", "BackendError: x", None)
PILOT_PATH = ["c0", "c1", "c2", "c3"]


def write_steps(path: Path, case_ids: list[str]) -> Path:
    lines = [
        json.dumps({"index": i, "case_id": c, "oracle": {"verdict": ORACLE_SECRET}})
        for i, c in enumerate(case_ids)
    ]
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def make_cell(
    tmp_path: Path,
    name: str,
    case_ids: list[str] | None,
    *,
    abort: dict[str, object] | None = None,
    returncode: int | None = None,
    label: str = "S-u",
    search: str = "policy-s",
    seed: int = 8110,
    state: str = "ran",
) -> CellFiles:
    steps = None if case_ids is None else write_steps(tmp_path / f"{name}.steps.jsonl", case_ids)
    report = tmp_path / f"{name}.json"
    code = returncode if returncode is not None else (1 if abort else 0)
    if abort:
        report.write_text(json.dumps({"aborted": abort}), encoding="utf-8")
    return CellFiles(label, search, seed, code, steps, report, state)


def stub(step: int, case_id: str, **extra: object) -> dict[str, object]:
    return {"step_index": step, "case_id": case_id, "reason": "BackendError: x", **extra}


@pytest.mark.parametrize(
    ("rerun", "rerun_abort", "expected"),
    [
        (["c0", "c1", "c2", "c3", "c4"], None, (PASSED, True)),
        (["c0", "c1", "c2"], ABORT, (RECURRED, True)),
        (["c0", "xx", "c2"], ABORT, (RECURRED, False)),
        (["c0", "xx", "c2", "c3"], None, (NOT_TESTED_DIVERGED, False)),
        (["c0", "c1"], AbortRecord(2, "c2", "r", None), (NOT_TESTED_STOPPED, True)),
        (["c0", "c1", "c2"], None, (NOT_TESTED_STOPPED, True)),
        (["c0", "c1", "c2", "other"], None, (NOT_TESTED_OTHER_CASE, True)),
        (["c0", "c1", "c2"], AbortRecord(3, "other", "r", None), (NOT_TESTED_OTHER_CASE, True)),
        (None, None, (NOT_TESTED_NO_RECORD, None)),
        (None, ABORT, (RECURRED, None)),
    ],
)
def test_classify_abort(rerun, rerun_abort, expected) -> None:
    assert classify_abort(ABORT, ["c0", "c1", "c2"], rerun, rerun_abort) == expected


def test_abort_at_the_same_step_with_another_case_is_not_a_recurrence() -> None:
    status, _ = classify_abort(
        ABORT, ["c0", "c1", "c2"], ["c0", "c1", "c2"], AbortRecord(3, "z", "r", None)
    )
    assert status != RECURRED


def test_abort_at_another_step_with_the_same_case_is_not_a_recurrence() -> None:
    status, _ = classify_abort(
        ABORT, ["c0", "c1", "c2"], ["c0", "c1"], AbortRecord(2, "c3", "r", None)
    )
    assert status != RECURRED


@pytest.mark.parametrize(
    ("pilot", "rerun", "budget", "prefix", "mismatch", "limit"),
    [
        (["a", "b"], ["a", "b"], 2, 2, None, "budget"),
        (["a", "b"], ["a", "b"], 5, 2, None, "both_ended"),
        (["a"], ["a", "b"], 2, 1, None, "pilot_ended"),
        (["a", "b"], ["a"], 2, 1, None, "rerun_ended"),
        (["a", "b"], ["a", "x"], 2, 1, 1, "mismatch"),
        (["x"], ["y"], 1, 0, 0, "mismatch"),
    ],
)
def test_compare_paths(pilot, rerun, budget, prefix, mismatch, limit) -> None:
    result = compare_paths(pilot, rerun, budget)
    assert result["common_prefix"] == prefix
    assert result["first_mismatch_step"] == mismatch
    assert result["limit"] == limit
    assert common_prefix(pilot, rerun) == prefix


def test_summary_bound_only_with_passes_and_no_recurrence() -> None:
    passed = {"status": PASSED}
    assert summarize([passed])["recurrence_upper95"] == pytest.approx(0.95)
    assert summarize([passed] * 24)["recurrence_upper95"] == pytest.approx(0.117, abs=0.001)
    assert summarize([passed, {"status": RECURRED}])["recurrence_upper95"] is None
    untested = summarize([{"status": NOT_TESTED_DIVERGED}])
    assert untested["passes_m"] == 0
    assert untested["recurrence_upper95"] is None
    assert untested["not_tested"] == {NOT_TESTED_DIVERGED: 1}


def test_steps_with_wrong_index_or_bad_json_are_unreadable(tmp_path: Path) -> None:
    bad_index = tmp_path / "a.jsonl"
    bad_index.write_text(json.dumps({"index": 5, "case_id": "x"}) + "\n", encoding="utf-8")
    with pytest.raises(UnreadableSteps):
        read_case_ids(bad_index)
    bad_json = tmp_path / "b.jsonl"
    bad_json.write_text("{nope\n", encoding="utf-8")
    with pytest.raises(UnreadableSteps):
        read_case_ids(bad_json)


def test_a_completed_cell_report_is_not_opened(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-report.json"
    cell = CellFiles("S-u", "p", 1, 0, None, missing)
    assert read_abort(cell) is None
    garbage = tmp_path / "garbage.json"
    garbage.write_text("not json", encoding="utf-8")
    assert read_abort(dataclasses.replace(cell, report=garbage)) is None


def pilot_map(tmp_path: Path) -> dict[tuple[str, int], CellFiles]:
    pilot_dir = tmp_path / "pilot"
    pilot_dir.mkdir()
    cell = make_cell(pilot_dir, "p", ["c0", "c1", "c2"], abort=stub(3, "c3"))
    return {(cell.search, cell.seed): cell}


def rerun_dir(tmp_path: Path) -> Path:
    path = tmp_path / "rerun"
    path.mkdir()
    return path


def test_passing_rerun_gives_m_and_bound(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0", "c1", "c2", "c3", "c4"])
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    assert result["summary"]["passes_m"] == 1
    assert result["summary"]["recurrence_upper95"] == pytest.approx(0.95)
    assert result["input_dependence_signal"] is False
    assert result["cells"][0]["limit"] == "pilot_ended"


def test_recurrence_raises_the_signal_and_withholds_the_bound(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(
        rerun_dir(tmp_path), "r", ["c0", "c1", "c2"], abort=stub(3, "c3", category="other")
    )
    result = compare(pilot, [RerunBlock("b1", 4, (cell,))], 5)
    assert result["input_dependence_signal"] is True
    assert result["summary"]["recurrences"] == 1
    assert result["summary"]["recurrence_upper95"] is None
    assert result["recurrences"][0]["rerun_category"] == "other"
    assert result["summary_by_jobs"]["4"]["recurrences"] == 1


def test_diverged_rerun_is_out_of_the_denominator_and_says_nothing(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0", "x", "c2", "c3"])
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    summary = result["summary"]
    assert (summary["passes_m"], summary["recurrences"], summary["recurrence_upper95"]) == (
        0,
        0,
        None,
    )
    assert summary["not_tested"] == {NOT_TESTED_DIVERGED: 1}
    assert result["cells"][0]["first_mismatch_step"] == 1
    assert "재발과 상한을 말하지 않는다" in render_markdown(
        {
            "label": "t",
            "pilot_head": "h",
            "rerun_heads": [],
            **result,
        }
    )


def test_missing_and_not_run_cells_are_not_tested(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    directory = rerun_dir(tmp_path)
    absent = make_cell(directory, "r1", None)
    not_run = make_cell(directory, "r2", ["c0"], state="not-run")
    result = compare(pilot, [RerunBlock("b1", 2, (absent, not_run))], 5)
    assert result["summary"]["not_tested"] == {NOT_TESTED_NO_RECORD: 2}
    assert {row["limit"] for row in result["cells"]} == {"no_record", "not_run"}


def test_unreadable_rerun_is_not_tested(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    directory = rerun_dir(tmp_path)
    cell = make_cell(directory, "r", ["c0"])
    assert cell.steps is not None
    cell.steps.write_text("{nope\n", encoding="utf-8")
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    assert result["summary"]["not_tested"] == {NOT_TESTED_NO_RECORD: 1}
    assert result["cells"][0]["limit"].startswith("unreadable")


def test_same_case_elsewhere_is_information_only(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0", "c1"], abort=stub(2, "c3"))
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    assert result["input_dependence_signal"] is None
    assert [item["step"] for item in result["same_case_elsewhere_information_only"]] == [2]


def test_a_cell_outside_the_pilot_is_only_listed(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0"], seed=6100)
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    assert result["cells"][0]["limit"] == "not_a_pilot_cell"
    assert result["abort_tests"] == []


def test_pilot_compared_with_itself_flags_each_abort_with_no_mismatch(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    result = compare(pilot, [RerunBlock("self", None, tuple(pilot.values()))], 5)
    assert result["cells"][0]["first_mismatch_step"] is None
    assert result["cells"][0]["common_prefix"] == result["cells"][0]["pilot_steps"] == 3
    assert result["summary"]["passes_m"] == 0
    assert result["summary"]["recurrences"] == 1
    assert result["input_dependence_signal"] is True


def test_oracle_values_do_not_reach_the_output(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0", "c1", "c2", "c3"])
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    report = {"label": "t", "pilot_head": "h", "rerun_heads": [], **result}
    assert ORACLE_SECRET not in json.dumps(report)
    assert ORACLE_SECRET not in render_markdown(report)


def test_report_states_what_a_matching_path_implies(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0", "c1", "c2", "c3"])
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    text = render_markdown({"label": "t", "pilot_head": "h", "rerun_heads": [], **result})
    assert "경로 일치 구간의 값은 파일럿에서 추론 가능하다" in text
    assert "재실행 사건 수를 만들지 않는다" in text


def test_the_arm_is_matched_by_policy_not_label(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0", "c1", "c2", "c3"], label="renamed")
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    assert result["summary"]["passes_m"] == 1


def test_real_designs_agree_and_a_changed_condition_is_refused() -> None:
    pilot, benchmark = load_pilot(PILOT_DESIGN), load_benchmark(BENCHMARK_DESIGN)
    assert design_differences(pilot, benchmark) == []
    for field, value in (("image_digest", "sha256:other"), ("sentinel_count", 3), ("budget", 20)):
        changed = dataclasses.replace(benchmark, **{field: value})
        assert any(item.startswith(field) for item in design_differences(pilot, changed))
    foreign = dataclasses.replace(benchmark.arms[0], search="another-policy")
    other = dataclasses.replace(benchmark, arms=(foreign, *benchmark.arms[1:]))
    assert any("not a pilot arm" in item for item in design_differences(pilot, other))


def test_manifest_mismatch_is_refused(tmp_path: Path) -> None:
    cell = make_cell(tmp_path, "p", ["c0"], abort=stub(1, "c1"))
    assert cell.steps is not None and cell.report is not None
    manifest = tmp_path / "m.sha256"
    good = f"{hash_file(cell.steps)}  ./p.steps.jsonl\n{hash_file(cell.report)}  ./p.json\n"
    manifest.write_text(good, encoding="utf-8")
    verify_pilot_files(tmp_path, manifest, [cell])
    manifest.write_text(
        f"{'0' * 64}  ./p.steps.jsonl\n{hash_file(cell.report)}  ./p.json\n", encoding="utf-8"
    )
    with pytest.raises(ComparisonError):
        verify_pilot_files(tmp_path, manifest, [cell])
    manifest.write_text(f"{hash_file(cell.report)}  ./p.json\n", encoding="utf-8")
    with pytest.raises(ComparisonError):
        verify_pilot_files(tmp_path, manifest, [cell])


def test_rerun_blocks_read_the_driver_layout(tmp_path: Path) -> None:
    design = load_benchmark(BENCHMARK_DESIGN)
    blocks = cmp.rerun_blocks(tmp_path, "A", design)
    assert [block.jobs for block in blocks] == [2, 4, 4, 2]
    assert {cell.state for block in blocks for cell in block.cells} == {"not-run"}
    block = blocks[0]
    first = block.cells[0]
    run_id = f"{design.target_version}-{first.label}-s{first.seed}"
    directory = tmp_path / "A" / block.name
    (directory / "raw").mkdir(parents=True)
    record = {
        "cells": [
            {
                "run_id": run_id,
                "state": "ran",
                "returncode": 1,
                "report": "x.json",
                "steps": "x.jsonl",
            }
        ]
    }
    (directory / "block.json").write_text(json.dumps(record), encoding="utf-8")
    (directory / "preflight.json").write_text(
        json.dumps({"preflight": {"checkout_head": "abc"}}), encoding="utf-8"
    )
    loaded = cmp.rerun_blocks(tmp_path, "A", design)[0]
    assert loaded.checkout_head == "abc"
    assert loaded.cells[0].state == "ran"
    assert loaded.cells[0].returncode == 1
    assert loaded.cells[0].steps == directory / "raw" / "x.jsonl"
    assert loaded.cells[1].state == "not-run"


@pytest.mark.parametrize("inside", ["repository", "evidence"])
def test_output_inside_the_repository_or_evidence_tree_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inside: str
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = ROOT if inside == "repository" else tmp_path / "inodefence-evidence"
    out = root / "must-not-be-created-by-this-test"
    code = cmp.main(
        [
            "--pilot-raw",
            str(tmp_path / "no-raw"),
            "--pilot-design",
            str(PILOT_DESIGN),
            "--pilot-manifest",
            str(tmp_path / "no-manifest"),
            "--self-test-seeds",
            "8110",
            "--out",
            str(out),
        ]
    )
    assert code == 2
    assert not out.exists()


def test_no_pass_and_no_recurrence_is_not_a_false_signal(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0", "x", "c2", "c3"])
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    assert result["input_dependence_signal"] is None
    report = {"label": "t", "pilot_head": "h", "rerun_heads": [], **result}
    assert "입력 종속 신호: **시험 안 됨**" in render_markdown(report)
    assert json.loads(json.dumps(report))["input_dependence_signal"] is None


def test_a_pass_gives_a_false_signal_and_a_recurrence_a_true_one() -> None:
    passed, recurred = {"status": PASSED}, {"status": RECURRED}
    assert cmp.input_dependence_signal([passed]) is False
    assert cmp.input_dependence_signal([recurred]) is True
    assert cmp.input_dependence_signal([passed, recurred]) is True
    assert cmp.input_dependence_signal([{"status": NOT_TESTED_DIVERGED}]) is None
    assert cmp.input_dependence_signal([]) is None


def test_six_passes_give_the_stated_bound() -> None:
    summary = summarize([{"status": PASSED}] * 6)
    assert summary["recurrence_upper95"] == pytest.approx(0.393, abs=0.001)


def test_a_damaged_rerun_report_marks_only_that_cell(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    directory = rerun_dir(tmp_path)
    damaged = make_cell(directory, "r1", ["c0", "c1", "c2"], abort=stub(3, "c3"))
    assert damaged.report is not None
    damaged.report.write_text("{not json", encoding="utf-8")
    fine = make_cell(directory, "r2", ["c0", "c1", "c2", "c3"])
    result = compare(pilot, [RerunBlock("b1", 2, (damaged, fine))], 5)
    assert [row["report_unreadable"] for row in result["cells"]] == [True, False]
    assert [test["status"] for test in result["abort_tests"]] == [NOT_TESTED_REPORT, PASSED]
    assert result["summary"]["passes_m"] == 1
    assert result["summary"]["not_tested"] == {NOT_TESTED_REPORT: 1}
    assert result["input_dependence_signal"] is None
    assert result["summary"]["recurrence_upper95"] is None


def test_a_damaged_stub_in_a_rerun_report_marks_the_cell(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    damaged = make_cell(rerun_dir(tmp_path), "r", ["c0", "c1", "c2"], abort={"step_index": "x"})
    result = compare(pilot, [RerunBlock("b1", 2, (damaged,))], 5)
    assert result["abort_tests"][0]["status"] == NOT_TESTED_REPORT


def test_a_damaged_pilot_report_is_still_refused(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    source = next(iter(pilot.values()))
    assert source.report is not None
    source.report.write_text("{not json", encoding="utf-8")
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0", "c1", "c2", "c3"])
    with pytest.raises(ComparisonError):
        compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)


def test_summary_line_states_attempts_against_the_maximum(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    directory = rerun_dir(tmp_path)
    blocks = [
        RerunBlock("b1", 2, (make_cell(directory, "r1", ["c0", "c1", "c2", "c3"]),)),
        RerunBlock("b2", 4, (make_cell(directory, "r2", ["x"]),)),
    ]
    result = compare(pilot, blocks, 5)
    assert result["attempts"] == {"tests": 2, "pilot_aborts": 1, "blocks": 2, "maximum": 2}
    text = render_markdown({"label": "t", "pilot_head": "h", "rerun_heads": [], **result})
    assert "시도 2건(파일럿 abort 1 × 블록 2 = 최댓값 2), 통과 m = 1, 시험 안 됨 1" in text


def _stopped_at_three(directory: Path, name: str, how: str) -> CellFiles:
    """A nonzero cell that stopped at the pilot's abort position with no readable stub."""
    cell = make_cell(directory, name, ["c0", "c1", "c2"], returncode=1)
    assert cell.report is not None
    if how == "damaged":
        cell.report.write_text("{not json", encoding="utf-8")
    elif how == "no_stub":
        cell.report.write_text(json.dumps({"aborted": None}), encoding="utf-8")
    return cell


UNREADABLE_WAYS = ("damaged", "no_stub", "no_report")
UNRESOLVED_SENTENCE = (
    "같은 위치에서 멈췄지만 보고서를 읽지 못한 1건이 있어 재발을 배제하지 못한다. "
    "상한을 내지 않는다."
)


@pytest.mark.parametrize("how", UNREADABLE_WAYS)
def test_a_stop_at_the_position_without_a_stub_withholds_signal_and_bound(
    tmp_path: Path, how: str
) -> None:
    pilot = pilot_map(tmp_path)
    cell = _stopped_at_three(rerun_dir(tmp_path), "r", how)
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    assert result["abort_tests"][0]["status"] == NOT_TESTED_REPORT
    assert result["abort_tests"][0]["prefix_identical"] is True
    assert result["cells"][0]["report_unreadable"] is True
    assert result["input_dependence_signal"] is None
    assert result["summary"]["recurrence_upper95"] is None
    report = {"label": "t", "pilot_head": "h", "rerun_heads": [], **result}
    assert UNRESOLVED_SENTENCE in render_markdown(report)


@pytest.mark.parametrize("how", UNREADABLE_WAYS)
def test_a_pass_alongside_an_unresolved_stop_still_gives_no_signal_or_bound(
    tmp_path: Path, how: str
) -> None:
    pilot = pilot_map(tmp_path)
    directory = rerun_dir(tmp_path)
    cell = _stopped_at_three(directory, "r1", how)
    fine = make_cell(directory, "r2", ["c0", "c1", "c2", "c3"])
    result = compare(pilot, [RerunBlock("b1", 2, (cell, fine))], 5)
    assert [test["status"] for test in result["abort_tests"]] == [NOT_TESTED_REPORT, PASSED]
    assert result["summary"]["passes_m"] == 1
    assert result["input_dependence_signal"] is None
    assert result["summary"]["recurrence_upper95"] is None
    report = {"label": "t", "pilot_head": "h", "rerun_heads": [], **result}
    text = render_markdown(report)
    assert UNRESOLVED_SENTENCE in text
    assert "입력 종속 신호: **시험 안 됨**" in text


@pytest.mark.parametrize("how", UNREADABLE_WAYS)
def test_a_recurrence_elsewhere_keeps_the_signal_true(tmp_path: Path, how: str) -> None:
    pilot = pilot_map(tmp_path)
    directory = rerun_dir(tmp_path)
    cell = _stopped_at_three(directory, "r1", how)
    again = make_cell(directory, "r2", ["c0", "c1", "c2"], abort=stub(3, "c3"))
    result = compare(pilot, [RerunBlock("b1", 2, (cell, again))], 5)
    assert result["summary"]["recurrences"] == 1
    assert result["input_dependence_signal"] is True
    assert result["summary"]["recurrence_upper95"] is None
    report = {"label": "t", "pilot_head": "h", "rerun_heads": [], **result}
    assert "재발 1건" in render_markdown(report)


def test_a_diverged_stop_at_the_position_without_a_stub_is_also_unresolved() -> None:
    # A recurrence is decided by the key alone, so a diverged path does not rule it out.
    status = classify_abort(ABORT, PILOT_PATH, ["c0", "xx", "c2"], None, stopped_nonzero=True)
    assert status == (NOT_TESTED_REPORT, False)


def test_a_nonzero_cell_with_no_step_record_and_no_stub_is_unresolved() -> None:
    assert classify_abort(ABORT, PILOT_PATH, None, None, stopped_nonzero=True) == (
        NOT_TESTED_REPORT,
        None,
    )


@pytest.mark.parametrize(
    ("rerun", "expected"),
    [
        (["c0", "c1"], (NOT_TESTED_STOPPED, True)),
        (["c0", "c1", "c2", "c3"], (PASSED, True)),
        (["c0", "c1", "c2", "other"], (NOT_TESTED_OTHER_CASE, True)),
    ],
)
def test_no_stub_away_from_the_position_changes_nothing(rerun, expected) -> None:
    assert classify_abort(ABORT, PILOT_PATH, rerun, None, stopped_nonzero=True) == expected


def test_a_clean_exit_at_the_position_is_only_stopped(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0", "c1", "c2"])
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    assert result["abort_tests"][0]["status"] == NOT_TESTED_STOPPED
    assert result["cells"][0]["report_unreadable"] is False


def test_a_cell_that_did_not_run_is_not_unresolved(tmp_path: Path) -> None:
    pilot = pilot_map(tmp_path)
    cell = make_cell(rerun_dir(tmp_path), "r", ["c0"], returncode=1, state="not-run")
    result = compare(pilot, [RerunBlock("b1", 2, (cell,))], 5)
    assert result["abort_tests"][0]["status"] == NOT_TESTED_NO_RECORD
    assert result["cells"][0]["report_unreadable"] is False


def test_a_readable_stub_for_another_case_at_the_position_is_not_unresolved() -> None:
    other = AbortRecord(3, "other", "r", None)
    assert classify_abort(ABORT, PILOT_PATH, ["c0", "c1", "c2"], other, stopped_nonzero=True) == (
        NOT_TESTED_OTHER_CASE,
        True,
    )

"""Record checks of a cell. The steps here carry no outcome: the check reads indexes only."""

import json
from pathlib import Path
from typing import Any

import pytest

from inodefence.evaluation.cell_completeness import (
    ABORT_FINAL,
    COMPLETE,
    NO_RECORD,
    RECORD_INCONSISTENT,
    UNATTEMPTED,
    Attempt,
    CellCheck,
    classify_cell,
    infrastructure_summary,
    read_cell_results,
    scan_steps,
)

BUDGET = 4


def _end(returncode: int = 0, *, watchdog: bool = False) -> dict[str, Any]:
    return {"event": "end", "returncode": returncode, "watchdog_fired": watchdog}


def _attempts(*ends: dict[str, Any] | None) -> tuple[Attempt, ...]:
    return tuple(
        Attempt(number, {"event": "start"}, ended) for number, ended in enumerate(ends, start=1)
    )


def _steps(count: int) -> list[str]:
    return [json.dumps({"index": index}) for index in range(count)]


def _classify(
    tmp_path: Path,
    *,
    lines: list[str] | None = None,
    report: object = None,
    attempts: tuple[Attempt, ...] = (),
    complete: bool = False,
) -> CellCheck:
    steps_path, report_path = tmp_path / "cell.steps.jsonl", tmp_path / "cell.json"
    if lines is not None:
        steps_path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    if report is not None:
        text = report if isinstance(report, str) else json.dumps(report)
        report_path.write_text(text, encoding="utf-8")
    return classify_cell(
        report_path=report_path,
        steps_path=steps_path,
        budget=BUDGET,
        attempts=attempts,
        complete_and_conformant=complete,
    )


def _complete_report() -> dict[str, Any]:
    return {"steps": [{"index": index} for index in range(BUDGET)]}


def _abort_report(step_index: int = 2, reason: object = "broker") -> dict[str, Any]:
    return {"aborted": {"step_index": step_index, "reason": reason}}


def test_complete_needs_the_report_the_budget_and_exit_zero(tmp_path: Path) -> None:
    check = _classify(
        tmp_path,
        lines=_steps(BUDGET),
        report=_complete_report(),
        attempts=_attempts(_end()),
        complete=True,
    )
    assert check == CellCheck(COMPLETE, step_count=BUDGET)


@pytest.mark.parametrize(
    ("kwargs", "problem"),
    [
        ({"attempts": _attempts(_end(1))}, "complete-report-with-a-nonzero-exit"),
        ({"attempts": _attempts(None)}, "no-exit-record"),
        ({"attempts": ()}, "no-exit-record"),
        ({"complete": False}, "report-incomplete-without-an-abort-record"),
        ({"lines": _steps(BUDGET - 1)}, "steps-file-does-not-reach-the-budget"),
        ({"report": "{not json"}, "report-unreadable"),
        ({"report": "[]"}, "report-is-not-an-object"),
        ({"report": {"steps": [{"index": 9}]}}, "steps-not-a-prefix-of-the-report"),
    ],
)
def test_a_complete_looking_record_with_one_check_off_is_inconsistent(
    tmp_path: Path, kwargs: dict[str, Any], problem: str
) -> None:
    base: dict[str, Any] = {
        "lines": _steps(BUDGET),
        "report": _complete_report(),
        "attempts": _attempts(_end()),
        "complete": True,
    }
    check = _classify(tmp_path, **{**base, **kwargs})
    assert check.state == RECORD_INCONSISTENT and problem in check.problems


def test_a_missing_exit_record_is_named_once_and_a_codeless_one_is_its_own_problem(
    tmp_path: Path,
) -> None:
    check = _classify(
        tmp_path,
        lines=_steps(BUDGET),
        report=_complete_report(),
        attempts=_attempts(None),
        complete=True,
    )
    assert check.problems == ("no-exit-record",)
    check = _classify(
        tmp_path,
        lines=_steps(BUDGET),
        report=_complete_report(),
        attempts=_attempts({"event": "end", "watchdog_fired": False}),
        complete=True,
    )
    assert check.problems == ("exit-record-without-an-exit-code",)


def test_an_abort_record_that_holds_together_is_final(tmp_path: Path) -> None:
    check = _classify(
        tmp_path, lines=_steps(2), report=_abort_report(), attempts=_attempts(_end(1))
    )
    assert check == CellCheck(ABORT_FINAL, step_count=2)


@pytest.mark.parametrize(
    ("kwargs", "problem"),
    [
        ({"report": _abort_report(step_index=3)}, "abort-step-index-differs-from-the-record-count"),
        ({"attempts": _attempts(_end(0))}, "abort-with-exit-code-zero"),
        ({"report": _abort_report(reason="")}, "abort-without-a-reason"),
        ({"report": _abort_report(reason=None)}, "abort-without-a-reason"),
        ({"attempts": _attempts(None)}, "no-exit-record"),
        ({"lines": ['{"index": 1}', '{"index": 2}']}, "step-indexes-not-contiguous"),
        ({"lines": ['{"index": 0}', '{"index": 0}']}, "step-indexes-not-contiguous"),
        (
            {"lines": ['{"index": 0}', "cut", '{"index": 1}']},
            "unparsable-line-inside-the-steps-file",
        ),
        ({"lines": [*_steps(2), "cut"]}, "unparsable-last-line-without-the-watchdog"),
    ],
)
def test_an_abort_record_with_one_check_off_is_inconsistent(
    tmp_path: Path, kwargs: dict[str, Any], problem: str
) -> None:
    base: dict[str, Any] = {
        "lines": _steps(2),
        "report": _abort_report(),
        "attempts": _attempts(_end(1)),
    }
    check = _classify(tmp_path, **{**base, **kwargs})
    assert check.state == RECORD_INCONSISTENT and problem in check.problems


def test_no_record_is_unattempted_until_the_attempts_are_used_up(tmp_path: Path) -> None:
    assert _classify(tmp_path).state == UNATTEMPTED
    assert _classify(tmp_path, attempts=_attempts(_end(1))).state == UNATTEMPTED
    assert _classify(tmp_path, attempts=_attempts(None)).state == UNATTEMPTED  # start only
    assert _classify(tmp_path, attempts=_attempts(_end(1), None)).state == NO_RECORD
    assert _classify(tmp_path, attempts=_attempts(None, None)).state == NO_RECORD


def test_a_single_cut_line_alone_is_no_record(tmp_path: Path) -> None:
    attempts = _attempts(_end(-15, watchdog=True))
    assert _classify(tmp_path, lines=["cut"], attempts=attempts).state == UNATTEMPTED


def test_watchdog_cell_rules_read_only_the_flag(tmp_path: Path) -> None:
    fired = _attempts(_end(-15, watchdog=True))
    whole = _classify(tmp_path, lines=_steps(2), attempts=fired)
    assert whole == CellCheck(ABORT_FINAL, (), True, 0, 2)
    cut = _classify(tmp_path, lines=[*_steps(2), "cut"], attempts=fired)
    assert cut == CellCheck(ABORT_FINAL, (), True, 1, 2)
    # Exit code -15 without the flag is an outside SIGTERM.
    outside = _classify(tmp_path, lines=_steps(2), attempts=_attempts(_end(-15)))
    assert outside.state == RECORD_INCONSISTENT and outside.watchdog is False
    assert outside.problems == ("no-report-and-no-watchdog",)
    # The flag must be literally true.
    loose = _attempts({"event": "end", "returncode": -15, "watchdog_fired": "true"})
    assert _classify(tmp_path, lines=_steps(2), attempts=loose).state == RECORD_INCONSISTENT


@pytest.mark.parametrize(
    "lines",
    [
        [*_steps(1), "cut", "cut"],  # two cut lines
        ['{"index": 0}', "cut", '{"index": 1}'],  # a cut line inside
        ['{"index": 0}', '{"index": 2}'],  # a gap
    ],
)
def test_a_watchdog_cell_with_more_damage_is_inconsistent(tmp_path: Path, lines: list[str]) -> None:
    fired = _attempts(_end(-15, watchdog=True))
    assert _classify(tmp_path, lines=lines, attempts=fired).state == RECORD_INCONSISTENT


def test_a_watchdog_flag_does_not_excuse_a_report_that_disagrees(tmp_path: Path) -> None:
    fired = _attempts(_end(-15, watchdog=True))
    check = _classify(tmp_path, lines=_steps(2), report=_abort_report(step_index=9), attempts=fired)
    assert check.state == RECORD_INCONSISTENT
    assert check.problems == ("abort-step-index-differs-from-the-record-count",)


def test_only_the_last_attempt_decides(tmp_path: Path) -> None:
    attempts = _attempts(_end(1), _end(-15, watchdog=True))
    assert _classify(tmp_path, lines=_steps(2), attempts=attempts).state == ABORT_FINAL
    attempts = _attempts(_end(-15, watchdog=True), None)
    assert _classify(tmp_path, lines=_steps(2), attempts=attempts).state == RECORD_INCONSISTENT


def test_the_scan_keeps_indexes_only(tmp_path: Path) -> None:
    path = tmp_path / "steps.jsonl"
    secret = {"index": 0, "oracle": {"C1": True}, "case_id": "secret"}
    path.write_text(json.dumps(secret) + "\n\n[1]\n", encoding="utf-8")
    scan = scan_steps(path)
    assert scan.indexes == (
        0,
        None,
    )  # a non-object record has no index, and blank lines are skipped
    assert "secret" not in repr(scan)
    assert scan_steps(tmp_path / "missing").indexes == ()


def test_results_file_gives_attempts_in_order_and_skips_a_cut_line(tmp_path: Path) -> None:
    path = tmp_path / "cell-results.jsonl"
    rows = [
        {"event": "start", "run_id": "a", "attempt": 2},
        {"event": "start", "run_id": "a", "attempt": 1},
        {"event": "end", "run_id": "a", "attempt": 1, "returncode": 1},
        {"event": "start", "run_id": "b", "attempt": 1},
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows) + '{"event": "end", "run_i',
        encoding="utf-8",
    )
    results = read_cell_results(path)
    assert [attempt.number for attempt in results["a"]] == [1, 2]
    assert results["a"][0].ended == rows[2] and results["a"][1].ended is None
    assert results["b"][0].ended is None
    assert read_cell_results(tmp_path / "missing") == {}


def test_infrastructure_summary_adds_inconsistent_records_to_aborts() -> None:
    checks = {
        "complete": CellCheck(COMPLETE),
        "abort": CellCheck(ABORT_FINAL),
        "watchdog": CellCheck(ABORT_FINAL, (), True, 1),
        "lost": CellCheck(NO_RECORD),
        "broken": CellCheck(RECORD_INCONSISTENT, ("no-exit-record",)),
        "waiting": CellCheck(UNATTEMPTED),
    }
    summary = infrastructure_summary(checks)
    assert summary["aborts"] == 3 and summary["watchdog"] == 1 and summary["no_record"] == 1
    assert summary["record_inconsistent"] == 1 and summary["aborts_plus_inconsistent"] == 4
    assert summary["infrastructure_failure_rate"] == pytest.approx(4 / 6)
    assert summary["unknown_outcome_steps"] == 1
    assert summary["inconsistent_checks"] == {"broken": ["no-exit-record"]}
    assert infrastructure_summary({})["infrastructure_failure_rate"] is None

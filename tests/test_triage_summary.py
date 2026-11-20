"""#519: per-case triage records grouped into cause-signature bundles (``triage_summary``).

Records are real ``inodefence-violation-triage-v2`` records built by ``violation_triage`` from the
synthetic evaluators of ``tests/test_violation_triage.py`` (no target is run). Nothing here is a
seed or corpus entry of anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.test_violation_triage import (
    ESCAPE,
    LINK,
    NOISE,
    THROUGH,
    Evaluator,
    Flaky,
    case_of,
)

from inodefence import triage_summary as ts
from inodefence.violation_triage import TriagePolicy, triage, triage_record


def _record(entries, evaluator=None, **policy) -> dict:
    outcome = triage(case_of(entries), evaluator or Evaluator(), TriagePolicy(**policy))
    return triage_record(outcome, label="t")


def _deterministic(noise: int) -> dict:
    # Same structure (LINK before THROUGH, ESCAPE) with different noise: one cause signature.
    return _record([NOISE[noise], LINK, NOISE[noise + 1], THROUGH, ESCAPE])


def test_cases_with_the_same_structure_form_one_bundle() -> None:
    records = [_deterministic(0), _deterministic(2), _deterministic(4)]
    summary = ts.summarize(records)
    assert summary["schema"] == ts.SUMMARY_SCHEMA and summary["records"] == 3
    (bundle,) = summary["bundles"]
    assert bundle["case_count"] == 3 and bundle["contracts"] == ["C1", "C2"]
    assert bundle["status"] == {"result": 3, "reference-only": 0}
    assert bundle["nondeterministic"] is False and bundle["note"] is None
    assert bundle["minimal_entries"] == {"min": 3, "max": 3}
    assert summary["not_a_result"] == {"count": 0, "cases": []}


def test_a_different_structure_is_another_bundle_ordered_by_size() -> None:
    other = _record([NOISE[0], ESCAPE, NOISE[1]])  # C1 only
    summary = ts.summarize([_deterministic(0), other, _deterministic(2)])
    assert [b["case_count"] for b in summary["bundles"]] == [2, 1]
    assert summary["bundles"][1]["contracts"] == ["C1"]


def test_a_nondeterministic_bundle_is_marked_and_shows_both_rates() -> None:
    flaky = _record([NOISE[0], LINK, NOISE[1], THROUGH, NOISE[2]], Flaky(period=2))
    summary = ts.summarize([flaky])
    (bundle,) = summary["bundles"]
    assert bundle["nondeterministic"] is True and bundle["note"] == ts.NONDETERMINISTIC_NOTE
    assert bundle["status"]["reference-only"] == 1
    (rate,) = bundle["rates"]
    assert rate["original"] is not None and rate["minimum"] is not None


def test_records_that_are_not_a_result_are_counted_apart_never_bundled() -> None:
    never = _record([NOISE[0], NOISE[1]], baseline_runs=4)
    summary = ts.summarize([never, _deterministic(0)])
    assert summary["not_a_result"]["count"] == 1 and len(summary["bundles"]) == 1
    assert summary["records"] == 2


def test_order_of_records_does_not_change_the_summary() -> None:
    records = [_deterministic(0), _record([NOISE[0], ESCAPE]), _deterministic(2)]
    assert ts.summarize(records) == ts.summarize(list(reversed(records)))


def test_the_summary_holds_no_paths_names_or_tar_bytes() -> None:
    summary = ts.summarize([_deterministic(0), _record([NOISE[0], ESCAPE])])
    text = json.dumps(summary)
    # No entry path or link-target text appears as a JSON string value anywhere.
    for entry in (*NOISE, LINK, THROUGH, ESCAPE):
        assert json.dumps(entry.path) not in text, entry.path
        if entry.link_target:
            assert json.dumps(entry.link_target) not in text, entry.link_target
    assert "tar_b64" not in text and summary["use_restriction"] == ts.USE_RESTRICTION


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(schema="other"),
        lambda r: r.update(result_status="maybe"),
        lambda r: r["minimization"]["signature"].update(id=""),
        lambda r: r["baseline"].update(case_id=""),
    ],
)
def test_an_unreadable_record_is_refused(mutate) -> None:
    record = _deterministic(0)
    mutate(record)
    with pytest.raises(ts.TriageSummaryError):
        ts.summarize([record])


def test_the_same_case_twice_is_refused() -> None:
    record = _deterministic(0)
    with pytest.raises(ts.TriageSummaryError, match="more than one"):
        ts.summarize([record, json.loads(json.dumps(record))])


def test_result_folder_round_trip(tmp_path: Path) -> None:
    for record in (_deterministic(0), _deterministic(2)):
        folder = tmp_path / ts.TRIAGE_DIR / record["baseline"]["case_id"]
        folder.mkdir(parents=True)
        (folder / ts.RECORD_NAME).write_text(json.dumps(record), encoding="utf-8")
    path = ts.write_summary(tmp_path)
    assert path == tmp_path / ts.TRIAGE_DIR / ts.SUMMARY_NAME
    loaded = ts.load_summary(tmp_path)
    assert loaded is not None and loaded["bundles"][0]["case_count"] == 2
    lines = ts.summary_lines(loaded)
    assert lines[0].startswith("원인 서명 묶음 1개, triage 기록 2건")
    assert any("| `" in line and "| 2 |" in line for line in lines)


def test_no_triage_folder_means_no_summary(tmp_path: Path) -> None:
    assert ts.read_records(tmp_path) == [] and ts.load_summary(tmp_path) is None
    with pytest.raises(ts.TriageSummaryError, match="no triage"):
        ts.write_summary(tmp_path)

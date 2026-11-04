"""The abort-category roll-up tallies aborts per arm/reason over the shared vocabulary.

Fixtures are synthetic (no host evidence), so the check is reproducible in CI. The
raw stubs deliberately omit a ``category`` field to prove the roll-up classifies the
``reason`` string itself (back-filling pre-``category`` evidence).
"""

import json

from scripts.analyze_abort_rollup import (
    arm_from_filename,
    build_contingency,
    build_rollup,
    classify_md_label,
    parse_m3_abort_table,
    read_g1_index,
    render_markdown,
    rollup_raw_json,
)

from inodefence.evaluation.abort_classification import InvalidReason

_M3_TABLE = """\
# verdict

### abort 사유 (seeds 100-149, 92셀)

| 사유 | A1 | A3full |
|---|---|---|
| observer "evidence integrity failed(malformed_identity)" | 19 | 18 |
| docker broker disconnected | 3 | 1 |
| container runtime cleanup inspect failed (s118 포함) | 1 | 2 |
| remove failed | 0 | 1 |

### next section

text that must not be parsed as a row.
"""


def _write(path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_arm_from_filename() -> None:
    assert arm_from_filename("inodefence-decompress-selfdiscover-m45-sa-s504.json") == "sa"
    assert arm_from_filename("inodefence-decompress-selfdiscover-m45-a1-s500.json") == "a1"
    assert arm_from_filename("weird-name") == "weird-name"


def test_classify_md_label_maps_to_shared_vocabulary() -> None:
    assert (
        classify_md_label('observer "evidence integrity failed"')
        == InvalidReason.OBSERVER_INTEGRITY
    )
    assert classify_md_label("docker broker disconnected") == InvalidReason.BROKER
    assert (
        classify_md_label("container runtime cleanup inspect failed")
        == InvalidReason.CLEANUP_INSPECT
    )
    assert classify_md_label("remove failed") == InvalidReason.CLEANUP_REMOVE
    assert classify_md_label("worker reset residual") == InvalidReason.CLEANUP_RESET
    assert classify_md_label("something unexpected") == InvalidReason.OTHER


def test_rollup_raw_json_classifies_reason_without_category_field(tmp_path) -> None:
    # Two completed campaigns and three aborts across arms a1/sa. Stubs carry only a
    # reason (no category), matching pre-#203 evidence on the host.
    _write(tmp_path / "x-m45-a1-s001.json", {"config": {}, "steps": []})
    _write(tmp_path / "x-m45-a1-s002.json", {"config": {}, "steps": []})
    _write(
        tmp_path / "x-m45-a1-s003.json",
        {"aborted": {"reason": "trusted Docker broker disconnected or returned invalid data"}},
    )
    _write(
        tmp_path / "x-m45-sa-s004.json",
        {"aborted": {"reason": "container runtime cleanup inspect failed: "}},
    )
    _write(
        tmp_path / "x-m45-sa-s005.json",
        {
            "aborted": {
                "reason": "inodefence.observer.snapshot.ObservationError: cannot open sandbox"
            }
        },
    )

    arms = rollup_raw_json(sorted(str(p) for p in tmp_path.glob("*.json")))

    assert arms["a1"]["completed"] == 2
    assert arms["a1"]["aborted_total"] == 1
    assert arms["a1"]["by_invalid_reason"]["broker"] == 1
    assert arms["sa"]["completed"] == 0
    assert arms["sa"]["aborted_total"] == 2
    assert arms["sa"]["by_invalid_reason"]["cleanup_inspect"] == 1
    assert arms["sa"]["by_invalid_reason"]["observer_integrity"] == 1
    # every bucket carries all six vocabulary keys
    assert set(arms["a1"]["by_invalid_reason"]) == {r.value for r in InvalidReason}


def test_parse_m3_abort_table_matches_known_counts(tmp_path) -> None:
    md = tmp_path / "verdict.md"
    md.write_text(_M3_TABLE, encoding="utf-8")

    arms = parse_m3_abort_table(md)

    assert set(arms) == {"A1", "A3full"}
    assert arms["A1"]["completed"] is None
    assert arms["A1"]["by_invalid_reason"]["observer_integrity"] == 19
    assert arms["A1"]["by_invalid_reason"]["broker"] == 3
    assert arms["A1"]["by_invalid_reason"]["cleanup_inspect"] == 1
    assert arms["A1"]["by_invalid_reason"]["cleanup_remove"] == 0
    assert arms["A1"]["aborted_total"] == 23
    assert arms["A3full"]["by_invalid_reason"]["observer_integrity"] == 18
    assert arms["A3full"]["by_invalid_reason"]["broker"] == 1
    assert arms["A3full"]["by_invalid_reason"]["cleanup_inspect"] == 2
    assert arms["A3full"]["by_invalid_reason"]["cleanup_remove"] == 1
    assert arms["A3full"]["aborted_total"] == 22


def test_build_rollup_totals_and_markdown(tmp_path) -> None:
    md = tmp_path / "verdict.md"
    md.write_text(_M3_TABLE, encoding="utf-8")
    sources = {
        "m3_verdict_table": {
            "kind": "m3_verdict_table",
            "paths": [str(md)],
            "arms": parse_m3_abort_table(md),
        }
    }
    rollup = build_rollup(sources)

    assert rollup["abort_rollup_schema"] == 1
    assert rollup["vocabulary"] == [r.value for r in InvalidReason]
    # observer 19+18, broker 3+1, cleanup_inspect 1+2, cleanup_remove 0+1 = 45 aborts
    assert rollup["totals"]["aborted_total"] == 45
    assert rollup["totals"]["by_invalid_reason"]["observer_integrity"] == 37
    assert rollup["totals"]["by_invalid_reason"]["broker"] == 4

    md_text = render_markdown(rollup)
    assert "Abort category roll-up" in md_text
    assert "observer_integrity" in md_text


def test_rollup_counts_invalid_cases_and_schema3_invalid_steps(tmp_path) -> None:
    # Worker-pool invalid_cases[] (abandoned) + observer schema-3 steps[].validity=="invalid",
    # both the third validity=invalid bucket, counted by invalid_reason (not as aborts).
    _write(
        tmp_path / "x-m45-sa-s100.json",
        {
            "config": {},
            "steps": [
                {"index": 0, "validity": "valid"},
                {"index": 1, "validity": "invalid", "invalid_reason": "observer_integrity"},
            ],
            "invalid_cases": [
                {"case_id": "c", "invalid_reason": "broker"},
                {"case_id": "d", "invalid_reason": "cleanup_reset"},
            ],
        },
    )
    arms = rollup_raw_json(sorted(str(p) for p in tmp_path.glob("*.json")))
    sa = arms["sa"]
    assert sa["completed"] == 1
    assert sa["aborted_total"] == 0  # invalids are not aborts
    assert sa["invalid_total"] == 3
    assert sa["invalid_by_reason"]["observer_integrity"] == 1
    assert sa["invalid_by_reason"]["broker"] == 1
    assert sa["invalid_by_reason"]["cleanup_reset"] == 1


def _g1_index(tmp_path, cells) -> str:
    path = tmp_path / "index.json"
    path.write_text(json.dumps({"cells": cells}), encoding="utf-8")
    return str(path)


def test_read_g1_index_all_complete_is_all_zero(tmp_path) -> None:
    cells = [
        {"arm": a, "complete": True, "aborted": False, "invalid": False}
        for a in ("R", "D", "S-u")
        for _ in range(4)
    ]
    arms = read_g1_index(_g1_index(tmp_path, cells))
    assert set(arms) == {"R", "D", "S-u"}
    for arm in arms.values():
        assert arm["completed"] == 4
        assert arm["aborted_total"] == 0
        assert arm["invalid_total"] == 0
        assert set(arm["by_invalid_reason"].values()) == {0}
        assert set(arm["invalid_by_reason"].values()) == {0}


def test_read_g1_index_attributes_aborted_and_invalid_reasons(tmp_path) -> None:
    cells = [
        {"arm": "R", "complete": True},
        {"arm": "R", "aborted": True, "summary": "s_abort.json"},
        {"arm": "D", "invalid": True, "summary": "s_invalid.json"},
    ]

    def resolver(cell, _base):
        return InvalidReason.BROKER if cell.get("aborted") else InvalidReason.CLEANUP_RESET

    arms = read_g1_index(_g1_index(tmp_path, cells), reason_resolver=resolver)
    assert arms["R"]["completed"] == 1
    assert arms["R"]["aborted_total"] == 1
    assert arms["R"]["by_invalid_reason"]["broker"] == 1
    assert arms["D"]["invalid_total"] == 1
    assert arms["D"]["invalid_by_reason"]["cleanup_reset"] == 1


def test_g1_cell_reason_reads_summary_invalid_reason(tmp_path) -> None:
    (tmp_path / "s_invalid.json").write_text(
        json.dumps({"invalid_reason": "observer_integrity"}), encoding="utf-8"
    )
    cells = [{"arm": "S-u", "invalid": True, "summary": "s_invalid.json"}]
    arms = read_g1_index(_g1_index(tmp_path, cells))  # default resolver reads the summary
    assert arms["S-u"]["invalid_by_reason"]["observer_integrity"] == 1


def test_build_contingency_matrix_shape_and_totals(tmp_path) -> None:
    cells = [
        {"arm": "R", "complete": True},
        {"arm": "R", "complete": True},
        {"arm": "R", "aborted": True, "summary": "a.json"},
        {"arm": "D", "complete": True},
        {"arm": "D", "invalid": True, "summary": "i.json"},
    ]

    def resolver(cell, _base):
        return InvalidReason.BROKER if cell.get("aborted") else InvalidReason.OBSERVER_INTEGRITY

    arms = read_g1_index(_g1_index(tmp_path, cells), reason_resolver=resolver)
    cont = build_contingency(arms, arm_order=["R", "D"])

    assert cont["abort_contingency_schema"] == 1
    assert cont["arms"] == ["R", "D"]
    assert cont["reasons"] == [r.value for r in InvalidReason]
    # per-campaign is the independence-test input; per-event reasons are descriptive only.
    assert cont["primary_test_input"] == "per_campaign"
    assert cont["per_campaign"]["unit"] == "campaign"
    assert "not an independence-test input" in cont["per_event_reason"]["note"]
    assert cont["per_campaign"]["columns"] == ["complete", "aborted", "invalid"]
    # R: 2 complete, 1 aborted, 0 invalid ; D: 1 complete, 0 aborted, 1 invalid
    assert cont["per_campaign"]["matrix"] == [[2, 1, 0], [1, 0, 1]]
    # aborted reason matrix: R has 1 broker (col index 1); D none
    assert cont["per_event_reason"]["aborted"][0][cont["reasons"].index("broker")] == 1
    # invalid reason matrix: D has 1 observer_integrity (col index 0)
    assert cont["per_event_reason"]["invalid"][1][cont["reasons"].index("observer_integrity")] == 1
    assert cont["totals"]["aborted_grand"] == 1
    assert cont["totals"]["invalid_grand"] == 1
    assert cont["totals"]["event_grand_total"] == 2

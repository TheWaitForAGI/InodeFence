"""The abort-category roll-up tallies aborts per arm/reason over the shared vocabulary.

Fixtures are synthetic (no host evidence), so the check is reproducible in CI. The
raw stubs deliberately omit a ``category`` field to prove the roll-up classifies the
``reason`` string itself (back-filling pre-``category`` evidence).
"""

import json

from scripts.analyze_abort_rollup import (
    arm_from_filename,
    build_rollup,
    classify_md_label,
    parse_m3_abort_table,
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

"""#514 real-extractor fixture table on synthetic replays (no run, no Docker).

Each replay.json is made by the replay driver's own record builder
(``case_replay.build_replay_record``) from case folders the fixture generator writes, so the
reader is tested on the record shape ``inodefence replay`` publishes.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.analysis import oracle_accuracy_real_cases as cases
from scripts.analysis import oracle_accuracy_real_table as table

from inodefence.case_replay import ReplayRun, build_replay_record, load_replay_request

IMAGE = "sha256:" + "a" * 64
SETTINGS = {
    "sentinel_count": None,
    "sentinel_seed": None,
    "observer_integrity_policy": "stop",
    "profile": "full",
}
MOMENT = datetime(2026, 11, 18, tzinfo=UTC)
FIXTURES = ("F01", "F06", "F09", "F10", "F13")


def _label(fixture: str, expect, termination, grades, *, rounds: int = 3, design=None) -> dict:
    primary = next((g for g in "ADOI" if g in grades), None)
    return {
        "fixture": fixture,
        "cell": {"target": "node-tar", "version": "7.5.2"},
        "l_design": design or [False, False, False],
        "expect": expect,
        "termination": termination,
        "grades": grades,
        "primary": primary,
        "basis": "basis text",
        "rounds": rounds,
    }


LABELS = [
    _label("F01", [False, False, False], "success", ["O"]),
    _label("F06", [False, False, False], None, ["D"], design=[True, False, False]),
    _label("F09", [False, True, True], "success", ["O", "A"], design=[False, True, True]),
    _label("F10", [False, True, True], "success", ["O", "D"], design=[False, True, True]),
    _label("F13", "uncertain", None, [], design=[True, False, False]),
]


def _round(
    c=(False, False, False), termination: str | None = "success", outcome="judged", reason=None
) -> dict:
    if outcome == "run_error":
        return {"outcome": "run_error", "termination": termination, "reason": reason}
    return {
        "outcome": "judged",
        "termination": termination,
        "c0": c[0],
        "c1": c[1],
        "c2": c[2],
        "observation_complete": True,
    }


def _setup(tmp_path: Path, rounds: dict[str, list[dict]], *, labels=None, complete=True):
    out = tmp_path / "cases"
    rows = cases.write_cases(
        out,
        target="node-tar",
        version="7.5.2",
        image_id=IMAGE,
        run_settings=SETTINGS,
        fixtures=FIXTURES,
    )
    cases.write_manifest(out, rows)
    replays = tmp_path / "replays"
    for row in rows:
        if row["fixture"] not in rounds:
            continue
        request = load_replay_request(out / row["case_dir"])
        run = ReplayRun(tuple(rounds[row["fixture"]]), complete=complete, engine_commit="e" * 40)
        record = build_replay_record(request, run, started_at=MOMENT, finished_at=MOMENT)
        folder = replays / f"{row['fixture']}.replay"
        folder.mkdir(parents=True)
        (folder / "replay.json").write_text(json.dumps(record), encoding="utf-8")
    label_path = tmp_path / "514-labels-v1.json"
    label_path.write_text(
        json.dumps(
            {
                "schema": table.LABELS_SCHEMA,
                "design": {"sha256": "d" * 64},
                "cells": labels or LABELS,
            }
        ),
        encoding="utf-8",
    )
    return label_path, out / "manifest.json", replays


def _table(capsys, label_path: Path, manifest: Path, replays: Path) -> tuple[int, dict]:
    code = table.main(
        ["--labels", str(label_path), "--manifest", str(manifest), "--replays", str(replays)]
    )
    return code, json.loads(capsys.readouterr().out)


def _classes(out: dict) -> dict[str, str]:
    return {row["fixture"]: row["class"] for row in out["rows"]}


THREE_OK = [_round()] * 3
THREE_REJECTED = [_round(termination="rejected")] * 3
THREE_HIT = [_round((False, True, True))] * 3


def test_each_class_in_order(tmp_path: Path, capsys) -> None:
    code, out = _table(
        capsys,
        *_setup(
            tmp_path,
            {
                "F01": THREE_OK,  # 일치
                "F06": THREE_REJECTED,  # n n n expected, success/null, all rejected -> 막음
                "F09": THREE_REJECTED,  # expected y, all rejected -> 거부로 기대 효과 차단
                "F10": [_round((False, True, False))] * 3,  # 불일치
                "F13": THREE_HIT,  # uncertain
            },
        ),
    )
    assert code == 0
    assert _classes(out) == {
        "F01": "일치",
        "F06": "추출기가 막음",
        "F09": "거부로 기대 효과 차단",
        "F10": "불일치",
        "F13": "불확실",
    }
    summary = out["summary"]["node-tar 7.5.2"]
    assert summary["scored_cells"] == 2
    assert summary["excluded_line"] == (
        "분모에서 제외: 라운드 갈림 0, 거부 동작 일치 0, 추출기가 막음 1, "
        "거부로 기대 효과 차단 1, 불확실 1, 미완료·미판정 0"
    )
    # descriptive table: one column per cell, by the label's primary grade
    by_grade = summary["descriptive_by_primary_grade"]
    assert by_grade["O"]["일치"] == 1  # F01: O only
    assert by_grade["D"]["불일치"] == 1  # F10: O and D, primary D
    assert by_grade["D"]["mismatch_by_contract"]["C2"] == {
        "oracle_y_expect_n": 0,
        "oracle_n_expect_y": 1,
    }
    member = summary["claim_by_membership"]
    assert member["external (A or D)"]["불일치"] == 1
    assert member["ours (O and I only)"]["일치"] == 1
    assert out["header"] == "판정 대상은 손 라벨 기대값이지 파일시스템 진실이 아니다."
    assert "%" not in json.dumps(out["summary"], ensure_ascii=False)


def test_refusal_match_is_its_own_class(tmp_path: Path, capsys) -> None:
    labels = copy.deepcopy(LABELS)
    labels[1]["termination"] = "rejected"  # F06: expected n n n and rejected
    code, out = _table(capsys, *_setup(tmp_path, {"F06": THREE_REJECTED}, labels=labels))
    assert code == 0 and _classes(out)["F06"] == "거부 동작 일치"


def test_split_rounds_are_never_a_majority(tmp_path: Path, capsys) -> None:
    split = [_round(), _round(), _round((False, True, True))]
    by_termination = [_round(), _round(), _round(termination="failed")]
    code, out = _table(capsys, *_setup(tmp_path, {"F01": split, "F09": by_termination}))
    assert _classes(out)["F01"] == "라운드 갈림"
    assert _classes(out)["F09"] == "라운드 갈림"
    row = next(r for r in out["rows"] if r["fixture"] == "F01")
    assert row["contract_y_rounds"] == {"C0": "0/3", "C1": "1/3", "C2": "1/3"}


def test_partly_rejected_rounds_are_split_not_blocked(tmp_path: Path, capsys) -> None:
    rounds = [_round(termination="rejected"), _round(termination="rejected"), _round()]
    code, out = _table(capsys, *_setup(tmp_path, {"F06": rounds}))
    assert _classes(out)["F06"] == "라운드 갈림"


def test_run_errors_are_a_column_and_zero_judged_is_unjudged(tmp_path: Path, capsys) -> None:
    mixed = [_round(), _round(), _round(outcome="run_error", termination=None, reason="x")]
    none = [_round(outcome="run_error", termination="failed", reason="integrity")] * 3
    code, out = _table(capsys, *_setup(tmp_path, {"F01": mixed, "F09": none}))
    classes = _classes(out)
    assert classes["F01"] == "일치"
    assert classes["F09"] == "미완료·미판정"
    assert classes["F10"] == "미완료·미판정"  # no replay at all
    row = next(r for r in out["rows"] if r["fixture"] == "F01")
    assert (row["judged_rounds"], row["run_errors"], row["run_error_reasons"]) == (2, 1, ["x"])


def test_an_incomplete_replay_is_unfinished_whatever_it_judged(tmp_path: Path, capsys) -> None:
    code, out = _table(capsys, *_setup(tmp_path, {"F01": THREE_OK[:2]}, complete=False))
    assert _classes(out)["F01"] == "미완료·미판정"


def test_termination_is_a_flag_not_a_score(tmp_path: Path, capsys) -> None:
    labels = copy.deepcopy(LABELS)
    labels[0]["termination"] = "rejected"  # F01 expects rejected, runs succeed with n n n
    code, out = _table(capsys, *_setup(tmp_path, {"F01": THREE_OK}, labels=labels))
    row = next(r for r in out["rows"] if r["fixture"] == "F01")
    assert (row["class"], row["flags"]) == ("일치", ["종료 기대와 다름"])
    assert out["summary"]["node-tar 7.5.2"]["termination_flags"] == 1


def test_null_termination_is_not_looked_at(tmp_path: Path, capsys) -> None:
    rounds = [_round(termination="failed")] * 3
    code, out = _table(capsys, *_setup(tmp_path, {"F06": rounds}))
    row = next(r for r in out["rows"] if r["fixture"] == "F06")
    assert (row["class"], row["flags"]) == ("일치", [])


def test_i_only_cells_are_counted_apart(tmp_path: Path, capsys) -> None:
    labels = copy.deepcopy(LABELS)
    labels[0]["grades"], labels[0]["primary"] = ["I"], "I"
    code, out = _table(capsys, *_setup(tmp_path, {"F01": THREE_OK}, labels=labels))
    summary = out["summary"]["node-tar 7.5.2"]
    assert summary["i_only_cells"] == 1
    assert summary["claim_by_membership"]["ours (O and I only)"]["일치"] == 1


def test_inputs_carry_their_hashes_and_replays_their_provenance(tmp_path: Path, capsys) -> None:
    label_path, manifest, replays = _setup(tmp_path, {"F01": THREE_OK})
    code, out = _table(capsys, label_path, manifest, replays)
    assert out["inputs"]["labels_sha256"] == table._sha256(label_path)
    assert out["inputs"]["labels_header"]["design"] == {"sha256": "d" * 64}
    row = next(r for r in out["rows"] if r["fixture"] == "F01")
    assert row["provenance"]["image_id"] == IMAGE
    assert row["provenance"]["engine_commit"] == "e" * 40
    assert len(row["provenance"]["replay_json_sha256"]) == 64


# -- input errors (exit 2) ------------------------------------------------------------------------


def test_a_replay_not_in_the_manifest_is_refused(tmp_path: Path, capsys) -> None:
    label_path, manifest, replays = _setup(tmp_path, {"F01": THREE_OK})
    path = next(replays.rglob("replay.json"))
    data = json.loads(path.read_text())
    data["original"]["tar_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    code, out = _table(capsys, label_path, manifest, replays)
    assert code == 2 and "not in the manifest" in out["error"]


def test_the_folder_name_never_links_a_replay(tmp_path: Path, capsys) -> None:
    """Renaming a replay folder to another fixture changes nothing: the tar hash decides."""
    label_path, manifest, replays = _setup(tmp_path, {"F01": THREE_OK})
    (replays / "F01.replay").rename(replays / "F09.replay")
    code, out = _table(capsys, label_path, manifest, replays)
    assert code == 0 and _classes(out)["F01"] == "일치"
    assert _classes(out)["F09"] == "미완료·미판정"


def test_two_replays_for_one_cell_are_refused(tmp_path: Path, capsys) -> None:
    label_path, manifest, replays = _setup(tmp_path, {"F01": THREE_OK})
    (replays / "again").mkdir()
    (replays / "again" / "replay.json").write_text(
        (replays / "F01.replay" / "replay.json").read_text()
    )
    code, out = _table(capsys, label_path, manifest, replays)
    assert code == 2 and "second replay.json" in out["error"]


def test_rounds_must_match_the_label(tmp_path: Path, capsys) -> None:
    labels = copy.deepcopy(LABELS)
    labels[0]["rounds"] = 20
    code, out = _table(capsys, *_setup(tmp_path, {"F01": THREE_OK}, labels=labels))
    assert code == 2 and "rounds requested" in out["error"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("primary", "O", "not the first of A > D > O > I"),
        ("grades", ["X"], "grades must be among"),
        ("termination", "failed", "termination must be"),
        ("expect", [True, False], "three booleans"),
    ],
)
def test_malformed_labels_are_refused(tmp_path: Path, capsys, field, value, message) -> None:
    labels = copy.deepcopy(LABELS)
    labels[2][field] = value  # F09: grades O and A, primary A
    code, out = _table(capsys, *_setup(tmp_path, {"F01": THREE_OK}, labels=labels))
    assert code == 2 and message in out["error"]


def test_a_replay_of_an_unlabelled_cell_is_refused(tmp_path: Path, capsys) -> None:
    labels = [label for label in LABELS if label["fixture"] != "F01"]
    code, out = _table(capsys, *_setup(tmp_path, {"F01": THREE_OK}, labels=labels))
    assert code == 2 and "has no label" in out["error"]


def test_a_label_file_of_another_schema_is_refused(tmp_path: Path, capsys) -> None:
    label_path, manifest, replays = _setup(tmp_path, {"F01": THREE_OK})
    data = json.loads(label_path.read_text())
    data["schema"] = "something-else"
    label_path.write_text(json.dumps(data))
    code, out = _table(capsys, label_path, manifest, replays)
    assert code == 2 and "label file" in out["error"]


def test_one_judged_round_is_flagged_k_of_n(tmp_path: Path, capsys) -> None:
    rounds = [_round(), *[_round(outcome="run_error", termination=None, reason="x")] * 2]
    code, out = _table(capsys, *_setup(tmp_path, {"F01": rounds}))
    row = next(r for r in out["rows"] if r["fixture"] == "F01")
    assert (row["class"], row["flags"]) == ("일치", ["판정 1/3"])


def test_two_judged_of_three_are_flagged_and_still_scored(tmp_path: Path, capsys) -> None:
    rounds = [_round(), _round(), _round(outcome="run_error", termination=None, reason="x")]
    code, out = _table(capsys, *_setup(tmp_path, {"F01": rounds}))
    row = next(r for r in out["rows"] if r["fixture"] == "F01")
    assert (row["class"], row["flags"]) == ("일치", ["판정 2/3"])
    assert out["summary"]["node-tar 7.5.2"]["scored_cells"] == 1


def test_python_tarfile_cells_are_keyed_by_filter(tmp_path: Path, capsys) -> None:
    """The label cell carries extraction_filter; the replay's run_settings must match it."""
    out_dir = tmp_path / "cases"
    settings = {"extraction_filter": "data", "runtime_version": "3.12.16"}
    rows = cases.write_cases(
        out_dir,
        target="python-tarfile",
        version="3.12.16",
        image_id=IMAGE,
        run_settings=settings,
        fixtures=("F06",),
    )
    cases.write_manifest(out_dir, rows)
    assert rows[0]["extraction_filter"] == "data"
    request = load_replay_request(out_dir / rows[0]["case_dir"])
    record = build_replay_record(
        request,
        ReplayRun(tuple([_round(termination="rejected")] * 3), complete=True),
        started_at=MOMENT,
        finished_at=MOMENT,
    )
    replays = tmp_path / "replays" / "x"
    replays.mkdir(parents=True)
    (replays / "replay.json").write_text(json.dumps(record))
    label = {
        **_label("F06", [False, False, False], "rejected", ["D"], design=[True, False, False]),
        "cell": {"target": "python-tarfile", "version": "3.12.16", "extraction_filter": "data"},
    }
    label_path = tmp_path / "labels.json"
    label_path.write_text(json.dumps({"schema": table.LABELS_SCHEMA, "cells": [label]}))
    code, out = _table(capsys, label_path, out_dir / "manifest.json", tmp_path / "replays")
    assert code == 0
    assert out["rows"][0]["cell"] == "python-tarfile 3.12.16 data"
    assert out["rows"][0]["class"] == "거부 동작 일치"


def test_uncertain_comes_before_split_rounds(tmp_path: Path, capsys) -> None:
    """§2b order: ② 불확실 is checked before ③ 라운드 갈림."""
    split = [_round(), _round(), _round((True, False, False))]
    code, out = _table(capsys, *_setup(tmp_path, {"F13": split}))
    assert _classes(out)["F13"] == "불확실"

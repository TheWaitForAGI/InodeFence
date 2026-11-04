"""The evidence-chain checker classifies each summary's raw pointers."""

import json
from pathlib import Path

from scripts.check_evidence_chain import (
    ChainRow,
    _expand_braces,
    _failed,
    check_summaries,
    classify_pointer,
    iter_pointer_values,
)

INDEX = {"raw-manifest-mac-20261103.sha256": {"m3-powered-matched-20261030", "m4-powered-20261030"}}


def _classify(pointer: str, repo_root: Path) -> ChainRow:
    return classify_pointer(pointer, repo_root, INDEX)


def test_manifest_covered_and_absent(tmp_path: Path) -> None:
    covered = _classify("~/inodefence-evidence/m3-powered-matched-20261030/ (host-local)", tmp_path)
    assert covered.status == "MANIFEST-COVERED"
    absent = _classify("/Users/x/inodefence-evidence/never-recorded-20991231/*.json", tmp_path)
    assert absent.status == "MANIFEST-ABSENT"


def test_manifest_covered_handles_glob(tmp_path: Path) -> None:
    row = _classify("/Users/x/inodefence-evidence/m4-powered-20261030/*m4p-*.json", tmp_path)
    assert row.status == "MANIFEST-COVERED"


def test_repo_present_and_missing(tmp_path: Path) -> None:
    (tmp_path / "experiments" / "summaries").mkdir(parents=True)
    (tmp_path / "experiments" / "summaries" / "a.json").write_text("{}", encoding="utf-8")
    present = _classify("experiments/summaries/a.json", tmp_path)
    assert present.status == "REPO-PRESENT"
    missing = _classify("experiments/summaries/nope.json", tmp_path)
    assert missing.status == "REPO-MISSING"


def test_repo_present_accepts_script_pointer(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "x.py").write_text("", encoding="utf-8")
    row = _classify("scripts/x.py (eval-lane roll-up; code unchanged)", tmp_path)
    assert row.status == "REPO-PRESENT"


def test_brace_expansion_requires_every_member(tmp_path: Path) -> None:
    summaries = tmp_path / "experiments" / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "v1.md").write_text("", encoding="utf-8")
    (summaries / "v1.json").write_text("{}", encoding="utf-8")
    assert _classify("experiments/summaries/v1.{md,json}", tmp_path).status == "REPO-PRESENT"
    (summaries / "v1.json").unlink()
    assert _classify("experiments/summaries/v1.{md,json}", tmp_path).status == "REPO-MISSING"


def test_raw_gitignored_and_raw_filename(tmp_path: Path) -> None:
    assert _classify("experiments/raw/session-f-audit", tmp_path).status == "RAW-GITIGNORED"
    assert _classify("campaign-0-seed-11-budget-25.json", tmp_path).status == "RAW-FILENAME"


def test_expand_braces() -> None:
    assert _expand_braces("a.{md,json}") == ["a.md", "a.json"]
    assert _expand_braces("plain") == ["plain"]


def test_iter_pointer_values_only_under_pointer_keys() -> None:
    data = {
        "raw_pointer": "~/inodefence-evidence/x/",
        "note": "not/a/pointer/field",
        "nested": {"rollup_source": "experiments/summaries/y.json", "seed": 11},
    }
    found = set(iter_pointer_values(data))
    assert "~/inodefence-evidence/x/" in found
    assert "experiments/summaries/y.json" in found
    assert "not/a/pointer/field" not in found


def test_check_summaries_and_failed(tmp_path: Path) -> None:
    summaries = tmp_path / "experiments" / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "raw-manifest-mac-20261103.sha256").write_text(
        "0" * 64 + "  ./m3-powered-matched-20261030/cell.json\n", encoding="utf-8"
    )
    (summaries / "s.json").write_text(
        json.dumps(
            {"raw_pointers": {"evidence_dir": "~/inodefence-evidence/m3-powered-matched-20261030/"}}
        ),
        encoding="utf-8",
    )
    (summaries / "broken.json").write_text(
        json.dumps({"rollup_source": "experiments/summaries/missing.json"}), encoding="utf-8"
    )
    rows = check_summaries(summaries, tmp_path)
    statuses = {row.summary: row.status for row in rows}
    assert statuses["s.json"] == "MANIFEST-COVERED"
    assert statuses["broken.json"] == "REPO-MISSING"
    assert _failed(rows, strict=False) is True


def test_failed_strict_flags_absent() -> None:
    rows = [ChainRow("x.json", "p", "MANIFEST-ABSENT", "d")]
    assert _failed(rows, strict=False) is False
    assert _failed(rows, strict=True) is True

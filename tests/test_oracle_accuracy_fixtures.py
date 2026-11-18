"""#514: oracle-independent truth and the hand-labelled fixture runner (exploratory)."""

import ast
import os
from pathlib import Path

from scripts.fs_truth import snapshot, truth
from scripts.oracle_accuracy_fixtures import CASES, hand_labels, measure
from scripts.oracle_fixture_check import UncheckedControlledExtractor

ROOT = Path(__file__).resolve().parents[1]


def test_truth_module_imports_no_inodefence_code():
    tree = ast.parse((ROOT / "scripts/fs_truth.py").read_text(encoding="utf-8"))
    names = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in getattr(node, "names", [])
    ] + [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any("inodefence" in n or n.startswith("scripts") for n in names), names


def _sandbox(tmp_path: Path) -> Path:
    (tmp_path / "extract").mkdir()
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside/sentinel.txt").write_bytes(b"s")
    return tmp_path


def test_truth_on_raw_changes(tmp_path):
    root = _sandbox(tmp_path)
    before = snapshot(root)
    assert truth(before, snapshot(root)) == (False, False, False)

    os.link(root / "outside/sentinel.txt", root / "extract/alias")  # C1 and C2 (nlink)
    (root / "escape.txt").write_bytes(b"x")  # C0
    assert truth(before, snapshot(root)) == (True, True, True)


def test_in_place_content_change_outside_is_not_c0(tmp_path):
    root = _sandbox(tmp_path)
    (root / "outside/other.txt").write_bytes(b"a")
    before = snapshot(root)
    (root / "outside/other.txt").write_bytes(b"b")
    assert truth(before, snapshot(root)) == (False, False, False)


def test_every_executable_fixture_has_a_committed_hand_label():
    labels = hand_labels()
    assert set(CASES) <= set(labels)


def test_runner_reports_hand_truth_and_oracle_side_by_side():
    labels = hand_labels()
    for fixture in ("F01", "F06", "F09", "F12"):
        row = measure(fixture, UncheckedControlledExtractor())
        assert row["truth"] == list(labels[fixture]), fixture
        assert len(row["oracle"]) == 3

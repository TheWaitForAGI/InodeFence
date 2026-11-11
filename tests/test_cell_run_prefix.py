"""Cell.run_prefix (concurrency v3 hosts) leaves every existing run id byte-identical."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from scripts.run_exp0 import TargetCell, main
from scripts.run_parallel_native import Arm, Cell
from tests.test_run_exp0 import _base_args, _plan, clean_engine, prereg_file  # noqa: F401

ARM = Arm("R-restart", "s", "m")


def test_default_prefix_keeps_run_id_and_evidence_name() -> None:
    cell = Cell("demo-historical", "7.5.2", ARM, 8110, 2000)
    assert cell.run_prefix == ""
    assert cell.run_id == "7.5.2-R-restart-s8110"
    assert cell.evidence_basename == "inodefence-effect-demo-historical-7.5.2-R-restart-s8110"
    assert Cell("demo", None, ARM, 1, 1).run_id == "native-R-restart-s1"


def test_prefix_goes_in_front_of_the_v2_run_id() -> None:
    cell = Cell("demo-historical", "7.5.2", ARM, 8110, 2000, run_prefix="h2")
    assert cell.run_id == "h2-7.5.2-R-restart-s8110"
    assert cell.evidence_basename == "inodefence-effect-demo-historical-h2-7.5.2-R-restart-s8110"


def test_invalid_prefix_is_refused_like_any_run_id() -> None:
    with pytest.raises(ValueError, match="not a valid resource name"):
        _ = Cell("demo-historical", "7.5.2", ARM, 1, 1, run_prefix="-bad").run_id


def test_target_cell_run_id_is_unchanged() -> None:
    cell = TargetCell("demo-historical", "7.5.2", ARM, 9001, 6, target_id="7.5.2")
    assert cell.run_prefix == ""
    assert cell.run_id == "7.5.2-R-restart-s9001"


def test_exp0_plan_and_dry_run_run_ids_are_unchanged(
    prereg_file: Path,  # noqa: F811
    tmp_path: Path,
    clean_engine: None,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    cells = _plan(prereg_file).cells()
    assert all(cell.run_prefix == "" for cell in cells)
    expected = {f"{cell.version}-{cell.arm.label}-s{cell.seed}" for cell in cells}
    assert {cell.run_id for cell in cells} == expected
    assert main([*_base_args(prereg_file, tmp_path / "exp0"), "--dry-run"]) == 0
    printed = set(re.findall(r'"RUN_ID": "([^"]+)"', capsys.readouterr().out))
    assert printed == expected

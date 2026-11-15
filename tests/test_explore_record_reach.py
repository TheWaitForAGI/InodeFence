"""The exploration result-record rules never reach the registered experiment path.

``exploration_demo_report`` (node-tar) and ``python_tarfile_explore.case_record`` /
``python_tarfile_exploration_report`` decide how an exploration *records* each run (judged or
run_error). They are exploration-only: the registered EXP runs go through ``run_exp0`` (and the
hazard pilot ``run_hazard_pilot``) ->
``local_node_tar_smoke.sh demo-historical`` -> the controller's historical mode, and the RDS cells
through ``inodefence.evaluation.rds``. This test pins that wiring statically, so a change to the
exploration record cannot silently alter a registered run.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXPLORE_RECORD_NAMES = {
    "exploration_demo_report",
    "python_tarfile_exploration_report",
    "case_record",
    "python_tarfile_explore",
}


def _callers(path: Path, name: str) -> set[str]:
    """Top-level functions in ``path`` whose body calls ``name``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) == name:
                    found.add(node.name)
    return found


def test_only_the_explore_modes_of_the_controller_call_the_record_code() -> None:
    controller = REPO / "scripts" / "container_controller.py"
    assert _callers(controller, "exploration_demo_report") == {"run_native_exploration_demo"}
    assert _callers(controller, "python_tarfile_exploration_report") == {
        "run_native_python_tarfile_campaign"
    }
    assert _callers(controller, "historical_demo_report") == {"run_native_historical_demo"}


@pytest.mark.parametrize("runner", ["run_exp0.py", "run_hazard_pilot.py"])
def test_the_registered_runners_launch_only_the_historical_mode(runner: str) -> None:
    text = (REPO / "scripts" / runner).read_text(encoding="utf-8")
    assert "demo-historical" in text
    assert "effect-demo-explore" not in text and "python-tarfile-effect-campaign" not in text


def test_registered_modules_do_not_reference_the_exploration_record() -> None:
    registered = [
        REPO / "scripts" / "run_exp0.py",
        REPO / "scripts" / "run_hazard_pilot.py",
        REPO / "scripts" / "run_rds_cell.py",
        *sorted((REPO / "src" / "inodefence" / "evaluation").glob("rds*.py")),
    ]
    for path in registered:
        text = path.read_text(encoding="utf-8")
        hits = sorted(name for name in EXPLORE_RECORD_NAMES if name in text)
        assert hits == [], f"{path.relative_to(REPO)} references {hits}"

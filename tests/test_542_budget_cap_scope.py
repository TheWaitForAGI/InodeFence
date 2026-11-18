"""#542 decision A: the budget cap is lifted for the decompress and oras-go campaign modes, and only
the exploration drivers may ask them for more than the cap (W4 condition, option ①).

The two modes stream their steps into the report collectors (``scripts/container_controller.py``),
so memory no longer grows with the run count. The same modes also ran the past M4 campaigns, so
the cap is lifted for the whole mode; what keeps a bounded run bounded is that no path in the
repository other than the exploration drivers sets a budget for them. This file pins that:

* the argument check: both modes accept ``MAX_NATIVE_BUDGET + 1`` and refuse 0; every other
  capped mode still refuses ``MAX_NATIVE_BUDGET + 1``;
* the callers: the repository files (outside tests) that name either launcher or either mode are
  exactly the listed ones, and only the two exploration drivers among them set ``DEMO_BUDGET``.
  A new caller fails here until it is classified.

Not covered (stated in the decision): a person who runs a launcher or the controller by hand with
``DEMO_BUDGET`` above the cap. That run streams, so its memory does not grow with the budget.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest
from scripts.run_effect_demo import (
    DECOMPRESS_CAMPAIGN_MODE,
    MAX_NATIVE_BUDGET,
    ORAS_GO_CAMPAIGN_MODE,
    PYTHON_TARFILE_CAMPAIGN_MODE,
    UNCAPPED_BUDGET_MODES,
    add_demo_arguments,
    check_demo_arguments,
)

REPO = Path(__file__).resolve().parents[1]
OVER = str(MAX_NATIVE_BUDGET + 1)

#: Every repository file outside tests that names either launcher or either campaign mode, and
#: why. Only the two exploration drivers set a budget for them.
CALLERS = {
    "scripts/local_decompress_selfdiscover.sh": "the decompress launcher itself",
    "scripts/local_oras_go_selfdiscover.sh": "the oras-go launcher itself",
    "scripts/local_python_tarfile_explore.sh": "comment only (mirrors the decompress launcher)",
    "scripts/container_controller.py": "runs the modes",
    "scripts/container_host.py": "broker mode list",
    "scripts/run_effect_demo.py": "mode constants and the budget check",
    "scripts/analysis/analyze_m4_decompress_abcd.py": "reads finished reports, launches nothing",
    "src/inodefence/drivers/launcher.py": "target -> launcher path map",
    "src/inodefence/drivers/runtime/shared_images.py": "shared image build, no campaign",
    "src/inodefence/drivers/decompress/explore.py": "exploration driver (sets DEMO_BUDGET)",
    "src/inodefence/drivers/oras_go/explore.py": "exploration driver (sets DEMO_BUDGET)",
    "experiments/summaries/m4-7-oras-go-selfdiscover-v1.json": "a past run's summary (data)",
}
BUDGET_SETTERS = {
    "src/inodefence/drivers/decompress/explore.py",
    "src/inodefence/drivers/oras_go/explore.py",
}
_NAMES = re.compile(
    r"local_decompress_selfdiscover\.sh|local_oras_go_selfdiscover\.sh|"
    r"decompress-effect-campaign|oras-go-effect-campaign|"
    r"DECOMPRESS_CAMPAIGN_MODE|ORAS_GO_CAMPAIGN_MODE"
)
_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".toml", ".mk", ".cfg", ".ini", ".json"}
_SKIP = {".git", ".venv", "build", "tests", "node_modules", "__pycache__", ".claude"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    add_demo_arguments(parser)
    parser.add_argument("mode")
    return parser


@pytest.mark.parametrize("mode", [DECOMPRESS_CAMPAIGN_MODE, ORAS_GO_CAMPAIGN_MODE])
def test_the_streaming_campaign_modes_take_a_budget_above_the_cap(mode: str) -> None:
    parser = _parser()
    check_demo_arguments(parser, parser.parse_args(["--budget", OVER, mode]))
    with pytest.raises(SystemExit):
        check_demo_arguments(parser, parser.parse_args(["--budget", "0", mode]))


def test_the_other_capped_modes_keep_the_cap() -> None:
    assert set(UNCAPPED_BUDGET_MODES) == {
        "effect-demo-explore",
        DECOMPRESS_CAMPAIGN_MODE,
        ORAS_GO_CAMPAIGN_MODE,
    }
    parser = _parser()
    with pytest.raises(SystemExit):
        check_demo_arguments(parser, parser.parse_args(["--budget", OVER, "effect-demo"]))
    with pytest.raises(SystemExit):
        check_demo_arguments(
            parser,
            parser.parse_args(
                [
                    "--budget",
                    OVER,
                    "--runtime-version",
                    "3.14.10",
                    "--extraction-filter",
                    "data",
                    PYTHON_TARFILE_CAMPAIGN_MODE,
                ]
            ),
        )


def _repository_files() -> list[Path]:
    found = []
    for path in REPO.rglob("*"):
        parts = path.relative_to(REPO).parts
        if any(part in _SKIP for part in parts) or not path.is_file():
            continue
        if path.suffix in _SUFFIXES or path.name in {"Makefile"}:
            found.append(path)
    return found


def test_only_the_listed_files_reach_the_two_modes() -> None:
    naming = {
        path.relative_to(REPO).as_posix()
        for path in _repository_files()
        if _NAMES.search(path.read_text(encoding="utf-8", errors="replace"))
    }
    assert naming == set(CALLERS), (
        "a file names the decompress/oras-go launcher or campaign mode; classify it in CALLERS "
        f"(new: {sorted(naming - set(CALLERS))}, gone: {sorted(set(CALLERS) - naming)})"
    )


def test_only_the_exploration_drivers_set_a_budget_for_them() -> None:
    setters = {
        name
        for name in CALLERS
        if not name.endswith(".sh") and "DEMO_BUDGET" in (REPO / name).read_text(encoding="utf-8")
    }
    assert setters == BUDGET_SETTERS

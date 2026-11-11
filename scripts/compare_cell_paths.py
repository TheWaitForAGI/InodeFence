"""Compare cell paths pair by pair (``case_id`` sequences). Report only, never a verdict input.

Two uses, one input form (a labelled pair of steps files):

* across hosts: the same replicate-v1 cell on HOST1 and HOST2 (``merge_host_indexes --compare``);
* within a host: an original cell against its re-run, when a cross-host comparison needs
  explaining (v3 / D047: m_x >= 2 or incomparable >= 2).

    python -m scripts.compare_cell_paths --budget 2000 \\
        --pair 7.5.2-D-s8110=<original>.steps.jsonl,<rerun>.steps.jsonl [--pair ...] --out C.json

Per pair: whether the two sequences are equal, their common prefix and lengths, and each side's
infrastructure re-execution count (``infra_reexecutions`` of the report next to the steps file,
``<name>.json``). Summary: ``m_x`` (comparable pairs that differ), ``incomparable`` and
``identical``. Sealed: from steps files only ``index`` and ``case_id``; from reports only
``infra_reexecutions``. No case id, hash or oracle field is written out.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scripts.compare_pilot_rerun_paths import UnreadableSteps, compare_paths, read_case_ids

STEPS_SUFFIX = ".steps.jsonl"


def report_beside(steps: Path) -> Path:
    """The report written next to a steps file (``<name>.json``)."""
    name = steps.name
    stem = name[: -len(STEPS_SUFFIX)] if name.endswith(STEPS_SUFFIX) else steps.stem
    return steps.with_name(f"{stem}.json")


def reexecutions(steps: Path) -> int | None:
    """Infrastructure re-executions of the cell, from its report only (``None``: no report)."""
    report = report_beside(steps)
    if not report.is_file():
        return None
    try:
        value = json.loads(report.read_text(encoding="utf-8")).get("infra_reexecutions")
    except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
        return None
    return len(value) if isinstance(value, list) else 0


def compare_pairs(
    pairs: Mapping[str, tuple[Path, Path]], budget: int, sides: tuple[str, str] = ("a", "b")
) -> dict[str, Any]:
    """Each labelled pair of steps files, compared; then the summary counts."""
    cells: dict[str, Any] = {}
    for label, (left, right) in sorted(pairs.items()):
        flags = {sides[0]: reexecutions(left), sides[1]: reexecutions(right)}
        try:
            first, second = read_case_ids(left), read_case_ids(right)
        except (UnreadableSteps, OSError) as error:
            cells[label] = {
                "comparable": False,
                "reason": type(error).__name__,
                "reexecutions": flags,
            }
            continue
        result = compare_paths(first, second, budget)
        cells[label] = {
            "comparable": True,
            "path_identical": first == second,
            "common_prefix": result["common_prefix"],
            "steps": {sides[0]: len(first), sides[1]: len(second)},
            "limit": result["limit"],
            "reexecutions": flags,
        }
    comparable = [cell for cell in cells.values() if cell["comparable"]]
    return {
        "sides": list(sides),
        "cells": cells,
        "summary": {
            "pairs": len(cells),
            "identical": sum(1 for cell in comparable if cell["path_identical"]),
            "m_x": sum(1 for cell in comparable if not cell["path_identical"]),
            "incomparable": len(cells) - len(comparable),
            "with_reexecutions": sorted(
                label
                for label, cell in cells.items()
                if any(count for count in cell["reexecutions"].values())
            ),
        },
    }


def _pair(text: str) -> tuple[str, tuple[Path, Path]]:
    label, sep, rest = text.partition("=")
    left, comma, right = rest.partition(",")
    if not sep or not comma or not label or not left or not right:
        raise argparse.ArgumentTypeError(f"expected LABEL=LEFT,RIGHT, got {text!r}")
    return label, (Path(left), Path(right))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--pair", type=_pair, action="append", required=True)
    parser.add_argument("--budget", type=int, required=True)
    parser.add_argument("--sides", default="original,rerun", help="names of the two sides")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    pairs = dict(args.pair)
    if len(pairs) != len(args.pair):
        parser.error("each label once")
    sides = tuple(args.sides.split(","))
    if len(sides) != 2:
        parser.error("--sides names exactly two sides")
    document = {
        "classification": "cell path comparison: report only, never a verdict input",
        **compare_pairs(pairs, args.budget, (sides[0], sides[1])),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

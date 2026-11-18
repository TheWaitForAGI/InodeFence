"""Oracle accuracy on hand-labelled fixtures (#514, exploratory; not a registered result).

For each fixture in ``experiments/configs/oracle-accuracy-fixtures-v1.md`` this runs the
production pipeline (``run_case``: Observer + Oracle) with two extractors inside the disposable
sandbox, and reports three things side by side per contract C0, C1, C2:

* **hand**: the label committed before any run (read from the fixture file, never edited here);
* **truth**: what ``scripts/fs_truth.py`` finds in raw before/after snapshots of the sandbox,
  taken inside the extractor's run window by a wrapper; that module imports no InodeFence code;
* **oracle**: the pipeline's verdict.

The output is a per-fixture table and a per-contract confusion count over these fixtures only. It
does not claim a general accuracy. The oracle's meaning is not changed.

Run: PYTHONPATH=src python -m scripts.oracle_accuracy_fixtures [--json OUT]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from scripts.fs_truth import snapshot, truth
from scripts.generate_tar_fixtures import CONTENT
from scripts.oracle_fixture_check import UncheckedControlledExtractor
from scripts.oracle_fn_matrix import PolicyExtractor

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, ExecutionResult
from inodefence.pipeline import run_case

LABELS = Path(__file__).resolve().parents[1] / "experiments/configs/oracle-accuracy-fixtures-v1.md"
SENTINEL = "../outside/sentinel.txt"
CONTRACTS = ("C0", "C1", "C2")


def _reg(name: str) -> ArchiveEntry:
    return ArchiveEntry(name, EntryType.REGULAR, content=CONTENT)


def _dir(name: str) -> ArchiveEntry:
    return ArchiveEntry(name, EntryType.DIRECTORY)


def _sym(name: str, target: str) -> ArchiveEntry:
    return ArchiveEntry(name, EntryType.SYMLINK, link_target=target, mode=0o777)


def _hard(name: str, target: str) -> ArchiveEntry:
    return ArchiveEntry(name, EntryType.HARDLINK, link_target=target)


DEEP = "/".join(f"d{i}" for i in range(1, 11))

#: Executable fixtures (F01-F14). F15-F17 are left to the isolated lane or wait for C3/C4.
CASES: dict[str, ArchiveCase] = {
    "F01": ArchiveCase((_reg("a.txt"), _reg("b.txt"), _reg("c.txt"))),
    "F02": ArchiveCase(
        tuple(_dir("/".join(DEEP.split("/")[:i])) for i in range(1, 11)) + (_reg(DEEP + "/f"),)
    ),
    "F03": ArchiveCase((_reg("a.txt"), _hard("b.txt", "a.txt"))),
    "F04": ArchiveCase((_reg("a.txt"), _sym("l", "a.txt"))),
    "F05": ArchiveCase((_reg("a.txt"), _reg("a.txt"))),
    "F06": ArchiveCase((_reg("../escape.txt"),)),
    "F07": ArchiveCase((_reg("../outside/new.txt"),)),
    "F08": ArchiveCase((_reg(SENTINEL),)),
    "F09": ArchiveCase((_hard("alias", SENTINEL),)),
    "F10": ArchiveCase((_hard("alias", SENTINEL), _reg("alias"))),
    "F11": ArchiveCase((_sym("link", SENTINEL),)),
    "F12": ArchiveCase((_sym("link", SENTINEL), _reg("link"))),
    "F13": ArchiveCase((_sym("d", "../outside"), _reg("d/new.txt"))),
    "F14": ArchiveCase((_sym("b", ".."), _sym("a", "b"), _reg("a/escape2.txt"))),
}


def hand_labels(path: Path = LABELS) -> dict[str, tuple[bool, bool, bool]]:
    """``F01 -> (C0, C1, C2)`` from the committed table (rows whose three cells are y/n)."""
    labels = {}
    row = re.compile(r"^\| (F\d\d) \|[^|]*\| ([yn]) \| ([yn]) \| ([yn]) \|")
    for line in path.read_text(encoding="utf-8").splitlines():
        m = row.match(line)
        if m:
            labels[m.group(1)] = tuple(v == "y" for v in m.group(2, 3, 4))
    return labels


class Extractor(Protocol):
    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult: ...


@dataclass
class TruthExtractor:
    """Wrap an extractor; snapshot the sandbox right before and after it runs."""

    inner: Extractor
    found: tuple[bool, bool, bool] | None = field(default=None)

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        sandbox = extraction_root.parent
        before = snapshot(sandbox)
        result = self.inner.run(archive_path, extraction_root)
        self.found = truth(before, snapshot(sandbox))
        return result


def measure(fixture: str, extractor: Extractor) -> dict:
    wrapper = TruthExtractor(extractor)
    result = run_case(CASES[fixture], wrapper)
    oracle = tuple(v.violated for v in result.violations)
    return {
        "status": result.execution.status.value,
        "truth": list(wrapper.found or (False, False, False)),
        "oracle": list(oracle),
    }


def confusion(rows: list[dict], key: str) -> dict[str, dict[str, int]]:
    """Per contract: oracle against ``key`` (``truth`` or ``hand``), counts over these rows."""
    table = {c: {"TP": 0, "FP": 0, "TN": 0, "FN": 0} for c in CONTRACTS}
    for row in rows:
        for i, contract in enumerate(CONTRACTS):
            expected, got = row[key][i], row["oracle"][i]
            cell = ("T" if expected == got else "F") + ("P" if got else "N")
            table[contract][cell] += 1
    return table


def run_all() -> dict:
    hand = hand_labels()
    out: dict = {
        "label": "exploratory (not a registered result)",
        "scope": "F01–F14 (14 of 17). Not scored: F15 (absolute or multi-level paths leave the "
        "sandbox; isolated-run lane), F16 (C3 정의 전), F17 (C4 정의 전).",
        "limitation": "The truth uses the same before/after window as the oracle, so agreement "
        "tests the oracle's comparison logic, not the window limits (C-LIM3: changes that appear "
        "and disappear between snapshots, inode reuse, access outside the sandbox). "
        "이 일치는 창 밖 변화에 대한 정확도를 말하지 않는다.",
        "extractors": {},
    }
    for name, extractor in (
        ("controlled", UncheckedControlledExtractor()),
        ("python-tarfile-data", PolicyExtractor("data")),
    ):
        rows = []
        for fixture in CASES:
            row = {"fixture": fixture, **measure(fixture, extractor)}
            # data filter: attack shapes are expected to be rejected or neutralised (all n)
            row["hand"] = list(hand[fixture]) if name == "controlled" else [False] * 3
            if name != "controlled" and row["status"] == "rejected":
                # all-n because the archive was refused, not an oracle true negative on a
                # harmful write
                row["match_kind"] = "거부 동작 일치"
            rows.append(row)
        out["extractors"][name] = {
            "rows": rows,
            "oracle_vs_truth": confusion(rows, "truth"),
            "hand_vs_truth_mismatches": [r["fixture"] for r in rows if r["hand"] != r["truth"]],
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    report = run_all()
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.json:
        args.json.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

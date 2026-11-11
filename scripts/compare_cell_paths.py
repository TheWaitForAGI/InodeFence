"""Compare cell paths (D047 section 7): report only, never a verdict input; oracle-blind output.

The comparison is the concurrency benchmark's V9 path test
(``analyze_concurrency_benchmark.cell_path`` and ``compare_paths``): per step the ``case_id``, the
``trace_termination`` and a hash of the step's judgement (oracle plus feedback keys), up to the
shorter path (an aborted cell is compared up to its abort). Hashes live in memory only; the output
holds booleans, step indexes and counts, never a case id, a hash or an oracle value.

Two inputs, one tool:

* ``--pair LABEL=HOST1_STEPS,HOST2_STEPS``: the same replicate-v1 cell on both hosts
  (``merge_host_indexes --compare`` builds these);
* ``--rerun HOSTn:LABEL=ORIGINAL_STEPS,RERUN_STEPS``: a host's re-run of a cell against its own
  original run, for the explanation step when the cross-host comparison needs explaining
  (m_x >= 2 or incomparable >= 2).

    python -m scripts.compare_cell_paths --pair 7.5.2-D-s8110=<h1>.steps.jsonl,<h2>.steps.jsonl \\
        [--rerun HOST1:7.5.2-D-s8110=<orig>.steps.jsonl,<rerun>.steps.jsonl ...] --out C.json

Summary: ``m_x`` (comparable cells whose paths differ), ``incomparable`` (a side has no readable
path), ``one_sided_congestion`` (the first differing step is ``timed_out``/``failed`` on one side
only), ``with_reexecutions`` (cells whose report lists infrastructure re-executions; their
differences are flagged apart), ``needs_explanation`` (m_x >= 2 or incomparable >= 2). With re-runs:
per mismatching cell whether it is explained by a host's own nondeterminism (and by which) or is an
unexplained host-dependent difference, plus the HOST1-only and HOST2-only nondeterminism counts.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

STEPS_SUFFIX = ".steps.jsonl"
HOSTS = ("HOST1", "HOST2")


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


def load_path(steps: Path) -> Any:
    """The cell's ``CellPath`` (hashes in memory), or ``None`` when there is no readable path."""
    from scripts.analyze_concurrency_benchmark import cell_path

    if not steps.is_file():
        return None
    records: list[dict[str, Any]] = []
    for line in steps.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            break  # a cut last line ends the comparable path
        if not isinstance(record, dict):
            break
        records.append(record)
    return cell_path(records)


def compare_steps(left: Path, right: Path) -> dict[str, Any]:
    """One pair: comparable, whether the paths differ, the first differing step, congestion."""
    from scripts.analyze_concurrency_benchmark import compare_paths

    first, second = load_path(left), load_path(right)
    if first is None or second is None:
        return {
            "comparable": False,
            "reason": "no readable path on "
            + (
                "both sides"
                if first is None and second is None
                else ("the first side" if first is None else "the second side")
            ),
        }
    difference = compare_paths(first, second)
    return {
        "comparable": True,
        "differs": difference.differs,
        "case_sequence_same": difference.case_sequence_same,
        "judgements_same": difference.verdicts_same,
        "first_differing_step": difference.first_step,
        "one_sided_congestion": difference.one_sided_congestion,
        "compared_steps": min(len(first.case_ids), len(second.case_ids)),
    }


def compare_pairs(
    pairs: Mapping[str, tuple[Path, Path]], sides: tuple[str, str] = HOSTS
) -> dict[str, Any]:
    """Each labelled pair, compared; then the summary counts (D047 section 7)."""
    cells: dict[str, Any] = {}
    for label, (left, right) in sorted(pairs.items()):
        cell = compare_steps(left, right)
        cell["reexecutions"] = {sides[0]: reexecutions(left), sides[1]: reexecutions(right)}
        cells[label] = cell
    comparable = {label: cell for label, cell in cells.items() if cell["comparable"]}
    m_x = sorted(label for label, cell in comparable.items() if cell["differs"])
    incomparable = sorted(set(cells) - set(comparable))
    with_reexecutions = sorted(
        label for label, cell in cells.items() if any(cell["reexecutions"].values())
    )
    return {
        "sides": list(sides),
        "cells": cells,
        "summary": {
            "pairs": len(cells),
            "comparable": len(comparable),
            "identical": len(comparable) - len(m_x),
            "m_x": len(m_x),
            "incomparable": len(incomparable),
            "one_sided_congestion": sum(
                1 for cell in comparable.values() if cell["one_sided_congestion"]
            ),
            "with_reexecutions": with_reexecutions,
            "differing_with_reexecutions": sorted(set(m_x) & set(with_reexecutions)),
            "needs_explanation": len(m_x) >= 2 or len(incomparable) >= 2,
        },
        "differing_cells": m_x,
        "incomparable_cells": incomparable,
    }


def explain(
    compared: Mapping[str, Any], reruns: Mapping[str, Mapping[str, tuple[Path, Path]]]
) -> dict[str, Any]:
    """D047 section 7 step 2: each host's re-run against its own original, per differing cell.

    A cell is explained when at least one host's re-run differs from its own original (host-free
    nondeterminism); it is an unexplained host-dependent difference when both hosts reproduce
    themselves yet differ from each other. A cell without both re-runs stays "not re-run".
    """
    per_cell: dict[str, Any] = {}
    for label in compared["differing_cells"]:
        own: dict[str, bool | None] = {}
        for host in HOSTS:
            pair = reruns.get(host, {}).get(label)
            if pair is None:
                own[host] = None
                continue
            result = compare_steps(*pair)
            own[host] = None if not result["comparable"] else bool(result["differs"])
        if any(value is None for value in own.values()):
            status = "not re-run"
        elif own["HOST1"] or own["HOST2"]:
            status = "explained by nondeterminism"
        else:
            status = "unexplained host-dependent"
        per_cell[label] = {"self_differs": own, "status": status}
    statuses = [cell["status"] for cell in per_cell.values()]
    return {
        "cells": per_cell,
        "unexplained_host_dependent": statuses.count("unexplained host-dependent"),
        "explained": statuses.count("explained by nondeterminism"),
        "not_rerun": statuses.count("not re-run"),
        "host1_only_nondeterminism": sum(
            1 for c in per_cell.values() if c["self_differs"] == {"HOST1": True, "HOST2": False}
        ),
        "host2_only_nondeterminism": sum(
            1 for c in per_cell.values() if c["self_differs"] == {"HOST1": False, "HOST2": True}
        ),
        # D047 section 7 item 3: a held host needs two or more unexplained cells.
        "serious_difference": statuses.count("unexplained host-dependent") >= 2,
    }


def _pair(text: str) -> tuple[str, tuple[Path, Path]]:
    label, sep, rest = text.partition("=")
    left, comma, right = rest.partition(",")
    if not sep or not comma or not label or not left or not right:
        raise argparse.ArgumentTypeError(f"expected LABEL=LEFT,RIGHT, got {text!r}")
    return label, (Path(left), Path(right))


def _rerun(text: str) -> tuple[str, str, tuple[Path, Path]]:
    host, colon, rest = text.partition(":")
    if not colon or host not in HOSTS:
        raise argparse.ArgumentTypeError(f"expected HOSTn:LABEL=ORIGINAL,RERUN, got {text!r}")
    label, pair = _pair(rest)
    return host, label, pair


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--pair", type=_pair, action="append", required=True)
    parser.add_argument("--rerun", type=_rerun, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    pairs = dict(args.pair)
    if len(pairs) != len(args.pair):
        parser.error("each label once")
    reruns: dict[str, dict[str, tuple[Path, Path]]] = {}
    for host, label, pair in args.rerun:
        if label in reruns.setdefault(host, {}):
            parser.error(f"{host}:{label} given twice")
        reruns[host][label] = pair
    compared = compare_pairs(pairs)
    document = {
        "classification": "cell path comparison (D047 section 7): report only, oracle-blind",
        **compared,
        **({"explanation": explain(compared, reruns)} if reruns else {}),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Abort-category roll-up: per-arm, per-reason tally over native-campaign aborts.

Additive analyzer. It imports the shared vocabulary/classifier
(:mod:`inodefence.evaluation.abort_classification`) and re-derives no runtime-lane
determination. It answers "which kind of infrastructure/observer abort, how often,
per arm" from two honest inputs:

1. Native campaign evidence JSONs (e.g. the M4.5 decompress self-discovery raw on
   the experiment host). A campaign is either complete (``config`` present, no
   ``aborted``) or a fail-closed abort stub (``{"aborted": {"reason": ...}}``). The
   stub's ``reason`` is classified with :func:`classify_abort_reason`; this also
   back-fills a ``category`` for stubs written before that field existed.
2. The M3 powered verdict's ``### abort 사유`` markdown table (per-arm counts of
   observer/broker/cleanup reasons), parsed and mapped onto the same vocabulary.

Output keys use the shared ``invalid_reason`` vocabulary so a downstream reader
(e.g. the EXP-0 analyzer) can group by the same field names. The roll-up makes no
rate or effectiveness claim: it is a reason tally, and aborts are excluded from any
hit/eligibility denominator (they are reported in their own counts).
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path

from inodefence.evaluation.abort_classification import InvalidReason, classify_abort_reason

_SCHEMA = 1
# Default arm token in a raw evidence filename, e.g. "...-m45-sa-s504.json" -> "sa".
_DEFAULT_ARM_PATTERN = r"-([A-Za-z0-9]+)-s\d+(?:\.json)?$"


def _empty_counts() -> dict[str, int]:
    return {reason.value: 0 for reason in InvalidReason}


def classify_md_label(label: str) -> InvalidReason:
    """Map an ``abort 사유`` table row label to the shared vocabulary.

    The table labels are human-written summaries, not raw reason strings, so they
    are matched by keyword rather than via :func:`classify_abort_reason`.
    """
    text = label.lower()
    if "evidence integrity" in text or "observer" in text or "observation" in text:
        return InvalidReason.OBSERVER_INTEGRITY
    if "broker" in text:
        return InvalidReason.BROKER
    if "cleanup inspect" in text or "inspect failed" in text:
        return InvalidReason.CLEANUP_INSPECT
    if "remove failed" in text or "removal" in text:
        return InvalidReason.CLEANUP_REMOVE
    if "reset" in text:
        return InvalidReason.CLEANUP_RESET
    return InvalidReason.OTHER


def arm_from_filename(name: str, pattern: str = _DEFAULT_ARM_PATTERN) -> str:
    """Derive an arm label from an evidence filename; fall back to the stem."""
    match = re.search(pattern, name)
    return match.group(1) if match else Path(name).stem


def rollup_raw_json(
    paths: Sequence[str | Path], *, arm_pattern: str = _DEFAULT_ARM_PATTERN
) -> dict[str, dict]:
    """Group raw evidence JSONs by arm and tally completed vs aborted-by-reason.

    An aborted stub's ``reason`` is classified; its ``category`` field (when present)
    is only cross-checked, never trusted over the classifier, so pre-``category``
    stubs and newer stubs roll up identically.
    """
    arms: dict[str, dict] = {}
    for path in paths:
        name = Path(path).name
        arm = arm_from_filename(name, arm_pattern)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        bucket = arms.setdefault(
            arm, {"completed": 0, "aborted_total": 0, "by_invalid_reason": _empty_counts()}
        )
        aborted = data.get("aborted") if isinstance(data, dict) else None
        if isinstance(aborted, dict):
            reason = str(aborted.get("reason", ""))
            category = classify_abort_reason(reason)
            bucket["aborted_total"] += 1
            bucket["by_invalid_reason"][category.value] += 1
        elif isinstance(data, dict) and "config" in data:
            bucket["completed"] += 1
        else:
            # Neither a complete campaign nor a reason-bearing stub: count as an
            # other-category abort so nothing is silently dropped.
            bucket["aborted_total"] += 1
            bucket["by_invalid_reason"][InvalidReason.OTHER.value] += 1
    return arms


def parse_m3_abort_table(md_path: str | Path, *, heading: str = "abort 사유") -> dict[str, dict]:
    """Parse the M3 verdict ``### abort 사유`` table into per-arm reason counts.

    Returns ``{arm: {"completed": None, "aborted_total": int, "by_invalid_reason": {...}}}``.
    ``completed`` is ``None`` because the table records only aborts, not the denominator.
    """
    lines = Path(md_path).read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.lstrip("# ").strip().startswith(heading)),
        None,
    )
    if start is None:
        raise ValueError(f"heading {heading!r} not found in {md_path}")
    # Rows are contiguous after the heading; stop at the first non-table line.
    table: list[list[str]] = []
    for line in lines[start + 1 :]:
        if line.strip().startswith("|"):
            table.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        elif table:
            break
    if len(table) < 2:
        raise ValueError(f"no table under {heading!r} in {md_path}")
    header = table[0]
    arm_names = header[1:]
    arms: dict[str, dict] = {
        arm: {"completed": None, "aborted_total": 0, "by_invalid_reason": _empty_counts()}
        for arm in arm_names
    }
    for row in table[1:]:
        if set("".join(row[0])) <= set("-: "):  # separator row
            continue
        if len(row) != len(header):
            continue
        reason = classify_md_label(row[0])
        for arm, cell in zip(arm_names, row[1:], strict=True):
            count = int(cell) if cell.isdigit() else 0
            arms[arm]["by_invalid_reason"][reason.value] += count
            arms[arm]["aborted_total"] += count
    return arms


def build_rollup(sources: dict[str, dict]) -> dict:
    """Combine named sources into one roll-up with grand totals by reason."""
    totals_by_reason = _empty_counts()
    aborted_total = 0
    for source in sources.values():
        for arm in source["arms"].values():
            for reason, count in arm["by_invalid_reason"].items():
                totals_by_reason[reason] += count
            aborted_total += arm["aborted_total"]
    return {
        "abort_rollup_schema": _SCHEMA,
        "vocabulary": [reason.value for reason in InvalidReason],
        "sources": sources,
        "totals": {"aborted_total": aborted_total, "by_invalid_reason": totals_by_reason},
    }


def render_markdown(rollup: dict) -> str:
    """Human-readable per-arm, per-reason table for each source plus grand totals."""
    reasons = rollup["vocabulary"]
    out: list[str] = ["# Abort category roll-up", ""]
    for source_name, source in rollup["sources"].items():
        out.append(f"## {source_name} ({source['kind']})")
        out.append("")
        out.append("| arm | completed | aborted | " + " | ".join(reasons) + " |")
        out.append("|---|---|---|" + "|".join(["---"] * len(reasons)) + "|")
        for arm_name, arm in source["arms"].items():
            completed = "-" if arm["completed"] is None else str(arm["completed"])
            counts = " | ".join(str(arm["by_invalid_reason"][r]) for r in reasons)
            out.append(f"| {arm_name} | {completed} | {arm['aborted_total']} | {counts} |")
        out.append("")
    totals = rollup["totals"]
    out.append("## totals")
    out.append("")
    out.append("| aborted | " + " | ".join(reasons) + " |")
    out.append("|---|" + "|".join(["---"] * len(reasons)) + "|")
    out.append(
        f"| {totals['aborted_total']} | "
        + " | ".join(str(totals["by_invalid_reason"][r]) for r in reasons)
        + " |"
    )
    out.append("")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw", nargs="*", default=[], help="native evidence JSON paths (globs pre-expanded)"
    )
    parser.add_argument("--raw-name", default="raw_json", help="source name for the --raw group")
    parser.add_argument(
        "--arm-pattern", default=_DEFAULT_ARM_PATTERN, help="regex (1 group) for arm from filename"
    )
    parser.add_argument("--m3-table", type=Path, default=None, help="M3 verdict markdown path")
    parser.add_argument("--json-out", type=Path, default=None, help="write roll-up JSON here")
    parser.add_argument("--md-out", type=Path, default=None, help="write markdown readout here")
    args = parser.parse_args(argv)

    sources: dict[str, dict] = {}
    if args.raw:
        sources[args.raw_name] = {
            "kind": "raw_json",
            "paths": [str(p) for p in args.raw],
            "arms": rollup_raw_json(args.raw, arm_pattern=args.arm_pattern),
        }
    if args.m3_table is not None:
        sources["m3_verdict_table"] = {
            "kind": "m3_verdict_table",
            "paths": [str(args.m3_table)],
            "arms": parse_m3_abort_table(args.m3_table),
        }
    if not sources:
        parser.error("provide --raw and/or --m3-table")

    rollup = build_rollup(sources)
    text = json.dumps(rollup, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if args.json_out is not None:
        args.json_out.write_text(text, encoding="ascii")
    if args.md_out is not None:
        args.md_out.write_text(render_markdown(rollup), encoding="utf-8")
    if args.json_out is None and args.md_out is None:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

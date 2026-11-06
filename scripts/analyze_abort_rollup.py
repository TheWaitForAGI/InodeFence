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
from collections.abc import Callable, Sequence
from pathlib import Path

from inodefence.evaluation.abort_classification import InvalidReason, classify_abort_reason

_SCHEMA = 1
# Default arm token in a raw evidence filename, e.g. "...-m45-sa-s504.json" -> "sa".
_DEFAULT_ARM_PATTERN = r"-([A-Za-z0-9]+)-s\d+(?:\.json)?$"


def _empty_counts() -> dict[str, int]:
    return {reason.value: 0 for reason in InvalidReason}


def _empty_bucket() -> dict:
    """Per-arm tallies: completed campaigns, right-censored aborts, and the third
    ``validity=invalid`` (invalid-continue) bucket, each split by reason."""
    return {
        "completed": 0,
        "aborted_total": 0,
        "by_invalid_reason": _empty_counts(),
        "invalid_total": 0,
        "invalid_by_reason": _empty_counts(),
    }


def _reason_from_value(value: object) -> InvalidReason:
    """A stored ``invalid_reason`` string to the shared enum; unknown -> OTHER."""
    try:
        return InvalidReason(str(value))
    except ValueError:
        return InvalidReason.OTHER


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
    stubs and newer stubs roll up identically. The third ``validity=invalid`` bucket
    is also counted: the worker-pool lane's ``invalid_cases[]`` and the observer lane's
    schema-3 ``steps[].validity=="invalid"`` records, each by their ``invalid_reason``.
    """
    arms: dict[str, dict] = {}
    for path in paths:
        name = Path(path).name
        arm = arm_from_filename(name, arm_pattern)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        bucket = arms.setdefault(arm, _empty_bucket())
        aborted = data.get("aborted") if isinstance(data, dict) else None
        if isinstance(aborted, dict):
            category = classify_abort_reason(str(aborted.get("reason", "")))
            bucket["aborted_total"] += 1
            bucket["by_invalid_reason"][category.value] += 1
        elif isinstance(data, dict) and "config" in data:
            bucket["completed"] += 1
        elif not _has_invalid_records(data):
            # Neither a complete campaign, a reason-bearing stub, nor an invalid
            # record: count as an other-category abort so nothing is silently dropped.
            bucket["aborted_total"] += 1
            bucket["by_invalid_reason"][InvalidReason.OTHER.value] += 1
        _count_invalid_records(data, bucket)
    return arms


def _has_invalid_records(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    if isinstance(data.get("invalid_cases"), list) and data["invalid_cases"]:
        return True
    steps = data.get("steps")
    return isinstance(steps, list) and any(
        isinstance(s, dict) and s.get("validity") == "invalid" for s in steps
    )


def _count_invalid_records(data: object, bucket: dict) -> None:
    """Add ``validity=invalid`` events (invalid_cases[] + schema-3 invalid steps)."""
    if not isinstance(data, dict):
        return
    records = list(data.get("invalid_cases") or [])
    steps = data.get("steps")
    if isinstance(steps, list):
        records.extend(s for s in steps if isinstance(s, dict) and s.get("validity") == "invalid")
    for record in records:
        if isinstance(record, dict):
            reason = _reason_from_value(record.get("invalid_reason"))
            bucket["invalid_total"] += 1
            bucket["invalid_by_reason"][reason.value] += 1


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
    arms: dict[str, dict] = {}
    for arm in arm_names:
        bucket = _empty_bucket()
        bucket["completed"] = None  # the table records only aborts, not the denominator
        arms[arm] = bucket
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


def _g1_cell_reason(cell: dict, base: Path) -> InvalidReason:
    """Resolve an aborted/invalid G1 cell's reason from its summary's ``invalid_reason``.

    Falls back to classifying the cell's campaign ``aborted.reason`` when the summary
    carries no reason, and to OTHER when neither is available.
    """
    summary_rel = cell.get("summary")
    if isinstance(summary_rel, str):
        summary_path = base / summary_rel
        if summary_path.is_file():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if summary.get("invalid_reason") is not None:
                return _reason_from_value(summary["invalid_reason"])
    return InvalidReason.OTHER


def read_g1_index(
    index_path: str | Path, *, reason_resolver: Callable[[dict, Path], InvalidReason] | None = None
) -> dict[str, dict]:
    """Per-arm outcome tally from a G1/EXP-0 ``index.json`` (per-campaign cells).

    Each cell is one campaign with an ``arm`` and mutually exclusive ``complete`` /
    ``aborted`` / ``invalid`` flags. An aborted cell is a right-censored stop; an
    invalid cell is the ``validity=invalid`` invalid-continue bucket. Reasons for
    aborted/invalid cells come from ``reason_resolver`` (default: the cell summary's
    ``invalid_reason``). An all-complete smoke index yields all-zero reason buckets.
    """
    resolve = reason_resolver or _g1_cell_reason
    base = Path(index_path).parent
    data = json.loads(Path(index_path).read_text(encoding="utf-8"))
    arms: dict[str, dict] = {}
    for cell in data.get("cells", []):
        bucket = arms.setdefault(str(cell["arm"]), _empty_bucket())
        if cell.get("aborted"):
            bucket["aborted_total"] += 1
            bucket["by_invalid_reason"][resolve(cell, base).value] += 1
        elif cell.get("invalid"):
            bucket["invalid_total"] += 1
            bucket["invalid_by_reason"][resolve(cell, base).value] += 1
        elif cell.get("complete"):
            bucket["completed"] += 1
    return arms


def build_contingency(arms: dict[str, dict], *, arm_order: Sequence[str] | None = None) -> dict:
    """Arm x reason contingency for an independence test (owned downstream by lane 6).

    ``arms`` is one source's ``{arm: bucket}`` (e.g. from :func:`read_g1_index`). Emits
    a per-campaign matrix (arms x [complete, aborted, invalid]) and a per-event-reason
    split (arms x the shared reason vocabulary, separately for aborted and invalid), so
    the downstream test can collapse to whatever table it needs. Column order is the
    ``InvalidReason`` enum order. Per-campaign ``complete`` counts require a known
    denominator; a source with ``completed = None`` (e.g. the M3 table) reports
    ``complete`` as 0 and only the reason split is meaningful.
    """
    reasons = [reason.value for reason in InvalidReason]
    names = list(arm_order) if arm_order is not None else list(arms)

    def row_abort(arm: dict) -> list[int]:
        return [arm["by_invalid_reason"][r] for r in reasons]

    def row_invalid(arm: dict) -> list[int]:
        return [arm["invalid_by_reason"][r] for r in reasons]

    per_campaign = [
        [
            (arms[n]["completed"] or 0),
            arms[n]["aborted_total"],
            arms[n]["invalid_total"],
        ]
        for n in names
    ]
    aborted_matrix = [row_abort(arms[n]) for n in names]
    invalid_matrix = [row_invalid(arms[n]) for n in names]
    grand = sum(sum(row) for row in aborted_matrix) + sum(sum(row) for row in invalid_matrix)
    return {
        "abort_contingency_schema": 1,
        "arms": names,
        "reasons": reasons,
        # The independence / informative-censoring test's input is the per-campaign
        # disposition table (campaign = independent unit). Agreed with lane 6.
        "primary_test_input": "per_campaign",
        "per_campaign": {
            "columns": ["complete", "aborted", "invalid"],
            "matrix": per_campaign,
            "unit": "campaign",
        },
        "per_event_reason": {
            "columns": reasons,
            "aborted": aborted_matrix,
            "invalid": invalid_matrix,
            # Descriptive only, NOT an independence-test input: per-event reasons
            # within one campaign share corpus/retention and are correlated, which
            # would violate the chi-square/Fisher independence assumption (lane 6).
            "note": "descriptive; not an independence-test input (correlated within-campaign)",
        },
        "totals": {
            "per_campaign_row_totals": [sum(row) for row in per_campaign],
            "aborted_grand": sum(sum(row) for row in aborted_matrix),
            "invalid_grand": sum(sum(row) for row in invalid_matrix),
            "event_grand_total": grand,
        },
    }


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
    parser.add_argument(
        "--g1-index", type=Path, default=None, help="G1/EXP-0 index.json (per-campaign cells)"
    )
    parser.add_argument(
        "--g1-name", default="g1_index", help="source name for the --g1-index group"
    )
    parser.add_argument("--json-out", type=Path, default=None, help="write roll-up JSON here")
    parser.add_argument("--md-out", type=Path, default=None, help="write markdown readout here")
    parser.add_argument(
        "--contingency-out",
        type=Path,
        default=None,
        help="write the arm x reason contingency JSON here (prefers the G1 source, else --raw)",
    )
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
    if args.g1_index is not None:
        sources[args.g1_name] = {
            "kind": "g1_index",
            "paths": [str(args.g1_index)],
            "arms": read_g1_index(args.g1_index),
        }
    if not sources:
        parser.error("provide --raw, --m3-table and/or --g1-index")

    rollup = build_rollup(sources)
    text = json.dumps(rollup, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if args.json_out is not None:
        args.json_out.write_text(text, encoding="ascii")
    if args.md_out is not None:
        args.md_out.write_text(render_markdown(rollup), encoding="utf-8")
    if args.contingency_out is not None:
        contingency_source = sources.get(args.g1_name) or sources.get(args.raw_name)
        if contingency_source is None:
            parser.error("--contingency-out needs --g1-index or --raw")
        contingency = build_contingency(contingency_source["arms"])
        args.contingency_out.write_text(
            json.dumps(contingency, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="ascii",
        )
    if args.json_out is None and args.md_out is None and args.contingency_out is None:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

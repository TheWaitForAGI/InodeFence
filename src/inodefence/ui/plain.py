"""Plain-text result lines: standard library only (no Rich), for pipes, files, default install.

The Rich screens are in :mod:`inodefence.ui.results`. Both read the same ``app.runs`` models
and use the same words; a value the file does not hold is ``?``. "same" only when both recorded
SHA-256 values are equal.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from inodefence.app.runs import ReadState, RunSummary

UNKNOWN = "?"


def short(value: str | None, size: int = 12) -> str:
    if not value:
        return UNKNOWN
    return value if len(value) <= size else value[:size] + "…"


def identity(summary: RunSummary) -> tuple[str | None, str | None]:
    ref = summary.ref
    return (ref.target, ref.version) if ref is not None else (None, None)


def side_title(summary: RunSummary) -> str:
    target, version = identity(summary)
    return " ".join(p for p in (target, version) if p) or str(summary.result_path or UNKNOWN)


def mark(value: bool | None) -> str:
    """A contract: ``V`` violated, ``-`` held, ``?`` not judged."""
    return "V" if value is True else "-" if value is False else UNKNOWN


def same_word(row: Any) -> tuple[str, str]:
    """``(word, tone)`` for a compared case's input: same / different / unknown / one side."""
    if not row.in_a:
        return "only in B", "warn"
    if not row.in_b:
        return "only in A", "warn"
    if row.same_input is True:
        return "✓ same", "ok"
    if row.same_input is False:
        return "✗ different", "bad"
    return f"{UNKNOWN} unknown", "warn"


def unknown_reason(rows: Sequence[Any]) -> str:
    """Why the unknown cases are not called the same input (either side or one side)."""
    unknown = [r for r in rows if r.in_a and r.in_b and r.same_input is None]
    neither = sum(1 for r in unknown if not r.tar_sha256_a and not r.tar_sha256_b)
    parts = []
    if neither:
        parts.append(f"{neither} with no recorded SHA-256 on either side")
    if len(unknown) - neither:
        parts.append(f"{len(unknown) - neither} with a recorded SHA-256 on one side only")
    return "; ".join(parts)


def verdict_line(row: Any) -> str:
    if row is None:
        return "—"
    marks = " ".join(mark(v) for v in row.contracts.values())
    return f"{row.outcome or row.termination.value} {marks}"


def compare_lines(a: RunSummary, b: RunSummary, rows: Sequence[Any]) -> list[str]:
    """The comparison as plain text: one line per case."""
    lines = [f"A: {side_title(a)}  {a.result_path}", f"B: {side_title(b)}  {b.result_path}"]
    for side, summary in (("A", a), ("B", b)):
        if not summary.has_values:
            lines.append(f"{side}: result {summary.read_state.value}: {summary.error}")
            return lines
        if summary.read_state is ReadState.UNVALIDATED:
            lines.append(f"{side}: as stored, not validated: {summary.error}")
    verdict_a = a.verdict.value if a.verdict else UNKNOWN
    verdict_b = b.verdict.value if b.verdict else UNKNOWN
    lines.append(f"verdict: A {verdict_a}  B {verdict_b}")
    lines.append(f"{'case':24} {'input':12} {'sha256 A':14} {'sha256 B':14} {'A (C0 C1 C2)':18} B")
    for row in rows:
        lines.append(
            f"{row.case_id:24} {same_word(row)[0]:12} {short(row.tar_sha256_a):14} "
            f"{short(row.tar_sha256_b):14} {verdict_line(row.a):18} {verdict_line(row.b)}"
        )
    reason = unknown_reason(rows)
    if reason:
        lines.append(f"unknown input (not called the same): {reason}")
    return lines

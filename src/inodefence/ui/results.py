"""Result screens drawn from the shared read models (:mod:`inodefence.app.runs`).

Every value comes from a result file through ``app.runs``; a value the file does not hold is
shown as ``?`` or the cell is left out -- never invented. A result the strict reader refused is
shown with an "as stored" chip and the reader's reason, never like a validated one. Contracts:
``V`` violated (red), ``-`` held (grey), ``?`` not judged (amber).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from inodefence.app.runs import ReadState, RunSummary
from inodefence.ui import components as ui

UNKNOWN = "?"


def _contract(value: bool | None) -> Text:
    if value is True:
        return Text("V", style="bold if.bad")
    if value is False:
        return Text("-", style="if.muted")
    return Text(UNKNOWN, style="if.warn")


def _short(value: str | None, size: int = 12) -> str:
    if not value:
        return UNKNOWN
    return value if len(value) <= size else value[:size] + "…"


def _identity(summary: RunSummary) -> tuple[str | None, str | None]:
    ref = summary.ref
    return (ref.target, ref.version) if ref is not None else (None, None)


def _subject(summary: RunSummary) -> str:
    target, version = _identity(summary)
    parts = [" ".join(p for p in (target, version) if p)] if target or version else []
    if summary.ref is not None and summary.ref.run_id:
        parts.append(f"cell {summary.ref.run_id}")
    return "  ·  ".join(parts) or "result"


def _key_values(rows: Sequence[tuple[str, RenderableType]]) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="if.label", no_wrap=True)
    table.add_column(overflow="fold")
    for key, value in rows:
        table.add_row(key, value)
    return table


def no_result_panel(text: str) -> RenderableType:
    return ui.result_panel("UNKNOWN", "No result to show", [text])


def _unreadable(summary: RunSummary) -> RenderableType:
    state = summary.read_state.value.replace("_", " ")
    return ui.result_panel(
        "ERROR",
        f"result {state}",
        [str(summary.result_path or UNKNOWN), summary.error or ""],
    )


def _as_stored_line(summary: RunSummary) -> list[Text]:
    if summary.read_state is not ReadState.UNVALIDATED:
        return []
    line = ui.chip("as stored")
    line.append("  not validated — the values below are the file's, as stored: ", style="if.warn")
    line.append(summary.error or UNKNOWN)
    return [line]


def verify_screen(summary: RunSummary, *, version: str) -> list[RenderableType]:
    """A verify cell: header, cards, cases, evidence, result. Only what the file holds."""
    out: list[RenderableType] = [ui.header("verify", version=version, subject=_subject(summary))]
    if not summary.has_values:
        return [*out, _unreadable(summary)]
    out += _as_stored_line(summary)
    cases = summary.cases
    total = len(cases)
    violating = sum(1 for case in cases if case.violated)
    verdict = summary.verdict.value if summary.verdict is not None else UNKNOWN
    cards = [
        ("verdict", verdict, ui.theme.tone(verdict) if summary.verdict else "warn"),
        ("violating", f"{violating}/{total}", "bad" if violating else "ok"),
    ]
    if summary.errored is not None:
        cards.append(("errored", str(summary.errored), "bad" if summary.errored else "muted"))
    if summary.observed_contracts:
        cards.append(("contracts", " ".join(summary.observed_contracts), "plain"))
    out.append(ui.cards(cards))
    if total:
        out.append(ui.bars([("cases violating", violating, total, "bad")]))
    rows = [
        [
            Text(case.case_id, style="bold"),
            Text(_short(case.tar_sha256), style="if.muted"),
            Text(case.outcome or case.termination.value),
            _contract(case.c0),
            _contract(case.c1),
            _contract(case.c2),
            Text(case.judgment.value.replace("_", " "), style="if.label"),
        ]
        for case in cases
    ]
    table = ui.data_table(
        [
            ("case", "left"),
            ("input SHA-256", "left"),
            ("outcome", "left"),
            ("C0", "center"),
            ("C1", "center"),
            ("C2", "center"),
            ("", "left"),
        ],
        rows,
    )
    out.append(ui.section("Cases", table, subtitle=None))
    evidence: list[tuple[str, RenderableType]] = [
        ("result", Text(str(summary.result_path or UNKNOWN)))
    ]
    integrity = summary.integrity
    if integrity is not None:
        if integrity.inputs:
            folder = Path(integrity.inputs[0][2]).parent
            evidence.append(("inputs", Text(f"{folder}  ({len(integrity.inputs)} saved, SHA-256)")))
        if integrity.image_id:
            evidence.append(("image", Text(_short(integrity.image_id, 19))))
        if integrity.engine_sha:
            dirty = " (dirty tree)" if integrity.engine_dirty else ""
            evidence.append(("engine", Text(_short(integrity.engine_sha) + dirty)))
    if summary.benign_control:
        control = ", ".join(f"{k}={v}" for k, v in sorted(summary.benign_control.items()))
        evidence.append(("benign control", Text(control)))
    if summary.label:
        evidence.append(("label", Text(summary.label, style="if.label")))
    out.append(ui.section("Evidence", _key_values(evidence)))
    target, ver = _identity(summary)
    title = " ".join(p for p in (target, ver) if p) or "verify"
    lines: list[str | Text] = [f"{violating} of {total} cases violated a contract"]
    steps = []
    if summary.result_path is not None:
        steps.append(f"inodefence summary {summary.result_path}")
        steps.append(f"inodefence compare {summary.result_path} <another version's result.json>")
    out.append(
        ui.result_panel(verdict if summary.verdict else "UNKNOWN", title, lines, next_steps=steps)
    )
    return out


def _same(same: bool | None, in_a: bool, in_b: bool) -> Text:
    if not in_a:
        return Text("only in B", style="if.warn")
    if not in_b:
        return Text("only in A", style="if.warn")
    if same is True:
        return ui.flag(True, "same")
    if same is False:
        return Text("✗ different", style="if.bad")
    return Text(f"{UNKNOWN} unknown", style="if.warn")


def _side_title(summary: RunSummary) -> str:
    target, version = _identity(summary)
    return " ".join(p for p in (target, version) if p) or str(summary.result_path or UNKNOWN)


def _where(summary: RunSummary) -> Text:
    """``target version  path`` (target and version only when the result names them)."""
    target, version = _identity(summary)
    text = Text(" ".join(p for p in (target, version) if p), style="bold")
    if text.plain:
        text.append("  ")
    text.append(str(summary.result_path or UNKNOWN), style="if.label")
    return text


def _verdict_cell(row: Any) -> Text:
    if row is None:
        return Text("—", style="if.muted")
    marks = "".join(
        "V" if v is True else "-" if v is False else UNKNOWN for v in row.contracts.values()
    )
    style = "bold if.bad" if row.violated else "if.muted"
    return Text(f"{row.outcome or row.termination.value}  {marks}", style=style)


def compare_screen(
    a: RunSummary, b: RunSummary, rows: Sequence[Any], *, version: str
) -> list[RenderableType]:
    out: list[RenderableType] = [
        ui.header("compare", version=version, subject="two results, case by case"),
        _key_values(
            [
                ("A", _where(a)),
                ("B", _where(b)),
            ]
        ),
    ]
    for side, summary in (("A", a), ("B", b)):
        if not summary.has_values:
            return [*out, _unreadable(summary)]
        for line in _as_stored_line(summary):
            line.append(f"  ({side})")
            out.append(line)
    same = sum(1 for row in rows if row.same_input is True)
    different = sum(1 for row in rows if row.same_input is False)
    one_side = sum(1 for row in rows if not (row.in_a and row.in_b))
    unknown = len(rows) - same - different - one_side
    out.append(
        ui.cards(
            [
                ("same input", f"{same}/{len(rows)}", "ok" if same == len(rows) else "plain"),
                ("different input", str(different), "bad" if different else "muted"),
                ("only one side", str(one_side), "warn" if one_side else "muted"),
                ("input unknown", str(unknown), "warn" if unknown else "muted"),
            ]
        )
    )
    verdict_a = a.verdict.value if a.verdict else UNKNOWN
    verdict_b = b.verdict.value if b.verdict else UNKNOWN
    table = ui.data_table(
        [
            ("case", "left"),
            ("input", "left"),
            ("SHA-256 A", "left"),
            ("SHA-256 B", "left"),
            ("A", "left"),
            ("B", "left"),
        ],
        (
            [
                Text(row.case_id, style="bold"),
                _same(row.same_input, row.in_a, row.in_b),
                Text(_short(row.tar_sha256_a), style="if.muted"),
                Text(_short(row.tar_sha256_b), style="if.muted"),
                _verdict_cell(row.a),
                _verdict_cell(row.b),
            ]
            for row in rows
        ),
    )
    out.append(ui.section("Cases (C0 C1 C2: V violated · - held · ? not judged)", table))
    status = "PASS" if different == 0 and one_side == 0 and unknown == 0 else "WARN"
    lines: list[str | Text] = [
        Text.assemble("verdict  A ", ui.chip(verdict_a), "   B ", ui.chip(verdict_b)),
        f"{same} of {len(rows)} cases ran the same input (recorded SHA-256 equal on both sides)",
    ]
    if different:
        lines.append(Text(f"{different} case(s): a different input", style="if.bad"))
    if one_side:
        lines.append(Text(f"{one_side} case(s): in one result only", style="if.warn"))
    if unknown:
        lines.append(
            Text(
                f"{unknown} case(s): unknown — no recorded SHA-256 on one side, so not called "
                "the same input",
                style="if.warn",
            )
        )
    title = "Same inputs, two results" if status == "PASS" else "Not every input is shown same"
    out.append(ui.result_panel(status, title, lines))
    return out


def compare_plain_lines(a: RunSummary, b: RunSummary, rows: Sequence[Any]) -> list[str]:
    """The comparison as plain text (pipes, files, no Rich): one line per case."""
    lines = [f"A: {_side_title(a)}  {a.result_path}", f"B: {_side_title(b)}  {b.result_path}"]
    for side, summary in (("A", a), ("B", b)):
        if not summary.has_values:
            lines.append(f"{side}: result {summary.read_state.value}: {summary.error}")
            return lines
        if summary.read_state is ReadState.UNVALIDATED:
            lines.append(f"{side}: as stored, not validated: {summary.error}")
    verdict_a = a.verdict.value if a.verdict else UNKNOWN
    verdict_b = b.verdict.value if b.verdict else UNKNOWN
    lines.append(f"verdict: A {verdict_a}  B {verdict_b}")
    lines.append(f"{'case':24} {'input':10} {'sha256 A':14} {'sha256 B':14} {'A':14} B")
    for row in rows:
        same = _same(row.same_input, row.in_a, row.in_b).plain
        lines.append(
            f"{row.case_id:24} {same:10} {_short(row.tar_sha256_a):14} "
            f"{_short(row.tar_sha256_b):14} {_verdict_cell(row.a).plain:14} "
            f"{_verdict_cell(row.b).plain}"
        )
    return lines

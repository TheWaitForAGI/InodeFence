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

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from inodefence.app.runs import ReadState, RunSummary
from inodefence.ui import components as ui
from inodefence.ui.plain import UNKNOWN, identity, same_word, side_title, unknown_reason
from inodefence.ui.plain import short as _short


def _contract(value: bool | None) -> Text:
    if value is True:
        mark = Text("V", style="if.bad")  # a theme name cannot be combined in one style string
        mark.stylize("bold")
        return mark
    if value is False:
        return Text("-", style="if.muted")
    return Text(UNKNOWN, style="if.warn")


_identity = identity


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
            ("judgment", "left"),
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
            evidence.append(("engine commit", Text(_short(integrity.engine_sha) + dirty)))
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


def _same(row: Any) -> Text:
    word, tone = same_word(row)
    return Text(word, style=f"if.{tone}")


_side_title = side_title


def _where(summary: RunSummary) -> Text:
    """``target version  path`` (target and version only when the result names them)."""
    target, version = _identity(summary)
    text = Text(" ".join(p for p in (target, version) if p), style="bold")
    if text.plain:
        text.append("  ")
    text.append(str(summary.result_path or UNKNOWN), style="if.label")
    return text


def _verdict_cell(row: Any) -> Text:
    """``outcome`` over ``C0 C1 C2``, each mark in its own colour (V red, - grey, ? amber)."""
    if row is None:
        return Text("—", style="if.muted")
    # outcome on the first line, the three marks under it: never cropped at a narrow width
    text = Text(f"{row.outcome or row.termination.value}\n", style="bold" if row.violated else "")
    for number, value in enumerate(row.contracts.values()):
        if number:
            text.append(" ")
        text.append_text(_contract(value))
    return text


def _side_heading(side: str, summary: RunSummary) -> str:
    _, version = _identity(summary)
    return f"{side} · {version}" if version else side


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
            (_side_heading("A", a), "left"),
            (_side_heading("B", b), "left"),
        ],
        (
            [
                Text(row.case_id, style="bold"),
                _same(row),
                Text(_short(row.tar_sha256_a), style="if.muted"),
                Text(_short(row.tar_sha256_b), style="if.muted"),
                _verdict_cell(row.a),
                _verdict_cell(row.b),
            ]
            for row in rows
        ),
    )
    out.append(ui.section("Cases (C0 C1 C2: V violated · - held · ? not judged)", table))
    # The panel is about the inputs, not a verdict: PASS/FAIL words and the green chip belong to
    # verdicts only (shown on the line below), so the comparison uses neutral words.
    all_same = different == 0 and one_side == 0 and unknown == 0 and bool(rows)
    status = "INFO" if all_same else "PARTIAL"
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
            Text(f"unknown, so not called the same input: {unknown_reason(rows)}", style="if.warn")
        )
    title = f"Same inputs · {same} of {len(rows)}"
    out.append(ui.result_panel(status, title, lines))
    return out


_CONCLUSION_STATUS = {
    # the chip says what the replay found, not whether the command "failed"
    "reproduced_violation": "REPRODUCED",
    "partially_reproduced": "PARTIAL",
    "new_violation": "VIOLATION",
    "not_reproduced": "NONE",
    "no_violation": "NONE",
    "unjudged": "UNJUDGED",
    "infrastructure_failure": "RUN ERROR",
    "no_rounds": "INCOMPLETE",
}


def _count(value: int | None, total: int | None) -> str:
    """``n/m`` from stored counts; ``?`` for a count the record does not hold."""
    return f"{UNKNOWN if value is None else value}/{UNKNOWN if total is None else total}"


def replay_screen(record: Any, *, version: str) -> list[RenderableType]:
    """A replay record (``app.runs.ReplayRecord``): rounds, agreement, conclusion.

    Agreement is over the rounds the oracle judged (the record's own denominator), never over
    the rounds run: 2 judged of 3 run reads ``2/2`` with ``1 not judged``, never ``3/3``."""
    subject = record.original_case_id or record.path.parent.name
    out: list[RenderableType] = [ui.header("replay", version=version, subject=subject)]
    if record.read_state not in (ReadState.OK, ReadState.UNVALIDATED):
        state = record.read_state.value.replace("_", " ")
        return [
            *out,
            ui.result_panel("ERROR", f"replay {state}", [str(record.path), record.error or ""]),
        ]
    if record.read_state is ReadState.UNVALIDATED:
        line = ui.chip("as stored")
        line.append(
            "  not validated — the values below are the file's, as stored: ", style="if.warn"
        )
        line.append(record.error or UNKNOWN)
        out.append(line)
    conclusion = record.conclusion.value if record.conclusion is not None else None
    status = _CONCLUSION_STATUS.get(conclusion or "", "UNKNOWN")
    every = (
        record.judged is not None and record.same_contracts == record.judged and record.judged > 0
    )
    out.append(
        ui.cards(
            [
                ("rounds run", _count(record.rounds_done, record.rounds_requested), "plain"),
                ("judged", _count(record.judged, record.rounds_done), "plain"),
                (
                    "same contracts",
                    _count(record.same_contracts, record.judged),
                    "ok" if every else "plain",
                ),
                ("same fingerprint", _count(record.same_fingerprints, record.judged), "plain"),
            ]
        )
    )
    rows = [
        [
            Text(UNKNOWN if r.round is None else str(r.round), style="bold"),
            Text(r.outcome or r.termination or UNKNOWN),
            _contract(r.c0),
            _contract(r.c1),
            _contract(r.c2),
            Text((r.classification or UNKNOWN).replace("_", " "), style="if.label"),
            Text(r.reason or "", style="if.muted"),
        ]
        for r in record.rounds
    ]
    if rows:
        table = ui.data_table(
            [
                ("round", "left"),
                ("outcome", "left"),
                ("C0", "center"),
                ("C1", "center"),
                ("C2", "center"),
                ("class", "left"),
                ("note", "left"),
            ],
            rows,
        )
        out.append(ui.section("Rounds (C0 C1 C2: V violated · - held · ? not judged)", table))
    evidence: list[tuple[str, RenderableType]] = [("replay", Text(str(record.path)))]
    if record.original_tar_sha256:
        evidence.append(("input SHA-256", Text(_short(record.original_tar_sha256, 19))))
    if record.image_id:
        evidence.append(("image", Text(_short(record.image_id, 19))))
    if record.engine_differs:
        evidence.append(("engine commit", Text("differs from the original run", style="if.warn")))
    out.append(ui.section("Evidence", _key_values(evidence)))
    lines: list[str | Text] = [
        f"same contracts in {_count(record.same_contracts, record.judged)} judged rounds"
    ]
    if record.unjudged:
        lines.append(
            Text(
                f"{record.unjudged} round(s) not judged — not counted as agreeing", style="if.warn"
            )
        )
    if record.complete is False:
        reason = f": {record.stop_reason}" if record.stop_reason else ""
        lines.append(Text(f"replay incomplete{reason} (finished rounds are kept)", style="if.warn"))
    title = (conclusion or "no conclusion recorded").replace("_", " ")
    out.append(ui.result_panel(status, title, lines))
    return out


def status_screen(
    folder: Any, live: Sequence[str], rows: Sequence[Any], *, version: str
) -> list[RenderableType]:
    """``inodefence status``: the live blocks as the live view wrote them, then the results."""
    out: list[RenderableType] = [ui.header("status", version=version, subject=str(folder))]
    for block in live:
        out.append(ui.section("Live (running or stopped before result.json)", Text(block)))
    if not rows:
        return out
    verdicts = [str(row.get("verdict")) for row in rows]
    out.append(
        ui.cards(
            [
                ("results", str(len(rows)), "plain"),
                ("PASS", str(verdicts.count("PASS")), "ok" if "PASS" in verdicts else "muted"),
                ("FAIL", str(verdicts.count("FAIL")), "bad" if "FAIL" in verdicts else "muted"),
                ("ERROR", str(verdicts.count("ERROR")), "bad" if "ERROR" in verdicts else "muted"),
                (
                    "unreadable",
                    str(verdicts.count("UNREADABLE")),
                    "warn" if "UNREADABLE" in verdicts else "muted",
                ),
            ]
        )
    )

    def cell(value: Any) -> Text:
        return Text(UNKNOWN if value is None else str(value))

    def note(row: Any) -> str:
        return str(
            row.get("error")
            or row.get("warning")
            or ("stopped early" if row.get("stopped_early") else "")
        )

    # "first at" is an exploration value; a verify result has none, so the column is drawn only
    # when some result is an exploration (and then a missing value is "—")
    with_first = any(row.get("explore") for row in rows)
    columns = [
        ("result", "left"),
        ("verdict", "left"),
        ("target", "left"),
        ("runs", "right"),
        ("violations", "right"),
    ]
    if with_first:
        columns.append(("first at", "right"))
    table_rows = []
    for row in rows:
        target = " ".join(str(row[k]) for k in ("target", "version") if row.get(k))
        line = [
            Text(str(row["cell"]), style="bold"),
            ui.chip(str(row["verdict"])),
            Text(target or UNKNOWN),
            cell(row.get("runs")),
            Text(
                str(row.get("violations", UNKNOWN)), style="if.bad" if row.get("violations") else ""
            ),
        ]
        if with_first:
            line.append(Text("—" if row.get("first") is None else str(row["first"])))
        table_rows.append(line)
    table = ui.data_table(columns, table_rows, keep=tuple(range(len(columns))))
    # notes (an unreadable file's reason, a warning) go under the table, one line each, so a
    # long reason never squeezes the columns
    notes = [
        Text.assemble((f"{row['cell']}: ", "bold"), (note(row), "if.warn"))
        for row in rows
        if note(row)
    ]
    out.append(ui.section("Results", Group(table, *notes) if notes else table))
    return out

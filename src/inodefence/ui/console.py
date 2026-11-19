"""Terminal drawing for ``inodefence``: Rich on an interactive terminal, else plain text.

Two renderers draw the same data (:mod:`inodefence.app`):

- **plain** (standard library): fixed columns, values wrapped in their own column, the next step
  on its own line after an arrow, colour on the status tag only and only on a terminal. This is
  what a pipe, a file, ``NO_COLOR``, ``TERM=dumb`` or an install without Rich gets -- no escape
  code is ever written there.
- **rich** (optional extra ``inodefence[ui]``): used only when Rich imports *and* stdout is an
  interactive terminal *and* neither ``NO_COLOR`` nor ``TERM=dumb`` is set. Restrained on purpose:
  no box borders around items, colour on the status tag only.

Machine output (``targets --json``, ``result.json``, ``summary``'s markdown) never goes through
here; the commands write it directly so it is byte-identical with or without Rich.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TextIO

from inodefence.app.doctor import Item

#: Layout of a plain doctor line: the status column (``[UNKNOWN]`` and a space) and the item-name
#: column (the longest item name, 22, and two spaces).
STATUS_WIDTH = 10
LABEL_WIDTH = 24
#: Width used when stdout is not a terminal (a pipe or a file), so captured output is stable.
PIPE_WIDTH = 100
_ANSI = {"OK": "32", "WARN": "33", "FAIL": "31", "UNKNOWN": "2", "INFO": "2"}
_RICH_STYLE = {"OK": "green", "WARN": "yellow", "FAIL": "red", "UNKNOWN": "dim", "INFO": "dim"}


def rich_module() -> Any | None:
    """The ``rich`` package if it imports, else ``None`` (the optional ``ui`` extra)."""
    try:
        import rich  # noqa: F401
        import rich.console
        import rich.table
    except ImportError:
        return None
    return rich


def interactive(stream: TextIO, environ: Mapping[str, str] | None = None) -> bool:
    """A terminal a person reads: a TTY, ``TERM`` not ``dumb``, and no ``NO_COLOR``."""
    env = os.environ if environ is None else environ
    try:
        tty = stream.isatty()
    except (AttributeError, ValueError):
        return False
    return tty and env.get("TERM") != "dumb" and "NO_COLOR" not in env


@dataclass
class View:
    """How plain lines are drawn: width, whether the status tag is coloured, and the glyphs."""

    width: int = PIPE_WIDTH
    color: bool = False
    arrow: str = "->"
    dot: str = ","

    @classmethod
    def for_stream(cls, stream: TextIO) -> View:
        tty = stream.isatty()
        width = shutil.get_terminal_size((PIPE_WIDTH, 24)).columns if tty else PIPE_WIDTH
        try:
            "→·".encode(getattr(stream, "encoding", None) or "ascii")
            arrow, dot = "→", "·"
        except (LookupError, UnicodeEncodeError):
            arrow, dot = "->", ","
        return cls(width=max(width, 40), color=interactive(stream), arrow=arrow, dot=dot)


def _wrap(text: str, width: int, continuation: str = "") -> list[str]:
    return textwrap.wrap(
        text,
        width=max(width, 10),
        subsequent_indent=continuation,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [""]


def pack(parts: Sequence[str], separator: str, width: int) -> list[str]:
    """``parts`` joined by ``separator``, a new line only between parts (not inside one)."""
    lines: list[str] = []
    for part in parts:
        if lines and len(lines[-1]) + len(separator) + len(part) <= width:
            lines[-1] += separator + part
        else:
            lines.append(part)
    return lines


def plain_item_lines(item: Item, view: View) -> list[str]:
    """One doctor item as plain lines: status and name in fixed columns, the rest wrapped in the
    value column, each hint on its own line after an arrow. No line is longer than the width."""
    tag = f"[{item.status}]"
    shown = f"\x1b[{_ANSI.get(item.status, '0')}m{tag}\x1b[0m" if view.color else tag
    pad = " " * (STATUS_WIDTH - len(tag))
    indent = " " * (STATUS_WIDTH + LABEL_WIDTH)
    value_width = view.width - len(indent)
    values = _wrap(item.value, value_width)
    values += pack(item.parts, f" {view.dot} ", value_width) if item.parts else []
    values += [line for text in item.more for line in _wrap(text, value_width)]
    for hint in item.hints:
        values += _wrap(f"{view.arrow} {hint}", value_width, continuation="  ")
    lines: list[str] = []
    if len(item.label) <= LABEL_WIDTH - 2:  # two spaces at least between the name and the value
        lines.append(f"{shown}{pad}{item.label.ljust(LABEL_WIDTH)}{values[0]}".rstrip())
        values = values[1:]
    else:
        label_lines = _wrap(item.label, view.width - STATUS_WIDTH)
        lines.append(f"{shown}{pad}{label_lines[0]}")
        lines += [f"{' ' * STATUS_WIDTH}{line}" for line in label_lines[1:]]
    lines += [f"{indent}{line}".rstrip() for line in values]
    return lines


class Console:
    """Where a command's human-readable output goes; picks Rich or plain once, per stream."""

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        rich: Any | None = None,
        version: str = "",
        width: int | None = None,
    ) -> None:
        self.stream = sys.stdout if stream is None else stream
        self.view = View.for_stream(self.stream)
        self.version = version
        module = rich if rich is not None else rich_module()
        self._rich: Any = None
        if module is not None and interactive(self.stream):
            from rich.console import Console as RichConsole

            from inodefence.ui import theme

            self._rich = RichConsole(
                file=self.stream,
                highlight=False,
                soft_wrap=False,
                theme=theme.rich_theme(),
                width=width,
            )

    @property
    def uses_rich(self) -> bool:
        return self._rich is not None

    def line(self, text: str = "") -> None:
        """A plain line, identical in both renderers (summaries, notes)."""
        print(text, file=self.stream)

    def _print(self, *renderables: Any) -> None:
        assert self._rich is not None
        for renderable in renderables:
            self._rich.print(renderable)

    # -- doctor ------------------------------------------------------------------------------

    def doctor(self, report: Any) -> None:
        """``report``: :class:`inodefence.app.doctor.Report`."""
        if self._rich is None:
            for item in report.items:
                for line in plain_item_lines(item, self.view):
                    print(line, file=self.stream)
            self.line()
            self.line(report.summary)
            return
        self._rich_doctor(report)

    def _rich_doctor(self, report: Any) -> None:
        from inodefence.app.doctor import SECTIONS
        from inodefence.ui import components as ui

        items = report.items
        self._print(
            ui.header("doctor", version=self.version, subject=f"{len(items)} checks"),
            "",
        )
        tones = {"OK": "ok", "WARN": "warn", "FAIL": "bad", "UNKNOWN": "warn", "INFO": "info"}
        tally = [
            (status, str(report.count(status)), tones[status] if report.count(status) else "muted")
            for status in ("OK", "WARN", "FAIL", "UNKNOWN", "INFO")
            if status != "INFO" or report.count("INFO")
        ]
        self._print(ui.cards(tally))
        for name in SECTIONS:
            rows = [
                (
                    item.status,
                    item.label,
                    ui.value_text(
                        item.value,
                        parts=self._packed(item.parts),
                        more=item.more,
                        hints=item.hints,
                    ),
                )
                for item in items
                if item.section == name
            ]
            if rows:
                self._print(ui.section(name, ui.item_grid(rows)))
        if report.failed:
            status, title = "FAIL", "Some checks failed"
            steps = ["fix the FAIL items above (each has a → line), then run doctor again"]
        else:
            status, title = "OK", "Ready"
            steps = [
                "inodefence targets — the extractors and what each supports",
                "inodefence verify --target node-tar --version <v> --dry-run — the plan, run "
                "nothing",
            ]
        lines = [report.summary]
        self._print(ui.result_panel(status, title, lines, next_steps=steps))

    def _packed(self, parts: Sequence[str]) -> list[str]:
        if not parts:
            return []
        assert self._rich is not None
        # The value column: what is left after the chip (10) and name (22) columns, padding and
        # the section border; groups break only between groups.
        width = max(self._rich.size.width - 11 - 22 - 4 - 4, 20)  # chip, name, padding, border
        return pack(parts, " · ", width)

    # -- targets -----------------------------------------------------------------------------

    def targets(
        self,
        rows: Sequence[Sequence[str]],
        header: Sequence[str],
        note: str,
        support: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """The target table. Plain: the fixed-width table the command has always printed."""
        if self._rich is None:
            widths = (16, 11, 13, 8, 7)
            head = " ".join(f"{name:{w}}" for name, w in zip(header, widths, strict=False))
            head += " " + header[-1]
            print(head, file=self.stream)
            print("-" * len(head), file=self.stream)
            for row in rows:
                cells = " ".join(f"{cell:{w}}" for cell, w in zip(row, widths, strict=False))
                print(f"{cells} {row[-1]}", file=self.stream)
            self.line()
            self.line(note)
            return
        self._rich_targets(rows, header, note, support or {})

    def _rich_targets(
        self,
        rows: Sequence[Sequence[str]],
        header: Sequence[str],
        note: str,
        support: Mapping[str, Mapping[str, Any]],
    ) -> None:
        from rich.text import Text

        from inodefence.ui import components as ui

        total = len(rows)

        def able(column: int) -> int:
            return sum(1 for row in rows if row[column] == "yes")

        self._print(
            ui.header("targets", version=self.version, subject=f"{total} extractors registered"),
            "",
            ui.cards(
                [
                    ("regression", f"{able(1)}/{total}", "plain"),
                    ("auto-prepare", f"{able(2)}/{total}", "plain"),
                    ("exploration", f"{able(3)}/{total}", "plain"),
                    ("replay", f"{able(4)}/{total}", "plain"),
                ]
            ),
        )

        def capability(value: str) -> Text:
            if value == "yes":
                return ui.flag(True)
            text = ui.flag(False)
            if value.startswith("no ("):
                text.append(f" {value[3:]}", style="if.label")
            return text

        table = ui.data_table(
            [(header[0], "left"), *((name, "left") for name in header[1:5]), (header[5], "left")],
            (
                [Text(row[0], style="bold"), *(capability(cell) for cell in row[1:5]), row[5]]
                for row in rows
            ),
        )
        self._print(ui.section("Extractors", table))
        options = [
            (name, option)
            for name, feats in support.items()
            for option in feats.get("options") or []
        ]
        if options:
            option_rows = []
            for name, option in options:
                needed = "required" if option.get("required") else "optional"
                choices = option.get("choices")
                detail = Text(option.get("description") or "")
                if choices:
                    detail.append(f"\nchoices: {', '.join(map(str, choices))}", style="if.label")
                option_rows.append(
                    [
                        Text(name, style="bold"),
                        Text(f"--{option['name']}", style="if.accent"),
                        Text(needed, style="if.label"),
                        detail,
                    ]
                )
            self._print(
                ui.section(
                    "Target options",
                    ui.data_table(
                        [
                            ("target", "left"),
                            ("option", "left"),
                            ("need", "left"),
                            ("what", "left"),
                        ],
                        option_rows,
                    ),
                )
            )
        self._print(Text(note, style="if.label"))

    # -- verify / compare (Rich only: shown after the driver's own lines, never instead) -------

    def verify_results(self, summaries: Sequence[Any], out: Any) -> None:
        """One result screen per verify cell this run wrote (``app.runs.RunSummary``)."""
        if self._rich is None:
            return
        from inodefence.ui import results

        for summary in summaries:
            self._print("", *results.verify_screen(summary, version=self.version))
        if not summaries:
            self._print(
                "",
                results.no_result_panel(
                    f"no result.json was written under {out} by this run",
                ),
            )

    def compare(self, a: Any, b: Any, rows: Sequence[Any]) -> None:
        """Two results case by case (``app.runs.compare_results``)."""
        from inodefence.ui import results

        if self._rich is None:
            for line in results.compare_plain_lines(a, b, rows):
                print(line, file=self.stream)
            return
        self._print(*results.compare_screen(a, b, rows, version=self.version))

    # -- errors ------------------------------------------------------------------------------

    def error(self, text: str, hint: str | None = None, *, stream: TextIO | None = None) -> None:
        """An error for a person: the text, then the next step after an arrow (stderr)."""
        target = sys.stderr if stream is None else stream
        print(text, file=target)
        if hint:
            arrow = self.view.arrow
            print(f"{arrow} {hint}", file=target)

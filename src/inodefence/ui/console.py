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

    def __init__(self, stream: TextIO | None = None, *, rich: Any | None = None) -> None:
        self.stream = sys.stdout if stream is None else stream
        self.view = View.for_stream(self.stream)
        module = rich if rich is not None else rich_module()
        self._rich = None
        if module is not None and interactive(self.stream):
            from rich.console import Console as RichConsole

            self._rich = RichConsole(file=self.stream, highlight=False, soft_wrap=False)

    @property
    def uses_rich(self) -> bool:
        return self._rich is not None

    def line(self, text: str = "") -> None:
        """A plain line, identical in both renderers (summaries, notes)."""
        print(text, file=self.stream)

    # -- doctor ------------------------------------------------------------------------------

    def doctor(self, items: Sequence[Item], summary: str) -> None:
        if self._rich is None:
            for item in items:
                for line in plain_item_lines(item, self.view):
                    print(line, file=self.stream)
        else:
            self._rich_doctor(items)
        self.line()
        self.line(summary)

    def _rich_doctor(self, items: Sequence[Item]) -> None:
        from rich.table import Table
        from rich.text import Text

        table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column(no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column(overflow="fold")
        for item in items:
            value = Text(item.value)
            if item.parts:
                value.append("\n" + " · ".join(item.parts))
            for line in item.more:
                value.append("\n" + line)
            for hint in item.hints:
                value.append("\n→ " + hint, style="dim")
            table.add_row(Text(item.status, style=_RICH_STYLE[item.status]), item.label, value)
        assert self._rich is not None
        self._rich.print(table)

    # -- targets -----------------------------------------------------------------------------

    def targets(self, rows: Sequence[Sequence[str]], header: Sequence[str], note: str) -> None:
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
        else:
            from rich import box
            from rich.table import Table

            table = Table(box=box.SIMPLE_HEAD, pad_edge=False, header_style="bold")
            for name in header:
                table.add_column(name, overflow="fold")
            for row in rows:
                table.add_row(*row)
            assert self._rich is not None
            self._rich.print(table)
        self.line()
        self.line(note)

    # -- errors ------------------------------------------------------------------------------

    def error(self, text: str, hint: str | None = None, *, stream: TextIO | None = None) -> None:
        """An error for a person: the text, then the next step after an arrow (stderr)."""
        target = sys.stderr if stream is None else stream
        print(text, file=target)
        if hint:
            arrow = self.view.arrow
            print(f"{arrow} {hint}", file=target)

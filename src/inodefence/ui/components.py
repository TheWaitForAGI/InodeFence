"""The terminal design system: a few Rich building blocks every command screen is made of.

One grammar for every screen (and the same as the TUI's): a brand header line; sections as thin
cyan-bordered panels with their title on the border; a row of small number cards (label muted,
value bold); horizontal bars for ratios (only from real counts); chips for statuses (a symbol and
a word, coloured); tables with a thin header rule; a result panel at the end saying what was done,
what came out and what to look at next. No panel is put inside another; the terminal background
is never painted (colours: :data:`inodefence.ui.theme.TERMINAL`).

Rich is the optional ``ui`` extra: this module is imported only after :func:`console.rich_module`
said Rich is there.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from inodefence.ui import theme

BORDER = "if.border"
#: Thin rounded border for sections and cards (one line, no heavy frame).
FRAME = box.ROUNDED


def header(command: str, *, version: str, subject: str | None = None) -> RenderableType:
    """``InodeFence 0.2.0 › doctor · 14 checks`` -- one line, no logo."""
    line = Text()
    line.append("InodeFence", style="if.title")
    line.append(f"  {version}", style="if.label")
    line.append("  ›  ", style="if.label")
    line.append(command, style="bold")
    if subject:
        line.append(f"  ·  {subject}", style="if.label")
    return line


def chip(status: str) -> Text:
    """A status as a word with a symbol, in its meaning's colour (``✓ OK``, ``✗ FAIL``)."""
    return Text(theme.status_label(status), style=f"if.chip.{theme.tone(status)}")


def flag(value: bool, word: str | None = None) -> Text:
    """A yes/no capability, lower-case with a symbol (``✓ yes`` / ``· no``)."""
    tone = "ok" if value else "muted"
    text = word if word is not None else ("yes" if value else "no")
    return Text(f"{theme.TONE_SYMBOL[tone]} {text}", style=f"if.{tone}")


def section(title: str, body: RenderableType, *, subtitle: str | None = None) -> Panel:
    """A titled section: a thin cyan border with the title on it, left-aligned."""
    return Panel(
        body,
        title=Text(f" {title} ", style="if.title"),
        title_align="left",
        subtitle=Text(f" {subtitle} ", style="if.label") if subtitle else None,
        subtitle_align="right",
        box=FRAME,
        border_style=BORDER,
        padding=(0, 1),
    )


def cards(items: Iterable[tuple[str, str, str]]) -> Table:
    """A row of number cards of equal width across the screen: ``(label, value, tone)`` ->
    value bold in its tone, label muted below. A value the data does not have is passed as ``?``
    (never ``0``)."""
    panels = []
    for label, value, tone in items:
        body = Text(value, style="" if tone == "plain" else f"if.{tone}")
        body.stylize("bold")
        body.append(f"\n{label}", style="if.label")
        panels.append(Panel(body, box=FRAME, border_style=BORDER, padding=(0, 2), expand=True))
    row = Table.grid(expand=True, padding=(0, 1))
    for _ in panels:
        row.add_column(ratio=1)
    row.add_row(*panels)
    return row


def bars(rows: Sequence[tuple[str, int, int, str]], *, width: int = 28) -> Table:
    """Horizontal bars: ``(label, value, total, tone)`` -> label · percent · bar · value/total.

    Only for real counts: a row whose total is 0 shows no bar and no percentage.
    """
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(justify="right", no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(justify="right", no_wrap=True)
    for label, value, total, tone in rows:
        if total > 0:
            percent = Text(f"{100 * value // total}%", style="if.label")
            bar: RenderableType = ProgressBar(
                total=total,
                completed=value,
                width=width,
                complete_style=f"if.{tone}",
                finished_style=f"if.{tone}",
                style="if.track",  # a dark track, so any filled part reads
            )
        else:
            percent, bar = Text(""), Text("")
        table.add_row(Text(label), percent, bar, Text(f"{value}/{total}", style="bold"))
    return table


def data_table(
    columns: Sequence[tuple[str, str]],
    rows: Iterable[Sequence[RenderableType]],
    *,
    keep: Sequence[int] = (0,),
) -> Table:
    """A table with a thin header rule across its section: ``columns`` are ``(title,
    justify)``; numbers go right. Columns in ``keep`` (default: the first, which names the
    row) never wrap; the others wrap when the screen is narrow (nothing is cropped)."""
    table = Table(
        box=box.SIMPLE_HEAD,
        header_style="if.label",
        border_style=BORDER,
        pad_edge=False,
        show_edge=False,
        expand=True,
    )
    for number, (title, justify) in enumerate(columns):
        table.add_column(
            title,
            justify=justify,  # type: ignore[arg-type]
            overflow="fold",
            no_wrap=number in keep,
        )
    for row in rows:
        table.add_row(*row)
    return table


#: Fixed widths of an item grid's chip and name columns, so values line up across sections.
CHIP_WIDTH = 11  # the longest chip ("! UNKNOWN", 9) and two spaces
NAME_WIDTH = 22


def item_grid(rows: Iterable[tuple[str, str, RenderableType]]) -> Table:
    """Rows of ``(status, label, value)``: a chip, a bold label, the value (no header)."""
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True, width=CHIP_WIDTH)
    table.add_column(no_wrap=True, style="bold", width=NAME_WIDTH)
    table.add_column(overflow="fold")
    for status, label, value in rows:
        table.add_row(chip(status), label, value)
    return table


def value_text(
    value: str, *, more: Sequence[str] = (), hints: Sequence[str] = (), parts: Sequence[str] = ()
) -> Text:
    """A value with its extra lines (muted) and next steps (``→`` in the accent colour)."""
    text = Text(value)
    for line in parts:
        text.append(f"\n{line}")
    for line in more:
        text.append(f"\n{line}", style="if.label")
    for hint in hints:
        text.append(f"\n→ {hint}", style="if.hint")
    return text


def result_panel(
    status: str,
    title: str,
    lines: Sequence[str | Text],
    *,
    next_steps: Sequence[str] = (),
) -> Panel:
    """The closing panel: a status chip and a title on the border, what came out, what next."""
    body: list[Any] = [line if isinstance(line, Text) else Text(line) for line in lines]
    for step in next_steps:
        body.append(Text(f"→ {step}", style="if.hint"))
    head = chip(status)
    head.append(f"  {title}", style="bold")
    return Panel(
        Group(*body),
        title=head,
        title_align="left",
        box=FRAME,
        border_style=f"if.{theme.tone(status)}",
        padding=(0, 1),
    )

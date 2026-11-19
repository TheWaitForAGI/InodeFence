"""The shared palette (ui/theme.py): meaning names, status words, exports for TUI and web."""

from __future__ import annotations

import re

import pytest

from inodefence.ui import theme

HEX = re.compile(r"^#[0-9a-f]{6}$")


def test_every_colour_is_a_hex_value_and_the_terminal_set_is_a_subset_of_meanings() -> None:
    assert all(HEX.match(value) for value in theme.PALETTE.values())
    assert all(HEX.match(value) for value in theme.TERMINAL.values())
    assert set(theme.TERMINAL) <= set(theme.PALETTE)
    for name in ("accent", "ok", "warn", "bad", "info", "muted", "border", *theme.SERIES):
        assert name in theme.TERMINAL, name


def test_chart_colours_differ_from_the_status_colours() -> None:
    status = {theme.PALETTE[name] for name in ("ok", "warn", "bad", "info", "accent")}
    assert not status & {theme.PALETTE[name] for name in theme.SERIES}


@pytest.mark.parametrize(
    ("word", "meaning", "label"),
    [
        ("OK", "ok", "✓ OK"),
        ("PASS", "ok", "✓ PASS"),
        ("WARN", "warn", "! WARN"),
        ("UNKNOWN", "warn", "! UNKNOWN"),
        ("as_stored", "warn", "! AS STORED"),
        ("FAIL", "bad", "✗ FAIL"),
        ("ERROR", "bad", "✗ ERROR"),
        ("INFO", "info", "i INFO"),
        ("something-else", "muted", "· SOMETHING-ELSE"),
    ],
)
def test_a_status_is_always_a_word_with_a_symbol(word: str, meaning: str, label: str) -> None:
    assert theme.tone(word) == meaning
    assert theme.status_label(word) == label


def test_exports_for_the_tui_and_the_web() -> None:
    textual = theme.textual_css_variables().splitlines()
    assert "$if-accent: #22d3ee;" in textual and "$if-surface-alt: #111a2e;" in textual
    assert len(textual) == len(theme.PALETTE)
    css = theme.css_variables()
    assert css.startswith(":root {") and "--if-bad: #ef4444;" in css
    styles = theme.rich_styles()
    assert styles["if.ok"] == theme.TERMINAL["ok"] and styles["if.chip.bad"].startswith("bold")


def test_the_rich_theme_builds_when_rich_is_installed() -> None:
    pytest.importorskip("rich")
    from rich.console import Console

    console = Console(theme=theme.rich_theme(), width=40, file=__import__("io").StringIO())
    console.print("[if.ok]fine[/]")  # every style name resolves

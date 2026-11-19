"""One palette for every InodeFence screen (terminal, TUI, web), in meaning names.

Screens never name a colour; they name what it means:

- ``accent``: brand, headings, panel titles (cyan); ``border``: thin panel borders (darker cyan);
- ``ok``: a confirmed positive -- OK, PASS, a reproduced finding, a check that held (green);
- ``warn``: needs a look -- WARN, UNKNOWN, an undecided or unjudged value, a stalled run, a
  candidate that needs a reproduction check, a result shown as stored (amber);
- ``bad``: a failure or a judged violation -- FAIL, ERROR, a contract violated, a harness error
  (red);
- ``info``: neutral facts that are not a verdict (blue); ``muted``: missing values, labels (slate);
- ``surface`` / ``surface_alt`` / ``surface_raised``: the near-black navy ground (TUI and web only);
- ``series_1`` .. ``series_6``: chart colours (bars, graphs), distinct from the status colours.

:data:`PALETTE` is for dark grounds (the TUI and the web dashboard paint their background).
The terminal command never paints the background -- it is the user's -- so it uses
:data:`TERMINAL`, mid-tone foreground colours that stay readable on dark and light terminals.

A meaning is never carried by colour alone: every status is also written as a word with a symbol
(:func:`status_label`). Standard library only; the Rich theme is built on demand.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Meaning name -> hex colour, for dark grounds (TUI, web).
PALETTE: Mapping[str, str] = {
    "surface": "#0b1220",
    "surface_alt": "#111a2e",
    "surface_raised": "#1a2540",
    "border": "#0e7490",
    "accent": "#22d3ee",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "ok": "#22c55e",
    "warn": "#f59e0b",
    "bad": "#ef4444",
    "info": "#3b82f6",
    "series_1": "#a78bfa",
    "series_2": "#2dd4bf",
    "series_3": "#f472b6",
    "series_4": "#818cf8",
    "series_5": "#a3e635",
    "series_6": "#e879f9",
}

#: The same meanings for the terminal command: foreground only, readable on dark and light.
TERMINAL: Mapping[str, str] = {
    "border": "#0891b2",
    "accent": "#06b6d4",
    "muted": "#64748b",
    "ok": "#16a34a",
    "warn": "#d97706",
    "bad": "#dc2626",
    "info": "#2563eb",
    "series_1": "#7c3aed",
    "series_2": "#0d9488",
    "series_3": "#db2777",
    "series_4": "#4f46e5",
    "series_5": "#65a30d",
    "series_6": "#c026d3",
}

#: A status word -> its meaning. Words not listed are ``muted``.
STATUS_TONE: Mapping[str, str] = {
    "OK": "ok",
    "PASS": "ok",
    "REPRODUCED": "ok",
    "COMPLETE": "ok",
    "YES": "ok",
    "SAME": "ok",
    "WARN": "warn",
    "UNKNOWN": "warn",
    "UNJUDGED": "warn",
    "INDETERMINATE": "warn",
    "STALLED": "warn",
    "CANDIDATE": "warn",
    "AS STORED": "warn",
    "INCOMPLETE": "warn",
    "PARTIAL": "warn",
    "FAIL": "bad",
    "ERROR": "bad",
    "VIOLATION": "bad",
    "RUN ERROR": "bad",
    "DIFFERENT": "bad",
    "INFO": "info",
    "NO": "muted",
    "NONE": "muted",
}

#: A symbol beside each tone's word (the word is always there; this only helps scanning).
TONE_SYMBOL: Mapping[str, str] = {
    "ok": "✓",
    "warn": "!",
    "bad": "✗",
    "info": "i",
    "muted": "·",
    "accent": "›",
}

#: Chart colours in order (bars, graphs).
SERIES = tuple(f"series_{n}" for n in range(1, 7))


def tone(status: str) -> str:
    """The meaning of a status word (``OK`` -> ``ok``); unknown words are ``muted``."""
    return STATUS_TONE.get(status.upper().replace("_", " "), "muted")


def status_label(status: str) -> str:
    """The word with its symbol, e.g. ``✓ OK`` -- what a chip shows."""
    return f"{TONE_SYMBOL[tone(status)]} {status.upper().replace('_', ' ')}"


def rich_styles(colours: Mapping[str, str] = TERMINAL) -> dict[str, str]:
    """Rich style names for ``colours`` (default: the terminal set).

    ``if.<meaning>`` (foreground), ``if.chip.<meaning>`` (bold, foreground: a chip is a word
    with a symbol, not a painted block, so it reads on any background), ``if.title``,
    ``if.hint`` (a next step: dim accent), ``if.label``, ``if.value``, ``if.border``, and the
    ``markdown.*`` styles Rich uses for a Markdown document.
    """
    styles = {f"if.{name}": colour for name, colour in colours.items()}
    for name in ("ok", "warn", "bad", "info", "muted", "accent"):
        styles[f"if.chip.{name}"] = f"bold {colours[name]}"
    styles["if.title"] = f"bold {colours['accent']}"
    styles["if.hint"] = f"dim {colours['accent']}"
    styles["if.label"] = colours["muted"]
    styles["if.value"] = "bold"
    # Rich's own Markdown styles (``summary`` on a terminal), on the same palette.
    styles["markdown.h1"] = f"bold {colours['accent']}"
    styles["markdown.h1.border"] = colours["border"]
    styles["markdown.h2"] = f"bold {colours['accent']}"
    styles["markdown.h3"] = "bold"
    styles["markdown.code"] = colours["accent"]
    styles["markdown.block_quote"] = colours["muted"]
    styles["markdown.item.bullet"] = colours["accent"]
    styles["markdown.item.number"] = colours["accent"]
    styles["markdown.table.header"] = f"bold {colours['muted']}"
    styles["markdown.table.border"] = colours["border"]
    styles["markdown.hr"] = colours["border"]
    styles["markdown.link"] = colours["info"]
    return styles


def rich_theme(colours: Mapping[str, str] = TERMINAL) -> Any:
    """A ``rich.theme.Theme`` with :func:`rich_styles` (Rich must be installed)."""
    from rich.theme import Theme

    return Theme(rich_styles(colours))


def textual_css_variables() -> str:
    """Textual CSS variables (``$if-accent: #22d3ee;`` ...) from :data:`PALETTE` for the TUI."""
    return "\n".join(f"$if-{name.replace('_', '-')}: {colour};" for name, colour in PALETTE.items())


def css_variables(selector: str = ":root") -> str:
    """CSS custom properties (``--if-accent: #22d3ee;`` ...) from :data:`PALETTE` for the web."""
    body = "\n".join(
        f"  --if-{name.replace('_', '-')}: {colour};" for name, colour in PALETTE.items()
    )
    return f"{selector} {{\n{body}\n}}"

"""The TUI's colours by meaning, from the shared :mod:`inodefence.ui.theme` when it exists.

Until that module is on this branch the same semantic names and values (the ones the theme
announces) are used here, so swapping is a no-op for the screen.
"""

from __future__ import annotations

from collections.abc import Mapping

_FALLBACK: dict[str, str] = {
    "accent": "#22d3ee",
    "ok": "#22c55e",
    "warn": "#f59e0b",
    "bad": "#ef4444",
    "info": "#3b82f6",
    "muted": "#94a3b8",
    "text": "#e2e8f0",
    "surface": "#0b1220",
    "surface_alt": "#111a2e",
    "surface_raised": "#1a2540",
    "border": "#0e7490",
}

try:  # pragma: no cover - depends on which branch is merged
    from inodefence.ui.theme import PALETTE as _THEME  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    _THEME = {}

PALETTE: Mapping[str, str] = {**_FALLBACK, **dict(_THEME)}
#: Darker steps used only to separate regions (no meaning attached).
DEEP = PALETTE["surface"]
PANEL = PALETTE["surface_alt"]
TITLE = "#67e8f9"
BAR_LOW, BAR_MID, BAR_HIGH = "#38bdf8", "#facc15", "#fb923c"


def colour(meaning: str) -> str:
    return PALETTE.get(meaning, PALETTE["text"])

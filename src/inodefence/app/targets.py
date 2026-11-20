"""What each registered target supports, for every interface (read-only).

The data is the drivers' own registry (:func:`inodefence.locate.target_support`, read from each
adapter's hooks in the clone); nothing here decides support. :func:`table_rows` turns it into the
cells of the human table; ``inodefence targets --json`` prints the registry itself, unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from inodefence.locate import target_support

TABLE_HEADER = ("target", "regression", "auto-prepare", "explore", "replay", "target options")
TABLE_NOTE = "target options: a trailing '?' marks optional. Pass them to `verify` / `explore`."


def load(root: Path) -> dict[str, dict[str, Any]]:
    """The registry of the clone at ``root`` (raises like :func:`target_support`)."""
    return target_support(root)


def table_rows(support: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, ...]]:
    """One row per target, in registry order: the cells ``inodefence targets`` shows."""
    rows = []
    for name, feats in support.items():
        explore = "yes" if feats["explore"] else f"no ({feats['explore_reason']})"
        opts = feats.get("options") or []
        names = ", ".join(f"--{o['name']}" + ("" if o["required"] else "?") for o in opts) or "—"
        regression = "yes" if feats.get("regression", True) else "no"
        prepare = "yes" if feats.get("auto_prepare", True) else "no"
        replay = "yes" if feats.get("replay") else "no"
        rows.append((name, regression, prepare, explore, replay, names))
    return rows

"""``inodefence tui``: a full-screen dashboard of the runs on this host that can also run the CLI's
commands, one that starts Docker only after a confirmation (Textual).

Importing this package never imports Textual. :func:`run` does, and raises
:class:`TuiUnavailable` (an :class:`ImportError`) with the install hint when it is missing, so the
command handler can print the hint and exit 3.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

INSTALL_HINT = (
    "the TUI needs the optional 'tui' extra (Textual): pip install 'inodefence[tui]' "
    "(or: uv pip install 'inodefence[tui]')"
)
#: Lowest Textual this screen supports: the tested 8.2 line (8.2.8), the `tui` extra's floor.
TEXTUAL_MIN = "8.2"


class TuiUnavailable(ImportError):
    """Textual is not installed; ``str(error)`` is the install hint."""


def run(
    roots: Sequence[Path] | None = None,
    *,
    extra: Sequence[Path] = (),
    refresh: float = 1.0,
) -> int:
    """Open the dashboard on ``roots`` (default: the explore and verify output folders) plus
    ``extra`` folders; re-read every ``refresh`` seconds. Returns 0 when the user quits."""
    try:
        from inodefence.ui.tui.app import InodeFenceTui
    except ImportError as error:
        if error.name is not None and error.name.split(".")[0] in ("textual", "rich"):
            raise TuiUnavailable(INSTALL_HINT) from error
        raise
    app = InodeFenceTui(roots=roots, extra=extra, refresh=refresh)
    app.run()
    return 0


__all__ = ["INSTALL_HINT", "TEXTUAL_MIN", "TuiUnavailable", "run"]

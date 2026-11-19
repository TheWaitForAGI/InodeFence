"""``python -m inodefence.ui.tui [FOLDER ...]``: the TUI without the ``inodefence tui`` command.

The same as ``inodefence tui`` (which the CLI registers): the folders are read in addition to the
default output folders. Exit 3 with the install hint when Textual is missing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from inodefence.ui.tui import TuiUnavailable, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m inodefence.ui.tui",
        description="Read-only dashboard of the run folders on this host.",
    )
    parser.add_argument("folders", nargs="*", type=Path, help="extra folders to read")
    parser.add_argument("--refresh", type=float, default=1.0, help="seconds between re-reads")
    args = parser.parse_args(argv)
    if args.refresh <= 0:
        parser.error("--refresh must be > 0")
    try:
        return run(extra=args.folders, refresh=args.refresh)
    except TuiUnavailable as error:
        print(f"error: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

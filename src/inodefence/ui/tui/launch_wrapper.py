"""Run one ``inodefence`` command for the TUI and record how it ended.

``python -m inodefence.ui.tui.launch_wrapper <record folder> -- <inodefence> <command> ...``

Started by :func:`inodefence.ui.tui.launch.start` in a session of its own, with stdout and stderr
already sent to ``<record>/output.log``. It runs the command unchanged (inheriting that output),
waits for it, and writes the exit code and end time into ``<record>/launch.json`` -- so the code is
known even when the TUI was closed meanwhile. It changes nothing about the command: same argv,
environment, working directory and exit code (the wrapper exits with the command's code).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from inodefence.ui.tui.launch import RECORD_FILE, _now, write_record


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "--":
        print("usage: launch_wrapper <record folder> -- <command> ...", file=sys.stderr)
        return 2
    folder, command = Path(argv[0]), argv[2:]
    try:
        record = json.loads((folder / RECORD_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    record["pid"] = os.getpid()
    write_record(folder, record)
    try:
        code = subprocess.call(command)  # noqa: S603 -- the CLI command the person confirmed
    except OSError as error:  # the program could not be started at all
        print(f"inodefence tui: could not start {command[0]}: {error}", file=sys.stderr)
        record.update(error=str(error))
        code = 127
    record.update(exit_code=code, ended_at=_now())
    write_record(folder, record)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

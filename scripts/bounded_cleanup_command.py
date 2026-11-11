"""Run one cleanup CLI with a deadline and kill only its new process group."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Sequence


def run(command: Sequence[str], deadline: float, grace: float = 5) -> int:
    try:
        process = subprocess.Popen(command, start_new_session=True)
        try:
            return process.wait(timeout=deadline)
        except subprocess.TimeoutExpired:
            print(f"cleanup command timed out after {deadline:g}s: {command[0]}", file=sys.stderr)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                print("cleanup CLI termination unconfirmed", file=sys.stderr)
            return 124
    except OSError as error:
        print(f"cleanup CLI unavailable: {error}", file=sys.stderr)
        return 125


def main() -> int:
    return run(sys.argv[2:], float(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())

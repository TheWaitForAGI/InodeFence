"""A fake ``inodefence`` for the TUI's launch tests: no Docker, no engine, nothing else runs.

:func:`install` writes an executable script; its behaviour comes from the environment:

- ``FAKE_ARGV_LOG``: append the argv it got (as one JSON line) to this file
- ``FAKE_EXIT``: the exit code (default 0)
- ``FAKE_SLEEP``: seconds to run before exiting (default 0)
- ``FAKE_STDERR``: a line to print on stderr (a refusal reason, say)
- ``FAKE_LAUNCHER_LOG``: when set to an output folder, write a launcher log there
  (``<out>/runtime/explore-launcher-<UTC>-<pid>.log``) as a running exploration does
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT = """#!{python}
import json, os, sys, time
from datetime import datetime, timezone
log = os.environ.get("FAKE_ARGV_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(sys.argv[1:]) + "\\n")
out = os.environ.get("FAKE_LAUNCHER_LOG")
if out:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(out, "runtime", f"explore-launcher-{{stamp}}-{{os.getpid()}}.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("==> [python-tarfile-effect-campaign]\\n")
print("fake inodefence " + " ".join(sys.argv[1:]), flush=True)
if os.environ.get("FAKE_STDERR"):
    print(os.environ["FAKE_STDERR"], file=sys.stderr, flush=True)
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""


def install(folder: Path) -> Path:
    """Write the fake as ``<folder>/inodefence`` and return its path."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "inodefence"
    path.write_text(SCRIPT.format(python=sys.executable), encoding="utf-8")
    path.chmod(0o755)
    return path


def environ(**values: str) -> dict[str, str]:
    """``os.environ`` plus the fake's settings (for ``monkeypatch.setenv`` loops)."""
    return {**os.environ, **values}

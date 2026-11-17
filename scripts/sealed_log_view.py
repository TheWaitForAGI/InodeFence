"""Read a sealed run's log without seeing results (#520 D1).

While a registered run is sealed, this is the one command for reading its logs during a stop.
It is allowlist-first: a line is shown only if it matches an anchored infrastructure pattern
(stage headers, re-execution and Docker-call diagnostics, tracebacks, start-gate and failed-step
lines, abort lines, evidence paths). A second, deny pass then hides any shown line that still
carries verdict-bearing text (contract names, violation words, reward, corpus, new keys, shared
identity, ``verdict``/``oracle`` keys, hits). Every hidden run of lines becomes ``[가림] n줄``
with no content.

Each call appends one record to an audit file (JSON lines, append only): when, who, which file,
how many lines were read, shown and hidden. The access audit (``sealed_access_audit.py``) counts
these calls as allowed reads.

usage: python scripts/sealed_log_view.py LOG [--tail N] [--audit PATH]
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import re
import socket
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_AUDIT = Path.home() / ".inodefence" / "sealed-access.jsonl"
MASK = "[가림] {n}줄"

#: Infrastructure lines. Only these can be shown. Each pattern is anchored after an optional
#: traceback gutter (``  |``, ``  +``) and an optional one-word label (``effect-demo-historical``),
#: because the real lines carry those prefixes.
PREFIX = r"^[\s|+]*(?:[\w.-]+ )?"
ALLOW = tuple(
    re.compile(PREFIX + pattern)
    for pattern in (
        r"==> \[[^\]]+\]$",
        r"inodefence-infra-reexecution\b",
        r"inodefence-docker-call\b",
        r"([\w.]+\.)?(BackendError|ExceptionGroup)\b",
        r"(Exception Group )?Traceback \(most recent call last\):$",
        r'File "[^"]+", line \d+',
        r"start gate: ",
        r"FAILED at step: ",
        r"aborted: step \d+ case [0-9a-f]+",
        r"evidence: ",
        r"INODEFENCE_CLEANUP_UNKNOWN: ",
    )
)

#: Verdict-bearing text. A line that matches is hidden even when it is on the allowlist. A bare
#: ``verdict`` is not here on purpose: start-gate lines say "verdict not recorded" and must show.
DENY = re.compile(
    r"\bC[012]\b|violat|reward|corpus|new-keys|nlink>|\"verdict\"|\"oracle\"|\bhits?\b",
    re.IGNORECASE,
)


def shown(line: str) -> bool:
    """Whether ``line`` may be printed: on the allowlist and free of verdict-bearing text."""
    return any(p.search(line) for p in ALLOW) and not DENY.search(line)


def view(lines: Iterable[str]) -> tuple[list[str], int, int]:
    """(output lines, lines read, lines hidden). Runs of hidden lines collapse to one mask line."""
    out: list[str] = []
    hidden_run = read = hidden = 0
    for line in lines:
        read += 1
        line = line.rstrip("\n")
        if shown(line):
            if hidden_run:
                out.append(MASK.format(n=hidden_run))
                hidden_run = 0
            out.append(line)
        else:
            hidden_run += 1
            hidden += 1
    if hidden_run:
        out.append(MASK.format(n=hidden_run))
    return out, read, hidden


def audit_record(log: Path, read: int, hidden: int, tail: int | None) -> dict:
    return {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "user": getpass.getuser(),
        "tool": "sealed_log_view",
        "log": str(log.resolve()),
        "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        "tail": tail,
        "lines_read": read,
        "lines_shown": read - hidden,
        "lines_hidden": hidden,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", type=Path)
    parser.add_argument("--tail", type=int, default=None, help="only the last N lines")
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args(argv)
    lines = args.log.read_text(encoding="utf-8", errors="replace").splitlines()
    if args.tail is not None:
        lines = lines[-args.tail :]
    out, read, hidden = view(lines)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    with args.audit.open("a", encoding="utf-8") as handle:
        record = audit_record(args.log, read, hidden, args.tail)
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    sys.stdout.write("\n".join(out) + ("\n" if out else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

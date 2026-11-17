"""Running access audit for a sealed run (#520 D2).

Run on each host, hourly while a registered run is sealed. It looks at that host's own session
records and counts reads of the sealed run's outputs, from two sides:

* **command side**: Bash commands, Read/Grep/Glob tool calls (including subagent transcripts) and
  shell history lines that name a sealed path. A call through ``sealed_log_view.py`` is an
  allowed read; anything else is ``점검 필요`` (needs a person's look);
* **output side**: tool results that contain a state-line signature (a step line with contract
  verdicts, or ``violated``/``oracle`` JSON keys). This catches reads whose path was built in a
  variable and so escaped the command side.

The output is counts and times only: no command text, no result text, no paths. It is a regex
check, not a full reading, and it does not decide anything: a ``점검 필요`` count goes to a
person, who decides whether it is a deviation to disclose.

usage: python scripts/sealed_access_audit.py --sealed PREFIX [--sealed PREFIX ...]
           [--sessions DIR ...] [--history FILE ...] [--since ISO-TIME]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

VIEWER = "sealed_log_view.py"
TOOLS_WITH_PATHS = {"Read": "file_path", "Grep": "path", "Glob": "path"}

#: A result line that shows judged state: a step line with contract verdicts, or verdict keys.
STATE_SIGNATURES = re.compile(
    r"step \d+(?:/\d+)?\b[^\n]*\bC[012] (?:VIOLATED|ok)\b"
    r"|\"violated\"\s*:\s*(?:true|false)"
    r"|\"oracle\"\s*:\s*\{",
)


@dataclass
class Counts:
    allowed: int = 0
    check: int = 0
    check_times: list[str] = field(default_factory=list)


@dataclass
class Report:
    command_side: Counts = field(default_factory=Counts)
    output_side: Counts = field(default_factory=Counts)
    records_scanned: int = 0

    def as_json(self) -> dict:
        def side(c: Counts) -> dict:
            return {"allowed": c.allowed, "점검 필요": c.check, "점검 필요 시각": c.check_times}

        return {
            "records_scanned": self.records_scanned,
            "command_side": side(self.command_side),
            "output_side": {
                "점검 필요": self.output_side.check,
                "점검 필요 시각": self.output_side.check_times,
            },
        }


def names_sealed(text: str, sealed: Iterable[str]) -> bool:
    return any(prefix in text for prefix in sealed)


def classify_command(text: str, sealed: list[str]) -> str | None:
    """``allowed``, ``check`` or ``None`` (does not touch a sealed path)."""
    if not names_sealed(text, sealed):
        return None
    return "allowed" if VIEWER in text else "check"


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def session_events(path: Path) -> Iterator[tuple[str, str, str]]:
    """(kind, time, text) for each tool call (``command``) and tool result (``output``)."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue
            time = str(record.get("timestamp", ""))
            message = record.get("message")
            if not isinstance(message, dict) or not isinstance(message.get("content"), list):
                continue
            for part in message["content"]:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use":
                    name = part.get("name")
                    tool_input = part.get("input") or {}
                    if name == "Bash":
                        yield "command", time, str(tool_input.get("command", ""))
                    elif name in TOOLS_WITH_PATHS:
                        yield "command", time, json.dumps(tool_input, ensure_ascii=False)
                elif part.get("type") == "tool_result":
                    yield "output", time, _result_text(part.get("content"))


def in_window(time: str, since: datetime | None) -> bool:
    if since is None or not time:
        return True
    try:
        return datetime.fromisoformat(time.replace("Z", "+00:00")) >= since
    except ValueError:
        return True


def audit(
    sealed: list[str],
    sessions: list[Path],
    histories: list[Path],
    since: datetime | None = None,
) -> Report:
    report = Report()
    for directory in sessions:
        for path in sorted(directory.rglob("*.jsonl")):
            for kind, time, text in session_events(path):
                if not in_window(time, since):
                    continue
                report.records_scanned += 1
                if kind == "command":
                    verdict = classify_command(text, sealed)
                    if verdict == "allowed":
                        report.command_side.allowed += 1
                    elif verdict == "check":
                        report.command_side.check += 1
                        report.command_side.check_times.append(time)
                elif STATE_SIGNATURES.search(text):
                    report.output_side.check += 1
                    report.output_side.check_times.append(time)
    for history in histories:
        for line in history.read_text(encoding="utf-8", errors="replace").splitlines():
            report.records_scanned += 1
            verdict = classify_command(line, sealed)
            if verdict == "allowed":
                report.command_side.allowed += 1
            elif verdict == "check":
                report.command_side.check += 1
                report.command_side.check_times.append("(shell history, no time)")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sealed", action="append", required=True, help="sealed path prefix")
    parser.add_argument("--sessions", action="append", type=Path, default=[])
    parser.add_argument("--history", action="append", type=Path, default=[])
    parser.add_argument("--since", type=datetime.fromisoformat, default=None)
    args = parser.parse_args(argv)
    report = audit(args.sealed, args.sessions, args.history, args.since)
    json.dump(report.as_json(), sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

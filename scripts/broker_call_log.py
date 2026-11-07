"""Host-side record of the Docker calls that failed or took long. Reporting only.

An abort's reason cannot say whether a call timed out, and a timed-out call's duration stops at its
limit, so failures alone cannot say how far a limit would have to move. The broker sees every call
with its result, so it writes down the ones that were not routine:

* a time-out, truncated output or a nonzero return code, except two that are normal on every step:
  ``container inspect`` answering that the container is gone (the last cleanup check), and
  ``container start``, whose return code is the target's exit status;
* a call of ``SLOW_CALL_SECONDS`` or more, except ``container start``, whose duration is already in
  the report as ``target_seconds``.

A normal step writes nothing. A campaign writes one header line and one summary line outside its
steps; a header without a summary means the broker did not end normally.

Nothing here may change a campaign. A write failure raises nothing and is only counted. The record
holds no argv (``container create`` carries the target command), no stdout, and for ``container
start`` no stderr content (it is target output). The file stays on the host side, where neither the
target nor the controller has it mounted.
"""

import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from inodefence.execution.container import _container_absent
from inodefence.execution.docker_client import CommandResult

FORMAT_VERSION = 1
SLOW_CALL_SECONDS = 2.0
STDERR_LIMIT = 200
# About one per step on average, at about 21 calls per step. Normal calls are not recorded, so
# reaching this already means something went wrong; the summary counts what was dropped.
MAX_RECORDS = 2000
START = ("container", "start")
INSPECT = ("container", "inspect")
CREATE = ("container", "create")
# Argv is not recorded, so only a token that is exactly a container identity may leave it.
_IDENTITY = re.compile(r"[0-9a-f]{64}|inodefence-[0-9a-f]{32}")


def call_op(argv: Sequence[str]) -> str:
    return " ".join(argv[:2])


def call_container(argv: Sequence[str]) -> str | None:
    """The container this call is about, when a token is exactly a container identity."""
    if tuple(argv[:2]) == CREATE:
        token = argv[argv.index("--name") + 1] if "--name" in argv[:-1] else None
    else:
        token = argv[-1] if argv else None
    return token if token is not None and _IDENTITY.fullmatch(token) else None


def should_record(argv: Sequence[str], outcome: CommandResult, seconds: float) -> bool:
    """Whether this call was not routine (module docstring)."""
    if outcome.timed_out or outcome.truncated:
        return True
    key = tuple(argv[:2])
    if key == START:
        return False
    if seconds >= SLOW_CALL_SECONDS:
        return True
    if outcome.returncode == 0:
        return False
    return not (key == INSPECT and len(argv) > 2 and _container_absent(outcome, argv[2]))


def call_record(
    argv: Sequence[str], outcome: CommandResult, seconds: float, started_real: float
) -> dict[str, object]:
    record: dict[str, object] = {
        "kind": "call",
        "op": call_op(argv),
        "container": call_container(argv),
        "returncode": outcome.returncode,
        "timed_out": outcome.timed_out,
        "truncated": outcome.truncated,
        "seconds_monotonic": seconds,
        "started_real": started_real,
    }
    if tuple(argv[:2]) == START:
        record["stderr_bytes"] = len(outcome.stderr)
    else:
        record["stderr"] = outcome.stderr.decode(errors="replace")[:STDERR_LIMIT]
    return record


class BrokerCallLog:
    """Appends to one file, opened per line so a killed broker loses nothing already written."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.calls: Counter[str] = Counter()
        self.recorded = 0
        self.dropped = 0
        self.write_failures = 0
        self._write({"kind": "header", "format": FORMAT_VERSION, "file": path.name})

    def _write(self, value: Mapping[str, object]) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="ascii") as stream:
                stream.write(json.dumps(value, sort_keys=True) + "\n")
        except Exception:
            self.write_failures += 1
            return False
        return True

    def observe(
        self, argv: Sequence[str], outcome: CommandResult, seconds: float, started_real: float
    ) -> None:
        try:
            self.calls[call_op(argv)] += 1
            if not should_record(argv, outcome, seconds):
                return
            if self.recorded >= MAX_RECORDS:
                self.dropped += 1
                return
            if self._write(call_record(argv, outcome, seconds, started_real)):
                self.recorded += 1
        except Exception:
            self.write_failures += 1

    def close(self) -> None:
        summary = {
            "kind": "summary",
            "calls": dict(sorted(self.calls.items())),
            "recorded": self.recorded,
            "dropped": self.dropped,
            "write_failures": self.write_failures,
        }
        # A summary that cannot be written, or failures it counted, also reach the cell log.
        if not self._write(summary) or self.write_failures:
            try:
                print(f"broker call log: {self.write_failures} write failures", file=sys.stderr)
            except Exception:
                pass

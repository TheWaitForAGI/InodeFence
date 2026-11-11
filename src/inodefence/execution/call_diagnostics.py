"""Caller-side diagnostics of Docker calls, from the stall-recovery call journal.

The container backend is protected and stays as it is: a failed runtime or cleanup
call raises ``BackendError`` with the daemon's stderr, which is empty for a
time-out or a truncated answer. These helpers recover what the backend message
cannot say, from :class:`~inodefence.execution.stall_recovery.ObservedDockerClient`,
which already journals every call of the current attempt (operation, container,
return code, timed-out and truncated flags, time; no argv and no output).

* :func:`annotate_reason` appends the last anomalous call to an abort reason as
  ``[last anomalous docker call: op=... timed_out=... truncated=... returncode=...]``.
  The suffix contains no abort-signature phrase, so
  :func:`~inodefence.evaluation.abort_classification.classify_abort_reason` gives the
  same category with or without it.
* :func:`emit_anomalies` writes one ``inodefence-docker-call`` JSON line per
  anomalous call to stderr (the campaign log; never the broker's stdout protocol),
  and never lets a failing sink change the caller's result.

Nothing here retries, removes or decides anything; it only reports.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from .stall_recovery import CallObservation

DIAGNOSTIC_PREFIX = "inodefence-docker-call"
DIAGNOSTIC_SCHEMA = "inodefence-docker-call-v1"
SUFFIX_OPEN = "[last anomalous docker call: "


def last_anomaly(calls: Sequence[CallObservation]) -> CallObservation | None:
    """The most recent anomalous call (time-out, truncation, exception, unexpected code)."""
    return next((call for call in reversed(calls) if call.anomalous), None)


def summary(call: CallObservation) -> str:
    text = (
        f"op={call.op} timed_out={str(call.timed_out).lower()} "
        f"truncated={str(call.truncated).lower()} returncode={call.returncode}"
    )
    return text if call.error is None else f"{text} error={call.error}"


def annotate_reason(reason: str, calls: Sequence[CallObservation]) -> str:
    """``reason`` plus the last anomalous call; unchanged when there is none."""
    anomaly = last_anomaly(calls)
    if anomaly is None:
        return reason
    return f"{reason} {SUFFIX_OPEN}{summary(anomaly)}]"


def anomaly_record(call: CallObservation) -> dict[str, Any]:
    return {**call.to_record(), "absent": call.absent}


def emit_anomalies(
    calls: Sequence[CallObservation], scope: str, stream: TextIO | None = None
) -> int:
    """One stderr JSON line per anomalous call; returns how many were anomalous."""
    count = 0
    for call in calls:
        if not call.anomalous:
            continue
        count += 1
        record = {"schema": DIAGNOSTIC_SCHEMA, "scope": scope, **anomaly_record(call)}
        try:
            print(
                f"{DIAGNOSTIC_PREFIX} {json.dumps(record, sort_keys=True)}",
                file=stream if stream is not None else sys.stderr,
                flush=True,
            )
        except Exception:
            pass  # a diagnostic never changes the caller's result
    return count

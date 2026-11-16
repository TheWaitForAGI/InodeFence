"""Where and why a product run stopped: stage x category x preserved evidence, for one line.

A run of ``inodefence explore`` / ``replay`` can stop for reasons that are not the target's:
Docker not answering, a controller that never started, a loop aborted on an infrastructure error,
or a cleanup whose outcome is unknown. The research layer already records these (the controller's
``aborted`` stub with its ``category``, the start gate, the launcher's markers); this module only
reads what a run left behind and says, in one line, which stage it reached, which category it
falls in, and where the evidence is. It never changes an exit code, a verdict or a result file.

The classification uses only the launcher's exit code and which files exist (and the ``aborted``
block of a report that does). The launcher's terminal output is not captured or parsed, so a
cause that shows only there (for example ``INODEFENCE_CLEANUP_UNKNOWN`` from the node-tar launcher)
is not seen: such a run is reported by stage with category ``UNKNOWN``.

Categories are the shared ``InvalidReason`` values (``inodefence.evaluation.abort_classification``,
unchanged), plus ``daemon-unreachable`` / ``daemon-timeout`` for Docker itself and ``UNKNOWN``
when nothing on disk says more. An infrastructure stop is never a target violation.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inodefence.drivers.runtime.health import DaemonState, DaemonStatus, ImageLookup, ImageState
from inodefence.evaluation.abort_classification import InvalidReason, classify_abort_reason

UNKNOWN = "UNKNOWN"
DAEMON_CATEGORY = {
    DaemonState.UNREACHABLE: "daemon-unreachable",
    DaemonState.TIMEOUT: "daemon-timeout",
}


class Stage(enum.StrEnum):
    PREFLIGHT = "preflight"  # before anything was prepared: Docker / host questions
    IMAGE = "image"  # looking up or preparing the target image
    CONTROLLER_SETUP = "controller-setup"  # the launcher ran but left no loop report
    LOOP = "loop"  # the loop started and stopped (its report says aborted)
    CLEANUP = "cleanup"  # the loop finished, the launcher did not: cleanup state unknown


@dataclass(frozen=True)
class Diagnosis:
    stage: Stage
    category: str
    detail: str
    evidence: tuple[Path, ...] = ()
    result_written: bool = False

    def line(self, prefix: str) -> str:
        """``<prefix> DIAGNOSIS: stage=… category=… result=… evidence=…; <detail>``."""
        evidence = ", ".join(str(path) for path in self.evidence) or "none"
        result = "written" if self.result_written else "not-written"
        return (
            f"{prefix} DIAGNOSIS: stage={self.stage.value} category={self.category} "
            f"result={result} evidence={evidence}; {self.detail}"
        )

    def as_record(self) -> dict[str, Any]:
        """JSON-ready form; evidence as names only (no host paths in a record)."""
        return {
            "stage": self.stage.value,
            "category": self.category,
            "detail": self.detail,
            "evidence": [path.name for path in self.evidence],
            "result_written": self.result_written,
        }


def _valid_category(value: object) -> str | None:
    try:
        return InvalidReason(value).value if isinstance(value, str) else None
    except ValueError:
        return None


def abort_category(aborted: dict[str, Any]) -> str:
    """The recorded ``category`` if it is a shared value, else the reason classified the same way.

    An empty reason (the HOST4 PR 1 smoke had ``"container runtime cleanup inspect failed: "``)
    still classifies by its prefix; a block with neither is ``UNKNOWN``.
    """
    recorded = _valid_category(aborted.get("category"))
    if recorded is not None:
        return recorded
    reason = aborted.get("reason")
    if isinstance(reason, str) and reason.strip():
        return classify_abort_reason(reason).value
    return UNKNOWN


def daemon_diagnosis(status: DaemonStatus) -> Diagnosis | None:
    """A preflight stop when the daemon did not answer; None when it did."""
    if status.state is DaemonState.OK:
        return None
    return Diagnosis(Stage.PREFLIGHT, DAEMON_CATEGORY[status.state], status.detail)


def image_diagnosis(lookup: ImageLookup, daemon: DaemonStatus | None = None) -> Diagnosis | None:
    """An image-stage stop when the image question had no usable answer; None otherwise."""
    if lookup.state is not ImageState.UNKNOWN:
        return None
    category = UNKNOWN
    if daemon is not None and daemon.state is not DaemonState.OK:
        category = DAEMON_CATEGORY[daemon.state]
    elif "did not answer within" in lookup.detail:
        category = DAEMON_CATEGORY[DaemonState.TIMEOUT]
    return Diagnosis(Stage.IMAGE, category, lookup.detail)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def run_diagnosis(
    launcher_rc: int,
    report: Path,
    *,
    evidence: Iterable[Path] = (),
    result_written: bool = False,
    daemon_after: DaemonStatus | None = None,
) -> Diagnosis | None:
    """Classify a launcher run from its exit code and what it left; None for a clean run.

    ``report`` is where the launcher writes the loop report; ``evidence`` lists the other files it
    may leave (steps journal, call log, live folder) -- only those that exist are named.
    ``daemon_after`` (an optional read-only probe after the failure) can name Docker as the
    category when nothing on disk does.
    """
    present = tuple(path for path in (report, *evidence) if path.exists())
    data = _load(report) if report.is_file() else None
    fallback = UNKNOWN
    if daemon_after is not None and daemon_after.state is not DaemonState.OK:
        fallback = DAEMON_CATEGORY[daemon_after.state]
    if data is not None and isinstance(data.get("aborted"), dict):
        aborted = data["aborted"]
        category = abort_category(aborted)
        if category == UNKNOWN:
            category = fallback
        reason = str(aborted.get("reason") or "").strip() or "no reason recorded"
        step = aborted.get("step_index")
        where = f" at step {step}" if step is not None else ""
        return Diagnosis(
            Stage.LOOP,
            category,
            f"the loop aborted{where}: {reason}. An infrastructure stop, not a target verdict",
            present,
            result_written,
        )
    if launcher_rc == 0:
        if report.is_file() and data is None:
            return Diagnosis(
                Stage.LOOP,
                UNKNOWN,
                "the launcher exited 0 but its loop report is not readable JSON",
                present,
                result_written,
            )
        return None
    if data is not None:
        return Diagnosis(
            Stage.CLEANUP,
            fallback,
            f"the loop report is complete but the launcher exited {launcher_rc}: cleanup state "
            "unknown (or a post-loop copy failed); not treated as success, result not written",
            present,
            result_written,
        )
    if report.is_file():
        return Diagnosis(
            Stage.LOOP,
            fallback,
            f"the launcher exited {launcher_rc} and its loop report is not readable JSON",
            present,
            result_written,
        )
    return Diagnosis(
        Stage.CONTROLLER_SETUP,
        fallback,
        f"the launcher exited {launcher_rc} before any loop report (controller build, start or "
        "image check); see the launcher output above",
        present,
        result_written,
    )


def replay_diagnosis(
    launcher_rc: int | None,
    report: Path | None,
    *,
    evidence: Iterable[Path] = (),
    rounds_done: int = 0,
    hook_failure: str | None = None,
) -> Diagnosis:
    """Why a replay stopped before all its rounds (only called for an incomplete replay).

    Same rule as :func:`run_diagnosis`, on the replay controller's report (``complete`` /
    ``stop_reason`` instead of ``aborted``): no report -> controller setup, or the loop when the
    round journal shows rounds ran; a report that is complete while the launcher failed -> cleanup
    state unknown; an incomplete report -> the loop, its ``stop_reason`` classified with the shared
    classifier. ``launcher_rc`` is None when the hook failed before or without a launcher result.
    """
    present = tuple(
        path for path in ((report,) if report else ()) + tuple(evidence) if path.exists()
    )
    data = _load(report) if report is not None and report.is_file() else None
    if launcher_rc is None:
        return Diagnosis(
            Stage.CONTROLLER_SETUP if not rounds_done else Stage.LOOP,
            UNKNOWN,
            f"the replay hook failed: {hook_failure or 'no reason given'}",
            present,
        )
    if data is not None and data.get("complete") is True:
        return Diagnosis(
            Stage.CLEANUP,
            UNKNOWN,
            f"every round finished but the launcher exited {launcher_rc}: cleanup state unknown; "
            "not treated as a complete replay",
            present,
        )
    if data is not None:
        reason = str(data.get("stop_reason") or hook_failure or "").strip()
        category = classify_abort_reason(reason).value if reason else UNKNOWN
        return Diagnosis(
            Stage.LOOP,
            category,
            f"the replay stopped after {rounds_done} round(s): {reason or 'no reason recorded'}. "
            "An infrastructure stop is not a 'did not reproduce'",
            present,
        )
    if rounds_done:
        return Diagnosis(
            Stage.LOOP,
            UNKNOWN,
            f"the launcher exited {launcher_rc} with no report; {rounds_done} finished round(s) "
            "read from the journal",
            present,
        )
    return Diagnosis(
        Stage.CONTROLLER_SETUP,
        UNKNOWN,
        f"the launcher exited {launcher_rc} before any round (controller build, start or image "
        "check); see the launcher output above",
        present,
    )

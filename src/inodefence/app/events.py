"""Structured UI events from the files a run already writes (host-side, read-only follower).

Nothing is added to the engine, the drivers, the controller or the launchers: :class:`RunFollower`
re-reads runs with :func:`inodefence.app.runs.read_run` on a timer and turns what changed between
two snapshots into :class:`UiEvent` records (:func:`diff_snapshots`, a pure function). One follower
serves any number of subscribers (TUI, each web SSE client), each with its own bounded queue.

What an event can say is limited to what the files hold:

- there is no "current case" and no live per-contract count (the files have neither);
- the prepare phase, the time before a live folder exists, and the mid-run state of
  python-tarfile / decompress / oras-go are not visible to an outside reader: they show up as
  status ``unknown`` (or as a ``launcher_step`` estimate from the launcher log), never as numbers;
- ``timestamp`` says where it came from (``time_source``): the snapshot's ``updated_at``, a case's
  ``recorded_at``, a file's modification time, or the moment this follower observed the change;
- ``run_id`` is derived from folder names (``run_id_derived``).
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from inodefence.app.runs import (
    ReadState,
    RunRef,
    RunSnapshot,
    Source,
    discover_runs,
    read_run,
)

EVENT_SCHEMA = "inodefence-ui-event-v1"


class EventKind(StrEnum):
    PROGRESS = "progress"
    VIOLATION_CASE = "violation_case"
    STATE_CHANGE = "state_change"
    RESULT_READY = "result_ready"
    REPLAY_READY = "replay_ready"
    LAUNCHER_STEP = "launcher_step"
    READ_ERROR = "read_error"


class TimeSource(StrEnum):
    UPDATED_AT = "updated_at"
    RECORDED_AT = "recorded_at"
    MTIME = "mtime"
    OBSERVED = "observed"


@dataclass(frozen=True, slots=True)
class UiEvent:
    schema: str
    event_id: int
    timestamp: str
    time_source: TimeSource
    run_kind: str
    run_root: str
    run_id: str | None
    run_id_derived: bool
    target_id: str | None
    kind: EventKind
    status: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    #: only on ``result_ready``
    verdict: str | None = None
    #: only on ``violation_case`` (and never a "current case")
    case_id: str | None = None
    artifact_reference: str | None = None
    message: str | None = None
    #: the value is an estimate (the launcher's step line), not a recorded fact
    estimated: bool = False

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json_line(cls, text: str) -> UiEvent:
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("schema") != EVENT_SCHEMA:
            raise ValueError(f"not an {EVENT_SCHEMA} event")
        names = {f.name for f in fields(cls)}
        unknown = set(data) - names
        if unknown:
            raise ValueError(f"unknown event keys {sorted(unknown)}")
        data["time_source"] = TimeSource(data["time_source"])
        data["kind"] = EventKind(data["kind"])
        return cls(**data)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat(timespec="seconds")


def _mtime(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _event(
    ref: RunRef, kind: EventKind, when: float | None, source: TimeSource, observed: float, **fields_
) -> UiEvent:
    if when is None:
        when, source = observed, TimeSource.OBSERVED
    return UiEvent(
        schema=EVENT_SCHEMA,
        event_id=0,  # numbered by the follower
        timestamp=_iso(when),
        time_source=source,
        run_kind=ref.kind.value,
        run_root=str(ref.root),
        run_id=ref.run_id,
        run_id_derived=ref.run_id_derived,
        target_id=ref.target,
        kind=kind,
        **fields_,
    )


def diff_snapshots(previous: RunSnapshot | None, current: RunSnapshot) -> list[UiEvent]:
    """The events between two snapshots of one run (everything new when ``previous`` is None)."""
    ref, now = current.ref, current.read_at
    events: list[UiEvent] = []
    old_progress = previous.progress if previous else None
    new_progress = current.progress

    # progress (live numbers only; other sources have no running numbers to report)
    if new_progress is not None and new_progress.source is Source.LIVE:
        changed = old_progress is None or (
            (old_progress.updated_at, old_progress.runs, old_progress.state)
            != (new_progress.updated_at, new_progress.runs, new_progress.state)
        )
        # the run's state first (it appeared / changed), then its numbers
        old_state = old_progress.state if old_progress else None
        if new_progress.state != old_state and new_progress.state is not None:
            events.append(
                _event(
                    ref,
                    EventKind.STATE_CHANGE,
                    new_progress.updated_at,
                    TimeSource.UPDATED_AT,
                    now,
                    status=new_progress.state,
                    message=f"{old_state or 'unknown'} -> {new_progress.state}",
                )  # fmt: skip
            )
        if changed:
            events.append(
                _event(
                    ref,
                    EventKind.PROGRESS,
                    new_progress.updated_at,
                    TimeSource.UPDATED_AT,
                    now,
                    status=new_progress.state,
                    progress_current=new_progress.runs,
                    progress_total=new_progress.budget,
                )  # fmt: skip
            )
    elif previous is None and current.summary is None and not current.replays:
        # an explore run with no live folder and no result yet: nothing the files can say
        events.append(
            _event(
                ref,
                EventKind.STATE_CHANGE,
                None,
                TimeSource.OBSERVED,
                now,
                status="unknown",
                message="no live progress for this run (only node-tar writes one)",
            )  # fmt: skip
        )

    # launcher step (an estimate, all four targets)
    old_step = old_progress.launcher_step if old_progress else None
    if new_progress is not None and new_progress.launcher_step not in (None, old_step):
        events.append(
            _event(
                ref,
                EventKind.LAUNCHER_STEP,
                _mtime(current.launcher_log),
                TimeSource.MTIME,
                now,
                status=new_progress.launcher_step,
                artifact_reference=str(current.launcher_log) if current.launcher_log else None,
                estimated=True,
            )  # fmt: skip
        )

    # violation cases (candidates), in run order
    seen = {row.case_id for row in previous.findings} if previous else set()
    for row in current.findings:
        if row.case_id in seen:
            continue
        when = _parse(row.recorded_at)
        events.append(
            _event(
                ref,
                EventKind.VIOLATION_CASE,
                when,
                TimeSource.RECORDED_AT,
                now,
                status=row.finding.value if row.finding else None,
                case_id=row.case_id,
                artifact_reference=str(row.input_path) if row.input_path else None,
                message="+".join(k.upper() for k, v in row.contracts.items() if v is True) or None,
            )  # fmt: skip
        )

    # result ready (once it parses)
    was_ready = (
        previous is not None and previous.summary is not None and previous.summary.has_values
    )
    summary = current.summary
    if summary is not None and summary.has_values and not was_ready:
        events.append(
            _event(
                ref,
                EventKind.RESULT_READY,
                _mtime(summary.result_path),
                TimeSource.MTIME,
                now,
                status="validated" if summary.validated else "as-stored",
                verdict=summary.verdict.value if summary.verdict else None,
                progress_current=summary.executed,
                artifact_reference=str(summary.result_path),
            )  # fmt: skip
        )

    # replays
    known = {str(r.path) for r in previous.replays} if previous else set()
    for record in current.replays:
        if str(record.path) in known or record.read_state is not ReadState.OK:
            continue
        events.append(
            _event(
                ref,
                EventKind.REPLAY_READY,
                _mtime(record.path),
                TimeSource.MTIME,
                now,
                status=record.conclusion.value if record.conclusion else None,
                progress_current=record.judged,
                progress_total=record.rounds_requested,
                artifact_reference=str(record.path),
            )  # fmt: skip
        )

    # read errors (a half-written result.json is "not ready", not an error)
    old_errors = set(previous.read_errors) if previous else set()
    for error in current.read_errors:
        if error in old_errors or "does not parse yet" in error:
            continue
        events.append(
            _event(ref, EventKind.READ_ERROR, None, TimeSource.OBSERVED, now, message=error)
        )
    return events


def _parse(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


class Subscription:
    """One subscriber's bounded queue. When full, the oldest event is dropped and counted."""

    def __init__(self, follower: RunFollower, maxsize: int) -> None:
        self._follower = follower
        self._queue: queue.Queue[UiEvent] = queue.Queue(maxsize=maxsize)
        self.dropped = 0
        self.closed = False

    def _put(self, event: UiEvent) -> None:
        while True:
            try:
                self._queue.put_nowait(event)
                return
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self.dropped += 1
                except queue.Empty:
                    continue

    def get(self, timeout: float | None = None) -> UiEvent | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.closed = True
        self._follower._unsubscribe(self)


class RunFollower:
    """Poll runs (given ``refs`` and/or found under ``roots``) and publish what changed.

    ``poll_once`` is synchronous (tests, one-shot readers); ``start`` runs it every ``interval``
    seconds on one daemon thread until ``stop``. Only the in-memory last snapshot per run is kept.
    """

    def __init__(
        self,
        refs: Iterable[RunRef] = (),
        roots: Iterable[Path] = (),
        *,
        interval: float = 1.0,
        clock: Callable[[], float] = time.time,
        reader: Callable[..., RunSnapshot] = read_run,
    ) -> None:
        if interval <= 0:
            raise ValueError("interval must be > 0")
        self._refs = list(refs)
        self._roots = [Path(r) for r in roots]
        self.interval = interval
        self._clock = clock
        self._reader = reader
        self._last: dict[str, RunSnapshot] = {}
        self._next_id = 1
        self._subscribers: list[Subscription] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _current_refs(self) -> list[RunRef]:
        refs = {ref.key: ref for ref in self._refs}
        if self._roots:
            for listing in discover_runs(self._roots):
                if listing.ref is not None:
                    refs.setdefault(listing.ref.key, listing.ref)
        return list(refs.values())

    def poll_once(self) -> list[UiEvent]:
        out: list[UiEvent] = []
        for ref in self._current_refs():
            snapshot = self._reader(ref, now=self._clock())
            for event in diff_snapshots(self._last.get(ref.key), snapshot):
                out.append(self._number(event))
            self._last[ref.key] = snapshot
        with self._lock:
            subscribers = list(self._subscribers)
        for event in out:
            for subscriber in subscribers:
                subscriber._put(event)
        return out

    def _number(self, event: UiEvent) -> UiEvent:
        numbered = UiEvent(**{**_fields(event), "event_id": self._next_id})
        self._next_id += 1
        return numbered

    def snapshots(self) -> dict[str, RunSnapshot]:
        return dict(self._last)

    def subscribe(self, maxsize: int = 1000) -> Subscription:
        subscription = Subscription(self, maxsize)
        with self._lock:
            self._subscribers.append(subscription)
        return subscription

    def _unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            if subscription in self._subscribers:
                self._subscribers.remove(subscription)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 -- a reader bug must not kill the follower thread
                pass
            self._stop.wait(self.interval)

    def start(self) -> RunFollower:
        if self._thread is not None:
            raise RuntimeError("RunFollower already started")
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="inodefence-ui-follow", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float | None = None) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 5 if timeout is None else timeout)
            self._thread = None


def _fields(event: UiEvent) -> dict[str, Any]:
    return {f.name: getattr(event, f.name) for f in fields(event)}


__all__ = [
    "EVENT_SCHEMA",
    "EventKind",
    "RunFollower",
    "Subscription",
    "TimeSource",
    "UiEvent",
    "diff_snapshots",
]

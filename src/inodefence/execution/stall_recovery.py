"""Re-execute one case after a Docker infrastructure stall, never recording it as a result.

The container backend stays fail-closed: a timed-out runtime call raises ``BackendError``,
and a start that times out returns a target-timeout outcome. Docker Desktop sometimes
stalls for 24-143 s (a start that never completes for one container, or every call of the
daemon at once). Without this module such a stall aborts the whole campaign, and in one
observed case it would have been recorded as a target ``timed_out`` result although the
target had exited after 0.107 s.

This module sits entirely in the caller layer, around one whole case attempt
(sandbox + identity probe + target container). It changes no Docker argument, timeout or
isolation flag, and adds no Docker call while nothing stalls. The principle is: **an
attempt is reclassified only on positive evidence of a stall; everything else keeps the
behavior the backend already has.**

* :class:`ObservedDockerClient` passes every call through unchanged and keeps a short
  journal of the current attempt (operation, container, timed-out flag, monotonic and
  realtime stamps, and the ``State`` subset of ``container inspect`` answers). It stores no
  argv and no target output.
* :func:`classify_target_timeout` judges a TIMED_OUT outcome by the daemon's *state* after
  the start deadline, never by comparing the client deadline with daemon timestamps (the
  host monotonic clock and the daemon VM clock disagree by several percent and the latter
  steps backward). Only two states are stall evidence: the container was still
  ``created`` (the start never completed), or it had already ``exited`` on its own with a
  daemon run time in ``[0, TARGET_TIMEOUT_STALL_MAX_RUNTIME_SECONDS]`` (the attach did not
  return). A target still running at the deadline, which the backend then killed, stays
  TIMED_OUT without any time comparison, and so does every other or unreadable state.
* :func:`is_stall_failure` treats a raised ``BackendError`` as a stall only when the
  attempt has at least one anomalous Docker call and every anomalous call timed out.
* :class:`StallRecovery` discards such an attempt and waits, at most
  ``STALL_ABSENCE_CONFIRM_SECONDS``, until the daemon answers "no such container" for every
  container the attempt created, using the backend's own owner-checked ``remove_owned``.
  Only then does it call the attempt again, which builds a new sandbox, run root, container
  name and container. A removed container cannot start later, and the old container's mount
  was confined to the old, already deleted run root, so nothing of the discarded attempt
  can reach the new one. The discarded attempt's oracle result is never recorded.

Anything else propagates unchanged. Beyond the bounds (``MAX_INFRA_RETRIES`` per case,
``MAX_INFRA_RETRIES_PER_CAMPAIGN`` per campaign, or an absence that cannot be confirmed)
the campaign aborts: a raised stall re-raises the backend's own exception, exactly as
before; a TIMED_OUT outcome reclassified as a stall raises a new ``runtime_call``
``BackendError``, where the backend alone would have recorded TIMED_OUT and continued. The
retry draws no randomness, so the campaign RNG and search path are those of a run without
the stall. Every discarded attempt becomes one record in :attr:`StallRecovery.events` and
one ``inodefence-infra-reexecution`` stderr line.
"""

import json
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from inodefence.evaluation.abort_classification import (
    MAX_INFRA_RETRIES,
    MAX_INFRA_RETRIES_PER_CAMPAIGN,
    RETRY_BACKOFF_BASE_SECONDS,
    RETRY_BACKOFF_CAP_SECONDS,
    STALL_ABSENCE_CONFIRM_SECONDS,
    TARGET_TIMEOUT_STALL_MAX_RUNTIME_SECONDS,
    InvalidReason,
    classify_abort_reason,
)

from .base import BackendError, OutputLimitError
from .container import _container_absent, remove_owned
from .docker_client import CommandResult, DockerClient

EVENT_SCHEMA = "inodefence-infra-reexecution-v1"
STDERR_PREFIX = "inodefence-infra-reexecution"
# A stall records its anomalous calls; a case makes about 22 calls, so this never truncates
# a normal attempt and bounds a pathological one. The record counts what it dropped.
MAX_RECORDED_CALLS = 64
_STATE_KEYS = ("Status", "Running", "Pid", "StartedAt", "FinishedAt")
_TIMESTAMP = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)\Z")
_ZERO_TIME_PREFIX = "0001-01-01T"


class TimeoutVerdict(StrEnum):
    """What the daemon's state says about a target-timeout outcome.

    Only START_NOT_COMPLETED and ATTACH_NOT_RETURNED are stall evidence; the other two keep
    the TIMED_OUT result unchanged.
    """

    TARGET_TIMEOUT = "target_timeout"
    START_NOT_COMPLETED = "start_not_completed"
    ATTACH_NOT_RETURNED = "attach_not_returned"
    UNDETERMINED = "undetermined"

    @property
    def is_stall(self) -> bool:
        return self in (TimeoutVerdict.START_NOT_COMPLETED, TimeoutVerdict.ATTACH_NOT_RETURNED)


@dataclass(frozen=True, slots=True)
class CallObservation:
    """One Docker call of the current attempt. No argv and no stdout are kept."""

    op: str
    container: str | None
    returncode: int
    timed_out: bool
    truncated: bool
    started_monotonic: float
    started_realtime: float
    seconds: float
    absent: bool = False
    error: str | None = None
    state: Mapping[str, object] | None = None

    @property
    def anomalous(self) -> bool:
        """Not routine: an exception, a time-out, truncation or an unexpected nonzero code.

        ``container start`` returns the target's exit status and ``container inspect`` of a
        removed container answers nonzero; both are routine.
        """
        if self.error is not None or self.timed_out or self.truncated:
            return True
        if self.returncode == 0 or self.op == "container start":
            return False
        return not self.absent

    def to_record(self) -> dict[str, object]:
        return {
            "op": self.op,
            "container": self.container,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "truncated": self.truncated,
            "started_monotonic": self.started_monotonic,
            "started_realtime": self.started_realtime,
            "seconds": self.seconds,
            "error": self.error,
        }


def _call_container(args: tuple[str, ...]) -> str | None:
    if args[:2] == ("container", "create"):
        return args[args.index("--name") + 1] if "--name" in args[:-1] else None
    if args[:1] == ("container",) and len(args) > 2:
        return args[-1]
    return None


def _inspect_state(result: CommandResult) -> Mapping[str, object] | None:
    if result.returncode != 0 or result.timed_out or result.truncated:
        return None
    try:
        state = json.loads(result.stdout)[0]["State"]
    except (ValueError, LookupError, TypeError):
        return None
    if not isinstance(state, dict):
        return None
    return {key: state[key] for key in _STATE_KEYS if key in state}


class ObservedDockerClient:
    """Pass every call through unchanged; journal the current attempt for stall decisions."""

    def __init__(
        self,
        inner: DockerClient,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        realtime: Callable[[], float] = time.time,
    ) -> None:
        self._inner = inner
        self._monotonic = monotonic
        self._realtime = realtime
        self._calls: list[CallObservation] = []

    @property
    def calls(self) -> tuple[CallObservation, ...]:
        return tuple(self._calls)

    def begin_attempt(self) -> None:
        """Forget the previous attempt; the journal only ever holds one attempt."""
        self._calls.clear()

    def created_names(self) -> tuple[str, ...]:
        """Container names requested by ``container create`` in the journal, in order."""
        names: list[str] = []
        for call in self._calls:
            if call.op == "container create" and call.container and call.container not in names:
                names.append(call.container)
        return tuple(names)

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        started_monotonic = self._monotonic()
        started_realtime = self._realtime()
        op = " ".join(args[:2])
        container = _call_container(args)
        try:
            result = self._inner.run(args, timeout)
        except Exception as error:
            self._calls.append(
                CallObservation(
                    op,
                    container,
                    -1,
                    False,
                    False,
                    started_monotonic,
                    started_realtime,
                    self._monotonic() - started_monotonic,
                    error=type(error).__name__,
                )
            )
            raise
        state = None
        absent = False
        if args[:2] == ("container", "inspect") and len(args) > 2:
            absent = _container_absent(result, args[2])
            state = _inspect_state(result)
        self._calls.append(
            CallObservation(
                op,
                container,
                result.returncode,
                result.timed_out,
                result.truncated,
                started_monotonic,
                started_realtime,
                self._monotonic() - started_monotonic,
                absent,
                None,
                state,
            )
        )
        return result


def first_anomaly(calls: Sequence[CallObservation]) -> CallObservation | None:
    return next((call for call in calls if call.anomalous), None)


def _never(value: object) -> bool:
    """Docker reports an unset StartedAt/FinishedAt as its zero time."""
    return isinstance(value, str) and value.startswith(_ZERO_TIME_PREFIX)


def _parse_timestamp(value: object) -> tuple[int, int] | None:
    """RFC 3339 with up to nanoseconds as (whole epoch seconds, nanoseconds)."""
    if not isinstance(value, str) or _never(value):
        return None
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        return None
    whole, fraction, zone = match.groups()
    try:
        moment = datetime.fromisoformat(whole + ("+00:00" if zone == "Z" else zone))
    except ValueError:
        return None
    return int(moment.timestamp()), int((fraction or "0").ljust(9, "0"))


def daemon_runtime_seconds(state: Mapping[str, object]) -> float | None:
    """``FinishedAt - StartedAt`` as measured by the daemon, or None when either is unset."""
    started = _parse_timestamp(state.get("StartedAt"))
    finished = _parse_timestamp(state.get("FinishedAt"))
    if started is None or finished is None:
        return None
    return (finished[0] - started[0]) + (finished[1] - started[1]) / 1e9


def classify_target_timeout(
    calls: Sequence[CallObservation],
    stall_max_runtime_seconds: float = TARGET_TIMEOUT_STALL_MAX_RUNTIME_SECONDS,
) -> tuple[TimeoutVerdict, float | None]:
    """Judge a TIMED_OUT outcome from the first inspect after the attempt's last start.

    * ``created``: the start never completed -> START_NOT_COMPLETED (stall).
    * running (``Running`` true / ``running``): the target was alive at the deadline and the
      backend killed it -> TARGET_TIMEOUT, with no time comparison at all.
    * ``exited`` with ``0 <= FinishedAt - StartedAt <= stall_max_runtime_seconds``: the
      target ended on its own long before the deadline but the attach did not return ->
      ATTACH_NOT_RETURNED (stall).
    * anything else (``exited`` with a longer or negative run time, a missing or unparsable
      timestamp, no start time-out, no readable inspect) -> TARGET_TIMEOUT or UNDETERMINED,
      both of which keep the TIMED_OUT result exactly as the backend recorded it.
    """
    starts = [index for index, call in enumerate(calls) if call.op == "container start"]
    if not starts or not calls[starts[-1]].timed_out:
        return TimeoutVerdict.UNDETERMINED, None
    start = calls[starts[-1]]
    state = next(
        (
            call.state
            for call in calls[starts[-1] + 1 :]
            if call.op == "container inspect" and call.container == start.container and call.state
        ),
        None,
    )
    if state is None:
        return TimeoutVerdict.UNDETERMINED, None
    status = state.get("Status")
    if status == "created":
        return TimeoutVerdict.START_NOT_COMPLETED, None
    if state.get("Running") is True or status == "running":
        return TimeoutVerdict.TARGET_TIMEOUT, None
    if status != "exited":
        return TimeoutVerdict.UNDETERMINED, None
    runtime = daemon_runtime_seconds(state)
    if runtime is None:
        return TimeoutVerdict.UNDETERMINED, None
    if 0 <= runtime <= stall_max_runtime_seconds:
        return TimeoutVerdict.ATTACH_NOT_RETURNED, runtime
    return TimeoutVerdict.TARGET_TIMEOUT, runtime


def _reason(error: BaseException) -> str:
    return f"{type(error).__module__}.{type(error).__qualname__}: {error}"


def is_stall_failure(error: BaseException, calls: Sequence[CallObservation]) -> bool:
    """A backend failure caused by Docker time-outs and by nothing else.

    True only when ``error`` is a ``BackendError`` (not an output-limit error), the attempt
    has at least one anomalous Docker call, and every anomalous call of the attempt timed
    out. Any anomaly of another kind (a nonzero answer that is not "no such container", a
    truncation, a broker exception) makes it no stall, so the failure propagates as before.
    A ``BackendError`` raised without any anomalous call (for example a policy mismatch)
    is no stall either. The backend retries no call itself, so a time-out it hit is never
    silently recovered inside the attempt. Evidence: in the 48 Stage A call logs of the
    HOST1 benchmark, 40 of the 41 anomalous calls were time-outs (container start 10,
    container inspect 30) and the remaining one was a slow (4.1 s) inspect with return code 0;
    no nonzero answer other than "no such container" occurred, so this rule misses none of
    the observed stalls.
    """
    if not isinstance(error, BackendError) or isinstance(error, OutputLimitError):
        return False
    anomalies = [call for call in calls if call.anomalous]
    return bool(anomalies) and all(call.timed_out and call.error is None for call in anomalies)


@dataclass(frozen=True, slots=True)
class AbsenceConfirmation:
    confirmed: bool
    started_monotonic: float
    started_realtime: float
    seconds: float
    probes: int
    stopped_by: str | None

    def to_record(self) -> dict[str, object]:
        return {
            "confirmed": self.confirmed,
            "started_monotonic": self.started_monotonic,
            "started_realtime": self.started_realtime,
            "seconds": self.seconds,
            "probes": self.probes,
            "stopped_by": self.stopped_by,
        }


def confirm_absent(
    client: ObservedDockerClient,
    names: Sequence[str],
    owner: str,
    *,
    bound_seconds: float = STALL_ABSENCE_CONFIRM_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    realtime: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> AbsenceConfirmation:
    """Remove (owner-checked) and verify absence of every named container within the bound.

    Each probe is one ``remove_owned`` call: it answers only after the daemon said "no such
    container". A probe is repeated only when it failed because of a timed-out call or
    because the daemon still listed the container after a successful removal; any other
    failure (an owner mismatch, a daemon error, a broker failure, or a non-``BackendError``
    exception such as malformed inspect output) stops at once and is reported, never
    raised. No new probe starts after the bound; one probe in flight may finish after it
    (at most five 10 s calls). Pauses between probes are the deterministic
    ``min(RETRY_BACKOFF_CAP_SECONDS, RETRY_BACKOFF_BASE_SECONDS * 2**i)`` (no RNG).
    """
    started_monotonic = monotonic()
    started_realtime = realtime()
    deadline = started_monotonic + bound_seconds
    probes = 0
    stopped_by: str | None = None
    for name in names:
        attempt = 0
        while True:
            if monotonic() >= deadline:
                stopped_by = "bound"
                break
            mark = len(client.calls)
            probes += 1
            try:
                remove_owned(client, name, owner)
            except BackendError:
                window = client.calls[mark:]
                timed_out = any(call.timed_out for call in window)
                others = [call for call in window if call.anomalous and not call.timed_out]
                removed_but_present = any(
                    call.op == "container rm" and not call.anomalous for call in window
                )
                if others or not (timed_out or removed_but_present):
                    stopped_by = "non_timeout_failure"
                    break
                sleep(min(RETRY_BACKOFF_CAP_SECONDS, RETRY_BACKOFF_BASE_SECONDS * 2**attempt))
                attempt += 1
                continue
            except Exception as error:
                stopped_by = f"exception:{type(error).__name__}"
                break
            break
        if stopped_by is not None:
            break
    return AbsenceConfirmation(
        stopped_by is None,
        started_monotonic,
        started_realtime,
        monotonic() - started_monotonic,
        probes,
        stopped_by,
    )


def _emit(record: dict[str, object]) -> None:
    """Stderr reaches the campaign log; stdout is the broker protocol channel."""
    try:
        print(STDERR_PREFIX + " " + json.dumps(record, sort_keys=True), file=sys.stderr, flush=True)
    except Exception:
        pass


@dataclass(slots=True)
class StallRecovery:
    """Run one case attempt and re-execute it after a recoverable Docker stall.

    ``client`` must be the client the execution backend uses, so its journal sees every
    call of the attempt. ``owner`` is the backend's owner label value. ``events`` holds
    one record per discarded attempt; ``action`` is ``reexecuted`` or the reason the
    campaign aborts instead. No record carries the discarded attempt's oracle result.
    """

    client: ObservedDockerClient
    owner: str
    max_case_retries: int = MAX_INFRA_RETRIES
    max_campaign_retries: int = MAX_INFRA_RETRIES_PER_CAMPAIGN
    absence_bound_seconds: float = STALL_ABSENCE_CONFIRM_SECONDS
    stall_max_runtime_seconds: float = TARGET_TIMEOUT_STALL_MAX_RUNTIME_SECONDS
    monotonic: Callable[[], float] = time.monotonic
    realtime: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    emit: Callable[[dict[str, object]], None] = _emit
    events: list[dict[str, object]] = field(default_factory=list, init=False)

    @property
    def reexecution_count(self) -> int:
        return sum(1 for event in self.events if event["action"] == "reexecuted")

    def run[T](
        self,
        attempt: Callable[[], T],
        *,
        timed_out: Callable[[T], bool],
        step_index: int,
        case_id: str,
    ) -> T:
        """Return the first attempt that is not a stall; otherwise raise (module docstring)."""
        for attempt_index in range(self.max_case_retries + 1):
            self.client.begin_attempt()
            attempt_monotonic = self.monotonic()
            attempt_realtime = self.realtime()
            failure: BaseException
            verdict: TimeoutVerdict | None = None
            runtime: float | None = None
            try:
                value = attempt()
            except Exception as error:
                calls = self.client.calls
                if not is_stall_failure(error, calls):
                    raise
                failure = error
                reason = classify_abort_reason(_reason(error)).value
            else:
                if not timed_out(value):
                    return value
                calls = self.client.calls
                verdict, runtime = classify_target_timeout(calls, self.stall_max_runtime_seconds)
                if not verdict.is_stall:
                    return value
                failure = BackendError(
                    "container runtime start stalled: target timeout outcome reclassified "
                    f"as an infrastructure stall ({verdict.value})"
                )
                reason = InvalidReason.RUNTIME_CALL.value
            anomaly = first_anomaly(calls)
            anomalous = [call.to_record() for call in calls if call.anomalous]
            record: dict[str, object] = {
                "schema": EVENT_SCHEMA,
                "case_id": case_id,
                "step_index": step_index,
                "attempt_index": attempt_index,
                "invalid_reason": reason,
                "error": _reason(failure)[:500],
                "timeout_reclassified": None if verdict is None else verdict.value,
                "daemon_runtime_seconds": runtime,
                "stall_call": None if anomaly is None else anomaly.to_record(),
                "anomalous_calls": anomalous[:MAX_RECORDED_CALLS],
                "anomalous_calls_dropped": max(0, len(anomalous) - MAX_RECORDED_CALLS),
                "attempt": {
                    "started_monotonic": attempt_monotonic,
                    "started_realtime": attempt_realtime,
                    "seconds": self.monotonic() - attempt_monotonic,
                    "docker_calls": len(calls),
                },
                "absence": None,
            }
            if attempt_index >= self.max_case_retries:
                action = "abort_case_bound"
            elif self.reexecution_count >= self.max_campaign_retries:
                action = "abort_campaign_bound"
            else:
                absence = confirm_absent(
                    self.client,
                    self.client.created_names(),
                    self.owner,
                    bound_seconds=self.absence_bound_seconds,
                    monotonic=self.monotonic,
                    realtime=self.realtime,
                    sleep=self.sleep,
                )
                record["absence"] = absence.to_record()
                action = "reexecuted" if absence.confirmed else "abort_absence_unconfirmed"
            record["action"] = action
            self.events.append(record)
            self.emit(record)
            if action != "reexecuted":
                raise failure
        raise AssertionError("stall recovery loop must return or raise")

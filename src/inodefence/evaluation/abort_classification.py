"""Shared vocabulary + classifier for native-campaign invalid/abort reasons (additive).

A native effect campaign stops when its producer raises. The controller records
the stop as an ``{"aborted": {...}}`` report stub carrying the raised ``reason``
string (``scripts/container_controller.py``), and the downstream determiner then
counts the whole cell as right-censored. Today every abort reason is lumped into a
single "fail-closed observation-integrity" bucket, even though the reasons have
very different causes and very different recovery stories. This module is the
single source of truth for the cross-lane vocabulary that distinguishes them:

* :class:`InvalidReason` -- the shared top-level category recorded in a
  report/summary ``invalid_reason`` field (observer lane records observer-side
  invalid steps with the same enum; the worker-pool lane records retry/invalid
  cases with it).
* :func:`classify_abort_reason` -- turn an abort *reason string* into a category.
* :class:`ResetFailureDetail` -- finer detail for the ``cleanup_reset`` category,
  used by the worker-pool reset verification (parallels the observer lane's
  ``observation_failures[].kind`` sub-reason).
* retry-policy constants -- ``MAX_INFRA_RETRIES`` and the backoff schedule, plus the
  Docker-stall bounds (``MAX_INFRA_RETRIES_PER_CAMPAIGN``, ``STALL_ABSENCE_CONFIRM_SECONDS``,
  ``TARGET_TIMEOUT_STALL_MAX_RUNTIME_SECONDS``).

Everything here is pure and read-only. It makes no runtime decision and changes no
behavior, and nothing here relaxes the isolation contract.

Category boundaries (disjoint by design; agreed with the observer and worker-pool lanes)
----------------------------------------------------------------------------------------
The decisive split: a *trustworthy run happened* (target executed SUCCESS and a
transport frame was captured) but the observation evidence failed integrity ->
``observer_integrity`` (observer lane owns it, never retried). A state-observer
``ObservationError`` during before/after capture also classifies as
``observer_integrity`` (its observation_capture sub-reason), not as an infra abort.
Otherwise the failure is on the harness/runtime side -> broker / cleanup_* (the
worker-pool lane may retry).
``rejected`` / ``failed`` / ``timed_out`` target outcomes are *results*, not aborts,
and are never recorded as invalid.

Trace of the infrastructure-abort paths (cause hypothesis + where to repro)
---------------------------------------------------------------------------
The reason string is usually the wrapped form ``"<module>.<qualname>: <message>"``
built by the producer (``scripts/run_effect_demo.py``), so classification matches
the harness-generated message *substring*, never an exact string.

1. ``broker`` -- ``"trusted Docker broker disconnected or returned invalid data"``
   Origin: ``StdioDockerClient.run`` (``execution/docker_client.py``) when the line
   read back from the trusted host broker over the controller's own stdin/stdout is
   empty or not the expected JSON response object. Cause hypothesis: the host-side
   broker (``scripts/container_host.py``) stopped answering or sent a short/garbled
   line on that pipe; because the channel *is* the controller process's stdio, the
   controller cannot reconnect in-process -- recovery is a worker/host relaunch plus
   resume from the retained ``.steps.jsonl``. Repro: interrupt/stall the host broker
   mid-campaign, or feed the client a truncated response line.

2. ``cleanup_inspect`` -- ``"container runtime cleanup inspect failed: ..."``
   Origin: ``remove_owned`` (``execution/container.py``) via ``checked(..., "cleanup
   inspect")`` -- the ``container inspect`` issued to decide ownership before removal
   returned nonzero/timed-out/truncated and was *not* a clean "no such object"
   absence. Cause hypothesis: a transient daemon hiccup or inspect timeout under load
   (WSL2 serializes per-step container creation, so high concurrency collapses -- see
   LOG 2026-10-31). The broker is still alive, so this is recoverable in-process.
   Repro: make a cleanup inspect time out or return a daemon error under concurrency.

3. ``cleanup_remove`` -- ``"container runtime remove failed: ..."``,
   ``"container removal could not be verified"``, or
   ``"refusing to remove a container owned by another invocation"``
   Origin: the removal tail of ``remove_owned`` (``execution/container.py``). Cause
   hypothesis: same transient daemon pressure as (2), on the ``rm`` call. Recoverable
   in-process. Repro: make the ``rm`` fail or leave the container present on the
   verifying inspect.

4. ``cleanup_reset`` -- the worker-pool's post-run reset verification found the
   reused controller volume subpath dirty (residual ``core-run-*`` or an unexpected
   path change). No single abort string: the worker-pool lane detects this directly
   and records the :class:`ResetFailureDetail`. Recoverable by recycling the worker.

5. ``runtime_call`` -- ``"container runtime <op> failed: ..."`` for every other operation
   (``create``, ``inspect``, ``image inspect``, ``wait``, ``version``, ``timeout kill``, ``timeout
   wait``). Origin: ``checked`` (``execution/container.py``). It says that a harness call to the
   runtime failed outside cleanup, not that the case was harmless or that the abort carries no
   information. It is not in :data:`INFRASTRUCTURE_REASONS`, so the worker pool never retries
   it (D21). The one exception is a Docker stall: when the attempt failed because of an
   unrecovered Docker time-out and no other kind of Docker failure,
   ``execution/stall_recovery.py`` re-executes the case under the stall constants below.
   A cleanup error replacing one of these still
   classifies as cleanup, because the reason names only the last error; ``error_chain`` keeps the
   first one.
"""

from enum import StrEnum


class InvalidReason(StrEnum):
    """Shared top-level category for an invalid/aborted native-campaign step."""

    OBSERVER_INTEGRITY = "observer_integrity"
    BROKER = "broker"
    CLEANUP_INSPECT = "cleanup_inspect"
    CLEANUP_REMOVE = "cleanup_remove"
    CLEANUP_RESET = "cleanup_reset"
    RUNTIME_CALL = "runtime_call"
    OTHER = "other"


class ResetFailureDetail(StrEnum):
    """Sub-reason for ``cleanup_reset`` (worker-pool reset verification)."""

    RESET_RESIDUAL = "reset_residual"
    RESET_OTHER_PATH_CHANGE = "reset_other_path_change"


# Categories for which the worker-pool lane may discard the worker and retry the same
# ArchiveCase. observer_integrity and other are explicitly NOT retried.
INFRASTRUCTURE_REASONS: frozenset[InvalidReason] = frozenset(
    {
        InvalidReason.BROKER,
        InvalidReason.CLEANUP_INSPECT,
        InvalidReason.CLEANUP_REMOVE,
        InvalidReason.CLEANUP_RESET,
    }
)

# Retry policy (owned here; the worker-pool lane consumes these constants).
# K retries => up to K+1 attempts per case. Two retries clears the transient WSL2
# daemon pressure that produces most cleanup aborts without masking a persistent break.
MAX_INFRA_RETRIES: int = 2
# Bounded exponential backoff schedule min(cap, base*2**i) before attempt i+1 (i from 0).
# The worker pool draws a full-jitter wait in [0, that value] from its worker-local RNG;
# execution/stall_recovery.py waits exactly that value between absence probes (no RNG).
# Kept small so a stuck host cannot stall a campaign.
RETRY_BACKOFF_BASE_SECONDS: float = 0.5
RETRY_BACKOFF_CAP_SECONDS: float = 4.0

# Docker infrastructure stalls (execution/stall_recovery.py). This reopens D040-D21 only for
# stalls, and only on positive stall evidence: a case attempt that raised because of an
# unrecovered Docker time-out (and no other kind of Docker failure), or whose TIMED_OUT
# outcome the daemon's state shows to be a stall, is discarded and the same case is
# re-executed in a new container and run root once the daemon reports every container of
# the attempt absent. INFRASTRUCTURE_REASONS above is unchanged: a runtime_call failure that
# is not such a stall is still never retried. Per case the bound is MAX_INFRA_RETRIES; these
# are the campaign bound and the two stall-specific limits.
MAX_INFRA_RETRIES_PER_CAMPAIGN: int = 8
# Observed stalls (HOST1 benchmark 2026-11-07/08) lasted 24-143 s; confirmation starts about
# 40 s after a stall begins (start 10 s + inspect 10 s + two cleanup inspects), so 180 s
# covers more than 1.5x the longest observed stall.
STALL_ABSENCE_CONFIRM_SECONDS: float = 180.0
# A start time-out whose container had already *exited on its own* (the backend did not kill
# it) is a stall (the attach did not return) only when the daemon's FinishedAt - StartedAt is
# in [0, this]; otherwise the TIMED_OUT result stays. A target still running at the deadline
# stays TIMED_OUT without any time comparison. 5.0 s is half the 10 s target timeout, chosen
# so that clock error cannot move a case across it in either direction: the client deadline
# runs on the host monotonic clock (7-9 % fast on HOST1, so it fires after about 9.2 real
# seconds) and daemon timestamps come from the Docker VM wall clock, observed stepping back
# 0.1-2.5 s about every 29 s. A target that finished just before the deadline therefore
# measures >= 7.5 s, and a fast exit whose attach stalled measures <= 2.6 s (0.107 s
# observed).
TARGET_TIMEOUT_STALL_MAX_RUNTIME_SECONDS: float = 5.0

# Ordered (harness message substring, category); first containment match wins.
# The phrases are the harness-generated messages from execution/docker_client.py and
# execution/container.py, not target output, so substring containment is safe against
# the wrapped "<module>.<qualname>: <message>" reason form.
_SIGNATURES: tuple[tuple[str, InvalidReason], ...] = (
    ("trusted Docker broker disconnected", InvalidReason.BROKER),
    ("container runtime cleanup inspect failed", InvalidReason.CLEANUP_INSPECT),
    ("container runtime remove failed", InvalidReason.CLEANUP_REMOVE),
    ("container removal could not be verified", InvalidReason.CLEANUP_REMOVE),
    ("refusing to remove a container owned by another invocation", InvalidReason.CLEANUP_REMOVE),
    ("evidence integrity failed", InvalidReason.OBSERVER_INTEGRITY),
    # A state-observer ObservationError during before/after capture: the target ran
    # but the observer (not the reader) failed, so the evidence is untrustworthy. The
    # producer wraps it as "<module>.ObservationError: <msg>", so the type name is
    # present. The observer lane records the observation_capture sub-reason.
    ("ObservationError", InvalidReason.OBSERVER_INTEGRITY),
    # Last on purpose: the cleanup operations above share this prefix and must win.
    ("container runtime ", InvalidReason.RUNTIME_CALL),
)


def classify_abort_reason(reason: str) -> InvalidReason:
    """Classify a native-campaign abort reason string into an :class:`InvalidReason`.

    Pure function. An unrecognized or empty reason classifies as ``OTHER``. Never
    returns ``CLEANUP_RESET`` (that category is detected by reset verification, not
    from an abort string).
    """
    if not isinstance(reason, str):
        raise TypeError("abort reason must be a string")
    for phrase, category in _SIGNATURES:
        if phrase in reason:
            return category
    return InvalidReason.OTHER


def is_infrastructure_abort(reason: str) -> bool:
    """True when the reason string is a broker or container-cleanup infrastructure abort.

    These are the aborts the audit recommends treating as a case-invalid +
    worker-reset + continue event rather than a whole-campaign abort. The pre-existing
    fail-closed ``observer_integrity`` class is excluded.
    """
    return classify_abort_reason(reason) in INFRASTRUCTURE_REASONS

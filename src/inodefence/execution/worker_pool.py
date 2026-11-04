"""Per-case sandbox reset verification + infra retry/recycle for a worker campaign.

This is the worker-pool lane's single implementation of the retry/recycle wrapper
(the runtime abort classifier and its record formats are owned by another lane and
imported, never re-spelled). It changes no isolation and runs no target itself: it
wraps the campaign's per-case producer so that, inside one ``produce_result`` call,

1. the case runs on the worker (a controller container pinned to one campaign),
2. the worker's reused volume is checked for a clean teardown, and
3. a transient *infrastructure* failure (a broker disconnect, a container cleanup
   failure, or a dirty reset) discards the worker, waits a bounded jittered backoff,
   and retries the *same* ``ArchiveCase`` -- up to ``MAX_INFRA_RETRIES`` times.

The retry loop lives entirely inside the single producer call and draws only from a
worker-local RNG, never the campaign's ``random.Random``. So the campaign's case
selection, operator choice and mutation are byte-identical whether or not a case was
retried -- which is exactly what the parity comparison (G1) checks, and keeps
``steps[]`` a valid-completed-step-only, byte-identical trajectory.

An observer evidence-integrity failure (``observer_integrity``) and any unrecognized
error (``other``) are *never* retried or hidden: they propagate unchanged, so the
observer lane keeps ownership of that fail-closed policy.

A case that is still failing after the retries is *abandoned*: the producer raises
:class:`CaseAbandoned` carrying the agreed invalid-case record, the campaign stops
(right-censored) with its completed steps retained, and the orchestration writes the
record to the campaign report's ``invalid_cases[]`` sibling stream. Whether an
abandoned case consumes a step index is this lane's call: it does not -- ``steps[]``
holds only valid completed steps, and ``step_index`` records how many valid steps
preceded the abandonment (a sort key), matching the observer lane's invalid-step
accounting.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from inodefence.evaluation.abort_classification import (
    INFRASTRUCTURE_REASONS,
    MAX_INFRA_RETRIES,
    RETRY_BACKOFF_BASE_SECONDS,
    RETRY_BACKOFF_CAP_SECONDS,
    InvalidReason,
    ResetFailureDetail,
    classify_abort_reason,
)
from inodefence.model import ArchiveCase, EffectRunResult

# A reused controller volume is clean when neither flag is set after a case.
RUN_PREFIX = "core-run-"


@dataclass(frozen=True, slots=True)
class ResetObservation:
    """Post-run verdict on a worker's reused volume, in the abort classifier's polarity.

    ``reset_residual``: a ``core-run-*`` directory survived the case. ``reset_other_path_change``:
    the volume's other top-level entries diverged from the worker's start-of-campaign
    baseline. A clean teardown has neither.
    """

    reset_residual: bool
    reset_other_path_change: bool

    def __post_init__(self) -> None:
        if type(self.reset_residual) is not bool or type(self.reset_other_path_change) is not bool:
            raise ValueError("reset observation flags must be booleans")

    @property
    def clean(self) -> bool:
        return not self.reset_residual and not self.reset_other_path_change

    @property
    def detail(self) -> ResetFailureDetail | None:
        """The single sub-reason to record; residual takes priority when both hold."""
        if self.reset_residual:
            return ResetFailureDetail.RESET_RESIDUAL
        if self.reset_other_path_change:
            return ResetFailureDetail.RESET_OTHER_PATH_CHANGE
        return None


def verify_reset(baseline: frozenset[str], current: frozenset[str]) -> ResetObservation:
    """Compare a worker volume's top-level entries after a case against its baseline.

    ``baseline`` is the set of non-run entries captured at worker start (a dedicated
    volume is usually empty). ``current`` is the whole top-level listing after the
    case. Residual is any surviving ``core-run-*``; other-path change is any
    difference in the non-run entries from the baseline.
    """
    residual = any(name.startswith(RUN_PREFIX) for name in current)
    others = frozenset(name for name in current if not name.startswith(RUN_PREFIX))
    return ResetObservation(residual, others != baseline)


class ResetObserver:
    """Reads a worker volume's top-level listing and compares it to the baseline.

    ``list_top_level`` returns the current top-level names under the worker's runtime
    volume (the controller's mounted ``RUNTIME_BASE``); it is injected so the check is
    pure and testable without Docker. The baseline is captured once at worker start.
    """

    def __init__(self, list_top_level: Callable[[], frozenset[str]]) -> None:
        self._list = list_top_level
        self._baseline = frozenset(
            name for name in list_top_level() if not name.startswith(RUN_PREFIX)
        )

    @property
    def baseline(self) -> frozenset[str]:
        return self._baseline

    def observe(self) -> ResetObservation:
        return verify_reset(self._baseline, frozenset(self._list()))


class WorkerHandle:
    """A controller container + dedicated volume pinned to one campaign.

    ``recycle`` tears the worker down and brings an identical one back up (same image
    digest, same isolation flags, a fresh dedicated volume). The concrete Docker-backed
    handle reuses the existing controller/volume bring-up; it runs only on a Docker host
    and is not exercised by the no-Docker unit tests.
    """

    @property
    def worker_id(self) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def recycle(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class InfraRetry:
    """One failed-then-retried attempt, recorded on the step that finally succeeded."""

    attempt_index: int
    reason: InvalidReason
    detail: ResetFailureDetail | None
    worker_id: str

    def __post_init__(self) -> None:
        if type(self.attempt_index) is not int or self.attempt_index < 0:
            raise ValueError("attempt_index must be a nonnegative integer")
        if not isinstance(self.reason, InvalidReason):
            raise ValueError("reason must be an InvalidReason")
        if self.detail is not None and not isinstance(self.detail, ResetFailureDetail):
            raise ValueError("detail must be a ResetFailureDetail or None")
        if not isinstance(self.worker_id, str) or not self.worker_id:
            raise ValueError("worker_id must be nonempty text")

    def to_record(self) -> dict[str, object]:
        return {
            "attempt_index": self.attempt_index,
            "reason": self.reason.value,
            "detail": None if self.detail is None else self.detail.value,
            "worker_id": self.worker_id,
        }


@dataclass(frozen=True, slots=True)
class InvalidCase:
    """A case abandoned after exhausting retries; recorded in ``invalid_cases[]``."""

    case_id: str
    step_index: int
    invalid_reason: InvalidReason
    invalid_detail: ResetFailureDetail | None
    attempts: int
    final_worker_id: str
    validity: str = "invalid"

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("invalid case requires a case id")
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("step_index must be a nonnegative integer")
        if not isinstance(self.invalid_reason, InvalidReason):
            raise ValueError("invalid_reason must be an InvalidReason")
        if self.invalid_detail is not None and not isinstance(
            self.invalid_detail, ResetFailureDetail
        ):
            raise ValueError("invalid_detail must be a ResetFailureDetail or None")
        if type(self.attempts) is not int or self.attempts < 1:
            raise ValueError("attempts must be a positive integer")
        if not isinstance(self.final_worker_id, str) or not self.final_worker_id:
            raise ValueError("final_worker_id must be nonempty text")
        if self.validity != "invalid":
            raise ValueError("validity must be 'invalid'")

    def to_record(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "step_index": self.step_index,
            "validity": self.validity,
            "invalid_reason": self.invalid_reason.value,
            "invalid_detail": None if self.invalid_detail is None else self.invalid_detail.value,
            "attempts": self.attempts,
            "final_worker_id": self.final_worker_id,
        }


class CaseAbandoned(Exception):
    """Raised by the producer when a case is still failing after the retries.

    Carries the agreed :class:`InvalidCase` record. The campaign stops (right-censored)
    with its completed steps retained; the orchestration records ``invalid_case``.
    """

    def __init__(self, invalid_case: InvalidCase) -> None:
        super().__init__(
            f"case {invalid_case.case_id} abandoned after {invalid_case.attempts} attempts "
            f"({invalid_case.invalid_reason.value})"
        )
        self.invalid_case = invalid_case


def _reason_string(error: BaseException) -> str:
    """The wrapped reason form the native producer records, for classification."""
    return f"{type(error).__module__}.{type(error).__qualname__}: {error}"


@dataclass(slots=True)
class ResettingProducer:
    """Wrap a per-case producer with reset verification and infra retry/recycle.

    ``inner`` is the campaign's producer (``ArchiveCase -> EffectRunResult``).
    ``worker`` is recycled between retries. ``reset_observer`` verifies the volume
    after each attempt. ``completed_step_count`` returns how many valid steps the
    campaign has recorded so far (``lambda: len(steps)``), used for an abandoned case's
    ``step_index``. ``rng`` is worker-local and is the *only* RNG this wrapper draws
    from; it never touches the campaign RNG.
    """

    inner: Callable[[ArchiveCase], EffectRunResult]
    worker: WorkerHandle
    reset_observer: ResetObserver
    completed_step_count: Callable[[], int] = lambda: 0
    max_retries: int = MAX_INFRA_RETRIES
    backoff_base: float = RETRY_BACKOFF_BASE_SECONDS
    backoff_cap: float = RETRY_BACKOFF_CAP_SECONDS
    sleep: Callable[[float], None] = time.sleep
    rng: random.Random = field(default_factory=random.Random)
    _retry_log: dict[str, tuple[InfraRetry, ...]] = field(default_factory=dict, init=False)

    def retries_for(self, case_id: str) -> tuple[InfraRetry, ...]:
        """The infra retries that preceded the successful run of ``case_id`` (else ())."""
        return self._retry_log.get(case_id, ())

    def __call__(self, case: ArchiveCase) -> EffectRunResult:
        retries: list[InfraRetry] = []
        for attempt in range(self.max_retries + 1):
            outcome = self._attempt(case)
            if isinstance(outcome, EffectRunResult):
                self._retry_log[case.case_id] = tuple(retries)
                return outcome
            reason, detail = outcome
            if attempt >= self.max_retries:
                raise CaseAbandoned(
                    InvalidCase(
                        case_id=case.case_id,
                        step_index=self.completed_step_count(),
                        invalid_reason=reason,
                        invalid_detail=detail,
                        attempts=attempt + 1,
                        final_worker_id=self.worker.worker_id,
                    )
                )
            retries.append(InfraRetry(attempt, reason, detail, self.worker.worker_id))
            self._backoff(attempt)
            self.worker.recycle()
        raise AssertionError("retry loop must return or raise")

    def _attempt(
        self, case: ArchiveCase
    ) -> EffectRunResult | tuple[InvalidReason, ResetFailureDetail | None]:
        """Run one attempt: a result, or an infra ``(reason, detail)`` to retry.

        Non-infrastructure failures (observer_integrity, other) propagate unchanged.
        """
        try:
            result = self.inner(case)
        except Exception as error:
            reason = classify_abort_reason(_reason_string(error))
            if reason not in INFRASTRUCTURE_REASONS:
                raise
            return (reason, None)
        observation = self.reset_observer.observe()
        if observation.clean:
            return result
        return (InvalidReason.CLEANUP_RESET, observation.detail)

    def _backoff(self, attempt: int) -> None:
        """Full-jitter wait in ``[0, min(cap, base * 2**attempt)]`` from the worker RNG."""
        ceiling = min(self.backoff_cap, self.backoff_base * (2**attempt))
        self.sleep(self.rng.uniform(0.0, ceiling))

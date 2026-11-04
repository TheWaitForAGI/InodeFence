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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_demo import EffectStepReporter
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
from inodefence.runtime import RUNTIME_BASE

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


# ---------------------------------------------------------------------------
# Campaign orchestration wiring and host-side bring-up planning.
#
# Honest scope note (agreed with the orchestrator, verifier note): the campaign
# loop runs *inside* one controller container, and ``run_parallel_native`` already
# gives each campaign its own controller + dedicated volume. So this worker pool's
# real increment is per-case reset verification + in-controller infrastructure
# retry (cleanup_inspect / cleanup_remove / cleanup_reset), NOT a persistent fleet
# of pre-started workers. A ``broker`` failure kills the controller's channel; its
# host relaunch + resume-from-``.steps.jsonl`` is deferred past G1, so a broker
# failure right-censors the campaign (the completed steps are retained). The
# audit's "N pre-started workers" wording differs from this on purpose.
#
# Reset condition coverage (verifier note): ``verify_reset`` covers volume-path
# residue only. The other reset condition -- that no owned-label target container
# survives a case -- is enforced by the execution backend's ``remove_owned`` (it
# verifies absence and raises on failure, classified ``cleanup_remove``), so it is
# retried through the same path without being re-checked here.
# ---------------------------------------------------------------------------

WORKER_RUN_PREFIX = "s3wp-"
CONTROLLER_NAME_STEM = "inodefence-local-controller"
VOLUME_NAME_STEM = "inodefence-local-runtime"
CAMPAIGN_WATCHDOG_SECONDS: float = 2 * 60 * 60
DISK_PAUSE_FRACTION: float = 0.9


def worker_run_id(cell_run_id: str) -> str:
    """Prefix a parallel-matrix cell id with the worker-pool run tag."""
    if not isinstance(cell_run_id, str) or not cell_run_id:
        raise ValueError("cell run id must be nonempty")
    return f"{WORKER_RUN_PREFIX}{cell_run_id}"


def controller_name(run_id: str) -> str:
    """The dedicated controller container name for a worker (mirrors the smoke script)."""
    return f"{CONTROLLER_NAME_STEM}-{run_id}"


def volume_name(run_id: str) -> str:
    """The dedicated runtime volume name for a worker (no write path shared between workers)."""
    return f"{VOLUME_NAME_STEM}-{run_id}"


def campaign_deadline_exceeded(
    elapsed_seconds: float, limit: float = CAMPAIGN_WATCHDOG_SECONDS
) -> bool:
    """Whether a campaign has run past the watchdog limit and should be stopped."""
    return elapsed_seconds >= limit


def should_pause_for_disk(usage_fraction: float, threshold: float = DISK_PAUSE_FRACTION) -> bool:
    """Whether the runtime volume is full enough that new cases should pause."""
    return usage_fraction >= threshold


@dataclass(frozen=True, slots=True)
class WorkerBringup:
    """The planned bring-up of one worker: dedicated controller + volume + mount.

    ``env`` is the per-campaign environment the existing ``run_parallel_native`` path
    sets (RUN_ID, DEMO_SEED, ...). This is a plan for ``--dry-run`` and is never a
    command that runs here; Docker is launched only on a host with an assigned slot.
    """

    run_id: str
    controller: str
    volume: str
    mount_target: str
    env: tuple[tuple[str, str], ...]

    def describe(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "controller": self.controller,
            "volume": self.volume,
            "mount": f"{self.volume} -> {self.mount_target} (per-case subpath)",
            "env": dict(self.env),
        }


def plan_worker_bringup(cell_run_id: str, env: dict[str, str]) -> WorkerBringup:
    """Plan one worker's bring-up from a matrix cell id and its campaign environment."""
    run_id = worker_run_id(cell_run_id)
    worker_env = dict(env)
    worker_env["RUN_ID"] = run_id
    return WorkerBringup(
        run_id=run_id,
        controller=controller_name(run_id),
        volume=volume_name(run_id),
        mount_target=str(RUNTIME_BASE),
        env=tuple(sorted(worker_env.items())),
    )


def run_worker_campaign(
    initial_cases: Sequence[ArchiveCase],
    inner_producer: Callable[[ArchiveCase], EffectRunResult],
    config: EffectCampaignConfig,
    worker: WorkerHandle,
    reset_observer: ResetObserver,
    *,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> dict[str, object]:
    """Drive one campaign through the reset/retry wrapper, recording the agreed fields.

    Returns a report fragment: ``steps`` (valid completed step records, each carrying
    ``infra_retries`` only when the case needed one) and ``invalid_cases`` (at most one,
    present when a case was abandoned and the campaign was right-censored). The campaign
    RNG lives in ``run_effect_campaign`` (seeded from ``config``); ``rng`` here is only the
    worker-local backoff RNG, so the step trajectory is identical with or without retries.
    """
    reporter = EffectStepReporter()
    steps: list[dict[str, object]] = []
    producer = ResettingProducer(
        inner_producer,
        worker,
        reset_observer,
        completed_step_count=lambda: len(steps),
        sleep=sleep,
        rng=rng if rng is not None else random.Random(),
    )
    invalid_cases: list[dict[str, object]] = []

    def on_step(step: object) -> None:
        record = reporter.add(step)  # type: ignore[arg-type]
        case_id = step.result.base_result.case.case_id  # type: ignore[attr-defined]
        retries = producer.retries_for(case_id)
        if retries:
            record["infra_retries"] = [retry.to_record() for retry in retries]
        steps.append(record)

    try:
        run_effect_campaign(initial_cases, producer, config, on_step=on_step)
    except CaseAbandoned as abandoned:
        invalid_cases.append(abandoned.invalid_case.to_record())
    return {"steps": steps, "invalid_cases": invalid_cases}


def measurement_runners(jobs: int) -> tuple[object, object]:
    """Return the per-case and worker-pool method runners the throughput script expects.

    Each runner executes the matrix under one method and returns its timing plus the
    per-cell parity subjects the throughput report compares. That comparison needs the
    parity/throughput analysis modules (``evaluation.execution_parity`` /
    ``evaluation.throughput``), which arrive on the integration base (main + the parity
    PR + this stack), and executing either runner launches Docker on an assigned slot.
    This stacked PR ships the interface only; the executors are wired on the integration
    base, so the throughput script's test and this one guard on the analysis modules
    being importable (``pytest.importorskip``).
    """
    raise NotImplementedError(
        "measurement_runners executes campaigns under Docker; wire the per-case and "
        "worker-pool executors on the integration base (claude/s3-wp-integration) and "
        "run only with an assigned Docker slot"
    )

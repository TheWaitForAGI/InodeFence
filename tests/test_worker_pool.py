"""Unit tests for the worker-pool reset/retry/recycle wrapper (no Docker)."""

import random

import pytest

from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.abort_classification import InvalidReason, ResetFailureDetail
from inodefence.execution.base import BackendError
from inodefence.execution.worker_pool import (
    CaseAbandoned,
    InfraRetry,
    InvalidCase,
    ResetObservation,
    ResetObserver,
    ResettingProducer,
    WorkerHandle,
    verify_reset,
)
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.observer.snapshot import ObservationError

CASE = ArchiveCase((ArchiveEntry("a.txt", EntryType.REGULAR, content=b"x"),))
BROKER_MSG = "trusted Docker broker disconnected or returned invalid data"


class FakeWorker(WorkerHandle):
    def __init__(self) -> None:
        self.recycles = 0

    @property
    def worker_id(self) -> str:
        return f"w{self.recycles}"

    def recycle(self) -> None:
        self.recycles += 1


class FlakyInner:
    """Raises the queued exceptions on successive calls, then returns a synthetic result."""

    def __init__(self, *failures: Exception | None) -> None:
        self._failures = list(failures)
        self.calls = 0

    def __call__(self, case: ArchiveCase):
        self.calls += 1
        if self._failures:
            exc = self._failures.pop(0)
            if exc is not None:
                raise exc
        return synthetic_effect_result(case)


def _clean_observer() -> ResetObserver:
    return ResetObserver(lambda: frozenset())


def _scripted_observer(*listings: frozenset[str]) -> ResetObserver:
    stream = iter(listings)
    return ResetObserver(lambda: next(stream))


def _producer(inner, worker, observer, **kw) -> ResettingProducer:
    kw.setdefault("sleep", lambda _: None)
    kw.setdefault("rng", random.Random(0))
    return ResettingProducer(inner, worker, observer, **kw)


# ---- happy path --------------------------------------------------------------


def test_clean_run_returns_without_retry() -> None:
    worker = FakeWorker()
    producer = _producer(FlakyInner(), worker, _clean_observer())
    result = producer(CASE)
    assert result.base_result.case.case_id == CASE.case_id
    assert producer.retries_for(CASE.case_id) == ()
    assert worker.recycles == 0


# ---- infrastructure retries --------------------------------------------------


def test_broker_failure_retries_then_succeeds() -> None:
    worker = FakeWorker()
    producer = _producer(FlakyInner(BackendError(BROKER_MSG)), worker, _clean_observer())
    result = producer(CASE)
    assert result.base_result.case.case_id == CASE.case_id
    retries = producer.retries_for(CASE.case_id)
    assert len(retries) == 1
    assert retries[0].attempt_index == 0
    assert retries[0].reason is InvalidReason.BROKER
    assert retries[0].detail is None
    assert retries[0].worker_id == "w0"
    assert worker.recycles == 1


def test_dirty_reset_retries_then_clean() -> None:
    worker = FakeWorker()
    # baseline empty, then a residual run dir survives, then clean.
    observer = _scripted_observer(frozenset(), frozenset({"core-run-abc"}), frozenset())
    producer = _producer(FlakyInner(), worker, observer)
    producer(CASE)
    retries = producer.retries_for(CASE.case_id)
    assert len(retries) == 1
    assert retries[0].reason is InvalidReason.CLEANUP_RESET
    assert retries[0].detail is ResetFailureDetail.RESET_RESIDUAL
    assert worker.recycles == 1


# ---- non-infrastructure failures are never retried or hidden -----------------


def test_observer_integrity_propagates_unretried() -> None:
    worker = FakeWorker()
    producer = _producer(
        FlakyInner(ObservationError("incomplete snapshot")), worker, _clean_observer()
    )
    with pytest.raises(ObservationError):
        producer(CASE)
    assert worker.recycles == 0
    assert producer.retries_for(CASE.case_id) == ()


def test_evidence_integrity_message_propagates_unretried() -> None:
    worker = FakeWorker()
    producer = _producer(
        FlakyInner(RuntimeError("evidence integrity failed after target success")),
        worker,
        _clean_observer(),
    )
    with pytest.raises(RuntimeError):
        producer(CASE)
    assert worker.recycles == 0


def test_unrecognized_error_propagates_unretried() -> None:
    worker = FakeWorker()
    producer = _producer(FlakyInner(ValueError("unexpected")), worker, _clean_observer())
    with pytest.raises(ValueError):
        producer(CASE)
    assert worker.recycles == 0


# ---- abandonment after the retry budget --------------------------------------


def test_abandoned_after_max_retries() -> None:
    worker = FakeWorker()
    inner = FlakyInner(*(BackendError(BROKER_MSG) for _ in range(5)))
    producer = _producer(inner, worker, _clean_observer(), completed_step_count=lambda: 5)
    with pytest.raises(CaseAbandoned) as excinfo:
        producer(CASE)
    invalid = excinfo.value.invalid_case
    assert invalid.attempts == 3  # MAX_INFRA_RETRIES (2) + 1
    assert invalid.invalid_reason is InvalidReason.BROKER
    assert invalid.step_index == 5
    assert invalid.final_worker_id == "w2"
    assert worker.recycles == 2


# ---- RNG invariance: backoff draws only from the worker-local RNG ------------


def test_backoff_bounded_and_deterministic_from_worker_rng() -> None:
    waits_a: list[float] = []
    waits_b: list[float] = []
    for waits in (waits_a, waits_b):
        worker = FakeWorker()
        inner = FlakyInner(BackendError(BROKER_MSG), BackendError(BROKER_MSG))
        producer = ResettingProducer(
            inner, worker, _clean_observer(), sleep=waits.append, rng=random.Random(1234)
        )
        producer(CASE)
    assert waits_a == waits_b  # same worker-local seed => identical backoff schedule
    # Full-jitter ceilings: attempt 0 in [0, 0.5], attempt 1 in [0, 1.0].
    assert 0.0 <= waits_a[0] <= 0.5
    assert 0.0 <= waits_a[1] <= 1.0


def test_producer_does_not_accept_a_campaign_rng() -> None:
    # The wrapper has no parameter that could couple it to the campaign RNG; its only
    # RNG is the worker-local `rng`. This guards the parity-critical invariant.
    import dataclasses

    names = {f.name for f in dataclasses.fields(ResettingProducer)}
    assert "rng" in names
    assert not any("campaign" in name for name in names)


# ---- reset verification ------------------------------------------------------


def test_verify_reset_detects_residual_and_other_change() -> None:
    base = frozenset({"outside"})
    assert verify_reset(base, frozenset({"outside"})).clean
    assert verify_reset(base, frozenset({"outside", "core-run-x"})).reset_residual
    assert verify_reset(base, frozenset({"outside", "extra"})).reset_other_path_change


def test_reset_observer_baseline_excludes_run_dirs() -> None:
    observer = ResetObserver(lambda: frozenset({"core-run-seed", "keep"}))
    assert observer.baseline == frozenset({"keep"})


def test_reset_observation_detail_priority() -> None:
    assert ResetObservation(True, True).detail is ResetFailureDetail.RESET_RESIDUAL
    assert ResetObservation(False, True).detail is ResetFailureDetail.RESET_OTHER_PATH_CHANGE
    assert ResetObservation(False, False).detail is None


# ---- record shapes agreed with the runtime abort classifier lane -------------


def test_infra_retry_record_shape() -> None:
    record = InfraRetry(1, InvalidReason.CLEANUP_INSPECT, None, "w1").to_record()
    assert record == {
        "attempt_index": 1,
        "reason": "cleanup_inspect",
        "detail": None,
        "worker_id": "w1",
    }


def test_invalid_case_record_shape() -> None:
    record = InvalidCase(
        "cid", 3, InvalidReason.CLEANUP_RESET, ResetFailureDetail.RESET_RESIDUAL, 3, "w2"
    ).to_record()
    assert record == {
        "case_id": "cid",
        "step_index": 3,
        "validity": "invalid",
        "invalid_reason": "cleanup_reset",
        "invalid_detail": "reset_residual",
        "attempts": 3,
        "final_worker_id": "w2",
    }


def test_record_validation_rejects_bad_values() -> None:
    with pytest.raises(ValueError):
        InfraRetry(-1, InvalidReason.BROKER, None, "w0")
    with pytest.raises(ValueError):
        InvalidCase("cid", 0, InvalidReason.BROKER, None, 0, "w0")


# ---- reset observation recording (both paths) --------------------------------


def test_resetting_producer_records_clean_reset_observations() -> None:
    worker = FakeWorker()
    producer = _producer(FlakyInner(), worker, _clean_observer())
    producer(CASE)
    assert len(producer.reset_observations) == 1
    assert producer.reset_observations[0].clean is True


def test_reset_observing_producer_records_and_reraises() -> None:
    from inodefence.execution.worker_pool import NoRecycleWorker, ResetObservingProducer

    observer = _clean_observer()
    good = ResetObservingProducer(FlakyInner(), observer)
    good(CASE)
    assert len(good.reset_observations) == 1

    # Baseline wrapper never retries: an infra failure propagates unchanged.
    bad = ResetObservingProducer(FlakyInner(BackendError(BROKER_MSG)), observer)
    with pytest.raises(BackendError):
        bad(CASE)
    assert len(bad.reset_observations) == 0

    worker = NoRecycleWorker()
    assert worker.worker_id == "in-controller"
    assert worker.recycle() is None

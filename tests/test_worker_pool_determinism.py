"""Part 4: campaign-level trajectory determinism under infra retries (no Docker).

The worker_pool unit tests prove ``ResettingProducer`` draws only from a worker-local
RNG and has no campaign-RNG parameter. This integration test proves the *consequence*
at the campaign level: wiring ``ResettingProducer`` into ``run_effect_campaign``, the
whole mutation trajectory -- seed order, case selection, operator choice, and the
produced case ids -- is byte-identical whether or not mid-campaign infrastructure
faults trigger retries and worker recycles. That is the parity-critical (G1) guarantee
that keeps ``steps[]`` a byte-identical, valid-completed-step-only trajectory, and that
an abandoned case stops the campaign (right-censored) with a deterministic completed
prefix. Everything here runs without Docker via injected fakes.
"""

import random

import pytest

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.abort_classification import InvalidReason
from inodefence.execution.base import BackendError
from inodefence.execution.worker_pool import (
    CaseAbandoned,
    ResetObserver,
    ResettingProducer,
    WorkerHandle,
)
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.mutator import MutationPolicy

CONFIG = EffectCampaignConfig(
    random_seed=123,
    execution_budget=12,
    search_policy=EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
    mutation_policy=MutationPolicy.M1,
)


def _trajectory(steps) -> list[tuple]:
    """The RNG-driven decisions of a campaign: origin, parent, produced id, operator.

    Accepts either ``result.steps`` or the ``EffectCampaignStep`` list an ``on_step``
    sink collected, so a completed prefix and a full run compare with the same shape.
    """
    return [
        (
            step.index,
            step.origin,
            step.parent_case_id,
            step.result.base_result.case.case_id,
            None if step.mutation_attempt is None else step.mutation_attempt.operator_id,
        )
        for step in steps
    ]


class _FakeWorker(WorkerHandle):
    """A recyclable worker whose id changes on each recycle (no Docker)."""

    def __init__(self) -> None:
        self._n = 0
        self.recycles = 0

    @property
    def worker_id(self) -> str:
        return f"w{self._n}"

    def recycle(self) -> None:
        self._n += 1
        self.recycles += 1


class _FaultingInner:
    """Producer raising an infra error on the first ``k`` attempts of each case id.

    ``faults`` counts the raises so a test can assert retries actually fired (a case id
    the campaign reproduces later is already past its first ``k`` attempts and is not
    re-faulted, so the count tracks recycles rather than the step total).
    """

    def __init__(self, k: int) -> None:
        self.k = k
        self.faults = 0
        self._seen: dict[str, int] = {}

    def __call__(self, case):
        n = self._seen.get(case.case_id, 0)
        self._seen[case.case_id] = n + 1
        if n < self.k:
            self.faults += 1
            raise BackendError("trusted Docker broker disconnected or returned invalid data")
        return synthetic_effect_result(case)


def _clean_observer() -> ResetObserver:
    # Empty top-level listing => baseline empty, every observation clean.
    return ResetObserver(lambda: frozenset())


def test_resetting_producer_is_trajectory_transparent_without_faults() -> None:
    baseline = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)
    producer = ResettingProducer(
        _FaultingInner(0),
        _FakeWorker(),
        _clean_observer(),
        sleep=lambda _s: None,
        rng=random.Random(0),
    )
    wrapped = run_effect_campaign(minimal_seed_corpus(), producer, CONFIG)
    assert _trajectory(wrapped.steps) == _trajectory(baseline.steps)


def test_campaign_trajectory_identical_under_infra_retries() -> None:
    baseline = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)

    inner = _FaultingInner(1)  # every distinct case fails once (broker), then succeeds
    worker = _FakeWorker()
    producer = ResettingProducer(
        inner, worker, _clean_observer(), sleep=lambda _s: None, rng=random.Random(0)
    )
    faulted = run_effect_campaign(minimal_seed_corpus(), producer, CONFIG)

    # Retries actually fired, and each fault drove exactly one worker recycle...
    assert inner.faults > 0
    assert worker.recycles == inner.faults
    # ...yet the campaign's RNG-driven trajectory is byte-identical to the no-fault run.
    assert _trajectory(faulted.steps) == _trajectory(baseline.steps)


def test_abandoned_case_stops_campaign_right_censored_with_deterministic_prefix() -> None:
    baseline = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)

    successes = {"count": 0}
    stop_after = 6  # the 7th requested case fails every attempt and is abandoned

    def inner(case):
        if successes["count"] >= stop_after:
            raise BackendError("trusted Docker broker disconnected or returned invalid data")
        successes["count"] += 1
        return synthetic_effect_result(case)

    completed: list = []
    worker = _FakeWorker()
    producer = ResettingProducer(
        inner,
        worker,
        _clean_observer(),
        completed_step_count=lambda: len(completed),
        sleep=lambda _s: None,
        rng=random.Random(0),
    )

    with pytest.raises(CaseAbandoned) as excinfo:
        run_effect_campaign(minimal_seed_corpus(), producer, CONFIG, on_step=completed.append)

    invalid = excinfo.value.invalid_case
    assert invalid.validity == "invalid"
    assert invalid.invalid_reason == InvalidReason.BROKER
    assert invalid.invalid_detail is None
    assert invalid.attempts == producer.max_retries + 1
    # Only the infra retries of the abandoned case recycle the worker.
    assert worker.recycles == producer.max_retries
    # The abandoned case produced no step; step_index = completed valid steps so far.
    assert invalid.step_index == len(completed) == stop_after
    # The retained completed prefix is byte-identical to the uninterrupted run.
    assert _trajectory(completed) == _trajectory(baseline.steps)[:stop_after]


def test_observer_integrity_failure_is_not_retried_in_campaign() -> None:
    worker = _FakeWorker()
    seed_count = len(minimal_seed_corpus())
    seen = {"n": 0}

    def inner(case):
        # Let seeds succeed, then fail with an observer-integrity error on a mutation.
        if seen["n"] >= seed_count:
            raise BackendError("evidence integrity failed after target success: {}")
        seen["n"] += 1
        return synthetic_effect_result(case)

    producer = ResettingProducer(
        inner, worker, _clean_observer(), sleep=lambda _s: None, rng=random.Random(0)
    )
    # observer_integrity propagates unchanged (not CaseAbandoned) and is never retried.
    with pytest.raises(BackendError, match="evidence integrity failed"):
        run_effect_campaign(minimal_seed_corpus(), producer, CONFIG)
    assert worker.recycles == 0

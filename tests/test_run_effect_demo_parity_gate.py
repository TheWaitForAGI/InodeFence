"""Offline guards for the parity-emission gate and step-index threading (no Docker)."""

import argparse
import random

import pytest
from scripts.run_effect_demo import (
    _parity_campaign_producer,
    add_demo_arguments,
    demo_options,
    synthetic_demo_report,
)

from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.execution.base import BackendError
from inodefence.execution.worker_pool import CaseAbandoned
from inodefence.feedback import EffectSearchPolicy
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.mutator import MutationPolicy

CASE = ArchiveCase((ArchiveEntry("a.txt", EntryType.REGULAR, content=b"x"),))
BROKER = "trusted Docker broker disconnected or returned invalid data"


def test_non_emitting_report_has_no_parity_subject() -> None:
    # A report built without the emit-parity gate (same builder the historical path uses)
    # never carries a parity_subject; the key is added only by the gated attach.
    report = synthetic_demo_report(
        9001, 5, EffectSearchPolicy.P1_EFFECT_RETENTION, MutationPolicy.LEGACY
    )
    assert "parity_subject" not in report
    assert "worker_pool_retries" not in report


def test_demo_options_gate_off_by_default() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode")
    add_demo_arguments(parser)
    args = parser.parse_args(["effect-demo-historical", "--tar-version", "7.5.2"])
    options = demo_options(args)
    assert "emit_parity" not in options
    assert "worker_pool" not in options


def test_abandoned_case_records_real_step_index_not_zero() -> None:
    # The producer threads completed_step_count so an abandoned case's step_index reflects
    # how many valid steps preceded it, instead of a fixed zero.
    def always_broker(_case: ArchiveCase):
        raise BackendError(BROKER)

    producer = _parity_campaign_producer(
        always_broker, worker_pool=True, seed=1, completed_step_count=lambda: 7
    )
    producer.sleep = lambda _: None  # type: ignore[attr-defined]
    producer.rng = random.Random(0)  # type: ignore[attr-defined]
    with pytest.raises(CaseAbandoned) as excinfo:
        producer(CASE)
    assert excinfo.value.invalid_case.step_index == 7


def test_producer_is_transparent_on_clean_run() -> None:
    producer = _parity_campaign_producer(
        synthetic_effect_result, worker_pool=False, seed=1, completed_step_count=lambda: 0
    )
    result = producer(CASE)
    assert result.base_result.case.case_id == CASE.case_id
    assert len(producer.reset_observations) == 1  # one observation recorded for the case

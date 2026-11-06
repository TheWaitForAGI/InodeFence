"""Offline tests for the worker-pool parity judgement over emitted reports (no Docker)."""

import pytest
from scripts.compare_wp_parity import compare_reports

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.execution_parity import (
    ResetVerification,
    extract_parity_subject,
    parity_subject_to_dict,
)
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance, ResourcePolicy
from inodefence.mutator import MutationPolicy


def _d(obj: object) -> dict:
    assert isinstance(obj, dict)
    return obj


def _report(seed: int, wall: float, *, retries_total: int = 0, image: str = "a") -> dict:
    config = EffectCampaignConfig(
        seed, 5, EffectSearchPolicy.P1_EFFECT_RETENTION, MutationPolicy.LEGACY
    )
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    resets = tuple(ResetVerification(i, False, False) for i in range(len(result.steps)))
    isolation = IsolationProvenance(
        IsolationPolicy("sha256:" + image * 64, 1000, 1000, ResourcePolicy()),
        "docker-compatible",
        "27.0.0",
        "1.47",
        "linux",
        "amd64",
        "amd64",
    )
    subject = extract_parity_subject(result, label="x", isolation=isolation, resets=resets)
    return {
        "parity_subject": parity_subject_to_dict(subject),
        "timing": {"total_seconds": wall},
        "config": {"random_seed": seed},
        "steps": [{} for _ in result.steps],
        "node_tar_version": "7.5.2",
        "requested_tar_version": "R",
        "worker_pool_retries": {"total": retries_total, "by_step": []},
        "invalid_cases": [],
    }


def test_same_seed_runs_pass_four_dimensions_and_zero_retries() -> None:
    result = compare_reports(_report(9001, 78.0), _report(9001, 40.0))
    assert _d(result["verdict"])["four_dimension_parity_pass"] is True
    assert _d(result["verdict"])["retries_zero"] is True
    assert _d(result["verdict"])["overall_pass"] is True
    # throughput side-by-side present with a speedup.
    assert _d(_d(result["throughput"])["summary"])["speedup"] == pytest.approx(
        78.0 / 40.0, rel=1e-3
    )


def test_different_seed_fails_four_dimensions() -> None:
    result = compare_reports(_report(9001, 78.0), _report(9002, 40.0))
    assert _d(result["verdict"])["four_dimension_parity_pass"] is False
    assert _d(result["verdict"])["overall_pass"] is False


def test_nonzero_retries_fails_overall_even_if_four_dim_passes() -> None:
    result = compare_reports(_report(9001, 78.0), _report(9001, 40.0, retries_total=2))
    assert _d(result["verdict"])["four_dimension_parity_pass"] is True
    assert _d(result["verdict"])["retries_zero"] is False
    assert _d(result["verdict"])["overall_pass"] is False
    assert _d(result["worker_pool_retries"])["total"] == 2


def test_missing_parity_subject_is_refused() -> None:
    good = _report(9001, 10.0)
    with pytest.raises(SystemExit):
        compare_reports(good, {"timing": {"total_seconds": 1.0}})

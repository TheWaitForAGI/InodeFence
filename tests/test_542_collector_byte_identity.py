"""#542: more byte-identity checks for the decompress and oras-go streaming report collectors.

The collectors (``DecompressReportCollector``, ``OrasGoReportCollector``) must give the same report
as the retained path for every configuration the loops accept, not only the defaults. Compared
here with the controller's own encoding (``scripts/container_controller.py`` writes these reports
with ``json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\\n"``):

* every accepted search policy (decompress) x mutation policy x adaptive scheduler on/off;
* a mixed producer: benign runs, several violating runs (not only the seed), runs without a
  frame (unjudged) and failed extractions, so every step-record branch is collected;
* a longer budget, so the corpus and scheduler state churn;
* the collector keeps plain step records only, never the run objects (the memory point of #542);
* fail-closed: a result of the wrong type, or one whose step count differs, is refused (oras-go
  as well as decompress).

Synthetic producers only (the fakes of the existing campaign tests); no target runs.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from hashlib import sha256
from typing import Any

import pytest
from tests import test_decompress_effect_campaign as dct
from tests import test_oras_go_effect_campaign as ogt

from inodefence.builder import build_tar
from inodefence.campaign_hooks import CampaignHooks
from inodefence.decompress_effect_campaign import (
    DecompressEffectCampaignConfig,
    DecompressLightResult,
    DecompressReportCollector,
    decompress_effect_campaign_report,
    run_decompress_effect_campaign,
)
from inodefence.feedback.effect_search import EffectSearchPolicy
from inodefence.model import EntryType, ExecutionStatus
from inodefence.mutator.policy import V2_GRAMMAR_POLICIES, MutationPolicy
from inodefence.oras_go_effect_campaign import (
    OrasGoEffectCampaignConfig,
    OrasGoLightResult,
    OrasGoReportCollector,
    oras_go_effect_campaign_report,
    run_oras_go_effect_campaign,
)


def _controller_bytes(report: dict[str, Any]) -> bytes:
    """Exactly how the controller writes these reports."""
    return (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _bucket(case: Any) -> int:
    return int(sha256(case.case_id.encode()).hexdigest()[:8], 16)


def _has_hardlink(case: Any) -> bool:
    return any(entry.entry_type == EntryType.HARDLINK for entry in case.entries)


def _mixed(module: Any, violating_after: Callable[[Any], tuple], attempt: dict) -> Any:
    """A deterministic producer over every step-record branch, for one module's fakes."""

    def produce(case: Any) -> Any:
        bucket = _bucket(case)
        if case == module._ESCAPE_CASE or (_has_hardlink(case) and bucket % 3 == 0):
            run = module._run(
                case,
                before=module._SENTINEL_ONLY,
                after=violating_after(case),
                frame=module._frame((attempt,)),
            )
            digest = sha256(build_tar(case)).hexdigest()
            return dataclasses.replace(
                run, base_result=dataclasses.replace(run.base_result, archive_sha256=digest)
            )
        if bucket % 7 == 0:
            return module._run(
                case,
                before=module._SENTINEL_ONLY,
                after=module._SENTINEL_ONLY,
                frame=None,
                frame_error="no frame",
            )
        if bucket % 11 == 0:
            run = module._benign_run(case)
            return module._run(
                case,
                before=module._SENTINEL_ONLY,
                after=run.base_result.after.objects,
                frame=module._frame(()),
                status=ExecutionStatus.FAILED,
            )
        return module._benign_run(case)

    return produce


def _violating_after(module: Any, prefix: str) -> Any:
    def after(case: Any) -> tuple:
        return (
            module._obj(module._SENTINEL, ino=9, nlink=2),
            module._obj(f"{prefix}{case.case_id[:8]}", ino=9, nlink=2),
        )

    return after


DECOMPRESS_MIXED = _mixed(dct, _violating_after(dct, "extract/"), dct._external_hardlink_attempt())
ORAS_GO_MIXED = _mixed(ogt, _violating_after(ogt, "extract/d/"), ogt._external_hardlink_attempt())

V1_MUTATION_POLICIES = tuple(p for p in MutationPolicy if p not in V2_GRAMMAR_POLICIES)
DECOMPRESS_SEARCH_POLICIES = tuple(
    p
    for p in EffectSearchPolicy
    if p
    not in (
        EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M4,
        EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M6,
    )
)


def _decompress_pair(config: DecompressEffectCampaignConfig, produce: Any) -> tuple[bytes, bytes]:
    full = run_decompress_effect_campaign(dct._seeds(), produce, config)
    expected = decompress_effect_campaign_report(full, producer="unit-test", label="demo run")
    collector = DecompressReportCollector(producer="unit-test", label="demo run")
    light = run_decompress_effect_campaign(
        dct._seeds(),
        produce,
        config,
        hooks=CampaignHooks(on_step=collector.add, retain_steps=False),
    )
    assert isinstance(light, DecompressLightResult)
    assert all(type(record) is dict for record in collector.steps)  # records, not run objects
    return _controller_bytes(collector.report(light)), _controller_bytes(expected)


def _oras_go_pair(config: OrasGoEffectCampaignConfig, produce: Any) -> tuple[bytes, bytes]:
    full = run_oras_go_effect_campaign(ogt._seeds(), produce, config)
    expected = oras_go_effect_campaign_report(full, producer="unit-test", label="demo run")
    collector = OrasGoReportCollector(producer="unit-test", label="demo run")
    light = run_oras_go_effect_campaign(
        ogt._seeds(),
        produce,
        config,
        hooks=CampaignHooks(on_step=collector.add, retain_steps=False),
    )
    assert isinstance(light, OrasGoLightResult)
    assert all(type(record) is dict for record in collector.steps)
    return _controller_bytes(collector.report(light)), _controller_bytes(expected)


# -- every accepted configuration ---------------------------------------------------------------


def test_the_policy_lists_are_not_empty() -> None:
    assert V1_MUTATION_POLICIES and DECOMPRESS_SEARCH_POLICIES


@pytest.mark.parametrize("adaptive", [True, False])
@pytest.mark.parametrize("mutation", V1_MUTATION_POLICIES, ids=lambda p: p.value)
@pytest.mark.parametrize("search", DECOMPRESS_SEARCH_POLICIES, ids=lambda p: p.value)
def test_decompress_collector_matches_for_every_accepted_configuration(
    search: EffectSearchPolicy, mutation: MutationPolicy, adaptive: bool
) -> None:
    config = DecompressEffectCampaignConfig(
        random_seed=3,
        execution_budget=len(dct._seeds()) + 20,
        mutation_policy=mutation,
        search_policy=search,
        adaptive_scheduler=adaptive,
    )
    streamed, retained = _decompress_pair(config, DECOMPRESS_MIXED)
    assert streamed == retained


@pytest.mark.parametrize("adaptive", [True, False])
@pytest.mark.parametrize("mutation", V1_MUTATION_POLICIES, ids=lambda p: p.value)
def test_oras_go_collector_matches_for_every_accepted_configuration(
    mutation: MutationPolicy, adaptive: bool
) -> None:
    config = OrasGoEffectCampaignConfig(
        random_seed=3,
        execution_budget=len(ogt._seeds()) + 20,
        mutation_policy=mutation,
        adaptive_scheduler=adaptive,
    )
    streamed, retained = _oras_go_pair(config, ORAS_GO_MIXED)
    assert streamed == retained


# -- the mixed producer really reaches every branch; a longer budget ----------------------------


def test_the_mixed_producer_reaches_violations_unjudged_and_failed_steps() -> None:
    config = DecompressEffectCampaignConfig(random_seed=5, execution_budget=len(dct._seeds()) + 80)
    full = run_decompress_effect_campaign(dct._seeds(), DECOMPRESS_MIXED, config)
    report = decompress_effect_campaign_report(full, producer="unit-test")
    steps = report["steps"]
    assert isinstance(steps, list)
    inputs = report["violation_inputs"]
    assert isinstance(inputs, list) and len(inputs) >= 2  # more than the seed alone
    assert any(step.get("frame_error") for step in steps)
    assert any(step.get("termination") == ExecutionStatus.FAILED.value for step in steps)


@pytest.mark.parametrize("seed", [2, 5, 11])
def test_longer_budgets_still_match(seed: int) -> None:
    decompress = DecompressEffectCampaignConfig(
        random_seed=seed, execution_budget=len(dct._seeds()) + 80
    )
    assert (
        _decompress_pair(decompress, DECOMPRESS_MIXED)[0]
        == _decompress_pair(decompress, DECOMPRESS_MIXED)[1]
    )
    oras_go = OrasGoEffectCampaignConfig(random_seed=seed, execution_budget=len(ogt._seeds()) + 80)
    streamed, retained = _oras_go_pair(oras_go, ORAS_GO_MIXED)
    assert streamed == retained


# -- fail-closed --------------------------------------------------------------------------------


def test_the_collectors_refuse_a_retained_result() -> None:
    decompress = DecompressEffectCampaignConfig(random_seed=1, execution_budget=4)
    full = run_decompress_effect_campaign(dct._seeds(), dct._benign_run, decompress)
    with pytest.raises(ValueError, match="DecompressLightResult"):
        DecompressReportCollector(producer="unit-test").report(full)  # type: ignore[arg-type]
    oras_go = OrasGoEffectCampaignConfig(random_seed=1, execution_budget=4)
    full_og = run_oras_go_effect_campaign(ogt._seeds(), ogt._benign_run, oras_go)
    with pytest.raises(ValueError, match="OrasGoLightResult"):
        OrasGoReportCollector(producer="unit-test").report(full_og)  # type: ignore[arg-type]


def test_the_oras_go_collector_refuses_a_result_that_does_not_match_its_steps() -> None:
    config = OrasGoEffectCampaignConfig(random_seed=1, execution_budget=len(ogt._seeds()) + 2)
    collector = OrasGoReportCollector(producer="unit-test")
    light = run_oras_go_effect_campaign(
        ogt._seeds(),
        ogt._benign_run,
        config,
        hooks=CampaignHooks(on_step=lambda s: None, retain_steps=False),
    )
    assert isinstance(light, OrasGoLightResult)
    with pytest.raises(ValueError, match="collected 0 steps"):
        collector.report(light)

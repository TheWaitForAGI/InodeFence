"""One contract test suite for CampaignHooks, parametrized across every campaign loop.

The three extractor loops (node-tar, oras-go, decompress) are separate implementations that accept
the same ``CampaignHooks``. This suite states the contract once; each loop is a parameter, so the
same assertions run against all of them (no per-loop copies). node-tar is wired here; oras-go and
decompress are added to ``LOOP_SPECS`` by their owners (IF-MAC-D / IF-MAC-B) when they thread the
hooks through their loops.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from inodefence.campaign_hooks import CampaignHooks, LightCampaignResult
from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_synthetic import _result as _node_tar_result
from inodefence.feedback import EffectSearchPolicy
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.mutator import MutationPolicy


@dataclass(frozen=True)
class LoopSpec:
    """How to drive one campaign loop for the contract tests."""

    name: str
    run: Callable[..., Any]  # run(seed_cases, producer, config, *, on_step, hooks)
    seed_cases: tuple[Any, ...]
    producer: Callable[[Any], Any]
    budget: int
    config: Any


def _node_tar_spec() -> LoopSpec:
    seed = ArchiveCase((ArchiveEntry("seed", EntryType.REGULAR, b"seed"),))
    config = EffectCampaignConfig(
        random_seed=123,
        execution_budget=16,
        search_policy=EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
        mutation_policy=MutationPolicy.M1,
    )
    return LoopSpec("node-tar", run_effect_campaign, (seed,), _node_tar_result, 16, config)


# IF-MAC-D adds oras-go, IF-MAC-B adds decompress, once their loops accept `hooks`.
LOOP_SPECS = [_node_tar_spec()]
IDS = [spec.name for spec in LOOP_SPECS]


def _case_ids(spec: LoopSpec, hooks: CampaignHooks | None) -> list[str]:
    seen: list[str] = []
    recorder = CampaignHooks(
        on_step=lambda step: seen.append(step.result.base_result.case.case_id),
        should_stop=None if hooks is None else hooks.should_stop,
        retain_steps=True if hooks is None else hooks.retain_steps,
    )
    spec.run(spec.seed_cases, spec.producer, spec.config, hooks=recorder)
    return seen


@pytest.mark.parametrize("spec", LOOP_SPECS, ids=IDS)
def test_no_hooks_is_byte_identical(spec: LoopSpec) -> None:
    without = spec.run(spec.seed_cases, spec.producer, spec.config)
    none_bundle = spec.run(spec.seed_cases, spec.producer, spec.config, hooks=None)
    empty_bundle = spec.run(spec.seed_cases, spec.producer, spec.config, hooks=CampaignHooks())
    assert without == none_bundle == empty_bundle


@pytest.mark.parametrize("spec", LOOP_SPECS, ids=IDS)
def test_retain_off_streams_the_same_step_order(spec: LoopSpec) -> None:
    retained = _case_ids(spec, CampaignHooks(retain_steps=True))
    streamed = _case_ids(spec, CampaignHooks(retain_steps=False))
    assert streamed == retained and len(streamed) == spec.budget
    light = spec.run(
        spec.seed_cases, spec.producer, spec.config, hooks=CampaignHooks(retain_steps=False)
    )
    assert isinstance(light, LightCampaignResult)
    assert light.executed == spec.budget and light.stop_reason is None


@pytest.mark.parametrize("spec", LOOP_SPECS, ids=IDS)
def test_should_stop_ends_at_the_promised_boundary(spec: LoopSpec) -> None:
    stop_at = spec.budget // 2

    def should_stop(executed: int) -> str | None:
        return "reached limit" if executed >= stop_at else None

    result = spec.run(
        spec.seed_cases, spec.producer, spec.config, hooks=CampaignHooks(should_stop=should_stop)
    )
    assert isinstance(result, LightCampaignResult)  # an early stop never returns the full type
    assert result.executed == stop_at and result.stop_reason == "reached limit"
    # the step stream also stops at exactly that boundary
    assert len(_case_ids(spec, CampaignHooks(should_stop=should_stop))) == stop_at

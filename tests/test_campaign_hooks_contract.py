"""One contract test suite for CampaignHooks, parametrized across every campaign loop.

The three extractor loops (node-tar, oras-go, decompress) are separate implementations that accept
the same ``CampaignHooks``. This suite states the contract once; each loop is a parameter, so the
same assertions run against all of them (no per-loop copies). node-tar is wired here; oras-go and
decompress are added to ``LOOP_SPECS`` by their owners (IF-MAC-D / IF-MAC-B) when they thread the
hooks through their loops.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from inodefence.campaign_hooks import CampaignHooks, LightCampaignResult
from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_synthetic import _result as _node_tar_result
from inodefence.feedback import EffectSearchPolicy
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.mutator import MutationPolicy

# The golden digests below were minted from the code at this commit -- the confirmatory-experiment
# run SHA, the code the preregistered experiment runs. ``src/inodefence/effect_campaign.py`` is
# byte-identical between this commit and the base of the CampaignHooks PR (verified with
# ``git diff bed077a <base> -- src/inodefence/effect_campaign.py`` -> empty). The golden test
# asserts the current code's hooks-free path reproduces that exact search/feedback/weight
# trajectory, so "merged base path == registered-experiment code" is a test, not a manual check.
GOLDEN_COMMIT = "bed077af62b1cdd5cc8dec96eb9cbe93ba542f1d"
# How to regenerate (no docker, no sealed evidence -- code only):
#   git worktree add --detach /tmp/bed077a-wt bed077a
#   PYTHONPATH=src:. python - <<'PY'  (the same _trajectory_digest below, over COMBOS)
# then paste the printed {"seed:budget": sha256} map into each loop's ``golden``.


def _trajectory_digest(result: Any) -> str:
    """SHA-256 over the hooks-free run's full per-step search/feedback decision and the scheduler
    weight trajectory, plus the retained corpus -- the base path's observable output for a seed."""
    sha = hashlib.sha256()
    for step in result.steps:
        fb = step.feedback
        weights = (
            ""
            if step.scheduler_evidence is None
            else ",".join(f"{op.name}:{wt}" for op, wt in step.scheduler_evidence.weights_after)
        )
        row = "\x1f".join(
            [
                str(step.index),
                step.origin.name,
                step.parent_case_id or "",
                fb.case_id,
                str(fb.full_state_novel),
                str(fb.effect_novel),
                str(fb.contract_violated),
                str(fb.observation_failure),
                str(fb.feedback_eligible),
                str(fb.already_retained),
                str(fb.admission_eligible),
                "|".join(str(x) for x in fb.new_violation_fingerprints),
                "|".join(str(x) for x in fb.new_effect_keys),
                str(fb.trace_completeness),
                str(fb.trace_termination),
                weights,
            ]
        )
        sha.update((row + "\x1e").encode())
    sha.update(("R:" + "|".join(result.retained_case_ids)).encode())
    return sha.hexdigest()


@dataclass(frozen=True)
class LoopSpec:
    """How to drive one campaign loop for the contract tests."""

    name: str
    run: Callable[..., Any]  # run(seed_cases, producer, config, *, on_step, hooks)
    seed_cases: tuple[Any, ...]
    producer: Callable[[Any], Any]
    budget: int
    config: Any
    #: The case id a completed step ran (each loop's step type names its run differently).
    step_case_id: Callable[[Any], str] = lambda step: step.result.base_result.case.case_id
    #: Build a config for an arbitrary (seed, budget); used by the golden test over several combos.
    make_config: Callable[[int, int], Any] | None = None
    #: ``"seed:budget" -> sha256`` minted at GOLDEN_COMMIT. Empty until the loop's owner adds it.
    golden: dict[str, str] = field(default_factory=dict)
    #: The trajectory digest for this loop's result type (each loop's step records differ).
    digest: Callable[[Any], str] = _trajectory_digest


def _node_tar_config(seed: int, budget: int) -> EffectCampaignConfig:
    return EffectCampaignConfig(
        random_seed=seed,
        execution_budget=budget,
        search_policy=EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
        mutation_policy=MutationPolicy.M1,
    )


def _node_tar_spec() -> LoopSpec:
    seed = ArchiveCase((ArchiveEntry("seed", EntryType.REGULAR, b"seed"),))
    return LoopSpec(
        "node-tar",
        run_effect_campaign,
        (seed,),
        _node_tar_result,
        16,
        _node_tar_config(123, 16),
        make_config=_node_tar_config,
        # Minted from GOLDEN_COMMIT (see module header). Current code must reproduce these.
        golden={
            "123:16": "565d61a5f0ba8076b6fd138a44bf1d3a0a1641d4c6807759099c4790aeea8fa4",
            "7:24": "921dbb0149246cab8ebce008222546e009655b8f3d5e00bb5efddf98cb967c8d",
            "999:32": "2e86e3d72dac56192caccc062af3e984b08e947afb54ccf65a7398241fcb5292",
        },
    )


def _oras_go_trajectory_digest(result: Any) -> str:
    """SHA-256 over the oras-go loop's per-step decision and scheduler weights plus the retained
    corpus -- the oras-go counterpart of ``_trajectory_digest`` (its steps carry a ``decision``
    over boundary-attempt keys, violation fingerprints and full-state novelty)."""
    sha = hashlib.sha256()
    for step in result.steps:
        d = step.decision
        weights = (
            ""
            if step.scheduler_evidence is None
            else ",".join(f"{op.name}:{wt}" for op, wt in step.scheduler_evidence.weights_after)
        )
        row = "\x1f".join(
            [
                str(step.index),
                step.origin.name,
                step.parent_case_id or "",
                d.case_id,
                "|".join(str(k) for k in d.new_attempt_keys),
                "|".join(str(x) for x in d.new_violation_fingerprints),
                str(d.full_state_novel),
                str(d.contract_violated),
                str(d.frame_observed),
                str(d.eligible),
                str(d.already_retained),
                str(d.admission_eligible),
                "" if step.mutation_attempt is None else step.mutation_attempt.operator_id.name,
                weights,
            ]
        )
        sha.update((row + "\x1e").encode())
    sha.update(("R:" + "|".join(result.retained_case_ids)).encode())
    return sha.hexdigest()


def _oras_go_config(seed: int, budget: int) -> Any:
    from inodefence.oras_go_effect_campaign import OrasGoEffectCampaignConfig

    return OrasGoEffectCampaignConfig(random_seed=seed, execution_budget=budget)


def _oras_go_spec() -> LoopSpec:
    from tests.test_oras_go_effect_campaign import _benign_run, _seeds

    from inodefence.oras_go_effect_campaign import run_oras_go_effect_campaign

    return LoopSpec(
        "oras-go",
        run_oras_go_effect_campaign,
        _seeds(),
        _benign_run,
        12,
        _oras_go_config(7, 12),
        step_case_id=lambda step: step.run.base_result.case.case_id,
        make_config=_oras_go_config,
        golden=ORAS_GO_GOLDEN,
        digest=_oras_go_trajectory_digest,
    )


#: Minted from GOLDEN_COMMIT the same way as node-tar's (see module header), with
#: ``_oras_go_trajectory_digest`` over ``_oras_go_config`` and the oras-go test producer.
ORAS_GO_GOLDEN: dict[str, str] = {
    "123:16": "5c2e74bd5746144f109e96197b78af689484c0ea9097dc1ec1819391c99d6bb2",
    "7:24": "d606b14cfc3b746e0577ed52dfec9dc73054c6d783aaa7ea781941f8e5c46413",
    "999:32": "2f174d0f3504e6b5d8394b5b752b508d5f091506983bd164dc47ff5792f82c90",
}

# IF-MAC-B adds decompress once its loop accepts `hooks`, with its own ``golden``.
LOOP_SPECS = [_node_tar_spec(), _oras_go_spec()]
IDS = [spec.name for spec in LOOP_SPECS]


def _case_ids(spec: LoopSpec, hooks: CampaignHooks | None) -> list[str]:
    seen: list[str] = []
    recorder = CampaignHooks(
        on_step=lambda step: seen.append(spec.step_case_id(step)),
        should_stop=None if hooks is None else hooks.should_stop,
        retain_steps=True if hooks is None else hooks.retain_steps,
    )
    spec.run(spec.seed_cases, spec.producer, spec.config, hooks=recorder)
    return seen


@pytest.mark.parametrize("spec", LOOP_SPECS, ids=IDS)
def test_base_path_reproduces_registered_experiment_golden(spec: LoopSpec) -> None:
    """The hooks-free path still produces the exact trajectory the code at GOLDEN_COMMIT did.

    This is the one that pins "merged base path == the code the preregistered experiment runs":
    the expected digests were minted from GOLDEN_COMMIT (see module header), not from the current
    code, so a silent change to the base search/feedback/weight path fails here.
    """
    assert spec.make_config is not None and spec.golden, f"{spec.name}: golden not wired yet"
    for combo, expected in spec.golden.items():
        seed, budget = (int(part) for part in combo.split(":"))
        result = spec.run(spec.seed_cases, spec.producer, spec.make_config(seed, budget))
        assert spec.digest(result) == expected, f"{spec.name} {combo}: base path changed"


@pytest.mark.parametrize("spec", LOOP_SPECS, ids=IDS)
def test_hooks_absent_none_and_empty_bundle_all_agree(spec: LoopSpec) -> None:
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


@pytest.mark.parametrize("spec", LOOP_SPECS, ids=IDS)
def test_checkpoint_hook_is_refused_until_wired(spec: LoopSpec) -> None:
    # checkpoint has no loop behind it yet; a loop must reject it, not silently persist nothing.
    with pytest.raises(ValueError, match="checkpoint is not wired"):
        spec.run(
            spec.seed_cases,
            spec.producer,
            spec.config,
            hooks=CampaignHooks(checkpoint=lambda state, executed: None),
        )

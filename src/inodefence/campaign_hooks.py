"""Shared optional hooks for the extractor campaign loops (node-tar, oras-go, decompress).

The three loops (``effect_campaign.run_effect_campaign``,
``oras_go_effect_campaign.run_oras_go_effect_campaign``,
``decompress_effect_campaign.run_decompress_effect_campaign``) are separate implementations of the
same shape (seed observation -> ``while len(steps) < budget`` -> select_case -> choose_operator ->
apply_operator -> observe -> on_step). This module defines ONE hook type they all accept, so
streaming, early stop and checkpointing are added once, not three times, and the contract is the
same across targets.

A loop given no hooks (or ``CampaignHooks()``) behaves exactly as before -- byte-identical result,
identical RNG / mutation / feedback order. The hooks only observe and bound the loop; they never
change what it would produce for a given seed and step index.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CampaignState:
    """The campaign state a checkpoint captures, split into the part common to all three loops and
    an opaque target-specific part.

    Common part (serialized by this module, identical for every target):

    - ``rng_state``: ``random.Random.getstate()`` of the loop RNG, taken on the step boundary;
    - ``executed``: number of completed steps so far (the loop's ``len(steps)`` / counter);
    - ``observed_names``: the state-aware vocabulary accumulated from the general tree;
    - ``operator_weights``: the scheduler's per-operator weights;
    - ``seen_fingerprints``: the violation fingerprints seen so far (for cross-run dedup).

    Target-specific part (opaque here; each loop serializes its own retention/corpus and the shape
    of its feedback keys): ``target_state``. Resuming restores the common part uniformly and hands
    ``target_state`` back to the loop that produced it.
    """

    rng_state: tuple[Any, ...]
    executed: int
    observed_names: tuple[str, ...]
    operator_weights: dict[str, int]
    seen_fingerprints: tuple[str, ...]
    target_state: Any = None


@dataclass(frozen=True, slots=True)
class CampaignHooks:
    """Optional hooks a campaign loop accepts. Every field defaults to the loop's current
    behaviour, so a loop given ``None`` or ``CampaignHooks()`` is byte-identical to today.

    Each loop calls these at the SAME points:

    - ``on_step(step)``: right after a completed step is recorded (after feedback and scheduler
      bookkeeping), once per executed case. Same timing and object as the existing ``on_step``
      parameter; when both are given, this one is used.
    - ``should_stop(executed)``: called AFTER ``on_step``, before selecting the next case. Returns a
      reason string to stop now (the loop ends with ``executed`` completed steps) or ``None`` to
      continue. ``budget`` remains an upper bound; ``should_stop`` can only end the loop earlier,
      never extend it past ``budget``. Stopping early returns the lightweight result (the full
      result type requires a complete run), even when ``retain_steps`` is True.
    - ``checkpoint(state, executed)``: NOT WIRED YET. This slot is defined for the resume PR; no
      loop calls it today, so passing it would silently do nothing. Until that PR connects it, a
      loop given a ``checkpoint`` refuses (see ``ensure_no_unwired_hooks``) rather than look as if
      it is persisting. The intended contract once wired: called on the SAME boundary as
      ``should_stop`` (after a completed step) for periodic persistence, with a ``CampaignState``
      whose common part the loop fills; the hook decides how often (called every step, may
      rate-limit itself).
    - ``retain_steps``: when ``False`` the loop streams every completed step to ``on_step`` but does
      NOT keep it in memory, so an unbounded run stays O(1) in steps. The loop then returns a
      lightweight aggregate (execution/violation counts, stop reason) instead of the full result
      type. Default ``True`` keeps every step (current behaviour and result type).
    """

    on_step: Callable[[Any], None] | None = None
    should_stop: Callable[[int], str | None] | None = None
    checkpoint: Callable[[CampaignState, int], None] | None = None
    retain_steps: bool = True


#: A hook bundle with no effect: every loop treats this exactly as "no hooks given".
NO_HOOKS = CampaignHooks()


def ensure_no_unwired_hooks(hooks: CampaignHooks | None) -> None:
    """Refuse hooks whose slot no loop implements yet, so an unfinished feature never looks wired.

    ``checkpoint`` is defined but not connected until the resume PR; passing it must be a loud
    error, not a silent no-op. Every loop calls this once, before running, as it reads ``hooks``.
    """
    if hooks is not None and hooks.checkpoint is not None:
        raise ValueError(
            "CampaignHooks.checkpoint is not wired yet; the resume PR will connect it. "
            "Remove it until then (passing it would persist nothing)."
        )


def resolve_on_step(
    hooks: CampaignHooks | None, legacy_on_step: Callable[[Any], None] | None
) -> Callable[[Any], None] | None:
    """The effective ``on_step`` for a loop that still has a legacy ``on_step`` parameter: the
    hook's ``on_step`` wins when a hook bundle is given, otherwise the legacy parameter is used."""
    if hooks is not None and hooks.on_step is not None:
        return hooks.on_step
    return legacy_on_step


@dataclass(frozen=True, slots=True)
class LightCampaignResult:
    """What a loop returns in non-retaining mode: aggregates only, no per-step records.

    ``stop_reason`` is the reason ``should_stop`` gave, or ``None`` when the loop ran to ``budget``.
    ``retained_case_ids`` is the final corpus (small), so the caller still sees retention; per-step
    detail was streamed to ``on_step`` and is not kept here.
    """

    executed: int
    budget: int
    stop_reason: str | None
    retained_case_ids: tuple[str, ...] = field(default_factory=tuple)

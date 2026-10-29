"""Intermediate-state (transition/effect) gradient metrics for the A/B/C/D arms.

Companion to ``arm_comparison``: where that scores the TERMINAL C0/C1/C2 observation
(all-or-nothing, and on a sparse target like node-tar usually right-censored), this
scores the DENSE intermediate-state signal -- the per-execution set of target-agnostic
intermediate-state keys (entry-transition signatures, boundary-attempt / external-
resolve effect keys) that accrue on nearly every execution. On that signal the
A/B/C/D arms separate without a terminal hit, so an arm differential is measurable
even when terminal violations are censored.

Honest boundaries (audit EN-008): a larger intermediate-state key set is SEARCH
BEHAVIOUR, not a vulnerability count and not effectiveness. This module characterizes
HOW the arms explore intermediate states and makes no superiority or effectiveness-
ranking claim. A milestone first-hit (for example the first boundary-attempt key) is
a directed-gradient proxy for progress toward a boundary, NOT a confirmed violation.

Decoupling (so this neither stacks on unmerged producer wiring nor hardcodes a
target): the measurement consumes an abstract ordered sequence of per-execution key
SETS of hashable keys, plus an optional ``milestone`` predicate. The core never
imports a key type, path, sentinel or CVE. The adapters below extract such key sets
from the effect/transition signals already on main; a second extractor's or a later
producer's trace plugs into the same sequence-of-key-sets contract unchanged.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from inodefence.evaluation.arm_comparison import Arm
from inodefence.feedback import (
    boundary_attempt_keys,
    effect_feedback_keys,
    external_resolve_keys,
    transition_keys,
)
from inodefence.model import EffectEventTrace, EffectFeedbackKeyKind, TransitionTrace
from inodefence.model.effect_feedback import EffectFeedbackKey

Milestone = Callable[[object], bool]
_DEFAULT_CHECKPOINTS = (0.25, 0.5, 0.75, 1.0)

_INTERMEDIATE_NOTE = (
    "intermediate-state exploration is search behaviour (audit EN-008), not a "
    "vulnerability count and not effectiveness; no arm superiority/ranking is claimed"
)
_MILESTONE_NOTE = (
    "a milestone first-hit (e.g. first boundary-attempt key) is a directed-gradient "
    "proxy for progress toward a boundary, not a confirmed contract violation"
)


@dataclass(frozen=True, slots=True)
class IntermediateStateMetrics:
    """Dense per-arm exploration metrics over one ordered run of key sets.

    ``cumulative_unique_keys`` is the (fraction, cumulative-unique-key-count) gradient
    trajectory at the requested checkpoints -- its slope is the arm's exploration rate.
    ``milestone_executions`` is the 1-based index of the first execution whose key set
    satisfies the milestone predicate, or ``None`` (``milestone_censored``) if none did;
    unlike a terminal violation this directed milestone is typically reached early.
    """

    total_steps: int
    unique_keys: int
    novel_key_steps: int
    novelty_rate: float
    cumulative_unique_keys: tuple[tuple[float, int], ...]
    milestone_executions: int | None
    milestone_censored: bool
    milestone_key_count: int


def intermediate_state_metrics(
    step_key_sets: Sequence[frozenset],
    *,
    milestone: Milestone | None = None,
    checkpoints: Sequence[float] = _DEFAULT_CHECKPOINTS,
) -> IntermediateStateMetrics:
    """Score one ordered sequence of per-execution intermediate-state key sets.

    Each element is the set of intermediate-state keys observed on that execution
    (empty if the execution produced none). Keys must be hashable; the sets are read
    in order, so the first execution is index 1. No key type is assumed.
    """
    if milestone is not None and not callable(milestone):
        raise ValueError("milestone must be callable or None")
    ordered = [frozenset(keys) for keys in step_key_sets]
    checks = tuple(checkpoints)
    if not checks or any(not (0 < frac <= 1) for frac in checks):
        raise ValueError("checkpoints must be fractions in (0, 1]")

    seen: set = set()
    cumulative: list[int] = []
    novel_steps = 0
    milestone_exec: int | None = None
    milestone_count = 0
    for index, keys in enumerate(ordered):
        before = len(seen)
        seen |= keys
        if len(seen) > before:
            novel_steps += 1
        cumulative.append(len(seen))
        if milestone is not None:
            hit = sum(1 for key in keys if milestone(key))
            milestone_count += hit
            if milestone_exec is None and hit:
                milestone_exec = index + 1

    total = len(ordered)
    trajectory = tuple(
        (float(frac), cumulative[min(total, max(1, math.ceil(frac * total))) - 1] if total else 0)
        for frac in checks
    )
    return IntermediateStateMetrics(
        total_steps=total,
        unique_keys=len(seen),
        novel_key_steps=novel_steps,
        novelty_rate=novel_steps / total if total else 0.0,
        cumulative_unique_keys=trajectory,
        milestone_executions=milestone_exec,
        milestone_censored=milestone is not None and milestone_exec is None,
        milestone_key_count=milestone_count,
    )


@dataclass(frozen=True, slots=True)
class AbcdIntermediateComparison:
    """Per-arm intermediate-state metrics from one run, plus the honest caveats."""

    arms: tuple[Arm, ...]
    metrics: Mapping[Arm, IntermediateStateMetrics]
    note: str = _INTERMEDIATE_NOTE
    milestone_note: str = _MILESTONE_NOTE


def abcd_intermediate_comparison(
    arm_to_step_key_sets: Mapping[Arm, Sequence[frozenset]],
    *,
    milestone: Milestone | None = None,
    checkpoints: Sequence[float] = _DEFAULT_CHECKPOINTS,
) -> AbcdIntermediateComparison:
    """Score each arm's intermediate-state run identically; attach honest caveats.

    Every arm is measured with the same ``intermediate_state_metrics`` so a difference
    reflects the arm, not the metric. Takes pre-extracted per-arm key-set sequences
    (the caller runs each arm's campaign on whatever extractor supplies traces and
    extracts key sets via the adapters below), so no campaign engine, target or
    producer is bound here.
    """
    arms = tuple(arm_to_step_key_sets)
    if not arms:
        raise ValueError("at least one arm is required")
    if any(not isinstance(arm, Arm) for arm in arms):
        raise ValueError("arm keys must be Arm members")
    metrics = {
        arm: intermediate_state_metrics(
            arm_to_step_key_sets[arm], milestone=milestone, checkpoints=checkpoints
        )
        for arm in arms
    }
    return AbcdIntermediateComparison(arms, MappingProxyType(metrics))


# --- Adapters: extract an intermediate-state key set from the signals on main. ---
# These prove the consumption path on the existing effect/transition signals and are
# the same contract a second extractor's producer feeds. They are the only effect/
# transition-coupled part; the measurement above stays generic over hashable keys.


def effect_trace_keys(trace: EffectEventTrace) -> frozenset[EffectFeedbackKey]:
    """Full normalized effect keys for one execution (dense, SUCCESS-path signal)."""
    return frozenset(effect_feedback_keys(trace))


def boundary_attempt_trace_keys(trace: EffectEventTrace) -> frozenset[EffectFeedbackKey]:
    """Boundary-approach *attempt* keys (the opt-in directed-gradient rung)."""
    return frozenset(boundary_attempt_keys(trace))


def external_resolve_trace_keys(trace: EffectEventTrace) -> frozenset[EffectFeedbackKey]:
    """Observed-external-resolve keys (the rung between attempt and external success)."""
    return frozenset(external_resolve_keys(trace))


def transition_trace_keys(trace: TransitionTrace) -> frozenset:
    """Entry-transition signature keys for one execution (intermediate FS sequence)."""
    return frozenset(transition_keys(trace))


def is_boundary_attempt_key(key: object) -> bool:
    """Milestone predicate: a boundary-approach attempt key (directed-gradient hit)."""
    return (
        isinstance(key, EffectFeedbackKey)
        and key.kind == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT
    )


def is_external_resolve_key(key: object) -> bool:
    """Milestone predicate: an observed external-resolve key (closer to the boundary)."""
    return (
        isinstance(key, EffectFeedbackKey)
        and key.kind == EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE
    )

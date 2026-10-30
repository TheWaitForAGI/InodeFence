"""Right-censored single-arm roll-up for a large-budget control (e.g. M3.3).

The runtime lane runs the control and determines, per seed, whether its declared
target (a clean exact contract violation) was observed and at which execution. This
module is the EVALUATION-lane statistical roll-up over those per-seed facts: a hit
proportion with a 95% Wilson interval, an observed-only first-hit distribution, the
right-censored no-hit count, and the honest single-arm framing. It consumes abstract
``SeedOutcome`` facts, not raw traces, so it neither re-derives the runtime lane's
clean-hit determination nor depends on any producer or extractor.

Honest framing (fixed before running): this scores ONE arm (a control), so it states
only whether that arm reached the target under the budget -- never an effectiveness or
superiority claim, which needs a baseline comparison (audit EN-008). A no-hit seed is
right-censored at its budget (``> N``), never imputed to a hit. An infrastructure-
incomplete campaign is excluded from the denominator and reported separately; it is
not a no-hit and never silently grows the denominator toward a hit.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

_Z_95 = 1.959963984540054

_COMPARISON_NOTE = (
    "single-arm control; no baseline comparison here, so no effectiveness or "
    "superiority claim (audit EN-008)"
)
_INTERPRETATION_NOTE = (
    "states only whether this arm reached the target under the budget; a no-hit is "
    "not proof the target is unreachable, only that it was not observed within budget"
)


@dataclass(frozen=True, slots=True)
class SeedOutcome:
    """One seed's infrastructure-valid outcome, as the runtime lane determined it.

    ``complete`` is whether the campaign ran its full budget as a valid campaign (an
    infrastructure abort/incomplete run is ``complete=False`` and leaves the hit/censor
    denominator). ``hit`` is the runtime lane's clean-target determination; a hit needs
    a ``complete`` campaign and a 1-based ``first_hit_executions`` within the budget, and
    a non-hit carries ``first_hit_executions=None`` (right-censored at ``budget``).
    """

    seed: int
    budget: int
    complete: bool
    hit: bool
    first_hit_executions: int | None

    def __post_init__(self) -> None:
        if type(self.seed) is not int or type(self.budget) is not int or self.budget <= 0:
            raise ValueError("seed must be int and budget a positive int")
        if type(self.complete) is not bool or type(self.hit) is not bool:
            raise ValueError("complete and hit must be bool")
        if self.hit:
            if not self.complete:
                raise ValueError("a hit requires a complete campaign")
            if type(self.first_hit_executions) is not int or not (
                1 <= self.first_hit_executions <= self.budget
            ):
                raise ValueError("a hit requires a 1-based first-hit index within the budget")
        elif self.first_hit_executions is not None:
            raise ValueError("a non-hit must not carry a first-hit index")


def wilson_interval(hits: int, trials: int, *, z: float = _Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion; clamped to [0, 1].

    Suited to small samples and extreme proportions (0 or 1), unlike the normal
    approximation. ``trials`` must be positive and ``0 <= hits <= trials``.
    """
    if type(hits) is not int or type(trials) is not int or trials <= 0 or not (0 <= hits <= trials):
        raise ValueError("wilson_interval needs 0 <= hits <= trials and trials > 0")
    z2 = z * z
    center = (hits + z2 / 2) / (trials + z2)
    half = (z / (trials + z2)) * math.sqrt(hits * (trials - hits) / trials + z2 / 4)
    return (max(0.0, center - half), min(1.0, center + half))


def right_censored_summary(outcomes: Sequence[SeedOutcome]) -> dict:
    """Roll up per-seed control outcomes with honest denominators and censoring.

    Only complete campaigns enter the hit/censor denominator; incomplete campaigns are
    counted and listed separately. First-hit statistics describe runs with an
    observation only; no-hit seeds are right-censored at their budget.
    """
    complete = [outcome for outcome in outcomes if outcome.complete]
    incomplete = [outcome for outcome in outcomes if not outcome.complete]
    valid = len(complete)
    hits = [outcome for outcome in complete if outcome.hit]
    censored = [outcome for outcome in complete if not outcome.hit]
    first_hits = sorted(
        outcome.first_hit_executions for outcome in hits if outcome.first_hit_executions is not None
    )
    low, high = wilson_interval(len(hits), valid) if valid else (None, None)
    return {
        "schema_version": 1,
        "classification": "single-arm-right-censored-control",
        "number_complete_campaigns": valid,
        "number_incomplete_excluded": len(incomplete),
        "incomplete_seeds": [outcome.seed for outcome in incomplete],
        "number_observed_target": len(hits),
        "observed_proportion": {
            "numerator": len(hits),
            "denominator": valid,
            "value": len(hits) / valid if valid else None,
            "wilson_95_ci": [low, high],
        },
        "first_hit_executions_observed_only": {
            "population": "runs_with_observation_only",
            "unit": "one_based_execution_count",
            "values": first_hits,
            "min": first_hits[0] if first_hits else None,
            "max": first_hits[-1] if first_hits else None,
        },
        "number_right_censored": len(censored),
        "censored": [{"seed": outcome.seed, "budget": outcome.budget} for outcome in censored],
        "censoring": "no-hit right-censored at recorded budget (> N); no imputed hit index",
        "comparison": _COMPARISON_NOTE,
        "interpretation": _INTERPRETATION_NOTE,
    }

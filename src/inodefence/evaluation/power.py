"""Log-rank power and sample-size calculator (Schoenfeld approximation), stdlib-only.

The H-A primary test is the log-rank on T_first (see :mod:`inodefence.evaluation.survival`).
Its power is governed by the number of *events* observed, not the number of campaigns, via
Schoenfeld's approximation: for a two-arm comparison at a target hazard ratio ``HR``, the
required number of events is

    d = (z_alpha + z_beta)^2 * (1 + r)^2 / (r * ln(HR)^2)

where ``r`` is the allocation ratio (treatment campaigns / control campaigns), ``z_alpha`` is
the two-sided normal quantile ``Phi^{-1}(1 - alpha/2)``, and ``z_beta = Phi^{-1}(power)``.

This module turns that relation three ways, with every input an explicit argument so the
EXP-0 pilot's measured values can be substituted later (none are hard-coded here):

* :func:`required_events` -- events needed for a target power at a hazard ratio;
* :func:`power_for_events` -- the power delivered by a given expected event count;
* :func:`events_per_campaign` / :func:`expected_events` -- an exposure model mapping a per-
  execution hazard, budget, abort fraction and aborted-exposure fraction to the expected
  number of events, so campaign counts become event counts;
* :func:`required_campaigns_per_arm` -- inverting the exposure model to the campaigns/arm
  needed for a target power.

Assumptions (stated, not enforced): proportional hazards at the stated ``HR``; a constant
per-execution hazard within a campaign (a first-event-only Poisson exposure, so a campaign
contributes at most one event to T_first); independent campaigns; aborts and administrative
censoring that are non-informative (the exposure model only shortens exposure, it does not
correlate the event with the censoring). These are planning approximations for sizing EXP-3,
not an analysis of EXP-0 data; EXP-0 hits are never used to estimate the hazard (prereg v2).
"""

import math
from statistics import NormalDist

_NORMAL = NormalDist()


def _two_sided_z_alpha(alpha: float) -> float:
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    return _NORMAL.inv_cdf(1.0 - alpha / 2.0)


def _z_beta(power: float) -> float:
    if not 0.0 < power < 1.0:
        raise ValueError("power must be in (0, 1)")
    return _NORMAL.inv_cdf(power)


def required_events(
    hazard_ratio: float, *, power: float = 0.8, alpha: float = 0.05, allocation_ratio: float = 1.0
) -> float:
    """Schoenfeld expected number of events for a two-sided log-rank at ``hazard_ratio``.

    ``allocation_ratio`` ``r`` is treatment/control campaigns (1.0 = balanced). Returns a
    fractional event count; round up for planning. Raises if ``hazard_ratio`` is non-positive
    or exactly 1 (no effect needs infinite events).
    """
    if hazard_ratio <= 0.0:
        raise ValueError("hazard_ratio must be positive")
    if hazard_ratio == 1.0:
        raise ValueError("hazard_ratio = 1 (no effect) requires infinite events")
    if allocation_ratio <= 0.0:
        raise ValueError("allocation_ratio must be positive")
    z_alpha = _two_sided_z_alpha(alpha)
    z_beta = _z_beta(power)
    r = allocation_ratio
    return (z_alpha + z_beta) ** 2 * (1.0 + r) ** 2 / (r * math.log(hazard_ratio) ** 2)


def power_for_events(
    expected_event_count: float,
    hazard_ratio: float,
    *,
    alpha: float = 0.05,
    allocation_ratio: float = 1.0,
) -> float:
    """Power delivered by ``expected_event_count`` events at ``hazard_ratio`` (two-sided).

    Inverts :func:`required_events` for ``z_beta`` and returns ``Phi(z_beta)``, clamped to
    ``(0, 1)``. A non-positive event count yields a power at or below ``alpha``.
    """
    if hazard_ratio <= 0.0 or hazard_ratio == 1.0:
        raise ValueError("hazard_ratio must be positive and not equal to 1")
    if allocation_ratio <= 0.0:
        raise ValueError("allocation_ratio must be positive")
    if expected_event_count <= 0.0:
        return min(alpha, 1.0)
    z_alpha = _two_sided_z_alpha(alpha)
    r = allocation_ratio
    z_beta = (
        math.sqrt(expected_event_count * r / (1.0 + r) ** 2 * math.log(hazard_ratio) ** 2) - z_alpha
    )
    return max(0.0, min(1.0, _NORMAL.cdf(z_beta)))


def events_per_campaign(
    *,
    per_execution_hazard: float,
    budget: int,
    abort_fraction: float = 0.0,
    aborted_exposure_fraction: float = 0.5,
) -> float:
    """Expected probability one campaign contributes a T_first event, from the exposure model.

    A completing campaign is exposed for ``budget`` executions; an aborting campaign for a
    ``aborted_exposure_fraction`` share of that (mean). With a constant per-execution hazard
    ``lambda`` the first-event probability over ``m`` executions is ``1 - exp(-lambda*m)``.
    Returns the abort-weighted mean of that probability -- i.e. events per campaign.
    """
    if per_execution_hazard < 0.0:
        raise ValueError("per_execution_hazard must be non-negative")
    if type(budget) is not int or budget <= 0:
        raise ValueError("budget must be a positive int")
    if not 0.0 <= abort_fraction <= 1.0:
        raise ValueError("abort_fraction must be in [0, 1]")
    if not 0.0 <= aborted_exposure_fraction <= 1.0:
        raise ValueError("aborted_exposure_fraction must be in [0, 1]")
    complete_exposure = budget
    aborted_exposure = budget * aborted_exposure_fraction
    p_complete = 1.0 - math.exp(-per_execution_hazard * complete_exposure)
    p_aborted = 1.0 - math.exp(-per_execution_hazard * aborted_exposure)
    return (1.0 - abort_fraction) * p_complete + abort_fraction * p_aborted


def expected_events(
    *,
    campaigns_per_arm: int,
    per_execution_hazard: float,
    budget: int,
    hazard_ratio: float = 1.0,
    abort_fraction: float = 0.0,
    aborted_exposure_fraction: float = 0.5,
    allocation_ratio: float = 1.0,
) -> dict:
    """Expected T_first events across a control and a treatment arm under the exposure model.

    The control arm has ``campaigns_per_arm`` campaigns at ``per_execution_hazard``; the
    treatment arm has ``allocation_ratio`` times as many campaigns at ``hazard_ratio`` times
    the hazard. Returns per-arm and total expected events (the input to :func:`power_for_events`).
    """
    if type(campaigns_per_arm) is not int or campaigns_per_arm <= 0:
        raise ValueError("campaigns_per_arm must be a positive int")
    control_rate = events_per_campaign(
        per_execution_hazard=per_execution_hazard,
        budget=budget,
        abort_fraction=abort_fraction,
        aborted_exposure_fraction=aborted_exposure_fraction,
    )
    treatment_rate = events_per_campaign(
        per_execution_hazard=per_execution_hazard * hazard_ratio,
        budget=budget,
        abort_fraction=abort_fraction,
        aborted_exposure_fraction=aborted_exposure_fraction,
    )
    control_events = campaigns_per_arm * control_rate
    treatment_campaigns = campaigns_per_arm * allocation_ratio
    treatment_events = treatment_campaigns * treatment_rate
    return {
        "control_campaigns": campaigns_per_arm,
        "treatment_campaigns": treatment_campaigns,
        "control_events_per_campaign": control_rate,
        "treatment_events_per_campaign": treatment_rate,
        "control_expected_events": control_events,
        "treatment_expected_events": treatment_events,
        "total_expected_events": control_events + treatment_events,
    }


def power_from_design(
    *,
    campaigns_per_arm: int,
    per_execution_hazard: float,
    budget: int,
    hazard_ratio: float,
    abort_fraction: float = 0.0,
    aborted_exposure_fraction: float = 0.5,
    alpha: float = 0.05,
    allocation_ratio: float = 1.0,
) -> dict:
    """End-to-end power for a concrete EXP-3 design: campaigns/arm and hazards to power.

    Combines the exposure model (:func:`expected_events`) with the Schoenfeld power
    (:func:`power_for_events`) so a planner can read expected events and power together.
    """
    events = expected_events(
        campaigns_per_arm=campaigns_per_arm,
        per_execution_hazard=per_execution_hazard,
        budget=budget,
        hazard_ratio=hazard_ratio,
        abort_fraction=abort_fraction,
        aborted_exposure_fraction=aborted_exposure_fraction,
        allocation_ratio=allocation_ratio,
    )
    power = power_for_events(
        events["total_expected_events"],
        hazard_ratio,
        alpha=alpha,
        allocation_ratio=allocation_ratio,
    )
    return {**events, "hazard_ratio": hazard_ratio, "alpha": alpha, "power": power}


def required_campaigns_per_arm(
    *,
    per_execution_hazard: float,
    budget: int,
    hazard_ratio: float,
    power: float = 0.8,
    alpha: float = 0.05,
    abort_fraction: float = 0.0,
    aborted_exposure_fraction: float = 0.5,
    allocation_ratio: float = 1.0,
) -> dict:
    """Campaigns per (control) arm needed for ``power`` at ``hazard_ratio`` under the model.

    Uses the Schoenfeld required events and the exposure model's per-campaign event rates,
    counting events contributed by both arms per control campaign. Returns the fractional and
    rounded-up campaign counts plus the required events, so the cost side of the EXP-2 GO/NO-GO
    rule (prereg v2) is explicit.
    """
    needed = required_events(
        hazard_ratio, power=power, alpha=alpha, allocation_ratio=allocation_ratio
    )
    control_rate = events_per_campaign(
        per_execution_hazard=per_execution_hazard,
        budget=budget,
        abort_fraction=abort_fraction,
        aborted_exposure_fraction=aborted_exposure_fraction,
    )
    treatment_rate = events_per_campaign(
        per_execution_hazard=per_execution_hazard * hazard_ratio,
        budget=budget,
        abort_fraction=abort_fraction,
        aborted_exposure_fraction=aborted_exposure_fraction,
    )
    events_per_control_campaign = control_rate + allocation_ratio * treatment_rate
    if events_per_control_campaign <= 0.0:
        raise ValueError("exposure model yields zero events per campaign; cannot size the study")
    fractional = needed / events_per_control_campaign
    control_campaigns = math.ceil(fractional)
    return {
        "hazard_ratio": hazard_ratio,
        "power": power,
        "alpha": alpha,
        "required_events": needed,
        "events_per_control_campaign": events_per_control_campaign,
        "control_campaigns_fractional": fractional,
        "control_campaigns": control_campaigns,
        "treatment_campaigns": math.ceil(control_campaigns * allocation_ratio),
    }

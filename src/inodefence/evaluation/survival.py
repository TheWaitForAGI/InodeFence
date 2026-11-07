"""Right-censored survival roll-up for the H-A matched T_first contrast.

The research-questions v2 primary metric for H-A is **T_first** -- the execution count
of the first ``C1 || C2`` observation, right-censored when a campaign finishes its budget
with no observation (censored at ``N``) or aborts before the budget (censored at the abort
point). This module is the EVALUATION-lane survival roll-up over those per-seed facts:
Kaplan-Meier step curves, the log-rank test (2-arm and k-arm overall), the Vargha-Delaney
A12 effect size, seed-fixed bootstrap confidence intervals, a seed-block *paired* rank test,
and a zero-event rule-of-three fallback. It consumes abstract per-arm ``(time, event)``
facts, never raw traces, so it neither re-derives the runtime lane's clean-hit determination
nor depends on any producer or extractor. It adds to -- and never changes -- the single-arm
Wilson roll-up in :mod:`inodefence.evaluation.right_censored`.

Honest framing (fixed before running, audit EN-008):

* A no-hit seed is right-censored, never imputed to a hit; an *observed* event sets T_first
  at the first observation regardless of a later abort (a pre-abort observation is a real
  event, not a censoring).
* abort censoring is an **assumption**, not an observation: aborts may not be independent of
  arm (informative censoring; e.g. an arm that observes more may also abort more). The three
  :class:`AbortPolicy` conventions BRACKET that assumption; a verdict that flips across them
  is driven by the assumption and must be reported as such, never as a single number.
* A12 and the paired rank test compare *observed magnitudes*; they drop censored observations
  and report how many were dropped. They are supplementary effect sizes, exploratory when
  censoring is heavy. The censoring-aware primary test is the log-rank on the full KM risk set.
* The log-rank p-value and A12 are descriptive statistics over a pre-registered design; they
  are not an effectiveness verdict on their own and never license a CVE/rediscovery claim.
"""

import math
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Observation:
    """One campaign's T_first fact for one arm: a time and whether it is an event.

    ``time`` is a positive 1-based execution count. ``event`` is ``True`` when the first
    ``C1 || C2`` was observed at ``time`` and ``False`` when the campaign was right-censored
    at ``time`` (budget reached with no observation, or aborted at ``time``).
    """

    time: int
    event: bool

    def __post_init__(self) -> None:
        if type(self.time) is not int or self.time <= 0:
            raise ValueError("Observation.time must be a positive 1-based execution count")
        if type(self.event) is not bool:
            raise ValueError("Observation.event must be a bool")


@dataclass(frozen=True, slots=True)
class KMStep:
    """One drop of a Kaplan-Meier curve, recorded only at times where an event occurs."""

    time: int
    at_risk: int
    events: int
    survival: float


def _as_observations(observations: Iterable[Observation]) -> list[Observation]:
    obs = list(observations)
    for item in obs:
        if not isinstance(item, Observation):
            raise TypeError("each observation must be an Observation instance")
    return obs


def kaplan_meier(observations: Iterable[Observation]) -> list[KMStep]:
    """Kaplan-Meier survival estimate S(t) for T_first, stepping only at event times.

    Censored observations leave the at-risk set at their time without dropping S(t); ties
    between events and censors at the same time treat events as occurring first (standard).
    The returned steps are ordered by time; ``survival`` is S(t) just after each event time.
    """
    obs = _as_observations(observations)
    if not obs:
        return []
    event_times = sorted({item.time for item in obs if item.event})
    survival = 1.0
    steps: list[KMStep] = []
    for t in event_times:
        at_risk = sum(1 for item in obs if item.time >= t)
        events = sum(1 for item in obs if item.event and item.time == t)
        survival *= 1.0 - events / at_risk
        steps.append(KMStep(time=t, at_risk=at_risk, events=events, survival=survival))
    return steps


def km_median(steps: Sequence[KMStep]) -> int | None:
    """Median survival time: the first event time at which S(t) <= 0.5, else ``None``.

    ``None`` means the curve never reached 0.5 within the observed budget; the median is
    then right-censored and must not be imputed.
    """
    for step in steps:
        if step.survival <= 0.5:
            return step.time
    return None


@dataclass(frozen=True, slots=True)
class _RiskRow:
    """Pooled risk set at one event time, used by the log-rank construction."""

    time: int
    total_at_risk: int
    total_events: int
    at_risk: tuple[int, ...]
    events: tuple[int, ...]


def _risk_table(arms: Sequence[list[Observation]]) -> list[_RiskRow]:
    pooled_event_times = sorted({item.time for arm in arms for item in arm if item.event})
    rows: list[_RiskRow] = []
    for t in pooled_event_times:
        at_risk = tuple(sum(1 for item in arm if item.time >= t) for arm in arms)
        events = tuple(sum(1 for item in arm if item.event and item.time == t) for arm in arms)
        rows.append(
            _RiskRow(
                time=t,
                total_at_risk=sum(at_risk),
                total_events=sum(events),
                at_risk=at_risk,
                events=events,
            )
        )
    return rows


def _invert(matrix: list[list[float]]) -> list[list[float]]:
    """Invert a small square matrix by Gauss-Jordan elimination (pure Python)."""
    n = len(matrix)
    aug = [list(row) + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("log-rank covariance matrix is singular; check for empty arms")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        pivot_value = aug[col][col]
        aug[col] = [value / pivot_value for value in aug[col]]
        for other in range(n):
            if other == col:
                continue
            factor = aug[other][col]
            if factor != 0.0:
                aug[other] = [a - factor * b for a, b in zip(aug[other], aug[col], strict=True)]
    return [row[n:] for row in aug]


def logrank_test(arms: Mapping[str, Sequence[Observation]]) -> dict:
    """Log-rank test over two or more arms of right-censored T_first observations.

    Uses the standard hypergeometric construction: at each pooled event time the observed and
    expected events per arm are accumulated with the hypergeometric covariance. For two arms
    the statistic is ``(O1 - E1)^2 / V11``; for ``k`` arms it is the quadratic form over any
    ``k-1`` arms with the covariance's generalized inverse, with ``df = k - 1``. The returned
    ``p_value`` is the chi-square upper tail. Larger arm-level ``observed - expected`` means
    that arm's events came *earlier* (faster T_first).
    """
    names = list(arms)
    if len(names) < 2:
        raise ValueError("log-rank needs at least two arms")
    columns = [_as_observations(arms[name]) for name in names]
    for column in columns:
        if not column:
            raise ValueError("every arm needs at least one observation")
    rows = _risk_table(columns)
    k = len(names)
    observed = [0.0] * k
    expected = [0.0] * k
    covariance = [[0.0] * (k - 1) for _ in range(k - 1)]
    for row in rows:
        n, d = row.total_at_risk, row.total_events
        for g in range(k):
            observed[g] += row.events[g]
            expected[g] += d * row.at_risk[g] / n
        if n <= 1:
            continue
        variance_scale = d * (n - d) / (n - 1)
        for g in range(k - 1):
            fraction_g = row.at_risk[g] / n
            covariance[g][g] += variance_scale * fraction_g * (1.0 - fraction_g)
            for h in range(g + 1, k - 1):
                term = -variance_scale * fraction_g * (row.at_risk[h] / n)
                covariance[g][h] += term
                covariance[h][g] += term
    deviation = [observed[g] - expected[g] for g in range(k - 1)]
    inverse = _invert(covariance)
    statistic = sum(
        deviation[i] * inverse[i][j] * deviation[j] for i in range(k - 1) for j in range(k - 1)
    )
    statistic = max(0.0, statistic)
    df = k - 1
    return {
        "arms": names,
        "observed_events": {names[g]: observed[g] for g in range(k)},
        "expected_events": {names[g]: expected[g] for g in range(k)},
        "chi_square": statistic,
        "degrees_of_freedom": df,
        "p_value": chi_square_sf(statistic, df),
        "number_event_times": len(rows),
        "note": (
            "censoring-aware primary comparison of T_first; observed-minus-expected > 0 means "
            "earlier (faster) events for that arm. Not an effectiveness verdict on its own."
        ),
    }


def _lower_gamma_series(a: float, x: float) -> float:
    term = 1.0 / a
    total = term
    n = a
    for _ in range(1000):
        n += 1.0
        term *= x / n
        total += term
        if abs(term) < abs(total) * 1e-15:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _upper_gamma_cf(a: float, x: float) -> float:
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def chi_square_sf(x: float, df: int) -> float:
    """Upper-tail probability P(X >= x) for a chi-square with ``df`` degrees of freedom.

    Computed stdlib-only from the regularized upper incomplete gamma ``Q(df/2, x/2)`` via a
    power series below the crossover and a continued fraction above it.
    """
    if df < 1:
        raise ValueError("degrees of freedom must be a positive integer")
    if x <= 0.0:
        return 1.0
    a = df / 2.0
    half = x / 2.0
    if half < a + 1.0:
        return max(0.0, min(1.0, 1.0 - _lower_gamma_series(a, half)))
    return max(0.0, min(1.0, _upper_gamma_cf(a, half)))


def a12(faster_is_smaller_a: Sequence[float], b: Sequence[float]) -> float:
    """Vargha-Delaney A measure A(a>b) = P(a > b) + 0.5 * P(a == b) over raw magnitudes.

    This is the plain stochastic-superiority statistic: 0.5 is no effect, > 0.5 means sample
    ``a`` tends to hold the *larger* values. For T_first, where smaller is faster, call this
    with the slower arm first (or read ``1 - A`` as "a is faster"). Ties contribute 0.5. Both
    samples must be non-empty; censoring is not modeled here -- pass observed magnitudes only.
    """
    xs, ys = list(faster_is_smaller_a), list(b)
    if not xs or not ys:
        raise ValueError("a12 needs two non-empty samples of observed magnitudes")
    greater = sum(1 for x in xs for y in ys if x > y)
    equal = sum(1 for x in xs for y in ys if x == y)
    return (greater + 0.5 * equal) / (len(xs) * len(ys))


def _observed_times(observations: Iterable[Observation]) -> list[int]:
    return [item.time for item in observations if item.event]


def a12_first_faster(arm_a: Sequence[Observation], arm_b: Sequence[Observation]) -> dict:
    """A12 oriented so > 0.5 means arm_a reaches T_first *faster* (smaller times win).

    Compares only observed (event) times and reports how many censored observations were
    dropped per arm, because a censored time has no defined magnitude. Returns ``None`` for
    the statistic when either arm has no observed event.
    """
    a_obs, b_obs = _as_observations(arm_a), _as_observations(arm_b)
    a_times, b_times = _observed_times(a_obs), _observed_times(b_obs)
    value = None if not a_times or not b_times else 1.0 - a12(a_times, b_times)
    return {
        "a12_a_faster": value,
        "orientation": "P(a reaches T_first before b) + 0.5*P(tie); 0.5 is no effect",
        "number_observed": {"a": len(a_times), "b": len(b_times)},
        "number_censored_dropped": {
            "a": len(a_obs) - len(a_times),
            "b": len(b_obs) - len(b_times),
        },
        "note": (
            "supplementary effect size over observed magnitudes only. Dropping censored "
            "observations is a systematic bias, not noise: removing the campaigns that "
            "never reached the event makes the arm with more censoring look faster, so "
            "read it as exploratory only when censoring is heavy. The censoring-aware "
            "comparison is the log-rank test."
        ),
    }


def bootstrap_ci(
    statistic: Callable[..., float],
    *samples: Sequence[float],
    seed: int,
    resamples: int = 2000,
    alpha: float = 0.05,
) -> dict:
    """Seed-fixed percentile bootstrap CI for a statistic of one or more independent samples.

    Each sample is resampled with replacement to its own size using ``random.Random(seed)``;
    the exact ``seed`` makes the interval reproducible. Resamples on which the statistic is
    undefined (raising ``ValueError`` / ``ZeroDivisionError``) are skipped and counted.
    """
    pools = [list(sample) for sample in samples]
    if any(not pool for pool in pools):
        raise ValueError("every sample must be non-empty")
    if resamples < 1:
        raise ValueError("resamples must be positive")
    rng = random.Random(seed)
    point = statistic(*pools)
    values: list[float] = []
    skipped = 0
    for _ in range(resamples):
        draw = [[rng.choice(pool) for _ in pool] for pool in pools]
        try:
            values.append(statistic(*draw))
        except (ValueError, ZeroDivisionError):
            skipped += 1
    if not values:
        raise ValueError("statistic was undefined on every bootstrap resample")
    values.sort()
    low = values[max(0, math.floor((alpha / 2) * len(values)))]
    high = values[min(len(values) - 1, math.ceil((1 - alpha / 2) * len(values)) - 1)]
    return {
        "point_estimate": point,
        "confidence": 1 - alpha,
        "ci": [low, high],
        "method": "seed-fixed percentile bootstrap",
        "seed": seed,
        "resamples_used": len(values),
        "resamples_skipped_undefined": skipped,
    }


class AbortPolicy(StrEnum):
    """How an aborted no-observation campaign enters the T_first risk set.

    An aborted campaign that *did* observe an event keeps its event time under every policy
    (a pre-abort observation is a real event). These policies only change how an aborted
    campaign with **no** observation is treated, and together they bracket the informative-
    censoring assumption so a reader can see whether a verdict depends on it.
    """

    CENSOR_AT_ABORT = "censor-at-abort"
    CENSOR_AT_BUDGET = "censor-at-budget"
    EXCLUDE = "exclude"


@dataclass(frozen=True, slots=True)
class SeedRecord:
    """One seed's runtime-lane T_first fact for one arm, before a censoring convention.

    ``status`` is ``"complete"`` (ran the full budget) or ``"abort"`` (stopped early).
    ``first_event_executions`` is the 1-based execution of the first ``C1 || C2`` if one was
    observed (``None`` otherwise). ``abort_executions`` is the 1-based execution at which an
    abort stopped the campaign; it is required for an aborted seed and must be ``None`` for a
    complete seed. An observed event may precede an abort.
    """

    seed: int
    budget: int
    status: str
    first_event_executions: int | None
    abort_executions: int | None = None

    def __post_init__(self) -> None:
        if type(self.seed) is not int or type(self.budget) is not int or self.budget <= 0:
            raise ValueError("seed must be int and budget a positive int")
        if self.status not in ("complete", "abort"):
            raise ValueError("status must be 'complete' or 'abort'")
        event = self.first_event_executions
        if event is not None and (type(event) is not int or not (1 <= event <= self.budget)):
            raise ValueError("first_event_executions must be a 1-based index within the budget")
        abort = self.abort_executions
        if self.status == "abort":
            if type(abort) is not int or not (1 <= abort <= self.budget):
                raise ValueError("an aborted seed needs a 1-based abort index within the budget")
            if event is not None and event > abort:
                raise ValueError("an observed event cannot occur after the abort point")
        elif abort is not None:
            raise ValueError("a complete seed must not carry an abort index")


def to_observation(record: SeedRecord, policy: AbortPolicy) -> Observation | None:
    """Project one :class:`SeedRecord` to an :class:`Observation` under a censoring policy.

    An observed event always yields ``event=True`` at its first-event time. A no-observation
    complete seed is censored at the budget. A no-observation aborted seed follows ``policy``:
    censored at the abort point, censored at the budget, or excluded (``None``).
    """
    if record.first_event_executions is not None:
        return Observation(time=record.first_event_executions, event=True)
    if record.status == "complete":
        return Observation(time=record.budget, event=False)
    if policy is AbortPolicy.EXCLUDE:
        return None
    if policy is AbortPolicy.CENSOR_AT_BUDGET:
        return Observation(time=record.budget, event=False)
    assert record.abort_executions is not None
    return Observation(time=record.abort_executions, event=False)


def observations_for_policy(
    records: Iterable[SeedRecord], policy: AbortPolicy
) -> list[Observation]:
    """Project a set of seed records to observations under one abort-censoring policy."""
    projected = (to_observation(record, policy) for record in records)
    return [item for item in projected if item is not None]


def sensitivity_arms(
    arms: Mapping[str, Sequence[SeedRecord]],
) -> dict:
    """Run the log-rank test under all three abort-censoring policies for a sensitivity read.

    A verdict (sign of the per-arm observed-minus-expected, or the p-value crossing a
    threshold) that is stable across the three policies is robust to the abort assumption;
    one that flips is driven by it. This function reports every policy's result side by side
    and never collapses them to a single number.
    """
    results = {}
    for policy in AbortPolicy:
        projected = {
            name: observations_for_policy(records, policy) for name, records in arms.items()
        }
        non_empty = {name: obs for name, obs in projected.items() if obs}
        if len(non_empty) < 2:
            results[policy.value] = {"skipped": "fewer than two non-empty arms under this policy"}
            continue
        results[policy.value] = {
            "number_in_risk_set": {name: len(obs) for name, obs in projected.items()},
            "logrank": logrank_test(non_empty),
        }
    return {
        "classification": "abort-censoring-sensitivity",
        "policies": results,
        "note": (
            "three conventions bracket the informative-censoring assumption on aborts; a "
            "verdict stable across them is robust, one that flips is assumption-driven "
            "(audit EN-008)"
        ),
    }


def _midranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def wilcoxon_signed_rank(differences: Sequence[float]) -> dict:
    """Two-sided Wilcoxon signed-rank test on paired differences (zeros dropped).

    Ranks ``|d|`` with midranks for ties and sums the positive-sign ranks (``W+``). For up to
    20 nonzero differences the p-value is exact by enumerating the ``2^n`` sign assignments of
    the rank vector; above that it is the tie-corrected normal approximation with a continuity
    correction. Zero differences are dropped and counted (standard Wilcoxon handling).
    """
    nonzero = [d for d in differences if d != 0]
    dropped_zero = len(differences) - len(nonzero)
    n = len(nonzero)
    if n == 0:
        return {
            "statistic_w_plus": None,
            "p_value": None,
            "number_pairs": len(differences),
            "number_nonzero": 0,
            "number_zero_dropped": dropped_zero,
            "method": "undefined (no nonzero differences)",
        }
    ranks = _midranks([abs(d) for d in nonzero])
    w_plus = sum(rank for rank, d in zip(ranks, nonzero, strict=False) if d > 0)
    total_rank = sum(ranks)
    if n <= 20:
        count_le = 0
        count_ge = 0
        target_low = min(w_plus, total_rank - w_plus)
        target_high = max(w_plus, total_rank - w_plus)
        for pattern in range(1 << n):
            value = sum(ranks[i] for i in range(n) if pattern & (1 << i))
            if value <= target_low:
                count_le += 1
            if value >= target_high:
                count_ge += 1
        p_value = min(1.0, (count_le + count_ge) / (1 << n))
        method = "exact (sign enumeration)"
    else:
        tie_adjust = 0.0
        counts: dict[float, int] = {}
        for rank in ranks:
            counts[rank] = counts.get(rank, 0) + 1
        for size in counts.values():
            tie_adjust += size**3 - size
        mean = n * (n + 1) / 4.0
        variance = n * (n + 1) * (2 * n + 1) / 24.0 - tie_adjust / 48.0
        if variance <= 0:
            p_value = 1.0
        else:
            z = (abs(w_plus - mean) - 0.5) / math.sqrt(variance)
            p_value = min(1.0, math.erfc(z / math.sqrt(2.0)))
        method = "normal approximation (tie- and continuity-corrected)"
    return {
        "statistic_w_plus": w_plus,
        "p_value": p_value,
        "number_pairs": len(differences),
        "number_nonzero": n,
        "number_zero_dropped": dropped_zero,
        "method": method,
    }


def paired_permutation_test(
    differences: Sequence[float], *, seed: int, resamples: int = 10000
) -> dict:
    """Two-sided paired sign-flip permutation test on the mean of paired differences.

    Under the null each difference's sign is equally likely to flip. For up to 20 nonzero
    differences every sign pattern is enumerated (exact); above that ``resamples`` random
    flips are drawn with ``random.Random(seed)``. The p-value is the share of flips whose mean
    is at least as extreme (in absolute value) as the observed mean.
    """
    nonzero = [d for d in differences if d != 0]
    n = len(nonzero)
    if n == 0:
        return {
            "observed_mean": 0.0,
            "p_value": None,
            "number_nonzero": 0,
            "method": "undefined (no nonzero differences)",
        }
    observed = abs(sum(nonzero))
    if n <= 20:
        extreme = 0
        for pattern in range(1 << n):
            signed = sum(nonzero[i] if pattern & (1 << i) else -nonzero[i] for i in range(n))
            if abs(signed) >= observed - 1e-12:
                extreme += 1
        p_value = extreme / (1 << n)
        method = "exact (sign enumeration)"
        draws = 1 << n
    else:
        rng = random.Random(seed)
        extreme = 0
        for _ in range(resamples):
            signed = sum(d if rng.random() < 0.5 else -d for d in nonzero)
            if abs(signed) >= observed - 1e-12:
                extreme += 1
        p_value = extreme / resamples
        method = "random sign-flip permutation"
        draws = resamples
    return {
        "observed_mean": sum(nonzero) / n,
        "p_value": min(1.0, p_value),
        "number_nonzero": n,
        "method": method,
        "number_sign_patterns": draws,
        "seed": seed,
    }


def seed_block_paired(
    arm_a: Mapping[int, SeedRecord],
    arm_b: Mapping[int, SeedRecord],
    *,
    policy: AbortPolicy = AbortPolicy.CENSOR_AT_ABORT,
    seed: int = 0,
) -> dict:
    """Seed-block paired T_first comparison: rank/sign tests on same-seed differences.

    The matched design assigns the same seed to both arms, so same-seed T_first values are
    paired. A difference ``t_a - t_b`` is only defined when *both* arms observed an event at
    that seed; seed-blocks where either arm is censored are dropped and counted, because the
    difference of censored times is undefined. Reports both the Wilcoxon signed-rank and the
    paired sign-flip permutation p-value over the usable differences.
    """
    shared = sorted(set(arm_a) & set(arm_b))
    differences: list[float] = []
    usable_seeds: list[int] = []
    dropped_censored: list[int] = []
    for s in shared:
        obs_a = to_observation(arm_a[s], policy)
        obs_b = to_observation(arm_b[s], policy)
        if obs_a is not None and obs_b is not None and obs_a.event and obs_b.event:
            differences.append(obs_a.time - obs_b.time)
            usable_seeds.append(s)
        else:
            dropped_censored.append(s)
    result = {
        "classification": "seed-block-paired-t-first",
        "policy": policy.value,
        "number_shared_seeds": len(shared),
        "number_pairs_both_observed": len(usable_seeds),
        "number_dropped_censored_or_unobserved": len(dropped_censored),
        "usable_seeds": usable_seeds,
        "dropped_seeds": dropped_censored,
        "difference_convention": "t_a - t_b (negative means arm_a reached T_first earlier)",
        "note": (
            "pairs need an observed event in BOTH arms; a difference of censored times is "
            "undefined and the seed-block is dropped and counted. With few both-observed "
            "pairs this paired test is exploratory (audit EN-008)."
        ),
    }
    if differences:
        result["wilcoxon_signed_rank"] = wilcoxon_signed_rank(differences)
        result["paired_permutation"] = paired_permutation_test(differences, seed=seed)
    return result


def rule_of_three(n: int) -> float:
    """Upper 95% bound ``3/n`` on an unobserved-event rate given ``n`` null campaigns."""
    if type(n) is not int or n <= 0:
        raise ValueError("rule_of_three needs a positive campaign count")
    return 3.0 / n


def zero_event_summary(arms: Mapping[str, Sequence[Observation]]) -> dict:
    """Campaign-unit rule-of-three fallback for the all-arms-zero-event scenario (judgment 5).

    Requires that NO arm observed any event; otherwise a survival comparison applies and this
    is the wrong roll-up (raises). Reports each arm's campaign count and its ``3/n`` upper
    bound, labeled exploratory: the execution-unit T_first analysis is undefined with zero
    events, so only the coarse campaign-unit bound is honest here.
    """
    per_arm = {}
    for name, observations in arms.items():
        obs = _as_observations(observations)
        if any(item.event for item in obs):
            raise ValueError(f"arm {name!r} has an observed event; zero_event_summary misapplied")
        if not obs:
            raise ValueError(f"arm {name!r} has no campaigns")
        per_arm[name] = {
            "number_complete_null_campaigns": len(obs),
            "rule_of_three_upper_95": rule_of_three(len(obs)),
        }
    return {
        "classification": "all-arms-zero-event-rule-of-three",
        "unit": "campaign (not execution)",
        "label": "exploratory",
        "arms": per_arm,
        "note": (
            "judgment scenario 5: all arms observed zero events, so the execution-unit "
            "T_first survival analysis is undefined; only the coarse campaign-unit 3/n upper "
            "bound is reported, with the denominator stated (research-questions v2)."
        ),
    }


_DEFAULT_FIELD_MAP = {
    "seed": "seed",
    "budget": "budget",
    "status": "status",
    "first_event_executions": "first_event_executions",
    "abort_executions": "abort_executions",
}


def seed_records_from_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    field_map: Mapping[str, str] | None = None,
) -> list[SeedRecord]:
    """Adapter: read runner-output rows into :class:`SeedRecord` via a configurable field map.

    The default map uses this package's own field names; pass ``field_map`` to rename a key
    when the runtime lane (lane 5) ships a different runner-output schema -- the one place a
    producer-specific field name is bound, so the rest of this module stays producer-agnostic.
    A missing optional field (``abort_executions``) reads as ``None``.
    """
    mapping = {**_DEFAULT_FIELD_MAP, **(field_map or {})}
    records: list[SeedRecord] = []
    for row in rows:
        first_event = row.get(mapping["first_event_executions"])
        abort = row.get(mapping["abort_executions"])
        records.append(
            SeedRecord(
                seed=int(row[mapping["seed"]]),  # type: ignore[arg-type]
                budget=int(row[mapping["budget"]]),  # type: ignore[arg-type]
                status=str(row[mapping["status"]]),
                first_event_executions=None if first_event is None else int(first_event),  # type: ignore[arg-type]
                abort_executions=None if abort is None else int(abort),  # type: ignore[arg-type]
            )
        )
    return records


def _two_arm_logrank_chi2(group_a: Sequence[Observation], group_b: Sequence[Observation]) -> float:
    """Two-arm log-rank chi-square (0.0 when there are no events in the pooled risk set).

    With zero events the statistic is undefined (the covariance is singular -- no risk-set
    transitions); that is the no-evidence case, so it is reported as 0.0 rather than raised.
    """
    if not any(o.event for o in [*group_a, *group_b]):
        return 0.0
    stat = logrank_test({"a": list(group_a), "b": list(group_b)})["chi_square"]
    return float(stat) if stat is not None else 0.0


def _two_arm_logrank_observed(
    group_a: Sequence[Observation], group_b: Sequence[Observation]
) -> tuple[float, float]:
    """Observed two-arm log-rank chi-square and the signed ``O_a - E_a`` for arm ``a``.

    ``O_a - E_a > 0`` means arm ``a`` had more events than the null expects -- for
    right-censored T_first that is EARLIER events, i.e. arm ``a`` is the *faster* arm; ``< 0``
    means arm ``b`` is faster. The chi-square itself is direction-agnostic (two-sided), so this
    signed quantity is what tells a rejection apart as acceleration vs the reverse. Zero events
    -> ``(0.0, 0.0)`` (no evidence, no direction).
    """
    if not any(o.event for o in [*group_a, *group_b]):
        return 0.0, 0.0
    result = logrank_test({"a": list(group_a), "b": list(group_b)})
    chi2 = result["chi_square"]
    oe_a = result["observed_events"]["a"] - result["expected_events"]["a"]
    return (float(chi2) if chi2 is not None else 0.0), float(oe_a)


def seed_block_logrank_permutation(
    blocks: Sequence[tuple[Observation, Observation]],
    *,
    seed: int = 0,
    max_exact_blocks: int = 12,
    resamples: int = 10000,
) -> dict:
    """Stratified seed-block arm-label permutation log-rank -- ``exact-logrank-permutation-v1``.

    Each block is one seed's paired ``(arm_a, arm_b)`` T_first observations. Under the null the
    two arms are exchangeable WITHIN a seed, so the reference distribution permutes arm labels
    block-by-block (never across seeds); this respects the paired design that the ordinary
    two-sample log-rank's independence assumption violates. The statistic is the two-arm
    log-rank chi-square and the p-value is ``P(chi2_permuted >= chi2_observed)``. For up to
    ``max_exact_blocks`` blocks all ``2^n`` label assignments are enumerated EXACTLY; above that
    a ``seed``-fixed Monte-Carlo sample of ``resamples`` draws is used with a 95% binomial CI on
    the p-value. Valid at any n (no asymptotic assumption): with few/no events it correctly
    returns p near 1. ``total_events`` is the observed event count over both arms -- the caller
    flags underpowered and adds the rule-of-three bound below the registered ``event_threshold``;
    this function never switches the test.
    """
    blocks = list(blocks)
    n = len(blocks)
    if n == 0:
        return {
            "test": "exact-logrank-permutation-v1",
            "exact": None,
            "p_value": None,
            "observed_chi_square": None,
            "number_blocks": 0,
            "total_events": 0,
            "note": "no paired seed blocks (no seed observed in both arms)",
        }
    group_a = [a for a, _ in blocks]
    group_b = [b for _, b in blocks]
    observed, observed_oe_a = _two_arm_logrank_observed(group_a, group_b)
    total_events = sum(1 for obs in [*group_a, *group_b] if obs.event)
    eps = 1e-9

    def stat_for(bits: Sequence[int]) -> float:
        a = [blocks[i][1] if bit else blocks[i][0] for i, bit in enumerate(bits)]
        b = [blocks[i][0] if bit else blocks[i][1] for i, bit in enumerate(bits)]
        return _two_arm_logrank_chi2(a, b)

    if n <= max_exact_blocks:
        total = 1 << n
        ge = sum(
            1
            for mask in range(total)
            if stat_for([(mask >> i) & 1 for i in range(n)]) >= observed - eps
        )
        return {
            "test": "exact-logrank-permutation-v1",
            "exact": True,
            "p_value": ge / total,
            "observed_chi_square": observed,
            "observed_minus_expected_a": observed_oe_a,
            "number_blocks": n,
            "number_permutations": total,
            "total_events": total_events,
            "note": "exact: all 2^n within-seed arm-label assignments enumerated",
        }
    rng = random.Random(seed)
    ge = 0
    for _ in range(resamples):
        if stat_for([rng.getrandbits(1) for _ in range(n)]) >= observed - eps:
            ge += 1
    p = ge / resamples
    half = 1.96 * math.sqrt(max(p * (1.0 - p), 0.0) / resamples)
    return {
        "test": "exact-logrank-permutation-v1",
        "exact": False,
        "p_value": p,
        "p_value_mc_ci95": [max(0.0, p - half), min(1.0, p + half)],
        "observed_chi_square": observed,
        "observed_minus_expected_a": observed_oe_a,
        "number_blocks": n,
        "resamples": resamples,
        "seed": seed,
        "total_events": total_events,
        "note": f"monte-carlo: 2^{n} too large to enumerate; seed-fixed {resamples} draws",
    }


def holm_adjust(pvalues: Sequence[float]) -> list[float]:
    """Holm step-down FWER-adjusted p-values, returned in input order.

    For ``m`` raw p-values the j-th smallest (0-based) is scaled by ``m - j``, the sequence is
    made monotone non-decreasing, then capped at 1. Reject a hypothesis at level ``alpha`` iff
    its adjusted p-value is ``<= alpha``; this controls the family-wise error at ``alpha``
    without an independence assumption, and dominates Bonferroni. ``None`` is not accepted --
    resolve an undefined p-value (e.g. no seed blocks) to ``1.0`` before calling.
    """
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * pvalues[idx])
        adjusted[idx] = min(1.0, running)
    return adjusted

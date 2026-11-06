"""Arm x abort independence test for the informative-censoring reporting flag (audit 13a).

The H-A survival analysis right-censors aborted campaigns (see
:mod:`inodefence.evaluation.survival`). That is only valid if aborting is independent of arm;
if an arm that reaches more violations also aborts more (informative censoring, e.g. the s118
"65 hits then abort" case), the censoring is not ignorable and a single survival verdict would
mislead. Audit item 13(a) therefore asks for an arm x abort independence check on the
per-campaign contingency table (arm x {complete, aborted, invalid}) that lane 3's abort roll-up
produces.

This module runs that check two ways -- Fisher's exact test (2x2 exact; r x c by exact
enumeration of tables with the observed margins, i.e. Fisher-Freeman-Halton; a seeded
permutation fallback when the exact space is too large) and the chi-square test of independence
(reusing :func:`inodefence.evaluation.survival.chi_square_sf`) -- and emits a **reporting flag**,
never a verdict. The pre-registration owns the verdict; this flag only says whether the main
report should additionally carry the three-policy abort-censoring sensitivity:

* ``not_assessable`` -- no abort events (or <2 arms with data); independence cannot be tested.
* ``independence_assumption_retained`` -- p > ``flag_alpha`` (default 0.1): no evidence against
  independence at this (usually low) power; the single-policy survival report stands.
* ``report_sensitivity`` -- p <= ``flag_alpha``: arm and abort may be dependent, so the main
  report should carry the :func:`inodefence.evaluation.survival.sensitivity_arms` three-policy
  result, not a single censored verdict.

Everything here is a descriptive statistic over observed counts; it never re-derives a runtime
determination and makes no effectiveness claim.
"""

import math
import random
from collections.abc import Sequence

from .survival import chi_square_sf

_Row = Sequence[int]
_Table = Sequence[Sequence[int]]
_TIE = 1e-7


def _validate(table: _Table) -> tuple[list[list[int]], list[int], list[int], int]:
    rows = [list(row) for row in table]
    if not rows or not rows[0]:
        raise ValueError("table must be a non-empty 2D matrix")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("every row must have the same number of columns")
    if any(type(cell) is not int or cell < 0 for row in rows for cell in row):
        raise ValueError("counts must be non-negative integers")
    row_sums = [sum(row) for row in rows]
    col_sums = [sum(rows[i][j] for i in range(len(rows))) for j in range(width)]
    return rows, row_sums, col_sums, sum(row_sums)


def is_assessable(table: _Table) -> tuple[bool, str | None]:
    """Independence is assessable only with at least two non-empty rows and columns."""
    rows, row_sums, col_sums, total = _validate(table)
    if total == 0:
        return False, "no observations"
    if sum(1 for s in row_sums if s > 0) < 2:
        return False, "fewer than two arms have any campaign"
    if sum(1 for s in col_sums if s > 0) < 2:
        return False, "only one outcome category is non-empty (no abort/invalid variation)"
    return True, None


def chi_square_independence(table: _Table) -> dict:
    """Pearson chi-square test of independence for an r x c contingency table.

    ``df = (r-1)(c-1)``; expected ``E_ij = row_i * col_j / N``. Reports the minimum expected
    count (a cell < 5 makes the chi-square approximation unreliable -- prefer Fisher then).
    """
    rows, row_sums, col_sums, total = _validate(table)
    assessable, reason = is_assessable(table)
    if not assessable:
        return {"test": "chi_square", "assessable": False, "reason": reason, "p_value": None}
    nrows, ncols = len(rows), len(rows[0])
    statistic = 0.0
    min_expected = math.inf
    for i in range(nrows):
        for j in range(ncols):
            expected = row_sums[i] * col_sums[j] / total
            if expected > 0:
                statistic += (rows[i][j] - expected) ** 2 / expected
                min_expected = min(min_expected, expected)
    df = (nrows - 1) * (ncols - 1)
    return {
        "test": "chi_square",
        "assessable": True,
        "chi_square": statistic,
        "degrees_of_freedom": df,
        "p_value": chi_square_sf(statistic, df) if df >= 1 else None,
        "min_expected_count": min_expected,
        "low_expected_warning": min_expected < 5,
    }


def _log_factorial(n: int) -> float:
    return math.lgamma(n + 1)


def _log_prob(rows: list[list[int]], row_sums: list[int], col_sums: list[int], total: int) -> float:
    """Log probability of a table given fixed margins (multiple-hypergeometric)."""
    numerator = sum(_log_factorial(s) for s in row_sums) + sum(_log_factorial(s) for s in col_sums)
    denominator = _log_factorial(total) + sum(_log_factorial(cell) for row in rows for cell in row)
    return numerator - denominator


def _count_table_space(row_sums: list[int], col_sums: list[int]) -> int:
    """Rough upper bound on the number of tables with these margins (for the exact guard)."""
    bound = 1
    for i in range(len(row_sums) - 1):
        for j in range(len(col_sums) - 1):
            bound *= min(row_sums[i], col_sums[j]) + 1
    return bound


def _enumerate_tables(row_sums: list[int], col_sums: list[int]):
    """Yield every non-negative integer table with the given row and column sums."""
    nrows, ncols = len(row_sums), len(col_sums)
    free = [(i, j) for i in range(nrows - 1) for j in range(ncols - 1)]
    table = [[0] * ncols for _ in range(nrows)]

    def rec(k: int):
        if k == len(free):
            for i in range(nrows - 1):
                last = row_sums[i] - sum(table[i][j] for j in range(ncols - 1))
                if last < 0:
                    return
                table[i][ncols - 1] = last
            for j in range(ncols):
                last = col_sums[j] - sum(table[i][j] for i in range(nrows - 1))
                if last < 0:
                    return
                table[nrows - 1][j] = last
            if sum(table[nrows - 1]) != row_sums[nrows - 1]:
                return
            yield [row[:] for row in table]
            return
        i, j = free[k]
        placed_row = sum(table[i][jj] for jj in range(ncols - 1))
        placed_col = sum(table[ii][j] for ii in range(nrows - 1))
        upper = min(row_sums[i] - placed_row, col_sums[j] - placed_col)
        for value in range(upper + 1):
            table[i][j] = value
            yield from rec(k + 1)
            table[i][j] = 0

    yield from rec(0)


def fisher_exact(table: _Table, *, max_exact_tables: int = 200_000, seed: int = 0) -> dict:
    """Two-sided Fisher exact test of independence (2x2 exact; r x c by exact enumeration).

    Sums the hypergeometric probability of every table with the observed margins whose
    probability is <= that of the observed table (standard two-sided Fisher / Freeman-Halton).
    When the exact table space exceeds ``max_exact_tables`` it falls back to a seeded Monte
    Carlo permutation p-value (:func:`monte_carlo_independence`) and labels the method so.
    """
    rows, row_sums, col_sums, total = _validate(table)
    assessable, reason = is_assessable(table)
    if not assessable:
        return {"test": "fisher_exact", "assessable": False, "reason": reason, "p_value": None}
    if _count_table_space(row_sums, col_sums) > max_exact_tables:
        result = monte_carlo_independence(table, seed=seed)
        result["exact"] = False
        return result
    observed_log_prob = _log_prob(rows, row_sums, col_sums, total)
    p_value = 0.0
    total_prob = 0.0
    tables = 0
    for candidate in _enumerate_tables(row_sums, col_sums):
        tables += 1
        log_prob = _log_prob(candidate, row_sums, col_sums, total)
        probability = math.exp(log_prob)
        total_prob += probability
        if log_prob <= observed_log_prob + _TIE:
            p_value += probability
    return {
        "test": "fisher_exact",
        "assessable": True,
        "exact": True,
        "p_value": min(1.0, p_value / total_prob if total_prob else 1.0),
        "number_tables_enumerated": tables,
    }


def monte_carlo_independence(table: _Table, *, seed: int, resamples: int = 20_000) -> dict:
    """Seeded permutation p-value for independence, for tables too large to enumerate.

    Reconstructs the ``N`` units as (row, column) labels, holds the row labels fixed, shuffles
    the column labels with ``random.Random(seed)``, and counts how often a resampled table is at
    least as unlikely (hypergeometric probability) as the observed one.
    """
    rows, row_sums, col_sums, total = _validate(table)
    assessable, reason = is_assessable(table)
    if not assessable:
        return {"test": "monte_carlo", "assessable": False, "reason": reason, "p_value": None}
    row_labels = [i for i, s in enumerate(row_sums) for _ in range(s)]
    col_labels = [j for j, s in enumerate(col_sums) for _ in range(s)]
    nrows, ncols = len(row_sums), len(col_sums)
    observed_log_prob = _log_prob(rows, row_sums, col_sums, total)
    rng = random.Random(seed)
    at_least_as_extreme = 0
    for _ in range(resamples):
        rng.shuffle(col_labels)
        counts = [[0] * ncols for _ in range(nrows)]
        for r, c in zip(row_labels, col_labels, strict=True):
            counts[r][c] += 1
        if _log_prob(counts, row_sums, col_sums, total) <= observed_log_prob + _TIE:
            at_least_as_extreme += 1
    return {
        "test": "monte_carlo",
        "assessable": True,
        "exact": False,
        "p_value": min(1.0, at_least_as_extreme / resamples),
        "resamples": resamples,
        "seed": seed,
    }


def _collapse(matrix: list[list[int]], columns: Sequence[str], keep: str, rest_label: str) -> dict:
    """Collapse a per-campaign matrix to a 2-column arm x {keep, rest} table."""
    index = {name: i for i, name in enumerate(columns)}
    if keep not in index:
        raise ValueError(f"column {keep!r} not in {list(columns)}")
    keep_col = index[keep]
    table = [[row[keep_col], sum(row) - row[keep_col]] for row in matrix]
    return {"columns": [keep, rest_label], "table": table}


def _flag(p_value: float | None, *, flag_alpha: float) -> str:
    if p_value is None:
        return "not_assessable"
    return "report_sensitivity" if p_value <= flag_alpha else "independence_assumption_retained"


def _test_2col(table: list[list[int]], *, seed: int) -> dict:
    """Pick the right test for an arm x 2 collapse: exact Fisher, chi-square cross-check."""
    assessable, reason = is_assessable(table)
    if not assessable:
        return {"assessable": False, "reason": reason, "p_value": None, "test": None}
    fisher = fisher_exact(table, seed=seed)
    chi = chi_square_independence(table)
    return {
        "assessable": True,
        "p_value": fisher["p_value"],
        "test": fisher["test"],
        "fisher": fisher,
        "chi_square": chi,
    }


def arm_abort_independence(
    matrix: _Table,
    arms: Sequence[str],
    columns: Sequence[str] = ("complete", "aborted", "invalid"),
    *,
    flag_alpha: float = 0.1,
    seed: int = 0,
) -> dict:
    """Audit 13(a) arm x abort independence REPORTING FLAG from a per-campaign contingency table.

    ``matrix`` is lane 3's ``per_campaign`` matrix (one row per arm, columns ``complete`` /
    ``aborted`` / ``invalid``). The primary test is the arm x {aborted, not-aborted} collapse
    (informative-censoring is about aborts; ``invalid`` campaigns are a separate exclusion and
    get their own secondary test). The top-level ``flag`` is driven by the primary p-value and
    is a REPORTING FLAG, never a verdict (the pre-registration owns the verdict).
    """
    rows = [list(row) for row in matrix]
    if len(rows) != len(arms):
        raise ValueError("matrix must have one row per arm")
    if rows and len(rows[0]) != len(columns):
        raise ValueError("matrix column count must match columns")

    abort_collapse = _collapse(rows, columns, "aborted", "not_aborted")
    invalid_collapse = _collapse(rows, columns, "invalid", "valid")
    primary = _test_2col(abort_collapse["table"], seed=seed)
    secondary = _test_2col(invalid_collapse["table"], seed=seed)
    overall = chi_square_independence(rows)
    flag = _flag(primary["p_value"], flag_alpha=flag_alpha)

    return {
        "classification": "arm-abort-independence-flag",
        "note": (
            "audit 13(a) REPORTING FLAG, not a verdict: whether the main report must carry the "
            "three-policy abort-censoring sensitivity (survival.sensitivity_arms). The verdict "
            "is pre-registered. All values are descriptive over observed campaign counts."
        ),
        "arms": list(arms),
        "columns": list(columns),
        "per_campaign_matrix": rows,
        "flag_alpha": flag_alpha,
        "flag": flag,
        "flag_meaning": {
            "not_assessable": "no abort events (or <2 arms); independence cannot be tested",
            "independence_assumption_retained": f"p > {flag_alpha}; single-policy survival stands",
            "report_sensitivity": f"p <= {flag_alpha}; carry the three-policy sensitivity",
        }[flag],
        "primary_arm_vs_abort": {"collapse": abort_collapse, **primary},
        "secondary_arm_vs_invalid": {"collapse": invalid_collapse, **secondary},
        "overall_disposition_chi_square": overall,
    }


def arm_abort_independence_from_contingency(
    contingency: dict, *, flag_alpha: float = 0.1, seed: int = 0
) -> dict:
    """Run :func:`arm_abort_independence` on lane 3's abort-contingency JSON object.

    Reads ``arms`` and ``per_campaign`` (``columns`` + ``matrix``); never touches
    ``per_event_reason`` (lane 3 marks it descriptive-only, as per-event reasons are correlated
    within a campaign and would violate the test's independence assumption).
    """
    if not isinstance(contingency, dict):
        raise ValueError("contingency must be a JSON object")
    arms = contingency.get("arms")
    per_campaign = contingency.get("per_campaign")
    if not isinstance(arms, list) or not isinstance(per_campaign, dict):
        raise ValueError("contingency needs 'arms' and a 'per_campaign' object")
    columns = per_campaign.get("columns", ["complete", "aborted", "invalid"])
    matrix = per_campaign.get("matrix")
    if not isinstance(matrix, list):
        raise ValueError("per_campaign.matrix must be a list of rows")
    return arm_abort_independence(matrix, arms, columns, flag_alpha=flag_alpha, seed=seed)

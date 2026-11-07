# Repo copy: lint/format exempt (3 comment lines added); otherwise byte-identical, see README.md.
# ruff: noqa
# fmt: off
"""Second value for rule C, beside the mechanical output. Not a replacement and not a gated result.

The gated power model counts a comparison arm aborted before S-u's event as an S-u win
(analyze_hazard_pilot.py:186,211). This run swaps in a model where a block counts only when both arms
were still at risk at the first event, and leaves the analyzer file untouched. Everything else is the
same: constants, inputs, abort fraction, required_n search and rule C.

Usage: from the pilot's detached worktree, with PYTHONPATH=src:. and the report JSON as argument;
with --check it instead reproduces W3's grid points and exits.
"""

import json
import math
import random
import sys

import scripts.analyze_hazard_pilot as gated


def _draw(rng, rate, abort):
    exposure = gated.BUDGET * gated.ABORTED_EXPOSURE if abort > 0 and rng.random() < abort else gated.BUDGET
    time = rng.expovariate(rate) if rate > 0 else math.inf
    return (time if time <= exposure else math.inf), exposure


def _winner(first, second):
    """1 if the first arm's event came first with the second still at risk, -1 the reverse, else 0."""
    (time_a, exposure_a), (time_b, exposure_b) = first, second
    if time_a < time_b and time_a <= exposure_b:
        return 1
    if time_b < time_a and time_b <= exposure_a:
        return -1
    return 0


def scenario_power_pair_riskset(n, p_s, p_r, p_d, *, abort=0.0, sims=gated.SIMS, seed=gated.SIM_SEED):
    rng = random.Random(seed)
    rate_s, rate_r, rate_d = gated._rate(p_s), gated._rate(p_r), gated._rate(p_d)
    joint = 0
    for _ in range(sims):
        s_vs_r = r_vs_s = s_vs_d = d_vs_s = 0
        for _block in range(n):
            s = _draw(rng, rate_s, abort)
            r = _draw(rng, rate_r, abort)
            d = _draw(rng, rate_d, abort)
            against_r = _winner(s, r)
            against_d = _winner(s, d)
            s_vs_r += against_r == 1
            r_vs_s += against_r == -1
            s_vs_d += against_d == 1
            d_vs_s += against_d == -1
        if s_vs_r <= r_vs_s or s_vs_d <= d_vs_s:
            continue
        low, high = sorted(
            (gated.sign_p(s_vs_r, s_vs_r + r_vs_s), gated.sign_p(s_vs_d, s_vs_d + d_vs_s))
        )
        if 2 * low <= gated.FAMILY_ALPHA and high <= gated.FAMILY_ALPHA:
            joint += 1
    return joint / sims


original = gated.scenario_power
if sys.argv[1] == "--check":
    for p_s, abort, expected in ((0.145, 0.0, 61), (0.145, 0.28, 81), (0.117, 0.28, 101), (0.145, 0.45, 102)):
        gated.scenario_power = original
        mechanical = gated.required_n(p_s, 0.0, 0.0, abort=abort)
        gated.scenario_power = scenario_power_pair_riskset
        paired = gated.required_n(p_s, 0.0, 0.0, abort=abort)
        print(f"p_s {p_s} a {abort}: gated model {mechanical}, pair risk set {paired}, W3 DP {expected}")
    raise SystemExit(0)

report = json.load(open(sys.argv[1]))
inputs = report["planning_inputs"]
condition = report["condition_6"]
gated.scenario_power = scenario_power_pair_riskset
second = gated.feasibility(
    inputs,
    abort=condition["abort_fraction_used"],
    campaigns_per_host_day=condition["campaigns_per_host_day"],
)
print(
    json.dumps(
        {
            "mechanical": {
                key: condition[key]
                for key in ("verdict", "verdict_label", "required_n_point", "required_n_s_upper95")
            },
            "zero_information_truncated_blocks": {
                key: second[key]
                for key in ("verdict", "verdict_label", "required_n_point", "required_n_s_upper95")
            },
            "abort_fraction_used": condition["abort_fraction_used"],
            "campaigns_per_host_day": condition["campaigns_per_host_day"],
            "n_capacity_by_host_days": condition["n_capacity_by_host_days"],
        },
        indent=1,
        ensure_ascii=False,
    )
)

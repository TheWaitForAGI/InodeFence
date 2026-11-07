# Repo copy: lint/format exempt (3 comment lines added); see README.md.
# ruff: noqa
# fmt: off
"""Does exp3_power_registered.py compute the registered statistic? Same data through both.

Compares the script's squared Z with survival.seed_block_logrank_permutation's observed chi-square,
and the two permutation p values, on simulated blocks with the script's own draws. Planning check.
"""
import importlib.util
import sys
import numpy as np
from inodefence.evaluation.survival import Observation, seed_block_logrank_permutation

spec = importlib.util.spec_from_file_location("power", sys.argv[1])
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)
rng = np.random.default_rng(1)
chi_diffs, p_diffs, tie_diffs, rejects_a, rejects_b = [], [], [], 0, 0
for _ in range(300):
    n = 76
    t_a, e_a = power.observe(rng, power.P_S, (n,), power.ABORT, "empirical")
    t_b, e_b = power.observe(rng, power.P_R, (n,), power.ABORT, "empirical")
    p, z = power.permutation_p(rng, t_a, e_a, t_b, e_b, 2000)
    scaled = lambda value: max(1, int(float(value) * 1_000_000))  # keeps the order, no ties
    blocks = [
        (Observation(scaled(ta), bool(ea)), Observation(scaled(tb), bool(eb)))
        for ta, ea, tb, eb in zip(t_a, e_a, t_b, e_b, strict=True)
    ]
    rounded = [
        (Observation(max(1, int(np.ceil(ta))), bool(ea)), Observation(max(1, int(np.ceil(tb))), bool(eb)))
        for ta, ea, tb, eb in zip(t_a, e_a, t_b, e_b, strict=True)
    ]
    tied = seed_block_logrank_permutation(rounded, seed=7, resamples=200)
    tie_diffs.append(abs(z * z - tied["observed_chi_square"]))
    out = seed_block_logrank_permutation(blocks, seed=7, resamples=2000)
    chi_diffs.append(abs(z * z - out["observed_chi_square"]))
    p_diffs.append(abs(p - out["p_value"]))
    rejects_a += p <= 0.05
    rejects_b += out["p_value"] <= 0.05
chi = np.array(chi_diffs)
pd = np.array(p_diffs)
print(f"datasets 300, n=76; max |z^2 - chi2| {chi.max():.2e}; median |p diff| {np.median(pd):.4f}, max {pd.max():.4f}")
print(f"integer times (real T_first form): median |z^2 - chi2| {np.median(tie_diffs):.2e}, max {max(tie_diffs):.2e}")
print(f"p<=.05: script {rejects_a}, registered {rejects_b}")

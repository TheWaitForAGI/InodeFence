# Repo copy: lint/format exempt (3 comment lines added); otherwise byte-identical, see README.md.
# ruff: noqa
# fmt: off
"""Power of the EXP-3 confirmatory test with the pilot's planning inputs. A plan, not a result.

Registered test: pooled two-arm log-rank chi-square, arm labels permuted within seed blocks
(src/inodefence/evaluation/survival.py, seed_block_logrank_permutation), two contrasts, Holm family
alpha .05, S-u faster on both. Inputs come from the pilot report (exp3-hazard-pilot-v1).

Assumes constant hazard and independent arms within a block. Abort steps are resampled from the
pilot's eleven. Needs numpy only.

    python exp3_power_registered.py permutation --sims 1500 --perms 1000
    python exp3_power_registered.py grid
"""
import argparse
import math

import numpy as np

BUDGET = 2000
PILOT_ABORT_STEPS = np.array([135, 790, 997, 1023, 1134, 1221, 1548, 1702, 1744, 1790, 1951], float)
P_S, P_R, P_D, ABORT = 0.670, 0.413, 0.401, 0.275


def censor(rng, shape, a, model):
    if a == 0 or model == "none":
        return np.full(shape, float(BUDGET))
    if model == "exp":
        return np.minimum(rng.exponential(BUDGET / -math.log(1 - a), shape), BUDGET)
    aborted = rng.random(shape) < a
    return np.where(aborted, rng.choice(PILOT_ABORT_STEPS, shape), BUDGET)


def observe(rng, p, shape, a, model):
    event_time = rng.exponential(BUDGET / -math.log(1 - p), shape)
    stop = censor(rng, shape, a, model)
    return np.minimum(event_time, stop), event_time <= stop


def logrank_z(t_a, e_a, t_b, e_b):
    """Signed Z per row, positive when arm a is faster. Continuous draws, so no ties."""
    times = np.concatenate([t_a, t_b], axis=1)
    events = np.concatenate([e_a, e_b], axis=1)
    is_a = np.concatenate([np.ones_like(e_a), np.zeros_like(e_b)], axis=1).astype(bool)
    order = np.argsort(times, axis=1)
    events = np.take_along_axis(events, order, 1)
    is_a = np.take_along_axis(is_a, order, 1)
    at_risk = np.arange(times.shape[1], 0, -1)[None, :]
    frac = np.cumsum(is_a[:, ::-1], axis=1)[:, ::-1] / at_risk
    u = ((is_a.astype(float) - frac) * events).sum(axis=1)
    v = (frac * (1 - frac) * events).sum(axis=1)
    return np.where(v > 0, u / np.sqrt(np.where(v > 0, v, 1)), 0.0)


def holm_both(z1, p1, z2, p2):
    return z1 > 0 and z2 > 0 and min(p1, p2) <= 0.025 and max(p1, p2) <= 0.05


def permutation_p(rng, t_a, e_a, t_b, e_b, perms):
    z0 = logrank_z(t_a[None], e_a[None], t_b[None], e_b[None])[0]
    swap = rng.random((perms, t_a.shape[0])) < 0.5
    z = logrank_z(
        np.where(swap, t_b, t_a), np.where(swap, e_b, e_a), np.where(swap, t_a, t_b), np.where(swap, e_a, e_b)
    )
    return (np.sum(np.abs(z) >= abs(z0) - 1e-9) + 1) / (perms + 1), z0


def permutation_power(rng, n, p_s, p_r, p_d, a, sims, perms, model="empirical"):
    hits = 0
    for _ in range(sims):
        t_s, e_s = observe(rng, p_s, (n,), a, model)
        t_r, e_r = observe(rng, p_r, (n,), a, model)
        t_d, e_d = observe(rng, p_d, (n,), a, model)
        p1, z1 = permutation_p(rng, t_s, e_s, t_r, e_r, perms)
        p2, z2 = permutation_p(rng, t_s, e_s, t_d, e_d, perms)
        hits += holm_both(z1, p1, z2, p2)
    return hits / sims


def chi2_power(rng, n, p_s, p_r, p_d, a, sims=8000, model="empirical"):
    t_s, e_s = observe(rng, p_s, (sims, n), a, model)
    t_r, e_r = observe(rng, p_r, (sims, n), a, model)
    t_d, e_d = observe(rng, p_d, (sims, n), a, model)
    zr, zd = logrank_z(t_s, e_s, t_r, e_r), logrank_z(t_s, e_s, t_d, e_d)
    pr = np.array([math.erfc(abs(x) / math.sqrt(2)) for x in zr])
    pd = np.array([math.erfc(abs(x) / math.sqrt(2)) for x in zd])
    return (
        (zr > 0) & (zd > 0) & (np.minimum(pr, pd) <= 0.025) & (np.maximum(pr, pd) <= 0.05)
    ).mean()


def scaled(p, s):
    return 1 - (1 - p) ** s


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("permutation", "grid"))
    parser.add_argument("--sims", type=int, default=1500)
    parser.add_argument("--perms", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261107)
    parser.add_argument("--n", type=int, nargs="*", default=[70, 74, 78, 82, 86, 120])
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)
    if args.mode == "permutation":
        for n in args.n:
            power = permutation_power(rng, n, P_S, P_R, P_D, ABORT, args.sims, args.perms)
            se = math.sqrt(power * (1 - power) / args.sims)
            print(f"n={n} permutation joint power {power:.3f} se {se:.3f}", flush=True)
        return
    scenarios = (
        ("point HR 2.08", P_S, P_R, P_D),
        ("HR 2", scaled(P_R, 2), P_R, P_D),
        ("HR 1.75", scaled(P_R, 1.75), P_R, P_D),
        ("HR 1.5", scaled(P_R, 1.5), P_R, P_D),
        ("HR 2.08 s=.5", scaled(P_S, 0.5), scaled(P_R, 0.5), scaled(P_D, 0.5)),
        ("HR 2 s=.5", scaled(scaled(P_R, 0.5), 2), scaled(P_R, 0.5), scaled(P_D, 0.5)),
        ("HR 2.08 s=.25", scaled(P_S, 0.25), scaled(P_R, 0.25), scaled(P_D, 0.25)),
    )
    for name, a, b, c in scenarios:
        row = [round(float(chi2_power(rng, n, a, b, c, ABORT)), 3) for n in (94, 120, 150)]
        hi = [round(float(chi2_power(rng, n, a, b, c, 0.43, model="exp")), 3) for n in (94, 120, 150)]
        print(name, row, "a=.43", hi)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# Repo copy: lint/format exempt (3 comment lines added); otherwise byte-identical, see README.md.
# ruff: noqa
# fmt: off
"""EXP-3 sizing grid -- PRE-REGISTRATION PLANNING INPUT, NOT A RESULT.

Produces sizing.json next to this file. Reproduce with:

    W=<scratchpad>/exp0-analysis-f655f18
    PYTHONPATH="$W/src:$W" nice -n 10 /home/linux/Projects/InodeFence/.venv/bin/python -I compute.py

(-I is fine: the repo modules are found via an explicit sys.path insert of $W/src below.)

Inputs (observed, read from disk where available):
  * EXP-0 registered run report  ~/inodefence-evidence/exp0-20261105-analysis-premerge/exp0-report-premerge.json
  * EXP-0 per-cell summaries + cell .log mtimes  ~/inodefence-evidence/exp0-20261105/
  * M3 powered matched verdict v2  <repo>/experiments/summaries/m3-powered-matched-verdict-v2.json
  * k-vs-reach design input  ~/inodefence-evidence/sentinel-k-reach-20261104/kscale_raw.txt
Code under test (unmerged stack-E head f655f18): inodefence.evaluation.power (Schoenfeld + exposure
model) and inodefence.evaluation.survival.seed_block_logrank_permutation (registered
exact-logrank-permutation-v1). Everything here is a planning approximation; no EXP-0 hit is used to
estimate a hazard (prereg v2 (a)).
"""

import glob
import json
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.dirname(HERE)
WT = os.path.join(SCRATCH, "exp0-analysis-f655f18")
sys.path.insert(0, os.path.join(WT, "src"))

from inodefence.evaluation import power as P  # noqa: E402
from inodefence.evaluation import survival as S  # noqa: E402

HOME = os.path.expanduser("~")
REPO = "/home/linux/Projects/InodeFence"
EXP0_REPORT = os.path.join(HOME, "inodefence-evidence/exp0-20261105-analysis-premerge/exp0-report-premerge.json")
EXP0_RAW = os.path.join(HOME, "inodefence-evidence/exp0-20261105")
M3_JSON = os.path.join(REPO, "experiments/summaries/m3-powered-matched-verdict-v2.json")
KREACH = os.path.join(HOME, "inodefence-evidence/sentinel-k-reach-20261104/kscale_raw.txt")

LABEL = "pre-registration planning input, not a result"
BUDGET = 2000
JOBS = 2
POWER = 0.8
ALPHA_FAMILY = 0.05
ALPHA = 0.025  # Holm over 2 primary contrasts: worst-case first step = 0.05/2 (two-sided)
N_GRID = [10, 15, 20, 25, 30, 40, 50]
N_GRID_EXT = [18, 37, 47, 60, 75, 94, 100, 150]  # window-derived n (2-day: 18, 37; 5-day: 47, 94) + larger n
PR_GRID = [0.02, 0.05, 0.10, 0.20]
ABORT_GRID = [0.0, 0.2]  # 0.2 = rule-of-three 3/15 on EXP-0 abort 0/15
ABORT_STRESS = 0.4  # M3 powered matched budget-2000 history: 24/60 aborted (older engine)
ABORTED_EXPOSURE = 0.5  # power.py default: an aborting campaign is exposed for half the budget
WINDOWS = [2, 3, 4, 5]
HOSTS = [1, 2]
TARGET_SETS = {
    # cells per n (n = campaigns per arm per target). Rust tar = fixed fixture only, 0 campaign cells.
    "train_only": {"targets": ["node-tar-7.5.2"], "arms": 3},
    "train+holdout": {"targets": ["node-tar-7.5.2", "node-tar-holdout"], "arms": 3},
    "train+holdout+fixver": {
        "targets": ["node-tar-7.5.2", "node-tar-holdout", "node-tar-7.5.6", "node-tar-7.5.7"],
        "arms": 3,
    },
    "train+holdout+fixver+pytarfile": {
        "targets": ["node-tar-7.5.2", "node-tar-holdout", "node-tar-7.5.6", "node-tar-7.5.7", "py-tarfile-3.12"],
        "arms": 3,
    },
    "train+holdout (+S-a)": {"targets": ["node-tar-7.5.2", "node-tar-holdout"], "arms": 4},
}


# ----------------------------------------------------------------------------- throughput
def throughput_inputs():
    rep = json.load(open(EXP0_REPORT))
    summed = rep["item3_throughput"]["summed"]
    aborts = rep["item1_aborts"]["by_arm"]
    n_abort = sum(a["number_abort"] for a in aborts.values())
    n_cells = sum(a["number_cells"] for a in aborts.values())
    p95 = rep["item2_p95_full_step"]
    pooled_p95 = None
    for key in ("pooled", "summed"):
        if isinstance(p95.get(key), dict):
            pooled_p95 = p95[key].get("p95_seconds")
    out = {
        "report_summed_exec_per_hour": summed["exec_per_hour"],
        "report_summed_executions": summed["executions"],
        "report_summed_wall_clock_seconds": summed["wall_clock_seconds"],
        "report_summed_note": (
            "OBSERVED: the report's 'summed' wall_clock_seconds is the SUM of per-cell walls "
            "(4447.9 s = sum of 15 cell walls), not the run's elapsed time; with jobs=2 the cells ran "
            "in pairs, so 2428 exec/h is a PER-STREAM rate, not the host aggregate."
        ),
        "aborts": f"{n_abort}/{n_cells}",
        "pooled_p95_full_step_seconds": pooled_p95,
        "source": EXP0_REPORT,
    }
    # elapsed reconstruction from per-cell walls + .log mtimes (observed file metadata; start inferred)
    rows = []
    for f in sorted(glob.glob(os.path.join(EXP0_RAW, "summaries", "*.summary.json"))):
        rid = os.path.basename(f).replace(".summary.json", "")
        timing = json.load(open(f))["timing"]
        log = os.path.join(EXP0_RAW, rid + ".log")
        if not os.path.exists(log):
            continue
        end = os.stat(log).st_mtime
        rows.append({"run_id": rid, "wall": timing["wall_seconds"], "exec_per_hour": timing["exec_per_hour"],
                     "start": end - timing["wall_seconds"], "end": end})
    if len(rows) == 15:
        t0 = min(r["start"] for r in rows)
        t1 = max(r["end"] for r in rows)
        elapsed = t1 - t0
        rows.sort(key=lambda r: r["start"])
        solo = rows[-1]  # 15 cells at jobs 2 -> the last cell ran alone
        paired = rows[:-1]
        steady_end = max(r["end"] for r in paired)
        out.update({
            "elapsed_seconds_inferred": elapsed,
            "aggregate_exec_per_hour_elapsed": 3000 / elapsed * 3600,
            "aggregate_exec_per_hour_steady_14_paired_cells": 2800 / (steady_end - t0) * 3600,
            "per_stream_exec_per_hour_paired_mean": sum(r["exec_per_hour"] for r in paired) / len(paired),
            "per_stream_exec_per_hour_solo": solo["exec_per_hour"],
            "solo_cell": solo["run_id"],
            "slot_utilisation": sum(r["wall"] for r in rows) / (JOBS * elapsed),
            "elapsed_method": (
                "start_i = log_mtime_i - wall_seconds_i; elapsed = max(log_mtime) - min(start). "
                "OBSERVED file metadata, INFERRED start times (mtime lags runner wall by ~10 s teardown)."
            ),
        })
    else:
        out["elapsed_seconds_inferred"] = None
    return out


def throughput_grid(tin):
    agg = tin.get("aggregate_exec_per_hour_elapsed") or 4740.1
    scen = {
        "quiet_measured_elapsed": {
            "exec_per_hour": agg,
            "source": "EXP-0 2026-11-05 run elapsed (log mtimes), jobs 2, per-case-container, quiet host",
        },
        "conservative_per_stream": {
            "exec_per_hour": tin["report_summed_exec_per_hour"],
            "source": "EXP-0 report item3 'summed' (= sum exec / sum per-cell wall) = one stream; "
                      "equivalent to jobs-2 giving no parallel gain",
        },
        "busy_host_stress": {
            "exec_per_hour": 0.40 * 3600,
            "source": "exp3-v1 draft (d): shared/busy host 0.40-0.51 c/s at jobs 2 (lane-4 Phase B); lower end",
        },
    }
    for s in scen.values():
        s["campaign_seconds_per_slot_budget2000"] = JOBS * BUDGET * 3600 / s["exec_per_hour"]
        s["campaigns_per_host_day"] = s["exec_per_hour"] * 24 / BUDGET
    windows = []
    for name, s in scen.items():
        per_slot_day = 86400 / s["campaign_seconds_per_slot_budget2000"]
        for h in HOSTS:
            for w in WINDOWS:
                total = h * JOBS * math.floor(w * per_slot_day)
                row = {"scenario": name, "hosts": h, "host_days": w, "total_campaigns": total, "target_sets": {}}
                for ts, spec in TARGET_SETS.items():
                    cells_per_n = spec["arms"] * len(spec["targets"])
                    n = total // cells_per_n
                    row["target_sets"][ts] = {
                        "cells_per_n": cells_per_n,
                        "per_target_cells": {t: spec["arms"] * n for t in spec["targets"]},
                        "n_max_per_arm_per_target": n,
                        "expected_complete_per_arm": {
                            f"abort_{a}": round(n * (1 - a), 1) for a in (0.0, 0.2, ABORT_STRESS)
                        },
                    }
                windows.append(row)
    return scen, windows


# ----------------------------------------------------------------------------- power models
def lam_from_p(p):
    """Per-execution constant hazard giving full-budget first-event probability p (power.py model)."""
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    return -math.log(1 - p) / BUDGET


def p_from_lam(lam, m=BUDGET):
    return 1 - math.exp(-lam * m)


def eff_p(lam, a):
    """Abort-weighted events/campaign = power.events_per_campaign (the repo exposure model)."""
    if lam <= 0:
        return 0.0
    return P.events_per_campaign(per_execution_hazard=lam, budget=BUDGET, abort_fraction=a,
                                 aborted_exposure_fraction=ABORTED_EXPOSURE)


def schoenfeld_power(n, lam_r, hr, a):
    return P.power_from_design(campaigns_per_arm=n, per_execution_hazard=lam_r, budget=BUDGET,
                               hazard_ratio=hr, abort_fraction=a,
                               aborted_exposure_fraction=ABORTED_EXPOSURE, alpha=ALPHA)


# block-winner sign-test approximation of the seed-block exact permutation log-rank.
# Exposure model identical to power.py: complete campaign exposure B, aborted B*0.5; hazard on the
# continuous scale (P(event by m) = 1-exp(-lam*m)), discretised per execution so ties are explicit.
def _win(la, ma, lb, mb):
    """P(arm A has an event at t<=ma AND arm B has no event in [1, min(t, mb)])."""
    if la <= 0:
        return 0.0
    qa, qb = math.exp(-la), math.exp(-lb)
    ha = -math.expm1(-la)  # per-execution event prob for A
    m = min(ma, mb)
    one_minus_r = -math.expm1(-(la + lb))
    part1 = ha * qb * (-math.expm1(-(la + lb) * m)) / one_minus_r
    part2 = qb ** mb * (qa ** m - qa ** ma) if ma > mb else 0.0
    return part1 + part2


def block_probs(lam_s, lam_r, a):
    ex = [(BUDGET, 1 - a), (int(BUDGET * ABORTED_EXPOSURE), a)]
    ws = wr = 0.0
    for ms, w1 in ex:
        for mr, w2 in ex:
            w = w1 * w2
            if w == 0:
                continue
            ws += w * _win(lam_s, ms, lam_r, mr)
            wr += w * _win(lam_r, mr, lam_s, ms)
    return ws, wr


def _lbinom(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def _binom_pmf(n, k, p):
    if p <= 0:
        return 1.0 if k == 0 else 0.0
    if p >= 1:
        return 1.0 if k == n else 0.0
    return math.exp(_lbinom(n, k) + k * math.log(p) + (n - k) * math.log1p(-p))


_CRIT = {}


def _crit(k, alpha):
    """Smallest x > k/2 whose exact two-sided sign-test p <= alpha (None if unattainable)."""
    key = (k, alpha)
    if key in _CRIT:
        return _CRIT[key]
    tail = 0.0
    res = None
    for x in range(k, -1, -1):
        tail += math.exp(_lbinom(k, x) - k * math.log(2))
        if 2 * x <= k:
            break
        if min(1.0, 2 * tail) <= alpha:
            res = x
        else:
            break
    _CRIT[key] = res
    return res


def sign_power(n, lam_s, lam_r, a, alpha=ALPHA):
    """P(reject AND faster_arm == S-u) under the block-winner sign-test approximation."""
    ws, wr = block_probs(lam_s, lam_r, a)
    pinf = ws + wr
    if pinf <= 0:
        return 0.0
    s = ws / pinf
    mu = n * pinf
    sd = math.sqrt(max(n * pinf * (1 - pinf), 0.0))
    klo = max(1, int(mu - 10 * sd) - 5)
    khi = min(n, int(mu + 10 * sd) + 5)
    tot = 0.0
    for k in range(klo, khi + 1):
        c = _crit(k, alpha)
        if c is None:
            continue
        pk = _binom_pmf(n, k, pinf)
        if pk < 1e-15:
            continue
        tot += pk * sum(_binom_pmf(k, x, s) for x in range(c, k + 1))
    return tot


def min_informative_blocks(alpha):
    k = 1
    while 2.0 ** (1 - k) > alpha:
        k += 1
    return k


def bisect(f, lo, hi, iters=80):
    """Smallest x in [lo, hi] (monotone increasing f) with f(x) >= POWER; None if f(hi) < POWER."""
    if f(hi) < POWER:
        return None
    if f(lo) >= POWER:
        return lo
    for _ in range(iters):
        mid = math.sqrt(lo * hi) if lo > 0 else (lo + hi) / 2
        if f(mid) >= POWER:
            hi = mid
        else:
            lo = mid
    return hi


def mde_rows():
    rows = []
    for a in ABORT_GRID:
        for pr in [0.0] + PR_GRID:
            lam_r = lam_from_p(pr)
            for n in N_GRID:
                row = {"abort_fraction": a, "p_R_complete": pr, "n_per_arm": n}
                # Schoenfeld (repo power.py), HR = lam_S/lam_R
                if pr > 0:
                    hr = bisect(lambda h: schoenfeld_power(n, lam_r, h, a)["power"], 1.0 + 1e-9, 0.05 / lam_r)
                    if hr is not None:
                        d = schoenfeld_power(n, lam_r, hr, a)
                        row["schoenfeld"] = {
                            "mde_hr": hr, "p_S_complete": p_from_lam(lam_r * hr),
                            "expected_events_total": d["total_expected_events"],
                            "asymptotic_valid_flag": "ok(>=10 events)" if d["total_expected_events"] >= 10
                            else ("invalid(<5 events)" if d["total_expected_events"] < 5 else "weak(5-10 events)"),
                        }
                    else:
                        row["schoenfeld"] = {"mde_hr": None}
                else:
                    row["schoenfeld"] = {"mde_hr": None, "note": "p_R=0: HR undefined (R floor)"}
                # sign-test approximation of the registered exact permutation test
                if pr > 0:
                    hr2 = bisect(lambda h: sign_power(n, lam_r * h, lam_r, a), 1.0 + 1e-9, 0.05 / lam_r)
                    if hr2 is not None:
                        ws, wr = block_probs(lam_r * hr2, lam_r, a)
                        row["permutation_signtest"] = {
                            "mde_hr": hr2, "p_S_complete": p_from_lam(lam_r * hr2),
                            "expected_informative_blocks": n * (ws + wr),
                        }
                    else:
                        row["permutation_signtest"] = {"mde_hr": None}
                else:
                    lam = bisect(lambda l: sign_power(n, l, 0.0, a), 1e-9, 0.05)
                    row["permutation_signtest"] = {
                        "mde_hr": None, "mde_p_S_complete": None if lam is None else p_from_lam(lam),
                        "mde_lambda_S": lam,
                    }
                rows.append(row)
    return rows


def n_needed_sign(lam_s, lam_r, a, nmax=8192):
    """Smallest n with power >= 0.8 (exact-test power is saw-toothed in n; first crossing reported)."""
    hi = 8
    while hi <= nmax and sign_power(hi, lam_s, lam_r, a) < POWER:
        hi *= 2
    if hi > nmax:
        return None
    for n in range(max(1, hi // 2), hi + 1):
        if sign_power(n, lam_s, lam_r, a) >= POWER:
            return n
    return hi


def pooled_x(p_list_eff, lam_list):
    """Pooled first-event rate over arms: events/campaign and events/time-at-risk (exp MLE)."""
    events = sum(p_list_eff)
    risk = 0.0
    for pe, lam in zip(p_list_eff, lam_list):
        risk += (pe / lam) if lam > 0 else BUDGET  # E[min(T,m)] = p/lam ; no-hazard arm ~ full exposure
    return events / len(p_list_eff), events / risk


def converse_rows():
    """x needed for 80% power at each n. Effect models: (A) registered prediction HR=2 with D=R;
    (B) R=D floor 0, S-u at p_S. x pooled over R/D/S-u (3 arms), first-event units."""
    rows = []
    for a in ABORT_GRID:
        for n in N_GRID + N_GRID_EXT:
            row = {"abort_fraction": a, "n_per_arm": n}
            # (A) HR = 2 Schoenfeld
            f = lambda l: schoenfeld_power(n, l, 2.0, a)["power"]  # noqa: E731
            lam = bisect(f, 1e-9, 0.01)
            if lam is None:
                row["hr2_schoenfeld"] = {"attainable": False,
                                         "note": "event ceiling 2n < required events at any hazard"}
            else:
                pe = [eff_p(lam, a), eff_p(lam, a), eff_p(2 * lam, a)]
                xc, xe = pooled_x(pe, [lam, lam, 2 * lam])
                row["hr2_schoenfeld"] = {"attainable": True, "lambda_R": lam, "p_R_complete": p_from_lam(lam),
                                         "x_events_per_campaign": xc, "x_events_per_execution_at_risk": xe}
            # (A') HR = 2 sign-test
            lam2 = bisect(lambda l: sign_power(n, 2 * l, l, a), 1e-9, 0.01)
            if lam2 is None:
                row["hr2_signtest"] = {"attainable": False, "note": "sign-test power < 0.8 at saturation"}
            else:
                pe = [eff_p(lam2, a), eff_p(lam2, a), eff_p(2 * lam2, a)]
                xc, xe = pooled_x(pe, [lam2, lam2, 2 * lam2])
                row["hr2_signtest"] = {"attainable": True, "lambda_R": lam2, "p_R_complete": p_from_lam(lam2),
                                       "x_events_per_campaign": xc, "x_events_per_execution_at_risk": xe}
            # (B) R = D = 0 floor, S-u at p_S: sign-test (= exact permutation in this regime)
            lam3 = bisect(lambda l: sign_power(n, l, 0.0, a), 1e-9, 0.05)
            if lam3 is None:
                row["floor_signtest"] = {"attainable": False}
            else:
                pe = [0.0, 0.0, eff_p(lam3, a)]
                xc, xe = pooled_x(pe, [0.0, 0.0, lam3])
                row["floor_signtest"] = {"attainable": True, "p_S_complete": p_from_lam(lam3),
                                         "p_S_effective": eff_p(lam3, a), "lambda_S": lam3,
                                         "x_events_per_campaign": xc, "x_events_per_execution_at_risk": xe,
                                         "expected_S_events": n * eff_p(lam3, a)}
            rows.append(row)
    return rows


# ----------------------------------------------------------------------------- MC validation
def _sample(lam, m, rng):
    if lam <= 0:
        return S.Observation(m, False)
    t = math.ceil(math.log(1 - rng.random()) / -lam) if lam < 50 else 1
    t = max(t, 1)
    return S.Observation(t, True) if t <= m else S.Observation(m, False)


def _exposure(a, rng):
    return int(BUDGET * ABORTED_EXPOSURE) if rng.random() < a else BUDGET


def exact_perm_p(blocks, seed):
    """Registered test p-value. Exact over informative blocks (identical-pair blocks are no-op swaps,
    so the fraction equals the repo's 2^n enumeration) when k<=12, else the repo function's own
    seed-fixed Monte-Carlo path (resamples=2000)."""
    inf = [i for i, (x, y) in enumerate(blocks) if x != y]
    ga = [x for x, _ in blocks]
    gb = [y for _, y in blocks]
    obs, oe = S._two_arm_logrank_observed(ga, gb)
    if len(inf) <= 12:
        ge = 0
        k = len(inf)
        for mask in range(1 << k):
            a = list(ga)
            b = list(gb)
            for j, i in enumerate(inf):
                if (mask >> j) & 1:
                    a[i], b[i] = gb[i], ga[i]
            if S._two_arm_logrank_chi2(a, b) >= obs - 1e-9:
                ge += 1
        return ge / (1 << k), oe, True
    r = S.seed_block_logrank_permutation(blocks, seed=seed, resamples=2000)
    return r["p_value"], r["observed_minus_expected_a"], False


def mc_power(n, lam_s, lam_r, a, sims, seed):
    rng = random.Random(seed)
    rej = 0
    for i in range(sims):
        blocks = [(_sample(lam_s, _exposure(a, rng), rng), _sample(lam_r, _exposure(a, rng), rng))
                  for _ in range(n)]
        p, oe, _ = exact_perm_p(blocks, seed * 100003 + i)
        if p is not None and p <= ALPHA and oe > 0:
            rej += 1
    est = rej / sims
    return est, 1.96 * math.sqrt(est * (1 - est) / sims)


def equivalence_check(seed=7, cases=25):
    """My informative-block enumeration == repo exact path (n<=12)."""
    rng = random.Random(seed)
    maxdiff = 0.0
    for _ in range(cases):
        n = rng.randint(6, 12)
        ls, lr = lam_from_p(rng.uniform(0.05, 0.6)), lam_from_p(rng.uniform(0.0, 0.3))
        blocks = [(_sample(ls, _exposure(0.2, rng), rng), _sample(lr, _exposure(0.2, rng), rng)) for _ in range(n)]
        mine, _, _ = exact_perm_p(blocks, 0)
        repo = S.seed_block_logrank_permutation(blocks)["p_value"]
        maxdiff = max(maxdiff, abs(mine - repo))
    return {"cases": cases, "max_abs_p_difference_vs_repo_exact": maxdiff}


VALIDATION_POINTS = [
    # (label, n, p_S_complete, p_R_complete, abort)
    ("floor n20 pS0.45", 20, 0.45, 0.0, 0.0),
    ("floor n30 pS0.30", 30, 0.30, 0.0, 0.0),
    ("floor n30 pS0.0588 (M3 A3full 1/17)", 30, 1 / 17, 0.0, 0.0),
    ("pR0.05 n30 pS0.35", 30, 0.35, 0.05, 0.0),
    ("pR0.20 n30 HR2", 30, None, 0.20, 0.0),
    ("pR0.50 n40 HR2", 40, None, 0.50, 0.0),
    ("pR0.10 n50 pS0.40 abort0.2", 50, 0.40, 0.10, 0.2),
    ("floor n76 pS0.117 (k=3 inferred x2.06 of 1/17)", 76, 1 - (1 - 1 / 17) ** 2.06, 0.0, 0.0),
]


def validation(sims):
    out = []
    for k, (label, n, ps, pr, a) in enumerate(VALIDATION_POINTS):
        lam_r = lam_from_p(pr)
        lam_s = 2 * lam_r if ps is None else lam_from_p(ps)
        t0 = time.time()
        est, half = mc_power(n, lam_s, lam_r, a, sims, seed=20261105 + k)
        row = {"label": label, "n": n, "p_S_complete": p_from_lam(lam_s), "p_R_complete": pr, "abort": a,
               "mc_power_registered_test": est, "mc_ci95_halfwidth": half, "sims": sims,
               "signtest_analytic_power": sign_power(n, lam_s, lam_r, a),
               "seconds": round(time.time() - t0, 1)}
        if lam_r > 0:
            row["schoenfeld_power"] = schoenfeld_power(n, lam_r, lam_s / lam_r, a)["power"]
        out.append(row)
        print("validation", row, flush=True)
    return out


# ----------------------------------------------------------------------------- sensitivity
def kreach():
    rel = {}
    try:
        for line in open(KREACH):
            parts = line.split()
            if parts and parts[0].isdigit():
                rel[int(parts[0])] = float(parts[2].rstrip("x"))
    except OSError:
        rel = {1: 1.0, 3: 2.06, 5: 2.59}
    return rel


def sensitivity():
    rel = kreach()
    m3 = json.load(open(M3_JSON))["pooled_matched_contrast_100_129"]
    a3 = m3["arm_b_shared"]
    base_complete = a3["complete_campaign_hits"] / a3["complete_campaigns"]  # 1/17
    base_obs = a3["number_observed_trigger_seeds"] / a3["shared_seeds"]  # 2/30 (incl. pre-abort)
    rows = []
    for label, p0 in (("M3 A3full complete 1/17", base_complete), ("M3 A3full observed-trigger 2/30", base_obs)):
        lam0 = lam_from_p(p0)
        for k in (1, 3, 5):
            mult = rel.get(k, 1.0)
            lam = lam0 * mult
            for a in (0.0, 0.2, ABORT_STRESS):
                rows.append({
                    "basis": label, "sentinel_k": k, "hazard_multiplier_vs_k1": mult,
                    "multiplier_status": "observed k=1 (M3)" if k == 1 else
                    "INFERRED: in-process C2 reach ratio assumed to transfer to realized C1|C2 hazard",
                    "abort": a, "p_S_complete": p_from_lam(lam), "p_S_effective": eff_p(lam, a),
                    "p_R": 0.0,
                    "power_at_n": {n: sign_power(n, lam, 0.0, a) for n in N_GRID},
                    "n_for_80pct_floor": n_needed_sign(lam, 0.0, a),
                    "n_for_80pct_if_pR_0.02_signtest": n_needed_sign(lam, lam_from_p(0.02), a)
                    if lam > lam_from_p(0.02) else None,
                    "n_for_80pct_if_pR_0.02_schoenfeld": P.required_campaigns_per_arm(
                        per_execution_hazard=lam_from_p(0.02), budget=BUDGET, hazard_ratio=lam / lam_from_p(0.02),
                        power=POWER, alpha=ALPHA, abort_fraction=a,
                        aborted_exposure_fraction=ABORTED_EXPOSURE)["control_campaigns"]
                    if lam > lam_from_p(0.02) else None,
                })
    m3_note = {
        "A1_complete": f"{m3['arm_a_shared']['complete_campaign_hits']}/{m3['arm_a_shared']['complete_campaigns']}",
        "A3full_complete": f"{a3['complete_campaign_hits']}/{a3['complete_campaigns']}",
        "A3full_observed_trigger_seeds": f"{a3['number_observed_trigger_seeds']}/{a3['shared_seeds']}",
        "A3full_total_clean_c1_steps": a3["total_observed_clean_exact_c1"],
        "A3full_observed_executions": m3.get("A3full_observed_executions"),
        "A1_observed_executions": m3.get("A1_observed_executions"),
        "aborts_A1_A3full": f"{30 - m3['arm_a_shared']['complete_campaigns']}/30, "
                            f"{30 - a3['complete_campaigns']}/30",
        "source": M3_JSON,
    }
    return rows, m3_note, rel


def go_rule_oc(conv):
    """P(EXP-3 pooled first-event rate x_hat >= x) for an EXP-3 of n_exp3 campaigns/arm on ONE target,
    floor model (R = D = 0 events, S-u events ~ Binomial(n_exp3, p_S_eff)); x from the converse rows."""
    rel = kreach()
    p0 = 1 / 17
    truths = {f"S-u k={k} ({'M3 observed' if k == 1 else 'inferred x' + str(rel.get(k))})":
              lam_from_p(p0) * rel.get(k, 1.0) for k in (1, 3, 5)}
    xs = {}
    for r in conv:
        if r["abort_fraction"] == 0.0 and r["n_per_arm"] in (47, 94) and r["floor_signtest"].get("attainable"):
            xs[f"x_for_EXP2_n{r['n_per_arm']}"] = r["floor_signtest"]["x_events_per_campaign"]
    out = []
    for n3 in (20, 37):
        for a in (0.0, 0.2):
            for xname, x in xs.items():
                need = math.ceil(x * 3 * n3 - 1e-12)
                row = {"n_exp3_per_arm_one_target": n3, "abort": a, "threshold": xname, "x": x,
                       "min_S_events_for_GO": need, "P_GO": {}}
                for tname, lam in truths.items():
                    pe = eff_p(lam, a)
                    row["P_GO"][tname] = sum(_binom_pmf(n3, j, pe) for j in range(need, n3 + 1))
                out.append(row)
    return out


# ----------------------------------------------------------------------------- main
def main():
    sims = int(os.environ.get("EXP3_SIZING_SIMS", "400"))
    t0 = time.time()
    tin = throughput_inputs()
    scen, windows = throughput_grid(tin)
    req = {str(h): P.required_events(h, power=POWER, alpha=ALPHA) for h in (1.5, 2, 3, 4, 5)}
    req05 = {str(h): P.required_events(h, power=POWER, alpha=ALPHA_FAMILY) for h in (1.5, 2, 3, 4, 5)}
    print("mde...", flush=True)
    mde = mde_rows()
    print("converse...", flush=True)
    conv = converse_rows()
    goc = go_rule_oc(conv)
    print("sensitivity...", flush=True)
    sens, m3_note, rel = sensitivity()
    print("validation...", flush=True)
    eq = equivalence_check()
    val = validation(sims) if sims > 0 else []
    out = {
        "label": LABEL,
        "generated_at_unix": int(time.time()),
        "code": {"script": os.path.abspath(__file__), "analysis_worktree": WT,
                 "analysis_head": "f655f18 (stack-E, unmerged)",
                 "modules": ["inodefence.evaluation.power", "inodefence.evaluation.survival"]},
        "constants": {"budget": BUDGET, "jobs": JOBS, "power": POWER, "alpha_family": ALPHA_FAMILY,
                      "alpha_per_contrast": ALPHA, "alpha_note": "Holm over S-u-vs-R, S-u-vs-D: worst-case "
                      "first step 0.05/2; two-sided; direction must be faster_arm == S-u",
                      "aborted_exposure_fraction": ABORTED_EXPOSURE, "abort_grid": ABORT_GRID,
                      "abort_stress": ABORT_STRESS},
        "throughput": {"inputs": tin, "scenarios": scen,
                       "jobs3": {"exec_per_hour": None, "status": "unknown - not measured on this engine/host "
                                 "(exp3-v1 draft (d): 'jobs 3~4 여지는 미측정 · 주장 안 함')"},
                       "target_sets": TARGET_SETS,
                       "rust_tar": "fixed-fixture only, fuzzing 0 (exp3-v1 (a) 5) -> 0 campaign cells",
                       "abort_note": "prereg: denominator = all cells incl. abort, abort right-censored, "
                                     "no replacement -> aborts cost no extra cells; they reduce exposure "
                                     "(power side). Infra retries are per-step (MAX_INFRA_RETRIES=2).",
                       "windows": windows},
        "power": {
            "schoenfeld_required_events_alpha0.025": req,
            "schoenfeld_required_events_alpha0.05": req05,
            "permutation_floor": {
                "min_informative_blocks_alpha0.025": min_informative_blocks(ALPHA),
                "min_informative_blocks_alpha0.05": min_informative_blocks(ALPHA_FAMILY),
                "repo_check": "seed_block_logrank_permutation: 7 one-way discordant blocks -> p=0.015625; "
                              "6 -> p=0.03125 (run 2026-11-05)",
            },
            "signtest_model": "block-winner exact sign test (two-sided) + direction; informative block = "
                              "pair not identical; winner = arm whose event precedes the other's event "
                              "(or the other has none); exposure model = power.py",
            "mde_grid": mde,
            "converse_x": conv,
            "go_rule_operating_characteristic": goc,
            "validation_equivalence": eq,
            "validation_mc": val,
        },
        "sensitivity": {"rows": sens, "m3_inputs": m3_note, "k_reach_rel_to_k1": rel,
                        "k_reach_source": KREACH + " (in-process C2 reach, NOT realized hazard; README)"},
        "planning_derivations": {
            "campaign_seconds_quiet_p95": BUDGET * tin["pooled_p95_full_step_seconds"],
            "busy_host_factor": 3.09,
            "busy_host_factor_source": "~/inodefence-evidence/wp-throughput-20261104/SUMMARY.md:14 (host/time 3.09x)",
            "campaign_seconds_busy_p95": BUDGET * tin["pooled_p95_full_step_seconds"] * 3.09,
            "watchdog_note": "INFERRED: campaign_watchdog_seconds at budget 2000 should exceed the busy-host "
                             "p95 campaign time; EXP-0's 7200 s (budget 200) would be < busy-host 2000-step time",
            "exp0_speedup_jobs2": (tin.get("aggregate_exec_per_hour_steady_14_paired_cells") or 0)
            / tin["per_stream_exec_per_hour_solo"] if tin.get("per_stream_exec_per_hour_solo") else None,
            "lane4_speedup_jobs2": "pc 1.79x / par_eff 0.89 (wp-throughput-20261104/SUMMARY.md:24)",
            "schedule": "STATUS.md:312-315 / BACKLOG.md:31-33: register 11/18, EXP-3 ~11/20 with rule applied "
                        "11/20 -> ~2 host-days; EXP-2 conditional ~11/25; G2 11/26",
            "hazard_proxy_definition_warning": "EXP-0 item7 proxy = hit STEPS / executions; M3 A3full: 66 clean "
                                               "C1 steps / 47263 exec = 1.4e-3 vs first events 2/47263 = 4.2e-5 "
                                               "(33x). x must be in FIRST-EVENT units.",
        },
        "runtime_seconds": round(time.time() - t0, 1),
    }
    with open(os.path.join(HERE, "sizing.json"), "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False, sort_keys=False)
    print("done", out["runtime_seconds"], "s")


if __name__ == "__main__":
    main()

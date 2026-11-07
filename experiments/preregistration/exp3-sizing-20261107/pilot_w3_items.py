# Repo copy: lint/format exempt (3 comment lines added); otherwise byte-identical, see README.md.
# ruff: noqa
# fmt: off
"""W3's extra completion items for the pilot memo. Reads no oracle field.

From step records it reads only case_id. From reports of aborted cells it reads only the aborted stub.
Everything else comes from clocks.jsonl, file modification times and the docker event log. Run after
all 40 cells finish: it scans every steps file once.
"""

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

COINCIDENCE_SECONDS = 60
root = Path("/home/linux/inodefence-evidence/exp3-hazard-pilot-20261106")
raw = root / "raw"
fixed = json.loads((root / "analysis" / "fixed-section.json").read_text())
cells = fixed["cells"]
aborts = fixed["aborts"]
out = {}


def percentiles(values):
    ordered = sorted(values)
    pick = lambda q: round(ordered[min(len(ordered) - 1, int(len(ordered) * q))], 3)
    return {
        "n": len(ordered),
        "p01": pick(0.01),
        "p10": pick(0.10),
        "p50": pick(0.50),
        "p90": pick(0.90),
        "p99": pick(0.99),
        "max": round(ordered[-1], 3),
    }


def steps_file(run_id):
    return raw / f"inodefence-effect-demo-historical-{run_id}.steps.jsonl"


# (c) aborted.step_index against recorded steps, and the stub's keys and category.
stubs = []
for row in aborts:
    report = json.loads((raw / f"inodefence-effect-demo-historical-{row['run_id']}.json").read_text())
    stub = report["aborted"]
    recorded = next(cell["steps"] for cell in cells if cell["run_id"] == row["run_id"])
    stubs.append(
        {
            "run_id": row["run_id"],
            "step_index": stub.get("step_index"),
            "recorded_steps": recorded,
            "equal": stub.get("step_index") == recorded,
            "stub_case_id": stub.get("case_id"),
            "stub_keys": sorted(stub),
            "observed_keys": sorted(stub["observed"]) if isinstance(stub.get("observed"), dict) else None,
            "category": stub["observed"].get("category") if isinstance(stub.get("observed"), dict) else None,
        }
    )
out["abort_stubs"] = stubs


def poisson_upper(events, confidence):
    """Exact Poisson upper mean: the mean whose P(X <= events) is 1 - confidence."""
    low, high = float(events), events + 200.0
    for _ in range(200):
        mean = (low + high) / 2
        term = math.exp(-mean)
        total = term
        for k in range(1, events + 1):
            term *= mean / k
            total += term
        if total > 1 - confidence:
            low = mean
        else:
            high = mean
    return (low + high) / 2


def abort_time(row):
    return (raw / f"inodefence-effect-demo-historical-{row['run_id']}.json").stat().st_mtime


# Occasions: aborts within 60 s of the previous one are one occasion (fixed before the final count).
times = sorted(abort_time(row) for row in aborts)
occasions = 1 + sum(1 for a, b in zip(times, times[1:]) if b - a > COINCIDENCE_SECONDS) if times else 0

# Abort rate: all recorded steps as denominator (not T), split by form.
total_steps = sum(cell["steps"] for cell in cells)
cleanup = sum(1 for row in aborts if "cleanup" in row["reason"])
other = len(aborts) - cleanup
mu_occasion = poisson_upper(occasions, 0.975) * len(aborts) / occasions
mu_independent = poisson_upper(len(aborts), 0.975)
out["abort_rate"] = {
    "campaigns": [len(aborts), len(cells)],
    "a_point_per_campaign": len(aborts) / len(cells),
    "occasions_60s": occasions,
    "recorded_steps_T": total_steps,
    "per_step_N_over_T": len(aborts) / total_steps,
    "per_step_E_over_T": occasions / total_steps,
    "per_step_cleanup_inspect": [cleanup, cleanup / total_steps],
    "per_step_inspect": [other, other / total_steps],
    "e_recorded_over_planned": total_steps / (2000 * len(cells)),
    "upper_by_occasion": {
        "mu": mu_occasion,
        "a_upper_exposure": 1 - math.exp(-2000 * mu_occasion / total_steps),
        "formula": "1 - exp(-budget * mu / T), mu = two-sided Poisson upper(E) * N/E",
    },
    "upper_independent": {
        "mu": mu_independent,
        "a_upper_exposure": 1 - math.exp(-2000 * mu_independent / total_steps),
    },
    "groups": Counter(row["container"] for row in aborts),
    "steps": sorted(row["step"] for row in aborts),
}

# Real-time axis: quarter bins and the split W3 estimated (22 of 40 cells finished).
first = min(cell["start"] for cell in cells)
last = max(cell["end"] for cell in cells)


def steps_between(lo, hi):
    total = 0.0
    for cell in cells:
        overlap = min(hi, cell["end"]) - max(lo, cell["start"])
        if overlap > 0:
            total += cell["steps"] * overlap / cell["real_seconds"]
    return total


def band(lo, hi):
    hits = sum(1 for row in aborts if lo <= abort_time(row) < hi)
    occasions = len({int(abort_time(row)) for row in aborts if lo <= abort_time(row) < hi})
    steps = steps_between(lo, hi)
    return {
        "from": datetime.fromtimestamp(lo).strftime("%m-%d %H:%M"),
        "to": datetime.fromtimestamp(hi).strftime("%m-%d %H:%M"),
        "real_seconds": round(hi - lo),
        "aborts": hits,
        "occasions": occasions,
        "per_real_second": hits / (hi - lo),
        "steps_interpolated": round(steps),
        "per_step": hits / steps if steps else None,
    }


quarter = (last - first) / 4
out["abort_rate_real_time_quarters"] = [
    band(first + index * quarter, first + (index + 1) * quarter + (1 if index == 3 else 0))
    for index in range(4)
]
ends = sorted(cell["end"] for cell in cells)
split = ends[21]
out["abort_rate_split_at_22nd_cell"] = [band(first, split), band(split, last + 1)]

# Lifecycle distributions.
lives = defaultdict(dict)
for line in (root / "host-docker-events.log").read_text().splitlines():
    parts = line.split()
    if len(parts) == 3 and parts[0].isdigit() and "local-controller" not in parts[2]:
        lives[parts[2]].setdefault(parts[1], int(parts[0]) / 1e9)
complete = [life for life in lives.values() if {"create", "start", "die", "destroy"} <= set(life)]
die_destroy = [life["destroy"] - life["die"] for life in complete]
out["die_to_destroy_all"] = percentiles(die_destroy)
out["die_to_destroy_normal_excluding_over_10s"] = percentiles([v for v in die_destroy if v <= 10])
out["die_to_destroy_counts"] = {
    "over_1s": sum(v > 1 for v in die_destroy),
    "over_3s": sum(v > 3 for v in die_destroy),
    "over_10s": sum(v > 10 for v in die_destroy),
    "negative_clock_jump": sum(v < 0 for v in die_destroy),
}
out["start_to_die_all"] = percentiles([life["die"] - life["start"] for life in complete])

# Identity against target: the final cell ran alone, so its containers alternate. Aligned from both
# ends: an even count means the two alignments agree. Only that one R-walk cell is separable.
final = max(cells, key=lambda cell: cell["end"])
alone_from = max(cell["end"] for cell in cells if cell is not final)
solo = sorted(
    (life for life in lives.values() if final["start"] <= life.get("create", 0) <= final["end"]),
    key=lambda life: life["create"],
)
out["solo_cell"] = {
    "run_id": final["run_id"],
    "returncode": final["returncode"],
    "alone_from": datetime.fromtimestamp(alone_from).strftime("%H:%M:%S"),
    "cell_start": datetime.fromtimestamp(final["start"]).strftime("%H:%M:%S"),
    "steps": final["steps"],
    "containers_in_window": len(solo),
    "containers_per_step": len(solo) / final["steps"] if final["steps"] else None,
    "incomplete_lifecycle": sum(1 for life in solo if "start" not in life or "die" not in life),
}
usable = [life for life in solo if {"start", "die", "destroy"} <= set(life)]
# One bind-time identify precedes the steps, so 4001 = 1 + 2 * 2000; then identity, target per step.
if len(usable) == 2 * final["steps"] + 1:
    identity = usable[1::2]
    target = usable[2::2]
    for label, chosen in (("identity", identity), ("target", target)):
        values = [life["die"] - life["start"] for life in chosen]
        out[f"solo_{label}_start_to_die"] = percentiles(values)
        out[f"solo_{label}_die_to_destroy"] = percentiles([life["destroy"] - life["die"] for life in chosen])
        out[f"solo_{label}_share_0.11_to_0.13s"] = sum(0.11 <= v <= 0.13 for v in values) / len(values)
else:
    out["solo_alignment"] = f"container count {len(usable)} is not 2 * steps + 1: roles not separated"


# Case IDs: the coincidence test, and earlier runs of each aborted case within its own cell.
def case_counts(run_id):
    counts = Counter()
    with steps_file(run_id).open(encoding="utf-8") as stream:
        for line in stream:
            counts[json.loads(line)["case_id"]] += 1
    return counts


restart = case_counts("7.5.2-R-restart-s8110")
s_u = case_counts("7.5.2-S-u-s8110")
n_r, n_s = sum(restart.values()), sum(s_u.values())
match = sum(restart[case] / n_r * s_u[case] / n_s for case in restart if case in s_u)
needle = next(row["case"] for row in aborts if row["run_id"] == "7.5.2-S-u-s8110")
full = next(case for case in s_u if case.startswith(needle))
out["case_coincidence"] = {
    "pair": ["7.5.2-R-restart-s8110", "7.5.2-S-u-s8110"],
    "sum_fR_fS": match,
    "distinct_cases": [len(restart), len(s_u)],
    "steps": [n_r, n_s],
    "shared_cases": len(set(restart) & set(s_u)),
    "case": full,
    "f_R": restart[full] / n_r,
    "f_S": s_u[full] / n_s,
    "top_shared": [
        {"case": case[:12], "f_R": round(restart[case] / n_r, 4), "f_S": round(s_u[case] / n_s, 4)}
        for case in sorted(set(restart) & set(s_u), key=lambda c: -restart[c] * s_u[c])[:5]
    ],
}

# The stub's case_id is the case being run at the aborted step (run_effect_demo.py raises with the
# loop's own index and case); that step has no record. Each f_i is that case's share of the cell's
# recorded steps; a random step would land on a case with probability sum f(c)^2.
stub_cases = {item["run_id"]: item["stub_case_id"] for item in stubs}
prior = []
for row in aborts:
    full_case = stub_cases[row["run_id"]]
    counts = Counter()
    earlier = []
    last_case = None
    with steps_file(row["run_id"]).open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            last_case = record["case_id"]
            counts[last_case] += 1
            if last_case == full_case:
                earlier.append((record.get("index"), record.get("origin")))
    steps = sum(counts.values())
    prior.append(
        {
            "run_id": row["run_id"],
            "step": row["step"],
            "aborted_step_case": full_case,
            "last_recorded_case": last_case,
            "same_as_last_recorded": last_case == full_case,
            "earlier_runs_in_cell": len(earlier),
            "first_earlier": earlier[:2],
            "f_i": counts[full_case] / steps,
            "sum_f_squared": sum((n / steps) ** 2 for n in counts.values()),
            "distinct_cases": len(counts),
        }
    )
out["aborted_case_earlier_runs"] = prior
sum_f = sum(item["f_i"] for item in prior)
sum_squared = sum(item["sum_f_squared"] for item in prior)
out["aborted_case_frequency_ratio"] = {
    "sum_f_i": sum_f,
    "sum_of_sum_f_squared": sum_squared,
    "ratio": sum_f / sum_squared if sum_squared else None,
    "case_is": "the aborted step's case (no record of that step exists)",
    "aborted_cases_seen_before_in_their_cell": sum(1 for item in prior if item["earlier_runs_in_cell"]),
}
shared = Counter(item["aborted_step_case"] for item in prior)
out["aborted_case_repeats_across_cells"] = {case[:12]: n for case, n in shared.items() if n > 1}

(root / "analysis" / "w3-items.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
print(json.dumps(out, indent=1, ensure_ascii=False))

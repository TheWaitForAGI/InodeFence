# Repo copy: lint/format exempt (3 comment lines added); otherwise byte-identical, see README.md.
# ruff: noqa
# fmt: off
"""Inputs for the pilot result memo's fixed section. Reads no oracle field and no step record.

Sources: clocks.jsonl, the failure-marker line of each aborted cell's log, file sizes and modification
times, host samples, and the docker event log (time, action, container name). Step counts come from
counting lines. Writes fixed-section.json beside the analysis output and prints the same tables.
Wall-clock values can be off by up to about 2.5 s because this host's wall clock jumps backward.
"""

import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

root = Path("/home/linux/inodefence-evidence/exp3-hazard-pilot-20261106")
raw = root / "raw"
out = root / "analysis"
ARMS = ("R-walk", "R-restart", "D", "S-u")
ABORT_LINE = re.compile(r"aborted: step (\d+) case ([0-9a-f]+): \S*BackendError: (.*)$", re.MULTILINE)


def stamp(value):
    return datetime.fromtimestamp(value).strftime("%H:%M:%S.%f")[:-3]


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


clocks = [json.loads(line) for line in (raw / "clocks.jsonl").read_text().splitlines()]
logger_start = float((root / "host-docker-events.started").read_text())

events = []
for line in (root / "host-docker-events.log").read_text().splitlines():
    parts = line.split()
    if len(parts) == 3 and parts[0].isdigit():
        events.append((int(parts[0]) / 1e9, parts[1], parts[2]))
lives = defaultdict(dict)
for time, action, name in events:
    if "local-controller" not in name:
        lives[name].setdefault(action, time)
last_event = events[-1][0]

# Per-cell table: steps by line count, real elapsed, raw size.
cells = []
for record in clocks:
    run_id = record["run_id"]
    base = f"inodefence-effect-demo-historical-{run_id}"
    steps_path = raw / f"{base}.steps.jsonl"
    with steps_path.open("rb") as stream:
        steps = sum(1 for _ in stream)
    size = sum(path.stat().st_size for path in raw.glob(f"*{run_id}*"))
    cells.append(
        {
            "run_id": run_id,
            "arm": record["arm"],
            "seed": record["seed"],
            "returncode": record["returncode"],
            "steps": steps,
            "start": record["started"]["realtime"],
            "end": record["ended"]["realtime"],
            "real_seconds": record["ended"]["realtime"] - record["started"]["realtime"],
            "raw_bytes": size,
        }
    )

# Abort table: kind, step, case prefix, time, logger coverage, container evidence.
aborts = []
never_started = {
    name: life
    for name, life in lives.items()
    if "create" in life and "start" not in life and "destroy" in life
}
slow_teardown = {
    name: life
    for name, life in lives.items()
    if "die" in life and "destroy" in life and life["destroy"] - life["die"] > 3.0
}
matched_never = set()
matched_slow = set()
for cell in cells:
    if cell["returncode"] == 0:
        continue
    run_id = cell["run_id"]
    base = f"inodefence-effect-demo-historical-{run_id}"
    last_step = (raw / f"{base}.steps.jsonl").stat().st_mtime
    report = (raw / f"{base}.json").stat().st_mtime
    log = (raw / f"{run_id}.log").read_text(encoding="utf-8", errors="replace")
    match = ABORT_LINE.search(log)
    step, case, reason = int(match[1]), match[2], match[3].strip()
    row = {
        "run_id": run_id,
        "arm": cell["arm"],
        "seed": cell["seed"],
        "step": step,
        "case": case[:12],
        "reason": reason,
        "last_step": stamp(last_step),
        "abort_report": stamp(report),
        "gap_seconds": round(report - last_step, 1),
        "logger_covered": report >= logger_start,
    }
    if not row["logger_covered"]:
        row["container"] = "미관찰"
    else:
        near = [
            name
            for name, life in never_started.items()
            if last_step - 3 <= life["create"] <= report + 3
        ]
        slow = [
            name
            for name, life in slow_teardown.items()
            if last_step - 3 <= life["die"] <= report + 3
        ]
        matched_never.update(near)
        matched_slow.update(slow)
        if near:
            life = never_started[near[0]]
            row["container"] = "created/never started"
            row["container_name"] = near[0][-12:]
            row["create"] = stamp(life["create"])
            row["destroy"] = stamp(life["destroy"])
        else:
            row["container"] = "started/died, then stall"
            row["containers"] = [
                {
                    "name": name[-12:],
                    "create": stamp(slow_teardown[name]["create"]),
                    "start": stamp(slow_teardown[name]["start"]),
                    "die": stamp(slow_teardown[name]["die"]),
                    "destroy": stamp(slow_teardown[name]["destroy"]),
                }
                for name in slow
            ]
    aborts.append(row)

# Lifecycle check: the rest of the log shows how unusual the abort containers are.
per_case_creates = sum(1 for life in lives.values() if "create" in life)
create_to_start = [
    life["start"] - life["create"] for life in lives.values() if "create" in life and "start" in life
]
gaps = [(events[i + 1][0] - events[i][0], events[i][0]) for i in range(len(events) - 1)]
big_gaps = sorted(
    ((round(d, 2), stamp(t)) for d, t in gaps if d > 2.0), key=lambda item: item[1]
)
never_by_arm = Counter(
    row["arm"] for row in aborts if row.get("container") == "created/never started"
)

# Containers per step. A cell that ran alone gives the ratio directly; the whole covered span checks it.
covered = [cell for cell in cells if cell["start"] >= logger_start]
straddling = [cell for cell in cells if cell["start"] < logger_start < cell["end"]]
solo = None
if cells and clocks:
    final = max(cells, key=lambda cell: cell["end"])
    others = [cell for cell in cells if cell is not final]
    alone_from = max((cell["end"] for cell in others), default=final["start"])
    if alone_from <= final["start"] + 5:
        creates = sum(
            1 for life in lives.values() if final["start"] <= life.get("create", 0) <= final["end"]
        )
        solo = {
            "run_id": final["run_id"],
            "steps": final["steps"],
            "creates": creates,
            "ratio": creates / final["steps"] if final["steps"] else None,
        }
covered_steps = sum(cell["steps"] for cell in covered)
straddling_steps_after = sum(
    cell["steps"] * (cell["end"] - logger_start) / cell["real_seconds"] for cell in straddling
)
expected_two = 2 * (covered_steps + straddling_steps_after)
creates_by_arm = {
    arm: {
        "steps_covered_cells": sum(cell["steps"] for cell in covered if cell["arm"] == arm),
        "derived_creates_two_per_step": 2
        * sum(cell["steps"] for cell in covered if cell["arm"] == arm),
        "straddling_cells": [cell["run_id"] for cell in straddling if cell["arm"] == arm],
    }
    for arm in ARMS
}

# Abort rates by arm, by segment, by campaign and by executed step.
total_steps = sum(cell["steps"] for cell in cells)
by_arm = {
    arm: {
        "cells": sum(1 for cell in cells if cell["arm"] == arm),
        "aborts": sum(1 for row in aborts if row["arm"] == arm),
        "executed_steps": sum(cell["steps"] for cell in cells if cell["arm"] == arm),
        "abort_steps": sorted(row["step"] for row in aborts if row["arm"] == arm),
    }
    for arm in ARMS
}
first_start = min(cell["start"] for cell in cells)
last_end = max(cell["end"] for cell in cells)
before_cells = [cell for cell in cells if cell["end"] < logger_start]
before_steps = sum(cell["steps"] for cell in before_cells) + sum(
    cell["steps"] * (logger_start - cell["start"]) / cell["real_seconds"] for cell in straddling
)
after_steps = total_steps - before_steps
before_aborts = sum(1 for row in aborts if not row["logger_covered"])
after_aborts = len(aborts) - before_aborts
segments = {
    "before_logger": {
        "real_seconds": logger_start - first_start,
        "cells_finished": len(before_cells),
        "aborts": before_aborts,
        "steps": before_steps,
        "exec_per_hour_real": before_steps / (logger_start - first_start) * 3600,
    },
    "after_logger": {
        "real_seconds": last_end - logger_start,
        "cells_finished": len(cells) - len(before_cells),
        "aborts": after_aborts,
        "steps": after_steps,
        "exec_per_hour_real": after_steps / (last_end - logger_start) * 3600,
    },
}

# Host: load bands by segment, and any container that is not this run's.
samples = [json.loads(line) for line in (root / "host" / "samples.jsonl").read_text().splitlines()]
own = re.compile(r"^inodefence-(local-controller-.*|[0-9a-f]{32})$")
foreign = Counter(
    name for sample in samples for name in sample["containers"] if not own.match(name)
)
load = {}
for label, chosen in (
    ("before_logger", [s for s in samples if s["realtime"] < logger_start]),
    ("after_logger", [s for s in samples if s["realtime"] >= logger_start]),
):
    ones = [sample["loadavg"][0] for sample in chosen]
    load[label] = {
        "samples": len(ones),
        "p10": round(percentile(ones, 0.10), 2),
        "p50": round(percentile(ones, 0.50), 2),
        "p90": round(percentile(ones, 0.90), 2),
        "max": round(max(ones), 2),
    }

result = {
    "logger_start": datetime.fromtimestamp(logger_start).isoformat(),
    "last_event": datetime.fromtimestamp(last_event).isoformat(),
    "aborts": aborts,
    "abort_steps_sorted": sorted(row["step"] for row in aborts),
    "abort_kinds": Counter(row["reason"] for row in aborts),
    "abort_containers": Counter(row["container"] for row in aborts),
    "by_arm": by_arm,
    "campaign_rate": [len(aborts), len(cells)],
    "per_executed_step_rate": len(aborts) / total_steps,
    "total_executed_steps": total_steps,
    "segments": segments,
    "lifecycle": {
        "per_case_creates_in_log": per_case_creates,
        "never_started": len(never_started),
        "never_started_matched_to_abort": len(matched_never),
        "never_started_by_arm": never_by_arm,
        "die_to_destroy_over_3s": len(slow_teardown),
        "die_to_destroy_over_3s_matched_to_abort": len(matched_slow),
        "create_to_start_seconds": {
            "p50": round(statistics.median(create_to_start), 3),
            "max": round(max(create_to_start), 2),
        },
        "event_gaps_over_2s": big_gaps,
    },
    "containers_per_step": {
        "solo_cell": solo,
        "covered_cell_steps": covered_steps,
        "straddling_steps_after_logger_estimate": round(straddling_steps_after),
        "expected_creates_two_per_step": round(expected_two),
        "observed_creates": per_case_creates,
    },
    "creates_by_arm": creates_by_arm,
    "load": load,
    "foreign_containers": foreign,
    "monotonic_over_real_by_cell": {
        "min": round(
            min(
                (r["ended"]["monotonic"] - r["started"]["monotonic"])
                / (r["ended"]["realtime"] - r["started"]["realtime"])
                for r in clocks
            ),
            4,
        ),
        "max": round(
            max(
                (r["ended"]["monotonic"] - r["started"]["monotonic"])
                / (r["ended"]["realtime"] - r["started"]["realtime"])
                for r in clocks
            ),
            4,
        ),
    },
    "cells": cells,
}
out.mkdir(exist_ok=True)
(out / "fixed-section.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

json.dump(
    {key: value for key, value in result.items() if key != "cells"},
    sys.stdout,
    indent=1,
    ensure_ascii=False,
)
print()
sizes = [cell for cell in cells]
for arm in ARMS:
    chosen = [cell for cell in sizes if cell["arm"] == arm and cell["returncode"] == 0]
    if chosen:
        print(
            f"{arm}: complete {len(chosen)}, raw MB min {min(c['raw_bytes'] for c in chosen) / 1e6:.0f} "
            f"max {max(c['raw_bytes'] for c in chosen) / 1e6:.0f}, real s min "
            f"{min(c['real_seconds'] for c in chosen):.0f} max {max(c['real_seconds'] for c in chosen):.0f}"
        )

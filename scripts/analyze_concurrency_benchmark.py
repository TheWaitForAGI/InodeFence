"""Analysis of the concurrency scaling benchmark (``concurrency-scaling-v1``).

Reads a benchmark output tree and writes ``concurrency-report.json`` and ``.md``. Timing and
counts only: oracle fields are never copied into a result, and no hit, T_first or U_viol is
computed here. The one comparison that touches them, ``check_native_determinism``, is reduced to
two booleans.

Terms (design file, section 4):

* normal campaign: return code 0, a report without an abort record, every planned step present,
  the planned config and image, and a steps file that matches the report;
* throughput uses CLOCK_REALTIME, because this host's monotonic clock is not real time. Per-step
  seconds come from the report and stay labelled monotonic;
* a ``cleanup_*`` abort category can hide an earlier error (design file, section 3), so such an
  abort is marked ``first_error_may_be_masked``.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from scripts.check_native_determinism import compare_report_pair
from scripts.run_concurrency_benchmark import BLOCK_FILE, SMOKE_STAGE, Design, load_design

from inodefence.evaluation.abort_classification import InvalidReason, classify_abort_reason
from inodefence.evaluation.rds_report import LoadedCell, ReportFormatError, load_cell_files

LABEL = "demo run; concurrency benchmark (unregistered, not pooled, no oracle analysis)"
REPORT_JSON = "concurrency-report.json"
REPORT_MD = "concurrency-report.md"
MASKING_CATEGORIES = frozenset({InvalidReason.CLEANUP_INSPECT, InvalidReason.CLEANUP_REMOVE})
TARGET_TIMEOUT_SECONDS = 10.0
_FAILED_STEP = re.compile(r"FAILED at step: (.+?) \(exit")


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def _rate(count: float, seconds: float) -> float | None:
    return count / seconds * 3600.0 if seconds > 0 else None


def _harness_step(log: Path) -> str | None:
    """The harness step a nonzero cell failed in, from the smoke script's own log line."""
    if not log.is_file():
        return None
    found = _FAILED_STEP.findall(log.read_text(encoding="utf-8", errors="replace"))
    return found[-1] if found else None


def _steps_match_report(loaded: LoadedCell, steps_path: Path) -> bool:
    """The steps file is a prefix of the report's steps, by index and case id."""
    if loaded.steps_from != "report":
        return True
    if not steps_path.is_file():
        return False
    lines = [line for line in steps_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) > len(loaded.records):
        return False
    for line, record in zip(lines, loaded.records, strict=False):
        step = json.loads(line)
        if step.get("index") != record.get("index") or step.get("case_id") != record.get("case_id"):
            return False
    return True


def _nonconformance(report: Mapping[str, Any], cell: Mapping[str, Any], design: Design) -> str:
    config = report.get("config")
    if isinstance(config, Mapping) and (
        config.get("random_seed") != cell["seed"]
        or config.get("execution_budget") != cell["budget"]
    ):
        return "report config differs from the planned cell"
    if report.get("image_id") != design.image_digest:
        return f"report image_id is {report.get('image_id')}"
    sentinels = report.get("sentinel_set")
    if isinstance(sentinels, Mapping) and sentinels.get("count") != design.sentinel_count:
        return f"report sentinel count is {sentinels.get('count')}"
    return ""


def summarize_cell(
    cell: Mapping[str, Any], raw: Path, design: Design
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """One cell's facts (no oracle field), and its report when the cell is comparable."""
    summary: dict[str, Any] = {
        "run_id": cell["run_id"],
        "arm": cell["arm"],
        "seed": cell["seed"],
        "returncode": cell["returncode"],
        "watchdog_killed": cell["watchdog_killed"],
        "real_seconds": cell["ended"]["realtime"] - cell["started"]["realtime"],
        "harness_failed_step": _harness_step(raw / cell["log"]),
        "executions": 0,
        "abort": None,
        "terminations": {},
        "invalid_steps": 0,
        "observation_failures": 0,
        "step_seconds_monotonic_p50": None,
        "step_seconds_monotonic_p95": None,
        "target_seconds_max": None,
        "integrity_problem": None,
    }
    report_path, steps_path = raw / cell["report"], raw / cell["steps"]
    if not report_path.is_file() and not steps_path.is_file():
        summary["disposition"] = "no-record"
        return summary, None
    try:
        loaded = load_cell_files(report_path, steps_path)
    except (ReportFormatError, ValueError, OSError) as error:
        summary["disposition"] = "unreadable"
        summary["integrity_problem"] = str(error)
        return summary, None
    records = loaded.records
    summary["executions"] = len(records)
    summary["terminations"] = dict(
        Counter(str((step.get("feedback") or {}).get("trace_termination")) for step in records)
    )
    summary["invalid_steps"] = sum(1 for step in records if step.get("validity") == "invalid")
    summary["observation_failures"] = sum(
        len((step.get("trace") or {}).get("observation_failures") or ()) for step in records
    )
    report = loaded.report
    timing = report.get("timing") if report else None
    per_case = timing.get("per_case") if isinstance(timing, Mapping) else None
    if isinstance(per_case, list) and per_case:
        walls = [float(item["wall_seconds"]) for item in per_case]
        summary["step_seconds_monotonic_p50"] = _percentile(walls, 0.5)
        summary["step_seconds_monotonic_p95"] = _percentile(walls, 0.95)
        summary["target_seconds_max"] = max(float(item["target_seconds"]) for item in per_case)
    if loaded.aborted_at_step is not None:
        aborted = report.get("aborted") if report else None
        reason = str(aborted.get("reason")) if isinstance(aborted, Mapping) else None
        category = classify_abort_reason(reason) if reason else InvalidReason.OTHER
        summary["disposition"] = "abort"
        summary["abort"] = {
            "step_index": aborted.get("step_index") if isinstance(aborted, Mapping) else None,
            "category": category.value,
            "first_error_may_be_masked": category in MASKING_CATEGORIES,
            "reason": reason if reason is not None else "no report written",
        }
        return summary, None
    assert report is not None
    problem = _nonconformance(report, cell, design)
    if problem:
        summary["disposition"] = "nonconformant"
        summary["integrity_problem"] = problem
        return summary, None
    if not _steps_match_report(loaded, steps_path):
        summary["disposition"] = "integrity-failure"
        summary["integrity_problem"] = "steps file is not a prefix of the report steps"
        return summary, None
    if cell["returncode"] != 0 or len(records) != cell["budget"]:
        summary["disposition"] = "incomplete"
        return summary, None
    summary["disposition"] = "normal"
    return summary, dict(report)


def lifecycle_seconds(lines: Iterable[str]) -> dict[str, dict[str, float | int | None]]:
    """create->start, start->die, die->destroy seconds per container class, on the daemon clock."""
    moments: dict[str, dict[str, int]] = defaultdict(dict)
    names: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        identity = event.get("id") or event.get("ID")
        action = event.get("Action") or event.get("status")
        stamp = event.get("timeNano")
        if not identity or not action or stamp is None:
            continue
        moments[identity].setdefault(action, int(stamp))
        attributes = (event.get("Actor") or {}).get("Attributes") or {}
        if "name" in attributes:
            names[identity] = attributes["name"]
    spans: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for identity, seen in moments.items():
        kind = "controller" if "controller" in names.get(identity, "") else "target"
        for span, first, second in (
            ("create_to_start", "create", "start"),
            ("start_to_die", "start", "die"),
            ("die_to_destroy", "die", "destroy"),
        ):
            if first in seen and second in seen:
                spans[kind][span].append((seen[second] - seen[first]) / 1e9)
    return {
        f"{kind}.{span}": {
            "count": len(values),
            "p50": _percentile(values, 0.5),
            "p95": _percentile(values, 0.95),
            "max": max(values),
        }
        for kind, by_span in sorted(spans.items())
        for span, values in sorted(by_span.items())
    }


def host_summary(lines: Iterable[str]) -> dict[str, Any]:
    """Peaks and means from the host samples; CPU busy share from the kernel counters."""
    samples = [json.loads(line) for line in lines if line.strip()]
    if not samples:
        return {"samples": 0}
    available = [s["memory"]["MemAvailable"] for s in samples if "MemAvailable" in s["memory"]]
    swap = [s["memory"]["SwapTotal"] - s["memory"]["SwapFree"] for s in samples]
    probes = [s["docker_ps_seconds"] for s in samples if "docker_ps_seconds" in s]
    first, last = samples[0]["cpu_jiffies"], samples[-1]["cpu_jiffies"]
    deltas = [after - before for before, after in zip(first, last, strict=False)]
    total = sum(deltas)
    # /proc/stat order: user nice system idle iowait irq softirq steal ...
    return {
        "samples": len(samples),
        "load1_max": max(s["loadavg"][0] for s in samples),
        "cpu_busy_fraction": 1 - (deltas[3] + deltas[4]) / total if total else None,
        "cpu_iowait_fraction": deltas[4] / total if total else None,
        "cpu_system_fraction": deltas[2] / total if total else None,
        "memory_available_min_bytes": min(available) if available else None,
        "swap_used_max_bytes": max(swap),
        "disk_fraction_max": max(s["disk_fraction"] for s in samples),
        "docker_ps_seconds_p50": _percentile(probes, 0.5),
        "docker_ps_seconds_max": max(probes) if probes else None,
        "docker_ps_errors": sum(1 for s in samples if "docker_ps_error" in s),
    }


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def _arm_spread(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Real seconds per executed step by arm, normal cells only."""
    per_arm: dict[str, list[float]] = defaultdict(list)
    for cell in cells:
        if cell["disposition"] == "normal" and cell["executions"]:
            per_arm[cell["arm"]].append(cell["real_seconds"] / cell["executions"])
    means = {arm: statistics.fmean(values) for arm, values in sorted(per_arm.items())}
    return {
        "real_seconds_per_step_by_arm": means,
        "slowest_over_fastest": (max(means.values()) / min(means.values()) if means else None),
    }


def summarize_block(
    directory: Path, record: Mapping[str, Any], design: Design
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """One block's metrics, and its comparable reports keyed by run id."""
    raw = directory / "raw"
    cells: list[dict[str, Any]] = []
    reports: dict[str, dict[str, Any]] = {}
    not_run = 0
    for cell in record["cells"]:
        if cell["state"] != "ran":
            not_run += 1
            continue
        summary, report = summarize_cell(cell, raw, design)
        cells.append(summary)
        if report is not None:
            reports[cell["run_id"]] = report
    real = record["ended"]["realtime"] - record["started"]["realtime"]
    monotonic = record["ended"]["monotonic"] - record["started"]["monotonic"]
    normal = [cell for cell in cells if cell["disposition"] == "normal"]
    executions = sum(cell["executions"] for cell in cells)
    aborts = [cell for cell in cells if cell["disposition"] == "abort"]
    terminations: Counter[str] = Counter()
    for cell in cells:
        terminations.update(cell["terminations"])
    target_max = [c["target_seconds_max"] for c in cells if c["target_seconds_max"] is not None]
    mean_cell = statistics.fmean(cell["real_seconds"] for cell in normal) if normal else None
    block = {
        "stage": record["stage"],
        "index": record["index"],
        "jobs": record["jobs"],
        "real_seconds": real,
        "monotonic_over_real": monotonic / real if real > 0 else None,
        "stopped_reason": record.get("stopped_reason"),
        "residual_after_block": record.get("residual_after_block"),
        "cells_planned": len(record["cells"]),
        "cells_not_run": not_run,
        "dispositions": dict(Counter(cell["disposition"] for cell in cells)),
        "normal_campaigns": len(normal),
        "normal_campaigns_per_real_hour": _rate(len(normal), real),
        # Every slot busy, without the tail of a batch that does not divide by jobs.
        "normal_campaigns_per_real_hour_full_slots": (
            record["jobs"] * 3600.0 / mean_cell if mean_cell else None
        ),
        "executions": executions,
        "executions_per_real_hour": _rate(executions, real),
        "aborts": [{"run_id": cell["run_id"], **cell["abort"]} for cell in aborts],
        "abort_per_execution_rule_of_three": (
            3.0 / executions if executions and not aborts else None
        ),
        "watchdog_kills": sum(1 for cell in cells if cell["watchdog_killed"]),
        "harness_failed_steps": dict(
            Counter(cell["harness_failed_step"] for cell in cells if cell["harness_failed_step"])
        ),
        "integrity_problems": {
            cell["run_id"]: cell["integrity_problem"] for cell in cells if cell["integrity_problem"]
        },
        "terminations": dict(terminations),
        "invalid_steps": sum(cell["invalid_steps"] for cell in cells),
        "observation_failures": sum(cell["observation_failures"] for cell in cells),
        "target_seconds_max": max(target_max) if target_max else None,
        "target_timeout_seconds": TARGET_TIMEOUT_SECONDS,
        "arm_spread": _arm_spread(cells),
        "host": host_summary(_read_lines(directory / "host" / "samples.jsonl")),
        "lifecycle_seconds": lifecycle_seconds(_read_lines(directory / "host" / "events.jsonl")),
        "cells": cells,
    }
    return block, reports


def determinism_against_reference(
    reports: Mapping[str, Mapping[str, Any]], reference: dict[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Compare each normal cell with its first normal run; booleans only, so no outcome leaks."""
    compared = passed = identical = 0
    differing: list[str] = []
    for run_id, report in reports.items():
        if run_id not in reference:
            reference[run_id] = report
            continue
        verdict = compare_report_pair(dict(reference[run_id]), dict(report))
        compared += 1
        passed += bool(verdict["determinism_pass"])
        identical += bool(verdict["observation_sequence_identical"])
        if not verdict["determinism_pass"]:
            differing.append(run_id)
    return {
        "cells_compared": compared,
        "determinism_pass": passed,
        "observation_sequence_identical": identical,
        "differing_cells": differing,
    }


def compare_levels(blocks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per-stage level table, plus the drift between a level's two blocks in crossed order."""
    by_jobs: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for block in blocks:
        by_jobs[block["jobs"]].append(block)
    levels: dict[str, Any] = {}
    for jobs, group in sorted(by_jobs.items()):
        rates = [b["normal_campaigns_per_real_hour"] or 0.0 for b in group]
        levels[str(jobs)] = {
            "blocks": len(group),
            "normal_campaigns_per_real_hour_mean": statistics.fmean(rates),
            "normal_campaigns_per_real_hour_blocks": rates,
            "executions_per_real_hour_mean": statistics.fmean(
                b["executions_per_real_hour"] or 0.0 for b in group
            ),
            "drift_second_over_first": rates[-1] / rates[0]
            if len(rates) > 1 and rates[0]
            else None,
            "executions": sum(b["executions"] for b in group),
            "aborts": sum(len(b["aborts"]) for b in group),
            "watchdog_kills": sum(b["watchdog_kills"] for b in group),
            "invalid_steps": sum(b["invalid_steps"] for b in group),
            "observation_failures": sum(b["observation_failures"] for b in group),
            "timed_out_steps": sum(b["terminations"].get("timed_out", 0) for b in group),
            "determinism_cells_differing": sum(
                len((b.get("determinism") or {}).get("differing_cells") or ()) for b in group
            ),
        }
    return levels


def analyze(output: Path, design: Design) -> dict[str, Any]:
    stages: dict[str, Any] = {}
    reference: dict[str, Mapping[str, Any]] = {}
    for stage in design.stages:
        if stage == SMOKE_STAGE or not (output / stage).is_dir():
            continue
        blocks: list[dict[str, Any]] = []
        for index, jobs in enumerate(design.stages[stage], start=1):
            directory = output / stage / f"block-{index}-j{jobs}"
            record_path = directory / BLOCK_FILE
            if not record_path.is_file():
                continue
            record = json.loads(record_path.read_text(encoding="utf-8"))
            block, reports = summarize_block(directory, record, design)
            block["determinism"] = determinism_against_reference(reports, reference)
            blocks.append(block)
        stages[stage] = {"levels": compare_levels(blocks), "blocks": blocks}
    return {
        "label": LABEL,
        "design_id": design.design_id,
        "design_sha256": design.sha256,
        "execution_mode": "per-case-container",
        "stages": stages,
    }


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# 동시 실행 벤치마크 결과: {report['design_id']}",
        "",
        f"라벨: {report['label']}.",
        "실험 결과가 아니며 EXP 데이터와 합치지 않는다. oracle 값은 읽지 않았다.",
        "처리량은 실시간 기준이다. step 초는 monotonic 값이다.",
    ]
    for stage, content in report["stages"].items():
        lines += [
            "",
            f"## 단계 {stage}",
            "",
            "| jobs | 블록 | 정상 캠페인/실시간 h | 블록별 | 실행/실시간 h | 드리프트 | 실행 수 | "
            "abort | watchdog | timed_out | invalid | 관찰 실패 | 결정론 불일치 셀 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for jobs, level in content["levels"].items():
            per_block = ", ".join(
                _fmt(value) for value in level["normal_campaigns_per_real_hour_blocks"]
            )
            lines.append(
                f"| {jobs} | {level['blocks']} | "
                f"{_fmt(level['normal_campaigns_per_real_hour_mean'])} | {per_block} | "
                f"{_fmt(level['executions_per_real_hour_mean'], 0)} | "
                f"{_fmt(level['drift_second_over_first'])} | {level['executions']} | "
                f"{level['aborts']} | {level['watchdog_kills']} | {level['timed_out_steps']} | "
                f"{level['invalid_steps']} | {level['observation_failures']} | "
                f"{level['determinism_cells_differing']} |"
            )
        lines += [
            "",
            "| 블록 | jobs | 실시간 h | 포화 캠페인/h | CPU 사용 | iowait | 최대 load | "
            "최소 가용 GiB | docker ps p50 s | target 최대 s | arm 편차 | 중단 사유 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for block in content["blocks"]:
            host = block["host"]
            available = host.get("memory_available_min_bytes")
            lines.append(
                f"| {block['index']} | {block['jobs']} | {block['real_seconds'] / 3600:.2f} | "
                f"{_fmt(block['normal_campaigns_per_real_hour_full_slots'])} | "
                f"{_fmt(host.get('cpu_busy_fraction'))} | "
                f"{_fmt(host.get('cpu_iowait_fraction'))} | "
                f"{_fmt(host.get('load1_max'))} | "
                f"{_fmt(available / 2**30 if available else None)} | "
                f"{_fmt(host.get('docker_ps_seconds_p50'))} | "
                f"{_fmt(block['target_seconds_max'])} | "
                f"{_fmt(block['arm_spread']['slowest_over_fastest'])} | "
                f"{block['stopped_reason'] or '—'} |"
            )
        aborts = [(block["index"], item) for block in content["blocks"] for item in block["aborts"]]
        lines += ["", "### abort", ""]
        if not aborts:
            lines.append("없음.")
        for index, item in aborts:
            masked = " (첫 오류가 가려졌을 수 있음)" if item["first_error_may_be_masked"] else ""
            lines.append(
                f"- 블록 {index} `{item['run_id']}` step {item['step_index']}: "
                f"{item['category']}{masked}"
            )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="the benchmark output tree")
    args = parser.parse_args(argv)
    report = analyze(args.output, load_design(args.design))
    (args.output / REPORT_JSON).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output / REPORT_MD).write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.output / REPORT_JSON} and {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

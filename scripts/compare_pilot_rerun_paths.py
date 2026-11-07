"""Compare benchmark re-run cells with the hazard pilot along the ``case_id`` path. Report only.

The concurrency benchmark re-runs pilot seeds. This script answers two questions the benchmark
analyzer does not ask, because the analyzer never reads the pilot:

* does a re-run cell follow the pilot cell's inputs (common prefix, first mismatch)?
* when it reaches a step where the pilot cell aborted, does the same abort come back?

A recurrence is the same (arm, seed, step, case_id). It is the input-dependence evidence for the
reopening decision (D040-D21): a flag for a human, never an automatic stop, and never an input to
the benchmark's selection rules. A pilot verdict is not changed by anything here.

Sealed raw: from step records only ``index`` and ``case_id`` are taken, and a report is opened only
for a cell that exited nonzero, for its ``aborted`` stub. No oracle field reaches the output.
Run it once at the end of a stage, not per block. Do not join the common prefix with the pilot's
event positions to count re-run events before EXP-3 is frozen.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.make_raw_manifest import hash_file, parse_manifest
from scripts.run_concurrency_benchmark import (
    BLOCK_FILE,
    EXECUTION_MODE,
    Design,
    output_problem,
    planned_blocks,
)
from scripts.run_concurrency_benchmark import load_design as load_benchmark_design
from scripts.run_hazard_pilot import PilotDesign, planned_cells
from scripts.run_hazard_pilot import load_design as load_pilot_design

REPORT_JSON = "pilot-path-comparison.json"
REPORT_MD = "pilot-path-comparison.md"
#: Fields that must agree between the two designs, or comparing paths means nothing.
SHARED_CONDITIONS = (
    "target_version",
    "image_digest",
    "docker_engine",
    "budget",
    "mutation_policy",
    "vocabulary",
    "sentinel_generator_id",
    "sentinel_generator_seed",
    "sentinel_count",
    "observer_integrity_policy",
)
PASSED = "passed"
RECURRED = "recurred"
NOT_TESTED_DIVERGED = "not_tested_diverged"
NOT_TESTED_STOPPED = "not_tested_rerun_stopped"
NOT_TESTED_OTHER_CASE = "not_tested_other_case"
NOT_TESTED_NO_RECORD = "not_tested_no_record"
NOT_TESTED_REPORT = "not_tested_report_unreadable"
GROUP_LABELS = {
    "created/never started": "(1)",
    "started/died, then stall": "(2)",
    "미관찰": "(3)",
}


class ComparisonError(ValueError):
    """The inputs cannot be compared; nothing is reported."""


class UnreadableSteps(ValueError):
    """A steps file does not parse, or its indices are not its line numbers."""


class UnreadableReport(ValueError):
    """A nonzero cell's report does not parse, or its abort stub is malformed."""


@dataclass(frozen=True, slots=True)
class AbortRecord:
    step_index: int
    case_id: str
    reason: str
    category: str | None


@dataclass(frozen=True, slots=True)
class CellFiles:
    """One cell's identity and files. ``state`` is the driver's: ``ran`` or ``not-run``."""

    label: str
    search: str
    seed: int
    returncode: int | None
    steps: Path | None
    report: Path | None
    state: str = "ran"


@dataclass(frozen=True, slots=True)
class RerunBlock:
    name: str
    jobs: int | None
    cells: tuple[CellFiles, ...]
    checkout_head: str | None = None


def read_case_ids(path: Path) -> list[str]:
    """The step sequence. Only ``index`` and ``case_id`` are taken from each record."""
    case_ids: list[str] = []
    with path.open(encoding="utf-8") as stream:
        for position, line in enumerate(stream):
            try:
                record = json.loads(line)
                index, case_id = record["index"], record["case_id"]
            except (json.JSONDecodeError, KeyError, TypeError) as error:
                raise UnreadableSteps(f"{path.name}: line {position}: {error}") from error
            if index != position or not isinstance(case_id, str):
                raise UnreadableSteps(f"{path.name}: line {position} has index {index}")
            case_ids.append(case_id)
    return case_ids


def read_abort(cell: CellFiles) -> AbortRecord | None:
    """The abort stub of a nonzero cell. A completed cell's report is never opened."""
    if not cell.returncode or cell.report is None or not cell.report.is_file():
        return None
    try:
        data = json.loads(cell.report.read_text(encoding="utf-8"))
        stub = data.get("aborted")
        if not isinstance(stub, Mapping):
            return None
        return AbortRecord(
            int(stub["step_index"]), str(stub["case_id"]), str(stub["reason"]), stub.get("category")
        )
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        raise UnreadableReport(f"{cell.report.name}: {type(error).__name__}") from error


def common_prefix(first: Sequence[str], second: Sequence[str]) -> int:
    length = 0
    for left, right in zip(first, second, strict=False):
        if left != right:
            break
        length += 1
    return length


def compare_paths(pilot: Sequence[str], rerun: Sequence[str], budget: int) -> dict[str, Any]:
    """Common prefix, first mismatch and why the comparison ended."""
    prefix = common_prefix(pilot, rerun)
    if prefix < min(len(pilot), len(rerun)):
        limit = "mismatch"
    elif len(pilot) == len(rerun):
        limit = "budget" if len(pilot) == budget else "both_ended"
    else:
        limit = "pilot_ended" if len(pilot) < len(rerun) else "rerun_ended"
    return {
        "pilot_steps": len(pilot),
        "rerun_steps": len(rerun),
        "common_prefix": prefix,
        "first_mismatch_step": prefix if limit == "mismatch" else None,
        "limit": limit,
    }


def classify_abort(
    pilot_abort: AbortRecord,
    pilot: Sequence[str],
    rerun: Sequence[str] | None,
    rerun_abort: AbortRecord | None,
) -> tuple[str, bool | None]:
    """A pilot abort against one re-run cell: (status, path identical up to that step).

    A recurrence is decided by the key alone, as the benchmark design defines it. Everything else
    needs the path: a diverged cell did not test the position, so it stays out of the denominator.
    """
    step, case_id = pilot_abort.step_index, pilot_abort.case_id
    if rerun is None:
        same_key = rerun_abort is not None and (
            (rerun_abort.step_index, rerun_abort.case_id) == (step, case_id)
        )
        return (RECURRED, None) if same_key else (NOT_TESTED_NO_RECORD, None)
    shared = min(step, len(rerun))
    identical = list(pilot[:shared]) == list(rerun[:shared])
    if rerun_abort is not None and (rerun_abort.step_index, rerun_abort.case_id) == (step, case_id):
        return RECURRED, identical and len(rerun) >= step
    if not identical:
        return NOT_TESTED_DIVERGED, False
    if len(rerun) > step:
        return (PASSED, True) if rerun[step] == case_id else (NOT_TESTED_OTHER_CASE, True)
    if len(rerun) == step and rerun_abort is not None and rerun_abort.step_index == step:
        return NOT_TESTED_OTHER_CASE, True
    return NOT_TESTED_STOPPED, True


def summarize(tests: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Passes, recurrences and the bound. With no pass and no recurrence nothing is claimed."""
    statuses = Counter(test["status"] for test in tests)
    passes, recurrences = statuses[PASSED], statuses[RECURRED]
    return {
        "passes_m": passes,
        "recurrences": recurrences,
        "not_tested": {
            status: count for status, count in sorted(statuses.items()) if status.startswith("not")
        },
        "recurrence_upper95": (
            1 - 0.05 ** (1 / passes) if passes >= 1 and recurrences == 0 else None
        ),
    }


def input_dependence_signal(tests: Iterable[Mapping[str, Any]]) -> bool | None:
    """True on any recurrence, False only when a position was really passed, else not tested.

    A cell that diverged or never reached the position says nothing, so no pass and no recurrence
    is ``None``, not ``False``.
    """
    summary = summarize(tests)
    if summary["recurrences"]:
        return True
    return False if summary["passes_m"] else None


def design_differences(pilot: PilotDesign, benchmark: Design) -> list[str]:
    differences = [
        f"{name}: pilot {getattr(pilot, name)!r}, benchmark {getattr(benchmark, name)!r}"
        for name in SHARED_CONDITIONS
        if getattr(pilot, name) != getattr(benchmark, name)
    ]
    if pilot.execution_mode != EXECUTION_MODE:
        differences.append(f"execution_mode: pilot {pilot.execution_mode}")
    known = {arm.search for arm in pilot.arms}
    differences += [
        f"arm {arm.label}: policy {arm.search} is not a pilot arm"
        for arm in benchmark.arms
        if arm.search not in known
    ]
    return differences


def pilot_files(raw: Path, design: PilotDesign) -> dict[tuple[str, int], CellFiles]:
    """Pilot cells by (policy, seed); the arm label is not the identity."""
    returncodes: dict[str, int] = {}
    clocks = raw / "clocks.jsonl"
    for line in clocks.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        returncodes[record["run_id"]] = record["returncode"]
    cells: dict[tuple[str, int], CellFiles] = {}
    for cell in planned_cells(design):
        search = cell.arm.search
        if search is None:
            raise ComparisonError(f"pilot arm {cell.arm.label} has no search policy")
        cells[(search, cell.seed)] = CellFiles(
            cell.arm.label,
            search,
            cell.seed,
            returncodes.get(cell.run_id),
            raw / f"{cell.evidence_basename}.steps.jsonl",
            raw / f"{cell.evidence_basename}.json",
        )
    return cells


def verify_pilot_files(raw: Path, manifest: Path, cells: Iterable[CellFiles]) -> None:
    """The pilot files used here must be the ones the committed manifest pins."""
    pinned = {
        name.removeprefix("./"): digest
        for digest, name in parse_manifest(manifest.read_text(encoding="utf-8"))
    }
    for cell in cells:
        for path in (cell.steps, cell.report):
            if path is None:
                continue
            name = path.relative_to(raw).as_posix()
            if name not in pinned:
                raise ComparisonError(f"{name} is not in {manifest.name}")
            if hash_file(path) != pinned[name]:
                raise ComparisonError(f"{name} differs from {manifest.name}")


def rerun_blocks(output: Path, stage: str, design: Design) -> tuple[RerunBlock, ...]:
    """The benchmark's blocks. An unstarted block is listed with its cells marked not run."""
    search_by_label = {arm.label: arm.search or "" for arm in design.arms}
    blocks: list[RerunBlock] = []
    for block in planned_blocks(design, stage):
        directory = output / stage / block.name
        record_path = directory / BLOCK_FILE
        records: dict[str, Mapping[str, Any]] = {}
        if record_path.is_file():
            record = json.loads(record_path.read_text(encoding="utf-8"))
            records = {item["run_id"]: item for item in record["cells"]}
        head = None
        preflight = directory / "preflight.json"
        if preflight.is_file():
            facts = json.loads(preflight.read_text(encoding="utf-8")).get("preflight") or {}
            head = facts.get("checkout_head")
        cells: list[CellFiles] = []
        for cell in block.cells:
            item = records.get(cell.run_id, {})
            raw = directory / "raw"
            cells.append(
                CellFiles(
                    cell.arm.label,
                    search_by_label[cell.arm.label],
                    cell.seed,
                    item.get("returncode"),
                    raw / item["steps"] if "steps" in item else None,
                    raw / item["report"] if "report" in item else None,
                    str(item.get("state", "not-run")),
                )
            )
        blocks.append(RerunBlock(block.name, block.jobs, tuple(cells), head))
    return tuple(blocks)


def self_test_block(
    pilot: Mapping[tuple[str, int], CellFiles], seeds: Sequence[int], labels: Sequence[str]
) -> RerunBlock:
    """The pilot compared with itself, to check the comparison. Not a result."""
    cells = [
        cell
        for seed in seeds
        for cell in pilot.values()
        if cell.seed == seed and cell.label in labels
    ]
    return RerunBlock("self-test", None, tuple(cells))


def _safe_ids(path: Path | None) -> tuple[list[str] | None, str | None]:
    if path is None or not path.is_file():
        return None, "no_record"
    try:
        return read_case_ids(path), None
    except UnreadableSteps as error:
        return None, f"unreadable: {error}"


def compare(
    pilot: Mapping[tuple[str, int], CellFiles],
    blocks: Sequence[RerunBlock],
    budget: int,
    groups: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Every re-run cell against its pilot cell, then every pilot abort against those cells."""
    cell_rows: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    elsewhere: list[dict[str, Any]] = []
    tested_aborts: dict[tuple[str, int], AbortRecord] = {}
    rerun_aborts: dict[tuple[str, str, int], AbortRecord | None] = {}
    for block in blocks:
        for cell in block.cells:
            key = (cell.search, cell.seed)
            source = pilot.get(key)
            if source is None:
                cell_rows.append(
                    {
                        "block": block.name,
                        "label": cell.label,
                        "seed": cell.seed,
                        "limit": "not_a_pilot_cell",
                    }
                )
                continue
            pilot_ids, pilot_problem = _safe_ids(source.steps)
            if pilot_ids is None:
                raise ComparisonError(f"pilot cell {source.label}-s{cell.seed}: {pilot_problem}")
            rerun_ids, problem = _safe_ids(cell.steps) if cell.state == "ran" else (None, "not_run")
            report_unreadable = False
            try:
                rerun_abort = read_abort(cell)
            except UnreadableReport:
                # One damaged re-run report stays that cell's problem; the others still count.
                rerun_abort, report_unreadable = None, True
            rerun_aborts[(block.name, cell.search, cell.seed)] = rerun_abort
            row: dict[str, Any] = {
                "block": block.name,
                "jobs": block.jobs,
                "label": cell.label,
                "seed": cell.seed,
                "returncode": cell.returncode,
                "report_unreadable": report_unreadable,
            }
            if rerun_ids is None:
                row.update(
                    pilot_steps=len(pilot_ids),
                    rerun_steps=None,
                    common_prefix=None,
                    first_mismatch_step=None,
                    limit=problem,
                )
            else:
                row.update(compare_paths(pilot_ids, rerun_ids, budget))
            cell_rows.append(row)
            try:
                pilot_abort = read_abort(source)
            except UnreadableReport as error:
                raise ComparisonError(f"pilot report: {error}") from error
            if pilot_abort is None:
                continue
            tested_aborts[key] = pilot_abort
            status, identical = classify_abort(pilot_abort, pilot_ids, rerun_ids, rerun_abort)
            if report_unreadable and status in (NOT_TESTED_STOPPED, NOT_TESTED_NO_RECORD):
                # The cell stopped and its stub cannot be read: a recurrence cannot be ruled out.
                status = NOT_TESTED_REPORT
            tests.append(
                {
                    "block": block.name,
                    "jobs": block.jobs,
                    "label": cell.label,
                    "seed": cell.seed,
                    "step": pilot_abort.step_index,
                    "case_id": pilot_abort.case_id,
                    "group": (groups or {}).get(f"{source.label}-s{cell.seed}", "unknown"),
                    "status": status,
                    "prefix_identical": identical,
                    "rerun_reason": rerun_abort.reason
                    if status == RECURRED and rerun_abort
                    else None,
                    "rerun_category": (
                        rerun_abort.category if status == RECURRED and rerun_abort else None
                    ),
                }
            )
    # Same case only, at another position: for information, never a recurrence.
    for block in blocks:
        for cell in block.cells:
            rerun_abort = rerun_aborts.get((block.name, cell.search, cell.seed))
            if rerun_abort is None:
                continue
            for (search, seed), pilot_abort in tested_aborts.items():
                if rerun_abort.case_id == pilot_abort.case_id and (
                    (search, seed, pilot_abort.step_index)
                    != (cell.search, cell.seed, rerun_abort.step_index)
                ):
                    elsewhere.append(
                        {
                            "block": block.name,
                            "label": cell.label,
                            "seed": cell.seed,
                            "step": rerun_abort.step_index,
                            "case_id": rerun_abort.case_id,
                        }
                    )
    recurrences = [test for test in tests if test["status"] == RECURRED]

    def by(field: str) -> dict[str, Any]:
        values = sorted({str(test[field]) for test in tests})
        return {
            value: summarize(test for test in tests if str(test[field]) == value)
            for value in values
        }

    return {
        "cells": cell_rows,
        "abort_tests": tests,
        "summary": summarize(tests),
        "summary_by_jobs": by("jobs"),
        "summary_by_group": by("group"),
        "summary_by_abort": {
            f"{label}-s{seed}": summarize(
                test for test in tests if (test["label"], test["seed"]) == (label, seed)
            )
            for label, seed in sorted({(test["label"], test["seed"]) for test in tests})
        },
        "attempts": {
            "tests": len(tests),
            "pilot_aborts": len(tested_aborts),
            "blocks": len(blocks),
            "maximum": len(tested_aborts) * len(blocks),
        },
        "input_dependence_signal": input_dependence_signal(tests),
        "recurrences": recurrences,
        "same_case_elsewhere_information_only": elsewhere,
    }


def _bound_sentence(summary: Mapping[str, Any]) -> str:
    if summary["recurrences"]:
        return f"재발 {summary['recurrences']}건, 통과 {summary['passes_m']}건. 상한을 내지 않는다."
    if not summary["passes_m"]:
        return "통과 0건. 재발과 상한을 말하지 않는다(시험 안 됨만 적는다)."
    return (
        f"통과 m = {summary['passes_m']}, 재발 0, "
        f"다시 지날 때 재발할 확률의 95% 상한 {summary['recurrence_upper95']:.3f}."
    )


def _signal_words(signal: bool | None) -> str:
    return "시험 안 됨" if signal is None else str(signal)


def render_markdown(report: Mapping[str, Any]) -> str:
    attempts = report["attempts"]
    not_tested = sum(report["summary"]["not_tested"].values())
    lines = [
        "# 파일럿 대 재실행 경로 대조",
        "",
        f"라벨: {report['label']}. 참고 보고이고 벤치마크 판정 입력이 아니다. "
        "파일럿 판정을 소급 변경하지 않는다. 이번 abort율을 EXP-3 abort 추정에 쓰지 않는다.",
        "",
        "경로 일치는 `case_id` 순서의 일치이고 같은 결과라는 뜻이 아니다. "
        "경로가 갈라진 원인은 이 보고서로 말할 수 없다.",
        "",
        "경로 일치 구간의 값은 파일럿에서 추론 가능하다. "
        "EXP-3 동결 전에는 공통 앞부분을 파일럿 사건 위치와 결합해 재실행 사건 수를 만들지 않는다.",
        "",
        f"- 파일럿 엔진: `{report['pilot_head']}`, 재실행 엔진: {report['rerun_heads']}",
        f"- 입력 종속 신호: **{_signal_words(report['input_dependence_signal'])}** "
        "(같은 arm, seed, step, case_id의 재발. 자동 정지가 아니라 지웅 판단이다)",
        f"- 시도 {attempts['tests']}건(파일럿 abort {attempts['pilot_aborts']} × "
        f"블록 {attempts['blocks']} = 최댓값 {attempts['maximum']}), "
        f"통과 m = {report['summary']['passes_m']}, 시험 안 됨 {not_tested}",
        f"- 전체: {_bound_sentence(report['summary'])}",
    ]
    if report["summary"]["passes_m"]:
        lines.append(
            "- 상한의 범위: 그 위치를 다시 지날 때의 재발이다. 같은 case의 반복이 포함되고, "
            "입력이 확률을 조금 올리는 경우는 배제하지 못한다."
        )
    lines += ["", "## 파일럿 abort 대조", ""]
    lines += [
        "| 묶음 | 셀 | step | case | 블록 | jobs | 상태 | 앞부분 동일 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {test['group']} | {test['label']}-s{test['seed']} | {test['step']} | "
        f"`{test['case_id'][:12]}` | {test['block']} | {test['jobs']} | {test['status']} | "
        f"{test['prefix_identical']} |"
        for test in report["abort_tests"]
    ]
    lines += ["", "## 나눠 보기", ""]
    for title, key in (("jobs", "summary_by_jobs"), ("묶음", "summary_by_group")):
        for value, summary in report[key].items():
            lines.append(f"- {title} {value}: {_bound_sentence(summary)} {summary['not_tested']}")
    lines += ["", "## 재실행 셀", ""]
    lines += [
        "| 블록 | 셀 | 파일럿 step | 재실행 step | 공통 앞부분 | 첫 불일치 | 끝난 이유 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {row['block']} | {row['label']}-s{row['seed']} | {row.get('pilot_steps')} | "
        f"{row.get('rerun_steps')} | {row.get('common_prefix')} | "
        f"{row.get('first_mismatch_step')} | {row['limit']} |"
        for row in report["cells"]
    ]
    elsewhere = report["same_case_elsewhere_information_only"]
    if elsewhere:
        lines += ["", "## 정보용: 같은 case가 다른 위치에서 abort (재발 아님)", ""]
        lines += [
            f"- {item['block']} {item['label']}-s{item['seed']} step {item['step']} "
            f"`{item['case_id'][:12]}`"
            for item in elsewhere
        ]
    return "\n".join(lines) + "\n"


def _load_groups(path: Path | None) -> dict[str, str]:
    """Abort groups from the pilot's fixed-section output; a label only, never a decision."""
    if path is None:
        return {}
    aborts = json.loads(path.read_text(encoding="utf-8"))["aborts"]
    return {
        f"{item['arm']}-s{item['seed']}": GROUP_LABELS.get(item["container"], "unknown")
        for item in aborts
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--pilot-raw", type=Path, required=True)
    parser.add_argument("--pilot-design", type=Path, required=True)
    parser.add_argument("--pilot-manifest", type=Path, required=True)
    parser.add_argument("--pilot-groups", type=Path, help="pilot fixed-section.json, labels only")
    parser.add_argument("--out", type=Path, required=True, help="report directory")
    parser.add_argument("--benchmark-design", type=Path)
    parser.add_argument("--benchmark-output", type=Path)
    parser.add_argument("--stage", default="A")
    parser.add_argument(
        "--self-test-seeds", help="comma-separated: compare the pilot with itself instead"
    )
    parser.add_argument("--self-test-arms", default="R-restart,D,S-u")
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    problem = output_problem(args.out, repo_root, Path.home())
    if problem is not None:
        print(f"refusing to run: {problem}", file=sys.stderr)
        return 2
    design = load_pilot_design(args.pilot_design)
    pilot = pilot_files(args.pilot_raw, design)
    benchmark_info: dict[str, Any] = {}
    try:
        if args.self_test_seeds:
            seeds = [int(item) for item in args.self_test_seeds.split(",")]
            blocks: tuple[RerunBlock, ...] = (
                self_test_block(pilot, seeds, args.self_test_arms.split(",")),
            )
            budget = design.budget
        else:
            if args.benchmark_design is None or args.benchmark_output is None:
                parser.error("needs --benchmark-design and --benchmark-output, or a self test")
            benchmark = load_benchmark_design(args.benchmark_design)
            differences = design_differences(design, benchmark)
            if differences:
                raise ComparisonError("; ".join(differences))
            pilot_seeds = set(design.seeds)
            if not pilot_seeds & set(benchmark.seeds):
                print("no benchmark seed is a pilot seed: nothing to compare")
                return 0
            blocks = rerun_blocks(args.benchmark_output, args.stage, benchmark)
            budget = benchmark.budget
            benchmark_info = {"design_id": benchmark.design_id, "design_sha256": benchmark.sha256}
        used = {
            (cell.search, cell.seed): pilot[(cell.search, cell.seed)]
            for block in blocks
            for cell in block.cells
            if (cell.search, cell.seed) in pilot
        }
        verify_pilot_files(args.pilot_raw, args.pilot_manifest, used.values())
        result = compare(pilot, blocks, budget, _load_groups(args.pilot_groups))
    except (ComparisonError, OSError) as error:
        print(f"refusing to run: {error}", file=sys.stderr)
        return 2
    pilot_record = json.loads((args.pilot_raw / "pilot.json").read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "label": "demo run, comparison only, not an input to the benchmark decision",
        "self_test": bool(args.self_test_seeds),
        "pilot_design_sha256": design.sha256,
        "pilot_head": pilot_record["preflight"]["checkout_head"],
        "rerun_heads": sorted({str(block.checkout_head) for block in blocks}),
        "benchmark": benchmark_info,
        "blocks": [asdict(block)["name"] for block in blocks],
        **result,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / REPORT_JSON).write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.out / REPORT_MD).write_text(render_markdown(report), encoding="utf-8")
    print(
        f"cells={len(result['cells'])} abort_tests={len(result['abort_tests'])} "
        f"m={result['summary']['passes_m']} recurrences={result['summary']['recurrences']} "
        f"signal={result['input_dependence_signal']}; wrote {args.out / REPORT_MD}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

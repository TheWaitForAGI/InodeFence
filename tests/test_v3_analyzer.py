"""Concurrency benchmark analyzer, design v3 (two hosts): v3 sections 6, 7 and 11.

Per-host decisions with V10' and V7', X1 cross-host path agreement, H2' joint stop, engine and
host identity, partial input, and v2 byte identity. Every input is a synthetic tree generated
here (no benchmark or pilot raw). Steps carry sentinel oracle strings so that a test can assert
that none of them reaches the analyzer's output.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from scripts import analyze_concurrency_benchmark as analysis
from scripts import run_concurrency_benchmark as bench

REPO = Path(__file__).resolve().parents[1]
DESIGN_V2_PATH = REPO / "experiments" / "configs" / "concurrency-scaling-v2.md"
#: Sentinel values in oracle-bearing fields. None may appear in any analyzer output.
ORACLE_SENTINELS = (
    "SENTINEL-ORACLE-VERDICT-7f3a",
    "SENTINEL-FINGERPRINT-91c2",
    "SENTINEL-EFFECT-KEY-0d4e",
    "SENTINEL-VIOLATED-CONTRACT-55aa",
)
CELL_BUDGET = 3

# The v3 machine block (main dfccedc) with probe_retry_max_attempts = 1, the value the driver
# accepts, and the two engines pinned so the engine check has something to compare.
V3_BLOCK = """\
```concurrency-benchmark
design_id = concurrency-scaling-v3
target_version = 7.5.2
image_digest = sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb
budget = 2000
seeds = 8110, 8102, 8103, 8106
smoke_budget = 20
smoke_seed = 6100
vocabulary = observed-names
mutation_policy = uniform-generic-m1-state-aware-escape-hardlink-fixed-baseline-v1
arm.R-restart = unretained-seed-restart-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = 20261104
sentinel_count = 5
observer_integrity_policy = invalid-continue
execution_mode = per-case-container
campaign_watchdog_seconds = 10800
disk_stop_fraction = 0.9
memory_stop_fraction = 0.1
stop_nonzero_cells = 6
preflight_load_fraction = 0.25
cooldown_seconds = 120
retry_max_attempts = 1
v10_monotonic_seconds = 7200
v10_realtime_seconds = 7200
x1_margin = 2
x1_incomparable_cells = 2
probe_seeds = 6200, 6201, 6202, 6203, 6204, 6205, 6206, 6207
probe_budget = 1000
probe_jobs = 4
probe_retry_max_attempts = 1
hosts = HOST1, HOST2
host.HOST1.run_prefix = h1
host.HOST1.docker_engine = 29.8.0
host.HOST2.run_prefix = h2
host.HOST2.docker_engine = 29.9.3
stage.smoke = 2
stage.A = 2,4,4,2
stage.B = 4,6,6,4
stage.C = 6,8,8,6
```
"""

#: A stand-in for the driver's shared path hashes (repository-relative path -> sha256 hex).
SHARED_PATHS = {
    "scripts/local_node_tar_smoke.sh": "a" * 64,
    "src/inodefence/execution/start_gate.py": "b" * 64,
}
IMAGE_ID = "sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb"

#: (block index, run id without prefix) -> changes for that cell.
CellChanges = Mapping[tuple[int, str], Mapping[str, Any]]


def v3_design(tmp_path: Path, **changes: str) -> bench.Design:
    """The v3 block written to a temporary file (never the repository's design file)."""
    lines = []
    for line in V3_BLOCK.splitlines():
        key = line.partition("=")[0].strip()
        lines.append(f"{key} = {changes[key]}" if key in changes else line)
    path = tmp_path / "concurrency-scaling-v3.test.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bench.load_design(path)


def step(index: int, *, termination: str = "success", case: str | None = None) -> dict[str, Any]:
    return {
        "index": index,
        "case_id": case or f"case-{index}",
        "validity": "valid",
        "oracle": {"C0": False, "C1": ORACLE_SENTINELS[0], "C2": False},
        "oracle_fingerprints": [ORACLE_SENTINELS[1]],
        "feedback": {
            "trace_termination": termination,
            "new_effect_keys": [ORACLE_SENTINELS[2]],
            "feedback_eligible": True,
            "contract_violated": ORACLE_SENTINELS[3],
        },
        "trace": {"observation_failures": [], "entries": [{"type": "regular"}] * (index + 1)},
        "mutation_attempt": {"operator_id": f"op-{index}"},
    }


def _aborted(at: int, *, case: str) -> dict[str, Any]:
    return {
        "step_index": at,
        "case_id": case,
        "reason": "x.BackendError: container runtime cleanup inspect failed: timeout",
        "error_chain": [
            {"type": "BackendError", "message": "container runtime cleanup inspect failed"},
            {"type": "BackendError", "message": "container target could not start"},
        ],
        "case_shape": {"entries": 2, "entry_types": {"regular": 2}, "content_bytes": 9},
    }


def write_cell(
    raw: Path,
    design: bench.Design,
    cell: Any,
    run_id: str,
    *,
    duration: float,
    start: float = 0.0,
    clock_ratio: float = 1.09,
    abort_at: int | None = None,
    abort_case: str = "case-x",
    case_at: Mapping[int, str] | None = None,
    termination_at: Mapping[int, str] | None = None,
    verdict_at: Mapping[int, str] | None = None,
    report_extra: Mapping[str, Any] | None = None,
    abort_extra: Mapping[str, Any] | None = None,
    drop_stamp: tuple[str, str] | None = None,
    no_record: bool = False,
) -> dict[str, Any]:
    """One cell's raw files and its block-record entry."""
    raw.mkdir(parents=True, exist_ok=True)
    count = CELL_BUDGET if abort_at is None else abort_at
    records = []
    for index in range(count):
        item = step(
            index,
            termination=(termination_at or {}).get(index, "success"),
            case=(case_at or {}).get(index),
        )
        if index in (verdict_at or {}):
            item["oracle"] = {"C0": True, "C1": (verdict_at or {})[index], "C2": True}
        records.append(item)
    report: dict[str, Any] = {
        "config": {"random_seed": cell.seed, "execution_budget": CELL_BUDGET},
        "image_id": design.image_digest,
        "sentinel_set": {"count": design.sentinel_count},
        "steps": records,
        "timing": {"per_case": [{"wall_seconds": 1.5, "target_seconds": 0.3} for _ in records]},
    }
    returncode = 0
    if abort_at is not None:
        report["aborted"] = {**_aborted(abort_at, case=abort_case), **(abort_extra or {})}
        report["steps"] = None
        returncode = 1
    report.update(report_extra or {})
    if not no_record:
        (raw / f"{run_id}.json").write_text(json.dumps(report), encoding="utf-8")
        (raw / f"{run_id}.steps.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
        )
    (raw / f"{run_id}.log").write_text("PASSED\n", encoding="utf-8")
    entry: dict[str, Any] = {
        "run_id": run_id,
        "state": "ran",
        "arm": cell.arm.label,
        "seed": cell.seed,
        "budget": CELL_BUDGET,
        "returncode": returncode,
        "watchdog_killed": False,
        "started": {"realtime": start, "monotonic": start * clock_ratio, "monotonic_raw": 0.0},
        "ended": {
            "realtime": start + duration,
            "monotonic": (start + duration) * clock_ratio,
            "monotonic_raw": 0.0,
        },
        "report": f"{run_id}.json",
        "steps": f"{run_id}.steps.jsonl",
        "log": f"{run_id}.log",
    }
    if drop_stamp is not None:
        side, clock = drop_stamp
        del entry[side][clock]
    return entry


def write_stage(
    root: Path,
    design: bench.Design,
    stage: str = "A",
    *,
    host: str | None = None,
    durations: Mapping[int, float] | None = None,
    cells: CellChanges | None = None,
    blocks: tuple[int, ...] | None = None,
    engine: str | None = None,
    record_extra: Mapping[str, Any] | None = None,
    not_run: Mapping[int, tuple[str, ...]] | None = None,
    record_hook: Callable[[int, dict[str, Any]], None] | None = None,
    shared_paths: Mapping[str, str] | None = SHARED_PATHS,
    image_id: str | None = IMAGE_ID,
    preflight_hook: Callable[[int, dict[str, Any]], None] | None = None,
) -> None:
    """A stage's blocks under ``root`` (one host's output tree), every cell normal by default.

    ``host`` names a v3 host: run ids get its prefix and the block record carries ``host`` and
    ``run_prefix``, as the v3 driver writes them. ``engine`` is the preflight's Docker server;
    without it no preflight file is written. ``shared_paths`` and ``image_id`` go in the same
    ``preflight`` object (None leaves the field out).
    """
    prefix = design.hosts[host].run_prefix if host is not None else None
    order = design.stages[stage]
    for index, jobs in enumerate(order, start=1):
        if blocks is not None and index not in blocks:
            continue
        directory = root / stage / f"block-{index}-j{jobs}"
        raw = directory / "raw"
        duration = (durations or {}).get(index, 720.0 / jobs)
        entries = []
        for cell in bench.planned_cells(design, stage):
            run_id = f"{prefix}-{cell.run_id}" if prefix else cell.run_id
            if cell.run_id in (not_run or {}).get(index, ()):
                entries.append({"run_id": run_id, "state": "not-run", "decision_order": 1})
                continue
            changes = dict((cells or {}).get((index, cell.run_id), {}))
            changes.setdefault("duration", duration)
            entries.append(write_cell(raw, design, cell, run_id, **changes))
        record: dict[str, Any] = {
            "label": list(bench.LABELS),
            "design_id": design.design_id,
            "design_sha256": design.sha256,
            "stage": stage,
            "index": index,
            "jobs": jobs,
            "started": {"realtime": 0.0, "monotonic": 0.0, "monotonic_raw": 0.0},
            "ended": {"realtime": duration, "monotonic": duration * 1.09, "monotonic_raw": 0.0},
            "stopped_reason": None,
            "stop_kind": None,
            "stop_order": None,
            "finished": True,
            "residual_after_block": [],
            "cells": entries,
        }
        if host is not None:
            record["host"] = host
            record["run_prefix"] = prefix
        record.update(record_extra or {})
        if record_hook is not None:
            record_hook(index, record)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / bench.BLOCK_FILE).write_text(json.dumps(record), encoding="utf-8")
        if engine is not None:
            facts: dict[str, Any] = {"docker_server": engine}
            if image_id is not None:
                facts["image_id"] = image_id
            if shared_paths is not None:
                facts["shared_path_sha256"] = dict(shared_paths)
            # The driver's layout: the engine and hashes sit inside "preflight".
            preflight: dict[str, Any] = {
                "label": list(bench.LABELS),
                "design_sha256": design.sha256,
                "approval_ref": "test",
                "host": host,
                "preflight": facts,
                "written_at": "2026-11-11T00:00:00+00:00",
            }
            if preflight_hook is not None:
                preflight_hook(index, preflight)
            (directory / "preflight.json").write_text(json.dumps(preflight), encoding="utf-8")


def write_v2_golden_tree(root: Path, design: bench.Design, *, null_host: bool = False) -> None:
    """The v2 regression input: a smoke block and stage A with an abort, a path change, a stall.

    No host, no prefix: what the v2 driver writes. ``null_host`` adds the v3 driver's
    ``"host": null`` and ``"run_prefix": null`` to every block record, as it writes them for v2.
    """
    nulls = {"host": None, "run_prefix": None} if null_host else {}
    smoke = bench.planned_cells(design, bench.SMOKE_STAGE)
    directory = root / bench.SMOKE_STAGE / f"block-1-j{design.stages[bench.SMOKE_STAGE][0]}"
    entries = [
        write_cell(directory / "raw", design, cell, cell.run_id, duration=50.0) for cell in smoke
    ]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / bench.BLOCK_FILE).write_text(
        json.dumps(
            {
                "stage": bench.SMOKE_STAGE,
                "index": 1,
                "jobs": design.stages[bench.SMOKE_STAGE][0],
                "started": {"realtime": 0.0, "monotonic": 0.0},
                "ended": {"realtime": 60.0, "monotonic": 65.0},
                "stopped_reason": None,
                "stop_kind": None,
                "finished": True,
                "cells": entries,
                **nulls,
            }
        ),
        encoding="utf-8",
    )
    planned = bench.planned_cells(design, "A")
    first, second, third = planned[0].run_id, planned[4].run_id, planned[7].run_id
    write_stage(
        root,
        design,
        "A",
        durations={1: 360.0, 2: 200.0, 3: 190.0, 4: 370.0},
        cells={
            (2, first): {"abort_at": 2, "abort_case": "case-2"},
            (3, second): {"termination_at": {1: "timed_out"}},
            (4, third): {"case_at": {1: "case-other"}},
            (4, first): {"verdict_at": {0: "SENTINEL-ORACLE-VERDICT-7f3a-other"}},
        },
        record_extra=nulls,
    )


# ---- helpers ---------------------------------------------------------------------------------

#: sha256 of concurrency-report.json and .md for ``write_v2_golden_tree`` under design v2, taken
#: with the analyzer before the v3 changes (2182a8c). A v2 design must keep these bytes.
V2_GOLDEN_JSON_SHA256 = "45ad6fc99e9493f9f97ad9229a40a53f2446b0486a386799c77a1c3e7ad41411"
V2_GOLDEN_MD_SHA256 = "fe2120294dacb764a9b5b4f51117b2a90e41869c129c963fdd28f090b0d67f45"


@pytest.fixture
def design(tmp_path: Path) -> bench.Design:
    return v3_design(tmp_path)


def run_ids(design: bench.Design, stage: str = "A") -> list[str]:
    return [cell.run_id for cell in bench.planned_cells(design, stage)]


def all_blocks(run_id: str, **changes: Any) -> dict[tuple[int, str], dict[str, Any]]:
    """The same change in every block of stage A, so a host stays consistent with itself."""
    return {(index, run_id): dict(changes) for index in range(1, 5)}


def two_hosts(
    tmp_path: Path,
    design: bench.Design,
    host1: Mapping[str, Any] | None = None,
    host2: Mapping[str, Any] | None = None,
) -> dict[str, Path]:
    outputs = {}
    for host, changes in (("HOST1", host1 or {}), ("HOST2", host2 or {})):
        root = tmp_path / host.lower()
        options: dict[str, Any] = {"engine": design.engine_for(host), **changes}
        write_stage(root, design, "A", host=host, **options)
        outputs[host] = root
    return outputs


def analyze(design: bench.Design, outputs: Mapping[str, Path], **kwargs: Any) -> dict[str, Any]:
    return analysis.analyze_v3(design, outputs, **kwargs)["combined"]


def host_rules(combined: Mapping[str, Any], host: str) -> list[str]:
    return [item["rule"] for item in combined["decisions"][host]["halts"]]


def violation_rules(combined: Mapping[str, Any], host: str, *, ref: bool = False) -> set[str]:
    verdict = combined["decisions"][host]["stages"]["A"]
    return {item["rule"] for item in verdict["ref_violations" if ref else "violations"]}


# ---- v2 stays byte-identical ---------------------------------------------------------------


@pytest.mark.parametrize("null_host", [False, True])
def test_v2_design_output_is_byte_identical_to_the_analyzer_before_v3(
    tmp_path: Path, null_host: bool
) -> None:
    design = bench.load_design(DESIGN_V2_PATH)
    assert not design.is_v3
    # With and without the v3 driver's "host": null, "run_prefix": null in the block records.
    write_v2_golden_tree(tmp_path, design, null_host=null_host)
    assert analysis.main(["--design", str(DESIGN_V2_PATH), "--output", str(tmp_path)]) == 0
    report_json = (tmp_path / bench.REPORT_JSON).read_bytes()
    report_md = (tmp_path / analysis.REPORT_MD).read_bytes()
    assert hashlib.sha256(report_json).hexdigest() == V2_GOLDEN_JSON_SHA256
    assert hashlib.sha256(report_md).hexdigest() == V2_GOLDEN_MD_SHA256
    # The fixture's verdict difference and timed_out step make the v2 rules do some work.
    decision = json.loads(report_json)["decision"]
    assert {item["rule"] for item in decision["stages"]["A"]["violations"]} == {"V7"}
    assert "V7'" not in report_json.decode() and "infra_reexecutions" not in report_json.decode()


def test_v2_design_refuses_the_v3_flags(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        analysis.main(["--design", str(DESIGN_V2_PATH), "--host-output", f"HOST1={tmp_path}"])
    with pytest.raises(SystemExit):
        analysis.main(["--design", str(DESIGN_V2_PATH), "--output", str(tmp_path), "--partial"])


# ---- per host, never pooled ----------------------------------------------------------------


def test_clean_hosts_are_decided_each_and_x1_does_not_fire(
    design: bench.Design, tmp_path: Path
) -> None:
    combined = analyze(design, two_hosts(tmp_path, design))
    for host in ("HOST1", "HOST2"):
        assert combined["decisions"][host]["status"] == "provisional"
        assert combined["decisions"][host]["selected_jobs"] == 4
        assert host_rules(combined, host) == []
    assert combined["selected_jobs"] == {"HOST1": 4, "HOST2": 4}
    assert combined["common_jobs_if_needed"] == 4
    assert combined["x1"]["status"] == "not fired"
    assert combined["x1"]["jobs_exclusion"] is False
    assert combined["x1"]["inputs"]["m_x"] == 0
    assert combined["h2_joint"] == {"fired": False, "source_hosts": []}


def test_one_hosts_exclusion_does_not_reach_the_other(design: bench.Design, tmp_path: Path) -> None:
    first = run_ids(design)[0]
    watchdog = {(2, first): {"duration": 180.0}}
    outputs = two_hosts(tmp_path, design, host2={"cells": watchdog})
    record = outputs["HOST2"] / "A" / "block-2-j4" / bench.BLOCK_FILE
    data = json.loads(record.read_text(encoding="utf-8"))
    data["cells"][0]["watchdog_killed"] = True
    record.write_text(json.dumps(data), encoding="utf-8")
    combined = analyze(design, outputs)
    assert "V1" in violation_rules(combined, "HOST2")
    assert combined["decisions"]["HOST2"]["selected_jobs"] == 2
    assert combined["decisions"]["HOST1"]["selected_jobs"] == 4
    assert combined["common_jobs_if_needed"] == 2


# ---- V10' (both clocks) --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "clock", "fires"),
    [
        # Monotonic over, real time under: v2's V10 would fire too.
        ({"duration": 6700.0, "clock_ratio": 1.09}, "monotonic", True),
        ({"duration": 6600.0, "clock_ratio": 1.09}, "monotonic", False),
        # Real time over, monotonic under (a slow monotonic clock): only V10' sees it.
        ({"duration": 7300.0, "clock_ratio": 0.97}, "realtime", True),
        ({"duration": 7150.0, "clock_ratio": 0.97}, "realtime", False),
    ],
)
def test_v10_prime_takes_the_stricter_clock(
    design: bench.Design, tmp_path: Path, changes: dict[str, float], clock: str, fires: bool
) -> None:
    first = run_ids(design)[0]
    combined = analyze(design, two_hosts(tmp_path, design, host2={"cells": {(2, first): changes}}))
    verdict = combined["decisions"]["HOST2"]["stages"]["A"]
    found = [item for item in verdict["violations"] if item["rule"] == "V10'"]
    assert bool(found) is fires
    if fires:
        assert found[0]["detail"]["clock"] == clock
    assert "V10" not in violation_rules(combined, "HOST2")
    assert "V10'" not in violation_rules(combined, "HOST1")


@pytest.mark.parametrize(("dropped", "fires"), [(("ended", "monotonic"), True), (None, False)])
def test_a_missing_cell_stamp_is_not_measurable_and_excludes(
    design: bench.Design, tmp_path: Path, dropped: tuple[str, str] | None, fires: bool
) -> None:
    first = run_ids(design)[0]
    cells = {(2, first): {"drop_stamp": dropped}}
    combined = analyze(design, two_hosts(tmp_path, design, host2={"cells": cells}))
    verdict = combined["decisions"]["HOST2"]["stages"]["A"]
    details = [item["detail"] for item in verdict["violations"] if item["rule"] == "V10'"]
    assert bool(details) is fires
    if fires:
        assert details == [{"arm": "R-restart", "clock": "monotonic", "unmeasurable_cells": 1}]


@pytest.mark.parametrize(("dropped", "incomplete"), [(True, True), (False, False)])
def test_a_block_record_without_stamps_is_incomplete(
    design: bench.Design, tmp_path: Path, dropped: bool, incomplete: bool
) -> None:
    def hook(index: int, record: dict[str, Any]) -> None:
        if dropped and index == 3:
            del record["ended"]["realtime"]

    combined = analyze(design, two_hosts(tmp_path, design, host2={"record_hook": hook}))
    assert ("incomplete-block" in host_rules(combined, "HOST2")) is incomplete
    assert host_rules(combined, "HOST1") == []


# ---- V7' (timed-out steps plus infrastructure re-executions) --------------------------------


def _arm(steps: int, timed_out: int, reexecutions: int) -> dict[str, Any]:
    return {
        "campaigns": 8,
        "aborts": 0,
        "steps": steps,
        "timed_out": timed_out,
        "ineligible_steps": 0,
        "target_seconds_p999": 0.3,
        "cell_monotonic_max": 100.0,
        "cell_real_max": 100.0,
        "cell_clock_unmeasured": {"monotonic": 0, "realtime": 0},
        "infra_reexecutions": reexecutions,
        "infra_reexecutions_unmeasured": 0,
        "cells_with_reexecution": 1 if reexecutions else 0,
        "v7_numerator": timed_out + reexecutions,
    }


def _level(arm: dict[str, Any]) -> dict[str, Any]:
    return {
        "watchdog_kills": 0,
        "other_abnormal": 0,
        "aborts": 0,
        "campaigns": 24,
        "stopped": [],
        "timed_out": arm["timed_out"],
        "infra_reexecutions": arm["infra_reexecutions"],
        "v7_numerator": arm["v7_numerator"],
        "arms": {"D": arm},
    }


RULES = analysis.V3Rules(7200.0, 7200.0)


def test_v7_prime_absolute_adds_reexecutions_to_timed_out() -> None:
    # 2 in 2000 steps is 1.0 per 1000, not over; one re-execution makes it 1.5.
    under = _level(_arm(2000, 2, 0))
    over = _level(_arm(2000, 2, 1))
    assert {v["rule"] for v in analysis.absolute_violations(under, v3=RULES)} == set()
    assert {v["rule"] for v in analysis.absolute_violations(over, v3=RULES)} == {"V7'"}
    # With no re-execution V7' judges what v2's V7 judges.
    for timed_out in (2, 3):
        level = _level(_arm(2000, timed_out, 0))
        v2 = {v["rule"] for v in analysis.absolute_violations(level)} == {"V7"}
        v3 = {v["rule"] for v in analysis.absolute_violations(level, v3=RULES)} == {"V7'"}
        assert v2 is v3


def test_v7_prime_relative_uses_the_same_table() -> None:
    ref = _level(_arm(100000, 0, 0))
    under = _level(_arm(100000, 4, 0))
    over = _level(_arm(100000, 4, 1))

    def rules(level: dict[str, Any], v3: analysis.V3Rules | None) -> set[str]:
        found = analysis.level_violations(
            level, ref, floor=0, block_m=[0, 0], one_sided_cells=0, v3=v3
        )
        return {item["rule"] for item in found}

    # A(ref) = 0 needs 5: four timed-out steps do not, four plus one re-execution do.
    assert rules(under, RULES) == set()
    assert rules(over, RULES) == {"V7'"}
    assert rules(under, None) == set()
    assert rules(_level(_arm(100000, 5, 0)), None) == {"V7"}
    assert rules(_level(_arm(100000, 5, 0)), RULES) == {"V7'"}


@pytest.mark.parametrize(
    ("report_extra", "abort_extra", "abort_at", "count"),
    [
        ({}, None, None, 0),
        (
            {"infra_reexecutions": [{"action": "reexecuted"}, {"action": "reexecuted"}]},
            None,
            None,
            2,
        ),
        ({"infra_reexecutions": [{}, {}, {}, {}]}, {"infra_reexecution_count": 3}, 2, 3),
        ({"infra_reexecutions": "broken"}, None, None, None),
    ],
)
def test_infra_reexecution_count_sources(
    design: bench.Design,
    tmp_path: Path,
    report_extra: dict[str, Any],
    abort_extra: dict[str, Any] | None,
    abort_at: int | None,
    count: int | None,
) -> None:
    cell = bench.planned_cells(design, "A")[0]
    entry = write_cell(
        tmp_path,
        design,
        cell,
        "h1-x",
        duration=10.0,
        report_extra=report_extra,
        abort_extra=abort_extra,
        abort_at=abort_at,
    )
    summary = analysis.summarize_cell(entry, tmp_path, design).summary
    assert summary["infra_reexecutions"] == count
    assert summary["infra_reexecutions_malformed"] is (count is None)


@pytest.mark.parametrize(("reexecutions", "fires"), [(1, True), (0, False)])
def test_v7_prime_end_to_end_and_reported_per_arm_and_level(
    design: bench.Design, tmp_path: Path, reexecutions: int, fires: bool
) -> None:
    first = run_ids(design)[0]
    events = [{"action": "reexecuted"}] * reexecutions
    cells = {(2, first): {"report_extra": {"infra_reexecutions": events}}}
    result = analysis.analyze_v3(
        design, two_hosts(tmp_path, design, host2={"cells": cells}), partial=False
    )
    combined = result["combined"]
    assert ("V7'" in violation_rules(combined, "HOST2")) is fires
    assert "V7" not in violation_rules(combined, "HOST2")
    level = result["hosts"]["HOST2"]["stages"]["A"]["levels"]["4"]
    assert level["timed_out"] == 0
    assert level["infra_reexecutions"] == reexecutions
    assert level["v7_numerator"] == reexecutions
    assert level["arms"]["R-restart"]["infra_reexecutions"] == reexecutions
    assert level["arms"]["R-restart"]["v7_numerator"] == reexecutions
    infra = combined["infra_reexecutions"]["HOST2"]
    assert infra["total"] == reexecutions
    assert infra["cells"][f"A/2/h2-{first}"] == reexecutions
    # Re-executions are not aborts: V3 and V4 do not count them.
    assert violation_rules(combined, "HOST2") == ({"V7'"} if fires else set())


@pytest.mark.parametrize(("broken", "fires"), [(True, True), (False, False)])
def test_an_unreadable_reexecution_count_is_not_measurable(
    design: bench.Design, tmp_path: Path, broken: bool, fires: bool
) -> None:
    first = run_ids(design)[0]
    extra = {"infra_reexecutions": "broken"} if broken else {}
    cells = {(2, first): {"report_extra": extra}}
    combined = analyze(design, two_hosts(tmp_path, design, host2={"cells": cells}))
    verdict = combined["decisions"]["HOST2"]["stages"]["A"]
    details = [item["detail"] for item in verdict["violations"] if item["rule"] == "V7'"]
    assert bool(details) is fires
    if fires:
        assert details == [{"arm": "R-restart", "unmeasurable_cells": 1}]


def test_v9_reports_differences_in_reexecuted_cells_without_judging(
    design: bench.Design, tmp_path: Path
) -> None:
    ids = run_ids(design)
    cells = {
        (2, ids[0]): {
            "case_at": {1: "case-other"},
            "report_extra": {"infra_reexecutions": [{"action": "reexecuted"}]},
        },
        (2, ids[1]): {"case_at": {1: "case-other"}},
    }
    result = analysis.analyze_v3(design, two_hosts(tmp_path, design, host2={"cells": cells}))
    block = result["hosts"]["HOST2"]["stages"]["A"]["blocks"][1]
    assert block["determinism"]["m"] == 2
    assert block["determinism"]["differing_cells_with_reexecution"] == 1
    level = result["hosts"]["HOST2"]["stages"]["A"]["levels"]["4"]
    assert level["differing_cells_with_reexecution"] == 1
    # The V9 judgement is the v2 one: m - F = 2 excludes, with or without the re-execution.
    assert "V9" in violation_rules(result["combined"], "HOST2")


# ---- X1 ------------------------------------------------------------------------------------


@pytest.mark.parametrize(("changed", "status"), [(2, "fired"), (1, "not fired")])
def test_x1_first_clause_boundary(
    design: bench.Design, tmp_path: Path, changed: int, status: str
) -> None:
    cells: dict[tuple[int, str], dict[str, Any]] = {}
    for run_id in run_ids(design)[:changed]:
        cells.update(all_blocks(run_id, case_at={1: "case-host2"}))
    combined = analyze(design, two_hosts(tmp_path, design, host2={"cells": cells}))
    x1 = combined["x1"]
    assert x1["status"] == status
    assert x1["inputs"]["m_x"] == changed
    assert x1["inputs"]["floors"] == {"HOST1": 0, "HOST2": 0}
    assert x1["clauses"]["excess_over_floor"] is (changed >= 2)
    # X1 is not a jobs exclusion: both hosts keep their own selection.
    assert combined["selected_jobs"] == {"HOST1": 4, "HOST2": 4}


@pytest.mark.parametrize(("floor", "status"), [(1, "not fired"), (0, "fired")])
def test_x1_subtracts_the_larger_host_floor(
    design: bench.Design, tmp_path: Path, floor: int, status: str
) -> None:
    ids = run_ids(design)
    host2: dict[tuple[int, str], dict[str, Any]] = {}
    for run_id in ids[:2]:
        host2.update(all_blocks(run_id, case_at={1: "case-host2"}))
    host1 = {(4, run_id): {"case_at": {2: "case-late"}} for run_id in ids[5 : 5 + floor]}
    combined = analyze(
        design, two_hosts(tmp_path, design, host1={"cells": host1}, host2={"cells": host2})
    )
    x1 = combined["x1"]
    assert x1["inputs"]["floors"]["HOST1"] == floor
    assert x1["inputs"]["excess"] == 2 - floor
    assert x1["status"] == status


@pytest.mark.parametrize(("stalled", "fires"), [(2, True), (1, False)])
def test_x1_second_clause_one_sided_congestion(
    design: bench.Design, tmp_path: Path, stalled: int, fires: bool
) -> None:
    ids = run_ids(design)
    host2: dict[tuple[int, str], dict[str, Any]] = {}
    for run_id in ids[:stalled]:
        host2.update(all_blocks(run_id, termination_at={1: "timed_out"}))
    # HOST1's floor of 1 keeps the first clause below its margin (stalled - 1 < 2).
    host1 = {(4, ids[6]): {"case_at": {2: "case-late"}}}
    combined = analyze(
        design, two_hosts(tmp_path, design, host1={"cells": host1}, host2={"cells": host2})
    )
    x1 = combined["x1"]
    assert x1["clauses"]["excess_over_floor"] is False
    assert x1["clauses"]["one_sided_congestion"] is fires
    assert x1["status"] == ("fired" if fires else "not fired")


@pytest.mark.parametrize(("lost", "status"), [(2, "fired"), (1, "not fired")])
def test_x1_third_clause_incomparable_cells(
    design: bench.Design, tmp_path: Path, lost: int, status: str
) -> None:
    not_run = {1: tuple(run_ids(design)[:lost])}
    combined = analyze(design, two_hosts(tmp_path, design, host2={"not_run": not_run}))
    x1 = combined["x1"]
    assert x1["inputs"]["incomparable_cells"] == lost
    assert x1["inputs"]["incomparable_missing_on"] == [0, lost]
    assert x1["clauses"]["incomparable"] is (lost >= 2)
    assert x1["one_incomparable_reported"] is (lost == 1)
    assert x1["status"] == status


@pytest.mark.parametrize(("measured", "status"), [(False, "not evaluated"), (True, "not fired")])
def test_x1_without_a_floor_is_not_evaluated(
    design: bench.Design, tmp_path: Path, measured: bool, status: str
) -> None:
    host1 = {} if measured else {"blocks": (1, 2, 3)}
    combined = analyze(design, two_hosts(tmp_path, design, host1=host1))
    assert combined["x1"]["status"] == status
    assert bool(combined["x1"]["reasons_not_evaluated"]) is not measured


def test_x1_last_block_pair_is_reported_only(design: bench.Design, tmp_path: Path) -> None:
    host2 = {(4, run_id): {"case_at": {1: "case-host2"}} for run_id in run_ids(design)[:3]}
    combined = analyze(design, two_hosts(tmp_path, design, host2={"cells": host2}))
    assert combined["x1"]["report_only_last_block"]["m_x"] == 3
    assert combined["x1"]["inputs"]["m_x"] == 0
    assert combined["x1"]["status"] == "not fired"


def test_x1_reports_differences_in_reexecuted_cells(design: bench.Design, tmp_path: Path) -> None:
    ids = run_ids(design)
    host2: dict[tuple[int, str], dict[str, Any]] = {}
    host2.update(all_blocks(ids[0], case_at={1: "case-host2"}))
    host2.update(
        all_blocks(
            ids[1],
            case_at={1: "case-host2"},
            report_extra={"infra_reexecutions": [{"action": "reexecuted"}]},
        )
    )
    x1 = analyze(design, two_hosts(tmp_path, design, host2={"cells": host2}))["x1"]
    assert x1["inputs"]["m_x"] == 2
    assert x1["inputs"]["differing_cells_with_reexecution"] == 1


# ---- H2' -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("blocks", "joint"), [((1, 2), True), ((1,), False)])
def test_h2_on_one_host_halts_both(
    design: bench.Design, tmp_path: Path, blocks: tuple[int, ...], joint: bool
) -> None:
    first = run_ids(design)[0]
    cells = {(index, first): {"abort_at": 2, "abort_case": "case-2"} for index in blocks}
    combined = analyze(design, two_hosts(tmp_path, design, host1={"cells": cells}))
    assert ("H2" in host_rules(combined, "HOST1")) is joint
    assert ("H2'" in host_rules(combined, "HOST2")) is joint
    assert combined["h2_joint"]["fired"] is joint
    if joint:
        for host in ("HOST1", "HOST2"):
            assert combined["decisions"][host]["status"] == "halted"
            assert combined["decisions"][host]["selected_jobs"] is None
            assert combined["decisions"][host]["fallback_jobs"] is None
    else:
        assert combined["decisions"]["HOST2"]["selected_jobs"] == 4


# ---- engine and host identity ----------------------------------------------------------------


def _on_block(index: int, change: Callable[[dict[str, Any]], None]) -> Any:
    def hook(at: int, value: dict[str, Any]) -> None:
        if at == index:
            change(value)

    return hook


def _drop_fact(key: str) -> Callable[[dict[str, Any]], None]:
    return lambda preflight: preflight["preflight"].pop(key)


def _other_hash(preflight: dict[str, Any]) -> None:
    preflight["preflight"]["shared_path_sha256"]["scripts/local_node_tar_smoke.sh"] = "c" * 64


def _set(key: str, value: Any) -> Callable[[dict[str, Any]], None]:
    return lambda record: record.__setitem__(key, value)


EXTERNAL_CASES = [
    ("engine-mismatch", {"engine": "29.8.0"}),
    ("engine-unverified", {"preflight_hook": _on_block(2, _drop_fact("docker_server"))}),
    ("host-mismatch", {"record_hook": _on_block(2, _set("host", "HOST1"))}),
    ("host-mismatch", {"preflight_hook": _on_block(2, _set("host", "HOST1"))}),
    ("shared-path-mismatch", {"preflight_hook": _on_block(3, _other_hash)}),
    ("shared-path-unverified", {"preflight_hook": _on_block(3, _drop_fact("shared_path_sha256"))}),
    (None, {}),
]


@pytest.mark.parametrize(("rule", "host2"), EXTERNAL_CASES)
def test_record_problems_void_the_stage_as_an_external_stop(
    design: bench.Design, tmp_path: Path, rule: str | None, host2: dict[str, Any]
) -> None:
    combined = analyze(design, two_hosts(tmp_path, design, host2=host2))
    decision = combined["decisions"]["HOST2"]
    verdict = decision["stages"]["A"]
    # Never a halt and never an exclusion: the stage's measurement is void (v2 section 6.3).
    assert decision["halts"] == []
    assert verdict["violations"] == [] and verdict["ref_violations"] == []
    assert [item["rule"] for item in verdict["external_problems"]] == ([rule] if rule else [])
    if rule:
        assert decision["stage_invalid"] == "A" and verdict["stage_invalid"] is True
        assert decision["status"] == "provisional"
        assert decision["selected_jobs"] is None and decision["fallback_jobs"] is None
        assert verdict["passed"] is False
        assert combined["x1"]["status"] == "not evaluated"
    else:
        assert decision["stage_invalid"] is None
        assert decision["selected_jobs"] == 4
        assert combined["x1"]["status"] == "not fired"
    assert combined["decisions"]["HOST1"]["selected_jobs"] == 4
    assert combined["stage_invalid"]["HOST1"] is None


def test_an_unpinned_design_engine_never_matches(tmp_path: Path) -> None:
    design = v3_design(tmp_path, **{"host.HOST2.docker_engine": "TBD-PREFLIGHT"})
    outputs = two_hosts(tmp_path, design, host2={"engine": "TBD-PREFLIGHT"})
    combined = analyze(design, outputs)
    problems = combined["decisions"]["HOST2"]["stages"]["A"]["external_problems"]
    assert [item["rule"] for item in problems] == ["engine-mismatch"]


def _voided_stage_inputs(design: bench.Design) -> dict[tuple[int, str], dict[str, Any]]:
    """Inputs that trip H1 (8/24 aborts at jobs 2), H3 (F = 3) and V10' at jobs 4."""
    ids = run_ids(design)
    cells: dict[tuple[int, str], dict[str, Any]] = {}
    for run_id in ids[:4]:
        cells[(1, run_id)] = {"abort_at": 2, "abort_case": "case-b1"}
    for run_id in ids[4:8]:
        cells[(4, run_id)] = {"abort_at": 2, "abort_case": "case-b4"}
    for run_id in ids[8:11]:
        cells[(4, run_id)] = {"case_at": {1: "case-late"}}
    cells[(2, ids[11])] = {"duration": 7300.0, "clock_ratio": 0.97}
    return cells


@pytest.mark.parametrize(("engine", "voided"), [("29.8.0", True), ("29.9.3", False)])
def test_no_rule_reads_a_voided_stage(
    design: bench.Design, tmp_path: Path, engine: str, voided: bool
) -> None:
    host2 = {"cells": _voided_stage_inputs(design), "engine": engine}
    combined = analyze(design, two_hosts(tmp_path, design, host2=host2))
    decision = combined["decisions"]["HOST2"]
    verdict = decision["stages"]["A"]
    if voided:
        assert decision["halts"] == []
        assert verdict["violations"] == [] and verdict["ref_violations"] == []
        assert decision["stage_invalid"] == "A"
    else:
        assert {"H1", "H3"} <= set(host_rules(combined, "HOST2"))
        assert "V10'" in {item["rule"] for item in verdict["violations"]}
        assert decision["stage_invalid"] is None


@pytest.mark.parametrize(("engine", "voided"), [("29.8.0", True), ("29.9.3", False)])
def test_a_voided_later_stage_keeps_the_passed_level_and_skips_the_reference_recheck(
    design: bench.Design, tmp_path: Path, engine: str, voided: bool
) -> None:
    outputs = two_hosts(tmp_path, design)

    def watchdog(record: dict[str, Any]) -> None:
        record["cells"][0]["watchdog_killed"] = True

    write_stage(
        outputs["HOST2"],
        design,
        "B",
        host="HOST2",
        engine=engine,
        record_hook=_on_block(1, watchdog),
    )
    combined = analyze(design, outputs)
    decision = combined["decisions"]["HOST2"]
    verdict = decision["stages"]["B"]
    if voided:
        assert decision["stage_invalid"] == "B"
        assert decision["status"] == "provisional"
        assert decision["selected_jobs"] == 4
        assert verdict["ref_violations"] == [] and verdict["ref_cancelled"] is False
    else:
        assert verdict["ref_cancelled"] is True
        assert "V1" in {item["rule"] for item in verdict["ref_violations"]}
        assert decision["status"] == "selected" and decision["selected_jobs"] == 2


@pytest.mark.parametrize(("engine", "voided"), [("29.8.0", True), ("29.9.3", False)])
def test_a_smoke_record_problem_voids_the_first_measured_stage(
    design: bench.Design, tmp_path: Path, engine: str, voided: bool
) -> None:
    outputs = two_hosts(tmp_path, design)
    write_stage(outputs["HOST2"], design, bench.SMOKE_STAGE, host="HOST2", engine=engine)
    combined = analyze(design, outputs)
    decision = combined["decisions"]["HOST2"]
    assert (decision["stage_invalid"] == "A") is voided
    blocks = [block for item in decision["external_problems"] for block in item["blocks"]]
    assert blocks == (["smoke/block-1-j2"] if voided else [])


def _other_paths(preflight: dict[str, Any]) -> None:
    preflight["preflight"]["shared_path_sha256"] = {**SHARED_PATHS, "scripts/extra.py": "d" * 64}


@pytest.mark.parametrize(
    ("host2", "field", "state"),
    [
        (
            {"shared_paths": {**SHARED_PATHS, "scripts/local_node_tar_smoke.sh": "e" * 64}},
            "shared_path_cross_host",
            "mismatch",
        ),
        (
            {"preflight_hook": lambda _index, preflight: _other_paths(preflight)},
            "shared_path_cross_host",
            "mismatch",
        ),
        ({}, "shared_path_cross_host", "match"),
        ({"image_id": "sha256:" + "f" * 64}, "image_id_cross_host", "mismatch"),
        ({"image_id": None}, "image_id_cross_host", "unverified"),
        ({}, "image_id_cross_host", "match"),
    ],
)
def test_cross_host_paths_and_image_gate_x1(
    design: bench.Design, tmp_path: Path, host2: dict[str, Any], field: str, state: str
) -> None:
    combined = analyze(design, two_hosts(tmp_path, design, host2=host2))
    assert combined[field] == state
    # A cross-host difference stops no host: each host is consistent with itself.
    assert combined["selected_jobs"] == {"HOST1": 4, "HOST2": 4}
    if state == "match":
        assert combined["x1"]["status"] == "not fired"
    else:
        assert combined["x1"]["status"] == "not evaluated"
        reasons = combined["x1"]["reasons_not_evaluated"]
        assert any(reason.endswith(f"across hosts is {state}") for reason in reasons)


def test_x1_consequence_covers_not_evaluated(design: bench.Design, tmp_path: Path) -> None:
    combined = analyze(design, two_hosts(tmp_path, design))
    assert (
        "X1이 not evaluated이면 본실험 합산 처리는 X1 발동과 같이 한다"
        in (combined["x1"]["consequence"])
    )


@pytest.mark.parametrize(("state", "fires"), [("not-run", False), ("ran", True)])
def test_a_cell_that_never_started_is_not_a_missing_stamp(
    design: bench.Design, tmp_path: Path, state: str, fires: bool
) -> None:
    first = run_ids(design)[0]
    if state == "not-run":
        host2: dict[str, Any] = {"not_run": {2: (first,)}}
    else:
        host2 = {"cells": {(2, first): {"drop_stamp": ("started", "realtime")}}}
    combined = analyze(design, two_hosts(tmp_path, design, host2=host2))
    assert ("V10'" in violation_rules(combined, "HOST2")) is fires


# ---- partial input and the CLI ---------------------------------------------------------------


def _cli(design_path: Path, outputs: Mapping[str, Path], combined: Path, *extra: str) -> int:
    argv = ["--design", str(design_path), "--combined-output", str(combined), *extra]
    for host, directory in outputs.items():
        argv += ["--host-output", f"{host}={directory}"]
    return analysis.main(argv)


def test_cli_refuses_a_missing_host_without_partial(design: bench.Design, tmp_path: Path) -> None:
    outputs = two_hosts(tmp_path, design)
    design_path = tmp_path / "concurrency-scaling-v3.test.md"
    with pytest.raises(SystemExit):
        _cli(design_path, {"HOST1": outputs["HOST1"]}, tmp_path / "combined")
    assert not (outputs["HOST1"] / bench.REPORT_JSON).exists()


@pytest.mark.parametrize("partial", [True, False])
def test_cli_partial_keeps_every_host_pending_and_x1_not_evaluated(
    design: bench.Design, tmp_path: Path, partial: bool
) -> None:
    outputs = two_hosts(tmp_path, design)
    design_path = tmp_path / "concurrency-scaling-v3.test.md"
    given = {"HOST1": outputs["HOST1"]} if partial else outputs
    flags = ("--partial",) if partial else ()
    assert _cli(design_path, given, tmp_path / "combined", *flags) == 0
    combined = json.loads(
        (tmp_path / "combined" / analysis.REPORT_V3_JSON).read_text(encoding="utf-8")
    )
    assert combined["partial"] is partial
    if partial:
        assert combined["missing_hosts"] == ["HOST2"]
        for host in ("HOST1", "HOST2"):
            assert combined["decisions"][host]["status"] == "pending"
            assert combined["decisions"][host]["selected_jobs"] is None
        assert combined["x1"]["status"] == "not evaluated"
        # No per-host report: the driver's stage gate cannot pass a host on partial input.
        assert not (outputs["HOST1"] / bench.REPORT_JSON).exists()
    else:
        assert combined["selected_jobs"] == {"HOST1": 4, "HOST2": 4}
        assert combined["x1"]["status"] == "not fired"
        for host in ("HOST1", "HOST2"):
            report = json.loads((outputs[host] / bench.REPORT_JSON).read_text(encoding="utf-8"))
            assert report["host"] == host
            assert report["design_sha256"] == design.sha256


def test_partial_input_keeps_a_joint_stop(design: bench.Design, tmp_path: Path) -> None:
    first = run_ids(design)[0]
    cells = {(index, first): {"abort_at": 2, "abort_case": "case-2"} for index in (1, 2)}
    outputs = two_hosts(tmp_path, design, host1={"cells": cells})
    combined = analyze(design, {"HOST1": outputs["HOST1"]}, partial=True)
    assert combined["decisions"]["HOST1"]["status"] == "halted"
    assert combined["decisions"]["HOST2"]["status"] == "halted"
    assert host_rules(combined, "HOST2") == ["H2'"]


def test_analyze_v3_refuses_unknown_hosts(design: bench.Design, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not in the design"):
        analysis.analyze_v3(design, {"HOST3": tmp_path})


# ---- seal ----------------------------------------------------------------------------------


def test_no_oracle_value_leaves_the_v3_analyzer(
    design: bench.Design, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = run_ids(design)
    host2: dict[tuple[int, str], dict[str, Any]] = {}
    host2.update(all_blocks(ids[0], case_at={1: "case-host2"}))
    host2.update(all_blocks(ids[1], verdict_at={0: "SENTINEL-ORACLE-VERDICT-7f3a-host2"}))
    host2[(2, ids[2])] = {"abort_at": 1, "report_extra": {"infra_reexecutions": [{"x": 1}]}}
    outputs = two_hosts(tmp_path, design, host2={"cells": host2})
    design_path = tmp_path / "concurrency-scaling-v3.test.md"
    assert _cli(design_path, outputs, tmp_path / "combined") == 0
    texts = [capsys.readouterr().out]
    for directory, names in (
        (outputs["HOST1"], (bench.REPORT_JSON, analysis.REPORT_MD)),
        (outputs["HOST2"], (bench.REPORT_JSON, analysis.REPORT_MD)),
        (tmp_path / "combined", (analysis.REPORT_V3_JSON, analysis.REPORT_V3_MD)),
    ):
        texts += [(directory / name).read_text(encoding="utf-8") for name in names]
    joined = "\n".join(texts)
    for sentinel in ORACLE_SENTINELS:
        assert sentinel not in joined
    for field in ('"oracle"', '"C1"', "oracle_fingerprints", "contract_violated"):
        assert field not in joined
    # The verdict-only difference still counted, by its hash, without its value.
    combined = json.loads(texts[-2])
    assert combined["x1"]["inputs"]["m_x"] == 2

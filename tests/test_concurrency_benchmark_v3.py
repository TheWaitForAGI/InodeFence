"""Design v3 (two hosts) parsing: concurrency-scaling-v3.md section 2 and section 9.

The block below is the v3 file's machine block (main dfccedc) with
``probe_retry_max_attempts`` set to 1, the value this driver accepts (the
design correction goes through its own documentation PR).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import run_concurrency_benchmark as bench

from inodefence.execution import start_gate

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
host.HOST1.docker_engine = TBD-PREFLIGHT
host.HOST2.run_prefix = h2
host.HOST2.docker_engine = TBD-PREFLIGHT
stage.smoke = 2
stage.A = 2,4,4,2
stage.B = 4,6,6,4
stage.C = 6,8,8,6
```
"""


def text(**changes: str | None) -> str:
    """The v3 block with keys replaced or added (``None`` removes a key)."""
    lines = []
    done: set[str] = set()
    for line in V3_BLOCK.splitlines():
        key = line.partition("=")[0].strip()
        if line == "```":
            # Keys the block does not have yet go in just before the closing fence.
            lines += [f"{k} = {v}" for k, v in changes.items() if k not in done and v is not None]
        if key in changes:
            done.add(key)
            if changes[key] is not None:
                lines.append(f"{key} = {changes[key]}")
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def test_v3_block_parses_with_every_new_field() -> None:
    design = bench.parse_design(V3_BLOCK)
    assert design.is_v3
    assert design.hosts == {
        "HOST1": bench.HostSpec("h1", "TBD-PREFLIGHT"),
        "HOST2": bench.HostSpec("h2", "TBD-PREFLIGHT"),
    }
    assert design.docker_engine == ""
    assert design.retry_max_attempts == 1
    assert design.probe == bench.ProbeSpec(tuple(range(6200, 6208)), 1000, 4, 1)
    assert (design.v10_monotonic_seconds, design.v10_realtime_seconds) == (7200.0, 7200.0)
    assert (design.x1_margin, design.x1_incomparable_cells) == (2, 2)
    assert design.stages["A"] == (2, 4, 4, 2)


def test_v2_design_is_unchanged() -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    assert not design.is_v3
    assert design.hosts == {}
    assert design.probe is None
    assert design.engine_for(None) == design.docker_engine != ""


def test_unresolved_engine_refuses_a_live_run_only() -> None:
    design = bench.parse_design(V3_BLOCK)  # parsing (plan, status) is allowed
    assert bench.unresolved_values(design, "HOST1") == [
        "host.HOST1.docker_engine = TBD-PREFLIGHT: pin it from a preflight first"
    ]
    pinned = bench.parse_design(text(**{"host.HOST1.docker_engine": "29.8.0"}))
    assert bench.unresolved_values(pinned, "HOST1") == []
    assert pinned.engine_for("HOST1") == "29.8.0"
    assert bench.unresolved_values(pinned, "HOST2") != []


def test_engine_for_requires_a_listed_host() -> None:
    design = bench.parse_design(V3_BLOCK)
    for host in (None, "HOST3"):
        with pytest.raises(bench.DesignError, match="--host must be one of"):
            design.engine_for(host)


@pytest.mark.parametrize("key", ["retry_max_attempts", "probe_retry_max_attempts"])
def test_only_a_single_attempt_is_accepted(key: str) -> None:
    with pytest.raises(bench.DesignError, match=f"{key} = 2: this driver runs each cell once"):
        bench.parse_design(text(**{key: "2"}))


def test_the_main_v3_file_value_two_is_refused_until_corrected() -> None:
    with pytest.raises(bench.DesignError, match="probe_retry_max_attempts = 2"):
        bench.parse_design(text(probe_retry_max_attempts="2"))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"probe_seeds": "6199, 6200"}, "probe_seeds must be distinct and inside 6200-6207"),
        ({"probe_seeds": "6200, 6200"}, "probe_seeds must be distinct"),
        ({"probe_jobs": "0"}, "probe_jobs must be positive"),
        ({"host.HOST2.run_prefix": "h1"}, "must not share a run_prefix"),
        ({"host.HOST2.run_prefix": "H-2"}, "is not"),
        ({"host.HOST2.docker_engine": None}, "host HOST2 needs"),
        ({"host.HOST3.run_prefix": "h3"}, "unknown host key: host.HOST3.run_prefix"),
        ({"hosts": "HOST1, HOST1"}, "hosts must be distinct"),
        ({"x1_margin": None}, "missing \\['x1_margin'\\]"),
        ({"docker_engine": "29.8.0"}, "unknown \\['docker_engine'\\]"),
    ],
)
def test_v3_refusals(changes: dict[str, str | None], message: str) -> None:
    with pytest.raises(bench.DesignError, match=message):
        bench.parse_design(text(**changes))


def test_probe_seed_range_is_reserved_for_other_uses() -> None:
    # A measured or smoke seed inside the probe range is refused like any reserved seed.
    with pytest.raises(bench.DesignError, match="reserved range 6200-6207"):
        bench.parse_design(text(smoke_seed="6205", probe_seeds="6200, 6201"))
    with pytest.raises(bench.DesignError, match="reserved range 6200-6207"):
        bench.parse_design(text(seeds="8110, 8102, 8103, 6203"))


def test_v2_block_with_host_keys_is_refused() -> None:
    v2 = Path("experiments/configs/concurrency-scaling-v2.md").read_text(encoding="utf-8")
    broken = v2.replace("stage.smoke", "host.HOST1.run_prefix = h1\nstage.smoke", 1)
    with pytest.raises(bench.DesignError, match="unknown \\['host.HOST1.run_prefix'\\]"):
        bench.parse_design(broken)


# ---- --host and run-id prefixes -------------------------------------------------------------


def test_hosts_run_the_same_cells_with_their_own_prefix() -> None:
    design = bench.parse_design(V3_BLOCK)
    one = bench.planned_blocks(design, "A", "HOST1")
    two = bench.planned_blocks(design, "A", "HOST2")
    assert [block.host for block in one] == ["HOST1"] * 4
    assert [(c.arm.label, c.seed) for c in one[0].cells] == [
        (c.arm.label, c.seed) for c in two[0].cells
    ]
    assert one[0].cells[0].run_id == "h1-7.5.2-R-restart-s8110"
    assert two[0].cells[0].run_id == "h2-7.5.2-R-restart-s8110"
    with pytest.raises(bench.DesignError, match="--host must be one of"):
        bench.planned_blocks(design, "A", "HOST3")


def test_v2_plan_has_no_host_and_no_prefix() -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    block = bench.planned_blocks(design, "A")[0]
    assert block.host is None
    assert block.cells[0].run_id == "7.5.2-R-restart-s8110"


def _v3_file(tmp_path: Path) -> Path:
    path = tmp_path / "v3.md"
    path.write_text("# test design\n\n" + V3_BLOCK)
    return path


def test_cli_requires_host_for_v3_and_refuses_it_for_v2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        bench.main(
            ["--design", str(_v3_file(tmp_path)), "--output", str(out), "--stage", "A", "--dry-run"]
        )
    assert "--host is required" in capsys.readouterr().err
    v2 = "experiments/configs/concurrency-scaling-v2.md"
    with pytest.raises(SystemExit):
        bench.main(
            ["--design", v2, "--output", str(out), "--stage", "A", "--host", "HOST1", "--dry-run"]
        )
    assert "--host does not apply" in capsys.readouterr().err


def test_dry_run_prints_prefixed_cells_and_the_unresolved_engine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["--design", str(_v3_file(tmp_path)), "--output", str(tmp_path / "o"), "--stage", "A"]
    assert bench.main([*args, "--host", "HOST2", "--dry-run"]) == 0
    printed = capsys.readouterr().out
    assert "  h2-7.5.2-D-s8102: " in printed
    assert "note: a live run would refuse: host.HOST2.docker_engine = TBD-PREFLIGHT" in printed


# ---- probe stage ------------------------------------------------------------------------------


def test_probe_plan_is_one_block_of_eight_rotated_cells() -> None:
    design = bench.parse_design(V3_BLOCK)
    (block,) = bench.planned_blocks(design, bench.PROBE_STAGE, "HOST1")
    assert (block.stage, block.index, block.jobs, block.host) == ("probe", 1, 4, "HOST1")
    assert block.name == "block-1-j4"
    assert [(c.seed, c.arm.label, c.budget) for c in block.cells] == [
        (6200, "R-restart", 1000),
        (6201, "D", 1000),
        (6202, "S-u", 1000),
        (6203, "R-restart", 1000),
        (6204, "D", 1000),
        (6205, "S-u", 1000),
        (6206, "R-restart", 1000),
        (6207, "D", 1000),
    ]
    assert block.cells[0].run_id == "h1-7.5.2-R-restart-s6200"
    assert bench.PROBE_STAGE not in bench.measured_stages(design)


def test_v2_design_has_no_probe() -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    with pytest.raises(bench.DesignError, match="has no probe stage"):
        bench.planned_blocks(design, bench.PROBE_STAGE)


def _write_probe(output: Path, design: bench.Design, **fields: object) -> None:
    (output / "probe").mkdir(parents=True, exist_ok=True)
    value = {
        "schema": bench.PROBE_SCHEMA,
        "design_sha256": design.sha256,
        "host": "HOST1",
        "passed": True,
        "conditions": {},
        **fields,
    }
    (output / "probe" / bench.PROBE_FILE).write_text(json.dumps(value))


def test_v3_smoke_needs_a_passed_probe_for_this_design_and_host(tmp_path: Path) -> None:
    design = bench.parse_design(V3_BLOCK)
    gate = bench.stage_gate_problem
    assert "run --stage probe first" in (gate(design, "smoke", tmp_path, "HOST1") or "")
    _write_probe(tmp_path, design, passed=False, conditions={"cleanup_unknown": 1})
    assert "did not pass" in (gate(design, "smoke", tmp_path, "HOST1") or "")
    _write_probe(tmp_path, design, host="HOST2")
    assert "is for host HOST2" in (gate(design, "smoke", tmp_path, "HOST1") or "")
    _write_probe(tmp_path, design, design_sha256="0" * 64)
    assert "not written for this design" in (gate(design, "smoke", tmp_path, "HOST1") or "")
    _write_probe(tmp_path, design)
    assert gate(design, "smoke", tmp_path, "HOST1") is None
    assert gate(design, bench.PROBE_STAGE, tmp_path, "HOST1") is None


def test_v2_smoke_has_no_probe_requirement(tmp_path: Path) -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    assert bench.stage_gate_problem(design, "smoke", tmp_path) is None


def _probe_block(tmp_path: Path) -> tuple[bench.Design, bench.Block, Path, Path]:
    design = bench.parse_design(V3_BLOCK)
    (block,) = bench.planned_blocks(design, bench.PROBE_STAGE, "HOST1")
    directory = tmp_path / "probe" / block.name
    (directory / "raw").mkdir(parents=True)
    return design, block, directory, tmp_path / "start-gate"


def _clean_record(block: bench.Block) -> dict[str, object]:
    return {
        "cells": [{"run_id": c.run_id, "state": "ran"} for c in block.cells],
        "residual_after_block": [],
        "start_gate_waits_seconds": [0.0, 1.5],
        "stopped_reason": None,
    }


def test_probe_summary_passes_only_when_all_four_conditions_are_zero(tmp_path: Path) -> None:
    design, block, directory, gate = _probe_block(tmp_path)
    raw = directory / "raw"
    (raw / f"{block.cells[0].run_id}.log").write_text(
        "inodefence-cleanup-attempt {}\ninodefence-infra-reexecution {}\nok\n"
    )
    (raw / "x.calls.jsonl").write_text(
        '{"timed_out": true}\n{"timed_out": false}\nnot json\n{"timed_out": true}\n'
    )
    summary = bench.summarize_probe(design, block, directory, gate, _clean_record(block))
    assert summary["passed"] is True
    assert summary["conditions"] == {
        "cleanup_unknown": 0,
        "residual_resources": 0,
        "runner_failures": 0,
        "start_failures": 0,
    }
    assert summary["report_only"]["calls_timeouts"] == 2
    assert summary["report_only"]["cleanup_diagnostic_lines"] == 1
    assert summary["report_only"]["infra_reexecutions"] == 1
    assert summary["report_only"]["start_gate_waits_seconds"] == [0.0, 1.5]
    assert (summary["schema"], summary["host"], summary["design_sha256"]) == (
        bench.PROBE_SCHEMA,
        "HOST1",
        design.sha256,
    )


@pytest.mark.parametrize("failure", ["verdict", "marker", "residual", "start"])
def test_probe_summary_fails_on_each_condition(tmp_path: Path, failure: str) -> None:
    design, block, directory, gate = _probe_block(tmp_path)
    record = _clean_record(block)
    cell = block.cells[2].run_id
    if failure == "verdict":
        gate.mkdir()
        start_gate.record_verdict(gate, cell, "U", "test")
    elif failure == "marker":
        (directory / "raw" / f"{cell}.log").write_text("INODEFENCE_CLEANUP_UNKNOWN: test\n")
    elif failure == "residual":
        record["residual_after_block"] = ["inodefence-local-runtime-x"]
    else:
        record["cells"] = [{"run_id": cell, "state": "not-run", "start_error": "OSError: x"}]
    summary = bench.summarize_probe(design, block, directory, gate, record)
    assert summary["passed"] is False
    key = {
        "verdict": "cleanup_unknown",
        "marker": "cleanup_unknown",
        "residual": "residual_resources",
        "start": "start_failures",
    }[failure]
    assert summary["conditions"][key] == 1


def test_probe_summary_after_an_exception_uses_incomplete_evidence(tmp_path: Path) -> None:
    design, block, directory, gate = _probe_block(tmp_path)
    assert bench.summarize_probe(design, block, directory, gate, None)["conditions"] == {
        "cleanup_unknown": 0,
        "residual_resources": None,
        "runner_failures": None,
        "start_failures": None,
    }
    (directory / bench.INCOMPLETE_BLOCK_FILE).write_text(
        json.dumps(
            {
                "cell_records": [],
                "failures": [{"where": "cell x", "type": "OSError"}],
                "residual_resources": {"status": "unknown", "error": "x"},
            }
        )
    )
    summary = bench.summarize_probe(design, block, directory, gate, None)
    assert summary["passed"] is False
    assert summary["conditions"]["runner_failures"] == 1
    assert summary["conditions"]["residual_resources"] is None


def _live_probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run_block: object) -> list[str]:
    seen: list[str] = []

    def fake_preflight(design: bench.Design, head: str, host: str | None) -> tuple[dict, list]:
        seen.append(f"preflight {host}")
        return {"docker_server": "29.8.0"}, []

    monkeypatch.setattr(bench, "preflight", fake_preflight)
    monkeypatch.setattr(bench, "run_block", run_block)
    monkeypatch.setattr(bench.time, "sleep", lambda _s: None)
    return seen


def test_live_probe_writes_probe_json_and_opens_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "out"

    def clean(design: bench.Design, block: bench.Block, directory: Path, *_a: object) -> dict:
        return {**_clean_record(block), "stopped_reason": None}

    seen = _live_probe(tmp_path, monkeypatch, clean)
    args = ["--design", str(_v3_file(tmp_path)), "--output", str(output), "--host", "HOST1"]
    live = ["--expected-head", "x", "--approval-ref", "test"]
    assert bench.main([*args, "--stage", "probe", *live]) == 0
    assert seen == ["preflight HOST1"]
    probe = json.loads((output / "probe" / bench.PROBE_FILE).read_text())
    assert probe["passed"] is True and probe["host"] == "HOST1"
    preflight = json.loads((output / "probe" / "block-1-j4" / "preflight.json").read_text())
    assert preflight["host"] == "HOST1"
    design = bench.load_design(_v3_file(tmp_path))
    assert bench.stage_gate_problem(design, "smoke", output, "HOST1") is None
    assert "is for host HOST1" in (bench.stage_gate_problem(design, "smoke", output, "HOST2") or "")


def test_live_probe_that_raises_still_writes_a_failed_probe_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "out"

    def broken(*_a: object) -> dict:
        raise OSError("injected block failure")

    _live_probe(tmp_path, monkeypatch, broken)
    args = ["--design", str(_v3_file(tmp_path)), "--output", str(output), "--host", "HOST1"]
    with pytest.raises(OSError, match="injected block failure"):
        bench.main([*args, "--stage", "probe", "--expected-head", "x", "--approval-ref", "t"])
    probe = json.loads((output / "probe" / bench.PROBE_FILE).read_text())
    assert probe["passed"] is False

"""EXP-0 launcher: gate, dry-run, idempotent rerun and summaries (no Docker)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep
from typing import Any

import pytest
from scripts import gen_exp3_tables, run_effect_demo, run_exp0
from scripts import run_concurrency_benchmark as bench
from scripts.analyze_exp0 import main as analyze_main
from scripts.run_effect_demo import synthetic_demo_report
from scripts.run_exp0 import (
    WATCHDOG_RETURNCODE,
    DiskUsageUnavailable,
    Exp0Plan,
    archive_attempt,
    cell_is_complete,
    disk_usage_fraction,
    exp0_cell_env,
    gate_mismatches,
    main,
    post_check,
    run_cell_with_watchdog,
    wait_for_disk,
)
from scripts.run_g1_smoke import cell_paths

from inodefence.evaluation.rds import RdsArm
from inodefence.evaluation.rds_preregistration import load_preregistration
from inodefence.model.provenance import SourceProvenance

SHA = "0123456789abcdef0123456789abcdef01234567"
DIGEST = "sha256:" + "ab" * 32
BLOCK = f"""# EXP-0 v2.1 (test fixture)

```preregistration
engine_sha = {SHA}
image_digest = {DIGEST}
seeds = 9001, 9002
budget = 6
vocabulary = observed-names
arm.R = unretained-walk-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
arm.S-a = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = 9001
sentinel_count = 3
observer_integrity_policy = invalid-continue
hit_definition = c1-or-c2-and-contract-violated
c0_counts_as_hit = false
denominator = all-cells-including-abort
abort_reporting = right-censored
rule_of_three_unit = campaign
```
"""
SENTINEL_SET = {"generator_id": "sentinel-names/seed-random-v1", "generator_seed": 9001, "count": 3}


@pytest.fixture
def prereg_file(tmp_path: Path) -> Path:
    path = tmp_path / "exp0-pilot-v2.1.md"
    path.write_text(BLOCK, encoding="utf-8")
    return path


@pytest.fixture
def clean_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_exp0, "capture_source", lambda: SourceProvenance(SHA, False))
    monkeypatch.setattr(run_exp0, "_script_has", lambda variable: True)


def _plan(path: Path, include_s_a: bool = False) -> Exp0Plan:
    import hashlib

    return Exp0Plan(
        load_preregistration(path),
        path,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        "7.5.2",
        include_s_a,
    )


def _base_args(prereg_file: Path, out: Path) -> list[str]:
    return [
        "--preregistration",
        str(prereg_file),
        "--output",
        str(out),
        "--image-digest",
        DIGEST,
        "--observer-integrity-policy",
        "invalid-continue",
        "--no-manifest",
    ]


def _rotated(seeds: Sequence[int], labels: Sequence[str]) -> list[tuple[int, str]]:
    return [
        (seed, labels[(position + offset) % len(labels)])
        for position, seed in enumerate(seeds)
        for offset in range(len(labels))
    ]


def test_multi_target_cell_order_follows_the_concurrency_benchmark_rule(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None
) -> None:
    """The benchmark's result moves to EXP-3 only if EXP-3 runs cells in the order it measured."""
    design = bench.load_design(
        Path(__file__).parents[1] / "experiments/configs/concurrency-scaling-v2.md"
    )
    measured = [(cell.seed, cell.arm.label) for cell in bench.planned_cells(design, "A")]
    assert measured == _rotated(design.seeds, [arm.label for arm in design.arms])
    _ledger_path, sha = _ledger(tmp_path)
    cells = _plan(_targets_file(tmp_path, ledger_sha=sha)).cells()
    train = [(cell.seed, cell.arm.label) for cell in cells if cell.version == "7.5.2"]
    assert train == _rotated((9001, 9002), ("R", "D", "S-u"))
    # A target with fewer arms rotates among its own arms.
    holdout = [(cell.seed, cell.arm.label) for cell in cells if cell.version == "7.9.9"]
    assert holdout == _rotated((9001, 9002), ("R", "S-u"))
    # All of one target runs before the next, and no cell is lost or repeated.
    assert [cell.version for cell in cells] == ["7.5.2"] * 6 + ["7.9.9"] * 4
    assert len(set(train)) == 6
    assert len(set(holdout)) == 4


def test_a_single_target_block_is_the_targets_form_and_rotates(tmp_path: Path) -> None:
    """D040 writes both registration files with ``targets.<id>``, one target included."""
    _ledger_path, sha = _ledger(tmp_path)
    dropped = ("exposure_ledger", "confirmatory_", "multiplicity", "primary_endpoint", "event_")
    lines = _targets_file(tmp_path, ledger_sha=sha).read_text(encoding="utf-8").splitlines()
    path = tmp_path / "exp3-one-target.md"
    path.write_text(
        "".join(
            f"{line}\n" for line in lines if "7.9.9" not in line and not line.startswith(dropped)
        ),
        encoding="utf-8",
    )
    plan = _plan(path)
    assert plan.multi_target is True
    assert [(cell.seed, cell.arm.label) for cell in plan.cells()] == _rotated(
        (9001, 9002), ("R", "D", "S-u")
    )


def test_plan_is_entirely_from_the_file(prereg_file: Path) -> None:
    plan = _plan(prereg_file)
    cells = plan.cells()
    assert len(cells) == 6 and {c.budget for c in cells} == {6}
    assert sorted({c.seed for c in cells}) == [9001, 9002]
    assert [a.label for a in plan.arms()] == ["R", "D", "S-u"]
    assert all(c.arm.mutation is not None and "fixed-baseline-v1" in c.arm.mutation for c in cells)
    assert len(_plan(prereg_file, include_s_a=True).cells()) == 8
    assert plan.sentinel_request() == SENTINEL_SET
    env = exp0_cell_env(plan, cells[0], Path("/out"), {})
    assert env["DEMO_SENTINEL_SEED"] == "9001" and env["DEMO_SENTINEL_COUNT"] == "3"
    assert env["DEMO_OBSERVER_INTEGRITY_POLICY"] == "invalid-continue"
    assert env["DEMO_BUDGET"] == "6" and env["TAR_VERSION"] == "7.5.2"


def test_gate_covers_every_declared_check(prereg_file: Path) -> None:
    plan = _plan(prereg_file)
    ok: dict[str, Any] = dict(
        engine_sha=SHA,
        engine_dirty=False,
        image_digest=DIGEST,
        observer_integrity_policy="invalid-continue",
    )
    assert gate_mismatches(plan, **ok) == ()
    for key, value, fragment in (
        ("engine_sha", "f" * 40, "engine SHA"),
        ("engine_dirty", True, "dirty"),
        ("image_digest", None, "not supplied"),
        ("observer_integrity_policy", "stop", "observer_integrity_policy"),
    ):
        problems = gate_mismatches(plan, **{**ok, key: value})
        assert any(fragment in item for item in problems), (key, problems)


def test_dry_run_prints_gate_and_all_cells_without_touching_output(
    prereg_file: Path, tmp_path: Path, clean_engine: None, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "exp0"
    assert main([*_base_args(prereg_file, out), "--dry-run"]) == 0
    text = capsys.readouterr().out
    assert "gate: PASS" in text and "cells=6 pending=6" in text
    assert "would be refused at live run:\n  (nothing)" in text
    assert text.count("[pending]") == 6 and '"DEMO_SENTINEL_SEED": "9001"' in text
    assert '"DEMO_OBSERVER_INTEGRITY_POLICY": "invalid-continue"' in text
    assert not out.exists()


def test_dry_run_reports_gate_failure_and_exits_2(
    prereg_file: Path, tmp_path: Path, clean_engine: None, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _base_args(prereg_file, tmp_path / "exp0")
    args[args.index("--image-digest") + 1] = "sha256:" + "cd" * 32
    assert main([*args, "--dry-run"]) == 2
    assert "gate: FAIL" in capsys.readouterr().out


def test_live_run_is_refused_on_gate_mismatch_and_writes_nothing(
    prereg_file: Path, tmp_path: Path, clean_engine: None, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "exp0"
    args = _base_args(prereg_file, out)
    args[args.index("--observer-integrity-policy") + 1] = "stop"
    assert main(args) == 2
    assert "refusing to run (preregistration gate)" in capsys.readouterr().err
    assert not out.exists()


def test_live_run_is_refused_when_controller_wiring_is_missing(
    prereg_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(run_exp0, "capture_source", lambda: SourceProvenance(SHA, False))
    monkeypatch.setattr(run_exp0, "_script_has", lambda variable: False)
    out = tmp_path / "exp0"
    assert main(_base_args(prereg_file, out)) == 2
    err = capsys.readouterr().err
    assert (
        "controller wiring" in err and "DEMO_SENTINEL_SEED" in err and "observer_integrity" in err
    )
    assert (out / "registration.json").is_file()  # registered, but nothing ran


def _fake_manifest_script(tmp_path: Path) -> Path:
    """Stand-in for scripts/make_raw_manifest.py: generate writes a file; --verify
    exits 1 when a ``verify_fail`` marker sits next to the script."""
    script = tmp_path / "fake_manifest.py"
    script.write_text(
        "import sys, pathlib\n"
        "argv = sys.argv[1:]\n"
        "if '--verify' in argv:\n"
        "    sys.exit(1 if pathlib.Path(__file__).with_name('verify_fail').exists() else 0)\n"
        "out = pathlib.Path(argv[argv.index('--out') + 1])\n"
        "out.write_text('fake\\n'); print('ok')\n"
    )
    return script


def _fake_runner(behaviour: dict[str, Any]):
    """Stand-in for run_parallel_native._run_cell writing synthetic native-shaped reports."""
    from scripts.run_parallel_native import CellResult

    calls: list[str] = []

    def run(cell, output: Path, env: dict[str, str], bash: str, **_limits: Any) -> CellResult:
        calls.append(cell.run_id)
        paths = cell_paths(cell, output)
        search = env["DEMO_POLICY"]
        from inodefence.feedback import EffectSearchPolicy
        from inodefence.mutator import MutationPolicy

        report: dict[str, Any] = synthetic_demo_report(
            cell.seed,
            cell.budget,
            EffectSearchPolicy(search),
            MutationPolicy(env["DEMO_MUTATION_POLICY"]),
        )
        by_target = behaviour.get("image_id_by_target", {})
        report["image_id"] = by_target.get(
            getattr(cell, "target_id", None), behaviour.get("image_id", DIGEST)
        )
        report["sentinel_set"] = behaviour.get(
            "sentinel_set", {**SENTINEL_SET, "names": ["a", "b", "c"]}
        )
        steps = report["steps"]
        if cell.run_id in behaviour.get("abort", ()):
            report = {
                "label": "demo run",
                "producer": "native",
                "aborted": {"step_index": 2, "reason": "broker", "case_id": "c", "observed": None},
            }
            steps = steps[:2]
        paths["report"].write_text(json.dumps(report), encoding="utf-8")
        paths["steps_jsonl"].write_text(
            "".join(json.dumps(s) + "\n" for s in steps), encoding="utf-8"
        )
        paths["log"].write_text(
            "context=default engine=29.8.0 mode=demo-historical\n", encoding="utf-8"
        )
        returncode = 1 if cell.run_id in behaviour.get("abort", ()) else 0
        return CellResult(cell, returncode, 1.0, paths["report"], True, paths["log"])

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_live_run_end_to_end_with_fake_cells_then_idempotent_rerun(
    prereg_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    out = tmp_path / "exp0"
    runner = _fake_runner({"abort": {"7.5.2-D-s9002"}})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    manifest_script = _fake_manifest_script(tmp_path)
    manifest_out = tmp_path / "raw-manifest-test.sha256"
    args = [
        "--preregistration",
        str(prereg_file),
        "--output",
        str(out),
        "--image-digest",
        DIGEST,
        "--observer-integrity-policy",
        "invalid-continue",
        "--manifest-script",
        str(manifest_script),
        "--manifest-out",
        str(manifest_out),
        "--manifest-host",
        "test",
    ]
    assert main(args) == 1  # one aborted cell -> not all complete
    assert sorted(runner.calls) == sorted(c.run_id for c in _plan(prereg_file).cells())  # type: ignore[attr-defined]
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["label"][0] == "registered run" and f"engine_sha={SHA}" in index["label"]
    assert "experiment=exp0" in index["label"] and index["outcomes_redacted"] is False
    assert index["preregistration"]["sha256"] == _plan(prereg_file).preregistration_sha256
    assert index["g1_verdict"]["complete"] == 5 and index["g1_verdict"]["aborts"] == 1
    assert index["vocabulary_equal_across_arms"] is True
    registration = json.loads((out / "registration.json").read_text())
    verification = json.loads((out / "manifest-verification.json").read_text())
    assert verification["raw_manifest"]["generated"] is True and manifest_out.is_file()
    assert verification["verification"]["verified"] is True
    assert registration["invocations"] == 1
    record = json.loads((out / "summaries" / "7.5.2-S-u-s9001.summary.json").read_text())
    assert record["summary"]["sentinel_set"] is None  # runner summary passthrough is report-level
    assert (
        record["environment"]["image_id"] == DIGEST
        and record["timing"]["execution_mode"] == "per-case-container"
    )

    # Rerun: only the aborted cell runs again; its first attempt is archived.
    runner2 = _fake_runner({})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner2)
    assert main(args) == 0
    assert runner2.calls == ["7.5.2-D-s9002"]  # type: ignore[attr-defined]
    assert list((out / "attempts").glob("7.5.2-D-s9002.attempt1.*"))
    matrix = json.loads((out / "matrix.json").read_text())
    assert len(matrix["skipped_complete"]) == 5 and matrix["archived_attempts"] == {
        "7.5.2-D-s9002": 1
    }
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["g1_verdict"]["pass"] is True and index["g1_verdict"]["complete"] == 6
    assert json.loads((out / "registration.json").read_text())["invocations"] == 2
    # A third run has nothing to do.
    runner3 = _fake_runner({})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner3)
    assert main(args) == 0 and runner3.calls == []  # type: ignore[attr-defined]


def test_nonconformant_image_or_sentinel_set_is_invalid_not_complete(
    prereg_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "exp0"
    runner = _fake_runner({"image_id": "sha256:" + "cd" * 32})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    assert main(_base_args(prereg_file, out)) == 1
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["invalid_count"] == 6 and all(c["invalid"] for c in index["cells"])
    record = json.loads((out / "summaries" / "7.5.2-R-s9001.summary.json").read_text())
    assert record["config_nonconformant"] and "image_id" in record["invalid_reason"]
    plan = _plan(prereg_file)
    cell = plan.cells()[0]
    assert not cell_is_complete(plan, cell, out)
    # Sentinel mismatch is also nonconformant.
    report = json.loads(cell_paths(cell, out)["report"].read_text())
    report["image_id"] = DIGEST
    report["sentinel_set"]["generator_seed"] = 1
    assert post_check(plan)(report, cell) is not None and "generator_seed" in str(
        post_check(plan)(report, cell)
    )


def test_registration_refuses_a_directory_from_another_registration(
    prereg_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "exp0"
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner({}))
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    assert main(_base_args(prereg_file, out)) == 0
    other = tmp_path / "other.md"
    other.write_text(BLOCK.replace("seeds = 9001, 9002", "seeds = 9001"), encoding="utf-8")
    args = _base_args(other, out)
    with pytest.raises(SystemExit, match="different preregistration_sha256"):
        main(args)


def test_archive_attempt_numbers_increase(tmp_path: Path, prereg_file: Path) -> None:
    plan = _plan(prereg_file)
    cell = plan.cells()[0]
    out = tmp_path / "exp0"
    out.mkdir()
    assert archive_attempt(cell, out) is None
    for expected in (1, 2):
        cell_paths(cell, out)["report"].write_text("{}")
        cell_paths(cell, out)["log"].write_text("log")
        assert archive_attempt(cell, out) == expected
    assert sorted(p.name for p in (out / "attempts").iterdir()) == [
        "7.5.2-R-s9001.attempt1.json",
        "7.5.2-R-s9001.attempt1.log",
        "7.5.2-R-s9001.attempt2.json",
        "7.5.2-R-s9001.attempt2.log",
    ]


def test_archive_attempt_moves_the_call_log(tmp_path: Path, prereg_file: Path) -> None:
    """A retry starts its own call log; the earlier attempt's records do not mix into it."""
    plan = _plan(prereg_file)
    cell = plan.cells()[0]
    out = tmp_path / "exp0"
    out.mkdir()
    calls = cell_paths(cell, out)["calls"]
    assert calls.name.endswith(".calls.jsonl")
    calls.write_text('{"kind":"header"}\n')
    assert archive_attempt(cell, out) == 1
    assert not calls.exists()
    assert (out / "attempts" / "7.5.2-R-s9001.attempt1.calls.jsonl").is_file()


def test_call_log_name_matches_the_harness(tmp_path: Path, prereg_file: Path) -> None:
    cell = _plan(prereg_file).cells()[0]
    paths = cell_paths(cell, tmp_path)
    assert paths["calls"].name == paths["report"].name.removesuffix(".json") + ".calls.jsonl"


def test_include_s_a_requires_declaration(
    prereg_file: Path, tmp_path: Path, clean_engine: None
) -> None:
    stripped = tmp_path / "no-sa.md"
    stripped.write_text(
        "\n".join(line for line in BLOCK.splitlines() if not line.startswith("arm.S-a")),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        main([*_base_args(stripped, tmp_path / "x"), "--include-s-a", "--dry-run"])
    assert RdsArm.S_A not in load_preregistration(stripped).arm_policies


EXP3_EXTRA = """experiment_id = exp3
execution_mode = per-case-container
jobs_max = 2
campaign_watchdog_seconds = 7200
disk_pause_fraction = 0.9
interim_analysis = forbidden
"""


@pytest.fixture
def exp3_file(tmp_path: Path) -> Path:
    path = tmp_path / "exp3-main-v1.md"
    path.write_text(
        BLOCK.replace(
            "rule_of_three_unit = campaign\n", "rule_of_three_unit = campaign\n" + EXP3_EXTRA
        ),
        encoding="utf-8",
    )
    return path


def test_scale_keys_are_parsed_and_label_the_plan(exp3_file: Path) -> None:
    prereg = load_preregistration(exp3_file)
    assert prereg.experiment_id == "exp3" and prereg.execution_mode == "per-case-container"
    assert (prereg.jobs_max, prereg.campaign_watchdog_seconds) == (2, 7200.0)
    assert (prereg.disk_pause_fraction, prereg.interim_analysis) == (0.9, "forbidden")
    plan = _plan(exp3_file)
    assert plan.plan == "exp3" and plan.interim_forbidden
    assert plan.watchdog_seconds == 7200.0 and plan.disk_pause_fraction == 0.9
    assert "experiment=exp3" in plan.labels(SHA)


@pytest.mark.parametrize(
    ("line", "wrong", "fragment"),
    (
        ("execution_mode = per-case-container", "execution_mode = cloud", "execution_mode"),
        ("jobs_max = 2", "jobs_max = 0", "jobs_max"),
        ("campaign_watchdog_seconds = 7200", "campaign_watchdog_seconds = -1", "positive"),
        ("disk_pause_fraction = 0.9", "disk_pause_fraction = 1.5", "disk_pause_fraction"),
        ("interim_analysis = forbidden", "interim_analysis = maybe", "interim_analysis"),
    ),
)
def test_scale_keys_fail_closed(exp3_file: Path, line: str, wrong: str, fragment: str) -> None:
    from inodefence.evaluation.rds_preregistration import (
        PreregistrationFormatError,
        parse_preregistration,
    )

    with pytest.raises(PreregistrationFormatError, match=fragment):
        parse_preregistration(exp3_file.read_text().replace(line, wrong))


def test_scale_gate_jobs_cap_and_execution_mode(
    exp3_file: Path, tmp_path: Path, clean_engine: None, capsys
) -> None:
    plan = _plan(exp3_file)
    ok: dict[str, Any] = dict(
        engine_sha=SHA,
        engine_dirty=False,
        image_digest=DIGEST,
        observer_integrity_policy="invalid-continue",
    )
    assert gate_mismatches(plan, **ok, jobs=2) == ()
    assert any(
        "jobs 3 > preregistered jobs_max 2" in m for m in gate_mismatches(plan, **ok, jobs=3)
    )
    args = [*_base_args(exp3_file, tmp_path / "x"), "--jobs", "3", "--dry-run"]
    assert main(args) == 2
    out = capsys.readouterr().out
    assert "gate: FAIL" in out and "- gate: jobs 3 > preregistered jobs_max 2" in out
    # Execution mode from the flag must match the file; worker-pool is refused when unwired.
    args = [*_base_args(exp3_file, tmp_path / "y"), "--execution-mode", "worker-pool", "--dry-run"]
    assert main(args) == 2
    out = capsys.readouterr().out
    assert "execution_mode 'worker-pool' != preregistered 'per-case-container'" in out


def test_worker_pool_mode_requires_module_and_wiring(
    exp3_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    text = exp3_file.read_text().replace(
        "execution_mode = per-case-container", "execution_mode = worker-pool"
    )
    exp3_file.write_text(text, encoding="utf-8")
    monkeypatch.setattr(run_exp0, "capture_source", lambda: SourceProvenance(SHA, False))
    monkeypatch.setattr(run_exp0, "_script_has", lambda variable: variable != "DEMO_EXECUTION_MODE")
    monkeypatch.setattr(run_exp0, "_worker_pool_module", lambda: None)
    out = tmp_path / "wp"
    assert main([*_base_args(exp3_file, out), "--dry-run"]) == 2  # gate passes; wiring refuses
    text = capsys.readouterr().out
    assert "gate: PASS" in text
    assert "wiring: execution_mode worker-pool needs inodefence.execution.worker_pool" in text
    assert "DEMO_EXECUTION_MODE" in text and '"DEMO_EXECUTION_MODE": "worker-pool"' in text
    assert main(_base_args(exp3_file, out)) == 2
    assert "controller wiring" in capsys.readouterr().err

    class FakePool:
        CAMPAIGN_WATCHDOG_SECONDS = 123.0
        DISK_PAUSE_FRACTION = 0.5

        @staticmethod
        def plan_worker_bringup(run_id: str, env: dict[str, str]):
            class Plan:
                pass

            plan = Plan()
            plan.env = (("RUN_ID", f"s3wp-{run_id}"),)  # type: ignore[attr-defined]
            return plan

        @staticmethod
        def should_pause_for_disk(fraction: float, threshold: float) -> bool:
            return fraction >= threshold

    monkeypatch.setattr(run_exp0, "_worker_pool_module", lambda: FakePool)
    plan = _plan(exp3_file)
    plan = Exp0Plan(
        plan.preregistration,
        plan.preregistration_path,
        plan.preregistration_sha256,
        "7.5.2",
        False,
        "worker-pool",
    )
    env = exp0_cell_env(plan, plan.cells()[0], out, {})
    assert env["RUN_ID"] == "s3wp-7.5.2-R-s9001" and env["DEMO_EXECUTION_MODE"] == "worker-pool"


def _fifteen_cell_file(tmp_path: Path) -> Path:
    path = tmp_path / "exp3-15.md"
    path.write_text(
        BLOCK.replace("seeds = 9001, 9002\n", "seeds = 9001, 9002, 9003, 9004, 9005\n").replace(
            "rule_of_three_unit = campaign\n", "rule_of_three_unit = campaign\n" + EXP3_EXTRA
        ),
        encoding="utf-8",
    )
    return path


def _manifest_args(tmp_path: Path) -> list[str]:
    return [
        "--manifest-script",
        str(_fake_manifest_script(tmp_path)),
        "--manifest-out",
        str(tmp_path / "raw-manifest-test.sha256"),
        "--manifest-host",
        "test",
    ]


def _interim_args(file: Path, out: Path, tmp_path: Path) -> list[str]:
    base = [a for a in _base_args(file, out) if a != "--no-manifest"]
    return [*base, *_manifest_args(tmp_path), "--jobs", "2"]


def test_interim_publishes_when_every_cell_is_final_and_evidence_verified(
    tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(i) one abort + fourteen complete + manifest OK: the abort is a result once it is
    marked final (right-censored, in the denominator); only then are outcomes published."""
    file = _fifteen_cell_file(tmp_path)
    out = tmp_path / "exp3"
    runner = _fake_runner({"abort": {"7.5.2-S-u-s9002"}})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    args = _interim_args(file, out, tmp_path)
    assert main(args) == 1
    index = json.loads((out / "summaries" / "index.json").read_text())
    # The abort record is not yet final: still redacted, with the reason named.
    assert index["outcomes_redacted"] is True
    assert index["interim"]["states"] == {
        "complete": 14,
        "abort-final": 0,
        "abort-pending": 1,
        "unattempted": 0,
    }
    assert any("abort record(s) not final" in r for r in index["interim"]["reasons"])
    assert index["interim"]["integrity_problems"] == [] and index["interim"]["pending_cells"] == 1
    assert not list((out / "summaries").glob("*.summary.json"))
    # Manual classification (the procedure's step until #203): finalize, re-summarize.
    assert (
        main([*args, "--finalize-abort", "7.5.2-S-u-s9002=campaign abort", "--summarize-only"]) == 1
    )
    decisions = json.loads((out / "abort-decisions.json").read_text())
    assert decisions["7.5.2-S-u-s9002"]["final"] is True
    assert decisions["7.5.2-S-u-s9002"]["abort_reason"] == "broker"
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["outcomes_redacted"] is False and index["interim"]["reasons"] == []
    assert index["interim"]["states"]["abort-final"] == 1
    assert index["interim"]["rule"] == run_exp0.INTERIM_RULE
    assert len(index["cells"]) == 15 and all("t_first" in c and "hit" in c for c in index["cells"])
    assert index["g1_verdict"]["complete"] == 14 and index["g1_verdict"]["aborts"] == 1
    aborted = next(c for c in index["cells"] if c["run_id"] == "7.5.2-S-u-s9002")
    assert aborted["aborted"] is True and aborted["complete"] is False
    assert aborted["t_first_censored"] is True and aborted["t_first_event"] == 0
    assert aborted["t_first"] == 2  # censored at the executions completed before the abort
    assert len(list((out / "summaries").glob("*.summary.json"))) == 15
    record = json.loads((out / "summaries" / "7.5.2-S-u-s9002.summary.json").read_text())
    assert record["summary"]["aborted"] is True and record["summary"]["t_first_censored"] is True
    verification = json.loads((out / "manifest-verification.json").read_text())
    assert (
        verification["verification"]["verified"] is True
        and verification["outcomes_redacted"] is False
    )
    registration = json.loads((out / "registration.json").read_text())
    assert registration["cell_states"]["7.5.2-S-u-s9002"] == "abort-final"
    # A final abort is never re-run: a live rerun skips it and keeps the publication.
    calls_before = len(runner.calls)  # type: ignore[attr-defined]
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner({}))
    assert main(args) == 1
    matrix = json.loads((out / "matrix.json").read_text())
    assert matrix["skipped_final_aborts"] == ["7.5.2-S-u-s9002"] and matrix["cells"] == []
    assert len(runner.calls) == calls_before  # type: ignore[attr-defined]
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["outcomes_redacted"] is False and index["g1_verdict"]["aborts"] == 1


def test_interim_stays_redacted_when_manifest_verification_fails(
    exp3_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(ii) every cell complete but the raw manifest does not re-verify: not published,
    reason recorded, summaries withheld, exit 1."""
    out = tmp_path / "exp3"
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner({}))
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    args = _interim_args(exp3_file, out, tmp_path)
    (tmp_path / "verify_fail").write_text("")
    assert main(args) == 1
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["outcomes_redacted"] is True
    assert index["interim"]["reasons"] == ["raw manifest verification failed"]
    assert index["interim"]["manifest"] == {"generated": True, "verified": False}
    assert index["g1_verdict"]["complete"] == 6  # completion state is still visible
    assert not list((out / "summaries").glob("*.summary.json"))
    verification = json.loads((out / "manifest-verification.json").read_text())
    assert verification["verification"]["verified"] is False and verification["outcomes_redacted"]
    # Fixed tree: a summary-only pass re-generates, re-verifies and publishes.
    (tmp_path / "verify_fail").unlink()
    assert main([*args, "--summarize-only"]) == 0
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["outcomes_redacted"] is False and all("t_first" in c for c in index["cells"])
    assert len(list((out / "summaries").glob("*.summary.json"))) == 6


def test_interim_stays_redacted_while_a_cell_is_unattempted(
    exp3_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(iii) a cell with no record (never started / died before writing) or in progress
    (steps on disk, no recorded termination) keeps the outcomes redacted."""
    out = tmp_path / "exp3"
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner({}))
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    args = _interim_args(exp3_file, out, tmp_path)
    assert main(args) == 0
    plan = _plan(exp3_file)
    victim = plan.cells()[3]
    paths = cell_paths(victim, out)
    for key in ("report", "steps_jsonl", "log"):
        paths[key].unlink()
    matrix = json.loads((out / "matrix.json").read_text())
    matrix["cells"] = [c for c in matrix["cells"] if c["run_id"] != victim.run_id]
    (out / "matrix.json").write_text(json.dumps(matrix))
    assert main([*args, "--summarize-only"]) == 1
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["outcomes_redacted"] is True
    assert index["interim"]["states"]["unattempted"] == 1 and index["interim"]["pending_cells"] == 1
    assert index["interim"]["reasons"][0].startswith("1 cell(s) unattempted")
    assert all(
        "hit" not in c and "t_first" not in c and c["summary"] is None for c in index["cells"]
    )
    assert not list((out / "summaries").glob("*.summary.json"))
    assert index["g1_verdict"]["complete"] == 5
    paths["steps_jsonl"].write_text("{}\n", encoding="utf-8")  # in progress, no termination
    assert main([*args, "--summarize-only"]) == 1
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["outcomes_redacted"] is True and index["interim"]["states"]["unattempted"] == 1
    paths["steps_jsonl"].unlink()
    assert main(args) == 0  # run to completion -> published
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["outcomes_redacted"] is False and all("t_first" in c for c in index["cells"])
    assert len(list((out / "summaries").glob("*.summary.json"))) == 6


def test_interim_stays_redacted_on_an_evidence_integrity_problem(
    exp3_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "exp3"
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner({}))
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    args = _interim_args(exp3_file, out, tmp_path)
    assert main(args) == 0
    plan = _plan(exp3_file)
    paths = cell_paths(plan.cells()[1], out)
    lines = paths["steps_jsonl"].read_text().splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    records[0]["oracle"] = {"C0": True, "C1": True, "C2": True}  # disagrees with the report
    paths["steps_jsonl"].write_text("".join(json.dumps(r) + "\n" for r in records))
    assert main([*args, "--summarize-only"]) == 1
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["outcomes_redacted"] is True
    assert index["interim"]["integrity_problems"] == [
        f"{plan.cells()[1].run_id}: steps file is not a prefix of the report steps"
    ]
    assert index["interim"]["reasons"][0].startswith("evidence integrity:")


def test_cell_state_rules(tmp_path: Path, prereg_file: Path) -> None:
    plan = _plan(prereg_file)
    cell = plan.cells()[0]
    paths = cell_paths(cell, tmp_path)
    state = run_exp0.cell_state
    assert state(plan, cell, tmp_path, {}, set()) == "unattempted"
    paths["steps_jsonl"].write_text("{}\n", encoding="utf-8")
    assert state(plan, cell, tmp_path, {}, set()) == "unattempted"  # in progress
    assert state(plan, cell, tmp_path, {}, {cell.run_id}) == "abort-pending"  # terminated
    final = {cell.run_id: {"final": True}}
    assert state(plan, cell, tmp_path, final, {cell.run_id}) == "abort-final"
    paths["steps_jsonl"].unlink()
    assert state(plan, cell, tmp_path, final, {cell.run_id}) == "unattempted"  # nothing written
    paths["report"].write_text(json.dumps({"aborted": {"reason": "x"}}), encoding="utf-8")
    assert state(plan, cell, tmp_path, {}, set()) == "abort-pending"
    assert state(plan, cell, tmp_path, final, set()) == "abort-final"
    assert run_exp0.recorded_terminations(tmp_path) == set()
    (tmp_path / "matrix.json").write_text(json.dumps({"cells": [{"run_id": "x"}, {"other": 1}]}))
    assert run_exp0.recorded_terminations(tmp_path) == {"x"}


def test_finalize_abort_is_fail_closed(
    exp3_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "exp3"
    monkeypatch.setattr(
        run_exp0, "run_cell_with_watchdog", _fake_runner({"abort": {"7.5.2-R-s9001"}})
    )
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    args = _interim_args(exp3_file, out, tmp_path)
    assert main(args) == 1
    for bad in ("7.5.2-R-s9999", "7.5.2-D-s9001"):  # unknown cell / complete cell
        with pytest.raises(SystemExit):
            main([*args, "--finalize-abort", bad, "--summarize-only"])
    paths = cell_paths(_plan(exp3_file).cells()[0], out)
    for key in ("report", "steps_jsonl", "log"):
        paths[key].unlink()
    with pytest.raises(SystemExit):  # no record left to finalize
        main([*args, "--finalize-abort", "7.5.2-R-s9001", "--summarize-only"])


def test_preregistration_commit_is_recorded_not_compared(
    prereg_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "exp0"
    commit = "f" * 40
    args = [*_base_args(prereg_file, out), "--preregistration-commit", commit, "--summarize-only"]
    assert main(args) == 1  # nothing run yet
    registration = json.loads((out / "registration.json").read_text())
    assert registration["preregistration_commit"] == commit
    assert registration["engine_sha"] == SHA and registration["preregistration_sha256"]
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["preregistration"]["commit"] == commit
    assert index["preregistration"]["engine_sha"] == SHA
    # Not a gate: a different (or absent) value on a rerun is accepted and recorded.
    assert main([*_base_args(prereg_file, out), "--summarize-only"]) == 1
    assert json.loads((out / "registration.json").read_text())["preregistration_commit"] is None
    dry = main([*_base_args(prereg_file, out), "--preregistration-commit", "zzz", "--dry-run"])
    assert dry == 0


def test_watchdog_terminates_an_overrunning_cell(tmp_path: Path, prereg_file: Path) -> None:
    import subprocess

    plan = _plan(prereg_file)
    cell = plan.cells()[0]
    events: list[str] = []

    class Hung:
        def wait(self, timeout=None):
            if timeout is not None and timeout < 30:
                events.append(f"wait:{timeout}")
                raise subprocess.TimeoutExpired("bash", timeout)
            events.append("wait")
            return 0

        def terminate(self):
            events.append("terminate")

        def kill(self):
            events.append("kill")

    result = run_cell_with_watchdog(
        cell, tmp_path, {}, "bash", limit_seconds=1.5, popen=lambda *a, **k: Hung()
    )
    assert result.returncode == WATCHDOG_RETURNCODE and events[:2] == ["wait:1.5", "terminate"]
    assert "[watchdog] terminated after 2 s" in (tmp_path / f"{cell.run_id}.log").read_text()
    assert not result.evidence_exists
    assert result.watchdog_fired is True


def test_watchdog_flag_stays_false_for_any_exit_the_watchdog_did_not_cause(
    prereg_file: Path, tmp_path: Path
) -> None:
    """Exit code -15 alone is an outside SIGTERM; only the timeout branch sets the flag."""

    class Terminated:
        def wait(self, timeout=None):
            return WATCHDOG_RETURNCODE

    result = run_cell_with_watchdog(
        _plan(prereg_file).cells()[0],
        tmp_path,
        {},
        "bash",
        limit_seconds=1.5,
        popen=lambda *a, **k: Terminated(),
    )
    assert result.returncode == WATCHDOG_RETURNCODE and result.watchdog_fired is False


def test_disk_pause_waits_until_below_threshold(tmp_path: Path) -> None:
    readings = iter([0.95, 0.93, 0.80])
    pauses: list[float] = []
    logs: list[str] = []
    taken = wait_for_disk(
        tmp_path,
        0.9,
        usage=lambda p: next(readings),
        pause=pauses.append,
        poll_seconds=5.0,
        log=logs.append,
    )
    assert taken == 2 and pauses == [5.0, 5.0]
    assert logs[0].startswith("disk usage at/above 90%") and "resuming" in logs[-1]
    assert wait_for_disk(tmp_path, 0.9, usage=lambda p: 0.1, pause=pauses.append) == 0


def test_unmeasurable_disk_usage_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    monkeypatch.setattr(shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(0, 0, 0))
    with pytest.raises(DiskUsageUnavailable, match="total=0"):
        disk_usage_fraction(tmp_path)
    # The pause loop propagates it: no silent skip of the disk guard.
    with pytest.raises(DiskUsageUnavailable):
        wait_for_disk(tmp_path, 0.9)


# ---- multi-target registrations (EXP-3 schema + gate) ---------------------------------

DIGEST_B = "sha256:" + "cd" * 32
LEDGER_TEXT = (
    "# exposure ledger (fixture)\n\n| extractor | version | exposure_kind |\n| --- | --- | --- |\n"
    "| node-tar | 7.5.2 | design-input |\n"
)


@pytest.fixture
def admit_fixture_holdout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The multi-target fixtures use a made-up holdout version the real allowlist refuses."""
    allowed = {"7.5.2": "lock-a", "7.9.9": "lock-b"}
    monkeypatch.setattr(run_effect_demo, "historical_target_versions", lambda: allowed)


def _targets_file(tmp_path: Path, *, ledger_sha: str, holdout_version: str = "7.9.9") -> Path:
    block = BLOCK.replace(f"image_digest = {DIGEST}\n", "").replace(
        "```preregistration\n",
        "```preregistration\n"
        "targets.node-tar-7.5.2.extractor = node-tar\n"
        "targets.node-tar-7.5.2.version = 7.5.2\n"
        f"targets.node-tar-7.5.2.image_digest = {DIGEST}\n"
        "targets.node-tar-7.5.2.role = train\n"
        "targets.node-tar-7.5.2.hypothesis = H-A\n"
        "targets.node-tar-7.5.2.exposure = pre-exposed\n"
        "targets.node-tar-7.5.2.exposure_ref = node-tar@7.5.2\n"
        f"targets.node-tar-{holdout_version}.extractor = node-tar\n"
        f"targets.node-tar-{holdout_version}.version = {holdout_version}\n"
        f"targets.node-tar-{holdout_version}.image_digest = {DIGEST_B}\n"
        f"targets.node-tar-{holdout_version}.role = holdout\n"
        f"targets.node-tar-{holdout_version}.hypothesis = H-A\n"
        f"targets.node-tar-{holdout_version}.exposure = none\n"
        f"targets.node-tar-{holdout_version}.arms = R, S-u\n"
        f"targets.node-tar-{holdout_version}.budget = 4\n"
        "exposure_ledger = exposure-ledger.md\n"
        f"exposure_ledger_sha256 = {ledger_sha}\n"
        "confirmatory_family = holdout:S-u-vs-R\n"
        "confirmatory_test = exact-logrank-permutation-v1\n"
        "multiplicity = holm-fwer-v1\n"
        "primary_endpoint = t_first\n"
        "event_threshold = 5\n",
    )
    path = tmp_path / "exp3-targets.md"
    path.write_text(block, encoding="utf-8")
    return path


def _ledger(tmp_path: Path, text: str = LEDGER_TEXT) -> tuple[Path, str]:
    import hashlib

    path = tmp_path / "exposure-ledger.md"
    path.write_text(text, encoding="utf-8")
    return path, hashlib.sha256(text.encode()).hexdigest()


def _target_args(file: Path, out: Path, ledger: Path) -> list[str]:
    return [
        "--preregistration",
        str(file),
        "--output",
        str(out),
        "--target-digest",
        f"node-tar-7.5.2={DIGEST}",
        "--target-digest",
        f"node-tar-7.9.9={DIGEST_B}",
        "--exposure-ledger",
        str(ledger),
        "--observer-integrity-policy",
        "invalid-continue",
        "--no-manifest",
    ]


def test_single_key_registration_plans_the_same_cells_as_before(prereg_file: Path) -> None:
    """EXP-0 v2.1 compatibility: the one-key form is one train target named by its
    version; run ids, evidence paths and the gate are unchanged."""
    plan = _plan(prereg_file)
    assert plan.multi_target is False
    (target,) = plan.targets()
    assert (target.target_id, target.extractor, target.version) == ("7.5.2", "node-tar", "7.5.2")
    assert (target.role, target.hypothesis, target.exposure, target.digest) == (
        "train",
        "H-A",
        "none",
        DIGEST,
    )
    cells = plan.cells()
    assert [c.run_id for c in cells] == [
        f"7.5.2-{arm}-s{seed}" for arm in ("R", "D", "S-u") for seed in (9001, 9002)
    ]
    assert all(c.subdir is None for c in cells)  # type: ignore[attr-defined]
    assert cell_paths(cells[0], Path("/out"))["report"].parent == Path("/out")
    assert (
        gate_mismatches(
            plan,
            engine_sha=SHA,
            engine_dirty=False,
            image_digest=DIGEST,
            observer_integrity_policy="invalid-continue",
        )
        == ()
    )
    assert plan.analysis_plan()["confirmatory_test"] is None


def test_multi_target_plan_cells_gate_and_per_target_evidence_dirs(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None
) -> None:
    ledger, sha = _ledger(tmp_path)
    plan = _plan(_targets_file(tmp_path, ledger_sha=sha))
    assert plan.multi_target
    assert [t.target_id for t in plan.targets()] == ["node-tar-7.5.2", "node-tar-7.9.9"]
    cells = plan.cells()
    ids = [c.run_id for c in cells]
    assert sorted(ids[:6]) == sorted(
        f"node-tar-7.5.2-{a}-s{s}" for a in ("R", "D", "S-u") for s in (9001, 9002)
    )
    assert sorted(ids[6:]) == sorted(
        f"node-tar-7.9.9-{a}-s{s}" for a in ("R", "S-u") for s in (9001, 9002)
    )
    holdout = cells[-1]
    assert holdout.budget == 4 and holdout.version == "7.9.9"
    assert holdout.subdir == "node-tar-7.9.9"  # type: ignore[attr-defined]
    paths = cell_paths(holdout, tmp_path / "out")
    assert paths["report"].parent == tmp_path / "out" / "node-tar-7.9.9"
    assert paths["summary"].parent == tmp_path / "out" / "summaries"
    env = exp0_cell_env(plan, holdout, tmp_path / "out", {})
    assert env["INODEFENCE_EVIDENCE_DIR"] == str(tmp_path / "out" / "node-tar-7.9.9")
    assert env["TAR_VERSION"] == "7.9.9" and env["DEMO_BUDGET"] == "4"
    ledger_state = run_exp0.read_ledger(ledger)
    ok = gate_mismatches(
        plan,
        engine_sha=SHA,
        engine_dirty=False,
        image_digest=None,
        observer_integrity_policy="invalid-continue",
        target_digests={"node-tar-7.5.2": DIGEST, "node-tar-7.9.9": DIGEST_B},
        ledger=ledger_state,
    )
    assert ok == ()
    missing = gate_mismatches(
        plan,
        engine_sha=SHA,
        engine_dirty=False,
        image_digest=None,
        observer_integrity_policy="invalid-continue",
        target_digests={"node-tar-7.5.2": DIGEST},
        ledger=ledger_state,
    )
    assert missing == ("target node-tar-7.9.9 image digest not supplied",)
    wrong = gate_mismatches(
        plan,
        engine_sha=SHA,
        engine_dirty=False,
        image_digest=None,
        observer_integrity_policy="invalid-continue",
        target_digests={"node-tar-7.5.2": DIGEST, "node-tar-7.9.9": DIGEST},
        ledger=ledger_state,
    )
    assert any("target node-tar-7.9.9 image digest" in item for item in wrong)
    no_ledger = gate_mismatches(
        plan,
        engine_sha=SHA,
        engine_dirty=False,
        image_digest=None,
        observer_integrity_policy="invalid-continue",
        target_digests={"node-tar-7.5.2": DIGEST, "node-tar-7.9.9": DIGEST_B},
        ledger=(None, None),
    )
    assert no_ledger == ("exposure ledger exposure-ledger.md not readable",)
    assert plan.analysis_plan()["confirmatory_test"] == "exact-logrank-permutation-v1"
    assert wiring_problems_for(plan) == ()


def wiring_problems_for(plan):
    from scripts.run_exp0 import wiring_problems

    return wiring_problems(plan)


def test_holdout_listed_in_the_ledger_is_refused_at_the_gate(tmp_path: Path) -> None:
    exposed = LEDGER_TEXT + "| node-tar | 7.9.9 | pre-exposed-seed |\n"
    ledger, sha = _ledger(tmp_path, exposed)
    plan = _plan(_targets_file(tmp_path, ledger_sha=sha))
    problems = gate_mismatches(
        plan,
        engine_sha=SHA,
        engine_dirty=False,
        image_digest=None,
        observer_integrity_policy="invalid-continue",
        target_digests={"node-tar-7.5.2": DIGEST, "node-tar-7.9.9": DIGEST_B},
        ledger=run_exp0.read_ledger(ledger),
    )
    assert problems == ("holdout target node-tar-7.9.9 (node-tar 7.9.9) is in the exposure ledger",)
    stale = gate_mismatches(
        plan,
        engine_sha=SHA,
        engine_dirty=False,
        image_digest=None,
        observer_integrity_policy="invalid-continue",
        target_digests={"node-tar-7.5.2": DIGEST, "node-tar-7.9.9": DIGEST_B},
        ledger=(LEDGER_TEXT, "0" * 64),
    )
    assert stale[0].startswith("exposure ledger sha256 0000")


def test_qualification_only_holdout_passes_the_gate(tmp_path: Path) -> None:
    checked = LEDGER_TEXT + "| node-tar | 7.9.9 | qualification-only |\n"
    ledger, sha = _ledger(tmp_path, checked)
    file = _targets_file(tmp_path, ledger_sha=sha)
    file.write_text(
        file.read_text(encoding="utf-8").replace(
            "targets.node-tar-7.9.9.exposure = none\n",
            "targets.node-tar-7.9.9.exposure = qualification-only\n"
            "targets.node-tar-7.9.9.exposure_ref = node-tar@7.9.9\n",
        ),
        encoding="utf-8",
    )
    problems = gate_mismatches(
        _plan(file),
        engine_sha=SHA,
        engine_dirty=False,
        image_digest=None,
        observer_integrity_policy="invalid-continue",
        target_digests={"node-tar-7.5.2": DIGEST, "node-tar-7.9.9": DIGEST_B},
        ledger=run_exp0.read_ledger(ledger),
    )
    assert problems == ()


# ---- execution deadline (D041) ---------------------------------------------------------------

DEADLINE_TEXT = "2026-11-25T12:00:00+09:00"
DEADLINE = datetime(2026, 11, 25, 3, 0, tzinfo=UTC)
BEFORE, AFTER = DEADLINE - timedelta(seconds=1), DEADLINE + timedelta(seconds=1)
TARGET_IMAGES = {"image_id_by_target": {"node-tar-7.5.2": DIGEST, "node-tar-7.9.9": DIGEST_B}}


def _deadline_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, now: datetime, *, jobs: str = "2"
) -> tuple[Path, list[str], dict[str, datetime]]:
    """A targets registration with a deadline, its live arguments, and a clock tests can move."""
    ledger, sha = _ledger(tmp_path)
    file = _targets_file(tmp_path, ledger_sha=sha)
    file.write_text(
        file.read_text(encoding="utf-8").replace(
            "event_threshold = 5\n",
            f"event_threshold = 5\n{EXP3_EXTRA}execution_deadline = {DEADLINE_TEXT}\n",
        ),
        encoding="utf-8",
    )
    out = tmp_path / "exp3"
    base = [a for a in _target_args(file, out, ledger) if a != "--no-manifest"]
    args = [*base, *_manifest_args(tmp_path), "--jobs", jobs]
    clock = {"now": now}
    monkeypatch.setattr(run_exp0, "_now", lambda: clock["now"])
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    return out, args, clock


def _forget_cell(out: Path, run_id: str, plan: Exp0Plan) -> None:
    """Leave a planned cell with no record at all, as if it never started."""
    cell = next(c for c in plan.cells() if c.run_id == run_id)
    paths = cell_paths(cell, out)
    for key in ("report", "steps_jsonl", "log"):
        paths[key].unlink()
    matrix = json.loads((out / "matrix.json").read_text())
    matrix["cells"] = [c for c in matrix["cells"] if c["run_id"] != run_id]
    (out / "matrix.json").write_text(json.dumps(matrix))


def _index(out: Path) -> dict[str, Any]:
    return json.loads((out / "summaries" / "index.json").read_text())


def _deadline_plan(args: list[str]) -> Exp0Plan:
    return _plan(Path(args[args.index("--preregistration") + 1]))


def test_deadline_instant_is_compared_across_offsets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _out, args, clock = _deadline_setup(tmp_path, monkeypatch, DEADLINE)
    plan = _deadline_plan(args)
    assert plan.preregistration.execution_deadline == DEADLINE
    assert run_exp0.deadline_passed(plan) is False  # the instant itself is still on time
    clock["now"] = DEADLINE + timedelta(microseconds=1)
    assert run_exp0.deadline_passed(plan) is True
    clock["now"] = DEADLINE - timedelta(microseconds=1)
    assert run_exp0.deadline_passed(plan) is False
    # The same instant written at another offset.
    clock["now"] = datetime(2026, 11, 25, 12, 0, 1, tzinfo=timezone(timedelta(hours=9)))
    assert run_exp0.deadline_passed(plan) is True


def test_no_deadline_leaves_every_record_as_it_was(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger, sha = _ledger(tmp_path)
    out = tmp_path / "exp3"
    args = _target_args(_targets_file(tmp_path, ledger_sha=sha), out, ledger)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    assert main(args) == 0
    assert "deadline" not in _index(out)
    assert "execution_deadline" not in json.loads((out / "registration.json").read_text())


def test_dry_run_shows_the_deadline(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch, capsys
) -> None:
    _out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    assert main([*args, "--dry-run"]) == 0
    assert f"execution_deadline={DEADLINE_TEXT}" in capsys.readouterr().out


def test_before_the_deadline_an_unfinished_cell_keeps_outcomes_hidden(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    assert main(args) == 0
    index = _index(out)
    assert index["outcomes_redacted"] is False
    assert index["deadline"] == {
        "execution_deadline": DEADLINE_TEXT,
        "passed": False,
        "excluded_seeds": {},
        "causes": {},
    }
    _forget_cell(out, "node-tar-7.9.9-R-s9002", _deadline_plan(args))
    assert main([*args, "--summarize-only"]) == 1
    index = _index(out)
    assert index["outcomes_redacted"] is True
    assert index["interim"]["reasons"][0].startswith("1 cell(s) unattempted")
    assert index["deadline"]["passed"] is False and index["deadline"]["excluded_seeds"] == {}
    assert all(c["summary"] is None and "t_first" not in c for c in index["cells"])


def test_after_the_deadline_outcomes_open_and_the_whole_seed_is_named(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    assert main(args) == 0
    _forget_cell(out, "node-tar-7.9.9-R-s9002", _deadline_plan(args))
    clock["now"] = AFTER
    assert main([*args, "--summarize-only"]) == 1  # not all complete, but published
    index = _index(out)
    assert index["outcomes_redacted"] is False and index["interim"]["reasons"] == []
    assert index["interim"]["states"]["unattempted"] == 1
    assert index["deadline"] == {
        "execution_deadline": DEADLINE_TEXT,
        "passed": True,
        "excluded_seeds": {"node-tar-7.9.9": [9002]},
        "causes": {"node-tar-7.9.9-R-s9002": "unattempted"},
    }
    published = [c for c in index["cells"] if c["run_id"] != "node-tar-7.9.9-R-s9002"]
    assert all("t_first" in c and c["summary"] for c in published)


def test_no_flag_can_open_outcomes_before_the_deadline(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, DEADLINE)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    assert main(args) == 0
    _forget_cell(out, "node-tar-7.5.2-D-s9001", _deadline_plan(args))
    assert main([*args, "--summarize-only"]) == 1  # exactly at the deadline: still hidden
    assert _index(out)["outcomes_redacted"] is True


def test_an_integrity_problem_keeps_outcomes_hidden_after_the_deadline(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    assert main(args) == 0
    plan = _deadline_plan(args)
    paths = cell_paths(plan.cells()[1], out)
    records = [json.loads(line) for line in paths["steps_jsonl"].read_text().splitlines()]
    records[0]["oracle"] = {"C0": True, "C1": True, "C2": True}  # disagrees with the report
    paths["steps_jsonl"].write_text("".join(json.dumps(r) + "\n" for r in records))
    clock["now"] = AFTER
    assert main([*args, "--summarize-only"]) == 1
    index = _index(out)
    assert index["outcomes_redacted"] is True
    assert index["interim"]["reasons"][0].startswith("evidence integrity:")


def test_no_cell_starts_after_the_deadline_and_records_stay_in_place(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    aborted, unfinished = "node-tar-7.5.2-D-s9002", "node-tar-7.9.9-R-s9001"
    out, args, clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    behaviour = {**TARGET_IMAGES, "abort": {aborted}}
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(behaviour))
    assert main(args) == 1
    _forget_cell(out, unfinished, _deadline_plan(args))
    report = _cell(args, aborted, out)["report"]
    before = report.read_bytes()

    def no_warmup(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("nothing runs after the deadline, so nothing warms up")

    late_runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "_warmup", no_warmup)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", late_runner)
    clock["now"] = AFTER
    assert main(args) == 1
    assert late_runner.calls == []  # type: ignore[attr-defined]
    assert report.read_bytes() == before  # the abort record was not moved or replaced
    assert not (out / "attempts").exists()
    assert json.loads((out / "matrix.json").read_text())["cells_not_started"] == [unfinished]
    deadline = _index(out)["deadline"]
    # An abort that ended in time is finished: only the cell with no record excludes its seed.
    assert deadline["causes"] == {unfinished: "unattempted"}
    assert deadline["excluded_seeds"] == {"node-tar-7.9.9": [9001]}


def _cell(args: list[str], run_id: str, out: Path) -> dict[str, Path]:
    cell = next(c for c in _deadline_plan(args).cells() if c.run_id == run_id)
    return cell_paths(cell, out)


def _result_lines(out: Path) -> list[dict[str, Any]]:
    path = out / "cell-results.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _rewrite_results(out: Path, lines: list[dict[str, Any]]) -> None:
    (out / "cell-results.jsonl").write_text(
        "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines), encoding="utf-8"
    )


def test_deadline_exclusion_is_the_same_across_summaries_as_a_late_cell_ends(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    """Restarts and repeated summaries read the exit record, so the excluded set cannot move."""
    victim = "node-tar-7.5.2-D-s9002"
    out, args, clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    assert main(args) == 0
    lines = _result_lines(out)
    end = next(row for row in lines if row["run_id"] == victim and row["event"] == "end")
    _rewrite_results(out, [row for row in lines if row is not end])  # still running at 12:00
    clock["now"] = AFTER
    assert main([*args, "--summarize-only"]) == 1
    first = _index(out)["deadline"]
    assert first["causes"] == {victim: "not-ended-by-deadline"}
    assert first["excluded_seeds"] == {"node-tar-7.5.2": [9002]}
    end["clocks"]["realtime"] = AFTER.timestamp()  # it ends between the two summaries
    _rewrite_results(out, [*_result_lines(out), end])
    assert main([*args, "--summarize-only"]) == 0
    second = _index(out)["deadline"]
    assert second["causes"] == {victim: "ended-after-deadline"}
    assert second["excluded_seeds"] == first["excluded_seeds"]


# ---- exit record and record checks of the targets form (D041 item 3) -------------------------

VICTIM = "node-tar-7.5.2-D-s9001"


def _runner_with(special: dict[str, Any]) -> Any:
    """The fake runner, with some cells replaced by a function that post-processes their files."""
    inner = _fake_runner(TARGET_IMAGES)

    def run(cell: Any, output: Path, env: dict[str, str], bash: str, **limits: Any) -> Any:
        result = inner(cell, output, env, bash, **limits)
        action = special.get(cell.run_id)
        return result if action is None else action(cell, output, result)

    run.calls = inner.calls  # type: ignore[attr-defined]
    return run


def _dies_without_a_record(cell: Any, output: Path, result: Any) -> Any:
    paths = cell_paths(cell, output)
    paths["report"].unlink()
    paths["steps_jsonl"].unlink()
    return replace(result, returncode=1, evidence_exists=False)


def _killed(keep: int, *, torn: int = 0, flag: bool = True) -> Any:
    """Terminated with no report: ``keep`` whole step lines, then ``torn`` cut ones."""

    def action(cell: Any, output: Path, result: Any) -> Any:
        paths = cell_paths(cell, output)
        lines = paths["steps_jsonl"].read_text(encoding="utf-8").splitlines()
        cut = [lines[keep + position][:20] for position in range(torn)]
        paths["steps_jsonl"].write_text("\n".join([*lines[:keep], *cut]) + "\n", encoding="utf-8")
        paths["report"].unlink()
        return replace(
            result, returncode=WATCHDOG_RETURNCODE, watchdog_fired=flag, evidence_exists=False
        )

    return action


def _state(out: Path, run_id: str = VICTIM) -> str:
    return _index(out)["interim"]["cell_states"][run_id]


def _digest(*paths: Path) -> list[str]:
    return [sha256(path.read_bytes()).hexdigest() for path in paths]


def test_each_attempt_writes_start_and_end_with_three_clocks_and_no_outcome(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    assert main(args) == 0
    lines = _result_lines(out)
    cells = _deadline_plan(args).cells()
    assert len(lines) == 2 * len(cells)
    clocks = {"realtime", "monotonic", "monotonic_raw"}
    for line in lines:
        assert set(line["clocks"]) == clocks and line["attempt"] == 1
        common = {"event", "run_id", "attempt", "clocks"}
        extra = {"returncode", "watchdog_fired", "wall_seconds"}
        assert set(line) == (common | extra if line["event"] == "end" else common | {"jobs"})
    # Not a result: it lets a resume be compared with the call it continues.
    assert {row["jobs"] for row in lines if row["event"] == "start"} == {2}
    assert all(row["watchdog_fired"] is False for row in lines if row["event"] == "end")
    assert all(row["returncode"] == 0 for row in lines if row["event"] == "end")


def test_single_key_form_keeps_its_records_and_states(
    exp3_file: Path, tmp_path: Path, clean_engine: None, monkeypatch
) -> None:
    out = tmp_path / "exp3"
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner({}))
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    assert main(_interim_args(exp3_file, out, tmp_path)) == 0
    assert not (out / "cell-results.jsonl").exists()
    index = _index(out)
    assert "cell_completeness" not in index
    assert set(index["interim"]["states"]) == set(run_exp0.CELL_STATES)
    assert "cells_not_started" not in json.loads((out / "matrix.json").read_text())


def test_a_record_is_final_across_two_restarts(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    aborted, inconsistent = VICTIM, "node-tar-7.5.2-R-s9002"
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    behaviour = {**TARGET_IMAGES, "abort": {aborted}}
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(behaviour))
    assert main(args) == 1
    paths = _cell(args, inconsistent, out)
    paths["steps_jsonl"].write_text("not json\n", encoding="utf-8")
    files = [
        *(_cell(args, aborted, out)[key] for key in ("report", "steps_jsonl")),
        paths["report"],
        paths["steps_jsonl"],
    ]
    before, lines = _digest(*files), _result_lines(out)
    restart = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", restart)
    for _ in range(2):
        assert main(args) == 1
        assert restart.calls == []  # type: ignore[attr-defined]
        assert _digest(*files) == before and _result_lines(out) == lines
        assert not (out / "attempts").exists()
    assert _state(out, aborted) == "abort-final"
    assert _state(out, inconsistent) == "record-inconsistent"


def test_a_cell_with_no_record_retries_at_once_in_its_place_and_then_is_no_record(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    runner = _runner_with({VICTIM: _dies_without_a_record})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    assert _state(out) == "no-record"  # one call: no later invocation is needed
    position = runner.calls.index(VICTIM)
    assert runner.calls[position + 1] == VICTIM  # the retry comes before the next cell
    assert main(args) == 1  # no third start
    assert runner.calls.count(VICTIM) == 2
    starts = [r for r in _result_lines(out) if r["run_id"] == VICTIM and r["event"] == "start"]
    assert [row["attempt"] for row in starts] == [1, 2]
    assert (out / "attempts" / f"{VICTIM}.attempt1.log").is_file()  # the first attempt's file
    summary = _index(out)["cell_completeness"]
    assert summary["no_record"] == 1 and summary["aborts"] == 1
    assert summary["infrastructure_stops"] == []
    entry = next(c for c in _index(out)["cells"] if c["run_id"] == VICTIM)
    assert entry["invalid"] is True  # T_first: leaves the contrast; counted as an abort


def test_a_retry_that_leaves_a_record_ends_the_cell(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    actions = [_dies_without_a_record]

    def first_attempt_only(cell: Any, output: Path, result: Any) -> Any:
        return actions.pop()(cell, output, result) if actions else result

    runner = _runner_with({VICTIM: first_attempt_only})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 0
    assert _state(out) == "complete" and runner.calls.count(VICTIM) == 2


def test_a_start_without_an_end_counts_as_an_attempt(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    """A launcher that keeps dying before the cell writes anything cannot retry for ever."""
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    out.mkdir()
    _rewrite_results(
        out, [{"event": "start", "run_id": VICTIM, "attempt": n, "clocks": {}} for n in (1, 2)]
    )
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    assert VICTIM not in runner.calls  # type: ignore[attr-defined]
    assert _state(out) == "no-record"


def test_one_earlier_attempt_leaves_exactly_one_more(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    out.mkdir()
    _rewrite_results(out, [{"event": "start", "run_id": VICTIM, "attempt": 1, "clocks": {}}])
    runner = _runner_with({VICTIM: _dies_without_a_record})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    assert runner.calls.count(VICTIM) == 1 and _state(out) == "no-record"


def test_three_cells_in_a_row_with_no_record_stop_new_cells(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    """A dead Docker must not use up every waiting cell's attempts within minutes."""
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    cells = [cell.run_id for cell in _deadline_plan(args).cells()]
    runner = _runner_with(dict.fromkeys(cells, _dies_without_a_record))
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    assert runner.calls == [run_id for run_id in cells[:3] for _ in range(2)]
    lines = _result_lines(out)
    started = {row["run_id"] for row in lines if row["event"] == "start"}
    assert started == set(cells[:3])  # a cell not started uses no attempt
    assert json.loads((out / "matrix.json").read_text())["cells_not_started"] == sorted(cells[3:])
    index = _index(out)
    states = index["interim"]["cell_states"]
    assert [states[run_id] for run_id in cells[:3]] == ["no-record"] * 3
    assert {states[run_id] for run_id in cells[3:]} == {"unattempted"}
    stops = index["cell_completeness"]["infrastructure_stops"]
    assert len(stops) == 1 and "3 consecutive cells left no record" in stops[0]["reason"]
    assert set(stops[0]["clocks"]) == {"realtime", "monotonic", "monotonic_raw"}
    assert index["outcomes_redacted"] is True  # the waiting cells still hide outcomes
    assert index["cell_completeness"]["infrastructure_stopped"] is True
    # Nothing was deleted: the first attempts are kept and the last attempts stay in place.
    for run_id in cells[:3]:
        assert (out / "attempts" / f"{run_id}.attempt1.log").is_file()
        assert _cell(args, run_id, out)["log"].is_file()
    # A later call starts nothing by itself and changes no record.
    fresh = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", fresh)
    before = _result_lines(out)
    assert main(args) == 1
    assert fresh.calls == []  # type: ignore[attr-defined]
    assert _result_lines(out) == before
    assert json.loads((out / "matrix.json").read_text())["cells_not_started"] == sorted(cells[3:])
    assert _index(out)["cell_completeness"]["infrastructure_stopped"] is True
    # A resume needs the operator's reference; the waiting cells still have both attempts.
    assert main([*args, "--resume-after-stop", "jiwoong-cause-found"]) == 1
    assert sorted(fresh.calls) == sorted(cells[3:])  # type: ignore[attr-defined]
    summary = _index(out)["cell_completeness"]
    assert summary["infrastructure_stopped"] is False
    assert summary["infrastructure_resumes"][0]["approval_ref"] == "jiwoong-cause-found"
    assert set(summary["infrastructure_resumes"][0]["clocks"]) == set(stops[0]["clocks"])
    assert [_index(out)["interim"]["cell_states"][run_id] for run_id in cells[:3]] == [
        "no-record"
    ] * 3  # a resume does not give used attempts back


@pytest.mark.parametrize("reference", ["some-reference", "   "])
def test_a_resume_needs_a_stop_and_a_reference(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch, reference: str
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main([*args, "--resume-after-stop", reference]) == 2  # no stop to resume
    assert runner.calls == []  # type: ignore[attr-defined]
    assert not (out / "cell-results.jsonl").exists()


def test_an_empty_reference_cannot_resume_a_real_stop(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    out.mkdir()
    _rewrite_results(out, [{"event": "infrastructure-stop", "reason": "why", "clocks": {}}])
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main([*args, "--resume-after-stop", " "]) == 2
    assert runner.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize("mode", ["--summarize-only", "--dry-run"])
def test_a_resume_cannot_go_with_a_mode_that_runs_no_cell(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch, mode: str
) -> None:
    _out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    with pytest.raises(SystemExit):
        main([*args, "--resume-after-stop", "ref", mode])


def test_a_failed_warmup_on_resume_leaves_the_stop_in_force(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    """If docker is still down the resume never happened: the next plain call starts nothing."""
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    out.mkdir()
    _rewrite_results(out, [{"event": "infrastructure-stop", "reason": "why", "clocks": {}}])
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 7)
    assert main([*args, "--resume-after-stop", "ref"]) == 7
    assert [row["event"] for row in _result_lines(out)] == ["infrastructure-stop"]
    assert runner.calls == []  # type: ignore[attr-defined]
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    assert main(args) == 1  # no flag: still stopped
    assert runner.calls == []  # type: ignore[attr-defined]
    assert main([*args, "--resume-after-stop", "ref"]) == 0
    assert [row["event"] for row in _result_lines(out)][:2] == [
        "infrastructure-stop",
        "infrastructure-resume",
    ]


def test_a_stop_during_a_first_attempt_blocks_its_retry_until_a_resume(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    """Not left to timing: the first attempt ends with no record only after the stop is written."""
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    cells = [cell.run_id for cell in _deadline_plan(args).cells()]
    waiting = cells[0]

    def ends_with_no_record_after_the_stop(cell: Any, output: Path, result: Any) -> Any:
        deadline = monotonic() + 30
        path = out / "cell-results.jsonl"
        while "infrastructure-stop" not in path.read_text(encoding="utf-8"):
            assert monotonic() < deadline, "the stop never came"
            sleep(0.01)
        return _dies_without_a_record(cell, output, result)

    special: dict[str, Any] = dict.fromkeys(cells[1:], _dies_without_a_record)
    special[waiting] = ends_with_no_record_after_the_stop
    runner = _runner_with(special)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    assert runner.calls.count(waiting) == 1  # no second attempt after the stop
    starts = [r for r in _result_lines(out) if r.get("run_id") == waiting and r["event"] == "start"]
    assert [row["attempt"] for row in starts] == [1]
    assert _index(out)["interim"]["cell_states"][waiting] == "unattempted"
    assert waiting in json.loads((out / "matrix.json").read_text())["cells_not_started"]
    # Its one remaining attempt is used exactly once after the resume.
    fresh = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", fresh)
    assert main([*args, "--resume-after-stop", "ref"]) == 1
    assert fresh.calls.count(waiting) == 1  # type: ignore[attr-defined]
    starts = [r for r in _result_lines(out) if r.get("run_id") == waiting and r["event"] == "start"]
    assert [row["attempt"] for row in starts] == [1, 2]
    assert _index(out)["interim"]["cell_states"][waiting] == "complete"


def test_two_jobs_with_every_cell_dying_stop_within_the_registered_counts(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    """The stop-path smoke's expectations: started cells = no-record cells + first-attempt cells."""
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    cells = [cell.run_id for cell in _deadline_plan(args).cells()]
    runner = _runner_with(dict.fromkeys(cells, _dies_without_a_record))
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    started = {r["run_id"] for r in _result_lines(out) if r["event"] == "start"}
    states = _index(out)["interim"]["cell_states"]
    no_record = {run_id for run_id in cells if states[run_id] == "no-record"}
    first_only = started - no_record
    assert len(started) in (3, 4) and len(no_record) in (3, 4) and len(first_only) in (0, 1)
    assert len(started) == len(no_record) + len(first_only)
    assert all(states[run_id] == "unattempted" for run_id in first_only)
    assert _index(out)["cell_completeness"]["no_record"] == len(no_record)


def test_a_running_cell_finishes_after_the_stop_and_keeps_its_record(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    cells = [cell.run_id for cell in _deadline_plan(args).cells()]
    long_running = cells[0]

    def stop_written() -> bool:
        path = out / "cell-results.jsonl"
        return path.is_file() and "infrastructure-stop" in path.read_text(encoding="utf-8")

    def waits_for_the_stop(_cell_: Any, _output: Path, result: Any) -> Any:
        deadline = monotonic() + 30
        while not stop_written():
            assert monotonic() < deadline, "the stop never came"
            sleep(0.01)
        return result

    special: dict[str, Any] = dict.fromkeys(cells, _dies_without_a_record)
    special[long_running] = waits_for_the_stop
    runner = _runner_with(special)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1  # two jobs: one slot waits while the other reaches the stop
    assert _index(out)["interim"]["cell_states"][long_running] == "complete"
    assert _cell(args, long_running, out)["report"].is_file()
    lines = _result_lines(out)
    stop_at = next(i for i, row in enumerate(lines) if row["event"] == "infrastructure-stop")
    end_at = next(
        i
        for i, row in enumerate(lines)
        if row.get("run_id") == long_running and row["event"] == "end"
    )
    assert stop_at < end_at  # it ended after the stop, and the stop stands
    summary = _index(out)["cell_completeness"]
    assert summary["infrastructure_stopped"] is True and len(summary["infrastructure_stops"]) == 1
    assert len(set(runner.calls)) == 4  # the waiting cell and three with no record


def test_a_recorded_cell_resets_the_no_record_streak(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    cells = [cell.run_id for cell in _deadline_plan(args).cells()]
    dying = [cells[0], cells[1], cells[3], cells[4]]  # never three in a row
    runner = _runner_with(dict.fromkeys(dying, _dies_without_a_record))
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    assert set(runner.calls) == set(cells)
    assert _index(out)["cell_completeness"]["infrastructure_stops"] == []


def test_a_record_without_an_exit_line_is_inconsistent_and_not_rerun(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    assert main(args) == 0
    lines = _result_lines(out)
    _rewrite_results(
        out, [row for row in lines if not (row["run_id"] == VICTIM and row["event"] == "end")]
    )
    restart = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", restart)
    assert main(args) == 1
    assert restart.calls == []  # type: ignore[attr-defined]
    assert _state(out) == "record-inconsistent"
    assert _index(out)["cell_completeness"]["inconsistent_checks"] == {VICTIM: ["no-exit-record"]}


def test_a_watchdog_cell_is_an_abort_and_its_cut_last_line_is_of_unknown_outcome(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    runner = _runner_with({VICTIM: _killed(2, torn=1)})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    assert _state(out) == "abort-final"
    index = _index(out)
    summary = index["cell_completeness"]
    assert summary["watchdog"] == 1 and summary["aborts"] == 1
    assert summary["unknown_outcome_steps"] == 1
    entry = next(c for c in index["cells"] if c["run_id"] == VICTIM)
    assert entry["invalid"] is False and entry["aborted"] is True
    record = json.loads((out / "summaries" / f"{VICTIM}.summary.json").read_text())
    assert record["unknown_outcome_steps"] == 1
    assert record["summary"]["executions_completed"] == 2  # the cut line's step is not counted
    assert "watchdog" in record["summary"]["abort_reason"]
    assert main(args) == 1
    assert runner.calls.count(VICTIM) == 1  # final: no retry


def test_a_whole_last_line_in_a_watchdog_cell_is_kept(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _runner_with({VICTIM: _killed(3)}))
    assert main(args) == 1
    assert _state(out) == "abort-final"
    assert _index(out)["cell_completeness"]["unknown_outcome_steps"] == 0
    record = json.loads((out / "summaries" / f"{VICTIM}.summary.json").read_text())
    assert record["summary"]["executions_completed"] == 3


def test_the_new_record_fields_exist_only_in_unredacted_summary_files(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    """Both hold outcomes (a boundary key, an event in the prefix): the seal must cover them."""
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    monkeypatch.setattr(
        run_exp0, "run_cell_with_watchdog", _runner_with({VICTIM: _killed(2, torn=2)})
    )
    assert main(args) == 1
    plan = _deadline_plan(args)
    other = next(cell.run_id for cell in plan.cells() if cell.run_id != VICTIM)
    index_path = out / "summaries" / "index.json"
    # Not hidden: the cell's own summary file has them, and the index never does.
    assert _index(out)["outcomes_redacted"] is False
    damaged = json.loads(_cell(args, VICTIM, out)["summary"].read_text(encoding="utf-8"))
    assert damaged["record_inconsistent_prefix"]["steps"] == 2
    plain = json.loads(_cell(args, other, out)["summary"].read_text(encoding="utf-8"))
    assert plain["dense_detail"]["recorded_steps"] > 0
    assert b"dense_detail" not in index_path.read_bytes()
    assert b"record_inconsistent_prefix" not in index_path.read_bytes()
    # A cell goes unfinished, so outcomes are hidden: nothing under the output may hold them.
    _forget_cell(out, other, plan)
    _rewrite_results(out, [row for row in _result_lines(out) if row.get("run_id") != other])
    assert main([*args, "--summarize-only"]) == 1
    assert _index(out)["outcomes_redacted"] is True
    assert not list((out / "summaries").glob("*.summary.json"))
    for path in out.rglob("*"):
        if path.is_file():
            assert b"dense_detail" not in path.read_bytes(), path
            assert b"record_inconsistent_prefix" not in path.read_bytes(), path


def test_two_cut_lines_in_a_watchdog_cell_are_inconsistent(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    monkeypatch.setattr(
        run_exp0, "run_cell_with_watchdog", _runner_with({VICTIM: _killed(2, torn=2)})
    )
    assert main(args) == 1
    assert _state(out) == "record-inconsistent"


def test_a_watchdog_cell_with_no_whole_line_has_no_record_and_keeps_its_file(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    actions = [_killed(0, torn=1)]
    originals: list[bytes] = []

    def first_attempt_only(cell: Any, output: Path, result: Any) -> Any:
        if not actions:
            return result
        killed = actions.pop()(cell, output, result)
        originals.append(cell_paths(cell, output)["steps_jsonl"].read_bytes())
        return killed

    runner = _runner_with({VICTIM: first_attempt_only})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 0  # the retry in the same call completes
    assert _state(out) == "complete"
    assert (out / "attempts" / f"{VICTIM}.attempt1.steps.jsonl").read_bytes() == originals[0]


def test_a_cut_line_alone_without_the_watchdog_is_inconsistent_and_not_retried(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    runner = _runner_with({VICTIM: _killed(0, torn=1, flag=False)})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    assert _state(out) == "record-inconsistent" and runner.calls.count(VICTIM) == 1


def test_two_cut_lines_alone_with_the_watchdog_are_inconsistent_and_not_retried(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    runner = _runner_with({VICTIM: _killed(0, torn=2)})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    assert _state(out) == "record-inconsistent" and runner.calls.count(VICTIM) == 1
    assert _index(out)["cell_completeness"]["watchdog"] == 0


def test_an_outside_sigterm_is_inconsistent_not_a_watchdog_abort(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    """Exit code -15 with the flag false and no report: a record, but one that does not hold."""
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    runner = _runner_with({VICTIM: _killed(2, flag=False)})
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert main(args) == 1
    assert _state(out) == "record-inconsistent"
    index = _index(out)
    assert index["cell_completeness"]["watchdog"] == 0
    assert index["cell_completeness"]["inconsistent_checks"] == {
        VICTIM: ["no-report-and-no-watchdog"]
    }
    entry = next(c for c in index["cells"] if c["run_id"] == VICTIM)
    assert entry["invalid"] is True
    assert main(args) == 1
    assert runner.calls.count(VICTIM) == 1


def test_an_inconsistent_record_does_not_hide_outcomes_and_counts_as_a_failure(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    behaviour = {**TARGET_IMAGES, "abort": {"node-tar-7.5.2-R-s9001"}}
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(behaviour))
    assert main(args) == 1
    _cell(args, VICTIM, out)["steps_jsonl"].write_text("not json\n", encoding="utf-8")
    assert main([*args, "--summarize-only"]) == 1
    index = _index(out)
    assert index["outcomes_redacted"] is False and index["interim"]["integrity_problems"] == []
    summary = index["cell_completeness"]
    cells = len(_deadline_plan(args).cells())
    assert (summary["aborts"], summary["record_inconsistent"]) == (1, 1)
    assert summary["aborts_plus_inconsistent"] == 2
    assert summary["infrastructure_failure_rate"] == pytest.approx(2 / cells)
    record = json.loads((out / "summaries" / f"{VICTIM}.summary.json").read_text())
    assert record["config_nonconformant"] is True
    assert "record-inconsistent" in record["invalid_reason"]


def test_finalize_abort_is_refused_in_the_targets_form(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    _out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    behaviour = {**TARGET_IMAGES, "abort": {VICTIM}}
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(behaviour))
    assert main(args) == 1
    with pytest.raises(SystemExit, match="refused for a targets"):
        main([*args, "--finalize-abort", VICTIM, "--summarize-only"])


def test_a_cell_running_across_the_deadline_finishes_and_excludes_its_seed(
    tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    out, args, clock = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    inner = _fake_runner(TARGET_IMAGES)

    def crossing(cell: Any, *rest: Any, **limits: Any) -> Any:
        result = inner(cell, *rest, **limits)
        clock["now"] = AFTER  # the deadline passes while this one cell runs
        return result

    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", crossing)
    assert main(args) == 1
    cells = _deadline_plan(args).cells()
    first = cells[0]
    assert inner.calls == [first.run_id]  # type: ignore[attr-defined]
    assert cell_paths(first, out)["report"].is_file()  # finished, not killed, record kept
    matrix = json.loads((out / "matrix.json").read_text())
    assert matrix["cells_not_started"] == sorted(c.run_id for c in cells[1:])
    deadline = _index(out)["deadline"]
    assert deadline["causes"][first.run_id] == "ended-after-deadline"
    assert deadline["excluded_seeds"] == {
        "node-tar-7.5.2": [9001, 9002],
        "node-tar-7.9.9": [9001, 9002],
    }


def test_multi_target_dry_run_and_live_run_with_fake_cells(
    tmp_path: Path,
    clean_engine: None,
    admit_fixture_holdout: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    ledger, sha = _ledger(tmp_path)
    file = _targets_file(tmp_path, ledger_sha=sha)
    out = tmp_path / "exp3"
    args = _target_args(file, out, ledger)
    assert main([*args, "--dry-run"]) == 0
    text = capsys.readouterr().out
    assert "gate: PASS" in text and "target node-tar-7.9.9: node-tar 7.9.9 role=holdout" in text
    # --image-digest does not apply to a multi-target registration (and vice versa).
    assert main([*args, "--image-digest", DIGEST, "--dry-run"]) == 2
    assert main([*args[:4], "--target-digest", "garbage", "--dry-run"]) == 2
    runner = _fake_runner(
        {"image_id_by_target": {"node-tar-7.5.2": DIGEST, "node-tar-7.9.9": DIGEST_B}}
    )
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    assert main([*args, "--jobs", "2"]) == 0
    assert sorted(runner.calls) == sorted(  # type: ignore[attr-defined]
        c.run_id for c in _plan(file).cells()
    )
    assert (out / "node-tar-7.9.9").is_dir() and (out / "node-tar-7.5.2").is_dir()
    assert list((out / "node-tar-7.9.9").glob("*.json"))
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert [t["target_id"] for t in index["targets"]] == ["node-tar-7.5.2", "node-tar-7.9.9"]
    assert index["targets"][1]["role"] == "holdout" and index["targets"][1]["budget"] == 4
    assert index["analysis_plan"]["multiplicity"] == "holm-fwer-v1"
    assert index["analysis_plan"]["event_threshold"] == 5
    contrasts = index["analysis_plan"]["confirmatory_contrasts"]
    assert [(c["order"], c["arm_a"], c["arm_b"]) for c in contrasts] == [(1, "S-u", "R")]
    assert all(c["role"] == "holdout" and c["hypothesis"] == "H-A" for c in contrasts)
    holdout_cells = [c for c in index["cells"] if c["target_id"] == "node-tar-7.9.9"]
    assert len(holdout_cells) == 4 and all(c["role"] == "holdout" for c in holdout_cells)
    assert all(c["hypothesis"] == "H-A" and c["budget"] == 4 for c in holdout_cells)
    assert index["g1_verdict"]["complete"] == 10
    record = json.loads((out / "summaries" / "node-tar-7.9.9-R-s9001.summary.json").read_text())
    assert record["target"] == {
        "target_id": "node-tar-7.9.9",
        "role": "holdout",
        "hypothesis": "H-A",
    }
    registration = json.loads((out / "registration.json").read_text())
    assert registration["image_digest"] is None and len(registration["targets"]) == 2
    matrix = json.loads((out / "matrix.json").read_text())
    assert {c["target_id"] for c in matrix["cells"]} == {"node-tar-7.5.2", "node-tar-7.9.9"}


def test_controller_refusals_stop_dry_run_and_live_run_before_warmup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A target the controller would refuse must fail fast, not after earlier targets ran.

    Uses the controller's real allowlist: 7.9.9 is not a catalog-registered target.
    """
    monkeypatch.setattr(run_exp0, "capture_source", lambda: SourceProvenance(SHA, False))
    monkeypatch.setattr(run_exp0, "_script_has", lambda variable: True)

    def no_warmup(*args: object, **kwargs: object) -> int:
        raise AssertionError("warmup must not start")

    monkeypatch.setattr(run_exp0, "_warmup", no_warmup)
    ledger, sha = _ledger(tmp_path)
    file = _targets_file(tmp_path, ledger_sha=sha)
    out = tmp_path / "exp3"
    args = _target_args(file, out, ledger)

    assert main([*args, "--dry-run"]) == 2
    text = capsys.readouterr().out
    assert "gate: PASS" in text  # the registration itself is fine; the controller is not
    assert "- wiring: target node-tar-7.9.9:" in text and "'7.9.9'" in text
    assert "node-tar-7.5.2:" not in text.split("would be refused at live run:")[1].split("plan=")[0]
    assert not out.exists()

    assert main(args) == 2
    err = capsys.readouterr().err
    assert "controller wiring" in err and "'7.9.9'" in err
    assert not list(out.glob("node-tar-*/*.json"))

    # An over-budget target is refused the same way (the controller's own budget check).
    over = file.read_text().replace(
        "targets.node-tar-7.9.9.budget = 4", "targets.node-tar-7.9.9.budget = 2001"
    )
    file.write_text(over.replace("7.9.9", "7.5.3"), encoding="utf-8")
    args = _target_args(file, tmp_path / "over", ledger)
    args[args.index(f"node-tar-7.9.9={DIGEST_B}")] = f"node-tar-7.5.3={DIGEST_B}"
    assert main([*args, "--dry-run"]) == 2
    assert "budget must be in 1..2000" in capsys.readouterr().out

    # A plan the controller admits still passes: 7.5.2 single target, real allowlist.
    file = tmp_path / "single.md"
    file.write_text(BLOCK, encoding="utf-8")
    assert run_exp0.wiring_problems(_plan(file)) == ()
    assert main([*_base_args(file, tmp_path / "single"), "--dry-run"]) == 0


def test_single_key_index_entries_gain_only_default_target_fields(
    prereg_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "exp0"
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner({}))
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    assert main([*_base_args(prereg_file, out), "--jobs", "2"]) == 0
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert all(
        (c["target_id"], c["role"], c["hypothesis"]) == ("7.5.2", "train", "H-A")
        for c in index["cells"]
    )
    assert index["targets"][0]["target_id"] == "7.5.2" and len(index["targets"]) == 1
    assert not any(
        p.is_dir() and p.name != "summaries" and p.name != "attempts" for p in out.iterdir()
    )


# ---- launcher to tables, one registered target (PR-E) ------------------------------------------

ONE_TARGET_TABLES = {
    "holdout": ("T-EXP2-1", "T-EXP2-2", "T-EXP2-3", "T-EXP2-4", "T-EXP2-5", "T-EXP2-6"),
    "train": ("T-EXP3-1", "T-EXP3-2", "T-EXP3-3"),
}
ONE_TARGET_HAND = {
    "abort_split": {
        "target_not_started": 0,
        "lost_after_execution": 0,
        "first_error_unconfirmed": 0,
    },
    "operating_stop": {"fired": False},
}


def _one_target_args(args: list[str], role: str) -> list[str]:
    """A real EXP-3 or EXP-2 registration has one target: the tables refuse several."""
    dropped = "node-tar-7.9.9" if role == "train" else "node-tar-7.5.2"
    file = Path(args[args.index("--preregistration") + 1])
    lines = file.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [
        line
        for line in lines
        if not line.startswith(f"targets.{dropped}.")
        and not (role == "train" and line.startswith("confirmatory_family"))
    ]
    file.write_text("".join(kept), encoding="utf-8")
    result = list(args)
    for index, value in enumerate(result):
        if value.startswith(f"{dropped}="):
            del result[index - 1 : index + 1]
            break
    return result


@pytest.mark.parametrize("role", ["holdout", "train"])
def test_a_launcher_run_feeds_the_analyzer_and_every_table(
    role: str, tmp_path: Path, clean_engine: None, admit_fixture_holdout: None, monkeypatch
) -> None:
    """The real keys, not ones a fixture wrote: launcher index, analyzer report, table text."""
    out, args, clock = _deadline_setup(tmp_path, monkeypatch, DEADLINE - timedelta(hours=10))
    args = _one_target_args(args, role)
    cells = _deadline_plan(args).cells()

    def timed(cell: Any, output: Path, result: Any) -> Any:
        clock["now"] += timedelta(seconds=30)  # the run span must be real for the GO inputs
        paths = cell_paths(cell, output)
        report = json.loads(paths["report"].read_text(encoding="utf-8"))
        report["timing"] = {
            "total_seconds": 10.0,
            "per_case": [{"wall_seconds": 1.0, "target_seconds": 0.5} for _step in report["steps"]],
        }
        paths["report"].write_text(json.dumps(report), encoding="utf-8")
        return result

    monkeypatch.setattr(
        run_exp0,
        "run_cell_with_watchdog",
        _runner_with({cell.run_id: timed for cell in cells}),
    )
    assert main(args) == 0

    report_path = tmp_path / "report.json"
    assert (
        analyze_main(
            ["--index", str(out / "summaries" / "index.json"), "--output", str(report_path)]
        )
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    hand = tmp_path / "hand.json"
    hand.write_text(json.dumps(ONE_TARGET_HAND), encoding="utf-8")
    decision = tmp_path / "decision.json"
    decided_at = (DEADLINE - timedelta(hours=2)).isoformat()
    decision.write_text(json.dumps({"decided_at": decided_at}), encoding="utf-8")
    inputs = gen_exp3_tables.Inputs(report, out / "cell-results.jsonl", hand, decision)
    tables = {name: gen_exp3_tables.render(name, inputs) for name in ONE_TARGET_TABLES[role]}

    # The launcher's cell values are the ones the analyzer's dense table summed.
    budget = 4 if role == "holdout" else 6
    target_id = "node-tar-7.9.9" if role == "holdout" else "node-tar-7.5.2"
    section = report["by_target"][target_id]
    arms = {cell.arm.value for cell in cells}
    assert set(section["dense_signals_registered"]["by_arm"]) == arms
    for arm in arms:
        by_arm = section["dense_signals_registered"]["by_arm"][arm]
        assert by_arm["recorded_steps"] == budget * 2  # two seeds, every cell complete
    for cell in cells:
        record = json.loads(cell_paths(cell, out)["summary"].read_text(encoding="utf-8"))
        keys = record["dense_detail"]["boundary_keys"]
        assert len(keys) == record["summary"]["boundary_attempt_keys"]

    if role == "train":
        assert report["confirmatory"] is None
        text = tables["T-EXP3-2"]
        assert "| e: 기록/계획 step 비율 | 1.000 | 입력 |" in text
        assert "| 시작하지 않은 셀 | 0 | 기록 |" in text
        assert "미산출" not in text and "정지 0회, 누적 공백 0.0 h" in text
        assert f"GO 판정 시각(실시간): {decided_at}" in text
    else:
        contrast = report["confirmatory"]["contrasts"][0]
        assert contrast["contrast"] == "S-u-vs-R" and contrast["number_seed_blocks"] == 2
        assert "| S-u-vs-R | 2 |" in tables["T-EXP2-2"]
        assert "- 운영 중단: 발동 없음" in tables["T-EXP2-3"]
        assert "| S-u | exclude |" in tables["T-EXP2-4"]
        assert "| 실행 수 | 16 |" in tables["T-EXP2-5"]  # two arms, two seeds, budget 4

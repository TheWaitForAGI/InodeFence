"""EXP-0 launcher: gate, dry-run, idempotent rerun and summaries (no Docker)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts import run_exp0
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
        return CellResult(cell, 0, 1.0, paths["report"], True, paths["log"])

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
    assert main([*_base_args(exp3_file, out), "--dry-run"]) == 0  # gate passes; wiring is previewed
    text = capsys.readouterr().out
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
        "confirmatory_family = holdout:S-u-vs-R,S-u-vs-D\n"
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
    tmp_path: Path, clean_engine: None
) -> None:
    ledger, sha = _ledger(tmp_path)
    plan = _plan(_targets_file(tmp_path, ledger_sha=sha))
    assert plan.multi_target
    assert [t.target_id for t in plan.targets()] == ["node-tar-7.5.2", "node-tar-7.9.9"]
    cells = plan.cells()
    ids = [c.run_id for c in cells]
    assert ids[:6] == [f"node-tar-7.5.2-{a}-s{s}" for a in ("R", "D", "S-u") for s in (9001, 9002)]
    assert ids[6:] == [f"node-tar-7.9.9-{a}-s{s}" for a in ("R", "S-u") for s in (9001, 9002)]
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


def test_multi_target_dry_run_and_live_run_with_fake_cells(
    tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch, capsys
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
    assert [(c["order"], c["arm_a"], c["arm_b"]) for c in contrasts] == [
        (1, "S-u", "R"),
        (2, "S-u", "D"),
    ]
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

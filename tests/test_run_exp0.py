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
    Exp0Plan,
    archive_attempt,
    cell_is_complete,
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
        report["image_id"] = behaviour.get("image_id", DIGEST)
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
    manifest_script = tmp_path / "fake_manifest.py"
    manifest_script.write_text(
        "import sys, pathlib\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])\n"
        "out.write_text('fake\\n'); print('ok')\n"
    )
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
    assert runner.calls == [c.run_id for c in _plan(prereg_file).cells()]  # type: ignore[attr-defined]
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["label"][0] == "registered run" and f"engine_sha={SHA}" in index["label"]
    assert "experiment=exp0" in index["label"] and index["outcomes_redacted"] is False
    assert index["preregistration"]["sha256"] == _plan(prereg_file).preregistration_sha256
    assert index["g1_verdict"]["complete"] == 5 and index["g1_verdict"]["aborts"] == 1
    assert index["vocabulary_equal_across_arms"] is True
    registration = json.loads((out / "registration.json").read_text())
    assert registration["raw_manifest"]["generated"] is True and manifest_out.is_file()
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


def test_interim_forbidden_redacts_index_until_every_cell_is_complete(
    exp3_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "exp3"
    monkeypatch.setattr(
        run_exp0, "run_cell_with_watchdog", _fake_runner({"abort": {"7.5.2-S-u-s9002"}})
    )
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    args = [*_base_args(exp3_file, out), "--jobs", "2"]
    assert main(args) == 1
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["outcomes_redacted"] is True and index["interim"]["pending_cells"] == 1
    assert all(
        "hit" not in c and "t_first" not in c and c["summary"] is None for c in index["cells"]
    )
    assert not list((out / "summaries").glob("*.summary.json"))
    assert index["g1_verdict"]["complete"] == 5  # completion state is still visible
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner({}))
    assert main(args) == 0
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index["outcomes_redacted"] is False and all("t_first" in c for c in index["cells"])
    assert len(list((out / "summaries").glob("*.summary.json"))) == 6


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

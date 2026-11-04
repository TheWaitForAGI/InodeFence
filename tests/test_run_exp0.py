"""EXP-0 launcher: gate, dry-run, idempotent rerun and summaries (no Docker)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts import run_exp0
from scripts.run_effect_demo import synthetic_demo_report
from scripts.run_exp0 import (
    Exp0Plan,
    archive_attempt,
    cell_is_complete,
    exp0_cell_env,
    gate_mismatches,
    main,
    post_check,
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

    def run(cell, output: Path, env: dict[str, str], bash: str) -> CellResult:
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
    monkeypatch.setattr(run_exp0, "_run_cell", runner)
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
    monkeypatch.setattr(run_exp0, "_run_cell", runner2)
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
    monkeypatch.setattr(run_exp0, "_run_cell", runner3)
    assert main(args) == 0 and runner3.calls == []  # type: ignore[attr-defined]


def test_nonconformant_image_or_sentinel_set_is_invalid_not_complete(
    prereg_file: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "exp0"
    runner = _fake_runner({"image_id": "sha256:" + "cd" * 32})
    monkeypatch.setattr(run_exp0, "_run_cell", runner)
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
    monkeypatch.setattr(run_exp0, "_run_cell", _fake_runner({}))
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

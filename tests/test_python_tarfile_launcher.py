"""PR-B: python-tarfile in-process cells in the EXP-3 launcher (no docker).

lock_digest composition, the host-side controller script, and the launcher's
extractor-aware command / environment / wiring / post-check for lock targets.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from scripts import run_exp0
from scripts import run_python_tarfile_effect_demo as host
from scripts.run_effect_demo import python_tarfile_demo_report
from scripts.run_exp0 import TargetCell, cell_command, cell_execution_mode, exp0_cell_env, main
from scripts.run_g1_smoke import cell_paths

from inodefence.evaluation.lock_digest import LockRecord, lock_digest, lock_record
from inodefence.evaluation.rds import RdsArm, RdsCellConfig
from inodefence.evaluation.rds_report import summarize_report_records
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.model.provenance import SourceProvenance
from inodefence.mutator import MutationPolicy
from inodefence.targets.python_tarfile_effect import PythonTarfileEffectTarget, python_tarfile_lock

SHA = "0123456789abcdef0123456789abcdef01234567"
DIGEST = "sha256:" + "ab" * 32
R_POLICY = EffectSearchPolicy("unretained-walk-v1-uniform-mutation-v1")
FIXED = MutationPolicy("uniform-generic-m1-state-aware-escape-hardlink-fixed-baseline-v1")
SEEDS_ONLY = len(minimal_seed_corpus())


# ---- lock digest -----------------------------------------------------------------------


def test_lock_digest_is_canonical_and_verbatim() -> None:
    expected = (
        "sha256:"
        + __import__("hashlib").sha256(b"Python 3.12\n" + b"ab" * 32 + b"\nLinux 6.1\n").hexdigest()
    )
    assert lock_digest("Python 3.12", "ab" * 32, "Linux 6.1") == expected
    assert lock_digest("Python 3.12\n", "ab" * 32, "Linux 6.1") != expected  # no stripping
    with pytest.raises(ValueError):
        lock_digest("", "ab" * 32, "Linux 6.1")
    record = lock_record(python_tarfile_lock())
    assert isinstance(record, LockRecord) and record.lock_digest.startswith("sha256:")
    assert record.lock_digest == lock_digest(**record.material())
    assert lock_record(PythonTarfileEffectTarget("data").lock) == record  # stable within a host


# ---- demo report + host script (real in-process extraction, seeds only) ----------------


def test_python_tarfile_demo_report_records_lock_and_parses(tmp_path: Path) -> None:
    sink: list[dict] = []
    report = python_tarfile_demo_report(
        seed=9001,
        budget=SEEDS_ONLY,
        policy=R_POLICY,
        mutation_policy=FIXED,
        step_sink=sink.append,
        observer_integrity_policy="invalid-continue",
    )
    assert report["mode"] == "python-tarfile" and report["extractor"] == "python-tarfile"
    assert report["execution_mode"] == "per-case-subprocess"
    assert report["mechanism"] == "python-tarfile-inprocess"
    assert report["python_tarfile_policy"] == "data"
    material = cast(dict[str, str], report["lock_material"])
    assert report["lock_digest"] == lock_digest(**material)
    assert report["observer_integrity_policy"] == "invalid-continue"
    steps = cast(list[dict[str, Any]], report["steps"])
    assert len(sink) == SEEDS_ONLY == len(steps)
    step = steps[-1]
    assert {s["mechanism"] for s in step["trace"]["sources"]} == {"python-tarfile-inprocess"}
    assert step["trace"]["synthetic"] is False and "oracle_fingerprints" in step
    summary = summarize_report_records(steps, RdsCellConfig(RdsArm.R, 9001, SEEDS_ONLY))
    assert summary.summary.complete and summary.summary.executions_completed == SEEDS_ONLY
    assert summary.summary.u_viol_source == "oracle"


@pytest.mark.xfail(
    strict=True,
    reason="PR-A producer: a mutated case with two entries on one path fails the "
    "EffectRunResult entry-identity check (reported to lane 3); flip when fixed",
)
def test_python_tarfile_demo_report_survives_mutated_cases() -> None:
    python_tarfile_demo_report(
        seed=9001, budget=SEEDS_ONLY + 3, policy=R_POLICY, mutation_policy=FIXED
    )


def test_host_script_reads_the_cell_environment_and_writes_both_files(tmp_path: Path) -> None:
    env = {
        "RUN_ID": "py-tarfile-3.12-R-s9001",
        "INODEFENCE_EVIDENCE_DIR": str(tmp_path),
        "DEMO_SEED": "9001",
        "DEMO_BUDGET": str(SEEDS_ONLY),
        "DEMO_POLICY": R_POLICY.value,
        "DEMO_MUTATION_POLICY": FIXED.value,
        "DEMO_OBSERVER_INTEGRITY_POLICY": "invalid-continue",
        "DEMO_EXTRACTOR": "python-tarfile",
        "DEMO_EXECUTION_MODE": "per-case-subprocess",
    }
    completed = subprocess.run(
        [sys.executable, str(host.__file__)],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-800:]
    report_path, steps_path = host.evidence_paths(tmp_path, env["RUN_ID"])
    assert report_path.name == "inodefence-effect-demo-python-tarfile-py-tarfile-3.12-R-s9001.json"
    report = json.loads(report_path.read_text())
    assert report["lock_digest"].startswith("sha256:") and len(report["steps"]) == SEEDS_ONLY
    assert sum(1 for line in steps_path.read_text().splitlines() if line.strip()) == SEEDS_ONLY
    assert "effect demo report:" in completed.stderr


def test_host_script_abort_leaves_steps_and_an_abort_record(tmp_path: Path) -> None:
    code = host.main(
        ["--run-id", "x-R-s1", "--evidence-dir", str(tmp_path), "--seed", "1", "--budget", "1"]
    )
    assert code == 1  # budget below the seed count aborts before any step
    report_path, steps_path = host.evidence_paths(tmp_path, "x-R-s1")
    report = json.loads(report_path.read_text())
    assert report["aborted"]["step_index"] == 0 and "ValueError" in report["aborted"]["reason"]
    assert report["execution_mode"] == "per-case-subprocess" and steps_path.is_file()


# ---- launcher: cells, env, command, wiring, post-check ------------------------------------

BLOCK = f"""# EXP-3 (test fixture)

```preregistration
engine_sha = {SHA}
seeds = 9001, 9002
budget = {SEEDS_ONLY}
vocabulary = observed-names
arm.R = unretained-walk-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
targets.node-tar-7.5.2.extractor = node-tar
targets.node-tar-7.5.2.version = 7.5.2
targets.node-tar-7.5.2.image_digest = {DIGEST}
targets.node-tar-7.5.2.role = train
targets.node-tar-7.5.2.hypothesis = H-A
targets.node-tar-7.5.2.exposure = none
targets.py-tarfile-3.12.extractor = python-tarfile
targets.py-tarfile-3.12.version = 3.12
targets.py-tarfile-3.12.lock_digest = LOCK
targets.py-tarfile-3.12.role = train
targets.py-tarfile-3.12.hypothesis = H-B
targets.py-tarfile-3.12.exposure = none
targets.py-tarfile-3.12.arms = R
observer_integrity_policy = invalid-continue
execution_mode = per-case-container
```
"""


def _file(tmp_path: Path, lock: str) -> Path:
    path = tmp_path / "exp3.md"
    path.write_text(BLOCK.replace("LOCK", lock), encoding="utf-8")
    return path


def _plan(path: Path) -> run_exp0.Exp0Plan:
    import hashlib

    from inodefence.evaluation.rds_preregistration import load_preregistration

    return run_exp0.Exp0Plan(
        load_preregistration(path),
        path,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        "7.5.2",
        False,
    )


@pytest.fixture
def clean_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_exp0, "capture_source", lambda: SourceProvenance(SHA, False))
    monkeypatch.setattr(run_exp0, "_script_has", lambda variable: True)


def test_in_process_cells_get_their_own_mode_command_env_and_paths(
    tmp_path: Path, clean_engine: None
) -> None:
    lock = lock_record(python_tarfile_lock()).lock_digest
    plan = _plan(_file(tmp_path, lock))
    cells = plan.cells()
    py = [c for c in cells if isinstance(c, TargetCell) and c.in_process]
    assert [c.run_id for c in py] == ["py-tarfile-3.12-R-s9001", "py-tarfile-3.12-R-s9002"]
    cell = py[0]
    assert cell.mode == "demo-python-tarfile" and cell.digest_kind == "lock"
    assert cell.evidence_basename == "inodefence-effect-demo-python-tarfile-py-tarfile-3.12-R-s9001"
    assert (
        cell_paths(cell, tmp_path / "out")["report"].parent == tmp_path / "out" / "py-tarfile-3.12"
    )
    assert cell_execution_mode(plan, cell) == "per-case-subprocess"
    assert cell_execution_mode(plan, cells[0]) == "per-case-container"
    assert cell_command(cell, "/bin/bash", "/usr/bin/python3") == [
        "/usr/bin/python3",
        str(run_exp0.PYTHON_SCRIPT),
    ]
    assert cell_command(cells[0], "/bin/bash", "/usr/bin/python3")[:2] == [
        "/bin/bash",
        str(run_exp0.SCRIPT),
    ]
    env = exp0_cell_env(plan, cell, tmp_path / "out", {})
    assert (
        env["DEMO_EXTRACTOR"] == "python-tarfile"
        and env["DEMO_EXECUTION_MODE"] == "per-case-subprocess"
    )
    assert env["INODEFENCE_EVIDENCE_DIR"] == str(tmp_path / "out" / "py-tarfile-3.12")
    assert "TAR_VERSION" not in env and env["DEMO_OBSERVER_INTEGRITY_POLICY"] == "invalid-continue"
    node_env = exp0_cell_env(plan, cells[0], tmp_path / "out", {})
    assert node_env["DEMO_EXTRACTOR"] == "node-tar" and node_env["TAR_VERSION"] == "7.5.2"
    assert run_exp0.wiring_problems(plan) == ()
    ok = run_exp0.gate_mismatches(
        plan,
        engine_sha=SHA,
        engine_dirty=False,
        image_digest=None,
        observer_integrity_policy="invalid-continue",
        target_digests={"node-tar-7.5.2": DIGEST, "py-tarfile-3.12": lock},
    )
    assert ok == ()


def test_wiring_refuses_when_the_host_script_is_missing_or_mispinned(
    tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = lock_record(python_tarfile_lock()).lock_digest
    plan = _plan(_file(tmp_path, lock))
    monkeypatch.setattr(run_exp0, "PYTHON_SCRIPT", tmp_path / "missing.py")
    assert run_exp0.wiring_problems(plan) == (
        "target py-tarfile-3.12: missing.py (in-process controller) is missing",
    )
    (tmp_path / "nolock.py").write_text("print('no digest here')\n")
    monkeypatch.setattr(run_exp0, "PYTHON_SCRIPT", tmp_path / "nolock.py")
    assert run_exp0.wiring_problems(plan)[0].endswith("does not record lock_digest in the report")
    # An in-process target pinned by image_digest is a registration error the wiring catches.
    mispinned = BLOCK.replace(
        "targets.py-tarfile-3.12.lock_digest = LOCK",
        f"targets.py-tarfile-3.12.image_digest = {DIGEST}",
    )
    path = tmp_path / "mis.md"
    path.write_text(mispinned, encoding="utf-8")
    monkeypatch.setattr(run_exp0, "PYTHON_SCRIPT", Path(host.__file__))
    assert run_exp0.wiring_problems(_plan(path))[0].endswith(
        "is pinned by lock_digest, not image_digest"
    )


def test_live_run_with_fake_cells_records_and_checks_the_lock_digest(
    tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_run_exp0 import _fake_runner  # shared fake controller (writes synthetic reports)

    lock = lock_record(python_tarfile_lock()).lock_digest
    file = _file(tmp_path, lock)
    out = tmp_path / "exp3"
    calls: list[list[str]] = []

    def runner(cell, output, env, bash, **limits):
        calls.append(cell_command(cell, bash, "py"))
        behaviour = {"image_id": DIGEST}
        if isinstance(cell, TargetCell) and cell.in_process:
            behaviour = {"lock_digest": env.get("EXPECT_LOCK", lock)}
        return _fake_runner(behaviour)(cell, output, env, bash, **limits)

    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    monkeypatch.setattr(run_exp0, "_warmup", lambda *a, **k: 0)
    args = [
        "--preregistration",
        str(file),
        "--output",
        str(out),
        "--target-digest",
        f"node-tar-7.5.2={DIGEST}",
        "--target-digest",
        f"py-tarfile-3.12={lock}",
        "--observer-integrity-policy",
        "invalid-continue",
        "--no-manifest",
        "--jobs",
        "2",
    ]
    assert main([*args, "--dry-run"]) == 0
    assert main(args) == 0
    assert sum(1 for c in calls if c[0] == "py") == 2 and sum(1 for c in calls if c[0] != "py") == 6
    index = json.loads((out / "summaries" / "index.json").read_text())
    py_cells = [c for c in index["cells"] if c["target_id"] == "py-tarfile-3.12"]
    assert len(py_cells) == 2 and all(c["complete"] and c["hypothesis"] == "H-B" for c in py_cells)
    matrix = json.loads((out / "matrix.json").read_text())
    modes = {c["run_id"]: c["execution_mode"] for c in matrix["cells"]}
    assert modes["py-tarfile-3.12-R-s9001"] == "per-case-subprocess"
    assert modes["node-tar-7.5.2-R-s9001"] == "per-case-container"
    # A report whose lock_digest differs from the registration is config-nonconformant.
    wrong = "sha256:" + "ee" * 32
    for path in (out / "py-tarfile-3.12").glob("*.json"):
        report = json.loads(path.read_text())
        report["lock_digest"] = wrong
        path.write_text(json.dumps(report))
    assert main([*args, "--summarize-only"]) == 1
    index = json.loads((out / "summaries" / "index.json").read_text())
    bad = [c for c in index["cells"] if c["target_id"] == "py-tarfile-3.12"]
    assert all(c["invalid"] for c in bad)

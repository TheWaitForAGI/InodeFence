"""run_exp0 --jobs launcher fixes after W4's (C) part 2 review of the integration head.

Preflight before warmup, expected controller/helper/target ids refused before any start,
the execution SHA in the preflight record, the start gate on the real run_exp0 path
(three reproductions W4 wrote against fa8ccb4), the gate verdict before the end line,
and an escaping launcher error that stops every later start.
"""

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0

from inodefence.evaluation.cell_completeness import INFRASTRUCTURE_STOP_EVENT, START_DENIED_FIELD
from inodefence.execution import start_gate
from inodefence.execution.start_gate import StartDenied, StartGate, acknowledge
from test_run_exp0 import (
    BEFORE,
    SHA,
    TARGET_IMAGES,
    AlwaysCleanGate,
    _deadline_plan,
    _deadline_setup,
    _fake_runner,
    _result_lines,
)
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine
from test_run_exp0_host_guards import CONTROLLER_ID, HELPER_ID, FakeDocker
from test_run_exp0_host_guards import real_guards as real_guards

GATE_SCRIPT = Path(start_gate.__file__)


def _stops(out: Path) -> list[dict[str, Any]]:
    return [r for r in _result_lines(out) if r.get("event") == INFRASTRUCTURE_STOP_EVENT]


def _preflight(out: Path) -> dict[str, Any]:
    (path,) = sorted((out / run_exp0.HOST_RECORD_DIR).glob("preflight-*.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def _without_skip_build(args: list[str]) -> list[str]:
    return [a for a in args if a != "--skip-build"]


def _expected(tmp_path: Path, **override: str) -> Path:
    ids = {
        "inodefence-node-tar-effect:7.5.2": FakeDocker().ids["inodefence-node-tar-effect:7.5.2"],
        "inodefence-node-tar-effect:7.9.9": FakeDocker().ids["inodefence-node-tar-effect:7.9.9"],
        "inodefence-controller:local": CONTROLLER_ID,
        "inodefence-helper:local": HELPER_ID,
        **override,
    }
    path = tmp_path / "criteria.json"
    path.write_text(json.dumps({"schema": "any", "expected_image_ids": ids}), encoding="utf-8")
    return path


# ---- 1. preflight before warmup; expected images; execution SHA --------------------------------


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_the_preflight_is_recorded_before_the_warmup_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    seen: list[str] = []

    def warmup(*_a: object, **_k: object) -> int:
        seen.append("warmup")
        assert list((out / run_exp0.HOST_RECORD_DIR).glob("preflight-*.json")), "no preflight yet"
        assert any(call[:2] == ("image", "inspect") for call in real_guards.calls)
        return 0

    monkeypatch.setattr(run_exp0, "_warmup", warmup)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    assert run_exp0.main(_without_skip_build(args)) == 0
    assert seen == ["warmup"]


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_a_warmup_that_changes_an_image_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")

    def rebuilding_warmup(*_a: object, **_k: object) -> int:
        real_guards.ids["inodefence-controller:local"] = "sha256:" + "e" * 64
        return 0

    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "_warmup", rebuilding_warmup)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert run_exp0.main(_without_skip_build(args)) == 2
    assert runner.calls == []  # type: ignore[attr-defined]


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_expected_ids_are_checked_and_a_mismatch_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    wrong = _expected(tmp_path, **{"inodefence-helper:local": "sha256:" + "0" * 64})
    assert run_exp0.main([*args, "--expected-images", str(wrong)]) == 2
    assert runner.calls == []  # type: ignore[attr-defined]
    problems = _preflight(out)["problems"]
    assert any("inodefence-helper:local is " + HELPER_ID in item for item in problems)


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_matching_expected_ids_run_and_are_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    expected = _expected(tmp_path)
    assert run_exp0.main([*args, "--expected-images", str(expected)]) == 0
    record = _preflight(out)
    assert record["problems"] == []
    assert record["expected_images"]["file"] == "criteria.json"
    assert record["execution_sha"] == {"revision": SHA, "dirty": False}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"drop": "inodefence-helper:local"}, "the guarded images are"),
        ({"inodefence-node-tar-effect:7.5.2": "sha256:" + "1" * 64}, "the registration pins"),
        ({"inodefence-controller:local": ""}, "must map image names to ids"),
    ],
)
@pytest.mark.usefixtures("admit_fixture_holdout")
def test_an_unusable_expected_images_file_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_guards: FakeDocker,
    capsys: pytest.CaptureFixture[str],
    change: dict[str, str],
    message: str,
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    path = _expected(tmp_path, **{k: v for k, v in change.items() if k != "drop"})
    if "drop" in change:
        data = json.loads(path.read_text())
        del data["expected_image_ids"][change["drop"]]
        path.write_text(json.dumps(data))
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert run_exp0.main([*args, "--expected-images", str(path)]) == 2
    assert message in capsys.readouterr().err
    assert runner.calls == []  # type: ignore[attr-defined]


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_a_two_host_run_needs_expected_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from test_two_host_split import _host_args, _setup

    out, args, assignment = _setup(tmp_path, monkeypatch)
    host_args = _host_args(args, out, "HOST1", assignment, "2")
    index = host_args.index("--expected-images")
    without = host_args[:index] + host_args[index + 2 :]
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    assert run_exp0.main(without) == 2
    assert "needs --expected-images" in capsys.readouterr().err
    assert runner.calls == []  # type: ignore[attr-defined]


def test_guard_images_take_expected_local_ids() -> None:
    class Plan:
        def targets(self) -> list[Any]:
            return []

    images = run_exp0.guard_images(Plan(), {"inodefence-controller:local": CONTROLLER_ID})  # type: ignore[arg-type]
    assert images["inodefence-controller:local"] == CONTROLLER_ID
    assert images["inodefence-helper:local"] is None


# ---- 2. the real start gate on the run_exp0 path (W4 reproductions) ---------------------------


@pytest.fixture
def real_gate(clean_engine: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_exp0, "StartGate", StartGate)


@pytest.mark.usefixtures("real_gate", "admit_fixture_holdout")
def test_cross_process_unknown_denies_the_next_start_with_two_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """X's child records U while X's runner is still blocked; Y ends S; Z's start is denied."""
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="2")
    order = [c.run_id for c in _deadline_plan(args).cells()]
    x, y, z = order[0], order[1], order[2]
    inner = _fake_runner(TARGET_IMAGES)
    release, y_spawned, x_recorded = threading.Event(), threading.Event(), threading.Event()
    calls: list[str] = []
    spawned: list[str] = []

    def run(cell, output, env, bash, *, limit_seconds, popen=subprocess.Popen, on_timeout=None):
        calls.append(cell.run_id)
        verdict = ["U", "race: test"] if cell.run_id == x else ["S"]
        if cell.run_id == x:
            assert y_spawned.wait(60)
        try:
            process = popen([sys.executable, str(GATE_SCRIPT), "record", *verdict], env=dict(env))
        except StartDenied:
            release.set()
            raise
        spawned.append(cell.run_id)
        if cell.run_id == y:
            y_spawned.set()
        process.wait()
        if cell.run_id == y:
            assert x_recorded.wait(60)
        if cell.run_id == x:
            x_recorded.set()
            assert release.wait(60), "Z never attempted"
        return inner(cell, output, env, bash, limit_seconds=limit_seconds)

    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", run)
    run_exp0.main(args)
    assert release.is_set()
    assert z in calls and z not in spawned
    z_end = [r for r in _result_lines(out) if r.get("run_id") == z and r["event"] == "end"]
    assert len(z_end) == 1 and "race: test" in z_end[0][START_DENIED_FIELD]
    stops = _stops(out)
    assert len(stops) == 1 and stops[0]["reason"].startswith(f"start gate denied {z}")
    assert len(calls) == 3  # nothing after Z
    # Persisted: the next call refuses before any start.
    again = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", again)
    run_exp0.main(args)
    assert again.calls == []  # type: ignore[attr-defined]


@pytest.mark.usefixtures("admit_fixture_holdout", "clean_engine")
def test_a_popen_that_fails_after_the_fork_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    children: list[subprocess.Popen[Any]] = []

    def broken_popen(*_a: Any, **k: Any) -> Any:
        children.append(
            subprocess.Popen(
                [sys.executable, "-c", "import sys; sys.stdin.read()"],
                stdin=subprocess.PIPE,
                **{key: value for key, value in k.items() if key in ("env", "pass_fds")},
            )
        )
        raise OSError("popen failed after fork")

    class Gate(StartGate):
        def popen(self, cell: str, popen: Any = broken_popen) -> Any:  # type: ignore[override]
            return super().popen(cell, popen)

    monkeypatch.setattr(run_exp0, "StartGate", Gate)
    inner = _fake_runner(TARGET_IMAGES)
    calls: list[str] = []

    def run(cell, output, env, bash, *, limit_seconds, popen=subprocess.Popen, on_timeout=None):
        calls.append(cell.run_id)
        popen(["true"], env=dict(env))
        return inner(cell, output, env, bash, limit_seconds=limit_seconds)

    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", run)
    try:
        run_exp0.main(args)
        assert len(calls) == 1
        gate = StartGate(out / run_exp0.START_GATE_DIR, check_filesystem=False)
        verdict = gate.verdict(calls[0])
        assert verdict is not None and verdict[0] == "U" and "start indeterminate" in verdict[1]
        end = [r for r in _result_lines(out) if r.get("run_id") == calls[0] and r["event"] == "end"]
        assert "runner_error" in end[-1] and START_DENIED_FIELD not in end[-1]
        assert len(_stops(out)) == 1
        assert gate.problem() is not None
    finally:
        for child in children:
            assert child.stdin is not None
            child.stdin.close()
            child.wait(timeout=30)


@pytest.mark.usefixtures("real_gate", "admit_fixture_holdout")
def test_an_unfinished_cell_of_an_earlier_session_denies_until_acknowledged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    gate_dir = out / run_exp0.START_GATE_DIR
    gate_dir.mkdir(parents=True)
    (gate_dir / "ghost.session").write_text("other-session\n")
    (gate_dir / "ghost.lock").write_text("")
    runner = _fake_runner(TARGET_IMAGES)
    seen: list[str] = []

    def run(cell, output, env, bash, *, limit_seconds, popen=subprocess.Popen, on_timeout=None):
        seen.append(cell.run_id)
        process = popen([sys.executable, str(GATE_SCRIPT), "record", "S"], env=dict(env))
        process.wait()
        return runner(cell, output, env, bash, limit_seconds=limit_seconds)

    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", run)
    run_exp0.main(args)
    assert seen == []
    [stop] = _stops(out)
    assert "launcher session other-session" in stop["reason"]
    assert run_exp0.main([*args, "--resume-after-stop", "A1"]) == 2
    assert seen == []
    acknowledge(gate_dir, "ghost", "approval=A1; by=v; reason=checked")
    assert run_exp0.main([*args, "--resume-after-stop", "A1"]) == 0
    assert seen


# ---- 3. verdict before the end line; an escaping error stops later starts ---------------------


@pytest.mark.usefixtures("admit_fixture_holdout", "clean_engine")
def test_the_gate_verdict_comes_before_the_end_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    events: list[tuple[str, str]] = []

    class Recording(AlwaysCleanGate):
        def require_clean(self, cell: str) -> None:
            events.append(("verdict", cell))

    real_append = run_exp0.append_cell_result

    def append(output: Path, record: Any) -> None:
        if record.get("event") == "end":
            events.append(("end", record["run_id"]))
        real_append(output, record)

    monkeypatch.setattr(run_exp0, "StartGate", Recording)
    monkeypatch.setattr(run_exp0, "append_cell_result", append)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    assert run_exp0.main(args) == 0
    cells = [cell for kind, cell in events if kind == "end"]
    assert cells
    for cell in cells:
        assert events.index(("verdict", cell)) < events.index(("end", cell))


@pytest.mark.usefixtures("real_gate", "admit_fixture_holdout")
def test_an_escaping_launcher_error_stops_every_later_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replaces W4's probe: an end-line write failure used to let later cells start."""
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    order = [c.run_id for c in _deadline_plan(args).cells()]
    real_append = run_exp0.append_cell_result
    calls: list[str] = []
    inner = _fake_runner(TARGET_IMAGES)

    def append(output: Path, record: Any) -> None:
        if record.get("event") == "end" and record.get("run_id") == order[0]:
            raise OSError("disk hiccup")
        real_append(output, record)

    def run(cell, output, env, bash, *, limit_seconds, popen=subprocess.Popen, on_timeout=None):
        calls.append(cell.run_id)
        process = popen([sys.executable, str(GATE_SCRIPT), "record", "S"], env=dict(env))
        process.wait()
        return inner(cell, output, env, bash, limit_seconds=limit_seconds)

    monkeypatch.setattr(run_exp0, "append_cell_result", append)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", run)
    with pytest.raises(OSError, match="disk hiccup"):
        run_exp0.main(args)
    assert calls == [order[0]]
    [stop] = _stops(out)
    assert stop["reason"].startswith(f"launcher error on {order[0]}: OSError: disk hiccup")


@pytest.mark.usefixtures("admit_fixture_holdout", "clean_engine")
def test_an_unavailable_disk_reading_stops_every_later_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    runner = _fake_runner(TARGET_IMAGES)
    readings = {"n": 0}

    def disk(path: Path, fraction: float) -> int:
        readings["n"] += 1
        if readings["n"] == 2:
            raise run_exp0.DiskUsageUnavailable("statvfs failed")
        return 0

    monkeypatch.setattr(run_exp0, "wait_for_disk", disk)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    with pytest.raises(run_exp0.DiskUsageUnavailable):
        run_exp0.main(args)
    assert len(runner.calls) == 1  # type: ignore[attr-defined]
    [stop] = _stops(out)
    assert "DiskUsageUnavailable" in stop["reason"]


@pytest.mark.usefixtures("admit_fixture_holdout", "clean_engine")
def test_a_popen_that_fails_before_the_fork_leaves_a_visible_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")

    def missing(*_a: Any, **_k: Any) -> Any:
        raise FileNotFoundError("bash vanished")

    class Gate(StartGate):
        def popen(self, cell: str, popen: Any = missing) -> Any:  # type: ignore[override]
            return super().popen(cell, popen)

    monkeypatch.setattr(run_exp0, "StartGate", Gate)

    def run(cell, output, env, bash, *, limit_seconds, popen=subprocess.Popen, on_timeout=None):
        popen(["true"], env=dict(env))
        raise AssertionError("unreachable")

    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", run)
    run_exp0.main(args)
    gate = StartGate(out / run_exp0.START_GATE_DIR, check_filesystem=False)
    problem = gate.problem()
    assert problem is not None and "launcher: runner error: FileNotFoundError" in problem
    assert len(_stops(out)) == 1

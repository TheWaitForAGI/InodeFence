"""The D042 stop/resume smoke procedure, end to end, judged by the real checker (#347).

The real run_exp0 (targets form, real start gate, real host guard code on a fake docker CLI,
the real raw-manifest script) runs scenario B (B-0..B-5) and scenario A. Only the cell itself
is a stand-in: it records its start-gate verdict through the real gate child, as the smoke
script's cleanup trap does, and either writes a record or (under ``HISTORICAL_IMAGE``) fails
where the injected image lookup fails and leaves none. The snapshots, verify-tools and judge
are the real ones. A correct procedure must pass every criterion, so a criterion text that
disagrees with the launcher's normal behaviour fails here, not on the host.

Stand-ins (the criteria they touch also use the stand-in value):
* docker residual state and context for the snapshots (A6, X2, SA6): an empty, ``default``
  docker, since no container ever exists;
* the controller destroy events (X1): the stand-in cell appends one per attempt to
  ``host/events.jsonl``, as the host event recorder would;
* the cell log lines (A8): the stand-in writes the smoke script's failure lines.
"""

import json
import os
import random
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0
from scripts import check_stop_path_smoke as check
from scripts.run_g1_smoke import cell_paths

from inodefence.execution import start_gate
from inodefence.execution.start_gate import StartGate, acknowledge
from test_run_exp0 import BEFORE, TARGET_IMAGES, _deadline_plan, _deadline_setup, _fake_runner
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine
from test_run_exp0_host_guards import FakeDocker
from test_run_exp0_host_guards import real_guards as real_guards
from test_run_exp0_launcher_order import _expected

REPO = Path(run_exp0.__file__).resolve().parents[1]
GATE_SCRIPT = Path(start_gate.__file__)
MISSING_IMAGE = "inodefence-node-tar-effect:does-not-exist"
REF_B = "D042-smoke-1-B-20261112-1000"
REF_A = "D042-smoke-1-A-20261112-1100"


WAIT_SECONDS = 120.0
#: Optional random delay (seconds, upper bound) at the stand-in's steps, to check that the
#: tests do not depend on timing: INODEFENCE_TEST_STANDIN_JITTER=0.05 pytest ...
JITTER = float(os.environ.get("INODEFENCE_TEST_STANDIN_JITTER", "0") or 0)


def _jitter() -> None:
    if JITTER > 0:
        time.sleep(random.uniform(0, JITTER))


def _wait_for(condition: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not condition():
        assert time.monotonic() < deadline, f"stand-in waited too long for {what}"
        time.sleep(0.01)


def _stopped(out: Path) -> bool:
    path = out / run_exp0.CELL_RESULTS_FILE
    return path.is_file() and f'"{check.STOP}"' in path.read_text(encoding="utf-8")


class _Lockstep:
    """Injected attempts end in pairs (jobs 2), whatever the machine's speed.

    An attempt returns only when the other worker's attempt has also arrived (or the run has
    stopped, so no partner will come). Between a cell's attempt-1 end and its retry start, the
    other worker can then write at most one start: the order a real run has because an attempt
    takes seconds while the launcher's gap between end and retry takes milliseconds. It also
    fixes the B-1 shape: cells 1-2 and 3-4 each fail twice in parallel, 4 no-record cells, the
    stop on the third end, no first-attempt-only cell.
    """

    def __init__(self, out: Path) -> None:
        self.out = out
        self.arrived = 0
        self.lock = threading.Lock()

    def meet(self) -> None:
        with self.lock:
            self.arrived += 1
            target = self.arrived + self.arrived % 2
        _wait_for(lambda: self.arrived >= target or _stopped(self.out), "the paired attempt")


#: A gate child that first touches a file and/or waits for a file (with a prefix), then
#: becomes ``start_gate.py record <verdict>`` (exec keeps the lifetime lock descriptor).
CHILD = """
import os, sys, time
touch, wait, prefix, gate, *verdict = sys.argv[1:]
if touch:
    open(touch, "w").close()
deadline = time.monotonic() + 120
while wait and not (os.path.isfile(wait) and open(wait).read().startswith(prefix)):
    if time.monotonic() > deadline:
        sys.exit("stand-in child waited too long")
    time.sleep(0.01)
os.execv(sys.executable, [sys.executable, gate, "record", *verdict])
"""


def _cell_runner(
    out: Path, unknown: str | None = None, clean_after_unknown: str | None = None
) -> Any:
    """A cell that records its gate verdict, then a record (or none under the injection).

    Scenario A, made deterministic: both first cells are admitted while neither has a verdict;
    ``unknown``'s child records U only after ``clean_after_unknown``'s child has been admitted,
    which then records S only after that U; ``unknown`` returns only after the stop line. So:
    the U cell, one cell that ran clean, the next start denied by the gate, then the stop
    ("start gate denied") — a shape the launcher can produce on any machine (SA1 corrected).
    """
    inner = _fake_runner(TARGET_IMAGES)
    lockstep = _Lockstep(out)
    admitted = out.parent / "second-cell-admitted"

    def run(cell, output, env, bash, *, limit_seconds, popen=subprocess.Popen, on_timeout=None):
        _jitter()
        injected = env.get("HISTORICAL_IMAGE") == MISSING_IMAGE
        gate_dir = output / run_exp0.START_GATE_DIR
        touch, wait, prefix, verdict = "", "", "", ["S"]
        if cell.run_id == unknown:
            wait, verdict = str(admitted), ["U", "cleanup: test"]
        elif cell.run_id == clean_after_unknown and unknown is not None:
            touch, wait, prefix = str(admitted), str(gate_dir / f"{unknown}.verdict"), "U"
        child = [sys.executable, "-c", CHILD, touch, wait, prefix, str(GATE_SCRIPT), *verdict]
        process = popen(child, env=dict(env))
        assert process.wait() == 0
        _jitter()
        if cell.run_id == unknown:
            _wait_for(lambda: _stopped(output), "the stop line")
        host = output / run_exp0.HOST_RECORD_DIR
        host.mkdir(exist_ok=True)
        with (host / "events.jsonl").open("a", encoding="utf-8") as events:
            name = f"inodefence-local-controller-{cell.run_id}"
            events.write(
                json.dumps({"Action": "destroy", "Actor": {"Attributes": {"name": name}}}) + "\n"
            )
        if injected:
            from scripts.run_parallel_native import CellResult

            paths = cell_paths(cell, output)
            paths["log"].write_text(
                "context=default engine=29.8.0 mode=demo-historical\n"
                f"Error response from daemon: No such image: {MISSING_IMAGE}\n"
                "FAILED at step: effect-demo-historical\n",
                encoding="utf-8",
            )
            _jitter()
            lockstep.meet()
            return CellResult(cell, 1, 1.0, paths["report"], True, paths["log"])
        result = inner(cell, output, env, bash, limit_seconds=limit_seconds)
        cell_paths(cell, output)["calls"].write_text("{}\n", encoding="utf-8")
        return result

    return run


def _no_residuals(*call: str) -> str:
    return "default" if call[:2] == ("context", "show") else ""


class _Run:
    """One output folder: run_exp0 calls and the snapshots of the procedure."""

    def __init__(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        self.monkeypatch, self.capsys = monkeypatch, capsys
        (tmp_path / name).mkdir()
        self.out, args, _ = _deadline_setup(tmp_path / name, monkeypatch, BEFORE, jobs="2")
        self.manifest = tmp_path / name / "raw-manifest.sha256"
        index = args.index("--manifest-script")
        args[index + 1] = str(run_exp0.DEFAULT_MANIFEST_SCRIPT)  # the real manifest script
        args[args.index("--manifest-out") + 1] = str(self.manifest)
        self.args = [*args, "--expected-images", str(_expected(tmp_path / name))]
        self.snaps = tmp_path / name / "snaps"
        monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _cell_runner(self.out))

    def call(self, *extra: str, inject: bool = False) -> tuple[int, str]:
        if inject:
            self.monkeypatch.setenv("HISTORICAL_IMAGE", MISSING_IMAGE)
        try:
            code = run_exp0.main([*self.args, *extra])
        finally:
            self.monkeypatch.delenv("HISTORICAL_IMAGE", raising=False)
        return code, self.capsys.readouterr().err

    def snapshot(
        self, stage: str, code: int | None = None, err: str | None = None, manifest: bool = False
    ) -> None:
        record = check.take_snapshot(
            self.out,
            stage,
            manifest=self.manifest if manifest else None,
            exit_code=code,
            stderr=err,
            docker=_no_residuals,
        )
        self.snaps.mkdir(parents=True, exist_ok=True)
        (self.snaps / f"{stage}.json").write_text(json.dumps(record), encoding="utf-8")


@pytest.fixture
def end_to_end(
    real_guards: FakeDocker, admit_fixture_holdout: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_exp0, "StartGate", StartGate)
    monkeypatch.setenv("PYTHONPATH", f"{REPO / 'src'}:{REPO}")  # for verify-tools' analyzer


def _failures(result: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {name: item["evidence"] for name, item in result.items() if item["result"] != "PASS"}


@pytest.mark.usefixtures("end_to_end")
def test_scenario_b_by_the_procedure_passes_every_criterion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _Run(tmp_path, monkeypatch, capsys, "b")
    run.snapshot("b0")
    code, err = run.call(inject=True)  # B-1: the injected image lookup fails in every cell
    run.snapshot("b1", code, err)
    run.snapshot("pre-b2")
    code, err = run.call()  # B-2: no flag, nothing starts
    run.snapshot("b2", code, err)
    cause_logged_at = BEFORE.timestamp() - 1  # B-3: the cause line is written before B-4
    run.snapshot("pre-b4")
    code, err = run.call("--resume-after-stop", REF_B)  # B-4
    run.snapshot("b4", code, err)
    run.snapshot("pre-b5a")
    code, err = run.call()  # B-5, first call
    run.snapshot("b5a", code, err)
    run.snapshot("pre-b5b", manifest=True)
    code, err = run.call()  # B-5, second call (idempotence)
    run.snapshot("b5b", code, err, manifest=True)
    tools = check.verify_tools(run.out, run.manifest)
    (run.snaps / "tools.json").write_text(json.dumps(tools), encoding="utf-8")

    snaps = check.load_snapshots(run.snaps)
    result = check.judge_b(
        {k: v for k, v in snaps.items() if k != "tools"},
        snaps["tools"],
        cause_logged_at=cause_logged_at,
        round_number=1,
    )
    assert len(result) == 24
    assert _failures(result) == {}
    # The lockstep fixes B-1's shape: 4 cells fail twice, none first-attempt-only.
    b1 = snaps["b1"]["index"]
    assert b1["completeness"]["no_record"] == 4
    assert result["A5"]["evidence"]["first_attempt_only"] == 0


@pytest.mark.usefixtures("end_to_end")
def test_scenario_a_by_the_procedure_passes_every_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _Run(tmp_path, monkeypatch, capsys, "a")
    first, second = (cell.run_id for cell in _deadline_plan(run.args).cells()[:2])
    runner = _cell_runner(run.out, unknown=first, clean_after_unknown=second)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    code, err = run.call()  # the first cell's cleanup is unknown: the gate stops the run
    run.snapshot("a1", code, err)
    code, err = run.call("--resume-after-stop", REF_A)  # refused while U
    run.snapshot("a-refused", code, err)
    cell = first
    acknowledge(
        run.out / run_exp0.START_GATE_DIR,
        cell,
        f"approval={REF_A}; checked_at=2026-11-12T11:00:00+09:00; by=test; "
        "residual=docker ps -a --filter name=inodefence- -> (none); reason=test",
    )
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _cell_runner(run.out))
    code, err = run.call("--resume-after-stop", REF_A)
    run.snapshot("a2", code, err)
    code, err = run.call()
    run.snapshot("a-final", code, err)
    result = check.judge_a(check.load_snapshots(run.snaps))
    assert len(result) == 6
    assert _failures(result) == {}
    # The shape the corrected SA1 allows and the literal "starts <= jobs" did not.
    assert result["SA1"]["evidence"]["starts_before_stop"] == {
        "unknown": 1,
        "ran_clean": 1,
        "denied": 1,
        "other": 0,
    }

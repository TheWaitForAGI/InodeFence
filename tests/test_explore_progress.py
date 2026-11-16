"""The live progress display of ``inodefence explore`` (``inodefence.drivers.progress``).

Unit tests only: line formatting, unknown values, the ETA rule, terminal vs line mode, rate
limiting, the launcher-log redirect, the driver's ``--output`` modes, and that the numbers shown
are the ones ``inodefence status`` reports from the same ``progress.json``. No Docker.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from inodefence.drivers import progress as pg
from inodefence.drivers import run_target_explore as rte
from inodefence.drivers.run_target import (
    ExploreOutcome,
    PreparedTargetImage,
    TargetAdapter,
)
from inodefence.drivers.runtime.hooks import Finding, LaunchArtifacts
from inodefence.drivers.runtime.policy import STRICT
from inodefence.live_exploration import PROGRESS_FILE, read_progress, render_live_status
from inodefence.target_result import (
    CampaignInfo,
    CaseVerdict,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)
from test_live_exploration import _recorder, _step


def _view(counts: pg.Counts | None = None, **kw: Any) -> pg.View:
    base: dict[str, Any] = {
        "phase": pg.RUNNING,
        "target": "node-tar",
        "version": "7.5.23",
        "version_exact": True,
        "profile": "strict",
        "seed": 321,
        "budget": 40,
        "out": Path("/data/out"),
        "counts": counts or pg.Counts(),
    }
    base.update(kw)
    return pg.View(**base)


def _live_counts(**kw: Any) -> pg.Counts:
    base: dict[str, Any] = {
        "source": "live",
        "runs": 18,
        "terminations": {"success": 15, "rejected": 3, "failed": 0, "timed_out": 0},
        "unjudged": 0,
        "violations": 0,
        "contracts": {"c0": 0, "c1": 0, "c2": 0},
        "runs_per_second": 0.586,
        "budget": 40,
        "state": "running",
        "updated_at": 1000.0,
    }
    base.update(kw)
    return pg.Counts(**base)


# ---- line formatting ---------------------------------------------------------------------------


def test_line_shows_every_required_field() -> None:
    line = pg.format_line(_view(_live_counts(), eta_seconds=37.5, elapsed_seconds=45.0))
    assert line == (
        "[explore] running runs=18/40 | node-tar 7.5.23 profile=strict seed=321 | "
        "success=15 rejected=3 failed=0 timed_out=0 un-judged=0 | "
        "violations=0 C0=0 C1=0 C2=0 | 0.586 runs/s eta~38s | elapsed=45s | out=/data/out"
    )


def test_unknown_values_are_question_marks_never_zero() -> None:
    line = pg.format_line(_view(pg.Counts()))
    assert "runs=?/40" in line
    assert "success=? rejected=? failed=? timed_out=? un-judged=?" in line
    assert "violations=? C0=? C1=? C2=?" in line and "? runs/s" in line
    assert "=0" not in line and "eta" not in line


def test_a_snapshot_missing_fields_keeps_them_unknown() -> None:
    counts = pg.counts_from_progress({"runs_executed": 5, "terminations": {"success": "5"}}, [])
    assert counts.runs == 5
    assert counts.terminations == dict.fromkeys(pg.STATUSES, None)  # a string is not a count
    assert counts.unjudged is None and counts.violations is None
    assert counts.contracts == {"c0": None, "c1": None, "c2": None}  # steps unknown: not 0
    assert counts.runs_per_second is None
    assert pg.counts_from_progress({"runs_executed": True}, None).runs is None  # bool is no count


def test_contract_counts_are_exact_or_a_marked_lower_bound() -> None:
    progress = {"violations": {"steps": 3}}
    cases = [{"c1": True, "c2": True}, {"c2": True}, {"c0": True}]
    exact = pg.counts_from_progress(progress, cases)
    assert exact.contracts == {"c0": 1, "c1": 1, "c2": 2} and not exact.contracts_lower_bound
    partial = pg.counts_from_progress(progress, cases[:2])  # one case not on the host (yet)
    assert partial.contracts_lower_bound
    assert "C0>=0 C1>=1 C2>=2" in pg.format_line(_view(partial))
    unlisted = pg.counts_from_progress(progress, None)  # the case folder could not be listed
    assert "violations=3 C0=? C1=? C2=?" in pg.format_line(_view(unlisted))
    none = pg.counts_from_progress({"violations": {"steps": 0}}, None)
    assert none.contracts == {"c0": 0, "c1": 0, "c2": 0}  # no violating run: really zero


def test_requested_version_is_marked_until_the_exact_one_is_known() -> None:
    line = pg.format_line(_view(version="latest", version_exact=False, phase=pg.PREPARE))
    assert "node-tar latest(requested)" in line and "[explore] prepare" in line


def test_completed_and_aborted_lines_carry_verdict_and_cause() -> None:
    done = pg.format_line(_view(_live_counts(state="finished"), phase=pg.COMPLETED, verdict="PASS"))
    assert done.startswith("[explore] completed verdict=PASS runs=18/40")
    aborted = pg.format_line(_view(phase=pg.ABORTED, cause="controller run failed [stage=loop]"))
    assert aborted.endswith("| cause: controller run failed [stage=loop]")


def test_narrow_terminal_drops_identity_and_folder_first() -> None:
    view = _view(_live_counts(), eta_seconds=37.0, elapsed_seconds=45.0, snapshot_age=3.0)
    full = pg.format_line(view)
    assert "snapshot=3s ago" in full
    fitted = pg.format_line(view, 120)
    assert len(fitted) <= 120 and " out=/" not in fitted and "node-tar" not in fitted
    assert "runs=18/40" in fitted and "C0=0 C1=0 C2=0" in fitted
    tiny = pg.format_line(view, 30)
    assert len(tiny) <= 30 and tiny.startswith("[explore] running runs=18/40")


def test_step_label_is_shown_while_the_launcher_runs_and_out_only_when_asked() -> None:
    line = pg.format_line(_view(step="effect-demo-explore", show_out=False))
    assert line.startswith("[explore] running step=effect-demo-explore runs=?/40")
    assert " out=/" not in line
    done = pg.format_line(_view(step="validate", phase=pg.COMPLETED, verdict="PASS"))
    assert "step=" not in done and done.endswith("| out=/data/out")


def test_last_launcher_step_reads_the_last_step_line_of_the_log(tmp_path: Path) -> None:
    log = tmp_path / "launcher.log"
    assert pg.last_launcher_step(log) is None  # no log yet
    log.write_text("context=default\n==> [preflight]\nnoise\n", encoding="utf-8")
    assert pg.last_launcher_step(log) == "preflight"
    with log.open("a", encoding="utf-8") as stream:
        stream.write("x" * 20000 + "\n==> [prepare controller]\nmore output\n")
    assert pg.last_launcher_step(log) == "prepare-controller"


def test_header_names_results_folder_and_log() -> None:
    header = pg.header_line(_view(phase=pg.PREPARE), Path("/data/out/runtime/x.log"))
    assert "results: /data/out" in header and "launcher output: /data/out/runtime/x.log" in header
    assert "node-tar 7.5.23 profile=strict seed=321 budget=40" in header


# ---- same numbers as `inodefence status` -------------------------------------------------------


def test_numbers_equal_what_status_reports_from_the_same_progress_json(tmp_path: Path) -> None:
    rec, clock, live = _recorder(tmp_path, every_runs=1)
    statuses = ["success", "success", "rejected", "failed", "timed_out", "success", "success"]
    for index, status in enumerate(statuses):
        clock.now += 2
        kw: dict[str, Any] = {"status": status}
        if index == 1:
            kw.update(c1=True, c2=True, fingerprints=("c1-" + "a" * 16,))
        if index == 5:
            kw.update(c2=True, fingerprints=("c2-" + "b" * 16,))
        if index == 3:
            kw.update(unjudged=True)
        rec.on_step(_step(index, **kw))
    status = render_live_status(live, now=clock.now + 1, display="live")
    counts = pg.read_live_counts(live)
    assert counts is not None
    line = pg.format_line(_view(counts, budget=100))

    def number(pattern: str, text: str) -> str:
        found = re.search(pattern, text)
        assert found, (pattern, text)
        return found.group(1)

    assert number(r"runs=(\d+)", status) == number(r"runs=(\d+)/", line) == "7"
    assert number(r"violations=(\d+) steps", status) == number(r"violations=(\d+)", line) == "2"
    assert number(r"un-judged=(\d+)", status) == number(r"un-judged=(\d+)", line) == "1"
    for name in pg.STATUSES:
        assert number(rf"{name}=(\d+)", status) == number(rf"{name}=(\d+)", line)
    assert number(r"\((\S+)/s\)", status) == number(r"(\S+) runs/s", line)  # the same rate text
    # C0/C1/C2: status lists each case's contracts; the line counts the same case records.
    listed = re.findall(r"run \d+: (\S+) ended=", status)
    assert listed == ["C1+C2", "C2"]
    assert "C0=0 C1=1 C2=2" in line
    progress = read_progress(live)
    assert progress is not None and counts.runs == progress["runs_executed"]


def test_counts_from_result_match_the_result_file(tmp_path: Path) -> None:
    cases = (
        CaseVerdict("step-0", "judged", False, False, False, termination="success"),
        CaseVerdict("step-1", "judged", False, True, True, termination="rejected"),
        CaseVerdict("step-2", "run_error", None, None, None, termination=None),
    )
    result = TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.23"),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cases=cases,
        repro_inputs=(repro_input("step-1", "inputs/step-1.tar", b"tar"),),
        provenance=Provenance("b" * 40, False, "img:ref", None),
        campaign=CampaignInfo(seed=1, budget=3, runs_to_first_violation=2),
    )
    path = tmp_path / "result.json"
    path.write_text(result.dumps(), encoding="utf-8")
    counts = pg.counts_from_result(path)
    assert counts is not None and counts.source == "result"
    assert counts.runs == result.executed == 3
    assert counts.terminations == result.termination_counts
    assert counts.unjudged == result.unjudged_steps == 1
    assert counts.violations == len(result.violating_cases) == 1
    assert counts.contracts == {"c0": 0, "c1": 1, "c2": 1} and not counts.contracts_lower_bound
    assert counts.runs_per_second is None  # result.json holds no rate: shown as ?
    assert pg.counts_from_result(tmp_path / "absent.json") is None


# ---- ETA rule ----------------------------------------------------------------------------------


def test_eta_needs_min_runs_two_snapshots_and_a_stable_rate() -> None:
    eta = pg.EtaEstimator()
    first = _live_counts(runs=12, runs_per_second=0.6, updated_at=10.0)
    eta.observe(first)
    assert eta.eta_seconds(first, pg.RUNNING) is None  # one snapshot is not evidence of a rate
    eta.observe(first)  # the same snapshot read again does not count twice
    assert eta.eta_seconds(first, pg.RUNNING) is None
    second = _live_counts(runs=24, runs_per_second=0.5, updated_at=40.0)
    eta.observe(second)
    assert eta.eta_seconds(second, pg.RUNNING) == pytest.approx((40 - 24) / 0.5)
    assert eta.eta_seconds(second, pg.CLEANUP) is None  # only while the loop runs
    jumpy = _live_counts(runs=30, runs_per_second=0.2, updated_at=70.0)  # rate moved > 25%
    eta.observe(jumpy)
    assert eta.eta_seconds(jumpy, pg.RUNNING) is None


def test_eta_is_withheld_below_min_runs_without_budget_or_from_a_result() -> None:
    eta = pg.EtaEstimator()
    for runs, at in ((4, 10.0), (pg.ETA_MIN_RUNS - 1, 20.0)):
        few = _live_counts(runs=runs, runs_per_second=0.5, updated_at=at)
        eta.observe(few)
    assert eta.eta_seconds(few, pg.RUNNING) is None
    enough = _live_counts(runs=pg.ETA_MIN_RUNS, runs_per_second=0.5, updated_at=30.0)
    eta.observe(enough)
    assert eta.eta_seconds(enough, pg.RUNNING) is not None
    assert eta.eta_seconds(_live_counts(runs=20, budget=None), pg.RUNNING) is None
    assert eta.eta_seconds(_live_counts(runs=40), pg.RUNNING) is None  # budget reached
    assert eta.eta_seconds(pg.Counts(source="result", runs=20, budget=40), pg.RUNNING) is None


# ---- terminal vs line mode, rate limiting ------------------------------------------------------


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_is_terminal_needs_a_tty_that_is_not_dumb() -> None:
    assert pg.is_terminal(_Tty(), {"TERM": "xterm"})
    assert not pg.is_terminal(_Tty(), {"TERM": "dumb"})
    assert not pg.is_terminal(io.StringIO(), {"TERM": "xterm"})


def test_terminal_mode_redraws_in_place_with_carriage_return_only() -> None:
    stream = _Tty()
    display = pg.Display(stream, terminal=True, width=lambda: 200)
    display.update(_view(_live_counts(runs=18)))
    display.update(_view(_live_counts(runs=9)))  # a shorter line must erase the longer one
    text = stream.getvalue()
    assert "\n" not in text and text.startswith("\r[explore] running runs=18/40")
    assert "\x1b" not in text  # no escape sequence, no colour (NO_COLOR needs nothing more)
    assert text.split("\r")[-1].startswith("[explore] running runs=9/40")
    display.message("TARGET-EXPLORE PASS")  # a permanent line first clears the status line
    tail = stream.getvalue()[len(text) :]
    assert tail.startswith("\r ") and tail.endswith("\rTARGET-EXPLORE PASS\n")


def test_terminal_line_is_cut_to_the_terminal_width() -> None:
    stream = _Tty()
    pg.Display(stream, terminal=True, width=lambda: 60).update(_view(_live_counts()))
    assert len(stream.getvalue().lstrip("\r")) <= 59


def test_line_mode_prints_on_phase_change_and_rate_limits_count_changes() -> None:
    stream, now = io.StringIO(), [0.0]
    display = pg.Display(stream, terminal=False, clock=lambda: now[0])
    assert display.update(_view(phase=pg.PREPARE))  # the first line
    assert not display.update(_view(phase=pg.PREPARE))  # nothing changed
    now[0] = 1.0
    assert display.update(_view(_live_counts(runs=0), phase=pg.RUNNING))  # phase change: at once
    now[0] = 5.0
    assert not display.update(_view(_live_counts(runs=3)))  # changed, but inside LINE_INTERVAL
    now[0] = 1.0 + pg.LINE_INTERVAL
    assert display.update(_view(_live_counts(runs=18)))
    now[0] += pg.LINE_INTERVAL + 1
    assert not display.update(_view(_live_counts(runs=18)))  # no change: no line
    now[0] += pg.HEARTBEAT_INTERVAL
    assert display.update(_view(_live_counts(runs=18)))  # heartbeat
    lines = stream.getvalue().splitlines()
    assert len(lines) == 4 and "\r" not in stream.getvalue()
    assert all(line.startswith("[explore] ") and "success=" in line for line in lines)


def test_no_color_and_dumb_terminals_get_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    stream = io.StringIO()
    display = pg.Display(stream, terminal=pg.is_terminal(_Tty(), {"TERM": "dumb"}))
    display.update(_view(_live_counts()))
    display.final(_view(_live_counts(state="finished"), phase=pg.COMPLETED, verdict="PASS"))
    assert "\x1b" not in stream.getvalue() and "\r" not in stream.getvalue()


# ---- ExploreProgress: phases, staleness, cause -------------------------------------------------


def _session(*launches: Any) -> Any:
    return SimpleNamespace(policy=STRICT, launches=list(launches))


def _launch(artifacts: LaunchArtifacts, **kw: Any) -> Any:
    base: dict[str, Any] = {"duration_seconds": None, "error": None, "findings": []}
    base.update(kw)
    return SimpleNamespace(request=SimpleNamespace(artifacts=artifacts), **base)


def _progress(mode: str, session: Any, tmp_path: Path, **kw: Any) -> pg.ExploreProgress:
    base: dict[str, Any] = {
        "session": session,
        "target": "node-tar",
        "requested": "latest",
        "seed": 321,
        "budget": 40,
        "out": tmp_path,
    }
    base.update(kw)
    return pg.ExploreProgress(mode, **base)


def _write_progress(live: Path, **fields: Any) -> None:
    rec, clock, _ = _recorder(live.parent, every_runs=1)
    data = rec.snapshot()
    data.update(fields)
    (live / PROGRESS_FILE).write_text(json.dumps(data), encoding="utf-8")


def test_phase_follows_the_session_and_the_files(tmp_path: Path) -> None:
    session = _session()
    run = _progress(pg.PROGRESS, session, tmp_path, wall=lambda: 1_800_000_001.0)
    assert run.phase() == pg.PREPARE and run.view().profile == "strict"
    live, report = tmp_path / "live", tmp_path / "report.json"
    record = _launch(LaunchArtifacts(report=report, live=live))
    session.launches.append(record)
    assert run.phase() == pg.RUNNING
    assert run.view().counts.source == "none"  # no snapshot yet: every count unknown
    _write_progress(live, runs_executed=12, state="running")
    view = run.view()
    assert view.phase == pg.RUNNING and view.counts.runs == 12 and view.counts.source == "live"
    _write_progress(live, runs_executed=40, state="finished")
    assert run.view().phase == pg.CLEANUP  # the loop ended; the launcher is still cleaning up
    record.duration_seconds = 50.0
    assert run.phase() == pg.CLEANUP
    run._final_phase = pg.COMPLETED
    assert run.phase() == pg.COMPLETED


def test_report_on_the_host_means_cleanup_for_targets_without_a_live_folder(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    session = _session(_launch(LaunchArtifacts(report=report)))
    run = _progress(pg.PROGRESS, session, tmp_path, target="oras-go")
    assert run.phase() == pg.RUNNING
    line = pg.format_line(run.view())
    assert "runs=?/40" in line and "success=?" in line and "C0=? C1=? C2=?" in line
    report.write_text("{}", encoding="utf-8")
    assert run.phase() == pg.CLEANUP


def test_a_snapshot_left_by_an_earlier_run_is_ignored(tmp_path: Path) -> None:
    live = tmp_path / "live"
    _write_progress(live, runs_executed=33)  # updated_at is the recorder clock: 1_800_000_000
    session = _session(_launch(LaunchArtifacts(live=live)))
    later = _progress(pg.PROGRESS, session, tmp_path, wall=lambda: 1_800_000_600.0)
    assert later.view().counts.source == "none" and later.view().counts.runs is None
    same_run = _progress(pg.PROGRESS, session, tmp_path, wall=lambda: 1_800_000_001.0)
    assert same_run.view().counts.runs == 33


def test_profile_is_read_from_the_session_policy(tmp_path: Path) -> None:
    fast = SimpleNamespace(
        policy=SimpleNamespace(profile=SimpleNamespace(value="fast")), launches=[]
    )
    assert _progress(pg.PROGRESS, fast, tmp_path).view().profile == "fast"


def test_stop_cause_quotes_the_error_and_the_sessions_diagnosis() -> None:
    finding = Finding("info", "stop-diagnosis", "stage=loop category=daemon-timeout result=x e=y")
    session = _session(_launch(LaunchArtifacts(), findings=[finding]))
    cause = pg.stop_cause(session, RuntimeError("controller run failed (exit 1)\nmore"))
    assert cause == "controller run failed (exit 1) [stage=loop category=daemon-timeout]"
    assert pg.stop_cause(_session(), KeyboardInterrupt()) == "interrupted (Ctrl-C)"
    assert pg.stop_cause(_session(), ValueError("x already exists")) == "x already exists"
    assert pg.stop_cause(_session(), None) == "stopped without a result"


def test_stream_mode_is_a_no_op(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    run = _progress(pg.STREAM, _session(), tmp_path)
    run.start()
    run.prepared("7.5.23")
    run.failed(RuntimeError("x"))
    run.finish()
    captured = capfd.readouterr()
    assert captured.out == "" and captured.err == ""
    assert list(tmp_path.iterdir()) == [] and run.log is None and run.display is None


def test_unknown_mode_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="output mode"):
        _progress("loud", _session(), tmp_path)


# ---- the launcher log (file-descriptor redirect) -----------------------------------------------


def test_launcher_log_takes_child_output_and_leaves_prints_on_the_terminal(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    log = pg.LauncherLog(tmp_path / "runtime" / "launcher.log")
    log.start()
    try:
        log.attach(None)
        subprocess.run(["sh", "-c", "echo RAW-OUT; echo RAW-ERR >&2"], check=True)
        print("driver stdout line")
        print("driver stderr line", file=sys.stderr)
        assert log.tail(1) == ["RAW-ERR"]
    finally:
        log.stop()
    captured = capfd.readouterr()
    assert captured.out == "driver stdout line\n" and captured.err == "driver stderr line\n"
    assert log.path.read_text(encoding="utf-8").splitlines() == ["RAW-OUT", "RAW-ERR"]
    subprocess.run(["sh", "-c", "echo AFTER"], check=True)  # restored: the terminal again
    assert capfd.readouterr().out == "AFTER\n"


def test_an_empty_launcher_log_is_removed(tmp_path: Path) -> None:
    log = pg.LauncherLog(tmp_path / "runtime" / "launcher.log")
    log.start()
    log.stop()
    assert not (tmp_path / "runtime").exists()


# ---- the driver's --output modes ---------------------------------------------------------------


def _adapter(explore: Any) -> TargetAdapter:
    return TargetAdapter(
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cells=lambda v, f: [],
        plan=lambda c: [],
        run=lambda c: [],
        explore=explore,
    )


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rte, "docker_problem", lambda: None)
    monkeypatch.setattr(
        rte,
        "prepare_target_image",
        lambda *a, **k: PreparedTargetImage(
            "node-tar", "latest", "7.5.23", "img:ref", "sha256:" + "c" * 64, True
        ),
    )


def _run(tmp_path: Path, mode: str | None) -> int:
    argv = ["--target", "node-tar", "--version", "latest", "--auto-prepare", "--out", str(tmp_path)]
    return rte.main(argv + (["--output", mode] if mode else []))


def _noisy_hook(result_path: Path) -> Any:
    def explore(prepared: Any, options: Any) -> ExploreOutcome:
        subprocess.run(["sh", "-c", "echo '==> [raw launcher step]'"], check=True)
        print("loop report: /somewhere/report.json")
        return ExploreOutcome(result_path=result_path, verdict="PASS", runs=20, violations=0)

    return explore


_RESULT_LINE = "TARGET-EXPLORE PASS node-tar version=7.5.23 (requested latest) runs=20 violations=0"


def test_default_output_mode_is_todays_stream(
    driver: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    hook = _noisy_hook(tmp_path / "r" / "result.json")
    monkeypatch.setattr(rte, "load_adapter", lambda t: _adapter(hook))
    assert _run(tmp_path, None) == 0
    default = capfd.readouterr()
    assert _run(tmp_path, "stream") == 0
    explicit = capfd.readouterr()
    assert default == explicit  # the driver's default is the stream mode, byte for byte
    assert default.out.splitlines()[0] == "==> [raw launcher step]"
    assert _RESULT_LINE in default.out and "result: " in default.out
    assert "[explore]" not in default.out + default.err
    assert not (tmp_path / "runtime").exists()  # no log, no redirect


def test_progress_mode_logs_the_raw_stream_and_keeps_the_result_lines(
    driver: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    hook = _noisy_hook(tmp_path / "r" / "result.json")
    monkeypatch.setattr(rte, "load_adapter", lambda t: _adapter(hook))
    assert _run(tmp_path, "progress") == 0
    captured = capfd.readouterr()
    assert "raw launcher step" not in captured.out + captured.err
    assert captured.out.splitlines()[0] == "loop report: /somewhere/report.json"
    assert (
        _RESULT_LINE in captured.out and f"result: {tmp_path / 'r' / 'result.json'}" in captured.out
    )
    assert "[explore]" not in captured.out  # progress is on stderr; stdout stays for scripts
    (log,) = (tmp_path / "runtime").glob("explore-launcher-*.log")
    assert log.read_text(encoding="utf-8") == "==> [raw launcher step]\n"
    lines = captured.err.splitlines()
    assert lines[0].startswith("[explore] node-tar latest(requested) profile=strict seed=123")
    assert f"results: {tmp_path}" in lines[0] and f"launcher output: {log}" in lines[0]
    assert "[explore] version resolved: 7.5.23" in lines
    final = lines[-1]
    assert final.startswith("[explore] completed verdict=PASS runs=?/20 | node-tar 7.5.23")
    assert "success=?" in final  # the fake result file does not exist: unknown, not zero


def test_quiet_mode_prints_no_progress_lines_but_keeps_result_lines(
    driver: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    hook = _noisy_hook(tmp_path / "r" / "result.json")
    monkeypatch.setattr(rte, "load_adapter", lambda t: _adapter(hook))
    assert _run(tmp_path, "quiet") == 0
    captured = capfd.readouterr()
    assert captured.err == "" and "raw launcher step" not in captured.out
    assert _RESULT_LINE in captured.out and "result: " in captured.out
    assert len(list((tmp_path / "runtime").glob("explore-launcher-*.log"))) == 1


@pytest.mark.parametrize("mode", ["progress", "quiet"])
def test_a_failed_run_keeps_its_exit_code_and_shows_cause_and_log_tail(
    driver: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    def boom(prepared: Any, options: Any) -> Any:
        subprocess.run(["sh", "-c", "echo 'FAILED at step: prepare controller (exit 1)' >&2"])
        raise RuntimeError("controller run failed (exit 1); see output above")

    monkeypatch.setattr(rte, "load_adapter", lambda t: _adapter(boom))
    assert _run(tmp_path, mode) == 2  # ERROR, exactly as in stream mode
    captured = capfd.readouterr()
    assert "TARGET-EXPLORE ERROR: controller run failed (exit 1)" in captured.err
    assert "cause: controller run failed (exit 1); see output above" in captured.err
    assert "[explore] aborted" in captured.err
    assert "  FAILED at step: prepare controller (exit 1)" in captured.err  # the log's last lines
    assert "launcher output: " in captured.err and captured.out == ""
    assert sys.stdout is sys.__stdout__ or not isinstance(sys.stdout, pg._Passthrough)


def test_a_setup_refusal_keeps_exit_3_and_leaves_no_log(
    driver: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    def refuse(prepared: Any, options: Any) -> Any:
        raise ValueError("result.json already exists; choose another --out")

    monkeypatch.setattr(rte, "load_adapter", lambda t: _adapter(refuse))
    assert _run(tmp_path, "progress") == 3
    err = capfd.readouterr().err
    assert "TARGET-EXPLORE SETUP: result.json already exists" in err
    assert "[explore] aborted" in err and "cause: result.json already exists" in err
    assert not (tmp_path / "runtime").exists()  # nothing ran: the empty log was removed

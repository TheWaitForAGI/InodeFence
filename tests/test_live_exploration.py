"""Mid-run observability: progress snapshot, immediate violation cases, host pull, status view."""

from __future__ import annotations

import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from inodefence import cli
from inodefence.builder import build_tar
from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_synthetic import _result as synthetic_result
from inodefence.feedback import EffectSearchPolicy
from inodefence.live_effect import live_step_from_effect
from inodefence.live_exploration import (
    CASE_SCHEMA,
    FETCH_SCHEMA,
    PROGRESS_SCHEMA,
    REPLAY_NOTE,
    LivePuller,
    LiveRecorder,
    LiveRunMeta,
    LiveStep,
    find_live_dirs,
    list_violation_cases,
    read_fetch,
    read_progress,
    render_live_status,
)
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ContractId,
    EntryType,
    ExecutionStatus,
    IdentityEvidence,
    ViolationResult,
)
from inodefence.mutator import MutationOperatorId, MutationPolicy

META = LiveRunMeta(
    target="node-tar",
    version="7.5.1",
    seed=123,
    budget=100,
    image_id="sha256:" + "a" * 64,
    search_policy="p2",
    vocab_mode="token-clean",
    engine_commit="b" * 40,
)


def _p(live: Path) -> dict:
    data = read_progress(live)
    assert data is not None, f"no progress snapshot in {live}"
    return data


def _f(live: Path) -> dict:
    data = read_fetch(live)
    assert data is not None, f"no fetch record in {live}"
    return data


class Clock:
    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def _step(index: int, **kw) -> LiveStep:
    kw.setdefault("status", "success")
    if kw.get("c0") or kw.get("c1") or kw.get("c2"):
        kw.setdefault("tar_bytes", f"tar-{index}".encode())
    return LiveStep(index=index, case_id=f"case-{index}", **kw)


def _recorder(tmp_path: Path, **kw) -> tuple[LiveRecorder, Clock, Path]:
    clock = Clock()
    live = tmp_path / "live"
    kw.setdefault("every_runs", 3)
    kw.setdefault("every_seconds", 30.0)
    return LiveRecorder(live, META, clock=clock, **kw), clock, live


def _no_dot_entries(live: Path) -> bool:
    return not any(p.name.startswith(".") for p in live.rglob("*"))


# -- recorder ----------------------------------------------------------------------------------


def test_fresh_run_is_visible_before_the_first_step(tmp_path: Path) -> None:
    _, _, live = _recorder(tmp_path)
    progress = _p(live)
    assert progress["schema"] == PROGRESS_SCHEMA
    assert progress["state"] == "running" and progress["runs_executed"] == 0
    assert progress["target"] == "node-tar" and progress["seed"] == 123
    assert progress["engine_commit"] == "b" * 40 and progress["vocab_mode"] == "token-clean"


def test_snapshot_cadence_by_runs_and_by_time(tmp_path: Path) -> None:
    rec, clock, live = _recorder(tmp_path, every_runs=3, every_seconds=30.0)
    rec.on_step(_step(0))
    rec.on_step(_step(1))
    assert _p(live)["runs_executed"] == 0  # not due yet
    rec.on_step(_step(2))
    assert _p(live)["runs_executed"] == 3  # every 3 runs
    clock.now += 31
    rec.on_step(_step(3))
    assert _p(live)["runs_executed"] == 4  # every 30 seconds
    assert _no_dot_entries(live)


def test_violation_is_written_immediately_and_atomically(tmp_path: Path) -> None:
    rec, _, live = _recorder(tmp_path, every_runs=1000)
    rec.on_step(_step(0))
    rec.on_step(_step(6, c0=False, c1=True, c2=None, fingerprints=("C1-x",), mutation="add_entry"))
    (case,) = list_violation_cases(live)
    assert case["schema"] == CASE_SCHEMA and case["run"] == 7 and case["c1"] is True
    assert case["mutation"] == "add_entry" and case["seed"] == 123
    tar = live / case["dir"] / "input.tar"
    assert tar.read_bytes() == b"tar-6"
    assert case["tar_sha256"] == sha256(b"tar-6").hexdigest()
    progress = _p(live)  # the snapshot follows the violation without waiting
    assert progress["runs_executed"] == 7
    assert progress["violations"]["steps"] == 1 and progress["violations"]["first_at_run"] == 7
    assert _no_dot_entries(live)


def test_repeated_fingerprint_counts_all_but_keeps_only_the_first_few(tmp_path: Path) -> None:
    rec, _, live = _recorder(tmp_path, per_fingerprint_cap=2)
    for i in range(5):
        rec.on_step(_step(i, c2=True, fingerprints=("C2-same",)))
    rec.on_step(_step(5, c2=True, fingerprints=("C2-same", "C0-new")))  # a new class -> kept
    progress = _p(live)
    assert progress["violations"]["by_fingerprint"] == {"C0-new": 1, "C2-same": 6}
    assert progress["violations"]["steps"] == 6
    assert progress["violations"]["unique_fingerprints"] == 2
    assert [c["run"] for c in list_violation_cases(live)] == [1, 2, 6]


def test_counts_unjudged_errors_timeouts_rejected_separately(tmp_path: Path) -> None:
    rec, _, live = _recorder(tmp_path, every_runs=1)
    rec.on_step(_step(0, unjudged=True))
    rec.on_step(_step(1, status="failed"))
    rec.on_step(_step(2, status="timed_out"))
    rec.on_step(_step(3, status="rejected"))
    progress = _p(live)
    assert progress["unjudged"] == {"steps": 1, "ratio": 0.25}
    assert progress["terminations"] == {"success": 1, "rejected": 1, "failed": 1, "timed_out": 1}


def test_files_survive_a_crash_and_close_records_how_it_ended(tmp_path: Path) -> None:
    rec, _, live = _recorder(tmp_path)
    rec.on_step(_step(0, c1=True))
    # the loop raised here: no close yet, but the case and snapshot are already on disk
    assert len(list_violation_cases(live)) == 1 and _p(live)["state"] == "running"
    rec.close(state="failed", stop_reason="RuntimeError: boom")
    progress = _p(live)
    assert progress["state"] == "failed" and progress["stop_reason"] == "RuntimeError: boom"
    with pytest.raises(RuntimeError, match="closed"):
        rec.on_step(_step(1))


def test_write_error_is_counted_and_shown_not_raised(tmp_path: Path) -> None:
    rec, _, live = _recorder(tmp_path)
    shutil.rmtree(live / "violations")
    (live / "violations").write_text("not a folder")  # case folders can no longer be made
    rec.on_step(_step(0, c1=True))  # must not raise into the exploration
    progress = _p(live)
    assert progress["write_errors"] == 1 and "violation run-000001" in progress["last_write_error"]
    assert progress["violations"]["case_dirs_written"] == 0


def test_replay_template_or_plain_note(tmp_path: Path) -> None:
    rec, _, live = _recorder(tmp_path)
    rec.on_step(_step(0, c1=True))
    assert list_violation_cases(live)[0]["replay"] is None
    assert list_violation_cases(live)[0]["replay_note"] == REPLAY_NOTE
    meta = LiveRunMeta(**{**META.as_dict(), "replay_template": "replay --tar {tar} {version}"})
    other = LiveRecorder(tmp_path / "other", meta, clock=Clock())
    other.on_step(_step(4, c2=True))
    assert list_violation_cases(tmp_path / "other")[0]["replay"] == (
        "replay --tar violations/run-000005/input.tar 7.5.1"
    )


def test_live_step_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="tar_bytes"):
        LiveStep(index=0, case_id="a", status="success", c1=True)
    with pytest.raises(ValueError, match="status"):
        LiveStep(index=0, case_id="a", status="exploded")
    with pytest.raises(ValueError, match="close state"):
        LiveRecorder(tmp_path / "live", META).close(state="running")


# -- host pull ---------------------------------------------------------------------------------


def _fake_docker_cp(source: Path, calls: list[list[str]]):
    """Emulate ``docker cp <ctr>:<dir>/. <dest>`` by copying ``source`` into ``dest``."""

    def run(argv, **kwargs):
        calls.append(argv)
        shutil.copytree(source, Path(argv[-1]), dirs_exist_ok=True)
        return subprocess.CompletedProcess(argv, 0, "", "")

    return run


def test_pull_promotes_progress_and_only_complete_cases(tmp_path: Path) -> None:
    container_live = tmp_path / "ctr"
    rec = LiveRecorder(container_live, META, clock=Clock())
    rec.on_step(_step(0, c1=True))
    (container_live / "violations" / ".tmp-run-000002-1").mkdir()  # being written
    (container_live / "violations" / "run-000003").mkdir()  # no case.json yet
    host = tmp_path / "out" / "live"
    calls: list[list[str]] = []
    runner = _fake_docker_cp(container_live, calls)
    puller = LivePuller("ctrl-1", "/evidence/live/", host, runner=runner)
    assert puller.pull_once() is True
    assert calls[0][:2] == ["docker", "cp"] and calls[0][2] == "ctrl-1:/evidence/live/."
    assert _p(host)["runs_executed"] == 1
    assert [c["run"] for c in list_violation_cases(host)] == [1]
    assert sorted(p.name for p in (host / "violations").iterdir()) == ["run-000001"]
    fetch = _f(host)
    assert fetch["schema"] == FETCH_SCHEMA and fetch["pulls_ok"] == 1 and fetch["pulls_failed"] == 0
    assert not (tmp_path / "out" / ".live.pull-tmp").exists()


def test_failed_pull_is_recorded_and_never_raises(tmp_path: Path) -> None:
    host = tmp_path / "out" / "live"
    host.mkdir(parents=True)
    (host / "progress.json").write_text('{"schema": "keep"}')

    def broken(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "Error: No such container: ctrl-1\n")

    def exploding(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 60)

    puller = LivePuller("ctrl-1", "/evidence/live", host, runner=broken)
    assert puller.pull_once() is False
    puller._runner = exploding
    assert puller.pull_once() is False
    fetch = _f(host)
    assert fetch["pulls_failed"] == 2 and fetch["pulls_ok"] == 0
    assert "TimeoutExpired" in fetch["last_error"]
    assert (host / "progress.json").read_text() == '{"schema": "keep"}'  # untouched


def test_puller_thread_makes_a_final_pull_on_stop(tmp_path: Path) -> None:
    container_live = tmp_path / "ctr"
    LiveRecorder(container_live, META, clock=Clock()).close()
    host = tmp_path / "out" / "live"
    calls: list[list[str]] = []
    puller = LivePuller(
        "c", "/l", host, interval=0.01, runner=_fake_docker_cp(container_live, calls)
    ).start()
    puller.stop()
    assert calls and _p(host)["state"] == "finished"


# -- reading / status ----------------------------------------------------------------------------


def test_status_view_shows_counts_cases_pull_and_staleness(tmp_path: Path) -> None:
    rec, clock, live = _recorder(tmp_path)
    rec.on_step(_step(0, c1=True, c0=False, fingerprints=("C1-abc",)))
    rec.on_step(_step(1, unjudged=True))
    rec._write_progress()  # flush (test only)
    text = render_live_status(live, now=clock.now + 5, display="live")
    assert text.startswith("live: running, snapshot 5s ago")
    assert "runs=2" in text and "violations=1 steps / 1 unique" in text
    assert "un-judged=1 (ratio 0.5)" in text
    assert "run 1: C1 ended=success REPRO-CHECK fp=C1-abc" in text  # observation not recorded
    assert "violations/run-000001/" in text
    assert "ended: success=2 rejected=0 failed=0 timed_out=0" in text
    assert "STALE" not in text
    assert "STALE" in render_live_status(live, now=clock.now + 3600)


def test_find_live_dirs_and_cli_status_on_a_running_exploration(tmp_path: Path, capsys) -> None:
    out = tmp_path / "out"
    rec = LiveRecorder(out / "live", META)
    rec.on_step(_step(0, c2=True))
    assert find_live_dirs(out) == [out / "live"]
    assert find_live_dirs(out / "live") == [out / "live"]
    assert cli.main(["status", str(out)]) == 0  # no result.json yet: live view only
    printed = capsys.readouterr().out
    assert printed.startswith("live: running") and "violation cases on disk: 1" in printed


# -- node-tar adapter (real effect loop, synthetic producer: no Docker) --------------------------


def test_adapter_on_real_effect_loop_steps_feeds_the_recorder(tmp_path: Path) -> None:
    seed = ArchiveCase((ArchiveEntry("seed", EntryType.REGULAR, b"seed"),))
    config = EffectCampaignConfig(
        random_seed=7,
        execution_budget=6,
        search_policy=EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
        mutation_policy=MutationPolicy.M1,
    )
    rec = LiveRecorder(tmp_path / "live", META, every_runs=1, clock=Clock())
    seen: list[LiveStep] = []

    def on_step(step) -> None:
        live = live_step_from_effect(step)
        seen.append(live)
        rec.on_step(live)

    result = run_effect_campaign((seed,), synthetic_result, config, on_step=on_step)
    rec.close()
    assert [s.index for s in seen] == list(range(6))
    assert seen[0].origin == "seed" and seen[0].mutation is None
    assert all(s.origin == "mutation" and s.mutation for s in seen[1:])
    assert all(s.status == "success" for s in seen)
    assert seen[3].parent_case_id == result.steps[3].parent_case_id
    assert _p(tmp_path / "live")["runs_executed"] == 6
    assert _p(tmp_path / "live")["state"] == "finished"


def _stand_in(
    status: ExecutionStatus,
    violations: tuple[ViolationResult, ...],
    *,
    integrity_valid: bool = True,
) -> SimpleNamespace:
    case = ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, b"x"),))
    base = SimpleNamespace(
        case=case, execution=SimpleNamespace(status=status), violations=violations
    )
    attempt = SimpleNamespace(operator_id=MutationOperatorId.ADD_ENTRY, applied=True)
    feedback = SimpleNamespace(new_violation_fingerprints=())
    trace = SimpleNamespace(integrity_valid=integrity_valid)
    return SimpleNamespace(
        index=4,
        origin=SimpleNamespace(value="mutation"),
        parent_case_id="parent-1",
        mutation_attempt=attempt,
        feedback=feedback,
        result=SimpleNamespace(base_result=base, trace=trace),
    )


def _identity_hit(internal: str) -> ViolationResult:
    evidence = (IdentityEvidence(internal, "outside/protected", 1, 10),)
    return ViolationResult(ContractId.C1, True, evidence, "shared identity", ())


def test_adapter_maps_verdicts_fingerprints_and_tar_like_the_report() -> None:
    clean = ViolationResult(ContractId.C0, False, (), "no change", ())
    step = _stand_in(ExecutionStatus.SUCCESS, (clean, _identity_hit("extract/a")))
    live = live_step_from_effect(step)
    assert (live.c0, live.c1, live.c2) == (False, True, None)
    assert live.violated and live.tar_bytes == build_tar(step.result.base_result.case)
    assert live.mutation == "add_entry" and live.mutation_applied is True
    assert live.parent_case_id == "parent-1" and live.index == 4 and live.origin == "mutation"
    (fp,) = live.fingerprints
    assert fp.startswith("C1-") and len(fp) == 3 + 16
    assert fp == live_step_from_effect(step).fingerprints[0]  # stable
    other = live_step_from_effect(_stand_in(ExecutionStatus.SUCCESS, (_identity_hit("extract/b"),)))
    assert other.fingerprints != live.fingerprints  # different evidence, different class
    assert live.observation == ("C1: shared identity",)


def test_adapter_keeps_verdicts_for_a_timeout_rejection_or_crash() -> None:
    # The oracle judges the snapshots whatever the exit status: a violation during a timeout counts.
    for status in (ExecutionStatus.TIMED_OUT, ExecutionStatus.REJECTED, ExecutionStatus.FAILED):
        hit = live_step_from_effect(_stand_in(status, (_identity_hit("extract/x"),)))
        assert hit.status == status.value and hit.c1 is True and hit.violated
        assert hit.tar_bytes is not None and hit.fingerprints and not hit.unjudged


def test_progress_json_is_plain_json_on_disk(tmp_path: Path) -> None:
    _, _, live = _recorder(tmp_path)
    data = json.loads((live / "progress.json").read_text(encoding="utf-8"))
    assert data["budget"] == 100 and data["violations"]["per_fingerprint_cap"] == 3


def test_adapter_unjudged_uses_the_result_file_rule() -> None:
    # Same rule as CaseVerdict.is_unjudged: observed, but no contract verdict at all.
    clean = ViolationResult(ContractId.C0, False, (), "ok", ())
    for status in (ExecutionStatus.SUCCESS, ExecutionStatus.REJECTED, ExecutionStatus.TIMED_OUT):
        no_verdict = live_step_from_effect(_stand_in(status, ()))
        assert (no_verdict.c0, no_verdict.c1, no_verdict.c2) == (None, None, None)
        assert no_verdict.unjudged is True
        assert live_step_from_effect(_stand_in(status, (clean,))).unjudged is False


def test_repro_check_and_observation_completeness_reach_the_case_file(tmp_path: Path) -> None:
    rec, _, live = _recorder(tmp_path)
    rec.on_step(_step(0, c1=True, observation_complete=True))  # success + complete
    rec.on_step(_step(1, c1=True, status="timed_out", observation_complete=True))
    rec.on_step(_step(2, c2=True, observation_complete=False))
    cases = {c["run"]: c for c in list_violation_cases(live)}
    assert cases[1]["needs_repro_check"] is False and cases[1]["observation_complete"] is True
    assert cases[2]["needs_repro_check"] is True and cases[2]["status"] == "timed_out"
    assert cases[3]["needs_repro_check"] is True and cases[3]["observation_complete"] is False


def test_adapter_observation_completeness_from_the_loop() -> None:
    hit = (_identity_hit("extract/a"),)
    complete = live_step_from_effect(_stand_in(ExecutionStatus.SUCCESS, hit))
    assert complete.observation_complete is True and not complete.needs_repro_check
    partial = live_step_from_effect(_stand_in(ExecutionStatus.SUCCESS, hit, integrity_valid=False))
    assert partial.observation_complete is False and partial.needs_repro_check

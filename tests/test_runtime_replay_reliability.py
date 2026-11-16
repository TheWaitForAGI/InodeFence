"""PR 3 replay reliability: image lookup states, kept evidence, same-second names, diagnosis.

Every Docker answer is a fake (runner injection); no daemon is touched.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import inodefence.drivers.run_target_replay as driver
from inodefence.case_replay import (
    CaseReplayError,
    ReplayRun,
    publish_replay,
    read_replays,
    replay_dir_name,
)
from inodefence.live_exploration import list_violation_cases, render_live_status
from test_case_replay import IMAGE, _case_folder, _round

MOMENT = datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC)


def _adapter(monkeypatch, hook) -> None:
    monkeypatch.setattr(driver, "load_adapter", lambda target: SimpleNamespace(replay=hook))


def _docker(*, image: str | None = IMAGE, image_timeout=False, info=(0, "29.9.3\n", "")):
    calls: list[list[str]] = []

    def run(argv, **kw):
        calls.append(argv)
        if argv[:3] == ["docker", "image", "inspect"]:
            if image_timeout:
                raise subprocess.TimeoutExpired(argv, kw["timeout"])
            if image is None:
                return subprocess.CompletedProcess(argv, 1, "", "No such image")
            return subprocess.CompletedProcess(argv, 0, image + "\n", "")
        if argv[:2] == ["docker", "info"]:
            if isinstance(info, BaseException):
                raise info
            return subprocess.CompletedProcess(argv, *info)
        raise AssertionError(argv)

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_silent_docker_is_not_reported_as_an_absent_image(tmp_path, monkeypatch, capsys) -> None:
    called: list = []
    _adapter(monkeypatch, lambda req, work: called.append(req))
    folder = _case_folder(tmp_path)
    stalled = subprocess.TimeoutExpired(["docker"], 10)
    runner = _docker(image_timeout=True, info=stalled)
    assert driver.main([str(folder)], runner=runner) == 3  # same exit code as before
    err = capsys.readouterr().err
    assert "Docker did not answer" in err and "Docker daemon timeout" in err
    assert "not on this host" not in err
    assert not called and not list(folder.parent.glob("*.replay-*"))

    runner = _docker(image_timeout=True)
    assert driver.main([str(folder), "--dry-run"], runner=runner) == 3
    out, err = capsys.readouterr()
    assert json.loads(out)["image_lookup"] == "unknown"
    assert "answers `docker info` but not the image question" in err


def test_absent_image_message_is_unchanged(tmp_path, monkeypatch, capsys) -> None:
    _adapter(monkeypatch, lambda req, work: None)
    assert driver.main([str(_case_folder(tmp_path))], runner=_docker(image=None)) == 3
    assert "is not on this host. It is not prepared again" in capsys.readouterr().err


def _stopping_hook(*, smoke_exit=1, report=True, complete=False, stop="BackendError: x"):
    def hook(request, work: Path) -> ReplayRun:
        evidence = work / "evidence"
        evidence.mkdir()
        name = "inodefence-case-replay-r"
        (evidence / f"{name}.steps.jsonl").write_text(json.dumps(_round()) + "\n")
        if report:
            body = {"complete": complete, "rounds": [_round()]}
            if not complete:
                body["stop_reason"] = stop
            (evidence / f"{name}.json").write_text(json.dumps(body))
        return ReplayRun(
            rounds=(_round(),),
            complete=False,
            stop_reason=stop,
            runner={"smoke_exit": smoke_exit, "run_id": "r"},
        )

    return hook


def test_an_infrastructure_stop_keeps_its_evidence_and_says_where(
    tmp_path, monkeypatch, capsys
) -> None:
    stop = "BackendError: container runtime cleanup inspect failed: "
    _adapter(monkeypatch, _stopping_hook(stop=stop))
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker()) == 1  # incomplete: same code as before
    (record,) = read_replays(folder)
    kept = folder.parent / record["dir"] / "evidence"
    assert sorted(p.name for p in kept.iterdir()) == [
        "inodefence-case-replay-r.json",
        "inodefence-case-replay-r.steps.jsonl",
    ]
    diagnosis = record["replay"]["diagnosis"]
    assert diagnosis["stage"] == "loop" and diagnosis["category"] == "cleanup_inspect"
    assert diagnosis["evidence"] == [
        "inodefence-case-replay-r.json",
        "inodefence-case-replay-r.steps.jsonl",
    ]
    err = capsys.readouterr().err
    assert "REPLAY DIAGNOSIS: stage=loop category=cleanup_inspect" in err
    assert str(kept) in err and "REPLAY INCOMPLETE" in err
    # Existing keys stay; the case folder itself is untouched.
    assert record["replay"]["complete"] is False and record["replay"]["stop_reason"] == stop
    assert sorted(p.name for p in folder.iterdir()) == ["case.json", "input.tar"]


@pytest.mark.parametrize(
    ("hook", "stage"),
    [
        (_stopping_hook(smoke_exit=125, complete=True), "cleanup"),
        (_stopping_hook(report=False), "loop"),  # rounds in the journal, no report
    ],
)
def test_replay_stage_from_exit_code_and_files(tmp_path, monkeypatch, hook, stage) -> None:
    _adapter(monkeypatch, hook)
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker()) == 1
    (record,) = read_replays(folder)
    assert record["replay"]["diagnosis"]["stage"] == stage
    assert record["replay"]["diagnosis"]["category"] == "UNKNOWN"


def test_a_complete_replay_records_no_diagnosis_and_no_checkout_path(tmp_path, monkeypatch) -> None:
    _adapter(monkeypatch, lambda req, work: ReplayRun(rounds=(_round(),) * 3, complete=True))
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker()) == 0
    (record,) = read_replays(folder)
    assert record["replay"]["diagnosis"] is None
    repository = record["replay"]["repository"]
    assert set(repository) == {"checkout_id", "dirty_tracked_files"}
    assert len(repository["checkout_id"]) == 12
    text = (folder.parent / record["dir"] / "replay.json").read_text()
    assert str(driver.REPO_ROOT.resolve()) not in text  # the checkout path is never written
    assert not (folder.parent / record["dir"] / "evidence").exists()  # nothing to keep


def test_same_second_replays_get_a_suffix_and_every_reader_sees_them(tmp_path) -> None:
    folder = _case_folder(tmp_path)
    evidence = tmp_path / "ev"
    evidence.mkdir()
    first = publish_replay(folder, _record("a"), moment=MOMENT, evidence=evidence)
    second = publish_replay(folder, _record("b"), moment=MOMENT, evidence=evidence)
    third = publish_replay(folder, _record("c"), moment=MOMENT, evidence=evidence)
    base = replay_dir_name(folder, MOMENT)
    assert [first.name, second.name, third.name] == [base, f"{base}-2", f"{base}-3"]
    assert [r["note"] for r in read_replays(folder)] == ["a", "b", "c"]
    live = folder.parent.parent
    assert [c["dir"] for c in list_violation_cases(live)] == ["violations/run-000005"]
    status = render_live_status(live, display="live")
    assert f"[{base}-3/]" in status  # status shows the newest, suffixed one


def test_without_evidence_publish_is_exactly_as_before(tmp_path) -> None:
    folder = _case_folder(tmp_path)
    publish_replay(folder, _record("a"), moment=MOMENT)
    with pytest.raises(CaseReplayError, match="already exists; a replay never overwrites"):
        publish_replay(folder, _record("b"), moment=MOMENT)
    (only,) = folder.parent.glob("*.replay-*")
    assert sorted(p.name for p in only.iterdir()) == ["replay.json"]


def test_a_record_that_cannot_be_written_is_printed_not_lost(tmp_path, monkeypatch, capsys) -> None:
    _adapter(monkeypatch, lambda req, work: ReplayRun(rounds=(_round(),) * 3, complete=True))

    def refuse(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(driver, "publish_replay", refuse)
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker()) == 1
    out, err = capsys.readouterr()
    assert "REPLAY FAILED: the record could not be written" in err
    assert json.loads(out)["summary"]["rounds_done"] == 3


def _record(note: str) -> dict:
    return {"schema": "inodefence-case-replay-v1", "note": note, "replay": {}, "rounds": []}


# -- the replay launches through a STRICT runtime session -------------------------------------


def _session_hook(returncode: int = 0, complete: bool = True):
    """A hook that launches through the session it is handed (``request.runtime``)."""
    from inodefence.drivers.runtime.hooks import LaunchArtifacts

    seen: dict = {}

    def hook(request, work: Path) -> ReplayRun:
        session = request.runtime
        seen["session"] = session
        evidence = work / "evidence"
        evidence.mkdir()
        report = evidence / "inodefence-case-replay-r.json"
        body = {"complete": complete, "rounds": [_round()] * (3 if complete else 1)}
        if not complete:
            body["stop_reason"] = "BackendError: container runtime cleanup inspect failed: "

        def runner(argv, **kwargs):
            report.write_text(json.dumps(body))
            return subprocess.CompletedProcess(argv, returncode)

        done = session.launch(
            Path("/repo/scripts/local_node_tar_smoke.sh"),
            ["replay"],
            runner=runner,
            env={"RUN_ID": "replay-abc-1"},
            artifacts=LaunchArtifacts(report=report),
        )
        return ReplayRun(
            rounds=tuple(body["rounds"]),
            complete=complete and done.returncode == 0,
            stop_reason=body.get("stop_reason"),
            runner={"smoke_exit": done.returncode, "run_id": "replay-abc-1"},
        )

    hook.seen = seen  # type: ignore[attr-defined]
    return hook


def test_replay_launches_through_a_strict_session_and_publishes_its_record(
    tmp_path, monkeypatch
) -> None:
    from inodefence.drivers.runtime.session import RuntimeSession

    hook = _session_hook()
    _adapter(monkeypatch, hook)
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker()) == 0
    assert isinstance(hook.seen["session"], RuntimeSession)  # type: ignore[attr-defined]
    (record,) = read_replays(folder)
    published = folder.parent / record["dir"] / "evidence" / driver.RUNTIME_RECORD_NAME
    runtime = json.loads(published.read_text())
    assert runtime["profile"] == "strict" and runtime["target"] == "node-tar"
    (launch,) = runtime["launches"]
    assert launch["classification"] == "completed"
    assert str(tmp_path) not in published.read_text()  # no host paths in the record
    assert sorted(p.name for p in folder.iterdir()) == ["case.json", "input.tar"]
    assert record["replay"]["complete"] is True and record["replay"]["diagnosis"] is None


def test_the_runtime_record_does_not_hide_the_replay_report_from_the_diagnosis(
    tmp_path, monkeypatch, capsys
) -> None:
    _adapter(monkeypatch, _session_hook(returncode=1, complete=False))
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker()) == 1
    (record,) = read_replays(folder)
    diagnosis = record["replay"]["diagnosis"]
    assert (diagnosis["stage"], diagnosis["category"]) == ("loop", "cleanup_inspect")
    assert "inodefence-case-replay-r.json" in diagnosis["evidence"]
    err = capsys.readouterr().err
    assert err.count("DIAGNOSIS") == 1 and "REPLAY DIAGNOSIS: stage=loop" in err
    assert "TARGET-EXPLORE DIAGNOSIS" not in err


def test_a_blocked_replay_stops_once_with_exit_3_and_publishes_nothing(
    tmp_path, monkeypatch, capsys
) -> None:
    from inodefence.drivers.runtime import diagnostics
    from inodefence.drivers.runtime.hooks import Finding

    class Block:
        def before(self, request):
            return [Finding("block", "run-resources-exist", "container x already exists")]

        def after(self, outcome):
            return []

    monkeypatch.setattr(diagnostics, "OBSERVERS", (Block(),))
    _adapter(monkeypatch, _session_hook())
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker()) == 3
    err = capsys.readouterr().err
    assert err.count("run-resources-exist") == 1
    assert "REPLAY STOPPED: run-resources-exist: container x already exists" in err
    assert not list(folder.parent.glob("*.replay-*"))


def test_an_unpublished_runtime_record_goes_to_stderr(tmp_path, monkeypatch, capsys) -> None:
    _adapter(monkeypatch, _session_hook())

    def refuse(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(driver, "publish_replay", refuse)
    assert driver.main([str(_case_folder(tmp_path))], runner=_docker()) == 1
    out, err = capsys.readouterr()
    assert json.loads(out)["summary"]["rounds_done"] == 3  # stdout: the replay record as before
    line = next(x for x in err.splitlines() if x.startswith("REPLAY RUNTIME RECORD"))
    assert "(not published; publish failed)" in line and '"profile": "strict"' in line


def test_shipped_observer_on_a_replay_prints_only_the_replay_diagnosis(
    tmp_path, monkeypatch, capsys
) -> None:
    from inodefence.drivers.runtime import diagnostics, health

    probed: list = []
    checked: list = []
    monkeypatch.setattr(diagnostics, "OBSERVERS", diagnostics.DEFAULT_OBSERVERS)
    monkeypatch.setattr(health, "run_resources_exist", lambda c, v, **kw: checked.append(c))
    monkeypatch.setattr(health, "probe_daemon", lambda **kw: probed.append(1))
    monkeypatch.setattr(
        health, "run_leftovers", lambda c, v, **kw: [f"this run's container {c} still exists"]
    )
    _adapter(monkeypatch, _session_hook(returncode=1, complete=False))
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker()) == 1
    err = capsys.readouterr().err
    assert err.count("DIAGNOSIS") == 1 and "REPLAY DIAGNOSIS: stage=loop" in err
    assert "TARGET-EXPLORE" not in err and not probed  # no explore line, no extra daemon probe
    assert checked == ["inodefence-local-controller-replay-abc-1"]  # the launcher's own name
    assert "RUNTIME DIAGNOSTIC WARN leftover-resources: this run's container" in err
    (record,) = read_replays(folder)
    runtime = json.loads(
        (folder.parent / record["dir"] / "evidence" / driver.RUNTIME_RECORD_NAME).read_text()
    )
    assert runtime["kind"] == "replay" and runtime["launches"][0]["kind"] == "replay"

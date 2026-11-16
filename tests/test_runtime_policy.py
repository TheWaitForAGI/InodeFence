"""drivers.runtime: STRICT launches unchanged, the runtime record, the diagnostics contract.

No docker: every launcher runner is a fake that records what it was called with.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import inodefence.drivers.run_target_explore as rte
from inodefence.drivers import repo
from inodefence.drivers.launcher import LAUNCHERS, RUN_RESOURCES, run_launcher, run_resources
from inodefence.drivers.lazy_import import LazyModule
from inodefence.drivers.run_target import ExploreOutcome, PreparedTargetImage, TargetAdapter
from inodefence.drivers.runtime import diagnostics, policy
from inodefence.drivers.runtime.hooks import (
    RECORDED_ENV,
    Finding,
    LaunchArtifacts,
    LaunchBlocked,
    LaunchOutcome,
    LaunchRequest,
)
from inodefence.drivers.runtime.session import RECORD_DIR, SCHEMA, RuntimeSession
from inodefence.target_result import ResultMode

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "inodefence"
SCRIPT = REPO / "scripts" / "local_node_tar_smoke.sh"
ENV = {
    "RUN_ID": "7.5.2-1-20",
    "DEMO_BUDGET": "20",
    "INODEFENCE_EVIDENCE_DIR": "/home/someone/out",
    "DEMO_HOST_LIVE_DIR": "/home/someone/out/live",
    "HOME": "/home/someone",
    "GITHUB_TOKEN": "secret",
}


class Recorder:
    """A launcher runner that records its call and returns a fixed exit code (or raises)."""

    def __init__(self, returncode: int = 0, raises: BaseException | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.returncode = returncode
        self.raises = raises

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        self.calls.append((argv, kwargs))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode)


# ---- STRICT: the launch is exactly the call the hook made before ----


def test_strict_session_calls_the_runner_exactly_like_a_plain_launch() -> None:
    plain, recorded = Recorder(), Recorder()
    run_launcher(SCRIPT, ["explore"], runner=plain, env=dict(ENV), cwd="/r", check=False)
    session = RuntimeSession(target="node-tar")
    run_launcher(
        SCRIPT, ["explore"], runner=recorded, env=dict(ENV), session=session, cwd="/r", check=False
    )
    assert plain.calls == recorded.calls
    assert plain.calls[0][0] == ["bash", str(SCRIPT), "explore"]


def test_strict_is_the_default_profile_and_has_no_flags() -> None:
    # a profile is added only with a measured flag: FAST has exactly one (tests/test_runtime_fast)
    assert [p.value for p in policy.RuntimeProfile] == ["strict", "fast"]
    assert policy.STRICT.flags() == {} and RuntimeSession(target="x").policy is policy.STRICT
    assert policy.FAST.flags() == {"reuse_shared_images": True}
    assert policy.PROFILES == {"strict": policy.STRICT, "fast": policy.FAST}


def test_session_returns_the_runners_result_and_records_the_launch() -> None:
    session = RuntimeSession(target="node-tar")
    done = session.launch(SCRIPT, ["explore"], runner=Recorder(returncode=4), env=dict(ENV))
    assert done.returncode == 4
    (launch,) = session.launches
    assert launch.returncode == 4 and launch.classification is None  # classified at finish()
    session.finish(result_written=False)
    assert launch.classification == "failed"
    assert (launch.request.controller, launch.request.volume) == (
        "inodefence-local-controller-7.5.2-1-20",
        "inodefence-local-runtime-7.5.2-1-20",
    )
    assert (
        launch.request.script == "local_node_tar_smoke.sh"
        and launch.request.run_id == ENV["RUN_ID"]
    )
    assert launch.request.env == {"RUN_ID": ENV["RUN_ID"], "DEMO_BUDGET": "20"}


def test_a_runner_exception_is_recorded_and_re_raised_unchanged() -> None:
    session = RuntimeSession(target="node-tar")
    with pytest.raises(KeyboardInterrupt):
        session.launch(SCRIPT, [], runner=Recorder(raises=KeyboardInterrupt()), env=dict(ENV))
    session.finish(result_written=False)
    (launch,) = session.launches
    assert launch.returncode is None and launch.error == "KeyboardInterrupt"
    assert launch.classification == "runner-error"


# ---- the runtime record ----


def test_record_is_an_additional_file_that_is_never_overwritten(tmp_path: Path) -> None:
    session = RuntimeSession(target="node-tar")
    assert session.write(tmp_path) is None and not (tmp_path / RECORD_DIR).exists()  # no launch
    session.launch(SCRIPT, ["explore"], runner=Recorder(), env=dict(ENV))
    first = session.write(tmp_path)
    second = session.write(tmp_path)
    assert first is not None and second is not None and first != second
    assert first.parent == second.parent == tmp_path / RECORD_DIR
    assert first.name.startswith(ENV["RUN_ID"] + "-") and second.name.endswith(".1.json")
    assert sorted(p.name for p in first.parent.iterdir()) == sorted([first.name, second.name])
    record = json.loads(first.read_text(encoding="utf-8"))
    assert record["schema"] == SCHEMA and record["profile"] == "strict" and record["policy"] == {}
    assert [launch["returncode"] for launch in record["launches"]] == [0]


def test_record_holds_no_path_and_no_environment_beyond_the_whitelist(tmp_path: Path) -> None:
    session = RuntimeSession(target="node-tar")
    artifacts = LaunchArtifacts(report=tmp_path / "report.json", live=tmp_path / "live")
    session.launch(SCRIPT, ["explore"], runner=Recorder(), env=dict(ENV), artifacts=artifacts)
    session.finish(result_written=True)
    text = session.write(tmp_path).read_text(encoding="utf-8")  # type: ignore[union-attr]
    for leaked in ("/home/someone", "secret", "GITHUB_TOKEN", "HOME", str(REPO), str(tmp_path)):
        assert leaked not in text
    assert not any(key.endswith("_DIR") for key in RECORDED_ENV)


def _launching_adapter(runner: Recorder, result: Path) -> TargetAdapter:
    def explore(prepared: Any, options: Any) -> ExploreOutcome:
        done = run_launcher(
            SCRIPT, ["explore"], runner=runner, env=dict(ENV), session=options.runtime
        )
        if done.returncode != 0:
            raise RuntimeError(f"controller run failed (exit {done.returncode})")
        return ExploreOutcome(result_path=result, verdict="PASS", runs=20, violations=0)

    return TargetAdapter(
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cells=lambda v, f: [],
        plan=lambda c: [],
        run=lambda c: [],
        explore=explore,
    )


def _main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: Recorder, *extra: str) -> int:
    def prepare(*a: Any, **k: Any) -> PreparedTargetImage:
        return PreparedTargetImage("node-tar", "7.5.2", "7.5.2", "img", "sha256:" + "c" * 64, True)

    monkeypatch.setattr(rte, "docker_problem", lambda: None)
    monkeypatch.setattr(rte, "load_adapter", lambda t: _launching_adapter(runner, tmp_path / "r"))
    monkeypatch.setattr(rte, "prepare_target_image", prepare)
    argv = ["--version", "7.5.2", "--auto-prepare", "--out", str(tmp_path / "out"), *extra]
    return rte.main(argv)


def _records(tmp_path: Path) -> list[dict[str, Any]]:
    folder = tmp_path / "out" / RECORD_DIR
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]


def test_explore_writes_the_record_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(tmp_path, monkeypatch, Recorder()) == 0
    (record,) = _records(tmp_path)
    assert record["profile"] == "strict" and record["launches"][0]["classification"] == "completed"
    assert "RUNTIME" not in capsys.readouterr().err  # STRICT, no diagnostics: nothing printed


def test_explore_writes_the_record_when_the_launcher_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(tmp_path, monkeypatch, Recorder(returncode=125)) == 2  # exit path unchanged
    (record,) = _records(tmp_path)
    assert record["launches"][0]["returncode"] == 125
    assert "TARGET-EXPLORE ERROR: controller run failed (exit 125)" in capsys.readouterr().err


def test_explore_writes_the_record_when_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(KeyboardInterrupt):
        _main(tmp_path, monkeypatch, Recorder(raises=KeyboardInterrupt()))
    (record,) = _records(tmp_path)
    assert record["launches"][0]["error"] == "KeyboardInterrupt"


def test_an_unknown_profile_is_refused_before_anything_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = Recorder()
    with pytest.raises(SystemExit) as stopped:
        _main(tmp_path, monkeypatch, runner, "--profile", "turbo")
    assert stopped.value.code == 3 and runner.calls == []
    assert "invalid choice: 'turbo'" in capsys.readouterr().err


def test_explicit_strict_is_the_default_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    default, explicit = Recorder(), Recorder()
    assert _main(tmp_path / "a", monkeypatch, default) == 0
    assert _main(tmp_path / "b", monkeypatch, explicit, "--profile", "strict") == 0
    assert default.calls == explicit.calls
    assert "RUNTIME" not in capsys.readouterr().err


def test_a_record_that_cannot_be_written_never_changes_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(self: Any, out: Path) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(RuntimeSession, "write", refuse)
    assert _main(tmp_path, monkeypatch, Recorder()) == 0
    assert "runtime record not written (read-only)" in capsys.readouterr().err


# ---- the diagnostics contract ----


class Observer:
    def __init__(self, before: list[Finding] | None = None, fail: str | None = None) -> None:
        self._before = before or []
        self._fail = fail
        self.seen: list[Any] = []

    def before(self, request: LaunchRequest) -> list[Finding]:
        self.seen.append(request)
        if self._fail == "before":
            raise OSError("probe broke")
        return self._before

    def after(self, outcome: LaunchOutcome) -> list[Finding]:
        self.seen.append(outcome)
        if self._fail == "after":
            raise OSError("probe broke")
        return [Finding("info", "seen", "after")]


def test_observers_see_the_request_and_the_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    observer = Observer([Finding("warn", "w", "a warning")])
    monkeypatch.setattr(diagnostics, "OBSERVERS", (observer,))
    session = RuntimeSession(target="node-tar")
    session.launch(SCRIPT, [], runner=Recorder(returncode=1), env=dict(ENV))
    assert len(observer.seen) == 1  # the after check runs once the run is over
    session.finish(result_written=True)
    session.finish(result_written=True)  # once per launch
    request, outcome = observer.seen
    assert isinstance(request, LaunchRequest) and outcome.returncode == 1
    assert outcome.result_written and outcome.prefix == "TARGET-EXPLORE"
    assert outcome.request.controller == "inodefence-local-controller-7.5.2-1-20"
    assert [f.code for f in session.launches[0].findings] == ["w", "seen"]


@pytest.mark.parametrize("phase", ["before", "after"])
def test_a_failing_observer_is_recorded_not_swallowed_and_changes_nothing(
    phase: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(diagnostics, "OBSERVERS", (Observer(fail=phase),))
    runner = Recorder(returncode=3)
    session = RuntimeSession(target="node-tar")
    assert session.launch(SCRIPT, [], runner=runner, env=dict(ENV)).returncode == 3
    session.finish(result_written=False)
    assert len(runner.calls) == 1
    (failure,) = session.launches[0].diagnostic_failures
    assert failure == f"Observer.{phase}: OSError: probe broke"
    assert "RUNTIME DIAGNOSTIC FAILED (not a check result)" in capsys.readouterr().err


def test_a_failing_classifier_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(outcome: LaunchOutcome) -> str:
        raise KeyError("x")

    monkeypatch.setattr(diagnostics, "classify", broken)
    session = RuntimeSession(target="node-tar")
    assert session.launch(SCRIPT, [], runner=Recorder(), env=dict(ENV)).returncode == 0
    session.finish(result_written=True)
    assert session.launches[0].classification is None
    assert session.launches[0].diagnostic_failures == ["classify: KeyError: 'x'"]


def test_a_block_finding_stops_the_launch_as_a_setup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        diagnostics, "OBSERVERS", (Observer([Finding("block", "stale", "stale controller")]),)
    )
    runner = Recorder()
    assert _main(tmp_path, monkeypatch, runner) == 3
    assert runner.calls == []
    err = capsys.readouterr().err
    assert err.count("stale controller") == 1  # printed once, as the driver's setup refusal
    assert "TARGET-EXPLORE SETUP: stale: stale controller" in err
    (record,) = _records(tmp_path)
    assert record["launches"][0]["classification"] == "blocked"
    assert issubclass(LaunchBlocked, ValueError)


def test_shipped_diagnostics_are_the_read_only_health_observer() -> None:
    # OBSERVERS is emptied for every test (tests/conftest.py); the shipped default is this.
    assert [type(o).__name__ for o in diagnostics.DEFAULT_OBSERVERS] == ["HealthObserver"]
    request = LaunchRequest("node-tar", "strict", "s.sh", (), None)
    assert diagnostics.classify(LaunchOutcome(request, 0, 1.0)) == "completed"
    assert diagnostics.classify(LaunchOutcome(request, 2, 1.0)) == "failed"


# ---- direction ----


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
    return names


def test_the_engine_never_imports_the_runtime_policy() -> None:
    product = {SRC / "cli.py", SRC / "locate.py"}
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if not path.is_relative_to(SRC / "drivers") and path not in product
        if any(name.startswith("inodefence.drivers.runtime") for name in _imports(path))
    ]
    assert offenders == []


def test_the_runtime_package_uses_only_the_standard_library_itself_and_the_launcher() -> None:
    # (the launcher module is itself stdlib-only: it names the launchers and their resources;
    # the shared abort classifier is a stdlib-only engine leaf the diagnosis reuses unchanged)
    allowed = (
        "inodefence.drivers.runtime",
        "inodefence.drivers.launcher",
        "inodefence.evaluation.abort_classification",
    )
    for path in [*(SRC / "drivers" / "runtime").glob("*.py"), SRC / "drivers" / "launcher.py"]:
        for name in _imports(path):
            top = name.partition(".")[0]
            assert (
                top in sys.stdlib_module_names or top == "__future__" or (name.startswith(allowed))
            ), (path.name, name)


def test_the_runtime_package_imports_nothing_eagerly() -> None:
    # doctor loads one leaf of the package without the drivers
    assert _imports(SRC / "drivers" / "runtime" / "__init__.py") == set()


# ---- PR 2 carry-overs ----


def test_a_missing_repository_package_is_guidance_and_exit_3(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stop:
        LazyModule("no_such_repository_package.repro").anything  # noqa: B018
    assert stop.value.code == repo.REPOSITORY_CODE_EXIT == 3
    err = capsys.readouterr().err
    assert "`no_such_repository_package` is not importable" in err
    assert "inodefence verify / explore / replay" in err and "Traceback" not in err


def test_a_missing_module_inside_an_importable_package_is_raised_unchanged() -> None:
    with pytest.raises(ModuleNotFoundError, match="inodefence.no_such_module"):
        LazyModule("inodefence.no_such_module").anything  # noqa: B018


def test_old_layout_refusal_names_the_clone_and_the_missing_package() -> None:
    message = repo.OLD_LAYOUT_REFUSAL.format(root="/clones/old")
    assert "/clones/old has no src/inodefence/drivers/" in message and "git pull" in message


# ---- what the diagnostics are handed ----


@pytest.mark.parametrize("target", sorted(LAUNCHERS))
def test_run_resources_are_the_launchers_own_names(target: str) -> None:
    text = (REPO / "scripts" / LAUNCHERS[target]).read_text(encoding="utf-8")
    controller, volume = RUN_RESOURCES[target]
    assert f'CONTROLLER="{controller}${{RUN_ID:+-$RUN_ID}}"' in text
    assert f'VOLUME="{volume}${{RUN_ID:+-$RUN_ID}}"' in text
    assert run_resources(target, "r1") == (f"{controller}-r1", f"{volume}-r1")
    assert run_resources(target, "") == run_resources(target, None) == (controller, volume)


def test_artifacts_name_the_report_and_the_logs_beside_it(tmp_path: Path) -> None:
    report = tmp_path / "inodefence-effect-explore-r1.json"
    assert LaunchArtifacts(report=report, live=tmp_path / "live").evidence() == (
        report,
        tmp_path / "inodefence-effect-explore-r1.steps.jsonl",
        tmp_path / "inodefence-effect-explore-r1.calls.jsonl",
        tmp_path / "live",
    )
    assert LaunchArtifacts().evidence() == ()


def test_the_driver_reports_whether_a_result_was_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observer = Observer()
    monkeypatch.setattr(diagnostics, "OBSERVERS", (observer,))
    assert _main(tmp_path, monkeypatch, Recorder()) == 0
    assert observer.seen[-1].result_written is True
    observer.seen.clear()
    assert _main(tmp_path / "again", monkeypatch, Recorder(returncode=1)) == 2
    assert observer.seen[-1].result_written is False


def test_explore_checks_docker_first_like_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = Recorder()
    monkeypatch.setattr(rte, "load_adapter", lambda t: _launching_adapter(runner, tmp_path / "r"))
    monkeypatch.setattr(rte, "prepare_target_image", lambda *a, **k: pytest.fail("no prepare"))
    monkeypatch.setattr(rte, "docker_problem", lambda: "docker daemon not reachable; start it")
    argv = ["--version", "7.5.2", "--auto-prepare", "--out", str(tmp_path / "out")]
    assert rte.main(argv) == 3
    assert "TARGET-EXPLORE SETUP: docker daemon not reachable; start it" in capsys.readouterr().err
    assert runner.calls == [] and not (tmp_path / "out").exists()


def test_a_launch_without_a_session_is_never_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    # node-tar replay and decompress's own entry launch with no session: no observer runs there,
    # so no block can arise on a path whose driver would not print it as its setup refusal
    monkeypatch.setattr(
        diagnostics, "OBSERVERS", (Observer([Finding("block", "stale", "stale controller")]),)
    )
    runner = Recorder()
    assert run_launcher(SCRIPT, ["replay"], runner=runner, env=dict(ENV)).returncode == 0
    assert len(runner.calls) == 1


# ---- replay: the node-tar replay launch runs through the driver's STRICT session ----


def _replay_request(runtime: Any = None) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        case_id="c" * 64, tar_sha256="t" * 64, image_id="sha256:" + "i" * 64, runtime=runtime
    )


def _replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: Any) -> Recorder:
    import inodefence.drivers.node_tar.replay as nr

    monkeypatch.setattr(nr, "replay_input_line", lambda request: "{}\n")
    monkeypatch.setattr(nr.os, "getpid", lambda: 4242)
    runner = Recorder(returncode=1)  # no report: an incomplete replay, as the hook reads it
    work = tmp_path / ("with" if request.runtime else "plain")
    work.mkdir()
    nr.replay(request, work, runner=runner)
    return runner


def test_replay_launch_is_the_same_call_with_and_without_a_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = _replay(tmp_path, monkeypatch, _replay_request())
    session = RuntimeSession(target="node-tar", kind="replay")
    recorded = _replay(tmp_path, monkeypatch, _replay_request(session))
    (plain_argv, plain_kwargs), (argv, kwargs) = plain.calls[0], recorded.calls[0]
    assert argv == plain_argv and argv[-1] == "replay"
    # the scratch folder differs between the two calls; nothing else does
    strip = {"INODEFENCE_EVIDENCE_DIR", "REPLAY_INPUT"}
    assert {k: v for k, v in kwargs["env"].items() if k not in strip} == {
        k: v for k, v in plain_kwargs["env"].items() if k not in strip
    }
    assert {k: v for k, v in kwargs.items() if k != "env"} == {
        k: v for k, v in plain_kwargs.items() if k != "env"
    }


def test_replay_launch_is_recorded_as_a_replay_with_the_launchers_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import inodefence.drivers.node_tar.replay as nr

    session = RuntimeSession(target="node-tar", kind="replay")
    assert session.prefix == "REPLAY"
    _replay(tmp_path, monkeypatch, _replay_request(session))
    (launch,) = session.launches
    run_id = f"replay-{'c' * 12}-4242"
    assert launch.request.kind == "replay" and launch.request.run_id == run_id
    # local_node_tar_smoke.sh names controller/volume from RUN_ID the same way in every mode
    assert (launch.request.controller, launch.request.volume) == (
        f"inodefence-local-controller-{run_id}",
        f"inodefence-local-runtime-{run_id}",
    )
    report, _journal = nr.report_paths(tmp_path / "with" / "evidence", run_id)
    assert launch.request.artifacts.report == report
    session.finish(result_written=False)
    record = json.loads(session.render())
    assert record["kind"] == "replay" and record["launches"][0]["kind"] == "replay"
    assert str(tmp_path) not in session.render()


def test_the_launcher_names_its_resources_once_for_every_mode() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count("\nCONTROLLER=") == 1 and text.count("\nVOLUME=") == 1


def test_an_explore_session_keeps_its_prefix() -> None:
    assert RuntimeSession(target="node-tar").prefix == "TARGET-EXPLORE"
    assert RuntimeSession(target="node-tar", prefix="X").prefix == "X"

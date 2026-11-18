"""The FAST runtime profile: its one flag (reuse verified shared images), and what it never changes.

No docker: Docker's answers come from :class:`FakeDocker`, the launcher from :class:`Launcher`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import inodefence.drivers.node_tar.explore as nte
import inodefence.drivers.run_target_explore as rte
from inodefence import cli
from inodefence.drivers.launcher import LAUNCHERS, launcher_path, run_launcher
from inodefence.drivers.run_target import ExploreOutcome, PreparedTargetImage, TargetAdapter
from inodefence.drivers.runtime import health, policy, shared_images
from inodefence.drivers.runtime.hooks import LaunchBlocked
from inodefence.drivers.runtime.session import RECORD_DIR, RuntimeSession
from inodefence.target_result import ResultMode

REPO = Path(__file__).resolve().parents[1]
NODE_TAR = launcher_path("node-tar", REPO)
PYTHON_TARFILE = launcher_path("python-tarfile", REPO)
IDS = {
    "inodefence-controller:local": "sha256:" + "a" * 64,
    "inodefence-helper:local": "sha256:" + "b" * 64,
}


class FakeDocker:
    """``health.ask_docker`` for the two questions FAST asks: the context and the two image ids."""

    def __init__(self, ids: dict[str, str] | None = None, context: str = "default") -> None:
        self.ids = dict(ids or {})
        self.context = context
        self.silent = False
        self.asked: list[list[str]] = []

    def __call__(self, args: list[str], **_: Any) -> health.DockerAnswer:
        self.asked.append(list(args))
        if self.silent:
            return health.DockerAnswer(None, "", "", timed_out=True)
        if args == ["context", "show"]:
            return health.DockerAnswer(0, self.context + "\n", "")
        assert args[:2] == ["--context", self.context] and args[2:4] == ["image", "inspect"]
        found = [self.ids[ref] for ref in args[6:] if ref in self.ids]
        missing = len(found) != len(args[6:])
        return health.DockerAnswer(
            1 if missing else 0, "\n".join(found) + "\n", "No such image" if missing else ""
        )


class Launcher:
    """A launcher runner: records each call; a ``BUILD_ONLY=1`` call "builds" the shared images."""

    def __init__(
        self,
        docker: FakeDocker,
        *,
        returncode: int = 0,
        build_returncode: int = 0,
        builds: dict[str, str] | None = IDS,
        raises: BaseException | None = None,
    ) -> None:
        self.docker = docker
        self.returncode = returncode
        self.build_returncode = build_returncode
        self.builds = builds
        self.raises = raises
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        self.calls.append((argv, kwargs))
        if kwargs["env"].get("BUILD_ONLY") == "1":
            if self.build_returncode == 0 and self.builds is not None:
                self.docker.ids.update(self.builds)
            return subprocess.CompletedProcess(argv, self.build_returncode)
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode)

    def envs(self) -> list[dict[str, str]]:
        return [kwargs["env"] for _, kwargs in self.calls]


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    fake = FakeDocker()
    monkeypatch.setattr(health, "ask_docker", fake)
    return fake


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {
        "RUN_ID": "7.5.23-1-20",
        "DEMO_BUDGET": "20",
        "DEMO_SEED": "1",
        "HOME": str(tmp_path / "home"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }


def fast(target: str = "node-tar") -> RuntimeSession:
    return RuntimeSession(target=target, policy=policy.FAST)


def verify(env: dict[str, str], docker: FakeDocker) -> None:
    """Leave a valid stamp for ``IDS`` behind, as a build-only run would."""
    docker.ids.update(IDS)
    assert shared_images.record(REPO, env).verified


# ---- shared_images: the proof ----


def test_inputs_digest_covers_every_build_input(tmp_path: Path) -> None:
    for name in shared_images.BUILD_INPUTS:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / name, tmp_path / name)
    assert shared_images.inputs_digest(tmp_path) == shared_images.inputs_digest(REPO)
    seen = {shared_images.inputs_digest(tmp_path)}
    for name in shared_images.BUILD_INPUTS:
        with (tmp_path / name).open("a", encoding="utf-8") as stream:
            stream.write("# changed\n")
        seen.add(shared_images.inputs_digest(tmp_path))
    assert len(seen) == 1 + len(shared_images.BUILD_INPUTS)
    (tmp_path / shared_images.BUILD_INPUTS[0]).unlink()
    with pytest.raises(OSError):
        shared_images.inputs_digest(tmp_path)


def test_the_dockerfiles_copy_nothing_outside_the_build_inputs() -> None:
    copied = set()
    for name in shared_images.BUILD_INPUTS:
        if not name.endswith("Dockerfile"):
            continue
        for line in (REPO / name).read_text(encoding="utf-8").splitlines():
            words = line.split()
            if words and words[0].upper() in ("COPY", "ADD"):
                sources = [w for w in words[1:-1] if not w.startswith("--")]
                assert not any(w.startswith("--from") for w in words), line
                copied.update(sources)
    assert copied and copied <= set(shared_images.BUILD_INPUTS)


def test_launcher_tables_match_the_launcher_scripts() -> None:
    assert set(LAUNCHERS.values()) == shared_images.SKIP_BUILD_LAUNCHERS
    controller, helper = shared_images.SHARED_IMAGES
    for name in LAUNCHERS.values():
        text = (REPO / "scripts" / name).read_text(encoding="utf-8")
        assert f"CONTROLLER_IMAGE={controller}\n" in text and f"HELPER_IMAGE={helper}\n" in text
        assert 'if [ "$SKIP_BUILD" = 1 ]; then' in text
        # the two shared builds read only the declared Dockerfiles (context: the repository root)
        builds = re.findall(r'-f "\$REPO_ROOT/(\S+)" -t "\$(CONTROLLER|HELPER)_IMAGE"', text)
        assert sorted(builds) == [
            (".devcontainer/Dockerfile", "CONTROLLER"),
            ("tools/container-helper/Dockerfile", "HELPER"),
        ]
        build_only = 'if [ "$BUILD_ONLY" = 1 ]; then' in text
        assert build_only == (name in shared_images.BUILD_ONLY_LAUNCHERS)
        if build_only:  # it leaves before any volume or controller is created
            # (launchers sourcing scripts/launcher_bounded.sh create it with launcher_create_volume)
            create = (
                "launcher_create_volume" if "launcher_create_volume" in text else "dk volume create"
            )
            assert text.index('if [ "$BUILD_ONLY" = 1 ]; then') < text.index(create)


def test_not_verified_without_images_a_stamp_or_an_answer(
    env: dict[str, str], docker: FakeDocker
) -> None:
    assert "not on this host" in shared_images.check(REPO, env).reason
    docker.ids.update(IDS)
    answer = shared_images.check(REPO, env)
    assert not answer.verified and "not been verified" in answer.reason
    assert answer.image_ids == IDS and answer.context == "default"
    docker.silent = True
    assert not shared_images.check(REPO, env).verified
    assert not shared_images.record(REPO, env).verified  # nothing is stamped on silence
    docker.silent = False
    assert not shared_images.check(REPO, env).verified


def test_a_stamp_verifies_only_the_same_context_inputs_ids_and_day(
    env: dict[str, str], docker: FakeDocker, tmp_path: Path
) -> None:
    verify(env, docker)
    answer = shared_images.check(REPO, env)
    assert answer.verified and answer.image_ids == IDS and answer.verified_at
    record = answer.as_record()
    assert str(tmp_path) not in json.dumps(record) and record["inputs_sha256"]

    stamp = shared_images.stamp_path(env)
    assert stamp == tmp_path / "cache" / "inodefence" / "shared-images-v1.json"
    saved = json.loads(stamp.read_text(encoding="utf-8"))
    epoch = saved["contexts"]["default"]["verified_epoch"]
    limit = shared_images.MAX_AGE_SECONDS
    assert shared_images.check(REPO, env, now=epoch + limit).verified
    assert "older than 24 h" in shared_images.check(REPO, env, now=epoch + limit + 1).reason
    assert not shared_images.check(REPO, env, now=epoch - 1).verified  # a stamp from the future

    docker.ids["inodefence-helper:local"] = "sha256:" + "c" * 64  # rebuilt by another checkout
    assert "rebuilt or replaced" in shared_images.check(REPO, env).reason
    docker.ids.update(IDS)
    assert shared_images.check(REPO, env).verified

    docker.context = "other"
    assert "this Docker context" in shared_images.check(REPO, env).reason
    assert (
        "this Docker context"
        in shared_images.check(REPO, {**env, "INODEFENCE_DOCKER_CONTEXT": "other"}).reason
    )
    docker.context = "default"

    saved["contexts"]["default"]["inputs_sha256"] = "0" * 64  # an edited Dockerfile / helper
    stamp.write_text(json.dumps(saved), encoding="utf-8")
    assert "build inputs changed" in shared_images.check(REPO, env).reason
    stamp.write_text("not json", encoding="utf-8")
    assert "not been verified" in shared_images.check(REPO, env).reason


def test_a_stamp_that_cannot_be_saved_still_verifies_this_run(
    env: dict[str, str], docker: FakeDocker, tmp_path: Path
) -> None:
    docker.ids.update(IDS)
    (tmp_path / "cache").write_text("a file, not a folder", encoding="utf-8")
    answer = shared_images.record(REPO, env)
    assert answer.verified and "not remembered for the next run" in answer.reason
    assert not shared_images.check(REPO, env).verified


# ---- the session: what FAST changes in a launch, and what it does not ----


def strict_call(env: dict[str, str]) -> tuple[list[str], dict[str, Any]]:
    runner = Launcher(FakeDocker())
    run_launcher(
        NODE_TAR,
        ["explore"],
        runner=runner,
        env=dict(env),
        session=RuntimeSession("node-tar"),
        cwd="/r",
    )
    (call,) = runner.calls
    return call


#: FAST's second flag (#536 option 1): its main launch also carries the identity probe
#: interval; a build-only launch before it does not.
FAST_IDENTITY = {"DEMO_IDENTITY_CHECK_EVERY": "200"}


def test_verified_images_add_skip_build_and_nothing_else(
    env: dict[str, str], docker: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    verify(env, docker)
    runner, session = Launcher(docker), fast()
    done = run_launcher(
        NODE_TAR, ["explore"], runner=runner, env=dict(env), session=session, cwd="/r"
    )
    assert done.returncode == 0
    (argv, kwargs) = runner.calls[0]
    strict_argv, strict_kwargs = strict_call(env)
    assert len(runner.calls) == 1 and argv == strict_argv
    assert kwargs == {
        **strict_kwargs,
        "env": {**strict_kwargs["env"], "SKIP_BUILD": "1", **FAST_IDENTITY},
    }
    assert "SKIP_BUILD" not in env  # the hook's own environment is not modified

    session.finish(result_written=True)
    record = session.to_json()
    assert record["profile"] == "fast" and record["policy"] == {
        "reuse_shared_images": True,
        "identity_check_every": 200,
    }
    (launch,) = record["launches"]
    assert launch["env"]["SKIP_BUILD"] == "1" and launch["profile"] == "fast"
    applied = launch["policy_applied"]["reuse_shared_images"]
    assert applied["applied"] is True and applied["unchanged_after_launch"] is True
    assert applied["shared_images"]["image_ids"] == IDS and launch["findings"] == []
    err = capsys.readouterr().err
    assert "TARGET-EXPLORE RUNTIME: profile=fast reuse_shared_images=applied (SKIP_BUILD=1" in err


def test_unverified_images_are_built_by_the_launcher_first_then_reused(
    env: dict[str, str], docker: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    runner, session = Launcher(docker), fast()
    run_launcher(NODE_TAR, ["explore"], runner=runner, env=dict(env), session=session, cwd="/r")
    strict_argv, strict_kwargs = strict_call(env)
    assert [argv for argv, _ in runner.calls] == [strict_argv, strict_argv]
    build_env, run_env = runner.envs()
    assert build_env == {**strict_kwargs["env"], "BUILD_ONLY": "1"}
    assert run_env == {**strict_kwargs["env"], "SKIP_BUILD": "1", **FAST_IDENTITY}
    assert all(kwargs["cwd"] == "/r" for _, kwargs in runner.calls)

    session.finish(result_written=True)
    build, run = session.to_json()["launches"]
    assert build["classification"] == "shared-image-build" and build["env"]["BUILD_ONLY"] == "1"
    assert build["policy_applied"]["reuse_shared_images"]["shared_images"]["verified"] is True
    assert run["classification"] == "completed"
    assert run["policy_applied"]["reuse_shared_images"]["applied"] is True
    err = capsys.readouterr().err
    assert "have not been verified" not in err  # the images were absent: that is the reason said
    assert "not on this host" in err and "building them first" in err

    again = Launcher(docker)  # the stamp is remembered: the next run launches once
    run_launcher(NODE_TAR, ["explore"], runner=again, env=dict(env), session=fast(), cwd="/r")
    assert again.envs() == [run_env]


@pytest.mark.parametrize(
    ("launcher", "message"),
    [
        (
            lambda d: Launcher(d, build_returncode=1),
            "the shared-image build failed (launcher exit 1)",
        ),
        (lambda d: Launcher(d, builds=None), "the build reported success but a shared image"),
    ],
)
def test_a_failed_build_stops_before_anything_runs(
    launcher: Any, message: str, env: dict[str, str], docker: FakeDocker
) -> None:
    runner, session = launcher(docker), fast()
    with pytest.raises(LaunchBlocked, match=re.escape(message)):
        run_launcher(NODE_TAR, ["explore"], runner=runner, env=dict(env), session=session)
    assert [e.get("BUILD_ONLY") for e in runner.envs()] == ["1"]  # the run itself never started
    session.finish(result_written=False)
    (build,) = session.to_json()["launches"]
    assert build["classification"] in ("shared-image-build-failed", "shared-image-build")
    assert not shared_images.check(REPO, env).verified


def test_a_launcher_without_a_build_only_run_falls_back_visibly(
    env: dict[str, str], docker: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    runner, session = Launcher(docker), fast("python-tarfile")
    run_launcher(PYTHON_TARFILE, runner=runner, env=dict(env), session=session, check=False)
    plain = Launcher(FakeDocker())
    run_launcher(PYTHON_TARFILE, runner=plain, env=dict(env), check=False)
    # exactly STRICT's launch (the launcher builds the images) plus the identity interval
    ((fast_argv, fast_kwargs),), ((plain_argv, plain_kwargs),) = runner.calls, plain.calls
    assert fast_argv == plain_argv
    assert fast_kwargs == {**plain_kwargs, "env": {**plain_kwargs["env"], **FAST_IDENTITY}}
    session.finish(result_written=True)
    (launch,) = session.to_json()["launches"]
    applied = launch["policy_applied"]["reuse_shared_images"]
    assert applied["applied"] is False and "no build-only run" in applied["reason"]
    assert "SKIP_BUILD" not in launch["env"]
    err = capsys.readouterr().err
    assert "profile=fast reuse_shared_images=not-applied" in err and "as strict launches" in err

    verify(env, docker)  # verified by another target's run: python-tarfile reuses them too
    reused = Launcher(docker)
    run_launcher(PYTHON_TARFILE, runner=reused, env=dict(env), session=fast("python-tarfile"))
    assert reused.envs()[0]["SKIP_BUILD"] == "1" and len(reused.calls) == 1


def test_an_operator_set_switch_is_left_alone_and_said(
    env: dict[str, str], docker: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    preset = {**env, "SKIP_BUILD": "1"}
    runner, session = Launcher(docker), fast()
    run_launcher(NODE_TAR, ["explore"], runner=runner, env=dict(preset), session=session)
    assert runner.envs() == [{**preset, **FAST_IDENTITY}] and docker.asked == []
    applied = session.to_json()["launches"][0]["policy_applied"]["reuse_shared_images"]
    assert applied["applied"] is False and "already set" in applied["reason"]
    assert "reuse_shared_images=not-applied" in capsys.readouterr().err


def test_a_shared_image_that_moved_during_the_run_is_a_recorded_warning(
    env: dict[str, str], docker: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    verify(env, docker)

    class Moves(Launcher):
        def __call__(self, argv: list[str], **kwargs: Any) -> Any:
            self.docker.ids["inodefence-helper:local"] = "sha256:" + "d" * 64
            return super().__call__(argv, **kwargs)

    session = fast()
    done = run_launcher(NODE_TAR, ["explore"], runner=Moves(docker), env=dict(env), session=session)
    assert done.returncode == 0  # recorded, never a changed exit code
    session.finish(result_written=True)
    (launch,) = session.to_json()["launches"]
    assert [f["code"] for f in launch["findings"]] == ["shared-images-changed"]
    assert launch["policy_applied"]["reuse_shared_images"]["unchanged_after_launch"] is False
    assert "RUNTIME DIAGNOSTIC WARN shared-images-changed" in capsys.readouterr().err


def test_a_replay_never_runs_under_fast() -> None:
    with pytest.raises(ValueError, match="a replay always runs under the strict profile"):
        RuntimeSession(target="node-tar", policy=policy.FAST, kind="replay")
    assert RuntimeSession(target="node-tar", kind="replay").policy is policy.STRICT


# ---- fail-closed: a failing or interrupted run ends exactly as under STRICT ----


def _adapter(runner: Launcher, env: dict[str, str], result: Path) -> TargetAdapter:
    def explore(prepared: Any, options: Any) -> ExploreOutcome:
        done = run_launcher(
            NODE_TAR, ["explore"], runner=runner, env=dict(env), session=options.runtime
        )
        if done.returncode != 0:
            raise RuntimeError(f"controller run failed (exit {done.returncode})")
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("{}", encoding="utf-8")
        return ExploreOutcome(result_path=result, verdict="PASS", runs=20, violations=0)

    return TargetAdapter(
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cells=lambda v, f: [],
        plan=lambda c: [],
        run=lambda c: [],
        explore=explore,
    )


def _main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: Launcher,
    env: dict[str, str],
    *extra: str,
) -> int:
    def prepare(*a: Any, **k: Any) -> PreparedTargetImage:
        return PreparedTargetImage(
            "node-tar", "7.5.23", "7.5.23", "img", "sha256:" + "c" * 64, True
        )

    result = tmp_path / "out" / "x-result" / "result.json"
    monkeypatch.setattr(rte, "docker_problem", lambda: None)
    monkeypatch.setattr(rte, "load_adapter", lambda t: _adapter(runner, env, result))
    monkeypatch.setattr(rte, "prepare_target_image", prepare)
    argv = ["--version", "7.5.23", "--auto-prepare", "--out", str(tmp_path / "out"), *extra]
    return rte.main(argv)


def _records(tmp_path: Path) -> list[dict[str, Any]]:
    folder = tmp_path / "out" / RECORD_DIR
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]


@pytest.mark.parametrize("profile", ["strict", "fast"])
def test_exit_codes_do_not_depend_on_the_profile(
    profile: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str],
    docker: FakeDocker,
    capsys: pytest.CaptureFixture[str],
) -> None:
    verify(env, docker)
    flag = ("--profile", profile)
    assert _main(tmp_path / "ok", monkeypatch, Launcher(docker), env, *flag) == 0
    failed = Launcher(docker, returncode=125)
    assert _main(tmp_path / "failed", monkeypatch, failed, env, *flag) == 2
    assert "TARGET-EXPLORE ERROR: controller run failed (exit 125)" in capsys.readouterr().err
    assert not (tmp_path / "failed" / "out" / "x-result").exists()  # no result, under any profile
    (record,) = _records(tmp_path / "failed")
    assert record["profile"] == profile and record["launches"][-1]["returncode"] == 125
    with pytest.raises(KeyboardInterrupt):
        stopped = Launcher(docker, raises=KeyboardInterrupt())
        _main(tmp_path / "stopped", monkeypatch, stopped, env, *flag)
    (record,) = _records(tmp_path / "stopped")
    assert record["launches"][-1]["error"] == "KeyboardInterrupt"


def test_fast_with_a_failing_build_is_a_setup_refusal_not_a_strict_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str],
    docker: FakeDocker,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = Launcher(docker, build_returncode=1)
    assert _main(tmp_path, monkeypatch, runner, env, "--profile", "fast") == 3
    assert [e.get("BUILD_ONLY") for e in runner.envs()] == ["1"]  # never launched as STRICT
    err = capsys.readouterr().err
    assert "TARGET-EXPLORE SETUP: profile fast: the shared-image build failed" in err
    (record,) = _records(tmp_path)
    assert record["profile"] == "fast"
    assert [x["classification"] for x in record["launches"]] == ["shared-image-build-failed"]


def test_the_result_folder_names_the_profile_only_when_it_is_not_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], docker: FakeDocker
) -> None:
    verify(env, docker)
    assert _main(tmp_path / "s", monkeypatch, Launcher(docker), env) == 0
    assert _main(tmp_path / "f", monkeypatch, Launcher(docker), env, "--profile", "fast") == 0
    strict_dir, fast_dir = (tmp_path / p / "out" / "x-result" for p in "sf")
    assert sorted(p.name for p in strict_dir.iterdir()) == ["result.json"]  # STRICT: unchanged
    assert sorted(p.name for p in fast_dir.iterdir()) == ["result.json", "runtime-record.json"]
    published = json.loads((fast_dir / rte.RESULT_RUNTIME_RECORD).read_text(encoding="utf-8"))
    (record,) = _records(tmp_path / "f")
    assert published == record and published["profile"] == "fast"
    assert published["policy"] == {"reuse_shared_images": True, "identity_check_every": 200}
    assert published["launches"][0]["classification"] == "completed"
    (strict_record,) = _records(tmp_path / "s")
    assert strict_record["profile"] == "strict" and strict_record["policy"] == {}
    assert "policy_applied" not in strict_record["launches"][0]


def test_dry_run_names_the_profile_only_when_it_is_not_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str],
    docker: FakeDocker,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = Launcher(docker)
    assert _main(tmp_path, monkeypatch, runner, env, "--dry-run") == 0
    default = json.loads(capsys.readouterr().out)
    assert _main(tmp_path, monkeypatch, runner, env, "--dry-run", "--profile", "strict") == 0
    assert json.loads(capsys.readouterr().out) == default and "runtime_profile" not in default
    assert _main(tmp_path, monkeypatch, runner, env, "--dry-run", "--profile", "fast") == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned.pop("runtime_profile") == {
        "profile": "fast",
        "policy": {"reuse_shared_images": True, "identity_check_every": 200},
    }
    assert planned == default and runner.calls == [] and docker.asked == []


# ---- the same inputs reach the loop under both profiles (node-tar hook, fake launcher) ----


class _NoPull:
    def __init__(self, *a: Any, **k: Any) -> None: ...

    def start(self) -> _NoPull:
        return self

    def stop(self, **k: Any) -> None: ...


def test_node_tar_hook_hands_the_loop_the_same_inputs_under_both_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docker: FakeDocker
) -> None:
    monkeypatch.setattr(nte, "LivePuller", _NoPull)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    docker.ids.update(IDS)
    assert shared_images.record(nte.REPO_ROOT, {"XDG_CACHE_HOME": str(tmp_path / "cache")}).verified
    prepared = PreparedTargetImage(
        "node-tar",
        "7.5.23",
        "7.5.23",
        "inodefence-node-tar-registry:7.5.23",
        "sha256:" + "c" * 64,
        True,
    )
    seen: dict[str, tuple[list[str], dict[str, Any]]] = {}
    for name, chosen in policy.PROFILES.items():
        out = tmp_path / name

        def runner(argv: list[str], *, out: Path = out, name: str = name, **kwargs: Any) -> Any:
            seen[name] = (argv, kwargs)
            report = nte.controller_report_path(out, "rid")
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("{}", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0)

        nte.run_controller(
            prepared,
            out=out,
            run_id="rid",
            budget=20,
            seed=123,
            python="py",
            runner=runner,
            session=RuntimeSession(target="node-tar", policy=chosen),
        )
    (strict_argv, strict_kwargs), (fast_argv, fast_kwargs) = seen["strict"], seen["fast"]
    assert fast_argv == strict_argv
    strict_env, fast_env = dict(strict_kwargs.pop("env")), dict(fast_kwargs.pop("env"))
    assert fast_kwargs == strict_kwargs
    assert fast_env.pop("SKIP_BUILD") == "1" and "SKIP_BUILD" not in strict_env
    assert fast_env.pop("DEMO_IDENTITY_CHECK_EVERY") == "200"
    assert "DEMO_IDENTITY_CHECK_EVERY" not in strict_env
    # the only other difference is where each run writes (two output folders)
    paths = ("INODEFENCE_EVIDENCE_DIR", "DEMO_HOST_LIVE_DIR")
    assert {k: v for k, v in fast_env.items() if k not in paths} == {
        k: v for k, v in strict_env.items() if k not in paths
    }
    for key in (
        "DEMO_SEED",
        "DEMO_BUDGET",
        "EXPLORE_IMAGE",
        "TAR_VERSION",
        "DEMO_SENTINEL_SEED",
        "DEMO_SENTINEL_COUNT",
        "DEMO_OBSERVER_INTEGRITY_POLICY",
        "DEMO_LIVE_DIR",
    ):
        assert fast_env[key] == strict_env[key]


# ---- the CLI option ----


def test_cli_profiles_are_the_policy_profiles_strict_first() -> None:
    assert cli.RUNTIME_PROFILES[0] == policy.STRICT.profile.value
    assert sorted(cli.RUNTIME_PROFILES) == sorted(policy.PROFILES)


def test_cli_forwards_only_a_non_default_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(
        cli, "run_driver", lambda root, driver, argv, prog=None: calls.append(argv) or 0
    )
    base = ["explore", "--version", "7.5.23", "--auto-prepare", "--out", str(tmp_path)]
    assert cli.main(base) == 0 and cli.main([*base, "--profile", "strict"]) == 0
    assert cli.main([*base, "--profile", "fast"]) == 0
    default, strict, chosen = calls
    assert default == strict and "--profile" not in default
    assert chosen == [*default, "--profile", "fast"]
    with pytest.raises(SystemExit) as refused:
        cli.main([*base, "--profile", "turbo"])
    assert refused.value.code == 3 and "invalid choice: 'turbo'" in capsys.readouterr().err
    with pytest.raises(SystemExit) as refused:  # replay has no such option: it always runs strict
        cli.main(["replay", str(tmp_path), "--profile", "fast"])
    assert refused.value.code == 2 and len(calls) == 3  # the top-level usage error, as before


def test_a_build_only_run_is_listed_only_once_it_is_over(
    env: dict[str, str], docker: FakeDocker
) -> None:
    # the progress display reads the session's last launch: a finished build is not a finished run
    session = fast()
    listed: list[list[str | None]] = []

    class Watching(Launcher):
        def __call__(self, argv: list[str], **kwargs: Any) -> Any:
            listed.append([launch.classification for launch in session.launches])
            return super().__call__(argv, **kwargs)

    run_launcher(NODE_TAR, ["explore"], runner=Watching(docker), env=dict(env), session=session)
    assert listed == [[], ["shared-image-build", None]]

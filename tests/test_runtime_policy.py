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
from inodefence.drivers.launcher import run_launcher
from inodefence.drivers.run_target import ExploreOutcome, PreparedTargetImage, TargetAdapter
from inodefence.drivers.runtime import policy
from inodefence.drivers.runtime.hooks import (
    RECORDED_ENV,
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


def test_strict_is_the_only_profile_and_has_no_flags() -> None:
    # a later profile is added only with a measured flag (no FAST in name only)
    assert [p.value for p in policy.RuntimeProfile] == ["strict"]
    assert policy.STRICT.flags() == {} and RuntimeSession(target="x").policy is policy.STRICT


def test_session_returns_the_runners_result_and_records_the_launch() -> None:
    session = RuntimeSession(target="node-tar")
    done = session.launch(SCRIPT, ["explore"], runner=Recorder(returncode=4), env=dict(ENV))
    assert done.returncode == 4
    (launch,) = session.launches
    assert launch.returncode == 4
    assert (
        launch.request.script == "local_node_tar_smoke.sh"
        and launch.request.run_id == ENV["RUN_ID"]
    )
    assert launch.request.env == {"RUN_ID": ENV["RUN_ID"], "DEMO_BUDGET": "20"}


def test_a_runner_exception_is_recorded_and_re_raised_unchanged() -> None:
    session = RuntimeSession(target="node-tar")
    with pytest.raises(KeyboardInterrupt):
        session.launch(SCRIPT, [], runner=Recorder(raises=KeyboardInterrupt()), env=dict(ENV))
    (launch,) = session.launches
    assert launch.returncode is None and launch.error == "KeyboardInterrupt"


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
    session.launch(SCRIPT, ["explore"], runner=Recorder(), env=dict(ENV))
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
    assert record["profile"] == "strict" and record["launches"][0]["returncode"] == 0
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


def test_no_runtime_profile_option_is_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # one profile only: an option with a single choice is not offered (neither driver nor CLI)
    with pytest.raises(SystemExit):
        _main(tmp_path, monkeypatch, Recorder(), "--runtime-profile", "strict")
    assert "unrecognized arguments: --runtime-profile" in capsys.readouterr().err


def test_a_record_that_cannot_be_written_never_changes_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(self: Any, out: Path) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(RuntimeSession, "write", refuse)
    assert _main(tmp_path, monkeypatch, Recorder()) == 0
    assert "runtime record not written (read-only)" in capsys.readouterr().err


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


def test_the_runtime_package_uses_only_the_standard_library_and_itself() -> None:
    for path in (SRC / "drivers" / "runtime").glob("*.py"):
        for name in _imports(path):
            top = name.partition(".")[0]
            assert (
                top in sys.stdlib_module_names
                or top == "__future__"
                or (name.startswith("inodefence.drivers.runtime"))
            ), (path.name, name)

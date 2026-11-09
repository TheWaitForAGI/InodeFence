"""Exercise the real shell through #297's real watchdog wrapper, with inert doubles."""

import subprocess
from dataclasses import replace
from typing import Any, cast

import pytest
import scripts.run_exp0 as launcher

from test_local_node_tar_smoke import run_fake_docker
from test_run_exp0 import (
    BEFORE,
    TARGET_IMAGES,
    VICTIM,
    _cell,
    _deadline_setup,
    _fake_runner,
    _index,
    _result_lines,
)
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine

pytestmark = pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")


@pytest.mark.parametrize(
    ("controller", "volume", "host", "watchdog", "expected", "state"),
    [
        (0, 0, 0, False, 0, "complete"),
        (41, 0, 0, False, 41, "record-inconsistent"),
        (0, 42, 0, False, 42, "record-inconsistent"),
        (41, 42, 0, False, 41, "record-inconsistent"),
        (41, 42, 37, False, 37, "abort-final"),
        (41, 0, 0, True, launcher.WATCHDOG_RETURNCODE, "abort-final"),
    ],
)
def test_shell_diagnostics_reach_launcher_records(
    tmp_path, monkeypatch, controller, volume, host, watchdog, expected, state
):
    shell_dir = tmp_path / "shell"
    shell_dir.mkdir()
    run_fake_docker(shell_dir)  # prepare inert binaries; never reaches real Docker
    bin_dir = shell_dir / "bin"
    if watchdog:
        (bin_dir / "fake-python").write_text("#!/bin/bash\nexec /bin/sleep 1\n")
    overrides = {
        "PATH": str(bin_dir),
        "HOME": str(shell_dir),
        "FAKE_LOG": str(shell_dir / "calls"),
        "INODEFENCE_DOCKER_CONTEXT": "fake",
        "INODEFENCE_EVIDENCE_DIR": str(shell_dir),
        "PYTHON": str(bin_dir / "fake-python"),
        "SKIP_BUILD": "1",
        "RUN_ID": "test",
        "CONTROLLER_ERROR": str(controller),
        "VOLUME_ERROR": str(volume),
        "HOST_ERROR": str(host),
        "CREATE_ERROR": "",
    }
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    behavior: dict[str, Any] = dict(TARGET_IMAGES)
    if host:
        behavior["abort"] = {VICTIM}
    inner = _fake_runner(behavior)
    real_runner = launcher.run_cell_with_watchdog
    processes = []

    def popen(cmd, **kwargs):
        kwargs["env"] = {**kwargs["env"], **overrides}
        process = subprocess.Popen(cmd, **kwargs)
        processes.append(process)
        return process

    def runner(cell, output, env, bash, **limits):
        fake = inner(cell, output, env, bash, **limits)
        if cell.run_id != VICTIM:
            return fake
        paths = _cell(args, VICTIM, output)
        if watchdog:
            paths["report"].unlink()
            lines = paths["steps_jsonl"].read_text().splitlines()
            paths["steps_jsonl"].write_text("\n".join(lines[:2]) + "\n")
        actual = real_runner(
            cell, output, env, bash, limit_seconds=0.1 if watchdog else 10, popen=popen
        )
        return replace(fake, returncode=actual.returncode, watchdog_fired=actual.watchdog_fired)

    monkeypatch.setattr(launcher, "run_cell_with_watchdog", runner)
    launcher.main(args)
    end = next(
        row for row in _result_lines(out) if row.get("run_id") == VICTIM and row["event"] == "end"
    )
    log = _cell(args, VICTIM, out)["log"].read_text()
    assert end["returncode"] == expected and end["watchdog_fired"] is watchdog
    assert _index(out)["interim"]["cell_states"][VICTIM] == state
    if controller:
        assert "FAILED cleanup: controller" in log
    if volume:
        assert "FAILED cleanup: volume" in log
    if host:
        assert "FAILED at step: effect-demo-historical (exit 37)" in log
    if not (controller or volume or host or watchdog):
        assert "PASSED:" in log
    if watchdog:
        assert "[watchdog] terminated" in log
        print("watchdog actual shell exit", processes[0].returncode, "launcher", expected)
    else:
        assert processes[0].returncode == expected


def test_watchdog_kill_can_skip_cleanup(tmp_path):
    import os
    import signal

    shell_dir = tmp_path / "shell"
    shell_dir.mkdir()
    run_fake_docker(shell_dir)
    bin_dir = shell_dir / "bin"
    (bin_dir / "fake-python").write_text(
        '#!/bin/bash\nprintf R >&"$FAKE_READY_FD"\nexec /bin/sleep 30\n'
    )
    read_fd, write_fd = os.pipe()
    env = {
        "PATH": str(bin_dir),
        "HOME": str(shell_dir),
        "FAKE_LOG": str(shell_dir / "calls"),
        "INODEFENCE_DOCKER_CONTEXT": "fake",
        "INODEFENCE_EVIDENCE_DIR": str(shell_dir),
        "PYTHON": str(bin_dir / "fake-python"),
        "SKIP_BUILD": "1",
        "RUN_ID": "test",
        "CONTROLLER_ERROR": "41",
        "VOLUME_ERROR": "0",
        "HOST_ERROR": "0",
        "CREATE_ERROR": "",
        "FAKE_READY_FD": str(write_fd),
        "TAR_VERSION": "7.5.2",
    }
    (shell_dir / "calls").write_text("")

    class Cell:
        evidence_basename = "synthetic"
        run_id = "synthetic"
        mode = "demo-historical"

    proc = None

    def popen(cmd, **kwargs):
        nonlocal proc
        proc = subprocess.Popen(cmd, **kwargs, pass_fds=(write_fd,), start_new_session=True)
        process = proc
        assert os.read(read_fd, 1) == b"R"  # resources created, host double running

        class Stuck:
            def wait(self, timeout=None):
                if timeout is not None:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                return process.wait()

            def terminate(self):
                pass  # deterministic stand-in for a process that did not stop on SIGTERM

            def kill(self):
                process.kill()

        return Stuck()

    try:
        result = launcher.run_cell_with_watchdog(
            cast(Any, Cell()),
            tmp_path,
            env,
            "/bin/bash",
            limit_seconds=1,
            popen=popen,  # type: ignore[arg-type]
        )
        log = result.log.read_text()
        calls = (shell_dir / "calls").read_text().splitlines()
        assert result.watchdog_fired and result.returncode == launcher.WATCHDOG_RETURNCODE
        assert proc is not None and proc.returncode == -signal.SIGKILL
        assert not any(call.startswith(("rm -f ", "volume rm ")) for call in calls)
        assert "FAILED cleanup:" not in log and "[watchdog] terminated" in log
    finally:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        os.close(read_fd)
        os.close(write_fd)


def test_no_record_retry_preserves_each_log(tmp_path, monkeypatch):
    shell_dir = tmp_path / "shell"
    shell_dir.mkdir()
    run_fake_docker(shell_dir)
    bin_dir = shell_dir / "bin"
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    inner = _fake_runner(TARGET_IMAGES)
    actual_runner = launcher.run_cell_with_watchdog
    count = 0

    def runner(cell, output, env, bash, **limits):
        nonlocal count
        fake = inner(cell, output, env, bash, **limits)
        if cell.run_id != VICTIM:
            return fake
        count += 1
        paths = _cell(args, VICTIM, output)
        paths["report"].unlink()
        paths["steps_jsonl"].unlink()
        overrides = {
            "PATH": str(bin_dir),
            "HOME": str(shell_dir),
            "FAKE_LOG": str(shell_dir / "calls"),
            "INODEFENCE_DOCKER_CONTEXT": "fake",
            "INODEFENCE_EVIDENCE_DIR": str(shell_dir),
            "PYTHON": str(bin_dir / "fake-python"),
            "SKIP_BUILD": "1",
            "RUN_ID": "test",
            "CONTROLLER_ERROR": "41" if count == 1 else "0",
            "VOLUME_ERROR": "0" if count == 1 else "42",
            "HOST_ERROR": "0",
            "CREATE_ERROR": "",
        }

        def popen(cmd, **kwargs):
            kwargs["env"] = {**kwargs["env"], **overrides}
            return subprocess.Popen(cmd, **kwargs)

        result = actual_runner(cell, output, env, bash, limit_seconds=10, popen=popen)
        return replace(fake, returncode=result.returncode, watchdog_fired=False)

    monkeypatch.setattr(launcher, "run_cell_with_watchdog", runner)
    assert launcher.main(args) == 1
    log = _cell(args, VICTIM, out)["log"].read_text()
    archived = (out / "attempts" / f"{VICTIM}.attempt1.log").read_text()
    assert count == 2 and _index(out)["interim"]["cell_states"][VICTIM] == "no-record"
    assert "FAILED cleanup: volume" in log and "FAILED cleanup: controller" not in log
    assert "FAILED cleanup: controller" in archived
    ends = [r for r in _result_lines(out) if r.get("run_id") == VICTIM and r["event"] == "end"]
    assert [r["returncode"] for r in ends] == [41, 42]


def test_single_target_log_path_is_unchanged(tmp_path):
    class Cell:
        run_id = "single"
        evidence_basename = "single-evidence"
        mode = "demo"

    class Process:
        def wait(self, timeout=None):
            return 0

    def popen(cmd, **kwargs):
        kwargs["stdout"].write("single-target synthetic log\n")
        return Process()

    result = launcher.run_cell_with_watchdog(
        cast(Any, Cell()),
        tmp_path,
        {},
        "/bin/bash",
        limit_seconds=1,
        popen=popen,  # type: ignore[arg-type]
    )
    assert result.log == tmp_path / "single.log"
    assert result.log.read_text() == "single-target synthetic log\n"

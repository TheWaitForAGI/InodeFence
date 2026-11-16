"""Product health checks: read-only Docker questions with time limits (no real daemon touched)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from inodefence.drivers.runtime import health
from inodefence.drivers.runtime.health import DaemonState, ImageState


class FakeDocker:
    """A runner that answers ``docker`` argv by first-match rules and records every call."""

    def __init__(self, rules):
        self.rules = rules
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        assert argv[0] == "docker"
        assert kwargs.get("timeout") is not None, "every Docker question has a time limit"
        self.calls.append(list(argv))
        for match, answer in self.rules:
            if match(argv[1:]):
                if isinstance(answer, BaseException):
                    raise answer
                rc, out, err = answer
                return subprocess.CompletedProcess(argv, rc, out, err)
        raise AssertionError(f"unexpected docker call {argv}")


def _any(*_):
    return True


def _timeout():
    return subprocess.TimeoutExpired(["docker"], 10)


def test_daemon_ok_unreachable_timeout() -> None:
    ok = health.probe_daemon(runner=FakeDocker([(_any, (0, "29.9.3\n", ""))]))
    assert (ok.state, ok.server_version, ok.problem) == (DaemonState.OK, "29.9.3", None)

    down = health.probe_daemon(
        runner=FakeDocker([(_any, (1, "", "Cannot connect to the Docker daemon at unix://x\n"))])
    )
    assert down.state is DaemonState.UNREACHABLE
    assert "Cannot connect" in down.detail and down.problem is not None

    stalled = health.probe_daemon(runner=FakeDocker([(_any, _timeout())]))
    assert stalled.state is DaemonState.TIMEOUT
    assert "did not answer within" in stalled.detail

    denied = health.probe_daemon(runner=FakeDocker([(_any, (1, "", "permission denied\n"))]))
    assert denied.state is DaemonState.UNREACHABLE and "docker group" in denied.detail

    no_cli = health.probe_daemon(runner=FakeDocker([(_any, FileNotFoundError("docker"))]))
    assert no_cli.state is DaemonState.UNREACHABLE


def test_image_lookup_has_three_states_and_silence_is_never_absent() -> None:
    present = health.lookup_image("img", runner=FakeDocker([(_any, (0, "sha256:abc\n", ""))]))
    assert (present.state, present.image_id) == (ImageState.PRESENT, "sha256:abc")

    for err in ("Error response from daemon: No such image: img\n", "Error: No such object: img"):
        absent = health.lookup_image("img", runner=FakeDocker([(_any, (1, "", err))]))
        assert absent.state is ImageState.ABSENT

    for answer in (
        _timeout(),
        (1, "", "Cannot connect to the Docker daemon\n"),
        (0, "", ""),
        OSError("boom"),
    ):
        unknown = health.lookup_image("img", runner=FakeDocker([(_any, answer)]))
        assert unknown.state is ImageState.UNKNOWN, answer
        assert unknown.image_id is None


def test_residue_lists_by_label_and_launcher_names_and_never_removes() -> None:
    def is_ps(args):
        return args[:2] == ["ps", "-a"]

    def is_volume_ls(args):
        return args[:2] == ["volume", "ls"]

    fake = FakeDocker(
        [
            (
                lambda a: is_ps(a) and "name=inodefence-python-tarfile-controller" in a,
                (0, "inodefence-python-tarfile-controller-r\tExited (1) 2 hours ago\n", ""),
            ),
            (is_ps, (0, "", "")),
            (
                lambda a: is_volume_ls(a) and "name=inodefence-local-runtime" in a,
                (0, "inodefence-local-runtime-x\n", ""),
            ),
            (is_volume_ls, (0, "", "")),
        ]
    )
    residue = health.find_residue(runner=fake)
    assert residue.containers == (
        "inodefence-python-tarfile-controller-r (Exited (1) 2 hours ago)",
    )
    assert residue.volumes == ("inodefence-local-runtime-x",)
    assert not residue.clean
    text = "\n".join(residue.lines())
    assert "nothing was removed" in text and "docker container inspect" in text
    # Read-only: only listings were asked, never rm / prune / stop.
    assert all(call[1] in {"ps", "volume"} for call in fake.calls)
    assert not any(word in call for call in fake.calls for word in ("rm", "prune", "stop"))
    selectors = {call[call.index("--filter") + 1] for call in fake.calls}
    labels = {"label=org.inodefence.smoke-owner", "label=org.inodefence.execution-owner"}
    names = {f"name={n}" for n in (*health.LAUNCHER_CONTROLLERS, *health.LAUNCHER_VOLUMES)}
    assert selectors == labels | names


def test_launcher_names_match_the_launchers_own() -> None:
    from inodefence.drivers.launcher import RUN_RESOURCES

    assert set(health.LAUNCHER_CONTROLLERS) == {c for c, _ in RUN_RESOURCES.values()}
    assert set(health.LAUNCHER_VOLUMES) == {v for _, v in RUN_RESOURCES.values()}
    # The long-lived Dev Container volumes are not launcher names (never reported).
    assert not any(n in {"inodefence-codex", "inodefence-runtime"} for n in health.LAUNCHER_VOLUMES)


def test_run_leftovers_names_this_runs_resources_only() -> None:
    gone = FakeDocker([(_any, (1, "", "Error: No such object: x\n"))])
    assert health.run_leftovers("c-r", "v-r", runner=gone) == []
    kept = FakeDocker([(lambda a: a[0] == "volume", (0, "[{}]", "")), (_any, (1, "", "No such"))])
    (line,) = health.run_leftovers("c-r", "v-r", runner=kept)
    assert "volume v-r still exists" in line and "nothing was removed" in line
    (line,) = health.run_leftovers(
        "c-r",
        "v-r",
        runner=FakeDocker(
            [(lambda a: a[0] == "container", _timeout()), (_any, (1, "", "no such"))]
        ),
    )
    assert "could not tell" in line and "container c-r" in line


def test_residue_that_cannot_be_listed_is_unknown_not_clean() -> None:
    residue = health.find_residue(runner=FakeDocker([(_any, _timeout())]))
    assert not residue.clean and residue.unknown
    assert "state unknown" in "\n".join(residue.lines())


def test_run_resources_exist() -> None:
    absent = FakeDocker([(_any, (1, "", "Error: No such object: x\n"))])
    assert health.run_resources_exist("c", "v", runner=absent) is None

    taken = FakeDocker([(lambda a: a[0] == "container", (0, "[{}]", ""))])
    reason = health.run_resources_exist("c", "v", runner=taken)
    assert reason is not None and "already exists" in reason and "Nothing was removed" in reason

    silent = FakeDocker([(_any, _timeout())])
    reason = health.run_resources_exist("c", "v", runner=silent)
    assert reason is not None and "could not tell" in reason


def test_disk_free_warns_below_the_threshold(tmp_path: Path) -> None:
    roomy = health.disk_free(tmp_path / "not" / "yet", warn_below=1)
    assert roomy.free_bytes is not None and not roomy.low
    tight = health.disk_free(tmp_path, warn_below=1 << 62)
    assert tight.low and "may fill it" in tight.detail


def test_memory_is_never_reported_as_a_pass(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 100 kB\nMemAvailable: 2097152 kB\n", encoding="ascii")
    status = health.memory_status(meminfo)
    assert status.state == "UNKNOWN"
    assert status.available_bytes == 2097152 * 1024
    assert "Windows commit limit" in status.detail
    assert health.memory_status(tmp_path / "missing").state == "UNKNOWN"


@pytest.mark.parametrize("state", list(DaemonState))
def test_daemon_problem_only_when_not_ok(state: DaemonState) -> None:
    status = health.DaemonStatus(state, "d")
    assert (status.problem is None) is (state is DaemonState.OK)


def test_health_is_a_stdlib_leaf_so_doctor_loads_no_driver_code() -> None:
    import ast
    import sys

    tree = ast.parse(Path(health.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
    imported.discard("__future__")
    assert imported <= set(sys.stdlib_module_names), imported

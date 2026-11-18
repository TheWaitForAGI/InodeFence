"""#494: a non-node-tar replay shows the shared launcher's closing line with its own target name.

The shared replay launcher (``scripts/local_node_tar_smoke.sh``, protected) ends with
``PASSED: node-tar replay (context=...)`` for every target; the replay hooks of python-tarfile,
decompress and oras-go stream its stdout and relabel that one line. No container is started here.
"""

from __future__ import annotations

import subprocess

import pytest

from inodefence.drivers import replay_launch


@pytest.mark.parametrize("target", ["decompress", "oras-go", "python-tarfile"])
def test_the_passed_line_names_the_real_target(target: str) -> None:
    line = "PASSED: node-tar replay (context=default)\n"
    assert replay_launch.relabel_launcher_line(line, target) == (
        f"PASSED: {target} replay (context=default)\n"
    )


def test_other_lines_are_unchanged() -> None:
    for line in ("==> [replay]\n", "PASSED: node-tar explore (context=x)\n", "node-tar replay\n"):
        assert replay_launch.relabel_launcher_line(line, "decompress") == line


def test_the_runner_streams_stdout_relabelled_and_keeps_the_exit_code(capsys) -> None:
    run = replay_launch.relabeling_runner("decompress")
    script = "echo '==> [replay]'; echo 'PASSED: node-tar replay (context=c)'; exit 3"
    done = run(["bash", "-c", script], env={"PATH": "/usr/bin:/bin"}, check=False)
    assert done.returncode == 3
    assert capsys.readouterr().out == "==> [replay]\nPASSED: decompress replay (context=c)\n"


@pytest.mark.parametrize("given", ["default", "fake"])
def test_only_the_default_runner_is_wrapped(tmp_path, monkeypatch, given: str) -> None:
    """The default ``subprocess.run`` is replaced by the relabelling runner; a test's fake runner
    is passed through as given."""
    passed: list[object] = []

    def fake(command, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(command, 1)

    def launcher(script, args, *, runner, **kwargs):  # type: ignore[no-untyped-def]
        passed.append(runner)
        return subprocess.CompletedProcess(["bash"], 1)

    request = type(
        "R",
        (),
        {
            "target": "decompress",
            "case_id": "a" * 64,
            "tar_sha256": "b" * 64,
            "image_id": "sha256:" + "c" * 64,
            "run_settings": {},
            "runtime": None,
        },
    )()
    monkeypatch.setattr(replay_launch, "replay_input_line", lambda request: "{}\n")
    monkeypatch.setattr(replay_launch.dataclasses, "replace", lambda obj, **changes: obj)
    monkeypatch.setattr(replay_launch, "run_launcher", launcher)
    runner = subprocess.run if given == "default" else fake
    replay_launch.controller_replay(
        request,  # type: ignore[arg-type]
        tmp_path,
        {"target": "decompress"},
        runner=runner,
    )
    if given == "fake":
        assert passed == [fake]
    else:
        assert passed[0] is not subprocess.run and callable(passed[0])

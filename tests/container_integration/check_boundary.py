"""Explicit real-runtime suite, invoked through scripts.container_host validate."""

import json
import tempfile
from pathlib import Path

import pytest

from inodefence.execution import ContainerRequest
from inodefence.model import SnapshotPhase
from inodefence.observer import capture_state
from inodefence.runtime import disposable_sandbox


def test_real_filesystem_network_credentials_and_resource_policy(
    container_backend, container_image
):
    assert Path("/workspaces/InodeFence/AGENTS.md").is_file()
    with (
        tempfile.TemporaryDirectory(prefix=".inodefence-canary-", dir=Path.home()) as home_canary,
        disposable_sandbox() as neighbor,
        disposable_sandbox() as sandbox,
    ):
        canary = Path(home_canary) / "harmless"
        canary.write_bytes(b"dedicated disposable controller canary")
        sandbox.archive_path.write_bytes(b"benign controlled input")
        command = (
            "python",
            "/helper.py",
            "policy",
            str(sandbox.root),
            "/workspaces/InodeFence/AGENTS.md",
            str(canary),
            str(neighbor.root / "outside/sentinel.txt"),
        )
        request = ContainerRequest(container_image, command, sandbox.root, 10)
        with container_backend.prepare(request) as prepared:
            before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
            result = prepared.execute()
            assert result.exit_code == 0, result.stderr
            info = json.loads(result.stdout)
            after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
            sentinel = before.get("outside/sentinel.txt")
            assert sentinel is not None
            assert info["sentinel_identity"] == list(sentinel.identity)
            assert sentinel == after.get("outside/sentinel.txt")
            assert info["uid"] == info["gid"] == 1000
            assert info["cap_eff"] == "0000000000000000"
            assert info["no_new_privileges"] == "1"
            policy = container_backend.resources
            assert info["nofile"] == [policy.open_files] * 2
            assert info["fsize"] == [policy.file_size_bytes] * 2
            assert int(info["pids_max"]) == policy.pids
            assert int(info["memory_max"]) == policy.memory_bytes
            assert info["swap_max"] == "0"
            assert after.get("extract/visible") is not None
            identity = prepared.identity
        assert container_backend.client.run(("container", "inspect", identity), 10).returncode != 0
    assert not sandbox.root.exists() and not neighbor.root.exists()


@pytest.mark.parametrize("mode, expected", (("descendants", 0), ("timeout", None), ("failure", 4)))
def test_real_exit_timeout_and_detached_descendant_cleanup(
    container_backend, container_image, mode, expected
):
    with disposable_sandbox() as sandbox:
        request = ContainerRequest(
            container_image, ("python", "/helper.py", mode, str(sandbox.root)), sandbox.root, 3
        )
        with container_backend.prepare(request) as prepared:
            result = prepared.execute()
            assert result.exit_code == expected, result.stderr
            if mode != "failure":
                assert b"detached child and grandchild ready" in result.stdout
            state = container_backend.inspect(prepared.identity)["State"]
            assert not state["Running"] and state["Pid"] == 0
            assert (
                container_backend.client.run(("container", "top", prepared.identity), 10).returncode
                != 0
            )
            identity = prepared.identity
        assert container_backend.client.run(("container", "inspect", identity), 10).returncode != 0
    assert not sandbox.root.exists()


def test_real_startup_failure_is_infrastructure_error_and_cleans_up(
    container_backend, container_image
):
    from inodefence.execution import BackendError

    with disposable_sandbox() as sandbox:
        with container_backend.prepare(
            ContainerRequest(container_image, ("/missing-benign-helper",), sandbox.root, 3)
        ) as prepared:
            with pytest.raises(BackendError):
                prepared.execute()
        assert (
            container_backend.client.run(("container", "inspect", prepared.identity), 10).returncode
            != 0
        )
    assert not sandbox.root.exists()


def test_real_output_is_bounded(container_backend, container_image):
    from inodefence.execution.docker_client import OUTPUT_LIMIT

    with disposable_sandbox() as sandbox:
        with container_backend.prepare(
            ContainerRequest(
                container_image,
                ("python", "/helper.py", "output", str(sandbox.root)),
                sandbox.root,
                10,
            )
        ) as prepared:
            result = prepared.execute()
            assert result.exit_code == 0
            assert result.output_truncated and len(result.stdout) == OUTPUT_LIMIT

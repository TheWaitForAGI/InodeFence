"""Invocation-unit metadata is synthetic, never a runtime qualification result."""

from dataclasses import asdict, replace
from hashlib import sha256

import pytest

from inodefence.builder import build_tar
from inodefence.evaluation.encoding import json_bytes
from inodefence.evaluation.gnu_packaging import benign_profile_bytes, worker_bytes
from inodefence.evaluation.gnu_tar import REPOSITORY, GnuIdentity, GnuTarInvocation
from inodefence.execution.base import BackendError, ContainerOutcome
from inodefence.model import ExecutionStatus
from inodefence.replay.benign import benign_replay_cases


@pytest.fixture
def invocation():
    identity = GnuIdentity(
        "3.12.13",
        "1.34",
        sha256(worker_bytes(REPOSITORY)).hexdigest(),
        sha256(benign_profile_bytes()).hexdigest(),
        "a" * 64,
        "b" * 64,
    )
    return GnuTarInvocation("sha256:" + "c" * 64, identity)


def test_current_worker_profile_and_observed_artifact_identity(invocation):
    assert (
        invocation.verify_identity(json_bytes(asdict(invocation.identity))) == invocation.artifacts
    )
    assert len(invocation.artifacts) == 4
    changed = replace(invocation.identity, tar_binary_sha256="d" * 64)
    with pytest.raises(BackendError, match="identity changed"):
        invocation.verify_identity(json_bytes(asdict(changed)))
    with pytest.raises(ValueError, match="trusted fixed"):
        replace(invocation, identity=replace(invocation.identity, profile_sha256="0" * 64))


@pytest.mark.parametrize(
    "code,status",
    [
        (0, ExecutionStatus.SUCCESS),
        (2, ExecutionStatus.REJECTED),
        (1, ExecutionStatus.FAILED),
        (None, ExecutionStatus.TIMED_OUT),
    ],
)
def test_target_statuses_remain_distinct_from_worker_invalidity(invocation, code, status):
    outcome = ContainerOutcome(code, b"raw stdout", b"raw stderr", 0.25, False)
    result = invocation.classify(outcome, ("unit-command",))
    assert result.status == status
    assert result.stdout == "raw stdout" and result.stderr == "raw stderr"
    assert result.duration_seconds == 0.25
    assert result.timeout_seconds == invocation.timeout_seconds


@pytest.mark.parametrize("code", [3, 4])
def test_worker_failures_are_infrastructure_invalid(invocation, code):
    with pytest.raises(BackendError, match="infrastructure invalid"):
        invocation.classify(ContainerOutcome(code, b"", b"", 0.1, False), ("unit-command",))


def test_unsupported_archive_or_nonempty_root_never_forms_execution_command(tmp_path, invocation):
    root = tmp_path / "extract"
    root.mkdir()
    archive = tmp_path / "input.tar"
    archive.write_bytes(build_tar(benign_replay_cases()[0]))
    command = invocation.command(archive, root)
    assert "--extract" in command
    (root / "existing").write_bytes(b"ordinary marker")
    with pytest.raises(BackendError, match="fixed benign"):
        invocation.command(archive, root)
    (root / "existing").unlink()
    archive.write_bytes(b"ordinary unsupported input")
    with pytest.raises(BackendError, match="fixed benign"):
        invocation.command(archive, root)


@pytest.mark.parametrize("timeout", [0, True, float("inf"), 121])
def test_invalid_timeout_configuration_is_rejected(invocation, timeout):
    with pytest.raises(ValueError, match="bounded positive"):
        replace(invocation, timeout_seconds=timeout)

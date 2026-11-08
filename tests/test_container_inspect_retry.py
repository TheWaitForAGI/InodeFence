"""Bounded cleanup-only retry of inconclusive Docker metadata reads."""

import json

import pytest

from inodefence.execution.base import BackendError
from inodefence.execution.container import (
    OWNER_LABEL,
    _cleanup_inspect,
    checked,
    remove_owned,
)
from inodefence.execution.docker_client import CommandResult


class ScriptedDocker:
    def __init__(self, responses: list[CommandResult]):
        self.responses = iter(responses)
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        self.calls.append((args, timeout))
        return next(self.responses)


def timeout() -> CommandResult:
    return CommandResult(-9, b"", b"", timed_out=True)


def present(identity: str, owner: str) -> CommandResult:
    info = [{"Id": identity, "Config": {"Labels": {OWNER_LABEL: owner}}}]
    return CommandResult(0, json.dumps(info).encode(), b"")


def absent(identity: str) -> CommandResult:
    return CommandResult(1, b"", f"Error: No such object: {identity}".encode())


def test_cleanup_inspect_timeout_then_success_is_bounded_and_idempotent() -> None:
    docker = ScriptedDocker([timeout(), present("owned", "owner")])
    assert checked(_cleanup_inspect(docker, "owned"), "inspect")
    assert docker.calls == [
        (("container", "inspect", "owned"), 10),
        (("container", "inspect", "owned"), 10),
    ]


def test_cleanup_inspect_does_not_retry_an_explicit_error() -> None:
    docker = ScriptedDocker([absent("missing")])
    result = _cleanup_inspect(docker, "missing")
    assert result.returncode == 1
    assert len(docker.calls) == 1


def test_cleanup_inspect_second_timeout_still_fails_closed() -> None:
    docker = ScriptedDocker([timeout(), timeout()])
    with pytest.raises(BackendError, match="inspect failed"):
        checked(_cleanup_inspect(docker, "owned"), "inspect")
    assert len(docker.calls) == 2


def test_cleanup_retries_inspects_but_removes_exactly_once() -> None:
    docker = ScriptedDocker(
        [
            timeout(),
            present("owned", "owner"),
            CommandResult(0, b"", b""),
            timeout(),
            absent("owned"),
        ]
    )
    remove_owned(docker, "owned", "owner")
    assert [args for args, _ in docker.calls] == [
        ("container", "inspect", "owned"),
        ("container", "inspect", "owned"),
        ("container", "rm", "--force", "--volumes", "owned"),
        ("container", "inspect", "owned"),
        ("container", "inspect", "owned"),
    ]


def test_cleanup_does_not_remove_when_owner_differs_after_retry() -> None:
    docker = ScriptedDocker([timeout(), present("owned", "other-owner")])
    with pytest.raises(BackendError, match="another invocation"):
        remove_owned(docker, "owned", "owner")
    assert all(args[:2] == ("container", "inspect") for args, _ in docker.calls)


def test_cleanup_does_not_treat_repeated_timeout_as_absence() -> None:
    docker = ScriptedDocker([timeout(), timeout()])
    with pytest.raises(BackendError, match="cleanup inspect failed"):
        remove_owned(docker, "owned", "owner")
    assert all(args[:2] == ("container", "inspect") for args, _ in docker.calls)

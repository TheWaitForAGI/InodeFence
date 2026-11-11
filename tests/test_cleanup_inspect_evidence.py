"""Cleanup retry diagnostics must preserve both attempts without changing success."""

import json

import pytest

from inodefence.evaluation.abort_classification import InvalidReason, classify_abort_reason
from inodefence.execution.base import BackendError
from inodefence.execution.container import OWNER_LABEL, remove_owned
from inodefence.execution.docker_client import CommandResult


class Docker:
    def __init__(self, results: list[CommandResult]):
        self.results = iter(results)
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        self.calls.append((args, timeout))
        return next(self.results)


def present(owner: str = "owner") -> CommandResult:
    value = [{"Id": "owned", "Config": {"Labels": {OWNER_LABEL: owner}}}]
    return CommandResult(0, json.dumps(value).encode(), b"")


def absent() -> CommandResult:
    return CommandResult(1, b"", b"Error: No such object: owned")


def timeout() -> CommandResult:
    return CommandResult(-9, b"", b"", timed_out=True)


def read_diagnostic(capsys):
    output = capsys.readouterr()
    assert output.out == ""
    lines = [
        line
        for line in output.err.splitlines()
        if line.startswith("inodefence-cleanup-diagnostic ")
    ]
    assert len(lines) == 1
    prefix, payload = lines[0].split(" ", 1)
    assert prefix == "inodefence-cleanup-diagnostic"
    record = json.loads(payload)
    assert record["schema"] == "inodefence-cleanup-diagnostic-v1"
    return record


def test_successful_retry_preserves_both_inspect_attempts(capsys):
    client = Docker(
        [
            timeout(),
            present(),
            CommandResult(0, b"", b""),
            absent(),
        ]
    )
    assert remove_owned(client, "owned", "owner") is None
    record = read_diagnostic(capsys)
    assert record["outcome"] == "removed"
    assert [entry["timed_out"] for entry in record["inspections"][:2]] == [True, False]
    assert [entry["attempt"] for entry in record["inspections"][:2]] == [1, 2]
    assert record["inspections"][2]["phase"] == "verification"
    assert record["inspections"][2]["absent"] is True
    assert record["removal"]["returncode"] == 0
    assert len(client.calls) == 4


def test_timeout_is_flushed_before_retry_starts(capsys):
    class InspectDuringRetry(Docker):
        def run(self, args, timeout):
            if len(self.calls) == 1:
                output = capsys.readouterr().err
                prefix, payload = output.strip().split(" ", 1)
                assert prefix == "inodefence-cleanup-attempt"
                assert json.loads(payload)["timed_out"] is True
            return super().run(args, timeout)

    client = InspectDuringRetry([timeout(), present(), CommandResult(0, b"", b""), absent()])
    remove_owned(client, "owned", "owner")
    assert read_diagnostic(capsys)["outcome"] == "removed"


def test_normal_and_already_absent_produce_no_anomaly_or_retry(capsys):
    client = Docker([present(), CommandResult(0, b"", b""), absent()])
    assert remove_owned(client, "owned", "owner") is None
    assert len(client.calls) == 3
    assert capsys.readouterr().err == ""
    client = Docker([absent()])
    assert remove_owned(client, "owned", "owner") is None
    assert len(client.calls) == 1
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("second", [timeout(), CommandResult(2, b"", b"daemon error")])
def test_timeout_then_failure_keeps_both_attempts_and_abort_category(second, capsys):
    client = Docker([timeout(), second])
    with pytest.raises(BackendError, match="container runtime cleanup inspect failed") as error:
        remove_owned(client, "owned", "owner")
    assert classify_abort_reason(str(error.value)) == InvalidReason.CLEANUP_INSPECT
    record = read_diagnostic(capsys)
    assert record["outcome"] == "inspection_failed"
    assert [a["attempt"] for a in record["inspections"]] == [1, 2]
    assert record["inspections"][0]["timed_out"] is True
    assert record["inspections"][1]["returncode"] == second.returncode
    assert record["inspections"][1]["timed_out"] == second.timed_out
    assert len(client.calls) == 2


def test_non_timeout_failure_is_not_retried(capsys):
    client = Docker([CommandResult(2, b"", b"daemon error")])
    with pytest.raises(BackendError, match="cleanup inspect failed"):
        remove_owned(client, "owned", "owner")
    record = read_diagnostic(capsys)
    assert record["inspections"][0]["returncode"] == 2
    assert len(client.calls) == 1


def test_truncated_inspect_fails_closed_and_is_recorded(capsys):
    client = Docker([CommandResult(0, b"partial", b"", truncated=True)])
    with pytest.raises(BackendError, match="cleanup inspect failed"):
        remove_owned(client, "owned", "owner")
    record = read_diagnostic(capsys)
    assert record["inspections"][0]["truncated"] is True
    assert len(client.calls) == 1


def test_wrong_owner_after_retry_never_removes(capsys):
    client = Docker([timeout(), present("other")])
    with pytest.raises(BackendError, match="another invocation") as error:
        remove_owned(client, "owned", "owner")
    assert classify_abort_reason(str(error.value)) == InvalidReason.CLEANUP_REMOVE
    record = read_diagnostic(capsys)
    assert record["outcome"] == "owner_mismatch"
    assert len(record["inspections"]) == 2
    assert all(call[0][:2] == ("container", "inspect") for call in client.calls)


@pytest.mark.parametrize(
    "where", ["remove", "verify_timeout", "verify_present", "verify_truncated"]
)
def test_removal_and_final_confirmation_failures_remain_distinct(where, capsys):
    removal = (
        CommandResult(1, b"", b"remove error") if where == "remove" else CommandResult(0, b"", b"")
    )
    results = [present(), removal]
    if where == "verify_timeout":
        results.extend([timeout(), timeout()])
    elif where == "verify_present":
        results.append(present())
    elif where == "verify_truncated":
        results.append(CommandResult(0, b"partial", b"", truncated=True))
    client = Docker(results)
    with pytest.raises(BackendError) as error:
        remove_owned(client, "owned", "owner")
    assert classify_abort_reason(str(error.value)) == InvalidReason.CLEANUP_REMOVE
    record = read_diagnostic(capsys)
    assert record["outcome"] == ("remove_failed" if where == "remove" else "verification_failed")
    assert record["removal"]["returncode"] == removal.returncode
    assert len(client.calls) == len(results)
    if where == "verify_timeout":
        assert [a["timed_out"] for a in record["inspections"]] == [False, True, True]
    if where == "verify_present":
        assert record["inspections"][-1]["absent"] is False
    if where == "verify_truncated":
        assert record["inspections"][-1]["truncated"] is True


def test_diagnostic_sink_failure_does_not_change_cleanup_result(monkeypatch):
    class BrokenStderr:
        def write(self, _text):
            raise OSError("unavailable")

    monkeypatch.setattr("inodefence.execution.container.sys.stderr", BrokenStderr())
    client = Docker([timeout(), present(), CommandResult(0, b"", b""), absent()])
    assert remove_owned(client, "owned", "owner") is None

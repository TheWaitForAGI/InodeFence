"""Caller-layer Docker diagnostics after the protected-file revert (#340).

The 17 tests the revert removed were about a cleanup-inspect retry (dropped by
decision) and diagnostics added inside the protected backend. Their surviving
guarantees are tested here against the reverted backend, unchanged, with the
diagnostics now produced in the caller layer from the stall-recovery journal.
The PR body maps every removed test to a test here, or to "dropped".
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from scripts import container_controller, container_host

from inodefence.evaluation.abort_classification import InvalidReason, classify_abort_reason
from inodefence.execution import call_diagnostics as diag
from inodefence.execution import start_gate
from inodefence.execution.base import BackendError
from inodefence.execution.container import OWNER_LABEL, remove_owned
from inodefence.execution.docker_client import CommandResult
from inodefence.execution.stall_recovery import ObservedDockerClient, StallRecovery


class Scripted:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = iter(results)
        self.calls: list[tuple[str, ...]] = []

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        self.calls.append(args)
        return next(self.results)


def present(owner: str = "owner") -> CommandResult:
    value = [{"Id": "owned", "Config": {"Labels": {OWNER_LABEL: owner}}}]
    return CommandResult(0, json.dumps(value).encode(), b"")


def absent() -> CommandResult:
    return CommandResult(1, b"", b"Error: No such object: owned")


def timeout() -> CommandResult:
    return CommandResult(-9, b"", b"", timed_out=True)


def removed() -> CommandResult:
    return CommandResult(0, b"", b"")


def observed(results: list[CommandResult]) -> tuple[ObservedDockerClient, Scripted]:
    inner = Scripted(results)
    return ObservedDockerClient(inner), inner


# ---- the reverted backend stays fail-closed without a retry --------------------------------


def test_single_cleanup_inspect_timeout_fails_closed_without_retry() -> None:
    # replaces: timeout_then_success_is_bounded_and_idempotent, second_timeout_still_fails_closed
    client, inner = observed([timeout()])
    with pytest.raises(BackendError, match="cleanup inspect failed") as error:
        remove_owned(client, "owned", "owner")
    assert inner.calls == [("container", "inspect", "owned")]
    assert classify_abort_reason(str(error.value)) == InvalidReason.CLEANUP_INSPECT


def test_explicit_absence_is_one_call_and_no_anomaly() -> None:
    # replaces: does_not_retry_an_explicit_error, normal_and_already_absent_produce_no_anomaly
    client, inner = observed([absent()])
    remove_owned(client, "owned", "owner")
    assert len(inner.calls) == 1
    assert diag.last_anomaly(client.calls) is None


def test_normal_cleanup_removes_exactly_once_and_has_no_anomaly() -> None:
    # replaces: retries_inspects_but_removes_exactly_once, normal_and_already_absent_...
    client, inner = observed([present(), removed(), absent()])
    remove_owned(client, "owned", "owner")
    assert [args[:2] for args in inner.calls] == [
        ("container", "inspect"),
        ("container", "rm"),
        ("container", "inspect"),
    ]
    assert diag.last_anomaly(client.calls) is None
    assert diag.emit_anomalies(client.calls, "test", io.StringIO()) == 0


def test_another_owner_is_never_removed() -> None:
    # replaces: does_not_remove_when_owner_differs_after_retry, wrong_owner_after_retry_...
    client, inner = observed([present("other")])
    with pytest.raises(BackendError, match="another invocation") as error:
        remove_owned(client, "owned", "owner")
    assert all(args[:2] == ("container", "inspect") for args in inner.calls)
    assert classify_abort_reason(str(error.value)) == InvalidReason.CLEANUP_REMOVE


def test_a_timeout_is_never_read_as_absence() -> None:
    # replaces: does_not_treat_repeated_timeout_as_absence
    client, inner = observed([timeout()])
    with pytest.raises(BackendError):
        remove_owned(client, "owned", "owner")
    assert not any(args[:2] == ("container", "rm") for args in inner.calls)
    (call,) = client.calls
    assert call.absent is False and call.timed_out is True


# ---- what the journal records for each failure -----------------------------------------------


@pytest.mark.parametrize(
    ("results", "op", "flags", "category"),
    [
        # replaces: timeout_then_failure_keeps_both_attempts_and_abort_category
        ([timeout()], "container inspect", (True, False, -9), InvalidReason.CLEANUP_INSPECT),
        # replaces: non_timeout_failure_is_not_retried
        (
            [CommandResult(2, b"", b"daemon error")],
            "container inspect",
            (False, False, 2),
            InvalidReason.CLEANUP_INSPECT,
        ),
        # replaces: truncated_inspect_fails_closed_and_is_recorded
        (
            [CommandResult(0, b"partial", b"", truncated=True)],
            "container inspect",
            (False, True, 0),
            InvalidReason.CLEANUP_INSPECT,
        ),
        # replaces: removal_and_final_confirmation_failures_remain_distinct[remove]
        (
            [present(), CommandResult(1, b"", b"remove error")],
            "container rm",
            (False, False, 1),
            InvalidReason.CLEANUP_REMOVE,
        ),
        # replaces: ...remain_distinct[verify_timeout]
        (
            [present(), removed(), timeout()],
            "container inspect",
            (True, False, -9),
            InvalidReason.CLEANUP_REMOVE,
        ),
        # replaces: ...remain_distinct[verify_truncated]
        (
            [present(), removed(), CommandResult(0, b"partial", b"", truncated=True)],
            "container inspect",
            (False, True, 0),
            InvalidReason.CLEANUP_REMOVE,
        ),
    ],
)
def test_the_failing_call_is_named_with_its_flags(
    results: list[CommandResult], op: str, flags: tuple[bool, bool, int], category: InvalidReason
) -> None:
    client, _ = observed(results)
    with pytest.raises(BackendError) as error:
        remove_owned(client, "owned", "owner")
    anomaly = diag.last_anomaly(client.calls)
    assert anomaly is not None
    assert (anomaly.op, (anomaly.timed_out, anomaly.truncated, anomaly.returncode)) == (op, flags)
    annotated = diag.annotate_reason(str(error.value), client.calls)
    assert f"op={op} timed_out={str(flags[0]).lower()} truncated={str(flags[1]).lower()}" in (
        annotated
    )
    # The category is the backend message's, with or without the suffix.
    assert classify_abort_reason(annotated) == classify_abort_reason(str(error.value)) == category


def test_verification_that_still_finds_the_container_is_a_removal_failure() -> None:
    # replaces: ...remain_distinct[verify_present] (a present answer is not an anomalous call)
    client, _ = observed([present(), removed(), present()])
    with pytest.raises(BackendError, match="could not be verified") as error:
        remove_owned(client, "owned", "owner")
    assert classify_abort_reason(str(error.value)) == InvalidReason.CLEANUP_REMOVE
    assert diag.last_anomaly(client.calls) is None
    assert diag.annotate_reason(str(error.value), client.calls) == str(error.value)


@pytest.mark.parametrize(
    "reason",
    [
        "trusted Docker broker disconnected",
        "container runtime cleanup inspect failed: ",
        "container runtime remove failed: x",
        "container removal could not be verified",
        "refusing to remove a container owned by another invocation",
        "evidence integrity failed: x",
        "x.ObservationError: y",
        "container runtime inspect failed: ",
        "something else entirely",
    ],
)
@pytest.mark.parametrize(
    "op", ["container inspect", "container rm", "container create", "container start", "version"]
)
def test_the_suffix_never_changes_a_category(reason: str, op: str) -> None:
    call = diag.CallObservation(op, "c", -1, True, True, 0.0, 0.0, 10.0, error="TimeoutExpired")
    annotated = diag.annotate_reason(reason, [call])
    assert annotated.startswith(reason) and diag.SUFFIX_OPEN in annotated
    assert classify_abort_reason(annotated) == classify_abort_reason(reason)


def test_emitted_lines_are_one_json_record_per_anomalous_call() -> None:
    client, _ = observed([present(), removed(), timeout()])
    with pytest.raises(BackendError):
        remove_owned(client, "owned", "owner")
    stream = io.StringIO()
    assert diag.emit_anomalies(client.calls, "host-target-cleanup", stream) == 1
    (line,) = stream.getvalue().splitlines()
    prefix, payload = line.split(" ", 1)
    assert prefix == diag.DIAGNOSTIC_PREFIX
    record = json.loads(payload)
    assert record["schema"] == diag.DIAGNOSTIC_SCHEMA
    assert (record["scope"], record["op"], record["timed_out"]) == (
        "host-target-cleanup",
        "container inspect",
        True,
    )


def test_a_failing_sink_does_not_change_the_result() -> None:
    # replaces: diagnostic_sink_failure_does_not_change_cleanup_result
    class Broken(io.StringIO):
        def write(self, _text: str) -> int:
            raise OSError("unavailable")

    client, _ = observed([timeout()])
    with pytest.raises(BackendError):
        remove_owned(client, "owned", "owner")
    assert diag.emit_anomalies(client.calls, "test", Broken()) == 1


# ---- the two caller paths ---------------------------------------------------------------------


def _stub(reason: str) -> dict[str, Any]:
    return {"aborted": {"reason": reason, "category": classify_abort_reason(reason).value}}


def test_abort_stub_names_the_last_anomalous_call() -> None:
    # replaces: test_abort_error_chain::test_runtime_error_retains_timeout_and_truncation_flags
    client, _ = observed([timeout()])
    with pytest.raises(BackendError) as error:
        remove_owned(client, "owned", "owner")
    report = _stub(str(error.value))
    container_controller.apply_last_anomalous_call(report, StallRecovery(client, "owner"))
    aborted = report["aborted"]
    assert aborted["reason"] == (
        "container runtime cleanup inspect failed:  [last anomalous docker call: "
        "op=container inspect timed_out=true truncated=false returncode=-9]"
    )
    assert aborted["category"] == classify_abort_reason(aborted["reason"]).value
    assert aborted["last_anomalous_docker_call"]["timed_out"] is True
    assert aborted["last_anomalous_docker_call"]["truncated"] is False


def test_abort_stub_without_an_anomalous_call_is_unchanged() -> None:
    client, _ = observed([absent()])
    remove_owned(client, "owned", "owner")
    report = _stub("evidence integrity failed: x")
    before = json.dumps(report, sort_keys=True)
    container_controller.apply_last_anomalous_call(report, StallRecovery(client, "owner"))
    container_controller.apply_last_anomalous_call(report, None)
    assert json.dumps(report, sort_keys=True) == before


def test_host_target_cleanup_emits_the_failing_call_and_names_it_in_the_unknown(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gate_dir = tmp_path / "gate"
    gate_dir.mkdir()
    monkeypatch.setenv(start_gate.GATE_DIR_ENV, str(gate_dir))
    monkeypatch.setenv(start_gate.GATE_CELL_ENV, "a")
    inner = Scripted([present(), removed(), timeout()])
    with pytest.raises(ExceptionGroup, match="host target cleanup failed"):
        container_host.cleanup_targets(inner, {"owned"}, "owner")
    err = capsys.readouterr().err.splitlines()
    diagnostics = [line for line in err if line.startswith(diag.DIAGNOSTIC_PREFIX + " ")]
    marker = next(i for i, line in enumerate(err) if line.startswith("INODEFENCE_CLEANUP_UNKNOWN:"))
    assert len(diagnostics) == 1 and err.index(diagnostics[0]) < marker
    assert json.loads(diagnostics[0].split(" ", 1)[1])["scope"] == "host-target-cleanup"
    verdict = (gate_dir / "a.verdict").read_text()
    assert verdict.startswith("U host target cleanup failed: BackendError")
    assert "op=container inspect timed_out=true" in verdict


def test_clean_host_target_cleanup_emits_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    inner = Scripted([present(), removed(), absent()])
    container_host.cleanup_targets(inner, {"owned"}, "owner")
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("historical", [False, True])
def test_controller_abort_paths_write_the_last_anomalous_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, historical: bool
) -> None:
    import argparse

    from scripts.run_effect_demo import NativeDemoAborted

    client, _ = observed([timeout()])
    recovery = StallRecovery(client, "owner")

    def fake_report(*_args: object, **_kwargs: object) -> None:
        try:
            remove_owned(client, "owned", "owner")
        except BackendError as error:
            raise NativeDemoAborted(3, "case", str(error)) from error

    evidence = tmp_path / "demo.json"
    if historical:
        monkeypatch.setattr(container_controller, "historical_demo_report", fake_report)
        monkeypatch.setattr(container_controller, "sentinel_set_from_args", lambda _args: None)
        args = argparse.Namespace(
            seed=None, budget=None, policy=None, mutation_policy=None, tar_version="7.5.2"
        )
        run = container_controller.run_native_historical_demo
    else:
        monkeypatch.setattr(container_controller, "native_demo_report", fake_report)
        args = argparse.Namespace(seed=None, budget=None, policy=None, mutation_policy=None)
        run = container_controller.run_native_effect_demo
    assert run(object(), "img", evidence, args, recovery) == 1  # type: ignore[arg-type]
    aborted = json.loads(evidence.read_text(encoding="ascii"))["aborted"]
    assert aborted["category"] == InvalidReason.CLEANUP_INSPECT.value
    assert "op=container inspect timed_out=true" in aborted["reason"]
    assert aborted["last_anomalous_docker_call"]["op"] == "container inspect"

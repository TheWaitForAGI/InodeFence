"""The broker call log records unusual calls and can never change a campaign."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from scripts import broker_call_log, container_host
from scripts.broker_call_log import (
    MAX_RECORDS,
    SLOW_CALL_SECONDS,
    STDERR_LIMIT,
    BrokerCallLog,
    call_container,
    should_record,
)

from inodefence.execution.docker_client import CommandResult

IDENTITY = "a" * 64
NAME = "inodefence-" + "b" * 32
INSPECT = ("container", "inspect", IDENTITY)
START = ("container", "start", "--attach", IDENTITY)
CREATE = (
    "container",
    "create",
    "--name",
    NAME,
    "--entrypoint",
    "SECRET-ENTRYPOINT",
    "sha256:" + "0" * 64,
    "SECRET-TARGET-ARGUMENT",
)
ABSENT = CommandResult(1, b"", f"Error: No such object: {IDENTITY}\n".encode())
FAST = 0.01


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="ascii").splitlines()]


class _FakeClient:
    """Answers each call with the next scripted result."""

    def __init__(self, *results: CommandResult) -> None:
        self.results = list(results)

    def run(self, _argv: tuple[str, ...], _timeout: float) -> CommandResult:
        return self.results.pop(0)


def _normal_step() -> tuple[list[tuple[str, ...]], list[CommandResult]]:
    """One step as the backend runs it, with a rejected target and the final absence check."""
    state = json.dumps([{"State": {"Status": "exited", "Running": False, "Pid": 0}}]).encode()
    calls: list[tuple[tuple[str, ...], CommandResult]] = [
        (("image", "inspect", "sha256:" + "0" * 64), CommandResult(0, b"[{}]", b"")),
        (CREATE, CommandResult(0, f"{IDENTITY}\n".encode(), b"")),
        (INSPECT, CommandResult(0, state, b"")),
        (START, CommandResult(2, b"out", b"SECRET-TARGET-STDERR")),
        (INSPECT, CommandResult(0, state, b"")),
        (("container", "wait", IDENTITY), CommandResult(0, b"2\n", b"")),
        (INSPECT, CommandResult(0, state, b"")),
        (INSPECT, CommandResult(0, state, b"")),
        (("container", "rm", "--force", "--volumes", IDENTITY), CommandResult(0, b"", b"")),
        (INSPECT, ABSENT),
    ]
    return [argv for argv, _ in calls], [result for _, result in calls]


# ---- what a normal step writes (fixes the smoke grade) -------------------------------------


def test_a_normal_step_records_nothing_and_the_file_is_two_lines(tmp_path: Path) -> None:
    path = tmp_path / "cell.calls.jsonl"
    log = BrokerCallLog(path)
    calls, results = _normal_step()
    client = _FakeClient(*results)
    for argv in calls:
        container_host._broker_response(client, argv, 10, log)  # type: ignore[arg-type]
    log.close()
    lines = _lines(path)
    assert [line["kind"] for line in lines] == ["header", "summary"]
    summary = lines[1]
    assert summary["recorded"] == summary["dropped"] == summary["write_failures"] == 0
    assert sum(summary["calls"].values()) == len(calls)
    assert summary["calls"]["container inspect"] == 5


@pytest.mark.parametrize("failure", ["read-only path", "raises"])
def test_a_failing_log_leaves_the_broker_response_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    calls, results = _normal_step()
    timed_out = CommandResult(-9, b"", b"", timed_out=True)
    calls, results = [*calls, INSPECT], [*results, timed_out]
    expected = [
        container_host._broker_response(_FakeClient(result), argv, 10, None)  # type: ignore[arg-type]
        for argv, result in zip(calls, results, strict=True)
    ]
    if failure == "read-only path":
        blocker = tmp_path / "file"
        blocker.write_text("x")
        log = BrokerCallLog(blocker / "below" / "cell.calls.jsonl")
    else:
        log = BrokerCallLog(tmp_path / "cell.calls.jsonl")

        def broken(*_args: object) -> bool:
            raise RuntimeError("anything at all")

        monkeypatch.setattr(broker_call_log, "should_record", broken)
    actual = [
        container_host._broker_response(_FakeClient(result), argv, 10, log)  # type: ignore[arg-type]
        for argv, result in zip(calls, results, strict=True)
    ]
    log.close()
    assert actual == expected
    assert log.write_failures >= 1
    assert log.recorded == 0


def test_failures_reach_the_cell_log_when_the_file_cannot_be_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    BrokerCallLog(blocker / "cell.calls.jsonl").close()
    assert "write failures" in capsys.readouterr().err


def test_a_clean_campaign_prints_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    BrokerCallLog(tmp_path / "cell.calls.jsonl").close()
    assert capsys.readouterr().err == ""


def test_a_header_without_a_summary_is_what_a_killed_broker_leaves(tmp_path: Path) -> None:
    path = tmp_path / "cell.calls.jsonl"
    log = BrokerCallLog(path)
    log.observe(INSPECT, CommandResult(-9, b"", b"", timed_out=True), 10.0, 1.0)
    assert [line["kind"] for line in _lines(path)] == ["header", "call"]


# ---- which calls ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "outcome", "seconds", "expected"),
    [
        # Absence: exactly rc 1, no time-out or truncation, exactly the absence text.
        (INSPECT, ABSENT, FAST, False),
        (INSPECT, CommandResult(1, b"", b"Error: something else\n"), FAST, True),
        (INSPECT, CommandResult(2, b"", ABSENT.stderr), FAST, True),
        (INSPECT, CommandResult(1, b"", ABSENT.stderr, timed_out=True), FAST, True),
        (INSPECT, CommandResult(1, b"", ABSENT.stderr, truncated=True), FAST, True),
        (("container", "inspect", "other"), ABSENT, FAST, True),
        # A slow absence answer is not routine, and the limit question is about these.
        (INSPECT, ABSENT, SLOW_CALL_SECONDS, True),
        # Start: only a time-out or truncation, whatever the exit status or duration.
        (START, CommandResult(2, b"", b""), FAST, False),
        (START, CommandResult(1, b"", b"daemon error"), FAST, False),
        (START, CommandResult(0, b"", b""), 9.0, False),
        (START, CommandResult(-9, b"", b"", timed_out=True), 10.0, True),
        (START, CommandResult(0, b"", b"", truncated=True), FAST, True),
        # Everything else.
        (INSPECT, CommandResult(0, b"[]", b""), FAST, False),
        (INSPECT, CommandResult(0, b"[]", b""), 1.99, False),
        (INSPECT, CommandResult(0, b"[]", b""), SLOW_CALL_SECONDS, True),
        (CREATE, CommandResult(0, b"", b""), SLOW_CALL_SECONDS, True),
        (CREATE, CommandResult(1, b"", b"x"), FAST, True),
        (("container", "wait", IDENTITY), CommandResult(-9, b"", b"", timed_out=True), 10.0, True),
        (("container", "kill", IDENTITY), CommandResult(1, b"", b"is not running"), FAST, True),
    ],
)
def test_should_record(
    argv: tuple[str, ...], outcome: CommandResult, seconds: float, expected: bool
) -> None:
    assert should_record(argv, outcome, seconds) is expected


# ---- what a record holds -------------------------------------------------------------------


def test_a_record_holds_no_argv_stdout_or_target_output(tmp_path: Path) -> None:
    path = tmp_path / "cell.calls.jsonl"
    log = BrokerCallLog(path)
    secret = b"SECRET-STDOUT"
    log.observe(CREATE, CommandResult(1, secret, b"daemon said no"), FAST, 123.5)
    log.observe(
        START, CommandResult(-9, secret, b"SECRET-TARGET-STDERR", timed_out=True), 10.0, 1.0
    )
    log.close()
    text = path.read_text(encoding="ascii")
    assert "SECRET" not in text
    create, start = _lines(path)[1:3]
    assert create == {
        "kind": "call",
        "op": "container create",
        "container": NAME,
        "returncode": 1,
        "timed_out": False,
        "truncated": False,
        "seconds_monotonic": FAST,
        "started_real": 123.5,
        "stderr": "daemon said no",
    }
    assert start["op"] == "container start"
    assert start["container"] == IDENTITY
    assert start["stderr_bytes"] == len(b"SECRET-TARGET-STDERR")
    assert "stderr" not in start


def test_other_stderr_is_cut(tmp_path: Path) -> None:
    path = tmp_path / "cell.calls.jsonl"
    log = BrokerCallLog(path)
    log.observe(CREATE, CommandResult(1, b"", b"e" * (STDERR_LIMIT + 50)), FAST, 1.0)
    assert len(_lines(path)[1]["stderr"]) == STDERR_LIMIT


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (INSPECT, IDENTITY),
        (START, IDENTITY),
        (CREATE, NAME),
        (("container", "inspect", NAME), NAME),
        (("image", "inspect", "sha256:" + "0" * 64), None),
        (("version", "--format", "{{json .Server}}"), None),
        (("container", "create", "--name"), None),
        (("container", "inspect", "SECRET-NOT-AN-ID"), None),
        ((), None),
    ],
)
def test_only_an_exact_identity_leaves_argv(argv: tuple[str, ...], expected: str | None) -> None:
    assert call_container(argv) == expected


def test_records_stop_at_the_limit_and_the_summary_says_so(tmp_path: Path) -> None:
    path = tmp_path / "cell.calls.jsonl"
    log = BrokerCallLog(path)
    failed = CommandResult(1, b"", b"x")
    for _ in range(MAX_RECORDS + 3):
        log.observe(CREATE, failed, FAST, 1.0)
    log.close()
    lines = _lines(path)
    assert sum(1 for line in lines if line["kind"] == "call") == MAX_RECORDS
    summary = lines[-1]
    assert summary["recorded"] == MAX_RECORDS
    assert summary["dropped"] == 3
    assert summary["write_failures"] == 0
    assert summary["calls"] == {"container create": MAX_RECORDS + 3}


# ---- the broker's arguments ----------------------------------------------------------------


def _main_with(monkeypatch: pytest.MonkeyPatch, *arguments: str) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "container_host.py",
            "--context",
            "default",
            "--controller",
            "c",
            "--volume",
            "v",
            "--image",
            "i",
            *arguments,
        ],
    )
    container_host.main()


@pytest.mark.parametrize(
    "arguments",
    [
        # The N04 ledger binds its arguments, so this mode must not take a new one.
        (
            "--evidence",
            "/tmp/e",
            "--host-ledger",
            "/tmp/h",
            "--call-log",
            "/tmp/c",
            "preflight-node-n04-5s",
        ),
        ("--evidence", "/tmp/e", "--call-log", "/tmp/c", "benign-node-smoke"),
        ("--call-log", "/tmp/c", "validate"),
        # The broker runs from the repository root, so a relative path would land there.
        ("--evidence", "/tmp/e", "--call-log", "relative.calls.jsonl", "effect-demo"),
    ],
)
def test_call_log_is_refused_outside_effect_campaigns(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: tuple[str, ...],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        _main_with(monkeypatch, *arguments)
    assert stopped.value.code == 2
    assert "--call-log" in capsys.readouterr().err


def test_no_log_means_no_clock_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> float:
        raise AssertionError("no clock without a log")

    monkeypatch.setattr(container_host, "monotonic", forbidden)
    monkeypatch.setattr(container_host, "time", forbidden)
    client = _FakeClient(CommandResult(0, b"o", b"e"))
    response = container_host._broker_response(client, INSPECT, 10, None)  # type: ignore[arg-type]
    assert response["returncode"] == 0


def test_the_response_measures_the_call_on_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cell.calls.jsonl"
    log = BrokerCallLog(path)
    clock = {"now": 100.0}

    class SlowClient:
        def run(self, _argv: tuple[str, ...], _timeout: float) -> CommandResult:
            clock["now"] += 3.0
            return CommandResult(0, b"", b"")

    monkeypatch.setattr(container_host, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(container_host, "time", lambda: 1234.5)
    container_host._broker_response(SlowClient(), INSPECT, 10, log)  # type: ignore[arg-type]
    record = _lines(path)[1]
    assert record["seconds_monotonic"] == pytest.approx(3.0)
    assert record["started_real"] == 1234.5


# ---- the harness and the launcher ----------------------------------------------------------


def _script() -> str:
    return (Path(__file__).parents[1] / "scripts/local_node_tar_smoke.sh").read_text("utf-8")


def test_harness_passes_the_log_only_to_effect_campaigns() -> None:
    lines = [line for line in _script().splitlines() if "--call-log" in line]
    assert len(lines) == 2
    assert any("IF_HISTORICAL_IMAGE" in line for line in lines)
    assert any("IF_NODE_IMAGE" in line for line in lines)


@pytest.mark.parametrize(
    ("evidence_dir", "expected"),
    [
        ("/abs/out", "/abs/out/inodefence-node-smoke-L.calls.jsonl"),
        ("rel/out", "{cwd}/rel/out/inodefence-node-smoke-L.calls.jsonl"),
    ],
)
def test_harness_log_path_is_always_absolute(
    tmp_path: Path, evidence_dir: str, expected: str
) -> None:
    script = _script()
    start = script.index('case "$HOST_EVIDENCE" in')
    end = script.index("esac", start) + len("esac")
    snippet = (
        f'HOST_EVIDENCE="{evidence_dir}/inodefence-node-smoke-L"\n'
        + script[start:end]
        + '\nprintf %s "$HOST_CALL_LOG"\n'
    )
    out = subprocess.run(
        ["bash", "-c", snippet], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert out == expected.format(cwd=tmp_path)
    assert out.endswith(".calls.jsonl")

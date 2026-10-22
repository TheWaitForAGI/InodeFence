"""Trusted-host broker for one admitted Track A campaign cell."""

import argparse
import base64
import json
import math
import selectors
import shutil
import subprocess
import threading
from dataclasses import dataclass, fields
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import BinaryIO
from uuid import uuid4

from inodefence.evaluation.encoding import decode
from inodefence.evaluation.track_a_exploratory import (
    AFFECTED_IMAGE_ID,
    FIXED_IMAGE_ID,
    PROTOCOL_CONFIG_RELATIVE,
    read_track_a_execution,
)
from inodefence.evaluation.track_a_host_ledger import (
    ClaimedTrackAHostAttempt,
    TrackAControllerTerminal,
    TrackAHostCleanupStatus,
    TrackAHostLedger,
    validate_track_a_host_admission,
)
from inodefence.execution.container import OWNER_LABEL, checked, remove_owned
from inodefence.execution.docker_client import OUTPUT_LIMIT, BackendError, DockerCLI

WATCHDOG_SECONDS = 7200
BROKER_LINE_LIMIT = 3 * OUTPUT_LIMIT + 4096


@dataclass(slots=True)
class _LaunchState:
    controller_launched: bool = False
    controller_returncode: int | None = None
    controller_terminal: TrackAControllerTerminal | None = None
    controller_stderr: bytes = b""
    controller_stderr_truncated: bool = False
    controller_stderr_capture_complete: bool = False
    deadline_expired: bool = False
    cleanup_status: TrackAHostCleanupStatus = TrackAHostCleanupStatus.NOT_NEEDED
    cleanup_errors: tuple[str, ...] = ()


class _BoundedControllerStderr:
    """Drain stderr while retaining only its exact bounded prefix."""

    def __init__(self, limit: int = OUTPUT_LIMIT) -> None:
        if type(limit) is not int or limit < 1:
            raise ValueError("controller stderr limit must be positive")
        self.limit = limit
        self.buffer = bytearray()
        self.truncated = False
        self.error: BaseException | None = None

    def drain(self, stream: BinaryIO) -> None:
        try:
            while chunk := stream.read(65536):
                available = self.limit - len(self.buffer)
                self.buffer.extend(chunk[:available])
                self.truncated |= len(chunk) > available
        except BaseException as error:
            self.error = error

    def finish(self, thread: threading.Thread) -> tuple[bytes, bool]:
        thread.join(timeout=5)
        if thread.is_alive() or self.error is not None:
            raise BackendError("Track A controller stderr could not be drained") from self.error
        return bytes(self.buffer), self.truncated


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--controller-worktree", required=True, type=PurePosixPath)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--image", required=True, action="append")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--pilot-authorization", type=Path)
    parser.add_argument("--pilot-authorization-sha256")
    parser.add_argument("--approval-reference")
    parser.add_argument("--protocol-config", type=Path)
    parser.add_argument("--run-index", type=int)
    parser.add_argument("--execution-sha256")
    parser.add_argument("mode", choices=("prepare", "run-cell"))
    args = parser.parse_args()
    if (
        not args.controller_worktree.is_absolute()
        or ".." in args.controller_worktree.parts
        or args.controller_worktree == PurePosixPath("/workspaces/InodeFence")
    ):
        parser.error("Track A requires a separate absolute controller worktree")
    if args.image != [AFFECTED_IMAGE_ID, FIXED_IMAGE_ID]:
        parser.error("Track A requires the frozen affected/fixed image IDs in order")
    if args.mode == "prepare":
        parser.error(
            "Track A prepare is not a host/controller transport; freeze requires the exact live "
            "validator result in one process"
        )
    if (
        args.run_index is None
        or args.execution_sha256 is None
        or args.pilot_authorization is None
        or args.pilot_authorization_sha256 is None
        or args.approval_reference is None
        or args.protocol_config is None
    ):
        parser.error("Track A run-cell requires the complete trusted admission binding")
    for path, label in (
        (args.evidence, "evidence"),
        (args.pilot_authorization, "pilot authorization"),
        (args.protocol_config, "protocol config"),
    ):
        if not path.is_absolute() or path.is_symlink():
            parser.error(f"Track A {label} must be an absolute nonsymlink path")
    return args


def _controller_terminal(value: object) -> TrackAControllerTerminal:
    expected = {item.name for item in fields(TrackAControllerTerminal) if item.init}
    if not isinstance(value, dict) or set(value) != expected:
        raise BackendError("malformed Track A controller terminal summary")
    try:
        result = decode(TrackAControllerTerminal, value)
    except (KeyError, TypeError, ValueError) as error:
        raise BackendError("invalid Track A controller terminal summary") from error
    return result


def _validate_launch_binding(args: argparse.Namespace, admission) -> None:
    authorization = admission.original_admission.pilot_authorization
    if (
        args.context != authorization.host_docker_context
        or args.controller != authorization.controller_id
        or args.volume != authorization.runtime_volume_name
        or args.image != [item.image_id for item in authorization.targets]
        or args.evidence != Path(authorization.track_a_output_root)
        or args.run_index is None
        or not 0 <= args.run_index < len(admission.execution.repetitions.plan.runs)
    ):
        raise ValueError("host launch inputs differ from the trusted Track A admission")
    slots = admission.execution.repetitions.slots
    if any(slot.state.value != "completed" for slot in slots[: args.run_index]):
        raise ValueError("Track A execution must stop after a prior non-complete slot")
    if slots[args.run_index].state.value != "pending" or any(
        slot.state.value != "pending" for slot in slots[args.run_index :]
    ):
        raise ValueError("Track A host can consume only the next pending cell")


def _launch_controller(
    args: argparse.Namespace,
    claimed: ClaimedTrackAHostAttempt,
    state: _LaunchState,
) -> None:
    executable = shutil.which("docker")
    if executable is None:
        raise BackendError("host Docker CLI unavailable")
    client = DockerCLI(executable, args.context)
    owner = uuid4().hex
    names: set[str] = set()
    process: subprocess.Popen[bytes] | None = None
    stderr_capture: _BoundedControllerStderr | None = None
    stderr_thread: threading.Thread | None = None
    primary_error: BaseException | None = None
    try:
        controller = json.loads(
            checked(client.run(("container", "inspect", args.controller), 10), "controller inspect")
        )[0]
        identity = controller["Id"]
        if identity != args.controller:
            raise BackendError("controller inspect identity differs from admission")
        controller_protocol = args.controller_worktree / PROTOCOL_CONFIG_RELATIVE
        command = (
            executable,
            "--context",
            args.context,
            "exec",
            "--interactive",
            "--user",
            "vscode",
            "--workdir",
            str(args.controller_worktree),
            identity,
            "env",
            f"PYTHONPATH={args.controller_worktree / 'src'}",
            "python3.12",
            "-m",
            "scripts.track_a_container_controller",
            "--controller",
            identity,
            "--volume",
            args.volume,
            "--owner",
            owner,
            *(argument for image in args.image for argument in ("--image", image)),
            "--evidence",
            str(args.evidence),
            "--host-ledger",
            str(claimed.directory.parents[1]),
            "--host-started-sha256",
            claimed.started_sha256,
            "--attempt-id",
            claimed.started.attempt_id,
            "--run-index",
            str(claimed.started.run_index),
            "--execution-sha256",
            claimed.started.execution_sha256,
            "--protocol-config",
            str(controller_protocol),
            "run-cell",
        )
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        state.controller_launched = True
        assert (
            process.stdin is not None and process.stdout is not None and process.stderr is not None
        )
        stderr_capture = _BoundedControllerStderr()
        stderr_thread = threading.Thread(
            target=stderr_capture.drain,
            args=(process.stderr,),
            name="inodefence-track-a-controller-stderr",
            daemon=True,
        )
        stderr_thread.start()
        deadline = monotonic() + WATCHDOG_SECONDS
        terminal_seen = False
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    state.deadline_expired = True
                    process.kill()
                    state.controller_returncode = process.wait(timeout=10)
                    raise TimeoutError("Track A campaign exceeded the frozen 7200s watchdog")
                line = process.stdout.readline(BROKER_LINE_LIMIT + 1)
                if not line:
                    break
                if len(line) > BROKER_LINE_LIMIT or not line.endswith(b"\n"):
                    raise BackendError("oversized or unterminated Track A controller output")
                try:
                    request = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise BackendError("malformed trusted Track A controller output") from error
                if isinstance(request, dict) and set(request) == {"terminal"}:
                    if terminal_seen:
                        raise BackendError("duplicate Track A controller terminal summary")
                    state.controller_terminal = _controller_terminal(request["terminal"])
                    terminal_seen = True
                    continue
                if terminal_seen:
                    raise BackendError("Docker request followed Track A terminal summary")
                if (
                    not isinstance(request, dict)
                    or set(request) != {"args", "timeout"}
                    or not isinstance(request["args"], list)
                    or not request["args"]
                    or not all(
                        isinstance(argument, str) and argument and "\0" not in argument
                        for argument in request["args"]
                    )
                    or not isinstance(request["timeout"], (int, float))
                    or isinstance(request["timeout"], bool)
                    or not math.isfinite(request["timeout"])
                    or request["timeout"] <= 0
                ):
                    raise BackendError("malformed trusted Track A controller request")
                argv = tuple(request["args"])
                if argv[:2] == ("container", "create"):
                    if f"{OWNER_LABEL}={owner}" not in argv or "--name" not in argv:
                        raise BackendError("container request lacks invocation ownership")
                    names.add(argv[argv.index("--name") + 1])
                    state.cleanup_status = TrackAHostCleanupStatus.FAILED
                outcome = client.run(argv, min(float(request["timeout"]), remaining))
                process.stdin.write(
                    (
                        json.dumps(
                            {
                                "returncode": outcome.returncode,
                                "stdout": base64.b64encode(outcome.stdout).decode("ascii"),
                                "stderr": base64.b64encode(outcome.stderr).decode("ascii"),
                                "timed_out": outcome.timed_out,
                                "truncated": outcome.truncated,
                            }
                        )
                        + "\n"
                    ).encode("utf-8")
                )
                process.stdin.flush()
        remaining = deadline - monotonic()
        if remaining <= 0:
            state.deadline_expired = True
            process.kill()
            state.controller_returncode = process.wait(timeout=10)
            raise TimeoutError("Track A campaign exceeded the frozen 7200s watchdog")
        try:
            state.controller_returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            state.deadline_expired = True
            process.kill()
            state.controller_returncode = process.wait(timeout=10)
            raise TimeoutError("Track A campaign exceeded the frozen 7200s watchdog") from error
        if state.controller_returncode != 0:
            raise BackendError(
                f"Track A controller exited with status {state.controller_returncode}"
            )
        if not terminal_seen:
            raise BackendError("Track A controller ended without a terminal summary")
    except BaseException as error:
        primary_error = error
        raise
    finally:
        deferred_errors: list[Exception] = []
        if process is not None and process.poll() is None:
            try:
                process.kill()
                state.controller_returncode = process.wait(timeout=10)
            except Exception as error:
                deferred_errors.append(error)
        elif process is not None and state.controller_returncode is None:
            state.controller_returncode = process.poll()
        if stderr_capture is not None and stderr_thread is not None:
            try:
                stderr, truncated = stderr_capture.finish(stderr_thread)
                state.controller_stderr = stderr
                state.controller_stderr_truncated = truncated
                state.controller_stderr_capture_complete = True
            except Exception as error:
                if primary_error is not None:
                    primary_error.add_note(f"stderr capture also failed: {error}")
                else:
                    deferred_errors.append(error)
        cleanup_errors = []
        for name in names:
            try:
                remove_owned(client, name, owner)
            except Exception as error:
                cleanup_errors.append(
                    f"{type(error).__module__}.{type(error).__qualname__}: {error}"
                )
        state.cleanup_errors = tuple(cleanup_errors)
        state.cleanup_status = (
            TrackAHostCleanupStatus.FAILED
            if cleanup_errors
            else TrackAHostCleanupStatus.COMPLETE
            if names
            else TrackAHostCleanupStatus.NOT_NEEDED
        )
        deferred_errors.extend(BackendError(message) for message in cleanup_errors)
        if primary_error is not None:
            for error in deferred_errors:
                primary_error.add_note(
                    "post-controller handling also failed: "
                    f"{type(error).__module__}.{type(error).__qualname__}: {error}"
                )
        elif len(deferred_errors) == 1:
            raise deferred_errors[0]
        elif deferred_errors:
            raise ExceptionGroup(
                "Track A host post-controller handling failed",
                deferred_errors,
            )


def _run_cell(args: argparse.Namespace) -> int:
    assert args.run_index is not None
    assert args.execution_sha256 is not None
    assert args.pilot_authorization is not None
    assert args.pilot_authorization_sha256 is not None
    assert args.approval_reference is not None
    assert args.protocol_config is not None
    admission = validate_track_a_host_admission(
        args.evidence,
        expected_execution_sha256=args.execution_sha256,
        pilot_authorization_path=args.pilot_authorization,
        expected_pilot_authorization_sha256=args.pilot_authorization_sha256,
        trusted_approval_reference=args.approval_reference,
        protocol_config_path=args.protocol_config,
    )
    _validate_launch_binding(args, admission)
    scheduled = admission.execution.repetitions.plan.runs[args.run_index]
    attempt_id = f"{scheduled.run_id}-{uuid4().hex}"
    ledger = TrackAHostLedger(admission, protocol_config_path=args.protocol_config)
    claimed = ledger.claim(args.run_index, attempt_id=attempt_id)
    state = _LaunchState()
    error: BaseException | None = None
    try:
        _launch_controller(args, claimed, state)
    except BaseException as caught:
        error = caught
    execution = admission.execution
    try:
        execution = read_track_a_execution(
            args.evidence,
            expected_execution_sha256=args.execution_sha256,
            protocol_config_path=args.protocol_config,
        )
    except BaseException as observation_error:
        if error is None:
            error = observation_error
        else:
            error.add_note(f"campaign prefix reread also failed: {observation_error}")
    try:
        ledger.finish(
            claimed,
            execution,
            controller_stderr=state.controller_stderr,
            controller_stderr_truncated=state.controller_stderr_truncated,
            controller_stderr_capture_complete=state.controller_stderr_capture_complete,
            controller_launched=state.controller_launched,
            controller_returncode=state.controller_returncode,
            controller_terminal=state.controller_terminal,
            deadline_expired=state.deadline_expired,
            cleanup_status=state.cleanup_status,
            cleanup_errors=state.cleanup_errors,
            error=error,
        )
    except BaseException as terminal_error:
        if error is None:
            raise
        error.add_note(f"host terminal publication also failed: {terminal_error}")
    if error is not None:
        raise error
    return 0


def main() -> int:
    return _run_cell(_arguments())


if __name__ == "__main__":
    raise SystemExit(main())

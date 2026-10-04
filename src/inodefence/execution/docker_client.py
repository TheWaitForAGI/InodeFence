"""Docker command transport on the trusted side only; no shell or target socket."""

import base64
import json
import math
import os
import selectors
import signal
import subprocess
from dataclasses import dataclass
from time import monotonic
from typing import Protocol, TextIO

from .base import BackendError

OUTPUT_LIMIT = 1024 * 1024


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    truncated: bool = False


class DockerClient(Protocol):
    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult: ...


def validate_command(args: tuple[str, ...], timeout: float) -> None:
    if (
        not isinstance(args, tuple)
        or not args
        or not all(isinstance(arg, str) and arg and "\0" not in arg for arg in args)
        or not (
            args[0] == "version"
            or args[:2]
            in (
                ("image", "inspect"),
                ("volume", "inspect"),
                ("container", "create"),
                ("container", "inspect"),
                ("container", "start"),
                ("container", "wait"),
                ("container", "kill"),
                ("container", "rm"),
                ("container", "top"),
            )
        )
        or type(timeout) not in (int, float)
        or not math.isfinite(timeout)
        or not 0 < timeout <= 120
    ):
        raise BackendError("invalid trusted Docker command request")


@dataclass(frozen=True, slots=True)
class DockerCLI:
    """Explicit executable/context. Controller credentials never reach the target.

    Retain the first MiB of each pipe, drain the remainder, and report truncation.
    Deadline includes pipe draining; kill/reap the CLI process group on timeout.
    Killing a CLI is not container cleanup: the backend/broker owns that separately.
    """

    executable: str
    context: str

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        validate_command(args, timeout)
        buffers = [bytearray(), bytearray()]
        truncated = False
        timed_out = False
        deadline = monotonic() + timeout
        try:
            process = subprocess.Popen(
                (self.executable, "--context", self.context, *args),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            # Popen.__exit__ waits without a deadline, including after a failed
            # group signal. Own pipe closure and the bounded wait explicitly.
            try:
                assert process.stdout is not None and process.stderr is not None
                with selectors.DefaultSelector() as selector:
                    for index, pipe in enumerate((process.stdout, process.stderr)):
                        os.set_blocking(pipe.fileno(), False)
                        selector.register(pipe, selectors.EVENT_READ, index)
                    while selector.get_map():
                        remaining = deadline - monotonic()
                        if remaining <= 0:
                            timed_out = True
                            break
                        for key, _ in selector.select(remaining):
                            chunk = os.read(key.fd, 65536)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            buffer = buffers[key.data]
                            available = OUTPUT_LIMIT - len(buffer)
                            buffer.extend(chunk[:available])
                            truncated |= len(chunk) > available
                    if not timed_out:
                        try:
                            process.wait(timeout=max(deadline - monotonic(), 1e-9))
                        except subprocess.TimeoutExpired:
                            timed_out = True
            finally:
                try:
                    # Do not poll/reap before this signal. An exited direct
                    # child still pins its PID/group ID while descendants hold
                    # pipes. After a successful wait, returncode is set and we
                    # must not signal a possibly reused group ID.
                    if process.returncode is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    returncode = process.wait(timeout=5)
                finally:
                    if process.stdout is not None:
                        process.stdout.close()
                    if process.stderr is not None:
                        process.stderr.close()
            return CommandResult(
                returncode, bytes(buffers[0]), bytes(buffers[1]), timed_out, truncated
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise BackendError("Docker CLI unavailable or did not terminate") from error


@dataclass(frozen=True, slots=True)
class StdioDockerClient:
    """Synchronous explicit broker channel; target streams never use this channel."""

    reader: TextIO
    writer: TextIO

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        validate_command(args, timeout)
        self.writer.write(json.dumps({"args": args, "timeout": timeout}) + "\n")
        self.writer.flush()
        line = self.reader.readline(3 * OUTPUT_LIMIT + 4096)
        try:
            value = json.loads(line)
            if set(value) != {"returncode", "stdout", "stderr", "timed_out", "truncated"}:
                raise ValueError("bad response fields")
            if (
                type(value["returncode"]) is not int
                or type(value["timed_out"]) is not bool
                or type(value["truncated"]) is not bool
            ):
                raise ValueError("bad response types")
            return CommandResult(
                value["returncode"],
                base64.b64decode(value["stdout"], validate=True),
                base64.b64decode(value["stderr"], validate=True),
                value["timed_out"],
                value["truncated"],
            )
        except (ValueError, TypeError) as error:
            raise BackendError(
                "trusted Docker broker disconnected or returned invalid data"
            ) from error

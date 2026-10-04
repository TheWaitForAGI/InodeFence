"""Docker-compatible disposable Linux containers; no target-specific decisions."""

import json
import math
import os
import re
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from uuid import uuid4

from inodefence.runtime import RUNTIME_BASE, open_runtime_directory

from .docker_client import BackendError, CommandResult, DockerClient

OWNER_LABEL = "org.inodefence.execution-owner"
IMPLEMENTATION = "docker-volume-subpath-v1"


@dataclass(frozen=True, slots=True)
class ResourcePolicy:
    """Per-container bounds, not a volume quota; units are bytes/counts."""

    memory_bytes: int = 512 * 1024 * 1024
    pids: int = 64
    open_files: int = 1024
    file_size_bytes: int = 64 * 1024 * 1024
    tmpfs_bytes: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class ContainerRequest:
    """Immutable content anchor, explicit argv and one existing controlled run."""

    image_id: str
    command: tuple[str, ...]
    run_root: Path
    timeout_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.image_id, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", self.image_id
        ):
            raise ValueError("target image must be an immutable local SHA-256 image ID")
        if (
            not isinstance(self.command, tuple)
            or not self.command
            or not all(isinstance(arg, str) and arg and "\0" not in arg for arg in self.command)
        ):
            raise ValueError("target command must be nonempty explicit argv")
        relative = self.run_root.relative_to(RUNTIME_BASE)
        spelling = relative.as_posix()
        if ".." in relative.parts or not re.fullmatch(
            r"(?:[a-zA-Z0-9_.-]+/)*core-run-[a-zA-Z0-9_-]+", spelling
        ):
            raise ValueError("target mounts require a disposable core-run directory")
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 120
        ):
            raise ValueError("target wall-clock timeout must be positive and at most 120 seconds")


@dataclass(frozen=True, slots=True)
class ContainerOutcome:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    duration_seconds: float
    output_truncated: bool


def checked(result: CommandResult, operation: str) -> bytes:
    if result.returncode != 0 or result.timed_out or result.truncated:
        raise BackendError(
            f"container runtime {operation} failed: {result.stderr.decode(errors='replace')}"
        )
    return result.stdout


def remove_owned(client: DockerClient, name: str, owner: str) -> None:
    """Remove only an invocation-owned identity; verify absence, never prune."""
    result = client.run(("container", "inspect", name), 10)
    if _container_absent(result, name):
        return
    info = json.loads(checked(result, "cleanup inspect"))[0]
    if (info["Config"].get("Labels") or {}).get(OWNER_LABEL) != owner:
        raise BackendError("refusing to remove a container owned by another invocation")
    checked(client.run(("container", "rm", "--force", "--volumes", info["Id"]), 10), "remove")
    remaining = client.run(("container", "inspect", info["Id"]), 10)
    if not _container_absent(remaining, info["Id"]):
        raise BackendError("container removal could not be verified")


def _container_absent(result: CommandResult, identity: str) -> bool:
    # Missing socket/context/API is a runtime error, not absence of this identity.
    messages = (
        f"Error: No such object: {identity}",
        f"Error response from daemon: No such container: {identity}",
    )
    return (
        result.returncode == 1
        and not result.timed_out
        and not result.truncated
        and result.stdout.strip() in (b"", b"[]")
        and result.stderr.decode(errors="replace").strip() in messages
    )


@dataclass(frozen=True, slots=True)
class ContainerExecutionBackend:
    """Trusted controller's named volume is shared one run at a time.

    Construction verifies Linux runtime and controller-volume binding before any
    run directory or target is created. Each prepared context rechecks image and
    runtime policy. The entire run is visible, including archive/ and outside/:
    these are observable target effects, not path-based Oracle exemptions.
    """

    client: DockerClient
    controller_id: str
    volume: str
    owner: str
    resources: ResourcePolicy = ResourcePolicy()

    def __post_init__(self) -> None:
        if sys.platform != "linux" or os.getuid() == 0 or os.getgid() == 0:
            raise ValueError("container controller requires supported non-root Linux")
        if not re.fullmatch(r"[0-9a-f]{64}", self.controller_id):
            raise ValueError("controller_id must be a full container ID")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", self.volume):
            raise ValueError("invalid named runtime volume")
        if not re.fullmatch(r"[0-9a-f]{32}", self.owner):
            raise ValueError("owner must be an invocation UUID")
        if not isinstance(self.resources, ResourcePolicy):
            raise ValueError("resources require an immutable ResourcePolicy")
        version = json.loads(
            checked(self.client.run(("version", "--format", "{{json .Server}}"), 10), "version")
        )
        if version["Os"] != "linux":
            raise BackendError("target runtime must use Linux containers")
        controller = self.inspect(self.controller_id)
        if (
            socket.gethostname() != self.controller_id[:12]
            or controller["Config"]["Hostname"] != self.controller_id[:12]
        ):
            raise BackendError("controller identity does not match this Linux process")
        if not any(
            mount["Type"] == "volume"
            and mount.get("Name") == self.volume
            and mount["Destination"] == str(RUNTIME_BASE)
            and mount["RW"]
            for mount in controller["Mounts"]
        ):
            raise BackendError("controller does not own the configured Linux runtime volume")

    def inspect(self, identity: str) -> dict:
        value = checked(self.client.run(("container", "inspect", identity), 10), "inspect")
        return json.loads(value)[0]

    def image(self, image_id: str) -> dict:
        info = json.loads(
            checked(self.client.run(("image", "inspect", image_id), 10), "image inspect")
        )[0]
        if info["Id"] != image_id or info["Os"] != "linux" or info["Config"].get("Volumes"):
            raise BackendError("image identity/platform/implicit volumes do not match the boundary")
        return info

    def create_command(self, request: ContainerRequest, name: str, image: dict) -> tuple[str, ...]:
        policy = self.resources
        root = str(request.run_root)
        subpath = request.run_root.relative_to(RUNTIME_BASE).as_posix()
        # Clear image defaults as well as excluding controller credential variables.
        env = tuple(
            arg
            for value in image["Config"].get("Env") or ()
            for arg in ("--env", value.split("=", 1)[0] + "=")
        )
        return (
            "container",
            "create",
            "--name",
            name,
            "--label",
            f"{OWNER_LABEL}={self.owner}",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--ipc",
            "private",
            "--cgroupns",
            "private",
            "--pids-limit",
            str(policy.pids),
            "--memory",
            str(policy.memory_bytes),
            "--memory-swap",
            str(policy.memory_bytes),
            "--ulimit",
            f"nofile={policy.open_files}:{policy.open_files}",
            "--ulimit",
            f"fsize={policy.file_size_bytes}:{policy.file_size_bytes}",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,nodev,size={policy.tmpfs_bytes},mode=1777",
            "--shm-size",
            "16m",
            "--log-driver",
            "none",
            "--mount",
            f"type=volume,src={self.volume},dst={root},volume-subpath={subpath},volume-nocopy",
            "--workdir",
            root + "/extract",
            *env,
            "--env",
            "PATH=/usr/local/bin:/usr/bin:/bin",
            "--env",
            "LANG=C.UTF-8",
            "--entrypoint",
            request.command[0],
            request.image_id,
            *request.command[1:],
        )

    @contextmanager
    def prepare(self, request: ContainerRequest) -> Iterator["PreparedContainer"]:
        """Prepare before BEFORE; remove after AFTER, also on observation errors."""
        with (
            open_runtime_directory(request.run_root),
            open_runtime_directory(request.run_root / "extract"),
        ):
            image = self.image(request.image_id)
            name = "inodefence-" + uuid4().hex
            try:
                identity = (
                    checked(
                        self.client.run(self.create_command(request, name, image), 20), "create"
                    )
                    .decode()
                    .strip()
                )
                info = self.inspect(identity)
                host = info["HostConfig"]
                policy = self.resources
                mount = host["Mounts"]
                # Docker versions differ only in emitting an empty default here.
                # Nonempty drivers/options and any other extra fields stay rejected.
                for entry in mount:
                    options = entry.get("VolumeOptions") or {}
                    if options.get("DriverConfig") == {}:
                        del options["DriverConfig"]
                if (
                    info["Image"] != request.image_id
                    or host["NetworkMode"] != "none"
                    or not host["ReadonlyRootfs"]
                    or host["Privileged"]
                    or host["PidMode"] != ""
                    or host["IpcMode"] != "private"
                    or host["CgroupnsMode"] != "private"
                    or host.get("CapAdd")
                    or host["CapDrop"] != ["ALL"]
                    or "no-new-privileges=true" not in host["SecurityOpt"]
                    or info["Config"]["User"] != f"{os.getuid()}:{os.getgid()}"
                    or host["PidsLimit"] != self.resources.pids
                    or host["Memory"] != self.resources.memory_bytes
                    or host["MemorySwap"] != policy.memory_bytes
                    or host["LogConfig"]["Type"] != "none"
                    or sorted(host["Ulimits"], key=lambda limit: limit["Name"])
                    != [
                        {
                            "Name": "fsize",
                            "Hard": policy.file_size_bytes,
                            "Soft": policy.file_size_bytes,
                        },
                        {"Name": "nofile", "Hard": policy.open_files, "Soft": policy.open_files},
                    ]
                    or host["Tmpfs"]
                    != {"/tmp": f"rw,noexec,nosuid,nodev,size={policy.tmpfs_bytes},mode=1777"}
                    or len(mount) != 1
                    or mount[0]
                    != {
                        "Type": "volume",
                        "Source": self.volume,
                        "Target": str(request.run_root),
                        "VolumeOptions": {
                            "NoCopy": True,
                            "Subpath": request.run_root.relative_to(RUNTIME_BASE).as_posix(),
                        },
                    }
                    or len(info["Mounts"]) != 1
                    or info["Mounts"][0]["Destination"] != str(request.run_root)
                ):
                    raise BackendError(
                        "created container differs from required execution policy: "
                        f"mounts={mount!r}; ulimits={host['Ulimits']!r}; tmpfs={host['Tmpfs']!r}"
                    )
                yield PreparedContainer(self, identity, request)
            finally:
                remove_owned(self.client, name, self.owner)


@dataclass(slots=True)
class PreparedContainer:
    backend: ContainerExecutionBackend
    identity: str
    request: ContainerRequest
    executed: bool = False

    def execute(self) -> ContainerOutcome:
        """Stop PID namespace before returning; removal is separate bookkeeping."""
        if self.executed:
            raise BackendError("one prepared container executes exactly once")
        self.executed = True
        client = self.backend.client
        start = monotonic()
        attached = client.run(
            ("container", "start", "--attach", self.identity), self.request.timeout_seconds
        )
        state = self.backend.inspect(self.identity)["State"]
        if state["Status"] == "created":
            raise BackendError("container target could not start")
        timed_out = attached.timed_out
        if not timed_out and state["Running"]:
            raise BackendError("attached runtime disconnected while target remained alive")
        if timed_out:
            if state["Running"]:
                killed = client.run(("container", "kill", self.identity), 10)
                stopped_race = (
                    killed.returncode != 0
                    and not killed.timed_out
                    and not killed.truncated
                    and b"is not running" in killed.stderr
                    and not self.backend.inspect(self.identity)["State"]["Running"]
                )
                if not stopped_race:
                    checked(killed, "timeout kill")
            checked(client.run(("container", "wait", self.identity), 10), "timeout wait")
            exit_code = None
        else:
            waited = client.run(("container", "wait", self.identity), 10)
            exit_code = int(checked(waited, "wait").strip())
        state = self.backend.inspect(self.identity)["State"]
        if state["Running"] or state["Pid"] != 0 or state["Status"] != "exited":
            raise BackendError("target execution context did not stop")
        if not timed_out and attached.returncode != exit_code:
            raise BackendError("attached runtime status differs from container exit status")
        return ContainerOutcome(
            exit_code, attached.stdout, attached.stderr, monotonic() - start, attached.truncated
        )

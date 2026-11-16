"""Host health checks for the product drivers: read-only questions to Docker and the host.

Every check here only asks; none of them changes anything. In particular nothing is removed:
a leftover container or volume is reported with the commands a person can run after inspecting
it, never cleaned up by the tool (deleting a resource whose owner is unclear could destroy another
run's evidence). Each Docker question has a time limit, and an unanswered question is a state of
its own (``timeout``), never read as "absent" or "fine".

What a check cannot see is reported as ``UNKNOWN``, not as a pass. The main example is memory on
Windows + WSL2 with Docker Desktop: the Docker Desktop backend runs on the Windows side, and its
commit limit is not visible from inside WSL (``/proc/meminfo`` there showed plenty while Windows
ran out, LOG 2026-11-16 HOST2 stop 4), so this module never claims memory is fine.

The research layer is not touched: the controller, the broker, the start gate and the experiment
launchers keep their own checks; these are the product drivers' checks around a run.
"""

from __future__ import annotations

import enum
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Seconds one Docker question may take before its answer is ``timeout``.
DOCKER_QUERY_TIMEOUT = 10.0
#: Below this much free space on the output disk a run is warned about (not refused).
DISK_WARN_BYTES = 2 * 1024**3
#: Labels the launchers and the execution backend put on what they create.
OWNER_LABELS = ("org.inodefence.smoke-owner", "org.inodefence.execution-owner")
#: The base names (before ``-<RUN_ID>``) of every launcher's controller and runtime volume: the
#: same as ``inodefence.drivers.launcher.RUN_RESOURCES`` (a test keeps them in step; repeated so
#: this module stays a stdlib-only leaf). Three launchers (decompress, oras-go, python-tarfile)
#: put no owner label on them, so they can only be found by name.
LAUNCHER_CONTROLLERS = (
    "inodefence-local-controller",
    "inodefence-decompress-controller",
    "inodefence-oras-go-controller",
    "inodefence-python-tarfile-controller",
)
LAUNCHER_VOLUMES = (
    "inodefence-local-runtime",
    "inodefence-decompress-runtime",
    "inodefence-oras-go-runtime",
    "inodefence-python-tarfile-runtime",
)

Runner = Callable[..., Any]


class DaemonState(enum.StrEnum):
    OK = "ok"
    UNREACHABLE = "unreachable"  # the CLI answered: no daemon to talk to (or not allowed)
    TIMEOUT = "timeout"  # no answer within the limit: the daemon may be alive but stalled


class ImageState(enum.StrEnum):
    PRESENT = "present"
    ABSENT = "absent"  # the daemon answered that it has no such image
    UNKNOWN = "unknown"  # no usable answer (timeout, no daemon, unexpected output)


@dataclass(frozen=True)
class DockerAnswer:
    """One Docker question: ``returncode`` is None when it did not answer (timeout / not run)."""

    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str | None = None  # the CLI could not be run at all (OSError)


def ask_docker(
    args: Sequence[str], *, runner: Runner = subprocess.run, timeout: float = DOCKER_QUERY_TIMEOUT
) -> DockerAnswer:
    """Run ``docker <args>`` with a time limit and capture the answer; never raises."""
    try:
        done = runner(
            ["docker", *args], capture_output=True, text=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return DockerAnswer(None, "", "", timed_out=True)
    except (OSError, subprocess.SubprocessError) as error:
        return DockerAnswer(None, "", "", error=f"{type(error).__name__}: {error}")
    return DockerAnswer(done.returncode, done.stdout or "", done.stderr or "")


@dataclass(frozen=True)
class DaemonStatus:
    state: DaemonState
    detail: str
    server_version: str | None = None

    @property
    def problem(self) -> str | None:
        """A one-line reason to stop before a run, or None when the daemon answered."""
        if self.state is DaemonState.OK:
            return None
        return f"Docker daemon {self.state.value}: {self.detail}"


def probe_daemon(
    *, runner: Runner = subprocess.run, timeout: float = DOCKER_QUERY_TIMEOUT
) -> DaemonStatus:
    """``docker info`` with a time limit -> ok / unreachable / timeout (read-only)."""
    if runner is subprocess.run and shutil.which("docker") is None:
        return DaemonStatus(
            DaemonState.UNREACHABLE,
            "docker not found on PATH; install Docker (Linux: Docker Engine; Windows: Docker "
            "Desktop with WSL integration) and run on that host (the Dev Container has no docker)",
        )
    answer = ask_docker(["info", "--format", "{{.ServerVersion}}"], runner=runner, timeout=timeout)
    if answer.timed_out:
        return DaemonStatus(
            DaemonState.TIMEOUT,
            f"`docker info` did not answer within {timeout:g}s; the daemon may be stalled. Nothing "
            "was started; check Docker (Docker Desktop) and retry",
        )
    if answer.returncode is None:
        return DaemonStatus(DaemonState.UNREACHABLE, f"could not run docker ({answer.error})")
    version = answer.stdout.strip()
    if answer.returncode == 0 and version:
        return DaemonStatus(DaemonState.OK, f"server {version}", version)
    lines = (answer.stderr or answer.stdout).strip().splitlines()
    first = lines[0] if lines else f"exit {answer.returncode}"
    if "permission denied" in first.lower():
        return DaemonStatus(
            DaemonState.UNREACHABLE,
            f"{first}; your user may not use the Docker daemon (Linux: add it to the docker group "
            "and log in again)",
        )
    return DaemonStatus(
        DaemonState.UNREACHABLE,
        f"{first}; start Docker (Docker Desktop, or `sudo service docker start`) and retry",
    )


_ABSENT_MARKERS = ("no such image", "no such object")


@dataclass(frozen=True)
class ImageLookup:
    state: ImageState
    image_id: str | None = None
    detail: str = ""


def lookup_image(
    image_ref: str, *, runner: Runner = subprocess.run, timeout: float = DOCKER_QUERY_TIMEOUT
) -> ImageLookup:
    """Is ``image_ref`` on this host? present (with its id) / absent / unknown.

    ``absent`` only when the daemon itself says so; a timeout, a missing daemon or any other
    failure is ``unknown``, so a caller never prepares (builds) an image because Docker was silent.
    """
    answer = ask_docker(
        ["image", "inspect", "--format", "{{.Id}}", image_ref], runner=runner, timeout=timeout
    )
    if answer.timed_out:
        return ImageLookup(
            ImageState.UNKNOWN,
            detail=f"`docker image inspect` did not answer within {timeout:g}s (Docker stalled?)",
        )
    if answer.returncode is None:
        return ImageLookup(ImageState.UNKNOWN, detail=f"could not run docker ({answer.error})")
    if answer.returncode == 0:
        found = answer.stdout.strip()
        if found:
            return ImageLookup(ImageState.PRESENT, found)
        return ImageLookup(ImageState.UNKNOWN, detail="`docker image inspect` printed no id")
    said = (answer.stderr + answer.stdout).lower()
    if any(marker in said for marker in _ABSENT_MARKERS):
        return ImageLookup(ImageState.ABSENT, detail="no such image on this host")
    first = (answer.stderr or answer.stdout).strip().splitlines()
    return ImageLookup(
        ImageState.UNKNOWN,
        detail=f"Docker did not answer the image question ({first[0] if first else 'no output'})",
    )


@dataclass(frozen=True)
class Residue:
    """Leftover containers / volumes that look like InodeFence's (read-only listing)."""

    containers: tuple[str, ...] = ()
    volumes: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()  # questions Docker did not answer (the listing is incomplete)

    @property
    def clean(self) -> bool:
        return not self.containers and not self.volumes and not self.unknown

    def lines(self) -> list[str]:
        """Human-readable findings with the commands a person may run; nothing is run here."""
        out = []
        if self.containers:
            out.append("leftover containers: " + ", ".join(self.containers))
        if self.volumes:
            out.append("leftover volumes: " + ", ".join(self.volumes))
        if self.containers or self.volumes:
            out.append(
                "nothing was removed. Inspect each first (`docker container inspect <name>`, "
                "`docker volume inspect <name>`); only if it is yours and no run is using it, "
                "remove it by name (`docker rm -f <name>`, `docker volume rm <name>`)"
            )
        for item in self.unknown:
            out.append(f"could not list {item}: state unknown (not reported as clean)")
        return out


def _container_listing(args: list[str]) -> list[str]:
    return ["ps", "-a", *args, "--format", "{{.Names}}\t{{.Status}}"]


def find_residue(
    *, runner: Runner = subprocess.run, timeout: float = DOCKER_QUERY_TIMEOUT
) -> Residue:
    """List containers and volumes carrying an InodeFence owner label or a launcher's own name.

    Read-only (``docker ps -a`` / ``docker volume ls`` with filters). The long-lived Dev Container
    volumes (``inodefence-codex``, ``inodefence-runtime``) match no launcher name and carry no
    owner label, so they are not reported.
    """
    containers: dict[str, str] = {}
    volumes: set[str] = set()
    unknown: list[str] = []
    labels = [f"label={label}" for label in OWNER_LABELS]
    for selector in [*labels, *(f"name={name}" for name in LAUNCHER_CONTROLLERS)]:
        answer = ask_docker(
            _container_listing(["--filter", selector]), runner=runner, timeout=timeout
        )
        if answer.returncode != 0:
            unknown.append(f"containers ({selector})")
            continue
        for line in answer.stdout.splitlines():
            name, _, status = line.partition("\t")
            if name.strip():
                containers[name.strip()] = status.strip()
    for selector in [*labels, *(f"name={name}" for name in LAUNCHER_VOLUMES)]:
        answer = ask_docker(
            ["volume", "ls", "--filter", selector, "--format", "{{.Name}}"],
            runner=runner,
            timeout=timeout,
        )
        if answer.returncode != 0:
            unknown.append(f"volumes ({selector})")
            continue
        volumes.update(name.strip() for name in answer.stdout.splitlines() if name.strip())
    return Residue(
        containers=tuple(
            f"{name} ({status})" if status else name for name, status in sorted(containers.items())
        ),
        volumes=tuple(sorted(volumes)),
        unknown=tuple(unknown),
    )


def run_resources_exist(
    controller: str,
    volume: str,
    *,
    runner: Runner = subprocess.run,
    timeout: float = DOCKER_QUERY_TIMEOUT,
) -> str | None:
    """Why a run must not start because its own controller / volume name is taken, or None.

    The launchers already stop (exit 1) on a stale controller or volume of the same name; this
    asks the same question before anything is prepared, so the refusal comes first. An unanswered
    question is a reason too (the name's state is unknown).
    """
    for kind, name in (("container", controller), ("volume", volume)):
        answer = ask_docker([kind, "inspect", name], runner=runner, timeout=timeout)
        if answer.returncode == 0:
            return (
                f"{kind} {name} already exists (left by an earlier run?). Nothing was removed; "
                f"inspect it (`docker {kind} inspect {name}`) and remove it yourself if it is "
                "yours and unused"
            )
        said = (answer.stderr + answer.stdout).lower()
        if answer.returncode is None or "no such" not in said:
            return f"could not tell whether {kind} {name} exists (Docker did not answer)"
    return None


def run_leftovers(
    controller: str,
    volume: str,
    *,
    runner: Runner = subprocess.run,
    timeout: float = DOCKER_QUERY_TIMEOUT,
) -> list[str]:
    """After a run: is this run's own controller / volume still there? One line per finding.

    Empty when both are gone. A name still present, or a question Docker did not answer, is
    reported (cleanup state not confirmed); nothing is removed.
    """
    found = []
    for kind, name in (("container", controller), ("volume", volume)):
        answer = ask_docker([kind, "inspect", name], runner=runner, timeout=timeout)
        if answer.returncode == 0:
            found.append(
                f"this run's {kind} {name} still exists (cleanup not confirmed; nothing was "
                f"removed -- inspect with `docker {kind} inspect {name}`)"
            )
        elif answer.returncode is None or "no such" not in (answer.stderr + answer.stdout).lower():
            found.append(f"could not tell whether this run's {kind} {name} is gone (no answer)")
    return found


@dataclass(frozen=True)
class DiskStatus:
    path: Path
    free_bytes: int | None
    low: bool
    detail: str


def disk_free(path: Path, *, warn_below: int = DISK_WARN_BYTES) -> DiskStatus:
    """Free space on the disk that holds ``path`` (its nearest existing parent)."""
    probe = path.expanduser()
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError as error:
        return DiskStatus(path, None, False, f"free space unknown ({error})")
    gib = free / 1024**3
    low = free < warn_below
    detail = f"{gib:.1f} GiB free at {probe}"
    if low:
        detail += f" (below {warn_below / 1024**3:.0f} GiB: a long run may fill it)"
    return DiskStatus(path, free, low, detail)


@dataclass(frozen=True)
class MemoryStatus:
    """Memory headroom as far as it can be seen; ``state`` is always ``UNKNOWN`` for a pass."""

    state: str
    detail: str
    available_bytes: int | None = field(default=None)


def memory_status(meminfo: Path = Path("/proc/meminfo")) -> MemoryStatus:
    """What this host can say about memory: never a pass for the Docker Desktop backend.

    ``MemAvailable`` is reported when readable, but on Windows + WSL2 the Docker Desktop backend's
    memory is on the Windows side (commit limit), which cannot be read from here; so the state
    stays ``UNKNOWN`` rather than OK.
    """
    available = None
    try:
        for line in meminfo.read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                available = int(line.split()[1]) * 1024
                break
    except (OSError, ValueError):
        available = None
    seen = (
        f"MemAvailable here {available / 1024**3:.1f} GiB"
        if available is not None
        else "MemAvailable unreadable"
    )
    return MemoryStatus(
        "UNKNOWN",
        f"not checked: inside WSL the Windows commit limit (where the Docker Desktop backend's "
        f"memory lives) cannot be seen; {seen}",
        available,
    )

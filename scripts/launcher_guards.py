"""Host-side guards shared by the concurrent launchers.

The concurrency benchmark (``scripts/run_concurrency_benchmark.py``) and the
registered launcher (``scripts/run_exp0.py --jobs``) must run cells under the
same protections, so these live here instead of inside one driver:

* docker preflight: engine version, image identities, running containers and
  leftover InodeFence resources before the first cell (:func:`docker_preflight`);
* leftover resources after a block (:func:`residual_resources`,
  :func:`residual_status`);
* a started child whose runner failed is terminated, then killed
  (:func:`terminate_started`), and incomplete evidence is published once,
  never replacing earlier evidence (:func:`publish_json_once`);
* record-only host sampling (memory, pressure, disk, docker responsiveness) and
  a docker event collector (:func:`sample_host`, :func:`start_docker_events`).

Stop policies are not decided here. Callers inject them: the benchmark stops a
level on host pressure; a registered launcher may only record samples. The
start gate for UNKNOWN cleanup is ``inodefence.execution.start_gate``.

Nothing here reads oracle values.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DOCKER_TIMEOUT_SECONDS = 60.0
PROC_SAMPLE_SECONDS = 30.0
DOCKER_PROBE_SECONDS = 60.0
EVENT_ACTIONS = ("create", "start", "die", "destroy")
TERMINATE_GRACE_SECONDS = 30.0
#: The execution path both launchers must share (concurrency design v3 section 4.1).
#: Recorded by sha256 before a run; if the benchmark's and the registration's
#: lists differ, benchmark results do not transfer.
SHARED_PATH_FILES = (
    "scripts/local_node_tar_smoke.sh",
    "scripts/bounded_cleanup_command.py",
    "src/inodefence/execution/container.py",
    "src/inodefence/execution/docker_client.py",
    "scripts/container_host.py",
    "scripts/container_controller.py",
    "scripts/run_exp0.py",
    "scripts/run_parallel_native.py",
    "src/inodefence/execution/start_gate.py",
    "scripts/launcher_guards.py",
)

Docker = Callable[..., str]


def clock_stamp() -> dict[str, float]:
    return {
        "realtime": time.clock_gettime(time.CLOCK_REALTIME),
        "monotonic": time.clock_gettime(time.CLOCK_MONOTONIC),
        "monotonic_raw": time.clock_gettime(time.CLOCK_MONOTONIC_RAW),
    }


def docker_cli(*args: str, timeout: float = DOCKER_TIMEOUT_SECONDS) -> str:
    """Run one docker CLI call; a nonzero exit raises ``RuntimeError`` with stderr."""
    done = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip()


def shared_path_sha256(repo_root: Path) -> dict[str, str | None]:
    """sha256 of every shared-path file at ``repo_root``; ``None`` for a missing file."""
    import hashlib

    hashes: dict[str, str | None] = {}
    for relative in SHARED_PATH_FILES:
        path = repo_root / relative
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return hashes


def residual_resources(docker: Docker = docker_cli) -> list[str]:
    """InodeFence containers or volumes left behind; a stale one blocks the next cell."""
    containers = docker("ps", "-a", "--filter", "name=inodefence-", "--format", "{{.Names}}")
    volumes = docker("volume", "ls", "--filter", "name=inodefence-local-", "--format", "{{.Name}}")
    return [*containers.split(), *volumes.split()]


def residual_status(probe: Callable[[], list[str]] = residual_resources) -> dict[str, Any]:
    """``{"status": "observed", "resources": [...]}``, or ``unknown`` with the error."""
    try:
        return {"status": "observed", "resources": probe()}
    except Exception as error:
        return {"status": "unknown", "error": f"{type(error).__name__}: {error}"}


def docker_preflight(
    *,
    engine: str,
    images: Mapping[str, str | None],
    docker: Docker = docker_cli,
    residual: Callable[[], list[str]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Docker facts before the first cell, and the problems that refuse the run.

    ``images`` maps an image reference to its required id, or to ``None`` when
    it only has to exist (cells run with ``SKIP_BUILD=1``). Any docker failure
    is one problem; the facts gathered so far are still returned.
    """
    facts: dict[str, Any] = {}
    problems: list[str] = []
    try:
        server = docker("version", "--format", "{{.Server.Version}}")
        image_ids = {
            name: docker("image", "inspect", name, "--format", "{{.Id}}") for name in images
        }
        running = docker("ps", "--format", "{{.Names}}").split()
        leftover = residual() if residual is not None else residual_resources(docker)
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        return facts, [f"docker: {error}"]
    facts.update(docker_server=server, image_ids=image_ids)
    if server != engine:
        problems.append(f"docker engine {server} != {engine}")
    for name, required in images.items():
        if required is not None and image_ids[name] != required:
            problems.append(f"{name} is {image_ids[name]}, not {required}")
    if running:
        problems.append(f"other containers are running: {running}")
    if leftover:
        problems.append(f"residual benchmark resources exist: {leftover}")
    return facts, problems


def terminate_started(process: Any, grace: float = TERMINATE_GRACE_SECONDS) -> str:
    """Terminate, then kill, a started child whose runner failed. Returns a note.

    Never raises: the note says whether the process is known to be gone. Its
    containers and volumes still need verification either way.
    """
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=grace)
        return (
            f"started process {process.pid} exited with {process.returncode}; "
            "container and volume cleanup still requires verification"
        )
    except Exception as cleanup_error:
        return (
            f"started process cleanup failed: {type(cleanup_error).__name__}: "
            f"{cleanup_error}; process and resources may remain"
        )


def publish_json_once(path: Path, value: Mapping[str, Any], prefix: str = ".block-") -> None:
    """Publish once without exposing a partial file or replacing existing evidence."""
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=prefix, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as error:
                print(f"temporary evidence file could not be removed: {error}", file=sys.stderr)


def read_host_counters(proc: Path = Path("/proc")) -> dict[str, Any]:
    """Cheap kernel counters. In WSL2 every distro shares one VM, so these cover Docker's work."""
    memory: dict[str, int] = {}
    for line in (proc / "meminfo").read_text(encoding="ascii").splitlines():
        name, _, rest = line.partition(":")
        if name in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
            memory[name] = int(rest.split()[0]) * 1024
    cpu = (proc / "stat").read_text(encoding="ascii").splitlines()[0].split()[1:]
    pressure: dict[str, str] = {}
    for name in ("cpu", "io", "memory"):
        path = proc / "pressure" / name
        if path.is_file():
            pressure[name] = path.read_text(encoding="ascii").splitlines()[0]
    return {"memory": memory, "cpu_jiffies": [int(item) for item in cpu], "pressure": pressure}


def sample_host(
    path: Path,
    stop: threading.Event,
    *,
    disk_fraction: Callable[[], float],
    on_sample: Callable[[dict[str, Any]], None] | None = None,
    on_failure: Callable[[Exception], None] | None = None,
    counters: Callable[[], dict[str, Any]] = read_host_counters,
    docker: Docker = docker_cli,
    seconds: float = PROC_SAMPLE_SECONDS,
    probe_seconds: float = DOCKER_PROBE_SECONDS,
) -> None:
    """Append host samples to ``path`` until ``stop`` is set.

    ``on_sample`` is the injected stop policy (``None`` = record only). A
    sampler failure goes to ``on_failure``: a caller that relies on the
    sampler's guards should stop, because they are off from then on.
    """
    next_probe = 0.0
    try:
        with path.open("a", encoding="utf-8") as stream:
            while True:
                sample: dict[str, Any] = {
                    **clock_stamp(),
                    "loadavg": os.getloadavg(),
                    "disk_fraction": disk_fraction(),
                    **counters(),
                }
                if sample["monotonic"] >= next_probe:
                    # Daemon responsiveness at a fixed low rate: the same load at every level.
                    probe_started = time.clock_gettime(time.CLOCK_REALTIME)
                    try:
                        names = docker("ps", "--format", "{{.Names}}").split()
                        sample["containers"] = names
                        sample["docker_ps_seconds"] = (
                            time.clock_gettime(time.CLOCK_REALTIME) - probe_started
                        )
                    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                        sample["docker_ps_error"] = str(error)
                    next_probe = sample["monotonic"] + probe_seconds
                stream.write(json.dumps(sample, sort_keys=True) + "\n")
                stream.flush()
                if on_sample is not None:
                    on_sample(sample)
                if stop.wait(seconds):
                    return
    except Exception as error:
        if on_failure is None:
            raise
        on_failure(error)


def start_docker_events(
    path: Path, actions: Sequence[str] = EVENT_ACTIONS
) -> subprocess.Popen[bytes]:
    """Collect container events as JSON lines into ``path`` until stopped."""
    filters = [item for action in actions for item in ("--filter", f"event={action}")]
    with path.open("wb") as stream:
        return subprocess.Popen(
            ["docker", "events", "--format", "{{json .}}", "--filter", "type=container", *filters],
            stdout=stream,
            stderr=subprocess.DEVNULL,
        )


def stop_docker_events(events: subprocess.Popen[bytes]) -> None:
    """Stop the event collector, preserving any failure and bounding the reap."""
    try:
        events.terminate()
        events.wait(timeout=30)
    except Exception as error:
        try:
            events.kill()
            events.wait(timeout=30)
        except Exception as cleanup_error:
            error.add_note(f"event collector cleanup failed: {cleanup_error}")
        raise


# ---- read-only stall instrumentation (records only; never stops anything) ----

PING_SECONDS = 1.0
PING_TIMEOUT_SECONDS = 10.0
DEFAULT_DOCKER_SOCKET = Path("/var/run/docker.sock")
LOG_TAIL_SECONDS = 1.0
LOG_TAIL_CHUNK = 1 << 20


def ping_daemon(socket_path: Path, timeout: float = PING_TIMEOUT_SECONDS) -> dict[str, Any]:
    """One ``GET /_ping`` on the daemon socket: latency and status, never raises.

    Lighter than any CLI call, so a stall shows up as the daemon's, not the CLI's.
    """
    import socket

    record: dict[str, Any] = clock_stamp()
    started = time.monotonic()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(socket_path))
            connection.sendall(b"GET /_ping HTTP/1.0\r\nHost: docker\r\n\r\n")
            response = b""
            while chunk := connection.recv(4096):
                response += chunk
                if len(response) > 65536:
                    break
        status_line = response.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
        record["status"] = status_line
        record["ok"] = status_line.split(" ")[1:2] == ["200"] and response.endswith(b"OK")
    except Exception as error:
        record["ok"] = False
        record["error"] = f"{type(error).__name__}: {error}"
    record["seconds"] = time.monotonic() - started
    return record


def ping_loop(
    path: Path,
    stop: threading.Event,
    socket_path: Path = DEFAULT_DOCKER_SOCKET,
    seconds: float = PING_SECONDS,
    ping: Callable[[Path], dict[str, Any]] = ping_daemon,
) -> None:
    """Append one ping record per ``seconds`` to ``path`` until ``stop`` is set."""
    with path.open("a", encoding="utf-8") as stream:
        while True:
            stream.write(json.dumps(ping(socket_path), sort_keys=True) + "\n")
            stream.flush()
            if stop.wait(seconds):
                return


def tail_log(
    source: Path,
    destination: Path,
    stop: threading.Event,
    seconds: float = LOG_TAIL_SECONDS,
) -> None:
    """Copy what is appended to ``source`` into ``destination`` until ``stop`` is set.

    Read-only on ``source``. For logs that keep only seconds of history (Docker
    Desktop's), copied continuously so a stall's surroundings survive. A
    truncated or replaced source is reopened from its start and marked.
    """
    position = 0
    identity: tuple[int, int] | None = None
    with destination.open("ab") as out:
        while True:
            try:
                status = source.stat()
                current = (status.st_dev, status.st_ino)
                if identity is not None and (current != identity or status.st_size < position):
                    out.write(b"\n[inodefence-log-tail: source rotated or truncated]\n")
                    position = 0
                identity = current
                with source.open("rb") as stream:
                    stream.seek(position)
                    while chunk := stream.read(LOG_TAIL_CHUNK):
                        out.write(chunk)
                        position += len(chunk)
            except FileNotFoundError:
                identity = None
                position = 0
            out.flush()
            if stop.wait(seconds):
                return


@dataclass(frozen=True)
class Recorders:
    """Optional record-only instruments; all off by default."""

    ping_socket: Path | None = None
    desktop_log: Path | None = None


def _record_quietly(function: Callable[..., None], *args: Any) -> None:
    try:
        function(*args)
    except Exception as error:  # a recorder never stops a run
        print(
            f"recorder {function.__name__} failed: {type(error).__name__}: {error}", file=sys.stderr
        )


def start_recorders(
    directory: Path, recorders: Recorders, stop: threading.Event
) -> list[threading.Thread]:
    """Start the enabled recorders into ``directory``; join them after setting ``stop``."""
    jobs: list[tuple[Callable[..., None], tuple[Any, ...]]] = []
    if recorders.ping_socket is not None:
        jobs.append((ping_loop, (directory / "ping.jsonl", stop, recorders.ping_socket)))
    if recorders.desktop_log is not None:
        jobs.append((tail_log, (recorders.desktop_log, directory / "desktop.log", stop)))
    threads = [
        threading.Thread(target=_record_quietly, args=(function, *args), daemon=True)
        for function, args in jobs
    ]
    for thread in threads:
        thread.start()
    return threads

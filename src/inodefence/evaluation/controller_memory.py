"""Linux controller-process peak-memory observation with explicit scope limits."""

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic_ns
from typing import ClassVar
from uuid import UUID

MEMORY_PROFILE = "linux-proc-self-vmhwm-v1"
MEMORY_SCOPE = "current-process-lifetime-not-campaign-delta"


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("memory timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("memory timestamp must be ISO-8601") from error
    if parsed.utcoffset() is None:
        raise ValueError("memory timestamp requires a UTC offset")
    return parsed


def _boot_id(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("boot ID must be text")
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise ValueError("boot ID must be a UUID") from error
    if str(parsed) != value:
        raise ValueError("boot ID must use canonical UUID text")


@dataclass(frozen=True, slots=True)
class LinuxProcessMemorySample:
    """One kernel-reported sample for the current Linux process."""

    serialization_schema: ClassVar[int] = 1

    process_id: int
    boot_id: str
    process_start_ticks: int
    clock_ticks_per_second: int
    resident_bytes: int
    lifetime_peak_resident_bytes: int
    profile: str = MEMORY_PROFILE

    def __post_init__(self) -> None:
        if type(self.process_id) is not int or self.process_id <= 0:
            raise ValueError("positive process ID required")
        _boot_id(self.boot_id)
        if (
            type(self.process_start_ticks) is not int
            or self.process_start_ticks < 0
            or type(self.clock_ticks_per_second) is not int
            or self.clock_ticks_per_second <= 0
            or type(self.resident_bytes) is not int
            or self.resident_bytes < 0
            or type(self.lifetime_peak_resident_bytes) is not int
            or self.lifetime_peak_resident_bytes < self.resident_bytes
        ):
            raise ValueError("invalid Linux process memory sample")
        if self.profile != MEMORY_PROFILE:
            raise ValueError("unsupported controller memory profile")

    @property
    def process_identity(self) -> tuple[str, int, int]:
        return (self.boot_id, self.process_id, self.process_start_ticks)


@dataclass(frozen=True, slots=True)
class ControllerMemoryObservation:
    """Process-lifetime HWM around one run, never an inferred campaign delta."""

    serialization_schema: ClassVar[int] = 1

    started_at_utc: str
    completed_at_utc: str
    elapsed_ns: int
    started: LinuxProcessMemorySample
    completed: LinuxProcessMemorySample
    scope: str = MEMORY_SCOPE

    def __post_init__(self) -> None:
        started_at = _timestamp(self.started_at_utc)
        completed_at = _timestamp(self.completed_at_utc)
        if completed_at < started_at:
            raise ValueError("memory completion timestamp precedes start")
        if type(self.elapsed_ns) is not int or self.elapsed_ns < 0:
            raise ValueError("memory observation elapsed time must be nonnegative")
        if (
            not isinstance(self.started, LinuxProcessMemorySample)
            or not isinstance(self.completed, LinuxProcessMemorySample)
            or self.started.process_identity != self.completed.process_identity
            or self.started.clock_ticks_per_second != self.completed.clock_ticks_per_second
            or self.completed.lifetime_peak_resident_bytes
            < self.started.lifetime_peak_resident_bytes
        ):
            raise ValueError("memory observation changed process identity or regressed HWM")
        if self.scope != MEMORY_SCOPE:
            raise ValueError("unsupported controller memory scope")

    @property
    def process_identity(self) -> tuple[str, int, int]:
        return self.started.process_identity

    @property
    def lifetime_peak_resident_bytes(self) -> int:
        return self.completed.lifetime_peak_resident_bytes


@dataclass(frozen=True, slots=True)
class ControllerMemoryObservationStart:
    """Non-serialized monotonic origin paired with the first process sample."""

    started_at_utc: str
    monotonic_origin_ns: int
    sample: LinuxProcessMemorySample


def _status_fields(content: str) -> tuple[int, int, int]:
    values: dict[str, str] = {}
    for line in content.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"Pid", "VmRSS", "VmHWM"}:
            if key in values:
                raise ValueError(f"duplicate /proc status field: {key}")
            values[key] = value.strip()
    if set(values) != {"Pid", "VmRSS", "VmHWM"}:
        raise ValueError("/proc status lacks Pid, VmRSS or VmHWM")

    def kibibytes(name: str) -> int:
        parts = values[name].split()
        if len(parts) != 2 or parts[1] != "kB":
            raise ValueError(f"unsupported /proc status unit for {name}")
        amount = int(parts[0])
        if amount < 0:
            raise ValueError(f"negative /proc status value for {name}")
        return amount * 1024

    process_id = int(values["Pid"])
    if process_id <= 0:
        raise ValueError("invalid /proc status process ID")
    return process_id, kibibytes("VmRSS"), kibibytes("VmHWM")


def _stat_identity(content: str) -> tuple[int, int]:
    closing = content.rstrip().rfind(")")
    if closing < 0:
        raise ValueError("invalid /proc stat command field")
    prefix = content[:closing]
    first_space = prefix.find(" ")
    if first_space <= 0 or prefix[first_space + 1 : first_space + 2] != "(":
        raise ValueError("invalid /proc stat process prefix")
    process_id = int(prefix[:first_space])
    fields = content[closing + 1 :].split()
    if len(fields) <= 19:
        raise ValueError("/proc stat lacks process start time")
    start_ticks = int(fields[19])
    if process_id <= 0 or start_ticks < 0:
        raise ValueError("invalid /proc stat process identity")
    return process_id, start_ticks


def sample_linux_process_memory(
    *,
    process_root: Path = Path("/proc/self"),
    boot_id_path: Path = Path("/proc/sys/kernel/random/boot_id"),
    clock_ticks_per_second: int | None = None,
) -> LinuxProcessMemorySample:
    """Read exact current-process RSS/HWM facts from procfs without polling."""
    if sys.platform != "linux":
        raise NotImplementedError("controller peak-memory observation requires Linux procfs")
    status_pid, resident_bytes, peak_bytes = _status_fields(
        (process_root / "status").read_text(encoding="ascii")
    )
    stat_pid, start_ticks = _stat_identity((process_root / "stat").read_text(encoding="ascii"))
    if status_pid != stat_pid:
        raise ValueError("/proc status/stat process identity mismatch")
    ticks = os.sysconf("SC_CLK_TCK") if clock_ticks_per_second is None else clock_ticks_per_second
    return LinuxProcessMemorySample(
        status_pid,
        boot_id_path.read_text(encoding="ascii").strip(),
        start_ticks,
        ticks,
        resident_bytes,
        peak_bytes,
    )


def start_controller_memory_observation() -> ControllerMemoryObservationStart:
    """Capture the process identity/HWM before a controller run is claimed."""
    started_at = datetime.now(UTC).isoformat()
    origin = monotonic_ns()
    if type(origin) is not int or origin < 0:
        raise ValueError("monotonic clock returned an invalid memory origin")
    return ControllerMemoryObservationStart(started_at, origin, sample_linux_process_memory())


def finish_controller_memory_observation(
    started: ControllerMemoryObservationStart,
) -> ControllerMemoryObservation:
    """Capture the same process after terminal evidence publication."""
    if not isinstance(started, ControllerMemoryObservationStart):
        raise ValueError("memory completion requires a typed observation start")
    completed = sample_linux_process_memory()
    now = monotonic_ns()
    if type(now) is not int or now < started.monotonic_origin_ns:
        raise ValueError("monotonic clock moved backward during memory observation")
    return ControllerMemoryObservation(
        started.started_at_utc,
        datetime.now(UTC).isoformat(),
        now - started.monotonic_origin_ns,
        started.sample,
        completed,
    )

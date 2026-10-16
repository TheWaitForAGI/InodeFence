"""Controller memory evidence preserves Linux facts without inventing a delta."""

import os
import sys
from dataclasses import replace

import pytest

import inodefence.evaluation.controller_memory as memory_module
from inodefence.evaluation.controller_memory import (
    MEMORY_SCOPE,
    ControllerMemoryObservation,
    LinuxProcessMemorySample,
    sample_linux_process_memory,
)

BOOT_ID = "12345678-1234-5678-9234-567812345678"


def _sample(*, resident: int = 10 * 1024, peak: int = 20 * 1024):
    return LinuxProcessMemorySample(123, BOOT_ID, 42, 100, resident, peak)


def test_proc_reader_converts_kibibytes_and_preserves_process_identity(monkeypatch, tmp_path):
    process_root = tmp_path / "self"
    process_root.mkdir()
    (process_root / "status").write_text(
        "Name:\tcontroller\nPid:\t123\nVmHWM:\t20 kB\nVmRSS:\t10 kB\n",
        encoding="ascii",
    )
    stat_fields = ["R", *("0" for _ in range(18)), "42"]
    (process_root / "stat").write_text(
        f"123 (controller worker) {' '.join(stat_fields)}\n",
        encoding="ascii",
    )
    boot_id = tmp_path / "boot_id"
    boot_id.write_text(f"{BOOT_ID}\n", encoding="ascii")
    monkeypatch.setattr(memory_module.sys, "platform", "linux")

    sample = sample_linux_process_memory(
        process_root=process_root,
        boot_id_path=boot_id,
        clock_ticks_per_second=100,
    )

    assert sample.process_identity == (BOOT_ID, 123, 42)
    assert sample.resident_bytes == 10 * 1024
    assert sample.lifetime_peak_resident_bytes == 20 * 1024


def test_proc_reader_rejects_missing_or_unknown_memory_units(monkeypatch, tmp_path):
    process_root = tmp_path / "self"
    process_root.mkdir()
    (process_root / "status").write_text(
        "Pid:\t123\nVmHWM:\t20 MB\nVmRSS:\t10 kB\n",
        encoding="ascii",
    )
    (process_root / "stat").write_text(
        f"123 (controller) {' '.join(['R', *('0' for _ in range(18)), '42'])}\n",
        encoding="ascii",
    )
    boot_id = tmp_path / "boot_id"
    boot_id.write_text(BOOT_ID, encoding="ascii")
    monkeypatch.setattr(memory_module.sys, "platform", "linux")

    with pytest.raises(ValueError, match="unsupported /proc status unit"):
        sample_linux_process_memory(
            process_root=process_root,
            boot_id_path=boot_id,
            clock_ticks_per_second=100,
        )


def test_observation_requires_stable_identity_and_monotonic_lifetime_peak():
    observation = ControllerMemoryObservation(
        "2026-10-16T00:00:00+00:00",
        "2026-10-16T00:00:01+00:00",
        1,
        _sample(),
        _sample(resident=12 * 1024, peak=24 * 1024),
    )
    assert observation.scope == MEMORY_SCOPE
    assert observation.lifetime_peak_resident_bytes == 24 * 1024

    with pytest.raises(ValueError, match="changed process identity"):
        replace(
            observation,
            completed=replace(observation.completed, process_start_ticks=43),
        )
    with pytest.raises(ValueError, match="regressed HWM"):
        replace(
            observation,
            completed=_sample(resident=10 * 1024, peak=19 * 1024),
        )


@pytest.mark.skipif(sys.platform != "linux", reason="live procfs contract is Linux-only")
def test_live_linux_procfs_sample_has_current_process_identity():
    sample = sample_linux_process_memory()

    assert sample.process_id == os.getpid()
    assert sample.lifetime_peak_resident_bytes >= sample.resident_bytes > 0

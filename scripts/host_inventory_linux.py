"""Read-only inventory of the Linux environment in which this script already runs.

Run inside an already running WSL distro: python3 scripts/host_inventory_linux.py
No Docker commands are invoked. Output is environment evidence, not approval.
"""

import json
import os
import platform
import subprocess
from pathlib import Path


def read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], stderr=subprocess.DEVNULL, text=True, timeout=10
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> None:
    stat = os.statvfs(".")
    status = git("status", "--porcelain")
    wsl_config = read("/etc/wsl.conf")
    output = {
        "purpose": "environment inventory only; no execution approval",
        "os_release": read("/etc/os-release"),
        "kernel": platform.release(),
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in (read("/proc/cpuinfo") or "").splitlines()
                if line.startswith("model name") and ":" in line
            ),
            None,
        ),
        "cpu_affinity_count": len(os.sched_getaffinity(0)),
        "memory": "\n".join(
            line
            for line in (read("/proc/meminfo") or "").splitlines()
            if line.startswith(("MemTotal:", "MemAvailable:"))
        ),
        "filesystem_type": subprocess.run(
            ["findmnt", "-n", "-o", "FSTYPE", "-T", "."],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or None,
        "available_bytes": stat.f_bavail * stat.f_frsize,
        "available_inodes": stat.f_favail,
        "psi": {name: read(f"/proc/pressure/{name}") for name in ("cpu", "memory", "io")},
        "wsl_config": "\n".join(
            line
            for line in (wsl_config or "").splitlines()
            if line.strip()
            and not line.lstrip().startswith("#")
            and (
                line.strip().startswith("[")
                or line.split("=", 1)[0].strip()
                in {
                    "systemd",
                    "enabled",
                    "mountFsTab",
                    "options",
                    "appendWindowsPath",
                    "generateResolvConf",
                    "generateHosts",
                }
            )
        )
        if wsl_config is not None
        else None,
        "git_head": git("rev-parse", "HEAD"),
        "git_dirty": None if status is None else bool(status),
        "docker_engine": None,
        "image_id": None,
        "remaining_resources": None,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

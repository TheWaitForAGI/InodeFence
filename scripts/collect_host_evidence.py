"""Collect bounded, read-only HOST evidence; observations never constitute qualification."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

MAX_BYTES = 1_000_000
TIMEOUT_SECONDS = 30


def collect(argv: list[str], directory: Path, name: str) -> dict[str, object]:
    started = datetime.now(UTC).isoformat()
    try:
        result = subprocess.run(argv, capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
        out, err = result.stdout, result.stderr
        code: int | None = result.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        out, err, code, timed_out = exc.stdout or b"", exc.stderr or b"", None, True
    except OSError as exc:
        out, err, code, timed_out = b"", str(exc).encode(), None, False
    truncated = len(out) > MAX_BYTES or len(err) > MAX_BYTES
    files: dict[str, str] = {}
    for suffix, content in (("stdout", out[:MAX_BYTES]), ("stderr", err[:MAX_BYTES])):
        path = directory / f"{name}.{suffix}"
        path.write_bytes(content)
        files[path.name] = hashlib.sha256(content).hexdigest()
    return {
        "argv": argv,
        "started_at_utc": started,
        "exit_code": code,
        "timeout": timed_out,
        "truncated": truncated,
        "files_sha256": files,
        "status": "measured" if code == 0 and not timed_out and not truncated else "UNKNOWN",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-id", choices=("HOST1", "HOST2"), required=True)
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument(
        "--output-path", type=Path, required=True, help="proposed experiment output"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=False, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    ps_source = (root / "scripts/host_inventory_extended.ps1").read_text(encoding="utf-8")
    ps_command = base64.b64encode(ps_source.encode("utf-16le")).decode("ascii")
    disk_path = args.output_path.resolve()
    while not disk_path.exists() and disk_path != disk_path.parent:
        disk_path = disk_path.parent
    commands = {
        "windows": [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            ps_command,
        ],
        "linux": ["python3", str(root / "scripts/host_inventory_linux.py")],
        "git_head": ["git", "rev-parse", "HEAD"],
        "git_status": ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        "docker_version": ["docker", "version", "--format", "{{json .}}"],
        "docker_info": ["docker", "info", "--format", "{{json .}}"],
        "docker_context": ["docker", "context", "show"],
        "docker_images": [
            "docker",
            "image",
            "inspect",
            "inodefence-node-tar-effect:7.5.2",
            "inodefence-controller:local",
            "inodefence-helper:local",
        ],
        "docker_containers": ["docker", "ps", "-a", "--no-trunc", "--format", "{{json .}}"],
        "docker_volumes": ["docker", "volume", "ls", "--format", "{{json .}}"],
        "host_processes": ["ps", "-eo", "pid,comm,pcpu,pmem"],
        "output_disk": ["df", "-B1", str(disk_path)],
        "wsl_version": ["wsl.exe", "--version"],
        "wsl_list": ["wsl.exe", "--list", "--verbose"],
        "docker_vm": [
            "wsl.exe",
            "-d",
            "docker-desktop",
            "-u",
            "root",
            "--",
            "sh",
            "-c",
            "cat /proc/meminfo; nproc; cat /proc/self/cgroup; "
            "cat /sys/fs/cgroup/cpuset.cpus.effective; "
            "df -B1 /mnt/docker-desktop-disk /tmp/docker-desktop-root/var/lib/docker",
        ],
    }
    records = {name: collect(cmd, args.output, name) for name, cmd in commands.items()}
    report = {
        "schema": "inodefence-host-collection-v1",
        "host_id": args.host_id,
        "collected_at_utc": datetime.now(UTC).isoformat(),
        "collector_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "windows_source_sha256": hashlib.sha256(ps_source.encode("utf-8")).hexdigest(),
        "experiment_output_declared": str(args.output_path),
        "output_exists_at_collection": args.output_path.exists(),
        "commands": records,
        "limitations": [
            "Raw observations are not authenticated and do not establish host qualification.",
            "Backing VHDX mapping and Windows restart protection require independent verification.",
        ],
        "host_qualified": "UNKNOWN",
        "configuration_freeze_eligible": "UNKNOWN",
    }
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    path = args.output / "collection.json"
    path.write_bytes(payload)
    print(f"{hashlib.sha256(payload).hexdigest()}  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

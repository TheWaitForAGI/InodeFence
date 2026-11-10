"""Verify raw collection integrity and conservative host checks; no authenticity claim."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def verify(
    directory: Path,
    collection_sha256: str,
    expected_sha: str,
    image_id: str,
    jobs: int,
    min_memory: int,
    min_disk: int,
) -> dict[str, Any]:
    issues: list[str] = []
    unknown: list[str] = []
    command_unknown: list[str] = []
    try:
        raw = (directory / "collection.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != collection_sha256:
            issues.append("collection manifest hash mismatch")
        report = json.loads(raw)
        commands = report["commands"]
        if report.get("schema") != "inodefence-host-collection-v1" or report.get("host_id") not in (
            "HOST1",
            "HOST2",
        ):
            raise ValueError("invalid collection identity")
        required = {
            "windows",
            "linux",
            "git_head",
            "git_status",
            "docker_version",
            "docker_info",
            "docker_context",
            "docker_images",
            "docker_containers",
            "docker_volumes",
            "host_processes",
            "output_disk",
            "wsl_version",
            "wsl_list",
            "docker_vm",
        }
        if not isinstance(commands, dict) or set(commands) != required:
            raise ValueError("missing or unexpected collection commands")
        for name, record in commands.items():
            if (
                record.get("exit_code") != 0
                or record.get("timeout") is not False
                or record.get("truncated") is not False
            ):
                command_unknown.append(f"{name}: command failed, timed out, or truncated")
            hashes = record.get("files_sha256")
            if not isinstance(hashes, dict) or set(hashes) != {f"{name}.stdout", f"{name}.stderr"}:
                raise ValueError(f"{name}: invalid file list")
            for filename, expected in hashes.items():
                if hashlib.sha256((directory / filename).read_bytes()).hexdigest() != expected:
                    issues.append(f"{filename}: hash mismatch")

        def read(name: str) -> str:
            return (directory / f"{name}.stdout").read_text(encoding="utf-8").strip()

        def usable(name: str) -> bool:
            record = commands[name]
            return (
                record.get("exit_code") == 0
                and record.get("timeout") is False
                and record.get("truncated") is False
            )

        if (
            usable("git_head")
            and usable("git_status")
            and (read("git_head") != expected_sha or read("git_status"))
        ):
            issues.append("checkout SHA or cleanliness mismatch")
        if usable("docker_images"):
            images = json.loads(read("docker_images"))
            if not isinstance(images, list) or not any(
                isinstance(image, dict)
                and image.get("Id") == image_id
                and "inodefence-node-tar-effect:7.5.2" in (image.get("RepoTags") or [])
                for image in images
            ):
                issues.append("required image ID not observed")
        if usable("docker_info"):
            info = json.loads(read("docker_info"))
            if type(info.get("NCPU")) is not int or info["NCPU"] < jobs:
                issues.append("Docker CPUs below jobs")
            if type(info.get("MemTotal")) is not int or info["MemTotal"] < min_memory:
                issues.append("Docker memory below minimum")
        if usable("output_disk"):
            lines = read("output_disk").splitlines()
            if len(lines) < 2 or int(lines[-1].split()[-3]) < min_disk:
                issues.append("output disk below minimum")
        if report.get("output_exists_at_collection") is not False:
            issues.append("output exists or collision status UNKNOWN")
        unknown.extend(
            (
                "automatic restart protection is not independently verified",
                "Docker backing VHDX and physical disk mapping not independently verified",
                "effective per-job cgroup and workload qualification not independently verified",
                "collection provenance is not authenticated and current state may differ",
            )
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        issues.append(f"invalid or missing evidence: {exc}")
    return {
        "inputs-consistent": "FAIL" if issues else ("UNKNOWN" if command_unknown else "PASS"),
        "host-qualified": "FAIL" if issues else "UNKNOWN",
        "configuration-freeze-eligible": "UNKNOWN",
        "issues": issues,
        "unknown": command_unknown + unknown,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--collection-sha256", required=True)
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--image-id", required=True)
    p.add_argument("--jobs", type=int, required=True)
    p.add_argument("--min-memory-bytes", type=int, required=True)
    p.add_argument("--min-disk-bytes", type=int, required=True)
    a = p.parse_args()
    if a.jobs < 1 or a.min_memory_bytes < 1 or a.min_disk_bytes < 1:
        p.error("jobs and minimum resources must be positive")
    result = verify(
        a.input,
        a.collection_sha256,
        a.expected_sha,
        a.image_id,
        a.jobs,
        a.min_memory_bytes,
        a.min_disk_bytes,
    )
    print(json.dumps(result, indent=2))
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

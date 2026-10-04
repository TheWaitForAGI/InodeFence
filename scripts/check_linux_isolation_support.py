"""Report Linux namespace prerequisites; never authorize target execution.

Fixed unshare/true probes create disposable namespaces, without fork, mounts,
network traffic, target invocation or experiment runtime creation. Exit 0 means
only that the five user-namespace creation probes succeeded. It does not
validate a filesystem view, credentials, network policy or descendant cleanup.
"""

import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from inodefence.provenance import capture_environment, capture_source

_PROBES = (
    ("user", ("--user", "--map-root-user")),
    ("user_mount", ("--user", "--map-root-user", "--mount")),
    ("user_network", ("--user", "--map-root-user", "--net")),
    ("user_pid", ("--user", "--map-root-user", "--pid")),
    ("user_mount_network_pid", ("--user", "--map-root-user", "--mount", "--net", "--pid")),
    ("mount", ("--mount",)),
    ("network", ("--net",)),
    ("pid", ("--pid",)),
)
_REQUIRED = frozenset(name for name, _ in _PROBES[:5])


def _read(path: str) -> dict:
    try:
        return {"value": Path(path).read_text().strip(), "error": None}
    except OSError as error:
        return {"value": None, "error": f"{type(error).__name__}: {error}"}


def _linux_facts() -> dict:
    import resource

    status = _read("/proc/self/status")
    fields = {}
    if status["value"] is not None:
        fields = dict(line.split(":", 1) for line in status["value"].splitlines() if ":" in line)
    try:
        cgroup_read_only = bool(os.statvfs("/sys/fs/cgroup").f_flag & os.ST_RDONLY)
        cgroup_error = None
    except OSError as error:
        cgroup_read_only = None
        cgroup_error = f"{type(error).__name__}: {error}"
    return {
        "uid": os.getuid(),
        "gid": os.getgid(),
        "process_status": {
            "fields": {
                name: fields[name].strip()
                for name in ("CapEff", "CapBnd", "NoNewPrivs", "Seccomp", "Seccomp_filters")
                if name in fields
            },
            "error": status["error"],
        },
        "max_user_namespaces": _read("/proc/sys/user/max_user_namespaces"),
        "unprivileged_userns_clone": _read("/proc/sys/kernel/unprivileged_userns_clone"),
        "cgroup_membership": _read("/proc/self/cgroup"),
        "cgroup_mount": {"read_only": cgroup_read_only, "error": cgroup_error},
        "observed_resource_limits": {
            name: resource.getrlimit(kind)
            for name, kind in (
                ("address_space", resource.RLIMIT_AS),
                ("processes_per_real_uid", resource.RLIMIT_NPROC),
                ("file_size", resource.RLIMIT_FSIZE),
                ("open_files", resource.RLIMIT_NOFILE),
            )
        },
    }


def collect_support() -> dict:
    """Read facts and attempt primitives; no result is an isolation certificate."""
    linux = platform.system() == "Linux"
    tools = {
        name: shutil.which(name) for name in ("unshare", "true", "setpriv", "prlimit", "bwrap")
    }
    unshare, true = tools["unshare"], tools["true"]
    probes = []
    for name, flags in _PROBES:
        command = (unshare, *flags, true)
        record = {
            "name": name,
            "command": command,
            "status": "unsupported_platform" if not linux else "missing_tool",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": None,
        }
        if linux and unshare is not None and true is not None:
            # No fork: unshare replaces itself with the fixed true executable.
            # subprocess.run kills and waits for this direct process on timeout.
            try:
                completed = subprocess.run(
                    (unshare, *flags, true),
                    capture_output=True,
                    text=True,
                    errors="surrogateescape",
                    timeout=5.0,
                    check=False,
                    env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                )
                record.update(
                    status="created" if completed.returncode == 0 else "denied_or_failed",
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                record.update(status="probe_error", error=f"{type(error).__name__}: {error}")
        probes.append(record)
    available = all(probe["status"] == "created" for probe in probes if probe["name"] in _REQUIRED)
    return {
        "schema_version": 1,
        "assessment_scope": "namespace-prerequisites-only",
        "namespace_creation": "unsupported_platform"
        if not linux
        else "available"
        if available
        else "unavailable",
        "source": asdict(capture_source()),
        "environment": asdict(capture_environment()),
        "tools": tools,
        "linux_facts": _linux_facts() if linux else None,
        "namespace_probes": probes,
    }


def main() -> int:
    report = collect_support()
    print(
        json.dumps(
            report, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        )
    )
    return 0 if report["namespace_creation"] == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())

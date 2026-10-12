"""Collect benign evidence for node-tar entry-completion observation candidates.

This is a qualification probe, not a target adapter or security benchmark. It
uses only disposable runtime sandboxes and refuses to overwrite raw evidence.
"""

import argparse
import ctypes
import hashlib
import json
import os
import platform
import select
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.runtime import disposable_sandbox

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/node-tar/node_modules/tar"
PROBE = ROOT / "tools/node-tar/entry-timing-probe.cjs"
WORKER = ROOT / "src/inodefence/targets/_node_worker.cjs"
LOCK = ROOT / "tools/node-tar/package-lock.json"
EXPECTED_NODE = "22.22.0"
EXPECTED_TAR = "7.5.22"
EXPERIMENT_ID = "node-transition-observation-qualification-v2"

IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_ISDIR = 0x40000000
INOTIFY_MASK = (
    IN_ATTRIB
    | IN_CLOSE_WRITE
    | IN_MOVED_FROM
    | IN_MOVED_TO
    | IN_CREATE
    | IN_DELETE
    | IN_DELETE_SELF
    | IN_MOVE_SELF
)
INOTIFY_EVENT = struct.Struct("iIII")
INOTIFY_NAMES = (
    (IN_ATTRIB, "attrib"),
    (IN_CLOSE_WRITE, "close_write"),
    (IN_MOVED_FROM, "moved_from"),
    (IN_MOVED_TO, "moved_to"),
    (IN_CREATE, "create"),
    (IN_DELETE, "delete"),
    (IN_DELETE_SELF, "delete_self"),
    (IN_MOVE_SELF, "move_self"),
    (IN_Q_OVERFLOW, "queue_overflow"),
    (IN_IGNORED, "ignored"),
    (IN_ISDIR, "is_directory"),
)


def qualification_case() -> ArchiveCase:
    """Exercise regular, directory, hardlink, symlink and replacement effects."""
    return ArchiveCase(
        (
            ArchiveEntry("regular", EntryType.REGULAR, content=b"first"),
            ArchiveEntry("dir", EntryType.DIRECTORY, mode=0o755),
            ArchiveEntry("hard", EntryType.HARDLINK, link_target="regular"),
            ArchiveEntry("sym", EntryType.SYMLINK, link_target="regular", mode=0o777),
            ArchiveEntry("regular", EntryType.REGULAR, content=b"second"),
        )
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _command_version(command: tuple[str, ...]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)
    return (completed.stdout or completed.stderr).strip().splitlines()[0]


def _run(command: tuple[str, ...], timeout: float) -> dict[str, Any]:
    start = perf_counter_ns()
    completed = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=timeout
    )
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_ns": perf_counter_ns() - start,
    }


def _object_snapshot(path: Path, relative: str) -> dict[str, Any]:
    before = path.lstat()
    kind = (
        "regular"
        if stat.S_ISREG(before.st_mode)
        else "directory"
        if stat.S_ISDIR(before.st_mode)
        else "symlink"
        if stat.S_ISLNK(before.st_mode)
        else "other"
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if kind == "regular" else None
    after = path.lstat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise RuntimeError(f"object changed during qualification snapshot: {relative}")
    return {
        "path": relative,
        "kind": kind,
        "dev": before.st_dev,
        "ino": before.st_ino,
        "nlink": before.st_nlink,
        "mode": stat.S_IMODE(before.st_mode),
        "size": before.st_size,
        "uid": before.st_uid,
        "gid": before.st_gid,
        "mtime_ns": before.st_mtime_ns,
        "ctime_ns": before.st_ctime_ns,
        "link_target": os.readlink(path) if kind == "symlink" else None,
        "content_sha256": digest,
    }


def _snapshot_tree(root: Path) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        objects.append(_object_snapshot(path, relative))
    return objects


def _semantic_snapshot(snapshot: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ("path", "kind", "nlink", "mode", "size", "link_target", "content_sha256")
    return [{field: obj[field] for field in fields} for obj in snapshot]


def _write_archive(path: Path, case: ArchiveCase) -> str:
    archive = build_tar(case)
    path.write_bytes(archive)
    return hashlib.sha256(archive).hexdigest()


def _node_worker_command(node: str, archive: Path, destination: Path) -> tuple[str, ...]:
    return (
        node,
        str(WORKER),
        str(MODULE),
        str(archive),
        str(destination),
        EXPECTED_NODE,
        EXPECTED_TAR,
    )


def _public_event_runs(
    node: str, case: ArchiveCase, mode: str, repetitions: int, timeout: float
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for repetition in range(repetitions):
        with disposable_sandbox() as sandbox:
            archive_sha256 = _write_archive(sandbox.archive_path, case)
            result = _run(
                (
                    node,
                    str(PROBE),
                    str(MODULE),
                    str(sandbox.archive_path),
                    str(sandbox.extraction_root),
                    mode,
                ),
                timeout,
            )
            if result["returncode"] != 0:
                raise RuntimeError(f"public-event probe failed: {result['stderr']}")
            runs.append(
                {
                    "repetition": repetition,
                    "archive_sha256": archive_sha256,
                    "duration_ns": result["duration_ns"],
                    "events": json.loads(result["stdout"]),
                }
            )
    return runs


def _event_state(event: dict[str, Any]) -> str:
    observed = event["observed"]
    if not observed["exists"]:
        return "absent"
    if observed.get("kind") == "regular" and observed.get("size") == 0:
        return "empty_regular"
    return "materialized"


def _summarize_public_events(runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, dict[str, int]] = {}
    for run in runs:
        for event in run["events"]:
            if event["phase"] not in {"on_read_entry", "entry_end"}:
                continue
            key = f"{event['entry_index']}:{event['phase']}"
            state = _event_state(event)
            summary.setdefault(key, {}).setdefault(state, 0)
            summary[key][state] += 1
    return summary


class _InotifyMonitor:
    def __init__(self, root: Path):
        self.root = root
        self.events: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._libc = ctypes.CDLL(None, use_errno=True)
        self._libc.inotify_init1.argtypes = [ctypes.c_int]
        self._libc.inotify_init1.restype = ctypes.c_int
        self._libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self._libc.inotify_add_watch.restype = ctypes.c_int
        self._fd = self._libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
        if self._fd < 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))
        self._watch = self._libc.inotify_add_watch(
            self._fd, os.fsencode(root), ctypes.c_uint32(INOTIFY_MASK)
        )
        if self._watch < 0:
            errno = ctypes.get_errno()
            os.close(self._fd)
            raise OSError(errno, os.strerror(errno))
        self._thread = threading.Thread(target=self._collect, name="inotify-qualification")

    def __enter__(self) -> "_InotifyMonitor":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError("inotify qualification monitor did not stop")
        os.close(self._fd)

    def _collect(self) -> None:
        while not self._stop.is_set():
            readable, _, _ = select.select((self._fd,), (), (), 0.01)
            if not readable:
                continue
            self._drain()
        self._drain()

    def _drain(self) -> None:
        while True:
            try:
                data = os.read(self._fd, 64 * 1024)
            except BlockingIOError:
                return
            if not data:
                return
            offset = 0
            while offset < len(data):
                watch, mask, cookie, name_length = INOTIFY_EVENT.unpack_from(data, offset)
                offset += INOTIFY_EVENT.size
                raw_name = data[offset : offset + name_length]
                offset += name_length
                name = raw_name.rstrip(b"\0").decode("utf-8", "surrogateescape")
                event: dict[str, Any] = {
                    "receipt_monotonic_ns": perf_counter_ns(),
                    "watch": watch,
                    "mask": mask,
                    "mask_names": [label for bit, label in INOTIFY_NAMES if mask & bit],
                    "cookie": cookie,
                    "name": name,
                }
                try:
                    event["receipt_snapshot"] = _snapshot_tree(self.root)
                    event["snapshot_complete"] = True
                except (FileNotFoundError, RuntimeError, OSError) as error:
                    event["receipt_snapshot"] = None
                    event["snapshot_complete"] = False
                    event["snapshot_error"] = f"{type(error).__name__}: {error}"
                self.events.append(event)


def _inotify_runs(
    node: str, case: ArchiveCase, repetitions: int, timeout: float
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for repetition in range(repetitions):
        with disposable_sandbox() as sandbox:
            archive_sha256 = _write_archive(sandbox.archive_path, case)
            with _InotifyMonitor(sandbox.extraction_root) as monitor:
                result = _run(
                    _node_worker_command(node, sandbox.archive_path, sandbox.extraction_root),
                    timeout,
                )
            if result["returncode"] != 0:
                raise RuntimeError(f"inotify target run failed: {result['stderr']}")
            runs.append(
                {
                    "repetition": repetition,
                    "archive_sha256": archive_sha256,
                    "duration_ns": result["duration_ns"],
                    "events": monitor.events,
                    "queue_overflow": any(
                        event["mask"] & IN_Q_OVERFLOW for event in monitor.events
                    ),
                    "final_snapshot": _snapshot_tree(sandbox.extraction_root),
                }
            )
    return runs


def _baseline_runs(
    node: str, case: ArchiveCase, repetitions: int, timeout: float
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for repetition in range(repetitions):
        with disposable_sandbox() as sandbox:
            archive_sha256 = _write_archive(sandbox.archive_path, case)
            result = _run(
                _node_worker_command(node, sandbox.archive_path, sandbox.extraction_root), timeout
            )
            if result["returncode"] != 0:
                raise RuntimeError(f"baseline target run failed: {result['stderr']}")
            runs.append(
                {
                    "repetition": repetition,
                    "archive_sha256": archive_sha256,
                    "duration_ns": result["duration_ns"],
                    "final_snapshot": _snapshot_tree(sandbox.extraction_root),
                }
            )
    return runs


def _strace_runs(
    strace: str, node: str, case: ArchiveCase, repetitions: int, timeout: float
) -> list[dict[str, Any]]:
    traced_syscalls = (
        "openat,close,write,pwrite64,ftruncate,fsync,fdatasync,link,linkat,symlink,"
        "symlinkat,unlink,unlinkat,mkdir,mkdirat,chmod,fchmod,fchmodat,chown,fchown,"
        "fchownat,utime,utimes,futimesat,utimensat"
    )
    runs: list[dict[str, Any]] = []
    for repetition in range(repetitions):
        with disposable_sandbox() as sandbox:
            archive_sha256 = _write_archive(sandbox.archive_path, case)
            trace_path = sandbox.root / "archive" / "strace.log"
            worker = _node_worker_command(node, sandbox.archive_path, sandbox.extraction_root)
            command = (
                strace,
                "-f",
                "-qq",
                "-ttt",
                "-T",
                "-yy",
                "-s",
                "4096",
                "-e",
                f"trace={traced_syscalls}",
                "-o",
                str(trace_path),
                *worker,
            )
            result = _run(command, timeout)
            if result["returncode"] != 0:
                raise RuntimeError(f"strace target run failed: {result['stderr']}")
            trace = trace_path.read_text(encoding="utf-8", errors="surrogateescape")
            root_text = str(sandbox.extraction_root)
            selected = [line for line in trace.splitlines() if root_text in line]
            runs.append(
                {
                    "repetition": repetition,
                    "archive_sha256": archive_sha256,
                    "duration_ns": result["duration_ns"],
                    "trace_sha256": hashlib.sha256(trace.encode("utf-8")).hexdigest(),
                    "trace_lines": trace.splitlines(),
                    "extraction_path_lines": selected,
                    "final_snapshot": _snapshot_tree(sandbox.extraction_root),
                }
            )
    return runs


def _straced_sync_public_probe(
    strace: str, node: str, case: ArchiveCase, timeout: float
) -> dict[str, Any]:
    traced_syscalls = (
        "openat,close,read,write,pwrite64,ftruncate,link,linkat,symlink,symlinkat,"
        "unlink,unlinkat,mkdir,mkdirat,chmod,fchmod,fchmodat,chown,fchown,fchownat,"
        "utime,utimes,futimesat,utimensat"
    )
    with disposable_sandbox() as sandbox:
        archive_sha256 = _write_archive(sandbox.archive_path, case)
        trace_path = sandbox.root / "archive" / "sync-public-strace.log"
        command = (
            strace,
            "-f",
            "-qq",
            "-ttt",
            "-T",
            "-yy",
            "-s",
            "4096",
            "-e",
            f"trace={traced_syscalls}",
            "-o",
            str(trace_path),
            node,
            str(PROBE),
            str(MODULE),
            str(sandbox.archive_path),
            str(sandbox.extraction_root),
            "sync",
        )
        result = _run(command, timeout)
        if result["returncode"] != 0:
            raise RuntimeError(f"straced sync public-event probe failed: {result['stderr']}")
        trace = trace_path.read_text(encoding="utf-8", errors="surrogateescape")
        root_text = str(sandbox.extraction_root)
        return {
            "archive_sha256": archive_sha256,
            "duration_ns": result["duration_ns"],
            "events": json.loads(result["stdout"]),
            "trace_sha256": hashlib.sha256(trace.encode("utf-8")).hexdigest(),
            "extraction_path_lines": [line for line in trace.splitlines() if root_text in line],
            "final_snapshot": _snapshot_tree(sandbox.extraction_root),
        }


def _prefix_replay_runs(
    node: str, case: ArchiveCase, repetitions: int, timeout: float
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for repetition in range(repetitions):
        prefixes: list[dict[str, Any]] = []
        for length in range(1, len(case.entries) + 1):
            prefix = ArchiveCase(case.entries[:length])
            with disposable_sandbox() as sandbox:
                archive_sha256 = _write_archive(sandbox.archive_path, prefix)
                result = _run(
                    _node_worker_command(node, sandbox.archive_path, sandbox.extraction_root),
                    timeout,
                )
                if result["returncode"] != 0:
                    raise RuntimeError(f"prefix replay failed: {result['stderr']}")
                prefixes.append(
                    {
                        "prefix_length": length,
                        "case_id": prefix.case_id,
                        "archive_sha256": archive_sha256,
                        "duration_ns": result["duration_ns"],
                        "final_snapshot": _snapshot_tree(sandbox.extraction_root),
                    }
                )
        runs.append({"repetition": repetition, "prefixes": prefixes})
    return runs


def _python_reference_candidate(case: ArchiveCase) -> dict[str, Any]:
    with disposable_sandbox() as sandbox:
        archive_sha256 = _write_archive(sandbox.archive_path, case)
        checkpoints: list[dict[str, Any]] = []
        with tarfile.open(sandbox.archive_path, mode="r:") as archive:
            archive.errorlevel = 2
            for ordinal, member in enumerate(archive):
                archive.extract(member, sandbox.extraction_root, filter="data")
                checkpoints.append(
                    {
                        "ordinal": ordinal,
                        "path": member.name,
                        "type": member.type.decode("ascii", "replace"),
                        "snapshot_after_extract_return": _snapshot_tree(sandbox.extraction_root),
                    }
                )
        member_loop_final = _snapshot_tree(sandbox.extraction_root)

    with disposable_sandbox() as sandbox:
        _write_archive(sandbox.archive_path, case)
        with tarfile.open(sandbox.archive_path, mode="r:") as archive:
            archive.errorlevel = 2
            archive.extractall(sandbox.extraction_root, filter="data")
        extractall_final = _snapshot_tree(sandbox.extraction_root)

    directory_case = ArchiveCase(
        (
            ArchiveEntry("locked", EntryType.DIRECTORY, mode=0o555),
            ArchiveEntry("locked/child", EntryType.REGULAR, content=b"child"),
        )
    )
    with disposable_sandbox() as sandbox:
        directory_archive_sha256 = _write_archive(sandbox.archive_path, directory_case)
        per_member_error = None
        per_member_completed = 0
        try:
            with tarfile.open(sandbox.archive_path, mode="r:") as archive:
                archive.errorlevel = 2
                for member in archive:
                    archive.extract(member, sandbox.extraction_root, filter="data")
                    per_member_completed += 1
        except (OSError, tarfile.TarError) as error:
            per_member_error = f"{type(error).__name__}: {error}"
        directory_member_loop_final = _snapshot_tree(sandbox.extraction_root)

    with disposable_sandbox() as sandbox:
        _write_archive(sandbox.archive_path, directory_case)
        extractall_error = None
        try:
            with tarfile.open(sandbox.archive_path, mode="r:") as archive:
                archive.errorlevel = 2
                archive.extractall(sandbox.extraction_root, filter="data")
        except (OSError, tarfile.TarError) as error:
            extractall_error = f"{type(error).__name__}: {error}"
        directory_extractall_final = _snapshot_tree(sandbox.extraction_root)

    member_directory = next(obj for obj in directory_member_loop_final if obj["path"] == "locked")
    extractall_directory = next(
        obj for obj in directory_extractall_final if obj["path"] == "locked"
    )

    return {
        "archive_sha256": archive_sha256,
        "checkpoints": checkpoints,
        "member_loop_final": member_loop_final,
        "extractall_final": extractall_final,
        "fixture_final_semantics_equal": _semantic_snapshot(member_loop_final)
        == _semantic_snapshot(extractall_final),
        "directory_deferral_counterexample": {
            "case_id": directory_case.case_id,
            "archive_sha256": directory_archive_sha256,
            "entries": [
                {"path": entry.path, "type": entry.entry_type.value, "mode": entry.mode}
                for entry in directory_case.entries
            ],
            "per_member_completed_entries": per_member_completed,
            "per_member_error": per_member_error,
            "per_member_final": directory_member_loop_final,
            "extractall_error": extractall_error,
            "extractall_final": directory_extractall_final,
            "directory_mtime_equal": member_directory["mtime_ns"]
            == extractall_directory["mtime_ns"],
        },
        "scope": (
            "The public per-member extract return is synchronous for this distinct invocation; "
            "it is not evidence of equivalence to extractall or node-tar."
        ),
    }


def _git_source() -> dict[str, Any]:
    revision = _command_version(("git", "rev-parse", "HEAD"))
    status = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    return {"revision": revision, "dirty": bool(status), "status_porcelain": status.splitlines()}


def _environment(node: str, strace: str) -> dict[str, Any]:
    findmnt = shutil.which("findmnt")
    mount = None
    if findmnt is not None:
        mount_result = _run(
            (findmnt, "-J", "-T", "/var/lib/inodefence", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"),
            10,
        )
        mount = {
            "returncode": mount_result["returncode"],
            "stdout": mount_result["stdout"],
            "stderr": mount_result["stderr"],
        }
    protected_hardlinks = Path("/proc/sys/fs/protected_hardlinks")
    process_umask = os.umask(0)
    os.umask(process_umask)
    process_status: dict[str, str] = {}
    status_path = Path("/proc/self/status")
    if status_path.exists():
        for line in status_path.read_text().splitlines():
            name, separator, value = line.partition(":")
            if separator and name in {"CapEff", "NoNewPrivs", "Seccomp"}:
                process_status[name] = value.strip()
    return {
        "platform": platform.system(),
        "kernel_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "python_executable": os.path.realpath(sys.executable),
        "node_version": _command_version((node, "--version")),
        "strace_version": _command_version((strace, "--version")),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "umask": oct(process_umask),
        "protected_hardlinks": protected_hardlinks.read_text().strip()
        if protected_hardlinks.exists()
        else None,
        "process_status": process_status,
        "runtime_mount": mount,
    }


def _validate_prerequisites(node: str, strace: str) -> dict[str, Any]:
    package = json.loads((MODULE / "package.json").read_text())
    node_version = _command_version((node, "--version")).removeprefix("v")
    tar_version = package["version"]
    if node_version != EXPECTED_NODE or tar_version != EXPECTED_TAR:
        raise RuntimeError(
            f"qualification requires node {EXPECTED_NODE}/tar {EXPECTED_TAR}, got "
            f"{node_version}/{tar_version}"
        )
    return {
        "target_id": "node-tar-strict",
        "node_version": node_version,
        "tar_version": tar_version,
        "module_package_sha256": _sha256(MODULE / "package.json"),
        "package_lock_sha256": _sha256(LOCK),
        "worker_sha256": _sha256(WORKER),
        "public_probe_sha256": _sha256(PROBE),
        "unpack_commonjs_sha256": _sha256(MODULE / "dist/commonjs/unpack.js"),
        "parse_commonjs_sha256": _sha256(MODULE / "dist/commonjs/parse.js"),
        "strace_path": strace,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.repetitions <= 0:
        raise ValueError("repetitions must be positive")
    if args.timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {args.output}")
    node = shutil.which("node")
    strace = shutil.which("strace")
    if node is None or strace is None:
        raise RuntimeError("node and strace are required")

    source = _git_source()
    target = _validate_prerequisites(node, strace)
    environment = _environment(node, strace)
    case = qualification_case()
    archive = build_tar(case)
    started = datetime.now(UTC)

    async_runs = _public_event_runs(node, case, "async", args.repetitions, args.timeout_seconds)
    sync_runs = _public_event_runs(node, case, "sync", args.repetitions, args.timeout_seconds)
    baseline_runs = _baseline_runs(node, case, args.repetitions, args.timeout_seconds)
    inotify_runs = _inotify_runs(node, case, args.repetitions, args.timeout_seconds)
    strace_runs = _strace_runs(strace, node, case, args.repetitions, args.timeout_seconds)
    sync_public_trace = _straced_sync_public_probe(strace, node, case, args.timeout_seconds)
    prefix_runs = _prefix_replay_runs(node, case, args.repetitions, args.timeout_seconds)
    python_candidate = _python_reference_candidate(case)

    evidence = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "evidence_tier": "RAW_ONLY",
        "started_at_utc": started.isoformat(),
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "source": source,
        "environment": environment,
        "target": target,
        "config": {
            "repetitions": args.repetitions,
            "timeout_seconds": args.timeout_seconds,
            "runtime_root": "/var/lib/inodefence",
            "fixture_case_id": case.case_id,
            "fixture_archive_sha256": hashlib.sha256(archive).hexdigest(),
            "fixture_builder_format": BUILDER_FORMAT,
            "fixture_entries": [
                {
                    "ordinal": ordinal,
                    "path": entry.path,
                    "type": entry.entry_type.value,
                    "link_target": entry.link_target,
                    "content_sha256": hashlib.sha256(entry.content).hexdigest()
                    if entry.content
                    else None,
                }
                for ordinal, entry in enumerate(case.entries)
            ],
        },
        "candidates": {
            "node_tar_public_async": {
                "runs": async_runs,
                "mechanical_summary": _summarize_public_events(async_runs),
            },
            "node_tar_public_sync": {
                "runs": sync_runs,
                "mechanical_summary": _summarize_public_events(sync_runs),
                "straced_run": sync_public_trace,
                "target_behavior_change": (
                    "sets upstream sync=true instead of the pinned adapter default"
                ),
            },
            "linux_inotify": {
                "watch_mask": INOTIFY_MASK,
                "watch_scope": "extraction root immediate children; fixture has no nested effects",
                "runs": inotify_runs,
            },
            "linux_strace": {
                "baseline_runs": baseline_runs,
                "traced_runs": strace_runs,
                "trace_semantics": (
                    "syscall return evidence and offline ordering; no entry identity or atomic "
                    "filesystem checkpoint is inferred"
                ),
            },
            "fresh_process_prefix_replay": {
                "runs": prefix_runs,
                "semantics": (
                    "final states of independently extracted archive prefixes, not checkpoints "
                    "from one full extraction"
                ),
            },
            "python_tarfile_per_member_reference": python_candidate,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(evidence, sort_keys=True, indent=2) + "\n").encode()
    with args.output.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    print(
        json.dumps(
            {
                "experiment_id": EXPERIMENT_ID,
                "output": str(args.output),
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "bytes": len(encoded),
                "repetitions": args.repetitions,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Collect benign evidence for libarchive write-disk entry boundaries.

This qualification probe evaluates a separately declared reference target. It
does not add a native adapter, run a fuzzing campaign or produce security verdicts.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.runtime import disposable_sandbox

ROOT = Path(__file__).resolve().parents[1]
PROBE_SOURCE = ROOT / "tools/libarchive/entry-boundary-probe.c"
EXPECTED_LIBARCHIVE_PACKAGE = "3.7.2-2ubuntu0.9"
EXPERIMENT_ID = "libarchive-entry-boundary-qualification-v1"
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")


def qualification_cases() -> dict[str, ArchiveCase]:
    """Return fixed benign cases for links, replacement and directory deferral."""
    return {
        "mixed-effects": ArchiveCase(
            (
                ArchiveEntry("regular", EntryType.REGULAR, content=b"first"),
                ArchiveEntry("dir", EntryType.DIRECTORY, mode=0o755),
                ArchiveEntry("hard", EntryType.HARDLINK, link_target="regular"),
                ArchiveEntry("sym", EntryType.SYMLINK, link_target="regular", mode=0o777),
                ArchiveEntry("regular", EntryType.REGULAR, content=b"second"),
            )
        ),
        "directory-child": ArchiveCase(
            (
                ArchiveEntry("locked", EntryType.DIRECTORY, mode=0o555),
                ArchiveEntry("locked/child", EntryType.REGULAR, content=b"child"),
            )
        ),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _command_version(command: tuple[str, ...]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)
    return (completed.stdout or completed.stderr).strip().splitlines()[0]


def _run(command: tuple[str, ...], timeout: float) -> dict[str, Any]:
    start = perf_counter_ns()
    try:
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as error:
        return {
            "command": list(command),
            "returncode": None,
            "stdout": error.stdout or "",
            "stderr": error.stderr or "",
            "timed_out": True,
            "duration_ns": perf_counter_ns() - start,
        }
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "timed_out": False,
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


def _snapshot_tree(root: Path) -> dict[str, Any]:
    try:
        objects = [
            _object_snapshot(path, path.relative_to(root).as_posix())
            for path in sorted(root.rglob("*"))
        ]
    except (FileNotFoundError, OSError, RuntimeError) as error:
        return {
            "complete": False,
            "objects": None,
            "error": f"{type(error).__name__}: {error}",
        }
    return {"complete": True, "objects": objects, "error": None}


def _semantic_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not snapshot["complete"]:
        return None
    fields = ("path", "kind", "nlink", "mode", "size", "link_target", "content_sha256")
    return [{field: obj[field] for field in fields} for obj in snapshot["objects"]]


def _write_archive(path: Path, case: ArchiveCase) -> str:
    archive = build_tar(case)
    path.write_bytes(archive)
    return hashlib.sha256(archive).hexdigest()


def _compile_probe(cc: str, output: Path) -> dict[str, Any]:
    command = (
        cc,
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        str(PROBE_SOURCE),
        "-larchive",
        "-o",
        str(output),
    )
    result = _run(command, 30)
    if result["timed_out"] or result["returncode"] != 0:
        raise RuntimeError(f"probe compilation failed: {result['stderr']}")
    return {
        "command": list(command),
        "duration_ns": result["duration_ns"],
        "binary_sha256": _sha256(output),
    }


def _parse_markers(stderr: str) -> dict[str, Any]:
    version = None
    boundaries: list[dict[str, Any]] = []
    before_close = None
    after_close = None
    unexpected: list[str] = []
    for line in stderr.splitlines():
        fields = line.split("\t")
        if fields[0] == "LIBARCHIVE" and len(fields) == 3:
            version = {"string": fields[1], "version_number": int(fields[2])}
        elif fields[0] == "BOUNDARY" and len(fields) == 3:
            boundaries.append({"ordinal": int(fields[1]), "path": fields[2]})
        elif fields[0] == "BEFORE_CLOSE" and len(fields) == 2:
            before_close = int(fields[1])
        elif fields[0] == "AFTER_CLOSE" and len(fields) == 2:
            after_close = int(fields[1])
        else:
            unexpected.append(line)
    return {
        "version": version,
        "boundaries": boundaries,
        "before_close_entry_count": before_close,
        "after_close_entry_count": after_close,
        "unexpected_lines": unexpected,
    }


def _deferred_directory_effects(case: ArchiveCase, trace_lines: list[str]) -> list[dict[str, Any]]:
    before_close = next(
        (index for index, line in enumerate(trace_lines) if "BEFORE_CLOSE\\t" in line),
        None,
    )
    after_close = next(
        (index for index, line in enumerate(trace_lines) if "AFTER_CLOSE\\t" in line),
        None,
    )
    effects: list[dict[str, Any]] = []
    if before_close is None or after_close is None:
        return effects
    effect_operations = ("utimensat(", "chmod(", "fchmod(", "fchmodat(")
    for ordinal, entry in enumerate(case.entries):
        if entry.entry_type != EntryType.DIRECTORY:
            continue
        boundary_token = f"BOUNDARY\\t{ordinal}\\t{entry.path}\\n"
        boundary = next(
            (index for index, line in enumerate(trace_lines) if boundary_token in line),
            None,
        )
        path_token = f"/extract/{entry.path}>"
        lines = [
            line
            for line in trace_lines[before_close + 1 : after_close]
            if path_token in line and any(operation in line for operation in effect_operations)
        ]
        effects.append(
            {
                "ordinal": ordinal,
                "path": entry.path,
                "boundary_seen_before_close": boundary is not None and boundary < before_close,
                "metadata_lines_after_before_close": lines,
            }
        )
    return effects


def _baseline_runs(
    binary: Path,
    case: ArchiveCase,
    repetitions: int,
    timeout: float,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for repetition in range(repetitions):
        with disposable_sandbox() as sandbox:
            archive_sha256 = _write_archive(sandbox.archive_path, case)
            result = _run(
                (
                    str(binary),
                    str(sandbox.archive_path),
                    str(sandbox.extraction_root),
                    "quiet",
                ),
                timeout,
            )
            runs.append(
                {
                    "repetition": repetition,
                    "archive_sha256": archive_sha256,
                    "returncode": result["returncode"],
                    "timed_out": result["timed_out"],
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "duration_ns": result["duration_ns"],
                    "final_snapshot": _snapshot_tree(sandbox.extraction_root),
                }
            )
    return runs


def _traced_runs(
    strace: str,
    binary: Path,
    case: ArchiveCase,
    repetitions: int,
    timeout: float,
) -> list[dict[str, Any]]:
    traced_syscalls = (
        "openat,close,read,write,writev,pwrite64,ftruncate,link,linkat,symlink,"
        "symlinkat,unlink,unlinkat,mkdir,mkdirat,rename,renameat,renameat2,chmod,"
        "fchmod,fchmodat,utime,utimes,futimesat,utimensat"
    )
    runs: list[dict[str, Any]] = []
    for repetition in range(repetitions):
        with disposable_sandbox() as sandbox:
            archive_sha256 = _write_archive(sandbox.archive_path, case)
            trace_path = sandbox.root / "archive" / "libarchive-strace.log"
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
                str(binary),
                str(sandbox.archive_path),
                str(sandbox.extraction_root),
            )
            result = _run(command, timeout)
            trace = (
                trace_path.read_text(encoding="utf-8", errors="surrogateescape")
                if trace_path.exists()
                else ""
            )
            root_text = str(sandbox.extraction_root)
            selected = [
                line
                for line in trace.splitlines()
                if root_text in line
                or "BOUNDARY\\t" in line
                or "LIBARCHIVE\\t" in line
                or "BEFORE_CLOSE\\t" in line
                or "AFTER_CLOSE\\t" in line
            ]
            runs.append(
                {
                    "repetition": repetition,
                    "archive_sha256": archive_sha256,
                    "returncode": result["returncode"],
                    "timed_out": result["timed_out"],
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "duration_ns": result["duration_ns"],
                    "markers": _parse_markers(result["stderr"]),
                    "trace_sha256": hashlib.sha256(trace.encode()).hexdigest(),
                    "relevant_trace_lines": selected,
                    "deferred_directory_effects": _deferred_directory_effects(case, selected),
                    "final_snapshot": _snapshot_tree(sandbox.extraction_root),
                }
            )
    return runs


def _case_summary(
    case: ArchiveCase,
    baseline_runs: list[dict[str, Any]],
    traced_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = [
        {"ordinal": ordinal, "path": entry.path} for ordinal, entry in enumerate(case.entries)
    ]
    baseline_success = sum(run["returncode"] == 0 and not run["timed_out"] for run in baseline_runs)
    traced_success = sum(run["returncode"] == 0 and not run["timed_out"] for run in traced_runs)
    marker_matches = sum(run["markers"]["boundaries"] == expected for run in traced_runs)
    baseline_semantics = [_semantic_snapshot(run["final_snapshot"]) for run in baseline_runs]
    traced_semantics = [_semantic_snapshot(run["final_snapshot"]) for run in traced_runs]
    semantic_variants = {
        json.dumps(value, sort_keys=True, separators=(",", ":"))
        for value in baseline_semantics + traced_semantics
    }
    directory_deferred_effect_runs: dict[str, int] = {}
    for ordinal, entry in enumerate(case.entries):
        if entry.entry_type != EntryType.DIRECTORY:
            continue
        key = f"{ordinal}:{entry.path}"
        directory_deferred_effect_runs[key] = sum(
            any(
                effect["ordinal"] == ordinal
                and effect["boundary_seen_before_close"]
                and effect["metadata_lines_after_before_close"]
                for effect in run["deferred_directory_effects"]
            )
            for run in traced_runs
        )
    return {
        "expected_boundaries": expected,
        "baseline_successes": baseline_success,
        "traced_successes": traced_success,
        "exact_marker_matches": marker_matches,
        "final_semantic_variant_count": len(semantic_variants),
        "directory_deferred_effect_runs": directory_deferred_effect_runs,
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


def _package_version(name: str) -> str:
    return _command_version(("dpkg-query", "--show", "--showformat=${Version}\n", name))


def _environment(cc: str, strace: str) -> dict[str, Any]:
    process_status: dict[str, str] = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        name, separator, value = line.partition(":")
        if separator and name in {"CapEff", "NoNewPrivs", "Seccomp"}:
            process_status[name] = value.strip()
    process_umask = os.umask(0)
    os.umask(process_umask)
    return {
        "platform": platform.system(),
        "kernel_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "python_executable": os.path.realpath(sys.executable),
        "compiler_version": _command_version((cc, "--version")),
        "strace_version": _command_version((strace, "--version")),
        "libarchive_dev_package": _package_version("libarchive-dev"),
        "libarchive_runtime_package": _package_version("libarchive13t64"),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "umask": oct(process_umask),
        "process_status": process_status,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--base-image-id", required=True)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.repetitions <= 0:
        raise ValueError("repetitions must be positive")
    if args.timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    if not IMAGE_ID.fullmatch(args.image_id) or not IMAGE_ID.fullmatch(args.base_image_id):
        raise ValueError("image IDs must be sha256:<64 lowercase hex>")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {args.output}")

    cc = shutil.which("cc")
    strace = shutil.which("strace")
    if cc is None or strace is None:
        raise RuntimeError("cc and strace are required")
    environment = _environment(cc, strace)
    if (
        environment["libarchive_dev_package"] != EXPECTED_LIBARCHIVE_PACKAGE
        or environment["libarchive_runtime_package"] != EXPECTED_LIBARCHIVE_PACKAGE
    ):
        raise RuntimeError("unexpected libarchive package version")

    binary = Path("/tmp") / f"inodefence-libarchive-probe-{os.getpid()}"
    compile_evidence = _compile_probe(cc, binary)
    source = _git_source()
    cases = qualification_cases()
    started = datetime.now(UTC)
    case_evidence: dict[str, Any] = {}
    try:
        for name, case in cases.items():
            baseline_runs = _baseline_runs(binary, case, args.repetitions, args.timeout_seconds)
            traced_runs = _traced_runs(strace, binary, case, args.repetitions, args.timeout_seconds)
            archive = build_tar(case)
            case_evidence[name] = {
                "case_id": case.case_id,
                "archive_sha256": hashlib.sha256(archive).hexdigest(),
                "entries": [
                    {
                        "ordinal": ordinal,
                        "path": entry.path,
                        "type": entry.entry_type.value,
                        "link_target": entry.link_target,
                        "mode": entry.mode,
                        "content_sha256": hashlib.sha256(entry.content).hexdigest()
                        if entry.content is not None
                        else None,
                    }
                    for ordinal, entry in enumerate(case.entries)
                ],
                "baseline_runs": baseline_runs,
                "traced_runs": traced_runs,
                "mechanical_summary": _case_summary(case, baseline_runs, traced_runs),
            }
    finally:
        binary.unlink(missing_ok=True)

    evidence = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "evidence_tier": "RAW_ONLY",
        "started_at_utc": started.isoformat(),
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "source": source,
        "environment": environment,
        "target": {
            "target_id": "libarchive-public-write-disk-reference",
            "image_id": args.image_id,
            "base_image_id": args.base_image_id,
            "probe_source_sha256": _sha256(PROBE_SOURCE),
            "compile": compile_evidence,
        },
        "config": {
            "repetitions": args.repetitions,
            "timeout_seconds": args.timeout_seconds,
            "runtime_root": "/var/lib/inodefence",
            "builder_format": BUILDER_FORMAT,
            "random_seed": None,
        },
        "cases": case_evidence,
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

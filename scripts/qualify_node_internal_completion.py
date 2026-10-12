"""Qualify node-tar's private filesystem-effect completion callback.

This benign experiment compares the unmodified target with marker-only and
same-callback snapshot profiles. It is not a target adapter, security finding,
or P0/P1/P2 effectiveness experiment. Raw evidence is never overwritten.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import statistics
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
MODULE = ROOT / "tools/node-tar/node_modules/tar"
LOCK = ROOT / "tools/node-tar/package-lock.json"
PROBE = ROOT / "tools/node-tar/internal-completion-probe.cjs"
UNPACK = MODULE / "dist/commonjs/unpack.js"
ENTRYPOINT = MODULE / "dist/commonjs/index.min.js"
EXPECTED_NODE = "22.22.0"
EXPECTED_TAR = "7.5.22"
EXPERIMENT_ID = "node-internal-completion-qualification-v3"
PROFILES = ("stock", "marker", "snapshot")

NODE_TYPES = {
    EntryType.REGULAR: "File",
    EntryType.DIRECTORY: "Directory",
    EntryType.HARDLINK: "Link",
    EntryType.SYMLINK: "SymbolicLink",
}


def qualification_cases() -> dict[str, ArchiveCase]:
    """Cover all scoped entry types, duplicate paths, and independent work."""
    return {
        "mixed": ArchiveCase(
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
                ArchiveEntry("parent", EntryType.DIRECTORY, mode=0o700),
                ArchiveEntry("parent/child", EntryType.REGULAR, content=b"child"),
            )
        ),
        "independent-files": ArchiveCase(
            (
                ArchiveEntry("large", EntryType.REGULAR, content=b"L" * (256 * 1024)),
                ArchiveEntry("small-a", EntryType.REGULAR, content=b"a"),
                ArchiveEntry("small-b", EntryType.REGULAR, content=b"b"),
                ArchiveEntry("empty-dir", EntryType.DIRECTORY, mode=0o750),
            )
        ),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _identity(entry: ArchiveEntry, ordinal: int) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "path": entry.path,
        "type": NODE_TYPES[entry.entry_type],
        "link_target": entry.link_target,
    }


def _entry_config(case: ArchiveCase) -> list[dict[str, Any]]:
    return [
        {
            **_identity(entry, ordinal),
            "entry_type": entry.entry_type.value,
            "mode": entry.mode,
            "content_sha256": hashlib.sha256(entry.content).hexdigest()
            if entry.content is not None
            else None,
        }
        for ordinal, entry in enumerate(case.entries)
    ]


def _run_profile(
    node: str,
    case: ArchiveCase,
    profile: str,
    repetition: int,
    timeout_seconds: float,
    unpack_sha256: str,
    entrypoint_sha256: str,
) -> dict[str, Any]:
    with disposable_sandbox() as sandbox:
        archive = build_tar(case)
        sandbox.archive_path.write_bytes(archive)
        command = (
            node,
            str(PROBE),
            str(MODULE),
            str(sandbox.archive_path),
            str(sandbox.extraction_root),
            profile,
            EXPECTED_NODE,
            EXPECTED_TAR,
            unpack_sha256,
            entrypoint_sha256,
        )
        started = perf_counter_ns()
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            return {
                "repetition": repetition,
                "profile": profile,
                "status": "timeout",
                "duration_ns": perf_counter_ns() - started,
                "archive_sha256": hashlib.sha256(archive).hexdigest(),
                "stdout": error.stdout,
                "stderr": error.stderr,
            }
        duration_ns = perf_counter_ns() - started
        record: dict[str, Any] = {
            "repetition": repetition,
            "profile": profile,
            "status": "completed" if completed.returncode == 0 else "target_error",
            "returncode": completed.returncode,
            "duration_ns": duration_ns,
            "archive_sha256": hashlib.sha256(archive).hexdigest(),
            "stderr": completed.stderr,
        }
        if completed.returncode == 0:
            record["observation"] = json.loads(completed.stdout)
        else:
            record["stdout"] = completed.stdout
        return record


def _future_effects(
    case: ArchiveCase, identity: dict[str, Any], snapshot: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Find fixture-grounded evidence of effects from later archive entries."""
    ordinal = identity["ordinal"]
    observed = {item["path"]: item for item in snapshot}
    first_ordinal: dict[str, int] = {}
    for index, entry in enumerate(case.entries):
        first_ordinal.setdefault(entry.path.rstrip("/"), index)
    effects: list[dict[str, Any]] = []
    for observed_path in observed:
        introduced = first_ordinal.get(observed_path)
        if introduced is not None and introduced > ordinal:
            effects.append(
                {
                    "kind": "later_path_present",
                    "path": observed_path,
                    "later_ordinal": introduced,
                }
            )
    for later_ordinal, entry in enumerate(case.entries[ordinal + 1 :], ordinal + 1):
        if entry.entry_type != EntryType.REGULAR or entry.path not in observed:
            continue
        digest = hashlib.sha256(entry.content or b"").hexdigest()
        if observed[entry.path]["content_sha256"] == digest:
            effects.append(
                {
                    "kind": "later_regular_content_present",
                    "path": entry.path,
                    "later_ordinal": later_ordinal,
                }
            )
    return effects


def assess_run(case: ArchiveCase, run: dict[str, Any]) -> dict[str, Any]:
    """Mechanically assess one run against the current TransitionTrace contract."""
    if run["status"] != "completed":
        return {"completed": False, "qualified": False, "failure": run["status"]}
    observation = run["observation"]
    expected = [_identity(entry, ordinal) for ordinal, entry in enumerate(case.entries)]
    reads = [
        event["identity"]
        for event in observation["events"]
        if event["phase"] == "archive_entry_read"
    ]
    completions = [
        event for event in observation["events"] if event["phase"] == "filesystem_effect_complete"
    ]
    if run["profile"] == "stock":
        return {
            "completed": True,
            "qualified": None,
            "final_semantic_sha256": _canonical_hash(observation["final_semantic_snapshot"]),
        }

    completion_identities = [event["identity"] for event in completions]
    associations_exact = (
        reads == expected
        and sorted(completion_identities, key=lambda value: value["ordinal"]) == expected
    )
    association_failures = sum(event["association_failure"] is not None for event in completions)
    target_errors = sum(event["target_error"] is not None for event in completions)
    completion_sequence = [event["identity"]["ordinal"] for event in completions]
    prefix_complete = []
    snapshot_failures = 0
    future_effects: list[dict[str, Any]] = []
    for event in completions:
        entry_ordinal = event["identity"]["ordinal"]
        prefix_complete.append(event["completed_ordinals"] == list(range(entry_ordinal + 1)))
        if run["profile"] == "snapshot":
            if event["snapshot_error"] is not None or event["snapshot"] is None:
                snapshot_failures += 1
            else:
                future_effects.extend(_future_effects(case, event["identity"], event["snapshot"]))
        completed_later = [value for value in event["completed_ordinals"] if value > entry_ordinal]
        for later_ordinal in completed_later:
            future_effects.append(
                {
                    "kind": "later_entry_completed",
                    "at_ordinal": entry_ordinal,
                    "later_ordinal": later_ordinal,
                }
            )

    has_snapshots = run["profile"] == "snapshot"
    qualified = (
        has_snapshots
        and associations_exact
        and association_failures == 0
        and target_errors == 0
        and len(completions) == len(expected)
        and all(prefix_complete)
        and snapshot_failures == 0
        and not future_effects
    )
    return {
        "completed": True,
        "qualified": qualified,
        "associations_exact": associations_exact,
        "association_failures": association_failures,
        "target_errors": target_errors,
        "completion_sequence": completion_sequence,
        "archive_order": list(range(len(expected))),
        "prefix_complete_at_each_callback": prefix_complete,
        "snapshot_failures": snapshot_failures,
        "future_effects": future_effects,
        "final_semantic_sha256": _canonical_hash(observation["final_semantic_snapshot"]),
    }


def summarize(
    cases: dict[str, ArchiveCase], runs: dict[str, dict[str, list[dict[str, Any]]]]
) -> dict[str, Any]:
    """Produce deterministic counts without promoting raw data to a claim."""
    case_summaries: dict[str, Any] = {}
    all_snapshot_qualified = True
    all_final_semantics_equal = True
    for case_name, profiles in runs.items():
        profile_summaries: dict[str, Any] = {}
        final_hashes: set[str] = set()
        for profile, profile_runs in profiles.items():
            assessments = [assess_run(cases[case_name], run) for run in profile_runs]
            completed = [
                (run, assessment)
                for run, assessment in zip(profile_runs, assessments, strict=True)
                if assessment["completed"]
            ]
            hashes = {assessment["final_semantic_sha256"] for _, assessment in completed}
            final_hashes.update(hashes)
            durations = [run["duration_ns"] for run, _ in completed]
            target_durations = [run["observation"]["target_duration_ns"] for run, _ in completed]
            profile_summary: dict[str, Any] = {
                "attempted": len(profile_runs),
                "completed": len(completed),
                "status_counts": {
                    status: sum(run["status"] == status for run in profile_runs)
                    for status in sorted({run["status"] for run in profile_runs})
                },
                "distinct_final_semantic_snapshots": len(hashes),
                "median_process_duration_ns": int(statistics.median(durations))
                if durations
                else None,
                "median_target_duration_ns": int(statistics.median(target_durations))
                if target_durations
                else None,
            }
            if profile != "stock":
                profile_summary.update(
                    {
                        "exact_association_runs": sum(
                            assessment.get("associations_exact", False)
                            for _, assessment in completed
                        ),
                        "archive_order_completion_runs": sum(
                            assessment.get("completion_sequence") == assessment.get("archive_order")
                            for _, assessment in completed
                        ),
                        "snapshot_failure_count": sum(
                            assessment.get("snapshot_failures", 0) for _, assessment in completed
                        ),
                        "future_effect_observation_count": sum(
                            len(assessment.get("future_effects", ())) for _, assessment in completed
                        ),
                        "qualified_runs": sum(
                            assessment["qualified"] is True for _, assessment in completed
                        ),
                        "completion_sequences": {
                            sequence: sum(
                                ",".join(map(str, item.get("completion_sequence", ()))) == sequence
                                for _, item in completed
                            )
                            for sequence in sorted(
                                {
                                    ",".join(map(str, item.get("completion_sequence", ())))
                                    for _, item in completed
                                }
                            )
                        },
                    }
                )
            if profile == "snapshot":
                all_snapshot_qualified = all_snapshot_qualified and (
                    len(completed) == len(profile_runs)
                    and all(item["qualified"] is True for _, item in completed)
                )
            profile_summaries[profile] = profile_summary
        stock_duration = profile_summaries["stock"]["median_target_duration_ns"]
        for profile_summary in profile_summaries.values():
            duration = profile_summary["median_target_duration_ns"]
            profile_summary["median_target_duration_ratio_to_stock"] = (
                duration / stock_duration if duration is not None and stock_duration else None
            )
        final_semantics_equal = len(final_hashes) == 1
        all_final_semantics_equal = all_final_semantics_equal and final_semantics_equal
        case_summaries[case_name] = {
            "profiles": profile_summaries,
            "final_semantics_equal_across_profiles": final_semantics_equal,
        }
    return {
        "cases": case_summaries,
        "native_transition_producer_qualified": (
            all_snapshot_qualified and all_final_semantics_equal
        ),
        "decision_rule": (
            "all snapshot runs complete with exact entry association, complete archive-prefix "
            "order, no snapshot failure or observed later-entry effect, and final semantics "
            "equal stock/marker/snapshot"
        ),
    }


def _git_source() -> dict[str, Any]:
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    return {
        "revision": revision,
        "dirty": bool(status),
        "status_porcelain": status.splitlines(),
    }


def _environment(node: str) -> dict[str, Any]:
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
        "node_version": subprocess.run(
            (node, "--version"),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip(),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "process_status": process_status,
        "runtime_root": os.environ.get("INODEFENCE_RUNTIME_ROOT", "/var/lib/inodefence"),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=20)
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
    if node is None:
        raise RuntimeError("node is required")
    if not MODULE.is_dir() or not UNPACK.is_file():
        raise RuntimeError("run npm ci in tools/node-tar before qualification")
    node_version = (
        subprocess.run(
            (node, "--version"),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        .stdout.strip()
        .removeprefix("v")
    )
    package = json.loads((MODULE / "package.json").read_text())
    if node_version != EXPECTED_NODE or package["version"] != EXPECTED_TAR:
        raise RuntimeError(
            f"requires node {EXPECTED_NODE}/tar {EXPECTED_TAR}, got "
            f"{node_version}/{package['version']}"
        )

    source = _git_source()
    cases = qualification_cases()
    unpack_sha256 = _sha256(UNPACK)
    entrypoint_sha256 = _sha256(ENTRYPOINT)
    started = datetime.now(UTC)
    runs: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for case_name, case in cases.items():
        runs[case_name] = {}
        for profile in PROFILES:
            runs[case_name][profile] = [
                _run_profile(
                    node,
                    case,
                    profile,
                    repetition,
                    args.timeout_seconds,
                    unpack_sha256,
                    entrypoint_sha256,
                )
                for repetition in range(args.repetitions)
            ]

    evidence = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "evidence_tier": "RAW_ONLY",
        "started_at_utc": started.isoformat(),
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "source": source,
        "environment": _environment(node),
        "target": {
            "target_id": "node-tar-strict-internal-completion-candidate",
            "node_version": node_version,
            "tar_version": package["version"],
            "package_lock_sha256": _sha256(LOCK),
            "module_package_sha256": _sha256(MODULE / "package.json"),
            "unpack_commonjs_sha256": unpack_sha256,
            "package_entrypoint_sha256": entrypoint_sha256,
            "probe_sha256": _sha256(PROBE),
            "invocation": {"strict": True, "preservePaths": False, "sync": False},
        },
        "config": {
            "repetitions": args.repetitions,
            "timeout_seconds": args.timeout_seconds,
            "profiles": list(PROFILES),
            "builder_format": BUILDER_FORMAT,
            "cases": {
                name: {
                    "case_id": case.case_id,
                    "archive_sha256": hashlib.sha256(build_tar(case)).hexdigest(),
                    "entries": _entry_config(case),
                }
                for name, case in cases.items()
            },
        },
        "runs": runs,
        "mechanical_summary": summarize(cases, runs),
        "scope": (
            "Benign private-callback qualification only. A passing callback association "
            "does not establish native transition effectiveness or a security result."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode()
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
                "qualified": evidence["mechanical_summary"]["native_transition_producer_qualified"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

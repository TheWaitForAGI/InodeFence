"""Qualify causally attributed node-tar filesystem-effect events.

This benign feasibility experiment compares stock extraction, minimal async-context
instrumentation, and causally attributed filesystem operation completions. It is not
a target adapter, Security Contract verdict, or P0/P1/P2 effectiveness experiment.
Raw evidence is never overwritten.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
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
PROBE = ROOT / "tools/node-tar/causal-effect-probe.cjs"
UNPACK = MODULE / "dist/commonjs/unpack.js"
ENTRYPOINT = MODULE / "dist/commonjs/index.min.js"
EXPECTED_NODE = "22.22.0"
EXPECTED_TAR = "7.5.22"
EXPERIMENT_ID = "node-causal-effect-qualification-v4"
PROFILES = ("stock", "context", "effects")
REJECTION_CASE = "partial-rejection"

NODE_TYPES = {
    EntryType.REGULAR: "File",
    EntryType.DIRECTORY: "Directory",
    EntryType.HARDLINK: "Link",
    EntryType.SYMLINK: "SymbolicLink",
}


def qualification_cases() -> dict[str, ArchiveCase]:
    """Cover each scoped effect and the required overlap/rejection cases."""
    return {
        "regular-file": ArchiveCase(
            (ArchiveEntry("regular", EntryType.REGULAR, content=b"regular-content"),)
        ),
        "directory-metadata": ArchiveCase(
            (ArchiveEntry("directory", EntryType.DIRECTORY, mode=0o750),)
        ),
        "hardlink-identity": ArchiveCase(
            (
                ArchiveEntry("source", EntryType.REGULAR, content=b"shared"),
                ArchiveEntry("hard", EntryType.HARDLINK, link_target="source"),
            )
        ),
        "symlink": ArchiveCase(
            (
                ArchiveEntry("source", EntryType.REGULAR, content=b"target"),
                ArchiveEntry("sym", EntryType.SYMLINK, link_target="source", mode=0o777),
            )
        ),
        "duplicate-path": ArchiveCase(
            (
                ArchiveEntry("duplicate", EntryType.REGULAR, content=b"first"),
                ArchiveEntry("duplicate", EntryType.REGULAR, content=b"second"),
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
        REJECTION_CASE: ArchiveCase(
            (
                ArchiveEntry("completed-before-error", EntryType.REGULAR, content=b"kept"),
                ArchiveEntry(
                    "completed-before-error",
                    EntryType.HARDLINK,
                    link_target="missing-target",
                ),
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


def archive_bytes(case_name: str, case: ArchiveCase) -> bytes:
    """Build the exact fixture artifact; case_name keeps the analysis call explicit."""
    if case_name not in qualification_cases():
        raise ValueError(f"unknown qualification case: {case_name}")
    return build_tar(case)


def _run_profile(
    node: str,
    case_name: str,
    case: ArchiveCase,
    profile: str,
    repetition: int,
    timeout_seconds: float,
    unpack_sha256: str,
    entrypoint_sha256: str,
) -> dict[str, Any]:
    with disposable_sandbox() as sandbox:
        archive = archive_bytes(case_name, case)
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
            "status": "process_returned",
            "returncode": completed.returncode,
            "duration_ns": duration_ns,
            "archive_sha256": hashlib.sha256(archive).hexdigest(),
            "stderr": completed.stderr,
        }
        try:
            record["observation"] = json.loads(completed.stdout)
        except ValueError:
            record["status"] = "observation_malformed"
            record["stdout"] = completed.stdout
        return record


def _valid_identity(identity: Any, expected: list[dict[str, Any]]) -> bool:
    return (
        isinstance(identity, dict)
        and type(identity.get("ordinal")) is int
        and 0 <= identity["ordinal"] < len(expected)
        and identity == expected[identity["ordinal"]]
    )


def assess_run(case_name: str, case: ArchiveCase, run: dict[str, Any]) -> dict[str, Any]:
    """Mechanically assess one run against the predeclared feasibility gate."""
    if run["status"] != "process_returned":
        return {"process_returned": False, "feasible": False, "failure": run["status"]}
    observation = run["observation"]
    expected = [_identity(entry, ordinal) for ordinal, entry in enumerate(case.entries)]
    expected_outcome = "rejected" if case_name == REJECTION_CASE else "success"
    outcome_matches = observation["target_outcome"] == expected_outcome
    returncode_matches = run["returncode"] == (2 if expected_outcome == "rejected" else 0)
    result: dict[str, Any] = {
        "process_returned": True,
        "target_outcome": observation["target_outcome"],
        "outcome_matches_fixture": outcome_matches and returncode_matches,
        "final_semantic_sha256": _canonical_hash(observation["final_semantic_snapshot"]),
        "observation_failure_count": len(observation["observation_failures"]),
    }
    if run["profile"] == "stock":
        result["feasible"] = None
        return result

    reads = [
        event["identity"]
        for event in observation["events"]
        if event["phase"] == "archive_entry_read"
    ]
    completions = [
        event for event in observation["events"] if event["phase"] == "entry_effect_complete"
    ]
    completion_identities = [event["identity"] for event in completions]
    reads_are_prefix = reads == expected[: len(reads)]
    identities_exact = reads_are_prefix and all(
        _valid_identity(identity, expected) for identity in completion_identities
    )
    associations_unique = len(
        {identity["ordinal"] for identity in completion_identities if identity is not None}
    ) == len(completion_identities)
    association_failures = sum(event["association_failure"] is not None for event in completions)
    target_errors = sum(event["target_error"] is not None for event in completions)
    completion_sequence = [identity["ordinal"] for identity in completion_identities]
    complete_archive = reads == expected and (
        sorted(completion_identities, key=lambda x: x["ordinal"]) == expected
    )
    archive_order = list(range(len(expected)))

    operation_events = [
        event
        for event in observation["events"]
        if event["phase"] == "filesystem_operation_complete"
    ]
    operation_associations_exact = all(
        _valid_identity(event["identity"], expected) for event in operation_events
    )
    operation_ids = [event["operation_id"] for event in operation_events]
    operation_order_valid = operation_ids == sorted(set(operation_ids))
    later_effects: list[dict[str, Any]] = []
    for completion in completions:
        completion_position = observation["events"].index(completion)
        current_ordinal = completion["identity"]["ordinal"]
        for event in observation["events"][:completion_position]:
            identity = event.get("identity")
            if (
                event["phase"] == "filesystem_operation_complete"
                and event["success"]
                and _valid_identity(identity, expected)
                and identity["ordinal"] > current_ordinal
            ):
                later_effects.append(
                    {
                        "at_ordinal": current_ordinal,
                        "later_ordinal": identity["ordinal"],
                        "operation": event["operation"],
                        "paths": event["paths"],
                    }
                )

    normal_case = case_name != REJECTION_CASE
    feasible = (
        run["profile"] == "effects"
        and normal_case
        and outcome_matches
        and returncode_matches
        and complete_archive
        and identities_exact
        and associations_unique
        and association_failures == 0
        and target_errors == 0
        and completion_sequence == archive_order
        and operation_events
        and operation_associations_exact
        and operation_order_valid
        and not later_effects
        and not observation["observation_failures"]
    )
    rejection_handled = (
        not normal_case
        and outcome_matches
        and returncode_matches
        and reads_are_prefix
        and identities_exact
        and associations_unique
        and association_failures == 0
        and target_errors > 0
        and 0 in completion_sequence
        and not observation["observation_failures"]
    )
    result.update(
        {
            "feasible": feasible,
            "rejection_handled": rejection_handled,
            "reads_are_archive_prefix": reads_are_prefix,
            "entry_associations_exact": identities_exact and associations_unique,
            "association_failure_count": association_failures,
            "target_error_count": target_errors,
            "complete_archive": complete_archive,
            "completion_sequence": completion_sequence,
            "archive_order": archive_order,
            "operation_event_count": len(operation_events),
            "operation_associations_exact": operation_associations_exact,
            "operation_order_valid": operation_order_valid,
            "later_effects_before_completion": later_effects,
        }
    )
    return result


def summarize(
    cases: dict[str, ArchiveCase], runs: dict[str, dict[str, list[dict[str, Any]]]]
) -> dict[str, Any]:
    """Produce deterministic counts without promoting raw data to a research result."""
    case_summaries: dict[str, Any] = {}
    all_final_semantics_equal = True
    all_outcomes_equal = True
    all_normal_effect_runs_feasible = True
    all_rejection_effect_runs_handled = True
    for case_name, profiles in runs.items():
        profile_summaries: dict[str, Any] = {}
        final_hashes: set[str] = set()
        outcomes: set[str] = set()
        for profile, profile_runs in profiles.items():
            assessments = [assess_run(case_name, cases[case_name], run) for run in profile_runs]
            returned = [
                (run, assessment)
                for run, assessment in zip(profile_runs, assessments, strict=True)
                if assessment["process_returned"]
            ]
            hashes = {assessment["final_semantic_sha256"] for _, assessment in returned}
            final_hashes.update(hashes)
            outcomes.update(assessment["target_outcome"] for _, assessment in returned)
            durations = [run["duration_ns"] for run, _ in returned]
            target_durations = [run["observation"]["target_duration_ns"] for run, _ in returned]
            summary: dict[str, Any] = {
                "attempted": len(profile_runs),
                "process_returned": len(returned),
                "status_counts": {
                    status: sum(run["status"] == status for run in profile_runs)
                    for status in sorted({run["status"] for run in profile_runs})
                },
                "target_outcome_counts": {
                    outcome: sum(
                        assessment.get("target_outcome") == outcome for _, assessment in returned
                    )
                    for outcome in sorted(
                        {assessment["target_outcome"] for _, assessment in returned}
                    )
                },
                "outcome_match_runs": sum(
                    assessment["outcome_matches_fixture"] for _, assessment in returned
                ),
                "distinct_final_semantic_snapshots": len(hashes),
                "observation_failure_count": sum(
                    assessment["observation_failure_count"] for _, assessment in returned
                ),
                "median_process_duration_ns": int(statistics.median(durations))
                if durations
                else None,
                "median_target_duration_ns": int(statistics.median(target_durations))
                if target_durations
                else None,
            }
            if profile != "stock":
                sequences = {
                    ",".join(map(str, assessment.get("completion_sequence", ())))
                    for _, assessment in returned
                }
                summary.update(
                    {
                        "exact_entry_association_runs": sum(
                            assessment.get("entry_associations_exact", False)
                            for _, assessment in returned
                        ),
                        "archive_order_completion_runs": sum(
                            assessment.get("completion_sequence") == assessment.get("archive_order")
                            for _, assessment in returned
                        ),
                        "operation_event_count": sum(
                            assessment.get("operation_event_count", 0) for _, assessment in returned
                        ),
                        "exact_operation_association_runs": sum(
                            assessment.get("operation_associations_exact", False)
                            for _, assessment in returned
                        ),
                        "later_effect_before_completion_count": sum(
                            len(assessment.get("later_effects_before_completion", ()))
                            for _, assessment in returned
                        ),
                        "feasible_runs": sum(
                            assessment.get("feasible") is True for _, assessment in returned
                        ),
                        "rejection_handled_runs": sum(
                            assessment.get("rejection_handled", False) for _, assessment in returned
                        ),
                        "completion_sequences": {
                            sequence: sum(
                                ",".join(map(str, item.get("completion_sequence", ()))) == sequence
                                for _, item in returned
                            )
                            for sequence in sorted(sequences)
                        },
                    }
                )
            profile_summaries[profile] = summary

        stock_duration = profile_summaries["stock"]["median_target_duration_ns"]
        for profile_summary in profile_summaries.values():
            duration = profile_summary["median_target_duration_ns"]
            profile_summary["median_target_duration_ratio_to_stock"] = (
                duration / stock_duration if duration is not None and stock_duration else None
            )
        final_semantics_equal = len(final_hashes) == 1
        outcomes_equal = len(outcomes) == 1
        all_final_semantics_equal = all_final_semantics_equal and final_semantics_equal
        all_outcomes_equal = all_outcomes_equal and outcomes_equal
        effect_assessments = [
            assess_run(case_name, cases[case_name], run) for run in profiles["effects"]
        ]
        if case_name == REJECTION_CASE:
            all_rejection_effect_runs_handled = all_rejection_effect_runs_handled and all(
                assessment.get("rejection_handled", False) for assessment in effect_assessments
            )
        else:
            all_normal_effect_runs_feasible = all_normal_effect_runs_feasible and all(
                assessment.get("feasible") is True for assessment in effect_assessments
            )
        case_summaries[case_name] = {
            "profiles": profile_summaries,
            "final_semantics_equal_across_profiles": final_semantics_equal,
            "target_outcomes_equal_across_profiles": outcomes_equal,
        }

    feasibility_qualified = (
        all_normal_effect_runs_feasible
        and all_rejection_effect_runs_handled
        and all_final_semantics_equal
        and all_outcomes_equal
    )
    return {
        "cases": case_summaries,
        "causal_effect_feasibility_qualified": feasibility_qualified,
        "native_transition_producer_qualified": False,
        "decision_rule": (
            "all normal effects-profile runs must preserve stock outcome/final semantics, "
            "associate every entry and filesystem operation exactly, complete in archive "
            "order with no later-ordinal operation completed before an earlier entry marker, "
            "and report no observation failure; the rejection fixture must preserve an "
            "explicit rejected outcome and well-formed completed evidence"
        ),
        "producer_boundary": (
            "This experiment records causal effect events, not complete EntryCheckpoint "
            "snapshots. A native producer can only follow a feasibility PASS."
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
    return {"revision": revision, "dirty": bool(status), "status": status.splitlines()}


def _environment(node: str) -> dict[str, Any]:
    status = Path("/proc/self/status").read_text()
    fields = {}
    for line in status.splitlines():
        if line.startswith(("CapEff:", "NoNewPrivs:", "Seccomp:")):
            key, value = line.split(":", 1)
            fields[key] = value.strip()
    stat = os.statvfs(os.environ.get("INODEFENCE_RUNTIME_ROOT", "/var/lib/inodefence"))
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "node_executable": node,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "runtime_root": os.environ.get("INODEFENCE_RUNTIME_ROOT", "/var/lib/inodefence"),
        "runtime_filesystem_block_size": stat.f_frsize,
        "process_status": fields,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    if not 0 < args.timeout_seconds <= 120:
        parser.error("--timeout-seconds must be in (0, 120]")
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("node executable is required")
    node_version = (
        subprocess.run((node, "--version"), check=True, capture_output=True, text=True, timeout=10)
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
                    case_name,
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
            "target_id": "node-tar-strict-causal-effect-candidate",
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
            "decision_rule_frozen_before_run": True,
            "cases": {
                name: {
                    "case_id": case.case_id,
                    "archive_sha256": hashlib.sha256(archive_bytes(name, case)).hexdigest(),
                    "expected_outcome": "rejected" if name == REJECTION_CASE else "success",
                    "entries": _entry_config(case),
                }
                for name, case in cases.items()
            },
        },
        "runs": runs,
        "mechanical_summary": summarize(cases, runs),
        "scope": (
            "Benign native-observation feasibility evidence only. Effect events are not "
            "TransitionTrace checkpoints, Security Contract verdicts, or effectiveness results."
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
                "feasibility_qualified": evidence["mechanical_summary"][
                    "causal_effect_feasibility_qualified"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

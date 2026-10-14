"""Run the fixed Gate 4 node-tar effect-observation qualification matrix."""

from __future__ import annotations

import json
import os
import platform
import statistics
import subprocess
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from scripts.qualify_node_causal_effects import REJECTION_CASE, qualification_cases

from inodefence.effect_pipeline import run_node_tar_effect_case
from inodefence.evaluation.encoding import json_bytes
from inodefence.evaluation.native_effect_evidence import (
    VerifiedNativeEffectEvidence,
    export_native_effect_run,
    reconstruct_native_effect_trace,
    verify_native_effect_evidence,
)
from inodefence.evaluation.storage import publish_bytes, sync_directory, write_record
from inodefence.evaluation.verify import VerificationError
from inodefence.execution.base import (
    BackendError,
    ContainerOutcome,
    ContainerRequest,
    ExecutionBackend,
    PreparedExecution,
)
from inodefence.model import (
    EffectClass,
    EffectStreamCompleteness,
    EffectTargetTermination,
    OperationOutcome,
    RunResult,
    canonical_json,
)
from inodefence.pipeline import run_case
from inodefence.targets.node_tar import NodeTarTarget
from inodefence.targets.node_tar_effect import NativeEffectProfile, NodeTarEffectTarget

EXPERIMENT_ID = "node-native-effect-observation-qualification-v2"
QUALIFIED = "V2_NATIVE_EFFECT_OBSERVATION_QUALIFIED"
NOT_QUALIFIED = "V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED"
PROFILES = ("stock", "minimal", "full")


def _git_source(root: Path) -> dict[str, Any]:
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.splitlines()
    return {"revision": revision, "dirty": bool(status), "status": status}


def _environment() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "runtime_root": os.environ.get("INODEFENCE_RUNTIME_ROOT", "/var/lib/inodefence"),
    }


def _semantic_state(result: RunResult) -> dict[str, Any]:
    objects = result.after.objects
    groups: dict[tuple[int, int], list[str]] = {}
    for item in objects:
        groups.setdefault(item.identity, []).append(item.path)
    return {
        "protected_paths": list(result.after.protected_paths),
        "objects": [
            {
                "path": item.path,
                "object_type": item.object_type.value,
                "identity_group": sorted(groups[item.identity])
                if len(groups[item.identity]) > 1
                else [],
                "nlink": item.st_nlink,
                "mode": item.mode,
                "size": item.size,
                "uid": item.uid,
                "gid": item.gid,
                "symlink_target": item.symlink_target,
                "content_digest": item.content_digest,
            }
            for item in objects
        ],
    }


def _semantic_sha256(result: RunResult) -> str:
    return sha256(json_bytes(_semantic_state(result))).hexdigest()


def _completion_order(verified: VerifiedNativeEffectEvidence) -> list[int]:
    return [
        event.entry.entry_index
        for event in verified.result.trace.lifecycle_events
        if event.kind.value == "effect_work_settled"
    ]


def _key_sha256(verified: VerifiedNativeEffectEvidence) -> str:
    encoded = json_bytes([json.loads(canonical_json(key)) for key in verified.feedback_keys])
    return sha256(encoded).hexdigest()


def _rewrite_terminal(envelope: dict) -> bytes:
    records = envelope["records"]
    terminal = envelope["terminal"]
    terminal["record_count"] = len(records)
    terminal["last_produced_sequence"] = records[-1]["sequence"] if records else -1
    terminal["last_attempted_sequence"] = terminal["last_produced_sequence"]
    terminal["records_sha256"] = sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return (json.dumps(envelope, separators=(",", ":")) + "\n").encode()


def _failure_injections(
    verified: VerifiedNativeEffectEvidence, destination: Path
) -> tuple[dict[str, bool], dict[str, str]]:
    """Mutate a valid full raw frame; every injected record must be rejected."""
    original = json.loads(verified.raw_stream)
    outcomes: dict[str, bool] = {}
    artifacts: dict[str, str] = {}
    destination.mkdir(parents=True)

    def rejected(name: str, envelope: dict) -> None:
        raw = _rewrite_terminal(envelope)
        artifacts[name] = publish_bytes(destination / f"{name}.json", raw)
        try:
            reconstruct_native_effect_trace(raw, verified.result)
        except VerificationError:
            outcomes[name] = True
        else:
            outcomes[name] = False

    def clone() -> dict:
        return json.loads(json.dumps(original))

    value = clone()
    if len(value["records"]) >= 2:
        del value["records"][1]
    rejected("missing_sequence", value)

    value = clone()
    if len(value["records"]) >= 2:
        value["records"][1]["sequence"] = value["records"][0]["sequence"]
    rejected("duplicate_sequence", value)

    value = clone()
    value["terminal"]["overflow"] = True
    value["terminal"]["dropped_records"] = 1
    rejected("buffer_overflow", value)

    value = clone()
    lifecycle = next(record for record in value["records"] if record["record_type"] == "lifecycle")
    lifecycle["entry"]["ordinal"] = "malformed"
    rejected("malformed_identity", value)

    value = clone()
    lifecycle = next(record for record in value["records"] if record["record_type"] == "lifecycle")
    lifecycle["entry"]["path"] += "-conflict"
    rejected("entry_association_conflict", value)

    value = clone()
    completion = next(
        record for record in value["records"] if record["record_type"] == "operation_completion"
    )
    completion["start_sequence"] += 1
    rejected("operation_correlation_conflict", value)

    value = clone()
    unmatched = next(
        record for record in value["records"] if record["record_type"] == "operation_start"
    ).copy()
    unmatched["sequence"] = len(value["records"])
    unmatched["record_id"] = "injected-unmatched-operation-start"
    unmatched["correlation_id"] = "injected-unmatched-operation"
    value["records"].append(unmatched)
    rejected("unmatched_operation", value)

    value = clone()
    start = next(
        record for record in value["records"] if record["record_type"] == "operation_start"
    )
    matching = next(
        record
        for record in value["records"]
        if record["record_type"] == "operation_completion"
        and record["correlation_id"] == start["correlation_id"]
    )
    start["handle_origin_completion_sequence"] = matching["sequence"]
    rejected("invalid_causal_edge", value)

    value = clone()
    value["terminal"]["flush"] = "interrupted"
    rejected("flush_interruption", value)

    value = clone()
    value["source"]["producer_sha256"] = "0" * 64
    rejected("source_reader_disagreement", value)
    return outcomes, artifacts


def _coverage_acceptance(runs: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    full = [item for item in runs if item["profile"] == "full"]
    by_case: dict[str, set[str]] = {}
    operations_by_case: dict[str, set[str]] = {}
    for item in full:
        by_case.setdefault(item["case"], set()).update(item["realized_effect_classes"])
        operations_by_case.setdefault(item["case"], set()).update(item["operation_types"])
    requirements = {
        "regular-file": {
            EffectClass.REGULAR_FILE_CONTENT_MODIFICATION.value,
            EffectClass.NAMESPACE_CREATION.value,
        },
        "directory-metadata": {
            EffectClass.NAMESPACE_CREATION.value,
            EffectClass.METADATA_MODIFICATION.value,
        },
        "hardlink-identity": {EffectClass.HARDLINK_IDENTITY_RELATION_CREATION.value},
        "symlink": {EffectClass.SYMLINK_CREATION.value},
        "duplicate-path": {EffectClass.NAMESPACE_REPLACEMENT.value},
    }
    checks = {case: required <= by_case.get(case, set()) for case, required in requirements.items()}
    operation_checks = {
        "regular_open_close": {"open", "close"} <= operations_by_case.get("regular-file", set()),
        "regular_data": bool({"write", "writev"} & operations_by_case.get("regular-file", set())),
        "directory_create": "mkdir" in operations_by_case.get("directory-metadata", set()),
        "directory_metadata": bool(
            {"chmod", "chown", "utimes", "futimes", "fchown"}
            & operations_by_case.get("directory-metadata", set())
        ),
        "hardlink": "link" in operations_by_case.get("hardlink-identity", set()),
        "symlink": "symlink" in operations_by_case.get("symlink", set()),
        "failure_cleanup": bool(
            {"unlink", "rmdir", "rm"} & operations_by_case.get(REJECTION_CASE, set())
        ),
    }
    return all(checks.values()) and all(operation_checks.values()), {
        "observed_by_case": {key: sorted(value) for key, value in sorted(by_case.items())},
        "operation_types_by_case": {
            key: sorted(value) for key, value in sorted(operations_by_case.items())
        },
        "required_realized_effect_checks": checks,
        "required_operation_checks": operation_checks,
        "unsupported_effect_classes": [EffectClass.IDENTITY_RELATION_REMOVAL.value],
    }


def _summarize(
    runs: list[dict[str, Any]],
    repetitions: int,
    source_clean: bool,
    failure_injections: dict[str, bool],
    timeout_pass: bool,
    overflow_pass: bool,
    backend_failure_pass: bool,
) -> dict[str, Any]:
    cases = qualification_cases()
    expected_runs = len(cases) * len(PROFILES) * repetitions
    status_ok = all(
        item["status"] == ("rejected" if item["case"] == REJECTION_CASE else "success")
        for item in runs
    )
    integrity_ok = all(item["profile"] == "stock" or item["integrity_valid"] for item in runs)
    semantic_ok = True
    key_stability = True
    completion_orders: dict[str, dict[str, Counter[str]]] = {}
    overhead: dict[str, dict[str, dict[str, float | int]]] = {}
    for case_name in cases:
        case_runs = [item for item in runs if item["case"] == case_name]
        for repetition in range(repetitions):
            hashes = {
                item["semantic_sha256"] for item in case_runs if item["repetition"] == repetition
            }
            semantic_ok &= len(hashes) == 1
        completion_orders[case_name] = {}
        overhead[case_name] = {}
        for profile in PROFILES:
            profile_runs = [item for item in case_runs if item["profile"] == profile]
            completion_orders[case_name][profile] = Counter(
                ",".join(map(str, item["completion_order"])) for item in profile_runs
            )
            durations = [item["full_duration_ns"] for item in profile_runs]
            evidence_sizes = [item["evidence_bytes"] for item in profile_runs]
            overhead[case_name][profile] = {
                "median_full_duration_ns": int(statistics.median(durations)),
                "median_evidence_bytes": int(statistics.median(evidence_sizes)),
            }
            if profile != "stock":
                key_stability &= len({item["key_sha256"] for item in profile_runs}) == 1
    coverage_ok, coverage = _coverage_acceptance(runs)
    rejected_prefix_ineligible = all(
        item["key_sha256"] == sha256(b"[]").hexdigest()
        for item in runs
        if item["case"] == REJECTION_CASE and item["profile"] != "stock"
    )
    rejection_failure_observed = any(
        item["failed_operation_count"] > 0
        for item in runs
        if item["case"] == REJECTION_CASE and item["profile"] == "full"
    )
    criteria = {
        "complete_fixed_matrix": len(runs) == expected_runs and repetitions >= 20,
        "clean_source_revision": source_clean,
        "expected_target_outcomes": status_ok,
        "transport_and_association_integrity": integrity_ok,
        "semantic_state_equality": semantic_ok,
        "required_effect_coverage": coverage_ok,
        "rejection_failure_operation_observed": rejection_failure_observed,
        "normalized_key_stability": key_stability,
        "rejected_prefix_feedback_ineligible": rejected_prefix_ineligible,
        "failure_injections_detected": bool(failure_injections)
        and all(failure_injections.values()),
        "timeout_preserved_incomplete": timeout_pass,
        "overflow_preserved_invalid": overflow_pass,
        "backend_failure_distinct": backend_failure_pass,
        "overhead_and_completion_order_reported": True,
    }
    qualified = all(criteria.values())
    return {
        "decision": QUALIFIED if qualified else NOT_QUALIFIED,
        "criteria": criteria,
        "coverage": coverage,
        "failure_injections": failure_injections,
        "completion_order_distributions": {
            case: {profile: dict(sorted(counter.items())) for profile, counter in profiles.items()}
            for case, profiles in completion_orders.items()
        },
        "overhead": overhead,
    }


class _FailingPrepared:
    def execute(self) -> ContainerOutcome:
        raise BackendError("qualification-injected backend failure")


class _InjectedBackendFailure(ExecutionBackend):
    """Delegate identification, then fail before any target outcome can exist."""

    def __init__(self, delegate: ExecutionBackend) -> None:
        self.delegate = delegate

    def validate_image(self, image_id: str) -> None:
        self.delegate.validate_image(image_id)

    def policy(self, image_id: str):
        return self.delegate.policy(image_id)

    def capture_isolation(self, image_id: str):
        return self.delegate.capture_isolation(image_id)

    @contextmanager
    def prepare(self, request: ContainerRequest) -> Iterator[PreparedExecution]:
        if "--identify" in request.command:
            with self.delegate.prepare(request) as prepared:
                yield prepared
        else:
            yield _FailingPrepared()


def run_qualification(
    backend: ExecutionBackend,
    image_id: str,
    output: Path,
    *,
    repetitions: int = 20,
) -> tuple[Path, str, str]:
    """Execute stock/minimal/full matrix and publish raw evidence without overwrite."""
    if repetitions < 20:
        raise ValueError("Gate 4 qualification requires at least 20 repetitions")
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    root = Path(__file__).resolve().parents[1]
    source = _git_source(root)
    started = datetime.now(UTC)
    output.mkdir()
    sync_directory(output.parent)
    (output / "runs").mkdir()
    sync_directory(output)

    stock = NodeTarTarget.bind(backend, image_id)
    minimal = NodeTarEffectTarget.bind(backend, image_id, profile=NativeEffectProfile.MINIMAL)
    full = NodeTarEffectTarget.bind(backend, image_id, profile=NativeEffectProfile.FULL)
    isolation = full.capture_isolation()
    cases = qualification_cases()
    runs: list[dict[str, Any]] = []
    first_full: VerifiedNativeEffectEvidence | None = None
    for case_name, case in cases.items():
        for profile in PROFILES:
            for repetition in range(repetitions):
                started_ns = perf_counter_ns()
                if profile == "stock":
                    result = run_case(case, stock)
                    artifact = output / "runs" / case_name / f"stock-{repetition}.json"
                    artifact_digest = write_record(artifact, result)
                    completion_order: list[int] = []
                    key_digest = sha256(b"[]").hexdigest()
                    realized: list[str] = []
                    operation_types: list[str] = []
                    integrity_valid = True
                    failed_operation_count = 0
                    evidence_bytes = artifact.stat().st_size
                else:
                    target = minimal if profile == "minimal" else full
                    native = run_node_tar_effect_case(case, target)
                    bundle = output / "runs" / case_name / f"{profile}-{repetition}"
                    bundle.parent.mkdir(parents=True, exist_ok=True)
                    manifest_digest = export_native_effect_run(native, bundle)
                    verified = verify_native_effect_evidence(
                        bundle, expected_manifest_sha256=manifest_digest
                    )
                    if profile == "full" and first_full is None:
                        first_full = verified
                    result = verified.result.base_result
                    artifact = bundle / "manifest.json"
                    artifact_digest = manifest_digest
                    completion_order = _completion_order(verified)
                    key_digest = _key_sha256(verified)
                    realized = sorted(
                        {
                            event.effect_class.value
                            for event in verified.result.trace.effect_events
                            if event.effect_class != EffectClass.OPERATION_OBSERVED
                        }
                    )
                    operation_types = sorted(
                        {event.operation.value for event in verified.result.trace.effect_events}
                    )
                    integrity_valid = verified.result.trace.integrity_valid
                    failed_operation_count = sum(
                        event.outcome != OperationOutcome.SUCCEEDED
                        for event in verified.result.trace.effect_events
                    )
                    evidence_bytes = sum(
                        path.stat().st_size for path in bundle.iterdir() if path.is_file()
                    )
                runs.append(
                    {
                        "case": case_name,
                        "case_id": case.case_id,
                        "profile": profile,
                        "repetition": repetition,
                        "status": result.execution.status.value,
                        "target_duration_seconds": result.execution.duration_seconds,
                        "full_duration_ns": perf_counter_ns() - started_ns,
                        "semantic_sha256": _semantic_sha256(result),
                        "completion_order": completion_order,
                        "key_sha256": key_digest,
                        "realized_effect_classes": realized,
                        "operation_types": operation_types,
                        "integrity_valid": integrity_valid,
                        "failed_operation_count": failed_operation_count,
                        "evidence_bytes": evidence_bytes,
                        "artifact": str(artifact.relative_to(output)),
                        "artifact_sha256": artifact_digest,
                    }
                )

    if first_full is None:
        raise RuntimeError("qualification produced no full-profile evidence")
    injections, injection_artifacts = _failure_injections(
        first_full, output / "failure-injections" / "derived-invalid-streams"
    )
    timeout_run = run_node_tar_effect_case(
        cases["regular-file"],
        NodeTarEffectTarget.bind(
            backend,
            image_id,
            profile=NativeEffectProfile.FULL,
            timeout_seconds=1e-9,
        ),
    )
    overflow_run = run_node_tar_effect_case(
        cases["regular-file"],
        NodeTarEffectTarget.bind(
            backend, image_id, profile=NativeEffectProfile.FULL, event_bound=3
        ),
    )
    timeout_manifest = export_native_effect_run(
        timeout_run, output / "failure-injections" / "timeout"
    )
    overflow_manifest = export_native_effect_run(
        overflow_run, output / "failure-injections" / "overflow"
    )
    timeout_trace = timeout_run.result.trace
    overflow_trace = overflow_run.result.trace
    try:
        verify_native_effect_evidence(
            output / "failure-injections" / "timeout",
            expected_manifest_sha256=timeout_manifest,
        )
    except VerificationError:
        timeout_reader_rejected = True
    else:
        timeout_reader_rejected = False
    try:
        verify_native_effect_evidence(
            output / "failure-injections" / "overflow",
            expected_manifest_sha256=overflow_manifest,
        )
    except VerificationError:
        overflow_reader_rejected = True
    else:
        overflow_reader_rejected = False
    timeout_pass = (
        timeout_trace.termination == EffectTargetTermination.TIMED_OUT
        and timeout_trace.completeness == EffectStreamCompleteness.INCOMPLETE
        and not timeout_trace.integrity_valid
        and not timeout_run.controller_flush_verified
        and timeout_reader_rejected
    )
    overflow_pass = (
        overflow_trace.completeness == EffectStreamCompleteness.INVALID
        and not overflow_trace.integrity_valid
        and overflow_run.controller_flush_verified
        and overflow_reader_rejected
    )
    try:
        failing_target = NodeTarEffectTarget.bind(
            _InjectedBackendFailure(backend),
            image_id,
            profile=NativeEffectProfile.FULL,
        )
        run_node_tar_effect_case(cases["regular-file"], failing_target)
    except BackendError:
        backend_failure_pass = True
    else:
        backend_failure_pass = False
    summary = _summarize(
        runs,
        repetitions,
        not source["dirty"],
        injections,
        timeout_pass,
        overflow_pass,
        backend_failure_pass,
    )
    evidence = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "classification": ("REPRODUCIBLE" if summary["decision"] == QUALIFIED else "RAW_ONLY"),
        "started_at_utc": started.isoformat(),
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "source": source,
        "environment": _environment(),
        "target": {
            "image_id": image_id,
            "node_version": full.node_version,
            "tar_version": full.tar_version,
            "producer_sha256": full.producer_sha256,
            "package_lock_sha256": full.package_lock_sha256,
            "package_entrypoint_sha256": full.package_entrypoint_sha256,
            "unpack_sha256": full.unpack_sha256,
            "isolation": json.loads(canonical_json(isolation)),
            "options": {"strict": True, "preservePaths": False, "sync": False},
        },
        "config": {
            "repetitions": repetitions,
            "profiles": list(PROFILES),
            "event_bound": full.event_bound,
            "timeout_seconds": full.timeout_seconds,
            "fixtures": {
                name: {"case_id": case.case_id, "entries": len(case.entries)}
                for name, case in cases.items()
            },
        },
        "runs": runs,
        "summary": summary,
        "failure_artifacts": {
            "derived_invalid_streams": {
                name: {
                    "path": f"failure-injections/derived-invalid-streams/{name}.json",
                    "sha256": digest,
                    "provenance": "programmatic mutation of first verified full-profile frame",
                }
                for name, digest in sorted(injection_artifacts.items())
            },
            "timeout_manifest": {
                "path": "failure-injections/timeout/manifest.json",
                "sha256": timeout_manifest,
                "provenance": "actual forced-timeout target invocation",
            },
            "overflow_manifest": {
                "path": "failure-injections/overflow/manifest.json",
                "sha256": overflow_manifest,
                "provenance": "actual event-bound overflow target invocation",
            },
        },
        "claim_boundary": (
            "Engineering observation qualification only; no feedback advantage, "
            "vulnerability, rediscovery or paper-effectiveness claim."
        ),
    }
    content = json.dumps(evidence, sort_keys=True, indent=2).encode() + b"\n"
    qualification_path = output / "qualification.json"
    qualification_digest = publish_bytes(qualification_path, content)
    return qualification_path, qualification_digest, summary["decision"]

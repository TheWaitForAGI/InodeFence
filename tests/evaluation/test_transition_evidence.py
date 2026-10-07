"""Synthetic completed-entry target for transition evidence ingest tests."""

from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.evaluation.encoding import json_bytes, read_json
from inodefence.evaluation.transition_evidence import (
    TransitionEvaluationConfig,
    export_transition_result,
    summarize_transition_evidence,
    verify_transition_evidence,
)
from inodefence.evaluation.transition_statistics import (
    TransitionDatasetMember,
    summarize_transition_statistics,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import TransitionSearchPolicy, state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ArchiveEntryReference,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    ObservationKind,
    ObservationPoint,
    RunResult,
    SnapshotPhase,
    TraceCompleteness,
    TraceTermination,
    TransitionRunResult,
    TransitionTrace,
    derive_transition,
)
from inodefence.model.provenance import ExecutionSafety, SourceProvenance, TargetProvenance
from inodefence.mutator import MutationPolicy
from inodefence.observer import capture_checkpoint, capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.provenance import freeze_provenance
from inodefence.runtime import SentinelSpec, disposable_sandbox
from inodefence.transition_campaign import (
    TransitionCampaignConfig,
    run_transition_campaign,
)

SENTINELS = (SentinelSpec(),)
TARGET = TargetProvenance(
    "deterministic-synthetic-transition",
    "1",
    1.0,
    ExecutionSafety.TRUSTED_REFERENCE,
)
SOURCE = SourceProvenance("a" * 40, False)


def _produce(case: ArchiveCase) -> TransitionRunResult:
    """Apply one deterministic file creation after every logical entry.

    This is a test adapter with an exact synchronous completion boundary. It is
    not node-tar, prefix replay or benchmark evidence.
    """
    archive = build_tar(case)
    with disposable_sandbox(SENTINELS) as sandbox:
        sandbox.archive_path.write_bytes(archive)
        before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
        checkpoints = [
            capture_checkpoint(
                sandbox.root,
                0,
                ObservationPoint(ObservationKind.BEFORE),
                sandbox.protected_paths,
            )
        ]
        for index, entry in enumerate(case.entries):
            (sandbox.extraction_root / f"entry-{index}").write_bytes(
                f"{index}:{entry.entry_type.value}:{entry.path}".encode()
            )
            checkpoints.append(
                capture_checkpoint(
                    sandbox.root,
                    index + 1,
                    ObservationPoint(
                        ObservationKind.ENTRY_BOUNDARY,
                        ArchiveEntryReference(
                            index, entry.path, entry.entry_type, entry.link_target
                        ),
                    ),
                    sandbox.protected_paths,
                )
            )
        after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
        trace = TransitionTrace(
            len(case.entries),
            tuple(checkpoints),
            tuple(
                derive_transition(checkpoints[index], checkpoints[index + 1], index)
                for index in range(len(checkpoints) - 1)
            ),
            after,
            TraceCompleteness.COMPLETE,
            TraceTermination.SUCCESS,
        )
        execution = ExecutionResult(
            TARGET.target_id,
            TARGET.target_version,
            ("synthetic-transition",),
            ExecutionStatus.SUCCESS,
            0,
            "",
            "",
            0.0,
            TARGET.timeout_seconds,
        )
        base = RunResult(
            case,
            sha256(archive).hexdigest(),
            BUILDER_FORMAT,
            execution,
            before,
            after,
            compare_states(before, after),
            state_signature(before, after),
            evaluate_contracts(before, after),
        )
        return TransitionRunResult(base, trace)


def _campaign(policy: TransitionSearchPolicy):
    case = ArchiveCase((ArchiveEntry("seed.txt", EntryType.REGULAR, content=b"seed"),))
    config = TransitionCampaignConfig(17, 7, policy, MutationPolicy.M1)
    result = run_transition_campaign((case,), _produce, config)
    declaration = TransitionEvaluationConfig(
        config,
        result.initial_case_ids,
        freeze_provenance(TARGET, SENTINELS, source=SOURCE),
        "fixed-synthetic-seed-v1",
        "unit-linux-v1",
        "default-sentinel-v1",
        "c0-c1-c2-final-v1",
        "generic-eight-operator-v1",
        "transition-ablation-v1",
    )
    return result, declaration


@pytest.fixture(scope="module", params=list(TransitionSearchPolicy))
def campaign(request):
    return _campaign(request.param)


def _modify_record(path, change):
    record = read_json(path.read_bytes())
    assert isinstance(record, dict)
    change(record["payload"]["value"])
    record["payload_sha256"] = sha256(json_bytes(record["payload"])).hexdigest()
    path.write_bytes(json_bytes(record) + b"\n")
    return sha256(path.read_bytes()).hexdigest()


def _rebind_result(directory, digest):
    _modify_record(directory / "manifest.json", lambda value: value["result"].update(sha256=digest))


def test_transition_bundle_roundtrip_replays_policy_mutation_and_scheduler(campaign, tmp_path):
    result, config = campaign
    directory = tmp_path / "transition"
    digest = export_transition_result(result, config, directory)
    verified = verify_transition_evidence(directory, expected_manifest_sha256=digest)

    assert verified.result == result
    assert verified.config == config
    assert verified.manifest_sha256 == digest
    summary = summarize_transition_evidence(directory, expected_manifest_sha256=digest)
    assert summary["search_policy"] == result.config.search_policy.value
    assert summary["mutation_attempt_count"] == 6
    assert summary["unique_transition_key_count"] >= 1
    assert summary["unique_transition_sequence_count"] >= 1
    assert sum(item["attempts"] for item in summary["operator_metrics"]) == 6
    assert summary["incomplete_trace_count"] == 0


def test_scheduler_tamper_fails_even_when_record_checksums_are_rebound(tmp_path):
    result, config = _campaign(TransitionSearchPolicy.P2_TRANSITION_ADAPTIVE)
    directory = tmp_path / "transition"
    export_transition_result(result, config, directory)

    def change(value):
        evidence = value["steps"][1]["scheduler_evidence"]
        evidence["reward"] = 1 - evidence["reward"]

    digest = _modify_record(directory / "result.json", change)
    _rebind_result(directory, digest)
    with pytest.raises(VerificationError, match="scheduler evidence"):
        verify_transition_evidence(directory)


def test_config_mismatch_and_incomplete_bundle_fail_closed(tmp_path):
    result, config = _campaign(TransitionSearchPolicy.P1_TRANSITION_RETENTION)
    with pytest.raises(ValueError, match="declaration differs"):
        export_transition_result(
            result,
            replace(config, campaign=replace(config.campaign, random_seed=18)),
            tmp_path / "mismatch",
        )
    directory = tmp_path / "transition"
    digest = export_transition_result(result, config, directory)
    (directory / "manifest.json").unlink()
    with pytest.raises(VerificationError):
        verify_transition_evidence(directory, expected_manifest_sha256=digest)


def test_policy_arm_statistics_require_equal_controls(tmp_path):
    members = []
    for policy in TransitionSearchPolicy:
        result, config = _campaign(policy)
        directory = tmp_path / policy.name.lower()
        digest = export_transition_result(result, config, directory)
        members.append(TransitionDatasetMember(directory, digest))

    summary = summarize_transition_statistics(tuple(members))
    assert summary["policy_ids"] == tuple(sorted(policy.value for policy in TransitionSearchPolicy))
    assert all(arm["run_count"] == 1 for arm in summary["arms"])
    assert "not vulnerability counts" in summary["interpretation"]

    result, config = _campaign(TransitionSearchPolicy.P1_TRANSITION_RETENTION)
    mismatched = replace(config, oracle_profile="different-oracle-v1")
    directory = tmp_path / "mismatched"
    export_transition_result(result, mismatched, directory)
    with pytest.raises(VerificationError, match="outside the declared search policy"):
        summarize_transition_statistics(
            (*members, TransitionDatasetMember(directory)), allow_seed_variation=False
        )

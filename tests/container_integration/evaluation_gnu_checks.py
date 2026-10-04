"""Actual fixed benign target/replay/pair checks; preserve raw results before assertions."""

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.evaluation.encoding import json_bytes
from inodefence.evaluation.failure import (
    ArtifactReference,
    FailureContext,
    FailurePhase,
    failure_record,
    write_failure,
)
from inodefence.evaluation.gnu_tar import GnuTarInvocation
from inodefence.evaluation.pair import PairArm, compare_pair, export_pair
from inodefence.evaluation.qualification import (
    QualificationCheck,
    QualificationContext,
    QualificationItem,
    QualificationStatus,
    qualification_report,
    verify_qualification,
    write_qualification,
)
from inodefence.evaluation.repeated import RepetitionController, RepetitionPlan
from inodefence.evaluation.statistics import summarize_repetition_statistics
from inodefence.evaluation.storage import publish_bytes, write_record
from inodefence.evaluation.verify import verify_campaign
from inodefence.experiment_config import (
    FEEDBACK_POLICY,
    MUTATION_POLICY,
    SEED_PROFILE,
    ExperimentConfig,
    run_configured_campaign,
)
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, ExecutionStatus, ObjectType
from inodefence.pipeline import run_case
from inodefence.provenance import freeze_provenance
from inodefence.replay.benign import benign_replay_cases
from inodefence.replay.execution import replay_benign
from inodefence.runtime import SentinelSpec, runtime_root
from inodefence.targets.python_tarfile import PythonTarfileTarget


def run_checks(backend, image: str, evidence: Path) -> dict:
    roots = set(runtime_root().iterdir())
    target = GnuTarInvocation.bind(backend, image)
    evidence.mkdir(parents=True, exist_ok=False)
    cases = benign_replay_cases()
    original = run_campaign(cases, PythonTarfileTarget(), CampaignConfig(31, len(cases)))
    original_path = evidence / "original"
    export_campaign(original, original_path)
    verified = verify_campaign(original_path)
    replay = replay_benign(original_path, evidence / "replay", target)
    pairs = []
    for index, record in enumerate(replay.steps):
        result = record.result
        pairs.append(
            export_pair(
                compare_pair(
                    cases[index],
                    PairArm(original.provenance, original.steps[index].result),
                    PairArm(replay.header.provenance, result),
                ),
                evidence / f"pair-{index:08d}.json",
            )
        )
        assert result.execution.status == ExecutionStatus.SUCCESS
        assert not Path(result.after.sandbox_root).exists()
        for entry in cases[index].entries:
            obj = result.after.get("extract/" + entry.path.rstrip("/"))
            assert obj is not None
            if entry.entry_type == EntryType.REGULAR:
                assert obj.object_type == ObjectType.REGULAR
                assert obj.content_digest == sha256(entry.content or b"").hexdigest()
            elif entry.entry_type == EntryType.DIRECTORY:
                assert obj.object_type == ObjectType.DIRECTORY
            elif entry.entry_type == EntryType.SYMLINK:
                assert obj.symlink_target == entry.link_target
            else:
                first = result.after.get("extract/" + (entry.link_target or ""))
                assert first is not None and first.identity == obj.identity
    timeout = GnuTarInvocation.bind(backend, image, 1e-9)
    sentinels = (SentinelSpec(),)
    frozen = freeze_provenance(timeout.provenance, sentinels, isolation=timeout.capture_isolation())
    timeout_result = run_case(cases[0], timeout)
    timeout_sha = write_record(evidence / "timeout.json", PairArm(frozen, timeout_result))
    assert timeout_result.execution.status == ExecutionStatus.TIMED_OUT
    assert not Path(timeout_result.after.sandbox_root).exists()
    source = replay.header.provenance
    try:
        run_case(
            ArchiveCase((ArchiveEntry("ordinary.txt", EntryType.REGULAR, content=b"ordinary"),)),
            target,
        )
    except Exception as error:
        from inodefence.execution.base import BackendError

        assert isinstance(error, BackendError)
        context = FailureContext(
            "gnu-benign-scope-check",
            verified.manifest_sha256,
            source.source,
            source.target,
            None,
            FailurePhase.UNKNOWN,
        )
        guard_sha = write_failure(evidence / "scope-failure.json", failure_record(error, context))
    else:
        raise AssertionError("unsupported benign input was admitted")
    config = ExperimentConfig(
        target.provenance,
        SEED_PROFILE,
        tuple(case.case_id for case in cases),
        CampaignConfig(31, len(cases)),
        MUTATION_POLICY,
        FEEDBACK_POLICY,
        sentinels,
        "linux-controller-gnu-benign-v1",
        target.isolation_policy,
    )
    # Exactly four initial fixtures per run: no generated mutation is executed.
    repetitions = RepetitionController.create(
        evidence / "repetitions", RepetitionPlan(config.to_json(), (31, 37), source)
    )
    for index in range(2):
        slot = repetitions.claim(index, attempt_id=f"gnu-fixed-benign-{index}")
        selected = repetitions.snapshot().plan.config_for(index)
        run = run_configured_campaign(selected, cases, target)
        export_campaign(run, slot / "evidence", experiment_config_json=selected.to_json())
        repetitions.complete(index)
    stats = summarize_repetition_statistics(
        repetitions.root, protocol_version="gnu-benign-protocol-v1"
    )
    stats_sha = publish_bytes(evidence / "statistics.json", json_bytes(stats) + b"\n")
    assert set(runtime_root().iterdir()) == roots
    links = (
        ArtifactReference(
            "replay/header.json", sha256((evidence / "replay/header.json").read_bytes()).hexdigest()
        ),
        ArtifactReference("timeout.json", timeout_sha),
        *(
            ArtifactReference(f"pair-{index:08d}.json", digest)
            for index, digest in enumerate(pairs)
        ),
    )
    observations = tuple(
        QualificationCheck(
            item,
            QualificationStatus.PASS,
            "Actual identity, fixtures, timeout, snapshots and cleanup in linked records.",
            links,
        )
        for item in QualificationItem
        if item != QualificationItem.STATUS
    ) + (
        QualificationCheck(
            QualificationItem.STATUS,
            QualificationStatus.NOT_RUN,
            "SUCCESS/TIMED_OUT observed; REJECTED/FAILED have only unit coverage.",
        ),
    )
    report = qualification_report(
        QualificationContext(
            target.provenance,
            "linux-controller-gnu-benign-v1",
            "default-sentinel-v1",
            "gnu-benign-protocol-v1",
            source,
            target.invocation.artifacts,
            image,
        ),
        observations,
    )
    qualification_sha = write_qualification(evidence / "qualification.json", report)
    assert not verify_qualification(
        evidence / "qualification.json", expected_sha256=qualification_sha
    ).ready
    checks = {
        "schema_version": 1,
        "classification": "benign-integration-only",
        "image_id": image,
        "source": asdict(source.source),
        "target": asdict(source.target),
        "original_manifest_sha256": verified.manifest_sha256,
        "pair_sha256": pairs,
        "timeout_evidence_sha256": timeout_sha,
        "scope_failure_sha256": guard_sha,
        "benign_fixture_count": len(replay.steps),
        "timeout_status": timeout_result.execution.status.value,
        "qualification": report.overall_status.value,
        "qualification_sha256": qualification_sha,
        "statistics_sha256": stats_sha,
        "benchmark_ready": False,
    }
    # Completion of this integration check is separate from replay completion.
    publish_bytes(evidence / "checks.json", json_bytes(checks) + b"\n")
    return checks

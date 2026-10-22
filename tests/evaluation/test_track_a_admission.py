"""Target-free Track A admission checks over synthetic N05 evidence only."""

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path

import pytest
from scripts.container_host import N04HostLedger, N05HostLedger
from tests.evaluation import test_n04_host_ledger as n04_support
from tests.evaluation import test_n05_preflight as n05_support

import inodefence.evaluation.n04_preflight as n04_preflight
import inodefence.evaluation.n05_preflight as preflight
import inodefence.evaluation.track_a_exploratory as track_a
from inodefence.evaluation.encoding import json_bytes
from inodefence.evaluation.failure import ArtifactReference
from inodefence.evaluation.n05_preflight_reader import verify_n05_preflight
from inodefence.evaluation.policy_repeated import PolicyRepetitionController
from inodefence.evaluation.storage import write_record
from inodefence.evaluation.track_a_admission import (
    PILOT_AUTHORIZATION_SCOPE,
    PILOT_DECISION,
    PILOT_HUMAN_REVIEW_STATEMENT,
    PILOT_RESUME_POLICY,
    PILOT_STOP_CONDITIONS,
    TRACK_A_N05_ENVIRONMENT_PROFILE,
    N05EvidenceBinding,
    PilotCampaignCell,
    PilotResourceLimits,
    PilotTargetIdentity,
    PilotTargetRole,
    TrackAPilotAuthorization,
    pilot_authorization_from_bytes,
    track_a_plan_sha256,
    validate_track_a_admission,
)
from inodefence.evaluation.track_a_exploratory import make_track_a_plan
from inodefence.feedback import FeedbackProjection
from inodefence.model import ContractId
from inodefence.model.provenance import ExecutionProvenance
from inodefence.mutator import MutationPolicy
from inodefence.provenance import sentinel_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.isolated import IsolatedTarget


@dataclass(frozen=True)
class SyntheticAdmission:
    authorization: TrackAPilotAuthorization
    authorization_path: Path
    authorization_sha256: str
    approval_reference: str
    protocol_path: Path
    host_root: Path
    linux_root: Path
    output_root: Path
    track_a_host_root: Path


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_authorization(fixture: SyntheticAdmission, value: object) -> str:
    content = json_bytes(asdict(value) if isinstance(value, TrackAPilotAuthorization) else value)
    content += b"\n"
    fixture.authorization_path.write_bytes(content)
    return sha256(content).hexdigest()


def _prospective_plan(affected: ExecutionProvenance, fixed: ExecutionProvenance):
    plan = make_track_a_plan(affected, fixed)
    return replace(
        plan,
        runs=tuple(
            replace(
                run,
                evaluation_config=replace(
                    run.evaluation_config,
                    environment_profile=TRACK_A_N05_ENVIRONMENT_PROFILE,
                ),
            )
            for run in plan.runs
        ),
    )


def _synthetic_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    failed_call: int | None = None,
    cleanup_status: str = "complete",
) -> SyntheticAdmission:
    host_root = tmp_path / "n05-host"
    authorization_path = tmp_path / "n05-authorization.json"
    package_paths = (tmp_path / "tar-7.5.2.tgz", tmp_path / "tar-7.5.3.tgz")
    monkeypatch.setattr(preflight, "HOST_LEDGER_ROOT", host_root)
    monkeypatch.setattr(preflight, "HOST_AUTHORIZATION_RECORD", authorization_path)
    monkeypatch.setattr(preflight, "HOST_PACKAGE_TARBALLS", package_paths)

    targets, contexts, packages, broker = n05_support._inputs(
        tmp_path, monkeypatch, failed_call=failed_call
    )
    linux_root = tmp_path / "evidence"
    outcome = n05_support.run_n05_preflight(
        linux_root,
        targets,
        contexts,
        packages,
        broker,
        repository=n05_support.ROOT,
        source=n05_support.SOURCE,
        environment=n05_support.ENVIRONMENT,
    )
    linux = verify_n05_preflight(linux_root, expected_raw_manifest_sha256=outcome.manifest_sha256)
    authorization_content = n05_support._AUTHORIZATION_CONTENT
    authorization_path.write_bytes(authorization_content)
    args = argparse.Namespace(
        authorization_record=authorization_path,
        controller="a" * 64,
        evidence=linux_root,
        host_ledger=host_root,
        image=[item.image_id for item in preflight.FROZEN_TARGETS],
        mode=preflight.MODE_ID,
        package_tarball=list(package_paths),
        volume=preflight.RUNTIME_VOLUME_NAME,
    )
    ledger = N05HostLedger(
        host_root,
        args,
        authorization_content,
        preflight.authorization_from_bytes(authorization_content),
    )
    ledger.owner = "b" * 32
    ledger.controller_id = "a" * 64
    ledger.controller_launched = True
    ledger.controller_stderr_capture_complete = True
    ledger.controller_stderr = b"synthetic controller stderr\n"
    ledger.cleanup_status = cleanup_status
    if cleanup_status == "failed":
        ledger.cleanup_errors = ["synthetic cleanup failure"]
    ledger.target_names.add("synthetic-target")
    ledger.linux_terminal = {
        "final_manifest_sha256": linux.final_manifest_sha256,
        "final_status": linux.final_manifest.final_status.value,
        "host_cleanup_pending": True,
        "independent_status": linux.verification.status.value,
        "pilot_authorized": False,
        "preflight_verdict": linux.verification.recomputed_verdict.value,
        "raw_manifest_sha256": outcome.manifest_sha256,
        "reader_returncode": 0,
    }
    ledger.finish(0, None)
    host_manifest_sha256 = sha256((host_root / "manifest.json").read_bytes()).hexdigest()

    output_root = tmp_path / "track-a-output"
    track_a_host_root = tmp_path / "track-a-host"
    protocol, _ = track_a.load_track_a_protocol()
    protocol["evidence"]["output_root"] = str(output_root)
    for value, frozen in zip(protocol["targets"], preflight.FROZEN_TARGETS, strict=True):
        value.update(
            image_id=frozen.image_id,
            lock_sha256=frozen.lock_sha256,
            package_tarball_sha256=frozen.package_tarball_sha256,
            platform_manifest_sha256=frozen.platform_manifest_sha256,
        )
    protocol_path = tmp_path / "track-a-protocol.json"
    protocol_path.write_bytes(json_bytes(protocol) + b"\n")
    monkeypatch.setattr(track_a, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(track_a, "AFFECTED_IMAGE_ID", preflight.FROZEN_TARGETS[0].image_id)
    monkeypatch.setattr(track_a, "FIXED_IMAGE_ID", preflight.FROZEN_TARGETS[1].image_id)
    monkeypatch.setattr(
        track_a,
        "AFFECTED_TARBALL_SHA256",
        preflight.FROZEN_TARGETS[0].package_tarball_sha256,
    )
    monkeypatch.setattr(
        track_a,
        "FIXED_TARBALL_SHA256",
        preflight.FROZEN_TARGETS[1].package_tarball_sha256,
    )
    _, protocol_sha256 = track_a.load_track_a_protocol(protocol_path)

    affected = ExecutionProvenance(
        n05_support.SOURCE,
        n05_support.ENVIRONMENT,
        targets[0].provenance,
        sentinel_provenance((SentinelSpec(),)),
        targets[0].capture_isolation(),
    )
    fixed = ExecutionProvenance(
        n05_support.SOURCE,
        n05_support.ENVIRONMENT,
        targets[1].provenance,
        sentinel_provenance((SentinelSpec(),)),
        targets[1].capture_isolation(),
    )
    plan = _prospective_plan(affected, fixed)
    serialized_plan_sha256 = write_record(tmp_path / "synthetic-plan.json", plan)
    assert track_a_plan_sha256(plan) == serialized_plan_sha256
    source_revision = n05_support.SOURCE.revision
    assert source_revision is not None
    resources = protocol["resource_limits"]
    pilot_resources = PilotResourceLimits(
        resources["memory_bytes"],
        resources["pids"],
        resources["open_files"],
        resources["file_size_bytes"],
        resources["tmpfs_bytes"],
        resources["shm_bytes"],
        resources["capture_bytes_per_stream"],
        broker.controller_memory_bytes,
        broker.controller_memory_swap_bytes,
        broker.controller_pids_limit,
        256 * 1024 * 1024,
    )
    pilot_targets = tuple(
        PilotTargetIdentity(
            PilotTargetRole(item.role.value),
            preflight.NODE_VERSION,
            item.tar_version,
            item.image_id,
            item.platform_manifest_sha256,
            item.package_tarball_sha256,
            item.lock_sha256,
            item.build_sha256,
            preflight.WORKER_SHA256,
        )
        for item in preflight.FROZEN_TARGETS
    )
    n05 = N05EvidenceBinding(
        preflight.ATTEMPT_ID,
        preflight.MODE_ID,
        str(host_root),
        str(linux_root),
        sha256(authorization_content).hexdigest(),
        host_manifest_sha256,
        linux.final_manifest_sha256,
        outcome.manifest_sha256,
        linux.verification_sha256,
        source_revision,
    )
    approval_reference = "synthetic-review://track-a-admission/unit-test"
    pilot = TrackAPilotAuthorization(
        schema_version=1,
        authorization_scope=PILOT_AUTHORIZATION_SCOPE,
        authorization_id="synthetic-track-a-pilot-authorization",
        decision=PILOT_DECISION,
        authorized_by="synthetic-reviewer-not-an-identity-proof",
        authorized_at="2026-10-22T00:00:00+00:00",
        approval_reference=approval_reference,
        human_review_statement=PILOT_HUMAN_REVIEW_STATEMENT,
        source_revision=source_revision,
        protocol_version=track_a.PROTOCOL_VERSION,
        protocol_config=ArtifactReference(
            track_a.PROTOCOL_CONFIG_RELATIVE.as_posix(), protocol_sha256
        ),
        repetition_plan_sha256=serialized_plan_sha256,
        campaigns=tuple(
            PilotCampaignCell(item.run_id, item.arm_id, item.random_seed)
            for item in track_a.TRACK_A_SCHEDULE
        ),
        total_campaigns=20,
        campaign_execution_budget=200,
        total_executions=4000,
        initial_case_ids=plan.runs[0].evaluation_config.initial_case_ids,
        seed_profile=track_a.SEED_PROFILE,
        campaign_rng_seeds=(9001, 9002, 9003, 9004, 9005),
        scheduling_rng_seed=4242,
        repetitions_per_arm=5,
        initial_seeds_in_budget=True,
        target_timeout_seconds=5.0,
        mutation_policy=MutationPolicy.M1_PROTECTED_COMPONENTS,
        feedback_projection=FeedbackProjection.FULL,
        oracle_contracts=(ContractId.C0, ContractId.C1, ContractId.C2),
        sentinels=affected.sentinels,
        sentinel_profile=track_a.SENTINEL_PROFILE,
        targets=pilot_targets,  # type: ignore[arg-type]
        controller_id=broker.controller_id,
        controller_image_id=broker.controller_image_id,
        host_docker_context=broker.context_name,
        daemon_id=broker.daemon_id,
        daemon_version=broker.daemon_version,
        daemon_api_version=broker.daemon_api_version,
        environment=n05_support.ENVIRONMENT,
        environment_profile=TRACK_A_N05_ENVIRONMENT_PROFILE,
        runtime_volume_name=broker.runtime_volume_name,
        runtime_root="/var/lib/inodefence",
        controller_isolation_profile=preflight.CONTROLLER_ISOLATION_PROFILE,
        target_isolation_profile=preflight.TARGET_ISOLATION_PROFILE,
        resource_limits=pilot_resources,
        campaign_watchdog_seconds=7200,
        sequential=True,
        fresh_controller_per_campaign=True,
        stop_conditions=PILOT_STOP_CONDITIONS,
        no_retry=True,
        resume_policy=PILOT_RESUME_POLICY,
        track_a_output_root=str(output_root),
        track_a_host_ledger_root=str(track_a_host_root),
        n05=n05,
    )
    pilot_path = tmp_path / "pilot-authorization.json"
    content = json_bytes(asdict(pilot)) + b"\n"
    pilot_path.write_bytes(content)
    return SyntheticAdmission(
        pilot,
        pilot_path,
        sha256(content).hexdigest(),
        approval_reference,
        protocol_path,
        host_root,
        linux_root,
        output_root,
        track_a_host_root,
    )


def _forbidden_spies(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("called")
        raise AssertionError("admission must not launch, execute, freeze, or claim")

    monkeypatch.setattr(track_a, "freeze_track_a_execution", forbidden)
    monkeypatch.setattr(PolicyRepetitionController, "claim", forbidden)
    monkeypatch.setattr(IsolatedTarget, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    return calls


def _validate(fixture: SyntheticAdmission):
    return validate_track_a_admission(
        pilot_authorization_path=fixture.authorization_path,
        expected_pilot_authorization_sha256=fixture.authorization_sha256,
        trusted_approval_reference=fixture.approval_reference,
        protocol_config_path=fixture.protocol_path,
    )


def _assert_unchanged(
    fixture: SyntheticAdmission,
    host_before: dict[str, bytes],
    linux_before: dict[str, bytes],
    calls: list[str],
) -> None:
    assert _tree_bytes(fixture.host_root) == host_before
    assert _tree_bytes(fixture.linux_root) == linux_before
    assert not fixture.output_root.exists()
    assert not fixture.track_a_host_root.exists()
    assert not list(fixture.output_root.parent.rglob("claim.json"))
    assert calls == []


def test_valid_synthetic_admission_reopens_every_binding_without_side_effects(
    tmp_path, monkeypatch
):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    verified = _validate(fixture)

    assert verified.pilot_authorization == fixture.authorization
    assert verified.pilot_authorization_sha256 == fixture.authorization_sha256
    assert verified.host.overall_status == "PREFLIGHT_PASS"
    assert verified.n05_preflight.final_manifest.final_status.value == "PREFLIGHT_PASS"
    assert verified.repetition_plan_sha256 == fixture.authorization.repetition_plan_sha256
    assert len(verified.repetition_plan.runs) == 20
    assert verified.pilot_authorization.resource_limits.controller_tmpfs_bytes == 256 * 1024 * 1024
    _assert_unchanged(fixture, host_before, linux_before, calls)


def test_controller_tmpfs_sub_mib_byte_mismatch_is_rejected(tmp_path, monkeypatch):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    changed = replace(
        fixture.authorization,
        resource_limits=replace(
            fixture.authorization.resource_limits,
            controller_tmpfs_bytes=(256 * 1024 * 1024) + 1,
        ),
    )
    digest = _write_authorization(fixture, changed)
    fixture = replace(fixture, authorization=changed, authorization_sha256=digest)
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError, match="exact MiB"):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


@pytest.mark.parametrize("case", ("arbitrary_digest", "approval_reference"))
def test_trusted_pilot_anchor_is_required(tmp_path, monkeypatch, case):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)
    kwargs = {
        "pilot_authorization_path": fixture.authorization_path,
        "expected_pilot_authorization_sha256": fixture.authorization_sha256,
        "trusted_approval_reference": fixture.approval_reference,
        "protocol_config_path": fixture.protocol_path,
    }
    if case == "arbitrary_digest":
        kwargs["expected_pilot_authorization_sha256"] = "a" * 64
    else:
        kwargs["trusted_approval_reference"] = "synthetic-review://wrong"

    with pytest.raises(ValueError):
        validate_track_a_admission(**kwargs)
    _assert_unchanged(fixture, host_before, linux_before, calls)


@pytest.mark.parametrize("case", ("missing_raw", "tampered_raw", "artifact_checksum"))
def test_missing_tampered_or_checksum_invalid_n05_raw_is_rejected(tmp_path, monkeypatch, case):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    if case == "missing_raw":
        (fixture.linux_root / "raw-manifest.json").unlink()
    elif case == "tampered_raw":
        path = fixture.linux_root / "raw-manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
    else:
        raw = json.loads((fixture.linux_root / "raw-manifest.json").read_bytes())
        readiness = raw["payload"]["value"]["readiness_runs"][0]["path"]
        path = fixture.linux_root / readiness
        path.write_bytes(path.read_bytes() + b" ")
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


@pytest.mark.parametrize("case", ("non_pass", "incomplete"))
def test_non_pass_or_incomplete_n05_evidence_is_rejected(tmp_path, monkeypatch, case):
    fixture = _synthetic_admission(
        tmp_path,
        monkeypatch,
        failed_call=2 if case == "non_pass" else None,
    )
    if case == "incomplete":
        (fixture.host_root / "terminal.json").unlink()
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


@pytest.mark.parametrize(
    "field",
    (
        "authorization_sha256",
        "host_manifest_sha256",
        "final_manifest_sha256",
        "raw_manifest_sha256",
        "independent_verification_sha256",
    ),
)
def test_host_linux_manifest_binding_mismatch_is_rejected(tmp_path, monkeypatch, field):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    changed_n05 = replace(fixture.authorization.n05, **{field: "f" * 64})
    changed = replace(fixture.authorization, n05=changed_n05)
    digest = _write_authorization(fixture, changed)
    fixture = replace(fixture, authorization=changed, authorization_sha256=digest)
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


@pytest.mark.parametrize("case", ("plan", "protocol", "output_root"))
def test_plan_protocol_or_output_binding_mismatch_is_rejected(tmp_path, monkeypatch, case):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    authorization = fixture.authorization
    if case == "plan":
        changed = replace(authorization, repetition_plan_sha256="f" * 64)
    elif case == "protocol":
        changed = replace(
            authorization,
            protocol_config=replace(authorization.protocol_config, sha256="f" * 64),
        )
    else:
        changed = replace(
            authorization,
            track_a_output_root=str(tmp_path / "other-track-a-output"),
        )
    digest = _write_authorization(fixture, changed)
    fixture = replace(fixture, authorization=changed, authorization_sha256=digest)
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


@pytest.mark.parametrize("case", ("cleanup_failed", "cleanup_record_missing"))
def test_cleanup_failure_or_missing_record_is_rejected(tmp_path, monkeypatch, case):
    fixture = _synthetic_admission(
        tmp_path,
        monkeypatch,
        cleanup_status="failed" if case == "cleanup_failed" else "complete",
    )
    if case == "cleanup_record_missing":
        (fixture.host_root / "terminal.json").unlink()
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


def test_source_sha_mismatch_is_rejected(tmp_path, monkeypatch):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    changed = replace(fixture.authorization, source_revision="f" * 40)
    digest = _write_authorization(fixture, changed)
    fixture = replace(fixture, authorization=changed, authorization_sha256=digest)
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


@pytest.mark.parametrize(
    "case",
    ("target", "controller", "controller_image", "daemon"),
)
def test_target_controller_image_or_daemon_mismatch_is_rejected(tmp_path, monkeypatch, case):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    authorization = fixture.authorization
    if case == "target":
        targets = (
            replace(authorization.targets[0], image_id="sha256:" + "f" * 64),
            *authorization.targets[1:],
        )
        changed = replace(authorization, targets=targets)
    elif case == "controller":
        changed = replace(authorization, controller_id="f" * 64)
    elif case == "controller_image":
        changed = replace(authorization, controller_image_id="sha256:" + "f" * 64)
    else:
        changed = replace(authorization, daemon_id="synthetic-other-daemon")
    digest = _write_authorization(fixture, changed)
    fixture = replace(fixture, authorization=changed, authorization_sha256=digest)
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


@pytest.mark.parametrize("case", ("timeout", "isolation", "environment", "resources"))
def test_timeout_isolation_environment_or_resource_mismatch_is_rejected(
    tmp_path, monkeypatch, case
):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    authorization = fixture.authorization
    if case == "timeout":
        value = asdict(authorization)
        value["target_timeout_seconds"] = 10.0
        digest = _write_authorization(fixture, value)
        fixture = replace(fixture, authorization_sha256=digest)
    elif case == "isolation":
        changed = replace(authorization, target_isolation_profile="other-isolation-v1")
    elif case == "environment":
        changed = replace(
            authorization,
            environment=replace(authorization.environment, machine="x86_64"),
        )
    else:
        changed = replace(
            authorization,
            resource_limits=replace(
                authorization.resource_limits,
                target_memory_bytes=authorization.resource_limits.target_memory_bytes + 1,
            ),
        )
    if case != "timeout":
        digest = _write_authorization(fixture, changed)
        fixture = replace(fixture, authorization=changed, authorization_sha256=digest)
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


def test_n04_binding_cannot_be_reused_as_n05(tmp_path, monkeypatch):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    n04_linux = tmp_path / "n04-linux-evidence"
    n04_host = tmp_path / "n04-host-ledger"
    n04_packages = [tmp_path / "n04-7.5.2.tgz", tmp_path / "n04-7.5.3.tgz"]
    n04_support._freeze_paths(monkeypatch, n04_linux, n04_host, n04_packages)
    n04_ledger = N04HostLedger(n04_host, n04_support._args(n04_linux, n04_packages))
    n04_ledger.owner = "c" * 32
    n04_ledger.controller_id = "c" * 64
    n04_ledger.target_names.add("synthetic-n04-target")
    n04_ledger.cleanup_status = "complete"
    n04_ledger.linux_terminal = n04_support._linux_terminal(n04_linux)
    n04_ledger.finish(0, None)
    n04_manifest_sha256 = sha256((n04_host / "manifest.json").read_bytes()).hexdigest()
    changed = replace(
        fixture.authorization,
        n05=replace(
            fixture.authorization.n05,
            attempt_id=n04_preflight.ATTEMPT_ID,
            mode_id="preflight-node-n04-5s",
            host_ledger_root=str(n04_host),
            linux_evidence_root=str(n04_linux),
            host_manifest_sha256=n04_manifest_sha256,
        ),
    )
    digest = _write_authorization(fixture, changed)
    fixture = replace(fixture, authorization=changed, authorization_sha256=digest)
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)
    n04_host_before, n04_linux_before = _tree_bytes(n04_host), _tree_bytes(n04_linux)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)
    assert _tree_bytes(n04_host) == n04_host_before
    assert _tree_bytes(n04_linux) == n04_linux_before


def test_n05_authorization_cannot_replace_pilot_authorization(tmp_path, monkeypatch):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    content = n05_support._AUTHORIZATION_CONTENT
    fixture.authorization_path.write_bytes(content)
    fixture = replace(fixture, authorization_sha256=sha256(content).hexdigest())
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        pilot_authorization_from_bytes(content)
    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


def test_missing_pilot_authorization_fails_closed(tmp_path, monkeypatch):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    fixture.authorization_path.unlink()
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)


@pytest.mark.parametrize("case", ("order", "seed", "budget"))
def test_campaign_order_seed_or_budget_mismatch_is_rejected(tmp_path, monkeypatch, case):
    fixture = _synthetic_admission(tmp_path, monkeypatch)
    value = asdict(fixture.authorization)
    if case == "order":
        campaigns = list(value["campaigns"])
        campaigns[0], campaigns[1] = campaigns[1], campaigns[0]
        value["campaigns"] = campaigns
    elif case == "seed":
        value["campaigns"][0]["random_seed"] = 9999
    else:
        value["campaign_execution_budget"] = 199
    digest = _write_authorization(fixture, value)
    fixture = replace(fixture, authorization_sha256=digest)
    calls = _forbidden_spies(monkeypatch)
    host_before, linux_before = _tree_bytes(fixture.host_root), _tree_bytes(fixture.linux_root)

    with pytest.raises(ValueError):
        _validate(fixture)
    _assert_unchanged(fixture, host_before, linux_before, calls)

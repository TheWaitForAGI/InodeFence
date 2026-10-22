"""Track A protocol/evidence checks; safe reference runs are engineering tests only."""

import subprocess
import sys
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

import pytest
from scripts import track_a_container_controller as controller_script
from scripts import track_a_container_host as host_script
from tests.evaluation import test_track_a_admission as admission_support

from inodefence.campaign import SearchCampaignConfig
from inodefence.evaluation import track_a_exploratory as track_a_module
from inodefence.evaluation.failure import ArtifactReference
from inodefence.evaluation.policy_repeated import PolicyRepetitionController
from inodefence.evaluation.policy_timing import run_timed_search_campaign
from inodefence.evaluation.storage import read_record, write_record
from inodefence.evaluation.track_a_admission import (
    TrackAAdmissionRecord,
    VerifiedTrackAAdmission,
)
from inodefence.evaluation.track_a_exploratory import (
    AFFECTED_IMAGE_ID,
    FIXED_IMAGE_ID,
    PROTOCOL_VERSION,
    TRACK_A_SCHEDULE,
    analyze_track_a,
    finalize_track_a_execution,
    freeze_track_a_execution,
    load_track_a_protocol,
    make_track_a_plan,
    nearest_rank_percentile,
    summarize_track_a_records,
    verify_track_a_final,
)
from inodefence.feedback import FeedbackProjection, SearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.model.isolation import ArtifactDigest, IsolationPolicy, IsolationProvenance
from inodefence.model.provenance import (
    EnvironmentProvenance,
    ExecutionProvenance,
    SourceProvenance,
    TargetProvenance,
)
from inodefence.mutator import MutationPolicy
from inodefence.provenance import sentinel_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.isolated import IsolatedTarget
from inodefence.targets.python_tarfile import PythonTarfileTarget


def _admitted_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = admission_support._synthetic_admission(tmp_path, monkeypatch)
    admission = admission_support._validate(fixture)
    affected = next(
        run.evaluation_config.provenance
        for run in admission.repetition_plan.runs
        if run.arm_id.startswith("affected-")
    )
    fixed = next(
        run.evaluation_config.provenance
        for run in admission.repetition_plan.runs
        if run.arm_id == "fixed-b3"
    )
    return fixture, admission, affected, fixed


def _freeze_admitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture, admission, affected, fixed = _admitted_fixture(tmp_path, monkeypatch)
    frozen = freeze_track_a_execution(
        fixture.output_root,
        affected,
        fixed,
        admission=admission,
        protocol_config_path=fixture.protocol_path,
    )
    return fixture, admission, affected, fixed, frozen


def _forbid_execution_side_effects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("called")
        raise AssertionError("admission failure must not claim, launch, or execute")

    monkeypatch.setattr(PolicyRepetitionController, "claim", forbidden)
    monkeypatch.setattr(IsolatedTarget, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    return calls


def _provenance(*, affected: bool = True) -> ExecutionProvenance:
    version = "7.5.2" if affected else "7.5.3"
    image = AFFECTED_IMAGE_ID if affected else FIXED_IMAGE_ID
    lock = (
        "31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243"
        if affected
        else "a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24"
    )
    isolation = IsolationProvenance(
        IsolationPolicy(image, 1000, 1000),
        "docker-compatible",
        "test-runtime",
        "test-api",
        "linux",
        "arm64",
        "arm64",
        artifacts=(
            ArtifactDigest("node-tar-package-lock", lock),
            ArtifactDigest(
                "node-tar-worker",
                "feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b",
            ),
        ),
        artifact_origin="image-identification-v1",
    )
    return ExecutionProvenance(
        SourceProvenance("a" * 40, False),
        EnvironmentProvenance("Linux", "test-kernel", "aarch64", "3.12.3"),
        TargetProvenance("node-tar-strict", f"node=22.22.0;tar={version}", 5.0),
        sentinel_provenance((SentinelSpec(),)),
        isolation,
    )


def test_static_protocol_and_exact_schedule_are_frozen():
    protocol, digest = load_track_a_protocol()
    assert len(digest) == 64
    assert protocol["protocol_version"] == PROTOCOL_VERSION
    assert protocol["authorization"]["pilot"] == "required-not-recorded"
    assert protocol["execution"]["total_campaigns"] == 20
    assert protocol["execution"]["total_executions"] == 4000
    assert [cell["run_id"] for cell in protocol["schedule"]] == [
        item.run_id for item in TRACK_A_SCHEDULE
    ]


def test_plan_reproduces_n03_order_and_exact_policy_cells():
    plan = make_track_a_plan(_provenance(), _provenance(affected=False))
    assert plan.protocol_version == PROTOCOL_VERSION
    assert [run.run_id for run in plan.runs] == [item.run_id for item in TRACK_A_SCHEDULE]
    assert [run.arm_id for run in plan.runs] == [item.arm_id for item in TRACK_A_SCHEDULE]
    assert [run.evaluation_config.campaign.random_seed for run in plan.runs] == [
        item.random_seed for item in TRACK_A_SCHEDULE
    ]
    assert all(run.evaluation_config.campaign.execution_budget == 200 for run in plan.runs)
    assert all(
        run.evaluation_config.campaign.mutation_policy == MutationPolicy.M1_PROTECTED_COMPONENTS
        and run.evaluation_config.campaign.feedback_projection == FeedbackProjection.FULL
        for run in plan.runs
    )
    assert {run.arm_id: run.evaluation_config.campaign.search_policy for run in plan.runs} == {
        "affected-b0": SearchPolicy.B0,
        "affected-b1": SearchPolicy.B1,
        "affected-b3": SearchPolicy.B3,
        "fixed-b3": SearchPolicy.B3,
    }
    assert all(
        run.evaluation_config.initial_case_ids
        == tuple(case.case_id for case in minimal_seed_corpus())
        for run in plan.runs
    )


@pytest.mark.parametrize(
    "changed",
    (
        lambda value: replace(value, target=replace(value.target, timeout_seconds=10.0)),
        lambda value: replace(
            value,
            isolation=replace(
                value.isolation,
                policy=replace(value.isolation.policy, uid=1001),
            ),
        ),
        lambda value: replace(value, source=SourceProvenance("a" * 40, True)),
    ),
)
def test_plan_rejects_timeout_isolation_or_clean_source_drift(changed):
    with pytest.raises(ValueError):
        make_track_a_plan(changed(_provenance()), _provenance(affected=False))


def test_record_summary_keeps_noops_statuses_curves_and_full_step_time():
    records = []
    config = SearchCampaignConfig(
        9001,
        8,
        SearchPolicy.B0,
        MutationPolicy.M1_PROTECTED_COMPONENTS,
        FeedbackProjection.FULL,
    )
    timed = run_timed_search_campaign(
        minimal_seed_corpus(),
        PythonTarfileTarget(),
        config,
        completed_record=records.append,
    )
    summary = summarize_track_a_records(tuple(records), timed.timing)
    assert summary["executions"] == 8
    assert summary["seed_executions"] == 4
    assert summary["mutation_attempts"] == 4
    assert sum(summary["mutation_operator_counts"].values()) == 4
    assert summary["mutation_applied"] + summary["mutation_noop"] == 4
    assert sum(summary["target_status_counts"].values()) == 8
    assert len(summary["state_signature_curve"]) == 8
    assert len(summary["violation_fingerprint_curve"]) == 8
    assert summary["full_step_seconds"]["count"] == 8
    assert summary["first_contract_observation_execution"] is None


def test_nearest_rank_p95_is_explicit_and_deterministic():
    assert nearest_rank_percentile((1.0,), 0.95) == 1.0
    assert nearest_rank_percentile(tuple(float(value) for value in range(1, 21)), 0.95) == 19.0
    with pytest.raises(ValueError):
        nearest_rank_percentile((), 0.95)
    with pytest.raises(ValueError):
        nearest_rank_percentile((1.0,), 0.0)


def test_verified_admission_freeze_read_and_raw_only_finalization(tmp_path, monkeypatch):
    fixture, _, _, _, frozen = _freeze_admitted(tmp_path, monkeypatch)
    root = fixture.output_root
    protocol_path = fixture.protocol_path

    assert frozen.admission.pilot_authorization == fixture.authorization
    assert frozen.manifest.pilot_authorization.name == "admission/pilot-authorization.json"
    assert frozen.manifest.admission_record.name == "admission/verified-admission.json"
    assert frozen.manifest.n05_evidence.name == "admission/n05-evidence-reference.json"
    assert (root / frozen.manifest.pilot_authorization.name).read_bytes() == (
        fixture.authorization_path.read_bytes()
    )
    assert all(slot.state.value == "pending" for slot in frozen.repetitions.slots)
    final_digest = finalize_track_a_execution(
        root,
        expected_execution_sha256=frozen.execution_sha256,
        stop_reason="unit-test-no-target-execution",
        protocol_config_path=protocol_path,
    )
    verified = verify_track_a_final(
        root,
        expected_final_manifest_sha256=final_digest,
        protocol_config_path=protocol_path,
    )
    assert verified.manifest.status.value == "stopped"
    assert verified.manifest.completed_campaigns == 0
    analysis = analyze_track_a(
        root,
        expected_final_manifest_sha256=final_digest,
        protocol_config_path=protocol_path,
    )
    assert analysis["evidence_stage"] == "RAW ONLY"
    assert analysis["arms"]["affected-b0"]["actual_executions"] == 0
    assert analysis["arms"]["affected-b0"]["campaign_completion_rate"] == 0


def test_reader_revalidates_after_output_root_exists_without_modifying_evidence(
    tmp_path, monkeypatch
):
    fixture, _, _, _, frozen = _freeze_admitted(tmp_path, monkeypatch)
    before = {
        "track_a": admission_support._tree_bytes(fixture.output_root),
        "host": admission_support._tree_bytes(fixture.host_root),
        "linux": admission_support._tree_bytes(fixture.linux_root),
    }

    reread = track_a_module.read_track_a_execution(
        fixture.output_root,
        expected_execution_sha256=frozen.execution_sha256,
        protocol_config_path=fixture.protocol_path,
    )

    assert reread.admission.pilot_authorization == fixture.authorization
    assert reread.repetitions.plan == frozen.repetitions.plan
    assert admission_support._tree_bytes(fixture.output_root) == before["track_a"]
    assert admission_support._tree_bytes(fixture.host_root) == before["host"]
    assert admission_support._tree_bytes(fixture.linux_root) == before["linux"]


def test_freeze_rejects_existing_output_without_overwrite_or_execution(tmp_path, monkeypatch):
    fixture, admission, affected, fixed = _admitted_fixture(tmp_path, monkeypatch)
    fixture.output_root.mkdir()
    marker = fixture.output_root / "existing"
    marker.write_bytes(b"preserve me")
    calls = _forbid_execution_side_effects(monkeypatch)

    with pytest.raises(ValueError, match="new output"):
        freeze_track_a_execution(
            fixture.output_root,
            affected,
            fixed,
            admission=admission,
            protocol_config_path=fixture.protocol_path,
        )

    assert marker.read_bytes() == b"preserve me"
    assert set(fixture.output_root.iterdir()) == {marker}
    assert calls == []


@pytest.mark.parametrize("case", ("missing", "tampered"))
def test_freeze_reopens_original_pilot_authorization(tmp_path, monkeypatch, case):
    fixture, admission, affected, fixed = _admitted_fixture(tmp_path, monkeypatch)
    if case == "missing":
        fixture.authorization_path.unlink()
    else:
        fixture.authorization_path.write_bytes(fixture.authorization_path.read_bytes() + b" ")
    calls = _forbid_execution_side_effects(monkeypatch)

    with pytest.raises(ValueError):
        freeze_track_a_execution(
            fixture.output_root,
            affected,
            fixed,
            admission=admission,
            protocol_config_path=fixture.protocol_path,
        )

    assert not fixture.output_root.exists()
    assert calls == []


@pytest.mark.parametrize("case", ("missing_root", "tampered_raw"))
def test_freeze_reopens_authoritative_n05_evidence(tmp_path, monkeypatch, case):
    fixture, admission, affected, fixed = _admitted_fixture(tmp_path, monkeypatch)
    if case == "missing_root":
        fixture.linux_root.rename(tmp_path / "removed-n05-linux-root")
    else:
        raw = fixture.linux_root / "raw-manifest.json"
        raw.write_bytes(raw.read_bytes() + b" ")
    calls = _forbid_execution_side_effects(monkeypatch)

    with pytest.raises(ValueError):
        freeze_track_a_execution(
            fixture.output_root,
            affected,
            fixed,
            admission=admission,
            protocol_config_path=fixture.protocol_path,
        )

    assert not fixture.output_root.exists()
    assert calls == []


@pytest.mark.parametrize("case", ("source", "image", "environment", "timeout", "isolation"))
def test_freeze_rejects_execution_provenance_mismatch(tmp_path, monkeypatch, case):
    fixture, admission, affected, fixed = _admitted_fixture(tmp_path, monkeypatch)
    if case == "source":
        affected = replace(affected, source=SourceProvenance("f" * 40, False))
    elif case == "image":
        assert affected.isolation is not None
        affected = replace(
            affected,
            isolation=replace(
                affected.isolation,
                policy=replace(affected.isolation.policy, image_id="sha256:" + "f" * 64),
            ),
        )
    elif case == "environment":
        affected = replace(affected, environment=replace(affected.environment, machine="x86_64"))
    elif case == "timeout":
        affected = replace(affected, target=replace(affected.target, timeout_seconds=10.0))
    else:
        assert affected.isolation is not None
        affected = replace(
            affected,
            isolation=replace(
                affected.isolation,
                policy=replace(affected.isolation.policy, uid=1001),
            ),
        )
    calls = _forbid_execution_side_effects(monkeypatch)

    with pytest.raises(ValueError):
        freeze_track_a_execution(
            fixture.output_root,
            affected,
            fixed,
            admission=admission,
            protocol_config_path=fixture.protocol_path,
        )

    assert not fixture.output_root.exists()
    assert calls == []


def test_freeze_rejects_protocol_change_after_admission(tmp_path, monkeypatch):
    fixture, admission, affected, fixed = _admitted_fixture(tmp_path, monkeypatch)
    fixture.protocol_path.write_bytes(fixture.protocol_path.read_bytes() + b" ")
    calls = _forbid_execution_side_effects(monkeypatch)

    with pytest.raises(ValueError):
        freeze_track_a_execution(
            fixture.output_root,
            affected,
            fixed,
            admission=admission,
            protocol_config_path=fixture.protocol_path,
        )

    assert not fixture.output_root.exists()
    assert calls == []


def test_manual_replaced_or_mutated_admission_cannot_freeze(tmp_path, monkeypatch):
    fixture, admission, affected, fixed = _admitted_fixture(tmp_path, monkeypatch)
    constructor = {
        item.name: getattr(admission, item.name)
        for item in fields(VerifiedTrackAAdmission)
        if item.init
    }
    manual = VerifiedTrackAAdmission(**constructor)
    replaced = replace(admission)
    object.__setattr__(admission, "repetition_plan_sha256", "f" * 64)
    calls = _forbid_execution_side_effects(monkeypatch)

    for untrusted in (manual, replaced, admission):
        with pytest.raises(ValueError, match="exact live validator result|changed before freeze"):
            freeze_track_a_execution(
                fixture.output_root,
                affected,
                fixed,
                admission=untrusted,
                protocol_config_path=fixture.protocol_path,
            )

    assert not fixture.output_root.exists()
    assert calls == []


def test_digest_only_freeze_inputs_cannot_bypass_admission(tmp_path, monkeypatch):
    fixture, _, affected, fixed = _admitted_fixture(tmp_path, monkeypatch)
    calls = _forbid_execution_side_effects(monkeypatch)
    legacy_freeze: Any = freeze_track_a_execution

    with pytest.raises(TypeError):
        legacy_freeze(
            fixture.output_root,
            affected,
            fixed,
            preflight_manifest_sha256="a" * 64,
            resource_authorization_sha256="b" * 64,
            protocol_config_path=fixture.protocol_path,
        )

    assert not fixture.output_root.exists()
    assert calls == []


@pytest.mark.parametrize("entrypoint", ("host", "controller"))
def test_digest_only_prepare_entrypoints_fail_before_launch(tmp_path, monkeypatch, entrypoint):
    evidence = tmp_path / "track-a-output"
    common = [
        "--controller",
        "a" * 64,
        "--volume",
        "inodefence-runtime",
        "--image",
        AFFECTED_IMAGE_ID,
        "--image",
        FIXED_IMAGE_ID,
        "--evidence",
        str(evidence),
        "--preflight-manifest-sha256",
        "b" * 64,
        "--resource-authorization-sha256",
        "c" * 64,
        "prepare",
    ]
    if entrypoint == "host":
        module = host_script
        arguments = [
            "track-a-host",
            "--context",
            "synthetic-context",
            "--controller-worktree",
            "/workspaces/InodeFence-track-a-unit-test",
            *common,
        ]
    else:
        module = controller_script
        arguments = ["track-a-controller", "--owner", "synthetic-owner", *common]
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("called")
        raise AssertionError("digest-only prepare must fail before controller launch")

    monkeypatch.setattr(sys, "argv", arguments)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(SystemExit):
        module.main()

    assert calls == []
    assert not evidence.exists()


@pytest.mark.parametrize("entrypoint", ("host", "controller"))
def test_unconnected_run_cell_entrypoints_fail_before_launch(tmp_path, monkeypatch, entrypoint):
    evidence = tmp_path / "track-a-output"
    common = [
        "--controller",
        "a" * 64,
        "--volume",
        "inodefence-runtime",
        "--image",
        AFFECTED_IMAGE_ID,
        "--image",
        FIXED_IMAGE_ID,
        "--evidence",
        str(evidence),
        "--run-index",
        "0",
        "--execution-sha256",
        "d" * 64,
        "run-cell",
    ]
    if entrypoint == "host":
        module = host_script
        arguments = [
            "track-a-host",
            "--context",
            "synthetic-context",
            "--controller-worktree",
            "/workspaces/InodeFence-track-a-unit-test",
            *common,
        ]
    else:
        module = controller_script
        arguments = ["track-a-controller", "--owner", "synthetic-owner", *common]
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("called")
        raise AssertionError("unconnected run-cell must fail before controller launch")

    monkeypatch.setattr(sys, "argv", arguments)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(SystemExit):
        module.main()

    assert calls == []
    assert not evidence.exists()


@pytest.mark.parametrize(
    "relative",
    (
        "admission/pilot-authorization.json",
        "admission/verified-admission.json",
        "admission/n05-evidence-reference.json",
        "repetitions/plan.json",
    ),
)
@pytest.mark.parametrize("case", ("missing", "tampered"))
def test_reader_rejects_missing_or_tampered_local_admission_and_plan(
    tmp_path, monkeypatch, relative, case
):
    fixture, _, _, _, frozen = _freeze_admitted(tmp_path, monkeypatch)
    path = fixture.output_root / relative
    if case == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b" ")
    before = admission_support._tree_bytes(fixture.output_root)

    with pytest.raises(ValueError):
        track_a_module.read_track_a_execution(
            fixture.output_root,
            expected_execution_sha256=frozen.execution_sha256,
            protocol_config_path=fixture.protocol_path,
        )

    assert admission_support._tree_bytes(fixture.output_root) == before


def test_reader_rejects_recalculated_admission_manifest_binding(tmp_path, monkeypatch):
    fixture, _, _, _, frozen = _freeze_admitted(tmp_path, monkeypatch)
    admission_path = fixture.output_root / "admission/verified-admission.json"
    record = read_record(
        admission_path,
        TrackAAdmissionRecord,
        expected_sha256=frozen.manifest.admission_record.sha256,
    )
    admission_path.unlink()
    changed_admission_sha256 = write_record(
        admission_path,
        replace(record, approval_reference="synthetic-review://changed-retained-binding"),
    )
    execution_path = fixture.output_root / "execution.json"
    execution_path.unlink()
    changed_execution_sha256 = write_record(
        execution_path,
        replace(
            frozen.manifest,
            admission_record=ArtifactReference(
                "admission/verified-admission.json", changed_admission_sha256
            ),
        ),
    )
    before = admission_support._tree_bytes(fixture.output_root)

    with pytest.raises(ValueError, match="approval|admission"):
        track_a_module.read_track_a_execution(
            fixture.output_root,
            expected_execution_sha256=changed_execution_sha256,
            protocol_config_path=fixture.protocol_path,
        )

    assert admission_support._tree_bytes(fixture.output_root) == before


@pytest.mark.parametrize("case", ("missing_host", "tampered_linux", "non_pass_binding"))
def test_reader_rejects_missing_tampered_or_nonpass_n05_originals(tmp_path, monkeypatch, case):
    fixture, _, _, _, frozen = _freeze_admitted(tmp_path, monkeypatch)
    if case == "missing_host":
        (fixture.host_root / "manifest.json").unlink()
    elif case == "tampered_linux":
        raw = fixture.linux_root / "raw-manifest.json"
        raw.write_bytes(raw.read_bytes() + b" ")
    else:
        terminal = fixture.host_root / "terminal.json"
        terminal.write_bytes(terminal.read_bytes().replace(b"PREFLIGHT_PASS", b"PREFLIGHT_FAIL"))
    track_a_before = admission_support._tree_bytes(fixture.output_root)

    with pytest.raises(ValueError):
        track_a_module.read_track_a_execution(
            fixture.output_root,
            expected_execution_sha256=frozen.execution_sha256,
            protocol_config_path=fixture.protocol_path,
        )

    assert admission_support._tree_bytes(fixture.output_root) == track_a_before

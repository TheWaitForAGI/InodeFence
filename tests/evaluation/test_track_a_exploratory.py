"""Track A protocol/evidence checks; safe reference runs are engineering tests only."""

import json
from dataclasses import replace

import pytest

from inodefence.campaign import SearchCampaignConfig
from inodefence.evaluation import track_a_exploratory as track_a_module
from inodefence.evaluation.policy_timing import run_timed_search_campaign
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
from inodefence.targets.python_tarfile import PythonTarfileTarget


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


def test_unrun_frozen_plan_finalizes_as_raw_only_not_pass(tmp_path, monkeypatch):
    root = tmp_path / "track-a-evidence"
    protocol_path = tmp_path / "protocol.json"
    protocol, _ = load_track_a_protocol()
    protocol["evidence"]["output_root"] = str(root)
    protocol_path.write_text(json.dumps(protocol), encoding="ascii")
    monkeypatch.setattr(track_a_module, "OUTPUT_ROOT", root)

    frozen = freeze_track_a_execution(
        root,
        _provenance(),
        _provenance(affected=False),
        preflight_manifest_sha256="b" * 64,
        resource_authorization_sha256="c" * 64,
        protocol_config_path=protocol_path,
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

"""Unit provenance/admission contracts; this test double is not real isolation evidence."""

import json
from contextlib import contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.execution.base import BackendError, ContainerOutcome, ExecutionBackend
from inodefence.experiment_config import (
    FEEDBACK_POLICY,
    MUTATION_POLICY,
    SEED_PROFILE,
    ExperimentConfig,
    run_configured_campaign,
)
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ExecutionResult, ExecutionStatus, canonical_json
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance, ResourcePolicy
from inodefence.model.provenance import TargetProvenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.isolated import IsolatedTarget

IMAGE = "sha256:" + "a" * 64


@dataclass(frozen=True)
class Invocation:
    artifacts: tuple = ()
    image_id: str = IMAGE
    provenance: TargetProvenance = TargetProvenance("controlled", "1.2.3", 5)

    def command(self, archive_path: Path, extraction_root: Path):
        return ("controlled-helper",)

    def classify(self, outcome, command):
        return ExecutionResult(
            "controlled", "1.2.3", command, ExecutionStatus.SUCCESS, 0, "", "", 0, 5
        )


class ControlledBackend(ExecutionBackend):
    resources = ResourcePolicy()

    def policy(self, image_id):
        return IsolationPolicy(image_id, 1000, 1000, self.resources)

    def capture_isolation(self, image_id):
        return IsolationProvenance(
            self.policy(image_id), "test-double", "test", "test", "linux", "test", "test"
        )

    def validate_image(self, image_id):
        assert image_id == IMAGE

    @contextmanager
    def prepare(self, request):
        class Prepared:
            def execute(self):
                return ContainerOutcome(0, b"", b"", 0, False)

        yield Prepared()


def test_contained_campaign_admission_uses_enforced_wrapper():
    target = IsolatedTarget(Invocation(), ControlledBackend())
    result = run_campaign(minimal_seed_corpus(), target, CampaignConfig(11, 4))
    assert len(result.steps) == 4
    assert result.provenance.target == target.provenance


def config(target):
    return ExperimentConfig(
        target.provenance,
        SEED_PROFILE,
        tuple(case.case_id for case in minimal_seed_corpus()),
        CampaignConfig(11, 4),
        MUTATION_POLICY,
        FEEDBACK_POLICY,
        (SentinelSpec(),),
        "linux-container-benign-v1",
        target.isolation_policy,
    )


def test_frozen_before_execution_and_export_ignores_changed_backend_defaults(tmp_path, monkeypatch):
    backend = ControlledBackend()
    target = IsolatedTarget(Invocation(), backend)
    configured = config(target)
    from inodefence.provenance import freeze_provenance

    events = []

    def freeze(*args, **kwargs):
        events.append("freeze")
        return freeze_provenance(*args, **kwargs)

    original_prepare = backend.prepare

    @contextmanager
    def prepare(request):
        assert events == ["freeze"]
        with original_prepare(request) as prepared:
            yield prepared

    monkeypatch.setattr("inodefence.campaign.freeze_provenance", freeze)
    monkeypatch.setattr(backend, "prepare", prepare)
    result = run_configured_campaign(configured, minimal_seed_corpus(), target)
    assert result.provenance.isolation is not None
    assert result.provenance.isolation.policy == configured.isolation
    assert result.experiment_config_id == configured.config_id
    backend.resources = replace(backend.resources, pids=32)

    def forbidden(*args, **kwargs):
        raise AssertionError("export must never query execution mechanism")

    monkeypatch.setattr(backend, "capture_isolation", forbidden)
    manifest, steps = export_campaign(result, tmp_path / "export")
    value = json.loads(manifest.read_bytes())
    assert value["schema_version"] == 3
    assert value["execution_provenance"]["isolation"]["policy"]["resources"]["pids"] == 64
    assert value["steps_sha256"] == sha256(steps.read_bytes()).hexdigest()
    assert json.loads(canonical_json(result.provenance))["schema_version"] == 2
    assert json.loads(canonical_json(result))["schema_version"] == 2
    assert json.loads(canonical_json(result.steps[0]))["schema_version"] == 1


def test_policy_config_roundtrip_and_reference_v1_compatibility():
    target = IsolatedTarget(Invocation(), ControlledBackend())
    configured = config(target)
    assert json.loads(configured.to_json())["schema_version"] == 2
    assert ExperimentConfig.from_json(configured.to_json()) == configured
    assert (
        ExperimentConfig.from_json(json.dumps(json.loads(configured.to_json()), indent=2)).config_id
        == configured.config_id
    )
    reference = ExperimentConfig.from_json(
        Path("experiments/configs/reference-smoke-v1.json").read_text()
    )
    assert json.loads(reference.to_json())["schema_version"] == 1
    assert reference.config_id == "5a24679b4a55f55fa20272e8817c9fd8f7d97fc994495c964d2b37f0967863a0"


@pytest.mark.parametrize("field", ResourcePolicy.__dataclass_fields__)
def test_each_resource_bound_changes_config_identity(field):
    target = IsolatedTarget(Invocation(), ControlledBackend())
    configured = config(target)
    limits = replace(
        target.isolation_policy.resources,
        **{field: getattr(target.isolation_policy.resources, field) * 2},
    )
    assert (
        replace(configured, isolation=replace(target.isolation_policy, resources=limits)).config_id
        != configured.config_id
    )


@pytest.mark.parametrize(
    "change",
    (
        {"image_id": "sha256:" + "b" * 64},
        {"uid": 1001},
        {"gid": 1001},
        {"shm_bytes": 8 * 1024 * 1024},
        {"capture_bytes_per_stream": 512 * 1024},
    ),
)
def test_content_and_execution_policy_change_config_identity(change):
    configured = config(IsolatedTarget(Invocation(), ControlledBackend()))
    assert configured.isolation is not None
    assert (
        replace(configured, isolation=replace(configured.isolation, **change)).config_id
        != configured.config_id
    )


@pytest.mark.parametrize("field", IsolationPolicy.__dataclass_fields__)
def test_all_policy_fields_required_in_v2_json(field):
    configured = config(IsolatedTarget(Invocation(), ControlledBackend()))
    raw = json.loads(configured.to_json())
    del raw["isolation"][field]
    with pytest.raises(ValueError):
        ExperimentConfig.from_json(json.dumps(raw))


@pytest.mark.parametrize(
    "changes",
    (
        {"network_policy": "bridge"},
        {"rootfs_mode": "writable"},
        {"uid": 0},
        {"gid": 0},
        {"cap_drop": ()},
        {"no_new_privileges": False},
        {"pid_namespace": "host"},
        {"schema_version": True},
    ),
)
def test_unsupported_or_weakened_policy_rejected(changes):
    with pytest.raises(ValueError):
        replace(IsolationPolicy(IMAGE, 1000, 1000), **changes)


def test_configuration_mismatch_precedes_execution_freeze_and_runtime(monkeypatch):
    target = IsolatedTarget(Invocation(), ControlledBackend())
    configured = config(target)

    def forbidden(*args, **kwargs):
        raise AssertionError("mismatch must precede capture/runtime/first case")

    monkeypatch.setattr("inodefence.campaign.freeze_provenance", forbidden)
    monkeypatch.setattr("inodefence.pipeline.disposable_sandbox", forbidden)
    for policy in (
        None,
        replace(target.isolation_policy, image_id="sha256:" + "b" * 64),
        replace(target.isolation_policy, resources=ResourcePolicy(pids=32)),
    ):
        with pytest.raises(ValueError, match="isolation configuration"):
            run_configured_campaign(
                replace(configured, isolation=policy), minimal_seed_corpus(), target
            )


def test_unavailable_backend_rejects_before_campaign_setup(monkeypatch):
    target = IsolatedTarget(Invocation(), ControlledBackend())

    def unavailable(*args):
        raise BackendError("runtime unavailable")

    def forbidden(*args, **kwargs):
        raise AssertionError("unavailable boundary must precede campaign setup")

    monkeypatch.setattr(target.backend, "capture_isolation", unavailable)
    monkeypatch.setattr("inodefence.campaign.freeze_provenance", forbidden)
    monkeypatch.setattr("inodefence.pipeline.disposable_sandbox", forbidden)
    with pytest.raises(BackendError, match="unavailable"):
        run_campaign(minimal_seed_corpus(), target, CampaignConfig(11, 4))


def test_subclass_cannot_replace_enforced_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("bypass must never execute or freeze")

    bypass = type("Bypass", (IsolatedTarget,), {"run": forbidden})(
        Invocation(), ControlledBackend()
    )
    monkeypatch.setattr("inodefence.campaign.freeze_provenance", forbidden)
    with pytest.raises(ValueError, match="requires execution isolation"):
        run_campaign(minimal_seed_corpus(), bypass, CampaignConfig(11, 4))


def test_policy_drift_stops_before_next_case(monkeypatch):
    backend = ControlledBackend()
    target = IsolatedTarget(Invocation(), backend)
    original = backend.prepare
    calls = []

    @contextmanager
    def changed(request):
        calls.append(request)
        with original(request) as prepared:
            yield prepared
        backend.resources = ResourcePolicy(pids=32)

    monkeypatch.setattr(backend, "prepare", changed)
    with pytest.raises(ValueError, match="isolation configuration changed"):
        run_campaign(minimal_seed_corpus(), target, CampaignConfig(11, 4))
    assert len(calls) == 1


def test_supplied_provenance_cannot_omit_or_rewrite_actual_policy():
    from inodefence.provenance import freeze_provenance

    target = IsolatedTarget(Invocation(), ControlledBackend())
    frozen = freeze_provenance(target.provenance, (SentinelSpec(),))
    with pytest.raises(ValueError, match="must match"):
        run_campaign(minimal_seed_corpus(), target, CampaignConfig(11, 4), provenance=frozen)
    actual = replace(frozen, isolation=target.capture_isolation())
    result = run_campaign(minimal_seed_corpus(), target, CampaignConfig(11, 4), provenance=actual)
    assert result.provenance is actual


def test_bare_requirement_or_provenance_attribute_cannot_certify_execution(monkeypatch):
    target = IsolatedTarget(Invocation(), ControlledBackend())

    class Bare:
        provenance = target.provenance
        isolation = target.capture_isolation()

        def run(self, archive_path, extraction_root) -> ExecutionResult:
            raise AssertionError("attribute certification must not bypass execution")

    with pytest.raises(ValueError, match="requires execution isolation"):
        run_campaign(minimal_seed_corpus(), Bare(), CampaignConfig(11, 4))


def test_wrapper_cannot_downgrade_requirement():
    from inodefence.model.provenance import ExecutionSafety

    with pytest.raises(ValueError, match="cannot downgrade"):
        IsolatedTarget(
            replace(
                Invocation(),
                provenance=replace(
                    Invocation().provenance, execution_safety=ExecutionSafety.TRUSTED_REFERENCE
                ),
            ),
            ControlledBackend(),
        )


def test_unknown_resource_fields_and_incomplete_resource_policy_rejected():
    configured = config(IsolatedTarget(Invocation(), ControlledBackend()))
    original = json.loads(configured.to_json())
    for changed in ({}, original["isolation"]["resources"] | {"unknown": 1}):
        raw = json.loads(configured.to_json())
        raw["isolation"]["resources"] = changed
        with pytest.raises(ValueError):
            ExperimentConfig.from_json(json.dumps(raw))


def test_subclass_cannot_downgrade_requirement_and_replace_preparation(monkeypatch):
    from inodefence.model.provenance import ExecutionSafety

    def forbidden(*args, **kwargs):
        raise AssertionError("subclass must not bypass contained execution")

    downgraded = replace(
        Invocation().provenance, execution_safety=ExecutionSafety.TRUSTED_REFERENCE
    )
    bypass = type(
        "Downgrade",
        (IsolatedTarget,),
        {
            "__post_init__": lambda self: None,
            "provenance": property(lambda self: downgraded),
            "prepare": forbidden,
        },
    )(Invocation(), ControlledBackend())
    monkeypatch.setattr("inodefence.campaign.freeze_provenance", forbidden)
    with pytest.raises(ValueError, match="requires execution isolation"):
        run_campaign(minimal_seed_corpus(), bypass, CampaignConfig(11, 4))


def test_backend_cannot_attest_a_different_image_than_invocation():
    class WrongImage(ControlledBackend):
        def policy(self, image_id):
            return IsolationPolicy("sha256:" + "b" * 64, 1000, 1000)

    target = IsolatedTarget(Invocation(), WrongImage())
    with pytest.raises(ValueError, match="image identity"):
        run_campaign(minimal_seed_corpus(), target, CampaignConfig(11, 4))


@pytest.mark.parametrize("timeout", (None, 121))
def test_isolated_descriptor_timeout_must_be_bounded_before_runtime(timeout):
    with pytest.raises(ValueError, match="bounded timeout"):
        IsolatedTarget(
            replace(
                Invocation(), provenance=replace(Invocation().provenance, timeout_seconds=timeout)
            ),
            ControlledBackend(),
        )

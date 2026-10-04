"""Portable invocation contracts; real fixture cases live in the explicit container suite."""

import json
from contextlib import contextmanager
from dataclasses import replace

import pytest

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.execution.base import (
    BackendError,
    ContainerOutcome,
    ExecutionBackend,
    OutputLimitError,
)
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance, ResourcePolicy
from inodefence.model.provenance import ExecutionSafety
from inodefence.runtime import SentinelSpec, runtime_root
from inodefence.targets.isolated import IsolatedTarget
from inodefence.targets.node_tar import NodeTarTarget

IMAGE = "sha256:" + "a" * 64
META = {
    "node_version": "22.22.0",
    "tar_version": "7.5.22",
    "worker_sha256": "b" * 64,
    "package_lock_sha256": "c" * 64,
}


class ControlledBackend(ExecutionBackend):
    """Test double, never evidence that a real runtime enforces containment."""

    outcome = ContainerOutcome(0, b"", b"", 0.5, False)

    resources = ResourcePolicy()

    def policy(self, image_id):
        return IsolationPolicy(image_id, 1000, 1000, self.resources)

    def capture_isolation(self, image_id):
        return IsolationProvenance(
            self.policy(image_id), "controlled-test-double", "test", "test", "linux", "test", "test"
        )

    def validate_image(self, image_id):
        assert image_id == IMAGE

    @contextmanager
    def prepare(self, request):
        backend = self

        class Prepared:
            def execute(self):
                if "--identify" in request.command:
                    return ContainerOutcome(0, json.dumps(META).encode(), b"", 0, False)
                return backend.outcome

        yield Prepared()


def target(timeout: float = 10):
    return NodeTarTarget.bind(ControlledBackend(), IMAGE, timeout)


def test_exact_discovered_versions_and_fixed_safety_requirement():
    bound = target(3.5)
    assert isinstance(bound.invocation, NodeTarTarget)
    assert bound.invocation.node_version == "22.22.0"
    assert bound.invocation.tar_version == "7.5.22"
    assert bound.provenance.target_version == "node=22.22.0;tar=7.5.22"
    assert bound.provenance.timeout_seconds == 3.5
    assert bound.provenance.execution_safety == ExecutionSafety.ISOLATION_REQUIRED
    with pytest.raises(ValueError, match="requires execution isolation"):
        run_campaign(minimal_seed_corpus(), bound.invocation, CampaignConfig(1, 4))  # type: ignore[arg-type]


@pytest.mark.parametrize("configured", (False, True))
def test_node_campaign_paths_reject_before_freeze_or_runtime(configured, monkeypatch):
    from inodefence.experiment_config import (
        FEEDBACK_POLICY,
        MUTATION_POLICY,
        SEED_PROFILE,
        ExperimentConfig,
        run_configured_campaign,
    )

    bound = target()
    seeds = minimal_seed_corpus()
    budget = CampaignConfig(11, 8)
    existing = set(runtime_root().iterdir())

    def forbidden(*args, **kwargs):
        raise AssertionError("Node campaign rejection must precede execution setup")

    monkeypatch.setattr("inodefence.campaign.freeze_provenance", forbidden)
    monkeypatch.setattr("inodefence.pipeline.disposable_sandbox", forbidden)
    monkeypatch.setattr(IsolatedTarget, "run", forbidden)

    class Uncontained:
        provenance = bound.provenance

        def run(self, archive_path, extraction_root) -> ExecutionResult:
            raise AssertionError("uncontained target must never execute")

    uncontained = Uncontained()
    with pytest.raises(ValueError, match="requires execution isolation"):
        if configured:
            config = ExperimentConfig(
                bound.provenance,
                SEED_PROFILE,
                tuple(case.case_id for case in seeds),
                budget,
                MUTATION_POLICY,
                FEEDBACK_POLICY,
                (SentinelSpec(),),
                "linux-development-v1",
            )
            run_configured_campaign(config, seeds, uncontained)
        else:
            run_campaign(seeds, uncontained, budget)
    assert set(runtime_root().iterdir()) == existing


def test_version_discovery_is_mockable_and_invalid_identity_rejected(monkeypatch):
    monkeypatch.setattr(
        "inodefence.targets.node_tar._identify", lambda *args: META | {"tar_version": "1.2.3"}
    )
    discovered = target().invocation
    assert isinstance(discovered, NodeTarTarget)
    assert discovered.tar_version == "1.2.3"
    monkeypatch.setattr(
        "inodefence.targets.node_tar._identify", lambda *args: META | {"node_version": "latest"}
    )
    with pytest.raises(ValueError, match="version"):
        target()


def test_invalid_timeout_and_missing_backend_rejected():
    with pytest.raises(ValueError):
        target(True)
    with pytest.raises(ValueError, match="ExecutionBackend"):
        NodeTarTarget.bind(None, IMAGE)  # type: ignore[arg-type]


def test_backend_unavailable_precedes_runtime_creation(monkeypatch):
    class Unavailable(ControlledBackend):
        def validate_image(self, image_id):
            raise BackendError("image unavailable")

    def forbidden(*args, **kwargs):
        raise AssertionError("unavailable boundary must precede runtime")

    monkeypatch.setattr("inodefence.targets.isolated.disposable_sandbox", forbidden)
    with pytest.raises(BackendError, match="unavailable"):
        NodeTarTarget.bind(Unavailable(), IMAGE)


@pytest.mark.parametrize(
    "exit_code,status",
    (
        (None, ExecutionStatus.TIMED_OUT),
        (1, ExecutionStatus.FAILED),
        (2, ExecutionStatus.REJECTED),
        (0, ExecutionStatus.SUCCESS),
    ),
)
def test_status_and_streams_preserved(sandbox, exit_code, status):
    bound = target()
    assert isinstance(bound.backend, ControlledBackend)
    bound.backend.outcome = ContainerOutcome(exit_code, b"output\xff", b"error", 0.5, False)
    result = bound.run(sandbox.archive_path, sandbox.extraction_root)
    assert result.status == status
    assert result.stdout == "output\udcff" and result.stderr == "error"
    assert result.duration_seconds == 0.5


def test_layout_rejection_precedes_backend_invocation(sandbox, monkeypatch):
    bound = target()

    def forbidden(*args, **kwargs):
        raise AssertionError("bad harness paths must never execute")

    monkeypatch.setattr(bound.backend, "prepare", forbidden)
    with pytest.raises(ValueError, match="layout"):
        bound.run(sandbox.archive_path, sandbox.root)


def test_output_limit_aborts_incomplete_evidence_with_bounded_prefix(sandbox):
    bound = target()
    assert isinstance(bound.backend, ControlledBackend)
    bound.backend.outcome = ContainerOutcome(0, b"prefix", b"", 1, True)
    with pytest.raises(OutputLimitError) as caught:
        bound.run(sandbox.archive_path, sandbox.extraction_root)
    assert caught.value.outcome.stdout == b"prefix"


def test_descriptor_has_no_direct_process_execution_or_safety_override():
    bound = target()
    assert isinstance(bound.invocation, NodeTarTarget)
    assert not hasattr(bound.invocation, "run")
    with pytest.raises(TypeError):
        replace(bound.invocation, execution_safety=ExecutionSafety.TRUSTED_REFERENCE)


@pytest.mark.parametrize("change", ({"timeout_seconds": True}, {"image_id": "latest"}))
def test_invalid_binding_configuration_precedes_identity_execution(change, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid configuration must not allocate runtime or identify")

    monkeypatch.setattr("inodefence.targets.node_tar._identify", forbidden)
    with pytest.raises(ValueError):
        NodeTarTarget.bind(
            ControlledBackend(), **({"image_id": IMAGE, "timeout_seconds": 10} | change)
        )


@pytest.mark.parametrize("configured", (False, True))
@pytest.mark.parametrize("construction", ("direct", "replace", "other-image"))
def test_cr001_audit_declarations_cannot_be_frozen_as_observed_artifacts(
    configured, construction, monkeypatch
):
    """Converted frozen audit witness; metadata execution is a benign test double."""
    from inodefence.experiment_config import (
        FEEDBACK_POLICY,
        MUTATION_POLICY,
        SEED_PROFILE,
        ExperimentConfig,
        run_configured_campaign,
    )

    class TwoImages(ControlledBackend):
        def validate_image(self, image_id):
            assert image_id in (IMAGE, "sha256:" + "d" * 64)

        @contextmanager
        def prepare(self, request):
            assert "--identify" in request.command, "no archive may execute"
            metadata = META if request.image_id == IMAGE else META | {"worker_sha256": "e" * 64}

            class Prepared:
                def execute(self):
                    return ContainerOutcome(0, json.dumps(metadata).encode(), b"", 0, False)

            yield Prepared()

    backend = TwoImages()
    descriptor = NodeTarTarget(IMAGE, "22.22.0", "7.5.22", "d" * 64, "e" * 64)
    if construction != "direct":
        descriptor = NodeTarTarget.bind(backend, IMAGE).invocation
        assert isinstance(descriptor, NodeTarTarget)
        descriptor = replace(
            descriptor,
            **(
                {"image_id": "sha256:" + "d" * 64}
                if construction == "other-image"
                else {"worker_sha256": "d" * 64, "package_lock_sha256": "e" * 64}
            ),
        )
    target = IsolatedTarget(descriptor, backend)

    def forbidden(*args, **kwargs):
        raise AssertionError("false artifact declarations must fail before freeze/first case")

    monkeypatch.setattr("inodefence.campaign.freeze_provenance", forbidden)
    monkeypatch.setattr("inodefence.campaign.run_case", forbidden)
    seeds = minimal_seed_corpus()
    budget = CampaignConfig(11, 4)
    config = ExperimentConfig(
        target.provenance,
        SEED_PROFILE,
        tuple(case.case_id for case in seeds),
        budget,
        MUTATION_POLICY,
        FEEDBACK_POLICY,
        (SentinelSpec(),),
        "test-double-v1",
        target.isolation_policy,
    )
    with pytest.raises(BackendError, match="identity changed"):
        if configured:
            run_configured_campaign(config, seeds, target)
        else:
            run_campaign(seeds, target, budget)


@pytest.mark.parametrize(
    "field", ("worker_sha256", "package_lock_sha256", "node_version", "tar_version")
)
def test_cr001_each_false_identity_declaration_rejects_standalone_execution(sandbox, field):
    bound = target()
    assert isinstance(bound.invocation, NodeTarTarget)
    value = "0" * 64 if field.endswith("sha256") else "99.0.0"
    changed = IsolatedTarget(replace(bound.invocation, **{field: value}), bound.backend)
    with pytest.raises(BackendError, match="identity changed"):
        changed.run(sandbox.archive_path, sandbox.extraction_root)


def test_cr001_verified_origin_survives_configured_freeze_and_manifest_export(
    tmp_path, monkeypatch
):
    """Synthetic backend observations, not a claim of real container validation."""
    from inodefence.campaign_export import export_campaign
    from inodefence.experiment_config import (
        FEEDBACK_POLICY,
        MUTATION_POLICY,
        SEED_PROFILE,
        ExperimentConfig,
        run_configured_campaign,
    )

    bound = target()
    seeds = minimal_seed_corpus()
    config = ExperimentConfig(
        bound.provenance,
        SEED_PROFILE,
        tuple(case.case_id for case in seeds),
        CampaignConfig(11, 4),
        MUTATION_POLICY,
        FEEDBACK_POLICY,
        (SentinelSpec(),),
        "test-double-v1",
        bound.isolation_policy,
    )
    result = run_configured_campaign(config, seeds, bound)
    assert result.provenance.isolation is not None
    assert result.provenance.isolation.artifact_origin == "image-identification-v1"
    assert result.provenance.isolation.artifacts == bound.invocation.artifacts
    assert result.provenance.isolation.policy.image_id == IMAGE

    def forbidden(*args, **kwargs):
        raise AssertionError("export must preserve frozen observations without reidentification")

    monkeypatch.setattr(bound.backend, "prepare", forbidden)
    manifest, _ = export_campaign(
        result, tmp_path / "evidence", experiment_config_json=config.to_json()
    )
    value = json.loads(manifest.read_bytes())
    isolation = value["execution_provenance"]["isolation"]
    assert value["schema_version"] == 4
    assert value["experiment_config_id"] == config.config_id
    assert isolation["artifact_origin"] == "image-identification-v1"
    assert isolation["artifacts"] == [
        {"name": "node-tar-package-lock", "sha256": META["package_lock_sha256"]},
        {"name": "node-tar-worker", "sha256": META["worker_sha256"]},
    ]


@pytest.mark.parametrize("metadata", (b"{}", b"[]", b"invalid-json"))
def test_cr001_invalid_probe_metadata_fails_closed(metadata):
    bound = target()
    with pytest.raises(BackendError, match="invalid identity metadata"):
        bound.invocation.verify_identity(metadata)

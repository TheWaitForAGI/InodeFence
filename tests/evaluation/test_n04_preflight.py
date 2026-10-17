"""N04 preflight orchestration tests use controlled adapters, never historical packages."""

import json
import os
import tarfile
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

import inodefence.evaluation.n04_preflight as preflight
from inodefence.evaluation.encoding import json_bytes
from inodefence.evaluation.failure import read_failure
from inodefence.evaluation.n04_preflight import (
    EXPECTED_BUILD_FILES,
    N04BrokerAttestation,
    N04BrokerImage,
    N04BuildContext,
    N04BuildFile,
    N04ControllerMount,
    N04PackageTarball,
    N04PreflightRole,
    N04PreflightStatus,
    N04PreflightVerdict,
    run_n04_preflight,
)
from inodefence.evaluation.n04_preflight_reader import (
    N04FinalManifest,
    N04FinalStatus,
    N04IndependentStatus,
    N04IndependentVerification,
    verify_n04_preflight,
)
from inodefence.evaluation.node_packaging import prepare_node_release, validate_node_release
from inodefence.evaluation.storage import read_record
from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance
from inodefence.model.provenance import EnvironmentProvenance, SourceProvenance
from inodefence.targets.node_tar import NodeTarTarget

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ROOT / "experiments" / "benchmarks" / "locks"
SOURCE = SourceProvenance("a" * 40, False)
ENVIRONMENT = EnvironmentProvenance("Linux", "controlled", "aarch64", "3.12.3")


class ControlledTarget:
    """Node-shaped test double with direct controlled benign extraction."""

    def __init__(
        self,
        role: N04PreflightRole,
        *,
        timeout_seconds: float = 5.0,
        failed_call: int | None = None,
    ) -> None:
        frozen = preflight.frozen_target(role)
        self.role = role
        self.invocation = NodeTarTarget(
            frozen.image_id,
            "22.22.0",
            frozen.tar_version,
            preflight.WORKER_SHA256,
            frozen.lock_sha256,
            timeout_seconds,
        )
        self.failed_call = failed_call
        self.calls = 0

    @property
    def provenance(self):
        return self.invocation.provenance

    def capture_isolation(self):
        return IsolationProvenance(
            IsolationPolicy(self.invocation.image_id, 1000, 1000),
            "docker-compatible",
            "29.8.2",
            "1.56",
            "linux",
            "arm64",
            "arm64",
            artifacts=self.invocation.artifacts,
            artifact_origin="image-identification-v1",
        )

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        call = self.calls
        self.calls += 1
        if self.failed_call == call:
            return self._result(ExecutionStatus.TIMED_OUT, None, "controlled timeout")
        with tarfile.open(archive_path, mode="r:") as archive:
            for member in archive.getmembers():
                destination = extraction_root / member.name.rstrip("/")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if member.isdir():
                    destination.mkdir(exist_ok=True)
                    destination.chmod(member.mode)
                elif member.isfile():
                    stream = archive.extractfile(member)
                    assert stream is not None
                    destination.write_bytes(stream.read())
                    destination.chmod(member.mode)
                elif member.issym():
                    os.symlink(member.linkname, destination)
                elif member.islnk():
                    os.link(extraction_root / member.linkname, destination)
                else:
                    raise AssertionError("unexpected controlled TAR member")
        return self._result(ExecutionStatus.SUCCESS, 0, "")

    def _result(
        self, status: ExecutionStatus, exit_code: int | None, stderr: str
    ) -> ExecutionResult:
        return ExecutionResult(
            self.provenance.target_id,
            self.provenance.target_version,
            ("controlled-node-tar", self.role),
            status,
            exit_code,
            "",
            stderr,
            0.001,
            self.invocation.timeout_seconds,
        )


def _context(tmp_path: Path, role: N04PreflightRole, image_id: str) -> N04BuildContext:
    frozen = preflight.frozen_target(role)
    directory = tmp_path / f"context-{role.value}"
    prepare_node_release(
        LOCKS / f"node-tar-{frozen.tar_version}.package-lock.json",
        directory,
        repository=ROOT,
    )
    packaging = validate_node_release(directory)
    build = {
        "format": "inodefence-node-image-build",
        "schema_version": 1,
        "image_id": image_id,
        "image_architecture": "arm64",
        "packaging_sha256": sha256((directory / "packaging.json").read_bytes()).hexdigest(),
        "tar_version": frozen.tar_version,
        "node_version": "22.22.0",
        "files_sha256": packaging["files_sha256"],
        "stdout": "controlled build",
        "stderr": f"exporting manifest sha256:{frozen.platform_manifest_sha256}",
    }
    (directory / "build.json").write_bytes(json_bytes(build) + b"\n")
    return N04BuildContext(
        role,
        tuple(N04BuildFile(name, (directory / name).read_bytes()) for name in EXPECTED_BUILD_FILES),
    )


def _inputs(tmp_path: Path, monkeypatch, *, failed_call: int | None = None):
    images = ("sha256:" + "1" * 64, "sha256:" + "2" * 64)
    package_contents = (b"controlled tar 7.5.2\n", b"controlled tar 7.5.3\n")
    contexts = (
        _context(tmp_path, N04PreflightRole.AFFECTED, images[0]),
        _context(tmp_path, N04PreflightRole.FIXED, images[1]),
    )
    patched = tuple(
        replace(
            target,
            image_id=images[index],
            package_tarball_sha256=sha256(package_contents[index]).hexdigest(),
            build_sha256=sha256(
                next(item.content for item in contexts[index].files if item.name == "build.json")
            ).hexdigest(),
        )
        for index, target in enumerate(preflight.FROZEN_TARGETS)
    )
    monkeypatch.setattr(preflight, "FROZEN_TARGETS", patched)
    monkeypatch.setattr(preflight, "EVIDENCE_ROOT", tmp_path / "evidence")
    packages = (
        N04PackageTarball(N04PreflightRole.AFFECTED, package_contents[0]),
        N04PackageTarball(N04PreflightRole.FIXED, package_contents[1]),
    )
    targets = (
        ControlledTarget(N04PreflightRole.AFFECTED),
        ControlledTarget(N04PreflightRole.FIXED, failed_call=failed_call),
    )
    broker = N04BrokerAttestation(
        "/usr/local/bin/docker",
        "orbstack",
        "2026-10-16T12:05:00+00:00",
        "controlled-daemon",
        "orbstack",
        "29.8.2",
        "1.56",
        "linux",
        "arm64",
        "a" * 64,
        "sha256:" + "3" * 64,
        "2026-10-16T12:00:00+00:00",
        True,
        False,
        "v1",
        "none",
        True,
        (),
        ("ALL",),
        ("no-new-privileges",),
        0,
        1024 * 1024 * 1024,
        1024 * 1024 * 1024,
        256,
        (("/tmp", "rw,nosuid,nodev,size=268435456"),),
        (
            N04ControllerMount("volume", "inodefence-runtime", "/var/lib/inodefence", True),
            N04ControllerMount("bind", "/controlled/source", "/workspaces/InodeFence", False),
        ),
        "inodefence-runtime",
        "/var/lib/docker/volumes/inodefence-runtime/_data",
        (
            N04BrokerImage(images[0], "linux", "arm64", ()),
            N04BrokerImage(images[1], "linux", "arm64", ()),
        ),
        1800,
    )
    return targets, contexts, packages, broker


def test_complete_preflight_is_independently_recomputed(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"
    outcome = run_n04_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N04PreflightStatus.COMPLETE, tuple(
        read_failure(evidence / item.path).exception_message for item in outcome.manifest.failures
    )
    assert outcome.manifest.declared_verdict == N04PreflightVerdict.PASS
    assert outcome.manifest.extractions_started == outcome.manifest.extractions_completed == 8
    assert all(
        read_record(
            evidence / item.path,
            preflight.N04ReadinessRecord,
        ).arm.result.execution.timeout_seconds
        == 5
        for item in outcome.manifest.readiness_runs
    )
    verified = verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N04IndependentStatus.PASS, (
        verified.verification.diagnostics
    )
    assert verified.verification.recomputed_verdict == N04PreflightVerdict.PASS
    assert verified.final_manifest.final_status == N04FinalStatus.PREFLIGHT_PASS
    assert verified.final_manifest.pilot_authorized is False
    assert (
        verified.verification.verified_admissions,
        verified.verification.verified_oracle_controls,
        verified.verification.verified_readiness_runs,
        verified.verification.verified_failures,
    ) == (2, 2, 8, 0)


def test_complete_timeout_is_retained_as_preflight_fail(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch, failed_call=2)
    evidence = tmp_path / "evidence"
    outcome = run_n04_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N04PreflightStatus.READINESS_FAILED
    assert outcome.manifest.declared_verdict == N04PreflightVerdict.FAIL
    assert len(outcome.manifest.readiness_runs) == 8
    verified = verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N04IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N04PreflightVerdict.FAIL
    assert verified.final_manifest.final_status == N04FinalStatus.PREFLIGHT_FAIL


def test_wrong_timeout_stops_before_archive_and_is_inconclusive(tmp_path, monkeypatch):
    _, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    targets = (
        ControlledTarget(N04PreflightRole.AFFECTED, timeout_seconds=10),
        ControlledTarget(N04PreflightRole.FIXED),
    )
    evidence = tmp_path / "evidence"
    outcome = run_n04_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N04PreflightStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert len(outcome.manifest.failures) == 1
    verified = verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N04IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N04PreflightVerdict.INCONCLUSIVE
    assert verified.final_manifest.final_status == N04FinalStatus.PREFLIGHT_INCONCLUSIVE


def test_broker_runtime_mismatch_stops_before_archive(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"

    outcome = run_n04_preflight(
        evidence,
        targets,
        contexts,
        packages,
        replace(broker, daemon_version="29.9.0"),
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N04PreflightStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert not outcome.manifest.admissions
    verified = verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N04IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N04PreflightVerdict.INCONCLUSIVE


def test_partial_build_failure_is_retained_and_independently_reconstructed(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    bad_file = replace(contexts[0].files[0], content=b"invalid controlled Dockerfile\n")
    bad_context = replace(contexts[0], files=(bad_file, *contexts[0].files[1:]))
    evidence = tmp_path / "evidence"

    outcome = run_n04_preflight(
        evidence,
        targets,
        (bad_context, contexts[1]),
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N04PreflightStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert len(outcome.manifest.build_files) == len(EXPECTED_BUILD_FILES)
    verified = verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N04IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N04PreflightVerdict.INCONCLUSIVE
    assert verified.final_manifest.final_status == N04FinalStatus.PREFLIGHT_INCONCLUSIVE


def test_package_digest_mismatch_stops_before_build_and_is_reconstructed(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    packages = (replace(packages[0], content=b"wrong package bytes\n"), packages[1])
    evidence = tmp_path / "evidence"

    outcome = run_n04_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N04PreflightStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert len(outcome.manifest.package_tarballs) == 1
    assert not outcome.manifest.build_files
    verified = verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N04IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N04PreflightVerdict.INCONCLUSIVE


def test_wrong_environment_architecture_stops_before_package_and_is_reconstructed(
    tmp_path, monkeypatch
):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"

    outcome = run_n04_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=replace(ENVIRONMENT, machine="x86_64"),
    )

    assert outcome.manifest.extractions_started == 0
    assert not outcome.manifest.package_tarballs
    verified = verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N04IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N04PreflightVerdict.INCONCLUSIVE


def test_alternate_evidence_root_is_rejected_before_creation(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    alternate = tmp_path / "alternate"

    with pytest.raises(ValueError, match="evidence root"):
        run_n04_preflight(
            alternate,
            targets,
            contexts,
            packages,
            broker,
            repository=ROOT,
            source=SOURCE,
            environment=ENVIRONMENT,
        )

    assert not alternate.exists()
    assert all(target.calls == 0 for target in targets)


def test_completed_control_is_published_before_later_control_failure(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)

    def fail_positive_control(create_alias: bool):
        if create_alias:
            raise RuntimeError("controlled positive-control failure")
        return preflight._oracle_control(False)

    evidence = tmp_path / "evidence"
    outcome = run_n04_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
        create_control=fail_positive_control,
    )

    assert outcome.manifest.attempt_status == N04PreflightStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert len(outcome.manifest.oracle_controls) == 1
    failure = read_failure(evidence / outcome.manifest.failures[0].path)
    assert {item.name for item in failure.context.artifacts} >= {
        outcome.manifest.contract.path,
        outcome.manifest.oracle_controls[0].path,
    }
    verified = verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N04IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N04PreflightVerdict.INCONCLUSIVE


def test_reader_rejects_tampered_readiness_record(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"
    outcome = run_n04_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )
    run_path = evidence / outcome.manifest.readiness_runs[0].path
    record = json.loads(run_path.read_text())
    record["payload"]["value"]["runtime_root_absent_after_return"] = False
    run_path.write_bytes(json_bytes(record) + b"\n")

    verified = verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N04IndependentStatus.FAIL
    assert verified.final_manifest.final_status == N04FinalStatus.INDEPENDENT_VERIFICATION_FAILED


def test_broker_attestation_rejects_docker_socket(tmp_path, monkeypatch):
    _, _, _, broker = _inputs(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="boundary"):
        replace(
            broker,
            controller_mounts=tuple(
                sorted(
                    broker.controller_mounts
                    + (
                        N04ControllerMount(
                            "bind",
                            "/var/run/docker.sock",
                            "/var/run/docker.sock",
                            True,
                        ),
                    ),
                    key=lambda item: item.destination,
                )
            ),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("controller_network_mode", "bridge"),
        ("controller_readonly_rootfs", False),
        ("controller_cap_drop", ()),
        ("controller_memory_bytes", 0),
        ("controller_pids_limit", 0),
        ("controller_label", "unexpected"),
    ),
)
def test_broker_attestation_rejects_weakened_controller(tmp_path, monkeypatch, field, value):
    _, _, _, broker = _inputs(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="authorized preflight"):
        replace(broker, **{field: value})


def test_broker_attestation_rejects_writable_source_and_stale_controller(tmp_path, monkeypatch):
    _, _, _, broker = _inputs(tmp_path, monkeypatch)
    writable_mounts = tuple(
        replace(item, read_write=True) if item.destination == "/workspaces/InodeFence" else item
        for item in broker.controller_mounts
    )

    with pytest.raises(ValueError, match="boundary"):
        replace(broker, controller_mounts=writable_mounts)
    with pytest.raises(ValueError, match="not fresh"):
        replace(broker, broker_started_at="2026-10-16T13:00:01+00:00")


def test_invalid_broker_attestation_is_retained_before_target_admission(tmp_path, monkeypatch):
    targets, contexts, packages, _ = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"

    def invalid_broker():
        raise ValueError("controlled broker boundary mismatch")

    outcome = run_n04_preflight(
        evidence,
        targets,
        contexts,
        packages,
        invalid_broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.broker is None
    assert outcome.manifest.extractions_started == 0
    assert all(target.calls == 0 for target in targets)
    verified = verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N04IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N04PreflightVerdict.INCONCLUSIVE


def test_final_manifest_round_trip_has_no_pilot_authorization(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"
    outcome = run_n04_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )
    verify_n04_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    verification = read_record(
        evidence / "independent-verification.json", N04IndependentVerification
    )
    final = read_record(evidence / "manifest.json", N04FinalManifest)
    assert verification.status == N04IndependentStatus.PASS
    assert final.pilot_authorized is False

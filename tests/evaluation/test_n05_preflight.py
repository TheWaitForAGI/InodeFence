"""N05 preflight orchestration tests use controlled adapters, never historical packages."""

import argparse
import json
import os
import tarfile
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

import pytest
from scripts import container_host
from scripts.container_host import N05HostLedger, verify_n05_host_ledger

import inodefence.evaluation.n05_preflight as preflight
from inodefence.evaluation.encoding import json_bytes
from inodefence.evaluation.failure import read_failure
from inodefence.evaluation.n05_preflight import (
    EXPECTED_BUILD_FILES,
    N05AuthorizedFile,
    N05BrokerAttestation,
    N05BrokerImage,
    N05BuildContext,
    N05BuildFile,
    N05ControllerMount,
    N05PackageTarball,
    N05PreflightAuthorization,
    N05PreflightRole,
    N05PreflightStatus,
    N05PreflightVerdict,
)
from inodefence.evaluation.n05_preflight import (
    run_n05_preflight as _run_n05_preflight,
)
from inodefence.evaluation.n05_preflight_reader import (
    N05FinalManifest,
    N05FinalStatus,
    N05IndependentStatus,
    N05IndependentVerification,
    read_n05_preflight,
    verify_n05_preflight,
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
_AUTHORIZATION_CONTENT = b""


def run_n05_preflight(evidence, targets, contexts, packages, broker, **kwargs):
    return _run_n05_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        _AUTHORIZATION_CONTENT,
        **kwargs,
    )


class ControlledTarget:
    """Node-shaped test double with direct controlled benign extraction."""

    def __init__(
        self,
        role: N05PreflightRole,
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


def test_consumed_runner_rejects_before_evidence_creation(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    monkeypatch.setattr(preflight, "EVIDENCE_ROOT", evidence)
    monkeypatch.setattr(preflight, "ATTEMPT_CONSUMED", True)

    with pytest.raises(RuntimeError, match="attempt is consumed"):
        run_n05_preflight(
            evidence,
            (),  # type: ignore[arg-type]
            (),  # type: ignore[arg-type]
            (),  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            repository=ROOT,
        )
    assert not evidence.exists()


def _context(tmp_path: Path, role: N05PreflightRole, image_id: str) -> N05BuildContext:
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
    return N05BuildContext(
        role,
        tuple(N05BuildFile(name, (directory / name).read_bytes()) for name in EXPECTED_BUILD_FILES),
    )


def _inputs(tmp_path: Path, monkeypatch, *, failed_call: int | None = None):
    global _AUTHORIZATION_CONTENT
    monkeypatch.setattr(preflight, "ATTEMPT_CONSUMED", False)
    images = ("sha256:" + "1" * 64, "sha256:" + "2" * 64)
    package_contents = (b"controlled tar 7.5.2\n", b"controlled tar 7.5.3\n")
    contexts = (
        _context(tmp_path, N05PreflightRole.AFFECTED, images[0]),
        _context(tmp_path, N05PreflightRole.FIXED, images[1]),
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
    monkeypatch.setattr(preflight, "CONTROLLER_IMAGE_ID", "sha256:" + "3" * 64)
    authorization = N05PreflightAuthorization(
        1,
        "n05-five-second-preflight-v2-attempt-001-human-authorization",
        "AUTHORIZE_ONE_N05_BENIGN_PREFLIGHT_ATTEMPT",
        preflight.ATTEMPT_ID,
        preflight.MODE_ID,
        "controlled-human-reviewer",
        "2026-10-19T00:00:00+00:00",
        "I authorize exactly one N05 benign preflight attempt; no pilot or campaign.",
        SOURCE.revision,  # type: ignore[arg-type]
        tuple(
            N05AuthorizedFile(path, sha256((ROOT / path).read_bytes()).hexdigest())
            for path in sorted(preflight.AUTHORIZED_EXECUTABLE_PATHS)
        ),
        "a" * 64,
        preflight.CONTROLLER_IMAGE_ID,
        patched,  # type: ignore[arg-type]
        "orbstack",
        "controlled-daemon",
        "29.8.2",
        "1.56",
        preflight.HOST_SOURCE_WORKTREE,
        str(preflight.EVIDENCE_ROOT),
        str(preflight.HOST_LEDGER_ROOT),
        preflight.RUNTIME_VOLUME_NAME,
        5.0,
        8,
        1800,
        preflight.CONTROLLER_ISOLATION_PROFILE,
        preflight.TARGET_ISOLATION_PROFILE,
        True,
        False,
    )
    _AUTHORIZATION_CONTENT = json_bytes(asdict(authorization)) + b"\n"
    packages = (
        N05PackageTarball(N05PreflightRole.AFFECTED, package_contents[0]),
        N05PackageTarball(N05PreflightRole.FIXED, package_contents[1]),
    )
    targets = (
        ControlledTarget(N05PreflightRole.AFFECTED),
        ControlledTarget(N05PreflightRole.FIXED, failed_call=failed_call),
    )
    broker = N05BrokerAttestation(
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
        "v2",
        "none",
        True,
        (),
        ("ALL",),
        ("no-new-privileges",),
        0,
        0,
        0,
        "",
        "private",
        "private",
        1024 * 1024 * 1024,
        1024 * 1024 * 1024,
        256,
        (("/tmp", "rw,nosuid,nodev,size=256m"),),
        (
            N05ControllerMount(
                "volume", preflight.RUNTIME_VOLUME_NAME, "/var/lib/inodefence", True
            ),
            N05ControllerMount(
                "bind",
                preflight.HOST_SOURCE_WORKTREE,
                "/workspaces/InodeFence",
                False,
            ),
        ),
        preflight.RUNTIME_VOLUME_NAME,
        "2026-10-16T12:00:00+00:00",
        "local",
        "local",
        "v2",
        (),
        f"/var/lib/docker/volumes/{preflight.RUNTIME_VOLUME_NAME}/_data",
        ("a" * 64,),
        (
            N05BrokerImage(images[0], "linux", "arm64", ()),
            N05BrokerImage(images[1], "linux", "arm64", ()),
        ),
        1800,
    )
    return targets, contexts, packages, broker


def test_complete_preflight_is_independently_recomputed(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"
    outcome = run_n05_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N05PreflightStatus.COMPLETE, tuple(
        read_failure(evidence / item.path).exception_message for item in outcome.manifest.failures
    )
    assert outcome.manifest.declared_verdict == N05PreflightVerdict.PASS
    assert outcome.manifest.extractions_started == outcome.manifest.extractions_completed == 8
    assert all(
        read_record(
            evidence / item.path,
            preflight.N05ReadinessRecord,
        ).arm.result.execution.timeout_seconds
        == 5
        for item in outcome.manifest.readiness_runs
    )
    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.PASS, (
        verified.verification.diagnostics
    )
    assert verified.verification.recomputed_verdict == N05PreflightVerdict.PASS
    assert verified.final_manifest.final_status == N05FinalStatus.PREFLIGHT_PASS
    assert verified.final_manifest.pilot_authorized is False
    assert verified.final_manifest.host_cleanup_pending is True
    assert (
        verified.verification.verified_admissions,
        verified.verification.verified_oracle_controls,
        verified.verification.verified_readiness_runs,
        verified.verification.verified_failures,
    ) == (2, 2, 8, 0)
    reread = read_n05_preflight(
        evidence, expected_final_manifest_sha256=verified.final_manifest_sha256
    )
    assert reread.final_manifest.final_status == N05FinalStatus.PREFLIGHT_PASS


def test_authorization_record_is_content_validated_before_evidence_creation(tmp_path, monkeypatch):
    _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"
    malformed = json.loads(_AUTHORIZATION_CONTENT)
    malformed["target_timeout_seconds"] = 10.0
    content = json_bytes(malformed) + b"\n"

    with pytest.raises(ValueError, match="authorization"):
        _run_n05_preflight(
            evidence,
            (),  # type: ignore[arg-type]
            (),  # type: ignore[arg-type]
            (),  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            content,
            repository=ROOT,
        )
    assert not evidence.exists()


def test_complete_timeout_is_retained_as_preflight_fail(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch, failed_call=2)
    evidence = tmp_path / "evidence"
    outcome = run_n05_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N05PreflightStatus.READINESS_FAILED
    assert outcome.manifest.declared_verdict == N05PreflightVerdict.FAIL
    assert len(outcome.manifest.readiness_runs) == 8
    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N05PreflightVerdict.FAIL
    assert verified.final_manifest.final_status == N05FinalStatus.PREFLIGHT_FAIL


def test_wrong_timeout_stops_before_archive_and_is_inconclusive(tmp_path, monkeypatch):
    _, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    targets = (
        ControlledTarget(N05PreflightRole.AFFECTED, timeout_seconds=10),
        ControlledTarget(N05PreflightRole.FIXED),
    )
    evidence = tmp_path / "evidence"
    outcome = run_n05_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N05PreflightStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert len(outcome.manifest.failures) == 1
    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N05PreflightVerdict.INCONCLUSIVE
    assert verified.final_manifest.final_status == N05FinalStatus.PREFLIGHT_INCONCLUSIVE


def test_broker_runtime_mismatch_stops_before_archive(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"

    outcome = run_n05_preflight(
        evidence,
        targets,
        contexts,
        packages,
        replace(broker, daemon_version="29.9.0"),
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N05PreflightStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert not outcome.manifest.admissions
    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N05PreflightVerdict.INCONCLUSIVE


def test_partial_build_failure_is_retained_and_independently_reconstructed(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    bad_file = replace(contexts[0].files[0], content=b"invalid controlled Dockerfile\n")
    bad_context = replace(contexts[0], files=(bad_file, *contexts[0].files[1:]))
    evidence = tmp_path / "evidence"

    outcome = run_n05_preflight(
        evidence,
        targets,
        (bad_context, contexts[1]),
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N05PreflightStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert len(outcome.manifest.build_files) == len(EXPECTED_BUILD_FILES)
    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N05PreflightVerdict.INCONCLUSIVE
    assert verified.final_manifest.final_status == N05FinalStatus.PREFLIGHT_INCONCLUSIVE


def test_package_digest_mismatch_stops_before_build_and_is_reconstructed(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    packages = (replace(packages[0], content=b"wrong package bytes\n"), packages[1])
    evidence = tmp_path / "evidence"

    outcome = run_n05_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N05PreflightStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert len(outcome.manifest.package_tarballs) == 1
    assert not outcome.manifest.build_files
    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N05PreflightVerdict.INCONCLUSIVE


def test_wrong_environment_architecture_stops_before_package_and_is_reconstructed(
    tmp_path, monkeypatch
):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"

    outcome = run_n05_preflight(
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
    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N05PreflightVerdict.INCONCLUSIVE


def test_alternate_evidence_root_is_rejected_before_creation(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    alternate = tmp_path / "alternate"

    with pytest.raises(ValueError, match="evidence root"):
        run_n05_preflight(
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
    outcome = run_n05_preflight(
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

    assert outcome.manifest.attempt_status == N05PreflightStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert len(outcome.manifest.oracle_controls) == 1
    failure = read_failure(evidence / outcome.manifest.failures[0].path)
    assert {item.name for item in failure.context.artifacts} >= {
        outcome.manifest.contract.path,
        outcome.manifest.oracle_controls[0].path,
    }
    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N05PreflightVerdict.INCONCLUSIVE


def test_reader_rejects_tampered_readiness_record(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"
    outcome = run_n05_preflight(
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

    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.FAIL
    assert verified.final_manifest.final_status == N05FinalStatus.INDEPENDENT_VERIFICATION_FAILED


def test_reader_rejects_same_directory_symlink_artifact(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"
    outcome = run_n05_preflight(
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
    alias = run_path.with_name("unreferenced-copy.json")
    alias.write_bytes(run_path.read_bytes())
    run_path.unlink()
    run_path.symlink_to(alias.name)

    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.FAIL
    assert "symlink" in verified.verification.diagnostics[0]


def test_broker_attestation_rejects_docker_socket(tmp_path, monkeypatch):
    _, _, _, broker = _inputs(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="boundary"):
        replace(
            broker,
            controller_mounts=tuple(
                sorted(
                    broker.controller_mounts
                    + (
                        N05ControllerMount(
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
        ("docker_executable", "/tmp/unapproved-docker"),
        ("controller_network_mode", "bridge"),
        ("controller_readonly_rootfs", False),
        ("controller_cap_drop", ()),
        ("controller_device_request_count", 1),
        ("controller_device_cgroup_rule_count", 1),
        ("controller_pid_mode", "host"),
        ("controller_ipc_mode", "host"),
        ("controller_cgroupns_mode", "host"),
        ("controller_memory_bytes", 0),
        ("controller_pids_limit", 0),
        ("controller_label", "unexpected"),
        ("runtime_volume_driver", "unexpected"),
        ("runtime_volume_scope", "global"),
        ("runtime_volume_label", "unexpected"),
        ("runtime_volume_options", (("unexpected", "1"),)),
        ("runtime_volume_container_ids", ("b" * 64,)),
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
    with pytest.raises(ValueError, match="not fresh"):
        replace(broker, runtime_volume_created_at="2026-10-16T11:00:00+00:00")


def test_invalid_broker_attestation_is_retained_before_target_admission(tmp_path, monkeypatch):
    targets, contexts, packages, _ = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"

    def invalid_broker():
        raise ValueError("controlled broker boundary mismatch")

    outcome = run_n05_preflight(
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
    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N05IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N05PreflightVerdict.INCONCLUSIVE


def test_final_manifest_round_trip_has_no_pilot_authorization(tmp_path, monkeypatch):
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"
    outcome = run_n05_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )
    verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    verification = read_record(
        evidence / "independent-verification.json", N05IndependentVerification
    )
    final = read_record(evidence / "manifest.json", N05FinalManifest)
    assert verification.status == N05IndependentStatus.PASS
    assert final.pilot_authorized is False
    assert final.host_cleanup_pending is True


def test_host_ledger_recomputes_authorization_linux_pass_and_stderr(tmp_path, monkeypatch):
    ledger_root = tmp_path / "host-ledger"
    authorization_path = tmp_path / "authorization.json"
    package_paths = (tmp_path / "tar-7.5.2.tgz", tmp_path / "tar-7.5.3.tgz")
    monkeypatch.setattr(preflight, "HOST_LEDGER_ROOT", ledger_root)
    monkeypatch.setattr(preflight, "HOST_AUTHORIZATION_RECORD", authorization_path)
    monkeypatch.setattr(preflight, "HOST_PACKAGE_TARBALLS", package_paths)
    targets, contexts, packages, broker = _inputs(tmp_path, monkeypatch)
    evidence = tmp_path / "evidence"
    outcome = run_n05_preflight(
        evidence,
        targets,
        contexts,
        packages,
        broker,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )
    verified = verify_n05_preflight(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    authorization_path.write_bytes(_AUTHORIZATION_CONTENT)
    args = argparse.Namespace(
        authorization_record=authorization_path,
        controller="a" * 64,
        evidence=evidence,
        host_ledger=ledger_root,
        image=[item.image_id for item in preflight.FROZEN_TARGETS],
        mode=preflight.MODE_ID,
        package_tarball=list(package_paths),
        volume=preflight.RUNTIME_VOLUME_NAME,
    )
    authorization = preflight.authorization_from_bytes(_AUTHORIZATION_CONTENT)
    ledger = N05HostLedger(ledger_root, args, _AUTHORIZATION_CONTENT, authorization)
    ledger.owner = "b" * 32
    ledger.controller_id = "a" * 64
    ledger.controller_launched = True
    ledger.controller_stderr_capture_complete = True
    ledger.controller_stderr = b"controlled stderr\n"
    ledger.cleanup_status = "complete"
    ledger.target_names.add("controlled-target")
    ledger.linux_terminal = {
        "final_manifest_sha256": verified.final_manifest_sha256,
        "final_status": "PREFLIGHT_PASS",
        "host_cleanup_pending": True,
        "independent_status": "PASS",
        "pilot_authorized": False,
        "preflight_verdict": "PREFLIGHT_PASS",
        "raw_manifest_sha256": outcome.manifest_sha256,
        "reader_returncode": 0,
    }
    ledger.finish(0, None)
    host_manifest_sha256 = sha256((ledger_root / "manifest.json").read_bytes()).hexdigest()

    host = verify_n05_host_ledger(
        ledger_root,
        evidence,
        expected_manifest_sha256=host_manifest_sha256,
    )
    assert host["overall_status"] == "PREFLIGHT_PASS"
    assert host["source_revision"] == SOURCE.revision
    assert host["authorization_sha256"] == sha256(_AUTHORIZATION_CONTENT).hexdigest()

    terminal_path = ledger_root / "terminal.json"
    terminal = json.loads(terminal_path.read_bytes())
    terminal["deadline_expired"] = True
    terminal_content = (
        json.dumps(terminal, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")
    terminal_path.write_bytes(terminal_content)
    manifest_path = ledger_root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"]["terminal.json"] = sha256(terminal_content).hexdigest()
    manifest_content = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")
    manifest_path.write_bytes(manifest_content)
    with pytest.raises(ValueError, match="overall status"):
        verify_n05_host_ledger(
            ledger_root,
            evidence,
            expected_manifest_sha256=sha256(manifest_content).hexdigest(),
        )

    (ledger_root / "controller-stderr.bin").write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="binding"):
        verify_n05_host_ledger(
            ledger_root,
            evidence,
            expected_manifest_sha256=sha256(manifest_content).hexdigest(),
        )


def test_host_authorization_rejects_digest_only_claim(tmp_path, monkeypatch):
    authorization_path = tmp_path / "authorization.json"
    monkeypatch.setattr(preflight, "HOST_AUTHORIZATION_RECORD", authorization_path)
    authorization_path.write_bytes(b"{}\n")

    with pytest.raises(ValueError, match="authorization"):
        container_host._read_n05_authorization(
            authorization_path, sha256(authorization_path.read_bytes()).hexdigest()
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("context", "default"),
        ("controller", "f" * 64),
        ("image", ["sha256:" + "9" * 64, "sha256:" + "8" * 64]),
        ("volume", "unapproved-runtime-volume"),
    ),
)
def test_host_invocation_rejects_unapproved_identity(tmp_path, monkeypatch, field, value):
    _inputs(tmp_path, monkeypatch)
    authorization = preflight.authorization_from_bytes(_AUTHORIZATION_CONTENT)
    args = argparse.Namespace(
        context="orbstack",
        controller="a" * 64,
        evidence=Path(authorization.evidence_root),
        host_ledger=Path(authorization.host_ledger_root),
        image=[item.image_id for item in authorization.frozen_targets],
        volume=authorization.runtime_volume_name,
    )
    setattr(args, field, value)

    with pytest.raises(ValueError, match="human authorization"):
        container_host._validate_n05_authorized_invocation(args, authorization)


def test_host_ledger_downgrades_interruption_and_cleanup_uncertainty(tmp_path, monkeypatch):
    ledger_root = tmp_path / "host-ledger"
    authorization_path = tmp_path / "authorization.json"
    package_paths = (tmp_path / "tar-7.5.2.tgz", tmp_path / "tar-7.5.3.tgz")
    monkeypatch.setattr(preflight, "HOST_LEDGER_ROOT", ledger_root)
    monkeypatch.setattr(preflight, "HOST_AUTHORIZATION_RECORD", authorization_path)
    monkeypatch.setattr(preflight, "HOST_PACKAGE_TARBALLS", package_paths)
    _inputs(tmp_path, monkeypatch)
    authorization_path.write_bytes(_AUTHORIZATION_CONTENT)
    args = argparse.Namespace(
        authorization_record=authorization_path,
        controller="a" * 64,
        evidence=preflight.EVIDENCE_ROOT,
        host_ledger=ledger_root,
        image=[item.image_id for item in preflight.FROZEN_TARGETS],
        mode=preflight.MODE_ID,
        package_tarball=list(package_paths),
        volume=preflight.RUNTIME_VOLUME_NAME,
    )
    ledger = N05HostLedger(
        ledger_root,
        args,
        _AUTHORIZATION_CONTENT,
        preflight.authorization_from_bytes(_AUTHORIZATION_CONTENT),
    )
    ledger.cleanup_status = "failed"
    ledger.cleanup_errors = ["controlled cleanup uncertainty"]
    ledger.target_names.add("controlled-target")
    ledger.finish(None, RuntimeError("controlled interruption"))
    host_manifest_sha256 = sha256((ledger_root / "manifest.json").read_bytes()).hexdigest()

    host = verify_n05_host_ledger(
        ledger_root,
        tmp_path / "missing-linux-evidence",
        expected_manifest_sha256=host_manifest_sha256,
    )
    assert host["overall_status"] == "PREFLIGHT_INCONCLUSIVE"
    assert host["final_manifest_sha256"] is None

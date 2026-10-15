"""N01 orchestration tests use controlled adapters, never historical packages."""

import json
import os
import subprocess
import sys
import tarfile
from hashlib import sha256
from pathlib import Path

from inodefence.builder import build_tar
from inodefence.evaluation.encoding import json_bytes, read_json
from inodefence.evaluation.n01 import (
    EXPECTED_BUILD_FILES,
    FROZEN_TARGETS,
    INPUT_TAR_SHA256,
    N01AttemptStatus,
    N01BuildContext,
    N01BuildFile,
    N01QualificationVerdict,
    N01Role,
    reconstruct_n01_case,
    run_n01_qualification,
)
from inodefence.evaluation.n01_reader import (
    N01FinalManifest,
    N01FinalStatus,
    N01IndependentStatus,
    N01IndependentVerification,
    verify_n01_evidence,
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
ENVIRONMENT = EnvironmentProvenance("Linux", "controlled", "arm64", "3.12.3")


class ControlledHistoricalTarget:
    """Node-shaped test double with direct controlled filesystem behavior."""

    def __init__(
        self,
        role: N01Role,
        image_id: str,
        *,
        tar_version: str | None = None,
        reject_readiness_call: int | None = None,
        fail_fixed_pair: bool = False,
    ) -> None:
        frozen = FROZEN_TARGETS[tuple(N01Role).index(role)]
        self.role = role
        self.invocation = NodeTarTarget(
            image_id,
            "22.22.0",
            frozen.tar_version if tar_version is None else tar_version,
            "feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b",
            frozen.lock_sha256,
            10,
        )
        self.reject_readiness_call = reject_readiness_call
        self.fail_fixed_pair = fail_fixed_pair
        self.calls = 0

    @property
    def provenance(self):
        return self.invocation.provenance

    def capture_isolation(self):
        return IsolationProvenance(
            IsolationPolicy(self.invocation.image_id, 1000, 1000),
            "docker-compatible",
            "controlled",
            "1.54",
            "linux",
            "arm64",
            "arm64",
            artifacts=self.invocation.artifacts,
            artifact_origin="image-identification-v1",
        )

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        call = self.calls
        self.calls += 1
        if self.reject_readiness_call == call:
            return self._result(ExecutionStatus.REJECTED, 2, "controlled readiness rejection")
        status = ExecutionStatus.SUCCESS
        exit_code = 0
        stderr = ""
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
                    if member.linkname == "../outside/sentinel.txt" and self.role == N01Role.FIXED:
                        status = (
                            ExecutionStatus.FAILED
                            if self.fail_fixed_pair
                            else ExecutionStatus.REJECTED
                        )
                        exit_code = 1 if self.fail_fixed_pair else 2
                        stderr = "controlled fixed-arm rejection"
                        break
                    os.link(extraction_root / member.linkname, destination)
                else:
                    raise AssertionError("unexpected controlled TAR member")
        return self._result(status, exit_code, stderr)

    def _result(self, status: ExecutionStatus, exit_code: int, stderr: str) -> ExecutionResult:
        return ExecutionResult(
            self.provenance.target_id,
            self.provenance.target_version,
            ("controlled-node-tar", self.role),
            status,
            exit_code,
            "",
            stderr,
            0.001,
            10,
        )


def _build_context(tmp_path: Path, role: N01Role, image_id: str) -> N01BuildContext:
    frozen = FROZEN_TARGETS[tuple(N01Role).index(role)]
    directory = tmp_path / f"context-{role.value}"
    prepare_node_release(
        LOCKS / f"node-tar-{frozen.tar_version}.package-lock.json",
        directory,
        repository=ROOT,
    )
    packaging = read_json((directory / "packaging.json").read_bytes())
    assert isinstance(packaging, dict)
    packaging["source"] = {"revision": SOURCE.revision, "dirty": SOURCE.dirty}
    (directory / "packaging.json").write_bytes(json_bytes(packaging) + b"\n")
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
        "stderr": "",
    }
    (directory / "build.json").write_bytes(json_bytes(build) + b"\n")
    return N01BuildContext(
        role,
        tuple(N01BuildFile(name, (directory / name).read_bytes()) for name in EXPECTED_BUILD_FILES),
    )


def _inputs(tmp_path: Path, **fixed_kwargs):
    images = ("sha256:" + "1" * 64, "sha256:" + "2" * 64)
    targets = (
        ControlledHistoricalTarget(N01Role.AFFECTED, images[0]),
        ControlledHistoricalTarget(N01Role.FIXED, images[1], **fixed_kwargs),
    )
    contexts = (
        _build_context(tmp_path, N01Role.AFFECTED, images[0]),
        _build_context(tmp_path, N01Role.FIXED, images[1]),
    )
    return targets, contexts


def test_frozen_case_is_reconstructed_through_versioned_mutation_api():
    case = reconstruct_n01_case()
    assert case.case_id == ("55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87")
    assert sha256(build_tar(case)).hexdigest() == INPUT_TAR_SHA256


def test_complete_pair_is_published_then_independently_recomputed(tmp_path):
    targets, contexts = _inputs(tmp_path)
    evidence = tmp_path / "evidence"

    outcome = run_n01_qualification(
        evidence,
        targets,
        contexts,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N01AttemptStatus.COMPLETE
    assert outcome.manifest.declared_verdict == N01QualificationVerdict.AUTOMATED_REPLAY_COMPLETE
    assert outcome.manifest.extractions_started == outcome.manifest.extractions_completed == 18
    assert len(outcome.manifest.readiness_runs) == 8
    assert len(outcome.manifest.pair_runs) == 10
    assert len(outcome.manifest.pairs) == 5
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "inodefence.evaluation.n01_reader",
            str(evidence),
            "--raw-manifest-sha256",
            outcome.manifest_sha256,
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    verification = read_record(
        evidence / "independent-verification.json", N01IndependentVerification
    )
    final = read_record(evidence / "manifest.json", N01FinalManifest)
    assert verification.status == N01IndependentStatus.PASS
    assert verification.recomputed_verdict == (N01QualificationVerdict.AUTOMATED_REPLAY_COMPLETE)
    assert final.final_status == N01FinalStatus.AWAITING_HUMAN_REVIEW
    assert (
        verification.verified_admissions,
        verification.verified_oracle_controls,
        verification.verified_readiness_runs,
        verification.verified_pair_runs,
        verification.verified_pairs,
    ) == (2, 2, 8, 10, 5)


def test_admission_failure_stops_before_any_archive_and_is_independently_inconclusive(
    tmp_path,
):
    targets, contexts = _inputs(tmp_path, tar_version="7.5.22")
    evidence = tmp_path / "admission-failure"

    outcome = run_n01_qualification(
        evidence,
        targets,
        contexts,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N01AttemptStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == outcome.manifest.extractions_completed == 0
    assert len(outcome.manifest.failures) == 1
    verified = verify_n01_evidence(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N01IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N01QualificationVerdict.INCONCLUSIVE
    assert verified.final_manifest.final_status == N01FinalStatus.QUALIFICATION_INCONCLUSIVE


def test_broker_preflight_failure_is_retained_before_target_load(tmp_path):
    _, contexts = _inputs(tmp_path)
    evidence = tmp_path / "broker-preflight-failure"

    def unavailable_targets():
        raise RuntimeError("controlled broker preflight failure")

    outcome = run_n01_qualification(
        evidence,
        unavailable_targets,
        contexts,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N01AttemptStatus.INFRASTRUCTURE_INVALID
    assert outcome.manifest.extractions_started == 0
    assert outcome.manifest.admissions == ()
    assert len(outcome.manifest.failures) == 1
    verified = verify_n01_evidence(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N01IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N01QualificationVerdict.INCONCLUSIVE


def test_readiness_failure_preserves_all_eight_runs_and_blocks_pair(tmp_path):
    targets, contexts = _inputs(tmp_path, reject_readiness_call=2)
    evidence = tmp_path / "readiness-failure"

    outcome = run_n01_qualification(
        evidence,
        targets,
        contexts,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.attempt_status == N01AttemptStatus.READINESS_BLOCKED
    assert outcome.manifest.extractions_completed == 8
    assert len(outcome.manifest.readiness_runs) == 8
    assert outcome.manifest.pair_runs == outcome.manifest.pairs == ()
    verified = verify_n01_evidence(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N01IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N01QualificationVerdict.INCONCLUSIVE


def test_independent_reader_rejects_tampered_run_even_if_runner_declared_pass(tmp_path):
    targets, contexts = _inputs(tmp_path)
    evidence = tmp_path / "tampered"
    outcome = run_n01_qualification(
        evidence,
        targets,
        contexts,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )
    run_path = evidence / outcome.manifest.pair_runs[0].path
    record = json.loads(run_path.read_text())
    record["payload"]["value"]["runtime_root_absent_after_return"] = False
    run_path.write_bytes(json_bytes(record) + b"\n")

    verified = verify_n01_evidence(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)

    assert verified.verification.status == N01IndependentStatus.FAIL
    assert verified.final_manifest.final_status == N01FinalStatus.INDEPENDENT_VERIFICATION_FAILED


def test_independent_reader_recomputes_instead_of_trusting_runner_verdict(tmp_path):
    targets, contexts = _inputs(tmp_path)
    evidence = tmp_path / "declared-verdict"
    run_n01_qualification(
        evidence,
        targets,
        contexts,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )
    path = evidence / "raw-manifest.json"
    record = read_json(path.read_bytes())
    assert isinstance(record, dict)
    record["payload"]["value"]["declared_verdict"] = "FAIL"
    record["payload_sha256"] = sha256(json_bytes(record["payload"])).hexdigest()
    content = json_bytes(record) + b"\n"
    path.write_bytes(content)

    verified = verify_n01_evidence(
        evidence, expected_raw_manifest_sha256=sha256(content).hexdigest()
    )

    assert verified.verification.recomputed_verdict == (
        N01QualificationVerdict.AUTOMATED_REPLAY_COMPLETE
    )
    assert not verified.verification.runner_verdict_consistent
    assert verified.verification.status == N01IndependentStatus.FAIL


def test_fixed_process_failure_is_not_coerced_to_a_safe_nonviolation(tmp_path):
    targets, contexts = _inputs(tmp_path, fail_fixed_pair=True)
    evidence = tmp_path / "fixed-process-failure"
    outcome = run_n01_qualification(
        evidence,
        targets,
        contexts,
        repository=ROOT,
        source=SOURCE,
        environment=ENVIRONMENT,
    )

    assert outcome.manifest.declared_verdict == N01QualificationVerdict.FAIL
    verified = verify_n01_evidence(evidence, expected_raw_manifest_sha256=outcome.manifest_sha256)
    assert verified.verification.status == N01IndependentStatus.PASS
    assert verified.verification.recomputed_verdict == N01QualificationVerdict.FAIL
    assert verified.final_manifest.final_status == N01FinalStatus.QUALIFICATION_FAILED

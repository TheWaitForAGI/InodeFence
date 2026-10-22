"""Independent reader for the bounded N05 five-second preflight evidence."""

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from inodefence.builder import build_tar
from inodefence.evaluation.failure import read_failure
from inodefence.evaluation.n05_preflight import (
    EXPECTED_BUILD_FILES,
    EXPERIMENT_ID,
    SENTINEL_SHA256,
    TIMEOUT_SECONDS,
    WORKER_SHA256,
    N05AdmissionRecord,
    N05ArtifactReference,
    N05OracleControlRecord,
    N05PreflightAuthorization,
    N05PreflightRole,
    N05PreflightStatus,
    N05PreflightVerdict,
    N05RawManifest,
    N05ReadinessRecord,
    authorization_from_bytes,
    benign_output_passes,
    frozen_target,
)
from inodefence.evaluation.node_packaging import validate_node_build, validate_node_release
from inodefence.evaluation.storage import read_record, write_record
from inodefence.evaluation.verify import VerificationError, _read_file, verify_binding, verify_run
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ContractId


class N05IndependentStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class N05FinalStatus(StrEnum):
    PREFLIGHT_PASS = "PREFLIGHT_PASS"
    PREFLIGHT_FAIL = "PREFLIGHT_FAIL"
    PREFLIGHT_INCONCLUSIVE = "PREFLIGHT_INCONCLUSIVE"
    INDEPENDENT_VERIFICATION_FAILED = "INDEPENDENT_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class N05IndependentVerification:
    experiment_id: str
    raw_manifest: N05ArtifactReference
    status: N05IndependentStatus
    recomputed_verdict: N05PreflightVerdict
    runner_verdict_consistent: bool
    verified_admissions: int
    verified_oracle_controls: int
    verified_readiness_runs: int
    verified_failures: int
    diagnostics: tuple[str, ...]
    verified_at: str

    def __post_init__(self) -> None:
        if (
            self.experiment_id != EXPERIMENT_ID
            or not isinstance(self.raw_manifest, N05ArtifactReference)
            or not isinstance(self.status, N05IndependentStatus)
            or not isinstance(self.recomputed_verdict, N05PreflightVerdict)
            or type(self.runner_verdict_consistent) is not bool
        ):
            raise ValueError("invalid independent preflight verification")
        for value, limit in (
            (self.verified_admissions, 2),
            (self.verified_oracle_controls, 2),
            (self.verified_readiness_runs, 8),
            (self.verified_failures, 1),
        ):
            if type(value) is not int or not 0 <= value <= limit:
                raise ValueError("invalid verified evidence count")
        if datetime.fromisoformat(self.verified_at).utcoffset() is None:
            raise ValueError("verification timestamp requires timezone")


@dataclass(frozen=True, slots=True)
class N05FinalManifest:
    experiment_id: str
    raw_manifest: N05ArtifactReference
    independent_verification: N05ArtifactReference
    final_status: N05FinalStatus
    pilot_authorized: bool
    host_cleanup_pending: bool
    published_at: str

    def __post_init__(self) -> None:
        if (
            self.experiment_id != EXPERIMENT_ID
            or not isinstance(self.raw_manifest, N05ArtifactReference)
            or not isinstance(self.independent_verification, N05ArtifactReference)
            or not isinstance(self.final_status, N05FinalStatus)
            or self.pilot_authorized is not False
            or self.host_cleanup_pending is not True
            or datetime.fromisoformat(self.published_at).utcoffset() is None
        ):
            raise ValueError("invalid final preflight manifest")


@dataclass(frozen=True, slots=True)
class VerifiedN05Preflight:
    verification: N05IndependentVerification
    verification_sha256: str
    final_manifest: N05FinalManifest
    final_manifest_sha256: str


def _path(root: Path, reference: N05ArtifactReference) -> Path:
    path = root / reference.path
    relative = Path(reference.path)
    ancestors = tuple(
        root.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts))
    )
    if (
        path.is_symlink()
        or any(item.is_symlink() for item in ancestors)
        or path.resolve().parent != path.parent.resolve()
        or not path.resolve().is_relative_to(root.resolve())
    ):
        raise VerificationError("artifact path escapes the evidence root or uses a symlink")
    return path


def _bytes(root: Path, reference: N05ArtifactReference) -> bytes:
    content = _read_file(_path(root, reference))
    if sha256(content).hexdigest() != reference.sha256:
        raise VerificationError(f"artifact checksum mismatch: {reference.path}")
    return content


def _record[T](root: Path, reference: N05ArtifactReference, kind: type[T]) -> T:
    return read_record(_path(root, reference), kind, expected_sha256=reference.sha256)


def _verify_authorization(
    root: Path, manifest: N05RawManifest
) -> tuple[N05PreflightAuthorization, bool]:
    authorization = authorization_from_bytes(_bytes(root, manifest.authorization))
    expected_sources = tuple(
        (f"source/{item.path}", item.sha256) for item in authorization.executable_files
    )
    actual_sources = tuple((item.path, item.sha256) for item in manifest.source_files)
    if actual_sources != expected_sources:
        raise VerificationError("retained source files differ from the human authorization")
    for reference in manifest.source_files:
        _bytes(root, reference)
    if manifest.source.revision != authorization.execution_source_revision:
        raise VerificationError("preflight source revision differs from authorization")
    if manifest.source.dirty is not False:
        raise VerificationError("preflight source was not clean")
    broker_authorized = manifest.broker is None or not (
        manifest.broker.controller_image_id != authorization.controller_image_id
        or manifest.broker.controller_id != authorization.controller_id
        or manifest.broker.context_name != authorization.host_docker_context
        or manifest.broker.daemon_id != authorization.daemon_id
        or manifest.broker.daemon_version != authorization.daemon_version
        or manifest.broker.daemon_api_version != authorization.daemon_api_version
        or tuple(item.image_id for item in manifest.broker.target_images)
        != tuple(item.image_id for item in authorization.frozen_targets)
    )
    if (
        not broker_authorized
        and manifest.attempt_status != N05PreflightStatus.INFRASTRUCTURE_INVALID
    ):
        raise VerificationError("broker identity differs from the human authorization")
    return authorization, broker_authorized


def _verify_packages(root: Path, manifest: N05RawManifest) -> bool:
    expected = tuple(
        f"packages/{role.value}/tar-{frozen_target(role).tar_version}.tgz"
        for role in N05PreflightRole
    )
    actual = tuple(item.path for item in manifest.package_tarballs)
    if actual != expected[: len(actual)]:
        raise VerificationError("package evidence is not an authorized publication prefix")
    valid = True
    for role, reference in zip(N05PreflightRole, manifest.package_tarballs, strict=False):
        _bytes(root, reference)
        valid &= reference.sha256 == frozen_target(role).package_tarball_sha256
    if not valid and manifest.attempt_status != N05PreflightStatus.INFRASTRUCTURE_INVALID:
        raise VerificationError("package tarball differs from the frozen SHA-256 identity")
    return len(actual) == len(expected) and valid


def _verify_builds(
    root: Path, manifest: N05RawManifest
) -> tuple[dict[N05PreflightRole, dict], bool]:
    expected = tuple(
        f"build/{role.value}/{name}" for role in N05PreflightRole for name in EXPECTED_BUILD_FILES
    )
    actual = tuple(item.path for item in manifest.build_files)
    if actual != expected[: len(actual)]:
        raise VerificationError("preflight build context is not an authorized publication prefix")
    for reference in manifest.build_files:
        _bytes(root, reference)
    builds = {}
    complete_roles = len(actual) // len(EXPECTED_BUILD_FILES)
    for role in tuple(N05PreflightRole)[:complete_roles]:
        frozen = frozen_target(role)
        directory = root / "build" / role.value
        try:
            packaging = validate_node_release(directory)
            build = validate_node_build(directory)
        except (OSError, ValueError) as error:
            if manifest.attempt_status != N05PreflightStatus.INFRASTRUCTURE_INVALID:
                raise VerificationError("terminal build context is invalid") from error
            return builds, False
        if (
            packaging["tar_version"] != frozen.tar_version
            or packaging["files_sha256"]["package-lock.json"] != frozen.lock_sha256
            or packaging["files_sha256"]["worker.cjs"] != WORKER_SHA256
            or build["image_id"] != frozen.image_id
            or build["tar_version"] != frozen.tar_version
            or f"exporting manifest sha256:{frozen.platform_manifest_sha256}" not in build["stderr"]
            or sha256((directory / "build.json").read_bytes()).hexdigest() != frozen.build_sha256
        ):
            if manifest.attempt_status != N05PreflightStatus.INFRASTRUCTURE_INVALID:
                raise VerificationError("retained build does not match the frozen target")
            return builds, False
        builds[role] = build
    return builds, len(actual) == len(expected)


def _verify_admission(
    admission: N05AdmissionRecord,
    manifest: N05RawManifest,
    build: dict,
    build_references: set[N05ArtifactReference],
) -> None:
    if manifest.broker is None:
        raise VerificationError("admission exists without a broker attestation")
    if (
        admission.image_id != build["image_id"]
        or admission.packaging not in build_references
        or admission.build not in build_references
        or admission.packaging.path != f"build/{admission.role.value}/packaging.json"
        or admission.build.path != f"build/{admission.role.value}/build.json"
        or admission.target.timeout_seconds != TIMEOUT_SECONDS
        or admission.isolation.runtime_os != "linux"
        or admission.isolation.runtime_architecture != "arm64"
        or admission.isolation.image_architecture != "arm64"
        or admission.isolation.runtime_version != manifest.broker.daemon_version
        or admission.isolation.runtime_api_version != manifest.broker.daemon_api_version
        or admission.isolation.runtime_os != manifest.broker.daemon_os
        or admission.isolation.runtime_architecture != manifest.broker.daemon_architecture
    ):
        raise VerificationError("admission does not bind the retained five-second target")
    broker = manifest.broker.target_images[tuple(N05PreflightRole).index(admission.role)]
    if broker.image_id != admission.image_id:
        raise VerificationError("controller admission differs from host broker image inspection")
    if (
        admission.isolation.image_architecture != broker.architecture
        or admission.isolation.image_repo_digests != broker.repo_digests
    ):
        raise VerificationError("controller image facts differ from host broker inspection")


def _verify_controls(controls: tuple[N05OracleControlRecord, ...]) -> bool:
    if tuple(item.control_id for item in controls) != (
        "unchanged-negative",
        "harness-hardlink-positive",
    ):
        raise VerificationError("oracle controls differ from the frozen order")
    if not all(item.runtime_root_absent_after_return for item in controls):
        return False
    if any(item.violated for item in controls[0].violations):
        return False
    positive = {item.contract_id: item.violated for item in controls[1].violations}
    return positive == {ContractId.C0: False, ContractId.C1: True, ContractId.C2: True}


def _verify_readiness(
    records: tuple[N05ReadinessRecord, ...],
    manifest: N05RawManifest,
    admissions: dict[N05PreflightRole, N05AdmissionRecord],
) -> bool:
    if len(records) > 8:
        raise VerificationError("readiness evidence exceeds the authorized schedule")
    passes = []
    for index, record in enumerate(records):
        role = N05PreflightRole.AFFECTED if index < 4 else N05PreflightRole.FIXED
        seed_index = index % 4
        admission = admissions[role]
        result = record.arm.result
        provenance = record.arm.provenance
        expected_seed = minimal_seed_corpus()[seed_index]
        if (
            record.role != role
            or record.execution_index != index
            or record.seed_index != seed_index
            or result.case != expected_seed
            or result.archive_sha256 != sha256(build_tar(expected_seed)).hexdigest()
            or provenance.source != manifest.source
            or provenance.environment != manifest.environment
            or provenance.target != admission.target
            or provenance.isolation != admission.isolation
            or len(provenance.sentinels) != 1
            or provenance.sentinels[0].name != "sentinel.txt"
            or provenance.sentinels[0].content_sha256 != SENTINEL_SHA256
            or provenance.sentinels[0].mode != 0o600
            or not record.runtime_root_absent_after_return
        ):
            raise VerificationError("readiness schedule/provenance/cleanup binding differs")
        verify_run(result)
        verify_binding(result, provenance)
        passes.append(benign_output_passes(result, seed_index))
    roots = tuple(record.arm.result.before.sandbox_root for record in records)
    if len(roots) != len(set(roots)):
        raise VerificationError("readiness reused a sandbox root")
    return len(records) == 8 and all(passes)


def _verify_raw(
    root: Path, manifest: N05RawManifest
) -> tuple[N05PreflightVerdict, tuple[int, int, int, int], tuple[str, ...]]:
    if not _bytes(root, manifest.contract):
        raise VerificationError("preflight contract is empty")
    _, broker_authorized = _verify_authorization(root, manifest)
    environment_valid = (
        manifest.source.revision is not None
        and manifest.source.dirty is False
        and manifest.environment.system == "Linux"
        and manifest.environment.machine == "aarch64"
    )
    if (
        (
            not environment_valid
            and manifest.attempt_status != N05PreflightStatus.INFRASTRUCTURE_INVALID
        )
        or manifest.extractions_started < manifest.extractions_completed
        or manifest.extractions_started - manifest.extractions_completed > 1
        or manifest.extractions_completed < len(manifest.readiness_runs)
        or manifest.extractions_completed - len(manifest.readiness_runs) > 1
    ):
        raise VerificationError("preflight source/environment/extraction accounting is invalid")
    failures = tuple(
        read_failure(_path(root, item), expected_sha256=item.sha256) for item in manifest.failures
    )
    expected_failures = (
        1 if manifest.attempt_status == N05PreflightStatus.INFRASTRUCTURE_INVALID else 0
    )
    if len(failures) != expected_failures:
        raise VerificationError("infrastructure status and failure ledger disagree")
    for failure in failures:
        if (
            failure.context.attempt_id != manifest.attempt_id
            or failure.context.experiment_id != manifest.experiment_id
            or failure.context.source != manifest.source
            or {(item.name, item.sha256) for item in failure.context.artifacts}
            != {
                (item.path, item.sha256)
                for item in (
                    manifest.contract,
                    manifest.authorization,
                    *manifest.source_files,
                    *manifest.package_tarballs,
                    *manifest.build_files,
                    *manifest.admissions,
                    *manifest.oracle_controls,
                    *manifest.readiness_runs,
                )
            }
        ):
            raise VerificationError("failure ledger does not bind the available raw evidence")
    if manifest.broker is None:
        if (
            manifest.attempt_status != N05PreflightStatus.INFRASTRUCTURE_INVALID
            or manifest.package_tarballs
            or manifest.build_files
            or manifest.admissions
            or manifest.oracle_controls
            or manifest.readiness_runs
            or manifest.extractions_started
        ):
            raise VerificationError("missing broker attestation has impossible downstream records")
        return (
            N05PreflightVerdict.INCONCLUSIVE,
            (0, 0, 0, len(failures)),
            ("broker attestation failed before target admission",),
        )
    if not broker_authorized:
        if (
            manifest.package_tarballs
            or manifest.build_files
            or manifest.admissions
            or manifest.oracle_controls
            or manifest.readiness_runs
            or manifest.extractions_started
        ):
            raise VerificationError("unauthorized broker has impossible downstream records")
        return (
            N05PreflightVerdict.INCONCLUSIVE,
            (0, 0, 0, len(failures)),
            ("broker identity differed from the inspected human authorization",),
        )
    packages_complete = _verify_packages(root, manifest)
    if not packages_complete:
        if (
            manifest.attempt_status != N05PreflightStatus.INFRASTRUCTURE_INVALID
            or manifest.build_files
            or manifest.admissions
            or manifest.oracle_controls
            or manifest.readiness_runs
            or manifest.extractions_started
        ):
            raise VerificationError("partial package evidence has impossible downstream records")
        return (
            N05PreflightVerdict.INCONCLUSIVE,
            (0, 0, 0, len(failures)),
            ("partial or mismatched package evidence was independently reconstructed",),
        )
    builds, builds_complete = _verify_builds(root, manifest)
    if not builds_complete:
        if (
            manifest.attempt_status != N05PreflightStatus.INFRASTRUCTURE_INVALID
            or manifest.admissions
            or manifest.oracle_controls
            or manifest.readiness_runs
            or manifest.extractions_started
        ):
            raise VerificationError("partial build evidence has impossible downstream records")
        return (
            N05PreflightVerdict.INCONCLUSIVE,
            (0, 0, 0, len(failures)),
            ("partial or rejected build evidence was independently reconstructed",),
        )
    admissions = tuple(_record(root, item, N05AdmissionRecord) for item in manifest.admissions)
    if tuple(item.role for item in admissions) != tuple(N05PreflightRole)[: len(admissions)]:
        raise VerificationError("admission records are not an affected/fixed prefix")
    build_references = set(manifest.build_files)
    for admission in admissions:
        _verify_admission(admission, manifest, builds[admission.role], build_references)
    if len(admissions) < 2:
        if manifest.attempt_status != N05PreflightStatus.INFRASTRUCTURE_INVALID:
            raise VerificationError("archive evidence requires two completed admissions")
        return (
            N05PreflightVerdict.INCONCLUSIVE,
            (len(admissions), 0, 0, len(failures)),
            ("target admission did not complete; no readiness PASS is possible",),
        )
    controls = tuple(
        _record(root, item, N05OracleControlRecord) for item in manifest.oracle_controls
    )
    if (
        tuple(item.control_id for item in controls)
        != (
            "unchanged-negative",
            "harness-hardlink-positive",
        )[: len(controls)]
    ):
        raise VerificationError("oracle controls are not an authorized publication prefix")
    if len(controls) < 2:
        if manifest.attempt_status != N05PreflightStatus.INFRASTRUCTURE_INVALID:
            raise VerificationError("readiness requires two complete oracle controls")
        if controls and (
            any(item.violated for item in controls[0].violations)
            or not controls[0].runtime_root_absent_after_return
        ):
            raise VerificationError("retained negative oracle control did not pass")
        return (
            N05PreflightVerdict.INCONCLUSIVE,
            (len(admissions), len(controls), 0, len(failures)),
            ("oracle control execution was infrastructure-invalid",),
        )
    controls_pass = _verify_controls(controls)
    control_roots = tuple(item.before.sandbox_root for item in controls)
    if len(control_roots) != len(set(control_roots)):
        raise VerificationError("oracle controls reused a sandbox root")
    if not controls_pass:
        if manifest.attempt_status == N05PreflightStatus.INFRASTRUCTURE_INVALID:
            return (
                N05PreflightVerdict.INCONCLUSIVE,
                (len(admissions), len(controls), 0, len(failures)),
                ("complete oracle controls failed their frozen predicates",),
            )
        raise VerificationError("oracle controls failed their frozen C0/C1/C2 predicates")
    readiness = tuple(_record(root, item, N05ReadinessRecord) for item in manifest.readiness_runs)
    readiness_pass = _verify_readiness(
        readiness, manifest, {item.role: item for item in admissions}
    )
    all_roots = (*control_roots, *(item.arm.result.before.sandbox_root for item in readiness))
    if len(all_roots) != len(set(all_roots)):
        raise VerificationError("preflight reused a runtime sandbox root")
    counts = (len(admissions), len(controls), len(readiness), len(failures))
    if manifest.attempt_status == N05PreflightStatus.INFRASTRUCTURE_INVALID:
        return (
            N05PreflightVerdict.INCONCLUSIVE,
            counts,
            ("infrastructure-invalid evidence is retained; no readiness verdict is inferred",),
        )
    if len(readiness) != 8:
        raise VerificationError("complete preflight requires all eight readiness records")
    verdict = N05PreflightVerdict.PASS if readiness_pass else N05PreflightVerdict.FAIL
    expected_status = (
        N05PreflightStatus.COMPLETE
        if verdict == N05PreflightVerdict.PASS
        else N05PreflightStatus.READINESS_FAILED
    )
    if manifest.attempt_status != expected_status or failures:
        raise VerificationError("terminal attempt status disagrees with readiness evidence")
    return (
        verdict,
        counts,
        (
            "raw integrity, target identity, controls, eight benign runs and cleanup "
            "were independently recomputed",
            "PREFLIGHT_PASS does not authorize B0/B1/B3 or issue an N01 human token",
        ),
    )


def verify_n05_preflight(root: Path, *, expected_raw_manifest_sha256: str) -> VerifiedN05Preflight:
    if root.is_symlink() or not root.is_dir():
        raise VerificationError("preflight evidence root must be a nonsymlink directory")
    raw_ref = N05ArtifactReference("raw-manifest.json", expected_raw_manifest_sha256)
    counts = (0, 0, 0, 0)
    try:
        manifest = _record(root, raw_ref, N05RawManifest)
        verdict, counts, diagnostics = _verify_raw(root, manifest)
        consistent = verdict == manifest.declared_verdict
        status = N05IndependentStatus.PASS if consistent else N05IndependentStatus.FAIL
        if not consistent:
            diagnostics += (
                f"runner declared {manifest.declared_verdict}; reader derived {verdict}",
            )
    except Exception as error:
        verdict = N05PreflightVerdict.INCONCLUSIVE
        consistent = False
        status = N05IndependentStatus.FAIL
        diagnostics = (
            "independent read failed: "
            f"{type(error).__module__}.{type(error).__qualname__}: {error}",
        )
    verification = N05IndependentVerification(
        EXPERIMENT_ID,
        raw_ref,
        status,
        verdict,
        consistent,
        *counts,
        diagnostics,
        datetime.now(UTC).isoformat(),
    )
    verification_path = root / "independent-verification.json"
    verification_digest = write_record(verification_path, verification)
    verification_ref = N05ArtifactReference("independent-verification.json", verification_digest)
    final_status = (
        N05FinalStatus.INDEPENDENT_VERIFICATION_FAILED
        if status == N05IndependentStatus.FAIL
        else N05FinalStatus.PREFLIGHT_PASS
        if verdict == N05PreflightVerdict.PASS
        else N05FinalStatus.PREFLIGHT_FAIL
        if verdict == N05PreflightVerdict.FAIL
        else N05FinalStatus.PREFLIGHT_INCONCLUSIVE
    )
    final = N05FinalManifest(
        EXPERIMENT_ID,
        raw_ref,
        verification_ref,
        final_status,
        False,
        True,
        datetime.now(UTC).isoformat(),
    )
    final_path = root / "manifest.json"
    final_digest = write_record(final_path, final)
    return VerifiedN05Preflight(verification, verification_digest, final, final_digest)


def read_n05_preflight(root: Path, *, expected_final_manifest_sha256: str) -> VerifiedN05Preflight:
    """Read existing terminal evidence and independently recompute its raw decision."""
    if root.is_symlink() or not root.is_dir():
        raise VerificationError("preflight evidence root must be a nonsymlink directory")
    final_ref = N05ArtifactReference("manifest.json", expected_final_manifest_sha256)
    final = _record(root, final_ref, N05FinalManifest)
    verification = _record(root, final.independent_verification, N05IndependentVerification)
    raw = _record(root, final.raw_manifest, N05RawManifest)
    verdict, counts, _ = _verify_raw(root, raw)
    runner_consistent = verdict == raw.declared_verdict
    independent_status = (
        N05IndependentStatus.PASS if runner_consistent else N05IndependentStatus.FAIL
    )
    expected_status = (
        N05FinalStatus.INDEPENDENT_VERIFICATION_FAILED
        if verification.status == N05IndependentStatus.FAIL
        else N05FinalStatus.PREFLIGHT_PASS
        if verdict == N05PreflightVerdict.PASS
        else N05FinalStatus.PREFLIGHT_FAIL
        if verdict == N05PreflightVerdict.FAIL
        else N05FinalStatus.PREFLIGHT_INCONCLUSIVE
    )
    if (
        verification.raw_manifest != final.raw_manifest
        or verification.status != independent_status
        or verification.recomputed_verdict != verdict
        or verification.runner_verdict_consistent is not runner_consistent
        or (
            verification.verified_admissions,
            verification.verified_oracle_controls,
            verification.verified_readiness_runs,
            verification.verified_failures,
        )
        != counts
        or final.final_status != expected_status
        or final.pilot_authorized is not False
        or final.host_cleanup_pending is not True
    ):
        raise VerificationError("terminal preflight evidence disagrees with recomputed raw data")
    return VerifiedN05Preflight(
        verification,
        final.independent_verification.sha256,
        final,
        expected_final_manifest_sha256,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("--raw-manifest-sha256", required=True)
    args = parser.parse_args()
    result = verify_n05_preflight(
        args.evidence_root, expected_raw_manifest_sha256=args.raw_manifest_sha256
    )
    print(
        json.dumps(
            {
                "independent_status": result.verification.status,
                "preflight_verdict": result.verification.recomputed_verdict,
                "final_status": result.final_manifest.final_status,
                "pilot_authorized": result.final_manifest.pilot_authorized,
                "host_cleanup_pending": result.final_manifest.host_cleanup_pending,
                "final_manifest_sha256": result.final_manifest_sha256,
            },
            sort_keys=True,
        )
    )
    return 0 if result.verification.status == N05IndependentStatus.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())

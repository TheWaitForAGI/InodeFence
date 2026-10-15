"""Independent fresh-process reader for N01 qualification evidence.

The reader ignores the runner's expected-outcome decision while recomputing
artifact integrity, raw derivations, benign readiness and affected/fixed rules.
It does not execute a target and is not a human correspondence review.
"""

import argparse
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from inodefence.evaluation.encoding import read_json
from inodefence.evaluation.failure import read_failure
from inodefence.evaluation.n01 import (
    AUTOMATED_TOKEN,
    CHILD_CASE_ID,
    EXPECTED_BUILD_FILES,
    EXPERIMENT_ID,
    FROZEN_TARGETS,
    INPUT_TAR_SHA256,
    PAIR_SCHEDULE,
    N01AdmissionRecord,
    N01ArtifactReference,
    N01AttemptStatus,
    N01OracleControlRecord,
    N01PairReference,
    N01QualificationVerdict,
    N01RawManifest,
    N01Role,
    N01RunPhase,
    N01RunRecord,
    reconstruct_n01_case,
)
from inodefence.evaluation.node_packaging import validate_node_build, validate_node_release
from inodefence.evaluation.pair import PairComparison, read_pair
from inodefence.evaluation.storage import read_record, write_record
from inodefence.evaluation.verify import VerificationError, _read_file, verify_binding, verify_run
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ContractId, ExecutionStatus, ObjectType, RunResult


class N01IndependentStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class N01HumanDisposition(StrEnum):
    PENDING = "pending_human_correspondence_review"


class N01FinalStatus(StrEnum):
    AWAITING_HUMAN_REVIEW = "AWAITING_HUMAN_CORRESPONDENCE_REVIEW"
    QUALIFICATION_FAILED = "QUALIFICATION_FAILED"
    QUALIFICATION_INCONCLUSIVE = "QUALIFICATION_INCONCLUSIVE"
    INDEPENDENT_VERIFICATION_FAILED = "INDEPENDENT_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class N01IndependentVerification:
    experiment_id: str
    raw_manifest: N01ArtifactReference
    status: N01IndependentStatus
    recomputed_verdict: N01QualificationVerdict
    runner_verdict_consistent: bool
    verified_admissions: int
    verified_oracle_controls: int
    verified_readiness_runs: int
    verified_pair_runs: int
    verified_pairs: int
    diagnostics: tuple[str, ...]
    verified_at: str

    def __post_init__(self) -> None:
        if (
            self.experiment_id != EXPERIMENT_ID
            or not isinstance(self.status, N01IndependentStatus)
            or not isinstance(self.recomputed_verdict, N01QualificationVerdict)
            or type(self.runner_verdict_consistent) is not bool
        ):
            raise ValueError("invalid independent N01 verification")
        counts = (
            self.verified_admissions,
            self.verified_oracle_controls,
            self.verified_readiness_runs,
            self.verified_pair_runs,
            self.verified_pairs,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValueError("verification counts must be nonnegative integers")
        if not self.diagnostics or not all(
            isinstance(item, str) and item for item in self.diagnostics
        ):
            raise ValueError("independent verification requires diagnostics")
        if datetime.fromisoformat(self.verified_at).utcoffset() is None:
            raise ValueError("verification timestamp requires a timezone")


@dataclass(frozen=True, slots=True)
class N01FinalManifest:
    experiment_id: str
    raw_manifest: N01ArtifactReference
    independent_verification: N01ArtifactReference
    final_status: N01FinalStatus
    automated_token: str | None
    human_disposition: N01HumanDisposition
    published_at: str

    def __post_init__(self) -> None:
        if (
            self.experiment_id != EXPERIMENT_ID
            or not isinstance(self.final_status, N01FinalStatus)
            or not isinstance(self.human_disposition, N01HumanDisposition)
        ):
            raise ValueError("invalid final N01 manifest")
        expected = (
            AUTOMATED_TOKEN if self.final_status == N01FinalStatus.AWAITING_HUMAN_REVIEW else None
        )
        if self.automated_token != expected:
            raise ValueError("automated token does not match final status")
        if datetime.fromisoformat(self.published_at).utcoffset() is None:
            raise ValueError("final manifest timestamp requires a timezone")


@dataclass(frozen=True, slots=True)
class VerifiedN01Evidence:
    verification: N01IndependentVerification
    verification_sha256: str
    final_manifest: N01FinalManifest
    final_manifest_sha256: str


def _path(root: Path, reference: N01ArtifactReference) -> Path:
    path = root / reference.path
    if path.resolve().parent != path.parent.resolve() or not path.resolve().is_relative_to(
        root.resolve()
    ):
        raise VerificationError("artifact path escapes the evidence root or uses a symlink")
    return path


def _bytes(root: Path, reference: N01ArtifactReference) -> bytes:
    content = _read_file(_path(root, reference))
    if sha256(content).hexdigest() != reference.sha256:
        raise VerificationError(f"artifact checksum mismatch: {reference.path}")
    return content


def _record[T](root: Path, reference: N01ArtifactReference, kind: type[T]) -> T:
    return read_record(_path(root, reference), kind, expected_sha256=reference.sha256)


def _violated(result: RunResult, contract: ContractId) -> bool:
    return next(item.violated for item in result.violations if item.contract_id == contract)


def _archive_unchanged(result: RunResult) -> bool:
    return result.before.get("archive/input.tar") == result.after.get("archive/input.tar")


def _benign_output_passes(result: RunResult, seed_index: int) -> bool:
    expected = minimal_seed_corpus()[seed_index]
    if result.case != expected:
        raise VerificationError("readiness case differs from its frozen benign seed")
    if not result.execution.succeeded or any(item.violated for item in result.violations):
        return False
    if not _archive_unchanged(result):
        return False
    after = result.after
    if seed_index == 0:
        file = after.get("extract/a.txt")
        if file is None or file.content_digest != sha256(b"hello inodefence").hexdigest():
            return False
    elif seed_index == 1:
        directory, file = after.get("extract/dir"), after.get("extract/dir/a.txt")
        if (
            directory is None
            or directory.object_type != ObjectType.DIRECTORY
            or file is None
            or file.content_digest != sha256(b"hello inodefence").hexdigest()
        ):
            return False
    elif seed_index == 2:
        first, second = after.get("extract/a.txt"), after.get("extract/b.txt")
        if first is None or second is None or first.identity != second.identity:
            return False
    elif seed_index == 3:
        link = after.get("extract/b.txt")
        if link is None or link.object_type != ObjectType.SYMLINK or link.symlink_target != "a.txt":
            return False
    return True


def _verify_target_binding(record: N01RunRecord, admission: N01AdmissionRecord) -> None:
    verify_run(record.arm.result)
    verify_binding(record.arm.result, record.arm.provenance)
    if (
        record.arm.provenance.target != admission.target
        or record.arm.provenance.isolation != admission.isolation
        or record.arm.result.execution.target_version != admission.target.target_version
        or not record.runtime_root_absent_after_return
    ):
        raise VerificationError("run target, isolation or cleanup differs from admission")


def _verify_builds(root: Path, manifest: N01RawManifest) -> dict[N01Role, dict]:
    expected_paths = {
        f"build/{role.value}/{name}" for role in N01Role for name in EXPECTED_BUILD_FILES
    }
    observed_paths = {item.path for item in manifest.build_files}
    if not observed_paths <= expected_paths:
        raise VerificationError("build context includes files outside the frozen pair")
    for reference in manifest.build_files:
        _bytes(root, reference)
    builds = {}
    locks = []
    for role, frozen in zip(N01Role, FROZEN_TARGETS, strict=True):
        directory = root / "build" / role.value
        role_paths = {f"build/{role.value}/{name}" for name in EXPECTED_BUILD_FILES}
        if not role_paths <= observed_paths:
            continue
        packaging = validate_node_release(directory)
        build = validate_node_build(directory)
        if (
            packaging["tar_version"] != frozen.tar_version
            or packaging["files_sha256"]["package-lock.json"] != frozen.lock_sha256
            or build["tar_version"] != frozen.tar_version
        ):
            raise VerificationError("build records differ from the frozen target")
        builds[role] = build
        lock = read_json(_read_file(directory / "package-lock.json"))
        if not isinstance(lock, dict):
            raise VerificationError("historical lock is not an object")
        locks.append(lock)
    normalized = []
    for lock in locks:
        item = deepcopy(lock)
        item["packages"][""]["dependencies"]["tar"] = "<PAIR-TARGET>"
        target = item["packages"]["node_modules/tar"]
        for field in ("version", "resolved", "integrity"):
            target[field] = f"<{field.upper()}>"
        normalized.append(item)
    if len(normalized) == 2 and normalized[0] != normalized[1]:
        raise VerificationError("non-target production dependency closure differs")
    return builds


def _independent_pair_verdict(records: tuple[N01RunRecord, ...]) -> N01QualificationVerdict:
    if len(records) != 10:
        return N01QualificationVerdict.INCONCLUSIVE
    affected = tuple(item.arm.result for item in records if item.role == N01Role.AFFECTED)
    fixed = tuple(item.arm.result for item in records if item.role == N01Role.FIXED)
    if len(affected) != 5 or len(fixed) != 5:
        return N01QualificationVerdict.INCONCLUSIVE
    for result in affected:
        alias = result.after.get("extract/b.txt")
        sentinel = result.after.get("outside/sentinel.txt")
        if not (
            result.execution.succeeded
            and alias is not None
            and sentinel is not None
            and alias.identity == sentinel.identity
            and _violated(result, ContractId.C1)
            and _violated(result, ContractId.C2)
            and not _violated(result, ContractId.C0)
            and _archive_unchanged(result)
        ):
            return N01QualificationVerdict.FAIL
    for result in fixed:
        alias = result.after.get("extract/b.txt")
        sentinel = result.after.get("outside/sentinel.txt")
        if not (
            result.execution.status == ExecutionStatus.REJECTED
            and not _violated(result, ContractId.C0)
            and not _violated(result, ContractId.C1)
            and not _violated(result, ContractId.C2)
            and (alias is None or sentinel is None or alias.identity != sentinel.identity)
            and _archive_unchanged(result)
        ):
            return N01QualificationVerdict.FAIL
    return N01QualificationVerdict.AUTOMATED_REPLAY_COMPLETE


def _verify_complete(
    root: Path, manifest: N01RawManifest
) -> tuple[N01QualificationVerdict, tuple[int, int, int, int, int], tuple[str, ...]]:
    if _bytes(root, manifest.contract).decode("utf-8") == "":
        raise VerificationError("approved contract is empty")
    if manifest.extractions_completed != len(manifest.readiness_runs) + len(manifest.pair_runs):
        raise VerificationError("completed extraction count differs from run records")
    if (
        manifest.extractions_started < manifest.extractions_completed
        or manifest.extractions_started - manifest.extractions_completed > 1
    ):
        raise VerificationError("started/completed extraction counts are inconsistent")
    builds = _verify_builds(root, manifest)
    for reference in manifest.failures:
        read_failure(_path(root, reference), expected_sha256=reference.sha256)
    admissions = tuple(
        _record(root, reference, N01AdmissionRecord) for reference in manifest.admissions
    )
    if tuple(item.role for item in admissions) != tuple(N01Role)[: len(admissions)]:
        raise VerificationError("admission records are not an affected/fixed prefix")
    admission_by_role = {item.role: item for item in admissions}
    build_reference_set = set(manifest.build_files)
    for admission in admissions:
        if admission.role not in builds or admission.image_id != builds[admission.role]["image_id"]:
            raise VerificationError("admitted immutable image differs from build record")
        if (
            admission.packaging not in build_reference_set
            or admission.build not in build_reference_set
        ):
            raise VerificationError("admission does not bind retained packaging/build records")
    if len(admissions) < 2:
        if manifest.attempt_status in (
            N01AttemptStatus.ADMISSION_BLOCKED,
            N01AttemptStatus.INFRASTRUCTURE_INVALID,
        ):
            return (
                N01QualificationVerdict.INCONCLUSIVE,
                (len(admissions), 0, 0, 0, 0),
                ("historical image admission did not complete; no archive phase was valid",),
            )
        raise VerificationError("archive evidence requires both historical admissions")
    controls = tuple(
        _record(root, reference, N01OracleControlRecord) for reference in manifest.oracle_controls
    )
    expected_controls = (
        "unchanged-negative",
        "harness-hardlink-positive",
    )
    if tuple(item.control_id for item in controls) != expected_controls[: len(controls)]:
        raise VerificationError("oracle controls are not a frozen-order prefix")
    if len(controls) < 2:
        if manifest.attempt_status == N01AttemptStatus.INFRASTRUCTURE_INVALID:
            return (
                N01QualificationVerdict.INCONCLUSIVE,
                (len(admissions), len(controls), 0, 0, 0),
                ("oracle-control execution was infrastructure-invalid",),
            )
        raise VerificationError("readiness evidence requires both oracle controls")
    if any(item.violated for item in controls[0].violations):
        raise VerificationError("negative oracle control unexpectedly violated a contract")
    positive = {item.contract_id: item.violated for item in controls[1].violations}
    controls_pass = positive == {
        ContractId.C0: False,
        ContractId.C1: True,
        ContractId.C2: True,
    }
    if not controls_pass:
        if manifest.attempt_status == N01AttemptStatus.ORACLE_CONTROL_BLOCKED:
            return (
                N01QualificationVerdict.INCONCLUSIVE,
                (len(admissions), len(controls), 0, 0, 0),
                ("oracle controls did not qualify the C1/C2 observation path",),
            )
        raise VerificationError("positive oracle control did not independently yield C1/C2")
    readiness = tuple(
        _record(root, reference, N01RunRecord) for reference in manifest.readiness_runs
    )
    readiness_passes = []
    for index, record in enumerate(readiness):
        expected_role = N01Role.AFFECTED if index < 4 else N01Role.FIXED
        expected_seed = index % 4
        if (
            record.phase != N01RunPhase.READINESS
            or record.role != expected_role
            or record.execution_index != index
            or record.seed_index != expected_seed
        ):
            raise VerificationError("readiness identity/order differs from the frozen schedule")
        _verify_target_binding(record, admission_by_role[record.role])
        readiness_passes.append(_benign_output_passes(record.arm.result, expected_seed))
    if len(readiness) != 8 or not all(readiness_passes):
        if manifest.attempt_status in (
            N01AttemptStatus.READINESS_BLOCKED,
            N01AttemptStatus.INFRASTRUCTURE_INVALID,
        ):
            return (
                N01QualificationVerdict.INCONCLUSIVE,
                (len(admissions), len(controls), len(readiness), 0, 0),
                ("readiness did not produce eight successful valid records; pair was blocked",),
            )
        raise VerificationError("complete evidence requires eight readiness runs")
    pair_runs = tuple(_record(root, reference, N01RunRecord) for reference in manifest.pair_runs)
    if len(pair_runs) > 10 or len(manifest.pairs) > 5:
        raise VerificationError("pair evidence exceeds the approved budget")
    expected_sequence = tuple(
        (schedule.repetition, position, role)
        for schedule in PAIR_SCHEDULE
        for position, role in enumerate(schedule.order)
    )
    for offset, (record, expected) in enumerate(zip(pair_runs, expected_sequence, strict=False)):
        repetition, position, role = expected
        if (
            record.phase != N01RunPhase.PAIR
            or record.role != role
            or record.execution_index != offset + 8
            or record.repetition != repetition
            or record.schedule_position != position
            or record.arm.result.case.case_id != CHILD_CASE_ID
            or record.arm.result.archive_sha256 != INPUT_TAR_SHA256
            or record.arm.result.case != reconstruct_n01_case()
        ):
            raise VerificationError("pair run differs from frozen input or schedule")
        _verify_target_binding(record, admission_by_role[record.role])
    comparisons = []
    run_by_path = {
        reference.path: record
        for reference, record in zip(manifest.pair_runs, pair_runs, strict=True)
    }
    for expected_schedule, reference in zip(PAIR_SCHEDULE, manifest.pairs, strict=False):
        if not isinstance(reference, N01PairReference) or (
            reference.repetition,
            reference.order,
        ) != (expected_schedule.repetition, expected_schedule.order):
            raise VerificationError("pair comparison schedule binding differs")
        comparison = read_pair(
            _path(root, reference.comparison),
            expected_sha256=reference.comparison.sha256,
        )
        if (
            reference.affected_run not in manifest.pair_runs
            or reference.fixed_run not in manifest.pair_runs
        ):
            raise VerificationError("pair binding does not use retained result-first records")
        affected = run_by_path[reference.affected_run.path]
        fixed = run_by_path[reference.fixed_run.path]
        if comparison != PairComparison(
            comparison.case_id,
            comparison.archive_sha256,
            comparison.builder_format,
            affected.arm,
            fixed.arm,
        ):
            raise VerificationError("pair comparison differs from result-first arm records")
        comparisons.append(comparison)
    if manifest.failures:
        return (
            N01QualificationVerdict.INCONCLUSIVE,
            (len(admissions), len(controls), len(readiness), len(pair_runs), len(comparisons)),
            ("infrastructure-invalid evidence is present",),
        )
    if manifest.attempt_status != N01AttemptStatus.COMPLETE:
        return (
            N01QualificationVerdict.INCONCLUSIVE,
            (len(admissions), len(controls), len(readiness), len(pair_runs), len(comparisons)),
            (f"attempt ended as {manifest.attempt_status}",),
        )
    if len(pair_runs) != 10 or len(comparisons) != 5:
        raise VerificationError("complete attempt requires ten pair runs and five comparisons")
    verdict = _independent_pair_verdict(pair_runs)
    return (
        verdict,
        (len(admissions), len(controls), len(readiness), len(pair_runs), len(comparisons)),
        (
            "raw integrity, image/case identity, snapshots, inode relations and C0/C1/C2 "
            "were independently recomputed",
            "this program is not the contract-required human correspondence review",
        ),
    )


def verify_n01_evidence(root: Path, *, expected_raw_manifest_sha256: str) -> VerifiedN01Evidence:
    if root.is_symlink() or not root.is_dir():
        raise VerificationError("N01 evidence root must be a nonsymlink directory")
    raw_ref = N01ArtifactReference("raw-manifest.json", expected_raw_manifest_sha256)
    counts = (0, 0, 0, 0, 0)
    try:
        manifest = _record(root, raw_ref, N01RawManifest)
        verdict, counts, diagnostics = _verify_complete(root, manifest)
        consistent = verdict == manifest.declared_verdict
        status = N01IndependentStatus.PASS if consistent else N01IndependentStatus.FAIL
        if not consistent:
            diagnostics += (
                f"runner declared {manifest.declared_verdict}; reader derived {verdict}",
            )
    except Exception as error:
        verdict = N01QualificationVerdict.INCONCLUSIVE
        consistent = False
        status = N01IndependentStatus.FAIL
        diagnostics = (
            "independent read failed: "
            f"{type(error).__module__}.{type(error).__qualname__}: {error}",
        )
    verification = N01IndependentVerification(
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
    verification_ref = N01ArtifactReference("independent-verification.json", verification_digest)
    if status == N01IndependentStatus.FAIL:
        final_status = N01FinalStatus.INDEPENDENT_VERIFICATION_FAILED
    elif verdict == N01QualificationVerdict.AUTOMATED_REPLAY_COMPLETE:
        final_status = N01FinalStatus.AWAITING_HUMAN_REVIEW
    elif verdict == N01QualificationVerdict.FAIL:
        final_status = N01FinalStatus.QUALIFICATION_FAILED
    else:
        final_status = N01FinalStatus.QUALIFICATION_INCONCLUSIVE
    final = N01FinalManifest(
        EXPERIMENT_ID,
        raw_ref,
        verification_ref,
        final_status,
        AUTOMATED_TOKEN if final_status == N01FinalStatus.AWAITING_HUMAN_REVIEW else None,
        N01HumanDisposition.PENDING,
        datetime.now(UTC).isoformat(),
    )
    final_path = root / "manifest.json"
    final_digest = write_record(final_path, final)
    return VerifiedN01Evidence(verification, verification_digest, final, final_digest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("--raw-manifest-sha256", required=True)
    args = parser.parse_args()
    result = verify_n01_evidence(
        args.evidence_root, expected_raw_manifest_sha256=args.raw_manifest_sha256
    )
    print(
        json.dumps(
            {
                "independent_status": result.verification.status,
                "qualification_verdict": result.verification.recomputed_verdict,
                "final_status": result.final_manifest.final_status,
                "final_manifest_sha256": result.final_manifest_sha256,
            },
            sort_keys=True,
        )
    )
    return 0 if result.verification.status == N01IndependentStatus.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())

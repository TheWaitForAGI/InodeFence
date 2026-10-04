"""Qualification reporting with explicit NOT_RUN and linked evidence integrity."""

import argparse
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from inodefence.model.filesystem import validate_observed_path
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import ExecutionProvenance, TargetProvenance

from .encoding import json_bytes
from .failure import ArtifactReference
from .storage import read_record, write_record
from .verify import VerificationError, _read_file


class QualificationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


class QualificationItem(StrEnum):
    TARGET_IDENTITY = "target_identity_verified"
    RUNTIME_IDENTITY = "runtime_identity_verified"
    ARTIFACT_DIGEST = "artifact_digest_verified"
    ISOLATION = "isolation_available"
    REGULAR = "benign_regular_extraction"
    DIRECTORY = "benign_directory_extraction"
    HARDLINK = "benign_hardlink_extraction"
    SYMLINK = "benign_symlink_extraction"
    STATUS = "status_classification"
    TIMEOUT = "timeout_behavior"
    CLEANUP = "cleanup"
    SNAPSHOTS = "snapshot_lifecycle"
    PROVENANCE = "provenance_capture"


def _identifier(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", value) is None:
        raise ValueError("qualification profile/protocol needs a stable identifier")


@dataclass(frozen=True, slots=True)
class QualificationContext:
    requested_target: TargetProvenance
    environment_profile: str
    sentinel_profile: str
    protocol_version: str
    provenance: ExecutionProvenance | None = None
    required_artifacts: tuple[ArtifactDigest, ...] = ()
    requested_image_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.requested_target, TargetProvenance
        ) or self.requested_target.target_version.lower() in {"latest", "current", "installed"}:
            raise ValueError("qualification requires an explicit pinned target")
        for value in (self.environment_profile, self.sentinel_profile, self.protocol_version):
            _identifier(value)
        if self.provenance is not None and (
            not isinstance(self.provenance, ExecutionProvenance)
            or self.provenance.target != self.requested_target
        ):
            raise ValueError("captured target provenance differs from requested identity")
        if (
            not isinstance(self.required_artifacts, tuple)
            or not all(isinstance(item, ArtifactDigest) for item in self.required_artifacts)
            or tuple(item.name for item in self.required_artifacts)
            != tuple(sorted({item.name for item in self.required_artifacts}))
        ):
            raise ValueError("artifact requirements must be sorted unique typed digests")
        if self.requested_image_id is not None and (
            not isinstance(self.requested_image_id, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.requested_image_id) is None
        ):
            raise ValueError("qualification image identity must be immutable")
        if (
            self.provenance is not None
            and self.provenance.isolation is not None
            and self.requested_image_id is not None
            and self.provenance.isolation.policy.image_id != self.requested_image_id
        ):
            raise ValueError("captured image differs from requested image")


@dataclass(frozen=True, slots=True)
class QualificationCheck:
    item: QualificationItem
    status: QualificationStatus
    detail: str
    evidence: tuple[ArtifactReference, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.item, QualificationItem)
            or not isinstance(self.status, QualificationStatus)
            or not isinstance(self.detail, str)
            or not self.detail
        ):
            raise ValueError("qualification requires explicit item/status/detail")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, ArtifactReference) for item in self.evidence
        ):
            raise ValueError("qualification evidence must be immutable artifact references")
        for reference in self.evidence:
            validate_observed_path(reference.name)
            if reference.name == ".":
                raise ValueError("evidence reference must name a file")
        if self.status == QualificationStatus.PASS and not self.evidence:
            raise ValueError("PASS requires linked evidence")


@dataclass(frozen=True, slots=True)
class QualificationReport:
    context: QualificationContext
    checks: tuple[QualificationCheck, ...]
    recorded_at: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.context, QualificationContext)
            or not isinstance(self.checks, tuple)
            or not all(isinstance(check, QualificationCheck) for check in self.checks)
            or tuple(check.item for check in self.checks) != tuple(QualificationItem)
        ):
            raise ValueError("report must preserve the complete qualification checklist in order")
        if datetime.fromisoformat(self.recorded_at).utcoffset() is None:
            raise ValueError("record timestamp needs timezone")

    @property
    def overall_status(self) -> QualificationStatus:
        if any(check.status == QualificationStatus.FAIL for check in self.checks):
            return QualificationStatus.FAIL
        if any(check.status == QualificationStatus.NOT_RUN for check in self.checks):
            return QualificationStatus.NOT_RUN
        return QualificationStatus.PASS


@dataclass(frozen=True, slots=True)
class VerifiedQualification:
    report: QualificationReport
    report_sha256: str

    @property
    def ready(self) -> bool:
        return self.report.overall_status == QualificationStatus.PASS


def qualification_report(
    context: QualificationContext, observations: tuple[QualificationCheck, ...] = ()
) -> QualificationReport:
    if (
        not isinstance(observations, tuple)
        or not all(isinstance(check, QualificationCheck) for check in observations)
        or len({check.item for check in observations}) != len(observations)
    ):
        raise ValueError("observations must have unique qualification items")
    observed = {check.item: check for check in observations}
    return QualificationReport(
        context,
        tuple(
            observed.get(
                item,
                QualificationCheck(item, QualificationStatus.NOT_RUN, "No observation supplied."),
            )
            for item in QualificationItem
        ),
        datetime.now(UTC).isoformat(),
    )


def write_qualification(path: Path, report: QualificationReport) -> str:
    if not isinstance(report, QualificationReport):
        raise ValueError("expected a QualificationReport")
    return write_record(path, report)


def read_evidence(directory: Path, reference: ArtifactReference) -> bytes:
    """Resolve only canonical relative artifact names under a trusted evidence root."""
    validate_observed_path(reference.name)
    if reference.name == "." or directory.is_symlink():
        raise ValueError("invalid evidence root/name")
    path = directory
    for component in reference.name.split("/"):
        path = path / component
        if path.is_symlink():
            raise ValueError("qualification evidence may not traverse symlinks")
    content = _read_file(path)
    if sha256(content).hexdigest() != reference.sha256:
        raise ValueError("linked evidence checksum mismatch")
    return content


def verify_qualification(
    path: Path, *, expected_sha256: str | None = None
) -> VerifiedQualification:
    """Validate stored assessor assertions and links; does not rerun qualification."""
    try:
        content = _read_file(path)
        report = read_record(path, QualificationReport, expected_sha256=sha256(content).hexdigest())
        if expected_sha256 is not None and sha256(content).hexdigest() != expected_sha256:
            raise ValueError("qualification report checksum mismatch")
        for check in report.checks:
            for reference in check.evidence:
                read_evidence(path.parent, reference)
        if report.overall_status == QualificationStatus.PASS:
            context, provenance = report.context, report.context.provenance
            if (
                provenance is None
                or provenance.source.revision is None
                or provenance.source.dirty is not False
            ):
                raise ValueError("PASS requires captured clean pinned source/runtime provenance")
            isolation = provenance.isolation
            if (
                isolation is None
                or context.requested_image_id is None
                or not context.required_artifacts
                or not set(context.required_artifacts) <= set(isolation.artifacts)
            ):
                raise ValueError("PASS requires verified image/isolation/artifact binding")
        return VerifiedQualification(report, sha256(content).hexdigest())
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid qualification evidence: {error}") from error


def qualification_markdown(verified: VerifiedQualification) -> str:
    report = verified.report
    lines = [
        "# Target qualification",
        "",
        f"Overall: **{report.overall_status}**; READY: **{verified.ready}**",
        "",
        f"Report SHA-256: `{verified.report_sha256}`",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in report.checks:
        detail = check.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {check.item} | {check.status} | {detail} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    try:
        verified = verify_qualification(args.report, expected_sha256=args.sha256)
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json_bytes(
            {
                "schema_version": 1,
                "overall_status": verified.report.overall_status,
                "ready": verified.ready,
                **asdict(verified),
            }
        ).decode("ascii")
        if args.format == "json"
        else qualification_markdown(verified),
        end="\n" if args.format == "json" else "",
    )
    return 0 if verified.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())

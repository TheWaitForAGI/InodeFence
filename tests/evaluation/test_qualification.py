from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.evaluation.failure import ArtifactReference
from inodefence.evaluation.qualification import (
    QualificationCheck,
    QualificationContext,
    QualificationItem,
    QualificationStatus,
    qualification_markdown,
    qualification_report,
    verify_qualification,
    write_qualification,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.model import canonical_json


@pytest.fixture
def context(campaign):
    return QualificationContext(
        campaign.provenance.target,
        "unit-linux-v1",
        "default-sentinel-v1",
        "unit-protocol-v1",
        campaign.provenance,
    )


def test_unrun_checklist_is_complete_and_never_ready(context, tmp_path):
    report = qualification_report(context)
    assert tuple(check.item for check in report.checks) == tuple(QualificationItem)
    assert all(check.status == QualificationStatus.NOT_RUN for check in report.checks)
    assert report.overall_status == QualificationStatus.NOT_RUN
    path = tmp_path / "qualification.json"
    digest = write_qualification(path, report)
    verified = verify_qualification(path, expected_sha256=digest)
    assert verified.report == report and not verified.ready
    assert "NOT_RUN" in qualification_markdown(verified)


def test_pass_needs_actual_linked_bytes_and_checksum(context, campaign, tmp_path):
    artifact = tmp_path / "benign-core-step.json"
    artifact.write_text(canonical_json(campaign.steps[0]) + "\n", encoding="ascii")
    reference = ArtifactReference(artifact.name, sha256(artifact.read_bytes()).hexdigest())
    check = QualificationCheck(
        QualificationItem.REGULAR,
        QualificationStatus.PASS,
        "Benign reference observation supplied for reporting test.",
        (reference,),
    )
    report = qualification_report(context, (check,))
    path = tmp_path / "qualification.json"
    write_qualification(path, report)
    assert not verify_qualification(path).ready
    artifact.write_bytes(b"corrupted evidence")
    with pytest.raises(VerificationError, match="checksum"):
        verify_qualification(path)
    artifact.unlink()
    with pytest.raises(VerificationError):
        verify_qualification(path)


def test_missing_evidence_and_incomplete_checklists_cannot_claim_pass(context):
    with pytest.raises(ValueError, match="PASS requires"):
        QualificationCheck(
            QualificationItem.RUNTIME_IDENTITY, QualificationStatus.PASS, "assertion"
        )
    report = qualification_report(
        context,
        (
            QualificationCheck(
                QualificationItem.TIMEOUT, QualificationStatus.FAIL, "Controlled failure."
            ),
        ),
    )
    assert report.overall_status == QualificationStatus.FAIL
    with pytest.raises(ValueError, match="complete qualification"):
        replace(report, checks=report.checks[:-1])
    with pytest.raises(ValueError, match="unique"):
        qualification_report(context, (report.checks[0], report.checks[0]))


def test_asserted_all_pass_without_pinned_runtime_is_rejected(context, tmp_path):
    artifact = tmp_path / "assessor-unit-output.json"
    artifact.write_bytes(b'{"classification":"synthetic-assessor-unit-input"}\n')
    reference = ArtifactReference(artifact.name, sha256(artifact.read_bytes()).hexdigest())
    checks = tuple(
        QualificationCheck(
            item,
            QualificationStatus.PASS,
            "Synthetic reporting assertion, not target qualification.",
            (reference,),
        )
        for item in QualificationItem
    )
    report = qualification_report(replace(context, provenance=None), checks)
    path = tmp_path / "qualification.json"
    write_qualification(path, report)
    with pytest.raises(VerificationError, match="captured clean"):
        verify_qualification(path)


@pytest.mark.parametrize("name", ["../outside.json", "/absolute.json", "a//b.json", "."])
def test_artifact_references_cannot_escape_evidence_root(name):
    with pytest.raises(ValueError):
        QualificationCheck(
            QualificationItem.CLEANUP,
            QualificationStatus.PASS,
            "unit",
            (ArtifactReference(name, "a" * 64),),
        )


def test_symlinked_evidence_is_rejected(context, tmp_path):
    original = tmp_path / "original.json"
    original.write_bytes(b"actual unit bytes")
    link = tmp_path / "alias.json"
    link.symlink_to(original)
    reference = ArtifactReference(link.name, sha256(original.read_bytes()).hexdigest())
    report = qualification_report(
        context,
        (
            QualificationCheck(
                QualificationItem.PROVENANCE, QualificationStatus.PASS, "unit", (reference,)
            ),
        ),
    )
    path = tmp_path / "qualification.json"
    write_qualification(path, report)
    with pytest.raises(VerificationError, match="symlinks"):
        verify_qualification(path)

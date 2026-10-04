from dataclasses import replace

import pytest

from inodefence.evaluation.catalog import (
    BindingStatus,
    EvaluationCatalog,
    ProtocolBinding,
    TargetRequirement,
    require_ready,
    validate_catalog,
    write_catalog,
)
from inodefence.evaluation.failure import ArtifactReference
from inodefence.evaluation.qualification import (
    QualificationContext,
    qualification_report,
    write_qualification,
)
from inodefence.evaluation.verify import VerificationError


def binding(campaign, reference=None):
    requirement = TargetRequirement(campaign.provenance.target, campaign.provenance, reference)
    return ProtocolBinding(
        "unit-pair",
        "reference",
        requirement,
        requirement,
        "unit-linux-v1",
        "default-sentinel-v1",
        "unit-protocol-v1",
    )


def test_documented_candidate_without_qualification_is_not_ready(tmp_path, campaign):
    path = tmp_path / "catalog.json"
    catalog = EvaluationCatalog((binding(campaign),))
    digest = write_catalog(path, catalog)
    (result,) = validate_catalog(path, expected_sha256=digest)
    assert result.status == BindingStatus.NOT_READY
    assert result.qualification_sha256 == ()
    with pytest.raises(VerificationError, match="fully verified"):
        require_ready(path, "unit-pair")


def test_linked_not_run_report_is_never_ready(tmp_path, campaign):
    context = QualificationContext(
        campaign.provenance.target,
        "unit-linux-v1",
        "default-sentinel-v1",
        "unit-protocol-v1",
        campaign.provenance,
    )
    report_path = tmp_path / "qualification.json"
    digest = write_qualification(report_path, qualification_report(context))
    reference = ArtifactReference(report_path.name, digest)
    path = tmp_path / "catalog.json"
    write_catalog(path, EvaluationCatalog((binding(campaign, reference),)))
    (result,) = validate_catalog(path)
    assert result.status == BindingStatus.NOT_READY
    assert any("NOT_RUN" in reason for reason in result.reasons)
    assert result.qualification_sha256 == (digest, digest)
    with pytest.raises(VerificationError):
        require_ready(path, "unit-pair")


def test_profile_mismatch_missing_and_tampered_links_fail_closed(tmp_path, campaign):
    context = QualificationContext(
        campaign.provenance.target,
        "other-linux-v1",
        "default-sentinel-v1",
        "unit-protocol-v1",
        campaign.provenance,
    )
    report_path = tmp_path / "qualification.json"
    digest = write_qualification(report_path, qualification_report(context))
    path = tmp_path / "catalog.json"
    write_catalog(
        path, EvaluationCatalog((binding(campaign, ArtifactReference(report_path.name, digest)),))
    )
    assert validate_catalog(path)[0].status == BindingStatus.INVALID
    report_path.write_bytes(b"tampered")
    assert validate_catalog(path)[0].status == BindingStatus.INVALID
    report_path.unlink()
    assert validate_catalog(path)[0].status == BindingStatus.INVALID


def test_duplicate_binding_ids_and_floating_target_versions_are_rejected(campaign):
    entry = binding(campaign)
    with pytest.raises(ValueError, match="unique"):
        EvaluationCatalog((entry, entry))
    with pytest.raises(ValueError, match="exact"):
        TargetRequirement(replace(campaign.provenance.target, target_version="latest"))

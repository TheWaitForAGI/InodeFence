"""Evaluation-owned explicit configuration binding for passive policy evidence."""

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import ClassVar

from inodefence.campaign import SearchCampaignConfig, SearchCampaignResult
from inodefence.model import canonical_json
from inodefence.model.provenance import ExecutionProvenance

from .failure import ArtifactReference
from .policy_evidence import (
    VerifiedPolicyEvidence,
    export_policy_result,
    validate_policy_result,
    verify_policy_evidence,
)
from .storage import read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file


@dataclass(frozen=True, slots=True)
class PolicyEvaluationConfig:
    """Explicit versioned evaluation declaration, distinct from ExperimentConfig.

    The caller can freeze this before execution. Captured full source/runtime/
    target/artifact/isolation/sentinel provenance must match the completed result.
    Profile/protocol labels are declarations, not proof of following a protocol.
    """

    serialization_schema: ClassVar[int] = 1

    campaign: SearchCampaignConfig
    initial_case_ids: tuple[str, ...]
    provenance: ExecutionProvenance
    seed_profile: str
    environment_profile: str
    sentinel_profile: str
    protocol_version: str

    def __post_init__(self) -> None:
        if type(self.campaign) is not SearchCampaignConfig or not isinstance(
            self.provenance, ExecutionProvenance
        ):
            raise ValueError("explicit policy configuration and execution provenance required")
        if (
            not isinstance(self.initial_case_ids, tuple)
            or not self.initial_case_ids
            or len(set(self.initial_case_ids)) != len(self.initial_case_ids)
            or len(self.initial_case_ids) > self.campaign.execution_budget
        ):
            raise ValueError("unique initial IDs must fit the execution budget")
        for case_id in self.initial_case_ids:
            _digest(case_id)
        for field in (
            "seed_profile",
            "environment_profile",
            "sentinel_profile",
            "protocol_version",
        ):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", value) is None
            ):
                raise ValueError(f"{field} requires an explicit stable version identifier")

    @property
    def config_id(self) -> str:
        return sha256(canonical_json(self).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyEvaluationBinding:
    """Last publication marker links the evaluation declaration to immutable raw bytes."""

    serialization_schema: ClassVar[int] = 1

    config: ArtifactReference
    campaign_manifest: ArtifactReference
    config_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.config, ArtifactReference)
            or self.config.name != "evaluation-config.json"
            or not isinstance(self.campaign_manifest, ArtifactReference)
            or self.campaign_manifest.name != "campaign/manifest.json"
        ):
            raise ValueError("unsupported policy binding artifacts")
        _digest(self.config_id)


@dataclass(frozen=True, slots=True)
class VerifiedBoundPolicyEvidence:
    config: PolicyEvaluationConfig
    campaign: VerifiedPolicyEvidence
    binding_sha256: str


def _matches(config: PolicyEvaluationConfig, result: SearchCampaignResult) -> None:
    if type(config) is not PolicyEvaluationConfig or (
        config.campaign != result.config
        or config.initial_case_ids != result.initial_case_ids
        or config.provenance != result.provenance
    ):
        raise ValueError("evaluation declaration differs from completed policy evidence")


def export_bound_policy_result(
    result: SearchCampaignResult, config: PolicyEvaluationConfig, directory: Path
) -> str:
    """Passive completed export; no execution, policy dispatch or Core config changes."""
    validate_policy_result(result)
    _matches(config, result)
    directory.mkdir()
    sync_directory(directory.parent)
    config_digest = write_record(directory / "evaluation-config.json", config)
    campaign_digest = export_policy_result(result, directory / "campaign")
    binding = PolicyEvaluationBinding(
        ArtifactReference("evaluation-config.json", config_digest),
        ArtifactReference("campaign/manifest.json", campaign_digest),
        config.config_id,
    )
    return write_record(directory / "binding.json", binding)


def verify_bound_policy_evidence(
    directory: Path, *, expected_binding_sha256: str | None = None
) -> VerifiedBoundPolicyEvidence:
    """All-or-nothing declaration/raw binding, not qualification or authorship."""
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("expected a completed bound policy evidence directory")
        if {path.name for path in directory.iterdir()} != {
            "binding.json",
            "evaluation-config.json",
            "campaign",
        }:
            raise ValueError("incomplete or unexpected bound evidence files")
        digest = sha256(_read_file(directory / "binding.json")).hexdigest()
        if expected_binding_sha256 is not None and digest != _digest(expected_binding_sha256):
            raise ValueError("binding checksum mismatch")
        binding = read_record(
            directory / "binding.json", PolicyEvaluationBinding, expected_sha256=digest
        )
        config = read_record(
            directory / binding.config.name,
            PolicyEvaluationConfig,
            expected_sha256=binding.config.sha256,
        )
        if config.config_id != binding.config_id:
            raise ValueError("evaluation config identifier mismatch")
        campaign = verify_policy_evidence(
            directory / "campaign", expected_manifest_sha256=binding.campaign_manifest.sha256
        )
        _matches(config, campaign.result)
        return VerifiedBoundPolicyEvidence(config, campaign, digest)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid bound policy evidence: {error}") from error

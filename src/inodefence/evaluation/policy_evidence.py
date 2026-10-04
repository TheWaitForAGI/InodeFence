"""Passive, fail-closed export/reader for completed policy-aware core results."""

import argparse
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import ClassVar

from inodefence.builder import BUILDER_FORMAT
from inodefence.campaign import CampaignOrigin, SearchCampaignResult
from inodefence.feedback import SearchDecision, SearchPolicy, SearchState
from inodefence.model import canonical_json

from .encoding import decode, json_bytes, object_fields, read_json
from .failure import ArtifactReference
from .storage import read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file, verify_binding, verify_run


@dataclass(frozen=True, slots=True)
class PolicyEvidenceManifest:
    """Completion marker binding full result bytes and the declared policy config.

    This config digest identifies SearchCampaignConfig, not ExperimentConfig.
    Environment/protocol/qualification bindings are not invented here.
    """

    serialization_schema: ClassVar[int] = 1

    result: ArtifactReference
    policy_config_sha256: str
    number_of_steps: int
    builder_format: str = BUILDER_FORMAT
    result_schema: int = 1
    step_schema: int = 1
    decision_schema: int = SearchDecision.serialization_schema
    signature_schema: int = 3
    classification: str = "raw-policy-campaign"

    def __post_init__(self) -> None:
        if not isinstance(self.result, ArtifactReference) or self.result.name != "result.json":
            raise ValueError("unsupported result artifact")
        _digest(self.policy_config_sha256)
        if type(self.number_of_steps) is not int or self.number_of_steps <= 0:
            raise ValueError("number_of_steps must be a positive integer")
        for value, expected in (
            (self.result_schema, 1),
            (self.step_schema, 1),
            (self.decision_schema, SearchDecision.serialization_schema),
            (self.signature_schema, 3),
        ):
            if type(value) is not int or value != expected:
                raise ValueError("unsupported policy evidence schema")
        if self.builder_format != BUILDER_FORMAT or self.classification != "raw-policy-campaign":
            raise ValueError("unsupported builder/classification")


@dataclass(frozen=True, slots=True)
class VerifiedPolicyEvidence:
    """Complete consistent raw evidence; checksums do not authenticate authorship."""

    result: SearchCampaignResult
    manifest: PolicyEvidenceManifest
    manifest_sha256: str


def validate_policy_result(result: SearchCampaignResult) -> None:
    """Check raw derivations and declared policy using the public pure SearchState.

    Validate admissible parent membership, not RNG draws or mutation proposals.
    Never run a target, mutator or search selection. Full state diagnostics and
    projected admission accounting remain distinct as defined by the core.
    """
    if type(result) is not SearchCampaignResult:
        raise ValueError("expected a SearchCampaignResult")
    # Core result/step constructors are trusted assembly. Enforce strict nested
    # types at this ingest boundary as well as when reading untrusted JSON.
    envelope = object_fields(
        read_json(canonical_json(result).encode("ascii")), {"model", "schema_version", "value"}
    )
    decode(SearchCampaignResult, envelope["value"])
    count = len(result.steps)
    initial = result.initial_case_ids
    if (
        count != result.config.execution_budget
        or not initial
        or len(initial) > count
        or len(set(initial)) != len(initial)
    ):
        raise ValueError("invalid initial cases or completed budget")
    for case_id in initial:
        _digest(case_id)
    state = SearchState(
        tuple(step.result.case for step in result.steps[: len(initial)]),
        result.config.search_policy,
        projection=result.config.feedback_projection,
    )
    for index, step in enumerate(result.steps):
        if type(step.index) is not int or step.index != index:
            raise ValueError("step index mismatch")
        if index < len(initial):
            if (
                step.origin != CampaignOrigin.SEED
                or step.parent_case_id is not None
                or step.result.case.case_id != initial[index]
            ):
                raise ValueError("seed lineage/case_id mismatch")
        else:
            if state.policy == SearchPolicy.B0:
                active = state.active_case
                parents = initial if active is None else (active.case_id,)
            else:
                parents = tuple(entry.case.case_id for entry in state.entries)
            if step.origin != CampaignOrigin.MUTATION or step.parent_case_id not in parents:
                raise ValueError("mutation parent differs from declared policy")
        verify_run(step.result)
        verify_binding(step.result, result.provenance)
        if step.feedback != state.consider(step.result):
            raise ValueError("policy feedback evidence mismatch")
    active = state.active_case
    if (
        result.final_corpus_stats != state.stats
        or result.retained_case_ids != tuple(entry.case.case_id for entry in state.entries)
        or type(result.unique_feedback_keys) is not int
        or result.unique_feedback_keys != state.unique_feedback_keys
        or result.active_case_id != (None if active is None else active.case_id)
    ):
        raise ValueError("final policy accounting mismatch")


def export_policy_result(result: SearchCampaignResult, directory: Path) -> str:
    """Publish a completed caller-produced result without overwriting any evidence.

    The synced manifest is last. A failed publication can leave result.json,
    which readers refuse without a valid marker. Linux, trusted parents and a
    single writer are required. This is not a completed-step callback/journal.
    """
    validate_policy_result(result)
    directory.mkdir()
    sync_directory(directory.parent)
    result_digest = write_record(directory / "result.json", result)
    manifest = PolicyEvidenceManifest(
        ArtifactReference("result.json", result_digest),
        sha256(canonical_json(result.config).encode("ascii")).hexdigest(),
        len(result.steps),
    )
    return write_record(directory / "manifest.json", manifest)


def verify_policy_evidence(
    directory: Path, *, expected_manifest_sha256: str | None = None
) -> VerifiedPolicyEvidence:
    """Verify all records before returning any result; no legacy schema fallback."""
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("expected a completed policy evidence directory")
        if {path.name for path in directory.iterdir()} != {"manifest.json", "result.json"}:
            raise ValueError("incomplete or unexpected policy evidence files")
        manifest_digest = sha256(_read_file(directory / "manifest.json")).hexdigest()
        if expected_manifest_sha256 is not None and manifest_digest != _digest(
            expected_manifest_sha256
        ):
            raise ValueError("manifest checksum mismatch")
        manifest = read_record(
            directory / "manifest.json",
            PolicyEvidenceManifest,
            expected_sha256=manifest_digest,
        )
        result = read_record(
            directory / manifest.result.name,
            SearchCampaignResult,
            expected_sha256=manifest.result.sha256,
        )
        validate_policy_result(result)
        if (
            manifest.number_of_steps != len(result.steps)
            or manifest.policy_config_sha256
            != sha256(canonical_json(result.config).encode("ascii")).hexdigest()
        ):
            raise ValueError("manifest count/config binding mismatch")
        return VerifiedPolicyEvidence(result, manifest, manifest_digest)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid policy campaign evidence: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    try:
        verified = verify_policy_evidence(
            args.directory, expected_manifest_sha256=args.manifest_sha256
        )
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json_bytes(
            {
                "classification": "verified-raw-policy-evidence",
                "manifest_sha256": verified.manifest_sha256,
                "number_of_steps": len(verified.result.steps),
                "policy_config_sha256": verified.manifest.policy_config_sha256,
            }
        ).decode("ascii")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Versioned full-step timing bound to completed policy campaign evidence."""

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic_ns
from typing import ClassVar

from inodefence.campaign import (
    SearchCampaignCompletedStep,
    SearchCampaignConfig,
    SearchCampaignResult,
    run_search_campaign,
)
from inodefence.model import ArchiveCase
from inodefence.model.provenance import ExecutionProvenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.base import CampaignTarget

from .encoding import json_bytes
from .failure import ArtifactReference
from .policy_binding import (
    PolicyEvaluationConfig,
    VerifiedBoundPolicyEvidence,
    export_bound_policy_result,
    verify_bound_policy_evidence,
)
from .policy_evidence import validate_policy_result
from .storage import read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file

TIMING_PROFILE = "policy-full-step-monotonic-v1"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _offset(origin: int) -> int:
    current = monotonic_ns()
    if type(current) is not int or current < origin:
        raise ValueError("monotonic clock moved backward or returned an invalid value")
    return current - origin


def _timestamp(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("timing timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("timing timestamp must be ISO-8601") from error
    if parsed.utcoffset() is None:
        raise ValueError("timing timestamp requires a UTC offset")


@dataclass(frozen=True, slots=True)
class PolicyStepTiming:
    """One sequential full-step interval relative to campaign monotonic origin."""

    serialization_schema: ClassVar[int] = 1

    index: int
    started_offset_ns: int
    completed_offset_ns: int

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("timed policy step index must be nonnegative")
        if (
            type(self.started_offset_ns) is not int
            or type(self.completed_offset_ns) is not int
            or self.started_offset_ns < 0
            or self.completed_offset_ns < self.started_offset_ns
        ):
            raise ValueError("full-step timing offsets must be ordered nonnegative integers")

    @property
    def duration_seconds(self) -> float:
        return (self.completed_offset_ns - self.started_offset_ns) / 1_000_000_000


@dataclass(frozen=True, slots=True)
class PolicyCampaignTiming:
    """Campaign/step timing only; target process duration remains in each RunResult."""

    serialization_schema: ClassVar[int] = 1

    started_at_utc: str
    completed_at_utc: str
    steps: tuple[PolicyStepTiming, ...]
    campaign_completed_offset_ns: int
    timing_profile: str = TIMING_PROFILE

    def __post_init__(self) -> None:
        _timestamp(self.started_at_utc)
        _timestamp(self.completed_at_utc)
        if (
            not isinstance(self.steps, tuple)
            or not self.steps
            or not all(isinstance(step, PolicyStepTiming) for step in self.steps)
        ):
            raise ValueError("campaign timing requires nonempty typed step timings")
        if tuple(step.index for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("timed policy step indexes must be contiguous")
        previous = 0
        for step in self.steps:
            if step.started_offset_ns != previous:
                raise ValueError("full-step intervals must form one contiguous campaign timeline")
            previous = step.completed_offset_ns
        if (
            type(self.campaign_completed_offset_ns) is not int
            or self.campaign_completed_offset_ns < previous
        ):
            raise ValueError("campaign completion must follow every completed step")
        if self.timing_profile != TIMING_PROFILE:
            raise ValueError("unsupported policy timing profile")

    @property
    def elapsed_seconds(self) -> float:
        return self.campaign_completed_offset_ns / 1_000_000_000


@dataclass(frozen=True, slots=True)
class TimedPolicyCampaign:
    """In-memory completed policy result plus separately versioned timing evidence."""

    result: SearchCampaignResult
    timing: PolicyCampaignTiming

    def __post_init__(self) -> None:
        if type(self.result) is not SearchCampaignResult or not isinstance(
            self.timing, PolicyCampaignTiming
        ):
            raise ValueError("timed policy campaign requires typed result and timing")
        if len(self.result.steps) != len(self.timing.steps):
            raise ValueError("timing count differs from completed policy result")


def run_timed_search_campaign(
    initial_cases: Sequence[ArchiveCase],
    target: CampaignTarget,
    config: SearchCampaignConfig,
    *,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    provenance: ExecutionProvenance | None = None,
    completed_record: Callable[[SearchCampaignCompletedStep], None] | None = None,
) -> TimedPolicyCampaign:
    """Run the unchanged policy core and record sequential orchestration offsets.

    The origin precedes campaign preflight/provenance work. Each completed offset
    is sampled only after run_case returned (including sandbox cleanup), feedback
    was derived and the immutable record was assembled. If a synchronous record
    sink is supplied, it runs before that sample, so its latency is part of the
    full step. The final offset follows complete SearchCampaignResult assembly.
    This is not process duration, final bundle publication, interrupted-run
    recovery or known-class adjudication time.
    """
    started_at = _utc_now().isoformat()
    origin = monotonic_ns()
    if type(origin) is not int or origin < 0:
        raise ValueError("monotonic clock returned an invalid campaign origin")
    timings: list[PolicyStepTiming] = []
    previous = 0

    def completed(record: SearchCampaignCompletedStep) -> None:
        nonlocal previous
        if completed_record is not None:
            completed_record(record)
        timing = PolicyStepTiming(record.step.index, previous, _offset(origin))
        timings.append(timing)
        previous = timing.completed_offset_ns

    result = run_search_campaign(
        initial_cases,
        target,
        config,
        sentinels=sentinels,
        provenance=provenance,
        completed_record=completed,
    )
    campaign_completed = _offset(origin)
    completed_at = _utc_now().isoformat()
    return TimedPolicyCampaign(
        result,
        PolicyCampaignTiming(
            started_at,
            completed_at,
            tuple(timings),
            campaign_completed,
        ),
    )


@dataclass(frozen=True, slots=True)
class PolicyTimingManifest:
    """Last marker binding the existing policy bundle to timing bytes."""

    serialization_schema: ClassVar[int] = 1

    campaign_binding: ArtifactReference
    timing: ArtifactReference
    evaluation_config_id: str
    number_of_steps: int
    timing_profile: str = TIMING_PROFILE

    def __post_init__(self) -> None:
        if (
            not isinstance(self.campaign_binding, ArtifactReference)
            or self.campaign_binding.name != "campaign/binding.json"
            or not isinstance(self.timing, ArtifactReference)
            or self.timing.name != "timing.json"
        ):
            raise ValueError("unsupported timed policy artifact names")
        _digest(self.evaluation_config_id)
        if type(self.number_of_steps) is not int or self.number_of_steps <= 0:
            raise ValueError("timed policy manifest requires completed steps")
        if self.timing_profile != TIMING_PROFILE:
            raise ValueError("unsupported policy timing manifest profile")


@dataclass(frozen=True, slots=True)
class VerifiedTimedPolicyEvidence:
    campaign: VerifiedBoundPolicyEvidence
    timing: PolicyCampaignTiming
    manifest: PolicyTimingManifest
    manifest_sha256: str


def export_timed_policy_result(
    timed: TimedPolicyCampaign,
    config: PolicyEvaluationConfig,
    directory: Path,
) -> str:
    """Publish the existing bound result and timing, then one immutable marker."""
    if not isinstance(timed, TimedPolicyCampaign) or not isinstance(config, PolicyEvaluationConfig):
        raise ValueError("timed export requires typed campaign and evaluation config")
    validate_policy_result(timed.result)
    if (
        config.campaign != timed.result.config
        or config.initial_case_ids != timed.result.initial_case_ids
        or config.provenance != timed.result.provenance
    ):
        raise ValueError("timed evaluation declaration differs from completed policy evidence")
    directory.mkdir()
    sync_directory(directory.parent)
    campaign_digest = export_bound_policy_result(timed.result, config, directory / "campaign")
    timing_digest = write_record(directory / "timing.json", timed.timing)
    manifest = PolicyTimingManifest(
        ArtifactReference("campaign/binding.json", campaign_digest),
        ArtifactReference("timing.json", timing_digest),
        config.config_id,
        len(timed.result.steps),
    )
    return write_record(directory / "manifest.json", manifest)


def verify_timed_policy_evidence(
    directory: Path, *, expected_manifest_sha256: str | None = None
) -> VerifiedTimedPolicyEvidence:
    """Verify the declaration/result bundle and timing before returning either."""
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("expected a completed timed policy evidence directory")
        if {path.name for path in directory.iterdir()} != {
            "campaign",
            "timing.json",
            "manifest.json",
        }:
            raise ValueError("incomplete or unexpected timed policy evidence files")
        manifest_digest = sha256(_read_file(directory / "manifest.json")).hexdigest()
        if expected_manifest_sha256 is not None and manifest_digest != _digest(
            expected_manifest_sha256
        ):
            raise ValueError("timed policy manifest checksum mismatch")
        manifest = read_record(
            directory / "manifest.json",
            PolicyTimingManifest,
            expected_sha256=manifest_digest,
        )
        campaign = verify_bound_policy_evidence(
            directory / "campaign",
            expected_binding_sha256=manifest.campaign_binding.sha256,
        )
        timing = read_record(
            directory / manifest.timing.name,
            PolicyCampaignTiming,
            expected_sha256=manifest.timing.sha256,
        )
        TimedPolicyCampaign(campaign.campaign.result, timing)
        if (
            manifest.evaluation_config_id != campaign.config.config_id
            or manifest.number_of_steps != len(campaign.campaign.result.steps)
            or manifest.timing_profile != timing.timing_profile
        ):
            raise ValueError("timing manifest differs from policy result/configuration")
        return VerifiedTimedPolicyEvidence(campaign, timing, manifest, manifest_digest)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid timed policy evidence: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    try:
        verified = verify_timed_policy_evidence(
            args.directory, expected_manifest_sha256=args.manifest_sha256
        )
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json_bytes(
            {
                "classification": "verified-policy-full-step-timing-v1",
                "manifest_sha256": verified.manifest_sha256,
                "evaluation_config_id": verified.manifest.evaluation_config_id,
                "number_of_steps": verified.manifest.number_of_steps,
                "campaign_elapsed_seconds": verified.timing.elapsed_seconds,
            }
        ).decode("ascii")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

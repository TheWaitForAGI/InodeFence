"""Incremental B0/B1/B3 evidence with deterministic mutation replay."""

import argparse
import random
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import ClassVar

from inodefence.campaign import (
    CampaignOrigin,
    SearchCampaignCompletedStep,
    SearchCampaignResult,
)
from inodefence.feedback import SearchState
from inodefence.model import ArchiveCase
from inodefence.mutator import mutate_attempt_with_policy
from inodefence.runtime import SentinelSpec
from inodefence.targets.base import CampaignTarget

from .encoding import json_bytes
from .failure import (
    ArtifactReference,
    CleanupStatus,
    FailureContext,
    FailurePhase,
    FailureRecord,
    failure_record,
    read_failure,
    write_failure,
)
from .policy_binding import PolicyEvaluationConfig
from .policy_timing import (
    TimedPolicyCampaign,
    VerifiedTimedPolicyEvidence,
    export_timed_policy_result,
    run_timed_search_campaign,
    verify_timed_policy_evidence,
)
from .storage import read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file, verify_binding, verify_run


def _timestamp(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("journal timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("journal timestamp must be ISO-8601") from error
    if parsed.utcoffset() is None:
        raise ValueError("journal timestamp requires a UTC offset")


def _identifier(value: str) -> None:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("journal identifier must be nonempty text without NUL")


@dataclass(frozen=True, slots=True)
class PolicyJournalHeader:
    """Frozen attempt identity and evaluation declaration written before execution."""

    serialization_schema: ClassVar[int] = 1

    attempt_id: str
    experiment_id: str
    evaluation_config: PolicyEvaluationConfig
    created_at_utc: str

    def __post_init__(self) -> None:
        _identifier(self.attempt_id)
        _identifier(self.experiment_id)
        if type(self.evaluation_config) is not PolicyEvaluationConfig:
            raise ValueError("journal requires a PolicyEvaluationConfig")
        _timestamp(self.created_at_utc)


@dataclass(frozen=True, slots=True)
class PolicyJournalCompletion:
    """Last marker binding the incremental trace to complete timed evidence."""

    serialization_schema: ClassVar[int] = 1

    header: ArtifactReference
    records: tuple[ArtifactReference, ...]
    timed_manifest: ArtifactReference
    evaluation_config_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.header, ArtifactReference) or self.header.name != "header.json":
            raise ValueError("journal completion requires its header")
        if (
            not isinstance(self.records, tuple)
            or not self.records
            or not all(isinstance(item, ArtifactReference) for item in self.records)
            or tuple(item.name for item in self.records)
            != tuple(_step_name(index) for index in range(len(self.records)))
        ):
            raise ValueError("journal completion requires contiguous step records")
        if (
            not isinstance(self.timed_manifest, ArtifactReference)
            or self.timed_manifest.name != "timed/manifest.json"
        ):
            raise ValueError("journal completion requires timed evidence")
        _digest(self.evaluation_config_id)


@dataclass(frozen=True, slots=True)
class PolicyJournalSnapshot:
    """Verified complete, failed, or interrupted journal state."""

    header: PolicyJournalHeader
    records: tuple[SearchCampaignCompletedStep, ...]
    header_sha256: str
    record_sha256: tuple[str, ...]
    completed_campaign: VerifiedTimedPolicyEvidence | None
    failure: FailureRecord | None
    completion_sha256: str | None
    failure_sha256: str | None

    @property
    def complete(self) -> bool:
        return self.completed_campaign is not None

    @property
    def infrastructure_invalid(self) -> bool:
        return self.failure is not None


def _step_name(index: int) -> str:
    return f"step-{index:08d}.json"


def _consume(
    header: PolicyJournalHeader, records: tuple[SearchCampaignCompletedStep, ...]
) -> SearchState | None:
    """Replay policy, RNG selection and mutation without running a target."""
    declared = header.evaluation_config
    campaign = declared.campaign
    initial = declared.initial_case_ids
    if len(records) > campaign.execution_budget:
        raise ValueError("policy journal exceeds execution budget")

    seed_count = min(len(records), len(initial))
    for index, record in enumerate(records):
        step = record.step
        if type(step.index) is not int or step.index != index:
            raise ValueError("policy journal step index gap/mismatch")
        verify_run(step.result)
        verify_binding(step.result, declared.provenance)
        if index < len(initial):
            if (
                step.origin != CampaignOrigin.SEED
                or step.parent_case_id is not None
                or record.mutation_attempt is not None
                or step.result.case.case_id != initial[index]
            ):
                raise ValueError("policy journal seed lineage mismatch")
        elif step.origin != CampaignOrigin.MUTATION or record.mutation_attempt is None:
            raise ValueError("policy journal mutation lineage mismatch")

    if not records:
        return None
    state = SearchState(
        tuple(record.step.result.case for record in records[:seed_count]),
        campaign.search_policy,
        projection=campaign.feedback_projection,
    )
    rng = random.Random(campaign.random_seed)
    for index, record in enumerate(records):
        step = record.step
        if index >= len(initial):
            parent = state.select_case(rng)
            expected = mutate_attempt_with_policy(parent, rng, campaign.mutation_policy)
            if (
                step.parent_case_id != parent.case_id
                or record.mutation_attempt != expected
                or expected.applied != (expected.child_case != parent)
                or step.result.case != expected.child_case
            ):
                raise ValueError("policy journal mutation replay mismatch")
        if step.feedback != state.consider(step.result):
            raise ValueError("policy journal feedback replay mismatch")
    return state


def _result(
    header: PolicyJournalHeader, records: tuple[SearchCampaignCompletedStep, ...]
) -> SearchCampaignResult:
    campaign = header.evaluation_config.campaign
    if len(records) != campaign.execution_budget:
        raise ValueError("incomplete policy journal cannot be finalized")
    state = _consume(header, records)
    assert state is not None
    active = state.active_case
    return SearchCampaignResult(
        campaign,
        header.evaluation_config.initial_case_ids,
        tuple(record.step for record in records),
        state.stats,
        tuple(entry.case.case_id for entry in state.entries),
        state.unique_feedback_keys,
        None if active is None else active.case_id,
        header.evaluation_config.provenance,
    )


def _references(
    header_digest: str, record_digests: tuple[str, ...]
) -> tuple[ArtifactReference, ...]:
    return (
        ArtifactReference("header.json", header_digest),
        *(
            ArtifactReference(_step_name(index), digest)
            for index, digest in enumerate(record_digests)
        ),
    )


def _verify_failure(
    failure: FailureRecord,
    header: PolicyJournalHeader,
    header_digest: str,
    record_digests: tuple[str, ...],
) -> None:
    context = failure.context
    expected_last = len(record_digests) - 1 if record_digests else None
    if (
        context.attempt_id != header.attempt_id
        or context.experiment_id != header.experiment_id
        or context.source != header.evaluation_config.provenance.source
        or context.target != header.evaluation_config.provenance.target
        or context.config_id != header.evaluation_config.config_id
        or context.last_fully_completed_step != expected_last
        or context.artifacts != _references(header_digest, record_digests)
        or context.cleanup_status != CleanupStatus.UNKNOWN
    ):
        raise ValueError("failure record differs from policy journal evidence")
    expected_step = (
        len(record_digests)
        if len(record_digests) < header.evaluation_config.campaign.execution_budget
        else None
    )
    if context.step_index != expected_step:
        raise ValueError("failure attempted-step accounting mismatch")


def read_policy_journal(
    directory: Path, *, expected_completion_sha256: str | None = None
) -> PolicyJournalSnapshot:
    """Verify a prefix; only a bound completion marker makes it complete."""
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("expected a policy journal directory")
        names = {path.name for path in directory.iterdir()}
        record_names = sorted(
            name for name in names if name.startswith("step-") and name.endswith(".json")
        )
        allowed = {"header.json", "completion.json", "failure.json", "timed", *record_names}
        if any(name not in allowed and not name.startswith(".record-") for name in names):
            raise ValueError("unexpected policy journal artifact")
        if record_names != [_step_name(index) for index in range(len(record_names))]:
            raise ValueError("policy journal record gap")
        if "completion.json" in names and "failure.json" in names:
            raise ValueError("policy journal cannot be complete and infrastructure-invalid")
        if expected_completion_sha256 is not None and "completion.json" not in names:
            raise ValueError("trusted completion digest supplied for a non-complete journal")

        header_path = directory / "header.json"
        header_digest = sha256(_read_file(header_path)).hexdigest()
        header = read_record(header_path, PolicyJournalHeader, expected_sha256=header_digest)
        record_digests = tuple(
            sha256(_read_file(directory / name)).hexdigest() for name in record_names
        )
        records = tuple(
            read_record(directory / name, SearchCampaignCompletedStep) for name in record_names
        )
        _consume(header, records)

        completed = None
        completion_digest = None
        if "completion.json" in names:
            completion_path = directory / "completion.json"
            completion_digest = sha256(_read_file(completion_path)).hexdigest()
            if expected_completion_sha256 is not None and completion_digest != _digest(
                expected_completion_sha256
            ):
                raise ValueError("policy journal completion checksum mismatch")
            marker = read_record(
                completion_path,
                PolicyJournalCompletion,
                expected_sha256=completion_digest,
            )
            expected_refs = _references(header_digest, record_digests)
            if (
                marker.header != expected_refs[0]
                or marker.records != expected_refs[1:]
                or marker.evaluation_config_id != header.evaluation_config.config_id
            ):
                raise ValueError("completion marker differs from policy journal")
            completed = verify_timed_policy_evidence(
                directory / "timed",
                expected_manifest_sha256=marker.timed_manifest.sha256,
            )
            if completed.campaign.config != header.evaluation_config or (
                completed.campaign.campaign.result != _result(header, records)
            ):
                raise ValueError("completed timed evidence differs from policy journal")

        failure = None
        failure_digest = None
        if "failure.json" in names:
            failure_path = directory / "failure.json"
            failure_digest = sha256(_read_file(failure_path)).hexdigest()
            failure = read_failure(failure_path, expected_sha256=failure_digest)
            _verify_failure(failure, header, header_digest, record_digests)
        return PolicyJournalSnapshot(
            header,
            records,
            header_digest,
            record_digests,
            completed,
            failure,
            completion_digest,
            failure_digest,
        )
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid policy evidence journal: {error}") from error


class PolicyEvidenceJournal:
    """Single-writer durable trace; never a campaign checkpoint or resume API."""

    def __init__(self, directory: Path):
        self.directory = directory

    @classmethod
    def create(cls, directory: Path, header: PolicyJournalHeader) -> "PolicyEvidenceJournal":
        if not isinstance(header, PolicyJournalHeader):
            raise ValueError("expected a PolicyJournalHeader")
        directory.mkdir(parents=True, exist_ok=False)
        write_record(directory / "header.json", header)
        sync_directory(directory.parent)
        return cls(directory)

    def append(self, record: SearchCampaignCompletedStep) -> str:
        snapshot = read_policy_journal(self.directory)
        if (
            snapshot.complete
            or snapshot.infrastructure_invalid
            or (self.directory / "timed").exists()
        ):
            raise ValueError("policy journal is already terminal or finalization started")
        if (
            type(record) is not SearchCampaignCompletedStep
            or type(record.step.index) is not int
            or record.step.index != len(snapshot.records)
        ):
            raise ValueError("append requires the next completed policy record")
        _consume(snapshot.header, (*snapshot.records, record))
        return write_record(self.directory / _step_name(record.step.index), record)

    def fail(self, exception: Exception, phase: FailurePhase) -> FailureRecord:
        """Publish a terminal infrastructure record without inventing run evidence."""
        if not isinstance(exception, Exception) or not isinstance(phase, FailurePhase):
            raise ValueError("failure publication requires an exception and phase")
        snapshot = read_policy_journal(self.directory)
        if snapshot.complete or snapshot.infrastructure_invalid:
            raise ValueError("policy journal is already terminal")
        completed = len(snapshot.records)
        budget = snapshot.header.evaluation_config.campaign.execution_budget
        context = FailureContext(
            snapshot.header.attempt_id,
            snapshot.header.experiment_id,
            snapshot.header.evaluation_config.provenance.source,
            snapshot.header.evaluation_config.provenance.target,
            completed if completed < budget else None,
            phase,
            completed - 1 if completed else None,
            snapshot.header.evaluation_config.config_id,
            ("opaque campaign execution does not expose a narrower lifecycle phase",)
            if phase == FailurePhase.UNKNOWN
            else (),
            cleanup_status=CleanupStatus.UNKNOWN,
            artifacts=_references(snapshot.header_sha256, snapshot.record_sha256),
        )
        record = failure_record(exception, context)
        write_failure(self.directory / "failure.json", record)
        return record

    def finish(self, timed: TimedPolicyCampaign) -> VerifiedTimedPolicyEvidence:
        """Bind exact-budget journal records to the complete timed policy bundle."""
        if not isinstance(timed, TimedPolicyCampaign):
            raise ValueError("finalization requires a TimedPolicyCampaign")
        snapshot = read_policy_journal(self.directory)
        if snapshot.completed_campaign is not None:
            return snapshot.completed_campaign
        if snapshot.infrastructure_invalid:
            raise ValueError("infrastructure-invalid policy journal cannot be finalized")
        result = _result(snapshot.header, snapshot.records)
        if timed.result != result:
            raise ValueError("timed campaign differs from policy journal replay")
        destination = self.directory / "timed"
        if not destination.exists():
            digest = export_timed_policy_result(
                timed, snapshot.header.evaluation_config, destination
            )
        else:
            digest = verify_timed_policy_evidence(destination).manifest_sha256
        verified = verify_timed_policy_evidence(destination, expected_manifest_sha256=digest)
        if (
            verified.campaign.config != snapshot.header.evaluation_config
            or verified.campaign.campaign.result != result
        ):
            raise VerificationError("existing timed evidence differs from policy journal")
        write_record(
            self.directory / "completion.json",
            PolicyJournalCompletion(
                ArtifactReference("header.json", snapshot.header_sha256),
                tuple(
                    ArtifactReference(_step_name(index), value)
                    for index, value in enumerate(snapshot.record_sha256)
                ),
                ArtifactReference("timed/manifest.json", digest),
                snapshot.header.evaluation_config.config_id,
            ),
        )
        completed = read_policy_journal(self.directory).completed_campaign
        assert completed is not None
        return completed


def run_journaled_timed_search_campaign(
    initial_cases: Sequence[ArchiveCase],
    target: CampaignTarget,
    evaluation_config: PolicyEvaluationConfig,
    directory: Path,
    *,
    attempt_id: str,
    experiment_id: str,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
) -> VerifiedTimedPolicyEvidence:
    """Run once with durable records; failures remain invalid, never no-hit."""
    if type(evaluation_config) is not PolicyEvaluationConfig:
        raise ValueError("evaluation_config must be a PolicyEvaluationConfig")
    cases = tuple(initial_cases)
    if (
        not cases
        or not all(isinstance(case, ArchiveCase) for case in cases)
        or tuple(case.case_id for case in cases) != evaluation_config.initial_case_ids
    ):
        raise ValueError("initial cases differ from the frozen evaluation configuration")
    header = PolicyJournalHeader(
        attempt_id,
        experiment_id,
        evaluation_config,
        datetime.now(UTC).isoformat(),
    )
    journal = PolicyEvidenceJournal.create(directory, header)

    def append_record(record: SearchCampaignCompletedStep) -> None:
        journal.append(record)

    try:
        timed = run_timed_search_campaign(
            cases,
            target,
            evaluation_config.campaign,
            sentinels=sentinels,
            provenance=evaluation_config.provenance,
            completed_record=append_record,
        )
    except Exception as error:
        try:
            journal.fail(error, FailurePhase.UNKNOWN)
        except Exception as ledger_error:
            error.add_note(
                "policy failure ledger publication also failed: "
                f"{type(ledger_error).__module__}.{type(ledger_error).__qualname__}: {ledger_error}"
            )
        raise
    try:
        return journal.finish(timed)
    except Exception as error:
        try:
            journal.fail(error, FailurePhase.PUBLICATION)
        except Exception as ledger_error:
            error.add_note(
                "policy failure ledger publication also failed: "
                f"{type(ledger_error).__module__}.{type(ledger_error).__qualname__}: {ledger_error}"
            )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--completion-sha256")
    args = parser.parse_args()
    try:
        snapshot = read_policy_journal(
            args.directory, expected_completion_sha256=args.completion_sha256
        )
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    status = (
        "complete"
        if snapshot.complete
        else "infrastructure_invalid"
        if snapshot.infrastructure_invalid
        else "incomplete"
    )
    print(
        json_bytes(
            {
                "classification": "verified-policy-journal-v1",
                "status": status,
                "attempt_id": snapshot.header.attempt_id,
                "evaluation_config_id": snapshot.header.evaluation_config.config_id,
                "completed_steps": len(snapshot.records),
                "execution_budget": snapshot.header.evaluation_config.campaign.execution_budget,
                "timed_manifest_sha256": None
                if snapshot.completed_campaign is None
                else snapshot.completed_campaign.manifest_sha256,
                "completion_sha256": snapshot.completion_sha256,
                "failure_sha256": snapshot.failure_sha256,
            }
        ).decode("ascii")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

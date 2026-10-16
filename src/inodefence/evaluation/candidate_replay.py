"""Exact-input affected/fixed replay evidence without known-class judgment."""

import argparse
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import ClassVar

from inodefence.campaign import CampaignConfig, CampaignOrigin, _prepare_campaign
from inodefence.model import ArchiveCase, RunResult
from inodefence.model.provenance import ExecutionProvenance, TargetProvenance
from inodefence.provenance import capture_source, sentinel_provenance
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
from .pair import PairArm, PairComparison, compare_pair, export_pair, read_pair
from .policy_binding import verify_bound_policy_evidence
from .storage import read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file, verify_binding, verify_run

PROTOCOL_VERSION = "policy-candidate-pair-replay-v1"
REPETITIONS = 3


def _text(value: str) -> None:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("identifier must be nonempty text without NUL")


def _timestamp(value: str) -> None:
    if not isinstance(value, str) or datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError("timestamp requires timezone-aware ISO-8601 text")


class CandidateReplayRole(StrEnum):
    AFFECTED = "affected"
    FIXED = "fixed"


@dataclass(frozen=True, slots=True)
class CandidateReplayScheduleEntry:
    repetition: int
    order: tuple[CandidateReplayRole, CandidateReplayRole]

    def __post_init__(self) -> None:
        if (
            type(self.repetition) is not int
            or not 0 <= self.repetition < REPETITIONS
            or not isinstance(self.order, tuple)
            or set(self.order) != set(CandidateReplayRole)
        ):
            raise ValueError("candidate replay requires one counterbalanced pair")


REPLAY_SCHEDULE = tuple(
    CandidateReplayScheduleEntry(
        repetition,
        (CandidateReplayRole.AFFECTED, CandidateReplayRole.FIXED)
        if repetition % 2 == 0
        else (CandidateReplayRole.FIXED, CandidateReplayRole.AFFECTED),
    )
    for repetition in range(REPETITIONS)
)


@dataclass(frozen=True, slots=True)
class CandidateOccurrence:
    step_index: int
    origin: CampaignOrigin
    parent_case_id: str | None

    def __post_init__(self) -> None:
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("candidate occurrence requires a nonnegative step")
        if not isinstance(self.origin, CampaignOrigin):
            raise ValueError("candidate occurrence requires a campaign origin")
        if self.origin == CampaignOrigin.SEED:
            if self.parent_case_id is not None:
                raise ValueError("seed occurrence cannot have a parent")
        else:
            _text(self.parent_case_id)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class PolicyCandidateNomination:
    """One exact case selected from verified completed policy evidence."""

    serialization_schema: ClassVar[int] = 1

    source_binding_sha256: str
    source_campaign_manifest_sha256: str
    source_evaluation_config_id: str
    case: ArchiveCase
    archive_sha256: str
    builder_format: str
    occurrences: tuple[CandidateOccurrence, ...]

    def __post_init__(self) -> None:
        for value in (
            self.source_binding_sha256,
            self.source_campaign_manifest_sha256,
            self.source_evaluation_config_id,
            self.archive_sha256,
        ):
            _digest(value)
        if not isinstance(self.case, ArchiveCase):
            raise ValueError("candidate nomination requires exact logical case")
        _text(self.builder_format)
        if (
            not isinstance(self.occurrences, tuple)
            or not self.occurrences
            or not all(isinstance(item, CandidateOccurrence) for item in self.occurrences)
            or tuple(item.step_index for item in self.occurrences)
            != tuple(sorted({item.step_index for item in self.occurrences}))
        ):
            raise ValueError("candidate occurrences must be unique and step-ordered")


def nominate_policy_candidate(
    source_directory: Path,
    case_id: str,
    *,
    expected_binding_sha256: str | None = None,
) -> PolicyCandidateNomination:
    """Select every occurrence of one case from freshly verified policy evidence."""
    _digest(case_id)
    verified = verify_bound_policy_evidence(
        source_directory, expected_binding_sha256=expected_binding_sha256
    )
    selected = tuple(
        step for step in verified.campaign.result.steps if step.result.case.case_id == case_id
    )
    if not selected:
        raise VerificationError("candidate case is absent from verified policy evidence")
    reference = selected[0].result
    if any(
        step.result.case != reference.case
        or step.result.archive_sha256 != reference.archive_sha256
        or step.result.archive_format != reference.archive_format
        for step in selected
    ):
        raise VerificationError("candidate occurrences disagree on exact input identity")
    return PolicyCandidateNomination(
        verified.binding_sha256,
        verified.campaign.manifest_sha256,
        verified.config.config_id,
        reference.case,
        reference.archive_sha256,
        reference.archive_format,
        tuple(
            CandidateOccurrence(step.index, step.origin, step.parent_case_id) for step in selected
        ),
    )


def verify_policy_candidate(nomination: PolicyCandidateNomination, source_directory: Path) -> None:
    if not isinstance(nomination, PolicyCandidateNomination):
        raise ValueError("typed candidate nomination required")
    reproduced = nominate_policy_candidate(
        source_directory,
        nomination.case.case_id,
        expected_binding_sha256=nomination.source_binding_sha256,
    )
    if reproduced != nomination:
        raise VerificationError("candidate nomination differs from source policy evidence")


@dataclass(frozen=True, slots=True)
class CandidateReplayRequest:
    serialization_schema: ClassVar[int] = 1

    attempt_id: str
    nomination: PolicyCandidateNomination
    affected_target: TargetProvenance
    fixed_target: TargetProvenance
    sentinels: tuple[SentinelSpec, ...]
    schedule: tuple[CandidateReplayScheduleEntry, ...] = REPLAY_SCHEDULE
    protocol_version: str = PROTOCOL_VERSION
    created_at_utc: str = ""

    def __post_init__(self) -> None:
        _text(self.attempt_id)
        if not isinstance(self.nomination, PolicyCandidateNomination):
            raise ValueError("replay request requires verified candidate identity")
        if not all(
            isinstance(item, TargetProvenance) for item in (self.affected_target, self.fixed_target)
        ):
            raise ValueError("replay request requires two target declarations")
        if (
            self.affected_target.target_id != self.fixed_target.target_id
            or self.affected_target.timeout_seconds != self.fixed_target.timeout_seconds
            or self.affected_target.execution_safety != self.fixed_target.execution_safety
        ):
            raise ValueError("replay targets require equal adapter, timeout and safety")
        if (
            not isinstance(self.sentinels, tuple)
            or not self.sentinels
            or not all(isinstance(item, SentinelSpec) for item in self.sentinels)
            or self.schedule != REPLAY_SCHEDULE
            or self.protocol_version != PROTOCOL_VERSION
        ):
            raise ValueError("replay request differs from protocol v1")
        sentinel_provenance(self.sentinels)
        _timestamp(self.created_at_utc)


@dataclass(frozen=True, slots=True)
class CandidateReplayHeader:
    serialization_schema: ClassVar[int] = 1

    request: ArtifactReference
    affected_provenance: ExecutionProvenance
    fixed_provenance: ExecutionProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.request, ArtifactReference) or self.request.name != "request.json":
            raise ValueError("replay header requires request reference")
        if not all(
            isinstance(item, ExecutionProvenance)
            for item in (self.affected_provenance, self.fixed_provenance)
        ):
            raise ValueError("replay header requires frozen arm provenance")


@dataclass(frozen=True, slots=True)
class CandidateReplayRun:
    serialization_schema: ClassVar[int] = 1

    run_index: int
    repetition: int
    schedule_position: int
    role: CandidateReplayRole
    provenance: ExecutionProvenance
    result: RunResult
    runtime_root_absent_after_return: bool
    recorded_at_utc: str

    def __post_init__(self) -> None:
        if (
            type(self.run_index) is not int
            or not 0 <= self.run_index < REPETITIONS * 2
            or type(self.repetition) is not int
            or not 0 <= self.repetition < REPETITIONS
            or type(self.schedule_position) is not int
            or self.schedule_position not in (0, 1)
            or not isinstance(self.role, CandidateReplayRole)
            or not isinstance(self.provenance, ExecutionProvenance)
            or not isinstance(self.result, RunResult)
            or type(self.runtime_root_absent_after_return) is not bool
        ):
            raise ValueError("invalid candidate replay record")
        verify_run(self.result)
        verify_binding(self.result, self.provenance)
        _timestamp(self.recorded_at_utc)


@dataclass(frozen=True, slots=True)
class CandidateReplayCompletion:
    serialization_schema: ClassVar[int] = 1

    request: ArtifactReference
    header: ArtifactReference
    runs: tuple[ArtifactReference, ...]
    pairs: tuple[ArtifactReference, ...]
    completed_at_utc: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.request, ArtifactReference)
            or self.request.name != "request.json"
            or not isinstance(self.header, ArtifactReference)
            or self.header.name != "header.json"
            or len(self.runs) != REPETITIONS * 2
            or len(self.pairs) != REPETITIONS
            or not all(isinstance(item, ArtifactReference) for item in (*self.runs, *self.pairs))
        ):
            raise ValueError("candidate completion requires the exact replay budget")
        _timestamp(self.completed_at_utc)


@dataclass(frozen=True, slots=True)
class CandidateReplaySnapshot:
    request: CandidateReplayRequest
    header: CandidateReplayHeader | None
    runs: tuple[CandidateReplayRun, ...]
    pairs: tuple[PairComparison, ...]
    failure: FailureRecord | None
    completion: CandidateReplayCompletion | None
    request_sha256: str
    header_sha256: str | None
    run_sha256: tuple[str, ...]
    pair_sha256: tuple[str, ...]
    failure_sha256: str | None
    completion_sha256: str | None

    @property
    def complete(self) -> bool:
        return self.completion is not None

    @property
    def infrastructure_invalid(self) -> bool:
        return self.failure is not None


def _run_name(index: int) -> str:
    return f"runs/run-{index:08d}.json"


def _pair_name(repetition: int) -> str:
    return f"pairs/repetition-{repetition:08d}.json"


def _reference(root: Path, name: str) -> ArtifactReference:
    return ArtifactReference(name, sha256(_read_file(root / name)).hexdigest())


def _available_references(root: Path) -> tuple[ArtifactReference, ...]:
    names = ["request.json"]
    if (root / "header.json").is_file():
        names.append("header.json")
    for index in range(REPETITIONS * 2):
        name = _run_name(index)
        if not (root / name).is_file():
            break
        names.append(name)
    for repetition in range(REPETITIONS):
        name = _pair_name(repetition)
        if (root / name).is_file():
            names.append(name)
    return tuple(_reference(root, name) for name in names)


def _verify_failure_context(
    failure: FailureRecord,
    request: CandidateReplayRequest,
    header: CandidateReplayHeader | None,
    runs: tuple[CandidateReplayRun, ...],
    artifacts: tuple[ArtifactReference, ...],
) -> None:
    context = failure.context
    expected_last = len(runs) - 1 if runs else None
    expected_cleanup = (
        CleanupStatus.FAILED if context.phase == FailurePhase.CLEANUP else CleanupStatus.UNKNOWN
    )
    if (
        context.attempt_id != request.attempt_id
        or context.experiment_id != request.protocol_version
        or context.config_id != request.nomination.source_evaluation_config_id
        or context.last_fully_completed_step != expected_last
        or context.artifacts != artifacts
        or context.cleanup_status != expected_cleanup
        or (header is not None and context.source != header.affected_provenance.source)
    ):
        raise ValueError("candidate failure record differs from available prefix")

    if context.step_index is None:
        if context.target is not None or context.phase not in {
            FailurePhase.SETUP,
            FailurePhase.PUBLICATION,
        }:
            raise ValueError("candidate failure lacks a consistent attempted run")
        return
    if header is None or not 0 <= context.step_index < REPETITIONS * 2:
        raise ValueError("candidate failure attempted run lacks frozen provenance")
    repetition, position = divmod(context.step_index, 2)
    role = request.schedule[repetition].order[position]
    expected_provenance = (
        header.affected_provenance
        if role == CandidateReplayRole.AFFECTED
        else header.fixed_provenance
    )
    possible_steps = {len(runs)} if len(runs) < REPETITIONS * 2 else set()
    if runs:
        possible_steps.add(len(runs) - 1)
    if (
        context.target != expected_provenance.target
        or context.phase
        not in {FailurePhase.EXECUTION, FailurePhase.PUBLICATION, FailurePhase.CLEANUP}
        or context.step_index not in possible_steps
        or (context.phase == FailurePhase.EXECUTION and context.step_index != len(runs))
        or (
            context.phase == FailurePhase.CLEANUP
            and (
                not runs
                or context.step_index != len(runs) - 1
                or runs[-1].runtime_root_absent_after_return
            )
        )
    ):
        raise ValueError("candidate failure attempted-run accounting mismatch")


def _expected_run(
    request: CandidateReplayRequest,
    header: CandidateReplayHeader,
    index: int,
    record: CandidateReplayRun,
) -> None:
    repetition, position = divmod(index, 2)
    role = request.schedule[repetition].order[position]
    provenance = (
        header.affected_provenance
        if role == CandidateReplayRole.AFFECTED
        else header.fixed_provenance
    )
    if (
        record.run_index != index
        or record.repetition != repetition
        or record.schedule_position != position
        or record.role != role
        or record.provenance != provenance
        or record.result.case != request.nomination.case
        or record.result.archive_sha256 != request.nomination.archive_sha256
        or record.result.archive_format != request.nomination.builder_format
    ):
        raise ValueError("candidate replay differs from request, schedule or input")


def _isolation_context(provenance: ExecutionProvenance) -> object:
    isolation = provenance.isolation
    if isolation is None:
        return None
    policy = isolation.policy
    return (
        replace(policy, image_id="sha256:" + "0" * 64),
        isolation.runtime_name,
        isolation.runtime_version,
        isolation.runtime_api_version,
        isolation.runtime_os,
        isolation.runtime_architecture,
        isolation.image_architecture,
        isolation.schema_version,
        isolation.artifact_origin,
    )


def read_candidate_replay(
    root: Path,
    source_policy_directory: Path,
    *,
    expected_completion_sha256: str | None = None,
) -> CandidateReplaySnapshot:
    """Verify complete, failed or interrupted exact-input replay evidence."""
    try:
        if root.is_symlink() or not root.is_dir():
            raise ValueError("expected candidate replay directory")
        allowed = {
            "request.json",
            "header.json",
            "completion.json",
            "failure.json",
            "runs",
            "pairs",
        }
        if any(
            path.name not in allowed and not path.name.startswith(".record-")
            for path in root.iterdir()
        ):
            raise ValueError("unexpected candidate replay artifact")
        request_sha = sha256(_read_file(root / "request.json")).hexdigest()
        request = read_record(
            root / "request.json", CandidateReplayRequest, expected_sha256=request_sha
        )
        verify_policy_candidate(request.nomination, source_policy_directory)

        header = None
        header_sha = None
        if (root / "header.json").is_file():
            header_sha = sha256(_read_file(root / "header.json")).hexdigest()
            header = read_record(
                root / "header.json", CandidateReplayHeader, expected_sha256=header_sha
            )
            if header.request != ArtifactReference("request.json", request_sha):
                raise ValueError("replay header request checksum mismatch")
            if (
                header.affected_provenance.target != request.affected_target
                or header.fixed_provenance.target != request.fixed_target
                or header.affected_provenance.sentinels != sentinel_provenance(request.sentinels)
                or header.fixed_provenance.sentinels != sentinel_provenance(request.sentinels)
                or header.affected_provenance.source != header.fixed_provenance.source
                or header.affected_provenance.environment != header.fixed_provenance.environment
                or _isolation_context(header.affected_provenance)
                != _isolation_context(header.fixed_provenance)
            ):
                raise ValueError("replay header differs from target/setup request")

        runs, run_sha = [], []
        for index in range(REPETITIONS * 2):
            path = root / _run_name(index)
            if not path.exists():
                break
            if header is None:
                raise ValueError("replay run exists without frozen header")
            digest = sha256(_read_file(path)).hexdigest()
            record = read_record(path, CandidateReplayRun, expected_sha256=digest)
            _expected_run(request, header, index, record)
            runs.append(record)
            run_sha.append(digest)
        runs_directory = root / "runs"
        if runs_directory.exists() and (
            runs_directory.is_symlink()
            or not runs_directory.is_dir()
            or {path.name for path in runs_directory.iterdir()}
            != {Path(_run_name(index)).name for index in range(len(runs))}
        ):
            raise ValueError("candidate replay runs are not one contiguous prefix")

        pairs, pair_sha = [], []
        for repetition in range(REPETITIONS):
            path = root / _pair_name(repetition)
            if not path.exists():
                continue
            if len(runs) < (repetition + 1) * 2 or header is None:
                raise ValueError("pair comparison exists before both arm records")
            digest = sha256(_read_file(path)).hexdigest()
            pair = read_pair(path, expected_sha256=digest)
            two = runs[repetition * 2 : repetition * 2 + 2]
            by_role = {item.role: item for item in two}
            expected = compare_pair(
                request.nomination.case,
                PairArm(
                    by_role[CandidateReplayRole.AFFECTED].provenance,
                    by_role[CandidateReplayRole.AFFECTED].result,
                ),
                PairArm(
                    by_role[CandidateReplayRole.FIXED].provenance,
                    by_role[CandidateReplayRole.FIXED].result,
                ),
            )
            if pair != expected:
                raise ValueError("pair comparison differs from retained arm records")
            pairs.append(pair)
            pair_sha.append(digest)
        pairs_directory = root / "pairs"
        if pairs_directory.exists() and (
            pairs_directory.is_symlink()
            or not pairs_directory.is_dir()
            or {path.name for path in pairs_directory.iterdir()}
            != {Path(_pair_name(repetition)).name for repetition in range(len(pairs))}
        ):
            raise ValueError("candidate pair records are not one contiguous prefix")

        failure = None
        failure_sha = None
        if (root / "failure.json").is_file():
            failure_sha = sha256(_read_file(root / "failure.json")).hexdigest()
            failure = read_failure(root / "failure.json", expected_sha256=failure_sha)
            _verify_failure_context(
                failure,
                request,
                header,
                tuple(runs),
                _available_references(root),
            )

        completion = None
        completion_sha = None
        if (root / "completion.json").is_file():
            completion_sha = sha256(_read_file(root / "completion.json")).hexdigest()
            if expected_completion_sha256 is not None and completion_sha != _digest(
                expected_completion_sha256
            ):
                raise ValueError("candidate completion checksum mismatch")
            completion = read_record(
                root / "completion.json",
                CandidateReplayCompletion,
                expected_sha256=completion_sha,
            )
            if failure is not None:
                raise ValueError("candidate replay cannot be both complete and failed")
            if (
                header_sha is None
                or completion.request != ArtifactReference("request.json", request_sha)
                or completion.header != ArtifactReference("header.json", header_sha)
                or completion.runs
                != tuple(
                    ArtifactReference(_run_name(index), digest)
                    for index, digest in enumerate(run_sha)
                )
                or completion.pairs
                != tuple(
                    ArtifactReference(_pair_name(index), digest)
                    for index, digest in enumerate(pair_sha)
                )
                or len(runs) != REPETITIONS * 2
                or len(pairs) != REPETITIONS
                or not all(item.runtime_root_absent_after_return for item in runs)
            ):
                raise ValueError("candidate completion differs from exact replay evidence")
        elif expected_completion_sha256 is not None:
            raise ValueError("expected candidate completion is absent")

        return CandidateReplaySnapshot(
            request,
            header,
            tuple(runs),
            tuple(pairs),
            failure,
            completion,
            request_sha,
            header_sha,
            tuple(run_sha),
            tuple(pair_sha),
            failure_sha,
            completion_sha,
        )
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid candidate replay evidence: {error}") from error


def run_candidate_replays(
    source_policy_directory: Path,
    case_id: str,
    evidence_root: Path,
    affected_target: CampaignTarget,
    fixed_target: CampaignTarget,
    *,
    attempt_id: str,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    expected_source_binding_sha256: str | None = None,
) -> CandidateReplaySnapshot:
    """Run the fixed 3+3 schedule once; retain results before any classification."""
    if evidence_root.exists() or evidence_root.is_symlink():
        raise ValueError("candidate replay evidence root must be a new path")
    nomination = nominate_policy_candidate(
        source_policy_directory,
        case_id,
        expected_binding_sha256=expected_source_binding_sha256,
    )
    request = CandidateReplayRequest(
        attempt_id,
        nomination,
        affected_target.provenance,
        fixed_target.provenance,
        sentinels,
        created_at_utc=datetime.now(UTC).isoformat(),
    )
    evidence_root.mkdir(parents=True, exist_ok=False)
    sync_directory(evidence_root.parent)
    request_sha = write_record(evidence_root / "request.json", request)
    current_target: TargetProvenance | None = None
    phase = FailurePhase.SETUP
    attempted_index: int | None = None
    run_references: list[ArtifactReference] = []
    pair_references: list[ArtifactReference] = []
    header: CandidateReplayHeader | None = None
    try:
        prepared = {
            CandidateReplayRole.AFFECTED: _prepare_campaign(
                (nomination.case,),
                affected_target,
                CampaignConfig(0, 1),
                sentinels=sentinels,
            ),
            CandidateReplayRole.FIXED: _prepare_campaign(
                (nomination.case,),
                fixed_target,
                CampaignConfig(0, 1),
                sentinels=sentinels,
            ),
        }
        header = CandidateReplayHeader(
            ArtifactReference("request.json", request_sha),
            prepared[CandidateReplayRole.AFFECTED].provenance,
            prepared[CandidateReplayRole.FIXED].provenance,
        )
        if (
            header.affected_provenance.source != header.fixed_provenance.source
            or header.affected_provenance.environment != header.fixed_provenance.environment
        ):
            raise ValueError("candidate replay arms require one source/environment")
        phase = FailurePhase.PUBLICATION
        header_sha = write_record(evidence_root / "header.json", header)
        run_index = 0
        for schedule in request.schedule:
            by_role: dict[CandidateReplayRole, CandidateReplayRun] = {}
            for position, role in enumerate(schedule.order):
                execution = prepared[role]
                current_target = execution.provenance.target
                attempted_index = run_index
                phase = FailurePhase.EXECUTION
                result = execution.execute(nomination.case)
                record = CandidateReplayRun(
                    run_index,
                    schedule.repetition,
                    position,
                    role,
                    execution.provenance,
                    result,
                    not Path(result.after.sandbox_root).exists(),
                    datetime.now(UTC).isoformat(),
                )
                name = _run_name(run_index)
                phase = FailurePhase.PUBLICATION
                digest = write_record(evidence_root / name, record)
                run_references.append(ArtifactReference(name, digest))
                by_role[role] = record
                run_index += 1
                if not record.runtime_root_absent_after_return:
                    phase = FailurePhase.CLEANUP
                    raise RuntimeError("candidate replay runtime root remains after return")
            pair = compare_pair(
                nomination.case,
                PairArm(
                    by_role[CandidateReplayRole.AFFECTED].provenance,
                    by_role[CandidateReplayRole.AFFECTED].result,
                ),
                PairArm(
                    by_role[CandidateReplayRole.FIXED].provenance,
                    by_role[CandidateReplayRole.FIXED].result,
                ),
            )
            name = _pair_name(schedule.repetition)
            phase = FailurePhase.PUBLICATION
            digest = export_pair(pair, evidence_root / name)
            pair_references.append(ArtifactReference(name, digest))
        phase = FailurePhase.PUBLICATION
        completion = CandidateReplayCompletion(
            ArtifactReference("request.json", request_sha),
            ArtifactReference("header.json", header_sha),
            tuple(run_references),
            tuple(pair_references),
            datetime.now(UTC).isoformat(),
        )
        completion_sha = write_record(evidence_root / "completion.json", completion)
    except Exception as error:
        source = header.affected_provenance.source if header is not None else capture_source()
        artifacts = _available_references(evidence_root)
        available_runs = sum(item.name.startswith("runs/") for item in artifacts)
        context = FailureContext(
            request.attempt_id,
            request.protocol_version,
            source,
            current_target,
            attempted_index
            if phase in {FailurePhase.EXECUTION, FailurePhase.PUBLICATION, FailurePhase.CLEANUP}
            else None,
            phase,
            available_runs - 1 if available_runs else None,
            nomination.source_evaluation_config_id,
            cleanup_status=(
                CleanupStatus.FAILED if phase == FailurePhase.CLEANUP else CleanupStatus.UNKNOWN
            ),
            artifacts=artifacts,
        )
        try:
            write_failure(evidence_root / "failure.json", failure_record(error, context))
        except Exception as ledger_error:
            error.add_note(
                "candidate replay failure publication also failed: "
                f"{type(ledger_error).__module__}.{type(ledger_error).__qualname__}: "
                f"{ledger_error}"
            )
        raise
    return read_candidate_replay(
        evidence_root,
        source_policy_directory,
        expected_completion_sha256=completion_sha,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("source_policy_evidence", type=Path)
    parser.add_argument("--completion-sha256")
    args = parser.parse_args()
    try:
        snapshot = read_candidate_replay(
            args.evidence,
            args.source_policy_evidence,
            expected_completion_sha256=args.completion_sha256,
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
                "classification": "verified-policy-candidate-pair-replay-v1",
                "status": status,
                "candidate_case_id": snapshot.request.nomination.case.case_id,
                "source_binding_sha256": snapshot.request.nomination.source_binding_sha256,
                "runs": len(snapshot.runs),
                "pairs": len(snapshot.pairs),
                "completion_sha256": snapshot.completion_sha256,
                "failure_sha256": snapshot.failure_sha256,
            }
        ).decode("ascii")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

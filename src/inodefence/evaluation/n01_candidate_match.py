"""N01 machine contrast for verified policy-candidate replay evidence."""

import argparse
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from inodefence.campaign import CampaignOrigin
from inodefence.feedback import FeedbackProjection
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ContractId,
    ExecutionStatus,
    IdentityEvidence,
    Region,
    RunResult,
    canonical_json,
)
from inodefence.model.filesystem import path_region, validate_observed_path
from inodefence.model.isolation import IsolationPolicy
from inodefence.model.provenance import ExecutionProvenance, ExecutionSafety
from inodefence.mutator import MutationPolicy
from inodefence.provenance import sentinel_provenance
from inodefence.runtime import SentinelSpec

from .candidate_replay import (
    CandidateReplayRole,
    CandidateReplayRun,
    CandidateReplaySnapshot,
    PolicyCandidateNomination,
    nominate_policy_candidate,
    read_candidate_replay,
)
from .n01 import NODE_VERSION, WORKER_SHA256, N01Role, frozen_target
from .policy_binding import VerifiedBoundPolicyEvidence, verify_bound_policy_evidence
from .verify import VerificationError, _digest

PROTOCOL_VERSION = "n01-policy-candidate-machine-match-v1"
SENTINEL_PATH = "outside/sentinel.txt"


class N01CandidateMachineStatus(StrEnum):
    MACHINE_CONTRAST_PASS_PENDING_HUMAN = "machine_contrast_pass_pending_human"
    AMBIGUOUS = "ambiguous"
    NOT_NOMINATED = "not_nominated"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, order=True, slots=True)
class N01Relation:
    internal_path: str
    sentinel_path: str

    def __post_init__(self) -> None:
        validate_observed_path(self.internal_path)
        validate_observed_path(self.sentinel_path)
        if (
            path_region(self.internal_path) != Region.EXTRACTION
            or self.sentinel_path != SENTINEL_PATH
            or path_region(self.sentinel_path) != Region.EXTERNAL
        ):
            raise ValueError("N01 relation requires extraction and controlled-sentinel paths")


@dataclass(frozen=True, slots=True)
class N01ReplayObservation:
    run_index: int
    role: CandidateReplayRole
    execution_status: ExecutionStatus
    relations: tuple[N01Relation, ...]
    selected_relation_present: bool
    c0: bool
    c1: bool
    c2: bool
    archive_unchanged: bool

    def __post_init__(self) -> None:
        if (
            type(self.run_index) is not int
            or self.run_index < 0
            or not isinstance(self.role, CandidateReplayRole)
            or not isinstance(self.execution_status, ExecutionStatus)
            or not isinstance(self.relations, tuple)
            or self.relations != tuple(sorted(set(self.relations)))
            or type(self.selected_relation_present) is not bool
            or type(self.archive_unchanged) is not bool
            or any(type(value) is not bool for value in (self.c0, self.c1, self.c2))
        ):
            raise ValueError("invalid N01 replay observation")


@dataclass(frozen=True, slots=True)
class N01PolicyCandidate:
    """One pre-replay relation selected from all verified source occurrences."""

    serialization_schema: ClassVar[int] = 1

    nomination: PolicyCandidateNomination
    selected_relation: N01Relation
    source_matching_steps: tuple[int, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.nomination, PolicyCandidateNomination)
            or not isinstance(self.selected_relation, N01Relation)
            or not isinstance(self.source_matching_steps, tuple)
            or not self.source_matching_steps
            or self.source_matching_steps != tuple(sorted(set(self.source_matching_steps)))
            or not all(type(item) is int and item >= 0 for item in self.source_matching_steps)
        ):
            raise ValueError("invalid N01 source candidate nomination")


@dataclass(frozen=True, slots=True)
class N01CandidateMachineAssessment:
    """Mechanical evidence disposition, never human confirmation or qualification."""

    serialization_schema: ClassVar[int] = 1

    protocol_version: str
    status: N01CandidateMachineStatus
    candidate_case_id: str
    source_binding_sha256: str
    replay_completion_sha256: str | None
    selected_relation: N01Relation | None
    source_matching_steps: tuple[int, ...]
    affected_matching_runs: int
    fixed_matching_runs: int
    observations: tuple[N01ReplayObservation, ...]
    diagnostics: tuple[str, ...]
    human_disposition: str = "pending_human_root_cause_review"
    confirmed_rediscovery: bool = False
    qualification_token: str | None = None

    def __post_init__(self) -> None:
        _digest(self.candidate_case_id)
        _digest(self.source_binding_sha256)
        if self.replay_completion_sha256 is not None:
            _digest(self.replay_completion_sha256)
        if (
            self.protocol_version != PROTOCOL_VERSION
            or not isinstance(self.status, N01CandidateMachineStatus)
            or (
                self.selected_relation is not None
                and not isinstance(self.selected_relation, N01Relation)
            )
            or not isinstance(self.source_matching_steps, tuple)
            or self.source_matching_steps != tuple(sorted(set(self.source_matching_steps)))
            or not all(type(item) is int and item >= 0 for item in self.source_matching_steps)
            or type(self.affected_matching_runs) is not int
            or not 0 <= self.affected_matching_runs <= 3
            or type(self.fixed_matching_runs) is not int
            or not 0 <= self.fixed_matching_runs <= 3
            or not isinstance(self.observations, tuple)
            or not all(isinstance(item, N01ReplayObservation) for item in self.observations)
            or tuple(item.run_index for item in self.observations)
            != tuple(range(len(self.observations)))
            or not isinstance(self.diagnostics, tuple)
            or not self.diagnostics
            or not all(isinstance(item, str) and item for item in self.diagnostics)
            or self.human_disposition != "pending_human_root_cause_review"
            or self.confirmed_rediscovery is not False
            or self.qualification_token is not None
        ):
            raise ValueError("invalid N01 candidate machine assessment")
        expected_affected = sum(
            item.selected_relation_present
            for item in self.observations
            if item.role == CandidateReplayRole.AFFECTED
        )
        expected_fixed = sum(
            item.selected_relation_present
            for item in self.observations
            if item.role == CandidateReplayRole.FIXED
        )
        if (
            self.affected_matching_runs != expected_affected
            or self.fixed_matching_runs != expected_fixed
            or (
                self.selected_relation is None
                and (self.source_matching_steps or expected_affected or expected_fixed)
            )
            or (
                self.selected_relation is not None
                and any(
                    item.selected_relation_present != (self.selected_relation in item.relations)
                    for item in self.observations
                )
            )
            or (
                self.status == N01CandidateMachineStatus.MACHINE_CONTRAST_PASS_PENDING_HUMAN
                and (
                    self.replay_completion_sha256 is None
                    or len(self.observations) != 6
                    or not self.source_matching_steps
                    or expected_affected != 3
                    or expected_fixed != 0
                )
            )
            or (
                self.status == N01CandidateMachineStatus.AMBIGUOUS
                and (
                    self.selected_relation is None
                    or not self.source_matching_steps
                    or (expected_affected == 3 and expected_fixed == 0)
                )
            )
            or (
                self.status == N01CandidateMachineStatus.NOT_NOMINATED
                and (self.selected_relation is not None or self.source_matching_steps)
            )
        ):
            raise ValueError("N01 assessment counts/status differ from observations")


def _violated(result: RunResult, contract: ContractId) -> bool:
    matching = tuple(item.violated for item in result.violations if item.contract_id == contract)
    if len(matching) != 1:
        raise VerificationError("run lacks one exact C0/C1/C2 result")
    return matching[0]


def _relations(result: RunResult) -> tuple[N01Relation, ...]:
    relations = []
    for verdict in result.violations:
        if verdict.contract_id != ContractId.C1:
            continue
        for evidence in verdict.evidence:
            if (
                not isinstance(evidence, IdentityEvidence)
                or evidence.sentinel_path != SENTINEL_PATH
            ):
                continue
            internal = result.after.get(evidence.internal_path)
            sentinel = result.after.get(evidence.sentinel_path)
            if (
                internal is None
                or sentinel is None
                or internal.region != Region.EXTRACTION
                or sentinel.region != Region.EXTERNAL
                or internal.identity != sentinel.identity
                or internal.identity != (evidence.st_dev, evidence.st_ino)
            ):
                raise VerificationError("N01 relation differs from verified post-state identity")
            relations.append(N01Relation(evidence.internal_path, evidence.sentinel_path))
    return tuple(sorted(set(relations)))


def _archive_unchanged(result: RunResult) -> bool:
    return result.before.get("archive/input.tar") == result.after.get("archive/input.tar")


def _target_binding(provenance: ExecutionProvenance, role: N01Role) -> bool:
    expected = frozen_target(role)
    target, isolation = provenance.target, provenance.isolation
    if (
        target.target_id != "node-tar-strict"
        or target.target_version != f"node={NODE_VERSION};tar={expected.tar_version}"
        or target.timeout_seconds not in (5.0, 10.0)
        or target.execution_safety != ExecutionSafety.ISOLATION_REQUIRED
        or isolation is None
        or isolation.policy != IsolationPolicy(isolation.policy.image_id, 1000, 1000)
    ):
        return False
    artifacts = {item.name: item.sha256 for item in isolation.artifacts}
    return artifacts == {
        "node-tar-package-lock": expected.lock_sha256,
        "node-tar-worker": WORKER_SHA256,
    }


def _source_matches_replay(
    source: VerifiedBoundPolicyEvidence, snapshot: CandidateReplaySnapshot
) -> bool:
    if snapshot.header is None:
        return False
    return (
        _source_candidate_context(source)
        and source.config.provenance == snapshot.header.affected_provenance
        and snapshot.request.sentinels == (SentinelSpec(),)
    )


def _source_candidate_context(source: VerifiedBoundPolicyEvidence) -> bool:
    provenance = source.config.provenance
    return (
        provenance.source.revision is not None
        and provenance.source.dirty is False
        and provenance.environment.system == "Linux"
        and provenance.sentinels == sentinel_provenance((SentinelSpec(),))
        and _target_binding(provenance, N01Role.AFFECTED)
        and source.config.initial_case_ids == tuple(case.case_id for case in minimal_seed_corpus())
        and source.config.campaign.mutation_policy == MutationPolicy.M1_PROTECTED_COMPONENTS
        and source.config.campaign.feedback_projection == FeedbackProjection.FULL
    )


def nominate_n01_policy_candidates(
    source_policy_directory: Path,
    *,
    expected_binding_sha256: str | None = None,
) -> tuple[N01PolicyCandidate, ...]:
    """Scan every raw mutation step and freeze candidates before any pair replay."""
    source = verify_bound_policy_evidence(
        source_policy_directory,
        expected_binding_sha256=expected_binding_sha256,
    )
    if not _source_candidate_context(source):
        raise VerificationError("policy evidence lacks the frozen N01 source/setup context")
    initial_ids = set(source.config.initial_case_ids)
    grouped: dict[str, dict[N01Relation, list[int]]] = {}
    for step in source.campaign.result.steps:
        result = step.result
        if (
            step.origin != CampaignOrigin.MUTATION
            or result.case.case_id in initial_ids
            or not _archive_unchanged(result)
        ):
            continue
        relations = _relations(result)
        if not relations:
            continue
        by_relation = grouped.setdefault(result.case.case_id, {})
        for relation in relations:
            by_relation.setdefault(relation, []).append(step.index)

    candidates = []
    for case_id, by_relation in grouped.items():
        selected = min(by_relation)
        candidates.append(
            N01PolicyCandidate(
                nominate_policy_candidate(
                    source_policy_directory,
                    case_id,
                    expected_binding_sha256=source.binding_sha256,
                ),
                selected,
                tuple(sorted(set(by_relation[selected]))),
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.source_matching_steps[0],
                candidate.nomination.case.case_id,
            ),
        )
    )


def _source_relations(
    source: VerifiedBoundPolicyEvidence,
    snapshot: CandidateReplaySnapshot,
) -> tuple[tuple[N01Relation, ...], dict[N01Relation, tuple[int, ...]]]:
    initial_ids = set(source.config.initial_case_ids)
    candidate_id = snapshot.request.nomination.case.case_id
    by_relation: dict[N01Relation, list[int]] = {}
    if candidate_id in initial_ids:
        return (), {}
    for occurrence in snapshot.request.nomination.occurrences:
        step = source.campaign.result.steps[occurrence.step_index]
        result = step.result
        if (
            step.origin != CampaignOrigin.MUTATION
            or result.case.case_id != candidate_id
            or not _archive_unchanged(result)
        ):
            continue
        for relation in _relations(result):
            by_relation.setdefault(relation, []).append(step.index)
    frozen = {relation: tuple(sorted(set(indexes))) for relation, indexes in by_relation.items()}
    return tuple(sorted(frozen)), frozen


def _observation(
    record: CandidateReplayRun,
    selected: N01Relation | None,
) -> N01ReplayObservation:
    relations = _relations(record.result)
    return N01ReplayObservation(
        record.run_index,
        record.role,
        record.result.execution.status,
        relations,
        selected is not None and selected in relations,
        _violated(record.result, ContractId.C0),
        _violated(record.result, ContractId.C1),
        _violated(record.result, ContractId.C2),
        _archive_unchanged(record.result),
    )


def assess_n01_candidate_replay(
    replay_root: Path,
    source_policy_directory: Path,
    *,
    expected_completion_sha256: str | None = None,
) -> N01CandidateMachineAssessment:
    """Recompute the N01 3/3 versus 0/3 contrast without a human verdict."""
    snapshot = read_candidate_replay(
        replay_root,
        source_policy_directory,
        expected_completion_sha256=expected_completion_sha256,
    )
    source = verify_bound_policy_evidence(
        source_policy_directory,
        expected_binding_sha256=snapshot.request.nomination.source_binding_sha256,
    )
    candidate_id = snapshot.request.nomination.case.case_id
    diagnostics: list[str] = []
    relations, source_steps = _source_relations(source, snapshot)
    selected = relations[0] if relations else None
    observations = tuple(_observation(record, selected) for record in snapshot.runs)
    affected = sum(
        item.selected_relation_present
        for item in observations
        if item.role == CandidateReplayRole.AFFECTED
    )
    fixed = sum(
        item.selected_relation_present
        for item in observations
        if item.role == CandidateReplayRole.FIXED
    )

    evaluable = True
    if not snapshot.complete or snapshot.infrastructure_invalid:
        diagnostics.append("candidate replay is not complete valid 3+3 evidence")
        evaluable = False
    if snapshot.header is None or not (
        _target_binding(snapshot.header.affected_provenance, N01Role.AFFECTED)
        and _target_binding(snapshot.header.fixed_provenance, N01Role.FIXED)
    ):
        diagnostics.append("replay target/artifact/isolation binding is not the frozen N01 pair")
        evaluable = False
    if not _source_matches_replay(source, snapshot):
        diagnostics.append("source campaign/setup does not match affected replay provenance")
        evaluable = False
    if any(not item.archive_unchanged for item in observations):
        diagnostics.append("one or more replay runs changed or removed the input archive")
        evaluable = False

    if not evaluable:
        status = N01CandidateMachineStatus.NOT_EVALUABLE
    elif selected is None:
        status = N01CandidateMachineStatus.NOT_NOMINATED
        diagnostics.append("no mutation-origin persistent N01 relation exists in source evidence")
    elif affected == 3 and fixed == 0:
        status = N01CandidateMachineStatus.MACHINE_CONTRAST_PASS_PENDING_HUMAN
        diagnostics.extend(
            (
                "selected source relation reproduced in affected 3/3 and fixed 0/3",
                "C2 and process statuses are retained observations, not match predicates",
                "human archive/source/root-cause correspondence remains required",
            )
        )
    else:
        status = N01CandidateMachineStatus.AMBIGUOUS
        diagnostics.append(
            f"selected relation reproduced in affected {affected}/3 and fixed {fixed}/3"
        )

    return N01CandidateMachineAssessment(
        PROTOCOL_VERSION,
        status,
        candidate_id,
        snapshot.request.nomination.source_binding_sha256,
        snapshot.completion_sha256,
        selected,
        () if selected is None else source_steps[selected],
        affected,
        fixed,
        observations,
        tuple(diagnostics),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path)
    parser.add_argument("source_policy_evidence", type=Path)
    parser.add_argument("--completion-sha256")
    args = parser.parse_args()
    try:
        assessment = assess_n01_candidate_replay(
            args.replay,
            args.source_policy_evidence,
            expected_completion_sha256=args.completion_sha256,
        )
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(canonical_json(assessment))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

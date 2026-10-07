"""Fail-closed export, replay verification and summary for transition campaigns."""

import math
import random
import re
from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import ClassVar

from inodefence.builder import BUILDER_FORMAT
from inodefence.campaign import CampaignOrigin
from inodefence.feedback import (
    TransitionSearchPolicy,
    TransitionSearchState,
    transition_sequence_key,
)
from inodefence.model import TraceCompleteness, canonical_json
from inodefence.model.provenance import ExecutionProvenance
from inodefence.mutation_scheduler import (
    TransitionAdaptiveScheduler,
    UniformMutationScheduler,
)
from inodefence.mutator import MutationOperatorId, apply_operator, operator_ids
from inodefence.transition_campaign import (
    TransitionCampaignConfig,
    TransitionCampaignResult,
)

from .encoding import decode, object_fields, read_json
from .failure import ArtifactReference
from .storage import read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file, verify_binding, verify_run


def _stable_label(value: str, field: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", value) is None:
        raise ValueError(f"{field} requires an explicit stable version identifier")


@dataclass(frozen=True, slots=True)
class TransitionEvaluationConfig:
    """Frozen experimental conditions for one P0/P1/P2 campaign.

    Labels are declarations. Verification binds them to raw evidence where a
    corresponding observable exists; it does not prove protocol compliance or
    qualify an extractor entry boundary.
    """

    serialization_schema: ClassVar[int] = 1

    campaign: TransitionCampaignConfig
    initial_case_ids: tuple[str, ...]
    provenance: ExecutionProvenance
    seed_profile: str
    environment_profile: str
    sentinel_profile: str
    oracle_profile: str
    mutation_vocabulary: str
    protocol_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.campaign, TransitionCampaignConfig) or not isinstance(
            self.provenance, ExecutionProvenance
        ):
            raise ValueError("typed transition campaign and provenance are required")
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
            "oracle_profile",
            "mutation_vocabulary",
            "protocol_version",
        ):
            _stable_label(getattr(self, field), field)

    @property
    def config_id(self) -> str:
        return sha256(canonical_json(self).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class TransitionEvidenceManifest:
    """Last publication marker for a complete transition evidence bundle."""

    serialization_schema: ClassVar[int] = 1

    config: ArtifactReference
    result: ArtifactReference
    config_id: str
    number_of_steps: int
    builder_format: str = BUILDER_FORMAT
    result_schema: int = TransitionCampaignResult.serialization_schema
    step_schema: int = 2
    trace_schema: int = 1
    transition_signature_schema: int = 1
    scheduler_evidence_schema: int = 1
    classification: str = "raw-transition-campaign"

    def __post_init__(self) -> None:
        if not isinstance(self.config, ArtifactReference) or self.config.name != "config.json":
            raise ValueError("unsupported transition config artifact")
        if not isinstance(self.result, ArtifactReference) or self.result.name != "result.json":
            raise ValueError("unsupported transition result artifact")
        _digest(self.config_id)
        if type(self.number_of_steps) is not int or self.number_of_steps <= 0:
            raise ValueError("number_of_steps must be positive")
        expected = (
            (self.result_schema, TransitionCampaignResult.serialization_schema),
            (self.step_schema, 2),
            (self.trace_schema, 1),
            (self.transition_signature_schema, 1),
            (self.scheduler_evidence_schema, 1),
        )
        if any(type(value) is not int or value != wanted for value, wanted in expected):
            raise ValueError("unsupported transition evidence schema")
        if self.builder_format != BUILDER_FORMAT or self.classification != (
            "raw-transition-campaign"
        ):
            raise ValueError("unsupported transition evidence classification")


@dataclass(frozen=True, slots=True)
class VerifiedTransitionEvidence:
    config: TransitionEvaluationConfig
    result: TransitionCampaignResult
    manifest: TransitionEvidenceManifest
    manifest_sha256: str


def _scheduler(policy: TransitionSearchPolicy):
    return (
        TransitionAdaptiveScheduler()
        if policy == TransitionSearchPolicy.P2_TRANSITION_ADAPTIVE
        else UniformMutationScheduler()
    )


def validate_transition_result(
    result: TransitionCampaignResult, config: TransitionEvaluationConfig
) -> None:
    """Replay every pure search/mutation decision and verify final-state evidence."""
    if type(result) is not TransitionCampaignResult or type(config) is not (
        TransitionEvaluationConfig
    ):
        raise ValueError("typed transition result and evaluation config are required")
    envelope = object_fields(
        read_json(canonical_json(result).encode("ascii")),
        {"model", "schema_version", "value"},
    )
    decode(TransitionCampaignResult, envelope["value"])
    if result.config != config.campaign or result.initial_case_ids != config.initial_case_ids:
        raise ValueError("evaluation declaration differs from completed transition evidence")
    initial_count = len(result.initial_case_ids)
    initial_cases = tuple(step.result.base_result.case for step in result.steps[:initial_count])
    if tuple(case.case_id for case in initial_cases) != result.initial_case_ids:
        raise ValueError("initial case IDs differ from seed observations")

    state = TransitionSearchState(initial_cases, result.config.search_policy)
    scheduler = _scheduler(result.config.search_policy)
    rng = random.Random(result.config.random_seed)
    for index, step in enumerate(result.steps):
        if step.index != index:
            raise ValueError("transition campaign step index mismatch")
        if index < initial_count:
            if (
                step.origin != CampaignOrigin.SEED
                or step.parent_case_id is not None
                or step.mutation_attempt is not None
                or step.scheduler_evidence is not None
                or step.result.base_result.case != initial_cases[index]
            ):
                raise ValueError("transition seed lineage mismatch")
            expected_attempt = None
            selection = None
        else:
            parent = state.select_case(rng)
            selection = scheduler.choose_operator(operator_ids(result.config.mutation_policy), rng)
            expected_attempt = apply_operator(
                parent,
                rng,
                result.config.mutation_policy,
                selection.operator_id,
            )
            if (
                step.origin != CampaignOrigin.MUTATION
                or step.parent_case_id != parent.case_id
                or step.mutation_attempt != expected_attempt
                or step.result.base_result.case != expected_attempt.child_case
            ):
                raise ValueError("mutation lineage or deterministic dispatch mismatch")

        verify_run(step.result.base_result)
        verify_binding(step.result.base_result, config.provenance)
        expected_feedback = state.consider(step.result)
        if step.feedback != expected_feedback:
            raise ValueError("transition feedback evidence mismatch")
        if expected_attempt is not None and selection is not None:
            expected_scheduler = scheduler.observe_outcome(
                selection,
                expected_attempt,
                expected_feedback.new_transition_keys,
                expected_feedback.new_violation_fingerprints,
            )
            if step.scheduler_evidence != expected_scheduler:
                raise ValueError("mutation scheduler evidence mismatch")

    if result.final_search_stats != state.stats or result.retained_case_ids != tuple(
        entry.case.case_id for entry in state.entries
    ):
        raise ValueError("final transition search accounting mismatch")


def export_transition_result(
    result: TransitionCampaignResult,
    config: TransitionEvaluationConfig,
    directory: Path,
) -> str:
    """Atomically publish records and write the checksummed manifest last."""
    validate_transition_result(result, config)
    directory.mkdir()
    sync_directory(directory.parent)
    config_digest = write_record(directory / "config.json", config)
    result_digest = write_record(directory / "result.json", result)
    manifest = TransitionEvidenceManifest(
        ArtifactReference("config.json", config_digest),
        ArtifactReference("result.json", result_digest),
        config.config_id,
        len(result.steps),
    )
    return write_record(directory / "manifest.json", manifest)


def verify_transition_evidence(
    directory: Path, *, expected_manifest_sha256: str | None = None
) -> VerifiedTransitionEvidence:
    """Return evidence only after schema, checksum, binding and replay verification."""
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("expected a completed transition evidence directory")
        if {path.name for path in directory.iterdir()} != {
            "config.json",
            "manifest.json",
            "result.json",
        }:
            raise ValueError("incomplete or unexpected transition evidence files")
        manifest_digest = sha256(_read_file(directory / "manifest.json")).hexdigest()
        if expected_manifest_sha256 is not None and manifest_digest != _digest(
            expected_manifest_sha256
        ):
            raise ValueError("manifest checksum mismatch")
        manifest = read_record(
            directory / "manifest.json",
            TransitionEvidenceManifest,
            expected_sha256=manifest_digest,
        )
        config = read_record(
            directory / manifest.config.name,
            TransitionEvaluationConfig,
            expected_sha256=manifest.config.sha256,
        )
        result = read_record(
            directory / manifest.result.name,
            TransitionCampaignResult,
            expected_sha256=manifest.result.sha256,
        )
        if config.config_id != manifest.config_id or len(result.steps) != (
            manifest.number_of_steps
        ):
            raise ValueError("transition manifest binding mismatch")
        validate_transition_result(result, config)
        return VerifiedTransitionEvidence(config, result, manifest, manifest_digest)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        RecursionError,
    ) as error:
        raise VerificationError(f"invalid transition campaign evidence: {error}") from error


def _entropy(counts: Counter[MutationOperatorId]) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((count / total) * math.log2(count / total) for count in counts.values() if count)


def _summary(verified: VerifiedTransitionEvidence) -> dict:
    result = verified.result
    attempts: Counter[MutationOperatorId] = Counter()
    yields: Counter[MutationOperatorId] = Counter()
    rewards: Counter[int] = Counter()
    sequences = set()
    checkpoint_count = 0
    snapshot_time_ns = 0
    snapshot_evidence_bytes = 0
    incomplete = 0
    first_novel = None
    final_weights = tuple((operator.value, 1) for operator in MutationOperatorId)
    for step in result.steps:
        trace = step.result.trace
        sequences.add(transition_sequence_key(trace))
        checkpoint_count += len(trace.checkpoints)
        snapshot_time_ns += sum(item.observation_duration_ns for item in trace.checkpoints)
        snapshot_evidence_bytes += sum(
            len(canonical_json(item).encode("ascii")) for item in trace.checkpoints
        )
        incomplete += int(trace.completeness == TraceCompleteness.INCOMPLETE)
        if step.feedback.transition_novel and first_novel is None:
            first_novel = step.index + 1
        evidence = step.scheduler_evidence
        if evidence is not None:
            operator = evidence.selected_operator_id
            attempts[operator] += 1
            yields[operator] += int(bool(evidence.new_transition_keys))
            rewards[evidence.reward] += 1
            final_weights = tuple((item.value, weight) for item, weight in evidence.weights_after)
    mutation_count = sum(attempts.values())
    operator_metrics = tuple(
        {
            "operator_id": operator.value,
            "attempts": attempts[operator],
            "transition_yields": yields[operator],
            "transition_yield_rate": (
                yields[operator] / attempts[operator] if attempts[operator] else None
            ),
        }
        for operator in MutationOperatorId
    )
    return {
        "schema_version": 1,
        "classification": "derived-transition-observations",
        "manifest_sha256": verified.manifest_sha256,
        "config_id": verified.config.config_id,
        "search_policy": result.config.search_policy.value,
        "mutation_policy": result.config.mutation_policy.value,
        "random_seed": result.config.random_seed,
        "execution_budget": result.config.execution_budget,
        "initial_case_count": len(result.initial_case_ids),
        "retained_case_count": len(result.retained_case_ids),
        "unique_final_state_count": result.final_search_stats.unique_full_states,
        "unique_transition_key_count": result.final_search_stats.unique_transition_keys,
        "unique_transition_sequence_count": len(sequences),
        "unique_violation_fingerprint_count": (
            result.final_search_stats.unique_violation_fingerprints
        ),
        "transition_novel_observations": sum(
            step.feedback.transition_novel for step in result.steps
        ),
        "transition_novelty_rate": sum(step.feedback.transition_novel for step in result.steps)
        / len(result.steps),
        "executions_to_first_novel_transition": first_novel,
        "incomplete_trace_count": incomplete,
        "entry_count": sum(step.result.trace.expected_entry_count for step in result.steps),
        "checkpoint_count": checkpoint_count,
        "snapshot_time_ns": snapshot_time_ns,
        "snapshot_evidence_bytes": snapshot_evidence_bytes,
        "execution_duration_seconds": sum(
            step.result.base_result.execution.duration_seconds for step in result.steps
        ),
        "observed_step_time_seconds": sum(
            step.result.base_result.execution.duration_seconds for step in result.steps
        )
        + snapshot_time_ns / 1_000_000_000,
        "peak_memory_bytes": None,
        "mutation_attempt_count": mutation_count,
        "operator_metrics": operator_metrics,
        "reward_distribution": tuple(sorted(rewards.items())),
        "scheduler_selection_entropy_bits": _entropy(attempts),
        "final_scheduler_weights": final_weights,
        "new_violation_observations": sum(
            bool(step.feedback.new_violation_fingerprints) for step in result.steps
        ),
        "labels": {
            "seed_profile": verified.config.seed_profile,
            "environment_profile": verified.config.environment_profile,
            "sentinel_profile": verified.config.sentinel_profile,
            "oracle_profile": verified.config.oracle_profile,
            "mutation_vocabulary": verified.config.mutation_vocabulary,
            "protocol_version": verified.config.protocol_version,
        },
        "target": asdict(verified.config.provenance.target),
    }


def summarize_transition_evidence(
    directory: Path, *, expected_manifest_sha256: str | None = None
) -> dict:
    """Derive metrics only from a freshly verified complete evidence bundle."""
    return _summary(
        verify_transition_evidence(directory, expected_manifest_sha256=expected_manifest_sha256)
    )

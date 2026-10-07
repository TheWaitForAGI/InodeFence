"""Compatible P0/P1/P2 transition metrics with explicit censoring."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from statistics import fmean

from .encoding import json_bytes
from .transition_evidence import (
    VerifiedTransitionEvidence,
    _summary,
    verify_transition_evidence,
)
from .verify import VerificationError, _digest


@dataclass(frozen=True, slots=True)
class TransitionDatasetMember:
    directory: Path
    expected_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.directory, Path):
            raise ValueError("transition dataset requires evidence directory Paths")
        if self.expected_manifest_sha256 is not None:
            _digest(self.expected_manifest_sha256)


def _conditions(verified: VerifiedTransitionEvidence, *, include_seed: bool) -> dict:
    config, result, provenance = verified.config, verified.result, verified.config.provenance
    if provenance.source.revision is None or provenance.source.dirty is not False:
        raise ValueError("clean pinned source required for transition comparison")
    conditions = {
        "source": asdict(provenance.source),
        "environment": asdict(provenance.environment),
        "target": asdict(provenance.target),
        "sentinels": tuple(asdict(item) for item in provenance.sentinels),
        "isolation": asdict(provenance.isolation) if provenance.isolation else None,
        "initial_case_ids": result.initial_case_ids,
        "execution_budget": result.config.execution_budget,
        "mutation_policy": result.config.mutation_policy.value,
        "seed_profile": config.seed_profile,
        "environment_profile": config.environment_profile,
        "sentinel_profile": config.sentinel_profile,
        "oracle_profile": config.oracle_profile,
        "mutation_vocabulary": config.mutation_vocabulary,
        "protocol_version": config.protocol_version,
        "schemas": {
            "manifest": 1,
            "config": 1,
            "result": 2,
            "step": 2,
            "transition_signature": 1,
            "scheduler_evidence": 1,
        },
    }
    if include_seed:
        conditions["random_seed"] = result.config.random_seed
    return conditions


def _mean(summaries: list[dict], field: str) -> float:
    return fmean(float(summary[field]) for summary in summaries)


def _mean_optional(summaries: list[dict], field: str) -> float | None:
    values = [summary[field] for summary in summaries if summary[field] is not None]
    return fmean(float(value) for value in values) if values else None


def summarize_transition_statistics(
    members: Sequence[TransitionDatasetMember], *, allow_seed_variation: bool = False
) -> dict:
    """Verify all inputs, require equal controls, then aggregate within policy arms.

    Search policy is the declared arm and is deliberately excluded from the
    equality check. Random seed may differ only when explicitly allowed.
    Missing first-novel events are censored and never replaced with the budget.
    """
    if type(allow_seed_variation) is not bool:
        raise ValueError("allow_seed_variation must be explicit bool")
    if not members:
        raise VerificationError("transition statistics require verified inputs")
    verified = []
    for member in members:
        if not isinstance(member, TransitionDatasetMember):
            raise ValueError("expected TransitionDatasetMember records")
        verified.append(
            verify_transition_evidence(
                member.directory,
                expected_manifest_sha256=member.expected_manifest_sha256,
            )
        )
    manifests = tuple(item.manifest_sha256 for item in verified)
    if len(set(manifests)) != len(manifests):
        raise VerificationError("same transition evidence cannot be counted twice")
    reference = json_bytes(_conditions(verified[0], include_seed=not allow_seed_variation))
    for item in verified[1:]:
        if json_bytes(_conditions(item, include_seed=not allow_seed_variation)) != reference:
            raise VerificationError(
                "transition policy arms differ outside the declared search policy"
            )

    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in verified:
        grouped[item.result.config.search_policy.value].append(_summary(item))
    arms = []
    for policy in sorted(grouped):
        summaries = grouped[policy]
        first = [summary["executions_to_first_novel_transition"] for summary in summaries]
        observed_first = [value for value in first if value is not None]
        operator_totals: dict[str, tuple[int, int]] = {}
        for operator in summaries[0]["operator_metrics"]:
            operator_id = operator["operator_id"]
            attempts = sum(
                next(
                    item
                    for item in summary["operator_metrics"]
                    if item["operator_id"] == operator_id
                )["attempts"]
                for summary in summaries
            )
            yields = sum(
                next(
                    item
                    for item in summary["operator_metrics"]
                    if item["operator_id"] == operator_id
                )["transition_yields"]
                for summary in summaries
            )
            operator_totals[operator_id] = (attempts, yields)
        arms.append(
            {
                "policy_id": policy,
                "run_count": len(summaries),
                "manifest_sha256": tuple(summary["manifest_sha256"] for summary in summaries),
                "mean_unique_final_states": _mean(summaries, "unique_final_state_count"),
                "mean_unique_transition_keys": _mean(summaries, "unique_transition_key_count"),
                "mean_unique_transition_sequences": _mean(
                    summaries, "unique_transition_sequence_count"
                ),
                "mean_transition_novelty_rate": _mean(summaries, "transition_novelty_rate"),
                "first_novel_transition_observed_count": len(observed_first),
                "first_novel_transition_censored_count": len(first) - len(observed_first),
                "mean_executions_to_first_novel_transition_observed": (
                    fmean(observed_first) if observed_first else None
                ),
                "mean_unique_violation_fingerprints": _mean(
                    summaries, "unique_violation_fingerprint_count"
                ),
                "mean_scheduler_weight_entropy_bits": _mean_optional(
                    summaries, "mean_scheduler_weight_entropy_bits"
                ),
                "mean_empirical_operator_selection_entropy_bits": _mean(
                    summaries, "empirical_operator_selection_entropy_bits"
                ),
                "operator_metrics": tuple(
                    {
                        "operator_id": operator_id,
                        "attempts": values[0],
                        "transition_yields": values[1],
                        "transition_yield_rate": (values[1] / values[0] if values[0] else None),
                    }
                    for operator_id, values in operator_totals.items()
                ),
            }
        )
    return {
        "schema_version": 1,
        "classification": "transition-policy-arm-statistics",
        "allow_seed_variation": allow_seed_variation,
        "manifest_sha256": manifests,
        "conditions_sha256": sha256(reference).hexdigest(),
        "policy_ids": tuple(arm["policy_id"] for arm in arms),
        "arms": tuple(arms),
        "interpretation": ("transition counts are search observations, not vulnerability counts"),
    }

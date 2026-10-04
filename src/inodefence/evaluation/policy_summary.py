"""Derived observation counts from freshly verified evaluation-bound policy results."""

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from .encoding import json_bytes
from .policy_binding import VerifiedBoundPolicyEvidence, verify_bound_policy_evidence
from .summary import _observation_counts, summary_markdown
from .verify import VerificationError


def _summarize_bound(verified: VerifiedBoundPolicyEvidence) -> dict:
    result, config = verified.campaign.result, verified.config
    return {
        "schema_version": 1,
        "classification": "derived-policy-contract-observations",
        "binding_sha256": verified.binding_sha256,
        "manifest_sha256": verified.campaign.manifest_sha256,
        "result_sha256": verified.campaign.manifest.result.sha256,
        "evaluation_config_id": config.config_id,
        "policy_config_sha256": verified.campaign.manifest.policy_config_sha256,
        "source": asdict(result.provenance.source),
        "target": asdict(result.provenance.target),
        "protocol_version": config.protocol_version,
        "seed_profile": config.seed_profile,
        "environment_profile": config.environment_profile,
        "sentinel_profile": config.sentinel_profile,
        "random_seed": result.config.random_seed,
        "execution_budget": result.config.execution_budget,
        "search_policy": result.config.search_policy.value,
        "mutation_policy": result.config.mutation_policy.value,
        "feedback_projection": result.config.feedback_projection.value,
        "initial_case_count": len(result.initial_case_ids),
        "retained_case_count": len(result.retained_case_ids),
        "unique_feedback_key_count": result.unique_feedback_keys,
        "active_case_id": result.active_case_id,
        **_observation_counts(tuple(step.result for step in result.steps)),
    }


def summarize_policy_campaign(
    directory: Path, *, expected_binding_sha256: str | None = None
) -> dict:
    """Only directory input; a forged caller verification flag cannot bypass ingest."""
    return _summarize_bound(
        verify_bound_policy_evidence(directory, expected_binding_sha256=expected_binding_sha256)
    )


def policy_summary_markdown(summary: dict) -> str:
    return summary_markdown(summary) + (
        f"\nEvaluation binding SHA-256: `{summary['binding_sha256']}`\n\n"
        f"Evaluation config ID: `{summary['evaluation_config_id']}`\n\n"
        f"Search policy: `{summary['search_policy']}`\n\n"
        f"Mutation policy: `{summary['mutation_policy']}`\n\n"
        f"Feedback projection: `{summary['feedback_projection']}`\n\n"
        f"Unique projected feedback keys: {summary['unique_feedback_key_count']}\n\n"
        f"Initial cases: {summary['initial_case_count']}\n\n"
        f"Active case ID: `{summary['active_case_id']}`\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--binding-sha256")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    try:
        summary = summarize_policy_campaign(
            args.directory, expected_binding_sha256=args.binding_sha256
        )
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json_bytes(summary).decode("ascii")
        if args.format == "json"
        else policy_summary_markdown(summary),
        end="\n" if args.format == "json" else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

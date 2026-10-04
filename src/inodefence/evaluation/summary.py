"""Derived counts from verified raw campaign exports, never invented measurements."""

import argparse
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from inodefence.feedback import violation_fingerprints
from inodefence.model import ContractId, ExecutionStatus, RunResult

from .encoding import json_bytes
from .verify import VerificationError, VerifiedCampaign, verify_campaign


def _observation_counts(runs: tuple[RunResult, ...]) -> dict:
    """Shared arithmetic; public summarizers first verify their own evidence schema."""
    statuses = Counter(run.execution.status for run in runs)
    contracts = {contract.value: 0 for contract in ContractId}
    any_count, first = 0, None
    fingerprints = set()
    for index, run in enumerate(runs):
        observed = False
        for verdict in run.violations:
            if verdict.violated:
                contracts[verdict.contract_id.value] += 1
                observed = True
        if observed:
            any_count += 1
            if first is None:
                first = {"step_index": index, "execution_count": index + 1}
        fingerprints.update(violation_fingerprints(run.violations))
    return {
        "total_executions": len(runs),
        "status_counts": {status.value: statuses[status] for status in ExecutionStatus},
        "contract_observed_counts": contracts,
        "any_contract_observed_count": any_count,
        "first_observed_contract_violation": first,
        "unique_state_signature_count": len({run.signature for run in runs}),
        "unique_violation_fingerprint_count": len(fingerprints),
        "unique_case_count": len({run.case.case_id for run in runs}),
    }


def _summarize(verified: VerifiedCampaign) -> dict:
    result = verified.result
    return {
        "schema_version": 1,
        "classification": "derived-contract-observations",
        "manifest_sha256": verified.manifest_sha256,
        "steps_sha256": verified.steps_sha256,
        "source": asdict(result.provenance.source),
        "target": asdict(result.provenance.target),
        "experiment_config_id": result.experiment_config_id,
        "random_seed": result.config.random_seed,
        "execution_budget": result.config.execution_budget,
        "retained_case_count": len(result.retained_case_ids),
        **_observation_counts(tuple(step.result for step in result.steps)),
    }


def summarize_campaign(directory: Path, *, expected_manifest_sha256: str | None = None) -> dict:
    """Accept a bundle path, not unchecked records or a caller-forged verification flag."""
    return _summarize(verify_campaign(directory, expected_manifest_sha256=expected_manifest_sha256))


def summary_markdown(summary: dict) -> str:
    """Render a computed summary; source digest links it to immutable raw evidence."""
    lines = [
        "# Verified campaign observations",
        "",
        f"Manifest SHA-256: `{summary['manifest_sha256']}`",
        "",
        f"Target: `{summary['target']['target_id']}` / `{summary['target']['target_version']}`",
        "",
        f"Total executions: {summary['total_executions']}",
        "",
        "| Execution status | Count |",
        "| --- | ---: |",
        *(f"| {key} | {value} |" for key, value in summary["status_counts"].items()),
        "",
        "| Contract observation | Count |",
        "| --- | ---: |",
        *(f"| {key} | {value} |" for key, value in summary["contract_observed_counts"].items()),
        f"| Any contract | {summary['any_contract_observed_count']} |",
        "",
    ]
    first = summary["first_observed_contract_violation"]
    lines.append(
        "First observation: none within the recorded budget."
        if first is None
        else f"First observation: step {first['step_index']} (zero-based), "
        f"execution {first['execution_count']} (one-based)."
    )
    lines.extend(
        [
            "",
            f"Unique signatures: {summary['unique_state_signature_count']}",
            f"Unique violation fingerprints: {summary['unique_violation_fingerprint_count']}",
            f"Retained cases: {summary['retained_case_count']}",
            f"Unique executed cases: {summary['unique_case_count']}",
            "",
            "These are recorded contract observations, not rediscovery or vulnerability claims.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    try:
        summary = summarize_campaign(args.directory, expected_manifest_sha256=args.manifest_sha256)
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json_bytes(summary).decode("ascii") if args.format == "json" else summary_markdown(summary),
        end="\n" if args.format == "json" else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

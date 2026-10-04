"""Verified compatible observations with explicit denominators and censoring."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .dataset import Compatibility, DatasetMember, validate_dataset
from .encoding import json_bytes
from .repeated import RunState, read_repetitions
from .summary import _summarize
from .verify import VerificationError, verify_campaign


def _distribution(values: Sequence[int]) -> dict:
    """Inclusive linear quantiles at positions (n-1)*p, conditional on observed hits."""
    if any(type(value) is not int or value <= 0 for value in values):
        raise ValueError("first-hit execution counts must be positive integers")
    ordered = sorted(values)

    def quantile(p: float):
        if not ordered:
            return None
        position = (len(ordered) - 1) * p
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    q1, median, q3 = quantile(0.25), quantile(0.5), quantile(0.75)
    return {
        "population": "runs_with_observation_only",
        "unit": "one_based_execution_count",
        "quantile_method": "inclusive_linear_position_(n-1)*p",
        "number_observed_runs": len(ordered),
        "median": median,
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1 if q1 is not None and q3 is not None else None,
        "min": ordered[0] if ordered else None,
        "max": ordered[-1] if ordered else None,
    }


def summarize_statistics(
    members: Sequence[DatasetMember], *, allow_seed_variation: bool = False
) -> dict:
    """Read raw directories, validate compatibility, then anchor every reread.

    No-hit runs are included in the observation denominator and right-censored
    for first-hit times. Invalid evidence raises, never a silent exclusion. Empty
    input is an explicit template; failed attempts are unavailable in raw exports.
    """
    report = validate_dataset(members, allow_seed_variation=allow_seed_variation)
    if members and report.compatibility != Compatibility.COMPATIBLE:
        raise VerificationError(
            f"dataset cannot be pooled: {json_bytes(asdict(report)).decode('ascii')}"
        )
    summaries = [
        _summarize(verify_campaign(member.directory, expected_manifest_sha256=digest))
        for member, digest in zip(members, report.manifest_sha256, strict=True)
    ]
    return _aggregate_observations(
        summaries, asdict(report) if summaries else None, report.manifest_sha256
    )


def _aggregate_observations(
    summaries: Sequence[dict], dataset_validation: dict | None, manifest_digests: tuple[str, ...]
) -> dict:
    """Shared denominator/censoring arithmetic after schema-specific verification."""
    hits, censored = [], []
    success_count, executions = 0, 0
    for summary in summaries:
        executions += summary["total_executions"]
        success_count += summary["status_counts"]["success"]
        first = summary["first_observed_contract_violation"]
        if first is None:
            censored.append(
                {
                    "manifest_sha256": summary["manifest_sha256"],
                    "execution_budget": summary["execution_budget"],
                }
            )
        else:
            hits.append(first["execution_count"])
    count = len(summaries)
    return {
        "schema_version": 1,
        "classification": "contract-observation-statistics" if count else "empty-template",
        "input_scope": "selected_verified_completed_campaigns",
        "dataset_validation": dataset_validation,
        "number_valid_runs": count,
        "number_invalid_runs": None,
        "invalid_runs_note": "unavailable in completed-only exports; use repetition metadata",
        "total_verified_executions": executions,
        "process_success_proportion": {
            "numerator": success_count,
            "denominator": executions,
            "value": success_count / executions if executions else None,
        },
        "any_contract_observation_proportion": {
            "numerator": len(hits),
            "denominator": count,
            "value": len(hits) / count if count else None,
        },
        "first_hit_execution_count": _distribution(hits),
        "number_no_hit_runs": len(censored),
        "no_hit_handling": "right_censored_at_recorded_budget; no imputed hit index",
        "censored_runs": censored,
        "rediscovery_classification": "not_available; observations are not benchmark rediscovery",
        "manifest_sha256": manifest_digests,
    }


def summarize_repetition_statistics(
    root: Path, *, protocol_version: str, expected_plan_sha256: str | None = None
) -> dict:
    """Only resolved scheduling plans; reverify all raw exports and failure ledgers."""
    DatasetMember(root, protocol_version)
    snapshot = read_repetitions(root, expected_plan_sha256=expected_plan_sha256)
    if any(slot.state in {RunState.PENDING, RunState.STARTED} for slot in snapshot.slots):
        raise VerificationError(
            "repetition plan has unresolved slots; statistics would be premature"
        )
    members = tuple(
        DatasetMember(
            root / slot.result_directory / "evidence",
            protocol_version,
            slot.terminal.artifact.sha256,
        )
        for slot in snapshot.slots
        if slot.state == RunState.COMPLETED and slot.terminal is not None
    )
    result = summarize_statistics(members, allow_seed_variation=True)
    result.update(
        input_scope="resolved_independent_repetition_plan",
        plan_sha256=snapshot.plan_sha256,
        number_planned_runs=len(snapshot.slots),
        number_invalid_runs=sum(
            slot.state in {RunState.FAILED, RunState.INVALID} for slot in snapshot.slots
        ),
        invalid_runs_note="verified failed/invalid slots excluded from observation denominator",
        run_states=[
            {
                "run_index": slot.run_index,
                "random_seed": slot.random_seed,
                "state": slot.state.value,
                "diagnostics": slot.diagnostics,
                "terminal": asdict(slot.terminal) if slot.terminal is not None else None,
            }
            for slot in snapshot.slots
        ],
    )
    if not members:
        result["classification"] = "no-valid-completed-runs"
    return result


def statistics_markdown(result: dict) -> str:
    proportion, first = (
        result["any_contract_observation_proportion"],
        result["first_hit_execution_count"],
    )
    return (
        "# Verified observation statistics\n\n"
        f"Scope: {result['input_scope']}\n\n"
        f"Valid completed runs: {result['number_valid_runs']}\n\n"
        f"Invalid runs: {result['number_invalid_runs']} ({result['invalid_runs_note']})\n\n"
        f"Runs with any contract observation: {proportion['numerator']} / "
        f"{proportion['denominator']}\n\n"
        f"No-hit right-censored runs: {result['number_no_hit_runs']}\n\n"
        "First-hit statistics apply only to runs with an observation, in one-based executions.\n\n"
        f"Median: {first['median']}; IQR: {first['iqr']}; "
        f"min/max: {first['min']}/{first['max']}.\n\n"
        "No-hit times are not imputed; no full-population survival median is estimated.\n\n"
        "Contract observations do not classify benchmark rediscovery.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="*", type=Path)
    parser.add_argument("--protocol-version", required=True)
    parser.add_argument("--repetitions", type=Path)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--allow-seed-variation", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    if args.repetitions is not None and args.directories:
        parser.error("use repetition metadata or raw campaign directories")
    if args.plan_sha256 is not None and args.repetitions is None:
        parser.error("plan checksum requires repetition metadata")
    try:
        result = (
            summarize_repetition_statistics(
                args.repetitions,
                protocol_version=args.protocol_version,
                expected_plan_sha256=args.plan_sha256,
            )
            if args.repetitions is not None
            else summarize_statistics(
                tuple(
                    DatasetMember(directory, args.protocol_version)
                    for directory in args.directories
                ),
                allow_seed_variation=args.allow_seed_variation,
            )
        )
    except (VerificationError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json_bytes(result).decode("ascii")
        if args.format == "json"
        else statistics_markdown(result),
        end="\n" if args.format == "json" else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

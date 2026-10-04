"""Compatible completed policy observations with explicit denominators and censoring."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .dataset import Compatibility
from .encoding import json_bytes
from .policy_binding import verify_bound_policy_evidence
from .policy_dataset import PolicyDatasetMember, validate_policy_dataset
from .policy_summary import _summarize_bound
from .statistics import _aggregate_observations, statistics_markdown
from .verify import VerificationError


def summarize_policy_statistics(
    members: Sequence[PolicyDatasetMember], *, allow_seed_variation: bool = False
) -> dict:
    """Fresh compatibility first, anchored rereads second; no automatic exclusions."""
    report = validate_policy_dataset(members, allow_seed_variation=allow_seed_variation)
    if members and report.compatibility != Compatibility.COMPATIBLE:
        raise VerificationError(
            f"policy dataset cannot be pooled: {json_bytes(asdict(report)).decode('ascii')}"
        )
    summaries = []
    for member, digest in zip(members, report.binding_sha256, strict=True):
        if digest is None:
            raise VerificationError("compatible input requires every binding digest")
        verified = verify_bound_policy_evidence(member.directory, expected_binding_sha256=digest)
        summaries.append(_summarize_bound(verified))
    result = _aggregate_observations(
        summaries,
        asdict(report) if summaries else None,
        tuple(summary["manifest_sha256"] for summary in summaries),
    )
    result.update(
        classification="policy-contract-observation-statistics" if summaries else "empty-template",
        input_scope="selected_verified_completed_policy_campaigns",
        binding_sha256=report.binding_sha256,
        evaluation_config_ids=tuple(summary["evaluation_config_id"] for summary in summaries),
        invalid_runs_note="unavailable in completed-only policy bundles; no ledger count inferred",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="*", type=Path)
    parser.add_argument("--allow-seed-variation", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    try:
        result = summarize_policy_statistics(
            tuple(PolicyDatasetMember(directory) for directory in args.directories),
            allow_seed_variation=args.allow_seed_variation,
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

"""Compare explicitly bound policy evidence before any multi-run pooling."""

import argparse
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from inodefence.model import canonical_json

from .dataset import Compatibility, DatasetDifference
from .encoding import json_bytes
from .policy_binding import VerifiedBoundPolicyEvidence, verify_bound_policy_evidence
from .verify import VerificationError, _digest


@dataclass(frozen=True, slots=True)
class PolicyDatasetMember:
    directory: Path
    expected_binding_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.directory, Path):
            raise ValueError("bound evidence directory Path required")
        if self.expected_binding_sha256 is not None:
            _digest(self.expected_binding_sha256)


@dataclass(frozen=True, slots=True)
class PolicyDatasetReport:
    schema_version: int
    compatibility: Compatibility
    binding_sha256: tuple[str | None, ...]
    campaign_manifest_sha256: tuple[str | None, ...]
    differences: tuple[DatasetDifference, ...]
    strata: tuple[tuple[int, ...], ...]
    allow_seed_variation: bool


def _conditions(verified: VerifiedBoundPolicyEvidence) -> dict:
    config, result = verified.config, verified.campaign.result
    provenance = result.provenance
    if provenance.source.revision is None or provenance.source.dirty is not False:
        raise ValueError("clean pinned source required for comparison")
    if not all(asdict(provenance.environment).values()):
        raise ValueError("known harness runtime identity required for comparison")
    isolation = asdict(provenance.isolation) if provenance.isolation else None
    policy, artifacts, runtime = None, None, None
    if isolation is not None:
        policy = isolation.pop("policy")
        artifacts = {
            "image_id": policy.pop("image_id"),
            "digests": isolation.pop("artifacts"),
            "origin": isolation.pop("artifact_origin"),
            "repo_digests": isolation.pop("image_repo_digests"),
        }
        runtime = isolation
    return {
        "source": asdict(provenance.source),
        "builder_format": verified.campaign.manifest.builder_format,
        "schemas": {
            "binding": 1,
            "config": 1,
            "manifest": 1,
            "result": 1,
            "step": 1,
            "decision": 2,
            "signature": 3,
        },
        "protocol_version": config.protocol_version,
        "seed_profile": config.seed_profile,
        "initial_case_ids": config.initial_case_ids,
        "execution_budget": config.campaign.execution_budget,
        "timeout_seconds": provenance.target.timeout_seconds,
        "sentinels": tuple(asdict(item) for item in provenance.sentinels),
        "sentinel_profile": config.sentinel_profile,
        "search_policy": config.campaign.search_policy.value,
        "mutation_policy": config.campaign.mutation_policy.value,
        "feedback_projection": config.campaign.feedback_projection.value,
        "isolation_policy": policy,
        "target": asdict(provenance.target),
        "target_artifacts": artifacts,
        "harness_runtime": asdict(provenance.environment),
        "container_runtime": runtime,
        "environment_profile": config.environment_profile,
        "random_seed": config.campaign.random_seed,
    }


_STRATIFIABLE = {
    "search_policy",
    "mutation_policy",
    "feedback_projection",
    "target",
    "target_artifacts",
    "harness_runtime",
    "container_runtime",
    "environment_profile",
    "random_seed",
}


def validate_policy_dataset(
    members: Sequence[PolicyDatasetMember], *, allow_seed_variation: bool = False
) -> PolicyDatasetReport:
    """Do not mix formats, silently exclude invalid inputs or pool across strata.

    Config/policy/provenance labels cannot turn copied raw executions into new
    independent observations. Duplicate full RunResult bytes are rejected even
    if the enclosing result/config/profiles have been coherently changed.
    """
    if type(allow_seed_variation) is not bool:
        raise ValueError("allow_seed_variation must be explicit bool")
    projections, bindings, manifests, differences = [], [], [], []
    raw_executions = set()
    for index, member in enumerate(members):
        if not isinstance(member, PolicyDatasetMember):
            raise ValueError("expected PolicyDatasetMember records")
        try:
            verified = verify_bound_policy_evidence(
                member.directory, expected_binding_sha256=member.expected_binding_sha256
            )
            conditions = _conditions(verified)
            for step in verified.campaign.result.steps:
                digest = sha256(canonical_json(step.result).encode("ascii")).hexdigest()
                if digest in raw_executions:
                    differences.append(
                        DatasetDifference(
                            f"member[{index}].duplicate_execution",
                            Compatibility.INCOMPATIBLE,
                            "same raw execution cannot be counted twice",
                        )
                    )
                raw_executions.add(digest)
            projections.append(conditions)
            bindings.append(verified.binding_sha256)
            manifests.append(verified.campaign.manifest_sha256)
        except (VerificationError, ValueError, TypeError, UnicodeError) as error:
            projections.append(None)
            bindings.append(None)
            manifests.append(None)
            differences.append(
                DatasetDifference(f"member[{index}]", Compatibility.INCOMPATIBLE, str(error))
            )
    if not members:
        differences.append(
            DatasetDifference("members", Compatibility.INCOMPATIBLE, "no verified runs provided")
        )
    if not differences:
        for dimension in projections[0]:
            if dimension == "random_seed" and allow_seed_variation:
                continue
            if len({json_bytes(projection[dimension]) for projection in projections}) > 1:
                differences.append(
                    DatasetDifference(
                        dimension,
                        Compatibility.REQUIRES_STRATIFICATION
                        if dimension in _STRATIFIABLE
                        else Compatibility.INCOMPATIBLE,
                        "recorded conditions differ",
                    )
                )
    state = Compatibility.COMPATIBLE
    if any(item.disposition == Compatibility.INCOMPATIBLE for item in differences):
        state = Compatibility.INCOMPATIBLE
    elif differences:
        state = Compatibility.REQUIRES_STRATIFICATION
    groups = {}
    if state != Compatibility.INCOMPATIBLE:
        for index, projection in enumerate(projections):
            key = json_bytes(
                {
                    name: value
                    for name, value in projection.items()
                    if not (name == "random_seed" and allow_seed_variation)
                }
            )
            groups.setdefault(key, []).append(index)
    return PolicyDatasetReport(
        1,
        state,
        tuple(bindings),
        tuple(manifests),
        tuple(differences),
        tuple(tuple(group) for group in groups.values()),
        allow_seed_variation,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--allow-seed-variation", action="store_true")
    args = parser.parse_args()
    report = validate_policy_dataset(
        tuple(PolicyDatasetMember(path) for path in args.directories),
        allow_seed_variation=args.allow_seed_variation,
    )
    print(json_bytes(asdict(report)).decode("ascii"))
    return 0 if report.compatibility == Compatibility.COMPATIBLE else 1


if __name__ == "__main__":
    raise SystemExit(main())

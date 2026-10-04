"""Fail-closed comparison of recorded experiment conditions before pooling."""

import argparse
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from inodefence.experiment_config import ExperimentConfig
from inodefence.provenance import sentinel_provenance

from .encoding import json_bytes, read_json
from .verify import VerificationError, VerifiedCampaign, _digest, verify_campaign


class Compatibility(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    REQUIRES_STRATIFICATION = "requires_stratification"


@dataclass(frozen=True, slots=True)
class DatasetMember:
    """Protocol is an explicit caller binding, not a fact inferred from raw v4."""

    directory: Path
    protocol_version: str | None = None
    expected_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.directory, Path):
            raise ValueError("dataset requires an evidence directory Path")
        if self.protocol_version is not None and (
            not isinstance(self.protocol_version, str)
            or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", self.protocol_version) is None
        ):
            raise ValueError("protocol requires an explicit stable version identifier")
        if self.expected_manifest_sha256 is not None:
            _digest(self.expected_manifest_sha256)


@dataclass(frozen=True, slots=True)
class DatasetDifference:
    dimension: str
    disposition: Compatibility
    detail: str


@dataclass(frozen=True, slots=True)
class DatasetReport:
    schema_version: int
    compatibility: Compatibility
    manifest_sha256: tuple[str, ...]
    differences: tuple[DatasetDifference, ...]
    strata: tuple[tuple[int, ...], ...]
    allow_seed_variation: bool


def _projection(member: DatasetMember, verified: VerifiedCampaign) -> dict:
    result, provenance = verified.result, verified.result.provenance
    if verified.experiment_config_bytes is None:
        raise ValueError("original experiment config is required for policy/profile comparison")
    if member.protocol_version is None:
        raise ValueError("protocol version is not recorded in raw v4; explicit binding required")
    source = provenance.source
    if source.revision is None or source.dirty is not False:
        raise ValueError("clean pinned source required; unknown/dirty source is not reproducible")
    raw = read_json(verified.experiment_config_bytes)
    if (
        not isinstance(raw, dict)
        or type(raw.get("schema_version")) is not int
        or raw["schema_version"] not in (1, 2)
    ):
        raise ValueError("unsupported experiment config schema")
    config = ExperimentConfig.from_json(verified.experiment_config_bytes.decode("ascii"))
    if (
        config.config_id != result.experiment_config_id
        or config.campaign != result.config
        or config.target != provenance.target
        or config.initial_case_ids != result.initial_case_ids
        or sentinel_provenance(config.sentinels) != provenance.sentinels
        or config.isolation != (provenance.isolation.policy if provenance.isolation else None)
    ):
        raise ValueError("original config differs from recorded execution binding")
    isolation = asdict(provenance.isolation) if provenance.isolation else None
    policy = asdict(config.isolation) if config.isolation else None
    image_id = policy.pop("image_id") if policy else None
    runtime = None
    artifacts = None
    if isolation is not None:
        isolation.pop("policy")
        artifacts = {
            "digests": isolation.pop("artifacts"),
            "origin": isolation.pop("artifact_origin"),
            "image_id": image_id,
            "repo_digests": isolation.pop("image_repo_digests"),
        }
        runtime = isolation
    return {
        "source": asdict(source),
        "builder_format": sorted({step.result.archive_format for step in result.steps}),
        "schemas": {"manifest": 4, "step": 1, "signature": 3, "config": raw["schema_version"]},
        "protocol_version": member.protocol_version,
        "seed_profile": config.seed_profile,
        "initial_case_ids": result.initial_case_ids,
        "execution_budget": result.config.execution_budget,
        "timeout_seconds": provenance.target.timeout_seconds,
        "sentinels": tuple(asdict(item) for item in provenance.sentinels),
        "mutation_policy": config.mutation_policy,
        "feedback_policy": config.feedback_policy,
        "isolation_policy": policy,
        "target": asdict(provenance.target),
        "target_artifacts": artifacts,
        "harness_runtime": asdict(provenance.environment),
        "container_runtime": runtime,
        "environment_profile": config.environment_profile,
        "random_seed": result.config.random_seed,
    }


_STRATIFIABLE = {
    "target",
    "target_artifacts",
    "harness_runtime",
    "container_runtime",
    "environment_profile",
    "random_seed",
}


def validate_dataset(
    members: Sequence[DatasetMember], *, allow_seed_variation: bool = False
) -> DatasetReport:
    """Unknown bindings or hard differences prevent pooling; no implicit exclusions."""
    if type(allow_seed_variation) is not bool:
        raise ValueError("allow_seed_variation must be explicit bool")
    projections, digests, steps_digests, differences = [], [], [], []
    for index, member in enumerate(members):
        if not isinstance(member, DatasetMember):
            raise ValueError("expected DatasetMember records")
        try:
            verified = verify_campaign(
                member.directory, expected_manifest_sha256=member.expected_manifest_sha256
            )
            projections.append(_projection(member, verified))
            digests.append(verified.manifest_sha256)
            steps_digests.append(verified.steps_sha256)
        except (VerificationError, ValueError, TypeError, UnicodeError) as error:
            differences.append(
                DatasetDifference(f"member[{index}]", Compatibility.INCOMPATIBLE, str(error))
            )
    if not members:
        differences.append(
            DatasetDifference("members", Compatibility.INCOMPATIBLE, "no verified runs provided")
        )
    if len(set(digests)) != len(digests) or len(set(steps_digests)) != len(steps_digests):
        differences.append(
            DatasetDifference(
                "duplicate_evidence",
                Compatibility.INCOMPATIBLE,
                "same raw run cannot be counted twice",
            )
        )
    if not differences:
        for dimension in projections[0]:
            if dimension == "random_seed" and allow_seed_variation:
                continue
            values = {json_bytes(projection[dimension]) for projection in projections}
            if len(values) > 1:
                disposition = (
                    Compatibility.REQUIRES_STRATIFICATION
                    if dimension in _STRATIFIABLE
                    else Compatibility.INCOMPATIBLE
                )
                differences.append(
                    DatasetDifference(dimension, disposition, "recorded conditions differ")
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
    return DatasetReport(
        1,
        state,
        tuple(digests),
        tuple(differences),
        tuple(tuple(group) for group in groups.values()),
        allow_seed_variation,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--protocol-version", required=True)
    parser.add_argument("--allow-seed-variation", action="store_true")
    args = parser.parse_args()
    report = validate_dataset(
        tuple(DatasetMember(path, args.protocol_version) for path in args.directories),
        allow_seed_variation=args.allow_seed_variation,
    )
    print(json_bytes(asdict(report)).decode("ascii"))
    return 0 if report.compatibility == Compatibility.COMPATIBLE else 1


if __name__ == "__main__":
    raise SystemExit(main())

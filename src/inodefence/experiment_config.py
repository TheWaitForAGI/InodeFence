"""Explicit, versioned comparison configuration; no results or OS attestation."""

import base64
import binascii
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256

from inodefence.campaign import CampaignConfig, CampaignResult, run_campaign
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ArchiveCase
from inodefence.model.provenance import ExecutionSafety, TargetProvenance
from inodefence.provenance import sentinel_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets import CampaignTarget

SEED_PROFILE = "minimal-generic-v1"
MUTATION_POLICY = "uniform-generic-v1"
FEEDBACK_POLICY = "state-v2-or-violation-v1-uniform-parent-v1"


def _object(value: object, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"object requires exactly these fields: {sorted(keys)}")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON field")
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON value: {value}")


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """All research-critical settings are explicit, without inferred defaults.

    Environment profile is an operator-specified stable setup label, not actual
    runtime identity. Source/platform facts belong to execution provenance. Initial
    case order matters; sentinel creation order is normalized by relative name.
    Only currently implemented search policies/profile are supported in v1.
    """

    target: TargetProvenance
    seed_profile: str
    initial_case_ids: tuple[str, ...]
    campaign: CampaignConfig
    mutation_policy: str
    feedback_policy: str
    sentinels: tuple[SentinelSpec, ...]
    environment_profile: str

    def __post_init__(self) -> None:
        if not isinstance(self.target, TargetProvenance) or not isinstance(
            self.campaign, CampaignConfig
        ):
            raise ValueError("target and campaign require canonical configuration types")
        if self.target.target_version.lower() in {"latest", "installed", "current"}:
            raise ValueError("target version must be explicit")
        if (self.seed_profile, self.mutation_policy, self.feedback_policy) != (
            SEED_PROFILE,
            MUTATION_POLICY,
            FEEDBACK_POLICY,
        ):
            raise ValueError("unsupported seed profile or mutation/feedback policy")
        if (
            not isinstance(self.environment_profile, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", self.environment_profile) is None
        ):
            raise ValueError("environment_profile requires a stable setup identifier")
        if (
            not isinstance(self.initial_case_ids, tuple)
            or not self.initial_case_ids
            or not all(
                isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
                for value in self.initial_case_ids
            )
            or len(set(self.initial_case_ids)) != len(self.initial_case_ids)
        ):
            raise ValueError("initial_case_ids must be a nonempty unique SHA-256 tuple")
        if self.campaign.execution_budget < len(self.initial_case_ids):
            raise ValueError("execution budget must cover initial cases")
        sentinel_provenance(self.sentinels)
        object.__setattr__(
            self, "sentinels", tuple(sorted(self.sentinels, key=lambda spec: spec.name))
        )

    def to_json(self) -> str:
        """Sorted-key ASCII JSON schema v1; canonical configuration ID input."""
        target = asdict(self.target)
        if self.target.timeout_seconds is not None:
            target["timeout_seconds"] = float(self.target.timeout_seconds)
        return json.dumps(
            {
                "schema_version": 1,
                "target": target,
                "seed_profile": self.seed_profile,
                "initial_case_ids": self.initial_case_ids,
                "campaign": asdict(self.campaign),
                "mutation_policy": self.mutation_policy,
                "feedback_policy": self.feedback_policy,
                "sentinels": [
                    {
                        "name": spec.name,
                        "content_base64": base64.b64encode(spec.content).decode("ascii"),
                        "mode": spec.mode,
                    }
                    for spec in self.sentinels
                ],
                "environment_profile": self.environment_profile,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    @property
    def config_id(self) -> str:
        return sha256(self.to_json().encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, text: str) -> "ExperimentConfig":
        """Reject missing/unknown/duplicate fields, nonfinite values and bad types."""
        value = _object(
            json.loads(
                text,
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            ),
            {
                "schema_version",
                "target",
                "seed_profile",
                "initial_case_ids",
                "campaign",
                "mutation_policy",
                "feedback_policy",
                "sentinels",
                "environment_profile",
            },
        )
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("unsupported experiment configuration schema")
        target = _object(
            value["target"], {"target_id", "target_version", "timeout_seconds", "execution_safety"}
        )
        campaign = _object(value["campaign"], {"random_seed", "execution_budget"})
        if not isinstance(value["initial_case_ids"], list) or not isinstance(
            value["sentinels"], list
        ):
            raise ValueError("initial_case_ids and sentinels must be JSON arrays")
        specs = []
        for raw in value["sentinels"]:
            raw = _object(raw, {"name", "content_base64", "mode"})
            try:
                if not isinstance(raw["content_base64"], str):
                    raise ValueError("sentinel content_base64 must be text")
                content = base64.b64decode(raw["content_base64"], validate=True)
            except (ValueError, binascii.Error) as error:
                raise ValueError("invalid sentinel base64 content") from error
            specs.append(SentinelSpec(raw["name"], content, raw["mode"]))
        return cls(
            TargetProvenance(
                target["target_id"],
                target["target_version"],
                target["timeout_seconds"],
                ExecutionSafety(target["execution_safety"]),
            ),
            value["seed_profile"],
            tuple(value["initial_case_ids"]),
            CampaignConfig(campaign["random_seed"], campaign["execution_budget"]),
            value["mutation_policy"],
            value["feedback_policy"],
            tuple(specs),
            value["environment_profile"],
        )


def run_configured_campaign(
    config: ExperimentConfig,
    initial_cases: Sequence[ArchiveCase],
    target: CampaignTarget,
) -> CampaignResult:
    """Validate binding before calling the unchanged bounded campaign engine.

    This does not select a target or silently supply seeds. The caller supplies
    both, matching the formal config. Existing execution-safety rejection applies.
    """
    cases = tuple(initial_cases)
    ids = tuple(case.case_id for case in cases)
    if ids != config.initial_case_ids or ids != tuple(
        case.case_id for case in minimal_seed_corpus()
    ):
        raise ValueError("seed cases/order do not match the configured profile and IDs")
    if target.provenance != config.target:
        raise ValueError("target configuration does not match experiment configuration")
    return run_campaign(
        cases,
        target,
        config.campaign,
        sentinels=config.sentinels,
        experiment_config_id=config.config_id,
    )

"""Versioned feedback-only projections; never alter observations or oracle inputs."""

from dataclasses import dataclass, replace
from enum import StrEnum

from inodefence.model import StateSignature


class FeedbackProjection(StrEnum):
    FULL = "state-v3-full-key-v1"
    A1 = "state-v3-no-identity-groups-key-v1"
    A2 = "state-v3-no-external-effects-key-v1"


@dataclass(frozen=True, slots=True)
class FeedbackKey:
    """Policy-tagged normalized key, separate from the full evidence signature."""

    projection: FeedbackProjection
    projected_signature: StateSignature

    def __post_init__(self) -> None:
        if not isinstance(self.projection, FeedbackProjection) or not isinstance(
            self.projected_signature, StateSignature
        ):
            raise ValueError("feedback key requires a supported projection and StateSignature")
        if self.projection == FeedbackProjection.A1 and self.projected_signature.identity_groups:
            raise ValueError("A1 key must exclude identity_groups")
        if self.projection == FeedbackProjection.A2 and self.projected_signature.external_effects:
            raise ValueError("A2 key must exclude external_effects")


def feedback_key(signature: StateSignature, projection: FeedbackProjection) -> FeedbackKey:
    if not isinstance(signature, StateSignature) or not isinstance(projection, FeedbackProjection):
        raise ValueError("feedback projection requires StateSignature and supported projection")
    if projection == FeedbackProjection.A1:
        projected = replace(signature, identity_groups=())
    elif projection == FeedbackProjection.A2:
        projected = replace(signature, external_effects=())
    else:
        projected = signature
    return FeedbackKey(projection, projected)

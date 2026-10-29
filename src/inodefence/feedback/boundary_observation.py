"""inodefence-boundary-attempt-v1 frame SET -> main M3.1 boundary-attempt feedback keys.

The rich effect path (node-tar's `FilesystemEffectEvent` inside an ordered `EffectEventTrace`)
exposes an ordered, entry-correlated completion boundary and derives the M3.1 boundary-approach
gradient from it. A second extractor need not expose that ordering: the decompress(JS)
feasibility probe found entries are recorded concurrently and reordered, with no entry context
on the filesystem operation, so an ordered trace cannot be reconstructed. The locked
`inodefence-boundary-attempt-v1` producer frame is the honest contract for what *is* observable:
a single JSON per extraction whose `attempts` is an **unordered SET**. Each attempt is one
boundary-relevant filesystem operation the producer observed through fs-level interposition --
which operation, where it wrote, the raw and resolved target, the regions, whether it aliased an
external object, and the realized outcome -- with no ordering or entry correlation.

This module maps that SET into the existing M3.1 `BoundaryAttemptSignature` feedback keys, so the
boundary-attempt gradient generalizes to any extractor that emits the frame. The frame is common
to node-tar (native emission) and decompress, so the mapping is **uniform**: the frame SET is the
only input, there is no per-target branch, and node-tar-native and decompress frames flow through
one path.

Strictly additive and target-agnostic. It consumes no `EffectEventTrace`, changes no existing
derivation, and produces the same `BOUNDARY_ESCAPE_ATTEMPT` key the trace path produces (reusing
the exact `_escape_shape` bucketing), so a frame attempt and the equivalent trace event land on
one key and the existing P3 consumption is unchanged. It is answer-agnostic: a key encodes only
the operation kind, the resolved region, the coarse outcome, and the bounded *escape shape* of
the raw target -- never the raw path, tail, the declared-protected marker, a sentinel, a CVE or a
PoC. Whether a reached object is the protected sentinel stays a C1/C2 oracle judgment, never
feedback. A key is boundary-approach evidence, never a C0/C1/C2 verdict and never a vulnerability.
"""

from dataclasses import dataclass
from typing import ClassVar

from inodefence.model import (
    BoundaryAttemptSignature,
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    EntryType,
    OperationOutcome,
    Region,
)

from .effect import _escape_shape
from .effect_novelty import EffectNoveltyDecision

# LOCKED inodefence-boundary-attempt-v1 vocabulary -> typed model values. This module is the
# single place the frame's string fields are interpreted.
_FRAME_OPERATION: dict[str, EntryType] = {
    "hardlink": EntryType.HARDLINK,
    "symlink": EntryType.SYMLINK,
    "regular": EntryType.REGULAR,
    "dir": EntryType.DIRECTORY,
}
_FRAME_REGION: dict[str, Region] = {
    "extraction": Region.EXTRACTION,
    "external": Region.EXTERNAL,
    "harness": Region.HARNESS,
}
# The frame coarsens the realized outcome to three classes; each maps to one distinct
# OperationOutcome so created/refused/io_error stay distinguishable keys (the gradient
# distinguishes outcomes). The frame intentionally drops the raw errno, so a refused attempt
# collapses to one canonical declined outcome regardless of ENOENT/EACCES/EINVAL.
_FRAME_OUTCOME: dict[str, OperationOutcome] = {
    "created": OperationOutcome.SUCCEEDED,
    "refused": OperationOutcome.ACCESS_DENIED,
    "io_error": OperationOutcome.OTHER_ERROR,
}


@dataclass(frozen=True, slots=True)
class BoundaryAttemptObservation:
    """One boundary attempt from the `inodefence-boundary-attempt-v1` frame, signature-ready.

    The honest SET unit. It carries only the fields the answer-agnostic
    `BoundaryAttemptSignature` needs: the operation kind, the raw target text (read only
    through the bounded escape shape), the region the target resolved to, and the realized
    outcome. No concrete path (`created_path` / `target_resolved_absolute`) enters it. The
    producer-side boundary decision -- `target_region != extraction` OR `created_region !=
    extraction` OR `aliases_external_object` -- decides WHICH frame attempts the producer
    surfaces; that decision and those fields stay in the frame producer, not here.
    """

    serialization_schema: ClassVar[int] = 1

    operation: EntryType
    target_raw: str
    target_region: Region
    outcome: OperationOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.operation, EntryType):
            raise ValueError("boundary attempt observation requires an EntryType operation")
        if not isinstance(self.target_raw, str):
            raise ValueError("boundary attempt observation requires a raw target string")
        if not isinstance(self.target_region, Region):
            raise ValueError("boundary attempt observation requires a target region")
        if not isinstance(self.outcome, OperationOutcome):
            raise ValueError("boundary attempt observation requires an operation outcome")


def boundary_attempt_observation_from_frame(
    attempt: dict[str, object],
) -> BoundaryAttemptObservation:
    """Parse one locked v1-frame attempt (raw strings) into a typed observation.

    Encodes the LOCKED `inodefence-boundary-attempt-v1` vocabulary -> model values. It reads only
    the signature-relevant fields (`operation`, `target_raw`, `target_region`, `outcome`);
    `created_path`, `created_region`, `target_resolved_absolute` and `aliases_external_object` are
    producer-side boundary-decision / diagnostic fields and never enter the answer-agnostic key.
    """

    def field(name: str) -> str:
        value = attempt.get(name)
        if not isinstance(value, str):
            raise ValueError(f"v1 frame attempt requires string field {name!r}")
        return value

    try:
        operation = _FRAME_OPERATION[field("operation")]
        target_region = _FRAME_REGION[field("target_region")]
        outcome = _FRAME_OUTCOME[field("outcome")]
    except KeyError as error:
        raise ValueError(f"unknown inodefence-boundary-attempt-v1 enum value: {error}") from error
    return BoundaryAttemptObservation(operation, field("target_raw"), target_region, outcome)


def _boundary_sort_key(key: EffectFeedbackKey) -> tuple[object, ...]:
    # Every key this module builds is a BOUNDARY_ESCAPE_ATTEMPT over a BoundaryAttemptSignature,
    # so narrowing to it gives a total, deterministic order.
    signature = key.signature
    assert isinstance(signature, BoundaryAttemptSignature)
    return signature.sort_key()


def boundary_attempt_keys_from_observations(
    observations: tuple[BoundaryAttemptObservation, ...],
) -> tuple[EffectFeedbackKey, ...]:
    """Map frame boundary attempts into main M3.1 `BOUNDARY_ESCAPE_ATTEMPT` keys.

    The SET analogue of `feedback.effect.boundary_attempt_keys`. An attempt whose target resolved
    outside the extraction root (`target_region != EXTRACTION`) and whose raw target lexically
    escapes (a bounded escape shape) yields one `BoundaryAttemptSignature(operation,
    target_region, outcome, escape_shape)`; an attempt with an in-root target or no escaping shape
    yields nothing, exactly as the trace derivation skips them. Duplicate attempts collapse to one
    key, and the result is in the same canonical order the trace path uses.

    Uniform across extractors: the frame SET is the only input, so node-tar-native and decompress
    frames map through one path with no per-target branch. Answer-agnostic: the key encodes the
    bounded escape SHAPE of `target_raw` (never the raw path, tail, sentinel, CVE or PoC), the
    operation kind, the resolved region and the coarse outcome. It reuses the exact `_escape_shape`
    bucketing the trace path uses, so a frame attempt and the equivalent trace event land on one
    key. Like the trace keys it assumes nothing about termination; the caller gates on a cleanly
    recorded frame.
    """
    if not isinstance(observations, tuple) or not all(
        isinstance(observation, BoundaryAttemptObservation) for observation in observations
    ):
        raise ValueError("observations must be a tuple of BoundaryAttemptObservation")
    keys: set[EffectFeedbackKey] = set()
    for observation in observations:
        if observation.target_region == Region.EXTRACTION:
            continue
        shape = _escape_shape(observation.target_raw)
        if shape is None:
            continue
        keys.add(
            EffectFeedbackKey(
                EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT,
                BoundaryAttemptSignature(
                    observation.operation, observation.target_region, observation.outcome, shape
                ),
            )
        )
    return tuple(sorted(keys, key=_boundary_sort_key))


class FrameBoundaryNoveltyIndex:
    """Standalone novelty admission for frame-derived boundary-attempt keys.

    Mirrors `EffectNoveltyIndex`'s key-level admission (a novel key is admitted; additive) but is
    fed by the frame SET instead of an `EffectEventTrace`, so it admits the boundary-attempt
    gradient uniformly for any extractor that emits the v1 frame (node-tar native, decompress)
    with no per-target branch and no trace. It does not import or modify the trace-driven index.

    This is the boundary-attempt arm -- the same research-honesty judgment point as
    `EffectNoveltyIndex(include_boundary_attempt=True)`: deriving the key from a cleanly recorded
    *rejected* attempt is the one relaxation, and activating it as a live reward channel is
    human-review-gated. The caller gates frame eligibility (a frame is emitted only for a cleanly
    recorded extraction), exactly as the trace functions assume nothing about termination.
    """

    def __init__(self) -> None:
        self._keys: set[EffectFeedbackKey] = set()

    @property
    def keys(self) -> frozenset[EffectFeedbackKey]:
        return frozenset(self._keys)

    def observe(
        self, observations: tuple[BoundaryAttemptObservation, ...]
    ) -> EffectNoveltyDecision:
        keys = boundary_attempt_keys_from_observations(observations)
        new = tuple(key for key in keys if key not in self._keys)
        self._keys.update(keys)
        return EffectNoveltyDecision(new, bool(new), True)
